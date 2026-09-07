# Clarke-Wright 容量重分配 — 设计文档

日期：2026-09-07
分支：feat/python-api-backend

## 1. 背景与目标

验证脚本的对比实验（热启动 vs 原算法）显示 0% 差异，根因：CW 的
`to_individual()` 分配结果与 DE 现有贪心初始化逐位等价（任务挂最近 UAV，
路线顺序在整数编码中被丢弃）。本设计为 CW 增加**容量驱动的任务重分配**，
使 CW 在容量受限场景下产出与贪心不同、且更可行的分配，让 DE 热启动
产生真实增益。

## 2. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 机制形态 | 构造后修复循环（savings 合并结束后调用 `_rebalance`），合并逻辑不变 |
| 移交策略 | 从超容 UAV 最后一条路线**末尾**移除一个任务，移交给"移交后仍不超容且代价增量最小"的其他 UAV |
| 插入位置 | 追加到目标 UAV 最后一条路线末尾；目标无路线时新建单点路线 |
| 容量语义 | 统一为**每机总量**：该机全部路线总航程 ≤ max_range 且总载荷 ≤ max_payload（与 DE 航程约束语义一致）；合并阶段的 `_feasible` 同步改为总量检查 |
| 装不下 | 所有 UAV 均无法容纳时任务保持原位，该机维持超容（DE 罚分处理）；CW 覆盖全部任务、unassigned 恒空契约不变 |
| 终止条件 | 一轮扫描无任何移交即结束；每任务记录上次移出 UAV、禁止移回（防弹跳死循环）；轮数上限 N_task 双保险 |
| 波及面 | DE 零改动；`to_individual()` / `clarke_wright_allocate()` 自动反映重分配 |

## 3. 算法细节

`solve()` 流程变为：

```
1. 初始: 每个任务一条单点路线，挂到最近 UAV（不变）
2. savings 合并: _feasible 改为每机总量检查（航程 + 载荷）
3. _rebalance 修复循环（新增）:
   while 轮数 <= N_task:
       找第一架总容量超限的 UAV
       → 取其最后一条路线的末尾任务 task
       → 对每个其他 UAV 计算: 追加 task 后是否仍不超容
         （总航程 + 新增段代价 ≤ max_range 且 总载荷 + task 载荷 ≤ max_payload）
         且 task 非"刚从该 UAV 移出"
       → 选代价增量最小的目标; 有则移交并从头重新扫描;
         该路线无目标可接时，继续检查该 UAV 的其余超容路线，再检查其他 UAV
       一轮无任何移交 → 退出
```

代价增量 = 新段代价 `cost_matrix[尾部点或目标 UAV, task]`。

## 4. 测试计划（先写测试，后实现）

`tests/test_task_allocation.py` 增加：

1. `test_cw_rebalance_range`：3 机（uav-0 航程受限），两任务最近 uav-0 且
   总量超程 → 修复后超程任务移交给代价增量最小的 uav-1
2. `test_cw_rebalance_payload`：2 机，uav-0 总载荷 6 > max_payload 5 →
   一个任务移交给 uav-1
3. `test_cw_rebalance_no_target`：单机两任务总载荷超限、无人可接 →
   保持原位、正常返回（不崩溃、无死循环）
4. 回归：现有 51 个测试全部通过

## 5. 验证脚本更新（本地文件 scripts/verify_de.py，不入库）

对比实验的 2 个场景加入 `uav_max_ranges` 容量约束（部分 UAV 航程受限），
使贪心初始解产生高罚分。预期：热启动平均 best_cost 改善、收敛代数提前；
若仍无差异则说明场景约束力度不够，继续调场景参数（脚本本地迭代，不涉及仓库代码）。

## 6. 涉及文件清单

| 文件 | 动作 |
|---|---|
| `src/algorithms/task_allocation/clarke_wright.py` | 修改 — `_feasible` 总量语义 + `_rebalance` + solve 调用 |
| `tests/test_task_allocation.py` | 修改 — 新增 3 个重分配测试 |
| `scripts/verify_de.py`（本地，不入库） | 修改 — 对比场景加容量约束 |

## 7. 错误处理

- 空输入：`solve()` 直接返回空路线表（现有行为）
- 移交无目标：保持原位，循环按轮数上限退出
- 防死循环：禁止移回上次 UAV + 轮数上限 N_task
