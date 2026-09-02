"""③ 飞行风险评估 API"""

from fastapi import APIRouter

from src.schemas.risk_assessment import RiskAssessRequest, RiskAssessResponse
from src.services import risk_assessment as service
from src.utils.config import get_settings

router = APIRouter()


@router.post("/assess", response_model=RiskAssessResponse)
async def assess_risk(req: RiskAssessRequest) -> RiskAssessResponse:
    """对 UAV-Task 组合进行风险评估"""
    assessment = service.assess(
        uav=req.uav,
        task=req.task,
        obstacles=req.obstacles,
        weather_factor=req.weather_factor,
    )

    settings = get_settings()
    pass_check = assessment.overall_score < settings.risk_collision_threshold

    return RiskAssessResponse(assessment=assessment, pass_check=pass_check)
