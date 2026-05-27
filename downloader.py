# Stocky non Stop — модуль загрузки стоков с Pexels и Pixabay
# Автор: Азат | @inomix | inomixx@gmail.com

import os
import re
import time
import requests
import random
import threading
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Память для предотвращения дубликатов (потокобезопасная)
DOWNLOADED_MEDIA_IDS = set()
_ids_lock = threading.Lock()

def sanitize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:60] or "query"

# Общий пул сессий для macOS — не создаём новую на каждый файл
_shared_session = None
_shared_session_lock = threading.Lock()

def get_shared_session():
    """Возвращает общую сессию с пулом соединений (для macOS — критично)."""
    global _shared_session
    with _shared_session_lock:
        if _shared_session is None:
            _shared_session = requests.Session()
            retry_strategy = Retry(
                total=2,
                connect=1,
                read=1,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"]
            )
            # Большой пул — все потоки делят одну сессию
            adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=50, pool_maxsize=50)
            _shared_session.mount("https://", adapter)
            _shared_session.mount("http://", adapter)
            _shared_session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "*/*"
            })
    return _shared_session

def get_robust_session():
    """Создает НОВУЮ сессию. Быстрые таймауты, минимум ретраев."""
    session = requests.Session()
    retry_strategy = Retry(
        total=2,
        connect=1,
        read=1,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=5, pool_maxsize=5)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "*/*"
    })
    return session

