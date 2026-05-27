import json
import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


AI_PROVIDER_DEFAULTS = {
    "deepseek": {
        "label": "DeepSeek",
        "key_field": "deepseek_api_key",
        "model_field": "deepseek_model",
        "default_model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ],
    },
    "openrouter": {
        "label": "OpenRouter",
        "key_field": "openrouter_api_key",
        "model_field": "openrouter_model",
        "default_model": "openai/gpt-5.4-nano",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "google/gemini-3.1-pro-preview",
            "google/gemini-3.1-flash-lite-preview",
            "openai/gpt-5.4-nano",
            "deepseek/deepseek-v4-flash",
        ],
    },
    "gemini": {
        "label": "Gemini",
        "key_field": "gemini_api_key",
        "model_field": "gemini_model",
        "default_model": "gemini-3.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [
            "gemini-3.1-pro-preview",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
        ],
    },
}


def load_ai_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_ai_config(updates):
    config = load_ai_config()
    config.update(updates or {})
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    return config


def normalize_provider(provider):
    selected = (provider or "deepseek").strip().lower()
    if selected not in AI_PROVIDER_DEFAULTS:
        return "deepseek"
    return selected


def resolve_ai_settings(api_key=None, provider=None, model=None):
    config = load_ai_config()
    selected_provider = normalize_provider(provider or config.get("ai_provider") or "deepseek")
    defaults = AI_PROVIDER_DEFAULTS[selected_provider]

    selected_model = (model or config.get(defaults["model_field"]) or defaults["default_model"]).strip()
    if not selected_model:
        selected_model = defaults["default_model"]

    selected_key = (api_key or config.get(defaults["key_field"]) or "").strip()

    return {
        "provider": selected_provider,
        "provider_label": defaults["label"],
        "api_key": selected_key,
        "model": selected_model,
        "base_url": defaults["base_url"],
        "key_field": defaults["key_field"],
        "model_field": defaults["model_field"],
        "default_model": defaults["default_model"],
        "models": list(defaults.get("models") or []),
    }


def persist_ai_selection(api_key=None, provider=None, model=None):
    settings = resolve_ai_settings(api_key=api_key, provider=provider, model=model)
    updates = {
        "ai_provider": settings["provider"],
        settings["key_field"]: settings["api_key"],
        settings["model_field"]: settings["model"],
    }
    save_ai_config(updates)
    return settings
