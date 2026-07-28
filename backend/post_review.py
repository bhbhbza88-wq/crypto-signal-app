"""
Критика постов market_outlook — баги, несостыковки, стиль.

Модели:
  fast → google/gemini-2.5-flash
  deep → google/gemini-3.1-pro-preview (текст + график)

Запуск:
  py backend/post_review.py --mode fast --hours 24
  py backend/post_review.py --mode deep --hours 12 --model gemini
  py backend/post_review.py --auto
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import database as db

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).resolve()
OUT_DIR = DATA_DIR / "post_reviews"
CHARTS_DIR = DATA_DIR / "charts"
_SETTING_RECENT = "outlook_recent_posts"
_SETTING_LAST_REVIEW = "outlook_last_post_review_ts"

ENABLED = (os.getenv("POST_REVIEW_ENABLED", "1") or "1").strip().lower() in (
    "1", "true", "yes", "on",
)
FAST_INTERVAL_H = float(os.getenv("POST_REVIEW_FAST_INTERVAL_H", "6") or "6")
DEEP_INTERVAL_H = float(os.getenv("POST_REVIEW_DEEP_INTERVAL_H", "24") or "24")

MODEL_FAST = (os.getenv("POST_REVIEW_MODEL_FAST") or "google/gemini-2.5-flash").strip()
MODEL_DEEP_GEMINI = (
    os.getenv("POST_REVIEW_MODEL_DEEP") or "google/gemini-3.1-pro-preview"
).strip()
MODEL_DEEP_CLAUDE = "anthropic/claude-sonnet-4.5"
MODEL_DEEP_GPT = "openai/gpt-5.5-pro"

ReviewMode = Literal["fast", "deep"]
DeepModel = Literal["gemini", "claude", "gpt"]

FAST_REVIEW_PROMPT = """
Ты редактор крипто-канала. Проверь недавние посты на БАГИ и НЕСОСТЫКОВКИ.

Что искать:
1. Противоречия цены (post vs context_price / close).
2. Логические несостыковки (bias vs цели, SMC-термины вразрез с выводом).
3. AI-штампы: «важно отметить», «следовательно», «таким образом».
4. Дубли / одинаковые шаблоны.
5. Обещания без hedge: «точно», «гарантирую».

Верни СТРОГО JSON без markdown:
{{
  "ok": true,
  "score_1_10": 8,
  "summary": "1-2 предложения",
  "critical_issues": [{{"post_index": 0, "issue": "...", "severity": "high"}}],
  "style_warnings": [{{"phrase": "...", "count": 1, "advice": "..."}}],
  "duplicates": [],
  "recommendations": ["..."]
}}

Посты:
{posts_json}
"""

DEEP_REVIEW_PROMPT = """
Ты опытный трейдер и редактор. Глубокий разбор постов market outlook (стиль Букваръ / SMC).

Ищи скрытые проблемы доверия: логика прогноза, инвалидация, стиль (AI smell),
честность update-постов, согласованность текста с графиком (если картинка приложена).

Верни СТРОГО JSON без markdown:
{{
  "score_1_10": 7,
  "overall_verdict": "2-3 предложения",
  "trust_level": "high|medium|low",
  "ai_smell_score": 3,
  "issues_by_post": [
    {{"post_index": 0, "ticker": "BTC", "issues": ["..."], "rewrite_suggestion": "..."}}
  ],
  "systemic_problems": ["..."],
  "prompt_improvements": ["..."],
  "good_examples": [{{"post_index": 0, "why_good": "..."}}]
}}