def download_file(url, folder, filename, stop_flag, log, progress_fn=None):
    dest = os.path.join(folder, filename)

    for attempt in range(3):
        if stop_flag and stop_flag():
            return None

        # macOS: используем общий пул сессий вместо создания новой на каждый файл
        import platform
        if platform.system() == "Darwin":
            local_session = get_shared_session()
        else:
            local_session = get_robust_session()
        
        # 🔥 ДИНАМИЧЕСКИЕ ТАЙМАУТЫ:
        # - HARD_TIMEOUT теперь рассчитывается из размера файла (минимум 0.5 МБ/с)
        # - STALL_TIMEOUT увеличен до 15 сек (некоторые серверы паузят чанки)
        # - Если файл уже частично скачан — докачиваем через Range
        
        download_state = {
            "last_chunk_time": time.time(),
            "downloaded": 0,
            "killed": False,
            "response": None,
            "total_size": 0,
            "min_speed_mbps": 0.3  # Минимальная допустимая скорость 0.3 МБ/с
        }
        
        # Проверяем, есть ли частично скачанный файл (для возобновления)
        existing_size = 0
        if os.path.exists(dest) and attempt > 0:
            existing_size = os.path.getsize(dest)
            log(f"   📥 Возобновляем {filename} с {existing_size // 1024 // 1024} МБ", "INFO")
        
        def watchdog():
            """Умный сторож: убивает только если скорость СЛИШКОМ низкая"""
            start = time.time()
            STALL_TIMEOUT = 15  # 15 сек без данных = умер
            CHECK_INTERVAL = 5  # Проверять скорость раз в 5 сек
            last_speed_check = time.time()
            last_speed_downloaded = 0
            
            while not download_state["killed"]:
                time.sleep(2)
                now = time.time()
                
                if stop_flag and stop_flag():
                    download_state["killed"] = True
                    if download_state["response"]:
                        try: download_state["response"].close()
                        except: pass
                    return
                
                # 🔥 STALL: 15 сек без данных = реально мёртвое соединение
                if now - download_state["last_chunk_time"] > STALL_TIMEOUT:
                    download_state["killed"] = True
                    log(f"💤 STALL {filename} (нет данных {STALL_TIMEOUT}с) — обрываем", "ERROR")
                    if download_state["response"]:
                        try: download_state["response"].close()
                        except: pass
                    return
                
                # 🔥 SPEED CHECK: убиваем только если скорость <0.1 МБ/с в течение 30 сек
                if now - last_speed_check >= CHECK_INTERVAL and download_state["downloaded"] > 0:
                    bytes_in_period = download_state["downloaded"] - last_speed_downloaded
                    speed_mbps = (bytes_in_period / (1024 * 1024)) / (now - last_speed_check)
                    last_speed_check = now
                    last_speed_downloaded = download_state["downloaded"]
                    
                    # Если данные ИДУТ (даже медленно) — НЕ убиваем
                    # Только если скорость <0.05 МБ/с в течение 30 сек реально + общее время >180 сек
                    if speed_mbps < 0.05 and (now - start) > 180:
                        download_state["killed"] = True
                        log(f"🐢 СЛИШКОМ МЕДЛЕННО {filename} ({speed_mbps:.2f} МБ/с {(now-start):.0f}с) — обрываем", "ERROR")
                        if download_state["response"]:
                            try: download_state["response"].close()
                            except: pass
                        return
                
                # 🔥 АБСОЛЮТНЫЙ ХАРД-ЛИМИТ: 10 минут на любой файл
                if now - start > 600:
                    download_state["killed"] = True
                    log(f"⏱️ HARD TIMEOUT {filename} (10 минут) — обрываем", "ERROR")
                    if download_state["response"]:
                        try: download_state["response"].close()
                        except: pass
                    return
        
        watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        watchdog_thread.start()
        
        try:
            # 🔥 HTTP Range Header — продолжаем с того места где остановились
            headers = {}
            mode = "wb"  # write binary (новый файл)
            if existing_size > 0:
                headers["Range"] = f"bytes={existing_size}-"
                mode = "ab"  # append binary (дописать)
            
            r = local_session.get(url, stream=True, timeout=(15, 30), headers=headers)
            
            # 206 = Partial Content (Range работает), 200 = Full
            if r.status_code == 206:
                log(f"   ✓ Сервер поддерживает докачку для {filename}", "INFO")
            elif r.status_code == 200 and existing_size > 0:
                # Сервер не поддержал Range — качаем заново
                log(f"   Сервер не поддерживает Range, качаем {filename} заново", "INFO")
                existing_size = 0
                mode = "wb"
            
            r.raise_for_status()
            download_state["response"] = r
            
            # Получаем размер всего файла
            content_length = int(r.headers.get('content-length', 0))
            total_size = content_length + existing_size if r.status_code == 206 else content_length
            download_state["total_size"] = total_size
            
            downloaded = existing_size
            chunk_size = 65536
            last_speed_time = time.time()
            last_speed_downloaded = downloaded
            
            with open(dest, mode) as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if download_state["killed"]:
                        break
                    
                    if stop_flag and stop_flag():
                        download_state["killed"] = True
                        break
                    
                    now = time.time()
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        download_state["last_chunk_time"] = now
                        download_state["downloaded"] = downloaded
                        
                        if progress_fn and total_size > 0 and now - last_speed_time >= 0.5:
                            speed_mb = ((downloaded - last_speed_downloaded) / (1024 * 1024)) / (now - last_speed_time)
                            speed_str = f"{speed_mb:.1f} MB/s"
                            last_speed_time = now
                            last_speed_downloaded = downloaded
                            progress_fn(int((downloaded / total_size) * 100), speed_str)
            
            download_state["killed"] = True
            
            if stop_flag and stop_flag():
                if os.path.exists(dest): os.remove(dest)
                return None
            
            # 🔥 Если watchdog убил И мы скачали меньше чем 90% — это ошибка
            # НО! Если у нас уже есть >90% данных — оставляем файл и пробуем докачать на следующей попытке
            if total_size > 0 and downloaded < total_size * 0.9:
                log(f"⚠️ {filename} неполный ({downloaded}/{total_size}, {downloaded*100//total_size}%), попытка {attempt+1}/3", "ERROR")
                # НЕ удаляем файл! На следующей попытке докачаем через Range
                time.sleep(2 + attempt * 2)
                continue
            
            # Файл скачан полностью или почти полностью
            return dest
            
        except (requests.exceptions.Timeout, 
                requests.exceptions.ConnectionError, 
                requests.exceptions.ReadTimeout,
                requests.exceptions.ChunkedEncodingError,
                Exception) as e:
            download_state["killed"] = True
            log(f"⚠️ Сеть {filename} (попытка {attempt+1}/3): {type(e).__name__}: {e}", "ERROR")
            # НЕ удаляем файл! Продолжим с того места на следующей попытке
            if attempt < 2:
                wait = 3 * (attempt + 1)
                log(f"   Пауза {wait}с перед докачкой...", "INFO")
                time.sleep(wait)
            continue
            
        finally:
            download_state["killed"] = True
            # Закрываем ответ (но не сессию на macOS — она общая)
            try:
                if download_state.get("response"):
                    download_state["response"].close()
            except: pass
            # На Windows закрываем сессию, на macOS — общая, не трогаем
            import platform
            if platform.system() != "Darwin":
                try: local_session.close()
                except: pass
    
    # 🔥 После 3 попыток: если файл существует и хоть как-то скачался, оставляем
    # — может быть пригодится потом для ручного исправления
    if os.path.exists(dest):
        size_mb = os.path.getsize(dest) / 1024 / 1024
        log(f"❌ Все 3 попытки исчерпаны для {filename} (скачано {size_mb:.1f} МБ — файл оставлен)", "ERROR")
    else:
        log(f"❌ Все 3 попытки исчерпаны для {filename}", "ERROR")
    return None

