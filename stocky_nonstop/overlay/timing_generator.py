import os
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

# Внутренние импорты
from deepseek_engine import DeepSeekEngine
from srt_splitter import SRTWindow, format_seconds, parse_timecode

@dataclass
class ImageDescription:
    id: int
    title: str
    description: str
    keywords: List[str] = field(default_factory=list)

@dataclass
class TimingPlacement:
    image_id: int
    start_sec: float
    end_sec: float
    matched_phrase: str
    matched_timecode: str
    window_id: int

class TimingState:
    def __init__(self, buffer_size=30):
        self.placed: List[TimingPlacement] = []
        self.placed_ids: set = set()
        self.buffer_size: int = buffer_size

    def get_candidates(self, all_descriptions: List[ImageDescription]) -> List[ImageDescription]:
        candidates = []
        for d in all_descriptions:
            if d.id not in self.placed_ids:
                candidates.append(d)
                if len(candidates) >= self.buffer_size:
                    break
        return candidates

    def add_placement(self, placement: TimingPlacement, all_descriptions: List[ImageDescription]):
        self.placed.append(placement)
        self.placed_ids.add(placement.image_id)

    def is_placed(self, image_id: int) -> bool:
        return image_id in self.placed_ids


class TimingLogger:
    def __init__(self, log_dir="logs"):
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"timing_{today}.log")
        
        self.logger = logging.getLogger("TimingLogger")
        self.logger.setLevel(logging.INFO)
        
        if self.logger.handlers:
            self.logger.handlers.clear()
            
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        self.logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(ch)

    def log(self, msgs: str):
        self.logger.info(msgs)

