import os
import json
import logging
import threading
import re
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Заимствуем из overlay
from stocky_nonstop.overlay.deepseek_engine import DeepSeekEngine
from stocky_nonstop.overlay.srt_splitter import SRTWindow, format_seconds, parse_timecode, parse_srt_file, split_to_windows

# Цены DeepSeek (за 1M токенов)
PRICE_INPUT_PER_1M = 0.14
PRICE_OUTPUT_PER_1M = 0.28

@dataclass
class ImagePrompt:
    id: int
    titles: List[str]
    summary: str
    raw: str

@dataclass
class TimingPlacement:
    image_id: int
    start_sec: float
    end_sec: float
    matched_phrase: str
    matched_timecode: str
    window_id: int
    retry_level: int = 0

class TimingState:
    def __init__(self, buffer_size=30):
        self.placed: List[TimingPlacement] = []
        self.placed_ids: Set[int] = set()
        self.buffer_size: int = buffer_size

    def get_candidates(self, all_prompts: List[ImagePrompt]) -> List[ImagePrompt]:
        candidates = []
        # Выдаем только те промпты, которые еще не были размещены
        for p in all_prompts:
            if p.id not in self.placed_ids:
                candidates.append(p)
                if len(candidates) >= self.buffer_size:
                    break
        return candidates

    def add_placement(self, placement: TimingPlacement, all_prompts: List[ImagePrompt]):
        self.placed.append(placement)
        self.placed_ids.add(placement.image_id)

    def is_placed(self, image_id: int) -> bool:
        return image_id in self.placed_ids

class TimingLogger:
    def __init__(self, log_dir="logs"):
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"timing_{today}.log")
        
        self.logger = logging.getLogger("TimingLoggerPlacer")
        self.logger.setLevel(logging.INFO)
        
        if self.logger.handlers:
            self.logger.handlers.clear()
            
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(ch)

    def log(self, msgs: str):
        ts = datetime.now().strftime("%H:%M:%S")
        formatted = f"{ts} | {msgs}"
        self.logger.info(formatted)

