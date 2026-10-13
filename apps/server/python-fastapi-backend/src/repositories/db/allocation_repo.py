"""④ 任务分配结果仓储 — PostgreSQL 实现（run + 明细）"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.allocation import AllocationItemModel, AllocationRunModel
from src.domain.models import TaskAllocation


class AllocationRunDbRepository:
    """一次分配调用 = 一条 run + N 条 item"""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_run(
        self,
        *,
        algorithm: str,
        params: dict | None,
        uav_count: int,
        task_count: int,
        allocations: list[TaskAllocation],
        unassigned_task_ids: list[str],
        duration_ms: float | None = None,
    ) -> uuid.UUID:
        async with self._session_factory() as session:
            run = AllocationRunModel(
                algorithm=algorithm,
                params=params,
                uav_count=uav_count,
                task_count=task_count,
                assigned_count=len(allocations),
                unassigned_count=len(unassigned_task_ids),
                unassigned_task_ids=list(unassigned_task_ids),
                duration_ms=duration_ms,
            )
            session.add(run)
            await session.flush()          # 取得 run.id
            run_id = run.id
            session.add_all([
                AllocationItemModel(run_id=run_id, uav_id=a.uav_id,
                                    task_id=a.task_id, estimated_cost=a.estimated_cost)
                for a in allocations
            ])
            await session.commit()
        return run_id

    async def list_runs(self, algorithm: str | None = None, limit: int = 50) -> list[dict]:
        """返回 run 摘要（不含明细）"""
        async with self._session_factory() as session:
            stmt = select(AllocationRunModel).order_by(AllocationRunModel.created_at.desc()).limit(limit)
            if algorithm:
                stmt = stmt.where(AllocationRunModel.algorithm == algorithm)
            rows = (await session.execute(stmt)).scalars().all()
        return [self._summary(r) for r in rows]

    async def count_runs(self, algorithm: str | None = None) -> int:
        """匹配条件的 run 总数（不受 limit 影响，供分页 total 使用）"""
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(AllocationRunModel)
            if algorithm:
                stmt = stmt.where(AllocationRunModel.algorithm == algorithm)
            return (await session.execute(stmt)).scalar_one()

    async def get_run(self, run_id: uuid.UUID) -> dict | None:
        """返回 run 摘要 + 明细"""
        async with self._session_factory() as session:
            run = await session.get(AllocationRunModel, run_id)
            if run is None:
                return None
            items = (await session.execute(
                select(AllocationItemModel).where(AllocationItemModel.run_id == run_id)
                .order_by(AllocationItemModel.id))).scalars().all()
        data = self._summary(run)
        data["allocations"] = [
            TaskAllocation(uav_id=i.uav_id, task_id=i.task_id, estimated_cost=i.estimated_cost)
            for i in items
        ]
        return data

    @staticmethod
    def _summary(run: AllocationRunModel) -> dict:
        return {
            "id": run.id,
            "algorithm": run.algorithm,
            "params": run.params,
            "uav_count": run.uav_count,
            "task_count": run.task_count,
            "assigned_count": run.assigned_count,
            "unassigned_count": run.unassigned_count,
            "unassigned_task_ids": list(run.unassigned_task_ids or []),
            "duration_ms": run.duration_ms,
            "created_at": run.created_at,
        }
