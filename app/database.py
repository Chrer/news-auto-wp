from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from .text_utils import canonical_url, title_key, safe_slug

DB_PATH = Path(__file__).resolve().parent.parent / "news_auto.db"


def get_conn():
    return sqlite3.connect(DB_PATH)


def _columns(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_url TEXT UNIQUE NOT NULL,
                normalized_url TEXT,
                title TEXT NOT NULL,
                title_key TEXT,
                slug TEXT,
                source_name TEXT,
                wordpress_post_id INTEGER,
                wordpress_status TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cols = _columns(conn, "processed_posts")
        migrations = {
            "normalized_url": "ALTER TABLE processed_posts ADD COLUMN normalized_url TEXT",
            "title_key": "ALTER TABLE processed_posts ADD COLUMN title_key TEXT",
            "slug": "ALTER TABLE processed_posts ADD COLUMN slug TEXT",
            "wordpress_status": "ALTER TABLE processed_posts ADD COLUMN wordpress_status TEXT",
        }
        for col, sql in migrations.items():
            if col not in cols:
                conn.execute(sql)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_normalized_url ON processed_posts(normalized_url)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_title_key ON processed_posts(title_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_slug ON processed_posts(slug)")

        # Rellena columnas nuevas para registros antiguos.
        rows = conn.execute("SELECT id, original_url, title FROM processed_posts WHERE normalized_url IS NULL OR title_key IS NULL OR slug IS NULL").fetchall()
        for row_id, url, title in rows:
            conn.execute(
                "UPDATE processed_posts SET normalized_url = ?, title_key = ?, slug = ? WHERE id = ?",
                (canonical_url(url), title_key(title), safe_slug(title), row_id),
            )
        conn.commit()


def already_processed(url: str, title: str | None = None) -> bool:
    norm = canonical_url(url)
    tkey = title_key(title) if title else ""
    slug = safe_slug(title) if title else ""
    with get_conn() as conn:
        if norm:
            cur = conn.execute(
                "SELECT 1 FROM processed_posts WHERE original_url = ? OR normalized_url = ? LIMIT 1",
                (url, norm),
            )
            if cur.fetchone() is not None:
                return True
        if tkey:
            cur = conn.execute("SELECT 1 FROM processed_posts WHERE title_key = ? LIMIT 1", (tkey,))
            if cur.fetchone() is not None:
                return True
        if slug:
            cur = conn.execute("SELECT 1 FROM processed_posts WHERE slug = ? LIMIT 1", (slug,))
            if cur.fetchone() is not None:
                return True
    return False


def mark_processed(url: str, title: str, source_name: str, wordpress_post_id: int | None, wordpress_status: str | None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO processed_posts
            (original_url, normalized_url, title, title_key, slug, source_name, wordpress_post_id, wordpress_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                canonical_url(url),
                title,
                title_key(title),
                safe_slug(title),
                source_name,
                wordpress_post_id,
                wordpress_status,
                datetime.now(timezone.utc).isoformat(),
            ),
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
