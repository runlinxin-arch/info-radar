# -*- coding: utf-8 -*-
"""SQLite 建表与读写。"""
import os
import sqlite3
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "radar.db")

_lock = threading.Lock()


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            section TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'rss',
            url TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT,
            content TEXT,
            link TEXT NOT NULL UNIQUE,
            source TEXT,
            section TEXT NOT NULL,
            is_search_result INTEGER NOT NULL DEFAULT 0,
            published_at TEXT,
            fetched_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_items_section ON items(section, fetched_at DESC);
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            searched_at TEXT NOT NULL,
            result_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS update_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            new_count INTEGER NOT NULL DEFAULT 0,
            message TEXT
        );
        CREATE TABLE IF NOT EXISTS word_cache (
            word TEXT PRIMARY KEY,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "UPDATE update_logs SET status='interrupted', finished_at=?, "
            "message=COALESCE(message, '') || ' [进程中断，启动时自动标记]' "
            "WHERE status='running'",
            (now_str(),),
        )


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- sources ----------

def upsert_source(name, section, url, type_="rss", enabled=1):
    with _lock, _connect() as conn:
        conn.execute(
            """INSERT INTO sources (name, section, type, url, enabled)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                 name=excluded.name, section=excluded.section,
                 type=excluded.type, enabled=excluded.enabled""",
            (name, section, type_, url, enabled),
        )


def get_enabled_sources():
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sources WHERE enabled=1 ORDER BY section, id"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- items ----------

def item_exists(link):
    with _lock, _connect() as conn:
        row = conn.execute("SELECT 1 FROM items WHERE link=?", (link,)).fetchone()
    return row is not None


def insert_item(title, summary, content, link, source, section,
                published_at=None, is_search_result=0):
    with _lock, _connect() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO items
               (title, summary, content, link, source, section,
                is_search_result, published_at, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, summary, content, link, source, section,
             is_search_result, published_at, now_str()),
        )
        return cur.rowcount > 0


def get_items(section=None, limit=100, search_only=False):
    sql = "SELECT id, title, summary, link, source, section, is_search_result, published_at, fetched_at FROM items"
    conds, params = [], []
    if search_only:
        conds.append("is_search_result=1")
    elif section:
        conds.append("section=?")
        params.append(section)
        conds.append("is_search_result=0")
    else:
        conds.append("is_search_result=0")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?"
    params.append(limit)
    with _lock, _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_item(item_id):
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def get_sections():
    with _lock, _connect() as conn:
        rows = conn.execute(
            """SELECT section, COUNT(*) AS count FROM items
               WHERE is_search_result=0 GROUP BY section ORDER BY MIN(id)"""
        ).fetchall()
    return [dict(r) for r in rows]


def trim_section(section, keep):
    """每个板块只保留最新 keep 条（不含搜索结果）。"""
    with _lock, _connect() as conn:
        conn.execute(
            """DELETE FROM items WHERE section=? AND is_search_result=0 AND id NOT IN (
                 SELECT id FROM items WHERE section=? AND is_search_result=0
                 ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?)""",
            (section, section, keep),
        )


def get_recent_titles(section, days=7):
    with _lock, _connect() as conn:
        rows = conn.execute(
            """SELECT title FROM items WHERE section=?
               AND fetched_at >= datetime('now', 'localtime', ?)""",
            (section, f"-{days} days"),
        ).fetchall()
    return [r["title"] for r in rows]


def count_items():
    with _lock, _connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
        feeds = conn.execute(
            "SELECT COUNT(*) c FROM items WHERE is_search_result=0").fetchone()["c"]
    return {"total": total, "feed_items": feeds}


# ---------- searches ----------

def log_search(keyword, result_count):
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO searches (keyword, searched_at, result_count) VALUES (?, ?, ?)",
            (keyword, now_str(), result_count),
        )


# ---------- settings ----------

def get_setting(key, default=None):
    with _lock, _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


# ---------- word cache ----------

def get_word_cache(word):
    """返回缓存的结果 JSON 字符串，未命中返回 None。"""
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT result FROM word_cache WHERE word=?", (word,)).fetchone()
    return row["result"] if row else None


def set_word_cache(word, result_json):
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO word_cache (word, result, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(word) DO UPDATE SET result=excluded.result, "
            "created_at=excluded.created_at",
            (word, result_json, now_str()),
        )


# ---------- update logs ----------

def start_update_log():
    with _lock, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO update_logs (started_at, status) VALUES (?, 'running')",
            (now_str(),),
        )
        return cur.lastrowid


def finish_update_log(log_id, status, new_count, message=""):
    with _lock, _connect() as conn:
        conn.execute(
            """UPDATE update_logs SET finished_at=?, status=?, new_count=?, message=?
               WHERE id=?""",
            (now_str(), status, new_count, message, log_id),
        )


def get_last_logs(limit=10):
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM update_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
