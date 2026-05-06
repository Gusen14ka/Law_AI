"""
Prometheus метрики + NPS/CSAT/CES для Lex Analytica.
"""

from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import statistics
import logging
import requests
import threading
import time

logger = logging.getLogger("lex_analytica.metrics")


# ───────────────────────────────────────────────────────────────────────────────
# SYSTEM / OLLAMA METRICS
# ───────────────────────────────────────────────────────────────────────────────

ollama_up = Gauge("ollama_up", "Ollama доступность (1=ok, 0=fail)")
ollama_models_count = Gauge("ollama_models_count", "Количество моделей в Ollama")
ollama_request_duration = Histogram(
    "ollama_request_duration_seconds",
    "Время ответа Ollama /api/tags"
)


def check_ollama():
    """Проверка Ollama health + моделей"""
    start = time.time()

    try:
        r = requests.get("http://lex-ollama:11434/api/tags", timeout=2)
        duration = time.time() - start

        ollama_request_duration.observe(duration)

        if r.status_code == 200:
            data = r.json()
            ollama_up.set(1)
            ollama_models_count.set(len(data.get("models", [])))
        else:
            ollama_up.set(0)

    except Exception:
        ollama_up.set(0)


def ollama_loop():
    """Фоновый мониторинг Ollama"""
    while True:
        check_ollama()
        time.sleep(10)


def start_ollama_monitoring():
    thread = threading.Thread(target=ollama_loop, daemon=True)
    thread.start()


# ───────────────────────────────────────────────────────────────────────────────
# BUSINESS METRICS
# ───────────────────────────────────────────────────────────────────────────────

ai_analyses_total = Counter(
    "lex_ai_analyses_total",
    "Общее число AI-анализов",
    ["status"]
)

ai_analysis_duration = Histogram(
    "lex_ai_analysis_duration_seconds",
    "Время AI-анализа одного документа",
    buckets=[10, 30, 60, 120, 180, 300, 600]
)

active_sessions = Gauge("lex_active_sessions_total", "Активных пользовательских сессий")

ai_queue_size = Gauge("lex_ai_queue_size", "Документов в очереди на AI-анализ")

documents_uploaded = Counter("lex_documents_uploaded_total", "Загруженных документов")

requests_sent_to_lawyer = Counter("lex_requests_sent_to_lawyer_total", "Заявок отправленных юристу")

requests_reviewed_by_lawyer = Counter("lex_requests_reviewed_by_lawyer_total", "Заявок проверенных юристом")


# ───────────────────────────────────────────────────────────────────────────────
# NPS / CSAT / CES
# ───────────────────────────────────────────────────────────────────────────────

nps_gauge = Gauge("lex_nps_score", "Net Promoter Score (-100 до 100)")
csat_gauge = Gauge("lex_csat_score", "Customer Satisfaction Score (1-5)")
ces_gauge = Gauge("lex_ces_score", "Customer Effort Score (1-7)")

nps_responses_total = Counter("lex_nps_responses_total", "Количество NPS-ответов")
csat_responses_total = Counter("lex_csat_responses_total", "Количество CSAT-ответов")
ces_responses_total = Counter("lex_ces_responses_total", "Количество CES-ответов")


_nps_scores: list[int] = []
_csat_scores: list[float] = []
_ces_scores: list[float] = []


# ───────────────────────────────────────────────────────────────────────────────
# FASTAPI SETUP
# ───────────────────────────────────────────────────────────────────────────────

def setup_metrics(app):
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/api/health", "/docs", "/openapi.json"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    start_ollama_monitoring()

    logger.info("Prometheus metrics enabled at /metrics + Ollama monitoring started")


# ───────────────────────────────────────────────────────────────────────────────
# NPS LOGIC
# ───────────────────────────────────────────────────────────────────────────────

def _calc_nps(scores: list[int]) -> float:
    if not scores:
        return 0.0
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return round((promoters - detractors) / len(scores) * 100, 1)


# ───────────────────────────────────────────────────────────────────────────────
# FEEDBACK API
# ───────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class NPSSubmit(BaseModel):
    score: int
    comment: Optional[str] = None


class CSATSubmit(BaseModel):
    score: float
    request_uuid: Optional[str] = None
    comment: Optional[str] = None


class CESSubmit(BaseModel):
    score: float
    feature: Optional[str] = None
    comment: Optional[str] = None


@router.post("/nps")
async def submit_nps(data: NPSSubmit):
    if not 0 <= data.score <= 10:
        raise HTTPException(status_code=400, detail="NPS score: 0-10")

    _nps_scores.append(data.score)
    nps_responses_total.inc()

    current = _calc_nps(_nps_scores)
    nps_gauge.set(current)

    return {"message": "Спасибо!", "current_nps": current}


@router.post("/csat")
async def submit_csat(data: CSATSubmit):
    if not 1 <= data.score <= 5:
        raise HTTPException(status_code=400, detail="CSAT score: 1-5")

    _csat_scores.append(data.score)
    csat_responses_total.inc()

    csat_gauge.set(round(statistics.mean(_csat_scores), 2))

    return {"message": "Спасибо!"}


@router.post("/ces")
async def submit_ces(data: CESSubmit):
    if not 1 <= data.score <= 7:
        raise HTTPException(status_code=400, detail="CES score: 1-7")

    _ces_scores.append(data.score)
    ces_responses_total.inc()

    ces_gauge.set(round(statistics.mean(_ces_scores), 2))

    return {"message": "Спасибо!"}


@router.get("/stats")
async def feedback_stats():
    return {
        "nps": _calc_nps(_nps_scores),
        "csat": round(statistics.mean(_csat_scores), 2) if _csat_scores else None,
        "ces": round(statistics.mean(_ces_scores), 2) if _ces_scores else None,
    }