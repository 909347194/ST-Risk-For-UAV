"""②③⑤ 扁平结果记录仓储 — PostgreSQL 实现

适配评估、风险评估、航线规划都是「一次调用产生若干条独立记录」，
没有 run 概念，因此各自一张表、各自一个仓储。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.adaptability import AdaptabilityResultModel
from src.db.models.path_plan import PathPlanModel
from src.db.models.risk_record import RiskRecordModel
from src.domain.models import AdaptabilityResult, PathPlan, RiskAssessment
from src.repositories import mappers


class AdaptabilityDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_many(self, results: list[AdaptabilityResult]) -> None:
        if not results:
            return
        async with self._session_factory() as session:
            session.add_all([mappers.adaptability_to_model(r) for r in results])
            await session.commit()

    async def find_by_uav(self, uav_id: str, limit: int = 100) -> list[dict]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(AdaptabilityResultModel)
                .where(AdaptabilityResultModel.uav_id == uav_id)
                .order_by(AdaptabilityResultModel.created_at.desc()).limit(limit))
            ).scalars().all()
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: AdaptabilityResultModel) -> dict:
        return {
            "id": r.id, "uav_id": r.uav_id, "task_id": r.task_id,
            "capable": r.capable, "payload_ok": r.payload_ok, "battery_ok": r.battery_ok,
            "range_ok": r.range_ok, "time_ok": r.time_ok, "score": r.score,
            "reasons": list(r.reasons or []), "created_at": r.created_at,
        }


class RiskRecordDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(self, assessment: RiskAssessment, weather_factor: float | None = None) -> None:
        async with self._session_factory() as session:
            session.add(mappers.risk_to_model(assessment, weather_factor))
            await session.commit()

    async def find_by_uav(self, uav_id: str, limit: int = 100) -> list[dict]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(RiskRecordModel).where(RiskRecordModel.uav_id == uav_id)
                .order_by(RiskRecordModel.created_at.desc()).limit(limit))
            ).scalars().all()
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: RiskRecordModel) -> dict:
        return {
            "id": r.id, "uav_id": r.uav_id, "task_id": r.task_id,
            "risk_level": r.risk_level, "collision_risk": r.collision_risk,
            "weather_risk": r.weather_risk, "battery_risk": r.battery_risk,
            "overall_score": r.overall_score, "weather_factor": r.weather_factor,
            "details": list(r.details or []), "created_at": r.created_at,
        }


class PathPlanDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(self, plan: PathPlan, algorithm: str,
                   duration_ms: float | None = None) -> None:
        async with self._session_factory() as session:
            session.add(mappers.plan_to_model(plan, algorithm, duration_ms))
            await session.commit()

    async def find_by_uav(self, uav_id: str, limit: int = 100) -> list[dict]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(PathPlanModel).where(PathPlanModel.uav_id == uav_id)
                .order_by(PathPlanModel.created_at.desc()).limit(limit))
            ).scalars().all()
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: PathPlanModel) -> dict:
        return {
            "id": r.id, "uav_id": r.uav_id, "task_id": r.task_id,
            "algorithm": r.algorithm, "waypoints": list(r.waypoints or []),
            "total_distance": r.total_distance, "estimated_time": r.estimated_time,
            "duration_ms": r.duration_ms, "created_at": r.created_at,
        }
