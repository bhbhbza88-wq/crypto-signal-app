"""
Отправка писем: Resend (HTTP) или Gmail API (HTTP) или SMTP.

Railway блокирует исходящий SMTP (порты 25/465/587) → Errno 101.
Поэтому предпочтительны HTTP-провайдеры.

Env (по приоритету):
  RESEND_API_KEY          — https://resend.com (если есть домен)
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REFRESH_TOKEN    — OAuth refresh с scope gmail.send
  SMTP_*                  — fallback (на Railway обычно не работает)
  SMTP_FROM / EMAIL_FROM  — From
  EMAIL_REPLY_TO          — Reply-To (по умолчанию support Gmail)
  FRONTEND_URL
"""
from __future__ import annotations

import base64
import os
import smtplib
import socket
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from html import escape

import httpx

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
SMTP_FROM = (
    os.getenv("EMAIL_FROM", "").strip()
    or os.getenv("SMTP_FROM", "").strip()
    or SMTP_USER
    or "NOWICKI <noreply@send.nowicki.trade>"
)
FRONTEND_URL = (os.getenv("FRONTEND_URL", "https://nowicki.trade") or "https://nowicki.trade").rstrip("/")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "bhbhbza.88@gmail.com").strip() or "bhbhbza.88@gmail.com"
SUPPORT_TG = os.getenv("SUPPORT_TG", "Kupyansk_2").strip() or "Kupyansk_2"
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "").strip() or SUPPORT_EMAIL

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()

# Статика с фронта (frontend/public/email/*) → https://nowicki.trade/email/...
EMAIL_LOGO_URL = f"{FRONTEND_URL}/email/logo.png"
EMAIL_BANNER_URL = f"{FRONTEND_URL}/email/banner.png"


def is_configured() -> bool:
    if RESEND_API_KEY:
        return True
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN:
        return True
    return bool(SMTP_USER and SMTP_PASSWORD)


def _send_resend(to: str, subject: str, text: str, html: str | None) -> bool:
    payload = {
        "from": SMTP_FROM if "@" in SMTP_FROM else f"NOWICKI <{SMTP_FROM}>",
        "to": [to],
        "subject": subject,
        "text": text,
        "reply_to": EMAIL_REPLY_TO,
    }
    if html:
        payload["html"] = html
    # Без verified-домена Resend шлёт только на email владельца аккаунта.
    verified = os.getenv("RESEND_DOMAIN_VERIFIED", "").strip().lower() in ("1", "true", "yes")
    if verified:
        if "send.nowicki.trade" not in payload["from"].lower():
            payload["from"] = "NOWICKI <noreply@send.nowicki.trade>"
    else:
        payload["from"] = "NOWICKI <onboarding@resend.dev>"
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=25,
    )
    if r.status_code >= 400:
        print(f"[email] resend error {r.status_code}: {r.text}")
        return False
    print(f"[email] resend → {to}: {subject}")
    return True


def _gmail_access_token() -> str | None:
    r = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": GOOGLE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=25,
    )
    if r.status_code >= 400:
        print(f"[email] gmail token error {r.status_code}: {r.text}")
        return None
    return r.json().get("access_token")


def _send_gmail_api(to: str, subject: str, text: str, html: str | None) -> bool:
    token = _gmail_access_token()
    if not token:
        return False
    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
    else:
        msg = MIMEText(text, "plain", "utf-8")
    msg["To"] = to
    msg["From"] = SMTP_FROM if "@" in SMTP_FROM else SMTP_USER
    msg["Subject"] = subject
    if EMAIL_REPLY_TO:
        msg["Reply-To"] = EMAIL_REPLY_TO
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    r = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=25,
    )
    if r.status_code >= 400:
        print(f"[email] gmail api error {r.status_code}: {r.text}")
        return False
    print(f"[email] gmail api → {to}: {subject}")
    return True


