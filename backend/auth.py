"""
Аутентификация — email+пароль, Google OAuth, подтверждение почты, сброс пароля.
Пароли: pbkdf2. Сессии: токены в БД.
"""
from __future__ import annotations

import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta

import database as db
import email_smtp

PBKDF2_ITERATIONS = 200_000
SESSION_DAYS = 30
TRIAL_DAYS = 3
TRIAL_TIER = 'premium'
VERIFY_HOURS = 24
RESET_HOURS = 1

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
# Если SMTP не настроен — регистрация работает без обязательного подтверждения
REQUIRE_EMAIL_VERIFY = os.getenv("REQUIRE_EMAIL_VERIFY", "1").strip().lower() not in ("0", "false", "no")

TIERS = ['free', 'premium', 'vip']
TIER_RANK = {t: i for i, t in enumerate(TIERS)}


def _trial_active(user: dict) -> bool:
    ends = user.get('trial_ends_at') if user else None
    if not ends:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(ends)
    except (ValueError, TypeError):
        return False


def effective_tier(user: dict) -> str:
    if not user:
        return 'free'
    base = user.get('tier', 'free')
    if TIER_RANK.get(base, 0) >= TIER_RANK.get(TRIAL_TIER, 0):
        return base
    if _trial_active(user):
        return TRIAL_TIER
    return base


def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return dk.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    if not password_hash or not salt:
        return False
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _admin_emails() -> set[str]:
    raw = os.getenv("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _maybe_promote_admin(user: dict) -> dict:
    if user and user['email'] in _admin_emails() and not user.get('is_admin'):
        db.set_user_admin(user['id'], True)
        user = db.get_user_by_id(user['id'])
    return user


def _issue_session(user_id: int) -> str:
    token = new_session_token()
    expires = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat()
    db.create_session(token, user_id, expires)
    return token


def _email_verify_required() -> bool:
    return REQUIRE_EMAIL_VERIFY and email_smtp.is_configured()


def _create_token(user_id: int, kind: str, hours: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(hours=hours)).isoformat()
    db.create_auth_token(token, user_id, kind, expires)
    return token


def register(email: str, password: str):
    """
    Регистрация email+пароль.
    Если SMTP настроен — шлём письмо подтверждения, сессию не выдаём.
    Иначе — сразу логиним (dev / без почты).
    Возвращает dict или (None, error).
    """
    email = (email or '').lower().strip()
    if not email or '@' not in email:
        return None, 'Некорректный email'
    if not password or len(password) < 8:
        return None, 'Пароль минимум 8 символов'
    if db.get_user_by_email(email):
        return None, 'Email уже зарегистрирован'

    h, salt = hash_password(password)
    trial_ends = (datetime.now() + timedelta(days=TRIAL_DAYS)).isoformat()
    need_verify = _email_verify_required()
    uid = db.create_user(
        email, h, salt, tier='free', trial_ends_at=trial_ends,
        email_verified=0 if need_verify else 1,
    )
    user = db.get_user_by_id(uid)

    if need_verify:
        token = _create_token(uid, 'verify', VERIFY_HOURS)
        sent = email_smtp.send_verify_email(email, token)
        if not sent:
            return None, 'Не удалось отправить письмо. Попробуй позже или войди через Google.'
        return {
            'needs_verification': True,
            'email': email,
            'message': 'Проверь почту — мы отправили ссылку для подтверждения.',
        }, None

    user = _maybe_promote_admin(user)
    sess = _issue_session(uid)
    return {'token': sess, 'user': public_user(user), 'needs_verification': False}, None


def login(email: str, password: str):
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash'], user['salt']):
        return None, 'Неверный email или пароль'
    if _email_verify_required() and not user.get('email_verified') and not user.get('google_id'):
        return None, 'Сначала подтверди email — ссылка в письме. Можно запросить письмо снова.'
    user = _maybe_promote_admin(user)
    token = _issue_session(user['id'])
    return user, token


def verify_email(token: str):
    uid = db.consume_auth_token(token, 'verify')
    if not uid:
        return None, 'Ссылка недействительна или устарела'
    db.set_email_verified(uid, True)
    user = _maybe_promote_admin(db.get_user_by_id(uid))
    sess = _issue_session(uid)
    return {'token': sess, 'user': public_user(user)}, None


def resend_verification(email: str):
    email = (email or '').lower().strip()
    user = db.get_user_by_email(email)
    # Не раскрываем, есть ли email
    ok_msg = 'Если аккаунт существует и не подтверждён — письмо отправлено.'
    if not user or user.get('email_verified'):
        return {'ok': True, 'message': ok_msg}, None
    if not email_smtp.is_configured():
        return None, 'Отправка писем не настроена'
    token = _create_token(user['id'], 'verify', VERIFY_HOURS)
    if not email_smtp.send_verify_email(email, token):
        return None, 'Не удалось отправить письмо'
    return {'ok': True, 'message': ok_msg}, None


def request_password_reset(email: str):
    email = (email or '').lower().strip()
    ok_msg = 'Если аккаунт существует — письмо со ссылкой отправлено.'
    user = db.get_user_by_email(email)
    if not user:
        return {'ok': True, 'message': ok_msg}, None
    if not email_smtp.is_configured():
        return None, 'Отправка писем не настроена'
    token = _create_token(user['id'], 'reset', RESET_HOURS)
    if not email_smtp.send_reset_email(email, token):
        return None, 'Не удалось отправить письмо'
    return {'ok': True, 'message': ok_msg}, None


def reset_password(token: str, password: str):
    if not password or len(password) < 8:
        return None, 'Пароль минимум 8 символов'
    uid = db.consume_auth_token(token, 'reset')
    if not uid:
        return None, 'Ссылка недействительна или устарела'
    h, salt = hash_password(password)
    db.set_user_password(uid, h, salt)
    db.set_email_verified(uid, True)
    user = _maybe_promote_admin(db.get_user_by_id(uid))
    sess = _issue_session(uid)
    return {'token': sess, 'user': public_user(user)}, None


def login_with_google(id_token_str: str):
    """Проверяет Google ID token, создаёт/линкует пользователя, выдаёт сессию."""
    if not GOOGLE_CLIENT_ID:
        return None, 'Google вход не настроен'
    info = _verify_google_id_token(id_token_str)
    if not info:
        return None, 'Неверный Google-токен'
    email = (info.get('email') or '').lower().strip()
    sub = info.get('sub')
    if not email or not sub:
        return None, 'Google не вернул email'
    if not info.get('email_verified', False):
        return None, 'Email Google не подтверждён'

    user = db.get_user_by_google_id(sub) or db.get_user_by_email(email)
    if user:
        if not user.get('google_id'):
            db.set_user_google_id(user['id'], sub)
        if not user.get('email_verified'):
            db.set_email_verified(user['id'], True)
        user = db.get_user_by_id(user['id'])
    else:
        # Неиспользуемый пароль — вход только через Google, пока не зададут пароль через reset
        h, salt = hash_password(secrets.token_urlsafe(32))
        trial_ends = (datetime.now() + timedelta(days=TRIAL_DAYS)).isoformat()
        uid = db.create_user(
            email, h, salt, tier='free', trial_ends_at=trial_ends,
            email_verified=1, google_id=sub,
        )
        user = db.get_user_by_id(uid)

    user = _maybe_promote_admin(user)
    token = _issue_session(user['id'])
    return user, token


def _verify_google_id_token(token: str) -> dict | None:
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        return google_id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID,
        )
    except Exception as e:
        print(f"[auth] google token verify failed: {e}")
        return None


