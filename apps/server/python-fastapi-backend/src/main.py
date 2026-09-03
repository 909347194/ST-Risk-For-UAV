"""FastAPI 入口"""

from fastapi import FastAPI

from src.utils.config import get_settings
from src.api.v1.api import api_v1_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="无人机任务分配与路径规划服务",
        version=settings.app_version,
        debug=settings.debug,
    )

    app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_app()
