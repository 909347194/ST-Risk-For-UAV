"""④ 任务分配 API"""

from fastapi import APIRouter, HTTPException

from src.models.exceptions import AlgorithmNotFoundError
from src.schemas.task_allocation import AllocateRequest, AllocateResponse
from src.schemas.route_planning import PlanResponse
from src.services import task_allocation as service

router = APIRouter()


@router.post("/allocate", response_model=AllocateResponse)
async def allocate_tasks(req: AllocateRequest) -> AllocateResponse:
    """提交任务分配请求"""
    try:
        allocations, unassigned = service.allocate(
            uavs=req.uavs,
            tasks=req.tasks,
            algorithm=req.algorithm,
            params=req.params,
        )
    except AlgorithmNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AllocateResponse(
        allocations=allocations,
        unassigned_tasks=unassigned,
        algorithm_used=req.algorithm,
    )


@router.get("/algorithms")
async def list_algorithms() -> list[dict]:
    """列出可用的任务分配算法"""
    return service.list_available_algorithms()
