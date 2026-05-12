"""
FastAPI Admin Panel API
JWT auth + RBAC endpoints для дашборда.
"""

from __future__ import annotations
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.core.config.settings import settings
from app.core.database.engine import async_session_factory
from app.core.security.jwt import create_access_token, verify_token
from app.repositories.repositories import (
    UserRepository, SiteObjectRepository, ShiftRepository,
    TaskRepository, PhotoRepository, NotificationRepository,
)
from app.models.models import UserRole, ShiftStatus, ObjectStatus

logger = logging.getLogger(__name__)
security = HTTPBearer()


# ══════════════════════════════════════════════════════════════════
#  PYDANTIC SCHEMAS (DTO)
# ══════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserDTO(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: Optional[str]
    phone: Optional[str]
    role: str
    is_active: bool
    last_seen_at: Optional[datetime]

    class Config:
        from_attributes = True


class SiteObjectDTO(BaseModel):
    id: int
    name: str
    address: str
    client_name: Optional[str]
    latitude: float
    longitude: float
    radius_meters: int
    status: str
    planned_hours: Optional[float]
    manager_id: Optional[int]

    class Config:
        from_attributes = True


class SiteObjectCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    address: str = Field(..., min_length=5)
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    latitude: float
    longitude: float
    radius_meters: int = Field(100, ge=50, le=500)
    planned_hours: Optional[float] = None
    manager_id: Optional[int] = None
    notes: Optional[str] = None


class ShiftDTO(BaseModel):
    id: int
    employee_id: int
    site_object_id: int
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    total_hours: Optional[float]
    is_late: bool
    late_minutes: int

    class Config:
        from_attributes = True