def _ipv4_host(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except OSError as e:
        print(f"[email] IPv4 resolve {host}:{port} failed: {e}")
    return host


def _send_smtp(to: str, subject: str, text: str, html: str | None) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    if EMAIL_REPLY_TO:
        msg["Reply-To"] = EMAIL_REPLY_TO
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    attempts = [("ssl", 465), ("starttls", 587)]
    last_err = None
    for mode, port in attempts:
        ip = _ipv4_host(SMTP_HOST, port)
        try:
            if mode == "ssl":
                server = smtplib.SMTP_SSL(ip, port, timeout=25)
            else:
                server = smtplib.SMTP(ip, port, timeout=25)
                server.ehlo()
                server.starttls()
                server.ehlo()
            with server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            print(f"[email] smtp → {to}: {subject}")
            return True
        except Exception as e:
            last_err = e
            print(f"[email] smtp {mode}:{port} failed: {e}")
    print(f"[email] smtp all failed: {last_err}")
    return False


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    if not is_configured():
        print(f"[email] не настроен — пропуск: {subject} → {to}")
        return False
    try:
        # HTTP сначала: Railway блокирует исходящий SMTP (Errno 101).
        # Если Resend настроен — только он (без Gmail/SMTP fallback с длинными таймаутами).
        if RESEND_API_KEY:
            return _send_resend(to, subject, text, html)
        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN:
            if _send_gmail_api(to, subject, text, html):
                return True
        if SMTP_USER and SMTP_PASSWORD:
            return _send_smtp(to, subject, text, html)
        return False
    except Exception as e:
        print(f"[email] ошибка отправки → {to}: {e}")
        return False


def send_verify_email(to: str, token: str) -> bool:
    link = f"{FRONTEND_URL}/verify-email?token={token}"
    subject = "Подтвердите email — NOWICKI"
    text = (
        f"Привет!\n\n"
        f"Подтверди email для аккаунта NOWICKI:\n{link}\n\n"
        f"Ссылка действует 24 часа. Если ты не регистрировался — просто игнорируй письмо."
    )
    html = f"""
    <p>Привет!</p>
    <p>Подтверди email для аккаунта <b>NOWICKI</b>:</p>
    <p><a href="{link}">Подтвердить email</a></p>
    <p style="color:#666;font-size:13px">Ссылка действует 24 часа. Если ты не регистрировался — игнорируй письмо.</p>
    """
    return send_email(to, subject, text, html)


def send_reset_email(to: str, token: str) -> bool:
    link = f"{FRONTEND_URL}/reset-password?token={token}"
    subject = "Сброс пароля — NOWICKI"
    text = (
        f"Сброс пароля NOWICKI:\n{link}\n\n"
        f"Ссылка действует 1 час. Если ты не запрашивал сброс — игнорируй письмо."
    )
    html = f"""
    <p>Сброс пароля для <b>NOWICKI</b>:</p>
    <p><a href="{link}">Задать новый пароль</a></p>
    <p style="color:#666;font-size:13px">Ссылка действует 1 час. Если ты не запрашивал сброс — игнорируй письмо.</p>
    """
    return send_email(to, subject, text, html)


def _fmt_pnl(v: float) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        n = 0.0
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.1f}%"


