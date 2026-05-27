import os
import time
import requests
import docx
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading
import logging
from datetime import datetime
from urllib.parse import quote

from stocky_nonstop.ai_router import resolve_ai_settings

class DeepSeekLogger:
    def __init__(self, log_dir="logs"):
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"deepseek_{today}.log")
        
        self.logger = logging.getLogger("DeepSeekLogger")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid logging duplicates if re-instantiated
        if self.logger.handlers:
            self.logger.handlers.clear()
            
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        
    def log_request(self, system_prompt, user_message):
        sys_preview = (system_prompt[:50] + "...") if len(system_prompt) > 50 else system_prompt
        user_preview = (user_message[:50] + "...") if len(user_message) > 50 else user_message
        self.logger.info(f"REQUEST -> System: {sys_preview} | User: {user_preview}")
        
    def log_response(self, content, tokens_in, tokens_out):
        content_preview = (content[:100] + "...") if len(content) > 100 else content
        self.logger.info(f"RESPONSE <- Success. Tokens: IN={tokens_in}, OUT={tokens_out}. Content: {content_preview}")
        
    def log_error(self, error_msg):
        self.logger.error(f"ERROR <- {error_msg}")


class DeepSeekEngine:
    def __init__(self, api_key=None, model=None, base_url=None, requests_per_minute=60, provider=None):
        settings = resolve_ai_settings(api_key=api_key, provider=provider, model=model)
        self.provider = settings["provider"]
        self.api_key = settings["api_key"]
        self.model = settings["model"]
        self.base_url = (base_url or settings["base_url"]).rstrip('/')
        self.requests_per_minute = requests_per_minute
        self.logger = DeepSeekLogger()
        self._rate_limit_sem = threading.Semaphore(1)
        self._last_request_time = 0.0

    def _apply_rate_limit(self):
        delay = 60.0 / self.requests_per_minute if self.requests_per_minute > 0 else 0
        with self._rate_limit_sem:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < delay:
                time.sleep(delay - elapsed)
            self._last_request_time = time.time()

    def test_connection(self) -> bool:
        """Testing the configured AI provider key."""
        if not self.api_key:
            self.logger.log_error(f"{self.provider}: empty API key")
            return False
        try:
            self._apply_rate_limit()
            if self.provider == "gemini":
                response = requests.get(
                    f"{self.base_url}/models",
                    params={"key": self.api_key},
                    timeout=10
                )
            else:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                response = requests.get(f"{self.base_url}/models", headers=headers, timeout=10)
            if response.status_code == 200:
                return True
            else:
                self.logger.log_error(f"{self.provider} test failed with status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.logger.log_error(f"{self.provider} test exception: {str(e)}")
            return False
            
    def send_message(self, system_prompt, user_message, temperature=0.3, max_tokens=2000, response_format=None) -> dict:
        if self.provider == "gemini":
            return self._send_gemini_message(system_prompt, user_message, temperature, max_tokens, response_format)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if response_format:
            payload["response_format"] = response_format

        self.logger.log_request(system_prompt, user_message)

        max_attempts = 3
        backoff_times = [2, 4, 8]
        
        for attempt in range(max_attempts):
            self._apply_rate_limit()
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                status = response.status_code
                if status == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    tokens_in = usage.get("prompt_tokens", 0)
                    tokens_out = usage.get("completion_tokens", 0)
                    
                    self.logger.log_response(content, tokens_in, tokens_out)
                    
                    return {
                        "success": True,
                        "content": content,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "error": None
                    }
                    
                # Handling status codes according to retry logic criteria
                if status in [401, 400]:
                    error_msg = f"HTTP {status}: {response.text}"
                    self.logger.log_error(error_msg)
                    return {"success": False, "error": error_msg}
                elif status in [429, 500, 502, 503]:
                    error_msg = f"HTTP {status}: {response.text}"
                    self.logger.log_error(f"Attempt {attempt + 1}/{max_attempts} failed: {error_msg}")
                    if attempt < max_attempts - 1:
                        time.sleep(backoff_times[attempt])
                        continue
                    else:
                        return {"success": False, "error": error_msg}
                else:
                    error_msg = f"HTTP {status}: {response.text}"
                    self.logger.log_error(error_msg)
                    return {"success": False, "error": error_msg}
                    
            except requests.exceptions.RequestException as e:
                error_msg = f"Network error: {str(e)}"
                self.logger.log_error(f"Attempt {attempt + 1}/{max_attempts} failed: {error_msg}")
                if attempt < max_attempts - 1:
                    time.sleep(backoff_times[attempt])
                    continue
                else:
                    return {"success": False, "error": error_msg}
            except Exception as e:
                error_msg = f"Unknown error: {str(e)}"
                self.logger.log_error(error_msg)
                return {"success": False, "error": error_msg}

        return {"success": False, "error": "Maximum retries exceeded."}

    def _send_gemini_message(self, system_prompt, user_message, temperature=0.3, max_tokens=2000, response_format=None) -> dict:
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt or "You are a helpful assistant."}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_message}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        if response_format and response_format.get("type") == "json_object":
            payload["generationConfig"]["responseMimeType"] = "application/json"

        self.logger.log_request(system_prompt, user_message)

        max_attempts = 3
        backoff_times = [2, 4, 8]
        model_path = quote(self.model, safe="")

        for attempt in range(max_attempts):
            self._apply_rate_limit()
            try:
                response = requests.post(
                    f"{self.base_url}/models/{model_path}:generateContent",
                    params={"key": self.api_key},
                    json=payload,
                    timeout=30
                )

                status = response.status_code
                if status == 200:
                    data = response.json()
                    parts = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                    content = "\n".join([p.get("text", "") for p in parts if p.get("text")])
                    usage = data.get("usageMetadata", {})
                    tokens_in = usage.get("promptTokenCount", 0)
                    tokens_out = usage.get("candidatesTokenCount", 0)
                    self.logger.log_response(content, tokens_in, tokens_out)
                    return {
                        "success": True,
                        "content": content,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "error": None
                    }

                error_msg = f"HTTP {status}: {response.text}"
                self.logger.log_error(f"Gemini attempt {attempt + 1}/{max_attempts} failed: {error_msg}")
                if status in [429, 500, 502, 503] and attempt < max_attempts - 1:
                    time.sleep(backoff_times[attempt])
                    continue
                return {"success": False, "error": error_msg}

            except requests.exceptions.RequestException as e:
                error_msg = f"Network error: {str(e)}"
                self.logger.log_error(f"Gemini attempt {attempt + 1}/{max_attempts} failed: {error_msg}")
                if attempt < max_attempts - 1:
                    time.sleep(backoff_times[attempt])
                    continue
                return {"success": False, "error": error_msg}
            except Exception as e:
                error_msg = f"Unknown error: {str(e)}"
                self.logger.log_error(error_msg)
                return {"success": False, "error": error_msg}

        return {"success": False, "error": "Maximum retries exceeded."}

    def send_messages_parallel(self, requests_list, max_workers=5, progress_callback=None) -> list:
        total = len(requests_list)
        results = [None] * total
        done = 0
        done_lock = threading.Lock()

        def worker(index, req):
            nonlocal done
            res = self.send_message(
                system_prompt=req.get("system", ""),
                user_message=req.get("user", "")
            )
            # Attach source item ID to the response dictionary 
            res["id"] = req.get("id")
            
            with done_lock:
                results[index] = res
                done += 1
                if progress_callback:
                    try:
                        progress_callback(done, total, req.get("id"))
                    except Exception as e:
                        self.logger.log_error(f"Error in progress callback: {str(e)}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, req in enumerate(requests_list):
                futures.append(executor.submit(worker, i, req))
            
            concurrent.futures.wait(futures)
            
        return results

    def load_system_prompt_from_file(self, path) -> str:
        try:
            ext = os.path.splitext(str(path))[1].lower()
            if ext == ".docx":
                doc = docx.Document(path)
                full_text = [para.text for para in doc.paragraphs]
                return "\n".join(full_text)

            if ext in (".txt", ".md", ""):
                for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
                    try:
                        with open(path, "r", encoding=enc) as f:
                            return f.read()
                    except UnicodeDecodeError:
                        continue
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()

            self.logger.log_error(f"Unsupported system prompt format: '{path}'")
            return ""
        except Exception as e:
            self.logger.log_error(f"Failed to load system prompt from '{path}': {str(e)}")
            return ""

    def load_system_prompt_from_docx(self, docx_path) -> str:
        return self.load_system_prompt_from_file(docx_path)

    def estimate_tokens(self, text) -> int:
        if not text:
            return 0
        return len(str(text)) // 3

if __name__ == "__main__":
    import sys
    
    # Provide simple formatting for test outputs
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    
    if not API_KEY:
        print("INFO: Skipping tests. Set DEEPSEEK_API_KEY env var to run tests.")
        # Alternatively, user can manually set it here for local testing.
        sys.exit(0)
        
    print("=== Testing DeepSeekEngine ===")
    engine = DeepSeekEngine(api_key=API_KEY)
    
    print("\n1. Testing connection...")
    is_connected = engine.test_connection()
    print(f"Connection test result: {is_connected}")
    
    if not is_connected:
        print("Cannot proceed with tests without connection.")
        sys.exit(1)
        
    print("\n2. Testing single request...")
    res = engine.send_message("You are a helpful assistant.", "What is 2+2? Answer briefly.")
    print("Single request result:", res)
    
    print("\n3. Testing parallel requests (3 workers, 5 requests)...")
    req_list = [
        {"system": "You are a math genius.", "user": f"What is {i}+{i}? Answer in number only.", "id": f"q_{i}"}
        for i in range(1, 6)
    ]
    
    def on_progress(d, t, c_id):
        print(f"Progress: {d}/{t} completed (Last completed ID: {c_id})")
        
    start_time = time.time()
    results = engine.send_messages_parallel(req_list, max_workers=3, progress_callback=on_progress)
    elapsed = time.time() - start_time
    
    print(f"\nParallel test completed in {elapsed:.2f} seconds.")
    for r in results:
        success_str = "SUCCESS" if r.get("success") else "FAILED"
        print(f"ID={r.get('id')} | {success_str} | Content='{r.get('content')}' | In={r.get('tokens_in')} Out={r.get('tokens_out')}")
