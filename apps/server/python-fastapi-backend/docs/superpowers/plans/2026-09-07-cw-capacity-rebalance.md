# CW 容量重分配 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ClarkeWrightSolver 增加构造后容量重分配修复循环，使 CW 在容量受限场景产出可行且不同于贪心的分配，让 DE 热启动产生真实增益。

**Architecture:** `_feasible` 改为每机总量语义（总航程 ≤ max_range、总载荷 ≤ max_payload）；solve() 合并后调用 `_rebalance`：超容 UAV 路线末尾任务移交给最小代价增量且不超容的目标，防回移 + 轮数上限保证终止。

**Tech Stack:** Python 3.12、numpy、pytest。

**Spec:** `docs/superpowers/specs/2026-09-07-cw-capacity-rebalance-design.md`

## Global Constraints

- 所有改动仅限 `apps/server/python-fastapi-backend/` 目录（分支范围约束）
- DE 零改动；`to_individual()` / `clarke_wright_allocate()` 行为随重分配自动变化，现有测试必须继续通过
- 容量语义：**每机总量**（全部路线总航程 ≤ max_range 且总载荷 ≤ max_payload），合并阶段与修复阶段统一
- 移交规则：从超容 UAV 最后一条路线**末尾**移除任务；目标 = "移交后不超容且代价增量最小"的其他 UAV；无路线时新建单点路线，否则追加到最后一条路线末尾
- 终止：一轮无移交即退出；每任务禁止移回上次移出的 UAV；轮数上限 N_task
- 装不下保持原位；unassigned 恒空契约不变；空输入行为不变
- `scripts/verify_de.py` 是本地文件（已被 .gitignore 忽略），**不提交**、不 `git add`
- Commit 规范：`feat(python-api): 中文描述`
- 测试命令在 `apps/server/python-fastapi-backend/` 目录下运行，用 `uv run`

---

### Task 1: 每机总量语义 + _rebalance 修复循环

**Files:**
- Modify: `src/algorithms/task_allocation/clarke_wright.py`（`_feasible`、合并循环调用点、新增 `_rebalance`、solve 调用）
- Test: `tests/test_task_allocation.py`（追加 3 个测试）

**Interfaces:**
- Consumes: `ClarkeWrightSolver` 现状（`route_segment_costs` / `cost_matrix` / `uav_max_ranges` / `solve`）
- Produces: `_feasible(uav_idx, route_list: list[list[int]]) -> bool`（每机总量语义）；`_rebalance(routes) -> None`；`solve()` 输出在容量受限场景含重分配结果

- [ ] **Step 1: 追加失败测试**

`tests/test_task_allocation.py` 末尾追加：

```python
def test_cw_rebalance_range():
    uavs = [
        _de_uav(0, 0, "uav-0"),
        _de_uav(100, 0, "uav-1"),
        _de_uav(0, 100, "uav-2"),
    ]
    tasks = [
        _de_task(30, 0, "task-0", priority="low"),
        _de_task(45, 0, "task-1", priority="low"),
    ]
    # 两任务都最近 uav-0（30<70、45<55）；uav-0 航程 40：
    # 合并 [0,1] 总航程 45 > 40 被拒；修复把 t1（单点 45 > 40 也超）移交给
    # 代价增量最小的 uav-1（55）而非 uav-2（≈110）
    solver = ClarkeWrightSolver(uavs, tasks, uav_max_ranges=[40.0, 1000.0, 1000.0])
    routes = solver.solve()
    flat0 = [t for route in routes[0] for t in route]
    flat1 = [t for route in routes[1] for t in route]
    assert flat0 == [0]
    assert flat1 == [1]


def test_cw_rebalance_payload():
    uav0 = UAV(id="uav-0", position=Position(x=0, y=0, z=0), speed=10.0, max_payload=5.0, battery=1000.0)
    uav1 = UAV(id="uav-1", position=Position(x=100, y=0, z=0), speed=10.0, max_payload=10.0, battery=1000.0)
    t0 = Task(id="task-0", position=Position(x=10, y=0, z=0), payload_weight=3.0)
    t1 = Task(id="task-1", position=Position(x=20, y=0, z=0), payload_weight=3.0)
    # 两任务都最近 uav-0；总载荷 6 > 5 超容 → t1 移交给 uav-1
    solver = ClarkeWrightSolver([uav0, uav1], [t0, t1])
    routes = solver.solve()
    flat0 = [t for route in routes[0] for t in route]
    flat1 = [t for route in routes[1] for t in route]
    assert flat0 == [0]
    assert flat1 == [1]


def test_cw_rebalance_no_target():
    uav = UAV(id="uav-0", position=Position(x=0, y=0, z=0), speed=10.0, max_payload=5.0, battery=1000.0)
    t0 = Task(id="task-0", position=Position(x=10, y=0, z=0), payload_weight=3.0)
    t1 = Task(id="task-1", position=Position(x=20, y=0, z=0), payload_weight=3.0)
    # 单机、无人可接 → 保持原位、正常返回（无死循环）
    solver = ClarkeWrightSolver([uav], [t0, t1])
    routes = solver.solve()
    assigned = sorted(t for route_list in routes.values() for route in route_list for t in route)
    assert assigned == [0, 1]
    assert len(routes[0]) == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_cw_rebalance_range -v`
