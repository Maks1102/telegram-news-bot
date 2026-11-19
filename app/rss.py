"""Асинхронная загрузка и разбор RSS-фидов."""
import asyncio
import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp
import feedparser

logger = logging.getLogger(__name__)

_USER_AGENT = "telegram-news-bot/1.0 (+https://t.me/)"


@dataclass(slots=True)
class Article:
    title: str
    url: str
    source: str
    published: datetime | None


def _parse_published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    except (OverflowError, ValueError, TypeError):
        return None


def _parse_feed(content: bytes, feed_url: str) -> list[Article]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Не удалось разобрать фид {feed_url}: {parsed.bozo_exception}")
    source = (parsed.feed.get("title") if parsed.feed else None) or feed_url

    articles: list[Article] = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        articles.append(Article(
            title=title,
            url=link,
            source=str(source).strip(),
            published=_parse_published(entry),
        ))
    return articles


async def _fetch_one(session: aiohttp.ClientSession, feed_url: str) -> list[Article]:
    async with session.get(feed_url) as resp:
        resp.raise_for_status()
        content = await resp.read()
    # feedparser синхронный, но разбор небольшого фида — миллисекунды
    return _parse_feed(content, feed_url)


async def fetch_all_feeds(feed_urls: list[str], timeout: int = 15) -> list[Article]:
    """Скачивает все фиды конкурентно. Упавший фид не роняет остальные."""
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"}

    async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as session:
        results = await asyncio.gather(
            *(_fetch_one(session, url) for url in feed_urls),
            return_exceptions=True,
        )

    articles: list[Article] = []
    for url, result in zip(feed_urls, results):
        if isinstance(result, Exception):
            logger.warning("Фид %s пропущен: %s", url, result)
            continue
        logger.info("Фид %s: %d статей", url, len(result))
        articles.extend(result)
    return articles
