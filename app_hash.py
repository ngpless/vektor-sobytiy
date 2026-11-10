"""Хеширование паролей без зависимости от Flask-приложения (используется и скриптом наполнения БД).

Алгоритм: scrypt (hashlib.scrypt) через werkzeug.security, соль генерируется автоматически
и хранится в самой строке хеша. Открытые пароли в БД не хранятся.
"""
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    return generate_password_hash(password, method="scrypt")


def verify_password(stored_hash, password):
    return check_password_hash(stored_hash, password)