Expected: FAIL（当前无 `_rebalance`，routes[0] 含两任务）

- [ ] **Step 3: 修改 _feasible 为每机总量语义**

替换 `clarke_wright.py` 中的 `_feasible` 方法：

```python
    # ———— 容量检查 ————
    def _feasible(self, uav_idx: int, route_list: list[list[int]]) -> bool:
        """每机总量容量检查：全部路线总航程 ≤ max_range 且总载荷 ≤ max_payload"""
        total_distance = sum(
            sum(self.route_segment_costs(uav_idx, route)) for route in route_list
        )
        if total_distance > self.uav_max_ranges[uav_idx]:
            return False
        total_payload = sum(
            self.tasks[tid].payload_weight for route in route_list for tid in route
        )
        if total_payload > self.uavs[uav_idx].max_payload:
            return False
        return True
```

合并循环中的检查调用改为（找到 `if not self._feasible(uav_idx, merged):` 一行替换为）：

```python
                        other_routes = [
                            route_list[idx]
                            for idx in range(len(route_list))
                            if idx not in (a, b)
                        ]
                        if not self._feasible(uav_idx, other_routes + [merged]):
                            continue
```

- [ ] **Step 4: 新增 _rebalance 并接入 solve**

在 `solve()` 的合并循环 `return routes` 之前插入调用：

```python
        self._rebalance(routes)
        return routes
```

在 `solve` 方法之后新增方法：

```python
    # ———— 容量修复 ————
    def _rebalance(self, routes: dict[int, list[list[int]]]) -> None:
        """构造后修复：超容 UAV 路线末尾任务移交给最小代价增量且不超容的目标"""
        last_moved_from: dict[int, int] = {}  # task_idx -> 上次移出的 UAV（禁止移回）
        rounds = 0
        while rounds <= self.N_task:
            rounds += 1
            any_moved = False
            for uav_idx in range(self.N_uav):
                if self._feasible(uav_idx, routes[uav_idx]):
                    continue
                for route in reversed(routes[uav_idx]):
                    task = route[-1]
                    best_target: int | None = None
                    best_inc = float("inf")
                    for target in range(self.N_uav):
                        if target == uav_idx or last_moved_from.get(task) == target:
                            continue
                        if routes[target]:
                            candidate = routes[target][:-1] + [routes[target][-1] + [task]]
                            prev = routes[target][-1][-1]
                            inc = self.cost_matrix[self.N_uav + prev, self.N_uav + task]
                        else:
                            candidate = [[task]]
                            inc = self.cost_matrix[target, self.N_uav + task]
                        if not self._feasible(target, candidate):
                            continue
                        if inc < best_inc:
                            best_inc = inc
                            best_target = target
                    if best_target is not None:
                        route.pop()
                        if not route:
                            routes[uav_idx].remove(route)
                        if routes[best_target]:
                            routes[best_target][-1].append(task)
                        else:
                            routes[best_target].append([task])
                        last_moved_from[task] = uav_idx
                        any_moved = True
                        break
                if any_moved:
                    break
            if not any_moved:
                return
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k "cw" -v`
Expected: 全部 CW 测试通过（新增 3 + 现有 9）

- [ ] **Step 6: 全量回归**

Run: `uv run pytest tests/ -q`
Expected: 54 passed（51 + 3）

- [ ] **Step 7: Commit**

```bash
git add src/algorithms/task_allocation/clarke_wright.py tests/test_task_allocation.py
git commit -m "feat(python-api): 添加 CW 容量重分配修复循环"
```

---

### Task 2: 验证脚本对比场景加容量约束（本地文件，不提交）

**Files:**
- Modify: `scripts/verify_de.py`（本地，.gitignore 忽略，不提交）

**Interfaces:**
- Consumes: Task 1 的 `_rebalance`（CW 在容量受限场景产出可行分配）
- Produces: 对比实验输出（热启动 vs 原算法在容量受限场景的 best_cost / 收敛代数 / 改善率）

- [ ] **Step 1: 修改第 9 节对比场景**

把 `verify_de.py` 中 `== 9. 热启动 vs 原算法对比 ==` 一节整体替换为：

