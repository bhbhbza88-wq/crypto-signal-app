"""
Единая точка доступа к LLM.

Бюджетный режим (рекомендуется):
  GROQ_API_KEY       — AI «Ник» на сайте (бесплатный tier)
  ANTHROPIC_API_KEY  — парсинг сигналов / vision (Haiku 4.5, дёшево)

Опционально:
  COMETAPI_KEY       — прокси Claude (если нет прямого Anthropic)
  OLLAMA_URL         — локальный chat_engage
  INGEST_VISION      — 0/1, читать скрины сигналов (дорого по токенам)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parent.parent
_backend = Path(__file__).resolve().parent
load_dotenv(_root / ".env")
load_dotenv(_backend / ".env")

import anthropic
import httpx

COMETAPI_KEY = os.getenv("COMETAPI_KEY", "").strip()
COMETAPI_BASE = (
    os.getenv("COMETAPI_BASE_URL") or os.getenv("CLAUDE_BASE_URL") or "https://api.cometapi.com"
).strip().rstrip("/")
COMETAPI_OPENAI_URL = f"{COMETAPI_BASE}/v1/chat/completions"

OLLAMA_URL = os.getenv("OLLAMA_URL", "").strip().rstrip("/")
OLLAMA_MODEL_CHAT_ENGAGE = (
    os.getenv("OLLAMA_MODEL_CHAT_ENGAGE") or os.getenv("OLLAMA_MODEL") or "qwen2.5:7b"
).strip()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Vision по умолчанию выкл — скрины жрут токены; включить INGEST_VISION=1
INGEST_VISION = os.getenv("INGEST_VISION", "0").strip().lower() in ("1", "true", "yes", "on")

HAIKU_MODEL = "claude-haiku-4-5-20251001"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"


def claude_api_key() -> str:
    """Anthropic напрямую предпочтительнее CometAPI (у Comet часто 403/баланс)."""
    return ANTHROPIC_API_KEY or COMETAPI_KEY


def claude_base_url() -> str | None:
    if ANTHROPIC_API_KEY:
        return None  # официальный api.anthropic.com
    if COMETAPI_KEY:
        return COMETAPI_BASE
    custom = (os.getenv("CLAUDE_BASE_URL") or "").strip()
    return custom or None


def fast_configured() -> bool:
    """Парсинг сигналов (Haiku)."""
    return bool(claude_api_key())


def chat_configured() -> bool:
    """AI «Ник» на сайте — сначала Groq (бесплатно)."""
    return bool(GROQ_API_KEY or COMETAPI_KEY or OPENAI_API_KEY)


def configured() -> bool:
    """Хоть какой-то LLM доступен."""
    return fast_configured() or chat_configured()


def api_key() -> str:
    """Legacy: ключ «для чего угодно». Предпочитаем Groq для OpenAI-совместимых вызовов."""
    return GROQ_API_KEY or COMETAPI_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY


def openai_chat_url() -> str:
    """URL для веб-чата (Ник)."""
    if GROQ_API_KEY:
        return "https://api.groq.com/openai/v1/chat/completions"
    if COMETAPI_KEY:
        return COMETAPI_OPENAI_URL
    return "https://api.openai.com/v1/chat/completions"


def openai_auth_headers() -> dict[str, str]:
    if GROQ_API_KEY:
        key = GROQ_API_KEY
    elif COMETAPI_KEY:
        key = COMETAPI_KEY
    else:
        key = OPENAI_API_KEY
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _default_chat_model() -> str:
    if GROQ_API_KEY:
        return GROQ_CHAT_MODEL
    if COMETAPI_KEY:
        return "claude-sonnet-5"
    return "gpt-4o-mini"


def _default_fast_model() -> str:
    if claude_api_key():
        return HAIKU_MODEL
    if GROQ_API_KEY:
        return GROQ_CHAT_MODEL
    return "gpt-4o-mini"


def _default_vision_model() -> str:
    if claude_api_key():
        return HAIKU_MODEL  # Haiku 4.5 умеет vision
    if GROQ_API_KEY:
        return "llama-3.2-90b-vision-preview"
    return "gpt-4o-mini"


MODEL_CHAT = (os.getenv("COMETAPI_MODEL_CHAT") or os.getenv("AI_MODEL") or _default_chat_model()).strip()
MODEL_FAST = (
    os.getenv("ANTHROPIC_MODEL_FAST")
    or os.getenv("COMETAPI_MODEL_FAST")
    or os.getenv("AI_MODEL_CHAT")
    or _default_fast_model()
).strip()
MODEL_VISION = (os.getenv("COMETAPI_MODEL_VISION") or _default_vision_model()).strip()
MODEL_CHAT_ENGAGE = (os.getenv("COMETAPI_MODEL_CHAT_ENGAGE") or MODEL_FAST).strip()
CLAUDE_MODEL = (os.getenv("CLAUDE_MODEL") or MODEL_CHAT).strip()


def ollama_configured() -> bool:
    return bool(OLLAMA_URL)


def chat_engage_provider() -> str:
    if ollama_configured():
        return "ollama"
    if claude_api_key():
        return "anthropic"
    return ""


def chat_engage_configured() -> bool:
    return bool(chat_engage_provider())


def chat_engage_model() -> str:
    if ollama_configured():
        return OLLAMA_MODEL_CHAT_ENGAGE
    return MODEL_CHAT_ENGAGE


def async_claude_client(*, max_retries: int = 2) -> anthropic.AsyncAnthropic:
    key = claude_api_key()
    kwargs: dict = {"api_key": key, "max_retries": max_retries}
    base = claude_base_url()
    if base:
        kwargs["base_url"] = base
    return anthropic.AsyncAnthropic(**kwargs)


def _claude_text(resp) -> str:
    parts: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            parts.append(block.text)
        elif hasattr(block, "text") and getattr(block, "type", None) != "thinking":
            parts.append(block.text)
    return "\n".join(parts).strip()


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def parse_json_content(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty model response")
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


async def anthropic_completion(
    *,
    system: str,
    user_content,
    model: str | None = None,
    max_tokens: int = 200,
    temperature: float = 0.0,
    timeout: float = 30,
) -> str:
    """Прямой вызов Anthropic Messages API (Haiku для парсинга)."""
    if not claude_api_key():
        raise RuntimeError("Anthropic not configured (set ANTHROPIC_API_KEY)")
    client = async_claude_client(max_retries=1)
    # httpx timeout через клиент по умолчанию; timeout параметр — для единообразия API
    _ = timeout
    resp = await client.messages.create(
        model=model or MODEL_FAST,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return _claude_text(resp)


async def fast_json_completion(
    *,
    system: str,
    user_text: str,
    max_tokens: int = 180,
) -> dict:
    """Дешёвый JSON-парсинг через Haiku."""
    sys = system.rstrip() + "\n\nОтветь ТОЛЬКО валидным JSON-объектом. Без markdown и пояснений."
    raw = await anthropic_completion(
        system=sys,
        user_content=user_text,
        model=MODEL_FAST,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return parse_json_content(raw)


async def vision_json_completion(
    *,
    system: str,
    image_bytes: bytes,
    caption: str = "",
    max_tokens: int = 180,
    media_type: str = "image/jpeg",
    require_ingest_flag: bool = True,
) -> dict:
    """Vision через Haiku.
    require_ingest_flag=True — только если INGEST_VISION=1 (парсинг каналов).
    Для разбора графика пользователем передавайте require_ingest_flag=False.
    """
    import base64

    if require_ingest_flag and not INGEST_VISION:
        raise RuntimeError("INGEST_VISION=0")
    if not claude_api_key():
        raise RuntimeError("Anthropic not configured (set ANTHROPIC_API_KEY)")
    b64 = base64.b64encode(image_bytes).decode()
    user_content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        },
        {
            "type": "text",
            "text": (caption[:800] if caption.strip() else "Извлеки параметры сигнала со скриншота."),
        },
    ]
    sys = system.rstrip() + "\n\nОтветь ТОЛЬКО валидным JSON-объектом. Без markdown и пояснений."
    raw = await anthropic_completion(
        system=sys,
        user_content=user_content,
        model=MODEL_VISION,
        max_tokens=max_tokens,
        temperature=0.0,
        timeout=60,
    )
    return parse_json_content(raw)


async def openai_chat_completion(payload: dict, *, timeout: float = 30) -> dict:
    """OpenAI-совместимый чат — для «Ника» (Groq)."""
    if not chat_configured():
        raise RuntimeError("Chat AI not configured (set GROQ_API_KEY)")
    # Всегда подставляем модель чата, если вызывающий передал устаревшую
    body = dict(payload)
    body.setdefault("model", MODEL_CHAT)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            openai_chat_url(),
            json=body,
            headers=openai_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def ollama_chat_completion(payload: dict, *, timeout: float = 90) -> dict:
    if not ollama_configured():
        raise RuntimeError("Ollama not configured (set OLLAMA_URL)")
    url = f"{OLLAMA_URL}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def chat_engage_completion(
    *,
    system: str,
    user: str,
    max_tokens: int = 120,
    temperature: float = 0.9,
    timeout: float = 90,
) -> str | None:
    if ollama_configured():
        payload = {
            "model": OLLAMA_MODEL_CHAT_ENGAGE,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        data = await ollama_chat_completion(payload, timeout=timeout)
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        ) or None

    if not claude_api_key():
        return None

    return (
        await anthropic_completion(
            system=system,
            user_content=user,
            model=MODEL_CHAT_ENGAGE,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
    ) or None
