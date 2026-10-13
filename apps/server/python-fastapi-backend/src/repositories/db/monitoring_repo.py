"""⑥ 飞行监控仓储 — PostgreSQL 实现（快照 + 告警）"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.monitoring import FlightAlertModel, FlightSnapshotModel
from src.domain.models import UAVHealthSnapshot
from src.repositories import mappers


class FlightLogDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    # ── 快照 ──

    async def append_snapshot(self, snapshot: UAVHealthSnapshot) -> None:
        async with self._session_factory() as session:
            session.add(mappers.snapshot_to_model(snapshot))
            await session.commit()

    async def get_track(self, uav_id: str, limit: int = 100) -> list[UAVHealthSnapshot]:
        async with self._session_factory() as session:
            subq = (select(FlightSnapshotModel.id)
                    .where(FlightSnapshotModel.uav_id == uav_id)
                    .order_by(FlightSnapshotModel.ts.desc(), FlightSnapshotModel.id.desc())
                    .limit(limit).subquery())
            # 逐列显式选取：行对象按列名暴露属性，snapshot_to_domain 直接消费
            rows = (await session.execute(
                select(
                    FlightSnapshotModel.uav_id,
                    FlightSnapshotModel.ts,
                    FlightSnapshotModel.battery_remaining,
                    FlightSnapshotModel.speed,
                    FlightSnapshotModel.heading,
                    FlightSnapshotModel.is_anomaly,
                    FlightSnapshotModel.anomaly_reasons,
                    func.ST_AsText(FlightSnapshotModel.position).label("position_wkt"),
                )
                .where(FlightSnapshotModel.id.in_(select(subq.c.id)))
                .order_by(FlightSnapshotModel.ts.asc(), FlightSnapshotModel.id.asc())
            )).all()
        return [mappers.snapshot_to_domain(r) for r in rows]

    async def get_latest(self, uav_id: str) -> UAVHealthSnapshot | None:
        track = await self.get_track(uav_id, limit=1)
        return track[-1] if track else None

    async def get_active_uav_ids(self) -> list[str]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(FlightSnapshotModel.uav_id).distinct()
                .order_by(FlightSnapshotModel.uav_id))).all()
        return [r.uav_id for r in rows]

    # ── 告警 ──

    async def append_alert(self, uav_id: str, alert: str) -> None:
        async with self._session_factory() as session:
            session.add(FlightAlertModel(uav_id=uav_id, message=alert))
            await session.commit()

    async def get_alerts(self, uav_id: str) -> list[str]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(FlightAlertModel.message)
                .where(FlightAlertModel.uav_id == uav_id)
                .order_by(FlightAlertModel.id))).all()
        return [r.message for r in rows]

    async def clear_alerts(self, uav_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(FlightAlertModel).where(FlightAlertModel.uav_id == uav_id))
            await session.commit()
