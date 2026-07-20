"""
Единая точка доступа к LLM через CometAPI.

Env:
  COMETAPI_KEY          — основной ключ (приоритет)
  COMETAPI_BASE_URL     — default https://api.cometapi.com
  COMETAPI_MODEL_CHAT   — claude-sonnet-5 (бот + ассистент)
  COMETAPI_MODEL_FAST   — claude-haiku-4-5-20251001 (парсинг JSON, дёшево)
  COMETAPI_MODEL_VISION — gpt-4o-mini (скриншоты сигналов)
"""

from __future__ import annotations

import os

import anthropic
import httpx

COMETAPI_KEY = os.getenv("COMETAPI_KEY", "").strip()
COMETAPI_BASE = (
    os.getenv("COMETAPI_BASE_URL") or os.getenv("CLAUDE_BASE_URL") or "https://api.cometapi.com"
).strip().rstrip("/")
COMETAPI_OPENAI_URL = f"{COMETAPI_BASE}/v1/chat/completions"

# Legacy fallback (если CometAPI не задан)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


def api_key() -> str:
    return COMETAPI_KEY or ANTHROPIC_API_KEY or GROQ_API_KEY or OPENAI_API_KEY


def configured() -> bool:
    return bool(api_key())


def openai_chat_url() -> str:
    if COMETAPI_KEY:
        return COMETAPI_OPENAI_URL
    if GROQ_API_KEY:
        return "https://api.groq.com/openai/v1/chat/completions"
    return "https://api.openai.com/v1/chat/completions"


def openai_auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
    }


def _default_chat_model() -> str:
    if COMETAPI_KEY:
        return "claude-sonnet-5"
    if GROQ_API_KEY:
        return "llama-3.3-70b-versatile"
    return "gpt-4o-mini"


def _default_fast_model() -> str:
    if COMETAPI_KEY:
        return "claude-haiku-4-5-20251001"
    if GROQ_API_KEY:
        return "llama-3.3-70b-versatile"
    return "gpt-4o-mini"


def _default_vision_model() -> str:
    if COMETAPI_KEY:
        return "gpt-4o-mini"
    if GROQ_API_KEY:
        return "llama-3.2-90b-vision-preview"
    return "gpt-4o-mini"


MODEL_CHAT = (os.getenv("COMETAPI_MODEL_CHAT") or os.getenv("AI_MODEL") or _default_chat_model()).strip()
MODEL_FAST = (os.getenv("COMETAPI_MODEL_FAST") or os.getenv("AI_MODEL_CHAT") or _default_fast_model()).strip()
MODEL_VISION = (os.getenv("COMETAPI_MODEL_VISION") or _default_vision_model()).strip()
# Telegram-бот: haiku в ~10x дешевле sonnet — для коротких реплик хватает
MODEL_CHAT_ENGAGE = (
    os.getenv("COMETAPI_MODEL_CHAT_ENGAGE") or MODEL_FAST
).strip()
CLAUDE_MODEL = (os.getenv("CLAUDE_MODEL") or MODEL_CHAT).strip()


def claude_api_key() -> str:
    return COMETAPI_KEY or ANTHROPIC_API_KEY


def claude_base_url() -> str | None:
    if COMETAPI_KEY:
        return COMETAPI_BASE
    custom = (os.getenv("CLAUDE_BASE_URL") or "").strip()
    return custom or None


def async_claude_client(*, max_retries: int = 2) -> anthropic.AsyncAnthropic:
    key = claude_api_key()
    kwargs: dict = {"api_key": key, "max_retries": max_retries}
    base = claude_base_url()
    if base:
        kwargs["base_url"] = base
    return anthropic.AsyncAnthropic(**kwargs)


async def openai_chat_completion(payload: dict, *, timeout: float = 30) -> dict:
    if not configured():
        raise RuntimeError("AI not configured (set COMETAPI_KEY)")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            openai_chat_url(),
            json=payload,
            headers=openai_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()
