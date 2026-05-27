#!/usr/bin/env python3
"""srt_splitter.py — Разделение SRT на временные окна."""

import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class SRTEntry:
    index: int
    start_sec: float
    end_sec: float
    text: str


@dataclass
class SRTWindow:
    window_id: int
    start_sec: float
    end_sec: float
    entries: List[SRTEntry] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join(entry.text for entry in self.entries)

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0


def parse_timecode(tc_str: str) -> float:
    tc_str = tc_str.strip().replace(',', '.')
    parts = tc_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(tc_str)


def format_seconds(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _clean_srt_text(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def parse_srt(srt_text: str) -> List[SRTEntry]:
    srt_text = srt_text.lstrip('\ufeff')
    blocks = re.split(r'\n\s*\n', srt_text.replace('\r', '').strip())

    entries = []
    for block in blocks:
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if len(lines) >= 3:
            try:
                index = int(lines[0])
                timecode_line = lines[1]
                if '-->' in timecode_line:
                    start_str, end_str = timecode_line.split('-->')
                    start_sec = parse_timecode(start_str)
                    end_sec = parse_timecode(end_str)
                    text_content = " ".join(lines[2:])
                    text_content = _clean_srt_text(text_content)
                    if text_content:
                        entries.append(SRTEntry(
                            index=index,
                            start_sec=start_sec,
                            end_sec=end_sec,
                            text=text_content
                        ))
            except Exception:
                continue
    return entries


def read_file_safe(filepath: str) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'cp1251', 'latin-1'):
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise RuntimeError(f"Не удалось прочитать файл: {filepath}")


def parse_srt_file(filepath: str) -> List[SRTEntry]:
    try:
        text = read_file_safe(filepath)
        return parse_srt(text)
    except FileNotFoundError:
        print(f"ОШИБКА: Файл не найден: {filepath}")
        return []
    except Exception as e:
        print(f"ОШИБКА чтения '{filepath}': {e}")
        return []


def auto_window_size(entries: List[SRTEntry]) -> float:
    if not entries:
        return 30.0
    total_chars = sum(len(e.text) for e in entries)
    total_time = entries[-1].end_sec - entries[0].start_sec
    if total_time <= 0:
        return 30.0
    density = total_chars / total_time
    if density > 20:
        return 20.0
    elif density >= 8:
        return 30.0
    else:
        return 45.0


def split_to_windows(entries: List[SRTEntry], window_size: Optional[float] = None) -> List[SRTWindow]:
    """Разделяет на окна. Нумерация ВСЕГДА с window_001,
    независимо от того с какого времени начинается SRT.
    Реальные таймкоды (для рендера) сохраняются в start_sec/end_sec."""
    if not entries:
        return []

    if window_size is None or window_size <= 0:
        window_size = auto_window_size(entries)

    # === АВТО-СДВИГ ===
    # Берём время первого субтитра, округляем ВНИЗ до целого окна
    first_start = entries[0].start_sec
    offset = (int(first_start // window_size)) * window_size

    if offset > 0:
        print(f"[INFO] SRT начинается с {format_seconds(first_start)}, "
              f"сдвиг -{format_seconds(offset)} (окна с window_001)")

    windows = []

    for e in entries:
        shifted_start = e.start_sec - offset
        if shifted_start < 0:
            shifted_start = 0

        win_idx = int(shifted_start // window_size) + 1

        while len(windows) < win_idx:
            w_id = len(windows) + 1
            real_start = (w_id - 1) * window_size + offset
            real_end = w_id * window_size + offset
            windows.append(SRTWindow(
                window_id=w_id,
                start_sec=real_start,
                end_sec=real_end,
                entries=[]
            ))

        windows[win_idx - 1].entries.append(e)

    return windows


def get_window_info(windows: List[SRTWindow]) -> dict:
    total = len(windows)
    empty = sum(1 for w in windows if w.is_empty)
    return {
        "total_windows": total,
        "filled_windows": total - empty,
        "empty_windows": empty,
        "total_subs": sum(len(w.entries) for w in windows)
    }


def export_windows_to_text(windows: List[SRTWindow], output_dir: str) -> int:
    os.makedirs(output_dir, exist_ok=True)
    count = 0
    for w in windows:
        if not w.is_empty:
            filename = os.path.join(output_dir, f"window_{w.window_id:03d}.txt")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Окно {w.window_id} [{format_seconds(w.start_sec)} - {format_seconds(w.end_sec)}]\n")
                f.write("=" * 50 + "\n\n")
                for entry in w.entries:
                    f.write(f"[{format_seconds(entry.start_sec)}] {entry.text}\n")
            count += 1
    return count


# ============================================================
#  ТЕСТ
# ============================================================

if __name__ == "__main__":

    log_lines = []

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        log_lines.append(line)
        print(line)

    try:
        print("=" * 60)
        print("  SRT SPLITTER")
        print("=" * 60)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        log(f"Папка: {script_dir}")

        # ВАЖНО: чистим старую test_output
        out_dir = os.path.join(script_dir, "test_output")
        if os.path.exists(out_dir):
            import shutil
            shutil.rmtree(out_dir)
            log("Старая test_output удалена")

        srt_files = [f for f in os.listdir(script_dir) if f.lower().endswith('.srt')]
        log(f"SRT файлов найдено: {len(srt_files)}")

        if not srt_files:
            log("ОШИБКА: Нет .srt в папке!")
        else:
            srt_file = srt_files[0]
            srt_path = os.path.join(script_dir, srt_file)
            log(f"Файл: {srt_file} ({os.path.getsize(srt_path)} байт)")

            entries = parse_srt_file(srt_path)
            log(f"Распарсено: {len(entries)} субтитров")

            if entries:
                log(f"Первый субтитр: {format_seconds(entries[0].start_sec)}")
                log(f"Последний:      {format_seconds(entries[-1].end_sec)}")

                ws = auto_window_size(entries)
                log(f"Размер окна: {ws} сек")

                windows = split_to_windows(entries, window_size=ws)
                info = get_window_info(windows)
                log(f"Всего окон: {info['total_windows']}")
                log(f"С текстом:  {info['filled_windows']}")
                log(f"Пустых:     {info['empty_windows']}")

                log("")
                log("Первые 3 окна:")
                for w in windows[:3]:
                    label = "ПУСТО" if w.is_empty else f"{len(w.entries)} субт."
                    log(f"  {w.window_id:03d} [{format_seconds(w.start_sec)}-{format_seconds(w.end_sec)}] {label}")
                    if not w.is_empty:
                        log(f"      > {w.full_text[:90]}")

                log("")
                log("Последние 3 окна:")
                for w in windows[-3:]:
                    label = "ПУСТО" if w.is_empty else f"{len(w.entries)} субт."
                    log(f"  {w.window_id:03d} [{format_seconds(w.start_sec)}-{format_seconds(w.end_sec)}] {label}")
                    if not w.is_empty:
                        log(f"      > {w.full_text[:90]}")

                saved = export_windows_to_text(windows, out_dir)
                log("")
                log(f"Экспортировано: {saved} файлов")
                log(f"Папка: {out_dir}")

                files = sorted(os.listdir(out_dir))
                if files:
                    log(f"Первый файл:    {files[0]}")
                    log(f"Последний файл: {files[-1]}")

                log("")
                log("=" * 40)
                log("ГОТОВО!")

    except Exception as e:
        log(f"ОШИБКА: {e}")
        log(traceback.format_exc())

    finally:
        try:
            log_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "srt_splitter_log.txt"
            )
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(log_lines))
        except Exception:
            pass

        print("\nНажми Enter...")
        try:
            input()
        except EOFError:
            pass