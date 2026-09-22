"""④ 任务分配 API"""

from fastapi import APIRouter, HTTPException

from src.domain.exceptions import AlgorithmNotFoundError
from src.schemas.task_allocation import (
    AllocateRequest,
    AllocateResponse,
    ChargeEventOut,
    UAVRechargePlanOut,
)
from src.algorithms.task_allocation.energy import RechargePlan
from src.services import task_allocation as service

router = APIRouter()


def _to_plan_out(plan: RechargePlan) -> UAVRechargePlanOut:
    """RechargePlan → 响应 schema"""
    return UAVRechargePlanOut(
        uav_id=plan.uav_id,
        feasible=plan.feasible,
        total_time=plan.total_time,
        total_energy=plan.total_energy,
        charges=[
            ChargeEventOut(
                station_id=c.station_id,
                charge_wh=c.charge_wh,
                arrive_time=c.arrive_time,
                leave_time=c.leave_time,
            )
            for c in plan.charges
        ],
    )


@router.post("/allocate", response_model=AllocateResponse)
async def allocate_tasks(req: AllocateRequest) -> AllocateResponse:
    """提交任务分配请求"""
    try:
        allocations, unassigned, plans = service.allocate_with_plans(
            uavs=req.uavs,
            tasks=req.tasks,
            algorithm=req.algorithm,
            params=req.params,
            stations=req.stations,
            sigma=req.sigma,
            energy_strategy=req.energy_strategy,
        )
    except AlgorithmNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # 非法算法参数(uav_max_ranges 长度、energy_strategy、sigma 等)→ 400
        raise HTTPException(status_code=400, detail=str(e))

    return AllocateResponse(
        allocations=allocations,
        unassigned_tasks=unassigned,
        algorithm_used=req.algorithm,
        recharge_plans=[_to_plan_out(p) for p in plans],
    )


@router.get("/algorithms")
async def list_algorithms() -> list[dict]:
    """列出可用的任务分配算法"""
    return service.list_available_algorithms()
