import asyncio
import os
import uuid
import aiofiles
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Response, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database import get_db, init_db
from models import User, DocumentRequest, UserRole, RequestStatus
from auth import (
    hash_password, verify_password, create_session, destroy_session,
    get_current_user, require_admin, require_lawyer, require_any, _sessions
)
from schemas import (
    RegisterRequest, LoginRequest, UserOut, RequestOut, RequestListItem,
    LawyerReportSubmit, UpdateUserRole
)
from modules.document_parser import DocumentParser
from modules.ai_module import AIModule
from modules.response_builder import ResponseBuilder
from modules.metrics import (
    setup_metrics, router as metrics_router,
    ai_analyses_total, ai_analysis_duration,
    active_sessions, ai_queue_size,
    documents_uploaded, requests_sent_to_lawyer, requests_reviewed_by_lawyer
)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("lex_analytica")

app = FastAPI(title="Lex Analytica API", version="2.0.0")

# Prometheus metrics
setup_metrics(app)
app.include_router(metrics_router)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 15 * 1024 * 1024

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

parser = DocumentParser()
ai = AIModule()
builder = ResponseBuilder()



@app.on_event("startup")
async def startup():
    await init_db()
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "admin@lexanalytica.ru"))
        if not result.scalar_one_or_none():
            admin = User(
                email="admin@lexanalytica.ru",
                full_name="Администратор",
                hashed_password=hash_password("admin123"),
                role=UserRole.admin
            )
            db.add(admin)
            await db.commit()
            logger.info("Default admin created: admin@lexanalytica.ru / admin123")


@app.middleware("http")
async def update_session_gauge(request: Request, call_next):
    active_sessions.set(len(_sessions))
    response = await call_next(request)
    return response


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register")
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == data.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    user = User(
        email=data.email.lower(),
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=UserRole.user
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"New user registered: {user.email}")
    return {"message": "Регистрация успешна", "user": UserOut.model_validate(user)}


@app.post("/api/auth/login")
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        logger.warning(f"Failed login attempt for: {data.email}")
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    token = create_session(user.id, user.role.value)
    response.set_cookie(
        key="session_token", value=token, httponly=True,
        samesite="lax", max_age=86400, path="/"
    )
    logger.info(f"User logged in: {user.email} role={user.role.value}")
    return {"message": "Вход выполнен", "user": UserOut.model_validate(user)}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        destroy_session(token)
    response.delete_cookie("session_token")
    return {"message": "Выход выполнен"}


@app.get("/api/auth/me")
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


# ── User requests ─────────────────────────────────────────────────────────────

@app.post("/api/requests")
async def create_request(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any)
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Только PDF и DOCX")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл слишком большой (макс 15 МБ)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Файл пустой")

    file_uuid = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{file_uuid}{ext}"
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    req = DocumentRequest(
        user_id=current_user.id,
        original_filename=file.filename,
        file_path=str(save_path),
        file_size=len(content),
        status=RequestStatus.pending_ai,
        user_comment=comment or None
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    documents_uploaded.inc()
    ai_queue_size.inc()
    logger.info(f"Document uploaded: {file.filename} by user_id={current_user.id}")

    background_tasks.add_task(run_ai_analysis, req.id, str(save_path), file.filename)

    return {"message": "Документ загружен, анализ начат", "request_id": req.id, "uuid": req.uuid}


async def run_ai_analysis(request_id: int, file_path: str, filename: str):
    from database import AsyncSessionLocal
    start = time.time()
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(DocumentRequest).where(DocumentRequest.id == request_id))
            req = result.scalar_one_or_none()
            if not req:
                return

            text = parser.extract_text(file_path, filename)
            if not text or len(text.strip()) < 30:
                req.status = RequestStatus.ai_done
                req.ai_report = {"error": "Не удалось извлечь текст из документа"}
                req.ai_analyzed_at = datetime.utcnow()
                await db.commit()
                ai_analyses_total.labels(status="error").inc()
                return

            raw = await ai.analyze(text)
            report = builder.parse(raw)

            req.ai_report = report
            req.ai_analyzed_at = datetime.utcnow()
            req.status = RequestStatus.ai_done
            await db.commit()

            duration = time.time() - start
            ai_analysis_duration.observe(duration)
            ai_analyses_total.labels(status="success").inc()
            ai_queue_size.dec()
            logger.info(f"AI analysis done for request_id={request_id} in {duration:.1f}s")

        except Exception as e:
            logger.error(f"AI analysis failed for request_id={request_id}: {e}")
            try:
                req.status = RequestStatus.ai_done
                req.ai_report = {"error": str(e)}
                req.ai_analyzed_at = datetime.utcnow()
                await db.commit()
                ai_analyses_total.labels(status="error").inc()
                ai_queue_size.dec()
            except Exception:
                pass


@app.get("/api/requests")
async def list_my_requests(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_any)):
    result = await db.execute(
        select(DocumentRequest)
        .where(DocumentRequest.user_id == current_user.id)
        .options(selectinload(DocumentRequest.user), selectinload(DocumentRequest.lawyer))
        .order_by(DocumentRequest.created_at.desc())
    )
    return [RequestListItem.model_validate(r) for r in result.scalars().all()]


