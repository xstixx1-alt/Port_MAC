import os
import csv
import time
import subprocess
import shutil
import re
from pathlib import Path
from platform_utils import get_creationflags, popen_detached

class ImageOverlay:
    def __init__(self, gpu_engine_module):
        self.gpu_engine = gpu_engine_module
        self.process = None
        self._cancel_requested = False

    def parse_timings_file(self, filepath) -> list:
        timings = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                header = next(reader, None)
                # Check if the first row is actually a header or data
                if header and not header[0].strip().isdigit():
                    pass # it was header
                elif header:
                    f.seek(0)
                    reader = csv.reader(f, delimiter=';')
                
                for row in reader:
                    if len(row) >= 3:
                        try:
                            n = int(row[0].strip())
                            start = float(row[1].replace(',', '.').strip())
                            end = float(row[2].replace(',', '.').strip())
                            timings.append({"n": n, "start": start, "end": end})
                        except ValueError:
                            continue
        except Exception as e:
            print(f"Error parsing timing file: {e}")
            
        return timings

    def get_video_duration(self, video_path) -> float:
        try:
            cmd = [
                'ffprobe', '-v', 'error', 
                '-show_entries', 'format=duration', 
                '-of', 'default=noprint_wrappers=1:nokey=1', 
                str(video_path)
            ]
            output = subprocess.check_output(cmd, text=True, creationflags=get_creationflags()).strip()
            return float(output)
        except Exception:
            return 0.0

    def get_video_dimensions(self, video_path):
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'csv=s=x:p=0',
                str(video_path)
            ]
            output = subprocess.check_output(cmd, text=True, creationflags=get_creationflags()).strip()
            w, h = map(int, output.split('x'))
            return w, h
        except Exception:
            return 1920, 1080

    def validate_inputs(self, video, images_folder, timings) -> dict:
        result = {"valid": True, "errors": []}
        
        # 1. Video exists and readable
        if not os.path.exists(video):
            result["valid"] = False
            result["errors"].append(f"Video file not found: {video}")
            dur = 0.0
        else:
            dur = self.get_video_duration(video)
            if dur <= 0:
                result["valid"] = False
                result["errors"].append("Could not read video duration or video is invalid.")
                
        # 2. Check images
        for t in timings:
            img_path = os.path.join(images_folder, f"image_{t['n']}.png")
            if not os.path.exists(img_path):
                img_path_jpg = os.path.join(images_folder, f"image_{t['n']}.jpg")
                if not os.path.exists(img_path_jpg):
                    result["valid"] = False
                    result["errors"].append(f"Image not found: image_{t['n']}.png")
                    t["path"] = ""
                else:
                    t["path"] = img_path_jpg
            else:
                t["path"] = img_path
                
        # 3. Timecodes bounds
        if dur > 0:
            for t in timings:
                if t['end'] > dur:
                    t['end'] = dur
                if t['start'] > dur:
                    result["valid"] = False
                    result["errors"].append(f"Timecode for image_{t['n']} is out of bounds ({t['start']} > {dur})")
                    
        return result

    def build_filter_complex(self, timings, settings, video_h) -> tuple:
        filters = []
        base_layer = "0:v"
        
        size = settings.get("image_size", "small")
        pos = settings.get("position", "center")
        fade_in = settings.get("fade_in", 0.5)
        fade_out = settings.get("fade_out", 0.5)
        opacity = settings.get("opacity", 1.0)
        pad = settings.get("padding", 50)
        
        if size == "small":
            target_h = int(video_h * 0.3)
        else:
            target_h = int(video_h * 0.5)
            
        target_h = target_h - (target_h % 2)
        
        for i, t in enumerate(timings, start=1):
            start = t['start']
            end = t['end']
            
            filters.append(f"[{i}:v]format=rgba,colorchannelmixer=aa={opacity},fade=t=in:st={start}:d={fade_in}:alpha=1,fade=t=out:st={end-fade_out}:d={fade_out}:alpha=1[alpha{i}]")
            filters.append(f"[alpha{i}]scale=-1:{target_h}[img{i}]")
            
            if pos == "center":
                y_expr = "(H-h)/2"
            elif pos == "top":
                y_expr = f"{pad}"
            elif pos == "bottom":
                y_expr = f"H-h-{pad}"
            else:
                y_expr = "(H-h)/2"
            x_expr = "(W-w)/2"
            
            out_layer = f"v{i}"
            filters.append(f"[{base_layer}][img{i}]overlay=x={x_expr}:y={y_expr}:enable='between(t,{start},{end})'[{out_layer}]")
            base_layer = out_layer
            
        return ";\n".join(filters), base_layer

    def cancel(self):
        self._cancel_requested = True
        if self.process:
            try:
                self.process.communicate(b'q', timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def render(self, video_path, images_folder, timings_file, output_path, settings, progress_callback=None) -> dict:
        self._cancel_requested = False
        start_time = time.time()
        
        result = {
            "success": False,
            "output_file": output_path,
            "file_size_mb": 0.0,
            "duration_sec": 0.0,
            "render_time_sec": 0.0,
            "rendered_images": 0,
            "skipped_images": [], 
            "method": "single_pass",
            "gpu_used": "cpu",
            "errors": [],
            "ffmpeg_log_file": "ffmpeg_overlay.log"
        }
        
        timings = self.parse_timings_file(timings_file)
        if not timings:
            result["errors"].append("No timings found or invalid format.")
            return result
            
        validation = self.validate_inputs(video_path, images_folder, timings)
        if not validation["valid"]:
            result["errors"].extend(validation["errors"])
            return result
            
        gpu_info = self.gpu_engine.get_gpu_info() if hasattr(self.gpu_engine, 'get_gpu_info') else {"type": "cpu", "encoder": "libx264"}
        result["gpu_used"] = gpu_info.get("type", "cpu")
        encoder = gpu_info.get("encoder", "libx264")
        
        result["rendered_images"] = len(timings)
        
        if len(timings) > 80:
            result["method"] = "batched"
            return self._render_batched(video_path, timings, output_path, settings, progress_callback, encoder, result, start_time)
            
        return self._do_render(video_path, timings, output_path, settings, progress_callback, encoder, result, start_time)

    def _do_render(self, video_path, timings, output_path, settings, progress_callback, encoder, result, start_time):
        _, video_h = self.get_video_dimensions(video_path)
        duration = self.get_video_duration(video_path)
        
        gpu_info = self.gpu_engine.get_gpu_info() if hasattr(self.gpu_engine, 'get_gpu_info') else {}
        
        # 🔥 Аппаратное декодирование
        inputs = []
        if gpu_info.get("hwaccel"):
            inputs.extend(['-hwaccel', gpu_info["hwaccel"]])
            
        inputs.extend(['-i', str(video_path)])
        for t in timings:
            inputs.extend(['-loop', '1', '-t', str(t['end']), '-i', t['path']])
            
        filter_complex_str, final_layer = self.build_filter_complex(timings, settings, video_h)
        
        cmd = ['ffmpeg', '-y'] + inputs
        
        if len(timings) >= 50:
            script_path = "filter_script.txt"
            with open(script_path, "w", encoding='utf-8') as f:
                f.write(filter_complex_str)
            cmd.extend(['-filter_complex_script', script_path])
        else:
            cmd.extend(['-filter_complex', filter_complex_str])
            
        cmd.extend([
            '-map', f'[{final_layer}]',
            '-map', '0:a?',
            '-c:v', encoder
        ])
        
        # 🔥 Разгоняем кодек на максимум
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
            
        cmd.extend(['-c:a', 'copy', str(output_path)])
        
        return self._run_ffmpeg(cmd, duration, result, start_time, output_path, progress_callback)

    def _render_batched(self, video_path, timings, output_path, settings, progress_callback, encoder, result, start_time):
        batch_size = 40
        batches = [timings[i:i + batch_size] for i in range(0, len(timings), batch_size)]
        
        current_input = video_path
        temp_files = []
        
        for i, batch in enumerate(batches):
            is_last = (i == len(batches) - 1)
            current_output = str(output_path) if is_last else f"temp_batch_{i}.mp4"
            if not is_last:
                temp_files.append(current_output)
                
            def batch_progress(p, ct, tt, fps, spd):
                if progress_callback:
                    overall_p = (i * 100 + p) / len(batches)
                    progress_callback(overall_p, ct, tt, fps, spd)
                    
            res = self._do_render(current_input, batch, current_output, settings, batch_progress, encoder, result, start_time)
            
            if not res["success"]:
                for tmp in temp_files:
                    if os.path.exists(tmp): os.remove(tmp)
                return res
                
            current_input = current_output
            
        # Cleanup
        for tmp in temp_files:
            if os.path.exists(tmp): os.remove(tmp)
            
        return res

    def _run_ffmpeg(self, cmd, duration, result, start_time, output_path, progress_callback):
        self.process = popen_detached(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace'
        )
        
        log_f = open(result["ffmpeg_log_file"], "w", encoding="utf-8")
        
        # Regex to parse ffmpeg output
        time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})")
        fps_regex = re.compile(r"fps=\s*(\d+)")
        speed_regex = re.compile(r"speed=\s*([\d\.]+)x")
        
        try:
            for line in self.process.stdout:
                if self._cancel_requested:
                    break
                    
                log_f.write(line)
                log_f.flush()
                
                t_match = time_regex.search(line)
                if t_match and duration > 0:
                    h, m, s = t_match.groups()
                    current_t = int(h)*3600 + int(m)*60 + float(s)
                    percent = min(100.0, current_t / duration * 100.0)
                    
                    fps_m = fps_regex.search(line)
                    fps = float(fps_m.group(1)) if fps_m else 0.0
                    
                    spd_m = speed_regex.search(line)
                    speed = float(spd_m.group(1)) if spd_m else 0.0
                    
                    if progress_callback:
                        progress_callback(percent, current_t, duration, fps, speed)
                        
            self.process.wait()
        except Exception as e:
            result["errors"].append(str(e))
        finally:
            log_f.close()
            
        if self._cancel_requested:
            if os.path.exists(output_path):
                try: 
                    os.remove(output_path)
                except:
                    pass
            result["success"] = False
            result["errors"].append("Render was cancelled by user.")
            return result
            
        if self.process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            result["success"] = True
            result["file_size_mb"] = os.path.getsize(output_path) / (1024 * 1024)
            result["duration_sec"] = self.get_video_duration(output_path)
            result["render_time_sec"] = time.time() - start_time
        else:
            result["success"] = False
            result["errors"].append(f"FFmpeg exited with code {self.process.returncode}")
            
        return result


