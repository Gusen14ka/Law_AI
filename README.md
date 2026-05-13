# ⚖ Lex Analytica v2.0

## Структура проекта

```
lex-analytica/
├── docker-compose.yml          ← ВСЁ в одном файле (приложение + мониторинг)
├── pull-model.sh               ← скачать LLM модель после первого запуска
│
├── backend/                    ← FastAPI (Python)
│   ├── main.py
│   ├── models.py               ← таблицы БД
│   ├── database.py             ← подключение PostgreSQL
│   ├── auth.py                 ← сессии + bcrypt
│   ├── schemas.py              ← Pydantic схемы
│   ├── requirements.txt
│   ├── Dockerfile
│   └── modules/
│       ├── ai_module.py        ← Ollama streaming
│       ├── document_parser.py  ← PyPDF2 + python-docx
│       ├── response_builder.py ← парсинг ответа LLM
│       ├── file_handler.py     ← валидация файлов
│       ├── report_generator.py ← PDF-отчёты
│       └── metrics.py          ← Prometheus + NPS/CSAT/CES
│
├── frontend/                   ← Vanilla JS + Vite + Nginx
│   ├── src/
│   │   ├── pages/              ← auth, user, lawyer, admin
│   │   ├── components/         ← layout (sidebar)
│   │   ├── api/client.js       ← все fetch-запросы
│   │   ├── main.js / router.js / store.js / ui.js
│   │   └── style.css
│   ├── index.html
│   ├── nginx.conf
│   └── Dockerfile
│
├── monitoring/
│   ├── prometheus/
│   │   ├── prometheus.yml      ← что собирать
│   │   └── rules.yml           ← правила алертов
│   ├── alertmanager/
│   │   └── alertmanager.yml    ← куда слать (email)  ← НАСТРОИТЬ
│   ├── loki/loki.yml           ← хранение логов
│   ├── promtail/promtail.yml   ← сбор Docker-логов
│   └── grafana/provisioning/   ← автоподключение datasources
│
├── tests/
│   ├── tests.py                ← unit + regression + нагрузочный + security
│   ├── alert_test.py           ← тест алерта (стоп сервис → email)
│   ├── gui_test.md             ← Playwright + ручные сценарии
│   └── acceptance_tests.md     ← 10 приёмо-сдаточных сценариев
│
└── docs/
    └── DOCUMENTATION.md        ← полная техническая документация
```

---

## Запуск — пошаговая инструкция

### Шаг 1 — Предварительные требования

Убедитесь что установлены:
- **Docker Desktop** (Windows/Mac) или Docker Engine (Linux)
- **NVIDIA Container Toolkit** — для GPU (RTX 4060)

Проверить GPU в Docker:
```bash
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```
Если видите карточку — GPU работает. Если ошибка — установите [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

> **Без GPU тоже работает** — Ollama автоматически переключится на CPU, анализ будет медленнее (~3-7 мин вместо ~30 сек).

---

### Шаг 2 — Настройка email-алертов (опционально)

Откройте `monitoring/alertmanager/alertmanager.yml` и замените:

```yaml
smtp_auth_username: 'your-gmail@gmail.com'   # ваш Gmail
smtp_auth_password: 'xxxx xxxx xxxx xxxx'    # App Password (не обычный пароль!)
```

Как получить App Password для Gmail:
1. Аккаунт Google → Безопасность
2. Включить двухфакторную аутентификацию
3. Безопасность → Пароли приложений → Создать
4. Скопировать 16-значный код

Также замените адрес получателя:
```yaml
to: 'your-email@example.com'
```

---

### Шаг 3 — Запуск всего

```bash
docker-compose up --build
```

Первый запуск занимает 3-5 минут (скачиваются образы).

Когда увидите в логах:
```
backend-1   | INFO:     Application startup complete.
frontend-1  | /docker-entrypoint.sh: Configuration complete; ready for start up
grafana-1   | logger=http.server t=... msg="HTTP Server Listen"
```
— всё готово.

---

### Шаг 4 — Скачать LLM модель

В **новом терминале** (пока контейнеры работают):

```bash
# Windows
docker exec -it lex-analytica-ollama-1 ollama pull mistral-nemo:12b

# Linux / Mac
bash pull-model.sh
```

Скачивание ~7 ГБ, займёт 5-15 минут. Прогресс видно в терминале.

> Если имя контейнера другое — найдите его: `docker ps | grep ollama`

---

### Шаг 5 — Открыть приложение

| Что | Адрес | Логин |
|-----|-------|-------|
| 🌐 Приложение | http://localhost:5173 | admin@lexanalytica.ru / admin123 |
| 📊 Grafana | http://localhost:3000 | admin / admin123 |
| 🔥 Prometheus | http://localhost:9090 | — |
| 🔔 Alertmanager | http://localhost:9093 | — |
| 📖 API Docs | http://localhost:8000/docs | — |

---

### Шаг 6 — Проверить что всё работает

```bash
# Сервис отвечает?
curl http://localhost:8000/api/health
# → {"status":"ok"}

# Метрики собираются?
curl http://localhost:8000/metrics | head -20

# Модель загружена на GPU?
docker exec -it lex-analytica-ollama-1 ollama ps
# → mistral-nemo:12b ... 7.2 GiB  100% GPU
```

В Grafana (http://localhost:3000):
- Explore → выбрать Loki → запустить `{service="backend"}` — появятся логи
- Dashboards → Lex Analytica → Executive Overview — статус системы

---

## Запуск тестов

```bash
cd tests

# Установить зависимости
pip install pytest bcrypt locust requests

# Unit-тесты (без запущенного сервера, быстро)
pytest tests.py -v -k "not Regression and not SQL and not Horizontal"

# Все тесты включая безопасность (нужен запущенный сервер)
pytest tests.py -v

# Нагрузочный тест — откройте http://localhost:8089
locust -f tests.py --host=http://localhost:8000

# Нагрузочный тест без UI (50 пользователей, 60 секунд)
locust -f tests.py --host=http://localhost:8000 \
       --users=50 --spawn-rate=5 --run-time=60s --headless

# Тест алерта (нужен настроенный SMTP в alertmanager.yml)
python alert_test.py
```

---

## Полезные команды

```bash
# Посмотреть логи конкретного сервиса
docker-compose logs -f backend
docker-compose logs -f ollama

# Перезапустить только backend после изменений в коде
docker-compose restart backend

# Остановить всё
docker-compose down

# Остановить и удалить данные (БД, логи, модели)
docker-compose down -v

# Зайти внутрь контейнера
docker exec -it lex-analytica-backend-1 bash
```

---

## Роли пользователей

| Роль | Возможности |
|------|-------------|
| **user** | Загрузка документов, просмотр AI-отчёта, отправка юристу |
| **lawyer** | Новые заявки → взять в работу → редактировать отчёт → сохранить |
| **admin** | Всё выше + управление пользователями, смена ролей, блокировка |

Сменить роль: войти как admin → Пользователи → выбрать роль в dropdown.
