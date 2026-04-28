from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, case
from app.database import get_db
from app.models import User, DailySubmission, StateProfile
from app.auth import require_federal

router = APIRouter(prefix="/api/federal", tags=["federal"])

STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos",
    "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers",
    "Sokoto", "Taraba", "Yobe", "Zamfara"
]


# ==========================================
# GET /api/federal/overview
# National-level summary for the dashboard
# ==========================================
@router.get("/overview")
async def national_overview(
    user: User = Depends(require_federal),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # Total cases today
    result = await db.execute(
        select(func.sum(DailySubmission.new_cases)).where(
            DailySubmission.report_date == today
        )
    )
    today_national = result.scalar() or 0

    # Total cases yesterday
    result = await db.execute(
        select(func.sum(DailySubmission.new_cases)).where(
            DailySubmission.report_date == yesterday
        )
    )
    yesterday_national = result.scalar() or 0

    # Total cumulative
    result = await db.execute(
        select(func.sum(DailySubmission.new_cases))
    )
    cumulative_national = result.scalar() or 0

    # 7-day total
    result = await db.execute(
        select(func.sum(DailySubmission.new_cases)).where(
            DailySubmission.report_date >= week_ago
        )
    )
    week_total = result.scalar() or 0

    # States reporting today
    result = await db.execute(
        select(func.count(func.distinct(DailySubmission.state))).where(
            DailySubmission.report_date == today
        )
    )
    states_reporting = result.scalar() or 0

    # States with active lockdown (from most recent submission per state)
    result = await db.execute(
        select(func.count()).where(
            and_(
                DailySubmission.report_date == today,
                DailySubmission.lockdown == True,
            )
        )
    )
    states_locked = result.scalar() or 0

    # 7-day national trend
    result = await db.execute(
        select(
            DailySubmission.report_date,
            func.sum(DailySubmission.new_cases).label("total")
        )
        .where(DailySubmission.report_date >= week_ago)
        .group_by(DailySubmission.report_date)
        .order_by(DailySubmission.report_date)
    )
    trend = [{"date": str(row.report_date), "cases": row.total} for row in result.all()]

    return {
        "today_cases": today_national,
        "yesterday_cases": yesterday_national,
        "cases_delta": today_national - yesterday_national,
        "cumulative_cases": cumulative_national,
        "week_total": week_total,
        "states_reporting_today": states_reporting,
        "total_states": len(STATES),
        "states_locked_down": states_locked,
        "trend_7day": trend,
    }


# ==========================================
# GET /api/federal/states
# Summary card data for all 37 states
# ==========================================
@router.get("/states")
async def all_states_summary(
    user: User = Depends(require_federal),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    states_data = []

    for state in STATES:
        # Latest submission
        result = await db.execute(
            select(DailySubmission)
            .where(DailySubmission.state == state)
            .order_by(desc(DailySubmission.report_date))
            .limit(1)
        )
        latest = result.scalar_one_or_none()

        # Cumulative
        result = await db.execute(
            select(func.sum(DailySubmission.new_cases)).where(
                DailySubmission.state == state
            )
        )
        cumulative = result.scalar() or 0

        # 7-day total
        result = await db.execute(
            select(func.sum(DailySubmission.new_cases)).where(
                and_(
                    DailySubmission.state == state,
                    DailySubmission.report_date >= week_ago,
                )
            )
        )
        week_total = result.scalar() or 0

        # Yesterday cases for delta
        result = await db.execute(
            select(DailySubmission.new_cases).where(
                and_(
                    DailySubmission.state == state,
                    DailySubmission.report_date == yesterday,
                )
            )
        )
        yesterday_cases = result.scalar() or 0

        # Population
        result = await db.execute(
            select(StateProfile.population).where(StateProfile.state == state)
        )
        population = result.scalar() or 0

        # Risk level based on 7-day per-capita rate
        risk = "low"
        if population > 0 and week_total > 0:
            rate_per_100k = (week_total / population) * 100_000
            if rate_per_100k > 50:
                risk = "critical"
            elif rate_per_100k > 20:
                risk = "high"
            elif rate_per_100k > 5:
                risk = "moderate"

        today_cases = 0
        reported_today = False
        mask = False
        lockdown = False
        school = False

        if latest:
            if latest.report_date == today:
                today_cases = latest.new_cases
                reported_today = True
            mask = latest.mask_mandate
            lockdown = latest.lockdown
            school = latest.school_closure

        states_data.append({
            "state": state,
            "today_cases": today_cases,
            "yesterday_cases": yesterday_cases,
            "cumulative_cases": cumulative,
            "week_total": week_total,
            "population": population,
            "risk_level": risk,
            "reported_today": reported_today,
            "mask_mandate": mask,
            "lockdown": lockdown,
            "school_closure": school,
        })

    # Sort by week_total descending (hottest states first)
    states_data.sort(key=lambda x: x["week_total"], reverse=True)

    return {"states": states_data}


# ==========================================
# GET /api/federal/states/{state_name}
# Detailed placard for a single state
# ==========================================
@router.get("/states/{state_name}")
async def state_detail(
    state_name: str,
    user: User = Depends(require_federal),
    db: AsyncSession = Depends(get_db),
):
    if state_name not in STATES:
        raise HTTPException(status_code=404, detail=f"State '{state_name}' not found")

    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Population
    result = await db.execute(
        select(StateProfile).where(StateProfile.state == state_name)
    )
    profile = result.scalar_one_or_none()
    population = profile.population if profile else 0

    # Cumulative
    result = await db.execute(
        select(func.sum(DailySubmission.new_cases)).where(
            DailySubmission.state == state_name
        )
    )
    cumulative = result.scalar() or 0

    # 7-day total
    result = await db.execute(
        select(func.sum(DailySubmission.new_cases)).where(
            and_(
                DailySubmission.state == state_name,
                DailySubmission.report_date >= week_ago,
            )
        )
    )
    week_total = result.scalar() or 0

    # 30-day trend
    result = await db.execute(
        select(DailySubmission.report_date, DailySubmission.new_cases)
        .where(
            and_(
                DailySubmission.state == state_name,
                DailySubmission.report_date >= month_ago,
            )
        )
        .order_by(DailySubmission.report_date)
    )
    daily_trend = [{"date": str(row.report_date), "cases": row.new_cases} for row in result.all()]

    # Latest intervention status
    result = await db.execute(
        select(DailySubmission)
        .where(DailySubmission.state == state_name)
        .order_by(desc(DailySubmission.report_date))
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    # Intervention timeline (last 30 days)
    result = await db.execute(
        select(
            DailySubmission.report_date,
            DailySubmission.mask_mandate,
            DailySubmission.lockdown,
            DailySubmission.school_closure,
        )
        .where(
            and_(
                DailySubmission.state == state_name,
                DailySubmission.report_date >= month_ago,
            )
        )
        .order_by(DailySubmission.report_date)
    )
    intervention_timeline = [
        {
            "date": str(row.report_date),
            "mask_mandate": row.mask_mandate,
            "lockdown": row.lockdown,
            "school_closure": row.school_closure,
        }
        for row in result.all()
    ]

    # Risk calculation
    risk = "low"
    if population > 0 and week_total > 0:
        rate = (week_total / population) * 100_000
        if rate > 50:
            risk = "critical"
        elif rate > 20:
            risk = "high"
        elif rate > 5:
            risk = "moderate"

    # Peak day in last 30 days
    peak_day = None
    peak_cases = 0
    for d in daily_trend:
        if d["cases"] > peak_cases:
            peak_cases = d["cases"]
            peak_day = d["date"]

    return {
        "state": state_name,
        "population": population,
        "cumulative_cases": cumulative,
        "week_total": week_total,
        "risk_level": risk,
        "daily_trend_30d": daily_trend,
        "intervention_timeline": intervention_timeline,
        "peak_day": peak_day,
        "peak_cases": peak_cases,
        "current_interventions": {
            "mask_mandate": latest.mask_mandate if latest else False,
            "lockdown": latest.lockdown if latest else False,
            "school_closure": latest.school_closure if latest else False,
        },
        "last_reported": str(latest.report_date) if latest else None,
    }


# ==========================================
# POST /api/federal/forecast
# Scenario-based SEIR model projections
# ==========================================
from app.schemas import ForecastRequest, ForecastResponse
from app.ml.ml_service import generate_state_forecast, is_model_loaded
import numpy as np

@router.post("/forecast", response_model=ForecastResponse)
async def get_forecast(
    request: ForecastRequest,
    user: User = Depends(require_federal),
    db: AsyncSession = Depends(get_db),
):
    if not is_model_loaded():
        raise HTTPException(
            status_code=503, 
            detail="Machine learning model is currently unavailable."
        )

    # 1. Fetch the latest intervention status for each state from DB
    current_masks = []
    current_locks = []
    
    for state in STATES:
        result = await db.execute(
            select(DailySubmission)
            .where(DailySubmission.state == state)
            .order_by(desc(DailySubmission.report_date))
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        
        current_masks.append(1.0 if latest and latest.mask_mandate else 0.0)
        current_locks.append(1.0 if latest and latest.lockdown else 0.0)
        
    current_masks = np.array(current_masks)
    current_locks = np.array(current_locks)
    
    # 2. Build the intervention matrices for the forecast horizon
    days = request.days
    num_states = len(STATES)
    
    mask_matrix = np.zeros((days, num_states))
    lock_matrix = np.zeros((days, num_states))
    
    if request.scenario == "status_quo":
        # Continue current interventions
        mask_matrix = np.tile(current_masks, (days, 1))
        lock_matrix = np.tile(current_locks, (days, 1))
    elif request.scenario == "national_lockdown":
        # 100% compliance everywhere
        mask_matrix = np.ones((days, num_states))
        lock_matrix = np.ones((days, num_states))
    elif request.scenario == "no_interventions":
        # Lift all interventions
        mask_matrix = np.zeros((days, num_states))
        lock_matrix = np.zeros((days, num_states))
    elif request.scenario == "mask_only":
        # 100% mask compliance everywhere, no lockdowns
        mask_matrix = np.ones((days, num_states))
        lock_matrix = np.zeros((days, num_states))
    else:
        # Default fallback
        mask_matrix = np.tile(current_masks, (days, 1))
        lock_matrix = np.tile(current_locks, (days, 1))

    # 3. Generate the per-state and national forecast using JAX simulation
    try:
        forecast_data = generate_state_forecast(mask_matrix, lock_matrix, forecast_days=days)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

    # 4. Return formatted response
    return ForecastResponse(
        days=forecast_data["days"],
        national=forecast_data["national"],
        states=forecast_data["states"],
        state_names=forecast_data["state_names"]
    )

