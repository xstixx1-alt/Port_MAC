# Stocky non Stop — модуль синтеза речи и транскрибации
# Автор: Азат | @inomix | inomixx@gmail.com

import os
import sys
import time
import json
import threading
import subprocess
import re
import requests
import traceback
import logging
import shutil
import uuid
from datetime import datetime
import eel
import tkinter as tk
from tkinter import filedialog
from platform_utils import get_creationflags

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')
MODELS_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# === ДЕТАЛЬНЫЙ ЛОГГЕР VOICER ===
DEBUG_LOG_PATH = os.path.join(BASE_DIR, 'voicer_debug.log')
fh = logging.FileHandler(DEBUG_LOG_PATH, encoding='utf-8', mode='w')
fh.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
voicer_logger = logging.getLogger("VoicerDebug")
voicer_logger.setLevel(logging.DEBUG)
if not voicer_logger.handlers:
    voicer_logger.addHandler(fh)

_whisper_model_cache = {}
_tts_stop_flags = {}
_whisper_stop_flags = {}

# === API CONFIG ===
VOICER_API_BASE = "https://voiceapiru.csv666.ru"
VOICER_API_FALLBACK_BASES = ["https://voiceapi.csv666.ru"]

@eel.expose
def voicer_get_debug_log():
    try:
        if os.path.exists(DEBUG_LOG_PATH):
            with open(DEBUG_LOG_PATH, 'r', encoding='utf-8') as f:
                return {"success": True, "log_content": f.read()}
        return {"success": False, "error": "Лог файл пуст или не существует."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def voicer_safe_eel(func_name, *args):
    try:
        import gevent
        def _execute():
            try:
                func = getattr(eel, func_name, None)
                if func: func(*args)
            except: pass
        gevent.spawn(_execute)
    except: pass

def v_log(tab_id, msg, log_type="info"):
    voicer_safe_eel("voicer_add_log", tab_id, msg, log_type)
    if log_type == "error":
        voicer_logger.error(f"[TAB:{tab_id}] {msg}")
    elif log_type == "warning":
        voicer_logger.warning(f"[TAB:{tab_id}] {msg}")
    else:
        voicer_logger.info(f"[TAB:{tab_id}] {msg}")

def load_config():
    if not os.path.exists(CONFIG_FILE): return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_config(data):
    config = load_config()
    config.update(data)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def load_app_settings_local():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_app_settings_local(data):
    settings = load_app_settings_local()
    settings.update(data or {})
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


def _normalize_voice_presets(raw_presets):
    presets = []
    if not isinstance(raw_presets, list):
        return presets

    for raw in raw_presets:
        if not isinstance(raw, dict):
            continue
        engine = raw.get("engine")
        if engine not in ("standard", "mateo"):
            continue
        preset_id = str(raw.get("id") or uuid.uuid4().hex[:10])
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        preset = {
            "id": preset_id,
            "name": name,
            "engine": engine,
            "standardTemplateUuid": str(raw.get("standardTemplateUuid") or "").strip(),
            "standardTemplateTitle": str(raw.get("standardTemplateTitle") or "").strip(),
            "mateoVoiceId": str(raw.get("mateoVoiceId") or "").strip(),
            "mateoVoiceLabel": str(raw.get("mateoVoiceLabel") or "").strip(),
        }
        presets.append(preset)
    return presets


def load_voice_presets():
    settings = load_app_settings_local()
    return _normalize_voice_presets(settings.get("voicer_voice_presets", []))


def save_voice_presets(presets):
    normalized = _normalize_voice_presets(presets)
    save_app_settings_local({"voicer_voice_presets": normalized})
    return normalized


@eel.expose
def voicer_get_voice_presets():
    return {"success": True, "presets": load_voice_presets()}


@eel.expose
def voicer_save_voice_preset(preset):
    try:
        if not isinstance(preset, dict):
            return {"success": False, "error": "Неверный формат пресета"}

        name = str(preset.get("name") or "").strip()
        engine = str(preset.get("engine") or "").strip()
        if not name:
            return {"success": False, "error": "Введите название шаблона"}
        if engine not in ("standard", "mateo"):
            return {"success": False, "error": "Неизвестный тип войсера"}

        standard_uuid = str(preset.get("standardTemplateUuid") or "").strip()
        mateo_voice_id = str(preset.get("mateoVoiceId") or "").strip()
        if engine == "standard" and not standard_uuid:
            return {"success": False, "error": "Для ElevenLabs API нужно выбрать голосовой шаблон"}
        if engine == "mateo" and not mateo_voice_id:
            return {"success": False, "error": "Для Voicer Mateo нужен Voice ID"}

        presets = load_voice_presets()
        preset_id = str(preset.get("id") or uuid.uuid4().hex[:10])
        payload = {
            "id": preset_id,
            "name": name,
            "engine": engine,
            "standardTemplateUuid": standard_uuid,
            "standardTemplateTitle": str(preset.get("standardTemplateTitle") or "").strip(),
            "mateoVoiceId": mateo_voice_id,
            "mateoVoiceLabel": str(preset.get("mateoVoiceLabel") or "").strip(),
        }

        replaced = False
        for idx, current in enumerate(presets):
            if current.get("id") == preset_id:
                presets[idx] = payload
                replaced = True
                break
        if not replaced:
            presets.append(payload)

        saved = save_voice_presets(presets)
        return {"success": True, "preset": payload, "presets": saved}
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def voicer_delete_voice_preset(preset_id):
    try:
        preset_id = str(preset_id or "").strip()
        if not preset_id:
            return {"success": False, "error": "Не передан id шаблона"}
        presets = [preset for preset in load_voice_presets() if preset.get("id") != preset_id]
        saved = save_voice_presets(presets)
        return {"success": True, "presets": saved}
    except Exception as e:
        return {"success": False, "error": str(e)}


def normalize_path(path):
    return os.path.normpath(path) if path else ""


def pick_srt_output_dir(file_path, explicit_dir=""):
    file_path = normalize_path(file_path)
    explicit_dir = normalize_path(explicit_dir)
    app_settings = load_app_settings_local()
    default_dir = normalize_path(app_settings.get("voicer_srt_save_dir", ""))

    if explicit_dir:
        return explicit_dir, "selected"
    if default_dir:
        return default_dir, "global_default"
    return os.path.dirname(file_path), "source"

@eel.expose
def voicer_save_api_key(api_key):
    save_config({"elevenlabs_api_key": api_key})
    return {"success": True}

@eel.expose
def voicer_get_api_key():
    return load_config().get("elevenlabs_api_key", "")

def _normalize_tts_template(raw_template):
    if not isinstance(raw_template, dict):
        return None
    uuid_value = (
        raw_template.get("uuid")
        or raw_template.get("id")
        or raw_template.get("template_uuid")
        or raw_template.get("templateUuid")
        or raw_template.get("voice_id")
        or raw_template.get("voiceId")
    )
    if not uuid_value:
        return None
    title = (
        raw_template.get("name")
        or raw_template.get("title")
        or raw_template.get("label")
        or raw_template.get("voice_name")
        or raw_template.get("voiceName")
        or uuid_value
    )
    return {"uuid": str(uuid_value), "title": str(title)}

def _extract_tts_templates(data):
    if isinstance(data, list):
        raw_templates = data
    elif isinstance(data, dict):
        raw_templates = None
        for key in ("templates", "items", "data", "voices", "results"):
            value = data.get(key)
            if isinstance(value, list):
                raw_templates = value
                break
    else:
        raw_templates = None

    if not isinstance(raw_templates, list):
        return None

    templates = []
    for raw_template in raw_templates:
        template = _normalize_tts_template(raw_template)
        if template:
            templates.append(template)
    return templates

def _voicer_api_bases():
    bases = [VOICER_API_BASE] + list(VOICER_API_FALLBACK_BASES)
    seen = set()
    unique_bases = []
    for base in bases:
        base = str(base or "").rstrip("/")
        if base and base not in seen:
            unique_bases.append(base)
            seen.add(base)
    return unique_bases

def _voicer_request(method, path, **kwargs):
    last_error = None
    for base in _voicer_api_bases():
        url = f"{base}{path}"
        try:
            response = requests.request(method, url, **kwargs)
            response._voicer_base_url = base
            return response
        except requests.exceptions.RequestException as e:
            last_error = e
            voicer_logger.warning("[Voicer API] %s %s failed: %s", method.upper(), url, e)
    if last_error:
        raise last_error
    raise requests.exceptions.ConnectionError("No Voicer API base URL configured")

# === VOICER MATEO API ===
VOICER_MATEO_API_BASE = "https://voicer.mat3u.com/api/v1"

@eel.expose
def voicer_save_mateo_token(token):
    save_config({"voicer_mateo_api_key": token})
    return {"success": True}

@eel.expose
def voicer_get_mateo_token():
    return load_config().get("voicer_mateo_api_key", "")

@eel.expose
def voicer_mateo_tts_start(tab_id, token, text, voice_id, model_id, split_type,
                           split_output, auto_pause_enabled, auto_pause_duration,
                           auto_pause_frequency, save_path, auto_transcribe,
                           whisper_model, whisper_lang, custom_filename="", speed_up=0):
    _tts_stop_flags[tab_id] = False

    def worker():
        try:
            v_log(tab_id, "--- СТАРТ СИНТЕЗА РЕЧИ (Voicer Mateo) ---", "info")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Создание задачи...", "text-yellow-400")
            voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 10)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            # 1. Создаём задачу
            payload = {
                "text": text,
                "voice_id": voice_id,
                "model_id": model_id,
                "split_type": split_type,
                "split_output": split_output,
                "auto_pause_enabled": auto_pause_enabled,
                "auto_pause_duration": float(auto_pause_duration),
                "auto_pause_frequency": int(auto_pause_frequency),
            }

            create_url = f"{VOICER_MATEO_API_BASE}/voice/synthesize"
            c_resp = requests.post(create_url, json=payload, headers=headers, timeout=30)

            if c_resp.status_code == 401:
                raise Exception("Ошибка авторизации: неверный токен Voicer Mateo")
            if c_resp.status_code == 403:
                raise Exception("Доступ запрещён: исчерпан лимит или нет подписки")
            if c_resp.status_code not in [200, 201]:
                raise Exception(f"Ошибка создания задачи: {c_resp.status_code} {c_resp.text[:200]}")

            resp_data = c_resp.json()
            task_id = resp_data.get("task_id")
            chunks_count = resp_data.get("chunks_count", 1)
            v_log(tab_id, f"✅ Задача #{task_id} создана. Чанков: {chunks_count}. Ожидание...", "info")

            # 2. Polling статуса
            voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 20)
            while True:
                if _tts_stop_flags.get(tab_id):
                    raise Exception("Отменено пользователем")

                status_url = f"{VOICER_MATEO_API_BASE}/voice/status/{task_id}"
                s_resp = requests.get(status_url, headers=headers, timeout=30)
                s_resp.raise_for_status()
                status_data = s_resp.json()
                current_status = status_data.get("status")

                progress_pct = status_data.get("progress", 0)
                if progress_pct:
                    mapped = 20 + int(progress_pct * 0.65)
                    voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", mapped)

                if current_status == "processing":
                    voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Генерация...", "text-pink-400")
                elif current_status == "completed":
                    v_log(tab_id, "✅ Задача завершена успешно!", "success")
                    break
                elif current_status == "censored":
                    # Логируем заблокированные чанки
                    blocked = status_data.get("blocked_chunks", [])
                    v_log(tab_id, f"⚠️ Цензура ElevenLabs: заблокировано {len(blocked)} чанк(ов).", "warning")
                    for chunk in blocked:
                        v_log(tab_id, f"  🚫 Чанк #{chunk.get('index', '?')}: «{chunk.get('text', '')[:80]}...»", "warning")
                    raise Exception(f"Задача заблокирована цензурой ElevenLabs ({len(blocked)} чанков). Исправьте текст и повторите.")
                elif current_status in ["error", "failed"]:
                    raise Exception(f"Ошибка на стороне сервера Mateo: {status_data.get('message', 'неизвестная ошибка')}")

                time.sleep(3)

            # 3. Скачиваем результат
            v_log(tab_id, "📥 Скачивание аудио...", "info")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Скачивание...", "text-yellow-400")
            voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 88)

            download_url = f"{VOICER_MATEO_API_BASE}/voice/download/{task_id}"
            r_resp = requests.get(download_url, headers=headers, timeout=60)
            r_resp.raise_for_status()

            os.makedirs(save_path, exist_ok=True)

            # Определяем имя файла и расширение
            if custom_filename:
                safe_name = re.sub(r'[\\/*?:"<>|]', "", custom_filename).strip()
                if not safe_name:
                    safe_name = f"mateo_{task_id}"
            else:
                safe_name = f"mateo_{task_id}"

            # Если split_output — это ZIP-архив
            if split_output:
                final_path = os.path.join(save_path, f"{safe_name}.zip")
                with open(final_path, "wb") as f:
                    f.write(r_resp.content)
                v_log(tab_id, f"📦 ZIP-архив сохранён: {final_path}", "success")
                voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 100)
                voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Успешно завершено", "text-green-400")
                voicer_safe_eel("voicer_task_done", tab_id, "synthesis", True, final_path)
                return

            # MP3 — возможно с ускорением
            final_audio_path = os.path.join(save_path, f"{safe_name}.mp3")

            if speed_up > 0:
                temp_audio_path = os.path.join(save_path, f"temp_mateo_{task_id}.mp3")
                with open(temp_audio_path, "wb") as f:
                    f.write(r_resp.content)

                v_log(tab_id, f"⚡ Ускорение аудио на {speed_up}% (FFmpeg)...", "warning")
                voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Ускорение...", "text-yellow-400")

                atempo = 1.0 + (speed_up / 100.0)
                cflags = get_creationflags()
                subprocess.run([
                    "ffmpeg", "-y", "-i", temp_audio_path,
                    "-filter:a", f"atempo={atempo}",
                    "-q:a", "0", final_audio_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=cflags)

                try:
                    os.remove(temp_audio_path)
                except:
                    pass
            else:
                with open(final_audio_path, "wb") as f:
                    f.write(r_resp.content)

            voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 100)
            v_log(tab_id, f"✅ Аудио сохранено: {final_audio_path}", "success")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Успешно завершено", "text-green-400")
            voicer_safe_eel("voicer_task_done", tab_id, "synthesis", True, final_audio_path)

            # 4. Авто-транскрибация
            if auto_transcribe:
                v_log(tab_id, "📝 Авто-перенос в транскрибацию...", "info")
                voicer_whisper_start(tab_id, final_audio_path, whisper_model, whisper_lang, text)

        except Exception as e:
            v_log(tab_id, f"ОШИБКА СИНТЕЗА (Mateo): {str(e)}", "error")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Ошибка", "text-red-400")
            voicer_safe_eel("voicer_task_done", tab_id, "synthesis", False, str(e))

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True}

