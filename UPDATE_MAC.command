#!/bin/bash
# ============================================================
#  Stocky non Stop — macOS Auto-Update
#  Двойной клик = обновление с GitHub + запуск
#  Работает и с git-репозиторием, и с ZIP-распаковкой
# ============================================================
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

REPO="xstixx1-alt/Port_MAC"
BRANCH="main"
ZIP_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"

echo ""
echo "=========================================="
echo "  Stocky non Stop — Обновление"
echo "=========================================="
echo ""

# --- 1. Проверяем git (опционально) ---
HAS_GIT=false
if command -v git &>/dev/null; then
    HAS_GIT=true
fi

# --- 2. Сохраняем конфиг пользователя ---
echo -e "${YELLOW}[1/4]${NC} Сохраняю ваши данные (config.json, settings.json)..."
cp -f config.json config.json.bak 2>/dev/null
cp -f settings.json settings.json.bak 2>/dev/null

# --- 3. Обновление ---
if [ -d ".git" ] && $HAS_GIT; then
    # Способ 1: git pull (если репозиторий клонирован)
    echo -e "${YELLOW}[2/4]${NC} Обновление через git pull..."
    git fetch origin
    git reset --hard origin/${BRANCH}
else
    # Способ 2: скачать ZIP с GitHub и распаковать поверх
    echo -e "${YELLOW}[2/4]${NC} Скачиваю обновление с GitHub..."
    TMP_ZIP="/tmp/stocky_update_$$.zip"
    TMP_DIR="/tmp/stocky_update_$$"

    # Скачиваем
    if command -v curl &>/dev/null; then
        curl -sL -o "$TMP_ZIP" "$ZIP_URL"
    elif command -v wget &>/dev/null; then
        wget -q -O "$TMP_ZIP" "$ZIP_URL"
    else
        echo -e "${RED}Нет curl/wget! Установите Xcode Command Line Tools:${NC}"
        echo "  xcode-select --install"
        read -p "Нажмите Enter для выхода..."
        exit 1
    fi

    if [ ! -f "$TMP_ZIP" ] || [ ! -s "$TMP_ZIP" ]; then
        echo -e "${RED}Не удалось скачать обновление.${NC}"
        rm -f "$TMP_ZIP"
        read -p "Нажмите Enter для выхода..."
        exit 1
    fi

    # Распаковываем
    echo -e "${YELLOW}[3/4]${NC} Распаковываю..."
    unzip -qo "$TMP_ZIP" -d "$TMP_DIR"

    # Ищем папку внутри архива (GitHub создаёт Port_MAC-main/)
    EXTRACTED_DIR=$(ls -d "$TMP_DIR"/Port_MAC-* 2>/dev/null | head -1)
    if [ -z "$EXTRACTED_DIR" ]; then
        echo -e "${RED}Не удалось распаковать архив.${NC}"
        rm -rf "$TMP_ZIP" "$TMP_DIR"
        read -p "Нажмите Enter для выхода..."
        exit 1
    fi

    # Копируем файлы поверх, ИСКЛЮЧАЯ пользовательские данные
    rsync -a --exclude='.git' \
        --exclude='config.json' \
        --exclude='settings.json' \
        --exclude='stocky.log' \
        --exclude='downloads/' \
        --exclude='.venv/' \
        --exclude='__pycache__/' \
        --exclude='build/' \
        --exclude='dist/' \
        --exclude='merge_test_tmp*/' \
        "$EXTRACTED_DIR"/ ./

    # Убираем за собой
    rm -rf "$TMP_ZIP" "$TMP_DIR"
fi

# --- 4. Восстанавливаем конфиг ---
echo -e "${YELLOW}[4/4]${NC} Восстанавливаю ваши настройки..."
cp -f config.json.bak config.json 2>/dev/null
cp -f settings.json.bak settings.json 2>/dev/null
rm -f config.json.bak settings.json.bak

# --- 5. Обновляем зависимости ---
echo -e "${CYAN}Проверяю зависимости...${NC}"
if [ -d ".venv" ]; then
    source .venv/bin/activate
    pip install -q eel gevent requests python-docx 2>/dev/null
else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q eel gevent requests python-docx 2>/dev/null
fi

echo ""
echo -e "${GREEN}✅ Обновление завершено!${NC}"
echo ""

# --- 6. Запуск ---
echo "Запускаю Stocky non Stop..."
python3 main.py
