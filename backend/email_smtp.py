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
  FRONTEND_URL
"""
from __future__ import annotations

import base64
import os
import smtplib
import socket
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()


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


def send_welcome_email(to: str) -> bool:
    app_url = f"{FRONTEND_URL}/app/overview"
    subject = "Добро пожаловать в NOWICKI"
    text = (
        f"Привет!\n\n"
        f"Аккаунт на NOWICKI подтверждён. Открытые сигналы и история — в кабинете:\n"
        f"{app_url}\n\n"
        f"Если будут вопросы — ответь на это письмо или напиши в поддержку на сайте."
    )
    html = f"""
    <p>Привет!</p>
    <p>Аккаунт на <b>NOWICKI</b> подтверждён. Открытые сигналы и история — в кабинете:</p>
    <p><a href="{app_url}">Открыть кабинет</a></p>
    <p style="color:#666;font-size:13px">Вопросы — ответь на письмо или напиши в поддержку на сайте.</p>
    """
    return send_email(to, subject, text, html)


def send_pricing_nudge_email(to: str) -> bool:
    pricing_url = f"{FRONTEND_URL}/app/pricing"
    subject = "Premium на NOWICKI — уровни входов и закрытый канал"
    text = (
        f"Привет!\n\n"
        f"Ты уже смотришь сигналы на NOWICKI. С Premium открываются уровни входа/стопа/TP "
        f"и доступ в закрытый канал.\n\n"
        f"Тарифы: {pricing_url}\n\n"
        f"Если не интересно — просто игнорируй письмо, больше не напомним."
    )
    html = f"""
    <p>Привет!</p>
    <p>Ты уже смотришь сигналы на <b>NOWICKI</b>. С Premium открываются уровни входа/стопа/TP
    и доступ в закрытый канал.</p>
    <p><a href="{pricing_url}">Смотреть тарифы</a></p>
    <p style="color:#666;font-size:13px">Если не интересно — игнорируй письмо, больше не напомним.</p>
    """
    return send_email(to, subject, text, html)
