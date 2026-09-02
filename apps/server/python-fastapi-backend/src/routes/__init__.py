"""表现层 — API 路由"""

from fastapi import APIRouter

from src.routes.uav_resource import router as uav_router
from src.routes.task_adaptability import router as adapt_router
from src.routes.risk_assessment import router as risk_router
from src.routes.task_allocation import router as alloc_router
from src.routes.route_planning import router as plan_router
from src.routes.flight_monitoring import router as monitor_router
from src.routes.common import router as common_router

api_router = APIRouter()

# ── 公共 ──
api_router.include_router(common_router, tags=["公共"])

# ── 6 大业务模块 ──
api_router.include_router(uav_router,   prefix="/uavs",          tags=["① 无人机资源管理"])
api_router.include_router(adapt_router, prefix="/adaptability",   tags=["② 任务适配评估"])
api_router.include_router(risk_router,  prefix="/risk",           tags=["③ 飞行风险评估"])
api_router.include_router(alloc_router, prefix="/tasks",          tags=["④ 任务分配"])
api_router.include_router(plan_router,  prefix="/paths",          tags=["⑤ 航线规划"])
api_router.include_router(monitor_router, prefix="/monitoring",   tags=["⑥ 飞行监控"])
