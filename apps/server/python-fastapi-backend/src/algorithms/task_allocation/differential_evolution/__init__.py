"""离散差分进化 (DE) 任务分配算法

参考：
  樊国政等《基于改进差分进化算法的同构无人机任务分配》
  Zhao et al., Acta Automatica Sinica, 2012, 38(12): 2038-2048.

核心思想：整数编码 + 连续空间差分变异 + 取整钳位修复

实现按职责拆分：
  config.py      超参数 DEConfig 与命名常量（单一来源）
  encoding.py    整数编码 ↔ 分配方案、最近邻排序与路径代价
  population.py  种群初始化（随机 / 贪心 / 热启动）
  operators.py   自适应 F/CR、变异、交叉、修复
  fitness.py     基础 / 约束感知适应度
  solver.py      DiscreteDESolver 主循环与 de_allocate 入口
"""

from .solver import DiscreteDESolver, de_allocate

__all__ = ["DiscreteDESolver", "de_allocate"]
