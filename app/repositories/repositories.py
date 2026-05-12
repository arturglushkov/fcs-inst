"""
Repository Pattern — все репозитории для работы с БД.
Полная изоляция от бизнес-логики.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Sequence
from datetime import datetime, date

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.models.models import (
    User, SiteObject, EmployeeObject, Shift, LocationLog,
    Task, Photo, Notification, WorkSchedule, AuditLog,
    UserRole, ShiftStatus, TaskStatus, ObjectStatus, PhotoType,
)

T = TypeVar("T")


# ══════════════════════════════════════════════════════════════════
#  BASE REPOSITORY
# ══════════════════════════════════════════════════════════════════

class BaseRepository(Generic[T], ABC):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: int) -> Optional[T]:
        return await self.session.get(self._model, id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[T]:
        result = await self.session.execute(
            select(self._model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def save(self, obj: T) -> T:
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: T) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    @property
    @abstractmethod
    def _model(self):
        ...


# ══════════════════════════════════════════════════════════════════
#  USER REPOSITORY
# ══════════════════════════════════════════════════════════════════

class UserRepository(BaseRepository[User]):
    _model = User

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_all_employees(self, active_only: bool = True) -> Sequence[User]:
        q = select(User).where(User.role == UserRole.EMPLOYEE)
        if active_only:
            q = q.where(User.is_active == True)
        result = await self.session.execute(q)
        return result.scalars().all()

    async def get_all_managers(self) -> Sequence[User]:
        result = await self.session.execute(
            select(User).where(
                User.role.in_([UserRole.MANAGER, UserRole.OWNER]),
                User.is_active == True,
            )
        )
        return result.scalars().all()

    async def get_employees_for_object(self, site_object_id: int) -> Sequence[User]:
        result = await self.session.execute(
            select(User)
            .join(EmployeeObject, EmployeeObject.employee_id == User.id)
            .where(
                EmployeeObject.site_object_id == site_object_id,
                EmployeeObject.is_active == True,
                User.is_active == True,
            )
        )
        return result.scalars().all()

    async def update_last_seen(self, telegram_id: int) -> None:
        await self.session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(last_seen_at=func.now())
        )

    async def create(
        self,
        telegram_id: int,
        first_name: str,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
        phone: Optional[str] = None,
        role: UserRole = UserRole.EMPLOYEE,
        language_code: str = "ru",
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            telegram_username=username,
            phone=phone,
            role=role,
            language_code=language_code,
        )
        return await self.save(user)


# ══════════════════════════════════════════════════════════════════
#  SITE OBJECT REPOSITORY
# ══════════════════════════════════════════════════════════════════

class SiteObjectRepository(BaseRepository[SiteObject]):
    _model = SiteObject

    async def get_active_objects(self) -> Sequence[SiteObject]:
        result = await self.session.execute(
            select(SiteObject)
            .where(SiteObject.status == ObjectStatus.ACTIVE)
            .order_by(SiteObject.name)
        )
        return result.scalars().all()

    async def get_by_manager(self, manager_id: int) -> Sequence[SiteObject]:
        result = await self.session.execute(
            select(SiteObject).where(SiteObject.manager_id == manager_id)
        )
        return result.scalars().all()

    async def get_by_qr_code(self, qr_code: str) -> Optional[SiteObject]:
        result = await self.session.execute(
            select(SiteObject).where(SiteObject.qr_code == qr_code)
        )
        return result.scalar_one_or_none()

    async def get_objects_for_employee(self, employee_id: int) -> Sequence[SiteObject]:
        result = await self.session.execute(
            select(SiteObject)
            .join(EmployeeObject, EmployeeObject.site_object_id == SiteObject.id)
            .where(
                EmployeeObject.employee_id == employee_id,
                EmployeeObject.is_active == True,
                SiteObject.status == ObjectStatus.ACTIVE,
            )
        )
        return result.scalars().all()

    async def get_with_stats(self, site_object_id: int) -> Optional[SiteObject]:
        result = await self.session.execute(
            select(SiteObject)
            .options(
                selectinload(SiteObject.shifts),
                selectinload(SiteObject.employee_assignments),
            )
            .where(SiteObject.id == site_object_id)
        )
        return result.scalar_one_or_none()


# ══════════════════════════════════════════════════════════════════
#  SHIFT REPOSITORY
# ══════════════════════════════════════════════════════════════════

class ShiftRepository(BaseRepository[Shift]):
    _model = Shift

    async def get_active_shift(self, employee_id: int) -> Optional[Shift]:
        result = await self.session.execute(
            select(Shift).where(
                Shift.employee_id == employee_id,
                Shift.status == ShiftStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    async def get_shifts_by_employee(
        self,
        employee_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 50,
    ) -> Sequence[Shift]:
        q = select(Shift).where(Shift.employee_id == employee_id)
        if date_from:
            q = q.where(Shift.started_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            q = q.where(Shift.started_at <= datetime.combine(date_to, datetime.max.time()))
        q = q.order_by(Shift.started_at.desc()).limit(limit)
        result = await self.session.execute(q)
        return result.scalars().all()

    async def get_shifts_by_object(
        self,
        site_object_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Sequence[Shift]:
        q = select(Shift).where(Shift.site_object_id == site_object_id)
        if date_from:
            q = q.where(Shift.started_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            q = q.where(Shift.started_at <= datetime.combine(date_to, datetime.max.time()))
        result = await self.session.execute(q)
        return result.scalars().all()

    async def get_total_hours_by_employee(
        self,
        employee_id: int,
        date_from: date,
        date_to: date,
    ) -> float:
        result = await self.session.execute(
            select(func.sum(Shift.total_hours)).where(
                Shift.employee_id == employee_id,
                Shift.status == ShiftStatus.COMPLETED,
                Shift.started_at >= datetime.combine(date_from, datetime.min.time()),
                Shift.started_at <= datetime.combine(date_to, datetime.max.time()),
            )
        )
        return float(result.scalar() or 0)

    async def get_active_employees_today(self) -> Sequence[Shift]:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(Shift)
            .options(
                joinedload(Shift.employee),
                joinedload(Shift.site_object),
            )
            .where(
                Shift.status == ShiftStatus.ACTIVE,
                Shift.started_at >= today_start,
            )
        )
        return result.scalars().all()

    async def get_late_starts_count(self, employee_id: int, month: date) -> int:
        month_start = month.replace(day=1)
        if month.month == 12:
            month_end = month.replace(year=month.year + 1, month=1, day=1)
        else:
            month_end = month.replace(month=month.month + 1, day=1)
        result = await self.session.execute(
            select(func.count(Shift.id)).where(
                Shift.employee_id == employee_id,
                Shift.is_late == True,
                Shift.started_at >= datetime.combine(month_start, datetime.min.time()),
                Shift.started_at < datetime.combine(month_end, datetime.min.time()),
            )
        )
        return result.scalar() or 0

    async def start_shift(
        self,
        employee_id: int,
        site_object_id: int,
        lat: float,
        lon: float,
        is_late: bool = False,
        late_minutes: int = 0,
    ) -> Shift:
        shift = Shift(
            employee_id=employee_id,
            site_object_id=site_object_id,
            status=ShiftStatus.ACTIVE,
            started_at=datetime.utcnow(),
            start_latitude=lat,
            start_longitude=lon,
            is_late=is_late,
            late_minutes=late_minutes,
        )
        return await self.save(shift)

    async def end_shift(self, shift: Shift, lat: float, lon: float) -> Shift:
        now = datetime.utcnow()
        shift.ended_at = now
        shift.end_latitude = lat
        shift.end_longitude = lon
        shift.status = ShiftStatus.COMPLETED
        delta = (now - shift.started_at).total_seconds() / 3600
        shift.total_hours = round(delta, 2)
        from app.core.config.settings import settings
        if delta > settings.NOTIFY_OVERTIME_HOURS:
            shift.overtime_hours = round(delta - settings.NOTIFY_OVERTIME_HOURS, 2)
        self.session.add(shift)
        await self.session.flush()
        return shift


# ══════════════════════════════════════════════════════════════════
#  LOCATION LOG REPOSITORY
# ══════════════════════════════════════════════════════════════════

class LocationLogRepository(BaseRepository[LocationLog]):
    _model = LocationLog

    async def log_location(
        self,
        employee_id: int,
        lat: float,
        lon: float,
        shift_id: Optional[int] = None,
        is_on_site: bool = True,
        accuracy: Optional[float] = None,
    ) -> LocationLog:
        log = LocationLog(
            employee_id=employee_id,
            shift_id=shift_id,
            latitude=lat,
            longitude=lon,
            accuracy=accuracy,
            is_on_site=is_on_site,
        )
        return await self.save(log)

    async def get_shift_path(self, shift_id: int) -> Sequence[LocationLog]:
        result = await self.session.execute(
            select(LocationLog)
            .where(LocationLog.shift_id == shift_id)
            .order_by(LocationLog.recorded_at)
        )
        return result.scalars().all()


# ══════════════════════════════════════════════════════════════════
#  TASK REPOSITORY
# ══════════════════════════════════════════════════════════════════

class TaskRepository(BaseRepository[Task]):
    _model = Task

    async def get_tasks_for_employee(
        self, employee_id: int, status: Optional[TaskStatus] = None
    ) -> Sequence[Task]:
        q = select(Task).where(Task.assignee_id == employee_id)
        if status:
            q = q.where(Task.status == status)
        q = q.order_by(Task.deadline.asc().nulls_last())
        result = await self.session.execute(q)
        return result.scalars().all()

    async def get_tasks_for_object(self, site_object_id: int) -> Sequence[Task]:
        result = await self.session.execute(
            select(Task)
            .where(Task.site_object_id == site_object_id)
            .order_by(Task.created_at.desc())
        )
        return result.scalars().all()

    async def get_overdue_tasks(self) -> Sequence[Task]:
        result = await self.session.execute(
            select(Task).where(
                Task.deadline < datetime.utcnow(),
                Task.status.not_in([TaskStatus.DONE]),
            )
        )
        return result.scalars().all()

    async def get_tasks_by_manager(self, manager_id: int) -> Sequence[Task]:
        result = await self.session.execute(
            select(Task).where(Task.creator_id == manager_id)
            .order_by(Task.created_at.desc())
        )
        return result.scalars().all()


# ══════════════════════════════════════════════════════════════════
#  PHOTO REPOSITORY
# ══════════════════════════════════════════════════════════════════

class PhotoRepository(BaseRepository[Photo]):
    _model = Photo

    async def get_photos_for_shift(self, shift_id: int) -> Sequence[Photo]:
        result = await self.session.execute(
            select(Photo).where(Photo.shift_id == shift_id)
            .order_by(Photo.created_at)
        )
        return result.scalars().all()

    async def get_photos_for_object(
        self, site_object_id: int, photo_type: Optional[PhotoType] = None
    ) -> Sequence[Photo]:
        q = select(Photo).where(Photo.site_object_id == site_object_id)
        if photo_type:
            q = q.where(Photo.photo_type == photo_type)
        q = q.order_by(Photo.created_at.desc())
        result = await self.session.execute(q)
        return result.scalars().all()

    async def get_safety_violations(self, site_object_id: Optional[int] = None) -> Sequence[Photo]:
        q = select(Photo).where(
            or_(Photo.has_helmet == False, Photo.has_vest == False)
        )
        if site_object_id:
            q = q.where(Photo.site_object_id == site_object_id)
        result = await self.session.execute(q)
        return result.scalars().all()


# ══════════════════════════════════════════════════════════════════
#  NOTIFICATION REPOSITORY
# ══════════════════════════════════════════════════════════════════

class NotificationRepository(BaseRepository[Notification]):
    _model = Notification

    async def get_unsent(self, limit: int = 50) -> Sequence[Notification]:
        result = await self.session.execute(
            select(Notification)
            .options(joinedload(Notification.recipient))
            .where(Notification.is_sent == False)
            .order_by(Notification.created_at)
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_sent(self, notification_id: int) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(is_sent=True, sent_at=func.now())
        )


# ══════════════════════════════════════════════════════════════════
#  AUDIT LOG REPOSITORY
# ══════════════════════════════════════════════════════════════════

class AuditLogRepository(BaseRepository[AuditLog]):
    _model = AuditLog

    async def log(
        self,
        action: str,
        entity: str,
        entity_id: Optional[int] = None,
        user_id: Optional[int] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
        )
        return await self.save(log)
