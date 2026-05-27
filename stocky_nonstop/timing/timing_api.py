# Stocky non Stop — Timing Placer (расстановка картинок по таймингам)
# Автор: Азат | @inomix

import eel
import os
import json
import tkinter as tk
from tkinter import filedialog
import threading
import sys

from stocky_nonstop.timing.timing_generator import TimingGenerator
from stocky_nonstop.ai_router import persist_ai_selection

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

_stop_flags = {}

def _safe_progress(tab_id, data):
    try:
        import gevent
        def _execute():
            try:
                func = getattr(eel, "timing_progress", None)
                if func:
                    func(tab_id, data)
            except Exception:
                pass
        gevent.spawn(_execute)
    except:
        pass

@eel.expose
def timing_browse_file(file_types):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        ftypes = [("All files", "*.*")]
        if isinstance(file_types, str):
            if "srt" in file_types.lower():
                ftypes = [("Subtitles", "*.srt"), ("All files", "*.*")]
            elif "docx" in file_types.lower():
                ftypes = [("Prompt files", "*.docx *.txt *.md"), ("All files", "*.*")]
            elif "txt" in file_types.lower() or "prompts" in file_types.lower():
                ftypes = [("Text", "*.txt"), ("All files", "*.*")]

        path = filedialog.askopenfilename(title="Выберите файл", filetypes=ftypes)
        root.destroy()
        return {"success": True, "path": path} if path else {"success": False, "error": "Отменено пользователем"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def timing_browse_folder():
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
def timing_scan_folder(folder_path):
    """Рекурсивно ищет пары prompts_export.txt + *.srt в подпапках.
    Возвращает список {folder, prompts, srt, name}.
    """
    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "error": "Папка не существует"}
    pairs = []
    for root_dir, dirs, files in os.walk(folder_path):
        prompts_file = None
        srt_file = None
        for f in files:
            if f.lower() == "prompts_export.txt":
                prompts_file = os.path.join(root_dir, f).replace('\\', '/')
            elif f.lower().endswith(".srt") and not srt_file:
                srt_file = os.path.join(root_dir, f).replace('\\', '/')
        if prompts_file and srt_file:
            pairs.append({
                "folder": root_dir.replace('\\', '/'),
                "prompts": prompts_file,
                "srt": srt_file,
                "name": os.path.basename(root_dir) or "project"
            })
    return {"success": True, "pairs": pairs}

def _single_worker(tab_id, prompts_path, srt_path, docx_path, api_key, threads=20, block_size=30, dead_zone=13, provider=None, model=None):
    try:
        def cb(data):
            if _stop_flags.get(tab_id, False):
                raise Exception("Cancelled by user")
            _safe_progress(tab_id, data)
            
        ai_settings = persist_ai_selection(api_key=api_key, provider=provider, model=model)
        generator = TimingGenerator(
            api_key=ai_settings["api_key"],
            progress_callback=cb,
            provider=ai_settings["provider"],
            model=ai_settings["model"],
        )
        generator.block_size = block_size
        generator.dead_zone = dead_zone

        _safe_progress(tab_id, {
            "message": f"AI provider: {ai_settings['provider_label']} | model: {ai_settings['model']}",
            "status": "info"
        })
            
        success = generator.start_process(prompts_path, srt_path, docx_path, max_workers=threads)
        
        if success:
            _safe_progress(tab_id, {"message": "✅ Генерация таймингов успешно завершена", "status": "success"})
        else:
            _safe_progress(tab_id, {"message": "❌ Ошибка при генерации", "status": "error"})
            
    except Exception as e:
        if str(e) == "Cancelled by user":
            _safe_progress(tab_id, {"message": "⚠️ Отменено пользователем", "status": "error"})
        else:
            _safe_progress(tab_id, {"message": f"Критическая ошибка: {e}", "status": "error"})
            import traceback
            traceback.print_exc()

@eel.expose
def timing_start_single(tab_id, prompts_path, srt_path, docx_path, api_key, threads=20, block_size=30, dead_zone=13, provider=None, model=None):
    _stop_flags[tab_id] = False
    threading.Thread(
        target=_single_worker,
        args=(tab_id, prompts_path, srt_path, docx_path, api_key, threads, block_size, dead_zone, provider, model),
        daemon=True
    ).start()
    return {"success": True}

@eel.expose
def timing_start_all(jobs):
    """jobs = [{tab_id, prompts, srt, docx, api_key, threads, block_size, dead_zone}]"""
    for job in jobs:
        tab_id = job["tab_id"]
        _stop_flags[tab_id] = False
        threading.Thread(
            target=_single_worker,
            args=(
                tab_id, 
                job["prompts"], 
                job["srt"], 
                job["docx"], 
                job["api_key"], 
                job.get("threads", 20),
                job.get("block_size", 30),
                job.get("dead_zone", 13),
                job.get("provider"),
                job.get("model")
            ),
            daemon=True
        ).start()
    return {"success": True, "started": len(jobs)}

@eel.expose
def timing_cancel(tab_id):
    _stop_flags[tab_id] = True
    return {"success": True}
