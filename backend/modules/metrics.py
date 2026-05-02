"""
Модуль метрик — Prometheus + NPS/CSAT/CES.

Подключение в main.py:
    from modules.metrics import setup_metrics, router as metrics_router
    setup_metrics(app)
    app.include_router(metrics_router)
"""

from prometheus_client import Counter, Histogram, Gauge, Summary
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import statistics

# ── Prometheus метрики ────────────────────────────────────────────────────────

# Счётчик AI-анализов
ai_analyses_total = Counter(
    "lex_ai_analyses_total",
    "Общее число выполненных AI-анализов",
    ["status"]  # success / error
)

# Время AI-анализа
ai_analysis_duration = Histogram(
    "lex_ai_analysis_duration_seconds",
    "Время выполнения AI-анализа документа",
    buckets=[10, 30, 60, 120, 180, 300, 600]
)

# Активные сессии
active_sessions = Gauge(
    "lex_active_sessions_total",
    "Количество активных пользовательских сессий"
)

# Размер очереди AI
ai_queue_size = Gauge(
    "lex_ai_queue_size",
    "Документов в очереди на AI-анализ"
)

# Загрузки документов
documents_uploaded = Counter(
    "lex_documents_uploaded_total",
    "Загруженных документов",
    ["file_type"]  # pdf / docx
)

# Заявки отправленные юристу
requests_sent_to_lawyer = Counter(
    "lex_requests_sent_to_lawyer_total",
    "Заявок отправленных на проверку юристу"
)

# Заявки проверенные юристом
requests_reviewed_by_lawyer = Counter(
    "lex_requests_reviewed_by_lawyer_total",
    "Заявок проверенных юристом"
)


def setup_metrics(app):
    """Подключить Prometheus к FastAPI приложению."""
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/api/health"],
    ).instrument(app).expose(app, endpoint="/metrics")


# ── NPS / CSAT / CES хранилище (in-memory, замените на Redis/БД) ─────────────

_nps_scores: list[int] = []      # -100..100 (promoters - detractors)
_csat_scores: list[float] = []   # 1..5
_ces_scores: list[float] = []    # 1..7

# Prometheus gauges для Grafana
nps_gauge = Gauge("lex_nps_score", "Текущий NPS Score (-100 до 100)")
csat_gauge = Gauge("lex_csat_score", "Текущий CSAT Score (1-5)")
ces_gauge = Gauge("lex_ces_score", "Текущий CES Score (1-7, меньше = лучше)")

nps_responses_total = Counter("lex_nps_responses_total", "Количество NPS-ответов")
csat_responses_total = Counter("lex_csat_responses_total", "Количество CSAT-ответов")
ces_responses_total = Counter("lex_ces_responses_total", "Количество CES-ответов")


def _calc_nps(scores: list[int]) -> float:
    """NPS = %промоутеров (9-10) - %критиков (0-6)"""
    if not scores:
        return 0
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return round((promoters - detractors) / len(scores) * 100, 1)


# ── API роутер для метрик качества ───────────────────────────────────────────

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class NPSSubmit(BaseModel):
    score: int          # 0-10 (насколько вероятно порекомендуете)
    comment: Optional[str] = None


class CSATSubmit(BaseModel):
    score: float        # 1-5 (удовлетворённость)
    request_uuid: Optional[str] = None
    comment: Optional[str] = None


class CESSubmit(BaseModel):
    score: float        # 1-7 (насколько легко было пользоваться)
    feature: Optional[str] = None   # какой функцией пользовались
    comment: Optional[str] = None


@router.post("/nps")
async def submit_nps(data: NPSSubmit):
    """
    NPS — Net Promoter Score.
    Вопрос: «Насколько вероятно, что вы порекомендуете Lex Analytica? (0-10)»
    9-10 = промоутеры, 7-8 = нейтральные, 0-6 = критики
    """
    if not 0 <= data.score <= 10:
        raise HTTPException(status_code=400, detail="NPS score должен быть 0-10")

    _nps_scores.append(data.score)
    nps_responses_total.inc()

    # Обновляем Prometheus gauge
    current_nps = _calc_nps(_nps_scores)
    nps_gauge.set(current_nps)

    return {
        "message": "Спасибо за оценку!",
        "current_nps": current_nps,
        "total_responses": len(_nps_scores)
    }


@router.post("/csat")
async def submit_csat(data: CSATSubmit):
    """
    CSAT — Customer Satisfaction Score.
    Вопрос: «Насколько вы довольны анализом документа? (1-5)»
    """
    if not 1 <= data.score <= 5:
        raise HTTPException(status_code=400, detail="CSAT score должен быть 1-5")

    _csat_scores.append(data.score)
    csat_responses_total.inc()

    avg = round(statistics.mean(_csat_scores), 2)
    csat_gauge.set(avg)

    return {
        "message": "Спасибо за оценку!",
        "current_csat": avg,
        "total_responses": len(_csat_scores)
    }


@router.post("/ces")
async def submit_ces(data: CESSubmit):
    """
    CES — Customer Effort Score.
    Вопрос: «Насколько легко вам было загрузить и получить анализ документа? (1-7)»
    1 = очень легко, 7 = очень сложно
    """
    if not 1 <= data.score <= 7:
        raise HTTPException(status_code=400, detail="CES score должен быть 1-7")

    _ces_scores.append(data.score)
    ces_responses_total.inc()

    avg = round(statistics.mean(_ces_scores), 2)
    ces_gauge.set(avg)

    return {
        "message": "Спасибо за оценку!",
        "current_ces": avg,
        "total_responses": len(_ces_scores)
    }


@router.get("/stats")
async def feedback_stats():
    """Текущие значения всех метрик качества."""
    return {
        "nps": {
            "score": _calc_nps(_nps_scores),
            "total_responses": len(_nps_scores),
            "promoters": sum(1 for s in _nps_scores if s >= 9),
            "passives": sum(1 for s in _nps_scores if 7 <= s <= 8),
            "detractors": sum(1 for s in _nps_scores if s <= 6),
            "description": "Net Promoter Score: насколько вероятно порекомендуют"
        },
        "csat": {
            "score": round(statistics.mean(_csat_scores), 2) if _csat_scores else None,
            "total_responses": len(_csat_scores),
            "description": "Customer Satisfaction: удовлетворённость анализом (1-5)"
        },
        "ces": {
            "score": round(statistics.mean(_ces_scores), 2) if _ces_scores else None,
            "total_responses": len(_ces_scores),
            "description": "Customer Effort: простота использования (1-7, меньше = лучше)"
        }
    }
