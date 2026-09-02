"""② 任务适配评估 API"""

from fastapi import APIRouter, HTTPException

from src.models.exceptions import InsufficientResourceError
from src.schemas.task_adaptability import (
    AdaptabilityRequest,
    BatchAdaptabilityRequest,
    AdaptabilityResponse,
    BatchAdaptabilityResponse,
)
from src.services import task_adaptability as service
from src.services import uav_resource

router = APIRouter()


@router.post("/evaluate", response_model=AdaptabilityResponse)
async def evaluate_adaptability(req: AdaptabilityRequest) -> AdaptabilityResponse:
    """评估单架 UAV 对任务的适配度"""
    try:
        uav = uav_resource.get_uav(req.uav_id)
    except InsufficientResourceError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = service.evaluate(uav, req.task, req.min_battery_reserve)
    return AdaptabilityResponse(result=result)


@router.post("/batch", response_model=BatchAdaptabilityResponse)
async def batch_evaluate(req: BatchAdaptabilityRequest) -> BatchAdaptabilityResponse:
    """批量评估多架 UAV 对同一任务的适配度"""
    results = service.evaluate_all(req.uavs, req.task, req.min_battery_reserve)
    best = results[0].uav_id if results and results[0].capable else None
    return BatchAdaptabilityResponse(results=results, best_uav_id=best)