class TimingGenerator:
    def __init__(self, deepseek_engine: DeepSeekEngine, block_size: int = 30, dead_zone: int = 13):
        self.engine = deepseek_engine
        self.system_prompt = ""
        self.logger = TimingLogger()
        self.block_size = block_size
        self.dead_zone = dead_zone

    def load_system_prompt(self, prompt_path: str) -> None:
        if os.path.exists(prompt_path):
            self.system_prompt = self.engine.load_system_prompt_from_file(prompt_path)
            self.logger.log(f"System prompt loaded from {prompt_path}")
        else:
            self.logger.log(f"Warning: System prompt file {prompt_path} not found.")

    def load_descriptions(self, filepath: str) -> List[ImageDescription]:
        """
        Загрузка описаний картинок. Поддержка JSON или текстового формата 
        (каждая строка: ID;Title;Description;Keywords)
        """
        descriptions = []
        if not os.path.exists(filepath):
            self.logger.log(f"Error: Descriptions file {filepath} not found.")
            return []
            
        try:
            if filepath.endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        descriptions.append(ImageDescription(
                            id=item.get("id"),
                            title=item.get("title", ""),
                            description=item.get("description", ""),
                            keywords=item.get("keywords", [])
                        ))
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        parts = line.split(';')
                        if len(parts) >= 3:
                            try:
                                img_id = int(parts[0].strip())
                                title = parts[1].strip()
                                desc = parts[2].strip()
                                kw = [k.strip() for k in parts[3].split(',')] if len(parts) > 3 else []
                                descriptions.append(ImageDescription(img_id, title, desc, kw))
                            except ValueError:
                                pass
        except Exception as e:
            self.logger.log(f"Error loading descriptions: {e}")
            
        self.logger.log(f"Loaded {len(descriptions)} image descriptions.")
        return descriptions

    def _clean_text(self, text: str) -> str:
        # Убираем лишние знаки для более стабильного поиска фразы
        import string
        text = text.lower()
        return text.translate(str.maketrans('', '', string.punctuation)).replace(" ", "")

    def process_window(self, window: SRTWindow, candidates: List[ImageDescription], state: TimingState) -> List[TimingPlacement]:
        if window.is_empty or not candidates:
            return []

        # Формирование system_prompt + json requirement
        sys_prompt = self.system_prompt
        if not sys_prompt:
            sys_prompt = """Ты определяешь моменты появления картинок на видео.
Тебе дано: окно SRT + список картинок-кандидатов.
Для каждой картинки скажи — говорит ли диктор о ней в этом окне, и если да — точная фраза + таймкод (из предоставленных субтитров).

Отвечай ТОЛЬКО в формате JSON:
{"matches": [{"id": 12, "phrase": "цитата", "timecode": "00:04:48,439"}]}
Если ничего не подходит: {"matches": []}"""

        # Формирование субтитров с таймкодами
        subs_text = ""
        for entry in window.entries:
            start_tc = format_seconds(entry.start_sec).replace(".", ",")
            subs_text += f"{start_tc} --> {entry.text}\n"

        cands_text = ""
        for c in candidates:
            cands_text += f"[{c.id}] \"{c.title}\" — {c.description}\n"

        user_message = f"""Окно №{window.window_id} ({format_seconds(window.start_sec)} - {format_seconds(window.end_sec)}):

Субтитры:
{subs_text}

Картинки-кандидаты:
{cands_text}"""

        res = self.engine.send_message(
            system_prompt=sys_prompt,
            user_message=user_message,
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"}
        )

        placements = []
        if not res.get("success"):
            self.logger.log(f"DeepSeek Error in window {window.window_id}: {res.get('error')}")
            return []

        content = res.get("content", "")
        try:
            data = json.loads(content)
            matches = data.get("matches", [])
        except json.JSONDecodeError:
            self.logger.log(f"JSON Parse Error in window {window.window_id}. Raw: {content}")
            return []

        cand_ids = {c.id for c in candidates}
        window_full_cleaned = self._clean_text(window.full_text)

        for match in matches:
            m_id = match.get("id")
            m_phrase = match.get("phrase", "")
            m_tc = match.get("timecode", "")

            # Валидация 1: ID в кандидатах
            if m_id not in cand_ids:
                self.logger.log(f"  [Skip] ID {m_id} not in candidates.")
                continue
            
            # Валидация 2: Уже размещен
            if state.is_placed(m_id):
                self.logger.log(f"  [Skip] ID {m_id} already placed.")
                continue

            # Валидация 3: Фраза присутствует в тексте (расслабленный поиск)
            phrase_cleaned = self._clean_text(m_phrase)
            if phrase_cleaned and phrase_cleaned not in window_full_cleaned:
                self.logger.log(f"  [Skip] ID {m_id} phrase not found in text: '{m_phrase}'")
                continue

            # Валидация 4: Таймкод и старт
            try:
                # заменяем возможные ошибки gpt (00:00:23.400 -> 00:00:23,400)
                m_tc_norm = str(m_tc).replace('.', ',')
                # если парсер timecode поддерживает миллисекунды, учитываем:
                if ',' in m_tc_norm:
                    parts = m_tc_norm.split(',')
                    base_sec = parse_timecode(parts[0])
                    milli = int(parts[1][:3]) / 1000.0 if parts[1] else 0.0
                    start_sec = base_sec + milli
                else:
                    start_sec = parse_timecode(m_tc_norm)
                
                # Check limits
                if start_sec < window.start_sec - 1.0 or start_sec > window.end_sec + 1.0:
                    self.logger.log(f"  [Skip] ID {m_id} TC out of window bounds ({start_sec} not in {window.start_sec}-{window.end_sec})")
                    continue

                end_sec = start_sec + 8.0 # Начальная длительность

                p = TimingPlacement(
                    image_id=int(m_id),
                    start_sec=start_sec,
                    end_sec=end_sec,
                    matched_phrase=m_phrase,
                    matched_timecode=m_tc,
                    window_id=window.window_id
                )
                placements.append(p)
                self.logger.log(f"  [Matched] ID {m_id} at {m_tc} in W{window.window_id}")
            except Exception as e:
                self.logger.log(f"  [Skip] ID {m_id} Invalid timecode format '{m_tc}': {e}")

        return placements

    def process_all_windows(self, windows: List[SRTWindow], descriptions: List[ImageDescription], max_workers=5, progress_callback=None) -> List[TimingPlacement]:
        dyn_buffer = max(30, max_workers * 3)
        state = TimingState(buffer_size=dyn_buffer)
        all_placements = []
        total = len(windows)
        done = 0

        # Обрабатываем окнами батчами, чтобы гарантировать обновление стейта
        from concurrent.futures import ThreadPoolExecutor

        for i in range(0, total, max_workers):
            batch = windows[i:i+max_workers]
            candidates = state.get_candidates(descriptions)
            
            if not candidates:
                # Кандидаты закончились, просто маркируем оставшиеся окна
                done += len(batch)
                if progress_callback:
                    for w in batch:
                        progress_callback(done, total, w.window_id, 0, "skipped_no_candidates")
                continue

            batch_results = []
            batch_lock = threading.Lock()

            def worker(w):
                nonlocal done
                if progress_callback:
                    progress_callback(done, total, w.window_id, 0, "processing")
                    
                placements = self.process_window(w, candidates, state)
                
                with batch_lock:
                    batch_results.append((w.window_id, placements))
                    done += 1
                    if progress_callback:
                        progress_callback(done, total, w.window_id, len(placements), "done")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Ожидаем завершения всех задач в батче
                list(executor.map(worker, batch))

            # Сортируем разультаты батча по window_id, чтобы добавлять в порядке хронологии
            batch_results.sort(key=lambda x: x[0])
            for wid, pls in batch_results:
                # Сортируем внутри окна по времени
                pls.sort(key=lambda x: x.start_sec)
                for p in pls:
                    if not state.is_placed(p.image_id): 
                        # Могла быть поставлена другим потоком в этом же батче если дубль
                        state.add_placement(p, descriptions)
                        all_placements.append(p)

        return all_placements

    def validate_and_fix(self, placements: List[TimingPlacement], video_duration: float) -> List[TimingPlacement]:
        self.logger.log("--- Starting Programmatic Validation ---")
        if not placements:
            return []

        # 1. Сортировка по времени
        placements.sort(key=lambda x: x.start_sec)

        # 2. Удаление дублей (оставляем хронологически первые)
        seen_ids = set()
        unique_placements = []
        for p in placements:
            if p.image_id not in seen_ids:
                seen_ids.add(p.image_id)
                unique_placements.append(p)
            else:
                self.logger.log(f"  [Fix] Removed duplicate ID {p.image_id}")
                
        # 3. Восстановление строгого порядка ID по времени
        id_sorted = sorted(unique_placements, key=lambda x: x.image_id)
        for i in range(len(id_sorted)):
            target = unique_placements[i]
            if id_sorted[i].image_id != target.image_id:
                self.logger.log(f"  [Fix] Reordered ID {id_sorted[i].image_id} -> slot {format_seconds(target.start_sec)}")
            id_sorted[i].start_sec = target.start_sec
            id_sorted[i].end_sec = target.end_sec
            id_sorted[i].window_id = target.window_id

        placements = id_sorted
        
        # 4. Мертвая зона
        if placements and placements[0].start_sec < float(self.dead_zone):
            dur = placements[0].end_sec - placements[0].start_sec
            placements[0].start_sec = float(self.dead_zone)
            placements[0].end_sec = float(self.dead_zone) + dur

        # 5. Автокоррекция перекрытий (минимум 0.5s зазор)
        MIN_GAP = 0.5
        MIN_DURATION = 7.0
        MAX_DURATION = 12.0
        
        valid = []
        if placements:
            valid.append(placements[0])
            
        for i in range(1, len(placements)):
            prev = valid[-1]
            curr = placements[i]

            # Нормализация длительности
            curr_dur = curr.end_sec - curr.start_sec
            if curr_dur < MIN_DURATION:
                curr.end_sec = curr.start_sec + MIN_DURATION
            elif curr_dur > MAX_DURATION:
                curr.end_sec = curr.start_sec + MAX_DURATION

            gap = curr.start_sec - prev.end_sec
            if gap < MIN_GAP:
                overlap = MIN_GAP - gap
                # Пытаемся укоротить prev
                if (prev.end_sec - overlap - prev.start_sec) >= MIN_DURATION:
                    prev.end_sec -= overlap
                    self.logger.log(f"  [Fix] ID {prev.image_id} shrunken to resolve overlap.")
                else:
                    # Пытаемся подвинуть curr вперед
                    old_start = curr.start_sec
                    curr.start_sec = prev.end_sec + MIN_GAP
                    curr.end_sec = curr.start_sec + MIN_DURATION # сбрасываем к min_dur
                    self.logger.log(f"  [Fix] ID {curr.image_id} pushed +{curr.start_sec - old_start:.2f}s to resolve overlap.")
                    
            valid.append(curr)

        # 4. Проверка границ видео (Первый старт >= 0.2, Последний <= video_duration)
        final_list = []
        for p in valid:
            if p.start_sec < 0.2:
                self.logger.log(f"  [Fix] ID {p.image_id} start_sec < 0.2s, pushed to 0.2s.")
                dur = p.end_sec - p.start_sec
                p.start_sec = 0.2
                p.end_sec = p.start_sec + dur

            if p.end_sec > video_duration:
                excess = p.end_sec - video_duration
                if (p.end_sec - excess - p.start_sec) >= MIN_DURATION:
                    p.end_sec -= excess
                    self.logger.log(f"  [Fix] ID {p.image_id} trimmed at end of video.")
                else:
                    self.logger.log(f"  [Fix] ID {p.image_id} removed, too close to end.")
                    continue
                    
            final_list.append(p)

        self.logger.log(f"--- Validation Complete: {len(final_list)} valid placements ---")
        return final_list

    def export_table(self, placements: List[TimingPlacement], output_path: str) -> None:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("IMAGE_ID;START_SEC;END_SEC;WINDOW_ID;MATCHED_PHRASE\n")
                for p in placements:
                    str_clean_phrase = p.matched_phrase.replace(";", ",").replace("\n", " ")
                    start_str = f"{p.start_sec:.3f}".replace('.', ',')
                    end_str = f"{p.end_sec:.3f}".replace('.', ',')
                    f.write(f"{p.image_id};{start_str};{end_str};{p.window_id};{str_clean_phrase}\n")
            self.logger.log(f"Exported placement table to {output_path}")
        except Exception as e:
            self.logger.log(f"Error exporting table: {e}")


