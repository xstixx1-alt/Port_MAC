# Stocky non Stop

Программа для автоматизированной работы со стоковыми материалами (Pixabay, Pexels) и обработки видео.

## Автор

Программу разработал **Азат**.

### Контакты
- **Telegram:** @inomix
- **ВКонтакте:** @inomix
- **Email:** inomixx@gmail.com

## Установка

### Windows
1. Установить Python 3.10+
2. Установить FFmpeg и добавить в PATH
3. Установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Запустить:
   ```bash
   python main.py
   ```

### macOS
1. Двойной клик на `INSTALL_MAC.command` — всё установится автоматически
2. На рабочем столе появится ярлык "Stocky non Stop"
3. Для повторного запуска — двойной клик на ярлык

Ручная установка:
```bash
brew install ffmpeg python-tk
pip3 install -r requirements_mac.txt
./run_app_mac.sh
```

## Конфигурация

При первом запуске откройте настройки и введите API-ключи:
- **Pixabay API:** https://pixabay.com/api/docs/
- **Pexels API:** https://www.pexels.com/api/
- **DeepSeek API:** https://platform.deepseek.com/
- **ElevenLabs API:** https://elevenlabs.io/

---

© Азат @inomix почта inomixx@gmail.com. Все права на оригинальный код принадлежат автору.
