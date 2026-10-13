from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config import settings

app = FastAPI(
    title="GitHub Repository Q&A Agent",
    description="Index a public GitHub repository and ask grounded questions about it.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-User-Id"],
    expose_headers=["X-Error-Code"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
