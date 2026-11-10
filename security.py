"""Безопасность учебного уровня: хеши паролей, CSRF-токены, проверка ролей."""
import re
import secrets
import time
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from app_hash import hash_password, verify_password  # noqa: F401

ROLE_TITLES = {"client": "Клиент", "manager": "Менеджер", "admin": "Администратор"}

LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def password_problem(password):
    """Возвращает текст ошибки по-русски или None, если пароль подходит."""
    if len(password) < 8:
        return "Пароль должен содержать не менее 8 символов."
    if not re.search(r"[A-Za-zА-Яа-яЁё]", password) or not re.search(r"\d", password):
        return "Пароль должен содержать и буквы, и цифры."
    return None


def generate_password(length=10):
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        if password_problem(value) is None:
            return value


# ---------- CSRF ----------

def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def check_csrf():
    sent = request.form.get("csrf_token", "")
    expected = session.get("_csrf", "")
    if not expected or not secrets.compare_digest(sent, expected):
        abort(400, description="csrf")


# ---------- роли ----------

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ---------- ограничение числа неудачных входов (в памяти процесса) ----------

_failed = {}
MAX_FAILS = 5
WINDOW = 300


def too_many_attempts(key):
    now = time.time()
    attempts = [t for t in _failed.get(key, []) if now - t < WINDOW]
    _failed[key] = attempts
    return len(attempts) >= MAX_FAILS


def register_fail(key):
    _failed.setdefault(key, []).append(time.time())


def clear_fails(key):
    _failed.pop(key, None)
