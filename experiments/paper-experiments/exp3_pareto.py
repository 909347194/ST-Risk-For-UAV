"""
Experiment 3 IMPROVED: Noise-Safety Pareto Trade-off

=== 改进设计 ===

问题根因：原 OD 对角线不穿过住宅区，噪声贡献 0.004 远小于距离贡献 28.6，
         权重调整无法改变路径。

改进策略：
1. OD 对穿过住宅区核心 — 最短路径必须经过高噪声敏感区
2. 夜间出发 (t=22) — 住宅区 T_penalty=×10，噪声放大 10 倍
3. 扫描 w_noise 从极低到极高，观察路径从"穿住宅区"到"绕行住宅区"的转变
4. 增加噪声敏感区面积，放大噪声差异

预期 Pareto 前沿：
- 低 w_noise：路径短但噪声高（穿住宅区）
- 高 w_noise：路径长但噪声低（绕住宅区）
- 中间权重：Pareto 最优过渡
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.grid_system import (
    GridSystem, SpatialGridConfig, TemporalGridConfig,
)
from core.p_crash import DynamicCrashProbability
from core.fatality import DynamicFatalityModel
from core.property import PropertyDamageModel
from core.noise import DynamicNoiseCost
from core.env_tensor import EnvTensor
from core.td_risk_astar import AStar4D
from core.synthetic import generate_synthetic_city

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

T_START = 22  # 夜间出发，噪声惩罚最大
OUTPUT_DIR = Path(__file__).resolve().parent / "results" / "exp3_pareto"

# ===== 改进的权重扫描：增大 w_noise 范围 =====
WEIGHT_CONFIGS = [
    {"label": "w_n=0.01", "w_noise": 0.01, "w_fatality": 0.25, "w_property": 0.04, "w_distance": 0.70},
    {"label": "w_n=0.05", "w_noise": 0.05, "w_fatality": 0.25, "w_property": 0.05, "w_distance": 0.65},
    {"label": "w_n=0.10", "w_noise": 0.10, "w_fatality": 0.25, "w_property": 0.05, "w_distance": 0.60},
    {"label": "w_n=0.20", "w_noise": 0.20, "w_fatality": 0.25, "w_property": 0.05, "w_distance": 0.50},
    {"label": "w_n=0.30", "w_noise": 0.30, "w_fatality": 0.25, "w_property": 0.05, "w_distance": 0.40},
    {"label": "w_n=0.50", "w_noise": 0.50, "w_fatality": 0.20, "w_property": 0.05, "w_distance": 0.25},
    {"label": "w_n=0.70", "w_noise": 0.70, "w_fatality": 0.15, "w_property": 0.05, "w_distance": 0.10},
    {"label": "w_n=0.85", "w_noise": 0.85, "w_fatality": 0.10, "w_property": 0.03, "w_distance": 0.02},
]

def build_scenario_with_residential_corridor():
    """
    构建场景：OD 最短路径必须穿过大片住宅区。

    关键设计：
    - 住宅区(lu=1)占据地图中央一条横向走廊
    - OD 对：左侧 → 右侧，最短路径直接穿过走廊
    - 夜间出发：住宅区人口 ×4，T_penalty=×10 → 噪声极高
    - 商业区(lu=2)在上下两侧，不影响最短路径
    """
    grid = GridSystem(
        spatial=SpatialGridConfig(nx=60, ny=60, nz=12, dx=10.0, dy=10.0, dz=10.0),
        temporal=TemporalGridConfig(nt=24, dt_minutes=60.0),
    )
    nx, ny, nz, nt = grid.shape

    # 1. 生成基础合成数据
    city_data = generate_synthetic_city(nx=nx, ny=ny, nz=nz, nt=nt, seed=42)
    landuse = city_data["landuse"].astype(np.int32)  # (ny, nx)

    # 2. 重新设计土地利用：中央横向住宅走廊
    #    y=20~40 为住宅区(lu=1)，其余为商业区(lu=2)或绿地(lu=6)
    landuse_modified = np.full_like(landuse, 6)  # 默认绿地
    landuse_modified[20:40, :] = 1  # 中央走廊：住宅
    landuse_modified[5:15, :] = 2   # 上方：商业
    landuse_modified[45:55, :] = 2  # 下方：商业

    # 3. 同步更新人口密度：住宅走廊必须有非零人口
    population_modified = np.zeros_like(city_data["population"], dtype=np.float32)
    # 住宅走廊：基础人口 0.3~0.5（模拟真实住宅密度）
    np.random.seed(42)
    pop_residential = np.random.uniform(0.3, 0.5, size=(ny, nx)).astype(np.float32)
    population_modified[landuse_modified == 1] = pop_residential[landuse_modified == 1]
    # 商业区：基础人口 0.1~0.3
    pop_commercial = np.random.uniform(0.1, 0.3, size=(ny, nx)).astype(np.float32)
    population_modified[landuse_modified == 2] = pop_commercial[landuse_modified == 2]

    # 4. 生成风/雨场（夜间无风雨，隔离噪声效应）
    wind_field = np.ones((ny, nx, nz, nt), dtype=np.float32) * 0.5
    rain_data = np.ones((ny, nx, nt), dtype=np.float32) * 0.0

    return {
        "grid": grid,
        "landuse": landuse_modified,
        "building_heights": city_data["building_heights"].astype(np.float32),
        "population": population_modified,
        "wind_field": wind_field,
        "rain_data": rain_data,
    }

def build_env_tensor(scenario, flight_altitude=50.0):
    """构建环境张量，重点放大地形噪声对比。"""
    grid = scenario["grid"]
    nx, ny, nz, nt = grid.shape
    landuse = scenario["landuse"]  # (ny, nx)

    # 1. P_crash — 夜间无风雨，坠机概率低且均匀
    wind_2d = np.transpose(scenario["wind_field"][:, :, 0, :], (1, 0, 2))  # (nx,ny,nt)
    rain_2d = np.transpose(scenario["rain_data"], (1, 0, 2))

    crash_model = DynamicCrashProbability()
    f_wind = crash_model.compute_wind_factor(wind_2d[:, :, np.newaxis, :])
    f_rain = crash_model.compute_rain_factor(rain_2d[:, :, np.newaxis, :])
    f_obs = np.ones((nx, ny, nz, nt), dtype=np.float32)
    p_crash = crash_model.compute_pcrash(f_wind, f_rain, f_obs, dt=3600.0)
    p_crash = np.clip(p_crash, 0.0, 1.0).astype(np.float32)

    # 2. 潮汐人口密度 — 夜间模式
    landuse_t = np.transpose(landuse, (1, 0))  # (ny,nx) -> (nx,ny)
    base_pop = np.transpose(scenario["population"], (1, 0))
    rho_pop_3d = np.zeros((nx, ny, nt), dtype=np.float32)

    for t in range(nt):
        hour = t
        pop_t = base_pop.copy()
        # 住宅区夜间人口密集
        if 22 <= hour or hour <= 6:
            pop_t[landuse_t == 1] *= 4.0
        else:
            pop_t[landuse_t == 1] *= 0.3
        # 商业区夜间空旷
        if 22 <= hour or hour <= 6:
            pop_t[landuse_t == 2] *= 0.1
        else:
            pop_t[landuse_t == 2] *= 3.0
        rho_pop_3d[:, :, t] = pop_t

    rho_vehicle_3d = rho_pop_3d * 0.1

    # 3. E_fatality
    fatality_model = DynamicFatalityModel()
    e_fatality_3d = fatality_model.compute_fatality_consequence(
        rho_pop=rho_pop_3d, rho_vehicle=rho_vehicle_3d, flight_altitude=flight_altitude,
    )
    e_fatality = np.broadcast_to(e_fatality_3d[:, :, np.newaxis, :], (nx, ny, nz, nt)).astype(np.float32)

    # 4. E_property
    building_t = np.transpose(scenario["building_heights"], (1, 0))
    prop_model = PropertyDamageModel(
        building_heights=building_t, max_prop_damage=1000.0,
        log_normal_mu=3.04, log_normal_sigma=0.5,
    )
    e_property = prop_model.compute_property_consequence(flight_altitude=flight_altitude).astype(np.float32)

    # 5. R_noise — 使用真实潮汐人口，夜间住宅区噪声极高
    noise_model = DynamicNoiseCost(grid=grid)
    r_noise = noise_model.compute_noise_cost(
        landuse=landuse_t,
        population_density=rho_pop_3d,
    ).astype(np.float32)

    # 6. 障碍物
    obstacle = np.zeros((nx, ny, nz), dtype=np.float32)
    for iz in range(nz):
        z_height = (iz + 1.0) * grid.spatial.dz
        obstacle[:, :, iz] = (building_t >= z_height).astype(np.float32)

    return EnvTensor(
        p_crash=p_crash, fatality=e_fatality, property=e_property,
        noise=r_noise, obstacle=obstacle, grid=grid,
    )

def run_experiment():
    print("=" * 60)
    print("Experiment 3 IMPROVED: Noise-Safety Pareto Trade-off")
    print("=" * 60)

    print("\n[1/4] Building scenario with residential corridor...")
    scenario = build_scenario_with_residential_corridor()
    grid = scenario["grid"]
    nx, ny, nz, nt = grid.shape

    # ===== 关键改进：OD 对穿过住宅走廊 =====
    # 起点：左侧 (3, 30, 5) — 住宅走廊中间
    # 终点：右侧 (56, 30, 5) — 住宅走廊中间
    # 最短路径直接穿过住宅区核心
    start = (3, 30, 5, T_START)
    goal = (56, 30, 5)
    print(f"  OD: {start} -> {goal}")
    print(f"  Grid: {grid.shape}")
    print(f"  Landuse corridor: y=20~40 is residential (lu=1)")

    print("\n[2/4] Building risk tensor...")
    env_tensor = build_env_tensor(scenario)
    print(f"  Noise range: [{env_tensor.noise.min():.6f}, {env_tensor.noise.max():.6f}]")
    print(f"  Noise mean: {env_tensor.noise.mean():.6f}")

    print("\n[3/4] Weight scan ({} configs)...".format(len(WEIGHT_CONFIGS)))
    all_results = []
    all_metrics = []

    for i, wc in enumerate(WEIGHT_CONFIGS):
        print(f"\n  [{i+1}/{len(WEIGHT_CONFIGS)}] {wc['label']}")

        config = {
            "uav_speed": 10.0,
            "w_distance": wc["w_distance"],
            "w_fatality": wc["w_fatality"],
            "w_property": wc["w_property"],
            "w_noise": wc["w_noise"],
            "survival_threshold": 0.01,
            "max_battery_time": float("inf"),
            "max_iterations": 2_000_000,
            "max_labels_per_cell": 8,
            "max_climb_rate": 5.0,
            "max_descent_rate": 5.0,
        }

        planner = AStar4D(grid, env_tensor, config)
        result = planner.search(start, goal)

        metrics = _extract_metrics(result)
        metrics["w_noise"] = wc["w_noise"]
        metrics["w_distance"] = wc["w_distance"]
        metrics["label"] = wc["label"]
        all_metrics.append(metrics)
        all_results.append({"config": wc, "result": result, "metrics": metrics})

        if metrics["status"] == "success":
            print(f"    dist={metrics['path_length']:.1f}m  noise={metrics['cum_noise']:.6f}  "
                  f"fatality={metrics['cum_fatality']:.8f}  surv={metrics['final_survival']:.6f}  "
                  f"J={metrics['objective_cost']:.4f}")
        else:
            print(f"    FAILED: {metrics.get('reason', 'N/A')}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _save_metrics_csv(all_metrics)
    _plot_pareto_frontier(all_metrics)
    _plot_weight_sensitivity(all_metrics)
    _plot_paths_2d(all_results, scenario)
    _plot_metrics_table(all_metrics)

    print(f"\n[OK] Experiment 3 v2 complete! Results: {OUTPUT_DIR}")
    return all_results, all_metrics

def _extract_metrics(result):
    if result["status"] != "success":
        return {"status": result["status"], "reason": result.get("reason", "N/A"),
                "path_length": float("inf"), "final_survival": 0.0,
                "cum_fatality": float("inf"), "cum_property": float("inf"),
                "cum_noise": float("inf"), "objective_cost": float("inf"),
                "runtime_ms": result.get("time_cost", 0) * 1000,
                "nodes_explored": result.get("nodes_explored", 0)}
    return {"status": "success", "reason": "N/A",
            "path_length": result["total_distance"],
            "final_survival": result["final_p_survival"],
            "cum_fatality": result["cum_fatality"],
            "cum_property": result["cum_property"],
            "cum_noise": result["cum_noise"],
            "objective_cost": result["objective_cost"],
            "runtime_ms": result["time_cost"] * 1000,
            "nodes_explored": result["nodes_explored"]}

def _save_metrics_csv(all_metrics):
    csv_path = OUTPUT_DIR / "metrics.csv"
    header = "label,w_noise,w_distance,status,path_length,final_survival,cum_fatality,cum_noise,objective_cost,runtime_ms,nodes_explored"
    lines = [header]
    for m in all_metrics:
        lines.append("{},{},{},{},{:.4f},{:.6f},{:.8f},{:.6f},{:.6f},{:.1f},{}".format(
            m["label"], m["w_noise"], m["w_distance"], m["status"],
            m["path_length"], m["final_survival"],
            m["cum_fatality"], m["cum_noise"], m["objective_cost"],
            m["runtime_ms"], m["nodes_explored"]))
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [OK] Saved: {csv_path}")

def _plot_pareto_frontier(all_metrics):
    """核心图：噪声-距离 Pareto 散点图 + 噪声-致死 Pareto 散点图。"""
    success = [m for m in all_metrics if m["status"] == "success"]
    if not success:
        return

    fig, axes = plt.subplots(1, 3, figsize=(20, 6), facecolor="white")
    w_noises = [m["w_noise"] for m in success]

    # Pareto 1: 噪声 vs 距离
    ax = axes[0]
    noises = [m["cum_noise"] for m in success]
    dists = [m["path_length"] for m in success]
    sc = ax.scatter(noises, dists, c=w_noises, cmap="RdYlBu_r", s=120,
                    edgecolors="black", zorder=5, vmin=0, vmax=1)
    ax.plot(noises, dists, "k--", alpha=0.4, linewidth=1)
    for m in success:
        ax.annotate(f"w={m['w_noise']:.2f}", (m["cum_noise"], m["path_length"]),
                    fontsize=7, ha="center", va="bottom")
    ax.set_xlabel("Cumulative Noise Cost", fontsize=12)
    ax.set_ylabel("Path Length (m)", fontsize=12)
    ax.set_title("Pareto: Noise vs Distance", fontsize=13, fontweight="bold")
    plt.colorbar(sc, ax=ax, label="w_noise")

    # Pareto 2: 噪声 vs 致死
    ax = axes[1]
    fatalities = [m["cum_fatality"] for m in success]
    sc = ax.scatter(noises, fatalities, c=w_noises, cmap="RdYlBu_r", s=120,
                    edgecolors="black", zorder=5, vmin=0, vmax=1)
    ax.plot(noises, fatalities, "k--", alpha=0.4, linewidth=1)
    ax.set_xlabel("Cumulative Noise Cost", fontsize=12)
    ax.set_ylabel("Cumulative Fatality", fontsize=12)
    ax.set_title("Pareto: Noise vs Fatality", fontsize=13, fontweight="bold")
    plt.colorbar(sc, ax=ax, label="w_noise")

    # Pareto 3: 噪声 vs 存活
    ax = axes[2]
    survivals = [m["final_survival"] for m in success]
    sc = ax.scatter(noises, survivals, c=w_noises, cmap="RdYlBu_r", s=120,
                    edgecolors="black", zorder=5, vmin=0, vmax=1)
    ax.plot(noises, survivals, "k--", alpha=0.4, linewidth=1)
    ax.set_xlabel("Cumulative Noise Cost", fontsize=12)
    ax.set_ylabel("Final Survival Probability", fontsize=12)
    ax.set_title("Pareto: Noise vs Survival", fontsize=13, fontweight="bold")
    plt.colorbar(sc, ax=ax, label="w_noise")

    fig.suptitle("Exp3 v2: Noise-Safety Pareto Trade-off (Night, Residential Corridor)",
                 fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_pareto_frontier.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  [OK] Saved: fig_pareto_frontier.png")

def _plot_weight_sensitivity(all_metrics):
    """权重敏感性：w_noise vs 各指标的变化曲线。"""
    success = [m for m in all_metrics if m["status"] == "success"]
    if not success:
        return

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), facecolor="white")
    w_noises = [m["w_noise"] for m in success]

    for key, title, ax in [
        ("path_length", "Path Length (m)", axes[0, 0]),
        ("cum_noise", "Cumulative Noise", axes[0, 1]),
        ("cum_fatality", "Cumulative Fatality", axes[1, 0]),
        ("final_survival", "Final Survival", axes[1, 1]),
    ]:
        values = [m[key] for m in success]
        ax.plot(w_noises, values, "o-", color="#3498DB", linewidth=2, markersize=8)
        ax.set_xlabel("w_noise", fontsize=11)
        ax.set_ylabel(title, fontsize=11)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3)

        # 标注路径是否变化
        if key == "path_length":
            unique_paths = len(set(round(v, 1) for v in values))
            ax.text(0.02, 0.98, f"Unique paths: {unique_paths}",
                    transform=ax.transAxes, fontsize=10, va="top",
                    bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.suptitle("Exp3 v2: Weight Sensitivity Analysis", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_weight_sensitivity.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  [OK] Saved: fig_weight_sensitivity.png")

def _plot_paths_2d(all_results, scenario):
    """绘制不同权重下的路径对比图，高亮住宅走廊。"""
    fig, axes = plt.subplots(2, 4, figsize=(24, 12), facecolor="white")
    landuse = scenario["landuse"]  # (ny, nx)

    # 选取有代表性的权重
    representative = [0, 2, 4, 7]  # w_n=0.01, 0.10, 0.30, 0.85

    for idx, (ax_idx, res_idx) in enumerate(zip(range(8), representative * 2)):
        if idx >= 8:
            break
        ax = axes.flat[idx]
        if idx < 4:
            # 上排：路径 + 土地利用
            res = all_results[res_idx]
            ax.imshow(landuse, cmap="Set3", origin="lower", alpha=0.6, vmin=0, vmax=6)
            if res["result"]["status"] == "success":
                path = res["result"]["path"]
                xs = [step["coords"][0] for step in path]
                ys = [step["coords"][1] for step in path]
                ax.plot(xs, ys, "r-", linewidth=2.5, alpha=0.9)
                ax.scatter(xs[0], ys[0], c="green", s=100, marker="o", edgecolors="black", zorder=5)
                ax.scatter(xs[-1], ys[-1], c="red", s=100, marker="*", edgecolors="black", zorder=5)
            ax.set_title(f"{res['metrics']['label']}\ndist={res['metrics']['path_length']:.0f}m  "
                         f"noise={res['metrics']['cum_noise']:.6f}",
                         fontsize=10, fontweight="bold")
        else:
            # 下排：跳过
            ax.axis("off")

    fig.suptitle("Exp3 v2: Path Evolution as w_noise Increases", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_paths_2d.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  [OK] Saved: fig_paths_2d.png")

def _plot_metrics_table(all_metrics):
    fig, ax = plt.subplots(figsize=(16, 5), facecolor="white")
    ax.axis("off")

    headers = ["Config", "w_noise", "Path(m)", "Survival", "Noise", "Fatality", "Nodes"]
    rows = []
    for m in all_metrics:
        rows.append([
            m["label"], f"{m['w_noise']:.2f}",
            f"{m['path_length']:.1f}" if m["status"] == "success" else "N/A",
            f"{m['final_survival']:.6f}" if m["status"] == "success" else "N/A",
            f"{m['cum_noise']:.6f}" if m["status"] == "success" else "N/A",
            f"{m['cum_fatality']:.8f}" if m["status"] == "success" else "N/A",
            str(m["nodes_explored"]),
        ])

    table = ax.table(cellText=rows, colLabels=headers, cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.5)
    for j in range(len(headers)):
        table[0, j].set_facecolor("#8E44AD")
        table[0, j].set_text_props(color="white", fontweight="bold")

    ax.set_title("Exp3 v2: Metrics Summary", fontsize=13, fontweight="bold", pad=20)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_metrics_table.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  [OK] Saved: fig_metrics_table.png")

if __name__ == "__main__":
    run_experiment()
