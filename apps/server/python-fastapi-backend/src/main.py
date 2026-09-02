"""FastAPI 入口 — 分层架构"""

from fastapi import FastAPI

from src.utils.config import get_settings
from src.routes import api_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="无人机任务分配与路径规划服务（分层架构）",
        version=settings.app_version,
        debug=settings.debug,
    )

    # 所有路由统一通过 api_router 挂载，前缀 /api/v1
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
