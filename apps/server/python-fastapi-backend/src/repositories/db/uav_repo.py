"""① 无人机仓储 — PostgreSQL 实现"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.uav import UAVModel
from src.domain.enums import UAVStatus
from src.domain.models import Position, UAV
from src.repositories import mappers


class UAVDbRepository:
    """无人机仓储 —— 表归属标注见 src/db/models/uav.py（将来写权限归 Node）"""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _select():
        """逐列显式选取 + ST_AsText 别名。

        必须显式列：select(Model, label) 的结果行只能按 "Model"/"label"
        两个键取属性，row.id / row.position_wkt 会 AttributeError。
        显式列后行对象按列名暴露属性，mappers.uav_to_domain(row) 可直接用。
        """
        return select(
            UAVModel.id,
            UAVModel.speed,
            UAVModel.max_payload,
            UAVModel.battery,
            UAVModel.status,
            func.ST_AsText(UAVModel.position).label("position_wkt"),
        )

    async def save(self, uav: UAV) -> UAV:
        async with self._session_factory() as session:
            model = mappers.uav_to_model(uav)
            await session.merge(model)
            await session.commit()
        return uav

    async def find_by_id(self, uav_id: str) -> UAV | None:
        async with self._session_factory() as session:
            row = (await session.execute(
                self._select().where(UAVModel.id == uav_id))).first()
        return mappers.uav_to_domain(row) if row else None

    async def find_all(self) -> list[UAV]:
        async with self._session_factory() as session:
            rows = (await session.execute(self._select().order_by(UAVModel.id))).all()
        return [mappers.uav_to_domain(r) for r in rows]

    async def find_by_status(self, status: UAVStatus) -> list[UAV]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                self._select().where(UAVModel.status == status.value)
                .order_by(UAVModel.id))).all()
        return [mappers.uav_to_domain(r) for r in rows]

    async def delete(self, uav_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(UAVModel).where(UAVModel.id == uav_id))
            await session.commit()
        return result.rowcount > 0

    async def exists(self, uav_id: str) -> bool:
        return await self.find_by_id(uav_id) is not None

    async def update_status(self, uav_id: str, status: UAVStatus) -> UAV | None:
        async with self._session_factory() as session:
            model = await session.get(UAVModel, uav_id)
            if model is None:
                return None
            model.status = status.value
            await session.commit()
        return await self.find_by_id(uav_id)

    async def update_position(self, uav_id: str, x: float, y: float, z: float) -> UAV | None:
        async with self._session_factory() as session:
            model = await session.get(UAVModel, uav_id)
            if model is None:
                return None
            model.position = mappers.position_to_wkt(Position(x=x, y=y, z=z))
            await session.commit()
        return await self.find_by_id(uav_id)
