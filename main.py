from gevent import monkey
monkey.patch_all(thread=False)

import os
import sys
import time
import json
import threading
import subprocess
import re
import platform
import zipfile
import random
import importlib.util
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog
import uuid
import shutil
import datetime
import eel
from concurrent.futures import ThreadPoolExecutor

# Import our custom downloader
import downloader
import gpu_engine
from platform_utils import (
    command_exists,
    ffmpeg_encoder_runtime_works,
    ffmpeg_supports_encoder,
    find_font_file,
    get_creationflags,
    list_system_fonts,
    open_path,
    reveal_in_file_manager,
)

try:
    from stocky_nonstop.frame_composer import composer_api
except ImportError as e:
    print(f"Warning: frame_composer modules could not be imported: {e}")

try:
    from stocky_nonstop.timing import timing_api  # noqa: F401
except ImportError as e:
    print(f"Warning: timing_api module could not be imported: {e}")

try:
    from voicer import voicer_backend # noqa: F401
except ImportError as e:
    print(f"Warning: voicer module could not be imported: {e}")

# === ДОБАВЛЯЕМ ЭТОТ БЛОК: ===
try:
    import prompter_backend
except ImportError as e:
    print(f"Warning: prompter_backend could not be imported: {e}")
# ============================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'web')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')
DEFAULT_DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')
LOG_FILE = os.path.join(BASE_DIR, 'stocky.log')

# --- Файловый лог ---
_log_lock = threading.Lock()

def _write_log(message, lvl="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{lvl}] {message}\n"
    try:
        with _log_lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
            # Ротация: если лог > 5 МБ — обрезаем начало
            if os.path.getsize(LOG_FILE) > 5 * 1024 * 1024:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-5000:])
    except Exception:
        pass

# --- Telegram уведомления ---
_tg_last_sent = {"time": 0}
_TG_RATE_LIMIT = 5  # минимум 5 сек между сообщениями

def _send_telegram(message, silent=False):
    config = load_config()
    token = (config.get("telegram_bot_token") or "").strip()
    chat_id = (config.get("telegram_chat_id") or "").strip()
    if not token or not chat_id:
        return
    now = time.time()
    if now - _tg_last_sent["time"] < _TG_RATE_LIMIT:
        return
    _tg_last_sent["time"] = now
    hostname = platform.node() or "unknown"
    text = f"[{hostname}] {message}"
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if silent:
            payload["disable_notification"] = True
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        _write_log(f"TG send failed: {e}", "WARN")

def _tg_event(event_type, tab_name="", detail=""):
    """Отправляет ключевые события в Telegram для мониторинга."""
    short = tab_name[:20] if tab_name else "?"
    if event_type == "app_start":
        _send_telegram("🟢 <b>StockyNonStop запущен</b>")
    elif event_type == "app_close":
        _send_telegram("🔴 <b>StockyNonStop закрыт</b>")
    elif event_type == "download_start":
        _send_telegram(f"⬇️ Скачивание: <b>{short}</b> — {detail}", silent=True)
    elif event_type == "download_done":
        _send_telegram(f"✅ Скачано: <b>{short}</b> — {detail}", silent=True)
    elif event_type == "download_error":
        _send_telegram(f"❌ Ошибка скачивания: <b>{short}</b> — {detail}")
    elif event_type == "render_start":
        _send_telegram(f"🎬 Рендер: <b>{short}</b> — {detail}", silent=True)
    elif event_type == "render_done":
        _send_telegram(f"✅ Рендер завершён: <b>{short}</b> — {detail}", silent=True)
    elif event_type == "render_error":
        _send_telegram(f"❌ Ошибка рендера: <b>{short}</b> — {detail}")
    elif event_type == "render_stuck":
        _send_telegram(f"⚠️ РЕНДЕР ЗАВИС: <b>{short}</b> — {detail} (watchdog сбросил)")
    elif event_type == "merge_done":
        _send_telegram(f"🔗 Склейка: <b>{short}</b> — {detail}", silent=True)

DEFAULT_CLIP_RULES = [
    {"from": 0.0, "to": 60.0, "mode": "random", "durationMin": 2.0, "durationMax": 4.0},
    {"from": 60.0, "to": None, "mode": "random", "durationMin": 3.0, "durationMax": 6.0},
]



eel.init(WEB_DIR)

# Global state
tab_queues = {} # { tab_id: list of dicts }
tab_stop_flags = {} # { tab_id: bool } for downloads
tab_render_stop_flags = {} # { tab_id: bool } for renders

active_downloads_lock = threading.Lock()
active_download_tabs = set()
API_KEY_ROTATION_STATE = {"pexels": 0, "pixabay": 0}
API_KEY_ROTATION_LOCK = threading.Lock()

# [NEW] Глобальная очередь рендера
GLOBAL_RENDER_LOCK = threading.Lock()
ACTIVE_RENDER_TAB = None
ACTIVE_RENDER_TAB_NAME = None
RENDER_WAIT_QUEUE = []
render_lock_mutex = threading.Lock()

def try_acquire_render_slot(tab_id, tab_name):
    """[NEW] Пытается занять глобальный слот рендера"""
    global ACTIVE_RENDER_TAB, ACTIVE_RENDER_TAB_NAME
    with render_lock_mutex:
        if ACTIVE_RENDER_TAB is None:
            ACTIVE_RENDER_TAB = tab_id
            ACTIVE_RENDER_TAB_NAME = tab_name
            _notify_render_status_update()
            return True
        elif ACTIVE_RENDER_TAB == tab_id:
            return True
        return False

def add_to_wait_queue(tab_id, tab_name, kwargs):
    """[NEW] Добавляет вкладку в очередь ожидания"""
    global RENDER_WAIT_QUEUE
    with render_lock_mutex:
        remove_from_wait_queue_internal(tab_id) # Избегаем дублей
        RENDER_WAIT_QUEUE.append({"id": tab_id, "name": tab_name, "kwargs": kwargs})
        pos = len(RENDER_WAIT_QUEUE)
        _notify_render_status_update()
        return pos

def remove_from_wait_queue_internal(tab_id):
    """[NEW] Внутренняя функция без лока (для использования внутри mutex)"""
    global RENDER_WAIT_QUEUE
    RENDER_WAIT_QUEUE = [item for item in RENDER_WAIT_QUEUE if item['id'] != tab_id]

def remove_from_wait_queue(tab_id):
    """[NEW] Удаляет из очереди"""
    with render_lock_mutex:
        remove_from_wait_queue_internal(tab_id)
        _notify_render_status_update()

def _notify_render_status_update():
    """[NEW] Отправляет в JS статус глобальной очереди"""
    waiting_names = [f"{item['name']} (позиция {i+1})" for i, item in enumerate(RENDER_WAIT_QUEUE)]
    safe_eel_call("update_global_render_status", {
        "active": ACTIVE_RENDER_TAB_NAME,
        "waiting": waiting_names
    })

def release_render_slot(tab_id):
    """[NEW] Освобождает слот и запускает следующего в очереди"""
    global ACTIVE_RENDER_TAB, ACTIVE_RENDER_TAB_NAME, RENDER_WAIT_QUEUE
    with render_lock_mutex:
        if ACTIVE_RENDER_TAB == tab_id:
            ACTIVE_RENDER_TAB = None
            ACTIVE_RENDER_TAB_NAME = None
            if RENDER_WAIT_QUEUE:
                next_item = RENDER_WAIT_QUEUE.pop(0)
                ACTIVE_RENDER_TAB = next_item['id']
                ACTIVE_RENDER_TAB_NAME = next_item['name']
                _notify_render_status_update()
                
                # Запускаем отложенный рендер
                kwargs = next_item['kwargs']
                def start_next():
                    thread = threading.Thread(
                        target=render_worker,
                        kwargs=kwargs,
                        daemon=True
                    )
                    thread.start()
                threading.Thread(target=start_next, daemon=True).start()
            else:
                _notify_render_status_update()

# ═══════════════════════════════════════════════════════════
#  Render State Manager — единый источник правды + watchdog
# ═══════════════════════════════════════════════════════════
_render_state_lock = threading.Lock()
RENDER_STATES = {}  # { tab_id: { "status": str, "started_at": float, "last_progress_at": float, "tab_name": str } }
RENDER_WATCHDOG_INTERVAL = 30  # проверяем каждые 30 сек
RENDER_STUCK_TIMEOUT = 120     # если нет прогресса 120 сек — сбрасываем

def _render_state_set(tab_id, status, tab_name=""):
    """Обновляет состояние рендера для вкладки."""
    with _render_state_lock:
        now = time.time()
        if tab_id not in RENDER_STATES:
            RENDER_STATES[tab_id] = {}
        RENDER_STATES[tab_id]["status"] = status
        RENDER_STATES[tab_id]["last_progress_at"] = now
        RENDER_STATES[tab_id]["tab_name"] = tab_name
        if status == "rendering":
            RENDER_STATES[tab_id]["started_at"] = now

def _render_state_touch(tab_id):
    """Обновляет время последнего прогресса (вызывается при update_render_progress)."""
    with _render_state_lock:
        if tab_id in RENDER_STATES:
            RENDER_STATES[tab_id]["last_progress_at"] = time.time()

def _render_state_get(tab_id):
    with _render_state_lock:
        return RENDER_STATES.get(tab_id, None)

def _render_state_remove(tab_id):
    with _render_state_lock:
        RENDER_STATES.pop(tab_id, None)

def _render_watchdog():
    """Фоновый поток: сбрасывает зависший рендер если нет прогресса > RENDER_STUCK_TIMEOUT сек."""
    while True:
        time.sleep(RENDER_WATCHDOG_INTERVAL)
        now = time.time()
        stuck_tabs = []
        with _render_state_lock:
            for tab_id, state in list(RENDER_STATES.items()):
                if state.get("status") == "rendering":
                    elapsed = now - state.get("last_progress_at", state.get("started_at", now))
                    if elapsed > RENDER_STUCK_TIMEOUT:
                        stuck_tabs.append((tab_id, state.get("tab_name", "?"), int(elapsed)))

        for tab_id, tab_name, elapsed in stuck_tabs:
            _write_log(f"WATCHDOG: рендер вкладки '{tab_name}' завис ({elapsed}s без прогресса) — принудительный сброс", "ERROR")
            _tg_event("render_stuck", tab_name=tab_name, detail=f"нет прогресса {elapsed}с")
            # Сбрасываем состояние
            _render_state_set(tab_id, "stuck_reset", tab_name)
            # Гарантированно отправляем render_batch_complete в UI
            safe_eel_call("render_batch_complete", tab_id, 0, 0, 1)
            safe_eel_call("add_render_log", tab_id, f"⚠️ WATCHDOG: рендер принудительно сброшен (завис на {elapsed}с)", "error")
            # Освобождаем слот
            release_render_slot(tab_id)

# Запускаем watchdog при старте
threading.Thread(target=_render_watchdog, daemon=True).start()


def safe_eel_call(func_name, *args):
    """Безопасный вызов Eel. Логирует ошибки вместо молчаливого проглатывания."""
    try:
        def _execute():
            try:
                func = getattr(eel, func_name, None)
                if func:
                    func(*args)
                else:
                    _write_log(f"safe_eel_call: function '{func_name}' not found", "WARN")
            except Exception as e:
                err_str = str(e)[:200]
                _write_log(f"safe_eel_call('{func_name}') failed: {err_str}", "WARN")
                # Если это критический вызов для рендера — пробуем гарантировать сброс UI
                if func_name == "render_batch_complete":
                    _write_log("CRITICAL: render_batch_complete failed via eel — UI may be stuck", "ERROR")
                    _tg_event("render_stuck", detail=f"eel failed: render_batch_complete ({err_str})")

        import gevent
        gevent.spawn(_execute)
    except Exception as e:
        _write_log(f"safe_eel_call: gevent spawn failed for '{func_name}': {e}", "ERROR")

def update_single_item(tab_id, idx):
    """Отправляет в JS только 1 элемент, а не всю очередь."""
    try:
        queue = get_tab_queue(tab_id)
        if 0 <= idx < len(queue):
            item = queue[idx]
            compact = {
                "id": item.get("id", ""),
                "status": item.get("status", "Pending"),
                "progress": item.get("progress", 0),
                "path": item.get("path", ""),
                "speed": item.get("speed", "")
            }
            safe_eel_call("update_single_queue_item", tab_id, idx, compact)
    except Exception:
        pass

def get_tab_queue(tab_id):
    if tab_id not in tab_queues:
        tab_queues[tab_id] = []
    return tab_queues[tab_id]

def load_config():
    if not os.path.exists(CONFIG_FILE):
        template = {
            "pexels_api_key": "ВСТАВЬ_СВОЙ_КЛЮЧ",
            "pixabay_api_key": "ВСТАВЬ_СВОЙ_КЛЮЧ",
            "pexels_api_keys": [],
            "pixabay_api_keys": []
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=4, ensure_ascii=False)
        return None
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return None


