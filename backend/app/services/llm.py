import httpx
from .. import config

def available() -> bool:
    return bool(config.GEMINI_API_KEY or config.LLM_API_KEY)

def _gemini(system: str, user: str, max_tokens: int):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    r = httpx.post(url, timeout=40, headers={"x-goog-api-key": config.GEMINI_API_KEY, "content-type": "application/json"},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}],
              "generationConfig": {"maxOutputTokens": max(max_tokens, 800), "temperature": 0.2}})
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def _anthropic(system: str, user: str, max_tokens: int):
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=30,
        headers={"x-api-key": config.LLM_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": config.LLM_MODEL, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]})
    r.raise_for_status()
    return r.json()["content"][0]["text"]

def complete(system: str, user: str, max_tokens: int = 600):
    try:
        if config.GEMINI_API_KEY: return _gemini(system, user, max_tokens)
        if config.LLM_API_KEY: return _anthropic(system, user, max_tokens)
    except Exception as e:
        print("[LLM ERROR]", e)
    return None