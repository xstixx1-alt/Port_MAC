# Stocky non Stop — модуль AI-генерации промптов
# Автор: Азат | Telegram: @inomix | Email: inomixx@gmail.com

import os
import eel
import threading
import re
import math
import json

try:
    from stocky_nonstop.overlay.deepseek_engine import DeepSeekEngine
    from stocky_nonstop.ai_router import persist_ai_selection
except ImportError as e:
    print(f"Warning: DeepSeekEngine for Prompter could not be loaded: {e}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
PROMPTER_CANCEL_EVENTS = {}
PROMPTER_CANCEL_LOCK = threading.Lock()


def prompter_safe_eel(func_name, *args):
    try:
        import gevent
        def _execute():
            try:
                func = getattr(eel, func_name, None)
                if func: func(*args)
            except: pass
        gevent.spawn(_execute)
    except: pass


@eel.expose
def prompter_stop_generation(tab_id):
    with PROMPTER_CANCEL_LOCK:
        cancel_event = PROMPTER_CANCEL_EVENTS.get(str(tab_id))
        if cancel_event:
            cancel_event.set()
    prompter_safe_eel("add_log_entry", tab_id, "⏹ Остановка генерации: новые API-запросы больше не запускаются", "warning")
    prompter_safe_eel("prompter_update_status", tab_id, "Остановка генерации...", "text-red-300")
    return {"success": bool(cancel_event)}


@eel.expose
def prompter_browse_docx():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Выберите файл с системным промптом",
        filetypes=[("Prompt files", "*.docx *.txt *.md"), ("All files", "*.*")]
    )
    return file_path


@eel.expose
def prompter_browse_srt():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Выберите SRT файл",
        filetypes=[("SRT files", "*.srt"), ("All files", "*.*")]
    )
    return file_path


@eel.expose
def prompter_scan_srt_folder(folder_path):
    import os
    if not folder_path or not os.path.isdir(folder_path):
        return []
    srt_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith('.srt'):
                srt_files.append(os.path.join(root, file).replace('\\', '/'))
    return srt_files


@eel.expose
def prompter_browse_output_folder():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_path = filedialog.askdirectory(title="Выберите папку для сохранения промптов")
    return folder_path


@eel.expose
def prompter_browse_save_folder():
    import tkinter as tk
    from tkinter import filedialog
    import os
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_path = filedialog.askdirectory(title="Выберите папку для сохранения")
    root.destroy()

    if not folder_path:
        return {"success": False, "path": "", "srt_file": ""}

    # Сканируем ТОЛЬКО верхний уровень (не рекурсивно)
    srt_file = ""
    try:
        for fname in sorted(os.listdir(folder_path)):
            if fname.lower().endswith('.srt'):
                srt_file = os.path.join(folder_path, fname).replace('\\', '/')
                break
    except Exception as e:
        pass

    return {
        "success": True,
        "path": folder_path.replace('\\', '/'),
        "srt_file": srt_file
    }


@eel.expose
def prompter_parse_srt_layout(srt_path):
    """Считывает SRT и возвращает длительность + базовую инфу.
    Возвращает структуру: {success, total_subs, duration_sec}"""
    from stocky_nonstop.overlay.srt_splitter import parse_srt_file
    if not srt_path or not os.path.exists(srt_path):
        return {"success": False}

    subs = parse_srt_file(srt_path)
    if not subs:
        return {"success": False}

    # Получаем длительность как время окончания последнего субтитра
    last_sub = subs[-1]
    duration = getattr(last_sub, 'end_sec', 0) if not isinstance(last_sub, dict) else last_sub.get('end_sec', 0)

    return {
        "success": True,
        "total_subs": len(subs),
        "duration_sec": float(duration)
    }


def _load_prompter_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _normalize_scene_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned)
    return cleaned