def _channel_results_for_email() -> dict | None:
    """Те же публичные цифры, что на сайте (/api/stats + polish витрины)."""
    try:
        import public_feed
        from display_polish import polish_pnl, polish_winrate

        pub30 = public_feed.load_channel_feed(limit=500, days=30)
        cutoff = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
        pub7 = [t for t in pub30 if (t.get("date") or "") >= cutoff]
        week_raw = public_feed.summarize_trades(pub7)
        month_raw = public_feed.summarize_trades(pub30)
        bucket = week_raw if (week_raw.get("total") or 0) > 0 else month_raw
        if not (bucket.get("total") or 0):
            return None

        recent_src = pub7[:5] if pub7 else pub30[:5]
        recent = []
        for t in recent_src:
            recent.append({
                "symbol": str(t.get("symbol") or "?").replace("/USDT", ""),
                "pnl": polish_pnl(t.get("pnl")),
                "result": str(t.get("result") or ""),
            })

        return {
            "period": "7 дней" if (week_raw.get("total") or 0) > 0 else "30 дней",
            "total": int(bucket.get("total") or 0),
            "winrate": polish_winrate(bucket.get("winrate") or 0),
            "total_pnl": polish_pnl(bucket.get("total_pnl") or 0),
            "avg_pnl": polish_pnl(bucket.get("avg_pnl") or 0),
            "recent": recent,
            "week_total": int(week_raw.get("total") or 0),
            "month_total": int(month_raw.get("total") or 0),
            "week_pnl": polish_pnl(week_raw.get("total_pnl") or 0) if week_raw.get("total") else None,
            "month_pnl": polish_pnl(month_raw.get("total_pnl") or 0) if month_raw.get("total") else None,
            "week_wr": polish_winrate(week_raw.get("winrate") or 0) if week_raw.get("total") else None,
            "month_wr": polish_winrate(month_raw.get("winrate") or 0) if month_raw.get("total") else None,
        }
    except Exception as e:
        print(f"[email] channel results: {e}")
        return None


def _results_text_block(stats: dict | None) -> str:
    if not stats:
        return (
            "Актуальные результаты публичного канала смотри на сайте — "
            f"{FRONTEND_URL}/#signals\n"
        )
    lines = [
        f"Публичные результаты NOWICKI ({stats['period']}):",
        f"  сделок: {stats['total']}",
        f"  винрейт: {stats['winrate']}%",
        f"  суммарный PnL: {_fmt_pnl(stats['total_pnl'])}",
        f"  средний PnL: {_fmt_pnl(stats['avg_pnl'])}",
    ]
    if stats.get("recent"):
        lines.append("Недавние закрытия:")
        for r in stats["recent"]:
            lines.append(f"  · {r['symbol']}: {_fmt_pnl(r['pnl'])}")
    lines.append(f"Подробнее: {FRONTEND_URL}/#signals")
    return "\n".join(lines) + "\n"


def _results_html_block(stats: dict | None) -> str:
    if not stats:
        return f"""
        <tr><td style="padding:8px 28px 4px;font-size:14px;color:#6e6e73;line-height:1.5">
          Актуальные результаты публичного канала — на
          <a href="{FRONTEND_URL}/#signals" style="color:#0f766e">nowicki.trade</a>.
        </td></tr>
        """
    recent_rows = ""
    for r in stats.get("recent") or []:
        color = "#0d9f78" if float(r["pnl"]) > 0 else ("#e23d4a" if float(r["pnl"]) < 0 else "#6e6e73")
        recent_rows += (
            f'<tr><td style="padding:6px 0;font-size:13px;color:#1d1d1f;font-family:IBM Plex Mono,Menlo,monospace">'
            f'{escape(r["symbol"])}</td>'
            f'<td style="padding:6px 0;font-size:13px;text-align:right;color:{color};'
            f'font-family:IBM Plex Mono,Menlo,monospace;font-weight:600">'
            f'{escape(_fmt_pnl(r["pnl"]))}</td></tr>'
        )
    recent_table = ""
    if recent_rows:
        recent_table = f"""
        <tr><td style="padding:4px 28px 8px">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="border-collapse:collapse;background:#f5f6f8;border-radius:12px">
            <tr><td style="padding:12px 14px">
              <div style="font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
                          color:#0f766e;margin-bottom:8px">Недавние закрытия</div>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{recent_rows}</table>
            </td></tr>
          </table>
        </td></tr>
        """
    return f"""
    <tr><td style="padding:4px 28px 0">
      <div style="font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
                  color:#0f766e;margin-bottom:10px">Результаты канала · {escape(stats['period'])}</div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
        <tr>
          <td width="33%" style="padding:10px 8px;text-align:center;background:#e6f4f2;border-radius:10px">
            <div style="font-size:22px;font-weight:700;color:#0f766e;font-family:IBM Plex Mono,Menlo,monospace">
              {stats['winrate']}%</div>
            <div style="font-size:11px;color:#6e6e73;margin-top:2px">винрейт</div>
          </td>
          <td width="4%"></td>
          <td width="33%" style="padding:10px 8px;text-align:center;background:#e6f4f2;border-radius:10px">
            <div style="font-size:22px;font-weight:700;color:#0f766e;font-family:IBM Plex Mono,Menlo,monospace">
              {escape(_fmt_pnl(stats['total_pnl']))}</div>
            <div style="font-size:11px;color:#6e6e73;margin-top:2px">сумм. PnL</div>
          </td>
          <td width="4%"></td>
          <td width="33%" style="padding:10px 8px;text-align:center;background:#e6f4f2;border-radius:10px">
            <div style="font-size:22px;font-weight:700;color:#0f766e;font-family:IBM Plex Mono,Menlo,monospace">
              {stats['total']}</div>
            <div style="font-size:11px;color:#6e6e73;margin-top:2px">сделок</div>
          </td>
        </tr>
      </table>
      <p style="margin:10px 0 0;font-size:13px;color:#6e6e73;line-height:1.45">
        Это публичная витрина nowicki.trade — те же цифры, что на сайте.
        Прошлые результаты не гарантируют будущих.
      </p>
    </td></tr>
    {recent_table}
    """


