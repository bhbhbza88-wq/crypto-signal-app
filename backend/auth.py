"""
Аутентификация — email + пароль, сессионные токены в БД.
Без внешних зависимостей: pbkdf2 (hashlib) для паролей, secrets для токенов.
"""
import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta

import database as db

PBKDF2_ITERATIONS = 200_000
SESSION_DAYS = 30
TRIAL_DAYS = 3          # бесплатный Premium-триал при регистрации
TRIAL_TIER = 'premium'  # что даёт триал

# Тарифы по возрастанию прав
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
    """Фактический тариф с учётом активного триала.
    Платный тариф (premium/vip) всегда побеждает; иначе — триал даёт TRIAL_TIER."""
    if not user:
        return 'free'
    base = user.get('tier', 'free')
    if TIER_RANK.get(base, 0) >= TIER_RANK.get(TRIAL_TIER, 0):
        return base
    if _trial_active(user):
        return TRIAL_TIER
    return base


def hash_password(password: str, salt: str = None):
    """Возвращает (hash_hex, salt_hex). Соль генерируется, если не передана."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return dk.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def register(email: str, password: str):
    """Создаёт пользователя (tier=free) и сессию. Возвращает (user, token) или (None, error)."""
    email = (email or '').lower().strip()
    if not email or '@' not in email:
        return None, 'Некорректный email'
    if not password or len(password) < 6:
        return None, 'Пароль минимум 6 символов'
    if db.get_user_by_email(email):
        return None, 'Email уже зарегистрирован'
    h, salt = hash_password(password)
    trial_ends = (datetime.now() + timedelta(days=TRIAL_DAYS)).isoformat()
    uid = db.create_user(email, h, salt, tier='free', trial_ends_at=trial_ends)
    user = db.get_user_by_id(uid)
    token = _issue_session(uid)
    return user, token


def _admin_emails() -> set[str]:
    raw = os.getenv("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def login(email: str, password: str):
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash'], user['salt']):
        return None, 'Неверный email или пароль'
    if user['email'] in _admin_emails() and not user.get('is_admin'):
        db.set_user_admin(user['id'], True)
        user = db.get_user_by_id(user['id'])
    token = _issue_session(user['id'])
    return user, token


def _issue_session(user_id: int) -> str:
    token = new_session_token()
    expires = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat()
    db.create_session(token, user_id, expires)
    return token


def logout(token: str):
    db.delete_session(token)


def user_from_token(token: str):
    return db.get_user_by_token(token)


def tier_allows(user_tier: str, required_tier: str) -> bool:
    return TIER_RANK.get(user_tier, 0) >= TIER_RANK.get(required_tier, 0)


def public_user(user: dict) -> dict:
    """Безопасное представление пользователя (без хеша/соли).
    tier — фактический (с учётом триала); base_tier — оплаченный."""
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
    }
