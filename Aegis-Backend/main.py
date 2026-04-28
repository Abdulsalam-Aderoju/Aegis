from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routes import auth_routes, coordinator_routes, federal_routes


# ==========================================
# LIFESPAN: Create tables on startup
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables (use Alembic migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Load ML Model
    from app.ml.ml_service import load_ml_package
    load_ml_package()
    
    yield
    await engine.dispose()


# ==========================================
# APP FACTORY
# ==========================================
app = FastAPI(
    title="Aegis — Disease Outbreak Prediction System",
    version="0.1.0",
    lifespan=lifespan,
)

# ==========================================
# MIDDLEWARE: CORS
# ==========================================
from fastapi.middleware.cors import CORSMiddleware

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API routes
app.include_router(auth_routes.router)
app.include_router(coordinator_routes.router)
app.include_router(federal_routes.router)

