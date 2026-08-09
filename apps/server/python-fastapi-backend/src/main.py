"""FastAPI 入口"""

from fastapi import FastAPI

from src.task_allocation.router import router as task_router
from src.path_planning.router import router as planning_router

app = FastAPI(
    title="ST-Risk UAV Service",
    description="无人机任务分配与路径规划服务",
    version="0.1.0",
)

app.include_router(task_router, prefix="/api/v1/tasks", tags=["任务分配"])
app.include_router(planning_router, prefix="/api/v1/paths", tags=["路径规划"])


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}
