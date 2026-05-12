# 🏗️ MontazhBot — Система контроля монтажников

Production-ready Telegram bot для строительных и монтажных компаний.

## 🚀 Быстрый старт

```bash
git clone <repo>
cd montazh_bot
cp .env.example .env        # заполни переменные
docker compose up -d        # запуск всех сервисов
docker compose exec app alembic upgrade head  # миграции
```

Бот готов к работе.

---

## 🏛️ Архитектура

```
montazh_bot/
├── app/
│   ├── bot/                  # Telegram bot (aiogram 3)
│   │   ├── handlers/         # Обработчики команд и callback
│   │   ├── middlewares/      # Auth, logging, rate limit
│   │   ├── keyboards/        # Inline и Reply клавиатуры
│   │   └── filters/          # Фильтры ролей
│   ├── api/                  # FastAPI admin panel
│   │   ├── routers/          # REST endpoints
│   │   ├── schemas/          # Pydantic DTO
│   │   └── dependencies/     # DI, auth
│   ├── core/
│   │   ├── config/           # Settings (pydantic-settings)
│   │   ├── database/         # SQLAlchemy async engine
│   │   ├── cache/            # Redis client
│   │   └── security/         # JWT, RBAC, crypto
│   ├── models/               # SQLAlchemy ORM models
│   ├── repositories/         # Repository pattern (DB layer)
│   ├── services/             # Business logic
│   ├── tasks/                # APScheduler jobs
│   ├── utils/                # Helpers: geo, excel, pdf
│   └── integrations/         # AI, S3, external APIs
├── migrations/               # Alembic
├── docker/                   # Dockerfiles
├── nginx/                    # Nginx config
├── tests/
└── docs/                     # API docs, ER diagram
```

---

## 🎭 Роли

| Роль | Описание |
|------|----------|
| `OWNER` | Полный доступ, все объекты, все сотрудники |
| `MANAGER` | Только свои объекты и сотрудники |
| `EMPLOYEE` | Смены, фото, задачи, свои часы |

---

## 📱 Telegram функции

- ✅ Регистрация по номеру телефона
- ✅ Начало/конец смены с GPS
- ✅ Проверка геолокации (радиус 100м)
- ✅ Live tracking каждые 15 минут
- ✅ Фотоотчёты (до/в процессе/после)
- ✅ AI проверка фото (каска, жилет, прогресс)
- ✅ Задачи от менеджера
- ✅ Уведомления об опозданиях/переработках
- ✅ QR check-in на объекте

---

## 🔧 Технологии

| Компонент | Технология |
|-----------|-----------|
| Bot | aiogram 3.x |
| API | FastAPI |
| DB | PostgreSQL 15 + SQLAlchemy 2 async |
| Cache | Redis 7 |
| Queue | APScheduler |
| Storage | S3 (MinIO self-hosted) |
| AI | OpenAI Vision API |
| Auth | JWT + RBAC |
| Deploy | Docker Compose + Nginx |

---

## 🌍 Переменные окружения

Смотри `.env.example`

---

## 📊 Admin API

Swagger UI: `http://localhost:8000/docs`

---

## 🚢 Production deploy

Смотри `docs/DEPLOYMENT.md`
