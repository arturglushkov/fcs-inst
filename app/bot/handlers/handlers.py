"""
Telegram handlers — все команды и callback.
Структура: start → auth → shift → photo → tasks → reports
"""

from __future__ import annotations
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, PhotoSize,
    ContentType, ReplyKeyboardRemove,
)

from app.core.database.engine import async_session_factory
from app.core.cache.redis_client import redis_client
from app.services.services import UserService, ShiftService, TaskService, ReportService
from app.repositories.repositories import (
    UserRepository, ShiftRepository, SiteObjectRepository,
    TaskRepository, PhotoRepository,
)
from app.models.models import UserRole, ShiftStatus, PhotoType, TaskStatus
from app.bot.keyboards.keyboards import (
    kb_main_employee, kb_main_manager, kb_main_owner,
    kb_request_phone, kb_request_location, kb_remove,
    kb_select_object, kb_photo_type, kb_confirm_shift_end,
    kb_tasks, kb_task_actions, kb_my_hours_period,
    kb_report_type, kb_manager_employees, kb_employee_actions,
    kb_objects_list, kb_cancel, kb_back,
)
from app.integrations.storage import storage_service

logger = logging.getLogger(__name__)
router = Router()


# ══════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════

class RegistrationStates(StatesGroup):
    waiting_phone    = State()
    waiting_location = State()

class ShiftStates(StatesGroup):
    waiting_object   = State()
    waiting_location = State()
    confirming_end   = State()

class PhotoStates(StatesGroup):
    waiting_type  = State()
    waiting_photo = State()

class TaskCreateStates(StatesGroup):
    waiting_title       = State()
    waiting_description = State()
    waiting_assignee    = State()
    waiting_deadline    = State()

class TaskCompleteStates(StatesGroup):
    waiting_report = State()


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def _main_keyboard(role: UserRole):
    if role == UserRole.OWNER:
        return kb_main_owner()
    elif role == UserRole.MANAGER:
        return kb_main_manager()
    return kb_main_employee()


def _role_badge(role: UserRole) -> str:
    return {"owner": "👑 Владелец", "manager": "🔧 Менеджер", "employee": "👷 Сотрудник"}.get(role, role)


# ══════════════════════════════════════════════════════════════════
#  /START — регистрация
# ══════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    async with async_session_factory() as session:
        svc = UserService(session)
        user, created = await svc.get_or_create(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            username=message.from_user.username,
            language_code=message.from_user.language_code or "ru",
        )

    # Сохраняем в кэш сразу
    user_dict = {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "role": user.role if isinstance(user.role, str) else user.role.value,
        "is_active": user.is_active,
        "phone": user.phone,
    }
    await redis_client.set_user_session(message.from_user.id, user_dict, expire=3600)

    if not user.phone:
        await message.answer(
            "👋 Привет! Я бот для контроля рабочих смен.\n\n"
            "Для начала работы мне нужен твой номер телефона.\n"
            "Нажми кнопку ниже 👇",
            reply_markup=kb_request_phone(),
        )
        await state.set_state(RegistrationStates.waiting_phone)
        return

    await message.answer(
        f"👋 С возвращением, {user.first_name}!\n"
        f"Роль: {_role_badge(user.role)}",
        reply_markup=_main_keyboard(user.role),
    )


