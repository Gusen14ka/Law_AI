from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, field_validator
from models import UserRole, RequestStatus


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("Пароль должен быть не менее 6 символов")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Requests ──────────────────────────────────────────────────────────────────

class RequestOut(BaseModel):
    id: int
    uuid: str
    original_filename: str
    file_size: int
    status: RequestStatus
    user_comment: Optional[str]
    ai_report: Optional[Any]
    ai_analyzed_at: Optional[datetime]
    lawyer_report: Optional[Any]
    lawyer_comment: Optional[str]
    lawyer_reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    user: UserOut
    lawyer: Optional[UserOut]

    model_config = {"from_attributes": True}


class RequestListItem(BaseModel):
    id: int
    uuid: str
    original_filename: str
    file_size: int
    status: RequestStatus
    user_comment: Optional[str]
    ai_analyzed_at: Optional[datetime]
    lawyer_reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    user: UserOut
    lawyer: Optional[UserOut]

    model_config = {"from_attributes": True}


# ── Lawyer review ─────────────────────────────────────────────────────────────

class RiskItem(BaseModel):
    level: str  # high / medium / low
    title: str
    description: str
    recommendation: str


class KeyTerm(BaseModel):
    category: str
    title: str
    description: str


class LawyerReportSubmit(BaseModel):
    summary: str
    document_type: str
    parties: list[str]
    key_terms: list[KeyTerm]
    risks: list[RiskItem]
    plain_language_summary: str
    lawyer_comment: str
    overall_risk: str  # high / medium / low


# ── Admin ─────────────────────────────────────────────────────────────────────

class UpdateUserRole(BaseModel):
    role: UserRole
