from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.database import engine


def create_app() -> FastAPI:
    app = FastAPI(
        title="SAR Copilot API",
        version="0.1.0",
        description="Evidence-grounded SAR narrative generation — Part 1 (schema + synthetic data).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as exc:  # pragma: no cover - exercised via integration test
            db_status = f"error: {exc}"

        return {
            "status": "ok" if db_status == "connected" else "degraded",
            "database": db_status,
            "environment": settings.environment,
        }

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
