import os
import json
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading

# Импорт необходимых классов
from deepseek_engine import DeepSeekEngine
from srt_splitter import SRTWindow, format_seconds

class PromptGenerator:
    def __init__(self, deepseek_engine: DeepSeekEngine):
        self.engine = deepseek_engine
        self.system_prompt = ""

    def load_system_prompt(self, prompt_path: str) -> None:
        """Загрузить системный промпт из .docx, .txt или .md"""
        self.system_prompt = self.engine.load_system_prompt_from_file(prompt_path)
        if not self.system_prompt:
            print(f"Warning: Failed to load system prompt from {prompt_path} or it was empty.")

    def generate_for_window(self, window: SRTWindow) -> dict:
        """Один запрос для одного окна."""
        if not self.system_prompt:
            return {
                "window_id": window.window_id,
                "prompt": "",
                "success": False,
                "error": "System prompt not loaded."
            }
            
        user_message = f"""Окно №{window.window_id}
Временной диапазон: {format_seconds(window.start_sec)} - {format_seconds(window.end_sec)}

Текст субтитров:
{window.full_text}

Сгенерируй промт для картинки согласно инструкции."""

        result = self.engine.send_message(
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=0.7,
            max_tokens=800
        )

        res_dict = {
            "window_id": window.window_id,
            "prompt": "",
            "success": False,
            "error": None,
            "tokens_in": 0,
            "tokens_out": 0
        }

        if result.get("success"):
            prompt = result.get("content", "").strip()
            
            # Валидация
            if not prompt:
                res_dict["error"] = "Empty prompt generated."
            elif len(prompt) < 10:
                res_dict["error"] = "Prompt too short."
                res_dict["prompt"] = prompt
            else:
                res_dict["success"] = True
                res_dict["prompt"] = prompt
            
            res_dict["tokens_in"] = result.get("tokens_in", 0)
            res_dict["tokens_out"] = result.get("tokens_out", 0)
        else:
            res_dict["error"] = result.get("error", "Unknown API error")
            
        return res_dict

    def generate_for_windows(self, windows: list, max_workers=5, progress_callback=None) -> list:
        """
        Параллельная генерация для всех окон.
        Пропускает пустые, возвращает список результатов.
        """
        results = [None] * len(windows)
        to_process = []
        
        # Заполнение пропущенных / пустых
        for i, w in enumerate(windows):
            if w.is_empty:
                results[i] = {
                    "window_id": w.window_id,
                    "prompt": "",
                    "success": False,
                    "error": "empty_window",
                    "status": "skipped"
                }
            else:
                to_process.append((i, w))
                
        total = len(windows)
        done = 0
        done_lock = threading.Lock()
        
        # Сначала триггерим callback для тех, что уже skipped
        for i, w in enumerate(windows):
            if w.is_empty:
                done += 1
                if progress_callback:
                    try:
                        progress_callback(done, total, w.window_id, "done")
                    except Exception:
                        pass
                    
        def worker(index, window):
            nonlocal done
            if progress_callback:
                try:
                    progress_callback(done, total, window.window_id, "processing")
                except Exception:
                    pass
                
            res = self.generate_for_window(window)
            res["status"] = "ok" if res["success"] else "error"
            
            with done_lock:
                results[index] = res
                done += 1
                if progress_callback:
                    status_str = "done" if res["success"] else "error"
                    try:
                        progress_callback(done, total, window.window_id, status_str)
                    except Exception:
                        pass

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for idx, w in to_process:
                futures.append(executor.submit(worker, idx, w))
            concurrent.futures.wait(futures)
            
        return results

    def save_prompts(self, results: list, output_dir: str) -> dict:
        """Сохраняет каждый промт в pic_N.txt"""
        os.makedirs(output_dir, exist_ok=True)
        stats = {"saved": 0, "skipped": 0, "files": []}
        
        for res in results:
            if not res:
                continue
                
            wid = res.get("window_id")
            if res.get("status") == "skipped":
                stats["skipped"] += 1
                continue
                
            if res.get("success"):
                filename = f"pic_{wid}.txt"
                filepath = os.path.join(output_dir, filename)
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(res.get("prompt", ""))
                    stats["saved"] += 1
                    stats["files"].append(filename)
                except Exception as e:
                    print(f"Error saving {filename}: {e}")
            else:
                # Ошибки не сохраняем как txt файлов
                pass
                
        return stats

    def export_summary(self, results: list, output_path: str) -> None:
        """Сохраняет сводку: обработанные, пропущенные, токены."""
        total_windows = len(results)
        skipped = sum(1 for r in results if r and r.get("status") == "skipped")
        processed = sum(1 for r in results if r and r.get("status") != "skipped")
        errors = sum(1 for r in results if r and r.get("status") == "error")
        
        tokens_in = sum(r.get("tokens_in", 0) for r in results if r)
        tokens_out = sum(r.get("tokens_out", 0) for r in results if r)
        
        windows_list = []
        for r in results:
            if not r:
                continue
                
            wid = r.get("window_id")
            if r.get("status") == "skipped":
                windows_list.append({
                    "id": wid,
                    "status": "skipped",
                    "reason": r.get("error")
                })
            else:
                if r.get("success"):
                    windows_list.append({
                        "id": wid,
                        "status": "ok",
                        "file": f"pic_{wid}.txt",
                        "tokens": r.get("tokens_in", 0) + r.get("tokens_out", 0)
                    })
                else:
                    windows_list.append({
                        "id": wid,
                        "status": "error",
                        "error": r.get("error")
                    })
                    
        summary = {
            "total_windows": total_windows,
            "processed": processed,
            "skipped_empty": skipped,
            "errors": errors,
            "total_tokens_in": tokens_in,
            "total_tokens_out": tokens_out,
            "windows": windows_list
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    from srt_splitter import parse_srt_file, split_to_windows, auto_window_size
    
    print("=== Testing PromptGenerator ===")
    
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    if not API_KEY:
        print("Set DEEPSEEK_API_KEY env var to run API generation.")
        sys.exit(0)
        
    engine = DeepSeekEngine(api_key=API_KEY)
    generator = PromptGenerator(engine)
    
    # Пытаемся найти любой docx для теста 
    script_dir = os.path.dirname(os.path.abspath(__file__))
    docx_files = [f for f in os.listdir(script_dir) if f.endswith('.docx')]
    
    if docx_files:
        sys_prompt_file = os.path.join(script_dir, docx_files[0])
        print(f"Loading system prompt from {sys_prompt_file}...")
        generator.load_system_prompt(sys_prompt_file)
    else:
        print("No .docx found. Using dummy system prompt.")
        generator.system_prompt = (
            "You are an image prompt generator for a text-to-image AI model. "
            "Respond ONLY with a verbose english detailed prompt for Midjourney describing a cinematic shot, based on the sub text. Minimum 30 characters."
        )
        
    srt_files = [f for f in os.listdir(script_dir) if f.endswith('.srt')]
    if not srt_files:
        print("No .srt found in script folder. Cannot test proper splitting with text.")
        sys.exit(0)
        
    srt_path = os.path.join(script_dir, srt_files[0])
    print(f"Parsing {srt_path}...")
    entries = parse_srt_file(srt_path)
    if not entries:
        print("No valid entries in parsed SRT.")
        sys.exit(0)
        
    ws = auto_window_size(entries)
    windows = split_to_windows(entries, window_size=ws)
    
    if len(windows) > 5:
        print(f"Divided into {len(windows)} windows. Taking first 5 for test.")
        test_windows = windows[:5]
    else:
        print(f"Divided into {len(windows)} windows. Testing on all of them.")
        test_windows = windows
    
    def on_progress(done, total, curr_id, status):
        print(f"Progress [{done}/{total}]: Window {curr_id} -> {status}")
        
    print("\nStarting generation...")
    results = generator.generate_for_windows(test_windows, max_workers=3, progress_callback=on_progress)
    
    out_dir = os.path.join(script_dir, "test_prompts_output")
    print(f"\nSaving to {out_dir}...")
    save_stats = generator.save_prompts(results, out_dir)
    print("Save stats:", save_stats)
    
    sum_path = os.path.join(out_dir, "_summary.json")
    generator.export_summary(results, sum_path)
    print(f"Summary saved to {sum_path}")
    print("Test finished successfully!")
