"""
ORM Models — MontazhBot
Все таблицы с индексами, relationships и constraints.
"""

from __future__ import annotations
import enum
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime, Date,
    ForeignKey, Enum, Numeric, Index, UniqueConstraint,
    JSON, BigInteger, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.engine import Base


# ══════════════════════════════════════════════════════════════════
#  ENUMS
# ══════════════════════════════════════════════════════════════════

class UserRole(str, enum.Enum):
    OWNER    = "owner"
    MANAGER  = "manager"
    EMPLOYEE = "employee"


class ShiftStatus(str, enum.Enum):
    ACTIVE    = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(str, enum.Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    DONE       = "done"
    OVERDUE    = "overdue"


class TaskPriority(str, enum.Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class PhotoType(str, enum.Enum):
    BEFORE       = "before"
    DURING       = "during"
    AFTER        = "after"
    TASK_REPORT  = "task_report"


class NotificationType(str, enum.Enum):
    ARRIVED        = "arrived"
    LEFT           = "left"
    LATE           = "late"
    OVERTIME       = "overtime"
    NO_SHOW        = "no_show"
    LEFT_SITE      = "left_site"
    TASK_OVERDUE   = "task_overdue"


class ObjectStatus(str, enum.Enum):
    ACTIVE    = "active"
    COMPLETED = "completed"
    PAUSED    = "paused"


# ══════════════════════════════════════════════════════════════════
#  MIXIN
# ══════════════════════════════════════════════════════════════════

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ══════════════════════════════════════════════════════════════════
#  USER
# ══════════════════════════════════════════════════════════════════

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int]              = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int]     = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[str]      = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    role: Mapped[UserRole]       = mapped_column(
        Enum(UserRole), nullable=False, default=UserRole.EMPLOYEE
    )
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True, nullable=False)
    language_code: Mapped[str]   = mapped_column(String(5), default="ru")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    managed_objects: Mapped[List["SiteObject"]] = relationship(
        "SiteObject", back_populates="manager", foreign_keys="SiteObject.manager_id"
    )
    assignments: Mapped[List["EmployeeObject"]] = relationship(
        "EmployeeObject", back_populates="employee"
    )
    shifts: Mapped[List["Shift"]] = relationship("Shift", back_populates="employee")
    tasks: Mapped[List["Task"]] = relationship(
        "Task", back_populates="assignee", foreign_keys="Task.assignee_id"
    )
    created_tasks: Mapped[List["Task"]] = relationship(
        "Task", back_populates="creator", foreign_keys="Task.creator_id"
    )
    photos: Mapped[List["Photo"]] = relationship("Photo", back_populates="uploaded_by")
    location_logs: Mapped[List["LocationLog"]] = relationship(
        "LocationLog", back_populates="employee"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="recipient"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user")

    __table_args__ = (
        Index("ix_users_role_active", "role", "is_active"),
    )

    @property
    def full_name(self) -> str:
        parts = [self.first_name]
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts)


# ══════════════════════════════════════════════════════════════════
#  SITE OBJECT
# ══════════════════════════════════════════════════════════════════

class SiteObject(TimestampMixin, Base):
    __tablename__ = "site_objects"

    id: Mapped[int]             = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str]           = mapped_column(String(200), nullable=False)
    address: Mapped[str]        = mapped_column(String(500), nullable=False)
    client_name: Mapped[Optional[str]] = mapped_column(String(200))
    client_phone: Mapped[Optional[str]] = mapped_column(String(20))
    latitude: Mapped[float]     = mapped_column(Float, nullable=False)
    longitude: Mapped[float]    = mapped_column(Float, nullable=False)
    radius_meters: Mapped[int]  = mapped_column(Integer, default=100, nullable=False)
    status: Mapped[ObjectStatus] = mapped_column(
        Enum(ObjectStatus), default=ObjectStatus.ACTIVE, nullable=False
    )
    planned_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    start_date: Mapped[Optional[date]]  = mapped_column(Date)
    end_date: Mapped[Optional[date]]    = mapped_column(Date)
    manager_id: Mapped[Optional[int]]   = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    qr_code: Mapped[Optional[str]]      = mapped_column(String(100), unique=True)
    notes: Mapped[Optional[str]]        = mapped_column(Text)

    # Relationships
    manager: Mapped[Optional["User"]] = relationship(
        "User", back_populates="managed_objects", foreign_keys=[manager_id]
    )
    employee_assignments: Mapped[List["EmployeeObject"]] = relationship(
        "EmployeeObject", back_populates="site_object"
    )
    shifts: Mapped[List["Shift"]] = relationship("Shift", back_populates="site_object")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="site_object")
    photos: Mapped[List["Photo"]] = relationship("Photo", back_populates="site_object")

    __table_args__ = (
        Index("ix_site_objects_status", "status"),
        Index("ix_site_objects_manager_id", "manager_id"),
    )


