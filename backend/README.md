# ⚖ Lex Analytica — Юридический AI-помощник

Полнофункциональное приложение для анализа юридических документов (PDF, DOCX) с использованием AI.

---

## Архитектура

```
frontend/index.html   — единый HTML-файл (React-подобный SPA)
backend/
  main.py             — FastAPI приложение
  modules/
    file_handler.py   — валидация и сохранение файлов
    document_parser.py — извлечение текста (PyPDF2, python-docx)
    ai_module.py      — отправка в LLM (Ollama / HuggingFace)
    response_builder.py — парсинг и структурирование ответа AI
    report_generator.py — генерация PDF-отчёта (reportlab)
docker-compose.yml    — запуск всего через Docker
```

---

## Быстрый старт через Docker (рекомендуется)

```bash
# 1. Запустить всё одной командой:
docker-compose up --build

# 2. Открыть фронтенд:
open frontend/index.html
# Или просто открыть файл в браузере

# Бэкенд будет доступен на: http://localhost:8000
# Ollama (LLM) на: http://localhost:11434
```

Первый запуск скачает модель Mistral (~4 ГБ). Требуется интернет.

---

## Ручной запуск (без Docker)

### 1. Установить Ollama (бесплатный локальный LLM)

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Запустить сервер
ollama serve

# Скачать модель (в другом терминале)
ollama pull mistral
# Альтернативы: llama3, qwen2.5, gemma3
```

### 2. Запустить бэкенд

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Открыть фронтенд

```bash
open frontend/index.html
```

---

## Использование HuggingFace (без Ollama)

Если не хотите запускать Ollama локально — используйте бесплатный HuggingFace Inference API:

```bash
# 1. Зарегистрируйтесь на huggingface.co
# 2. Получите токен: https://huggingface.co/settings/tokens
# 3. Установите переменную среды:

export HF_API_TOKEN=hf_ваш_токен_здесь
uvicorn main:app --reload
```

---

## Фронтенд (автономный режим)

`frontend/index.html` может работать **полностью без бэкенда** — напрямую через Anthropic API.

Для этого в браузере нужно разрешить CORS или открыть файл локально.

> **Примечание**: При прямом использовании API ключ Anthropic передаётся через браузер.
> Для продакшена — использовать бэкенд как прокси.

---

## API эндпоинты (бэкенд)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | /api/upload | Загрузка и анализ документа |
| POST | /api/report | Генерация PDF-отчёта |
| GET | /api/health | Проверка состояния сервера |

### Пример запроса:

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@contract.pdf"
```

### Пример ответа:

```json
{
  "success": true,
  "filename": "contract.pdf",
  "analyzed_at": "2025-01-15T10:30:00Z",
  "document_stats": { "characters": 4500, "words": 900 },
  "analysis": {
    "summary": "Договор аренды жилого помещения...",
    "document_type": "Договор аренды",
    "parties": ["Арендодатель: Иванов И.И.", "Арендатор: Петров П.П."],
    "key_terms": [...],
    "risks": [...],
    "plain_language_summary": "..."
  }
}
```

---

## Используемые технологии (все бесплатные и open-source)

| Компонент | Технология | Лицензия |
|-----------|-----------|----------|
| Фронтенд | Vanilla JS (HTML/CSS/JS) | — |
| PDF в браузере | PDF.js (Mozilla) | Apache 2.0 |
| DOCX в браузере | Mammoth.js | MIT |
| Бэкенд | FastAPI | MIT |
| PDF парсинг | PyPDF2 | BSD |
| DOCX парсинг | python-docx | MIT |
| PDF генерация | ReportLab | BSD |
| LLM (локально) | Ollama + Mistral 7B | MIT / Apache |
| LLM (облако) | HuggingFace Inference API | бесплатный tier |

---

## Требования к системе

- Python 3.11+
- 8 ГБ RAM (для запуска Mistral локально)
- Или: HuggingFace аккаунт (бесплатный)
- Docker + Docker Compose (для быстрого запуска)
