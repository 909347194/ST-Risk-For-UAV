"""DE 算法本地验证脚本 — 端到端自检（不入库，已加入 .gitignore）

运行:
    cd apps/server/python-fastapi-backend
    uv run python scripts/verify_de.py

退出码: 0 = 全部通过, 1 = 存在失败项
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# 直接以脚本方式运行时，把后端根目录加入 sys.path 以便 import src
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.enums import TaskPriority
from src.domain.models import Position, Task, TaskAllocation, UAV
from src.algorithms.task_allocation.differential_evolution import (
    DiscreteDESolver,
    de_allocate,
)
from src.algorithms.task_allocation.clarke_wright import ClarkeWrightSolver
from src.services.task_allocation import allocate

# ── 校验工具 ──────────────────────────────────────────

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


# ── 场景构造 ──────────────────────────────────────────

def make_uav(x: float, y: float, uid: str, battery: float = 1000.0, speed: float = 10.0) -> UAV:
    return UAV(id=uid, position=Position(x=x, y=y, z=0), speed=speed, max_payload=5.0, battery=battery)


def make_task(x: float, y: float, tid: str, priority: str = "medium", time_limit: float | None = None) -> Task:
    return Task(id=tid, position=Position(x=x, y=y, z=0), payload_weight=1.0,
                priority=TaskPriority(priority), time_limit=time_limit)


def main() -> int:
    uavs = [make_uav(0, 0, "uav-0"), make_uav(100, 0, "uav-1"), make_uav(0, 100, "uav-2")]
    tasks = [
        make_task(10, 10, "task-0", priority="low"),
        make_task(90, 10, "task-1", priority="high"),
        make_task(50, 50, "task-2", priority="urgent"),
        make_task(10, 90, "task-3", priority="medium"),
        make_task(90, 90, "task-4", priority="low"),
    ]

    print("== 1. 注册路径（与 API 同款调用）==")
    t0 = time.perf_counter()
    allocations, unassigned = allocate(
        uavs, tasks, algorithm="de",
        params={"seed": 0, "pop_size": 40, "generations": 100},
    )
    elapsed = time.perf_counter() - t0
    check("unassigned 为空", unassigned == [], str(unassigned))
    check(
        "每任务恰被分配一次",
        sorted(a.task_id for a in allocations) == sorted(t.id for t in tasks),
        f"共 {len(allocations)} 条分配",
    )
    pairs = [(a.uav_id, a.task_id) for a in allocations]
    check("无重复 (uav, task) 对", len(pairs) == len(set(pairs)))
    check("代价非负", all(a.estimated_cost >= 0 for a in allocations))
    print(f"  总代价 = {sum(a.estimated_cost for a in allocations):.2f}，耗时 {elapsed:.3f}s")

    print("\n== 2. 每机任务序列与收敛统计 ==")
    solver = DiscreteDESolver(uavs, tasks, pop_size=40, generations=100, seed=0,)
    allocation, stats = solver.solve()
    for uav_idx, seq in allocation.items():
        route = " -> ".join(tasks[t].id for t in seq) or "(无任务)"
        print(f"  {uavs[uav_idx].id}: {route}")
    print(
        f"  best_cost={stats['best_cost']:.2f}  "
        f"convergence_gen={stats['convergence_gen']}  time={stats['time_seconds']}s"
    )

    print("\n== 3. 种子可复现 ==")
    a1, _ = de_allocate(uavs, tasks, seed=42)
    a2, _ = de_allocate(uavs, tasks, seed=42)
    key = lambda a: sorted((x.uav_id, x.task_id, round(x.estimated_cost, 6)) for x in a)
    check("同种子两次结果一致", key(a1) == key(a2))

    print("\n== 4. 约束惩罚生效 ==")
    constrained = DiscreteDESolver(uavs, tasks, uav_max_ranges=[5.0] * 3, seed=0)
    free = DiscreteDESolver(uavs, tasks, seed=0)
    ind = [0, 1, 2, 2, 1]  # 任意合法个体
    f_constrained = constrained.evaluate_constrained(ind)
    f_free = free.evaluate_constrained(ind)
    check(
        "超航程违反量大幅抬升适应度",
        f_constrained > f_free + 1000.0,
        f"constrained={f_constrained:.2f} vs free={f_free:.2f}",
    )

    dl_solver = DiscreteDESolver(
        [make_uav(0, 0, "uav-dl")], [make_task(10, 10, "t-dl", time_limit=0.5)], seed=0
    )
    no_dl = DiscreteDESolver([make_uav(0, 0, "uav-dl")], [make_task(10, 10, "t-dl")], seed=0)
    f_dl = dl_solver.evaluate_constrained([0])
    f_no = no_dl.evaluate_constrained([0])
    check(
        "任务 deadline 违反抬升适应度",
        f_dl > f_no + 100.0,
        f"with_dl={f_dl:.2f} vs no_dl={f_no:.2f}",
    )

    print("\n== 5. 参数校验 ==")
    try:
        DiscreteDESolver(uavs, tasks, pop_size=3)
        check("pop_size<4 被拒绝", False, "未抛异常")
    except ValueError as e:
        check("pop_size<4 被拒绝", True, str(e))

    print("\n== 6. 与 hungarian/auction 对比（2 机 2 任务，一对一可比）==")
    cmp_uavs = [make_uav(0, 0, "cu-0"), make_uav(100, 0, "cu-1")]
    cmp_tasks = [make_task(10, 0, "ct-0"), make_task(90, 0, "ct-1")]
    for algo in ("hungarian", "auction", "de"):
        params = {"seed": 0} if algo == "de" else None
        allocs, unalloc = allocate(cmp_uavs, cmp_tasks, algorithm=algo, params=params)
        total = sum(a.estimated_cost for a in allocs)
        print(f"  {algo:>9}: 总代价 {total:8.2f}  未分配 {unalloc}")

    print("\n== 7. 收敛曲线（ASCII，降采样）==")
    hist = stats["history_min"]
    if len(hist) > 1:
        lo, hi = min(hist), max(hist)
        step = max(1, len(hist) // 30)
        for i in range(0, len(hist), step):
            width = 0 if hi == lo else int((hist[i] - lo) / (hi - lo) * 40)
            print(f"  gen {i:>3}: {'#' * width} {hist[i]:.2f}")

    print("\n== 8. 不同规模计时 ==")
    for n_uav, n_task in ((3, 5), (5, 10), (8, 20)):
        big_uavs = [make_uav(i * 30.0, (i % 3) * 40.0, f"b-{i}") for i in range(n_uav)]
        big_tasks = [
            make_task((j * 13) % 250, (j * 7) % 200, f"bt-{j}") for j in range(n_task)
        ]
        t0 = time.perf_counter()
        de_allocate(big_uavs, big_tasks, pop_size=30, generations=60, seed=0)
        dt = time.perf_counter() - t0
        print(f"  {n_uav} 机 × {n_task:>2} 任务: {dt:.3f}s")

    print("\n== 9. 热启动 vs 原算法对比（同 seed 统计，含容量约束）==")
    # 任务沿 x 轴聚类在受限 UAV 附近：贪心初始解会全部塞给受限 UAV 产生高罚分，
    # CW 重分配产出的可行分配作为热启动应带来增益
    scenario1 = (  # 3 机 × 5 任务：uav-0 航程 50，任务链总长 ~88 超过单机容量
        "3 机 × 5 任务（uav-0 航程受限 50）",
        [(0.0, 0.0), (150.0, 0.0), (0.0, 150.0)],
        [(20.0 + 15.0 * j, 15.0) for j in range(5)],
        [50.0, 10000.0, 10000.0],
    )
    scenario2 = (  # 5 机 × 10 任务：uav-0/uav-1 航程 55，任务链需外溢给远端 UAV
        "5 机 × 10 任务（uav-0/uav-1 航程受限 55）",
        [(0.0, 0.0), (150.0, 0.0), (0.0, 150.0), (150.0, 150.0), (300.0, 0.0)],
        [(20.0 + 12.0 * j, 15.0) for j in range(10)],
        [55.0, 55.0, 10000.0, 10000.0, 10000.0],
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

    print("\n" + "=" * 50)
    if FAILURES:
        print(f"结果: {len(FAILURES)} 项失败 -> {FAILURES}")
        return 1
    print("结果: 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
