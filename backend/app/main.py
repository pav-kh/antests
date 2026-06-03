from fastapi import FastAPI

from app.assessment.router import router as assessment_router
from app.auth.router import router as auth_router
from app.generation.router import router as sessions_router
from app.overview.router import router as overview_router


def create_app() -> FastAPI:
    app = FastAPI(title="IBS Certification Trainer")
    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(assessment_router)
    app.include_router(overview_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
