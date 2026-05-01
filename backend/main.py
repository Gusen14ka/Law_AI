import os
import uuid
import aiofiles
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
    get_current_user, require_admin, require_lawyer, require_any
)
from schemas import (
    RegisterRequest, LoginRequest, UserOut, RequestOut, RequestListItem,
    LawyerReportSubmit, UpdateUserRole
)
from modules.document_parser import DocumentParser
from modules.ai_module import AIModule
from modules.response_builder import ResponseBuilder

app = FastAPI(title="Lex Analytica API", version="2.0.0")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB

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
    # Create default admin if not exists
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
            print("[STARTUP] Default admin created: admin@lexanalytica.ru / admin123")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Auth routes ───────────────────────────────────────────────────────────────

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
    return {"message": "Регистрация успешна", "user": UserOut.model_validate(user)}


@app.post("/api/auth/login")
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")

    token = create_session(user.id, user.role.value)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
        path="/"
    )
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


# ── User: document requests ───────────────────────────────────────────────────

@app.post("/api/requests")
async def create_request(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any)
):
    # Validate file
    ext = Path(file.filename).suffix.lower() # type: ignore
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Только PDF и DOCX")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл слишком большой (макс 15 МБ)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Файл пустой")

    # Save file
    file_uuid = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{file_uuid}{ext}"
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    # Create DB record
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

    # Run AI analysis in background
    background_tasks.add_task(run_ai_analysis, req.id, str(save_path), file.filename) # type: ignore

    return {"message": "Документ загружен, анализ начат", "request_id": req.id, "uuid": req.uuid}


async def run_ai_analysis(request_id: int, file_path: str, filename: str):
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(DocumentRequest).where(DocumentRequest.id == request_id)
            )
            req = result.scalar_one_or_none()
            if not req:
                return

            text = parser.extract_text(file_path, filename)
            if not text or len(text.strip()) < 30:
                req.status = RequestStatus.ai_done
                req.ai_report = {"error": "Не удалось извлечь текст из документа"}
                req.ai_analyzed_at = datetime.utcnow()
                await db.commit()
                return

            raw = await ai.analyze(text)
            report = builder.parse(raw) # type: ignore

            req.ai_report = report
            req.ai_analyzed_at = datetime.utcnow()
            req.status = RequestStatus.ai_done
            await db.commit()
            print(f"[AI] Request {request_id} analyzed successfully")

        except Exception as e:
            print(f"[AI] Error analyzing request {request_id}: {e}")
            try:
                req.status = RequestStatus.ai_done # type: ignore
                req.ai_report = {"error": str(e)} # type: ignore
                req.ai_analyzed_at = datetime.utcnow() # type: ignore
                await db.commit()
            except Exception:
                pass


@app.get("/api/requests")
async def list_my_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any)
):
    result = await db.execute(
        select(DocumentRequest)
        .where(DocumentRequest.user_id == current_user.id)
        .options(selectinload(DocumentRequest.user), selectinload(DocumentRequest.lawyer))
        .order_by(DocumentRequest.created_at.desc())
    )
    requests = result.scalars().all()
    return [RequestListItem.model_validate(r) for r in requests]


@app.get("/api/requests/{req_uuid}")
async def get_request(
    req_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any)
):
    result = await db.execute(
        select(DocumentRequest)
        .where(DocumentRequest.uuid == req_uuid)
        .options(selectinload(DocumentRequest.user), selectinload(DocumentRequest.lawyer))
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # Users can only see their own; lawyers/admins see all
    if current_user.role == UserRole.user and req.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")

    return RequestOut.model_validate(req)


@app.post("/api/requests/{req_uuid}/send-to-lawyer")
async def send_to_lawyer(
    req_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any)
):
    result = await db.execute(
        select(DocumentRequest).where(DocumentRequest.uuid == req_uuid)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if req.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    if req.status != RequestStatus.ai_done:
        raise HTTPException(status_code=400, detail="Дождитесь завершения AI-анализа")

    req.status = RequestStatus.pending_lawyer
    await db.commit()
    return {"message": "Заявка отправлена на проверку юристу"}


# ── Lawyer routes ─────────────────────────────────────────────────────────────

@app.get("/api/lawyer/requests")
async def lawyer_list_requests(
    status: str = "all",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lawyer)
):
    query = select(DocumentRequest).options(
        selectinload(DocumentRequest.user), selectinload(DocumentRequest.lawyer)
    )

    if status == "new":
        query = query.where(DocumentRequest.status == RequestStatus.pending_lawyer)
    elif status == "mine":
        query = query.where(
            DocumentRequest.lawyer_id == current_user.id,
            DocumentRequest.status == RequestStatus.lawyer_review
        )
    elif status == "done":
        query = query.where(DocumentRequest.status == RequestStatus.lawyer_done)
    else:
        query = query.where(DocumentRequest.status.in_([
            RequestStatus.pending_lawyer,
            RequestStatus.lawyer_review,
            RequestStatus.lawyer_done
        ]))

    query = query.order_by(DocumentRequest.updated_at.desc())
    result = await db.execute(query)
    requests = result.scalars().all()
    return [RequestListItem.model_validate(r) for r in requests]


@app.post("/api/lawyer/requests/{req_uuid}/take")
async def take_request(
    req_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lawyer)
):
    result = await db.execute(
        select(DocumentRequest).where(DocumentRequest.uuid == req_uuid)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if req.status != RequestStatus.pending_lawyer:
        raise HTTPException(status_code=400, detail="Заявка уже взята или не ожидает проверки")

    req.lawyer_id = current_user.id
    req.status = RequestStatus.lawyer_review
    await db.commit()
    return {"message": "Заявка взята в работу"}


@app.post("/api/lawyer/requests/{req_uuid}/submit")
async def submit_lawyer_review(
    req_uuid: str,
    data: LawyerReportSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lawyer)
):
    result = await db.execute(
        select(DocumentRequest).where(DocumentRequest.uuid == req_uuid)
    )
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
    return {"message": "Отчёт юриста сохранён"}


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def admin_list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserOut.model_validate(u) for u in users]


@app.patch("/api/admin/users/{user_id}/role")
async def admin_update_role(
    user_id: int,
    data: UpdateUserRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя изменить свою роль")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.role = data.role
    await db.commit()
    return {"message": f"Роль изменена на {data.role.value}"}


@app.patch("/api/admin/users/{user_id}/toggle")
async def admin_toggle_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать себя")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.is_active = not user.is_active
    await db.commit()
    return {"message": "активен" if user.is_active else "заблокирован", "is_active": user.is_active}


@app.get("/api/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    total_requests = (await db.execute(select(func.count(DocumentRequest.id)))).scalar()
    pending = (await db.execute(
        select(func.count(DocumentRequest.id))
        .where(DocumentRequest.status == RequestStatus.pending_lawyer)
    )).scalar()
    lawyer_done = (await db.execute(
        select(func.count(DocumentRequest.id))
        .where(DocumentRequest.status == RequestStatus.lawyer_done)
    )).scalar()
    return {
        "total_users": total_users,
        "total_requests": total_requests,
        "pending_lawyer": pending,
        "lawyer_done": lawyer_done
    }