def logout(token: str):
    db.delete_session(token)


def user_from_token(token: str):
    return db.get_user_by_token(token)


def tier_allows(user_tier: str, required_tier: str) -> bool:
    return TIER_RANK.get(user_tier, 0) >= TIER_RANK.get(required_tier, 0)


def public_auth_config() -> dict:
    return {
        'google_client_id': GOOGLE_CLIENT_ID or None,
        'email_enabled': email_smtp.is_configured(),
        'require_email_verify': _email_verify_required(),
    }


def public_user(user: dict) -> dict:
    if not user:
        return None
    eff = effective_tier(user)
    active = _trial_active(user) and eff == TRIAL_TIER and TIER_RANK.get(user.get('tier', 'free'), 0) < TIER_RANK.get(TRIAL_TIER, 0)
    days_left = None
    if active:
        try:
            delta = datetime.fromisoformat(user['trial_ends_at']) - datetime.now()
            days_left = max(0, delta.days + (1 if delta.seconds else 0))
        except (ValueError, TypeError):
            days_left = None
    return {
        'id': user['id'],
        'email': user['email'],
        'tier': eff,
        'base_tier': user.get('tier', 'free'),
        'on_trial': active,
        'trial_days_left': days_left,
        'trial_ends_at': user.get('trial_ends_at'),
        'is_admin': bool(user.get('is_admin')),
        'email_verified': bool(user.get('email_verified')),
        'has_google': bool(user.get('google_id')),
    }