def collect_runtime_diagnostics():
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    diagnostics = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "ffmpeg": {
            "available": bool(ffmpeg_path),
            "path": ffmpeg_path or "",
        },
        "ffprobe": {
            "available": bool(ffprobe_path),
            "path": ffprobe_path or "",
        },
        "tkinter": {"available": True, "error": ""},
        "packages": {},
    }

    for package_name in ["eel", "gevent", "requests", "docx", "whisper", "torch"]:
        diagnostics["packages"][package_name] = importlib.util.find_spec(package_name) is not None

    if command_exists("ffmpeg"):
        try:
            diagnostics["ffmpeg"]["videotoolbox"] = ffmpeg_supports_encoder("h264_videotoolbox")
        except Exception as e:
            diagnostics["ffmpeg"]["videotoolbox"] = False
            diagnostics["ffmpeg"]["encoder_probe_error"] = str(e)
    else:
        diagnostics["ffmpeg"]["videotoolbox"] = False

    try:
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
    except Exception as e:
        diagnostics["tkinter"] = {"available": False, "error": str(e)}

    return diagnostics


@eel.expose
def get_runtime_diagnostics():
    return collect_runtime_diagnostics()

def log_to_js(tab_id, message, type="info"):
    """Неблокирующий вызов — спавним отдельный гринлет с таймаутом.
    Если WebSocket занят/мёртв — НЕ блокирует воркер.
    Также пишет в файл-лог и шлёт ошибки в Telegram."""
    # Файловый лог — всегда
    _write_log(message, type.upper())

    # Telegram — только ошибки
    if type == "error":
        threading.Thread(target=_send_telegram, args=(message,), daemon=True).start()

    # Eel UI
    try:
        import gevent
        def _send():
            try:
                with gevent.Timeout(3):
                    eel.add_log_entry(tab_id, message, type)
            except Exception:
                pass
        gevent.spawn(_send)
    except Exception:
        pass

def update_ui_queue(tab_id):
    """Неблокирующий вызов — спавним отдельный гринлет с таймаутом.
    Если WebSocket занят/мёртв — НЕ блокирует воркер."""
    try:
        import gevent
        snapshot = list(get_tab_queue(tab_id))
        def _send():
            try:
                with gevent.Timeout(3):
                    eel.update_queue(tab_id, snapshot)
            except Exception:
                pass
        gevent.spawn(_send)
    except Exception:
        pass

@eel.expose
def get_queue_snapshot(tab_id):
    """JS polling endpoint — фронтенд сам спрашивает статус очереди."""
    return get_tab_queue(tab_id)

@eel.expose
def get_config():
    defaults = {
        "pexels_api_key": "",
        "pixabay_api_key": "",
        "pexels_api_keys": [],
        "pixabay_api_keys": [],
        "deepseek_api_key": "",
        "openrouter_api_key": "",
        "gemini_api_key": "",
        "elevenlabs_api_key": "",
        "ai_provider": "deepseek",
        "deepseek_model": "deepseek-v4-flash",
        "openrouter_model": "openai/gpt-5.4-nano",
        "gemini_model": "gemini-3.5-flash",
        "telegram_bot_token": "",
        "telegram_chat_id": ""
    }
    config = load_config() or {}
    changed = False
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
            changed = True
    if changed:
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except:
            pass
    return config

def get_provider_api_keys(config, provider, rotation_seed=0):
    primary_key_name = f"{provider}_api_key"
    list_key_name = f"{provider}_api_keys"

    raw_keys = []
    primary = (config.get(primary_key_name) or "").strip()
    if primary and primary != "ВСТАВЬ_СВОЙ_КЛЮЧ":
        raw_keys.append(primary)

    for value in config.get(list_key_name, []) or []:
        key = str(value or "").strip()
        if key and key != "ВСТАВЬ_СВОЙ_КЛЮЧ":
            raw_keys.append(key)

    keys = []
    seen = set()
    for key in raw_keys:
        if key not in seen:
            seen.add(key)
            keys.append(key)

    if not keys:
        return []

    offset = int(rotation_seed or 0) % len(keys)
    return keys[offset:] + keys[:offset]


def _normalize_api_key_list(value):
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    result = []
    seen = set()
    for item in value:
        key = str(item or "").strip()
        if not key or key == "ВСТАВЬ_СВОЙ_КЛЮЧ" or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _get_provider_api_keys(config, provider):
    plural_key = f"{provider}_api_keys"
    single_key = f"{provider}_api_key"
    keys = _normalize_api_key_list(config.get(plural_key))
    single = str(config.get(single_key, "") or "").strip()
    if single and single != "ВСТАВЬ_СВОЙ_КЛЮЧ" and single not in keys:
        keys.insert(0, single)
    return keys


def _get_rotated_provider_api_keys(config, provider):
    keys = _get_provider_api_keys(config, provider)
    if len(keys) <= 1:
        return keys
    with API_KEY_ROTATION_LOCK:
        start = API_KEY_ROTATION_STATE.get(provider, 0) % len(keys)
    return keys[start:] + keys[:start]


def _mark_provider_key_used(config, provider, used_key):
    keys = _get_provider_api_keys(config, provider)
    if not keys or used_key not in keys:
        return
    with API_KEY_ROTATION_LOCK:
        API_KEY_ROTATION_STATE[provider] = (keys.index(used_key) + 1) % len(keys)

@eel.expose
def load_app_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                 return json.load(f)
        except: pass
    return {}

@eel.expose
def save_app_settings(new_settings):
    settings = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                 settings = json.load(f)
        except: pass
    settings.update(new_settings)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
         json.dump(settings, f, indent=4, ensure_ascii=False)

@eel.expose
def get_gpu_info():
    gpu_info = gpu_engine.get_gpu_info()
    return {
        "name": gpu_info.get("name", "Неизвестный GPU"),
        "type": gpu_info.get("type", "cpu"),
    }

@eel.expose
def save_config(tab_id, new_config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_config, f, indent=4, ensure_ascii=False)
    log_to_js(tab_id, "Настройки сохранены в config.json", "success")

@eel.expose
def clear_all_queues():
    global RENDER_WAIT_QUEUE
    RENDER_WAIT_QUEUE = []
    print("[PY] All queues cleared.")

@eel.expose
def get_overlay_frames():
    overlay_dir = os.path.join(BASE_DIR, "OverLay")
    if not os.path.exists(overlay_dir):
        return []
    frames = [os.path.splitext(f)[0] for f in os.listdir(overlay_dir) if f.lower().endswith('.png')]
    return frames

@eel.expose
def clear_queue_backend(tab_id):
    tab_queues[tab_id] = []
    log_to_js("Очередь очищена.", "success")
    update_ui_queue(tab_id)

@eel.expose
def sync_queue(tab_id, new_queue):
    tab_queues[tab_id] = new_queue
    update_ui_queue(tab_id)

# --- RENDER PANEL LOGIC ---

@eel.expose
def start_render(tab_id, items, trim_start, trim_end, fmt, quality):
    tab_render_stop_flags[tab_id] = False
    
    # Check if FFmpeg is installed
    if not shutil.which("ffmpeg"):
        log_to_js(tab_id, "FFmpeg не найден в системе! Установите FFmpeg и добавьте его в PATH.", "error")
        eel.render_complete(tab_id, 0, 0)
        return
    if not shutil.which("ffprobe"):
        log_to_js(tab_id, "FFprobe не найден в системе! Установите FFmpeg и добавьте его в PATH.", "error")
        eel.render_complete(tab_id, 0, 0)
        return

    print(f"[PY][start_render_batch] Запускаю поток render_worker...")
    thread = threading.Thread(
        target=render_worker,
        args=(tab_id, items, trim_start, trim_end, fmt, quality),
        daemon=True
    )
    thread.start()

