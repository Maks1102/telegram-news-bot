"""Сборка, дедупликация и отправка дайджеста."""
import html
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app import db
from app.config import Settings
from app.rss import Article, fetch_all_feeds

logger = logging.getLogger(__name__)

TG_MESSAGE_LIMIT = 4096
SAFE_LIMIT = 4000


def _prepare(articles: list[Article], digest_size: int) -> list[dict]:
    """Внутрибатчевая дедупликация по URL и нормализованному заголовку."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict] = []

    for a in articles:
        url_hash = db.hash_url(a.url)
        title_hash = db.hash_title(a.title)
        if url_hash in seen_urls or title_hash in seen_titles:
            continue
        seen_urls.add(url_hash)
        seen_titles.add(title_hash)
        unique.append({
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "published": a.published,
            "url_hash": url_hash,
            "title_hash": title_hash,
        })

    # Свежие сверху; статьи без даты — в конец
    unique.sort(key=lambda a: a["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return unique[:digest_size]


async def collect_new_articles(settings: Settings) -> list[dict]:
    raw = await fetch_all_feeds(settings.feed_list, timeout=settings.request_timeout)
    candidates = _prepare(raw, settings.digest_size * 3)  # берём с запасом до фильтра по БД

    known_urls, known_titles = await db.filter_new_hashes(
        settings.database_path,
        [a["url_hash"] for a in candidates],
        [a["title_hash"] for a in candidates],
    )
    fresh = [
        a for a in candidates
        if a["url_hash"] not in known_urls and a["title_hash"] not in known_titles
    ]
    logger.info("Собрано %d кандидатов, новых после дедупликации: %d", len(candidates), len(fresh))
    return fresh[: settings.digest_size]


def format_digest(articles: list[dict]) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    if not articles:
        return f"📭 <b>Сводка новостей</b>\n<i>{today}</i>\n\nНовых новостей за неделю не нашлось."

    lines = [f"📰 <b>Сводка новостей за неделю</b>", f"<i>{today}</i>", ""]
    for i, a in enumerate(articles, 1):
        title = html.escape(a["title"])
        url = html.escape(a["url"], quote=True)
        source = f" — <i>{html.escape(a['source'])}</i>" if a.get("source") else ""
        date = f" · {a['published'].strftime('%d.%m')}" if a.get("published") else ""
        lines.append(f'{i}. <a href="{url}">{title}</a>{source}{date}')
    lines += ["", f"Показано новых статей: <b>{len(articles)}</b>"]
    return "\n".join(lines)


def _split_message(text: str) -> list[str]:
    """Разбивает сообщение по строкам так, чтобы уложиться в лимит Telegram."""
    if len(text) <= TG_MESSAGE_LIMIT:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > SAFE_LIMIT and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def send_digest(bot: Bot, chat_id: int, settings: Settings, *, mark_sent: bool = True) -> int:
    """Собирает и отправляет дайджест. Возвращает число отправленных статей."""
    articles = await collect_new_articles(settings)
    text = format_digest(articles)

    for chunk in _split_message(text):
        try:
            await bot.send_message(chat_id, chunk, disable_web_page_preview=True)
        except TelegramAPIError:
            logger.exception("Не удалось отправить сообщение в чат %s", chat_id)
            raise

    if mark_sent and articles:
        inserted = await db.save_articles(settings.database_path, articles)
        logger.info("В SQLite сохранено %d статей", inserted)
    return len(articles)