Посты:
{posts_json}
"""


def is_configured() -> bool:
    return ENABLED


def save_chart_png(symbol: str, png: bytes | None) -> str | None:
    """Сохранить график на диск для multimodal review. Возвращает путь."""
    if not png:
        return None
    try:
        CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]+", "_", (symbol or "UNK").replace("/", ""))
        path = CHARTS_DIR / f"{safe}_latest.png"
        path.write_bytes(png)
        return str(path)
    except Exception as e:
        print(f"[post_review] save chart fail: {e}", flush=True)
        return None


def _fetch_recent_posts(hours: float = 48.0) -> list[dict[str, Any]]:
    """Посты из settings.outlook_recent_posts (body сохраняется при publish)."""
    try:
        raw = db.get_setting(_SETTING_RECENT, "{}") or "{}"
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []

    cutoff = time.time() - max(1.0, hours) * 3600
    posts: list[dict[str, Any]] = []
    for sym, meta in data.items():
        if not isinstance(meta, dict):
            continue
        ts = float(meta.get("ts") or 0)
        if ts < cutoff:
            continue
        body = (meta.get("body") or "").strip()
        if not body:
            continue
        safe = re.sub(r"[^\w.-]+", "_", str(sym).replace("/", ""))
        chart_path = CHARTS_DIR / f"{safe}_latest.png"
        posts.append(
            {
                "symbol": str(sym),
                "created_at": ts,
                "bias": meta.get("bias"),
                "close": meta.get("close"),
                "context_price": meta.get("close"),
                "key_level": meta.get("key_level"),
                "target": meta.get("target"),
                "post_type": meta.get("post_type") or "analysis",
                "body": body[:600],
                "message_id": meta.get("message_id"),
                "chart_path": str(chart_path) if chart_path.exists() else None,
            }
        )
    posts.sort(key=lambda x: float(x["created_at"]), reverse=True)
    return posts


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Gemini иногда кладёт JSON после reasoning/thinking блока
    for candidate in (text,):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # Последний JSON-объект в тексте (часто после preamble)
    matches = list(re.finditer(r"\{[\s\S]*\}", text))
    for m in reversed(matches):
        chunk = m.group(0)
        # усечь до сбалансированных скобок
        depth = 0
        end = None
        for i, ch in enumerate(chunk):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end:
            chunk = chunk[:end]
        try:
            data = json.loads(chunk)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    print(f"[post_review] parse_error raw[:800]={text[:800]!r}", flush=True)
    return {
        "parse_error": True,
        "raw": (raw or "")[:3000],
        "summary": "не удалось распарсить ответ модели",
        "overall_verdict": "не удалось распарсить ответ модели",
        "score_1_10": None,
    }


async def _call_llm(
    *,
    model: str,
    messages: list[dict],
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> str:
    import ai_client

    return await ai_client.openai_compatible_completion(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=90,
    )


async def analyze_fast(posts: list[dict[str, Any]]) -> dict[str, Any]:
    if not posts:
        return {
            "ok": True,
            "score_1_10": 0,
            "summary": "нет постов за период",
            "critical_issues": [],
            "style_warnings": [],
            "duplicates": [],
            "recommendations": [],
        }
    payload = [
        {
            "index": i,
            "symbol": p["symbol"],
            "post_type": p.get("post_type"),
            "body": p.get("body"),
            "bias": p.get("bias"),
            "context_price": p.get("context_price") or p.get("close"),
            "key_level": p.get("key_level"),
            "target": p.get("target"),
        }
        for i, p in enumerate(posts[:30])
    ]
    prompt = FAST_REVIEW_PROMPT.format(
        posts_json=json.dumps(payload, ensure_ascii=False, indent=2)
    )
    raw = await _call_llm(
        model=MODEL_FAST,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.25,
    )
    parsed = _parse_json_object(raw)
    parsed["model_used"] = MODEL_FAST
    parsed["ai"] = True
    return parsed


async def analyze_deep(
    posts: list[dict[str, Any]], model_hint: DeepModel = "gemini"
) -> dict[str, Any]:
    if not posts:
        return {
            "score_1_10": 0,
            "overall_verdict": "нет постов за период",
            "trust_level": "unknown",
            "ai_smell_score": None,
            "issues_by_post": [],
            "systemic_problems": [],
            "prompt_improvements": [],
            "good_examples": [],
        }

    model_map = {
        "gemini": MODEL_DEEP_GEMINI,
        "claude": MODEL_DEEP_CLAUDE,
        "gpt": MODEL_DEEP_GPT,
    }
    model = model_map.get(model_hint, MODEL_DEEP_GEMINI)

    payload = [
        {
            "index": i,
            "symbol": p["symbol"],
            "post_type": p.get("post_type"),
            "body": p.get("body"),
            "bias": p.get("bias"),
            "context_price": p.get("context_price") or p.get("close"),
            "key_level": p.get("key_level"),
            "target": p.get("target"),
            "has_chart": bool(p.get("chart_path")),
        }
        for i, p in enumerate(posts[:20])
    ]
    prompt = DEEP_REVIEW_PROMPT.format(
        posts_json=json.dumps(payload, ensure_ascii=False, indent=2)
    )

    # Multimodal: Gemini + charts
    content: Any = prompt
    if model_hint == "gemini":
        parts: list[dict] = [{"type": "text", "text": prompt}]
        attached = 0
        for p in posts[:5]:
            chart_path = p.get("chart_path")
            if not chart_path or not Path(chart_path).exists():
                continue
            try:
                img = Path(chart_path).read_bytes()
                b64 = base64.b64encode(img).decode("ascii")
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
                attached += 1
            except Exception:
                continue
        if attached:
            content = parts
            print(f"[post_review] multimodal: {attached} charts attached", flush=True)

    raw = await _call_llm(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=2500,
        temperature=0.3,
    )
    parsed = _parse_json_object(raw)
    parsed["model_used"] = model
    parsed["ai"] = True
    return parsed


def format_report_md(
    mode: ReviewMode, posts: list[dict[str, Any]], review: dict[str, Any]
) -> str:
    lines = [
        f"# Post Review ({mode.upper()}) — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Model:** {review.get('model_used', '—')}",
        f"**Posts:** {len(posts)}",
    ]
    if mode == "fast":
        lines += [
            f"**Score:** {review.get('score_1_10', '—')}/10",
            f"**OK:** {review.get('ok')}",
            f"**Summary:** {review.get('summary', '')}",
            "",
            "## Critical Issues",
        ]
        for issue in review.get("critical_issues") or []:
            if isinstance(issue, dict):
                lines.append(
                    f"- Post {issue.get('post_index')}: {issue.get('issue')} "
                    f"[{issue.get('severity')}]"
                )
            else:
                lines.append(f"- {issue}")
        lines += ["", "## Recommendations"]
        for rec in review.get("recommendations") or []:
            lines.append(f"- {rec}")
    else:
        lines += [
            f"**Score:** {review.get('score_1_10', '—')}/10",
            f"**Trust:** {review.get('trust_level')}",
            f"**AI smell:** {review.get('ai_smell_score')}/10",
            f"**Verdict:** {review.get('overall_verdict', '')}",
            "",
            "## Systemic Problems",
        ]
        for p in review.get("systemic_problems") or []:
            lines.append(f"- {p}")
        lines += ["", "## Prompt Improvements"]
        for p in review.get("prompt_improvements") or []:
            lines.append(f"- {p}")

    lines += ["", "## Sample Posts"]
    for i, p in enumerate(posts[:8]):
        lines.append(
            f"- `{i}` {p.get('symbol')} ({p.get('post_type')}): {p.get('body', '')[:220]}"
        )
    return "\n".join(lines) + "\n"


def save_report(
    mode: ReviewMode,
    posts: list[dict[str, Any]],
    review: dict[str, Any],
    model_hint: str = "",
) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = f"_{model_hint}" if model_hint else ""
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "model_hint": model_hint,
        "posts_count": len(posts),
        "posts": posts,
        "review": review,
    }
    json_path = OUT_DIR / f"review_{mode}{suffix}_{stamp}.json"
    md_path = OUT_DIR / f"review_{mode}{suffix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = format_report_md(mode, posts, review)
    md_path.write_text(md, encoding="utf-8")
    (OUT_DIR / f"latest_{mode}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / f"latest_{mode}.md").write_text(md, encoding="utf-8")
    return json_path, md_path


def short_telegram_summary(mode: ReviewMode, review: dict[str, Any], n: int) -> str:
    if mode == "fast":
        issues = review.get("critical_issues") or []
        lines = [
            f"📝 Post review FAST · score {review.get('score_1_10', '—')}/10 · n={n}",
            str(review.get("summary") or ""),
            "",
            "Issues:",
        ]
        for x in issues[:5]:
            if isinstance(x, dict):
                lines.append(f"• {x.get('issue')}")
            else:
                lines.append(f"• {x}")
        for x in (review.get("recommendations") or [])[:3]:
            lines.append(f"→ {x}")
        return "\n".join(lines)[:3500]

    lines = [
        f"📝 Post review DEEP · score {review.get('score_1_10', '—')}/10 · n={n}",
        f"Trust: {review.get('trust_level')} · AI smell: {review.get('ai_smell_score')}",
        str(review.get("overall_verdict") or ""),
        "",
        "Systemic:",
    ]
    for x in (review.get("systemic_problems") or [])[:5]:
        lines.append(f"• {x}")
    for x in (review.get("prompt_improvements") or [])[:4]:
        lines.append(f"→ {x}")
    return "\n".join(lines)[:3500]


async def run_review(
    mode: ReviewMode = "fast",
    hours: float = 48.0,
    model_hint: DeepModel = "gemini",
    notify: bool = True,
) -> dict[str, Any]:
    posts = _fetch_recent_posts(hours)
    print(f"[post_review] mode={mode} posts={len(posts)} hours={hours}", flush=True)
    if not posts:
        return {"posts": 0, "review": {"summary": "нет постов"}}

    if mode == "fast":
        review = await analyze_fast(posts)
    else:
        review = await analyze_deep(posts, model_hint)

    json_path, md_path = save_report(
        mode, posts, review, model_hint if mode == "deep" else ""
    )
    print(f"[post_review] saved {md_path}", flush=True)
    print(
        f"[post_review] score={review.get('score_1_10')} "
        f"model={review.get('model_used')}",
        flush=True,
    )

    if notify:
        try:
            import telegram_bot

            await telegram_bot._notify_admins(
                short_telegram_summary(mode, review, len(posts))
            )
        except Exception as e:
            print(f"[post_review] notify fail: {e}", flush=True)

    db.set_setting(
        _SETTING_LAST_REVIEW,
        json.dumps(
            {
                "ts": time.time(),
                "mode": mode,
                "score": review.get("score_1_10"),
                "path": str(md_path),
            }
        ),
    )
    return {"posts": len(posts), "review": review, "md": str(md_path), "json": str(json_path)}


async def run() -> None:
    """Фоновый цикл: fast каждые Nч, deep каждые Mч."""
    if not is_configured():
        print("[post_review] disabled", flush=True)
        return
    print(
        f"[post_review] loop start fast={FAST_INTERVAL_H}h deep={DEEP_INTERVAL_H}h",
        flush=True,
    )
    await asyncio.sleep(120)  # дать БД/LLM подняться
    last_fast = 0.0
    last_deep = 0.0
    while True:
        try:
            import ai_client

            if not ai_client.openrouter_configured() and not ai_client.OPENAI_API_KEY:
                print("[post_review] no AI key, sleep 1h", flush=True)
                await asyncio.sleep(3600)
                continue

            now = time.time()
            if now - last_fast >= FAST_INTERVAL_H * 3600:
                await run_review("fast", hours=FAST_INTERVAL_H * 1.5, notify=True)
                last_fast = now
            if now - last_deep >= DEEP_INTERVAL_H * 3600:
                await run_review(
                    "deep", hours=DEEP_INTERVAL_H, model_hint="gemini", notify=True
                )
                last_deep = now
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[post_review] loop error: {e}", flush=True)
        await asyncio.sleep(600)


async def _cli_run(args: argparse.Namespace) -> int:
    if args.mode == "auto":
        await run()
        return 0
    mode: ReviewMode = "fast" if args.mode == "fast" else "deep"
    result = await run_review(
        mode=mode,
        hours=args.hours,
        model_hint=args.model,
        notify=args.notify,
    )
    review = result.get("review") or {}
    print(f"Score: {review.get('score_1_10')} | {review.get('summary') or review.get('overall_verdict')}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Критика постов market_outlook")
    p.add_argument("--mode", choices=["fast", "deep", "auto"], default="fast")
    p.add_argument("--hours", type=float, default=48.0)
    p.add_argument("--model", choices=["gemini", "claude", "gpt"], default="gemini")
    p.add_argument("--notify", action="store_true", help="отправить итог админам в TG")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_cli_run(args)))


if __name__ == "__main__":
    main()
