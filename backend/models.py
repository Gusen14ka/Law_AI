from datetime import datetime
from enum import Enum as PyEnum
import uuid

from sqlalchemy import (
    String, Text, DateTime, Enum, ForeignKey,
    Boolean, Integer, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID


class Base(DeclarativeBase):
    pass


class UserRole(str, PyEnum):
    admin = "admin"
    lawyer = "lawyer"
    user = "user"


class RequestStatus(str, PyEnum):
    pending_ai = "pending_ai"        # ожидает анализа AI
    ai_done = "ai_done"              # AI проанализировал
    pending_lawyer = "pending_lawyer"  # отправлен юристу
    lawyer_review = "lawyer_review"  # юрист работает
    lawyer_done = "lawyer_done"      # юрист завершил
    closed = "closed"                # закрыт


class RiskLevel(str, PyEnum):
    high = "high"
    medium = "medium"
    low = "low"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    requests: Mapped[list["DocumentRequest"]] = relationship(
        "DocumentRequest", foreign_keys="DocumentRequest.user_id", back_populates="user"
    )
    lawyer_requests: Mapped[list["DocumentRequest"]] = relationship(
        "DocumentRequest", foreign_keys="DocumentRequest.lawyer_id", back_populates="lawyer"
    )


class DocumentRequest(Base):
    __tablename__ = "document_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    lawyer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # File info
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), default=RequestStatus.pending_ai, nullable=False
    )

    # User comment on submit
    user_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI analysis result
    ai_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Lawyer review
    lawyer_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lawyer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    lawyer_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="requests")
    lawyer: Mapped["User | None"] = relationship("User", foreign_keys=[lawyer_id], back_populates="lawyer_requests")
