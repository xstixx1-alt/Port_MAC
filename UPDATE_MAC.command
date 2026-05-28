#!/bin/bash
# ============================================================
#  Stocky non Stop — macOS Auto-Update
#  Двойной клик = обновление с GitHub + запуск
# ============================================================
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=========================================="
echo "  Stocky non Stop — Обновление"
echo "=========================================="
echo ""

# --- 1. Проверяем git ---
if ! command -v git &>/dev/null; then
    echo -e "${RED}Git не установлен! Установите Xcode Command Line Tools:${NC}"
    echo "  xcode-select --install"
    echo ""
    echo "После установки запустите UPDATE_MAC.command снова."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

# --- 2. Проверяем что это git-репозиторий ---
if [ ! -d ".git" ]; then
    echo -e "${RED}Это не git-репозиторий. Обновление невозможно.${NC}"
    echo "Скачайте свежую версию с GitHub."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

# --- 3. Сохраняем конфиг пользователя ---
echo -e "${YELLOW}[1/3]${NC} Сохраняю ваш config.json..."
cp -f config.json config.json.bak 2>/dev/null

# --- 4. Git pull ---
echo -e "${YELLOW}[2/3]${NC} Скачиваю обновление с GitHub..."
git fetch origin
git reset --hard origin/main

# --- 5. Восстанавливаем конфиг ---
echo -e "${YELLOW}[3/3]${NC} Восстанавливаю ваш config.json..."
cp -f config.json.bak config.json 2>/dev/null
rm -f config.json.bak

# --- 6. Обновляем зависимости ---
echo -e "${YELLOW}Обновляю зависимости...${NC}"
if [ -d ".venv" ]; then
    source .venv/bin/activate
    pip install -q eel gevent requests python-docx 2>/dev/null
else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q eel gevent requests python-docx 2>/dev/null
fi

echo ""
echo -e "${GREEN}Обновление завершено!${NC}"
echo ""

# --- 7. Запуск ---
echo "Запускаю Stocky non Stop..."
python3 main.py
