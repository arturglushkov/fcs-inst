"""Все клавиатуры бота — inline и reply."""

from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import Sequence, Optional
from app.models.models import SiteObject, Task, TaskStatus


# ══════════════════════════════════════════════════════════════════
#  REPLY KEYBOARDS
# ══════════════════════════════════════════════════════════════════

def kb_main_employee() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🟢 Начать смену"),
        KeyboardButton(text="🔴 Завершить смену"),
    )
    builder.row(
        KeyboardButton(text="📸 Отправить фото"),
        KeyboardButton(text="📋 Мои задачи"),
    )
    builder.row(
        KeyboardButton(text="⏱ Мои часы"),
        KeyboardButton(text="📍 Моя локация", request_location=True),
    )
    return builder.as_markup(resize_keyboard=True)


def kb_main_manager() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="👥 Сотрудники"),
        KeyboardButton(text="🏗 Объекты"),
    )
    builder.row(
        KeyboardButton(text="📋 Задачи"),
        KeyboardButton(text="📊 Отчёты"),
    )
    builder.row(
        KeyboardButton(text="🗺 Карта (live)"),
        KeyboardButton(text="⚙️ Настройки"),
    )
    return builder.as_markup(resize_keyboard=True)


def kb_main_owner() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="👥 Сотрудники"),
        KeyboardButton(text="🏗 Объекты"),
    )
    builder.row(
        KeyboardButton(text="📋 Задачи"),
        KeyboardButton(text="📊 Отчёты"),
    )
    builder.row(
        KeyboardButton(text="🗺 Карта (live)"),
        KeyboardButton(text="💰 Зарплата"),
    )
    builder.row(
        KeyboardButton(text="⚙️ Настройки"),
        KeyboardButton(text="🔑 Управление доступом"),
    )
    return builder.as_markup(resize_keyboard=True)


def kb_request_phone() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📱 Поделиться номером", request_contact=True))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_request_location() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📍 Отправить геолокацию", request_location=True))
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_remove() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ══════════════════════════════════════════════════════════════════
#  INLINE KEYBOARDS
# ══════════════════════════════════════════════════════════════════

def kb_select_object(objects: Sequence[SiteObject]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for obj in objects:
        builder.row(InlineKeyboardButton(
            text=f"🏗 {obj.name}",
            callback_data=f"select_object:{obj.id}",
        ))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def kb_photo_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Фото ДО работы", callback_data="photo_type:before")],
        [InlineKeyboardButton(text="📸 Фото В ПРОЦЕССЕ", callback_data="photo_type:during")],
        [InlineKeyboardButton(text="✅ Фото ПОСЛЕ работы", callback_data="photo_type:after")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def kb_confirm_shift_end() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, завершить", callback_data="confirm_end_shift"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel"),
        ]
    ])


def kb_tasks(tasks: Sequence[Task]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status_emoji = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.IN_PROGRESS: "🔄",
        TaskStatus.DONE: "✅",
        TaskStatus.OVERDUE: "🔴",
    }
    for task in tasks:
        emoji = status_emoji.get(task.status, "📋")
        deadline_str = ""
        if task.deadline:
            deadline_str = f" | {task.deadline.strftime('%d.%m')}"
        builder.row(InlineKeyboardButton(
            text=f"{emoji} {task.title[:30]}{deadline_str}",
            callback_data=f"task_view:{task.id}",
        ))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_main"))
    return builder.as_markup()


def kb_task_actions(task_id: int, is_assignee: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_assignee:
        builder.row(
            InlineKeyboardButton(text="▶️ В работу", callback_data=f"task_start:{task_id}"),
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"task_done:{task_id}"),
        )
    builder.row(InlineKeyboardButton(text="🔙 К задачам", callback_data="back_tasks"))
    return builder.as_markup()


def kb_my_hours_period() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="hours_today"),
            InlineKeyboardButton(text="📆 Неделя", callback_data="hours_week"),
        ],
        [
            InlineKeyboardButton(text="🗓 Месяц", callback_data="hours_month"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_main"),
        ],
    ])


def kb_report_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 По сотрудникам", callback_data="report_employees")],
        [InlineKeyboardButton(text="🏗 По объектам", callback_data="report_objects")],
        [InlineKeyboardButton(text="📊 Общая сводка", callback_data="report_summary")],
        [InlineKeyboardButton(text="📥 Excel выгрузка", callback_data="report_excel")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")],
    ])


def kb_manager_employees(employees) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for emp in employees:
        builder.row(InlineKeyboardButton(
            text=f"👤 {emp.full_name}",
            callback_data=f"employee_view:{emp.id}",
        ))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_main"))
    return builder.as_markup()


def kb_employee_actions(employee_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"emp_stats:{employee_id}")],
        [InlineKeyboardButton(text="📋 Назначить задачу", callback_data=f"emp_task:{employee_id}")],
        [InlineKeyboardButton(text="📍 Локация", callback_data=f"emp_location:{employee_id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="back_employees")],
    ])


def kb_objects_list(objects: Sequence[SiteObject]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for obj in objects:
        builder.row(InlineKeyboardButton(
            text=f"🏗 {obj.name}",
            callback_data=f"object_view:{obj.id}",
        ))
    builder.row(InlineKeyboardButton(text="➕ Добавить объект", callback_data="object_create"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_main"))
    return builder.as_markup()


def kb_pagination(current: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row = []
    if current > 1:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_page:{current-1}"))
    row.append(InlineKeyboardButton(text=f"{current}/{total_pages}", callback_data="noop"))
    if current < total_pages:
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_page:{current+1}"))
    builder.row(*row)
    return builder.as_markup()


def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


def kb_back(callback: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback)]
    ])