# ==========================================
# ТЕСТИРОВАНИЕ
# ==========================================
if __name__ == "__main__":
    import sys
    from srt_splitter import parse_srt_file, split_to_windows, auto_window_size
    
    print("=== Testing TimingGenerator ===")
    
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    if not API_KEY:
        print("Set DEEPSEEK_API_KEY env var to run API generation.")
        sys.exit(0)
        
    engine = DeepSeekEngine(api_key=API_KEY)
    generator = TimingGenerator(engine)
    
    # 1. Загрузка промта
    script_dir = os.path.dirname(os.path.abspath(__file__))
    docx_files = [f for f in os.listdir(script_dir) if f.endswith('.docx')]
    if docx_files:
        generator.load_system_prompt(os.path.join(script_dir, docx_files[0]))
    else:
        print("No .docx found. Using default system prompt.")
        
    # 2. Создание фейковых кандиатов (txt файл с описаниями)
    desc_path = os.path.join(script_dir, "test_descriptions.txt")
    if not os.path.exists(desc_path):
        with open(desc_path, 'w', encoding='utf-8') as f:
            f.write("1;Вступление;Начало видео и приветствие;старт,привет\n")
            f.write("2;Важный факт;Диктор описывает статистику;статистика,график\n")
            f.write("3;Пример;Жизненная ситуация;пример,человек\n")
            f.write("4;Заключение;Прощание с аудиторией;конец,пока\n")
        print(f"Created fake descriptions file: {desc_path}")
        
    descriptions = generator.load_descriptions(desc_path)
    
    # 3. Загрузка SRT
    srt_files = [f for f in os.listdir(script_dir) if f.endswith('.srt')]
    if not srt_files:
        print("No .srt found in script folder. Cannot test.")
        sys.exit(0)
        
    srt_path = os.path.join(script_dir, srt_files[0])
    print(f"Parsing {srt_path}...")
    entries = parse_srt_file(srt_path)
    if not entries:
        print("No valid entries in parsed SRT.")
        sys.exit(0)
        
    # Видео duration определяем по самому концу субтитров + 5 секунд
    video_dur = entries[-1].end_sec + 5.0
        
    ws = float(generator.block_size)
    windows = split_to_windows(entries, window_size=ws)
    
    num_to_test = min(len(windows), 5)
    test_windows = windows[:num_to_test]
    print(f"Testing on first {num_to_test} windows...")
    
    def on_progress(done, total, curr_id, found_count, status):
        print(f"Progress [{done}/{total}]: Window {curr_id} -> {status} (Found: {found_count})")
        
    print("\nStarting generator processing...")
    placements = generator.process_all_windows(
        windows=test_windows, 
        descriptions=descriptions, 
        max_workers=3, 
        progress_callback=on_progress
    )
    
    print("\nStarting validation phase...")
    valid_placements = generator.validate_and_fix(placements, video_duration=video_dur)
    
    out_table = os.path.join(script_dir, "test_timings.csv")
    generator.export_table(valid_placements, out_table)
    
    print("Test finished successfully!")