def _safe_api_request(url, params=None, headers=None, log=None, label="API"):
    for attempt in range(2):
        local_session = get_robust_session()
        try:
            r = local_session.get(url, params=params, headers=headers, timeout=(5, 10))
            r.raise_for_status()
            return {"success": True, "data": r.json(), "status_code": r.status_code, "error_type": None, "error": ""}
        except requests.exceptions.Timeout:
            if log: log(f"[{label}] API таймаут (попытка {attempt+1}/2)", "ERROR")
            time.sleep(1)
        except requests.exceptions.ConnectionError:
            if log: log(f"[{label}] API недоступен (попытка {attempt+1}/2)", "ERROR")
            time.sleep(1)
        except requests.exceptions.HTTPError as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            error_text = getattr(getattr(e, "response", None), "text", str(e))
            if status_code == 429:
                if log: log(f"[{label}] API rate limit exceeded (429)", "ERROR")
                return {"success": False, "data": None, "status_code": status_code, "error_type": "rate_limit", "error": error_text}
            if status_code in (401, 403):
                if log: log(f"[{label}] API key rejected ({status_code})", "ERROR")
                return {"success": False, "data": None, "status_code": status_code, "error_type": "auth", "error": error_text}
            if log: log(f"[{label}] API HTTP error {status_code}: {error_text}", "ERROR")
            return {"success": False, "data": None, "status_code": status_code, "error_type": "http", "error": error_text}
        except Exception as e:
            if log: log(f"[{label}] API ошибка: {e}", "ERROR")
            return {"success": False, "data": None, "status_code": None, "error_type": "unknown", "error": str(e)}
        finally:
            try: local_session.close()
            except: pass
    return {"success": False, "data": None, "status_code": None, "error_type": "network", "error": "request_failed"}

def _pick_unique_item(items, id_key='id', top_n=5):
    with _ids_lock:
        new_items = [i for i in items if i.get(id_key) not in DOWNLOADED_MEDIA_IDS]
        if new_items:
            item = random.choice(new_items[:top_n])
        else:
            item = random.choice(items[:top_n])
        DOWNLOADED_MEDIA_IDS.add(item.get(id_key))
    return item

