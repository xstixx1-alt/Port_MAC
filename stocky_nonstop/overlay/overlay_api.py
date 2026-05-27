# Stocky non Stop — Image Overlay (генерация промптов для картинок)
# Автор: Азат | @inomix

import eel
import os
import json
import tkinter as tk
from tkinter import filedialog
import threading
import sys
import glob
import gpu_engine

# Добавляем текущую директорию в sys.path, чтобы модули могли импортировать друг друга (deepseek_engine и т.д.)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Configuration for reading config.json
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def safe_eel_call(func_name, *args):
    """Safe Eel call to prevent dying socket exceptions"""
    try:
        import gevent
        def _execute():
            try:
                func = getattr(eel, func_name, None)
                if func:
                    func(*args)
            except Exception:
                pass
        gevent.spawn(_execute)
    except Exception:
        pass


try:
    from .srt_splitter import (parse_srt_file, split_to_windows, get_window_info, export_windows_to_text)
    from .deepseek_engine import DeepSeekEngine
    from .prompt_generator import PromptGenerator
    from .timing_generator import TimingGenerator
    from .image_overlay import ImageOverlay
    from stocky_nonstop.ai_router import persist_ai_selection, resolve_ai_settings
    OVERLAY_MODULES_READY = True
except ImportError as e:
    OVERLAY_MODULES_READY = False
    print(f"[OVERLAY] Modules not ready: {e}")

deepseek_engine = None
prompt_gen = None
timing_gen = None
overlay = None

# Изолированное состояние по вкладкам
_tab_state = {}  # { tab_id: { "windows": [...], "descriptions": [...], "generated_prompts": {} } }
_current_tab_id = "default"  # Активная вкладка

def _get_tab_state(tab_id=None):
    """Получить состояние конкретной вкладки (или активной)."""
    tid = tab_id or _current_tab_id
    if tid not in _tab_state:
        _tab_state[tid] = {
            "windows": [],
            "descriptions": [],
            "generated_prompts": {}
        }
    return _tab_state[tid]

@eel.expose
def overlay_check_available():
    return {
        "available": OVERLAY_MODULES_READY,
        "modules": {
            "srt_splitter": OVERLAY_MODULES_READY,
            "deepseek_engine": OVERLAY_MODULES_READY,
            "prompt_generator": OVERLAY_MODULES_READY,
            "timing_generator": OVERLAY_MODULES_READY,
            "image_overlay": OVERLAY_MODULES_READY
        }
    }

