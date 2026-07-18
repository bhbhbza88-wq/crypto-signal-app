"""
Отправка писем через Gmail SMTP (или любой SMTP).

Env:
  SMTP_HOST       — по умолчанию smtp.gmail.com
  SMTP_PORT       — по умолчанию 587
  SMTP_USER       — Gmail адрес
  SMTP_PASSWORD   — пароль приложения Google (не обычный пароль)
  SMTP_FROM       — опционально, иначе SMTP_USER
  FRONTEND_URL    — https://nowicki.trade (ссылки в письмах)
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
FRONTEND_URL = (os.getenv("FRONTEND_URL", "https://nowicki.trade") or "https://nowicki.trade").rstrip("/")


def is_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    if not is_configured():
        print(f"[email] SMTP не настроен — письмо не отправлено: {subject} → {to}")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[email] отправлено → {to}: {subject}")
        return True
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
