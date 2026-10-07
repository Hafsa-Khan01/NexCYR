"""NexCYR application entry point.

AI-Powered Unified Cybersecurity Assessment & Purple Team Platform.

Run locally:   uvicorn main:app --reload
Production:    uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import Config
from database import init_db

from api.routes.assessments import router as assessment_router
from api.routes.targets import router as target_router
from api.routes.scans import router as scan_router
from api.routes.findings import router as finding_router
from api.routes.recon import router as recon_router
from api.routes.soc import router as soc_router
from api.routes.ai import router as ai_router
from api.routes.purple_team import router as purple_team_router
from api.routes.attack_map import router as attack_map_router
from api.routes.wifi import router as wifi_router
from api.routes.reports import router as reports_router
from api.routes.settings import router as settings_router
from api.routes.search import router as search_router
from api.routes.dashboard import router as dashboard_router
from api.routes.agents import router as agents_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("nexcyr")

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    Config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(
        "NexCYR v%s started (AI provider: %s)",
        Config.APP_VERSION,
        Config.AI_PROVIDER if Config.ai_enabled() else "fallback engine",
    )
    yield
    logger.info("NexCYR shutting down")


app = FastAPI(
    title=Config.APP_NAME,
    version=Config.APP_VERSION,
    description=Config.APP_DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

for router in (
    assessment_router,
    target_router,
    scan_router,
    finding_router,
    recon_router,
    soc_router,
    ai_router,
    purple_team_router,
    attack_map_router,
    wifi_router,
    reports_router,
    settings_router,
    search_router,
    dashboard_router,
    agents_router,
):
    app.include_router(router)


@app.get("/", include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/boot", include_in_schema=False)
def boot_page(request: Request):
    return templates.TemplateResponse(request, "boot.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/health", tags=["System"])
def health_check():
    return {
        "service": "NexCYR API",
        "status": "healthy",
        "version": Config.APP_VERSION,
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. The incident was logged."},
    )
