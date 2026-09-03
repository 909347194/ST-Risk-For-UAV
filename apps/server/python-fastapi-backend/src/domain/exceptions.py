"""领域异常"""


class DomainError(Exception):
    """领域异常基类"""


class AlgorithmNotFoundError(DomainError):
    """算法不存在"""

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(f"未知算法: {name}，可用: {available}")


class InsufficientResourceError(DomainError):
    """资源不足（电池、载荷等）"""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class RiskExceededError(DomainError):
    """风险超限"""

    def __init__(self, risk_level: str, threshold: str) -> None:
        self.risk_level = risk_level
        self.threshold = threshold
        super().__init__(f"风险等级 {risk_level} 超过阈值 {threshold}")