@router.message(RegistrationStates.waiting_phone, F.content_type == ContentType.CONTACT)
async def process_phone(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number
    async with async_session_factory() as session:
        svc = UserService(session)
        user = await svc.register_phone(message.from_user.id, phone)

    if not user:
        await message.answer(
            "❌ Ошибка регистрации. Попробуй снова /start",
            reply_markup=kb_remove(),
        )
        return

    # Сохраняем в Redis кэш
    user_dict = {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "role": user.role if isinstance(user.role, str) else user.role.value,
        "is_active": user.is_active,
        "phone": user.phone,
    }
    await redis_client.set_user_session(message.from_user.id, user_dict, expire=3600)

    await state.clear()
    await message.answer(
        f"✅ Телефон сохранён: {phone}\n\n"
        f"Добро пожаловать, {user.first_name}! 🎉\n"
        f"Роль: {_role_badge(user.role)}",
        reply_markup=_main_keyboard(user.role),
    )


# ══════════════════════════════════════════════════════════════════
#  /me — профиль
# ══════════════════════════════════════════════════════════════════

@router.message(Command("me"))
async def cmd_profile(message: Message) -> None:
    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("❌ Ты не зарегистрирован. Введи /start")
        return
    await message.answer(
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {user.full_name}\n"
        f"Телефон: {user.phone or '—'}\n"
        f"Роль: {_role_badge(user.role)}\n"
        f"Статус: {'✅ Активен' if user.is_active else '🚫 Заблокирован'}",
        parse_mode="HTML",
        reply_markup=kb_back(),
    )


# ══════════════════════════════════════════════════════════════════
#  НАЧАТЬ СМЕНУ
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "🟢 Начать смену")
async def start_shift_init(message: Message, state: FSMContext) -> None:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer("❌ Сначала зарегистрируйся /start")
            return

        shift_repo = ShiftRepository(session)
        active = await shift_repo.get_active_shift(user.id)
        if active:
            await message.answer(
                "⚠️ У тебя уже есть активная смена!\n"
                "Сначала заверши текущую 👇",
                reply_markup=_main_keyboard(user.role),
            )
            return

        obj_repo = SiteObjectRepository(session)
        objects = await obj_repo.get_objects_for_employee(user.id)

    if not objects:
        await message.answer(
            "❌ Тебе не назначено ни одного объекта.\n"
            "Обратись к менеджеру.",
        )
        return

    await state.set_state(ShiftStates.waiting_object)
    await state.update_data(user_id=user.id, objects={str(o.id): o.name for o in objects})
    await message.answer(
        "🏗 <b>Выбери объект:</b>",
        parse_mode="HTML",
        reply_markup=kb_select_object(objects),
    )


@router.callback_query(ShiftStates.waiting_object, F.data.startswith("select_object:"))
async def select_object(callback: CallbackQuery, state: FSMContext) -> None:
    site_object_id = int(callback.data.split(":")[1])
    await state.update_data(site_object_id=site_object_id)
    await state.set_state(ShiftStates.waiting_location)
    await callback.message.edit_text(
        "📍 <b>Отправь свою геолокацию</b>\n\n"
        "Нажми кнопку ниже, чтобы подтвердить своё местоположение.",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "👇 Отправь геолокацию",
        reply_markup=kb_request_location(),
    )
    await callback.answer()


@router.message(ShiftStates.waiting_location, F.content_type == ContentType.LOCATION)
async def process_start_location(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    site_object_id = data["site_object_id"]
    lat = message.location.latitude
    lon = message.location.longitude

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        obj_repo = SiteObjectRepository(session)
        site_obj = await obj_repo.get_by_id(site_object_id)
        shift_svc = ShiftService(session)

        can_start, reason = await shift_svc.can_start_shift(user, site_obj, lat, lon)
        if not can_start:
            await message.answer(reason, reply_markup=_main_keyboard(user.role))
            await state.clear()
            return

        shift = await shift_svc.start_shift(user, site_obj, lat, lon)

    await state.clear()
    await message.answer(
        f"✅ <b>Смена начата!</b>\n\n"
        f"🏗 Объект: {site_obj.name}\n"
        f"⏰ Время начала: {shift.started_at.strftime('%H:%M')}\n"
        f"{'⏰ Есть опоздание!' if shift.is_late else ''}",
        parse_mode="HTML",
        reply_markup=_main_keyboard(user.role),
    )


# ══════════════════════════════════════════════════════════════════
#  ЗАВЕРШИТЬ СМЕНУ
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "🔴 Завершить смену")
async def end_shift_init(message: Message, state: FSMContext) -> None:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer("❌ Сначала зарегистрируйся /start")
            return
        shift_repo = ShiftRepository(session)
        active = await shift_repo.get_active_shift(user.id)

    if not active:
        await message.answer(
            "❌ У тебя нет активной смены.",
            reply_markup=_main_keyboard(user.role),
        )
        return

    duration = (datetime.utcnow() - active.started_at).total_seconds() / 3600
    await state.set_state(ShiftStates.confirming_end)
    await state.update_data(shift_id=active.id)
    await message.answer(
        f"⏱ <b>Завершить смену?</b>\n\n"
        f"Начало: {active.started_at.strftime('%H:%M')}\n"
        f"Сейчас прошло: {duration:.1f} ч.",
        parse_mode="HTML",
        reply_markup=kb_confirm_shift_end(),
    )


