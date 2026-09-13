import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

from config import DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                chat_id INTEGER,
                join_date TEXT,
                warning INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS menfess (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                sender_username TEXT,
                receiver_username TEXT,
                kategori TEXT,
                pesan TEXT,
                status TEXT,
                channel_message_id INTEGER,
                likes INTEGER DEFAULT 0,
                waktu TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                menfess_id INTEGER,
                reporter_id INTEGER,
                reason TEXT,
                status TEXT,
                waktu TEXT
            )
            """
        )
        conn.commit()


# ---------------- USERS ----------------

def upsert_user(telegram_id: int, username: str, chat_id: int):
    """Simpan/perbarui data user setiap kali dia /start bot (dibutuhkan agar
    bot bisa mengirim DM anonim & balasan ke user ini nanti)."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET username = ?, chat_id = ? WHERE telegram_id = ?",
                (username or "", chat_id, telegram_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (telegram_id, username, chat_id, join_date, warning, banned)
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (telegram_id, username or "", chat_id, datetime.utcnow().isoformat()),
            )
        conn.commit()


def get_user_by_username(username: str):
    username = username.lstrip("@")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_telegram_id(telegram_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def is_banned(telegram_id: int) -> bool:
    user = get_user_by_telegram_id(telegram_id)
    return bool(user and user["banned"])


def ban_user(telegram_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET banned = 1 WHERE telegram_id = ?", (telegram_id,)
        )
        conn.commit()


def unban_user(telegram_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET banned = 0 WHERE telegram_id = ?", (telegram_id,)
        )
        conn.commit()


def list_banned_users():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users WHERE banned = 1").fetchall()
        return [dict(r) for r in rows]


def list_all_chat_ids():
    """Dipakai untuk broadcast."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM users WHERE banned = 0 AND chat_id IS NOT NULL"
        ).fetchall()
        return [r["chat_id"] for r in rows]


def count_users() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_new_users_today() -> int:
    today = datetime.utcnow().date().isoformat()
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (today + "%",)
        ).fetchone()[0]


# ---------------- MENFESS ----------------

def create_menfess(sender_id, sender_username, receiver_username, kategori, pesan, status):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO menfess
                (sender_id, sender_username, receiver_username, kategori, pesan, status, waktu)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sender_id, sender_username or "", receiver_username,
                kategori, pesan, status, datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return cur.lastrowid


def set_channel_message_id(menfess_id: int, message_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE menfess SET channel_message_id = ? WHERE id = ?",
            (message_id, menfess_id),
        )
        conn.commit()


def update_menfess_status(menfess_id: int, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE menfess SET status = ? WHERE id = ?", (status, menfess_id)
        )
        conn.commit()


def get_menfess(menfess_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM menfess WHERE id = ?", (menfess_id,)
        ).fetchone()
        return dict(row) if row else None


def increment_like(menfess_id: int) -> int:
    with get_conn() as conn:
        conn.execute(
            "UPDATE menfess SET likes = likes + 1 WHERE id = ?", (menfess_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT likes FROM menfess WHERE id = ?", (menfess_id,)
        ).fetchone()
        return row["likes"]


def count_recent_by_sender(sender_id: int, minutes: int) -> int:
    since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM menfess WHERE sender_id = ? AND waktu >= ?",
            (sender_id, since),
        ).fetchone()
        return row["c"]


def seconds_since_last_sent(sender_id: int):
    """Return jumlah detik sejak menfess terakhir dikirim user ini, atau None
    kalau belum pernah kirim."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT waktu FROM menfess WHERE sender_id = ? ORDER BY id DESC LIMIT 1",
            (sender_id,),
        ).fetchone()
        if not row:
            return None
        last = datetime.fromisoformat(row["waktu"])
        return (datetime.utcnow() - last).total_seconds()


def count_menfess_total() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM menfess").fetchone()[0]


def count_menfess_today() -> int:
    today = datetime.utcnow().date().isoformat()
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM menfess WHERE waktu LIKE ?", (today + "%",)
        ).fetchone()[0]


def list_pending_menfess():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM menfess WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------- REPORTS ----------------

def create_report(menfess_id: int, reporter_id: int, reason: str):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO reports (menfess_id, reporter_id, reason, status, waktu)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (menfess_id, reporter_id, reason, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def list_pending_reports():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_report_status(report_id: int, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE reports SET status = ? WHERE id = ?", (status, report_id)
        )
        conn.commit()


def count_reports_total() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]


def count_banned_total() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
