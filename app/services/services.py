"""
Services Layer — вся бизнес-логика.
"""

from __future__ import annotations
import math
import uuid
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.repositories import (
    UserRepository, SiteObjectRepository, ShiftRepository,
    LocationLogRepository, TaskRepository, PhotoRepository,
    NotificationRepository, AuditLogRepository,
)
from app.models.models import (
    User, SiteObject, Shift, Task, Photo, Notification,
    UserRole, ShiftStatus, TaskStatus, PhotoType, NotificationType,
)
from app.core.config.settings import settings
from app.core.cache.redis_client import redis_client

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  GEO SERVICE
# ══════════════════════════════════════════════════════════════════

class GeoService:
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Расстояние между двумя точками в метрах (формула Хаверсина)."""
        R = 6_371_000  # радиус Земли в метрах
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    @staticmethod
    def is_within_radius(
        user_lat: float,
        user_lon: float,
        site_lat: float,
        site_lon: float,
        radius_meters: int,
    ) -> Tuple[bool, float]:
        """Возвращает (в_радиусе, расстояние_метров)."""
        dist = GeoService.haversine_distance(user_lat, user_lon, site_lat, site_lon)
        return dist <= radius_meters, round(dist)


geo_service = GeoService()


# ══════════════════════════════════════════════════════════════════
#  USER SERVICE
# ══════════════════════════════════════════════════════════════════

class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = UserRepository(session)
        self.audit = AuditLogRepository(session)

    async def get_or_create(
        self,
        telegram_id: int,
        first_name: str,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
        language_code: str = "ru",
    ) -> Tuple[User, bool]:
        """Возвращает (user, created)."""
        user = await self.repo.get_by_telegram_id(telegram_id)
        if user:
            await self.repo.update_last_seen(telegram_id)
            return user, False
        user = await self.repo.create(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            language_code=language_code,
        )
        await self.audit.log("create", "user", user.id, new_value={"telegram_id": telegram_id})
        return user, True

    async def register_phone(self, telegram_id: int, phone: str) -> Optional[User]:
        user = await self.repo.get_by_telegram_id(telegram_id)
        if not user:
            return None
        existing = await self.repo.get_by_phone(phone)
        if existing and existing.id != user.id:
            return None  # телефон уже занят
        user.phone = phone
        return await self.repo.save(user)

    async def set_role(self, user_id: int, role: UserRole, by_user_id: int) -> Optional[User]:
        user = await self.repo.get_by_id(user_id)
        if not user:
            return None
        old_role = user.role
        user.role = role
        await self.repo.save(user)
        await self.audit.log("update_role", "user", user_id,
                             user_id=by_user_id,
                             old_value={"role": old_role},
                             new_value={"role": role})
        return user

    async def deactivate(self, user_id: int) -> None:
        user = await self.repo.get_by_id(user_id)
        if user:
            user.is_active = False
            await self.repo.save(user)


# ══════════════════════════════════════════════════════════════════
#  SHIFT SERVICE
# ══════════════════════════════════════════════════════════════════

class ShiftService:
    def __init__(self, session: AsyncSession) -> None:
        self.shift_repo    = ShiftRepository(session)
        self.location_repo = LocationLogRepository(session)
        self.notif_repo    = NotificationRepository(session)
        self.obj_repo      = SiteObjectRepository(session)

    async def can_start_shift(
        self,
        employee: User,
        site_object: SiteObject,
        user_lat: float,
        user_lon: float,
    ) -> Tuple[bool, str]:
        """Проверяет можно ли начать смену."""
        # Уже есть активная смена?
        active = await self.shift_repo.get_active_shift(employee.id)
        if active:
            return False, "⚠️ У тебя уже есть активная смена. Сначала заверши её."

        # Геолокация
        in_radius, distance = geo_service.is_within_radius(
            user_lat, user_lon,
            site_object.latitude, site_object.longitude,
            site_object.radius_meters,
        )
        if not in_radius:
            return False, (
                f"📍 Ты находишься в {distance}м от объекта.\n"
                f"Допустимый радиус: {site_object.radius_meters}м.\n"
                f"Подойди ближе к объекту и попробуй снова."
            )

        return True, "OK"

    async def start_shift(
        self,
        employee: User,
        site_object: SiteObject,
        user_lat: float,
        user_lon: float,
        schedule_start: Optional[str] = None,
    ) -> Shift:
        is_late = False
        late_minutes = 0

        if schedule_start:
            planned = datetime.strptime(schedule_start, "%H:%M").replace(
                year=datetime.now().year,
                month=datetime.now().month,
                day=datetime.now().day,
            )
            delta = (datetime.now() - planned).total_seconds() / 60
            if delta > settings.NOTIFY_LATE_MINUTES:
                is_late = True
                late_minutes = int(delta)

        shift = await self.shift_repo.start_shift(
            employee_id=employee.id,
            site_object_id=site_object.id,
            lat=user_lat,
            lon=user_lon,
            is_late=is_late,
            late_minutes=late_minutes,
        )

        await self.location_repo.log_location(
            employee_id=employee.id,
            lat=user_lat,
            lon=user_lon,
            shift_id=shift.id,
            is_on_site=True,
        )

        await redis_client.update_employee_location(employee.id, user_lat, user_lon)

        if is_late and site_object.manager_id:
            await self._create_notification(
                recipient_id=site_object.manager_id,
                notif_type=NotificationType.LATE,
                title="⏰ Опоздание",
                body=f"{employee.full_name} опоздал на {late_minutes} мин.\nОбъект: {site_object.name}",
                extra_data={"shift_id": shift.id, "employee_id": employee.id},
            )
        else:
            if site_object.manager_id:
                await self._create_notification(
                    recipient_id=site_object.manager_id,
                    notif_type=NotificationType.ARRIVED,
                    title="✅ Сотрудник прибыл",
                    body=f"{employee.full_name} начал смену.\nОбъект: {site_object.name}",
                    extra_data={"shift_id": shift.id},
                )
        return shift

    async def end_shift(
        self,
        shift: Shift,
        employee: User,
        user_lat: float,
        user_lon: float,
    ) -> Shift:
        shift = await self.shift_repo.end_shift(shift, user_lat, user_lon)

        await self.location_repo.log_location(
            employee_id=employee.id,
            lat=user_lat,
            lon=user_lon,
            shift_id=shift.id,
            is_on_site=True,
        )

        obj = await self.obj_repo.get_by_id(shift.site_object_id)
        if obj and obj.manager_id:
            hours = float(shift.total_hours or 0)
            await self._create_notification(
                recipient_id=obj.manager_id,
                notif_type=NotificationType.LEFT,
                title="🏁 Смена завершена",
                body=(
                    f"{employee.full_name} закончил смену.\n"
                    f"Объект: {obj.name}\n"
                    f"Отработано: {hours:.1f} ч."
                ),
                extra_data={"shift_id": shift.id, "hours": hours},
            )

            if shift.overtime_hours and float(shift.overtime_hours) > 0:
                await self._create_notification(
                    recipient_id=obj.manager_id,
                    notif_type=NotificationType.OVERTIME,
                    title="🔴 Переработка",
                    body=(
                        f"{employee.full_name}: переработка {float(shift.overtime_hours):.1f} ч.\n"
                        f"Объект: {obj.name}"
                    ),
                )

        return shift

    async def check_employee_location(
        self,
        employee_id: int,
        shift: Shift,
        user_lat: float,
        user_lon: float,
    ) -> None:
        """Live tracking: проверяем геолокацию во время смены."""
        obj = await self.obj_repo.get_by_id(shift.site_object_id)
        if not obj:
            return

        in_radius, distance = geo_service.is_within_radius(
            user_lat, user_lon,
            obj.latitude, obj.longitude,
            obj.radius_meters + 50,  # чуть мягче для трекинга
        )

        await self.location_repo.log_location(
            employee_id=employee_id,
            lat=user_lat,
            lon=user_lon,
            shift_id=shift.id,
            is_on_site=in_radius,
        )
        await redis_client.update_employee_location(employee_id, user_lat, user_lon)

        if not in_radius and obj.manager_id:
            await self._create_notification(
                recipient_id=obj.manager_id,
                notif_type=NotificationType.LEFT_SITE,
                title="🚨 Сотрудник покинул объект",
                body=(
                    f"Сотрудник #{employee_id} находится в {distance}м от объекта!\n"
                    f"Объект: {obj.name}"
                ),
            )

    async def _create_notification(
        self,
        recipient_id: int,
        notif_type: NotificationType,
        title: str,
        body: str,
        extra_data: Optional[dict] = None,
    ) -> None:
        notif = Notification(
            recipient_id=recipient_id,
            notification_type=notif_type,
            title=title,
            body=body,
            extra_data=extra_data,
        )
        await self.notif_repo.save(notif)


# ══════════════════════════════════════════════════════════════════
#  TASK SERVICE
# ══════════════════════════════════════════════════════════════════

class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.task_repo  = TaskRepository(session)
        self.notif_repo = NotificationRepository(session)

    async def create_task(
        self,
        creator_id: int,
        title: str,
        assignee_id: int,
        site_object_id: Optional[int] = None,
        description: Optional[str] = None,
        deadline: Optional[datetime] = None,
        priority: str = "medium",
    ) -> Task:
        from app.models.models import TaskPriority
        task = Task(
            title=title,
            description=description,
            creator_id=creator_id,
            assignee_id=assignee_id,
            site_object_id=site_object_id,
            deadline=deadline,
            priority=TaskPriority(priority),
        )
        task = await self.task_repo.save(task)

        await self.notif_repo.save(Notification(
            recipient_id=assignee_id,
            notification_type=NotificationType.ARRIVED,  # reuse as "new task"
            title="📋 Новая задача",
            body=f"Тебе назначена задача: {title}\nДедлайн: {deadline.strftime('%d.%m %H:%M') if deadline else 'не указан'}",
            extra_data={"task_id": task.id},
        ))
        return task

    async def complete_task(
        self,
        task_id: int,
        employee_id: int,
        report: Optional[str] = None,
    ) -> Optional[Task]:
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.assignee_id != employee_id:
            return None
        task.status = TaskStatus.DONE
        task.completed_at = datetime.utcnow()
        task.completion_report = report
        return await self.task_repo.save(task)

    async def get_employee_tasks(self, employee_id: int) -> Sequence[Task]:
        return await self.task_repo.get_tasks_for_employee(employee_id)


# ══════════════════════════════════════════════════════════════════
#  REPORT SERVICE
# ══════════════════════════════════════════════════════════════════

class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.shift_repo = ShiftRepository(session)
        self.user_repo  = UserRepository(session)

    async def get_weekly_report(self, employee_id: int) -> dict:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = today

        shifts = await self.shift_repo.get_shifts_by_employee(
            employee_id, date_from=week_start, date_to=week_end
        )
        total_hours = sum(float(s.total_hours or 0) for s in shifts)
        overtime    = sum(float(s.overtime_hours or 0) for s in shifts)
        late_count  = sum(1 for s in shifts if s.is_late)

        return {
            "period": f"{week_start.strftime('%d.%m')} — {week_end.strftime('%d.%m')}",
            "total_shifts": len(shifts),
            "total_hours": round(total_hours, 1),
            "overtime_hours": round(overtime, 1),
            "late_count": late_count,
            "shifts": shifts,
        }

    async def get_monthly_summary(self, year: int, month: int) -> list[dict]:
        """Сводка по всем сотрудникам за месяц."""
        employees = await self.user_repo.get_all_employees()
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        result = []
        for emp in employees:
            hours = await self.shift_repo.get_total_hours_by_employee(
                emp.id, month_start, month_end
            )
            late = await self.shift_repo.get_late_starts_count(emp.id, month_start)
            result.append({
                "employee": emp.full_name,
                "hours": hours,
                "late_count": late,
            })
        return sorted(result, key=lambda x: x["hours"], reverse=True)


# ══════════════════════════════════════════════════════════════════
#  AI SERVICE
# ══════════════════════════════════════════════════════════════════

class AIService:
    """Анализ фотографий через OpenAI Vision API."""

    async def analyze_photo(self, image_url: str) -> dict:
        if not settings.OPENAI_API_KEY:
            return {"error": "OpenAI not configured"}
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.OPENAI_MODEL,
                "max_tokens": 500,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze this construction site photo. Return JSON with fields:\n"
                                "- has_helmet (bool): worker wearing hard hat\n"
                                "- has_vest (bool): worker wearing safety vest\n"
                                "- has_gloves (bool): worker wearing gloves\n"
                                "- progress_pct (int 0-100): estimated work completion\n"
                                "- is_work_site (bool): is this actually a work/construction site\n"
                                "- notes (string): brief description in Russian\n"
                                "Return ONLY valid JSON, no markdown."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }],
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                import json
                return json.loads(text)
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return {"error": str(e)}


ai_service = AIService()