def get_video_duration(path):
    """Get video duration using ffprobe"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ]
        creationflags_val = get_creationflags()
            
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=10,
            creationflags=creationflags_val
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0

def _format_clip_value(value):
    if value is None:
        return "null"
    return f"{float(value):.3f}".rstrip('0').rstrip('.')

def _format_rule_label(rule):
    return f"{_format_clip_value(rule['from'])}-{_format_clip_value(rule['to'])}"

def normalize_clip_rules(rules):
    if not isinstance(rules, list) or not rules:
        rules = DEFAULT_CLIP_RULES

    normalized = []
    errors = []

    for idx, raw_rule in enumerate(rules):
        if not isinstance(raw_rule, dict):
            errors.append(f"[validation error] rule[{idx}]: invalid rule payload")
            continue

        mode = raw_rule.get("mode")
        if mode not in ("fixed", "random"):
            errors.append(f"[validation error] rule[{idx}]: mode must be 'fixed' or 'random'")
            continue

        try:
            rule_from = float(raw_rule.get("from"))
        except (TypeError, ValueError):
            errors.append(f"[validation error] rule[{idx}]: from is required")
            continue

        raw_to = raw_rule.get("to")
        rule_to = None
        if raw_to is not None:
            try:
                rule_to = float(raw_to)
            except (TypeError, ValueError):
                errors.append(f"[validation error] rule[{idx}]: to must be a number or null")
                continue

        rule = {"from": rule_from, "to": rule_to, "mode": mode}

        if rule_to is not None and rule_from >= rule_to:
            errors.append(f"[validation error] rule[{idx}]: from={_format_clip_value(rule_from)} must be less than to={_format_clip_value(rule_to)}")

        if mode == "fixed":
            raw_duration = raw_rule.get("duration")
            try:
                duration = float(raw_duration)
                rule["duration"] = duration
            except (TypeError, ValueError):
                errors.append(f"[validation error] rule[{idx}]: duration is required for fixed mode")
                duration = None

            if duration is not None and (duration < 0.1 or duration > 6.0):
                errors.append(f"[validation error] rule[{idx}]: duration={_format_clip_value(duration)} is outside 0.1-6.0")
        else:
            raw_min = raw_rule.get("durationMin")
            raw_max = raw_rule.get("durationMax")
            try:
                duration_min = float(raw_min)
                rule["durationMin"] = duration_min
            except (TypeError, ValueError):
                errors.append(f"[validation error] rule[{idx}]: durationMin is required for random mode")
                duration_min = None

            try:
                duration_max = float(raw_max)
                rule["durationMax"] = duration_max
            except (TypeError, ValueError):
                errors.append(f"[validation error] rule[{idx}]: durationMax is required for random mode")
                duration_max = None

            if duration_min is not None and duration_min < 0.1:
                errors.append(f"[validation error] rule[{idx}]: durationMin={_format_clip_value(duration_min)} is below 0.1")
            if duration_max is not None and duration_max > 6.0:
                errors.append(f"[validation error] rule[{idx}]: durationMax={_format_clip_value(duration_max)} exceeds limit of 6.0")
            if duration_min is not None and duration_max is not None and duration_min > duration_max:
                errors.append(f"[validation error] rule[{idx}]: durationMin={_format_clip_value(duration_min)} exceeds durationMax={_format_clip_value(duration_max)}")

        normalized.append(rule)

    normalized.sort(key=lambda rule: rule["from"])

    for idx in range(len(normalized) - 1):
        current = normalized[idx]
        nxt = normalized[idx + 1]
        current_to = current["to"]
        if current_to is None or nxt["from"] < current_to:
            errors.append(
                f"[validation error] rule[{idx}] and rule[{idx + 1}] overlap: "
                f"{_format_rule_label(current)} and {_format_rule_label(nxt)}"
            )

    if errors:
        raise ValueError("\n".join(errors))

    return normalized

def _find_rule_for_position(rules, position):
    for rule in rules:
        rule_to = rule["to"]
        if position >= rule["from"] and (rule_to is None or position < rule_to):
            return rule
    return None

def _pick_clip_duration(rule):
    if rule["mode"] == "fixed":
        return float(rule["duration"])
    return random.uniform(float(rule["durationMin"]), float(rule["durationMax"]))

def _clip_rule_bounds(rule):
    if rule["mode"] == "fixed":
        duration = float(rule["duration"])
        return duration, duration
    return float(rule["durationMin"]), float(rule["durationMax"])

def build_clip_plan_for_count(count, clip_rules):
    rules = normalize_clip_rules(clip_rules)
    clips = []
    position = 0.0

    for idx in range(count):
        rule = _find_rule_for_position(rules, position)
        if rule is None:
            raise ValueError(
                f"[validation error] no clip rule covers prompt index {idx + 1} at position={_format_clip_value(position)}s"
            )

        clip_duration = _pick_clip_duration(rule)
        if clip_duration < 0.1:
            raise ValueError(
                f"[validation error] generated clip duration below minimum at prompt index {idx + 1}"
            )

        clip = {
            "start": round(position, 3),
            "duration": round(clip_duration, 3),
            "rule": {
                "from": rule["from"],
                "to": rule["to"],
                "mode": rule["mode"],
                "duration": rule.get("duration"),
                "durationMin": rule.get("durationMin"),
                "durationMax": rule.get("durationMax"),
            },
        }
        clips.append(clip)
        position += clip_duration

    return clips

def _remaining_duration_bounds(rules, start_position, remaining_count):
    min_position = float(start_position)
    max_position = float(start_position)
    min_total = 0.0
    max_total = 0.0

    for _ in range(remaining_count):
        min_rule = _find_rule_for_position(rules, min_position)
        max_rule = _find_rule_for_position(rules, max_position)
        if min_rule is None or max_rule is None:
            raise ValueError("[validation error] clip rules do not cover the full target duration")

        min_duration, _ = _clip_rule_bounds(min_rule)
        _, max_duration = _clip_rule_bounds(max_rule)
        min_total += min_duration
        max_total += max_duration
        min_position += min_duration
        max_position += max_duration

    return min_total, max_total

def _choose_targeted_duration(rules, position, remaining_after, target_remaining, fallback_rule):
    rule_min, rule_max = _clip_rule_bounds(fallback_rule)
    feasible_low = rule_min
    feasible_high = rule_max

    samples = 120
    found = []
    for step in range(samples + 1):
        candidate = rule_min + (rule_max - rule_min) * (step / samples)
        try:
            min_after, max_after = _remaining_duration_bounds(rules, position + candidate, remaining_after)
        except ValueError:
            continue
        left_after = target_remaining - candidate
        if min_after - 0.001 <= left_after <= max_after + 0.001:
            found.append(candidate)

    if not found:
        raise ValueError("[duration plan] cannot keep the remaining clips inside the target duration")

    feasible_low = min(found)
    feasible_high = max(found)

    if fallback_rule["mode"] == "fixed":
        return feasible_low
    return random.uniform(feasible_low, feasible_high)

def build_clip_plan_for_target_duration(count, clip_rules, target_duration):
    rules = normalize_clip_rules(clip_rules)
    count = int(count)
    target_duration = float(target_duration)

    if count <= 0:
        return []
    if target_duration <= 0:
        raise ValueError("[duration plan] target duration must be greater than zero")

    min_total, max_total = _remaining_duration_bounds(rules, 0.0, count)
    if target_duration < min_total - 0.001 or target_duration > max_total + 0.001:
        raise ValueError(
            "[duration plan] target duration is not reachable with current rules: "
            f"target={_format_clip_value(target_duration)}s, "
            f"possible={_format_clip_value(min_total)}-{_format_clip_value(max_total)}s"
        )

    durations = []
    position = 0.0
    for idx in range(count):
        rule = _find_rule_for_position(rules, position)
        if rule is None:
            raise ValueError(
                f"[validation error] no clip rule covers prompt index {idx + 1} at position={_format_clip_value(position)}s"
            )
        min_duration, max_duration = _clip_rule_bounds(rule)
        clip_duration = min_duration if min_duration == max_duration else random.uniform(min_duration, max_duration)
        durations.append(clip_duration)
        position += clip_duration

    def materialize():
        clips_local = []
        bounds_local = []
        pos = 0.0
        for idx, duration in enumerate(durations):
            rule = _find_rule_for_position(rules, pos)
            if rule is None:
                raise ValueError(
                    f"[validation error] no clip rule covers prompt index {idx + 1} at position={_format_clip_value(pos)}s"
                )
            min_duration, max_duration = _clip_rule_bounds(rule)
            duration = max(min_duration, min(max_duration, float(duration)))
            durations[idx] = duration
            clips_local.append((pos, duration, rule))
            bounds_local.append((min_duration, max_duration))
            pos += duration
        return clips_local, bounds_local, pos

    for _ in range(12):
        _, bounds, total = materialize()
        diff = target_duration - total
        if abs(diff) <= 0.0005:
            break
        if diff > 0:
            capacities = [max_duration - durations[idx] for idx, (_, max_duration) in enumerate(bounds)]
        else:
            capacities = [durations[idx] - min_duration for idx, (min_duration, _) in enumerate(bounds)]
        capacity_total = sum(max(0.0, cap) for cap in capacities)
        if capacity_total <= 0:
            raise ValueError("[duration plan] current rules have no room to match the target duration")
        if abs(diff) > capacity_total + 0.01:
            raise ValueError("[duration plan] target duration is not reachable after applying current rules")
        for idx, cap in enumerate(capacities):
            cap = max(0.0, cap)
            if cap <= 0:
                continue
            delta = diff * (cap / capacity_total)
            if diff > 0:
                delta = min(delta, cap)
            else:
                delta = -min(abs(delta), cap)
            durations[idx] += delta

    clips_raw, bounds, total = materialize()
    residual = target_duration - total
    if abs(residual) > 0.0005:
        for idx in reversed(range(count)):
            min_duration, max_duration = bounds[idx]
            if residual > 0:
                delta = min(residual, max_duration - durations[idx])
            else:
                delta = -min(abs(residual), durations[idx] - min_duration)
            if abs(delta) <= 0:
                continue
            durations[idx] += delta
            residual -= delta
            if abs(residual) <= 0.0005:
                break

    clips_raw, _, total = materialize()
    if abs(target_duration - total) > 0.01:
        raise ValueError(
            f"[duration plan] could not match target exactly: target={target_duration:.3f}s, result={total:.3f}s"
        )

    clips = []
    for position, clip_duration, rule in clips_raw:
        clips.append({
            "start": round(position, 3),
            "duration": round(clip_duration, 3),
            "rule": {
                "from": rule["from"],
                "to": rule["to"],
                "mode": rule["mode"],
                "duration": rule.get("duration"),
                "durationMin": rule.get("durationMin"),
                "durationMax": rule.get("durationMax"),
            },
        })

    correction = round(target_duration - sum(float(clip["duration"]) for clip in clips), 3)
    if clips and abs(correction) > 0:
        clips[-1]["duration"] = round(float(clips[-1]["duration"]) + correction, 3)
    return clips

def _parse_srt_timestamp(value):
    match = re.match(r"^\s*(\d+):(\d+):(\d+)[,.](\d+)\s*$", value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, millis = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis[:3].ljust(3, "0")) / 1000

def parse_srt_clip_plan(srt_path, count):
    if not srt_path or not os.path.exists(srt_path):
        raise ValueError("[srt plan] SRT file not found")

    with open(srt_path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()

    timings = re.findall(
        r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})",
        text
    )
    if len(timings) < count:
        raise ValueError(f"[srt plan] SRT has {len(timings)} blocks, but render queue has {count} videos")

    clips = []
    for idx, (start_raw, end_raw) in enumerate(timings[:count]):
        start = _parse_srt_timestamp(start_raw)
        end = _parse_srt_timestamp(end_raw)
        duration = end - start
        if duration <= 0:
            raise ValueError(f"[srt plan] block {idx + 1} has invalid duration")
        clips.append({
            "start": round(start, 3),
            "duration": round(duration, 3),
            "rule": {
                "from": round(start, 3),
                "to": round(end, 3),
                "mode": "srt",
                "duration": round(duration, 3),
                "durationMin": None,
                "durationMax": None,
            },
        })
    return clips

def build_render_clip_plan(count, clip_rules=None, duration_config=None):
    duration_config = duration_config if isinstance(duration_config, dict) else {}
    mode = duration_config.get("mode") or "rules"

    if mode == "srt":
        return parse_srt_clip_plan(duration_config.get("srtPath") or "", count), "SRT"

    if mode == "audio":
        target_duration = duration_config.get("targetSeconds")
        audio_path = duration_config.get("audioPath") or ""
        if (target_duration is None or str(target_duration).strip() == "") and audio_path:
            target_duration = get_video_duration(audio_path)
        try:
            target_duration = float(target_duration)
        except (TypeError, ValueError):
            raise ValueError("[duration plan] audio mode needs an audio file or target seconds")
        return build_clip_plan_for_target_duration(count, clip_rules or DEFAULT_CLIP_RULES, target_duration), f"audio {target_duration:.3f}s"

    return build_clip_plan_for_count(count, clip_rules or DEFAULT_CLIP_RULES), "rules"

def get_item_clip_metadata(item, index, clip_rules=None, total_items=None):
    clip_start = item.get("clip_start")
    clip_duration = item.get("clip_duration")
    clip_rule = item.get("clip_rule")

    if clip_start is not None and clip_duration is not None and clip_rule:
        return float(clip_start), float(clip_duration), clip_rule

    if total_items is None:
        total_items = index + 1

    clips = build_clip_plan_for_count(total_items, clip_rules or DEFAULT_CLIP_RULES)
    clip = clips[index]
    return clip["start"], clip["duration"], clip["rule"]

def build_ffmpeg_cmd(input_path, output_path, trim_start, exact_duration, fmt, quality, fps="24", keep_audio=False, gpu_mode="full_gpu", bitrate="8000", gpu_info=None, frame_enabled=True, frame_color="White"):
    if gpu_info is None:
        gpu_info = gpu_engine.get_gpu_info()

    cmd = ["ffmpeg", "-hide_banner", "-y"]
    use_hw_decode = gpu_mode == "full_gpu"
    use_hw_encode = gpu_mode in ("full_gpu", "cpu_gpu")

    # 🔥 ПРИНУДИТЕЛЬНОЕ АППАРАТНОЕ ДЕКОДИРОВАНИЕ (Читаем видео видюхой)
    if use_hw_decode and gpu_info.get("hwaccel"):
        cmd += ["-hwaccel", gpu_info["hwaccel"]]

    cmd += ["-i", input_path]
    frame_path = os.path.join(BASE_DIR, "OverLay", f"{frame_color}.png")
    frame_exists = frame_enabled and os.path.exists(frame_path)
    if frame_exists:
        cmd += ["-i", frame_path]

    # Точная обрезка
    if trim_start > 0:
        cmd += ["-ss", str(trim_start)]
    if exact_duration > 0:
        cmd += ["-t", f"{float(exact_duration):.3f}"]

    # 🔥 ВЫЖИМАЕМ ИЗ ВИДЕОКАРТЫ МАКСИМУМ
    encoder = gpu_info.get("encoder", "libx264") if use_hw_encode else "libx264"
    if encoder == "h264_nvenc":
        # Для NVIDIA: Динамический битрейт (CQ 20) — дает макс. скорость и качество
        cmd += ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "20", "-b:v", "0"]
    elif encoder == "h264_amf":
        # Для AMD: Аналог CQ для видеокарт Radeon
        cmd += ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20", "-qp_b", "20"]
    elif encoder == "h264_qsv":
        # Для Intel: Аппаратный QuickSync
        cmd += ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "20"]
    elif encoder == "h264_videotoolbox":
        # Для Apple Silicon: системный аппаратный энкодер macOS
        cmd += ["-c:v", "h264_videotoolbox", "-b:v", f"{bitrate}k"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "superfast", "-crf", "20"]

    scale_pad = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps={fps}"
    if frame_exists:
        filter_str = f"[0:v]{scale_pad},format=yuv420p[base];[1:v]scale=1920:1080,format=rgba[ovr];[base][ovr]overlay=0:0:format=auto[v]"
        cmd += ["-filter_complex", filter_str, "-map", "[v]"]
        if keep_audio:
            cmd += ["-map", "0:a?"]
        else:
            cmd += ["-an"]
    else:
        cmd += ["-filter:v", scale_pad]
        if not keep_audio:
            cmd += ["-an"]

    cmd += ["-pix_fmt", "yuv420p"]
    cmd += ["-avoid_negative_ts", "make_zero"]
    cmd += [output_path]
    return cmd

@eel.expose
def stop_render(tab_id):
    tab_render_stop_flags[tab_id] = True
    log_to_js(tab_id, "🛑 Пользователь отменил рендер. Остановка...", "error")
    # [NEW] Убираем из глобальной очереди
    remove_from_wait_queue(tab_id)

@eel.expose
def read_prompts_file(tab_id):
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(
        title="Выберите файл с промптами",
        filetypes=[("Prompt files", "*.txt *.docx *.md"), ("All files", "*.*")]
    )
    root.destroy()
    
    if not path: return ""
    
    try:
        if path.lower().endswith('.docx'):
            return extract_docx_text(path)
        else:
            for enc in ('utf-8-sig', 'utf-8', 'cp1251', 'latin-1'):
                try:
                    with open(path, 'r', encoding=enc) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    except Exception as e:
        log_to_js(tab_id, f"Ошибка чтения файла: {e}", "error")
        return ""

@eel.expose
def pick_local_videos_for_queue(tab_id):
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    paths = filedialog.askopenfilenames(
        title="Выберите видео для очереди рендера",
        filetypes=[
            ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mpeg *.mpg"),
            ("All files", "*.*")
        ]
    )
    root.destroy()

    if not paths:
        return 0

    queue = get_tab_queue(tab_id)
    existing_paths = {
        os.path.normcase(os.path.normpath(item.get("path", "")))
        for item in queue
        if item.get("path")
    }

    added_count = 0
    for path in paths:
        normalized = os.path.normcase(os.path.normpath(path))
        if normalized in existing_paths:
            continue

        filename = os.path.basename(path)
        queue.append({
            "id": uuid.uuid4().hex[:8],
            "prompt": filename,
            "status": "Done",
            "progress": 100,
            "path": path,
            "clip_start": 0,
            "clip_duration": 0,
            "clip_rule": None,
        })
        existing_paths.add(normalized)
        added_count += 1

    if added_count > 0:
        update_ui_queue(tab_id)
        log_to_js(tab_id, f"Добавлено локальных видео в очередь: {added_count}", "success")
    else:
        log_to_js(tab_id, "Все выбранные видео уже есть в очереди.", "info")

    return added_count

@eel.expose
def start_concat(tab_id, delete_after, open_folder_flag, additions=None):
    queue = get_tab_queue(tab_id)
    rendered_items = [item for item in queue if item.get('status') == 'Rendered']
    if not rendered_items:
        safe_eel_call("add_render_log", tab_id, "Нет файлов с расширением 'Rendered' для склейки!", "error")
        return
    
    import datetime
    default_name = f"merged_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    save_path = filedialog.asksaveasfilename(
        title="Сохранить финальное видео",
        initialfile=default_name,
        defaultextension=".mp4",
        filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
    )
    root.destroy()
    
    if not save_path:
        return

    thread = threading.Thread(
        target=merge_worker,
        args=(tab_id, rendered_items, save_path, delete_after, open_folder_flag, None, additions),
        daemon=True
    )
    thread.start()

def convert_srt_to_ass(srt_path, ass_path, font_name, font_size, color_bgr, outline_color_bgr, outline, margin_v, delay_sec=0.0, pos_y_pixels=900):
    """Превращает обычный SRT в ASS с ЯВНЫМИ координатами позиции (через \\pos)."""
    import re
    try:
        with open(srt_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    except:
        with open(srt_path, 'r', encoding='cp1251') as f:
            content = f.read()
    
    # 🔥 Alignment=2 (низ-центр). Координата Y задает линию, на которой СТОИТ текст.
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{color_bgr},&H000000FF,{outline_color_bgr},&H80000000,0,0,0,0,100,100,0,0,1,{outline},0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    blocks = re.split(r'\n\s*\n', content.strip())
    pos_x = 960  # центр по горизонтали
    pos_y = int(pos_y_pixels)
    
    for block in blocks:
        lines = [l for l in block.split('\n') if l.strip()]
        if len(lines) >= 3:
            time_line = lines[1]
            text = "\\N".join(lines[2:])
            text = re.sub(r'<[^>]+>', '', text)
            m = re.search(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
            if m:
                h1, m1, s1, ms1, h2, m2, s2, ms2 = m.groups()
                
                def shift_time(h, m, s, ms):
                    ts = int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0 + delay_sec
                    nh = int(ts // 3600)
                    nm = int((ts % 3600) // 60)
                    ns = int(ts % 60)
                    nms = int(round((ts - int(ts)) * 100))
                    if nms >= 100:
                        ns += 1; nms -= 100
                        if ns >= 60:
                            nm += 1; ns -= 60
                            if nm >= 60:
                                nh += 1; nm -= 60
                    return f"{nh}:{nm:02d}:{ns:02d}.{nms:02d}"

                start = shift_time(h1, m1, s1, ms1)
                end = shift_time(h2, m2, s2, ms2)
                
                # 🔥 Жестко прибиваем текст к координатам на экране
                positioned_text = f"{{\\pos({pos_x},{pos_y})}}{text}"
                
                events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{positioned_text}")
                
    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_header + "\n".join(events) + "\n")


def prepare_disclaimer(input_path, output_path, duration, fps, gpu_mode, bitrate, needs_audio):
    """Подготавливает дисклеймер, подстраивая аудиодорожку под основное видео"""
    is_image = input_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp'))
    import subprocess, os
    import gpu_engine
    gpu_info = gpu_engine.get_gpu_info()
    encoder = gpu_info.get("encoder", "libx264")

    work_dir = os.path.dirname(output_path)
    output_filename = os.path.basename(output_path)

    cmd = ["ffmpeg", "-hide_banner", "-y"]

    # Чтение исходника (абсолютный путь здесь работает нормально)
    if is_image:
        cmd.extend(["-loop", "1", "-t", str(duration), "-i", input_path])
    else:
        cmd.extend(["-i", input_path, "-t", str(duration)])

    # Фильтр масштабирования
    scale_pad = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p"
    cmd.extend(["-filter:v", scale_pad])

    cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-b:v", f"{bitrate}k"])

    # Умная работа с аудио
    if needs_audio:
        cmd.extend(["-f", "lavfi", "-t", str(duration), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"])
        cmd.extend(["-c:a", "aac", "-b:a", "128k", "-shortest"])
    else:
        cmd.extend(["-an"])

    # Пишем только КОРОТКОЕ имя файла на вывод
    cmd.append(output_filename)

    print(f"\n[prepare_disclaimer] FFmpeg команда (cwd={work_dir}):")
    print(" ".join(cmd))
    
    cflags = get_creationflags()
    
    # 🔥 ЗАПУСК ВНУТРИ ПАПКИ (cwd=work_dir)
    result = subprocess.run(
        cmd, capture_output=True, text=True, 
        encoding='utf-8', errors='replace',
        creationflags=cflags, cwd=work_dir
    )
    
    if result.returncode != 0:
        print(f"\n[prepare_disclaimer] ❌ ОШИБКА FFmpeg:")
        print(result.stderr[-2000:])
        print()
    elif os.path.exists(output_path):
        print(f"\n[prepare_disclaimer] ✓ Создан: {output_path} ({os.path.getsize(output_path)} bytes)\n")


def apply_additions(tab_id, input_video, output_video, additions, shift_sec=0.0, log_target="render"):
    """Наложение аудио и сабов с поддержкой нескольких аудиодорожек и умным микшированием"""
    import subprocess, os, shutil, uuid, platform
    
    def log_msg(msg, level="info"):
        if log_target == "composer":
            safe_eel_call("composerLog", msg)
        else:
            safe_eel_call("add_render_log", tab_id, msg, level)
            
    log_msg("⚙️ Финализация: наложение аудио/субтитров...", "info")

    work_dir = os.path.dirname(output_video)
    input_filename = os.path.basename(input_video)
    output_filename = os.path.basename(output_video)

    add_audio = additions.get("addAudio", False)
    audio_path = additions.get("audioPath", "")
    extra_audios = additions.get("extraAudios", [])
    
    add_subs = additions.get("addSubs", False)
    subs_path = additions.get("subsPath", "")

    # Собираем все валидные аудио-пути
    valid_audios = []
    
    audio_after = additions.get("audioAfterDisclaimer", True)
    audio_delay_ms = int(shift_sec * 1000) if (audio_after and shift_sec > 0) else 0

    if add_audio:
        if audio_path and os.path.exists(audio_path):
            valid_audios.append({"path": audio_path, "delay": audio_delay_ms})
        for ep in extra_audios:
            if ep and os.path.exists(ep):
                valid_audios.append({"path": ep, "delay": 0})  # Доп. дорожки БЕЗ сдвига

    has_subs = add_subs and subs_path and os.path.exists(subs_path)

    # Проверяем, есть ли звук в самом видео (твоя озвучка), чтобы смешать его с фоном
    original_has_audio = False
    try:
        cmd_probe = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", input_video]
        cflags = get_creationflags()
        res = subprocess.run(cmd_probe, capture_output=True, text=True, creationflags=cflags)
        if res.stdout.strip():
            original_has_audio = True
    except:
        pass

    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", input_filename]
    
    # Добавляем все доп. звуки как input
    if valid_audios:
        for a in valid_audios:
            cmd.extend(["-i", a["path"]])

    temp_ass_name = None
    temp_font_dir_name = None
    fontsdir_arg = ""
    
    if has_subs:
        log_msg("═" * 60, "info")
        log_msg("📝 [DEBUG] СТАРТ ОБРАБОТКИ СУБТИТРОВ", "info")
        log_msg(f"   SRT исходник: {subs_path}", "info")
        log_msg(f"   Размер SRT: {os.path.getsize(subs_path)} байт", "info")
        log_msg(f"   Рабочая папка: {work_dir}", "info")
        log_msg("─" * 60, "info")
        
        uid = uuid.uuid4().hex[:6]
        temp_ass_name = f"temp_subs_{uid}.ass"
        temp_ass_path = os.path.join(work_dir, temp_ass_name)

        def hex_to_ass(hx):
            hx = str(hx).lstrip('#')
            if len(hx) == 6: return f"&H00{hx[4:6]}{hx[2:4]}{hx[0:2]}"
            return "&H00FFFFFF"

        font_filename = str(additions.get("subsFont", "Arial.ttf"))
        font_name = os.path.splitext(font_filename)[0].replace("-", " ")
        
        log_msg(f"🔍 1. Имя файла: '{font_filename}' -> Имя в ASS: '{font_name}'", "info")
        
        ui_size = int(additions.get("subsFontSize", 20))
        size = int(ui_size * 1.5) 
        
        color = hex_to_ass(additions.get("subsColor", "#ffffff"))
        outline_col = hex_to_ass(additions.get("subsStrokeColor", "#000000"))
        outline = int(additions.get("subsStroke", 3))

        percent_y = max(0, min(100, int(additions.get("subsPosY", 85))))

        video_height = 1080
        text_block_height = size * 2.5
        padding = 20

        min_y = int(text_block_height + padding)
        max_y = int(video_height - padding)
        pos_y_pixels = int(min_y + (max_y - min_y) * (percent_y / 100.0))

        log_msg(f"⚙️ 2. Параметры: Размер={size}, Y={pos_y_pixels}px (позиция {percent_y}%, диапазон {min_y}..{max_y})", "info")

        margin_v = 10 # Просто заглушка

        convert_srt_to_ass(subs_path, temp_ass_path, font_name, size, color, outline_col, outline, margin_v, shift_sec, pos_y_pixels=pos_y_pixels)

        if os.path.exists(temp_ass_path):
            log_msg(f"✅ 3. ASS создан: {temp_ass_name}", "success")
        else:
            log_msg(f"❌ 3. ОШИБКА: ASS файл НЕ создан!", "error")

        font_path = None
        log_msg(f"🔍 4. Ищем '{font_filename}' в системных шрифтах...", "info")
        font_path = find_font_file(font_filename)

        if font_path:
            log_msg(f"✅ 5. Нашли шрифт на ПК: {font_path}", "success")
            temp_font_dir_name = f"fonts_{uid}"
            temp_font_dir_path = os.path.join(work_dir, temp_font_dir_name)
            os.makedirs(temp_font_dir_path, exist_ok=True)
            
            dst_font = os.path.join(temp_font_dir_path, font_filename)
            shutil.copy2(font_path, dst_font)
            
            if os.path.exists(dst_font):
                log_msg(f"✅ 6. Скопировано в {temp_font_dir_name}", "success")
                fontsdir_arg = f":fontsdir={temp_font_dir_name}"
            else:
                log_msg(f"❌ 6. Ошибка копирования шрифта!", "error")
        else:
            log_msg(f"⚠️ 5. ШРИФТ '{font_filename}' НЕ НАЙДЕН НА ПК! FFmpeg возьмёт дефолтный.", "warning")

        # Финальная проверка ASS-файла перед запуском FFmpeg
        if os.path.exists(temp_ass_path):
            ass_size = os.path.getsize(temp_ass_path)
            log_msg(f"📊 7. ASS файл готов: {ass_size} байт", "info")
            # Покажем первые 5 строк ASS для проверки
            try:
                with open(temp_ass_path, 'r', encoding='utf-8') as f:
                    preview = f.read(500)
                log_msg(f"📄 Превью ASS (первые 500 символов):", "info")
                for ln in preview.split('\n')[:8]:
                    if ln.strip():
                        log_msg(f"   │ {ln[:120]}", "info")
            except Exception as e:
                log_msg(f"⚠️ Не удалось прочитать ASS для превью: {e}", "warning")
        else:
            log_msg(f"❌ 7. ASS ФАЙЛ НЕ СУЩЕСТВУЕТ! Субтитры не появятся!", "error")

        log_msg("═" * 60, "info")

    import gpu_engine
    gpu_info = gpu_engine.get_gpu_info()
    encoder = gpu_info.get("encoder", "libx264")

    # 🔥 CQ-режим (Constant Quality) — даёт минимальный размер при идентичном качестве
    # Размер ~ как у оригинала (Этап 1), а не x3 как было раньше
    quality_value = int(additions.get("subsQuality", 23))  # 18=макс, 23=отлично, 28=среднее
    max_bitrate = str(additions.get("bitrate", "12000"))   # Только страховка, не основной режим

    if encoder == "h264_nvenc":
        # NVENC: -cq 23 → качество как у оригинала, размер минимальный
        cmd.extend([
            "-c:v", "h264_nvenc", "-preset", "p4",
            "-rc", "vbr", "-cq", str(quality_value),
            "-b:v", "0",  # 0 = битрейт регулируется автоматически
            "-maxrate", f"{max_bitrate}k",
            "-bufsize", f"{int(max_bitrate)*2}k"
        ])
    elif encoder == "h264_amf":
        cmd.extend([
            "-c:v", "h264_amf", "-quality", "balanced",
            "-rc", "cqp", "-qp_i", str(quality_value), "-qp_p", str(quality_value),
            "-maxrate", f"{max_bitrate}k"
        ])
    elif encoder == "h264_qsv":
        cmd.extend([
            "-c:v", "h264_qsv", "-preset", "medium",
            "-global_quality", str(quality_value),
            "-maxrate", f"{max_bitrate}k"
        ])
    elif encoder == "h264_videotoolbox":
        cmd.extend([
            "-c:v", "h264_videotoolbox",
            "-b:v", f"{max_bitrate}k"
        ])
    else:
        cmd.extend([
            "-c:v", "libx264", "-preset", "superfast",
            "-crf", str(quality_value),
            "-maxrate", f"{max_bitrate}k",
            "-bufsize", f"{int(max_bitrate)*2}k"
        ])

    log_msg(f"📊 Кодирование: CQ={quality_value} (визуально неотличимо от оригинала), лимит: {max_bitrate} kbps", "info")

    filters = []
    final_video_map = "0:v:0"
    
    # Видео фильтры (Субтитры)
    if has_subs:
        fontsdir_arg = f":fontsdir='{temp_font_dir_name}'" if temp_font_dir_name else ""
        filt_str = f"[0:v:0]subtitles='{temp_ass_name}'{fontsdir_arg}[vout]"
        log_msg(f"📝 Фильтр сабов: {filt_str}", "ffmpeg")
        filters.append(filt_str)
        final_video_map = "[vout]"

    # Аудио фильтры (Задержки и Микширование)
    final_audio_map = None
    if valid_audios or original_has_audio:
        amix_inputs = []
        
        if original_has_audio:
            amix_inputs.append("[0:a:0]")
            
        for i, a in enumerate(valid_audios):
            idx = i + 1
            if a["delay"] > 0:
                filters.append(f"[{idx}:a:0]adelay={a['delay']}|{a['delay']}[aud{idx}]")
                amix_inputs.append(f"[aud{idx}]")
            else:
                amix_inputs.append(f"[{idx}:a:0]")

        if len(amix_inputs) > 1:
            filters.append("".join(amix_inputs) + f"amix=inputs={len(amix_inputs)}:duration=longest:dropout_transition=0[aout]")
            final_audio_map = "[aout]"
        elif len(amix_inputs) == 1:
            val = amix_inputs[0]
            if val == "[0:a:0]":
                # 🔥 ФИКС ОШИБКИ ИНВАЛИДНОГО АРГУМЕНТА 🔥
                # Если звук оригинальный, не передаем его как фильтр,
                # тогда сработает прямое копирование аудиодорожки (c:a copy).
                final_audio_map = None
            else:
                # Убираем лишние квадратные скобки у прямых потоков (например, [1:a:0] превращаем в 1:a:0)
                if val.startswith("[") and val.endswith("]") and ":" in val:
                    final_audio_map = val[1:-1]
                else:
                    final_audio_map = val

    if filters:
        cmd.extend(["-filter_complex", ";".join(filters)])
        
    cmd.extend(["-map", final_video_map])
    
    if final_audio_map:
        cmd.extend(["-map", final_audio_map])
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    else:
        if original_has_audio:
            cmd.extend(["-map", "0:a:0", "-c:a", "copy"])

    cmd.append(output_filename)

    cflags = get_creationflags()
    
    log_msg("─" * 60, "info")
    log_msg(f"🚀 FFmpeg команда (cwd={work_dir}):", "ffmpeg")
    # Печатаем команду построчно для читаемости
    cmd_str = " ".join(cmd)
    log_msg(cmd_str, "ffmpeg")
    log_msg("─" * 60, "info")
    log_msg("⏳ Запуск FFmpeg... (это может занять несколько минут)", "info")
    
    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, 
        universal_newlines=True, creationflags=cflags, 
        cwd=work_dir, encoding='utf-8', errors='replace'
    )

    stderr_lines = []
    import time as _time
    last_progress_time = _time.time()
    last_progress_line = ""
    
    # 🔥 Узнаём длительность входного видео для прогресс-бара
    process_start_time = _time.time()
    total_duration_sec = 0
    try:
        probe_cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", input_video]
        cflags_p = get_creationflags()
        res_dur = subprocess.run(probe_cmd_dur, capture_output=True, text=True, creationflags=cflags_p)
        total_duration_sec = float(res_dur.stdout.strip())
        log_msg(f"📏 Длительность видео: {total_duration_sec:.0f} сек ({total_duration_sec/60:.1f} мин)", "info")
        # Сбрасываем прогресс-бар на 0% при старте этапа 2
        if log_target == "composer":
            safe_eel_call("composerProgressUpdate", 0, "--:--", 0)
    except Exception as e:
        log_msg(f"⚠️ Не удалось узнать длительность: {e}", "warning")
    
    while True:
        line = process.stderr.readline()
        if not line and process.poll() is not None: break
        if line:
            stderr_lines.append(line)
            l = line.lower()
            
            # Прогресс рендера с расчётом % и ETA
            if "frame=" in line and "time=" in line:
                now = _time.time()
                if now - last_progress_time >= 1.5:
                    last_progress_line = line.strip()
                    
                    # Парсим текущее время обработки
                    import re as _re
                    m = _re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                    if m and total_duration_sec > 0:
                        h, mn, s = m.groups()
                        current_sec = int(h)*3600 + int(mn)*60 + float(s)
                        percent = min(100.0, (current_sec / total_duration_sec) * 100.0)
                        
                        # Расчёт ETA
                        eta_str = "--:--"
                        total_elapsed = now - process_start_time
                        if current_sec > 0 and total_elapsed > 0:
                            rate = current_sec / total_elapsed
                            if rate > 0:
                                remaining_sec = (total_duration_sec - current_sec) / rate
                                eta_min = int(remaining_sec // 60)
                                eta_s = int(remaining_sec % 60)
                                eta_str = f"{eta_min:02d}:{eta_s:02d}"
                        
                        # FPS
                        fps_m = _re.search(r'fps=\s*(\d+)', line)
                        fps_val = float(fps_m.group(1)) if fps_m else 0
                        
                        # Отправляем прогресс в Frame Composer UI
                        if log_target == "composer":
                            safe_eel_call("composerProgressUpdate", percent, eta_str, fps_val)
                        
                        log_msg(f"⚙️ Субтитры: {percent:.1f}% | ETA: {eta_str} | {fps_val:.0f} fps", "ffmpeg")
                    else:
                        log_msg(f"⚙️ {last_progress_line[:120]}", "ffmpeg")
                    
                    last_progress_time = now
            
            # Критические сообщения
            if "error" in l or "invalid" in l or "could not" in l or "no such" in l or "unable" in l or "failed" in l:
                log_msg(f"⚠️ FFmpeg: {line.strip()}", "error")
            # Информационные сообщения о субтитрах и шрифтах
            elif "subtitle" in l or "fontselect" in l or "font" in l or "libass" in l:
                log_msg(f"📝 {line.strip()[:200]}", "info")
            # Stream mapping (показываем что куда мапится)
            elif "stream #" in l or "stream mapping" in l:
                log_msg(f"🔀 {line.strip()[:200]}", "info")

    process.wait()
    
    # Финальный прогресс
    if last_progress_line:
        log_msg(f"⚙️ Финал: {last_progress_line[:120]}", "ffmpeg")
    
    if temp_ass_name:
        try: os.remove(os.path.join(work_dir, temp_ass_name))
        except: pass
    if temp_font_dir_name:
        try: shutil.rmtree(os.path.join(work_dir, temp_font_dir_name))
        except: pass

    # 🔥 Если процесс упал — показываем подробный лог
    if process.returncode != 0:
        log_msg("═" * 60, "error")
        log_msg(f"❌ FFmpeg ЗАВЕРШИЛСЯ С ОШИБКОЙ (код {process.returncode})", "error")
        log_msg(f"📋 Последние 40 строк stderr:", "error")
        log_msg("─" * 60, "error")
        for ln in stderr_lines[-40:]:
            cleaned = ln.strip()
            if cleaned:
                log_msg(f"  │ {cleaned}", "error")
        log_msg("═" * 60, "error")
        return False
    else:
        log_msg(f"✓ FFmpeg завершён успешно (код 0)", "success")
        log_msg("✅ Наложение завершено успешно!", "success")
        return True

@eel.expose
def composer_apply_subs(tab_id, video_path, additions):
    """Специальная обертка для Frame Composer, использующая общую логику субтитров"""
    import uuid
    
    safe_eel_call("composerLog", "═" * 60)
    safe_eel_call("composerLog", "🎬 ЭТАП 2: НАЛОЖЕНИЕ СУБТИТРОВ НА ФИНАЛЬНОЕ ВИДЕО")
    safe_eel_call("composerLog", "═" * 60)
    safe_eel_call("composerLog", f"📹 Входное видео: {video_path}")
    safe_eel_call("composerLog", f"📝 SRT файл: {additions.get('subsPath', '(не указан)')}")
    safe_eel_call("composerLog", f"🔤 Шрифт: {additions.get('subsFont', 'Arial')}")
    safe_eel_call("composerLog", f"📏 Размер: {additions.get('subsFontSize', 24)}")
    safe_eel_call("composerLog", f"🎨 Цвет: {additions.get('subsColor', '#ffffff')} / Обводка: {additions.get('subsStrokeColor', '#000000')}")
    safe_eel_call("composerLog", f"📍 Позиция Y: {additions.get('subsPosY', 85)}%")
    safe_eel_call("composerLog", f"⏱️ Сдвиг времени: {additions.get('subsDelay', 0)} сек")
    
    # Проверка входных данных
    if not os.path.exists(video_path):
        safe_eel_call("composerLog", f"❌ ОШИБКА: Видео не найдено: {video_path}")
        return False
    
    srt_path = additions.get('subsPath', '')
    if not srt_path or not os.path.exists(srt_path):
        safe_eel_call("composerLog", f"❌ ОШИБКА: SRT файл не найден: {srt_path}")
        return False
    
    # ═══════════════════════════════════════════════════════════
    # 🛡️ ЗАЩИТА ОТ "ОПАСНЫХ" СИМВОЛОВ В ПУТИ (скобки, пробелы, кавычки)
    # ═══════════════════════════════════════════════════════════
    import shutil
    import tempfile
    _safe_srt_copy = None  # сюда запомним путь к временной копии для удаления
    
    def _path_has_unsafe_chars(p):
        # Символы, которые ломают filter_complex FFmpeg
        unsafe = [' ', '(', ')', '[', ']', "'", ',', ';', ':']
        # Двоеточие в "C:" не считаем — проверяем только после диска
        tail = p[2:] if len(p) > 2 and p[1] == ':' else p
        return any(ch in tail for ch in unsafe)
    
    if srt_path and os.path.exists(srt_path) and _path_has_unsafe_chars(srt_path):
        try:
            # Создаём временную папку с безопасным именем
            safe_dir = os.path.join(tempfile.gettempdir(), f"fc_subs_{uuid.uuid4().hex[:8]}")
            os.makedirs(safe_dir, exist_ok=True)
            
            # Копируем SRT с простым именем
            safe_name = f"subs_{uuid.uuid4().hex[:6]}.srt"
            _safe_srt_copy = os.path.join(safe_dir, safe_name)
            shutil.copy2(srt_path, _safe_srt_copy)
            
            safe_eel_call("composerLog", f"🛡️ В пути к SRT есть спец-символы — создана безопасная копия:")
            safe_eel_call("composerLog", f"   Оригинал: {srt_path}")
            safe_eel_call("composerLog", f"   Копия:    {_safe_srt_copy}")
            
            # Подменяем путь — дальше код работает с копией
            srt_path = _safe_srt_copy
            additions['subsPath'] = _safe_srt_copy
        except Exception as e:
            safe_eel_call("composerLog", f"⚠️ Не удалось создать безопасную копию SRT: {e}")
            safe_eel_call("composerLog", f"   Продолжаем с оригинальным путём...")
    
    safe_eel_call("composerLog", f"✓ Входные файлы проверены")
    safe_eel_call("composerLog", "─" * 60)
    
    work_dir = os.path.dirname(video_path)
    temp_out = os.path.join(work_dir, f"temp_composer_subs_{uuid.uuid4().hex[:6]}.mp4")
    safe_eel_call("composerLog", f"📂 Временный файл: {os.path.basename(temp_out)}")
    
    try:
        # Запускаем ту же самую функцию (аудио мы не передаем, так что аудио будет просто скопировано)
        import time
        start_time = time.time()
        success = apply_additions(tab_id, video_path, temp_out, additions, shift_sec=0.0, log_target="composer")
        elapsed = time.time() - start_time
        
        safe_eel_call("composerLog", "─" * 60)
        safe_eel_call("composerLog", f"⏱️ Время выполнения: {elapsed:.1f} сек")
        
        if success and os.path.exists(temp_out):
            temp_size_mb = os.path.getsize(temp_out) / (1024 * 1024)
            safe_eel_call("composerLog", f"✓ Временный файл создан: {temp_size_mb:.1f} MB")
            try:
                safe_eel_call("composerLog", "🔄 Перезапись финального видео...")
                os.replace(temp_out, video_path)
                final_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                safe_eel_call("composerLog", f"✅ ГОТОВО! Финальный файл: {final_size_mb:.1f} MB")
                safe_eel_call("composerLog", "═" * 60)
                return True
            except Exception as e:
                safe_eel_call("composerLog", f"❌ Ошибка перезаписи видео: {str(e)}")
                safe_eel_call("composerLog", "═" * 60)
                return False
        else:
            safe_eel_call("composerLog", f"❌ ОШИБКА: apply_additions вернула success={success}, файл существует={os.path.exists(temp_out) if temp_out else False}")
            safe_eel_call("composerLog", "═" * 60)
            if os.path.exists(temp_out):
                try:
                    os.remove(temp_out)
                except:
                    pass
            return False
    finally:
        # ═══════════════════════════════════════════════════════
        # 🧹 ОЧИСТКА: удаляем временную копию SRT (если создавали)
        # ═══════════════════════════════════════════════════════
        if _safe_srt_copy and os.path.exists(_safe_srt_copy):
            try:
                safe_dir = os.path.dirname(_safe_srt_copy)
                shutil.rmtree(safe_dir, ignore_errors=True)
                safe_eel_call("composerLog", f"🧹 Удалена временная копия SRT: {_safe_srt_copy}")
            except Exception as e:
                safe_eel_call("composerLog", f"⚠️ Не удалось удалить временную копию: {e}")


def merge_worker(tab_id, items, output_path, delete_after=False, open_folder_flag=True, nuke_dir=None, additions=None):
    concat_list_path = None
    disclaimer_temp = None
    merge_success = False
    try:
        import tempfile, time, uuid, subprocess
        safe_eel_call("add_render_log", tab_id, "Запуск склейки видео...", "info")
        
        items_to_concat = list(items)
        
        add_disclaimer = additions.get("addDisclaimer", False) if additions else False
        disclaimer_path = additions.get("disclaimerPath", "") if additions else ""
        disclaimer_len = float(additions.get("disclaimerLen", 1.5)) if additions else 1.5
        actual_shift_sec = 0.0
        
        # --- 1. Обработка Дисклеймера ---
        if add_disclaimer and disclaimer_path and os.path.exists(disclaimer_path):
            safe_eel_call("add_render_log", tab_id, "🎬 Подготовка дисклеймера...", "info")
            fps = additions.get("fps", "24") if additions else "24"
            bitrate = additions.get("bitrate", "8000") if additions else "8000"
            gpu_mode = additions.get("gpuMode", "full_gpu") if additions else "full_gpu"
            
            disclaimer_temp = os.path.join(os.path.dirname(output_path), f"disclaimer_temp_{uuid.uuid4().hex[:4]}.mp4").replace('\\', '/')
            
            first_clip_has_audio = False
            if items:
                probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", items[0]['path']]
                cflags = get_creationflags()
                try:
                    probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=cflags)
                    if probe_res.stdout.strip():
                        first_clip_has_audio = True
                except: pass

            prepare_disclaimer(disclaimer_path, disclaimer_temp, disclaimer_len, fps, gpu_mode, bitrate, first_clip_has_audio)
            
            if os.path.exists(disclaimer_temp) and os.path.getsize(disclaimer_temp) > 1024:
                items_to_concat.insert(0, {'path': disclaimer_temp})
                actual_shift_sec = disclaimer_len  # Фиксируем сдвиг времени для субтитров и звука
                safe_eel_call("add_render_log", tab_id, f"✓ Дисклеймер добавлен в начало ({os.path.getsize(disclaimer_temp)//1024} KB)", "success")
            else:
                safe_eel_call("add_render_log", tab_id, "❌ Дисклеймер не создался! Пропускаем его и склеиваем без него.", "error")
                disclaimer_temp = None
        
        # --- 2. Наложение Аудио и Сабов ---
        needs_post_process = False
        temp_concat = output_path
        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        if additions and (additions.get("addAudio") or additions.get("addSubs")):
            needs_post_process = True
            temp_concat = output_path.replace(".mp4", f"_temp_{uuid.uuid4().hex[:4]}.mp4")
        
        # --- 3. Склейка ---
        concat_dir_candidates = [os.path.join(tempfile.gettempdir(), "stocky_concat")]
        output_drive = os.path.splitdrive(os.path.abspath(output_path))[0]
        if output_drive:
            concat_dir_candidates.append(os.path.join(output_drive + os.sep, "stocky_concat"))
        concat_dir_candidates.append(os.path.join(os.getcwd(), "stocky_concat"))

        writable_concat_dirs = []
        for candidate in concat_dir_candidates:
            try:
                os.makedirs(candidate, exist_ok=True)
                probe_path = os.path.join(candidate, f"probe_{uuid.uuid4().hex[:6]}.tmp")
                with open(probe_path, "w", encoding="utf-8") as probe_file:
                    probe_file.write("ok")
                os.remove(probe_path)
                writable_concat_dirs.append(candidate)
            except Exception:
                continue

        if not writable_concat_dirs:
            safe_eel_call("add_render_log", tab_id, "Ошибка склейки: не удалось создать временный concat-list.", "error")
            return

        concat_temp_dir = next((p for p in writable_concat_dirs if p.isascii()), writable_concat_dirs[0])
        concat_list_path = os.path.join(concat_temp_dir, f"concat_list_{uuid.uuid4().hex[:6]}.txt")
        missing_files = [item.get('path', '') for item in items_to_concat if not os.path.exists(item.get('path', ''))]
        if missing_files:
            safe_eel_call(
                "add_render_log",
                tab_id,
                f"Ошибка склейки: не найден файл {os.path.basename(missing_files[0])}",
                "error"
            )
            return

        with open(concat_list_path, 'w', encoding='utf-8', newline='\n') as f:
            for item in items_to_concat:
                p = os.path.abspath(item['path']).replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{p}'\n")
                
        cmd = ["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", temp_concat]
        cflags = get_creationflags()
        
        print(f"\n[merge_worker] FFmpeg команда склейки:")
        print(" ".join(cmd))
        print()
        
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True, creationflags=cflags, encoding='utf-8', errors='replace')
        
        stderr_lines = []
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None: break
            if line:
                stderr_lines.append(line)
                if "time=" in line:
                    try:
                        time_str = line.split("time=")[1].split(" ")[0]
                        h, m, s = time_str.split(":")
                        cur_sec = float(h)*3600 + float(m)*60 + float(s)
                        safe_eel_call("update_concat_progress", tab_id, f"{cur_sec:.1f}s")
                    except: pass
                    
        process.wait()
        
        if process.returncode != 0:
            err_tail = "".join(stderr_lines[-15:])
            print(f"\n[merge_worker] FFmpeg STDERR (последние 15 строк):")
            print(err_tail)
            print()
            safe_eel_call("add_render_log", tab_id, f"Ошибка FFmpeg при склейке: {err_tail[-200:]}", "error")
            return
            
        if not os.path.exists(temp_concat) or os.path.getsize(temp_concat) < 1024:
            safe_eel_call("add_render_log", tab_id, "Ошибка: файл склейки пуст или не создан.", "error")
            return

        # --- 4. Финализация (Аудио/Сабы) ---
        if needs_post_process:
            success = apply_additions(tab_id, temp_concat, output_path, additions, shift_sec=actual_shift_sec)
            try: os.remove(temp_concat)
            except: pass
            if not success: return
        
        total_size_bytes = sum(os.path.getsize(item['path']) for item in items if os.path.exists(item['path']))
        size_mb = total_size_bytes / (1024 * 1024)
        safe_eel_call("add_render_log", tab_id, f"Склейка финально завершена: {os.path.basename(output_path)} ({len(items_to_concat)} файлов, {size_mb:.1f} MB)", "success")
        merge_success = True

        # --- 5. Очистка ---
        if concat_list_path and os.path.exists(concat_list_path):
            try: os.remove(concat_list_path)
            except: pass
        if disclaimer_temp and os.path.exists(disclaimer_temp):
            try: os.remove(disclaimer_temp)
            except: pass

        time.sleep(1.5)
        
        if delete_after:
            if nuke_dir and os.path.exists(nuke_dir):
                try:
                    for file_name in os.listdir(nuke_dir):
                        if "Links_Log" in file_name:
                            log_src = os.path.join(nuke_dir, file_name)
                            log_dst = f"{os.path.splitext(output_path)[0]}_{file_name}"
                            shutil.move(log_src, log_dst)
                            safe_eel_call("add_render_log", tab_id, f"📄 Файл со ссылками сохранен: {os.path.basename(log_dst)}", "success")
                    shutil.rmtree(nuke_dir)
                    safe_eel_call("add_render_log", tab_id, f"🗑️ Исходники и папка {os.path.basename(nuke_dir)} удалены.", "success")
                except Exception as e:
                    safe_eel_call("add_render_log", tab_id, f"Ошибка удаления папки: {e}", "error")
            else:
                for item in items:
                    try: os.remove(item['path'])
                    except: pass
        
        if open_folder_flag: 
            try: eel.open_folder(tab_id, output_path)()
            except: pass
            
    except Exception as e:
        safe_eel_call("add_render_log", tab_id, f"Ошибка склейки: {e}", "error")
    finally:
        if concat_list_path and os.path.exists(concat_list_path):
            try: os.remove(concat_list_path)
            except: pass
        if merge_success:
            safe_eel_call("render_batch_complete", tab_id, len(items), len(items), 0)
        else:
            safe_eel_call("render_batch_complete", tab_id, len(items), 0, 1)

def extract_docx_text(path):
    """Simple docx extraction without external libs"""
    try:
        with zipfile.ZipFile(path) as z:
            with z.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                texts = []
                for p in root.findall('.//w:p', ns):
                    para_text_parts = [node.text for node in p.findall('.//w:t', ns) if node.text]
                    para_text = "".join(str(t) for t in para_text_parts)
                    if para_text.strip():
                        texts.append(para_text.strip())
                return "\n".join(texts)
    except Exception as e:
        print(f"Docx error: {e}")
        return ""

@eel.expose
def start_render_batch(tab_id, tab_name, is_auto, trim_start, trim_end, fmt, quality, fps="24", keep_audio=False, auto_merge=False, delete_after_merge=False, gpu_mode="full_gpu", bitrate="8000", threads=1, frame_enabled=True, frame_color="White", additions=None, clip_rules=None, render_output_dir=None, duration_config=None):
    print(f"[PY][start_render_batch] ВЫЗВАНА: tab={tab_id}, is_auto={is_auto}, threads={threads}")
    _render_state_set(tab_id, "starting", tab_name)

    slot_acquired = try_acquire_render_slot(tab_id, tab_name)
    if not slot_acquired:
        if is_auto:
            kwargs = {
                "tab_id": tab_id, "items": None,
                "trim_start": int(trim_start) if str(trim_start).isdigit() else 3,
                "trim_end": int(trim_end) if str(trim_end).isdigit() else 6,
                "fmt": fmt, "quality": quality, "fps": fps, 
                "keep_audio": keep_audio, "auto_merge": auto_merge,
                "delete_after_merge": delete_after_merge, "gpu_mode": gpu_mode, 
                "bitrate": bitrate, "threads": int(threads) if str(threads).isdigit() else 1,
                "frame_enabled": frame_enabled, "frame_color": frame_color,
                "additions": additions, "clip_rules": clip_rules,
                "render_output_dir": render_output_dir,
                "duration_config": duration_config,
            }
            pos = add_to_wait_queue(tab_id, tab_name, kwargs)
            safe_eel_call("add_render_log", tab_id, f"⏸ Ждёт своей очереди рендера (позиция {pos})", "info")
            return
        else:
            safe_eel_call("show_render_busy_modal", ACTIVE_RENDER_TAB_NAME)
            safe_eel_call("render_batch_complete", tab_id, 0, 0, 0)
            return

    tab_render_stop_flags[tab_id] = False
    if not shutil.which("ffmpeg"):
        safe_eel_call("add_render_log", tab_id, "❌ FFmpeg не найден!", "error")
        safe_eel_call("render_batch_complete", tab_id, 0, 0, 0)
        release_render_slot(tab_id)
        return

    queue = get_tab_queue(tab_id)
    items = [item for item in queue if item.get('status') == 'Done']
    if not items:
        safe_eel_call("render_batch_complete", tab_id, 0, 0, 0)
        release_render_slot(tab_id)
        return

    try:
        trim_start = int(trim_start)
        trim_end = int(trim_end)
        threads = int(threads)
    except: 
        trim_start, trim_end, threads = 3, 6, 1

    print(f"[PY][start_render_batch] Запускаю поток render_worker...")
    thread = threading.Thread(
        target=render_worker,
        kwargs={
            "tab_id": tab_id, "items": items, "trim_start": trim_start, "trim_end": trim_end, "fmt": fmt, "quality": quality, "fps": fps, "keep_audio": keep_audio, "auto_merge": auto_merge, "delete_after_merge": delete_after_merge, "gpu_mode": gpu_mode, "bitrate": bitrate, "threads": threads, "frame_enabled": frame_enabled, "frame_color": frame_color, "additions": additions, "clip_rules": clip_rules, "render_output_dir": render_output_dir, "duration_config": duration_config
        },
        daemon=True
    )
    thread.start()

def render_worker(tab_id, items, trim_start, trim_end, fmt, quality, fps="24", keep_audio=False, auto_merge=False, delete_after_merge=False, gpu_mode="full_gpu", bitrate="8000", threads=1, frame_enabled=True, frame_color="White", additions=None, clip_rules=None, render_output_dir=None, duration_config=None):
    tab_name = (_render_state_get(tab_id) or {}).get("tab_name", "?")

    if items is None:
        queue = get_tab_queue(tab_id)
        items = [item for item in queue if item.get('status') == 'Done']
        if not items:
            safe_eel_call("render_batch_complete", tab_id, 0, 0, 0)
            _render_state_remove(tab_id)
            release_render_slot(tab_id)
            return

    print(f"[PY][render_worker] СТАРТ: {len(items)} файлов, {threads} потоков")
    _render_state_set(tab_id, "rendering", tab_name)
    _tg_event("render_start", tab_name=tab_name, detail=f"{len(items)} файлов, {threads} поток")
    total = len(items)
    success_count = 0
    error_count = 0
    counter_lock = threading.Lock()

    try:
        try:
            render_clip_plan, plan_label = build_render_clip_plan(total, clip_rules, duration_config)
            total_duration = sum(float(clip["duration"]) for clip in render_clip_plan)
            safe_eel_call(
                "add_render_log",
                tab_id,
                f"[plan] mode={plan_label} | clips={total} | total={total_duration:.3f}s",
                "success"
            )
        except Exception as e:
            safe_eel_call("add_render_log", tab_id, f"❌ Ошибка плана нарезки: {e}", "error")
            safe_eel_call("render_batch_complete", tab_id, 0, 0, 0)
            _render_state_remove(tab_id)
            _tg_event("render_error", tab_name=tab_name, detail=f"план нарезки: {e}")
            return

        first_item_path = items[0]['path']
        if render_output_dir and os.path.isdir(render_output_dir):
            render_dir = os.path.join(render_output_dir, "rendered")
        else:
            render_dir = os.path.join(os.path.dirname(first_item_path), "rendered")
        os.makedirs(render_dir, exist_ok=True)

        batch_gpu_info = gpu_engine.get_gpu_info()
        batch_encoder = batch_gpu_info.get("encoder", "libx264")
        if gpu_mode in ("full_gpu", "cpu_gpu") and batch_encoder != "libx264":
            if ffmpeg_encoder_runtime_works(batch_encoder):
                safe_eel_call(
                    "add_render_log",
                    tab_id,
                    f"⚙️ Энкодер: {batch_encoder}",
                    "ffmpeg"
                )
            else:
                safe_eel_call(
                    "add_render_log",
                    tab_id,
                    f"⚠️ Аппаратный энкодер {batch_encoder} не запускается. Переключаю пакет на CPU (libx264).",
                    "warning"
                )
                batch_gpu_info = {
                    "name": "CPU fallback",
                    "encoder": "libx264",
                    "hwaccel": None,
                    "type": "cpu",
                }
        elif gpu_mode in ("full_gpu", "cpu_gpu"):
            safe_eel_call(
                "add_render_log",
                tab_id,
                "⚠️ Аппаратный энкодер недоступен. Пакет будет отрендерен на CPU (libx264).",
                "warning"
            )
        
        def process_render_item(i_item):
            nonlocal success_count, error_count
            try:
                i, item = i_item
                if tab_render_stop_flags.get(tab_id): return
                
                input_path = item['path']
                if not os.path.exists(input_path):
                    with counter_lock: error_count += 1
                    return
            
                q_idx = -1
                queue = get_tab_queue(tab_id)
                for idx, qi in enumerate(queue):
                    if qi.get('id') == item.get('id'):
                        q_idx = idx
                        break
            
                orig_name = os.path.splitext(os.path.basename(input_path))[0]
                filename = f"{orig_name}_rendered.{fmt}"
                output_path = os.path.join(render_dir, filename)
            
                try:
                    safe_eel_call("update_render_current", tab_id, filename, i + 1, total)
                    if q_idx != -1:
                        queue[q_idx]['status'] = 'Rendering'
                        update_single_item(tab_id, q_idx)
                except: pass

                clip = render_clip_plan[i] if i < len(render_clip_plan) else None
                if clip:
                    clip_start, exact_duration, clip_rule = clip["start"], clip["duration"], clip["rule"]
                else:
                    clip_start, exact_duration, clip_rule = get_item_clip_metadata(item, i, clip_rules=clip_rules, total_items=total)
                if clip_rule.get("mode") == "srt":
                    rule_details = f"duration={_format_clip_value(exact_duration)}"
                elif clip_rule.get("mode") == "fixed":
                    rule_details = "duration=" + _format_clip_value(clip_rule.get("duration"))
                else:
                    rule_details = "range=" + _format_clip_value(clip_rule.get("durationMin")) + "-" + _format_clip_value(clip_rule.get("durationMax"))
                safe_eel_call(
                    "add_render_log",
                    tab_id,
                    f"[clip] position={clip_start:.3f}s | rule={_format_rule_label(clip_rule)} | mode={clip_rule['mode']} | "
                    f"{rule_details} | "
                    f"result={exact_duration:.3f}s",
                    "info"
                )
                cmd = build_ffmpeg_cmd(input_path, output_path, trim_start, exact_duration, fmt, quality, fps, keep_audio, gpu_mode, bitrate, batch_gpu_info, frame_enabled, frame_color)
            
                try:
                    cflags = get_creationflags()
                    process = subprocess.Popen(
                        cmd,
                        stderr=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        universal_newlines=True,
                        encoding='utf-8',
                        errors='replace',
                        creationflags=cflags
                    )
                
                    last_ws_update = 0
                    stderr_tail = []
                    while True:
                        line = process.stderr.readline()
                        if not line and process.poll() is not None: break
                        if line:
                            stderr_tail.append(line.strip())
                            stderr_tail = stderr_tail[-12:]
                        if line and "time=" in line:
                            time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                            if time_match and exact_duration > 0:
                                h, m, s = time_match.groups()
                                current_time = int(h)*3600 + int(m)*60 + float(s)
                                percent = min(100, int(current_time / exact_duration * 100))
                                now_t = time.time()
                                if now_t - last_ws_update > 0.5:
                                    safe_eel_call("update_render_progress", tab_id, q_idx, percent, current_time, exact_duration)
                                    _render_state_touch(tab_id)
                                    last_ws_update = now_t

                        if tab_render_stop_flags.get(tab_id):
                            process.terminate()
                            try: process.wait(timeout=2)
                            except: process.kill()
                            break
                
                    process.wait()
                    safe_eel_call("update_render_progress", tab_id, q_idx, 100, exact_duration, exact_duration)
                    _render_state_touch(tab_id)
                
                    if process.returncode == 0 and not tab_render_stop_flags.get(tab_id):
                        with counter_lock:
                            success_count += 1
                            current_done = success_count + error_count
                        safe_eel_call("update_batch_progress", tab_id, current_done, total)

                        if q_idx != -1:
                            queue = get_tab_queue(tab_id)
                            queue[q_idx]['status'] = 'Rendered'
                            queue[q_idx]['path'] = output_path
                            queue[q_idx]['progress'] = 100
                            safe_eel_call("render_file_done", tab_id, q_idx, "Rendered")
                            
                    elif not tab_render_stop_flags.get(tab_id):
                        with counter_lock:
                            error_count += 1
                            current_done = success_count + error_count
                        safe_eel_call("update_batch_progress", tab_id, current_done, total)
                        if stderr_tail:
                            err_text = " | ".join([line for line in stderr_tail if line])
                            safe_eel_call(
                                "add_render_log",
                                tab_id,
                                f"FFmpeg ошибка {filename}: {err_text[-1200:]}",
                                "error"
                            )

                        if q_idx != -1:
                            queue = get_tab_queue(tab_id)
                            queue[q_idx]['status'] = 'Error'
                            safe_eel_call("render_file_done", tab_id, q_idx, "Error")
                except Exception as e:
                    with counter_lock: error_count += 1
                    safe_eel_call("add_render_log", tab_id, f"Ошибка процесса {filename}: {e}", "error")
            except Exception as e:
                with counter_lock: error_count += 1

        enumerated_items = list(enumerate(items))
        if threads > 1:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = [executor.submit(process_render_item, ei) for ei in enumerated_items]
                for future in futures:
                    try: future.result()
                    except: pass
        else:
            for ei in enumerated_items:
                if tab_render_stop_flags.get(tab_id): break
                process_render_item(ei)

        safe_eel_call("render_batch_complete", tab_id, total, success_count, error_count)
        update_ui_queue(tab_id)
        _tg_event("render_done", tab_name=tab_name, detail=f"✅{success_count} ❌{error_count} из {total}")
        _render_state_remove(tab_id)

        # === АВТОСКЛЕЙКА ===
        if auto_merge and success_count > 0 and not tab_render_stop_flags.get(tab_id):
            queue = get_tab_queue(tab_id)
            rendered_items = [q for q in queue if q.get('status') == 'Rendered']
            if rendered_items:
                auto_name = f"1_auto_merged_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                source_dir = render_dir
                root_dir = render_output_dir if render_output_dir and os.path.isdir(render_output_dir) else os.path.dirname(os.path.dirname(first_item_path))
                save_merge_path = os.path.join(root_dir, auto_name)
                _tg_event("merge_done", tab_name=tab_name, detail=os.path.basename(save_merge_path))
                merge_worker(tab_id, rendered_items, save_merge_path, delete_after=delete_after_merge, open_folder_flag=True, nuke_dir=source_dir, additions=additions)

    except Exception as e:
        safe_eel_call("add_render_log", tab_id, f"Критическая ошибка рендера: {e}", "error")
        safe_eel_call("render_batch_complete", tab_id, 0, 0, 1)
        _tg_event("render_error", tab_name=tab_name, detail=f"критическая: {e}")
        _render_state_remove(tab_id)
    finally:
        release_render_slot(tab_id)

@eel.expose
def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.update()
    folder = filedialog.askdirectory(title="Выберите папку для сохранения")
    root.destroy()
    return folder if folder else ""

@eel.expose
def open_folder(tab_id, path):
    if not path: return
    # If path is a file, get its directory
    folder = os.path.dirname(path) if os.path.isfile(path) else path
    if not os.path.exists(folder):
        log_to_js(tab_id, f"Путь не найден: {folder}", "error")
        return
    
    try:
        reveal_in_file_manager(path if os.path.isfile(path) else folder)
    except Exception as e:
        log_to_js(tab_id, f"Ошибка открытия папки: {e}", "error")

@eel.expose
def open_file(tab_id, path):
    if not path or not os.path.exists(path):
        log_to_js(tab_id, f"Файл не найден: {path}", "error")
        return
    try:
        open_path(path)
    except Exception as e:
        log_to_js(tab_id, f"Ошибка открытия файла: {e}", "error")

@eel.expose
def stop_download(tab_id):
    tab_stop_flags[tab_id] = True

def _normalize_stock_pool(stock_pool):
    result = []
    if not isinstance(stock_pool, list):
        return result
    for item in stock_pool:
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        provider = str(item.get("provider") or "").strip().lower()
        api_key = str(item.get("apiKey") or item.get("api_key") or "").strip()
        if provider in ("pexels", "pixabay") and api_key and api_key != "ВСТАВЬ_СВОЙ_КЛЮЧ":
            result.append({"provider": provider, "api_key": api_key})
    return result


def _process_single_item(tab_id, idx, source, save_path, config, trim_start=3, trim_end=6, clip_rules=None, stock_pool=None):
    """Core download logic for a single queue item. Used by both batch download and retry."""
    queue = get_tab_queue(tab_id)
    if idx >= len(queue):
        return None

    # Инициализация перед загрузкой (ОБЯЗАТЕЛЬНО ЧИСТИМ СКОРОСТЬ)
    queue[idx]["status"] = "Downloading"
    queue[idx]["progress"] = 0
    queue[idx]["speed"] = "" 
    update_ui_queue(tab_id)

    # === НУМЕРАЦИЯ ФАЙЛА И ТАЙМКОД ===
    file_number = idx + 1
    file_name = f"{file_number:04d}.mp4"
    clip_start, clip_duration, clip_rule = get_item_clip_metadata(queue[idx], idx, clip_rules=clip_rules, total_items=len(queue))
    queue[idx]["clip_start"] = round(clip_start, 3)
    queue[idx]["clip_duration"] = round(clip_duration, 3)
    queue[idx]["clip_rule"] = clip_rule
    # =================================

    def make_update_fn(q_idx):
        def update(progress, path=None, speed=""):
            q = get_tab_queue(tab_id)
            current_status = q[q_idx].get("status", "")
            if current_status in ["Done", "Failed", "Cancelled"]:
                return
            q[q_idx]["progress"] = progress
            if speed:
                q[q_idx]["speed"] = speed
            if path:
                q[q_idx]["path"] = path
                q[q_idx]["status"] = "Done"
            update_ui_queue(tab_id)
        return update

    item_update = make_update_fn(idx)
    prompt = queue[idx]["prompt"]

    try:
        media_type = "photo" if "photo" in source else "video"

        active_stock_pool = _normalize_stock_pool(stock_pool)
        if active_stock_pool:
            assigned_worker = active_stock_pool[idx % len(active_stock_pool)]
            providers = [assigned_worker["provider"]]
            pool_key = assigned_worker["api_key"]
            log_to_js(tab_id, f"[stock pool] #{idx + 1} -> {assigned_worker['provider']} | worker {(idx % len(active_stock_pool)) + 1}/{len(active_stock_pool)}", "info")
        else:
            pool_key = None
            providers = []
            if source.startswith("pixabay"): providers = ["pixabay"]
            elif source.startswith("pexels"): providers = ["pexels"]
            else: providers = ["pexels", "pixabay"]

        downloaded_total = 0
        found_video_id = None
        log_to_js(
            tab_id,
            f"[clip] position={clip_start:.3f}s | rule={_format_rule_label(clip_rule)} | mode={clip_rule['mode']} | "
            f"{('duration=' + _format_clip_value(clip_rule.get('duration'))) if clip_rule['mode'] == 'fixed' else ('range=' + _format_clip_value(clip_rule.get('durationMin')) + '-' + _format_clip_value(clip_rule.get('durationMax')))} | "
            f"result={clip_duration:.3f}s",
            "info"
        )
        for provider in providers:
            if tab_stop_flags.get(tab_id): break
            api_keys = [pool_key] if pool_key and active_stock_pool else _get_rotated_provider_api_keys(config, provider)

            if not api_keys:
                log_to_js(tab_id, f"Ключ для {provider} не задан!", "error")
                continue

            target_min_duration = float(clip_duration) + float(trim_start) + float(trim_end)
            for key_index, api_key in enumerate(api_keys, start=1):
                if len(api_keys) > 1:
                    log_to_js(tab_id, f"[{provider}] Пробую ключ {key_index}/{len(api_keys)}", "info")

                if provider == "pexels":
                    cnt, meta = downloader.download_pexels(
                        prompt, api_key, save_path, media_type,
                        stop_flag=lambda: tab_stop_flags.get(tab_id),
                        log_fn=lambda m, l: log_to_js(tab_id, m, l),
                        item_update_fn=item_update,
                        min_duration=target_min_duration,
                        custom_filename=file_name
                    )
                    downloaded_total += cnt
                    if cnt > 0:
                        _mark_provider_key_used(config, provider, api_key)
                        break
                    error_type = (meta or {}).get("error_type")
                    if error_type in ("rate_limit", "auth"):
                        log_to_js(tab_id, f"[{provider}] Переключаюсь на следующий ключ из-за {error_type}.", "warning")
                        continue
                    break
                else:
                    cnt, vid_id, meta = downloader.download_pixabay(
                        prompt, api_key, save_path, media_type,
                        stop_flag=lambda: tab_stop_flags.get(tab_id),
                        log_fn=lambda m, l: log_to_js(tab_id, m, l),
                        item_update_fn=item_update,
                        min_duration=target_min_duration,
                        custom_filename=file_name
                    )
                    downloaded_total += cnt
                    if cnt > 0 and vid_id:
                        found_video_id = vid_id
                    if cnt > 0:
                        _mark_provider_key_used(config, provider, api_key)
                        break
                    error_type = (meta or {}).get("error_type")
                    if error_type in ("rate_limit", "auth"):
                        log_to_js(tab_id, f"[{provider}] Переключаюсь на следующий ключ из-за {error_type}.", "warning")
                        continue
                    break

            if downloaded_total > 0:
                break

        # --- КРИТИЧЕСКИЙ БЛОК: ИСПРАВЛЕНИЕ ЗАВИСАНИЙ СТАТУСА ---
        if tab_stop_flags.get(tab_id):
            queue[idx]["status"] = "Cancelled"
            queue[idx]["progress"] = 0
            queue[idx]["speed"] = ""
        elif downloaded_total == 0:
            queue[idx]["status"] = "Failed"
            queue[idx]["progress"] = 0
            queue[idx]["speed"] = ""
        else:
            queue[idx]["status"] = "Done"
            queue[idx]["progress"] = 100
            queue[idx]["speed"] = ""
            if found_video_id:
                queue[idx]["video_id"] = found_video_id

    except Exception as e:
        log_to_js(tab_id, f"Ошибка в процессе '{prompt}': {e}", "error")
        queue[idx]["status"] = "Failed"
        queue[idx]["progress"] = 0
        queue[idx]["speed"] = ""
        found_video_id = None

    update_ui_queue(tab_id)
    return found_video_id


def download_task(tab_id, prompts, source, save_path, config, trim_start=3, trim_end=6, workers_count=1, clip_rules=None, stock_pool=None):
    global active_download_tabs
    with active_downloads_lock:
        active_download_tabs.add(tab_id)
        
    try:
        tab_stop_flags[tab_id] = False
        if not save_path:
            save_path = DEFAULT_DOWNLOAD_DIR
        
        clip_plan = build_clip_plan_for_count(len(prompts), clip_rules or DEFAULT_CLIP_RULES)

        queue = []
        for idx, prompt in enumerate(prompts):
            clip = clip_plan[idx]
            queue.append({
                "id": uuid.uuid4().hex[:8],
                "prompt": prompt,
                "status": "Pending",
                "progress": 0,
                "path": "",
                "clip_start": clip["start"],
                "clip_duration": clip["duration"],
                "clip_rule": clip["rule"],
            })
        tab_queues[tab_id] = queue
        update_ui_queue(tab_id)
        
        active_stock_pool = _normalize_stock_pool(stock_pool)
        log_to_js(tab_id, f"Запущено скачивание ({source}). Потоков: {workers_count}...", "info")
        _tg_event("download_start", detail=f"{source}, {len(prompts)} промптов, {workers_count} потока")
        if active_stock_pool:
            log_to_js(tab_id, f"[stock pool] Активных воркеров: {len(active_stock_pool)}", "info")
            for worker_idx, worker in enumerate(active_stock_pool, start=1):
                log_to_js(tab_id, f"[stock pool] {worker_idx}. {worker['provider']}", "info")
        
        MIN_PROMPTS_FOR_RESET = 310
        total_prompts = len(prompts)
        midpoint = total_prompts // 2

        def process_item(idx):
            if tab_stop_flags.get(tab_id):
                queue[idx]["status"] = "Cancelled"
                return

            if total_prompts >= MIN_PROMPTS_FOR_RESET and idx == midpoint:
                downloader.DOWNLOADED_MEDIA_IDS.clear()
                log_to_js(tab_id, f"[ИНФО] Достигнута середина ({idx}/{total_prompts}). Кэш очищен!", "info")

            _process_single_item(tab_id, idx, source, save_path, config, trim_start, trim_end, clip_rules, active_stock_pool)

        if workers_count > 1:
            with ThreadPoolExecutor(max_workers=workers_count) as executor:
                futures = {executor.submit(process_item, idx): idx for idx in range(len(queue))}
                from concurrent.futures import as_completed, TimeoutError as FuturesTimeout
                for future in as_completed(futures, timeout=None):
                    # macOS: даём event loop подышать между задачами
                    if platform.system() == "Darwin":
                        import gevent; gevent.sleep(0)
                    idx = futures[future]
                    try:
                        future.result(timeout=1200) # Хард-лимит 20 минут
                    except FuturesTimeout:
                        log_to_js(tab_id, f"⏱️ ТАЙМАУТ задачи #{idx+1} (>1200 сек)", "error")
                        queue[idx]["status"] = "Failed"
                        queue[idx]["progress"] = 0
                        update_ui_queue(tab_id)
                    except Exception as e:
                        log_to_js(tab_id, f"❌ Ошибка задачи #{idx+1}: {e}", "error")
                        queue[idx]["status"] = "Failed"
                        queue[idx]["progress"] = 0
                        update_ui_queue(tab_id)
        else:
            idx = 0
            while idx < len(queue):
                if tab_stop_flags.get(tab_id):
                    break
                    
                with active_downloads_lock:
                    active_tabs_count = len(active_download_tabs)
                    
                remaining = len(queue) - idx
                
                # 🔥 АВТО-УСКОРЕНИЕ (Идея Опуса, но без JS-костылей)
                if active_tabs_count <= 5 and remaining > 10:
                    log_to_js(tab_id, f"⚡ Активных проектов: {active_tabs_count}. Включаю турбо-режим X5 для оставшихся {remaining} файлов!", "success")
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        futures = {executor.submit(process_item, i): i for i in range(idx, len(queue))}
                        from concurrent.futures import as_completed, TimeoutError as FuturesTimeout
                        for future in as_completed(futures, timeout=None):
                            i = futures[future]
                            try:
                                future.result(timeout=1200)
                            except FuturesTimeout:
                                log_to_js(tab_id, f"⏱️ ТАЙМАУТ задачи #{i+1} (>1200 сек)", "error")
                                queue[i]["status"] = "Failed"
                                queue[i]["progress"] = 0
                                update_ui_queue(tab_id)
                            except Exception as e:
                                log_to_js(tab_id, f"❌ Ошибка задачи #{i+1}: {e}", "error")
                                queue[i]["status"] = "Failed"
                                queue[i]["progress"] = 0
                                update_ui_queue(tab_id)
                    break 
                else:
                    process_item(idx)
                    idx += 1

        try:
            generate_pixabay_log(tab_id, source, save_path)
        except Exception as e:
            log_to_js(tab_id, f"Ошибка создания лога Pixabay: {e}", "warning")

        log_to_js(tab_id, f"Все задачи для {tab_id} обработаны.", "success")
        done_count = sum(1 for q in queue if q.get("status") == "Done")
        failed_count = sum(1 for q in queue if q.get("status") in ("Failed", "Error"))
        _tg_event("download_done", detail=f"✅{done_count} ❌{failed_count} из {len(queue)}")

    except Exception as e:
        log_to_js(tab_id, f"Критическая ошибка загрузки: {e}", "error")
        _tg_event("download_error", detail=str(e)[:200])
        import traceback
        traceback.print_exc()
    finally:
        with active_downloads_lock:
            active_download_tabs.discard(tab_id)
        # 🔥 ГАРАНТИЯ ВЫЗОВА ФИНИША И АВТОРЕТРАЯ (Даже если была критическая ошибка)
        try:
            safe_eel_call("download_complete", tab_id)
        except:
            pass


@eel.expose
def retry_single_item(tab_id, index, source, save_path, trim_start=3, trim_end=6, clip_rules=None):
    """Retry a single failed/cancelled item in a separate thread."""
    tab_stop_flags[tab_id] = False
    config = load_config()
    if not config:
        log_to_js(tab_id, "Заполните config.json рядом с main.py!", "error")
        return

    queue = get_tab_queue(tab_id)
    if index >= len(queue):
        log_to_js(tab_id, f"Индекс {index} за пределами очереди.", "error")
        return

    # Reset item state
    queue[index]["status"] = "Downloading"
    queue[index]["progress"] = 0
    update_ui_queue(tab_id)

    def _retry_worker():
        try:
            _process_single_item(tab_id, index, source, save_path, config, trim_start, trim_end, clip_rules)
            log_to_js(tab_id, f"Повторная загрузка элемента #{index+1} завершена ({queue[index]['status']}).", "info")
        finally:
            update_ui_queue(tab_id)
            safe_eel_call("single_retry_done", tab_id) 

    thread = threading.Thread(target=_retry_worker, daemon=True)
    thread.start()


@eel.expose
def generate_pixabay_log(tab_id, source, save_path):
    queue = get_tab_queue(tab_id)
    if not queue: return
    
    is_pixabay_source = source.startswith("pixabay")
    if not is_pixabay_source: return
    
    log_file_path = os.path.join(save_path, "Pixabay_Links_Log.txt")
    os.makedirs(save_path, exist_ok=True)
    
    with open(log_file_path, "w", encoding="utf-8") as lf:
        lf.write(f"=== ЛОГ ССЫЛОК PIXABAY === Финальная генерация: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        lf.write(f"Всего промптов: {len(queue)}\n")
        lf.write("=" * 70 + "\n")
        
        for idx, item in enumerate(queue):
            if item.get("status") == "Done" and item.get("video_id"):
                file_number = idx + 1
                file_name = f"{file_number:04d}.mp4"
                start_seconds = float(item.get("clip_start", 0.0))
                clip_duration = float(item.get("clip_duration", 0.0))
                end_seconds = start_seconds + clip_duration
                
                def fmt_tc(s):
                    total_seconds = max(0.0, float(s))
                    m = int(total_seconds // 60)
                    sec = total_seconds - (m * 60)
                    sec_text = f"{sec:06.3f}".rstrip('0').rstrip('.')
                    if sec < 10:
                        sec_text = f"0{sec_text}"
                    return f"{m:02d}:{sec_text}"
                
                start_tc = fmt_tc(start_seconds)
                end_tc = fmt_tc(end_seconds)
                pixabay_link = f"https://pixabay.com/videos/id-{item['video_id']}/"
                log_line = f"[{start_tc} - {end_tc}] Файл: {file_name} | Ссылка: {pixabay_link}\n"
                lf.write(log_line)
                
    log_to_js(tab_id, "[ЛОГ] Файл ссылок Pixabay сохранен в папку загрузки.", "info")

@eel.expose
def start_batch_download(tab_id, prompts, source, save_path, trim_start=3, trim_end=6, workers_count=1, clip_rules=None, stock_pool=None):
    config = load_config()
    if not config:
        # log_to_js requires a tab_id, so we use the one passed
        log_to_js(tab_id, "Заполните config.json рядом с main.py!", "error")
        return

    # Explicitly reset queue for this tab
    tab_queues[tab_id] = []
    
    thread = threading.Thread(target=download_task, args=(tab_id, prompts, source, save_path, config, trim_start, trim_end, workers_count, clip_rules, stock_pool))
    thread.daemon = True
    thread.start()



def close_callback(route, websockets):
    if not websockets:
        print("UI closed. Terminating safely...")
        _tg_event("app_close")
        # 1. Посылаем сигнал остановки во все вкладки, чтобы безопасно прервать циклы скачивания и рендера
        for tid in tab_stop_flags:
            tab_stop_flags[tid] = True
        for tid in tab_render_stop_flags:
            tab_render_stop_flags[tid] = True
        time.sleep(0.5)  # даём время TG отправиться

        # 2. Мгновенно закрываем ТОЛЬКО память текущего Python-скрипта.
        # (Никакого taskkill, поэтому Хром и другие вкладки в IDE останутся живы!)
        os._exit(0)

@eel.expose
def get_system_fonts():
    fonts = list_system_fonts()
    return fonts if fonts else ["Arial.ttf", "Times.ttf"]

# ═══════════════════════════════════════════════════════════
#  Stocky non Stop — главный модуль
#  Автор: Азат (Telegram: @inomix, ВКонтакте: @inomix)
#  Контакт: inomixx@gmail.com
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # ═══════════════════════════════════════════════════════════
    #  Stocky non Stop — Pro Edition
    #  Автор: Азат
    #  Telegram: @inomix | ВКонтакте: @inomix | Email: inomixx@gmail.com
    # ═══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  Stocky non Stop — Pro Edition")
    print("  Автор: Азат")
    print("  Telegram: @inomix | ВКонтакте: @inomix | Email: inomixx@gmail.com")
    print("=" * 70)
    
    if not os.path.exists(DEFAULT_DOWNLOAD_DIR):
        os.makedirs(DEFAULT_DOWNLOAD_DIR)
    
    load_config()
    _tg_event("app_start")
    print("Starting Eel app...")
    # === Overlay Module ===
    try:
        import stocky_nonstop.overlay.overlay_api
        print("[OK] Overlay module loaded")
    except Exception as e:
        print(f"[INFO] Overlay module not available: {e}")

    # Добавляем close_callback для убийства процессов при закрытии окна
    eel.start('index.html', size=(1400, 900), port=8011, close_callback=close_callback)
