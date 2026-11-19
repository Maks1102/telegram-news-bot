"""SQLite-хранилище для дедупликации статей (aiosqlite)."""
import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash    TEXT NOT NULL UNIQUE,
    title_hash  TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    source      TEXT,
    published   TEXT,
    sent_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_articles_title_hash ON articles(title_hash);
CREATE INDEX IF NOT EXISTS idx_articles_sent_at    ON articles(sent_at);
"""

_UTM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src"}


def normalize_url(url: str) -> str:
    """Нормализует URL для стабильного хэширования."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parts.path or "/").rstrip("/") or "/"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(_UTM_PREFIXES) and k.lower() not in _TRACKING_PARAMS
    ]
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


_TITLE_CLEAN_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Нормализует заголовок: регистр, пунктуация, пробелы."""
    text = unicodedata.normalize("NFKC", title).lower()
    text = _TITLE_CLEAN_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def hash_url(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def hash_title(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()


async def init_db(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def filter_new_hashes(path: str, url_hashes: list[str], title_hashes: list[str]) -> tuple[set[str], set[str]]:
    """Возвращает (известные url_hash, известные title_hash) для списка хэшей."""
    known_urls: set[str] = set()
    known_titles: set[str] = set()
    if not url_hashes and not title_hashes:
        return known_urls, known_titles

    async with aiosqlite.connect(path) as db:
        if url_hashes:
            placeholders = ",".join("?" * len(url_hashes))
            cur = await db.execute(
                f"SELECT url_hash FROM articles WHERE url_hash IN ({placeholders})", url_hashes
            )
            known_urls = {row[0] for row in await cur.fetchall()}
        if title_hashes:
            placeholders = ",".join("?" * len(title_hashes))
            cur = await db.execute(
                f"SELECT title_hash FROM articles WHERE title_hash IN ({placeholders})", title_hashes
            )
            known_titles = {row[0] for row in await cur.fetchall()}
    return known_urls, known_titles


async def save_articles(path: str, articles: list[dict]) -> int:
    """Сохраняет отправленные статьи. Возвращает число вставленных строк."""
    if not articles:
        return 0
    rows = [
        (
            a["url_hash"],
            a["title_hash"],
            a["title"],
            a["url"],
            a.get("source"),
            a["published"].isoformat() if a.get("published") else None,
        )
        for a in articles
    ]
    async with aiosqlite.connect(path) as db:
        cur = await db.executemany(
            """
            INSERT OR IGNORE INTO articles (url_hash, title_hash, title, url, source, published)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await db.commit()
        return cur.rowcount if cur.rowcount is not None else len(rows)


async def prune_old(path: str, retention_days: int) -> int:
    """Удаляет записи старше retention_days. Возвращает число удалённых строк."""
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "DELETE FROM articles WHERE sent_at < datetime('now', ?)", (f"-{retention_days} days",)
        )
        await db.commit()
        return cur.rowcount if cur.rowcount is not None else 0


async def stats(path: str) -> dict:
    async with aiosqlite.connect(path) as db:
        total = (await (await db.execute("SELECT COUNT(*) FROM articles")).fetchone())[0]
        last_week = (
            await (await db.execute(
                "SELECT COUNT(*) FROM articles WHERE sent_at >= datetime('now', '-7 days')"
            )).fetchone()
        )[0]
        last_sent = (
            await (await db.execute("SELECT MAX(sent_at) FROM articles")).fetchone()
        )[0]
    return {"total": total, "last_week": last_week, "last_sent": last_sent}
