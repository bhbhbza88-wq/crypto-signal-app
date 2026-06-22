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

# Тарифы по возрастанию прав
TIERS = ['free', 'premium', 'vip']
TIER_RANK = {t: i for i, t in enumerate(TIERS)}


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
    uid = db.create_user(email, h, salt, tier='free')
    user = db.get_user_by_id(uid)
    token = _issue_session(uid)
    return user, token


def login(email: str, password: str):
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash'], user['salt']):
        return None, 'Неверный email или пароль'
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
    """Безопасное представление пользователя (без хеша/соли)."""
    if not user:
        return None
    return {'id': user['id'], 'email': user['email'], 'tier': user['tier']}
