"""
Main FastAPI application entrypoint.
Wires together all routers, middleware, exception handlers, and startup hooks.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.auth_routes import router as auth_router
from app.api.chat_routes import router as chat_router
from app.api.health_routes import router as health_router
from app.api.kb_routes import router as kb_router
from app.api.ticket_routes import router as ticket_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.models import User
from app.db.session import Base, SessionLocal, engine

configure_logging()
logger = get_logger(__name__)


def seed_default_admin() -> None:
    """Create the bootstrap admin account, only if DEFAULT_ADMIN_PASSWORD is set."""
    if not settings.default_admin_password:
        logger.info("default_admin_seed_skipped", reason="DEFAULT_ADMIN_PASSWORD unset")
        return

    db = SessionLocal()
    try:
        exists = (
            db.query(User).filter(User.email == settings.default_admin_email).first()
        )
        if not exists:
            db.add(
                User(
                    email=settings.default_admin_email,
                    full_name="System Admin",
                    hashed_password=hash_password(settings.default_admin_password),
                    is_admin=True,
                )
            )
            db.commit()
            logger.info("default_admin_seeded", email=settings.default_admin_email)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error("seed_admin_failed", error=str(e))
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "starting_application", env=settings.app_env, version=settings.app_version
    )
    if settings.uses_default_secret_key:
        if settings.app_env == "production":
            raise RuntimeError(
                "SECRET_KEY is still the built-in placeholder; set a strong random "
                "value before running with APP_ENV=production."
            )
        logger.warning("insecure_default_secret_key", env=settings.app_env)

    # Create tables if they don't exist (use Alembic migrations in real production)
    Base.metadata.create_all(bind=engine)
    seed_default_admin()
    yield
    logger.info("shutting_down_application")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Enterprise AI Customer Support Agent Platform — RAG + Agentic AI + MLOps",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,  # set CORS_ORIGINS in production
    allow_credentials=False,  # auth uses a Bearer header, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics exposed at /metrics
Instrumentator().instrument(app).expose(app)

# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(ticket_router)
app.include_router(chat_router)
app.include_router(kb_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=str(request.url), error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again later."},
    )


@app.get("/")
def root():
    return {
        "message": f"{settings.app_name} is running",
        "docs": "/docs",
        "health": "/health",
    }
