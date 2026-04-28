from pydantic import BaseModel, EmailStr, Field
from datetime import date, datetime


# ==========================================
# AUTH
# ==========================================
class UserCreate(BaseModel):
    operator_name: str
    email: str
    password: str
    role: str = "coordinator"
    state: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    state: str | None = None
    operator_name: str


class UserOut(BaseModel):
    id: str
    operator_name: str
    email: str
    role: str
    state: str | None


# ==========================================
# DAILY SUBMISSION
# ==========================================
class SubmissionCreate(BaseModel):
    date: date
    new_cases: int = Field(ge=0)
    mask_mandate: int = Field(ge=0, le=1)
    lockdown: int = Field(ge=0, le=1)
    school_closure: int = Field(ge=0, le=1)
    daily_vaccinations: int = Field(ge=0, default=0)
    tests_conducted: int = Field(ge=0, default=0)
    notes: str | None = None


class SubmissionOut(BaseModel):
    date: date
    new_cases: int
    mask_mandate: bool
    lockdown: bool
    school_closure: bool
    daily_vaccinations: int
    tests_conducted: int
    notes: str | None
    submitted_at: datetime


class DashboardResponse(BaseModel):
    submitted_today: bool
    submission_time: str | None = None
    today_cases: int | None = None
    cumulative_cases: int
    cases_delta: int | None = None
    active_interventions_count: int
    active_interventions_list: str
    streak: int
    recent_submissions: list[SubmissionOut]


class HistoryResponse(BaseModel):
    submissions: list[SubmissionOut]
    total: int


# ==========================================
# FORECAST
# ==========================================
class ForecastRequest(BaseModel):
    days: int = Field(30, ge=1, le=90)
    # Optional overrides for scenarios. If None, it assumes status quo (current state policies continued)
    scenario: str = "status_quo" # "status_quo", "national_lockdown", "no_interventions"

class ForecastResponse(BaseModel):
    days: list[int]
    national: dict
    states: dict
    state_names: list[str]
