# Stocky non Stop — модуль резервного копирования проекта
# Автор: Азат (@inomix | inomixx@gmail.com)

import shutil
import os
from datetime import datetime

# === НАСТРОЙКИ ===
SOURCE = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(SOURCE)
folder_name = os.path.basename(SOURCE)
BACKUP_DIR = os.path.join(parent_dir, f"{folder_name}_Backups")

# Что исключать (node_modules НЕ нужен — восстанавливается через npm install)
EXCLUDE_PATTERNS = [
    '__pycache__', 
    '*.pyc', 
    'venv',          # виртуальное окружение
    '.venv',
    'env',
    'node_modules',  # НЕ нужен в бэкапе
    '*.pt',          # 🔥 модели Whisper (small.pt, base.pt, medium.pt и т.д.) — качаются автоматически
    # '.git',        # РАСКОММЕНТИРУЙ если хочешь БЕЗ git истории
    # '*.log',       # РАСКОММЕНТИРУЙ если логи не нужны
]

# 🔥 Конкретные тяжёлые файлы для отображения в диагностике
HEAVY_FILES_TO_REPORT = [
    os.path.join('models', 'small.pt'),
    os.path.join('models', 'base.pt'),
    os.path.join('models', 'medium.pt'),
    os.path.join('models', 'large.pt'),
    os.path.join('models', 'tiny.pt'),
]


def folder_size(path):
    """Размер папки в байтах"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except (OSError, FileNotFoundError):
                pass
    return total


def file_size(path):
    """Размер одного файла в байтах"""
    try:
        return os.path.getsize(path)
    except (OSError, FileNotFoundError):
        return 0


def format_size(size_bytes):
    """Красивый вывод размера"""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024**2):.1f} MB"
    else:
        return f"{size_bytes / 1024:.0f} KB"


def get_next_number():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    max_num = 0
    for folder in os.listdir(BACKUP_DIR):
        if folder.startswith("backup_"):
            try:
                parts = folder.split("_")
                num = int(parts[1])
                max_num = max(max_num, num)
            except:
                continue
    return max_num + 1


def backup():
    next_num = get_next_number()
    timestamp = datetime.now().strftime('%d.%m.%Y_%H-%M')
    backup_name = f"backup_{next_num}_{timestamp}"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    # === ДИАГНОСТИКА ДО КОПИРОВАНИЯ ===
    print(f"╔══════════════════════════════════════════╗")
    print(f"║         BACKUP STARTED                   ║")
    print(f"╠══════════════════════════════════════════╣")
    print(f"║  Откуда:  {SOURCE}")
    print(f"║  Куда:    ...\\{backup_name}")
    print(f"║  Номер:   #{next_num}")
    print(f"╠══════════════════════════════════════════╣")
    
    # Размер исходника
    source_size = folder_size(SOURCE)
    print(f"║  📁 Размер исходника: {format_size(source_size)}")
    
    # Показать что исключаем (папки)
    print(f"║")
    print(f"║  ⛔ Исключаем папки:")
    excluded_total = 0
    for pattern in ['node_modules', '.git', '__pycache__', 'venv', '.venv', 'env']:
        path = os.path.join(SOURCE, pattern)
        if os.path.exists(path):
            size = folder_size(path)
            excluded_total += size
            print(f"║     {pattern}: {format_size(size)}")
    
    # 🔥 Показать что исключаем (тяжёлые .pt модели)
    pt_excluded = 0
    pt_found = []
    for rel_path in HEAVY_FILES_TO_REPORT:
        full_path = os.path.join(SOURCE, rel_path)
        if os.path.exists(full_path):
            size = file_size(full_path)
            pt_excluded += size
            pt_found.append((rel_path, size))
    
    if pt_found:
        print(f"║")
        print(f"║  ⛔ Исключаем .pt модели Whisper:")
        for rel_path, size in pt_found:
            print(f"║     {rel_path}: {format_size(size)}")
        excluded_total += pt_excluded
    
    expected = source_size - excluded_total
    print(f"║")
    print(f"║  📊 Ожидаемый размер бэкапа: ~{format_size(expected)}")
    print(f"║  📊 Разница (исключённое): ~{format_size(excluded_total)}")
    print(f"╚══════════════════════════════════════════╝")
    print()
    print("Копирую...")
    
    # === КОПИРОВАНИЕ ===
    shutil.copytree(
        SOURCE, 
        backup_path,
        ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS)
    )
    
    # === РЕЗУЛЬТАТ ===
    backup_size = folder_size(backup_path)
    
    # Считаем файлы
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(backup_path):
        file_count += len(filenames)
    
    print()
    print(f"✅ Готово!")
    print(f"   📁 {backup_name}")
    print(f"   📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"   💾 Размер бэкапа: {format_size(backup_size)}")
    print(f"   📄 Файлов: {file_count}")
    print(f"   📊 Исходник: {format_size(source_size)} → Бэкап: {format_size(backup_size)}")
    print(f"   📊 Исключено: {format_size(source_size - backup_size)}")
    
    if backup_size < expected * 0.9:
        print()
        print(f"   ⚠️  ВНИМАНИЕ: Бэкап меньше ожидаемого! Возможно что-то пропущено.")


if __name__ == "__main__":
    backup()
    input("\nНажми Enter чтобы закрыть...")