class TimingGenerator:
    def parse_json_safe(self, text: str):
        if not text: return None
        import re, json
        match = re.search(r'\{[^{}]*"id"[^{}]*\}', text, re.DOTALL)
        if not match: return None
        try: return json.loads(match.group(0))
        except: return None

    def seconds_to_time(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def __init__(self, api_key: str, progress_callback: Optional[Callable] = None, block_size: int = 30, dead_zone: int = 13, provider: Optional[str] = None, model: Optional[str] = None):
        self.engine = DeepSeekEngine(api_key=api_key, provider=provider, model=model)
        self.progress_callback = progress_callback
        self.logger = TimingLogger()
        self.system_prompt = ""
        self.block_size = block_size
        self.dead_zone = dead_zone

    def log_and_progress(self, msg: str, status_str: str = "info", **kwargs):
        self.logger.log(msg)
        if self.progress_callback:
            try:
                self.progress_callback({"message": msg, "status": status_str, **kwargs})
            except Exception as e:
                self.logger.log(f"Error in progress callback: {e}")

    def load_system_prompt(self, prompt_path: str) -> None:
        if prompt_path and os.path.exists(prompt_path):
            self.system_prompt = self.engine.load_system_prompt_from_file(prompt_path)
            self.log_and_progress(f"System prompt loaded from {prompt_path}")

    def parse_prompts(self, prompts_path: str) -> List[ImagePrompt]:
        prompts = []
        if not os.path.exists(prompts_path):
            return []
        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            img_id = 1
            pattern = re.compile(r'["«“]([^"»”]+)["»”]')
            for line in lines:
                line = line.strip()
                if not line: continue
                titles = [t.strip() for t in pattern.findall(line) if len(t.strip()) >= 3]
                prompts.append(ImagePrompt(id=img_id, titles=titles, summary=line[:300], raw=line))
                img_id += 1
        except Exception as e:
            self.log_and_progress(f"Error parsing prompts: {e}", "error")
        return prompts

    def process_window(self, window: SRTWindow, candidate: ImagePrompt) -> dict:
        result = {"placements": [], "tokens": 0, "cost": 0.0}
        if window.is_empty or not candidate:
            return result

        subs_text = ""
        for entry in window.entries:
            start_tc = format_seconds(entry.start_sec).replace(".", ",")
            subs_text += f"{start_tc} --> {entry.text}\n"

        titles_str = " | ".join([f'"{t}"' for t in candidate.titles])
        if not titles_str: titles_str = "No Title"
        cand_text = f"[{candidate.id}] {titles_str} — {candidate.summary}...\n"

        user_message = (
            f"Окно №{window.window_id} ({format_seconds(window.start_sec)}–{format_seconds(window.end_sec)}):\n\n"
            f"СУБТИТРЫ В ЭТОМ ОКНЕ:\n{subs_text}\n\n"
            f"КАРТИНКА ДЛЯ ЭТОГО ОКНА (она ровно одна):\n{cand_text}\n\n"
            f"Твоя задача: найти точную секунду для ЭТОЙ картинки в этих субтитрах.\n"
            f"Ответь строго в формате JSON: "
            f'{{"matches":[{{"id":{candidate.id},"start":"HH:MM:SS,mmm","end":"HH:MM:SS,mmm","phrase":"цитата"}}]}}'
        )

        res = self.engine.send_message(
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=0.2,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )

        if not res.get("success"):
            self.log_and_progress(f"[WINDOW {window.window_id}] API Error: {res.get('error')}", "error")
            return result

        tokens_in = res.get("tokens_in", 0)
        tokens_out = res.get("tokens_out", 0)
        result["tokens"] = tokens_in + tokens_out
        result["cost"] = (tokens_in / 1_000_000.0) * PRICE_INPUT_PER_1M + (tokens_out / 1_000_000.0) * PRICE_OUTPUT_PER_1M

        content = res.get("content", "")
        data = self.parse_json_safe(content)
        if not data:
            self.log_and_progress(f"[WINDOW {window.window_id}] JSON Parse Error", "warning")
            return result

        matches = data.get("matches", [])
        if not matches and "id" in data:
            matches = [data]

        for match in matches:
            m_id = match.get("id")
            if str(m_id) != str(candidate.id): continue
                
            m_phrase = match.get("phrase", "")
            m_start_tc = match.get("start", "")
            m_end_tc = match.get("end", "")

            try:
                start_sec = parse_timecode(str(m_start_tc).replace('.', ','))
                end_sec = parse_timecode(str(m_end_tc).replace('.', ','))
                
                # ЖЁСТКАЯ ПРИВЯЗКА: Запрещаем GPT вылезать за пределы окна
                if start_sec < window.start_sec or start_sec > window.end_sec:
                    start_sec = window.start_sec
                    
                dur = end_sec - start_sec
                if dur < 7.0: end_sec = start_sec + 7.0
                if dur > 15.0: end_sec = start_sec + 15.0

                p = TimingPlacement(
                    image_id=int(candidate.id),
                    start_sec=start_sec,
                    end_sec=end_sec,
                    matched_phrase=m_phrase,
                    matched_timecode=m_start_tc,
                    window_id=window.window_id
                )
                result["placements"].append(p)
                self.log_and_progress(f"[WINDOW {window.window_id}] matched ID={m_id} start={m_start_tc} end={m_end_tc} phrase='{m_phrase}'", "success")
            except Exception as e:
                self.log_and_progress(f"[WINDOW {window.window_id}] Ошибка таймкода: {e}", "warning")

        return result

    def start_process(self, prompts_path: str, srt_path: str, docx_path: str, max_workers: int = 20) -> bool:
        self.log_and_progress(f"Starting Timing Placer...", "info")
        self.load_system_prompt(docx_path)
        
        prompts = self.parse_prompts(prompts_path)
        if not prompts: return False

        try:
            entries = parse_srt_file(srt_path)
        except Exception as e:
            self.log_and_progress(f"Error parsing SRT: {e}", "error")
            return False
            
        video_duration = entries[-1].end_sec if entries else 0
        from stocky_nonstop.overlay.srt_splitter import split_to_windows
        windows = split_to_windows(entries, window_size=float(self.block_size))
        
        # --- ЖЁСТКАЯ СВЯЗКА 1 К 1 ---
        pairs = []
        max_len = min(len(windows), len(prompts))
        for idx in range(max_len):
            pairs.append((windows[idx], prompts[idx]))
            
        if len(prompts) > len(windows):
            self.log_and_progress(f"⚠️ Картинок ({len(prompts)}) больше чем окон ({len(windows)}). Лишние отброшены.", "warning")
            
        all_placements = []
        total = len(pairs)
        total_tokens = 0
        total_cost = 0.0
        done = 0

        for i in range(0, total, max_workers):
            batch = pairs[i:i+max_workers]
            self.log_and_progress(f"Processing batch {i//max_workers + 1}...", "info", done=i, total=total)
            
            batch_results = []
            batch_lock = threading.Lock()

            def worker(pair):
                win, prompt = pair
                res = self.process_window(win, prompt)
                with batch_lock:
                    batch_results.append((win.window_id, res, prompt))
                    if res.get("tokens", 0) > 0:
                        self.log_and_progress(
                            f"[WINDOW {win.window_id}] токенов: {res.get('tokens', 0)}, стоимость: ${res.get('cost', 0.0):.6f}", "info"
                        )

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                list(executor.map(worker, batch))

            batch_results.sort(key=lambda x: x[0])
            
            for wid, res, prompt in batch_results:
                placements = res.get("placements", [])
                
                # Если нейросеть затупила - ставим принудительно (чтобы не было пропусков)
                if not placements:
                    self.log_and_progress(f"⚠️ Окно {wid}: GPT не дал ответ. Ставлю принудительно.", "warning")
                    start_sec = (wid - 1) * float(self.block_size)
                    self.log_and_progress(f"[WINDOW {wid}] matched ID={prompt.id} start={self.seconds_to_time(start_sec)} end={self.seconds_to_time(start_sec + 10.0)} phrase='[Авто-расстановка]'", "success")
                    all_placements.append(TimingPlacement(
                        image_id=prompt.id,
                        start_sec=start_sec,
                        end_sec=start_sec + 10.0,
                        matched_phrase="[Авто-генерация]",
                        matched_timecode=self.seconds_to_time(start_sec),
                        window_id=wid
                    ))
                else:
                    all_placements.extend(placements)
                        
                total_tokens += res.get("tokens", 0)
                total_cost += res.get("cost", 0.0)
                done += 1
                
                self.log_and_progress(
                    f"Прогресс: {done}/{total}", "info",
                    tokens=total_tokens, cost=total_cost, matched=len(all_placements), total=total
                )

        self.log_and_progress("✅ Генерация завершена. Выравниваем тайминги...", "info")
        valid_placements = self.validate_and_fix(all_placements, video_duration)
        
        output_path = os.path.join(os.path.dirname(prompts_path), "prompts_timings.txt")
        self.export_csv(valid_placements, output_path)
        self.log_and_progress(f"Process complete! Output saved to: {output_path}", "success", done=total, total=total, matched=len(valid_placements))
        return True

    def validate_and_fix(self, placements: List[TimingPlacement], video_duration: float) -> List[TimingPlacement]:
        if not placements: return []

        # Строгая сортировка по ID картинок
        placements.sort(key=lambda x: x.image_id)
        
        # Мертвая зона для первой картинки
        if placements[0].start_sec < float(self.dead_zone):
            dur = placements[0].end_sec - placements[0].start_sec
            placements[0].start_sec = float(self.dead_zone)
            placements[0].end_sec = placements[0].start_sec + dur

        MIN_GAP = 0.3
        valid = [placements[0]]
        
        for i in range(1, len(placements)):
            prev = valid[-1]
            curr = placements[i]

            # Если наезжает на предыдущую - двигаем вперед
            if curr.start_sec < prev.end_sec + MIN_GAP:
                curr.start_sec = prev.end_sec + MIN_GAP
                curr.end_sec = curr.start_sec + 10.0
                
            valid.append(curr)

        # Ограничение по длине видео
        for p in valid:
            if p.end_sec > video_duration:
                p.end_sec = video_duration
            if p.start_sec > video_duration - 1:
                p.start_sec = video_duration - 2

        self.log_and_progress(f"Validation Complete: {len(valid)} placements ready.", "info")
        return valid

    def export_csv(self, placements: List[TimingPlacement], output_path: str) -> None:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for p in placements:
                    start_str = f"{p.start_sec:.3f}".replace('.', ',')
                    end_str = f"{p.end_sec:.3f}".replace('.', ',')
                    f.write(f"{p.image_id};{start_str};{end_str}\n")
            self.log_and_progress(f"Exported placement table to {output_path}", "success")
        except Exception as e:
            self.log_and_progress(f"Error exporting table: {e}", "error")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--srt", required=True)
    parser.add_argument("--api_key", required=True)
    parser.add_argument("--docx", required=False, default="")
    args = parser.parse_args()
    
    gen = TimingGenerator(api_key=args.api_key)
    gen.start_process(args.prompts, args.srt, args.docx)
