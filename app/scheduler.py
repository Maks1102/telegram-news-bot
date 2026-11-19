"""Недельный дайджест по расписанию (APScheduler, AsyncIOScheduler)."""
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings
from app.digest import send_digest

logger = logging.getLogger(__name__)


async def weekly_digest_job(bot: Bot, settings: Settings) -> None:
    logger.info("Запуск еженедельной сборки дайджеста")
    try:
        sent = await send_digest(bot, settings.chat_id, settings)
        logger.info("Дайджест отправлен в чат %s (%d статей)", settings.chat_id, sent)
    except Exception:
        logger.exception("Ошибка при отправке еженедельного дайджеста")


def create_scheduler(bot: Bot, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        weekly_digest_job,
        CronTrigger(
            day_of_week=settings.schedule_day,
            hour=settings.schedule_hour,
            minute=settings.schedule_minute,
            timezone=settings.timezone,
        ),
        args=[bot, settings],
        id="weekly_digest",
        name="Еженедельный RSS-дайджест",
        replace_existing=True,
        coalesce=True,          # пропущенные запуски объединяются в один
        max_instances=1,
        misfire_grace_time=3600,
    )
    return scheduler
