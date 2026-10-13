"""⑤ 航线规划 API"""

import time

from fastapi import APIRouter, HTTPException

from src.api.v1.endpoints._persist import result_repo
from src.domain.exceptions import AlgorithmNotFoundError
from src.schemas.route_planning import PlanRequest, PlanResponse
from src.services import route_planning as service

router = APIRouter()


@router.post("/plan", response_model=PlanResponse)
async def plan_path(req: PlanRequest) -> PlanResponse:
    """提交航线规划请求"""
    started = time.perf_counter()
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
    # 算法不存在、算法参数非法（如 bounds 缺键/非数值）— 均为客户端错误
    except (AlgorithmNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo = result_repo("path_plan")
    if repo is not None:
        await repo.save(plan, algorithm=req.algorithm,
                        duration_ms=(time.perf_counter() - started) * 1000)

    return PlanResponse(plan=plan, algorithm_used=req.algorithm)


@router.get("/algorithms")
async def list_algorithms() -> list[dict]:
    """列出可用的路径规划算法"""
    return service.list_available_algorithms()
