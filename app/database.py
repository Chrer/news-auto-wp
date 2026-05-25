import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent.parent / "news_auto.db"


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                source_name TEXT,
                wordpress_post_id INTEGER,
                wordpress_status TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Compatibilidad con versiones anteriores de la tabla
        cols = [row[1] for row in conn.execute("PRAGMA table_info(processed_posts)").fetchall()]
        if "wordpress_status" not in cols:
            conn.execute("ALTER TABLE processed_posts ADD COLUMN wordpress_status TEXT")
        conn.commit()


def already_processed(url: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("SELECT 1 FROM processed_posts WHERE original_url = ? LIMIT 1", (url,))
        return cur.fetchone() is not None


def mark_processed(url: str, title: str, source_name: str, wordpress_post_id: int | None, wordpress_status: str | None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO processed_posts
            (original_url, title, source_name, wordpress_post_id, wordpress_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, title, source_name, wordpress_post_id, wordpress_status, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def latest(limit: int = 20):
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT title, source_name, original_url, wordpress_post_id, wordpress_status, created_at
            FROM processed_posts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()
