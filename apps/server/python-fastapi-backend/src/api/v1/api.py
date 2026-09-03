"""API v1 路由汇总"""

from fastapi import APIRouter

from src.api.v1.endpoints.uav_resource import router as uav_router
from src.api.v1.endpoints.task_adaptability import router as adapt_router
from src.api.v1.endpoints.risk_assessment import router as risk_router
from src.api.v1.endpoints.task_allocation import router as alloc_router
from src.api.v1.endpoints.route_planning import router as plan_router
from src.api.v1.endpoints.flight_monitoring import router as monitor_router
from src.api.v1.endpoints.common import router as common_router

api_v1_router = APIRouter()

# 公共
api_v1_router.include_router(common_router, tags=["公共"])

# 6 大业务模块
api_v1_router.include_router(uav_router,    prefix="/uavs",        tags=["① 无人机资源管理"])
api_v1_router.include_router(adapt_router,  prefix="/adaptability", tags=["② 任务适配评估"])
api_v1_router.include_router(risk_router,   prefix="/risk",         tags=["③ 飞行风险评估"])
api_v1_router.include_router(alloc_router,  prefix="/tasks",        tags=["④ 任务分配"])
api_v1_router.include_router(plan_router,   prefix="/paths",        tags=["⑤ 航线规划"])
api_v1_router.include_router(monitor_router, prefix="/monitoring",  tags=["⑥ 飞行监控"])
