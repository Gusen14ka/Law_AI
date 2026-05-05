# Lex Analytica — Техническая документация

## Содержание
1. [Общая архитектура](#1-общая-архитектура)
2. [Технологический стек](#2-технологический-стек)
3. [База данных](#3-база-данных)
4. [Авторизация и аутентификация](#4-авторизация-и-аутентификация)
5. [AI-модуль](#5-ai-модуль)
6. [Бизнес-логика и роли](#6-бизнес-логика-и-роли)
7. [API — полный справочник](#7-api--полный-справочник)
8. [Фронтенд](#8-фронтенд)
9. [Инфраструктура и Docker](#9-инфраструктура-и-docker)
10. [Безопасность](#10-безопасность)

---

## 1. Общая архитектура

Система построена по классической трёхзвенной архитектуре:

```
┌─────────────────────────────────────────────────────────┐
│                     КЛИЕНТ (браузер)                    │
│              Vanilla JS + Vite  :5173                   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP + Cookie (session_token)
                       ▼
┌─────────────────────────────────────────────────────────┐
│               NGINX (reverse proxy)  :80                │
│         /api/* → backend:8000                           │
│         /*     → static files                           │
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
           ▼                          ▼
┌──────────────────┐      ┌────────────────────────────┐
│  FastAPI Backend  │      │    Статика (dist/)         │
│  Python 3.11 :8000│      │    HTML/CSS/JS бандл       │
└──────┬───────────┘      └────────────────────────────┘
       │
       ├──────────────────────────────────┐
       ▼                                  ▼
┌──────────────────┐         ┌────────────────────────┐
│  PostgreSQL 16   │         │   Ollama (LLM) :11434  │
│  :5432           │         │   mistral-nemo:12b     │
│  lexanalytica DB │         │   GPU: RTX 4060        │
└──────────────────┘         └────────────────────────┘
```

Запросы от пользователя идут в браузер → Nginx проксирует `/api/*` на FastAPI, статику отдаёт сам. Все данные хранятся в PostgreSQL. AI-анализ выполняется локально через Ollama на GPU.

### Жизненный цикл запроса на анализ документа

```
Пользователь загружает файл
        │
        ▼
FastAPI: POST /api/requests
        │
        ├─ FileHandler: валидация формата/размера
        ├─ Сохранение файла в /app/uploads/{uuid}.pdf
        ├─ Создание записи DocumentRequest в БД (status=pending_ai)
        │
        ▼
BackgroundTask (async, не блокирует ответ пользователю)
        │
        ├─ DocumentParser: извлечение текста (PyPDF2 / python-docx)
        ├─ Очистка текста (regex)
        ├─ AIModule: стриминг запроса в Ollama
        ├─ ResponseBuilder: парсинг JSON из ответа LLM
        ├─ Обновление записи в БД (status=ai_done, ai_report={...})
        │
        ▼
Пользователь опрашивает GET /api/requests/{uuid}
→ Видит отчёт когда status=ai_done
```

---

## 2. Технологический стек

### Backend

| Компонент | Технология | Версия | Роль |
|-----------|-----------|--------|------|
| Web-фреймворк | FastAPI | 0.115 | HTTP-сервер, маршрутизация, DI |
| ASGI-сервер | Uvicorn | 0.30 | Запуск async приложения |
| ORM | SQLAlchemy | 2.0 (async) | Работа с БД через Python-объекты |
| БД-драйвер | asyncpg | 0.30 | Async PostgreSQL драйвер |
| Валидация | Pydantic v2 | встроен в FastAPI | Схемы запросов/ответов |
| Хэширование паролей | passlib + bcrypt | 1.7.4 | Безопасное хранение паролей |
| HTTP-клиент | httpx | 0.27 | Стриминг запросов к Ollama |
| Парсинг PDF | PyPDF2 | 3.0.1 | Извлечение текста из PDF |
| Парсинг DOCX | python-docx | 1.1.2 | Извлечение текста из Word |
| PDF-отчёты | reportlab | 4.2.2 | Генерация PDF-отчётов |
| Файловый I/O | aiofiles | 23.2.1 | Async запись файлов |

### Frontend

| Компонент | Технология | Роль |
|-----------|-----------|------|
| Сборщик | Vite 5 | Бандлинг, dev-сервер с HMR |
| UI-фреймворк | Vanilla JS | Нет зависимостей рантайма |
| Роутер | Самописный hash-router | Навигация без перезагрузки |
| CSS | Custom (CSS vars) | Тёмная тема, адаптивность |

### Инфраструктура

| Компонент | Технология | Роль |
|-----------|-----------|------|
| Контейнеризация | Docker + Compose | Изоляция сервисов |
| Reverse proxy | Nginx Alpine | Статика + проксирование /api |
| LLM-сервер | Ollama 0.20 | Локальный inference |
| LLM-модель | mistral-nemo:12b | Анализ документов |
| GPU | NVIDIA RTX 4060 (8 ГБ) | Ускорение inference |
| СУБД | PostgreSQL 16 Alpine | Основное хранилище |

---

## 3. База данных

### Подключение

FastAPI использует **асинхронное** подключение через `asyncpg` + `SQLAlchemy[asyncio]`.

```python
# database.py
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@db:5432/lexanalytica",
    echo=False,        # не выводить SQL в лог (включить при отладке)
    pool_pre_ping=True # проверять соединение перед использованием
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

**`expire_on_commit=False`** — важный параметр: без него SQLAlchemy "забывает" атрибуты объектов сразу после `commit()`, что вызывает ошибки при обращении к полям после сохранения.

Сессия БД передаётся в каждый эндпоинт через **Dependency Injection**:

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session  # FastAPI вызывает это как контекстный менеджер
```

### Схема данных

#### Таблица `users`

```sql
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,  -- уникальный индекс
    full_name       VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,          -- bcrypt-хэш, НЕ пароль
    role            user_role NOT NULL DEFAULT 'user',  -- ENUM
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT now()
);

-- ENUM тип для роли
CREATE TYPE user_role AS ENUM ('admin', 'lawyer', 'user');
```

**Индексы:** `email` индексируется автоматически (UNIQUE constraint), это обеспечивает O(log n) поиск при логине.

#### Таблица `document_requests`

```sql
CREATE TABLE document_requests (
    id                   SERIAL PRIMARY KEY,
    uuid                 VARCHAR(36) UNIQUE NOT NULL,  -- публичный ID (не раскрывает seq)
    user_id              INTEGER REFERENCES users(id) NOT NULL,
    lawyer_id            INTEGER REFERENCES users(id),

    -- Файл
    original_filename    VARCHAR(500) NOT NULL,
    file_path            VARCHAR(500) NOT NULL,  -- путь на диске
    file_size            INTEGER NOT NULL,        -- байты

    -- Статус жизненного цикла
    status               request_status NOT NULL DEFAULT 'pending_ai',

    -- Контент
    user_comment         TEXT,
    ai_report            JSONB,        -- структурированный JSON от AI
    ai_analyzed_at       TIMESTAMP,
    lawyer_report        JSONB,        -- JSON заключения юриста
    lawyer_comment       TEXT,
    lawyer_reviewed_at   TIMESTAMP,

    created_at           TIMESTAMP DEFAULT now(),
    updated_at           TIMESTAMP DEFAULT now()
);

CREATE TYPE request_status AS ENUM (
    'pending_ai',       -- только загружен
    'ai_done',          -- AI проанализировал
    'pending_lawyer',   -- отправлен юристу, ожидает
    'lawyer_review',    -- юрист взял в работу
    'lawyer_done',      -- юрист завершил
    'closed'            -- закрыт
);
```

**Почему UUID, а не ID?** Поле `id` — последовательный целочисленный ключ (1, 2, 3...). Если отдать его пользователю, он может перебирать чужие заявки по URL (`/requests/1`, `/requests/2`). UUID (случайный, 36 символов) это исключает — невозможно угадать.

**Почему JSONB для отчётов?** Структура AI-ответа может меняться (разное число рисков, условий). JSONB в PostgreSQL индексируется, поддерживает операторы `->`, `@>`, что позволяет делать сложные запросы по содержимому отчёта в будущем.

### Миграции

Таблицы создаются при старте через `Base.metadata.create_all()`. В production рекомендуется использовать **Alembic** (уже в зависимостях) для версионных миграций.

---

## 4. Авторизация и аутентификация

### Обзор механизма

Используется **серверные сессии с httponly cookies**. Это надёжнее JWT для веб-приложений: cookie недоступна из JavaScript (защита от XSS), сессия хранится на сервере (можно отозвать мгновенно).

### Хэширование паролей (bcrypt)

```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Регистрация — хэшируем пароль
hashed = pwd_context.hash("my_password123")
# Результат: "$2b$12$..." — bcrypt-хэш с солью

# Логин — проверяем пароль
is_valid = pwd_context.verify("my_password123", hashed)
```

**Почему bcrypt?** Bcrypt специально спроектирован для паролей — он медленный (параметр `cost=12` означает 2^12 итераций). Это делает брутфорс нецелесообразным: даже если злоумышленник получит БД, перебор займёт годы. MD5/SHA256 — **не подходят** для паролей: они быстрые.

**Соль** генерируется автоматически для каждого пароля и встраивается в хэш. Это защищает от Rainbow Table атак.

### Жизненный цикл сессии

```
POST /api/auth/login  {email, password}
        │
        ├─ Ищем пользователя в БД по email
        ├─ pwd_context.verify(password, hashed_password)
        ├─ Генерируем токен: secrets.token_urlsafe(32)
        │  Пример: "Kj8mN2xP..." (256 бит случайных данных)
        │
        ├─ Сохраняем в памяти:
        │  _sessions["Kj8mN2xP..."] = {
        │      "user_id": 5,
        │      "role": "lawyer",
        │      "expires": now() + 24h
        │  }
        │
        ├─ Устанавливаем cookie:
        │  Set-Cookie: session_token=Kj8mN2xP...; HttpOnly; SameSite=Lax; Max-Age=86400
        │
        └─ Response: {user: {...}}

--- Следующий запрос ---

GET /api/requests
Cookie: session_token=Kj8mN2xP...
        │
        ├─ get_current_user() читает cookie
        ├─ Ищет токен в _sessions
        ├─ Проверяет expires
        ├─ Загружает User из БД по user_id
        └─ Передаёт объект User в эндпоинт
```

### Cookie параметры

| Параметр | Значение | Назначение |
|---------|---------|-----------|
| `HttpOnly` | true | Cookie недоступна из JS — защита от XSS |
| `SameSite=Lax` | Lax | Отправляется только с "первичных" запросов — защита от CSRF |
| `Max-Age=86400` | 24 часа | Время жизни сессии |
| `Secure` | (добавить в prod) | Только по HTTPS |

### Система ролей (RBAC)

Реализован **Role-Based Access Control**. Три роли образуют иерархию:

```
admin ─── может всё
  │
  ├── lawyer ─── может всё что user + работа с заявками юриста
  │      │
  │      └── user ─── загрузка документов, просмотр своих заявок
```

Технически роли проверяются через FastAPI Dependency:

```python
def require_role(*roles: UserRole):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return current_user
    return checker

# Использование в эндпоинте:
@app.get("/api/lawyer/requests")
async def lawyer_requests(current_user = Depends(require_lawyer)):
    # require_lawyer = require_role(UserRole.admin, UserRole.lawyer)
    ...
```

**Dependency Injection в FastAPI** — это механизм, при котором FastAPI сам вызывает `require_lawyer`, передаёт нужные параметры (сессию БД, cookie из запроса), и если проверка не пройдена — автоматически возвращает 401/403 **до** выполнения тела функции.

### Хранилище сессий

Сейчас сессии хранятся **в памяти** (`_sessions: dict`). Это работает для одного экземпляра, но не масштабируется. В production следует заменить на **Redis**:

```python
# Замена для production:
import redis.asyncio as redis
r = redis.from_url("redis://localhost")
await r.setex(f"session:{token}", 86400, json.dumps(data))
```

---

## 5. AI-модуль

### Ollama и модель mistral-nemo:12b

**Ollama** — это open-source сервер для локального запуска LLM-моделей. Предоставляет REST API совместимый с OpenAI.

**mistral-nemo:12b** — 12-миллиардная модель от Mistral AI. Выбрана по критериям:
- Помещается в 8 ГБ VRAM при квантизации Q4 (~7 ГБ)
- Хорошо понимает русский язык
- Качество выше чем 7B-модели, меньше галлюцинаций
- Apache 2.0 лицензия (коммерческое использование разрешено)

### Стриминг вместо обычного запроса

Проблема: LLM генерирует ответ токен за токеном, ~2-10 токенов/сек на GPU. Для документа в 3000 слов ответ занимает 1-3 минуты. Обычный HTTP-запрос имеет таймаут.

Решение — **HTTP Streaming**:

```python
async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json={...}) as response:
    async for line in response.aiter_lines():
        data = json.loads(line)
        token = data["message"]["content"]  # один токен
        chunks.append(token)
        if data["done"]:
            break
```

Соединение остаётся открытым, данные текут непрерывно. `read=None` в таймауте означает "нет ограничения на время чтения".

### Промпт-инжиниринг

System prompt требует от модели строгого JSON-формата. Это ключевой момент — без него модель добавляет текст до/после JSON, и парсинг ломается.

`ResponseBuilder` реализует три стратегии парсинга (от простого к сложному):
1. Прямой `json.loads()` — если модель вернула чистый JSON
2. Поиск JSON в ````json ... ```` блоке — если модель добавила markdown
3. Поиск `{...}` в тексте — крайний случай

---

## 6. Бизнес-логика и роли

### Жизненный цикл заявки

```
pending_ai → ai_done → pending_lawyer → lawyer_review → lawyer_done
                │
                └── (пользователь может не отправлять юристу)
```

| Статус | Кто устанавливает | Что происходит |
|--------|-------------------|----------------|
| `pending_ai` | System (при загрузке) | Запущен AI-анализ в фоне |
| `ai_done` | System (AI завершил) | Пользователь видит отчёт AI |
| `pending_lawyer` | Пользователь | Заявка попадает в очередь юристов |
| `lawyer_review` | Юрист (POST /take) | Юрист берёт в работу, видит документ |
| `lawyer_done` | Юрист (POST /submit) | Пользователь видит итоговое заключение |

### Контроль доступа к данным

Горизонтальная изоляция (пользователь A не видит данные пользователя B):

```python
@app.get("/api/requests/{uuid}")
async def get_request(uuid: str, current_user: User = Depends(require_any)):
    req = await db.get(DocumentRequest, uuid=uuid)
    
    # Пользователь видит только СВОИ заявки
    if current_user.role == UserRole.user and req.user_id != current_user.id:
        raise HTTPException(status_code=403)
    
    # Юристы и админы видят все заявки
    return req
```

---

## 7. API — полный справочник

Базовый URL: `http://localhost:8000`

### Аутентификация

| Метод | Путь | Тело | Ответ |
|-------|------|------|-------|
| POST | `/api/auth/register` | `{email, full_name, password}` | `{message, user}` |
| POST | `/api/auth/login` | `{email, password}` | `{message, user}` + Set-Cookie |
| POST | `/api/auth/logout` | — | `{message}` + удаление cookie |
| GET | `/api/auth/me` | — | `UserOut` |

### Пользователь

| Метод | Путь | Доступ | Описание |
|-------|------|--------|----------|
| POST | `/api/requests` | any | Загрузить документ (multipart/form-data) |
| GET | `/api/requests` | any | Список своих заявок |
| GET | `/api/requests/{uuid}` | any | Детали заявки |
| POST | `/api/requests/{uuid}/send-to-lawyer` | any | Отправить юристу |

### Юрист

| Метод | Путь | Доступ | Описание |
|-------|------|--------|----------|
| GET | `/api/lawyer/requests?status=new\|mine\|done\|all` | lawyer, admin | Список заявок |
| POST | `/api/lawyer/requests/{uuid}/take` | lawyer, admin | Взять в работу |
| POST | `/api/lawyer/requests/{uuid}/submit` | lawyer, admin | Сохранить заключение |

### Администратор

| Метод | Путь | Доступ | Описание |
|-------|------|--------|----------|
| GET | `/api/admin/users` | admin | Все пользователи |
| PATCH | `/api/admin/users/{id}/role` | admin | Изменить роль |
| PATCH | `/api/admin/users/{id}/toggle` | admin | Активировать/заблокировать |
| GET | `/api/admin/stats` | admin | Статистика системы |

---

## 8. Фронтенд

### Архитектура

Фронтенд — **Single Page Application** без фреймворка. Вся навигация происходит через `window.location.hash` (hash-router), страница не перезагружается.

```
main.js         — bootstrap: проверка авторизации, регистрация роутов
router.js       — hash-router: #/dashboard → вызывает renderDashboard()
store.js        — глобальное состояние: текущий пользователь
api/client.js   — все fetch-запросы к backend
ui.js           — утилиты: el(), toast(), formatDate()
pages/          — страницы (auth, user, lawyer, admin)
components/     — переиспользуемые компоненты (layout с sidebar)
```

### Паттерн рендеринга

Вместо Virtual DOM используется прямое создание DOM-узлов:

```javascript
// ui.js — функция-хелпер
function el(tag, attrs, ...children) {
    const e = document.createElement(tag)
    // attrs.onclick → e.onclick = fn
    // attrs.class → e.className = "..."
    children.forEach(c => e.appendChild(...))
    return e
}

// Использование:
mount('#app', el('div', {class: 'card'},
    el('h2', {}, 'Заголовок'),
    el('p', {}, 'Текст')
))
```

Каждая "страница" — это функция, которая строит DOM и монтирует его в `#app`.

### Защита роутов

```javascript
function guard(requiredRoles, fn) {
    return async (params) => {
        const user = getUser()
        if (!user) { navigate('/login'); return }
        if (!requiredRoles.includes(user.role)) {
            // Редирект на "домашнюю" страницу роли
            navigate(user.role === 'admin' ? '/admin' : '/dashboard')
            return
        }
        fn(params)  // рендер страницы
    }
}
```

---

## 9. Инфраструктура и Docker

### Сеть контейнеров

Docker Compose создаёт изолированную сеть `project_default`. Внутри неё контейнеры обращаются друг к другу по имени сервиса:

```yaml
# backend видит БД как "db:5432"
# backend видит Ollama как "ollama:11434"
# frontend (nginx) проксирует /api/* на "backend:8000"
```

### GPU в Docker

```yaml
ollama:
  image: ollama/ollama:latest
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

Для работы требуется **NVIDIA Container Toolkit** — он пробрасывает GPU драйверы хоста внутрь контейнера. Ollama автоматически определяет GPU и загружает модель в VRAM.

### Healthcheck PostgreSQL

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U lexuser -d lexanalytica"]
  interval: 5s
  retries: 10
```

Backend стартует только после `condition: service_healthy` — это предотвращает ошибки подключения к БД при холодном старте.

---

## 10. Безопасность

### Реализованные меры

| Угроза | Защита |
|--------|--------|
| Перехват сессии через XSS | HttpOnly cookie — JS не может прочитать |
| CSRF-атака | SameSite=Lax — cookie не отправляется с внешних сайтов |
| Brute-force паролей | bcrypt с cost=12, ~300ms на проверку |
| Утечка паролей из БД | bcrypt-хэш вместо открытого пароля |
| SQL-инъекции | Параметризованные запросы SQLAlchemy ORM |
| Горизонтальное превышение прав | Проверка `req.user_id == current_user.id` |
| Раскрытие внутренних ID | UUID вместо последовательных целых |
| Загрузка вредоносных файлов | Whitelist форматов (PDF/DOCX) + проверка размера |

### Рекомендации для production

1. Добавить `Secure` флаг cookie (только HTTPS)
2. Перенести сессии с памяти на Redis
3. Добавить rate limiting (slowapi)
4. Настроить HTTPS через Let's Encrypt
5. Сменить дефолтный пароль администратора
6. Установить `SECRET_KEY` из переменной окружения (не хардкодить)

---

## 11. Тестирование

### 11.1 Юнит-тесты

Файл: `tests/tests.py`

Юнит-тесты проверяют изолированные компоненты без запуска приложения. Используется `pytest`.

| Класс | Проверяемый компонент | Ключевые тесты |
|-------|----------------------|----------------|
| `TestPasswordHashing` | bcrypt | хэширование, верификация, уникальность соли, отклонение пустого пароля |
| `TestResponseBuilder` | Парсинг ответа LLM | чистый JSON, JSON в markdown-блоке, JSON с окружающим текстом, пустой ответ, нормализация уровней риска |
| `TestDocumentParser` | Очистка текста | удаление управляющих символов, схлопывание пробелов, ограничение переводов строк |
| `TestSessionManagement` | Сессии в памяти | создание, получение, удаление, истечение времени, энтропия токенов |

**Запуск:**  
```bash
pytest tests/tests.py -v
```

### 11.2 Регрессионный тест

Класс `TestRegressionCriticalFlows` проверяет, что основные API-сценарии не сломались. Тест пропускается, если сервер не отвечает.

| ID | Проверка | Ожидание |
|----|----------|----------|
| REG-001 | `/api/health` | 200 OK |
| REG-002 | Неверный пароль | 401, не 500 |
| REG-003 | Неавторизованный доступ | 401 |
| REG-004 | Админ‑панель без сессии | 401 |
| REG-005 | Дублирование email | 400 |
| REG-006 | Формат UUID | соответствует стандарту |
| REG-007 | Хэш пароля в ответе | отсутствует (`$2b$` не виден) |

### 11.3 Нагрузочный тест (Locust)

Класс `LexAnalyticaUser` эмулирует поведение пользователя:

- регистрация + логин при старте;
- `@task(5)` – список заявок;
- `@task(3)` – детали заявки (случайный UUID);
- `@task(1)` – профиль;
- `@task(1)` – health.

**Запуск с веб‑интерфейсом:**  
```bash
locust -f tests.py --host=http://localhost:8000
```
**Headless (20 пользователей, 60 сек):**  
```bash
locust -f tests.py --host=http://localhost:8000 --users=20 --spawn-rate=2 --run-time=60s --headless
```

### 11.4 Тесты безопасности

#### SQL‑инъекции

Список вредоносных payloads (например, `' OR '1'='1`, `'; DROP TABLE users; --`, `' UNION SELECT * FROM users --`) подставляется в поля:

- `email` при логине;
- `password` при логине;
- `full_name` при регистрации.

**Ожидаемый результат:** ни один payload не вызывает `500 Internal Server Error`, не возвращает чужих данных, таблица `users` остаётся нетронутой.

#### Горизонтальные привилегии

Проверяется, что обычный пользователь **не может**:

- получить заявку другого пользователя по UUID (`403` или `404`);
- зайти на `/api/admin/users` (`403`);
- зайти на `/api/lawyer/requests` (`403`).

---

## 12. Тестирование графического интерфейса

Файл: `tests/gui_test.md` (содержит как автоматизированный скрипт на Playwright, так и ручные сценарии)

### 12.1 Автоматизированный тест (Playwright)

Скрипт `gui_test.py` последовательно выполняет:

1. Регистрация нового пользователя.
2. Логин.
3. Загрузка PDF (создаётся временный валидный PDF).
4. Проверка появления заявки в списке.
5. Навигация через боковое меню.
6. Выход.
7. Вход под администратором → проверка статистики и таблицы пользователей.
8. Смена роли (`user` → `lawyer`).
9. Блокировка пользователя.
10. Попытка прямого доступа к защищённому роуту после выхода → редирект на логин.

**Запуск:**  
```bash
pip install playwright
playwright install chromium
python gui_test.py
```

### 12.2 Ручные сценарии

Таблицы с шагами для трёх ключевых сценариев:

- **GUI-001: Регистрация** – проверка валидации, дубликата email, редиректов.
- **GUI-002: Загрузка документа** – drag&drop, preview, отправка, отслеживание статуса.
- **GUI-003: Работа юриста** – взятие заявки, редактирование, сохранение заключения.

Каждый шаг содержит ожидаемый визуальный результат.

---

## 13. Приёмо-сдаточные сценарии (10 пунктов)

Файл: `tests/acceptance_tests.md`

| № | Название | Основные критерии приёмки |
|---|----------|---------------------------|
| АС‑001 | Регистрация и авторизация | Сессия сохраняется после перезагрузки, выход чистит cookie, дубликат email → ошибка |
| АС‑002 | Загрузка документа и AI‑анализ | Поддерживаются PDF/DOCX; .exe и >15 МБ отклоняются; статус меняется с `pending_ai` → `ai_done`; отчёт содержит summary и риски |
| АС‑003 | Отправка заявки юристу | Кнопка только при `ai_done`; статус становится `pending_lawyer`; повторная отправка невозможна |
| АС‑004 | Работа юриста | Юрист берёт заявку → редактирует отчёт → сохраняет → заявка переходит в `lawyer_done` |
| АС‑005 | Разграничение доступа по ролям | User не видит чужие заявки и админ‑панель; lawyer не видит админ‑панель; admin видит всё |
| АС‑006 | Панель администратора | Статистика (4 карточки), таблица пользователей, смена роли, блокировка (кроме себя) |
| АС‑007 | SQL‑инъекции | Ни один payload из списка не вызывает 500 и не раскрывает данные |
| АС‑008 | Производительность (нагрузочный тест) | P95 времени ответа < 500 мс, ошибок < 1% при 20 RPS |
| АС‑009 | Мониторинг и алерты | Отключение `backend` → алерт `WebServiceDown` → email администратору; после включения – resolved |
| АС‑010 | Логирование | 5 событий (логин, загрузка, анализ, смена роли, ошибка) видны в Grafana → Explore → Loki |

Каждый сценарий заканчивается чек-листом и полями для подписей QA и заказчика.

---

## 14. Дашборды Grafana (4 уровня)

Все дашборды автоматически подключаются через provisioning (`monitoring/grafana/provisioning/dashboards/dashboards.yml`).  
Источники: Prometheus (метрики приложения, БД, хоста) и Loki (логи).

| Уровень | Файл | Название в Grafana | Ключевые панели |
|---------|------|-------------------|------------------|
| **Executive / Business Overview** | `1_executive.json` | Lex Analytica — Overview | Статус сервиса, RPS, успешность, NPS/CSAT/CES, uptime за 24ч, трафик по статусам, перцентили, бизнес-активность (AI-анализы, отправки юристам), логи |
| **Service Overview** | `2_service.json` | Lex Analytica — Service Overview | Health‑статусы (backend, БД, Ollama), RPS (общий), успешность (non‑5xx), P95 по эндпоинтам, ошибки 4xx/5xx, логи предупреждений и ошибок |
| **Infrastructure / Resource** | `3_infra.json` | Lex Analytica — Infrastructure / Resource | CPU (проценты, по ядрам), RAM, диск (корневой раздел), сетевой трафик (RX/TX), IOPS диска, загрузка GPU (опционально) |
| **Debugging / Deep Dive** | `4_debug.json` | Lex Analytica — Debugging / Deep Dive | P50/P95/P99 латентность, топ‑5 медленных эндпоинтов, частота ошибок по HTTP-статусам, гистограмма длительности AI-анализа, полные логи (все уровни), активные сессии, очередь AI, загружено документов за час |

Дашборды используют переменные времени и автообновление (30 с для Executive, 15 с для Debugging).

---

## 15. Алертинг

### 15.1 Правила алертов (`rules.yml`)

| Алерт | Условие | `for` | Severity | Действие |
|-------|---------|-------|----------|----------|
| `WebServiceDown` | `up{job="lex-backend"} == 0` | 30 с | critical | Email (critical) |
| `DatabaseDown` | `pg_up == 0` | 30 с | critical | Email (critical) |
| `OllamaDown` | `up{job="ollama-health"} == 0` | 60 с | warning | Email (warning) |
| `HighResponseTime` | P95 латентность > 5 с | 2 мин | warning | Email (warning) |
| `HighErrorRate` | 5xx / все запросы > 5% | 2 мин | warning | Email (warning) |
| `HighCPU` | CPU > 85% | 5 мин | warning | Email (warning) |
| `LowDiskSpace` | Свободно < 15% | 5 мин | warning | Email (warning) |
| `HighMemory` | RAM > 90% | 5 мин | warning | Email (warning) |
| `TooManyConnections` | PG connections > 80 | 2 мин | warning | Email (warning) |

### 15.2 Alertmanager (`alertmanager.yml`)

- **SMTP** (Gmail) – настроены `smtp_smarthost`, `smtp_auth_username`, `app‑password`.
- **Маршрутизация:** critical → немедленно (group_wait 10 с), warning → с паузой (2 мин). Повтор критических – каждый час, предупреждений – каждые 6 часов.
- **Email шаблон** содержит HTML с атрибутами `{{ .Annotations.summary }}`, `{{ .Annotations.description }}`, время и ссылки на Grafana/Prometheus.
- **Inhibit_rule:** critical подавляет warning для того же сервиса.

### 15.3 Тест алерта

Сценарий (АС‑009):

```bash
docker-compose stop backend
# Подождать 60–90 секунд
# Проверить Prometheus: /alerts → WebServiceDown = FIRING
# Проверить почту
docker-compose start backend
# Через 60 секунд приходит resolved-письмо
```

---

## 16. Логгирование в Grafana (Loki + Promtail)

### 16.1 Архитектура

- **Loki** – горизонтально масштабируемый агрегатор логов (хранилище, без индексации содержимого).
- **Promtail** – агент, собирающий логи из Docker-контейнеров через `/var/run/docker.sock`. Добавляет лейблы: `container`, `service` (из compose-проекта), `job=docker`.
- **Grafana** – подключается к Loki как datasource (автоматически через provisioning).

### 16.2 Настройки

- **Loki** (`loki.yml`): хранение на filesystem, retention 720ч (30 дней), ограничение ingestion 16 МБ/с.
- **Promtail** (`promtail.yml`): docker service discovery, релейблинг лейблов, парсинг JSON‑логов (если приложение пишет JSON), выделение уровня (`level`).
- **Grafana datasource** настраивается в `provisioning/datasources/`.

### 16.3 Использование

В любом дашборде можно добавить панель типа `Logs` с запросом, например:  
`{service="backend"} |= "ERROR"`

В Explore – свободный поиск по логам с фильтрацией по лейблам и регулярным выражениям.

---

## 17. Метрики NPS, CSAT, CES

### 17.1 Сбор метрик

В `backend/modules/metrics.py` реализованы:

- **Prometheus‑метрики**:
  - `lex_nps_score` (Gauge)
  - `lex_csat_score` (Gauge)
  - `lex_ces_score` (Gauge)
  - счётчики ответов: `lex_nps_responses_total` и аналоги.

- **In‑memory хранилище** (для демонстрации; в production заменить на Redis):
  - `_nps_scores: list[int]`
  - `_csat_scores: list[float]`
  - `_ces_scores: list[float]`

### 17.2 API для сбора feedback

| Эндпоинт | Метод | Тело | Описание |
|----------|-------|------|----------|
| `/api/feedback/nps` | POST | `{"score": 0-10, "comment": "..."}` | NPS (Net Promoter Score). Рассчитывается как % промоутеров (9–10) минус % детракторов (0–6). |
| `/api/feedback/csat` | POST | `{"score": 1-5, "request_uuid": "...", "comment": "..."}` | CSAT – удовлетворённость конкретным анализом. |
| `/api/feedback/ces` | POST | `{"score": 1-7, "feature": "upload/analysis", "comment": "..."}` | CES – лёгкость использования (1 – очень легко, 7 – очень сложно). |
| `/api/feedback/stats` | GET | – | Возвращает текущие агрегированные значения (NPS в ‑100…+100, средние CSAT/CES) и количество ответов. |

### 17.3 Расчёт и обновление в Prometheus

При каждом новом ответе:

- добавляется значение в список;
- пересчитывается среднее (для CSAT/CES) или NPS;
- обновляется Gauge-метрика (`nps_gauge.set(current)`).

Grafana дашборды отображают эти метрики в реальном времени (панели типа `Stat` или `Gauge`).

### 17.4 Интеграция с UI

На фронтенде после завершения анализа пользователю предлагается форма обратной связи (звёзды для CSAT, шкала 0–10 для NPS, шкала 1–7 для CES). При отправке вызывается соответствующий API.

---