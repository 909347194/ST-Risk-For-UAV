"""统一算法注册表 — 按类别管理所有算法"""

from enum import Enum
from typing import Any, Callable

from src.models.exceptions import AlgorithmNotFoundError


class AlgorithmCategory(str, Enum):
    PATH_PLANNING = "path_planning"
    TASK_ALLOCATION = "task_allocation"


# 全局注册表: {category: {name: fn}}
_REGISTRY: dict[str, dict[str, Callable]] = {}

# 算法元信息: {category: [{name, description, params_schema}]}
_INFO: dict[str, list[dict]] = {}


def register(category: AlgorithmCategory, name: str, fn: Callable, info: dict) -> None:
    """注册算法"""
    cat = category.value
    _REGISTRY.setdefault(cat, {})[name] = fn
    _INFO.setdefault(cat, []).append(info)


def get_algorithm(category: AlgorithmCategory, name: str) -> Callable:
    """获取算法函数，不存在则抛 AlgorithmNotFoundError"""
    cat = _REGISTRY.get(category.value, {})
    if name not in cat:
        available = list(cat.keys())
        raise AlgorithmNotFoundError(name, available)
    return cat[name]


def list_algorithms(category: AlgorithmCategory | None = None) -> list[dict]:
    """列出算法信息"""
    if category:
        return _INFO.get(category.value, [])
    result = []
    for cat, infos in _INFO.items():
        for info in infos:
            result.append({**info, "category": cat})
    return result


# ── 触发各子模块注册 ──────────────────────────────────
from src.algorithms.path_planning import _register as _pp  # noqa: E402
from src.algorithms.task_allocation import _register as _ta  # noqa: E402

_pp()
_ta()
