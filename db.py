"""Работа с базой данных SQLite (стандартный модуль sqlite3, без ORM).

Путь к файлу БД считается относительно этого файла, поэтому проект
одинаково работает локально, под XAMPP-прокси и на PythonAnywhere.
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("VEKTOR_DB") or os.path.join(BASE_DIR, "instance", "vektor.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    login         TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    phone         TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('client', 'manager', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    must_change   INTEGER NOT NULL DEFAULT 0,
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    short_title TEXT NOT NULL,
    description TEXT NOT NULL,
    art_key     TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id   INTEGER NOT NULL REFERENCES sections(id),
    slug         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    body         TEXT NOT NULL,
    author_id    INTEGER REFERENCES users(id),
    published_at TEXT NOT NULL,
    is_published INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS news (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    body         TEXT NOT NULL,
    author_id    INTEGER REFERENCES users(id),
    published_at TEXT NOT NULL,
    is_published INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS banners (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    title     TEXT NOT NULL,
    text      TEXT NOT NULL,
    link_url  TEXT NOT NULL,
    link_text TEXT NOT NULL,
    art_key   TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dialogs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  INTEGER NOT NULL REFERENCES users(id),
    subject    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dialog_id INTEGER NOT NULL REFERENCES dialogs(id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL REFERENCES users(id),
    body      TEXT NOT NULL,
    is_read   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  INTEGER NOT NULL REFERENCES users(id),
    dialog_id  INTEGER REFERENCES dialogs(id),
    event_type TEXT NOT NULL,
    event_date TEXT NOT NULL,
    guests     INTEGER NOT NULL,
    budget     TEXT NOT NULL DEFAULT '',
    comment    TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'work', 'done', 'rejected')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL,
    topic      TEXT NOT NULL,
    message    TEXT NOT NULL,
    is_handled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_section ON articles(section_id);
CREATE INDEX IF NOT EXISTS idx_messages_dialog ON messages(dialog_id);
CREATE INDEX IF NOT EXISTS idx_dialogs_client ON dialogs(client_id);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # LIKE в SQLite не умеет сравнивать регистр кириллицы, поэтому
    # поиск идёт через свою функцию приведения к нижнему регистру.
    conn.create_function("PYLOWER", 1, lambda s: s.lower() if isinstance(s, str) else s)
    return conn


def ensure_db():
    """Создаёт папку instance, схему и начальное наполнение, если БД ещё нет."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    is_new = not os.path.exists(DB_PATH)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        if is_new or conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0] == 0:
            import seed
            seed.fill(conn)
        conn.commit()
    finally:
        conn.close()