@eel.expose
def overlay_load_srt(filepath, tab_id=None):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    global _current_tab_id
    if tab_id:
        _current_tab_id = tab_id
    state = _get_tab_state(tab_id)
    try:
        entries = parse_srt_file(filepath)
        state["windows"] = split_to_windows(entries)
        info = get_window_info(state["windows"])
        # Добавляем total_entries для совместимости с JS
        info["total_entries"] = info.get("total_subs", len(entries))
        return {
            "success": True, 
            "info": info,
            "total_subs": len(entries),
            "windows_count": len(state["windows"]),
            "tab_id": tab_id or _current_tab_id
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_init_deepseek(api_key, model="deepseek-chat"):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    global deepseek_engine, prompt_gen, timing_gen, overlay
    try:
        settings = persist_ai_selection(api_key=api_key, model=model)
        deepseek_engine = DeepSeekEngine(api_key=settings["api_key"], model=settings["model"], provider=settings["provider"])
        ok = deepseek_engine.test_connection()
        if ok:
            prompt_gen = PromptGenerator(deepseek_engine)
            timing_gen = TimingGenerator(deepseek_engine, block_size=30, dead_zone=13)
            overlay = ImageOverlay(gpu_engine)
            
            # Сохранить API-ключ в config.json
            pass
                
        return {"success": ok}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_load_system_prompt(docx_path, task_type):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        if task_type == "prompts":
            prompt_gen.load_system_prompt(docx_path)
        elif task_type == "timings":
            timing_gen.load_system_prompt(docx_path)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_generate_prompts(output_dir, max_workers=5):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        def __worker():
            try:
                def progress(done, total, current_id, status):
                    try:
                        eel.overlay_prompt_progress(done, total, current_id, status)
                    except: pass
                
                results = prompt_gen.generate_for_windows(
                    overlay_windows, max_workers=max_workers, 
                    progress_callback=progress
                )
                saved = prompt_gen.save_prompts(results, output_dir)
                try: eel.overlay_generate_prompts_done(saved)
                except: pass
            except Exception as e:
                try: eel.overlay_generate_prompts_error(str(e))
                except: pass
                
        threading.Thread(target=__worker, daemon=True).start()
        return {"success": True, "started": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_load_descriptions(filepath):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    global overlay_descriptions
    try:
        overlay_descriptions = timing_gen.load_descriptions(filepath)
        return {"success": True, "count": len(overlay_descriptions)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_generate_timings(output_path, video_duration, max_workers=5):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        def __worker():
            try:
                def progress(done, total, window_id, found, status):
                    try:
                        eel.overlay_timing_progress(done, total, window_id, found, status)
                    except: pass
                
                placements = timing_gen.process_all_windows(
                    overlay_windows, overlay_descriptions,
                    max_workers=max_workers,
                    progress_callback=progress
                )
                validated = timing_gen.validate_and_fix(
                    placements, video_duration
                )
                timing_gen.export_table(validated, output_path)
                try: eel.overlay_generate_timings_done(len(validated))
                except: pass
            except Exception as e:
                try: eel.overlay_generate_timings_error(str(e))
                except: pass

        threading.Thread(target=__worker, daemon=True).start()
        return {"success": True, "started": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_render(video_path, images_folder, timings_file, output_path, settings):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        def __worker():
            try:
                def progress(pct, cur_time, total, fps, speed):
                    try:
                        eel.overlay_render_progress(pct, cur_time, total, fps, speed)
                    except: pass
                
                result = overlay.render(
                    video_path, images_folder, timings_file,
                    output_path, settings, 
                    progress_callback=progress
                )
                try: eel.overlay_render_done(result)
                except: pass
            except Exception as e:
                try: eel.overlay_render_error(str(e))
                except: pass
                
        threading.Thread(target=__worker, daemon=True).start()
        return {"success": True, "started": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_cancel_render():
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        if overlay:
            overlay.cancel()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_browse_file(file_types):
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        ftypes = [("All files", "*.*")]
        if isinstance(file_types, list):
            ftypes = file_types
        elif isinstance(file_types, str):
            if "srt" in file_types.lower():
                ftypes = [("Subtitles", "*.srt"), ("All files", "*.*")]
            elif "docx" in file_types.lower():
                ftypes = [("Prompt files", "*.docx *.txt *.md"), ("All files", "*.*")]
            elif "txt" in file_types.lower():
                ftypes = [("Text", "*.txt"), ("All files", "*.*")]
            elif "csv" in file_types.lower():
                ftypes = [("CSV", "*.csv"), ("All files", "*.*")]
            elif "mp4" in file_types.lower():
                ftypes = [("Video", "*.mp4 *.avi *.mkv"), ("All files", "*.*")]

        path = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=ftypes
        )
        root.destroy()
        return {"success": True, "path": path} if path else {"success": False, "error": "Отменено пользователем"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_browse_folder():
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(title="Выберите папку")
        root.destroy()
        return {"success": True, "path": path} if path else {"success": False, "error": "Отменено пользователем"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_validate_key(key, provider=None, model=None):
    global deepseek_engine, prompt_gen, timing_gen, overlay
    try:
        if not OVERLAY_MODULES_READY:
            return {"valid": False, "error": "Overlay modules not ready"}
        from .deepseek_engine import DeepSeekEngine
        from .prompt_generator import PromptGenerator
        from .timing_generator import TimingGenerator
        from .image_overlay import ImageOverlay
        from stocky_nonstop.ai_router import persist_ai_selection
        
        settings = persist_ai_selection(api_key=key, provider=provider, model=model)
        engine = DeepSeekEngine(api_key=settings["api_key"], model=settings["model"], provider=settings["provider"])
        valid = engine.test_connection()
        if valid:
            deepseek_engine = engine
            
            # Запоминаем загруженные инструкции (чтобы не стереть их при случайном обновлении)
            old_prompt_sys = prompt_gen.system_prompt if prompt_gen else ""
            old_timing_sys = timing_gen.system_prompt if timing_gen else ""
            
            prompt_gen = PromptGenerator(deepseek_engine)
            prompt_gen.system_prompt = old_prompt_sys  # Восстанавливаем инструкцию
            
            timing_gen = TimingGenerator(deepseek_engine, block_size=30, dead_zone=13)
            timing_gen.system_prompt = old_timing_sys  # Восстанавливаем инструкцию
            
            overlay = ImageOverlay(gpu_engine)
        return {
            "valid": valid,
            "provider": settings["provider"],
            "provider_label": settings["provider_label"],
            "model": settings["model"],
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}

@eel.expose
def overlay_get_windows(tab_id=None):
    """Возвращает окна в JSON-сериализуемом виде"""
    from .srt_splitter import format_seconds
    
    state = _get_tab_state(tab_id)
    windows_data = []
    for w in state["windows"]:
        windows_data.append({
            "window_id": w.window_id,
            "start_sec": w.start_sec,
            "end_sec": w.end_sec,
            "start_time": format_seconds(w.start_sec),
            "end_time": format_seconds(w.end_sec),
            "is_empty": w.is_empty,
            "text": w.full_text,
            "entries": [
                {
                    "index": e.index,
                    "start_sec": e.start_sec,
                    "end_sec": e.end_sec,
                    "text": e.text
                } for e in w.entries
            ]
        })
    
    return {"success": True, "windows": windows_data, "tab_id": tab_id or _current_tab_id}

@eel.expose
def overlay_generate_prompt(idx, tab_id=None):
    try:
        state = _get_tab_state(tab_id)
        windows = state["windows"]
        
        idx = int(idx)
        if idx < 0 or idx >= len(windows):
            return {"success": False, "error": f"Invalid index {idx} (windows count: {len(windows)})"}
        win = windows[idx]
        
        global prompt_gen
        if not prompt_gen:
            return {"success": False, "error": "Генератор промптов не инициализирован (проверьте API-ключ)"}
            
        result = prompt_gen.generate_for_window(win)
        
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "Неизвестная ошибка генерации")}
        
        prompt = result.get('prompt', '')
        state["generated_prompts"][idx] = prompt
        
        return {
            "success": True, 
            "window_index": idx, 
            "prompt": prompt, 
            "tokens_in": result.get('tokens_in', 0), 
            "tokens_out": result.get('tokens_out', 0),
            "tab_id": tab_id or _current_tab_id
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_generate_all_prompts(tab_id=None):
    try:
        global prompt_gen
        if not prompt_gen:
            return {"success": False, "error": "Генератор промптов не инициализирован"}
            
        state = _get_tab_state(tab_id)
        results = prompt_gen.generate_for_windows(state["windows"], max_workers=5)
        for r in results:
            if r and r.get("success"):
                state["generated_prompts"][r['window_id'] - 1] = r['prompt']
        return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_update_prompt(idx, text, tab_id=None):
    try:
        state = _get_tab_state(tab_id)
        state["generated_prompts"][int(idx)] = text
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_get_prompts(tab_id=None):
    state = _get_tab_state(tab_id)
    prompts = [state["generated_prompts"].get(i, "") for i in range(len(state["windows"]))]
    return {"success": True, "prompts": prompts}

@eel.expose
def overlay_export_prompts(path, tab_id=None):
    try:
        state = _get_tab_state(tab_id)
        with open(path, 'w', encoding='utf-8') as f:
            for i in range(len(state["windows"])):
                prompt = state["generated_prompts"].get(i, "")
                if prompt.strip():
                    clean_prompt = prompt.replace('\n', ' ').replace('\r', '').strip()
                    f.write(f"{clean_prompt}\n")
        return {"success": True, "filepath": path}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@eel.expose
def overlay_scan_srt_folder(folder_path):
    """Секьюрная функция, рекурсивно ищет .srt во всех подпапках"""
    if not OVERLAY_MODULES_READY:
        return {"success": False, "error": "Overlay modules not installed yet"}
    try:
        if not folder_path or not os.path.exists(folder_path):
            return {"success": False, "error": "Папка не существует"}
            
        srt_files = []
        # Рекурсивный поиск по всем подпапкам
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".srt"):
                    full_path = os.path.join(root, file)
                    # Заменяем слеши для JS
                    srt_files.append(full_path.replace('\\', '/'))
        
        return {"success": True, "files": srt_files}
    except Exception as e:
        return {"success": False, "error": str(e)}