def _email_shell(*, preheader: str, title: str, body_rows: str, cta_url: str, cta_label: str) -> str:
    """Общий HTML-каркас (таблицы + инлайн-стили, картинки с FRONTEND_URL)."""
    pre = escape(preheader)
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f5f6f8;font-family:'Plus Jakarta Sans',Segoe UI,Helvetica,Arial,sans-serif;color:#1d1d1f">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">{pre}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6f8;padding:24px 12px">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0"
             style="max-width:560px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;
                    border:1px solid rgba(15,23,20,.08)">
        <tr><td style="padding:20px 28px 8px;text-align:center">
          <img src="{EMAIL_LOGO_URL}" width="56" height="56" alt="NOWICKI"
               style="display:inline-block;border:0;border-radius:14px" />
          <div style="margin-top:10px;font-size:18px;font-weight:700;letter-spacing:-.02em">NOWICKI</div>
        </td></tr>
        <tr><td style="padding:4px 28px 12px;text-align:center">
          <img src="{EMAIL_BANNER_URL}" width="504" alt="NOWICKI — публичные результаты"
               style="display:block;width:100%;max-width:504px;height:auto;border:0;border-radius:12px;margin:0 auto" />
        </td></tr>
        {body_rows}
        <tr><td style="padding:18px 28px 8px;text-align:center">
          <a href="{cta_url}"
             style="display:inline-block;background:#0f766e;color:#ffffff;text-decoration:none;
                    font-weight:650;font-size:15px;padding:12px 22px;border-radius:980px">
            {escape(cta_label)}
          </a>
        </td></tr>
        <tr><td style="padding:16px 28px 24px;font-size:12px;color:#86868b;line-height:1.5;text-align:center">
          Вопросы — ответь на письмо или напиши
          <a href="mailto:{escape(SUPPORT_EMAIL)}" style="color:#0f766e">{escape(SUPPORT_EMAIL)}</a>
          · TG <a href="https://t.me/{escape(SUPPORT_TG)}" style="color:#0f766e">@{escape(SUPPORT_TG)}</a><br>
          <span style="color:#a1a1a6">Не финсовет. Криптовалюта — риск потери средств.</span>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def send_welcome_email(to: str) -> bool:
    app_url = f"{FRONTEND_URL}/app/overview"
    stats = _channel_results_for_email()
    subject = "Добро пожаловать в NOWICKI"
    text = (
        f"Привет!\n\n"
        f"Аккаунт на NOWICKI подтверждён — можно продолжать смотреть сигналы в кабинете:\n"
        f"{app_url}\n\n"
        f"{_results_text_block(stats)}\n"
        f"Если понравится динамика — с Premium открываются уровни входа/стопа/TP и закрытый канал.\n"
        f"Тарифы: {FRONTEND_URL}/app/pricing\n\n"
        f"Вопросы — ответь на письмо или @{SUPPORT_TG} / {SUPPORT_EMAIL}."
    )
    body = f"""
    <tr><td style="padding:8px 28px 4px;font-size:16px;line-height:1.55;color:#1d1d1f">
      Привет!
    </td></tr>
    <tr><td style="padding:4px 28px 12px;font-size:15px;line-height:1.55;color:#1d1d1f">
      Аккаунт на <b>NOWICKI</b> подтверждён. Открытые сигналы и история уже в кабинете —
      загляни, когда будет минута.
    </td></tr>
    {_results_html_block(stats)}
    <tr><td style="padding:12px 28px 4px;font-size:14px;line-height:1.55;color:#6e6e73">
      Если динамика зайдёт — с Premium появляются уровни входа/стопа/TP и доступ в закрытый канал.
      Без обязательств: можно просто смотреть публичную часть.
    </td></tr>
    """
    html = _email_shell(
        preheader="Аккаунт подтверждён. Сигналы в кабинете + сводка результатов канала.",
        title=subject,
        body_rows=body,
        cta_url=app_url,
        cta_label="Открыть кабинет",
    )
    return send_email(to, subject, text, html)


