import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Float, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    operator_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "coordinator" or "federal"
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)  # assigned state for coordinators
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    submissions: Mapped[list["DailySubmission"]] = relationship(back_populates="submitted_by_user")


class DailySubmission(Base):
    __tablename__ = "daily_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # === MODEL-CRITICAL FIELDS (these feed the SEIR) ===
    new_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    mask_mandate: Mapped[bool] = mapped_column(Boolean, default=False)
    lockdown: Mapped[bool] = mapped_column(Boolean, default=False)
    school_closure: Mapped[bool] = mapped_column(Boolean, default=False)

    # === OPTIONAL CONTEXT FIELDS ===
    daily_vaccinations: Mapped[int] = mapped_column(Integer, default=0)
    tests_conducted: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === METADATA ===
    submitted_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    submitted_by_user: Mapped["User"] = relationship(back_populates="submissions")

    # One submission per state per day
    __table_args__ = (
        UniqueConstraint("state", "report_date", name="uq_state_date"),
    )


class StateProfile(Base):
    """
    Infrequently updated state metadata.
    Population feeds N_vector, mobility feeds M_matrix.
    """
    __tablename__ = "state_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    state: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    population: Mapped[int] = mapped_column(Integer, nullable=False)
    density: Mapped[float] = mapped_column(Float, default=0.0)
    urbanization_rate: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