```python
    print("\n== 9. 热启动 vs 原算法对比（同 seed 统计，含容量约束）==")
    # 任务沿 x 轴聚类在受限 UAV 附近：贪心初始解会全部塞给受限 UAV 产生高罚分，
    # CW 重分配产出的可行分配作为热启动应带来增益
    scenario1 = (  # 3 机 × 5 任务：uav-0 航程 70，任务链总长 ~88 超过单机容量
        "3 机 × 5 任务（uav-0 航程受限 70）",
        [(0.0, 0.0), (150.0, 0.0), (0.0, 150.0)],
        [(20.0 + 15.0 * j, 15.0) for j in range(5)],
        [70.0, 10000.0, 10000.0],
    )
    scenario2 = (  # 5 机 × 10 任务：uav-0/uav-1 航程 70，任务链需外溢给远端 UAV
        "5 机 × 10 任务（uav-0/uav-1 航程受限 70）",
        [(0.0, 0.0), (150.0, 0.0), (0.0, 150.0), (150.0, 150.0), (300.0, 0.0)],
        [(20.0 + 12.0 * j, 15.0) for j in range(10)],
        [70.0, 70.0, 10000.0, 10000.0, 10000.0],
    )
    for name, uav_xy, task_xy, ranges in (scenario1, scenario2):
        print(f"\n 场景: {name}")
        plain_rows: list[dict] = []
        warm_rows: list[dict] = []
        for seed in range(5):
            uavs = [make_uav(x, y, f"c-{i}") for i, (x, y) in enumerate(uav_xy)]
            tasks = [make_task(x, y, f"ct-{j}") for j, (x, y) in enumerate(task_xy)]
            ws = ClarkeWrightSolver(uavs, tasks, uav_max_ranges=ranges).to_individual()

            plain = DiscreteDESolver(
                uavs, tasks, pop_size=40, generations=100, seed=seed, uav_max_ranges=ranges
            )
            _, s_plain = plain.solve()
            warm = DiscreteDESolver(
                uavs, tasks, pop_size=40, generations=100, seed=seed,
                uav_max_ranges=ranges, warm_start=ws,
            )
            _, s_warm = warm.solve()

            plain_rows.append(s_plain)
            warm_rows.append(s_warm)
            print(
                f"  seed={seed}: 原算法 best={s_plain['best_cost']:8.2f} "
                f"收敛@gen {s_plain['convergence_gen']:>3} {s_plain['time_seconds']}s | "
                f"热启动 best={s_warm['best_cost']:8.2f} "
                f"收敛@gen {s_warm['convergence_gen']:>3} {s_warm['time_seconds']}s"
            )

        avg_plain = sum(r["best_cost"] for r in plain_rows) / len(plain_rows)
        avg_warm = sum(r["best_cost"] for r in warm_rows) / len(warm_rows)
        avg_gen_plain = sum(r["convergence_gen"] for r in plain_rows) / len(plain_rows)
        avg_gen_warm = sum(r["convergence_gen"] for r in warm_rows) / len(warm_rows)
        improvement = (avg_plain - avg_warm) / avg_plain * 100 if avg_plain > 0 else 0.0
        print(
            f"  平均: 原算法 best={avg_plain:.2f} 收敛@gen {avg_gen_plain:.1f} | "
            f"热启动 best={avg_warm:.2f} 收敛@gen {avg_gen_warm:.1f} | "
            f"解质量改善 {improvement:+.1f}%"
        )
        check(
            f"{name} 热启动平均解质量不劣于原算法",
            avg_warm <= avg_plain * 1.01,
            f"改善 {improvement:+.1f}%（容忍 1% 随机波动）",
        )
```

- [ ] **Step 2: 运行验证脚本**

Run: `uv run python scripts/verify_de.py`
Expected: EXIT_CODE=0，第 9 节打印两场景各 5 seed 的对比与平均改善率

- [ ] **Step 3: 报告结果（无 commit）**

把第 9 节的实际输出（两场景的平均 best_cost、收敛代数、改善率）汇报给协调者。
若改善率仍为 0：说明场景容量约束力度不够（贪心与 CW 重分配后分配一致），
调紧受限 UAV 的航程值（如 70→50）重跑，直到出现差异或有明确结论为止。
脚本为本地文件，不 `git add`、不提交。

---

## 完成验收

- `uv run pytest tests/ -q` → 54 passed
- 对比实验显示容量受限场景下热启动的平均解质量不劣于原算法（且期望出现正改善与收敛提前）
- 全部 commit 落在 `feat/python-api-backend` 分支，只改 `apps/server/python-fastapi-backend/` 目录（scripts/verify_de.py 除外，本地忽略）
