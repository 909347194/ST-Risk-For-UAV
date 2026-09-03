"""③ 飞行风险评估仓储 — 评估结果缓存（可选）"""

from src.domain.models import RiskAssessment
from src.repositories.base import InMemoryRepository


class RiskAssessmentRepository(InMemoryRepository[RiskAssessment, str]):
    """风险评估结果仓储（按 'uav_id:task_id' 作 key）"""

    def _extract_id(self, entity: RiskAssessment) -> str:
        return f"{entity.uav_id}:{entity.task_id}"

    def find_by_uav(self, uav_id: str) -> list[RiskAssessment]:
        return [r for r in self._store.values() if r.uav_id == uav_id]

    def find_high_risk(self) -> list[RiskAssessment]:
        """返回高风险及以上的评估"""
        return [r for r in self._store.values() if r.risk_level.value in ("high", "critical")]
