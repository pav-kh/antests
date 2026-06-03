from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.assessment.router import router as assessment_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.generation.router import router as sessions_router
from app.overview.router import router as overview_router


def create_app() -> FastAPI:
    app = FastAPI(title="IBS Certification Trainer")
    # Credentialed cross-origin requests require an explicit origin (no wildcard)
    # plus allow_credentials so the browser accepts the session cookie.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(assessment_router)
    app.include_router(overview_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