@eel.expose
def voicer_browse_file(file_types="all"):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        # 🔥 РАСШИРЕННЫЕ ФИЛЬТРЫ ПО ТИПУ
        if file_types == "audio":
            ftypes = [("Аудио", "*.mp3 *.wav *.m4a *.flac *.ogg *.aac"), ("All files", "*.*")]
            title = "Выберите аудиофайл"
        elif file_types == "image":
            ftypes = [("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All files", "*.*")]
            title = "Выберите изображение"
        elif file_types == "video":
            ftypes = [("Видео", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All files", "*.*")]
            title = "Выберите видеофайл"
        elif file_types == "disclaimer":
            # Видео ИЛИ картинка
            ftypes = [
                ("Видео или Картинка", "*.mp4 *.mkv *.avi *.mov *.webm *.jpg *.jpeg *.png *.bmp *.webp"),
                ("Видео", "*.mp4 *.mkv *.avi *.mov *.webm"),
                ("Картинки", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("All files", "*.*")
            ]
            title = "Выберите дисклеймер (видео или картинка)"
        elif file_types == "srt":
            ftypes = [("Субтитры", "*.srt"), ("All files", "*.*")]
            title = "Выберите файл субтитров"
        elif file_types == "media":
            ftypes = [("Media", "*.mp3 *.wav *.mp4 *.mkv *.avi *.mov"), ("All files", "*.*")]
            title = "Выберите медиафайл"
        else:
            ftypes = [("All files", "*.*")]
            title = "Выберите файл"
        
        path = filedialog.askopenfilename(title=title, filetypes=ftypes)
        root.destroy()
        return {"success": True, "path": path} if path else {"success": False, "error": "Отменено"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def voicer_browse_folder():
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(title="Выберите папку")
        root.destroy()
        return {"success": True, "path": path} if path else {"success": False, "error": "Отменено"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def voicer_read_text_file(file_path):
    try:
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": f"Файл не найден: {file_path}"}
        with open(file_path, 'r', encoding='utf-8') as f:
            return {"success": True, "text": f.read()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def voicer_save_srt_default_dir(folder_path):
    try:
        if not folder_path:
            save_app_settings_local({"voicer_srt_save_dir": ""})
            return {"success": True, "path": ""}
        os.makedirs(folder_path, exist_ok=True)
        save_app_settings_local({"voicer_srt_save_dir": normalize_path(folder_path)})
        return {"success": True, "path": normalize_path(folder_path)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def voicer_save_srt_as(source_srt_path):
    try:
        if not source_srt_path or not os.path.exists(source_srt_path):
            return {"success": False, "error": f"SRT файл не найден: {source_srt_path}"}

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        base_name = os.path.basename(source_srt_path)
        target_path = filedialog.asksaveasfilename(
            title="Сохранить SRT как...",
            defaultextension=".srt",
            initialfile=base_name,
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")]
        )
        root.destroy()

        if not target_path:
            return {"success": False, "error": "Отменено пользователем"}

        shutil.copyfile(source_srt_path, target_path)
        return {"success": True, "path": normalize_path(target_path)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def voicer_pick_text_file(tab_id):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="Выберите текстовый файл",
            filetypes=[("Prompt files", "*.txt *.docx *.md"), ("All files", "*.*")]
        )
        root.destroy()
        
        if not path:
            return {"success": False, "error": "Отменено"}
            
        text = ""
        if path.lower().endswith('.docx'):
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(path) as z:
                with z.open('word/document.xml') as f:
                    tree = ET.parse(f)
                    root_xml = tree.getroot()
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    texts = []
                    for p in root_xml.findall('.//w:p', ns):
                        para_text_parts = [node.text for node in p.findall('.//w:t', ns) if node.text]
                        para_text = "".join(str(t) for t in para_text_parts)
                        if para_text.strip():
                            texts.append(para_text.strip())
                    text = "\n".join(texts)
        else:
            for enc in ('utf-8-sig', 'utf-8', 'cp1251', 'latin-1'):
                try:
                    with open(path, 'r', encoding=enc) as f:
                        text = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    text = f.read()
        
        # Извлекаем путь к папке и имя файла без расширения
        folder = os.path.dirname(path)
        filename = os.path.splitext(os.path.basename(path))[0]
        
        return {"success": True, "text": text, "folder": folder, "filename": filename}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def voicer_tts_get_templates(api_key):
    if not api_key:
        return {"success": False, "error": "API ключ пуст"}
    try:
        api_key = str(api_key).strip()
        headers = {"X-API-Key": api_key}

        voicer_logger.info("[TTS templates] Requesting templates from %s/templates", VOICER_API_BASE)
        resp = _voicer_request("get", "/templates", headers=headers, timeout=15)
        voicer_logger.info("[TTS templates] /templates base=%s status=%s", getattr(resp, "_voicer_base_url", ""), resp.status_code)
        if resp.status_code in (401, 403):
            return {"success": False, "error": "Неверный ключ (Отказано в доступе)"}

        try:
            data = resp.json()
        except Exception:
            data = None

        if resp.status_code == 200:
            templates = _extract_tts_templates(data)
            if templates is not None:
                voicer_logger.info("[TTS templates] Parsed templates=%s", len(templates))
                return {"success": True, "templates": templates}
            voicer_logger.warning("[TTS templates] Unknown JSON format: %s", str(data)[:800])

        voicer_logger.info("[TTS templates] Checking key via %s/balance", VOICER_API_BASE)
        balance_resp = _voicer_request("get", "/balance", headers=headers, timeout=15)
        voicer_logger.info("[TTS templates] /balance base=%s status=%s", getattr(balance_resp, "_voicer_base_url", ""), balance_resp.status_code)
        if balance_resp.status_code in (401, 403):
            return {"success": False, "error": "Неверный ключ (Отказано в доступе)"}

        balance_data = None
        try:
            balance_data = balance_resp.json()
        except Exception:
            pass

        if balance_resp.status_code == 200 and isinstance(balance_data, dict):
            if "balance" in balance_data or "telegram_id" in balance_data or "balance_text" in balance_data:
                return {
                    "success": True,
                    "templates": [],
                    "warning": "Ключ валиден, но шаблоны не были получены"
                }

        if isinstance(data, dict):
            err_msg = data.get("detail") or data.get("error") or data.get("message") or "Неизвестная ошибка"
            return {"success": False, "error": f"Ошибка {resp.status_code}: {err_msg}"}

        if data is None:
            return {"success": False, "error": f"Сервер вернул не JSON. Код: {resp.status_code}"}

        return {"success": False, "error": f"Неверный формат ответа Voicer. Код: {resp.status_code}"}
    except requests.exceptions.ConnectionError as e:
        voicer_logger.exception("[TTS templates] Connection error")
        return {
            "success": False,
            "error": "Нет соединения с доменами Voicer API. Проверьте интернет, DNS, VPN/прокси или блокировку антивирусом.",
            "details": str(e)
        }
    except requests.exceptions.Timeout as e:
        voicer_logger.exception("[TTS templates] Timeout")
        return {
            "success": False,
            "error": "Тайм-аут при загрузке шаблонов Voicer. Сервер не ответил за 15 секунд.",
            "details": str(e)
        }
    except requests.exceptions.RequestException as e:
        voicer_logger.exception("[TTS templates] Request error")
        return {"success": False, "error": f"Ошибка сети при загрузке шаблонов: {e}"}
    except Exception as e:
        voicer_logger.exception("[TTS templates] Unexpected error")
        return {"success": False, "error": str(e)}

@eel.expose
def voicer_tts_start(tab_id, api_key, text, template_uuid, save_path, auto_transcribe, whisper_model, whisper_lang, custom_filename="", speed_up=0):
    _tts_stop_flags[tab_id] = False
    
    def worker():
        try:
            v_log(tab_id, "--- СТАРТ СИНТЕЗА РЕЧИ ---", "info")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Создание задачи...", "text-yellow-400")
            voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 10)
            
            headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
            
            # 1. Создаем задачу
            payload = {
                "text": text,
                "template_uuid": template_uuid
            }
            
            c_resp = _voicer_request("post", "/tasks", json=payload, headers=headers, timeout=30)
            if c_resp.status_code not in [200, 201]:
                raise Exception(f"Ошибка создания задачи: {c_resp.status_code} {c_resp.text}")
            active_api_base = getattr(c_resp, "_voicer_base_url", VOICER_API_BASE)
                
            task_id = c_resp.json().get("task_id")
            v_log(tab_id, f"Задача #{task_id} создана в очереди через {active_api_base}. Ожидание...", "info")
            
            # 2. Ожидаем выполнения (Polling)
            while True:
                if _tts_stop_flags.get(tab_id):
                    raise Exception("Отменено пользователем")
                    
                s_resp = requests.get(f"{active_api_base}/tasks/{task_id}/status", headers=headers, timeout=30)
                s_resp.raise_for_status()
                status_data = s_resp.json()
                current_status = status_data.get("status")
                
                if current_status == "processing":
                    voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Генерация...", "text-pink-400")
                    voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 50)
                elif current_status == "ending":
                    break # Готово
                elif current_status in ["error", "error_handled"]:
                    raise Exception("Ошибка на стороне сервера (средства возвращены)")
                    
                time.sleep(2)
            
            # 3. Скачиваем результат
            v_log(tab_id, "Генерация завершена. Скачивание аудио...", "info")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Скачивание...", "text-yellow-400")
            voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 85)
            
            r_resp = requests.get(f"{active_api_base}/tasks/{task_id}/result", headers=headers, timeout=60)
            r_resp.raise_for_status()
            
            os.makedirs(save_path, exist_ok=True)
            
            # 🔥 ИСПОЛЬЗУЕМ ИМЯ ИСХОДНОГО ФАЙЛА, ЕСЛИ ОНО ПЕРЕДАНО
            if custom_filename:
                safe_name = re.sub(r'[\\/*?:"<>|]', "", custom_filename).strip()
                if not safe_name: safe_name = f"voice_{task_id}"
                final_audio_path = os.path.join(save_path, f"{safe_name}.mp3")
            else:
                final_audio_path = os.path.join(save_path, f"voice_{task_id}.mp3")
                
            if speed_up > 0:
                temp_audio_path = os.path.join(save_path, f"temp_voice_{task_id}.mp3")
                with open(temp_audio_path, "wb") as f:
                    f.write(r_resp.content)
                
                v_log(tab_id, f"Ускорение аудио на {speed_up}% (FFmpeg)...", "warning")
                voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Ускорение...", "text-yellow-400")
                
                atempo = 1.0 + (speed_up / 100.0)
                cflags = get_creationflags()
                subprocess.run([
                    "ffmpeg", "-y", "-i", temp_audio_path,
                    "-filter:a", f"atempo={atempo}",
                    "-q:a", "0", final_audio_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=cflags)
                
                try: os.remove(temp_audio_path)
                except: pass
            else:
                with open(final_audio_path, "wb") as f:
                    f.write(r_resp.content)
                
            voicer_safe_eel("voicer_update_progress", tab_id, "synthesis", 100)
            v_log(tab_id, f"Аудио успешно сохранено: {final_audio_path}", "success")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Успешно завершено", "text-green-400")
            voicer_safe_eel("voicer_task_done", tab_id, "synthesis", True, final_audio_path)
            
            # 4. Автоматическая транскрибация
            if auto_transcribe:
                v_log(tab_id, "📝 Авто-перенос в транскрибацию...", "info")
                voicer_whisper_start(tab_id, final_audio_path, whisper_model, whisper_lang, text)
                
        except Exception as e:
            v_log(tab_id, f"ОШИБКА СИНТЕЗА: {str(e)}", "error")
            voicer_safe_eel("voicer_update_status", tab_id, "synthesis", "Ошибка", "text-red-400")
            voicer_safe_eel("voicer_task_done", tab_id, "synthesis", False, str(e))
            
    threading.Thread(target=worker, daemon=True).start()
    return {"success": True}

@eel.expose
def voicer_scan_text_folder(folder_path):
    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "error": "Папка не существует"}

    import re
    # Ищет только файлы вида "scenario (1).txt" или "scenario (12).docx"
    pattern = re.compile(r'^scenario\s*\((\d+)\)\.(txt|md|docx)$', re.IGNORECASE)
    
    # Группируем файлы: словарь папок -> словарь номеров -> словарь форматов
    # scenarios[папка][номер_в_скобках] = {'txt': 'путь', 'docx': 'путь'}
    scenarios_by_folder = {}
    
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            match = pattern.match(file)
            if match:
                sort_num = int(match.group(1))
                ext = match.group(2).lower()
                full_path = os.path.join(root, file)
                
                if root not in scenarios_by_folder:
                    scenarios_by_folder[root] = {}
                if sort_num not in scenarios_by_folder[root]:
                    scenarios_by_folder[root][sort_num] = {}
                    
                scenarios_by_folder[root][sort_num][ext] = full_path

    files_data = []
    
    # Теперь проходим по сгруппированным данным и выбираем приоритетный формат
    for root, nums_dict in scenarios_by_folder.items():
        for sort_num, exts_dict in nums_dict.items():
            
            # Приоритет: берем txt, если его нет - берем docx
            selected_path = exts_dict.get('txt') or exts_dict.get('md') or exts_dict.get('docx')
            
            if not selected_path:
                continue
                
            filename = os.path.splitext(os.path.basename(selected_path))[0]
            folder = os.path.dirname(selected_path).replace('\\', '/')
            ext = selected_path.lower().split('.')[-1]
            text = ""
            
            try:
                if ext == 'docx':
                    import zipfile
                    import xml.etree.ElementTree as ET
                    with zipfile.ZipFile(selected_path) as z:
                        with z.open('word/document.xml') as f:
                            tree = ET.parse(f)
                            root_xml = tree.getroot()
                            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                            texts = []
                            for p in root_xml.findall('.//w:p', ns):
                                para_text_parts = [node.text for node in p.findall('.//w:t', ns) if node.text]
                                para_text = "".join(str(t) for t in para_text_parts)
                                if para_text.strip():
                                    texts.append(para_text.strip())
                            text = "\n".join(texts)
                else:
                    for enc in ('utf-8-sig', 'utf-8', 'cp1251', 'latin-1'):
                        try:
                            with open(selected_path, 'r', encoding=enc) as f:
                                text = f.read()
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        with open(selected_path, 'r', encoding='utf-8', errors='replace') as f:
                            text = f.read()

                files_data.append({
                    "folder": folder,
                    "filename": filename,
                    "text": text,
                    "sort_num": sort_num
                })
            except Exception as e:
                print(f"Error reading {selected_path}: {e}")

    # Сортируем сначала по имени папки, затем по номеру в скобках (1, 2, 3... 10)
    files_data.sort(key=lambda x: (x["folder"], x["sort_num"]))
    
    # Удаляем служебное поле перед отправкой в JS
    for item in files_data:
        del item["sort_num"]

    return {"success": True, "files": files_data}

@eel.expose
def voicer_scan_audio_folder(folder_path):
    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "error": "Папка не существует"}
    
    files_data = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            ext = file.lower()
            if ext.endswith(('.mp3', '.wav', '.m4a', '.flac', '.mp4', '.mkv', '.avi', '.mov', '.webm')):
                full_path = os.path.join(root, file)
                filename = os.path.splitext(file)[0]
                
                prompt_text = ""
                txt_path = os.path.join(root, f"{filename}.txt")
                if os.path.exists(txt_path):
                    try:
                        with open(txt_path, 'r', encoding='utf-8') as f:
                            prompt_text = f.read()
                    except: pass
                    
                files_data.append({
                    "path": full_path.replace('\\', '/'),
                    "filename": filename,
                    "prompt": prompt_text
                })
    return {"success": True, "files": files_data}

class ThreadSafeWhisperRedirector:
    def __init__(self, original_stdout):
        self.original = original_stdout
        self.active_tabs = {}
        self.segment_pattern = re.compile(r"\[(?:(\d+):)?(\d+):(\d+)\.\d+\s*-->")
        self.buffer = ""

    def register(self, tab_id, duration):
        self.active_tabs[tab_id] = {"duration": duration if duration > 0 else 1.0, "segments": 0}

    def unregister(self, tab_id):
        self.active_tabs.pop(tab_id, None)

    def write(self, msg):
        try: self.original.write(msg)
        except: pass

        if not self.active_tabs or not msg: 
            return

        self.buffer += msg
        if '\n' in self.buffer or '\r' in self.buffer:
            lines = self.buffer.replace('\r', '\n').split('\n')
            self.buffer = lines.pop() # Оставляем неполную строку в буфере
            
            for line in lines:
                clean_msg = line.strip()
                if not clean_msg: continue
                
                # Игнорируем спам от прогресс-бара tqdm ffmpeg/whisper
                if "100%|" in clean_msg or "it/s]" in clean_msg:
                    continue
                
                seg_match = self.segment_pattern.search(clean_msg)
                for tab_id, state in list(self.active_tabs.items()):
                    if seg_match:
                        groups = seg_match.groups()
                        hours = int(groups[0]) if groups[0] else 0
                        mins, secs = int(groups[1]), int(groups[2])
                        current_time = hours * 3600 + mins * 60 + secs
                        progress = min(current_time / state["duration"], 1.0) * 100
                        voicer_safe_eel("voicer_update_progress", tab_id, "transcription", progress)
                        state["segments"] += 1
                        
                    # Отправляем сам текст в UI
                    v_log(tab_id, clean_msg, "info")

        # 🔥 ГЛАВНЫЙ ФИКС GEVENT: Отдаем квант времени веб-сокетам Eel
        try:
            import gevent
            gevent.sleep(0.01)
        except:
            pass

    def flush(self):
        try: self.original.flush()
        except: pass

_global_whisper_redirector = ThreadSafeWhisperRedirector(sys.stdout)
sys.stdout = _global_whisper_redirector

# 🔥 Глобальная блокировка (Очередь) для Whisper
_whisper_queue_lock = threading.Lock()

@eel.expose
def voicer_whisper_start(tab_id, file_path, model="small", language="ru", initial_prompt="", save_dir=""):
    try:
        import whisper
        from whisper.utils import get_writer
        import torch
    except ImportError as ie:
        v_log(tab_id, f"❌ Библиотека не установлена: {ie}", "error")
        voicer_safe_eel("voicer_task_done", tab_id, "transcription", False, "No whisper")
        return {"success": False}

    _whisper_stop_flags[tab_id] = False

    def worker():
        # СНАЧАЛА ЖДЕМ В ОЧЕРЕДИ
        v_log(tab_id, "⏳ Ожидание в очереди (Whisper занят другим проектом)...", "warning")
        voicer_safe_eel("voicer_update_status", tab_id, "transcription", "В очереди", "text-gray-400")

        # 🔥 БЛОКИРУЕМ ПОТОК. Сюда зайдет только 1 проект за раз!
        with _whisper_queue_lock:
            # Если пользователь отменил задачу, пока она висела в очереди
            if _whisper_stop_flags.get(tab_id):
                v_log(tab_id, "❌ Отменено до начала распознавания", "warning")
                return

            worker_state = {"stage": "init", "start": time.time(), "alive": True, "duration": 1.0}

            def heartbeat():
                ping_count = 0
                while worker_state["alive"]:
                    time.sleep(2)
                    if not worker_state["alive"]:
                        break
                    
                    stage = worker_state["stage"]
                    elapsed = time.time() - worker_state["start"]
                    
                    if stage == "transcribing":
                        duration = worker_state.get("duration", 1.0)
                        estimated_total = duration / 5.0
                        progress = min(elapsed / max(estimated_total, 1.0), 0.95) * 100
                        voicer_safe_eel("voicer_update_progress", tab_id, "transcription", progress)
                        
                        ping_count += 1
                        if ping_count % 5 == 0:
                            v_log(tab_id, f"💓 Whisper работает... прошло {int(elapsed)}с (примерно {int(progress)}%)", "info")
                            voicer_logger.info(f"[HEARTBEAT] {int(elapsed)}с | Стадия: {stage} | Прогресс: {progress:.1f}%")

            hb_thread = threading.Thread(target=heartbeat, daemon=True)
            hb_thread.start()

            try:
                v_log(tab_id, "--- СТАРТ ТРАНСКРИБАЦИИ WHISPER ---", "info")
                voicer_safe_eel("voicer_update_status", tab_id, "transcription", "Подготовка...", "text-yellow-400")
                
                worker_state["stage"] = "ffmpeg"
                audio_path = file_path
                if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
                    v_log(tab_id, "Извлекаем аудио из видео (FFmpeg)...", "info")
                    audio_path = os.path.splitext(file_path)[0] + ".mp3"
                    cflags = get_creationflags()
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", file_path, "-q:a", "0", "-map", "a", audio_path],
                        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=cflags
                    )
                
                worker_state["stage"] = "load_audio"
                voicer_safe_eel("voicer_update_status", tab_id, "transcription", "Загрузка аудио...", "text-yellow-400")
                audio_array = whisper.load_audio(audio_path)
                duration = audio_array.shape[0] / whisper.audio.SAMPLE_RATE
                worker_state["duration"] = duration
                v_log(tab_id, f"Длительность трека: {duration:.1f} сек.", "info")

                worker_state["stage"] = "load_model"
                # MPS (Apple Silicon GPU) не поддерживается openai-whisper стабильно —
                # модель крашится при загрузке, а фоллбэк на CPU тоже может сломаться
                # из-за грязного состояния PyTorch. Сразу на CPU для Mac.
                if torch.cuda.is_available():
                    device = "cuda"
                else:
                    device = "cpu"
                voicer_logger.info(f"Определено устройство: {device.upper()}")
                v_log(tab_id, f"Устройство: {device.upper()}", "info")

                if model not in _whisper_model_cache:
                    v_log(tab_id, f"Загрузка модели ({model}) на {device.upper()}... (первый раз может занять минуту)", "warning")
                    voicer_safe_eel("voicer_update_status", tab_id, "transcription", f"Модель {model}...", "text-yellow-400")
                    _whisper_model_cache[model] = whisper.load_model(model, device=device, download_root=MODELS_DIR)
                
                w_model = _whisper_model_cache[model]
                
                options = {"verbose": False, "language": language}
                if initial_prompt:
                    options["initial_prompt"] = initial_prompt
                if device == "cpu":
                    options["fp16"] = False
                
                worker_state["stage"] = "transcribing"
                voicer_safe_eel("voicer_update_status", tab_id, "transcription", "Распознавание...", "text-green-400")
                v_log(tab_id, f"🎬 Запускаю распознавание (трек {duration:.0f} сек)...", "info")
                voicer_logger.info(f"[WORKER] Запуск transcribe()")
                
                _global_whisper_redirector.register(tab_id, duration)
                
                transcribe_start = time.time()
                result = w_model.transcribe(audio_array, **options)
                transcribe_elapsed = time.time() - transcribe_start
                
                _global_whisper_redirector.unregister(tab_id)
                
                voicer_logger.info(f"[WORKER] transcribe() завершён за {transcribe_elapsed:.1f}с")
                v_log(tab_id, f"✅ Распознавание завершено за {transcribe_elapsed:.1f}с. Найдено сегментов: {len(result.get('segments', []))}", "success")
                
                worker_state["stage"] = "outputting_segments"
                segments = result.get("segments", [])
                
                def format_tc(sec):
                    h = int(sec // 3600)
                    m = int((sec % 3600) // 60)
                    s = int(sec % 60)
                    if h > 0:
                        return f"{h:02d}:{m:02d}:{s:02d}"
                    return f"{m:02d}:{s:02d}"
                
                for i, seg in enumerate(segments):
                    if _whisper_stop_flags.get(tab_id):
                        break
                    seg_start = seg.get("start", 0)
                    seg_end = seg.get("end", 0)
                    seg_text = seg.get("text", "").strip()
                    if not seg_text:
                        continue
                    line = f"[{format_tc(seg_start)} --> {format_tc(seg_end)}]  {seg_text}"
                    v_log(tab_id, line, "info")
                
                v_log(tab_id, f"📝 Все {len(segments)} сегментов выведены.", "info")
                
                worker_state["stage"] = "writing"
                output_dir, save_mode = pick_srt_output_dir(file_path, save_dir)
                os.makedirs(output_dir, exist_ok=True)

                source_stem = os.path.splitext(os.path.basename(file_path))[0]
                temp_source_path = os.path.join(output_dir, f"{source_stem}{os.path.splitext(file_path)[1]}")
                writer = get_writer("srt", output_dir)
                writer(result, temp_source_path, {"max_line_width": None, "max_line_count": None, "highlight_words": False})

                generated_default_path = os.path.join(output_dir, f"{source_stem}.srt")
                final_srt_path = generated_default_path

                if not os.path.exists(final_srt_path):
                    attempted_path = final_srt_path
                    v_log(tab_id, f"❌ Ошибка сохранения SRT. Ожидался файл: {attempted_path}", "error")
                    raise FileNotFoundError(attempted_path)

                worker_state["stage"] = "done"
                save_note = {
                    "selected": "в выбранную папку",
                    "global_default": "в папку по умолчанию",
                    "source": "рядом с исходником",
                }.get(save_mode, "в папку сохранения")
                v_log(tab_id, f"✅ SRT сохранен: {final_srt_path}", "success")
                v_log(tab_id, f"📁 Режим сохранения: {save_note}", "info")
                voicer_safe_eel("voicer_update_progress", tab_id, "transcription", 100)
                voicer_safe_eel("voicer_update_status", tab_id, "transcription", "Готово! SRT сохранен.", "text-green-400")
                voicer_safe_eel("voicer_task_done", tab_id, "transcription", True, final_srt_path)
                
            except Exception as e:
                _global_whisper_redirector.unregister(tab_id)
                err_trace = traceback.format_exc()
                voicer_logger.error(f"CRITICAL WORKER ERROR:\n{err_trace}")
                v_log(tab_id, f"❌ ОШИБКА: {str(e)}", "error")
                voicer_safe_eel("voicer_update_status", tab_id, "transcription", "Ошибка", "text-red-400")
                voicer_safe_eel("voicer_task_done", tab_id, "transcription", False, str(e))
            finally:
                worker_state["alive"] = False

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True}
