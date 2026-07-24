"""
Единая точка доступа к LLM.

Главный провайдер: OpenRouter (один ключ → много моделей).
  OPENROUTER_API_KEY     — основной ключ

Модели по сложности (переопределяются env):
  OPENROUTER_MODEL_FAST   — дешёвая: прочий быстрый JSON
  OPENROUTER_MODEL_INGEST — парсинг сигналов из TG-каналов (сильнее FAST)
  OPENROUTER_MODEL_CHAT   — средняя: AI «Ник» на сайте
  OPENROUTER_MODEL_VISION — vision: скрины сигналов TG + графики на сайте

Fallback (если OpenRouter нет):
  GROQ_API_KEY / ANTHROPIC_API_KEY / COMETAPI_KEY / OPENAI_API_KEY
  OLLAMA_URL — локальный chat_engage
  INGEST_VISION — 0/1, vision для TG-ingest (по умолчанию ВКЛ)
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

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE = (
    os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
).strip().rstrip("/")
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE}/chat/completions"

# Дешёвая / ingest / средняя / vision (OpenRouter slugs)
OR_FAST_DEFAULT = "google/gemini-2.5-flash-lite"
OR_INGEST_DEFAULT = "google/gemini-2.5-flash"  # умнее lite для разбора каналов
OR_CHAT_DEFAULT = "google/gemini-2.5-flash"
OR_VISION_DEFAULT = "google/gemini-2.5-flash"  # multimodal: скрины сигналов из каналов

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

INGEST_VISION = os.getenv("INGEST_VISION", "1").strip().lower() in ("1", "true", "yes", "on")

HAIKU_MODEL = "claude-haiku-4-5-20251001"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"


def openrouter_configured() -> bool:
    return bool(OPENROUTER_API_KEY)


def claude_api_key() -> str:
    return ANTHROPIC_API_KEY or COMETAPI_KEY


def claude_base_url() -> str | None:
    if ANTHROPIC_API_KEY:
        return None
    if COMETAPI_KEY:
        return COMETAPI_BASE
    custom = (os.getenv("CLAUDE_BASE_URL") or "").strip()
    return custom or None


def fast_configured() -> bool:
    """Парсинг сигналов / JSON."""
    return openrouter_configured() or bool(claude_api_key()) or bool(GROQ_API_KEY)


def chat_configured() -> bool:
    """AI «Ник» на сайте."""
    return openrouter_configured() or bool(GROQ_API_KEY or COMETAPI_KEY or OPENAI_API_KEY)


def configured() -> bool:
    return fast_configured() or chat_configured()


def api_key() -> str:
    return (
        OPENROUTER_API_KEY
        or GROQ_API_KEY
        or COMETAPI_KEY
        or ANTHROPIC_API_KEY
        or OPENAI_API_KEY
    )


def openai_chat_url() -> str:
    if openrouter_configured():
        return OPENROUTER_CHAT_URL
    if GROQ_API_KEY:
        return "https://api.groq.com/openai/v1/chat/completions"
    if COMETAPI_KEY:
        return COMETAPI_OPENAI_URL
    return "https://api.openai.com/v1/chat/completions"


def openai_auth_headers() -> dict[str, str]:
    if openrouter_configured():
        key = OPENROUTER_API_KEY
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # OpenRouter extras (рекомендуются в доке)
            "HTTP-Referer": os.getenv("FRONTEND_URL", "https://nowicki.trade"),
            "X-Title": "NOWICKI",
        }
        return headers
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
    if openrouter_configured():
        return OR_CHAT_DEFAULT
    if GROQ_API_KEY:
        return GROQ_CHAT_MODEL
    if COMETAPI_KEY:
        return "claude-sonnet-5"
    return "gpt-4o-mini"


def _default_fast_model() -> str:
    if openrouter_configured():
        return OR_FAST_DEFAULT
    if claude_api_key():
        return HAIKU_MODEL
    if GROQ_API_KEY:
        return GROQ_CHAT_MODEL
    return "gpt-4o-mini"


def _default_ingest_model() -> str:
    if openrouter_configured():
        return OR_INGEST_DEFAULT
    if claude_api_key():
        return HAIKU_MODEL
    if GROQ_API_KEY:
        return GROQ_CHAT_MODEL
    return "gpt-4o-mini"


def _default_vision_model() -> str:
    if openrouter_configured():
        return OR_VISION_DEFAULT
    if claude_api_key():
        return HAIKU_MODEL
    if GROQ_API_KEY:
        return "llama-3.2-90b-vision-preview"
    return "gpt-4o-mini"


MODEL_CHAT = (
    os.getenv("OPENROUTER_MODEL_CHAT")
    or os.getenv("COMETAPI_MODEL_CHAT")
    or os.getenv("AI_MODEL")
    or _default_chat_model()
).strip()
MODEL_FAST = (
    os.getenv("OPENROUTER_MODEL_FAST")
    or os.getenv("ANTHROPIC_MODEL_FAST")
    or os.getenv("COMETAPI_MODEL_FAST")
    or os.getenv("AI_MODEL_CHAT")
    or _default_fast_model()
).strip()
MODEL_INGEST = (
    os.getenv("OPENROUTER_MODEL_INGEST")
    or os.getenv("ANTHROPIC_MODEL_INGEST")
    or os.getenv("COMETAPI_MODEL_INGEST")
    or _default_ingest_model()
).strip()
MODEL_VISION = (
    os.getenv("OPENROUTER_MODEL_VISION")
    or os.getenv("COMETAPI_MODEL_VISION")
    or _default_vision_model()
).strip()
MODEL_CHAT_ENGAGE = (
    os.getenv("OPENROUTER_MODEL_ENGAGE")
    or os.getenv("COMETAPI_MODEL_CHAT_ENGAGE")
    or MODEL_FAST
).strip()
CLAUDE_MODEL = (os.getenv("CLAUDE_MODEL") or MODEL_CHAT).strip()


def ollama_configured() -> bool:
    return bool(OLLAMA_URL)


def chat_engage_provider() -> str:
    if ollama_configured():
        return "ollama"
    if openrouter_configured():
        return "openrouter"
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


async def openai_compatible_completion(
    *,
    model: str,
    messages: list[dict],
    max_tokens: int = 400,
    temperature: float = 0.0,
    timeout: float = 45,
    response_format: dict | None = None,
) -> str:
    """OpenRouter / Groq / Comet / OpenAI chat completions → текст ответа."""
    if not (openrouter_configured() or GROQ_API_KEY or COMETAPI_KEY or OPENAI_API_KEY):
        raise RuntimeError("AI not configured (set OPENROUTER_API_KEY)")
    body: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        body["response_format"] = response_format
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            openai_chat_url(),
            json=body,
            headers=openai_auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )


async def anthropic_completion(
    *,
    system: str,
    user_content,
    model: str | None = None,
    max_tokens: int = 200,
    temperature: float = 0.0,
    timeout: float = 30,
) -> str:
    if not claude_api_key():
        raise RuntimeError("Anthropic not configured (set ANTHROPIC_API_KEY)")
    client = async_claude_client(max_retries=1)
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
    model: str | None = None,
) -> dict:
    """Дешёвый JSON (парсинг сигналов и прочий structured output)."""
    sys = system.rstrip() + "\n\nОтветь ТОЛЬКО валидным JSON-объектом. Без markdown и пояснений."
    use_model = (model or MODEL_FAST).strip()

    if openrouter_configured() or (GROQ_API_KEY and not claude_api_key()):
        # OpenRouter (или Groq) — OpenAI-совместимый путь
        raw = await openai_compatible_completion(
            model=use_model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user_text},
            ],
            max_tokens=max_tokens,
            temperature=0.0,
            timeout=40,
        )
        return parse_json_content(raw)

    raw = await anthropic_completion(
        system=sys,
        user_content=user_text,
        model=use_model,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return parse_json_content(raw)


async def ingest_json_completion(
    *,
    system: str,
    user_text: str,
    max_tokens: int = 260,
) -> dict:
    """JSON-парсинг постов TG-каналов — более сильная MODEL_INGEST."""
    return await fast_json_completion(
        system=system,
        user_text=user_text,
        max_tokens=max_tokens,
        model=MODEL_INGEST,
    )


async def vision_json_completion(
    *,
    system: str,
    image_bytes: bytes,
    caption: str = "",
    max_tokens: int = 180,
    media_type: str = "image/jpeg",
    require_ingest_flag: bool = True,
) -> dict:
    """Vision JSON: OpenRouter (gpt-4o-mini) или Anthropic Haiku."""
    import base64

    if require_ingest_flag and not INGEST_VISION:
        raise RuntimeError("INGEST_VISION=0")

    image_bytes, media_type = normalize_image_bytes(image_bytes, media_type)
    b64 = base64.b64encode(image_bytes).decode()
    caption_text = (
        caption[:800].strip()
        if caption and caption.strip()
        else "Извлеки параметры сигнала со скриншота."
    )
    sys = (
        system.rstrip()
        + "\n\nCRITICAL: reply with a single JSON object only. No markdown fences, no prose."
    )

    last_err: Exception | None = None
    for attempt in range(2):
        hint = ""
        if attempt == 1:
            hint = (
                "\n\nPREVIOUS REPLY WAS INVALID. Return ONLY raw JSON matching the schema. "
                "bias must be exactly long|short|flat."
            )
        try:
            if openrouter_configured() or (not claude_api_key() and (GROQ_API_KEY or OPENAI_API_KEY)):
                if not (openrouter_configured() or OPENAI_API_KEY or GROQ_API_KEY or COMETAPI_KEY):
                    raise RuntimeError("No OpenAI-compatible vision provider")
                user_content = [
                    {"type": "text", "text": caption_text + hint},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64}"},
                    },
                ]
                raw = await openai_compatible_completion(
                    model=MODEL_VISION,
                    messages=[
                        {"role": "system", "content": sys},
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=max(max_tokens, 900),
                    temperature=0.0,
                    timeout=75,
                )
            else:
                user_content = [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": caption_text + hint},
                ]
                raw = await anthropic_completion(
                    system=sys,
                    user_content=user_content,
                    model=MODEL_VISION,
                    max_tokens=max(max_tokens, 900),
                    temperature=0.0,
                    timeout=75,
                )
            if not (raw or "").strip():
                raise ValueError("empty model response")
            return parse_json_content(raw)
        except Exception as e:
            last_err = e
            print(f"[ai_client] vision_json attempt {attempt + 1} failed: {e}")
    raise last_err or RuntimeError("vision_json failed")


def normalize_image_bytes(image_bytes: bytes, media_type: str = "image/jpeg") -> tuple[bytes, str]:
    from io import BytesIO

    try:
        from PIL import Image
    except Exception:
        return image_bytes, media_type or "image/jpeg"

    try:
        im = Image.open(BytesIO(image_bytes))
        im.load()
        if im.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", im.size, (0, 0, 0))
            if im.mode == "P":
                im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1] if im.mode in ("RGBA", "LA") else None)
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        max_edge = 1400
        w, h = im.size
        scale = min(1.0, max_edge / max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        out = BytesIO()
        im.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[ai_client] normalize_image skip: {e}")
        mt = (media_type or "image/jpeg").lower()
        if mt in ("image/jpg", "image/heic", "image/heif"):
            mt = "image/jpeg"
        return image_bytes, mt


async def openai_chat_completion(payload: dict, *, timeout: float = 30) -> dict:
    """OpenAI-совместимый чат — для «Ника» (OpenRouter → …)."""
    if not chat_configured():
        raise RuntimeError("Chat AI not configured (set OPENROUTER_API_KEY)")
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

    if openrouter_configured():
        return (
            await openai_compatible_completion(
                model=MODEL_CHAT_ENGAGE,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )
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