# ══════════════════════════════════════════════════════════════════
#  EMPLOYEE ↔ OBJECT ASSIGNMENT
# ══════════════════════════════════════════════════════════════════

class EmployeeObject(TimestampMixin, Base):
    __tablename__ = "employee_objects"

    id: Mapped[int]              = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int]     = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    site_object_id: Mapped[int]  = mapped_column(
        BigInteger, ForeignKey("site_objects.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    employee: Mapped["User"] = relationship("User", back_populates="assignments")
    site_object: Mapped["SiteObject"] = relationship(
        "SiteObject", back_populates="employee_assignments"
    )

    __table_args__ = (
        UniqueConstraint("employee_id", "site_object_id", name="uq_employee_object"),
        Index("ix_employee_objects_employee_id", "employee_id"),
        Index("ix_employee_objects_object_id", "site_object_id"),
    )


# ══════════════════════════════════════════════════════════════════
#  SHIFT
# ══════════════════════════════════════════════════════════════════

class Shift(TimestampMixin, Base):
    __tablename__ = "shifts"

    id: Mapped[int]               = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int]      = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    site_object_id: Mapped[int]   = mapped_column(
        BigInteger, ForeignKey("site_objects.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ShiftStatus]   = mapped_column(
        Enum(ShiftStatus), default=ShiftStatus.ACTIVE, nullable=False
    )
    started_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # GPS at start/end
    start_latitude: Mapped[Optional[float]]  = mapped_column(Float)
    start_longitude: Mapped[Optional[float]] = mapped_column(Float)
    end_latitude: Mapped[Optional[float]]    = mapped_column(Float)
    end_longitude: Mapped[Optional[float]]   = mapped_column(Float)

    # Calculated
    total_hours: Mapped[Optional[Decimal]]   = mapped_column(Numeric(6, 2))
    overtime_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), default=0)
    is_late: Mapped[bool]                    = mapped_column(Boolean, default=False)
    late_minutes: Mapped[int]               = mapped_column(Integer, default=0)

    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    employee: Mapped["User"] = relationship("User", back_populates="shifts")
    site_object: Mapped["SiteObject"] = relationship("SiteObject", back_populates="shifts")
    photos: Mapped[List["Photo"]] = relationship("Photo", back_populates="shift")
    location_logs: Mapped[List["LocationLog"]] = relationship(
        "LocationLog", back_populates="shift"
    )

    __table_args__ = (
        Index("ix_shifts_employee_id", "employee_id"),
        Index("ix_shifts_object_id", "site_object_id"),
        Index("ix_shifts_status", "status"),
        Index("ix_shifts_started_at", "started_at"),
        Index("ix_shifts_employee_started", "employee_id", "started_at"),
    )


# ══════════════════════════════════════════════════════════════════
#  LOCATION LOG
# ══════════════════════════════════════════════════════════════════

class LocationLog(TimestampMixin, Base):
    __tablename__ = "location_logs"

    id: Mapped[int]            = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int]   = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    shift_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("shifts.id", ondelete="SET NULL")
    )
    latitude: Mapped[float]    = mapped_column(Float, nullable=False)
    longitude: Mapped[float]   = mapped_column(Float, nullable=False)
    accuracy: Mapped[Optional[float]] = mapped_column(Float)
    is_on_site: Mapped[bool]   = mapped_column(Boolean, default=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped["User"] = relationship("User", back_populates="location_logs")
    shift: Mapped[Optional["Shift"]] = relationship("Shift", back_populates="location_logs")

    __table_args__ = (
        Index("ix_location_logs_employee_id", "employee_id"),
        Index("ix_location_logs_shift_id", "shift_id"),
        Index("ix_location_logs_recorded_at", "recorded_at"),
    )


# ══════════════════════════════════════════════════════════════════
#  TASK
# ══════════════════════════════════════════════════════════════════

class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int]             = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str]          = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    creator_id: Mapped[int]     = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assignee_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    site_object_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("site_objects.id", ondelete="SET NULL")
    )
    status: Mapped[TaskStatus]   = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False
    )
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completion_report: Mapped[Optional[str]] = mapped_column(Text)
    attachments: Mapped[Optional[dict]] = mapped_column(JSON)  # file_ids list

    creator: Mapped["User"] = relationship(
        "User", back_populates="created_tasks", foreign_keys=[creator_id]
    )
    assignee: Mapped[Optional["User"]] = relationship(
        "User", back_populates="tasks", foreign_keys=[assignee_id]
    )
    site_object: Mapped[Optional["SiteObject"]] = relationship(
        "SiteObject", back_populates="tasks"
    )
    photos: Mapped[List["Photo"]] = relationship("Photo", back_populates="task")

    __table_args__ = (
        Index("ix_tasks_assignee_id", "assignee_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_deadline", "deadline"),
        Index("ix_tasks_object_id", "site_object_id"),
    )