@router.callback_query(ShiftStates.confirming_end, F.data == "confirm_end_shift")
async def confirm_end_shift(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ShiftStates.waiting_location)
    await callback.message.edit_text(
        "📍 Отправь геолокацию для подтверждения завершения смены."
    )
    await callback.message.answer(
        "👇 Отправь геолокацию",
        reply_markup=kb_request_location(),
    )
    await callback.answer()


@router.message(ShiftStates.waiting_location, F.content_type == ContentType.LOCATION)
async def process_end_location(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if "shift_id" not in data:
        return
    lat = message.location.latitude
    lon = message.location.longitude

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        shift_repo = ShiftRepository(session)
        shift = await shift_repo.get_by_id(data["shift_id"])
        obj_repo = SiteObjectRepository(session)
        site_obj = await obj_repo.get_by_id(shift.site_object_id)
        shift_svc = ShiftService(session)
        shift = await shift_svc.end_shift(shift, user, lat, lon)

    await state.clear()
    await message.answer(
        f"✅ <b>Смена завершена!</b>\n\n"
        f"🏗 Объект: {site_obj.name}\n"
        f"⏰ Начало: {shift.started_at.strftime('%H:%M')}\n"
        f"⏰ Конец: {shift.ended_at.strftime('%H:%M')}\n"
        f"⏱ Итого: {float(shift.total_hours):.1f} ч.\n"
        f"{'🔴 Переработка: ' + str(float(shift.overtime_hours)) + ' ч.' if shift.overtime_hours else ''}",
        parse_mode="HTML",
        reply_markup=_main_keyboard(user.role),
    )


# ══════════════════════════════════════════════════════════════════
#  ФОТО
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "📸 Отправить фото")
async def photo_init(message: Message, state: FSMContext) -> None:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        shift_repo = ShiftRepository(session)
        active = await shift_repo.get_active_shift(user.id)

    if not active:
        await message.answer("⚠️ Фото можно отправить только во время активной смены.")
        return

    await state.set_state(PhotoStates.waiting_type)
    await state.update_data(shift_id=active.id, site_object_id=active.site_object_id)
    await message.answer(
        "📷 <b>Тип фотоотчёта:</b>",
        parse_mode="HTML",
        reply_markup=kb_photo_type(),
    )


@router.callback_query(PhotoStates.waiting_type, F.data.startswith("photo_type:"))
async def photo_type_selected(callback: CallbackQuery, state: FSMContext) -> None:
    photo_type = callback.data.split(":")[1]
    await state.update_data(photo_type=photo_type)
    await state.set_state(PhotoStates.waiting_photo)
    type_labels = {"before": "ДО работы", "during": "В ПРОЦЕССЕ", "after": "ПОСЛЕ работы"}
    await callback.message.edit_text(
        f"📸 Отправь фото <b>{type_labels.get(photo_type, photo_type)}</b>\n\n"
        f"Можно добавить подпись.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(PhotoStates.waiting_photo, F.photo)
async def process_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    photo: PhotoSize = message.photo[-1]

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        photo_repo = PhotoRepository(session)

        # Загружаем в S3
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        s3_key, s3_url = await storage_service.upload_photo(
            file_bytes.read(),
            f"shifts/{data['shift_id']}/{data['photo_type']}_{photo.file_id}.jpg",
        )

        from app.models.models import Photo
        photo_record = Photo(
            file_id=photo.file_id,
            s3_key=s3_key,
            s3_url=s3_url,
            photo_type=PhotoType(data["photo_type"]),
            shift_id=data["shift_id"],
            site_object_id=data["site_object_id"],
            uploaded_by_id=user.id,
            caption=message.caption,
        )
        await photo_repo.save(photo_record)

        # AI анализ (async, не блокируем)
        if s3_url:
            from app.services.services import ai_service
            analysis = await ai_service.analyze_photo(s3_url)
            if "error" not in analysis:
                photo_record.ai_analysis = analysis
                photo_record.has_helmet   = analysis.get("has_helmet")
                photo_record.has_vest     = analysis.get("has_vest")
                photo_record.has_gloves   = analysis.get("has_gloves")
                photo_record.progress_pct = analysis.get("progress_pct")
                photo_record.ai_notes     = analysis.get("notes")
                await photo_repo.save(photo_record)

    await state.clear()

    warning = ""
    # Если AI нашёл нарушения — предупреждение
    if hasattr(photo_record, 'has_helmet') and photo_record.has_helmet is False:
        warning += "\n⚠️ AI: каска не обнаружена!"
    if hasattr(photo_record, 'has_vest') and photo_record.has_vest is False:
        warning += "\n⚠️ AI: жилет не обнаружен!"

    await message.answer(
        f"✅ Фото сохранено!{warning}",
        reply_markup=_main_keyboard(user.role),
    )


# ══════════════════════════════════════════════════════════════════
#  МОИ ЗАДАЧИ
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "📋 Мои задачи")
async def my_tasks(message: Message) -> None:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        task_svc = TaskService(session)
        tasks = await task_svc.get_employee_tasks(user.id)

    if not tasks:
        await message.answer(
            "📋 Задач нет. Хорошая работа! 🎉",
            reply_markup=_main_keyboard(user.role),
        )
        return

    await message.answer(
        f"📋 <b>Твои задачи ({len(tasks)}):</b>",
        parse_mode="HTML",
        reply_markup=kb_tasks(tasks),
    )


