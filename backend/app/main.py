import logging

from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.core.logging_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bank AI Assistant API",
    version="1.0.0",
)

app.include_router(auth_router)


@app.get("/health")
def health_check():
    logger.info("Health check requested")
    return {"status": "ok"}