class TaskCreateDTO(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    description: Optional[str] = None
    assignee_id: int
    site_object_id: Optional[int] = None
    deadline: Optional[datetime] = None
    priority: str = "medium"


class DashboardStats(BaseModel):
    active_shifts_count: int
    employees_total: int
    employees_active_today: int
    objects_total: int
    objects_active: int
    hours_today: float
    late_today: int
    tasks_pending: int
    tasks_overdue: int


class EmployeeStats(BaseModel):
    employee_id: int
    employee_name: str
    total_hours: float
    shifts_count: int
    late_count: int
    overtime_hours: float


# ══════════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="MontazhBot Admin API",
    description="REST API для административной панели системы контроля монтажников",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


def require_role(*roles: str):
    async def checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return checker


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(request: LoginRequest):
    """Вход в админку. Email и пароль из .env."""
    if request.email != settings.ADMIN_EMAIL or request.password != settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token({"sub": request.email, "role": "owner"})
    return TokenResponse(
        access_token=token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ══════════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════════

@app.get("/dashboard/stats", response_model=DashboardStats, tags=["Dashboard"])
async def dashboard_stats(current_user=Depends(require_role("owner", "manager"))):
    async with async_session_factory() as session:
        user_repo  = UserRepository(session)
        obj_repo   = SiteObjectRepository(session)
        shift_repo = ShiftRepository(session)
        task_repo  = TaskRepository(session)

        employees        = await user_repo.get_all_employees()
        active_today     = await shift_repo.get_active_employees_today()
        all_objects      = await obj_repo.get_active_objects()
        today            = date.today()
        total_hours_today = sum(
            float(s.total_hours or 0) for s in active_today
        )
        late_today = sum(1 for s in active_today if s.is_late)
        overdue    = await task_repo.get_overdue_tasks()
        pending_count = len(await task_repo.get_tasks_for_employee(0))  # placeholder

        return DashboardStats(
            active_shifts_count=len(active_today),
            employees_total=len(employees),
            employees_active_today=len(set(s.employee_id for s in active_today)),
            objects_total=len(all_objects),
            objects_active=len(all_objects),
            hours_today=round(total_hours_today, 1),
            late_today=late_today,
            tasks_pending=0,
            tasks_overdue=len(overdue),
        )


@app.get("/dashboard/live-locations", tags=["Dashboard"])
async def live_locations(current_user=Depends(require_role("owner", "manager"))):
    """Актуальные координаты всех активных сотрудников."""
    from app.core.cache.redis_client import redis_client
    locations = await redis_client.get_all_active_locations()
    return {"locations": locations, "count": len(locations)}


# ══════════════════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════════════════

@app.get("/users", response_model=List[UserDTO], tags=["Users"])
async def get_users(
    role: Optional[str] = Query(None),
    active_only: bool = True,
    current_user=Depends(require_role("owner", "manager")),
):
    async with async_session_factory() as session:
        repo = UserRepository(session)
        users = await repo.get_all_employees(active_only=active_only)
    return users


@app.get("/users/{user_id}", response_model=UserDTO, tags=["Users"])
async def get_user(user_id: int, current_user=Depends(require_role("owner", "manager"))):
    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/users/{user_id}/stats", tags=["Users"])
async def get_user_stats(
    user_id: int,
    date_from: date = Query(default_factory=lambda: date.today().replace(day=1)),
    date_to: date = Query(default_factory=date.today),
    current_user=Depends(require_role("owner", "manager")),
):
    async with async_session_factory() as session:
        shift_repo = ShiftRepository(session)
        user_repo  = UserRepository(session)
        user       = await user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        shifts      = await shift_repo.get_shifts_by_employee(user_id, date_from, date_to)
        total_hours = await shift_repo.get_total_hours_by_employee(user_id, date_from, date_to)
        late_count  = sum(1 for s in shifts if s.is_late)
        overtime    = sum(float(s.overtime_hours or 0) for s in shifts)

    return {
        "employee": user.full_name,
        "period": {"from": str(date_from), "to": str(date_to)},
        "total_hours": round(total_hours, 1),
        "shifts_count": len(shifts),
        "late_count": late_count,
        "overtime_hours": round(overtime, 1),
    }


# ══════════════════════════════════════════════════════════════════
#  OBJECTS
# ══════════════════════════════════════════════════════════════════

@app.get("/objects", response_model=List[SiteObjectDTO], tags=["Objects"])
async def get_objects(current_user=Depends(require_role("owner", "manager"))):
    async with async_session_factory() as session:
        repo = SiteObjectRepository(session)
        return await repo.get_active_objects()


@app.post("/objects", response_model=SiteObjectDTO, tags=["Objects"])
async def create_object(
    data: SiteObjectCreate,
    current_user=Depends(require_role("owner", "manager")),
):
    from app.models.models import SiteObject
    import uuid as _uuid
    async with async_session_factory() as session:
        repo = SiteObjectRepository(session)
        obj = SiteObject(
            **data.model_dump(),
            qr_code=str(_uuid.uuid4())[:8].upper(),
        )
        return await repo.save(obj)


@app.get("/objects/{object_id}/shifts", tags=["Objects"])
async def get_object_shifts(
    object_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user=Depends(require_role("owner", "manager")),
):
    async with async_session_factory() as session:
        repo = ShiftRepository(session)
        shifts = await repo.get_shifts_by_object(object_id, date_from, date_to)
        total = sum(float(s.total_hours or 0) for s in shifts)
    return {"shifts": shifts, "total_hours": round(total, 1)}


# ══════════════════════════════════════════════════════════════════
#  SHIFTS
# ══════════════════════════════════════════════════════════════════

@app.get("/shifts/active", tags=["Shifts"])
async def get_active_shifts(current_user=Depends(require_role("owner", "manager"))):
    async with async_session_factory() as session:
        repo = ShiftRepository(session)
        return await repo.get_active_employees_today()


@app.get("/shifts/{shift_id}", response_model=ShiftDTO, tags=["Shifts"])
async def get_shift(shift_id: int, current_user=Depends(get_current_user)):
    async with async_session_factory() as session:
        repo = ShiftRepository(session)
        shift = await repo.get_by_id(shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift


# ══════════════════════════════════════════════════════════════════
#  TASKS
# ══════════════════════════════════════════════════════════════════

@app.post("/tasks", tags=["Tasks"])
async def create_task(
    data: TaskCreateDTO,
    current_user=Depends(require_role("owner", "manager")),
):
    from app.services.services import TaskService
    async with async_session_factory() as session:
        svc = TaskService(session)
        task = await svc.create_task(
            creator_id=current_user.get("user_id", 1),
            **data.model_dump(),
        )
    return {"id": task.id, "title": task.title, "status": task.status}


@app.get("/tasks", tags=["Tasks"])
async def get_tasks(
    status: Optional[str] = None,
    assignee_id: Optional[int] = None,
    current_user=Depends(require_role("owner", "manager")),
):
    async with async_session_factory() as session:
        repo = TaskRepository(session)
        if assignee_id:
            from app.models.models import TaskStatus as TS
            s = TS(status) if status else None
            tasks = await repo.get_tasks_for_employee(assignee_id, s)
        else:
            tasks = await repo.get_overdue_tasks()
    return tasks


# ══════════════════════════════════════════════════════════════════
#  REPORTS
# ══════════════════════════════════════════════════════════════════

@app.get("/reports/monthly", tags=["Reports"])
async def monthly_report(
    year: int = Query(default_factory=lambda: datetime.now().year),
    month: int = Query(default_factory=lambda: datetime.now().month),
    current_user=Depends(require_role("owner", "manager")),
):
    from app.services.services import ReportService
    async with async_session_factory() as session:
        svc = ReportService(session)
        return await svc.get_monthly_summary(year, month)


@app.get("/reports/export/excel", tags=["Reports"])
async def export_excel(
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user=Depends(require_role("owner", "manager")),
):
    from app.utils.excel_export import generate_excel_report
    from fastapi.responses import StreamingResponse
    import io

    async with async_session_factory() as session:
        shift_repo = ShiftRepository(session)
        user_repo  = UserRepository(session)
        employees  = await user_repo.get_all_employees()

        data = []
        for emp in employees:
            shifts = await shift_repo.get_shifts_by_employee(emp.id, date_from, date_to)
            for s in shifts:
                data.append({
                    "Сотрудник": emp.full_name,
                    "Объект": s.site_object_id,
                    "Дата": s.started_at.strftime("%d.%m.%Y"),
                    "Начало": s.started_at.strftime("%H:%M"),
                    "Конец": s.ended_at.strftime("%H:%M") if s.ended_at else "—",
                    "Часы": float(s.total_hours or 0),
                    "Опоздание": s.late_minutes,
                })

    content = await generate_excel_report(data)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=report_{date_from}_{date_to}.xlsx"},
    )


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