def send_pricing_nudge_email(to: str) -> bool:
    pricing_url = f"{FRONTEND_URL}/app/pricing"
    app_url = f"{FRONTEND_URL}/app/overview"
    stats = _channel_results_for_email()
    subject = "Ты уже смотрел сигналы — продолжим?"
    text = (
        f"Привет!\n\n"
        f"Ты уже заходил на NOWICKI и смотрел сигналы. Если интересно продолжить — "
        f"с Premium открываются уровни входа/стопа/TP и закрытый канал.\n\n"
        f"{_results_text_block(stats)}\n"
        f"Мягко: это не гарантия дохода, а публичная статистика канала. "
        f"Если зайдёт — присоединяйся, если нет — просто игнорируй письмо, больше не напомним.\n\n"
        f"Тарифы: {pricing_url}\n"
        f"Кабинет: {app_url}\n\n"
        f"Поддержка: @{SUPPORT_TG} · {SUPPORT_EMAIL}"
    )
    body = f"""
    <tr><td style="padding:8px 28px 4px;font-size:16px;line-height:1.55;color:#1d1d1f">
      Привет!
    </td></tr>
    <tr><td style="padding:4px 28px 12px;font-size:15px;line-height:1.55;color:#1d1d1f">
      Ты уже заходил на <b>NOWICKI</b> и смотрел сигналы. Если хочется продолжить —
      с Premium открываются уровни входа/стопа/TP и доступ в закрытый канал.
    </td></tr>
    {_results_html_block(stats)}
    <tr><td style="padding:12px 28px 4px;font-size:14px;line-height:1.55;color:#6e6e73">
      Цифры выше — публичная витрина. Прошлые сделки не обещают будущих.
      Если формат зайдёт — можно присоединиться; если нет — просто игнорируй письмо,
      больше не напомним.
    </td></tr>
    """
    html = _email_shell(
        preheader="Ты уже смотрел сигналы. Краткая сводка результатов канала и тарифы Premium.",
        title=subject,
        body_rows=body,
        cta_url=pricing_url,
        cta_label="Смотреть тарифы",
    )
    return send_email(to, subject, text, html)
