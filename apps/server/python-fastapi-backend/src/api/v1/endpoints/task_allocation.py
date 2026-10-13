"""④ 任务分配 API"""

import time
from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.api.v1.endpoints._persist import result_repo
from src.domain.exceptions import AlgorithmNotFoundError
from src.schemas.task_allocation import (
    AllocateRequest,
    AllocateResponse,
    AllocationRunDetailResponse,
    AllocationRunListResponse,
)
from src.services import task_allocation as service

router = APIRouter()


@router.post("/allocate", response_model=AllocateResponse)
async def allocate_tasks(req: AllocateRequest) -> AllocateResponse:
    """提交任务分配请求"""
    started = time.perf_counter()
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

    repo = result_repo("allocation")
    if repo is not None:
        await repo.save_run(
            algorithm=req.algorithm,
            params=req.params,
            uav_count=len(req.uavs),
            task_count=len(req.tasks),
            allocations=allocations,
            unassigned_task_ids=unassigned,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    return AllocateResponse(
        allocations=allocations,
        unassigned_tasks=unassigned,
        algorithm_used=req.algorithm,
    )


@router.get("/algorithms")
async def list_algorithms() -> list[dict]:
    """列出可用的任务分配算法"""
    return service.list_available_algorithms()


@router.get("/runs", response_model=AllocationRunListResponse)
async def list_allocation_runs(algorithm: str | None = None, limit: int = 50) -> AllocationRunListResponse:
    """列出历史分配运行（按时间倒序）"""
    repo = result_repo("allocation")
    if repo is None:
        raise HTTPException(status_code=503, detail="未启用数据库持久化，无法查询历史运行")
    runs = await repo.list_runs(algorithm=algorithm, limit=limit)
    # total 必须用独立 COUNT 查询：list_runs 内部有 SQL LIMIT，
    # len(runs) 会把被截断的数量当总数（超过 limit 时错误）
    total = await repo.count_runs(algorithm=algorithm)
    return AllocationRunListResponse(runs=runs, total=total)


@router.get("/runs/{run_id}", response_model=AllocationRunDetailResponse)
async def get_allocation_run(run_id: UUID) -> AllocationRunDetailResponse:
    """查询单次分配运行的明细"""
    repo = result_repo("allocation")
    if repo is None:
        raise HTTPException(status_code=503, detail="未启用数据库持久化，无法查询历史运行")
    detail = await repo.get_run(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"分配运行 {run_id} 不存在")
    return AllocationRunDetailResponse(**detail)
