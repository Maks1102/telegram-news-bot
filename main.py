"""Точка входа: инициализация БД, планировщика и polling."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.db import init_db, prune_old
from app.handlers import router
from app.logging_config import setup_logging
from app.scheduler import create_scheduler


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    logger.info("Запуск Telegram News Bot…")
    await init_db(settings.database_path)
    deleted = await prune_old(settings.database_path, settings.retention_days)
    if deleted:
        logger.info("Удалено %d устаревших записей из БД", deleted)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = create_scheduler(bot, settings)
    scheduler.start()
    logger.info(
        "Планировщик запущен: каждый %s в %s (%s)",
        settings.schedule_day, settings.schedule_time, settings.timezone,
    )

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
