from fastapi import FastAPI

from src.api.routes import router

app = FastAPI(
    title="GitHub Repository Q&A Agent",
    description="Index a public GitHub repository and ask grounded questions about it.",
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
