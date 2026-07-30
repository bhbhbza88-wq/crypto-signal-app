# -*- coding: utf-8 -*-
"""Probe channels then audit charts on NEWS + VIP posts."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Всегда локальный отчёт в репо (railway DATA_DIR часто /data)
OUT_DIR = ROOT / "data" / "post_reviews"
AUDIT_DIR = OUT_DIR / "chart_audit_images"

NEWS_DEFAULT = "nowicki_news"
# username снят — резолвим по id / title
NEWS_CHANNEL_ID = int(os.getenv("TELEGRAM_NEWS_CHANNEL_ID", "-1004356979285") or "-1004356979285")
VIP_INVITE = "https://t.me/+ONlP_9aok4kxMDZi"

CHART_AUDIT_PROMPT = """Ты трейдер-ревьюер. Проверь ОДИН пост канала: текст + картинка.

Канал: {channel_kind}
Текст поста:
---
{caption}
---

Задача — понять, КОРРЕКТЕН ли график/карточка относительно текста.

Если NEWS (свечной график outlook):
1. Направление стрелки/path совпадает с bias в тексте (long/short/рост/падение)?
2. Цены/уровни из текста не противоречат графику (допуск ~1-2%)?
3. Зоны supply/demand не перепутаны со смыслом текста?
4. Монета/таймфрейм на графике = посту?
5. Явный баг: пустой график, чужая монета, зеркальный bias?

Если VIP (карточка позиции биржи — это НЕ полный график):
ВАЖНО: на карточке Bybit/BingX по дизайну часто TP = "--", а цели (TP1/TP2/TP3) только в ТЕКСТЕ поста.
Это НЕ ошибка. Не требуй TP1/TP2/TP3 на картинке.
Проверяй только:
1. Symbol совпадает?
2. Side Long/Short совпадает с текстом (цвет/лейбл)?
3. Entry/средняя цена ≈ вход из текста (допуск округления ок)?
4. Если SL на карточке есть — ≈ стопу из текста (допуск округления)?
5. Явный баг: другая монета, противоположная сторона, вход совсем другой?

chart_correct=false ТОЛЬКО при реальном баге (не из-за отсутствия TP на карточке).

