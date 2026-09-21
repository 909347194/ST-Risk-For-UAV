"""Clarke-Wright 节约算法 — 兼容入口

原单文件实现已按职责拆分为 encoding / capacity / solver 子模块。
本文件保留以兼容旧的子模块导入路径，例如：
  from src.algorithms.task_allocation.clarke_wright.clarke_wright import ClarkeWrightSolver
"""

from .solver import ClarkeWrightSolver, clarke_wright_allocate

__all__ = ["ClarkeWrightSolver", "clarke_wright_allocate"]