def _serialize_scene(sub, fallback_index: int):
    start_sec = float(getattr(sub, "start_sec", 0.0))
    end_sec = float(getattr(sub, "end_sec", start_sec))
    duration = max(0.0, end_sec - start_sec)
    raw_text = getattr(sub, "text", "") or ""
    return {
        "scene_number": fallback_index + 1,
        "subtitle_index": int(getattr(sub, "index", fallback_index + 1) or (fallback_index + 1)),
        "start_sec": start_sec,
        "end_sec": end_sec,
        "duration_sec": duration,
        "text": _normalize_scene_text(raw_text),
    }


@eel.expose
def prompter_parse_srt_scenes(srt_path):
    from stocky_nonstop.overlay.srt_splitter import parse_srt_file

    if not srt_path or not os.path.exists(srt_path):
        return {"success": False, "error": "SRT файл не найден", "scenes": []}

    subs = parse_srt_file(srt_path)
    if not subs:
        return {"success": False, "error": "SRT файл пуст", "scenes": []}

    scenes = [_serialize_scene(sub, idx) for idx, sub in enumerate(subs)]
    return {
        "success": True,
        "total_scenes": len(scenes),
        "duration_sec": float(scenes[-1]["end_sec"]) if scenes else 0.0,
        "scenes": scenes,
    }

def _normalize_clip_rules(clip_rules):
    raw_rules = clip_rules or [
        {"from": 0.0, "to": 60.0, "mode": "random", "durationMin": 2.0, "durationMax": 4.0},
        {"from": 60.0, "to": None, "mode": "random", "durationMin": 3.0, "durationMax": 6.0},
    ]
    normalized = []

    for rule in raw_rules:
        item = {
            "from": float(rule.get("from", 0)),
            "to": None if rule.get("to") in (None, "") else float(rule.get("to")),
            "mode": "fixed" if rule.get("mode") == "fixed" else "random",
        }
        if item["mode"] == "fixed":
            item["duration"] = float(rule.get("duration", 3.0))
        else:
            item["durationMin"] = float(rule.get("durationMin", 2.0))
            item["durationMax"] = float(rule.get("durationMax", 4.0))
        normalized.append(item)

    normalized.sort(key=lambda current: current["from"])
    return normalized


def _find_clip_rule_for_position(rules, position):
    for rule in rules:
        if position >= rule["from"] and (rule["to"] is None or position < rule["to"]):
            return rule
    return None


def _estimated_rule_duration(rule):
    if rule["mode"] == "fixed":
        return float(rule["duration"])
    return (float(rule["durationMin"]) + float(rule["durationMax"])) / 2.0


def build_prompt_clip_plan(duration_sec, clip_rules):
    if duration_sec <= 0:
        return []

    rules = _normalize_clip_rules(clip_rules)
    plan = []
    position = 0.0

    while position < duration_sec:
        rule = _find_clip_rule_for_position(rules, position)
        if rule is None:
            break

        clip_duration = min(_estimated_rule_duration(rule), duration_sec - position)
        if clip_duration < 0.1:
            break

        plan.append({
            "start_sec": round(position, 3),
            "duration_sec": round(clip_duration, 3),
        })
        position += clip_duration

    return plan


def calculate_total_prompts(duration_sec, clip_rules=None):
    return len(build_prompt_clip_plan(duration_sec, clip_rules))


def split_srt_into_windows(subs, clip_rules=None):
    """Режет SRT на окна по времени для отправки в AI-провайдер и считает промпты по clip rules."""
    if not subs:
        return []

    last_sub = subs[-1]
    total_duration = getattr(last_sub, 'end_sec', 0) if not isinstance(last_sub, dict) else last_sub.get('end_sec', 0)
    clip_plan = build_prompt_clip_plan(total_duration, clip_rules)
    windows = []

    first_end = min(60.0, total_duration)
    if first_end > 0:
        prompts_needed = sum(1 for clip in clip_plan if 0.0 <= clip["start_sec"] < first_end)
        if prompts_needed > 0:
            windows.append({
                "window_id": 1,
                "start_sec": 0.0,
                "end_sec": first_end,
                "prompts_needed": prompts_needed,
                "subs": _filter_subs_in_range(subs, 0.0, first_end)
            })

    if total_duration > 60:
        cursor = 60.0
        window_id = 2
        while cursor < total_duration:
            win_end = min(cursor + 120.0, total_duration)
            prompts_needed = sum(1 for clip in clip_plan if cursor <= clip["start_sec"] < win_end)
            if prompts_needed > 0:
                windows.append({
                    "window_id": window_id,
                    "start_sec": cursor,
                    "end_sec": win_end,
                    "prompts_needed": prompts_needed,
                    "subs": _filter_subs_in_range(subs, cursor, win_end)
                })
            cursor = win_end
            window_id += 1

    return windows


