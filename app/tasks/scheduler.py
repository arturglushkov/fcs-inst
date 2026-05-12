"""
Фоновые задачи — APScheduler.
Запускаются при старте приложения.
"""

from __future__ import annotations
import logging
from datetime import datetime, date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database.engine import async_session_factory
from app.core.cache.redis_client import redis_client
from app.repositories.repositories import (
    ShiftRepository, UserRepository, NotificationRepository,
    TaskRepository,
)
from app.models.models import (
    ShiftStatus, TaskStatus, NotificationType, Notification,
)

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


# ══════════════════════════════════════════════════════════════════
#  LIVE TRACKING — каждые 15 минут
# ══════════════════════════════════════════════════════════════════

async def request_location_updates() -> None:
    """
    Запрашивает геолокацию у всех сотрудников с активными сменами.
    Бот отправляет им сообщение с просьбой поделиться локацией.
    """
    from aiogram import Bot
    from app.core.config.settings import settings

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        async with async_session_factory() as session:
            shift_repo = ShiftRepository(session)
            active_shifts = await shift_repo.get_active_employees_today()

            for shift in active_shifts:
                try:
                    from app.bot.keyboards.keyboards import kb_request_location
                    await bot.send_message(
                        chat_id=shift.employee.telegram_id,
                        text="📍 Отправь свою геолокацию для трекинга смены.",
                        reply_markup=kb_request_location(),
                    )
                except Exception as e:
                    logger.warning(f"Failed to request location from {shift.employee_id}: {e}")
    finally:
        await bot.session.close()


# ══════════════════════════════════════════════════════════════════
#  NO-SHOW CHECK — каждый день в 09:30
# ══════════════════════════════════════════════════════════════════

async def check_no_shows() -> None:
    """
    Проверяет кто запланирован на сегодня но ещё не начал смену.
    Уведомляет менеджеров.
    """
    from app.core.config.settings import settings

    async with async_session_factory() as session:
        shift_repo = ShiftRepository(session)
        user_repo  = UserRepository(session)
        notif_repo = NotificationRepository(session)

        employees = await user_repo.get_all_employees(active_only=True)
        today_shifts = await shift_repo.get_active_employees_today()
        active_employee_ids = {s.employee_id for s in today_shifts}

        managers = await user_repo.get_all_managers()
        manager_ids = [m.id for m in managers]

        for emp in employees:
            if emp.id not in active_employee_ids:
                for manager_id in manager_ids:
                    notif = Notification(
                        recipient_id=manager_id,
                        notification_type=NotificationType.NO_SHOW,
                        title="❗ Не вышел на работу",
                        body=f"{emp.full_name} не начал смену. Сейчас {datetime.now().strftime('%H:%M')}",
                        extra_data={"employee_id": emp.id},
                    )
                    await notif_repo.save(notif)

        logger.info(f"No-show check done. Active: {len(active_employee_ids)}, Total: {len(employees)}")


# ══════════════════════════════════════════════════════════════════
#  OVERDUE TASKS — каждый час
# ══════════════════════════════════════════════════════════════════

async def check_overdue_tasks() -> None:
    async with async_session_factory() as session:
        task_repo  = TaskRepository(session)
        notif_repo = NotificationRepository(session)

        overdue = await task_repo.get_overdue_tasks()
        for task in overdue:
            if task.status != TaskStatus.OVERDUE:
                task.status = TaskStatus.OVERDUE
                await task_repo.save(task)

                if task.assignee_id:
                    notif = Notification(
                        recipient_id=task.assignee_id,
                        notification_type=NotificationType.TASK_OVERDUE,
                        title="🔴 Просроченная задача",
                        body=f"Задача «{task.title}» просрочена!\nДедлайн был: {task.deadline.strftime('%d.%m %H:%M')}",
                        extra_data={"task_id": task.id},
                    )
                    await notif_repo.save(notif)

        logger.info(f"Overdue tasks check: {len(overdue)} tasks updated")


# ══════════════════════════════════════════════════════════════════
#  SEND PENDING NOTIFICATIONS — каждую минуту
# ══════════════════════════════════════════════════════════════════

async def send_pending_notifications() -> None:
    """Отправляет все неотправленные уведомления через бот."""
    from aiogram import Bot
    from app.core.config.settings import settings

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        async with async_session_factory() as session:
            notif_repo = NotificationRepository(session)
            pending = await notif_repo.get_unsent(limit=50)

            for notif in pending:
                try:
                    await bot.send_message(
                        chat_id=notif.recipient.telegram_id,
                        text=f"<b>{notif.title}</b>\n\n{notif.body}",
                        parse_mode="HTML",
                    )
                    await notif_repo.mark_sent(notif.id)
                except Exception as e:
                    logger.warning(f"Failed to send notification {notif.id}: {e}")
    finally:
        await bot.session.close()


# ══════════════════════════════════════════════════════════════════
#  WEEKLY REPORT — каждый понедельник в 08:00
# ══════════════════════════════════════════════════════════════════

async def send_weekly_reports() -> None:
    """Отправляет недельный отчёт всем менеджерам."""
    from aiogram import Bot
    from app.core.config.settings import settings
    from app.services.services import ReportService

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            report_svc = ReportService(session)
            managers = await user_repo.get_all_managers()

            today = date.today()
            last_week_start = today - timedelta(days=7 + today.weekday())
            last_week_end   = last_week_start + timedelta(days=6)
            data = await report_svc.get_monthly_summary(today.year, today.month)

            text = (
                f"📊 <b>Недельный отчёт</b>\n"
                f"{last_week_start.strftime('%d.%m')} — {last_week_end.strftime('%d.%m')}\n\n"
            )
            for i, row in enumerate(data[:10], 1):
                text += f"{i}. {row['employee']} — {row['hours']:.1f} ч.\n"

            for manager in managers:
                try:
                    await bot.send_message(
                        chat_id=manager.telegram_id,
                        text=text,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"Failed to send weekly report to {manager.id}: {e}")
    finally:
        await bot.session.close()


# ══════════════════════════════════════════════════════════════════
#  SETUP SCHEDULER
# ══════════════════════════════════════════════════════════════════

def setup_scheduler() -> AsyncIOScheduler:
    scheduler.add_job(
        request_location_updates,
        trigger=IntervalTrigger(minutes=15),
        id="live_tracking",
        replace_existing=True,
    )
    scheduler.add_job(
        check_no_shows,
        trigger=CronTrigger(hour=9, minute=30),
        id="no_show_check",
        replace_existing=True,
    )
    scheduler.add_job(
        check_overdue_tasks,
        trigger=IntervalTrigger(hours=1),
        id="overdue_tasks",
        replace_existing=True,
    )
    scheduler.add_job(
        send_pending_notifications,
        trigger=IntervalTrigger(minutes=1),
        id="send_notifications",
        replace_existing=True,
    )
    scheduler.add_job(
        send_weekly_reports,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_reports",
        replace_existing=True,
    )
    logger.info("Scheduler configured with 5 jobs")
    return scheduler
