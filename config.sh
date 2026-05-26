#!/bin/bash
# ============================================================
#  Stocky non Stop — Конфиг обновлений
#  ИЗМЕНИТЬ ТОЛЬКО GITHUB_REPO — остальное вычисляется автоматом
# ============================================================

# === ЕДИНСТВЕННАЯ НАСТРОЙКА ===
# Формат: "имя-пользователя/имя-репозитория"
# Пример: "inomix/stocky-nonstop"
GITHUB_REPO="xstixx1-alt/Port_MAC"

# === Вычисляется автоматом — не трогать ===
GITHUB_API="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"
GITHUB_RAW="https://raw.githubusercontent.com/${GITHUB_REPO}/main/version.json"
APP_NAME="StockyNonStop"
INSTALL_DIR="$HOME/Applications/${APP_NAME}"
DESKTOP_SHORTCUT="$HOME/Desktop/${APP_NAME}.command"
VERSION_FILE="${INSTALL_DIR}/version.txt"