def _filter_subs_in_range(subs, start_sec, end_sec):
    result = []
    for sub in subs:
        sub_start = getattr(sub, 'start_sec', 0) if not isinstance(sub, dict) else sub.get('start_sec', 0)
        if start_sec <= sub_start < end_sec:
            result.append(sub)
    return result


def _strip_stock_keyword_prefix(line: str) -> str:
    line = re.sub(r"^\s*(?:[-*•]|\d+[\).\:-])\s*", "", line).strip()
    line = re.sub(
        r"^\s*(?:prompt|keywords?|search\s*(?:query|terms?|phrase)|result|answer|output)\s*[:\-]\s*",
        "",
        line,
        flags=re.IGNORECASE,
    ).strip()
    line = re.sub(
        r"^\s*(?:here(?:'s| is| are)?|sure|certainly)[,\s:;-]+",
        "",
        line,
        flags=re.IGNORECASE,
    ).strip()
    return line


def _clean_stock_keyword_phrase(text: str):
    """Возвращает (cleaned, error). Чистит ответ AI до одной строки stock keywords."""
    if not text:
        return "", "empty response"

    value = str(text)
    value = re.sub(r"```[a-zA-Z0-9_-]*", "", value).replace("```", " ")
    value = value.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    candidates = []
    for raw_line in value.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        if not line:
            continue

        line = _strip_stock_keyword_prefix(line)
        if ":" in line:
            tail = _strip_stock_keyword_prefix(line.split(":", 1)[1])
            if tail:
                line = tail

        for part in re.split(r"\s*[;|]\s*", line):
            part = _strip_stock_keyword_prefix(part.strip())
            if part:
                candidates.append(part)

    if not candidates:
        candidates = [_strip_stock_keyword_prefix(value.strip())]

    meta_phrases = [
        "here is", "here are", "the best", "this scene", "i would",
        "as requested", "stock search", "search phrase", "keywords",
        "prompt", "description", "generate", "image", "video"
    ]
    sentence_words = {
        "a", "an", "the", "is", "are", "was", "were", "with", "through",
        "during", "while", "showing", "depicting", "featuring", "beautiful",
        "majestic", "cinematic"
    }

    last_error = "no valid candidate"
    for candidate in candidates:
        lower = candidate.lower()
        if any(phrase in lower for phrase in meta_phrases):
            last_error = "meta text in response"
            continue
        if re.search(r"[а-яёА-ЯЁ]", candidate):
            last_error = "non-English characters"
            continue

        words = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", candidate)
        if not words:
            last_error = "empty after cleanup"
            continue
        if len(words) > 8:
            last_error = f"too many words ({len(words)})"
            continue
        if len(words) > 5 and sum(1 for word in words if word.lower() in sentence_words) >= 2:
            last_error = "looks like a sentence"
            continue

        cleaned = " ".join(words).strip()
        if len(cleaned) > 80:
            last_error = "too long"
            continue
        return cleaned, ""

    return "", last_error


def _format_scene_context(scene):
    return (scene or {}).get("text", "").strip() if scene else ""


