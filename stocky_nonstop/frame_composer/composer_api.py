# Stocky non Stop — Frame Composer (многослойное наложение изображений)
# Автор: Азат | @inomix

import eel
import os
from .image_placer import ImagePlacer, get_video_info
from .gpu_detector import detect_gpu
from .plan_parser import parse_plan

composer_projects = {}
composer_active_render = None

@eel.expose
def composer_get_gpu_info():
    return detect_gpu()

@eel.expose
def composer_pick_video():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(
        title="Выберите видео",
        filetypes=[("Видео", "*.mp4 *.mov *.mkv *.avi")]
    )
    root.destroy()
    if path:
        info = get_video_info(path)
        return {"success": True, "path": path, "info": info}
    return {"success": False}

@eel.expose
def composer_pick_txt_file():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(
        title="Выберите файл с таймингами (txt/csv)",
        filetypes=[("Text/CSV files", "*.txt *.csv"), ("All files", "*.*")]
    )
    root.destroy()
    if path and os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False}

@eel.expose
def composer_pick_folder():
    import tkinter as tk
    from tkinter import filedialog
    import re
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askdirectory(title="Папка с картинками")
    root.destroy()
    if path:
        # Считаем любые картинки, в названии которых есть цифры
        files = [f for f in os.listdir(path) if re.search(r'\d+', f) and f.lower().endswith(('.png','.jpg','.jpeg','.webp'))]
        return {"success": True, "path": path, "count": len(files)}
    return {"success": False}

@eel.expose
def composer_validate_plan(plan_text, images_folder=None, exclude_str=""):
    import re
    try:
        items = parse_plan(plan_text)
        
        # Если папка передана, строго проверяем физическое наличие всех файлов
        if images_folder and os.path.exists(images_folder):
            exclude = set(int(x.strip()) for x in exclude_str.split(",") if x.strip().isdigit())
            
            # Собираем номера всех картинок, которые реально лежат в папке
            available_numbers = set()
            for f in os.listdir(images_folder):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    match = re.search(r'\d+', f)
                    if match:
                        available_numbers.add(int(match.group()))
            
            # Сверяем с планом и ищем недостающие
            missing = []
            for item in items:
                if item["n"] in exclude:
                    continue
                if item["n"] not in available_numbers:
                    missing.append(str(item["n"]))
            
            # Если чего-то не хватает — блокируем запуск и выводим номера
            if missing:
                return {
                    "success": False, 
                    "error": f"В папке отсутствуют картинки под номерами: {', '.join(missing)}!\nДогенерируйте их, либо добавьте эти номера в поле 'Исключить картинки'."
                }

        return {"success": True, "count": len(items), "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def composer_render(project_data):
    global composer_active_render
    try:
        def cb_prog(p, eta, fps):
            try:
                eel.composerProgressUpdate(p, eta, fps)()
            except: pass
            
        def cb_log(msg):
            try:
                eel.composerLog(msg)()
            except: pass
            
        placer = ImagePlacer(progress_callback=cb_prog, log_callback=cb_log)
        composer_active_render = placer
        result = placer.render_multilayer(project_data)
        composer_active_render = None
        return result
    except Exception as e:
        composer_active_render = None
        return {"success": False, "error": str(e)}

@eel.expose
def composer_cancel():
    global composer_active_render
    if composer_active_render:
        composer_active_render.cancel()
        return {"success": True}
    return {"success": False, "error": "Нет активного рендера"}