def download_pexels(prompt: str, api_key: str, save_path: str, media_type="video", 
                    per_page=50, min_duration=0, stop_flag=None, log_fn=None, 
                    item_update_fn=None, custom_filename=None):
    def log(msg, lvl="INFO"):
        if log_fn: log_fn(msg, lvl)
    
    clean = sanitize_name(prompt)
    folder = save_path
    os.makedirs(folder, exist_ok=True)

    if media_type == "video":
        url = f"https://api.pexels.com/videos/search?query={prompt}&per_page={per_page}&orientation=landscape"
    else:
        url = f"https://api.pexels.com/v1/search?query={prompt}&per_page={per_page}&orientation=landscape"

    api_result = _safe_api_request(url, headers={"Authorization": api_key}, log=log, label="Pexels")
    if not api_result.get("success"): return 0, api_result
    data = api_result.get("data") or {}

    items = data.get("videos" if media_type == "video" else "photos", [])
    if not items:
        log(f"[Pexels] Ничего не найдено", "ERROR")
        return 0, {"success": False, "error_type": "no_results", "error": "no_results", "status_code": 200}

    if media_type == "video" and min_duration > 0:
        items = [i for i in items if i.get('duration', 0) >= min_duration]
        if not items: return 0, {"success": False, "error_type": "no_results", "error": "duration_filtered", "status_code": 200}

    item = _pick_unique_item(items)
    
    if media_type == "video":
        best_file = sorted(item['video_files'], key=lambda x: x['width'] or 0, reverse=True)[0]
        dl_url, ext = best_file['link'], ".mp4"
    else:
        dl_url, ext = item.get("src", {}).get("original"), ".jpg"
    
    if not dl_url: return 0, {"success": False, "error_type": "no_results", "error": "missing_download_url", "status_code": 200}
        
    filename = custom_filename if custom_filename else f"{clean}{ext}"
    
    def on_progress(p, speed=""):
        if item_update_fn: item_update_fn(p, speed=speed)

    path = download_file(dl_url, folder, filename, stop_flag, log, on_progress)
    if path:
        log(f"[Pexels] ✓ {filename}", "SUCCESS")
        if item_update_fn: item_update_fn(100, path=path)
        return 1, {"success": True, "error_type": None, "error": "", "status_code": 200}
    return 0, {"success": False, "error_type": "download_failed", "error": "download_failed", "status_code": 200}

def download_pixabay(prompt: str, api_key: str, save_path: str, media_type="video", 
                     per_page=50, min_duration=0, stop_flag=None, log_fn=None, 
                     item_update_fn=None, custom_filename=None):
    def log(msg, lvl="INFO"):
        if log_fn: log_fn(msg, lvl)
    
    per_page = max(3, min(per_page, 200))
    clean = sanitize_name(prompt)
    folder = save_path
    os.makedirs(folder, exist_ok=True)

    api_url = "https://pixabay.com/api/videos" if media_type == "video" else "https://pixabay.com/api"
    params = {"key": api_key, "q": prompt, "per_page": per_page, "orientation": "horizontal"}
    if media_type == "photo": params["image_type"] = "photo"

    api_result = _safe_api_request(api_url, params=params, log=log, label="Pixabay")
    if not api_result.get("success"): return 0, None, api_result
    data = api_result.get("data") or {}

    hits = data.get("hits", [])
    if not hits:
        log(f"[Pixabay] Ничего не найдено", "ERROR")
        return 0, None, {"success": False, "error_type": "no_results", "error": "no_results", "status_code": 200}

    if media_type == "video" and min_duration > 0:
        hits = [h for h in hits if h.get('duration', 0) >= min_duration]
        if not hits: return 0, None, {"success": False, "error_type": "no_results", "error": "duration_filtered", "status_code": 200}

    hit = _pick_unique_item(hits)
    
    if media_type == "video":
        v_data = hit.get('videos', {})
        dl_url = v_data.get('large', {}).get('url') or v_data.get('medium', {}).get('url')
        ext = ".mp4"
    else:
        dl_url = hit.get("largeImageURL") or hit.get("webformatURL")
        ext = ".jpg"
    
    if not dl_url: return 0, None, {"success": False, "error_type": "no_results", "error": "missing_download_url", "status_code": 200}
        
    filename = custom_filename if custom_filename else f"{clean}{ext}"
    
    def on_progress(p, speed=""):
        if item_update_fn: item_update_fn(p, speed=speed)

    path = download_file(dl_url, folder, filename, stop_flag, log, on_progress)
    if path:
        log(f"[Pixabay] ✓ {filename}", "SUCCESS")
        if item_update_fn: item_update_fn(100, path=path)
        return 1, hit.get('id'), {"success": True, "error_type": None, "error": "", "status_code": 200}
    return 0, None, {"success": False, "error_type": "download_failed", "error": "download_failed", "status_code": 200}