if __name__ == "__main__":
    print("starting test suite...")
    # Mock for gpu_engine
    class MockGpuEngine:
        def get_gpu_info(self):
            return {
                "name": "TEST GPU",
                "encoder": "libx264",
                "hwaccel": None,
                "type": "cpu"
            }
            
    # Setup testing workspace
    import tempfile
    test_dir = Path("test_workspace")
    test_dir.mkdir(exist_ok=True)
    
    test_video = test_dir / "test_video.mp4"
    test_csv = test_dir / "timings.csv"
    test_out = test_dir / "test_output.mp4"
    
    # 1. Generate test video (30 sec)
    if not test_video.exists():
        print("Generating test video...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=30:size=1280x720:rate=30",
            "-c:v", "libx264", str(test_video)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    # 2. Generate test images
    colors = ["red", "green", "blue", "yellow", "cyan"]
    for i, color in enumerate(colors, 1):
        img_path = test_dir / f"image_{i}.png"
        if not img_path.exists():
            print(f"Generating test image {i}...")
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=400x400",
                "-frames:v", "1", str(img_path)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
    # 3. Create test timings
    print("Generating timings table...")
    with open(test_csv, "w", encoding="utf-8") as f:
        f.write("N;START;END\n")
        # 5 images with 2s overlap
        f.write("1;1.0;6.0\n")
        f.write("2;5.0;11.0\n")
        f.write("3;10.0;16.0\n")
        f.write("4;15.0;21.0\n")
        f.write("5;20.0;28.0\n")
        
    settings = {
        "image_size": "small",
        "position": "center",
        "fade_in": 1.0,
        "fade_out": 1.0,
        "opacity": 0.9,
        "scale": 0.3,
        "padding": 50
    }
    
    def on_progress(p, ct, tt, fps, spd):
        print(f"Progress: {p:.1f}% | Time: {ct:.1f}/{tt:.1f}s | FPS: {fps} | Speed: {spd}x")
        
    print("Starting render...")
    overlay = ImageOverlay(MockGpuEngine())
    res = overlay.render(
        video_path=str(test_video),
        images_folder=str(test_dir),
        timings_file=str(test_csv),
        output_path=str(test_out),
        settings=settings,
        progress_callback=on_progress
    )
    
    print("\n--- Render Result ---")
    import json
    print(json.dumps(res, indent=2))
    
    # 4. Check if success
    if res["success"]:
        print(f"Test PASSED! Output exists: {test_out.exists()} with size {res['file_size_mb']:.2f} MB")
    else:
        print("Test FAILED!")
