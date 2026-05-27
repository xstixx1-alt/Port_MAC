#!/bin/bash
# ============================================================
#  Stocky non Stop — macOS Installer
#  Двойной клик на этот файл = установка + запуск
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=========================================="
echo "  Stocky non Stop — macOS Installer"
echo "=========================================="
echo ""

# --- 1. Homebrew ---
if ! command -v brew &>/dev/null; then
    echo -e "${YELLOW}[1/5]${NC} Устанавливаю Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for this session
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -f /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
else
    echo -e "${GREEN}[1/5]${NC} Homebrew уже установлен"
fi

# --- 2. Python ---
if ! command -v python3 &>/dev/null; then
    echo -e "${YELLOW}[2/5]${NC} Устанавливаю Python..."
    brew install python
else
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}[2/5]${NC} Python $PY_VER уже установлен"
fi

# --- 3. FFmpeg ---
if ! command -v ffmpeg &>/dev/null; then
    echo -e "${YELLOW}[3/5]${NC} Устанавливаю FFmpeg..."
    brew install ffmpeg
else
    echo -e "${GREEN}[3/5]${NC} FFmpeg уже установлен"
fi

# --- 4. Python dependencies ---
echo -e "${YELLOW}[4/5]${NC} Устанавливаю зависимости Python..."

# Create venv if not exists
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip -q

# Install dependencies
pip install -q eel gevent requests python-docx openai-whisper torch

echo -e "${GREEN}[4/5]${NC} Зависимости установлены"

# --- 5. Create desktop shortcut ---
echo -e "${YELLOW}[5/5]${NC} Создаю ярлык..."

DESKTOP=~/Desktop
APP_NAME="Stocky non Stop"
LAUNCHER="$DESKTOP/$APP_NAME.command"

cat > "$LAUNCHER" << LAUNCHER_EOF
#!/bin/bash
cd "$SCRIPT_DIR"
source .venv/bin/activate
python3 main.py
LAUNCHER_EOF
chmod +x "$LAUNCHER"

echo -e "${GREEN}[5/5]${NC} Ярлык создан на Рабочем столе"

# --- Done ---
echo ""
echo "=========================================="
echo -e "  ${GREEN}Установка завершена!${NC}"
echo "=========================================="
echo ""
echo "  Приложение запущено."
echo "  Для повторного запуска дважды кликните:"
echo "  \"Stocky non Stop\" на Рабочем столе"
echo ""

# --- Launch ---
source .venv/bin/activate
python3 main.py
