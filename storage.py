import sqlite3
from cryptography.fernet import Fernet
from config import ENCRYPTION_KEY

_fernet = Fernet(ENCRYPTION_KEY.encode())
DB_PATH = "repopilot.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                github_login TEXT,
                token_enc BLOB NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )


def track_user(user):
    """Record a Telegram user without requiring them to connect GitHub."""
    with _conn() as c:
        c.execute(
            """INSERT INTO bot_users (telegram_id, username, first_name, last_name)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   username = excluded.username,
                   first_name = excluded.first_name,
                   last_name = excluded.last_name,
                   last_seen = CURRENT_TIMESTAMP""",
            (user.id, user.username, user.first_name, user.last_name),
        )


def get_bot_users():
    with _conn() as c:
        count = c.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        rows = c.execute(
            "SELECT telegram_id, username, first_name, last_name "
            "FROM bot_users ORDER BY first_seen"
        ).fetchall()
    return count, rows


def save_token(telegram_id: int, github_login: str, token: str):
    enc = _fernet.encrypt(token.encode())
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO users (telegram_id, github_login, token_enc) VALUES (?, ?, ?)",
            (telegram_id, github_login, enc),
        )


def get_token(telegram_id: int):
    with _conn() as c:
        row = c.execute(
            "SELECT token_enc FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    if not row:
        return None
    return _fernet.decrypt(row[0]).decode()


def get_login(telegram_id: int):
    with _conn() as c:
        row = c.execute(
            "SELECT github_login FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return row[0] if row else None


def delete_user(telegram_id: int):
    with _conn() as c:
        c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))


def init_db():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                github_login TEXT,
                token_enc BLOB NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS watches (
                chat_id INTEGER,
                repo TEXT,
                hook_id INTEGER,
                PRIMARY KEY (chat_id, repo)
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS digest_subs (
                telegram_id INTEGER PRIMARY KEY
            )"""
        )


# ---------- watches ----------

def add_watch(chat_id: int, repo: str, hook_id: int):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO watches (chat_id, repo, hook_id) VALUES (?, ?, ?)",
            (chat_id, repo.lower(), hook_id),
        )


def get_watch(chat_id: int, repo: str):
    with _conn() as c:
        row = c.execute(
            "SELECT hook_id FROM watches WHERE chat_id = ? AND repo = ?",
            (chat_id, repo.lower()),
        ).fetchone()
    return row[0] if row else None


def remove_watch(chat_id: int, repo: str):
    with _conn() as c:
        c.execute(
            "DELETE FROM watches WHERE chat_id = ? AND repo = ?", (chat_id, repo.lower())
        )


def list_watches(chat_id: int):
    with _conn() as c:
        rows = c.execute(
            "SELECT repo FROM watches WHERE chat_id = ?", (chat_id,)
        ).fetchall()
    return [r[0] for r in rows]


# ---------- digest ----------

def set_digest(telegram_id: int, on: bool):
    with _conn() as c:
        if on:
            c.execute("INSERT OR IGNORE INTO digest_subs (telegram_id) VALUES (?)", (telegram_id,))
        else:
            c.execute("DELETE FROM digest_subs WHERE telegram_id = ?", (telegram_id,))


def is_digest_on(telegram_id: int) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM digest_subs WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return bool(row)


def list_digest_subs():
    with _conn() as c:
        rows = c.execute("SELECT telegram_id FROM digest_subs").fetchall()
    return [r[0] for r in rows]