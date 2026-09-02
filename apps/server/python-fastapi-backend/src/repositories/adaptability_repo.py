"""② 任务适配评估仓储 — 评估结果缓存（可选）"""

from src.models.models import AdaptabilityResult
from src.repositories.base import InMemoryRepository


class AdaptabilityResultRepository(InMemoryRepository[AdaptabilityResult, str]):
    """适配评估结果仓储（按 'uav_id:task_id' 作 key）"""

    def _extract_id(self, entity: AdaptabilityResult) -> str:
        return f"{entity.uav_id}:{entity.task_id}"

    def find_by_uav(self, uav_id: str) -> list[AdaptabilityResult]:
        return [r for r in self._store.values() if r.uav_id == uav_id]

    def find_by_task(self, task_id: str) -> list[AdaptabilityResult]:
        return [r for r in self._store.values() if r.task_id == task_id]

    def find_capable(self, task_id: str) -> list[AdaptabilityResult]:
        """返回能胜任指定任务的 UAV 评估结果（按评分降序）"""
        results = [r for r in self._store.values() if r.task_id == task_id and r.capable]
        results.sort(key=lambda r: r.score, reverse=True)
        return results