@router.callback_query(F.data.startswith("task_view:"))
async def task_view(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
    if not task:
        await callback.answer("Задача не найдена")
        return
    priority_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(task.priority, "⚪")
    deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
    text = (
        f"📋 <b>{task.title}</b>\n\n"
        f"Приоритет: {priority_emoji} {task.priority}\n"
        f"Дедлайн: {deadline_str}\n"
        f"Статус: {task.status}\n\n"
        f"{task.description or ''}"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=kb_task_actions(task.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task_done:"))
async def task_done(callback: CallbackQuery, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])
    await state.set_state(TaskCompleteStates.waiting_report)
    await state.update_data(task_id=task_id)
    await callback.message.edit_text(
        "✅ Напиши краткий отчёт о выполнении задачи:"
    )
    await callback.answer()


@router.message(TaskCompleteStates.waiting_report)
async def task_report(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        task_svc = TaskService(session)
        task = await task_svc.complete_task(data["task_id"], user.id, message.text)
    await state.clear()
    if task:
        await message.answer(
            "✅ Задача отмечена как выполненная!",
            reply_markup=_main_keyboard(user.role),
        )
    else:
        await message.answer("❌ Не удалось завершить задачу.")


# ══════════════════════════════════════════════════════════════════
#  МОИ ЧАСЫ
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "⏱ Мои часы")
async def my_hours(message: Message) -> None:
    await message.answer(
        "⏱ <b>Мои часы</b>\nВыбери период:",
        parse_mode="HTML",
        reply_markup=kb_my_hours_period(),
    )


@router.callback_query(F.data.startswith("hours_"))
async def hours_period(callback: CallbackQuery) -> None:
    period = callback.data.replace("hours_", "")
    today = date.today()

    if period == "today":
        date_from = date_to = today
        label = "Сегодня"
    elif period == "week":
        date_from = today - timedelta(days=today.weekday())
        date_to = today
        label = f"Эта неделя ({date_from.strftime('%d.%m')}–{date_to.strftime('%d.%m')})"
    else:
        date_from = today.replace(day=1)
        date_to = today
        label = f"Этот месяц ({date_from.strftime('%d.%m')}–{date_to.strftime('%d.%m')})"

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        report_svc = ReportService(session)
        total_hours = await report_svc.shift_repo.get_total_hours_by_employee(
            user.id, date_from, date_to
        )
        shifts = await report_svc.shift_repo.get_shifts_by_employee(
            user.id, date_from=date_from, date_to=date_to, limit=10
        )

    shift_lines = ""
    for s in shifts[:5]:
        h = float(s.total_hours or 0)
        shift_lines += f"\n• {s.started_at.strftime('%d.%m')} — {h:.1f} ч."

    await callback.message.edit_text(
        f"⏱ <b>{label}</b>\n\n"
        f"Итого: <b>{total_hours:.1f} ч.</b>\n"
        f"Смен: {len(shifts)}"
        f"{shift_lines}",
        parse_mode="HTML",
        reply_markup=kb_back("back_main"),
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════
#  МЕНЕДЖЕР — Отчёты
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "📊 Отчёты")
async def reports_menu(message: Message) -> None:
    await message.answer(
        "📊 <b>Отчёты</b>\nВыбери тип:",
        parse_mode="HTML",
        reply_markup=kb_report_type(),
    )


@router.callback_query(F.data == "report_employees")
async def report_employees(callback: CallbackQuery) -> None:
    async with async_session_factory() as session:
        report_svc = ReportService(session)
        today = date.today()
        data = await report_svc.get_monthly_summary(today.year, today.month)

    lines = "\n".join(
        f"{i+1}. {row['employee']} — {row['hours']:.1f} ч. "
        f"({'⏰ ' + str(row['late_count']) + ' оп.' if row['late_count'] else ''})"
        for i, row in enumerate(data[:15])
    )
    await callback.message.edit_text(
        f"👥 <b>Сотрудники за {today.strftime('%B %Y')}</b>\n\n{lines}",
        parse_mode="HTML",
        reply_markup=kb_back("back_reports"),
    )
    await callback.answer()


@router.callback_query(F.data == "report_summary")
async def report_summary(callback: CallbackQuery) -> None:
    async with async_session_factory() as session:
        shift_repo = ShiftRepository(session)
        active_today = await shift_repo.get_active_employees_today()

    lines = "\n".join(
        f"• {s.employee.full_name} → {s.site_object.name}"
        for s in active_today
    ) or "Нет активных смен"

    await callback.message.edit_text(
        f"📍 <b>Активные смены прямо сейчас ({len(active_today)}):</b>\n\n{lines}",
        parse_mode="HTML",
        reply_markup=kb_back("back_reports"),
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════
#  МЕНЕДЖЕР — Сотрудники
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "👥 Сотрудники")
async def employees_list(message: Message) -> None:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if user.role == UserRole.EMPLOYEE:
            await message.answer("❌ У тебя нет доступа к этому разделу.")
            return
        employees = await user_repo.get_all_employees()

    await message.answer(
        f"👥 <b>Сотрудники ({len(employees)}):</b>",
        parse_mode="HTML",
        reply_markup=kb_manager_employees(employees),
    )


@router.callback_query(F.data.startswith("employee_view:"))
async def employee_view(callback: CallbackQuery) -> None:
    emp_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        emp = await user_repo.get_by_id(emp_id)
        shift_repo = ShiftRepository(session)
        active = await shift_repo.get_active_shift(emp_id)
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        hours_week = await shift_repo.get_total_hours_by_employee(emp_id, week_start, today)

    status = f"🟢 На объекте" if active else "⚫️ Не работает"
    await callback.message.edit_text(
        f"👤 <b>{emp.full_name}</b>\n\n"
        f"Телефон: {emp.phone or '—'}\n"
        f"Статус: {status}\n"
        f"Часов за неделю: {hours_week:.1f} ч.",
        parse_mode="HTML",
        reply_markup=kb_employee_actions(emp_id),
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════
#  ОБЪЕКТЫ (менеджер)
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "🏗 Объекты")
async def objects_list(message: Message) -> None:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        obj_repo = SiteObjectRepository(session)
        if user.role == UserRole.OWNER:
            objects = await obj_repo.get_active_objects()
        else:
            objects = await obj_repo.get_by_manager(user.id)

    await message.answer(
        f"🏗 <b>Объекты ({len(objects)}):</b>",
        parse_mode="HTML",
        reply_markup=kb_objects_list(objects),
    )


# ══════════════════════════════════════════════════════════════════
#  УНИВЕРСАЛЬНЫЕ CALLBACK
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()


@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
    await callback.message.edit_text("Главное меню 👇")
    await callback.message.answer("👋 Выбери действие:", reply_markup=_main_keyboard(user.role))
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
