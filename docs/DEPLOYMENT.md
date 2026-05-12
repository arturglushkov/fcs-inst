# 🚀 Deployment Guide — MontazhBot

## Требования к серверу

- Ubuntu 22.04 LTS
- 2 CPU, 4 GB RAM (минимум)
- Docker 24+ и Docker Compose v2
- Домен с настроенным DNS A-записью

---

## Шаг 1 — Получить бот токен

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. `/newbot` → придумай имя → получи токен
3. Скопируй токен в `.env` → `BOT_TOKEN=...`

---

## Шаг 2 — Клонировать и настроить

```bash
git clone <repo> montazh_bot
cd montazh_bot
cp .env.example .env
nano .env          # заполни все переменные
```

Обязательно заполни:
- `BOT_TOKEN` — токен от BotFather
- `BOT_WEBHOOK_URL` — https://твой-домен.com
- `POSTGRES_PASSWORD` — придумай сложный пароль
- `REDIS_PASSWORD` — придумай сложный пароль
- `JWT_SECRET_KEY` — минимум 32 символа, случайная строка
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — для входа в API

Сгенерировать случайные ключи:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Шаг 3 — SSL сертификат

```bash
# Установить certbot
apt install certbot

# Получить сертификат (домен должен смотреть на сервер)
certbot certonly --standalone -d yourdomain.com

# Скопировать в nginx/ssl/
mkdir -p nginx/ssl
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/
```

---

## Шаг 4 — Запуск

```bash
# Собрать и запустить все сервисы
docker compose up -d --build

# Применить миграции БД
docker compose run --rm migrate

# Проверить логи
docker compose logs -f app
docker compose logs -f api
```

---

## Шаг 5 — Проверка

```bash
# Бот отвечает?
curl https://yourdomain.com/health

# API работает?
curl https://yourdomain.com/api/health

# Webhook установлен?
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

---

## Управление

```bash
# Перезапуск
docker compose restart app

# Просмотр логов
docker compose logs -f app --tail=100

# Остановка
docker compose down

# Обновление (после git pull)
docker compose up -d --build app api

# Бэкап БД
docker compose exec db pg_dump -U montazh montazh_bot > backup_$(date +%Y%m%d).sql
```

---

## Первоначальная настройка в боте

1. Открой бота в Telegram, отправь `/start`
2. Зарегистрируйся как owner — первый пользователь автоматически получает роль employee, смени через API:

```bash
# Войти в API
curl -X POST https://yourdomain.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@yourcompany.com","password":"your_password"}'

# Сохрани access_token из ответа
TOKEN="eyJ..."

# Поменять роль (user_id из /users)
curl -X PATCH https://yourdomain.com/api/users/1/role \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role":"owner"}'
```

3. Добавь объекты через API или через бот командой /admin
4. Пригласи сотрудников — они регистрируются через /start

---

## Автообновление SSL

```bash
# Добавить в crontab
0 3 * * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /path/to/montazh_bot/nginx/ssl/ && \
  cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /path/to/montazh_bot/nginx/ssl/ && \
  docker compose -f /path/to/montazh_bot/docker-compose.yml restart nginx
```

---

## Мониторинг

```bash
# Использование ресурсов
docker stats

# Размер БД
docker compose exec db psql -U montazh -c "\l+"

# Место на диске
df -h
du -sh ./  # размер проекта
```

---

## Возможные проблемы

| Проблема | Решение |
|----------|---------|
| Бот не отвечает | Проверь `docker compose logs app`, убедись что BOT_TOKEN правильный |
| Webhook не работает | Проверь что домен доступен, SSL настроен, порт 443 открыт |
| БД не подключается | Проверь `POSTGRES_PASSWORD` в .env, подожди 10с после запуска |
| Redis ошибка аутентификации | Убедись что `REDIS_PASSWORD` одинаковый в .env и команде redis |
| Фото не загружаются | Проверь MinIO запущен, `S3_ACCESS_KEY`/`S3_SECRET_KEY` правильные |
