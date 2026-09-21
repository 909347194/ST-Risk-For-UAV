"""Clarke-Wright 节约算法 — 多机多任务构造启发式

参考：Clarke G, Wright J W. Scheduling of Vehicles from a Central Depot
to a Number of Delivery Points. Operations Research, 1964.
（开放路线变体：无返程段，与 DE 适应度模型一致）

角色：为 DE 提供高质量初始解（warm_start），也可独立使用。

实现按职责拆分：
  encoding.py  路线逐段代价与 DE 整数编码（to_individual）
  capacity.py  航程/载荷容量检查与构造后修复（rebalance）
  solver.py    ClarkeWrightSolver 主循环与 clarke_wright_allocate 入口
"""

from .solver import ClarkeWrightSolver, clarke_wright_allocate

__all__ = ["ClarkeWrightSolver", "clarke_wright_allocate"]