# ══════════════════════════════════════════════════════════════════
#  PHOTO
# ══════════════════════════════════════════════════════════════════

class Photo(TimestampMixin, Base):
    __tablename__ = "photos"

    id: Mapped[int]               = mapped_column(BigInteger, primary_key=True)
    file_id: Mapped[str]          = mapped_column(String(200), nullable=False)  # Telegram file_id
    s3_key: Mapped[Optional[str]] = mapped_column(String(500))
    s3_url: Mapped[Optional[str]] = mapped_column(String(1000))
    photo_type: Mapped[PhotoType] = mapped_column(Enum(PhotoType), nullable=False)
    shift_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("shifts.id", ondelete="SET NULL")
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="SET NULL")
    )
    site_object_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("site_objects.id", ondelete="SET NULL")
    )
    uploaded_by_id: Mapped[int]   = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    caption: Mapped[Optional[str]] = mapped_column(Text)

    # AI analysis results
    ai_analysis: Mapped[Optional[dict]] = mapped_column(JSON)
    has_helmet: Mapped[Optional[bool]]  = mapped_column(Boolean)
    has_vest: Mapped[Optional[bool]]    = mapped_column(Boolean)
    has_gloves: Mapped[Optional[bool]]  = mapped_column(Boolean)
    progress_pct: Mapped[Optional[int]] = mapped_column(Integer)
    ai_notes: Mapped[Optional[str]]     = mapped_column(Text)

    shift: Mapped[Optional["Shift"]]    = relationship("Shift", back_populates="photos")
    task: Mapped[Optional["Task"]]      = relationship("Task", back_populates="photos")
    site_object: Mapped[Optional["SiteObject"]] = relationship(
        "SiteObject", back_populates="photos"
    )
    uploaded_by: Mapped["User"] = relationship("User", back_populates="photos")

    __table_args__ = (
        Index("ix_photos_shift_id", "shift_id"),
        Index("ix_photos_task_id", "task_id"),
        Index("ix_photos_object_id", "site_object_id"),
        Index("ix_photos_uploaded_by", "uploaded_by_id"),
    )


# ══════════════════════════════════════════════════════════════════
#  NOTIFICATION
# ══════════════════════════════════════════════════════════════════

class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int]                = mapped_column(BigInteger, primary_key=True)
    recipient_id: Mapped[int]      = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType), nullable=False
    )
    title: Mapped[str]             = mapped_column(String(200), nullable=False)
    body: Mapped[str]              = mapped_column(Text, nullable=False)
    is_sent: Mapped[bool]          = mapped_column(Boolean, default=False)
    is_read: Mapped[bool]          = mapped_column(Boolean, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)

    recipient: Mapped["User"] = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_recipient_id", "recipient_id"),
        Index("ix_notifications_is_sent", "is_sent"),
    )


# ══════════════════════════════════════════════════════════════════
#  SCHEDULE (рабочий график)
# ══════════════════════════════════════════════════════════════════

class WorkSchedule(TimestampMixin, Base):
    __tablename__ = "work_schedules"

    id: Mapped[int]          = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    site_object_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("site_objects.id", ondelete="SET NULL")
    )
    work_date: Mapped[date]  = mapped_column(Date, nullable=False)
    planned_start: Mapped[Optional[str]] = mapped_column(String(5))   # "08:00"
    planned_end: Mapped[Optional[str]]   = mapped_column(String(5))   # "17:00"
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_employee_date"),
        Index("ix_work_schedules_date", "work_date"),
    )


# ══════════════════════════════════════════════════════════════════
#  AUDIT LOG
# ══════════════════════════════════════════════════════════════════

class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[int]           = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str]       = mapped_column(String(100), nullable=False)
    entity: Mapped[str]       = mapped_column(String(100), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_entity", "entity"),
    )
