"""④ 任务分配 API"""

from fastapi import APIRouter, HTTPException

from src.domain.exceptions import AlgorithmNotFoundError
from src.schemas.task_allocation import AllocateRequest, AllocateResponse
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
    # 算法不存在、算法参数非法 — 均为客户端错误，须回传 400 而非 500
    except (AlgorithmNotFoundError, ValueError) as e:
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
