from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from app.database import get_db
from app.models import User, DailySubmission
from app.schemas import SubmissionCreate, SubmissionOut, DashboardResponse, HistoryResponse
from app.auth import require_coordinator

router = APIRouter(prefix="/api/coordinator", tags=["coordinator"])


# ==========================================
# HELPER: Convert DB row to response schema
# ==========================================
def submission_to_out(s: DailySubmission) -> SubmissionOut:
    return SubmissionOut(
        date=s.report_date,
        new_cases=s.new_cases,
        mask_mandate=s.mask_mandate,
        lockdown=s.lockdown,
        school_closure=s.school_closure,
        daily_vaccinations=s.daily_vaccinations,
        tests_conducted=s.tests_conducted,
        notes=s.notes,
        submitted_at=s.submitted_at,
    )


# ==========================================
# POST /api/coordinator/submit
# ==========================================
@router.post("/submit", status_code=201)
async def submit_daily_report(
    payload: SubmissionCreate,
    user: User = Depends(require_coordinator),
    db: AsyncSession = Depends(get_db),
):
    if not user.state:
        raise HTTPException(status_code=400, detail="No state assigned to your account")

    # Check if submission already exists for this state+date (upsert logic)
    result = await db.execute(
        select(DailySubmission).where(
            and_(
                DailySubmission.state == user.state,
                DailySubmission.report_date == payload.date,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing submission
        existing.new_cases = payload.new_cases
        existing.mask_mandate = bool(payload.mask_mandate)
        existing.lockdown = bool(payload.lockdown)
        existing.school_closure = bool(payload.school_closure)
        existing.daily_vaccinations = payload.daily_vaccinations
        existing.tests_conducted = payload.tests_conducted
        existing.notes = payload.notes
        existing.updated_at = datetime.utcnow()
        await db.commit()
        return {"message": "Submission updated", "date": str(payload.date)}
    else:
        # Create new submission
        submission = DailySubmission(
            state=user.state,
            report_date=payload.date,
            new_cases=payload.new_cases,
            mask_mandate=bool(payload.mask_mandate),
            lockdown=bool(payload.lockdown),
            school_closure=bool(payload.school_closure),
            daily_vaccinations=payload.daily_vaccinations,
            tests_conducted=payload.tests_conducted,
            notes=payload.notes,
            submitted_by=user.id,
        )
        db.add(submission)
        await db.commit()
        return {"message": "Submission recorded", "date": str(payload.date)}


# ==========================================
# GET /api/coordinator/dashboard
# ==========================================
@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    user: User = Depends(require_coordinator),
    db: AsyncSession = Depends(get_db),
):
    state = user.state
    today = date.today()

    # Today's submission
    result = await db.execute(
        select(DailySubmission).where(
            and_(DailySubmission.state == state, DailySubmission.report_date == today)
        )
    )
    today_sub = result.scalar_one_or_none()

    # Yesterday's submission (for delta)
    yesterday = today - timedelta(days=1)
    result = await db.execute(
        select(DailySubmission).where(
            and_(DailySubmission.state == state, DailySubmission.report_date == yesterday)
        )
    )
    yesterday_sub = result.scalar_one_or_none()

    # Cumulative cases
    result = await db.execute(
        select(func.sum(DailySubmission.new_cases)).where(DailySubmission.state == state)
    )
    cumulative = result.scalar() or 0

    # Submission streak: count consecutive days backward from today
    streak = 0
    check_date = today
    while True:
        result = await db.execute(
            select(DailySubmission).where(
                and_(DailySubmission.state == state, DailySubmission.report_date == check_date)
            )
        )
        if result.scalar_one_or_none():
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    # Active interventions from latest submission
    latest_sub = today_sub
    if not latest_sub:
        result = await db.execute(
            select(DailySubmission)
            .where(DailySubmission.state == state)
            .order_by(desc(DailySubmission.report_date))
            .limit(1)
        )
        latest_sub = result.scalar_one_or_none()

    active_count = 0
    active_list = []
    if latest_sub:
        if latest_sub.mask_mandate:
            active_count += 1
            active_list.append("Mask mandate")
        if latest_sub.lockdown:
            active_count += 1
            active_list.append("Lockdown")
        if latest_sub.school_closure:
            active_count += 1
            active_list.append("School closure")

    # Recent submissions (last 7)
    result = await db.execute(
        select(DailySubmission)
        .where(DailySubmission.state == state)
        .order_by(desc(DailySubmission.report_date))
        .limit(7)
    )
    recent = result.scalars().all()

    # Cases delta
    cases_delta = None
    if today_sub and yesterday_sub:
        cases_delta = today_sub.new_cases - yesterday_sub.new_cases

    return DashboardResponse(
        submitted_today=today_sub is not None,
        submission_time=today_sub.submitted_at.strftime("%H:%M") if today_sub else None,
        today_cases=today_sub.new_cases if today_sub else None,
        cumulative_cases=cumulative,
        cases_delta=cases_delta,
        active_interventions_count=active_count,
        active_interventions_list=", ".join(active_list) if active_list else "None active",
        streak=streak,
        recent_submissions=[submission_to_out(s) for s in recent],
    )


# ==========================================
# GET /api/coordinator/history
# ==========================================
@router.get("/history", response_model=HistoryResponse)
async def get_history(
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(require_coordinator),
    db: AsyncSession = Depends(get_db),
):
    query = select(DailySubmission).where(DailySubmission.state == user.state)

    if date_from:
        query = query.where(DailySubmission.report_date >= date_from)
    if date_to:
        query = query.where(DailySubmission.report_date <= date_to)

    query = query.order_by(desc(DailySubmission.report_date))
    result = await db.execute(query)
    submissions = result.scalars().all()

    return HistoryResponse(
        submissions=[submission_to_out(s) for s in submissions],
        total=len(submissions),
    )
