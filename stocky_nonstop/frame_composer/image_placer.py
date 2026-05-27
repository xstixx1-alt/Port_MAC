import os
import shutil
import tempfile
import re
import subprocess
import time
from .gpu_detector import detect_gpu
from .plan_parser import parse_plan
from platform_utils import get_creationflags, popen_detached, run_detached

def get_video_dimensions(path):
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            path
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=10, creationflags=get_creationflags()
        )
        if result.returncode == 0:
            w, h = map(int, result.stdout.strip().split('x'))
            return w, h
    except: pass
    return 1920, 1080 # Fallback

def get_video_info(path):
    w, h = get_video_dimensions(path)
    duration = 0
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ]
        res = run_detached(cmd, capture_output=True, text=True)
        duration = float(res.stdout.strip())
    except: pass
    return {"width": w, "height": h, "duration": round(duration, 1)}

class ImagePlacer:
    def __init__(self, progress_callback=None, log_callback=None):
        self.process = None
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self._temp_dir = tempfile.mkdtemp(prefix="frame_composer_")
        self._temp_files = []

    def _log(self, msg):
        print(f"[ImagePlacer] {msg}")
        if self.log_callback:
            self.log_callback(msg)

    def _copy_if_cyrillic(self, path):
        """Создает временную копию файла, если в пути есть кириллица (FFmpeg её ненавидит)"""
        if all(ord(c) < 128 for c in path):
            return path
        
        ext = os.path.splitext(path)[1]
        temp_filename = f"safe_file_{len(self._temp_files)}{ext}"
        temp_path = os.path.join(self._temp_dir, temp_filename)
        shutil.copy2(path, temp_path)
        self._temp_files.append(temp_path)
        return temp_path

    def _find_image(self, folder, n):
        for f in os.listdir(folder):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                match = re.search(r'\d+', f)
                if match and int(match.group()) == n:
                    return os.path.join(folder, f)
        raise FileNotFoundError(f"Картинка с номером {n} не найдена в {folder}")

    def _map_speed(self, speed):
        return {
            "ultrafast": "ultrafast",
            "fast": "faster",
            "quality": "medium"
        }.get(speed, "fast")

    def _position_to_expr(self, pos, pad=30):
        return {
            "center":       ("(W-w)/2",     "(H-h)/2"),
            "left_top":     (f"{pad}",      f"{pad}"),
            "right_top":    (f"W-w-{pad}",  f"{pad}"),
            "left_bottom":  (f"{pad}",      f"H-h-{pad}"),
            "right_bottom": (f"W-w-{pad}",  f"H-h-{pad}"),
        }[pos]

    def _run_ffmpeg_with_progress(self, cmd, output_path):
        self._log(f"Запуск FFmpeg: {' '.join(cmd)}")
        duration = get_video_info(cmd[cmd.index("-i")+1])["duration"] if "-i" in cmd else 1

        self.process = popen_detached(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
            universal_newlines=True
        )

        start_time = time.time()
        
        while True:
            line = self.process.stderr.readline()
            if not line and self.process.poll() is not None:
                break
                
            if line:
                if "time=" in line and self.progress_callback:
                    m = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                    if m and duration > 0:
                        h, mn, s = map(float, m.groups())
                        curr = h * 3600 + mn * 60 + s
                        percent = min(100.0, (curr / duration) * 100)
                        
                        fps_m = re.search(r'fps=\s*(\d+)', line)
                        fps = float(fps_m.group(1)) if fps_m else 0
                        
                        elapsed = time.time() - start_time
                        eta = "--:--"
                        if curr > 0:
                            rem = (duration - curr) * (elapsed / curr)
                            eta = f"{int(rem//60):02d}:{int(rem%60):02d}"
                            
                        self.progress_callback(percent, eta, fps)
                
                if "frame=" in line and time.time() - getattr(self, '_last_log_time', 0) > 0.5:
                    self._log(line.strip()[:80])
                    self._last_log_time = time.time()
                elif any(x in line.lower() for x in ["error", "invalid"]):
                    self._log(line.strip())

        self.process.wait()
        returncode = self.process.returncode
        self.process = None

        if returncode == 0:
            mb = os.path.getsize(output_path) / (1024*1024)
            self._log(f"Готово. Сохранено: {output_path} ({mb:.2f} MB)")
            return {
                "success": True, 
                "output_file": output_path,
                "file_size_mb": mb,
                "render_time_sec": time.time() - start_time
            }
        else:
            self._log("Ошибка рендера")
            return {"success": False, "error": "FFmpeg error exit code"}

    def render_multilayer(self, project_data):
        try:
            video = project_data["video"]
            images_folder = project_data["images_folder"]
            output = project_data["output"]
            layers = project_data["layers"]
            
            # 🔥 ПОЛУЧАЕМ СДВИГ ВРЕМЕНИ ДЛЯ КАРТИНОК
            global_shift = float(project_data.get("global_shift", 0.0))
            
            self._log("Анализ слоёв плана...")
            all_items = []
            for li, layer in enumerate(layers):
                if not layer["plan"].strip(): continue
                items = parse_plan(layer["plan"])
                exclude = set(int(x.strip()) for x in layer["exclude"].split(",") if x.strip().isdigit())
                for item in items:
                    if item["n"] in exclude: continue
                    img_path = self._find_image(images_folder, item["n"])
                    
                    # 🔥 ПРИМЕНЯЕМ СДВИГ К ТАЙМИНГАМ
                    shifted_start = max(0.0, item["start"] + global_shift)
                    shifted_end = max(0.0, item["end"] + global_shift)
                    
                    all_items.append({
                        "n": item["n"],
                        "start": shifted_start,
                        "end": shifted_end,
                        "size_percent": layer.get("size", 30),
                        "position": layer.get("position", "center"),
                        "image_path": img_path
                    })
                    
            if not all_items:
                raise ValueError("Не найдено элементов в планах для наложения.")

            encoder_conf = detect_gpu()
            
            unique_images = {}
            input_idx = 1
            inputs = []
            
            if encoder_conf.get("hwaccel"):
                inputs.extend(['-hwaccel', encoder_conf["hwaccel"]])
            
            video_safe = self._copy_if_cyrillic(video)
            inputs.extend(['-i', video_safe])
            
            self._log("Загрузка картинок (без дубликатов и без loop)...")
            for it in all_items:
                path = it["image_path"]
                if path not in unique_images:
                    safe_img = self._copy_if_cyrillic(path)
                    unique_images[path] = input_idx
                    inputs.extend(['-i', safe_img])
                    input_idx += 1
            
            video_w, video_h = get_video_dimensions(video_safe)
            filters = []
            base = "0:v"
            
            self._log(f"Построение графа для {len(all_items)} наложений...")
            for idx, it in enumerate(all_items, start=1):
                img_input_idx = unique_images[it["image_path"]]
                target_w = int(video_w * it["size_percent"] / 100)
                target_w -= target_w % 2
                x_expr, y_expr = self._position_to_expr(it["position"], pad=int(video_w*0.02))
                
                filters.append(f"[{img_input_idx}:v]scale={target_w}:-2[img{idx}]")
                filters.append(f"[{base}][img{idx}]overlay=x={x_expr}:y={y_expr}:enable='between(t,{it['start']},{it['end']})'[v{idx}]")
                base = f"v{idx}"
            
            filter_str = ";".join(filters)
            filter_file = os.path.join(self._temp_dir, "filter_script.txt")
            with open(filter_file, "w", encoding="utf-8") as ff:
                ff.write(filter_str)
                
            encoder = encoder_conf.get("encoder", "libx264")
            
            cmd = ['ffmpeg', '-y'] + inputs + [
                '-filter_complex_script', filter_file,
                '-map', f'[{base}]',
                '-map', '0:a?',
                '-c:v', encoder
            ]
            
            if encoder == "h264_nvenc":
                cmd.extend(['-preset', 'p4', '-rc', 'vbr', '-cq', '20', '-b:v', '0'])
            elif encoder == "h264_amf":
                cmd.extend(['-quality', 'balanced', '-rc', 'cqp', '-qp_i', '20', '-qp_p', '20', '-qp_b', '20'])
            elif encoder == "h264_qsv":
                cmd.extend(['-preset', 'medium', '-global_quality', '20'])
            elif encoder == "h264_videotoolbox":
                cmd.extend(['-b:v', '8000k'])
            else:
                cmd.extend(['-preset', 'superfast', '-crf', '20'])
                
            cmd.extend(['-c:a', 'copy', '-movflags', '+faststart'])
            
            needs_temp_output = any(ord(c) >= 128 for c in output)
            temp_out = os.path.join(self._temp_dir, "final_output.mp4") if needs_temp_output else output
            cmd.append(temp_out)
            
            self._log(f"Запуск FFmpeg: 1 поток на видеокарте...")
            start_time = time.time()
            res = self._run_ffmpeg_with_progress(cmd, temp_out)
            
            if res.get("success") and needs_temp_output:
                self._log("Перенос файла в финальную директорию...")
                import shutil
                shutil.move(temp_out, output)
                res["output_file"] = output
                
            if res.get("success"):
                res["render_time_sec"] = time.time() - start_time
                
            return res
            
        finally:
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except: pass

    def cancel(self):
        if self.process:
            self._log("Отмена операции пользователем!")
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
