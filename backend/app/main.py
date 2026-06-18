"""
Punto de entrada de la API FastAPI para el TRL Rugby.

Ejecutar:
  uvicorn backend.app.main:app --reload --port 8000
  o desde la raíz del proyecto: make dev-backend
"""

import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .config import get_settings
from .database import engine, get_db_context
from .routers import teams, matches, standings, predict, simulate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trl_api")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"=== TRL API {settings.app_version} iniciando ===")
    db_display = settings.database_url.split("@")[-1] if "@" in settings.database_url else "configured"
    logger.info(f"DB: {db_display}")
    logger.info(f"Temporada activa: {settings.current_season}")
    yield
    logger.info("=== TRL API cerrando ===")
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API para el Torneo Regional del Litoral de Rugby. "
        "Incluye estadísticas, predicciones ELO/ML y simulación Monte Carlo."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — API pública sin autenticación, permite todos los orígenes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
API_PREFIX = "/api/v1"
app.include_router(teams.router,     prefix=API_PREFIX)
app.include_router(matches.router,   prefix=API_PREFIX)
app.include_router(standings.router, prefix=API_PREFIX)
app.include_router(predict.router,   prefix=API_PREFIX)
app.include_router(simulate.router,  prefix=API_PREFIX)


@app.get("/health", tags=["health"])
async def health_check():
    db_status = "ok"
    try:
        async with get_db_context() as db:
            await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e}"

    return JSONResponse({
        "status": "ok" if db_status == "ok" else "degraded",
        "version": settings.app_version,
        "db": db_status,
    })


@app.get("/", tags=["root"])
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


# Vercel serverless handler
from mangum import Mangum
handler = Mangum(app, lifespan="off")