def _build_scene_system_prompt(file_prompt: str, master_prompt: str) -> str:
    parts = []
    if master_prompt and master_prompt.strip():
        parts.append(master_prompt.strip())
    if file_prompt and file_prompt.strip():
        parts.append(file_prompt.strip())

    if not parts:
        parts.append(
            "Return exactly one short English stock search keyword phrase for Pexels/Pixabay. "
            "No explanation, no quotes, no list, no punctuation."
        )
    return "\n\n".join(part for part in parts if part)


def _build_scene_user_message(project_context: str, previous_scene: dict, current_scene: dict, next_scene: dict) -> str:
    return (
        "PROJECT CONTEXT:\n"
        f"{project_context or '(empty)'}\n\n"
        "PREVIOUS SCENE:\n"
        f"{_format_scene_context(previous_scene) or '(none)'}\n\n"
        "CURRENT SCENE:\n"
        f"{_format_scene_context(current_scene)}\n\n"
        "NEXT SCENE:\n"
        f"{_format_scene_context(next_scene) or '(none)'}"
    )


def _build_scene_export_content(scenes):
    lines = []
    for scene in scenes:
        prompt = (scene.get("prompt") or "").strip()
        if prompt:
            lines.append(prompt)
    return "\n".join(lines)


@eel.expose
def generate_stock_prompts(tab_id, api_key, srt_path, docx_path, output_folder="", clip_rules=None, provider=None, model=None, scene_indices=None, existing_scenes=None, generation_threads=3, pause_every=100, pause_seconds=5, ai_pool=None):
    cancel_event = threading.Event()
    tab_key = str(tab_id)
    with PROMPTER_CANCEL_LOCK:
        previous_event = PROMPTER_CANCEL_EVENTS.get(tab_key)
        if previous_event:
            previous_event.set()
        PROMPTER_CANCEL_EVENTS[tab_key] = cancel_event

    def worker():
        try:
            prompter_safe_eel("add_log_entry", tab_id, f"🎬 Старт генерации", "info")
            prompter_safe_eel("add_log_entry", tab_id, f"   SRT: {srt_path}", "info")
            prompter_safe_eel("add_log_entry", tab_id, f"   Prompt file: {docx_path or '(не указан)'}", "info")
            if scene_indices:
                prompter_safe_eel("add_log_entry", tab_id, f"   Повторная генерация сцен: {len(scene_indices)}", "info")

            from stocky_nonstop.overlay.srt_splitter import parse_srt_file
            from concurrent.futures import CancelledError, ThreadPoolExecutor
            import threading

            try:
                MAX_WORKERS = max(1, min(50, int(generation_threads)))
            except (TypeError, ValueError):
                MAX_WORKERS = 3
            try:
                PAUSE_EVERY = max(1, min(1000, int(pause_every)))
            except (TypeError, ValueError):
                PAUSE_EVERY = 100
            try:
                PAUSE_SECONDS = max(0.0, min(120.0, float(pause_seconds)))
            except (TypeError, ValueError):
                PAUSE_SECONDS = 5.0

            prompter_safe_eel("prompter_update_status", tab_id, "Чтение SRT...", "text-yellow-400")

            if not srt_path or not os.path.exists(srt_path):
                prompter_safe_eel("prompter_done", tab_id, False, "", "SRT файл не найден", "")
                return

            subs = parse_srt_file(srt_path)
            if not subs:
                prompter_safe_eel("prompter_done", tab_id, False, "", "SRT файл пуст", "")
                return

            all_scenes = [_serialize_scene(sub, idx) for idx, sub in enumerate(subs)]
            if isinstance(existing_scenes, list):
                for idx, scene in enumerate(existing_scenes):
                    if idx >= len(all_scenes) or not isinstance(scene, dict):
                        continue
                    all_scenes[idx]["prompt"] = (scene.get("prompt") or "").strip()
                    all_scenes[idx]["status"] = scene.get("status") or "ОЖИДАНИЕ"
                    all_scenes[idx]["error"] = scene.get("error") or ""
            if scene_indices:
                target_indices = [idx for idx in scene_indices if isinstance(idx, int) and 0 <= idx < len(all_scenes)]
            else:
                target_indices = list(range(len(all_scenes)))

            total_scenes = len(all_scenes)
            if not target_indices:
                prompter_safe_eel("prompter_done", tab_id, False, "", "Не найдены сцены для генерации", "")
                return

            prompter_safe_eel("prompter_set_scenes", tab_id, all_scenes)
            prompter_safe_eel("add_log_entry", tab_id, f"📊 Сцен из SRT: {total_scenes}", "info")
            prompter_safe_eel("add_log_entry", tab_id, f"🧵 Потоки генерации: {MAX_WORKERS}", "info")
            prompter_safe_eel("add_log_entry", tab_id, f"⏱ Пауза: каждые {PAUSE_EVERY} сцен на {PAUSE_SECONDS:g} сек", "info")

            ai_settings = persist_ai_selection(api_key=api_key, provider=provider, model=model)

            active_pool = []
            if isinstance(ai_pool, list):
                for item in ai_pool:
                    if not isinstance(item, dict) or item.get("enabled") is False:
                        continue
                    pool_key = (item.get("apiKey") or item.get("api_key") or "").strip()
                    pool_provider = (item.get("provider") or "").strip()
                    pool_model = (item.get("model") or "").strip()
                    if pool_key and pool_provider and pool_model:
                        active_pool.append({
                            "provider": pool_provider,
                            "model": pool_model,
                            "api_key": pool_key,
                        })

            if active_pool:
                engine_pool = []
                for item in active_pool:
                    pool_engine = DeepSeekEngine(
                        api_key=item["api_key"],
                        model=item["model"],
                        provider=item["provider"]
                    )
                    engine_pool.append({
                        "engine": pool_engine,
                        "provider": pool_engine.provider,
                        "label": getattr(pool_engine, "provider", item["provider"]),
                        "model": pool_engine.model,
                    })
                engine = engine_pool[0]["engine"]
                prompter_safe_eel("add_log_entry", tab_id, f"🤖 AI pool: {len(engine_pool)} активных воркеров", "info")
                for idx, item in enumerate(engine_pool, start=1):
                    prompter_safe_eel("add_log_entry", tab_id, f"   {idx}. {item['provider']} | {item['model']}", "info")
            else:
                engine = DeepSeekEngine(
                    api_key=ai_settings["api_key"],
                    model=ai_settings["model"],
                    provider=ai_settings["provider"]
                )
                engine_pool = [{
                    "engine": engine,
                    "provider": ai_settings["provider"],
                    "label": ai_settings["provider_label"],
                    "model": ai_settings["model"],
                }]
                prompter_safe_eel(
                    "add_log_entry",
                    tab_id,
                    f"🤖 AI provider: {ai_settings['provider_label']} | model: {ai_settings['model']}",
                    "info"
                )

            file_prompt = ""
            if docx_path:
                try:
                    file_prompt = engine.load_system_prompt_from_file(docx_path) or ""
                except Exception as e:
                    print(f"Warning: docx load failed: {e}")

            settings = _load_prompter_settings()
            master_prompt = (settings.get("prompter_master_prompt") or "").strip()
            system_prompt = _build_scene_system_prompt(file_prompt, master_prompt)
            project_context = " ".join(scene["text"] for scene in all_scenes if scene.get("text")).strip()

            results = {}
            done_count = [0]
            done_lock = threading.Lock()

            assignment_map = {
                scene_idx: engine_pool[pos % len(engine_pool)]
                for pos, scene_idx in enumerate(target_indices)
            }

            def process_scene(scene_idx):
                if cancel_event.is_set():
                    return

                scene = all_scenes[scene_idx]
                prompter_safe_eel("prompter_update_scene", tab_id, scene_idx, "ГЕНЕРАЦИЯ...", None, "text-yellow-400 animate-pulse")

                if cancel_event.is_set():
                    prompter_safe_eel("prompter_update_scene", tab_id, scene_idx, "ОСТАНОВЛЕНО", None, "text-red-300")
                    return

                previous_scene = all_scenes[scene_idx - 1] if scene_idx > 0 else None
                next_scene = all_scenes[scene_idx + 1] if scene_idx + 1 < len(all_scenes) else None
                user_message = _build_scene_user_message(project_context, previous_scene, scene, next_scene)
                assigned = assignment_map.get(scene_idx) or engine_pool[0]
                assigned_engine = assigned["engine"]

                def request_keywords(message, max_tokens=120):
                    return assigned_engine.send_message(
                        system_prompt=system_prompt,
                        user_message=message,
                        temperature=0.2,
                        max_tokens=max_tokens
                    )

                res = request_keywords(user_message)

                if cancel_event.is_set():
                    prompter_safe_eel("prompter_update_scene", tab_id, scene_idx, "ОСТАНОВЛЕНО", None, "text-red-300")
                    return

                if res.get("success"):
                    raw_content = res.get("content", "").strip()
                    content, clean_error = _clean_stock_keyword_phrase(raw_content)

                    if not content and not cancel_event.is_set():
                        prompter_safe_eel(
                            "add_log_entry",
                            tab_id,
                            f"⚠️ Сцена {scene_idx + 1}: плохой формат ({clean_error}), повторяю запрос",
                            "warning"
                        )
                        retry_message = (
                            f"{user_message}\n\n"
                            "FORMAT CORRECTION:\n"
                            "Your previous answer was not valid for stock search. "
                            "Return exactly one short English search keyword phrase only. "
                            "Use 1-8 words. No explanation, no sentence, no quotes, no markdown, no punctuation."
                        )
                        retry_res = request_keywords(retry_message, max_tokens=60)
                        if retry_res.get("success"):
                            raw_content = retry_res.get("content", "").strip()
                            content, clean_error = _clean_stock_keyword_phrase(raw_content)
                        else:
                            clean_error = retry_res.get("error", "retry failed")

                    if content:
                        results[scene_idx] = {"prompt": content, "status": "ГОТОВО", "error": ""}
                        prompter_safe_eel("prompter_update_scene", tab_id, scene_idx, "ГОТОВО", content, "text-[#A855F7]")
                    else:
                        err = f"Bad keyword format: {clean_error}"
                        results[scene_idx] = {"prompt": "", "status": "ОШИБКА", "error": err}
                        prompter_safe_eel("add_log_entry", tab_id, f"❌ Сцена {scene_idx + 1}: {err}", "error")
                        prompter_safe_eel("prompter_update_scene", tab_id, scene_idx, "ОШИБКА", err, "text-red-400")
                else:
                    err = res.get("error", "Unknown")
                    results[scene_idx] = {"prompt": "", "status": "ОШИБКА", "error": err}
                    prompter_safe_eel("prompter_update_scene", tab_id, scene_idx, "ОШИБКА", err, "text-red-400")

                with done_lock:
                    done_count[0] += 1
                    prompter_safe_eel("prompter_update_status", tab_id, f"Обработано: {done_count[0]}/{len(target_indices)}", "text-yellow-400")

            prompter_safe_eel("prompter_update_status", tab_id, f"Параллельная генерация сцен ({MAX_WORKERS} потоков)...", "text-yellow-400")

            for batch_start in range(0, len(target_indices), PAUSE_EVERY):
                if cancel_event.is_set():
                    break

                batch = target_indices[batch_start:batch_start + PAUSE_EVERY]
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                    futures = [ex.submit(process_scene, idx) for idx in batch]
                    for f in futures:
                        try:
                            f.result()
                        except CancelledError:
                            pass
                        if cancel_event.is_set():
                            ex.shutdown(wait=True, cancel_futures=True)
                            break

                processed_so_far = min(batch_start + len(batch), len(target_indices))
                if (
                    not cancel_event.is_set()
                    and PAUSE_SECONDS > 0
                    and processed_so_far < len(target_indices)
                ):
                    prompter_safe_eel(
                        "prompter_update_status",
                        tab_id,
                        f"Пауза {PAUSE_SECONDS:g} сек после {processed_so_far}/{len(target_indices)} сцен...",
                        "text-yellow-300"
                    )
                    prompter_safe_eel(
                        "add_log_entry",
                        tab_id,
                        f"⏱ Пауза {PAUSE_SECONDS:g} сек после {processed_so_far}/{len(target_indices)} сцен",
                        "info"
                    )
                    cancel_event.wait(PAUSE_SECONDS)

            for scene_idx, payload in results.items():
                all_scenes[scene_idx]["prompt"] = payload.get("prompt", "")
                all_scenes[scene_idx]["status"] = payload.get("status", "ОЖИДАНИЕ")
                all_scenes[scene_idx]["error"] = payload.get("error", "")

            full_content = _build_scene_export_content(all_scenes)
            failed_count = sum(1 for scene in all_scenes if scene.get("status") == "ОШИБКА")

            if cancel_event.is_set():
                prompter_safe_eel("add_log_entry", tab_id, "⏹ Генерация остановлена пользователем", "warning")
                prompter_safe_eel("prompter_done", tab_id, True, full_content, "", "", failed_count, True)
                return

            result_file_path = ""
            try:
                base_name = os.path.splitext(os.path.basename(srt_path))[0]

                if output_folder:
                    output_folder_norm = os.path.normpath(output_folder)
                    prompter_safe_eel("add_log_entry", tab_id, f"📁 Папка сохранения (передана): {output_folder}", "info")
                else:
                    output_folder_norm = ""
                    prompter_safe_eel("add_log_entry", tab_id, f"⚠️ output_folder пустой, сохраняем рядом с SRT", "warning")

                if output_folder_norm:
                    if not os.path.exists(output_folder_norm):
                        try:
                            os.makedirs(output_folder_norm, exist_ok=True)
                        except Exception as mkdir_err:
                            prompter_safe_eel("add_log_entry", tab_id, f"❌ Не удалось создать папку: {mkdir_err}", "error")
                            output_folder_norm = ""

                    if output_folder_norm and not os.path.isdir(output_folder_norm):
                        prompter_safe_eel("add_log_entry", tab_id, f"❌ Указанный путь не является папкой: {output_folder_norm}", "error")
                        output_folder_norm = ""

                if output_folder_norm:
                    result_file_path = os.path.join(output_folder_norm, f"{base_name}_poisk.txt")
                else:
                    srt_dir = os.path.dirname(srt_path)
                    result_file_path = os.path.join(srt_dir, f"{base_name}_poisk.txt")
                    prompter_safe_eel("add_log_entry", tab_id, f"⚠️ Fallback: сохраняем рядом с SRT в {srt_dir}", "warning")

                result_file_path = os.path.normpath(result_file_path)

                with open(result_file_path, 'w', encoding='utf-8') as f:
                    f.write(full_content)

                if os.path.exists(result_file_path):
                    file_size = os.path.getsize(result_file_path)
                    prompter_safe_eel("add_log_entry", tab_id, f"✅ Промпты сохранены ({file_size} байт): {result_file_path}", "success")
                else:
                    prompter_safe_eel("add_log_entry", tab_id, f"❌ Файл не появился на диске после записи!", "error")
                    result_file_path = ""

            except Exception as e:
                import traceback
                traceback.print_exc()
                prompter_safe_eel("add_log_entry", tab_id, f"❌ Ошибка сохранения: {e}", "error")
                result_file_path = ""

            prompter_safe_eel("prompter_done", tab_id, True, full_content, "", result_file_path, failed_count)

        except Exception as e:
            import traceback
            traceback.print_exc()
            prompter_safe_eel("prompter_done", tab_id, False, "", str(e), "", 0)
        finally:
            with PROMPTER_CANCEL_LOCK:
                if PROMPTER_CANCEL_EVENTS.get(tab_key) is cancel_event:
                    PROMPTER_CANCEL_EVENTS.pop(tab_key, None)

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True}
