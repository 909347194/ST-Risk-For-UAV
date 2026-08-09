"""任务分配 API 路由"""

from fastapi import APIRouter, HTTPException

from src.task_allocation.schemas import (
    AllocateRequest,
    AllocateResponse,
    AlgorithmInfo,
)
from src.task_allocation import service

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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AllocateResponse(
        allocations=allocations,
        unassigned_tasks=unassigned,
        algorithm_used=req.algorithm,
    )


@router.get("/algorithms", response_model=list[AlgorithmInfo])
async def list_algorithms() -> list[AlgorithmInfo]:
    """列出可用的任务分配算法"""
    return [AlgorithmInfo(**a) for a in service.list_algorithms()]