@app.get("/api/requests/{req_uuid}")
async def get_request(req_uuid: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_any)):
    result = await db.execute(
        select(DocumentRequest).where(DocumentRequest.uuid == req_uuid)
        .options(selectinload(DocumentRequest.user), selectinload(DocumentRequest.lawyer))
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if current_user.role == UserRole.user and req.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return RequestOut.model_validate(req)


@app.post("/api/requests/{req_uuid}/send-to-lawyer")
async def send_to_lawyer(req_uuid: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_any)):
    result = await db.execute(select(DocumentRequest).where(DocumentRequest.uuid == req_uuid))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if req.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    if req.status != RequestStatus.ai_done:
        raise HTTPException(status_code=400, detail="Дождитесь завершения AI-анализа")
    req.status = RequestStatus.pending_lawyer
    await db.commit()
    requests_sent_to_lawyer.inc()
    logger.info(f"Request {req_uuid} sent to lawyer by user_id={current_user.id}")
    return {"message": "Заявка отправлена на проверку юристу"}


# ── Lawyer ────────────────────────────────────────────────────────────────────

@app.get("/api/lawyer/requests")
async def lawyer_list_requests(status: str = "all", db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lawyer)):
    query = select(DocumentRequest).options(selectinload(DocumentRequest.user), selectinload(DocumentRequest.lawyer))
    if status == "new":
        query = query.where(DocumentRequest.status == RequestStatus.pending_lawyer)
    elif status == "mine":
        query = query.where(DocumentRequest.lawyer_id == current_user.id, DocumentRequest.status == RequestStatus.lawyer_review)
    elif status == "done":
        query = query.where(DocumentRequest.status == RequestStatus.lawyer_done)
    else:
        query = query.where(DocumentRequest.status.in_([RequestStatus.pending_lawyer, RequestStatus.lawyer_review, RequestStatus.lawyer_done]))
    result = await db.execute(query.order_by(DocumentRequest.updated_at.desc()))
    return [RequestListItem.model_validate(r) for r in result.scalars().all()]


@app.post("/api/lawyer/requests/{req_uuid}/take")
async def take_request(req_uuid: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lawyer)):
    result = await db.execute(select(DocumentRequest).where(DocumentRequest.uuid == req_uuid))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if req.status != RequestStatus.pending_lawyer:
        raise HTTPException(status_code=400, detail="Заявка уже взята или не ожидает проверки")
    req.lawyer_id = current_user.id
    req.status = RequestStatus.lawyer_review
    await db.commit()
    logger.info(f"Request {req_uuid} taken by lawyer_id={current_user.id}")
    return {"message": "Заявка взята в работу"}


@app.post("/api/lawyer/requests/{req_uuid}/submit")
async def submit_lawyer_review(req_uuid: str, data: LawyerReportSubmit, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lawyer)):
    result = await db.execute(select(DocumentRequest).where(DocumentRequest.uuid == req_uuid))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if req.lawyer_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Это не ваша заявка")
    if req.status not in (RequestStatus.lawyer_review, RequestStatus.lawyer_done):
        raise HTTPException(status_code=400, detail="Заявка не в работе")
    req.lawyer_report = data.model_dump()
    req.lawyer_comment = data.lawyer_comment
    req.lawyer_reviewed_at = datetime.utcnow()
    req.status = RequestStatus.lawyer_done
    await db.commit()
    requests_reviewed_by_lawyer.inc()
    logger.info(f"Lawyer review submitted for {req_uuid} by lawyer_id={current_user.id}")
    return {"message": "Отчёт юриста сохранён"}


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def admin_list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@app.patch("/api/admin/users/{user_id}/role")
async def admin_update_role(user_id: int, data: UpdateUserRole, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя изменить свою роль")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    old_role = user.role.value
    user.role = data.role
    await db.commit()
    logger.info(f"User {user.email} role changed: {old_role} → {data.role.value} by admin_id={current_user.id}")
    return {"message": f"Роль изменена на {data.role.value}"}


@app.patch("/api/admin/users/{user_id}/toggle")
async def admin_toggle_user(user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать себя")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.is_active = not user.is_active
    await db.commit()
    action = "activated" if user.is_active else "blocked"
    logger.info(f"User {user.email} {action} by admin_id={current_user.id}")
    return {"message": "активен" if user.is_active else "заблокирован", "is_active": user.is_active}


@app.get("/api/admin/stats")
async def admin_stats(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    total_requests = (await db.execute(select(func.count(DocumentRequest.id)))).scalar()
    pending = (await db.execute(select(func.count(DocumentRequest.id)).where(DocumentRequest.status == RequestStatus.pending_lawyer))).scalar()
    lawyer_done = (await db.execute(select(func.count(DocumentRequest.id)).where(DocumentRequest.status == RequestStatus.lawyer_done))).scalar()
    return {"total_users": total_users, "total_requests": total_requests, "pending_lawyer": pending, "lawyer_done": lawyer_done}
