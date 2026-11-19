"""Обработчики команд бота."""
import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app import db
from app.config import get_settings
from app.digest import send_digest

logger = logging.getLogger(__name__)

router = Router(name="main")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    settings = get_settings()
    await message.answer(
        "👋 Привет! Я присылаю еженедельную сводку новостей из RSS.\n\n"
        f"Этот чат: <code>{message.chat.id}</code>\n"
        f"Рассылка: каждый <b>{settings.schedule_day}</b> в <b>{settings.schedule_time}</b> ({settings.timezone})\n\n"
        "Команды:\n"
        "/digest — получить сводку прямо сейчас\n"
        "/stats — статистика отправленного\n"
        "/help — справка"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Что я умею</b>\n"
        "• Раз в неделю собираю статьи из настроенных RSS-фидов\n"
        "• Отсеиваю дубликаты (по URL и нормализованному заголовку) через SQLite\n"
        f"• Присылаю сводку из {get_settings().digest_size} заголовков со ссылками\n\n"
        "<b>Команды</b>\n"
        "/digest — собрать и отправить сводку сейчас\n"
        "/stats — сколько статей уже отправлено\n"
        "/help — эта справка"
    )


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    settings = get_settings()
    status = await message.answer("⏳ Собираю свежие новости…")
    try:
        await send_digest(message.bot, message.chat.id, settings)
    except Exception:
        logger.exception("Ошибка ручной сборки дайджеста")
        await message.answer("⚠️ Не удалось собрать дайджест. Подробности в логах.")
    finally:
        try:
            await status.delete()
        except Exception:
            pass


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    settings = get_settings()
    try:
        s = await db.stats(settings.database_path)
    except Exception:
        logger.exception("Ошибка чтения статистики")
        await message.answer("⚠️ Не удалось прочитать статистику.")
        return
    await message.answer(
        "📊 <b>Статистика</b>\n"
        f"Всего отправлено статей: <b>{s['total']}</b>\n"
        f"За последние 7 дней: <b>{s['last_week']}</b>\n"
        f"Последняя отправка: <b>{s['last_sent'] or '—'}</b>"
    )
