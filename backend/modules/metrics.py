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

logger = logging.getLogger("lex_analytica.metrics")

# ── Кастомные бизнес-метрики ──────────────────────────────────────────────────

ai_analyses_total = Counter(
    "lex_ai_analyses_total",
    "Общее число AI-анализов",
    ["status"]  # success / error
)

ai_analysis_duration = Histogram(
    "lex_ai_analysis_duration_seconds",
    "Время AI-анализа одного документа",
    buckets=[10, 30, 60, 120, 180, 300, 600]
)

active_sessions = Gauge(
    "lex_active_sessions_total",
    "Активных пользовательских сессий"
)

ai_queue_size = Gauge(
    "lex_ai_queue_size",
    "Документов в очереди на AI-анализ"
)

documents_uploaded = Counter(
    "lex_documents_uploaded_total",
    "Загруженных документов",
    ["file_type"]
)

requests_sent_to_lawyer = Counter(
    "lex_requests_sent_to_lawyer_total",
    "Заявок отправленных юристу"
)

requests_reviewed_by_lawyer = Counter(
    "lex_requests_reviewed_by_lawyer_total",
    "Заявок проверенных юристом"
)

# NPS/CSAT/CES gauges — видны в Grafana
nps_gauge = Gauge("lex_nps_score", "Net Promoter Score (-100 до 100)")
csat_gauge = Gauge("lex_csat_score", "Customer Satisfaction Score (1-5)")
ces_gauge = Gauge("lex_ces_score", "Customer Effort Score (1-7)")
nps_responses_total = Counter("lex_nps_responses_total", "Количество NPS-ответов")
csat_responses_total = Counter("lex_csat_responses_total", "Количество CSAT-ответов")
ces_responses_total = Counter("lex_ces_responses_total", "Количество CES-ответов")

# In-memory хранилище (замените Redis в продакшне)
_nps_scores: list[int] = []
_csat_scores: list[float] = []
_ces_scores: list[float] = []


def setup_metrics(app):
    """Подключить Prometheus instrumentator к FastAPI."""
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/api/health", "/docs", "/openapi.json"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus metrics enabled at /metrics")


def _calc_nps(scores: list[int]) -> float:
    if not scores:
        return 0.0
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return round((promoters - detractors) / len(scores) * 100, 1)


# ── Feedback API ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class NPSSubmit(BaseModel):
    score: int          # 0-10
    comment: Optional[str] = None


class CSATSubmit(BaseModel):
    score: float        # 1-5
    request_uuid: Optional[str] = None
    comment: Optional[str] = None


class CESSubmit(BaseModel):
    score: float        # 1-7
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
    logger.info(f"NPS response: score={data.score}, current_nps={current}")
    return {"message": "Спасибо!", "current_nps": current, "total": len(_nps_scores)}


@router.post("/csat")
async def submit_csat(data: CSATSubmit):
    if not 1 <= data.score <= 5:
        raise HTTPException(status_code=400, detail="CSAT score: 1-5")
    _csat_scores.append(data.score)
    csat_responses_total.inc()
    avg = round(statistics.mean(_csat_scores), 2)
    csat_gauge.set(avg)
    return {"message": "Спасибо!", "current_csat": avg, "total": len(_csat_scores)}


@router.post("/ces")
async def submit_ces(data: CESSubmit):
    if not 1 <= data.score <= 7:
        raise HTTPException(status_code=400, detail="CES score: 1-7")
    _ces_scores.append(data.score)
    ces_responses_total.inc()
    avg = round(statistics.mean(_ces_scores), 2)
    ces_gauge.set(avg)
    return {"message": "Спасибо!", "current_ces": avg, "total": len(_ces_scores)}


@router.get("/stats")
async def feedback_stats():
    return {
        "nps": {
            "score": _calc_nps(_nps_scores),
            "total_responses": len(_nps_scores),
            "promoters": sum(1 for s in _nps_scores if s >= 9),
            "passives": sum(1 for s in _nps_scores if 7 <= s <= 8),
            "detractors": sum(1 for s in _nps_scores if s <= 6),
        },
        "csat": {
            "score": round(statistics.mean(_csat_scores), 2) if _csat_scores else None,
            "total_responses": len(_csat_scores),
        },
        "ces": {
            "score": round(statistics.mean(_ces_scores), 2) if _ces_scores else None,
            "total_responses": len(_ces_scores),
        }
    }