Верни СТРОГО JSON без markdown:
{{
  "ok": true,
  "chart_correct": true,
  "score_1_10": 8,
  "channel_kind": "{channel_kind}",
  "symbol_guess": "BTC",
  "bias_text": "long|short|flat|unknown",
  "bias_chart": "long|short|flat|unknown",
  "issues": ["конкретные проблемы или пустой список"],
  "verdict": "1-2 предложения по-русски"
}}
"""


def _mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF":
        return "image/webp"
    return "image/jpeg"


def _parse_json(raw: str) -> dict:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"ok": False, "parse_error": True, "raw": (raw or "")[:800]}


async def _llm_vision(prompt: str, png: bytes) -> dict:
    import ai_client

    mime = _mime(png)
    b64 = base64.b64encode(png).decode("ascii")
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]
    model = (os.getenv("POST_REVIEW_MODEL_DEEP") or "google/gemini-2.5-flash").strip()
    # flash дешевле и норм для vision checklist; pro если задан
    if "pro" in model.lower() and "3.1" in model:
        model = "google/gemini-2.5-flash"
    raw = await ai_client.openai_compatible_completion(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=900,
        temperature=0.15,
        timeout=90,
        response_format={"type": "json_object"},
    )
    parsed = _parse_json(raw)
    parsed["model_used"] = model
    return parsed


async def _collect_from_entity(client, entity, *, kind: str, limit: int) -> list[dict]:
    rows = []
    async for msg in client.iter_messages(entity, limit=limit):
        if not msg:
            continue
        has_photo = bool(getattr(msg, "photo", None))
        doc = getattr(msg, "document", None)
        mime = ""
        if doc is not None:
            mime = str(getattr(doc, "mime_type", "") or "")
        if not has_photo and not mime.startswith("image/"):
            continue
        try:
            data = await client.download_media(msg, file=bytes)
        except Exception as e:
            print(f"  download fail {kind} #{msg.id}: {e}", flush=True)
            continue
        if not data or len(data) < 800:
            continue
        caption = (msg.message or msg.raw_text or "").strip()
        rows.append(
            {
                "channel_kind": kind,
                "msg_id": int(msg.id),
                "date": msg.date.astimezone(timezone.utc).isoformat() if msg.date else None,
                "caption": caption[:2500],
                "image": data,
            }
        )
        print(f"  collected {kind} #{msg.id} bytes={len(data)} caption={caption[:60]!r}", flush=True)
    return rows


async def collect_posts(limit_per_channel: int = 25) -> list[dict]:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
    from telethon.errors import UserAlreadyParticipantError

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    sess = os.environ["TELEGRAM_SESSION"]
    client = TelegramClient(StringSession(sess), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("TELEGRAM_SESSION not authorized")

    posts: list[dict] = []

    # NEWS — без публичного username, берём id / диалог по title
    news = (os.getenv("TELEGRAM_NEWS_TARGET_CHANNEL") or NEWS_DEFAULT).strip().lstrip("@")
    news_ent = None
    try:
        news_ent = await client.get_entity(NEWS_CHANNEL_ID)
    except Exception:
        news_ent = None
    if news_ent is None:
        try:
            news_ent = await client.get_entity(news)
        except Exception:
            news_ent = None
    if news_ent is None:
        async for d in client.iter_dialogs(limit=300):
            t = (d.name or "").lower()
            if t in {"nowicki_news", "nowicki news"} or "nowicki_news" in t.replace(" ", "_"):
                news_ent = d.entity
                break
    try:
        if news_ent is None:
            raise RuntimeError("news channel not found in dialogs")
        title = getattr(news_ent, "title", None) or news
        print(f"NEWS entity: {title} id={getattr(news_ent,'id',None)}", flush=True)
        posts.extend(await _collect_from_entity(client, news_ent, kind="news", limit=limit_per_channel * 2))
    except Exception as e:
        print(f"NEWS fail: {type(e).__name__}: {e}", flush=True)

    # VIP targets
    vip_targets: list[tuple[str, str]] = []
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if chat_id:
        vip_targets.append(("vip", chat_id))
    prem = (os.getenv("TELEGRAM_PREMIUM_CHANNEL_IDS") or "").strip()
    for part in prem.split(","):
        p = part.strip()
        if p and p != chat_id:
            vip_targets.append(("vip", p))
    vip_targets.append(("vip", VIP_INVITE))
    # second farm invite if different
    vip_targets.append(("vip", "https://t.me/+oJgX5-6k3agwYjky"))

    seen = set()
    for kind, target in vip_targets:
        key = target
        if key in seen:
            continue
        seen.add(key)
        try:
            if "t.me/+" in target or target.startswith("+"):
                h = target.split("+")[-1].strip().rstrip("/")
                try:
                    await client(ImportChatInviteRequest(h))
                except UserAlreadyParticipantError:
                    pass
                except Exception:
                    pass
                inv = await client(CheckChatInviteRequest(h))
                ent = getattr(inv, "chat", None) or await client.get_entity(target)
            else:
                ent = await client.get_entity(int(target) if re.fullmatch(r"-?\d+", target) else target)
            title = getattr(ent, "title", None) or str(target)[:40]
            print(f"VIP entity: {title}", flush=True)
            batch = await _collect_from_entity(client, ent, kind="vip", limit=limit_per_channel * 2)
            posts.extend(batch)
            if batch:
                break  # one working VIP channel is enough
        except Exception as e:
            print(f"VIP fail {target[:30]}: {type(e).__name__}: {e}", flush=True)

    await client.disconnect()

    # keep newest with media, cap
    posts.sort(key=lambda x: x.get("date") or "", reverse=True)
    # balance: up to limit news + limit vip
    news_p = [p for p in posts if p["channel_kind"] == "news"][:limit_per_channel]
    vip_p = [p for p in posts if p["channel_kind"] == "vip"][:limit_per_channel]
    return news_p + vip_p


async def audit(posts: list[dict]) -> dict:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for i, p in enumerate(posts):
        kind = p["channel_kind"]
        img = p["image"]
        path = AUDIT_DIR / f"{kind}_{p['msg_id']}.png"
        try:
            path.write_bytes(img)
        except Exception:
            pass
        prompt = CHART_AUDIT_PROMPT.format(
            channel_kind=kind,
            caption=(p.get("caption") or "(нет текста)")[:2000],
        )
        print(f"[{i+1}/{len(posts)}] review {kind} #{p['msg_id']}...", flush=True)
        try:
            rev = await _llm_vision(prompt, img)
        except Exception as e:
            rev = {"ok": False, "chart_correct": None, "issues": [f"llm_error:{type(e).__name__}: {e}"], "verdict": "ошибка LLM"}
        row = {
            "index": i,
            "channel_kind": kind,
            "msg_id": p["msg_id"],
            "date": p.get("date"),
            "caption_preview": (p.get("caption") or "")[:180],
            "image_path": str(path),
            "review": rev,
        }
        results.append(row)
        ok = rev.get("chart_correct")
        print(f"  correct={ok} score={rev.get('score_1_10')} | {rev.get('verdict')}", flush=True)
        await asyncio.sleep(0.4)

    bad = [r for r in results if r.get("review", {}).get("chart_correct") is False]
    unknown = [r for r in results if r.get("review", {}).get("chart_correct") is None]
    good = [r for r in results if r.get("review", {}).get("chart_correct") is True]
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "news": sum(1 for r in results if r["channel_kind"] == "news"),
        "vip": sum(1 for r in results if r["channel_kind"] == "vip"),
        "correct": len(good),
        "incorrect": len(bad),
        "unknown": len(unknown),
        "results": results,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = OUT_DIR / f"chart_audit_{stamp}.json"
    md_path = OUT_DIR / f"chart_audit_{stamp}.md"
    latest_json = OUT_DIR / "latest_chart_audit.json"
    latest_md = OUT_DIR / "latest_chart_audit.md"

    md = [
        f"# Chart audit — {summary['created_at']}",
        "",
        f"**Total:** {summary['total']} (news={summary['news']}, vip={summary['vip']})",
        f"**Correct:** {summary['correct']} | **Incorrect:** {summary['incorrect']} | **Unknown:** {summary['unknown']}",
        "",
        "## Problems",
    ]
    if not bad:
        md.append("_Явных проблем с chart_correct=false не найдено._")
    for r in bad:
        rev = r["review"]
        md += [
            f"### {r['channel_kind']} #{r['msg_id']}",
            f"- score: {rev.get('score_1_10')}",
            f"- verdict: {rev.get('verdict')}",
            f"- issues: {', '.join(rev.get('issues') or []) or '—'}",
            f"- caption: `{r['caption_preview']}`",
            "",
        ]
    md += ["", "## All"]
    for r in results:
        rev = r["review"]
        flag = "OK" if rev.get("chart_correct") is True else ("BAD" if rev.get("chart_correct") is False else "?")
        md.append(
            f"- [{flag}] {r['channel_kind']} #{r['msg_id']} score={rev.get('score_1_10')} — {rev.get('verdict')}"
        )

    text = "\n".join(md) + "\n"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(text, encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(text, encoding="utf-8")
    print(f"saved {md_path}", flush=True)
    print(f"saved {json_path}", flush=True)
    return summary


async def main() -> int:
    limit = int(os.getenv("CHART_AUDIT_LIMIT", "20") or "20")
    print(f"collecting up to {limit} media posts per channel...", flush=True)
    posts = await collect_posts(limit_per_channel=limit)
    print(f"collected {len(posts)} posts with images", flush=True)
    if not posts:
        print("ERROR: no posts with media", flush=True)
        return 1
    # drop raw bytes from memory after audit writes files — audit uses image field
    summary = await audit(posts)
    print(
        json.dumps(
            {
                "total": summary["total"],
                "correct": summary["correct"],
                "incorrect": summary["incorrect"],
                "unknown": summary["unknown"],
                "news": summary["news"],
                "vip": summary["vip"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
