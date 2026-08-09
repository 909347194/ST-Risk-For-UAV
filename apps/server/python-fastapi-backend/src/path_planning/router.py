"""路径规划 API 路由"""

from fastapi import APIRouter, HTTPException

from src.path_planning.schemas import (
    PlanRequest,
    PlanResponse,
    AlgorithmInfo,
)
from src.path_planning import service

router = APIRouter()


@router.post("/plan", response_model=PlanResponse)
async def plan_path(req: PlanRequest) -> PlanResponse:
    """提交路径规划请求"""
    try:
        plan = service.plan_path(
            uav_id=req.uav_id,
            task_id=req.task_id,
            start=req.start,
            goal=req.goal,
            obstacles=req.obstacles,
            speed=req.speed,
            algorithm=req.algorithm,
            params=req.params,
            grid_resolution=req.grid_resolution,
            bounds=req.bounds,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PlanResponse(plan=plan, algorithm_used=req.algorithm)


@router.get("/algorithms", response_model=list[AlgorithmInfo])
async def list_algorithms() -> list[AlgorithmInfo]:
    """列出可用的路径规划算法"""
    return [AlgorithmInfo(**a) for a in service.list_algorithms()]
