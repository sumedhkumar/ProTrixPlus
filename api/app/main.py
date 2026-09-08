"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.logging_config import configure_logging
from app.routers import admin, dashboard, dev_identity, health, webhook

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        service=settings.service_name,
        secrets=settings.secret_values(),
    )
    log.info(
        "api starting env=%s dev_identity_enabled=%s",
        settings.app_env,
        settings.dev_identity_enabled,
    )
    if settings.is_production and settings.dev_identity_enabled:
        raise RuntimeError("dev identity must not be enabled in production")
    yield
    log.info("api shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Protrixplus API (S0 skeleton)",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(dev_identity.router)
    app.include_router(webhook.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)
    return app


app = create_app()
