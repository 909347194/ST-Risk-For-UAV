"""
微观实验完善版：基线对比 + 多OD泛化 + 参数敏感性 + 统计显著性

覆盖所有 P0/P1/P2 改进项，一次运行出完整结果。
"""
from __future__ import annotations
import time, json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import numpy as np

from core.grid_system import GridSystem, SpatialGridConfig, TemporalGridConfig
from core.p_crash import DynamicCrashProbability
from core.fatality import DynamicFatalityModel
from core.property import PropertyDamageModel
from core.noise import DynamicNoiseCost
from core.env_tensor import EnvTensor
from core.td_risk_astar import AStar4D
from core.synthetic import generate_synthetic_city

OUTPUT_DIR = Path(__file__).resolve().parent / "results" / "exp5_comprehensive"

# ============================================================
# 场景构建
# ============================================================

def build_micro_scenario(seed=42):
    """微观场景：60×60×12×24，含时空动态风险。"""
    grid = GridSystem(
        spatial=SpatialGridConfig(nx=60, ny=60, nz=12, dx=10.0, dy=10.0, dz=10.0),
        temporal=TemporalGridConfig(nt=24, dt_minutes=60.0),
    )
    nx, ny, nz, nt = grid.shape
    city = generate_synthetic_city(nx=nx, ny=ny, nz=nz, nt=nt, seed=seed)

    landuse = city["landuse"].astype(np.int32)
    bh = city["building_heights"].astype(np.float32)
    wind = city["wind_field"].astype(np.float32)
    rain = city["rain_data"].astype(np.float32)

    # 注入风场热点：中心 12-18 时 +8 m/s
    cy, cx = ny // 2, nx // 2
    yy, xx = np.mgrid[0:ny, 0:nx]
    dist_sq = (xx - cx) ** 2 + (yy - cy) ** 2
    hotspot = np.exp(-dist_sq / (2 * 8 ** 2))
    for t in range(nt):
        hr = t
        if 12 <= hr <= 18: f = 8.0
        elif 6 <= hr <= 11: f = 4.0
        else: f = 1.0
        for iz in range(nz):
            wind[:, :, iz, t] += hotspot * f

    # 降雨热点 14-20 时
    rain_hotspot = np.exp(-dist_sq / (2 * 10 ** 2))
    for t in range(nt):
        if 14 <= t <= 20:
            rain[:, :, t] += rain_hotspot * 15.0

    # 人口潮汐
    lu_t = np.transpose(landuse, (1, 0))
    bp = np.transpose(city["population"].astype(np.float32), (1, 0))
    rp = np.zeros((nx, ny, nt), dtype=np.float32)
    for t in range(nt):
        p = bp.copy()
        if 8 <= t <= 18: p[lu_t == 2] *= 5.0
        else: p[lu_t == 2] *= 0.1
        if 22 <= t or t <= 6: p[lu_t == 1] *= 4.0
        elif 9 <= t <= 17: p[lu_t == 1] *= 0.2
        if 8 <= t <= 17: p[lu_t == 3] *= 4.0
        else: p[lu_t == 3] *= 0.2
        rp[:, :, t] = p

    return {"grid": grid, "landuse": landuse, "building_heights": bh,
            "population": city["population"].astype(np.float32),
            "wind_field": wind, "rain_data": rain, "rho_pop": rp}

def build_env_tensor(sc, alt=50.0):
    """构建完整 EnvTensor。"""
    grid = sc["grid"]
    nx, ny, nz, nt = grid.shape
    lu = sc["landuse"]

    cm = DynamicCrashProbability()
    w2d = np.transpose(sc["wind_field"][:, :, 0, :], (1, 0, 2))
    r2d = np.transpose(sc["rain_data"], (1, 0, 2))
    fw = cm.compute_wind_factor(w2d[:, :, np.newaxis, :])
    fr = cm.compute_rain_factor(r2d[:, :, np.newaxis, :])
    fo = np.ones((nx, ny, nz, nt), dtype=np.float32)
    pc = np.clip(cm.compute_pcrash(fw, fr, fo, dt=3600.0), 0, 1).astype(np.float32)

    rp = sc["rho_pop"]
    rv = rp * 0.1
    fm = DynamicFatalityModel()
    ef3d = fm.compute_fatality_consequence(rho_pop=rp, rho_vehicle=rv, flight_altitude=alt)
    ef = np.broadcast_to(ef3d[:, :, np.newaxis, :], (nx, ny, nz, nt)).astype(np.float32)

    bt = np.transpose(sc["building_heights"], (1, 0))
    pm = PropertyDamageModel(building_heights=bt, max_prop_damage=1000.0, log_normal_mu=3.04, log_normal_sigma=0.5)
    ep = pm.compute_property_consequence(flight_altitude=alt).astype(np.float32)

    nm = DynamicNoiseCost(grid=grid)
    lu_t = np.transpose(lu, (1, 0))
    rn = nm.compute_noise_cost(landuse=lu_t, population_density=rp).astype(np.float32)

    obs = np.zeros((nx, ny, nz), dtype=np.float32)
    for iz in range(nz):
        obs[:, :, iz] = (bt >= (iz + 1.0) * grid.spatial.dz).astype(np.float32)

    return EnvTensor(p_crash=pc, fatality=ef, property=ep, noise=rn, obstacle=obs, grid=grid)

def build_static_env_tensor(sc, alt=50.0):
    """构建静态风险 EnvTensor（时间平均，用于 Static A* 基线）。"""
    et = build_env_tensor(sc, alt)
    nx, ny, nz, nt = et.p_crash.shape

    # 时间平均
    pc_avg = np.mean(et.p_crash, axis=3, keepdims=True)
    pc_avg = np.broadcast_to(pc_avg, (nx, ny, nz, nt)).astype(np.float32)

    fat_avg = np.mean(et.fatality, axis=3, keepdims=True)
    fat_avg = np.broadcast_to(fat_avg, (nx, ny, nz, nt)).astype(np.float32)

    # property 已经是静态的
    prop = et.property

    noise_avg = np.mean(et.noise, axis=3, keepdims=True)
    noise_avg = np.broadcast_to(noise_avg, (nx, ny, nz, nt)).astype(np.float32)

    obs = et.obstacle

    return EnvTensor(p_crash=pc_avg, fatality=fat_avg, property=prop,
                     noise=noise_avg, obstacle=obs, grid=sc["grid"])

# ============================================================
# 算法封装
# ============================================================

def run_td_riska_star(grid, et, start, goal, config_override=None):
    """TD-RiskA*（完整时间依赖版本）。"""
    config = {
        "uav_speed": 10.0, "w_distance": 0.40, "w_fatality": 0.30,
        "w_property": 0.15, "w_noise": 0.15, "survival_threshold": 0.01,
        "max_battery_time": float("inf"), "max_iterations": 2_000_000,
        "max_labels_per_cell": 8, "max_climb_rate": 5.0, "max_descent_rate": 5.0,
    }
    if config_override:
        config.update(config_override)
    planner = AStar4D(grid, et, config)
    t0 = time.time()
    result = planner.search(start, goal)
    result["runtime_ms"] = (time.time() - t0) * 1000
    result["algorithm"] = "TD-RiskA*"
    return result

def run_static_astar(grid, et_static, start, goal, config_override=None):
    """Static A* 基线：使用时间平均风险场，不随时间变化。"""
    config = {
        "uav_speed": 10.0, "w_distance": 0.40, "w_fatality": 0.30,
        "w_property": 0.15, "w_noise": 0.15, "survival_threshold": 0.01,
        "max_battery_time": float("inf"), "max_iterations": 2_000_000,
        "max_labels_per_cell": 8, "max_climb_rate": 5.0, "max_descent_rate": 5.0,
    }
    if config_override:
        config.update(config_override)
    planner = AStar4D(grid, et_static, config)
    t0 = time.time()
    result = planner.search(start, goal)
    result["runtime_ms"] = (time.time() - t0) * 1000
    result["algorithm"] = "Static A*"
    return result

def run_distance_only(grid, et, start, goal):
    """Distance-only A* 基线：只优化距离，不考虑风险。"""
    config = {
        "uav_speed": 10.0, "w_distance": 1.0, "w_fatality": 0.0,
        "w_property": 0.0, "w_noise": 0.0, "survival_threshold": 0.0,
        "max_battery_time": float("inf"), "max_iterations": 2_000_000,
        "max_labels_per_cell": 8, "max_climb_rate": 5.0, "max_descent_rate": 5.0,
    }
    planner = AStar4D(grid, et, config)
    t0 = time.time()
    result = planner.search(start, goal)
    result["runtime_ms"] = (time.time() - t0) * 1000
    result["algorithm"] = "Distance-only"
    return result

# ============================================================
# OD 对定义
# ============================================================

@dataclass
class ODPair:
    name: str
    start: Tuple[int, int, int, int]  # (x, y, z, t)
    goal: Tuple[int, int, int]
    desc: str
    category: str  # "short", "medium", "long", "diagonal", "cross_risk"

def get_od_pairs(grid) -> List[ODPair]:
    """多组 OD 对，覆盖不同路径场景。"""
    nx, ny = grid.spatial.nx, grid.spatial.ny
    return [
        # 短距离
        ODPair("short_NS", (30, 10, 5, 12), (30, 25, 5), "短距离 南→北", "short"),
        ODPair("short_EW", (10, 30, 5, 12), (25, 30, 5), "短距离 西→东", "short"),
        # 中距离
        ODPair("med_diag", (10, 10, 5, 12), (50, 50, 5), "中距离 对角线", "medium"),
        ODPair("med_cross", (5, 30, 5, 12), (55, 30, 5), "中距离 穿越中心", "medium"),
        # 长距离
        ODPair("long_diag", (2, 2, 5, 12), (57, 57, 5), "长距离 对角线（原版OD）", "long"),
        ODPair("long_NS", (30, 2, 5, 12), (30, 57, 5), "长距离 南→北", "long"),
        # 穿越高风险区
        ODPair("cross_wind", (20, 30, 5, 15), (40, 30, 5), "穿越风场热点（15时）", "cross_risk"),
        ODPair("cross_rain", (20, 30, 5, 17), (40, 30, 5), "穿越降雨热点（17时）", "cross_risk"),
        # 不同出发时刻
        ODPair("night_depart", (2, 2, 5, 22), (57, 57, 5), "夜间出发", "temporal"),
        ODPair("noon_depart", (2, 2, 5, 12), (57, 57, 5), "午间出发", "temporal"),
    ]

# ============================================================
# 实验 1：基线对比
# ============================================================

def run_baseline_comparison(grid, et, et_static, ods):
    """三种算法在多 OD 对上的对比。"""
    print("\n" + "=" * 60)
    print("Experiment A: Baseline Algorithm Comparison")
    print("=" * 60)

    results = []
    for od in ods:
        print(f"\n  {od.name}: {od.desc}")
        r_td = run_td_riska_star(grid, et, od.start, od.goal)
        r_static = run_static_astar(grid, et_static, od.start, od.goal)
        r_dist = run_distance_only(grid, et, od.start, od.goal)

        for r, label in [(r_td, "TD-RiskA*"), (r_static, "Static A*"), (r_dist, "Distance-only")]:
            if r["status"] == "success":
                print(f"    {label:15s}: dist={r['total_distance']:7.1f}m  "
                      f"J={r['objective_cost']:.4f}  surv={r['final_p_survival']:.6f}  "
                      f"fatality={r['cum_fatality']:.8f}  noise={r['cum_noise']:.6f}  "
                      f"time={r['runtime_ms']:.0f}ms  nodes={r['nodes_explored']}")
            else:
                print(f"    {label:15s}: FAILED ({r.get('reason', '?')})")

            results.append({
                "od": od.name, "category": od.category, "algorithm": label,
                "status": r["status"],
                "path_length": r.get("total_distance", float("inf")),
                "objective_cost": r.get("objective_cost", float("inf")),
                "final_survival": r.get("final_p_survival", 0.0),
                "cum_fatality": r.get("cum_fatality", 0.0),
                "cum_noise": r.get("cum_noise", 0.0),
                "runtime_ms": r.get("runtime_ms", 0),
                "nodes_explored": r.get("nodes_explored", 0),
            })

    return results

# ============================================================
# 实验 2：参数敏感性分析
# ============================================================

def run_sensitivity_analysis(grid, et, base_od):
    """关键参数敏感性扫描。"""
    print("\n" + "=" * 60)
    print("Experiment B: Parameter Sensitivity Analysis")
    print("=" * 60)

    results = []

    # B1: 存活阈值 P_th
    print("\n  --- B1: Survival Threshold P_th ---")
    for p_th in [0.0, 0.001, 0.01, 0.05, 0.10, 0.20, 0.50]:
        r = run_td_riska_star(grid, et, base_od.start, base_od.goal,
                              {"survival_threshold": p_th})
        st = f"dist={r['total_distance']:.1f}m J={r['objective_cost']:.4f} surv={r['final_p_survival']:.6f}" if r["status"] == "success" else r["status"]
        print(f"    P_th={p_th:.3f}: {st}  nodes={r.get('nodes_explored',0)}  time={r.get('runtime_ms',0):.0f}ms")
        results.append({"param": "P_th", "value": p_th, "status": r["status"],
                        "path_length": r.get("total_distance", 0), "objective_cost": r.get("objective_cost", 0),
                        "final_survival": r.get("final_p_survival", 0), "runtime_ms": r.get("runtime_ms", 0),
                        "nodes_explored": r.get("nodes_explored", 0)})

    # B2: w_fatality 权重
    print("\n  --- B2: w_fatality Weight ---")
    for w_f in [0.0, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90]:
        w_total = 0.40 + w_f + 0.15 + 0.15  # w_d + w_f + w_p + w_n
        w_d = max(0, 1.0 - w_f - 0.15 - 0.15)
        r = run_td_riska_star(grid, et, base_od.start, base_od.goal,
                              {"w_fatality": w_f, "w_distance": w_d})
        st = f"dist={r['total_distance']:.1f}m surv={r['final_p_survival']:.6f} fatality={r['cum_fatality']:.8f}" if r["status"] == "success" else r["status"]
        print(f"    w_f={w_f:.2f}: {st}")
        results.append({"param": "w_fatality", "value": w_f, "status": r["status"],
                        "path_length": r.get("total_distance", 0), "objective_cost": r.get("objective_cost", 0),
                        "final_survival": r.get("final_p_survival", 0), "cum_fatality": r.get("cum_fatality", 0),
                        "runtime_ms": r.get("runtime_ms", 0)})

    # B3: w_noise 权重
    print("\n  --- B3: w_noise Weight ---")
    for w_n in [0.0, 0.05, 0.10, 0.15, 0.30, 0.50, 0.70]:
        w_d = max(0, 1.0 - 0.30 - 0.15 - w_n)
        r = run_td_riska_star(grid, et, base_od.start, base_od.goal,
                              {"w_noise": w_n, "w_distance": w_d})
        st = f"dist={r['total_distance']:.1f}m noise={r['cum_noise']:.6f}" if r["status"] == "success" else r["status"]
        print(f"    w_n={w_n:.2f}: {st}")
        results.append({"param": "w_noise", "value": w_n, "status": r["status"],
                        "path_length": r.get("total_distance", 0), "cum_noise": r.get("cum_noise", 0),
                        "runtime_ms": r.get("runtime_ms", 0)})

    # B4: UAV 速度
    print("\n  --- B4: UAV Speed ---")
    for spd in [5.0, 10.0, 15.0, 20.0, 30.0]:
        r = run_td_riska_star(grid, et, base_od.start, base_od.goal,
                              {"uav_speed": spd})
        st = f"dist={r['total_distance']:.1f}m surv={r['final_p_survival']:.6f} time={r.get('runtime_ms',0):.0f}ms" if r["status"] == "success" else r["status"]
        print(f"    v={spd:.0f}m/s: {st}")
        results.append({"param": "uav_speed", "value": spd, "status": r["status"],
                        "path_length": r.get("total_distance", 0), "final_survival": r.get("final_p_survival", 0),
                        "runtime_ms": r.get("runtime_ms", 0)})

    return results

# ============================================================
# 实验 3：统计显著性（多次运行）
# ============================================================

def run_statistical_significance(grid, et, ods, n_runs=5):
    """多次运行验证结果稳定性。"""
    print("\n" + "=" * 60)
    print(f"Experiment C: Statistical Significance ({n_runs} runs)")
    print("=" * 60)

    results = []
    for od in ods:
        print(f"\n  {od.name}:")
        metrics_list = []
        for run_idx in range(n_runs):
            r = run_td_riska_star(grid, et, od.start, od.goal)
            if r["status"] == "success":
                metrics_list.append({
                    "path_length": r["total_distance"],
                    "objective_cost": r["objective_cost"],
                    "final_survival": r["final_p_survival"],
                    "cum_fatality": r["cum_fatality"],
                    "runtime_ms": r["runtime_ms"],
                    "nodes_explored": r["nodes_explored"],
                })

        if metrics_list:
            for key in ["path_length", "objective_cost", "final_survival", "runtime_ms"]:
                vals = [m[key] for m in metrics_list]
                mean_v = np.mean(vals)
                std_v = np.std(vals)
                print(f"    {key:18s}: {mean_v:.6f} ± {std_v:.6f}")
                results.append({"od": od.name, "metric": key, "mean": mean_v, "std": std_v, "n": len(vals)})

    return results

# ============================================================
# 实验 4：计算复杂度 Scaling
# ============================================================

def run_scaling_analysis():
    """不同网格规模的运行时间 scaling。"""
    print("\n" + "=" * 60)
    print("Experiment D: Computational Scaling")
    print("=" * 60)

    results = []
    # 不同网格尺寸
    configs = [
        (20, 20, 6, 12, "20×20×6×12"),
        (30, 30, 8, 12, "30×30×8×12"),
        (40, 40, 10, 12, "40×40×10×12"),
        (60, 60, 12, 24, "60×60×12×24"),
    ]

    for nx, ny, nz, nt, label in configs:
        print(f"\n  Grid: {label} ({nx*ny*nz*nt:,} cells)")
        grid = GridSystem(
            spatial=SpatialGridConfig(nx=nx, ny=ny, nz=nz, dx=10.0, dy=10.0, dz=10.0),
            temporal=TemporalGridConfig(nt=nt, dt_minutes=60.0),
        )
        city = generate_synthetic_city(nx=nx, ny=ny, nz=nz, nt=nt, seed=42)

        # 简化构建
        landuse = city["landuse"].astype(np.int32)
        bh = city["building_heights"].astype(np.float32)
        wind = city["wind_field"].astype(np.float32)
        rain = city["rain_data"].astype(np.float32)

        # 注入风场
        cy, cx = ny // 2, nx // 2
        yy, xx = np.mgrid[0:ny, 0:nx]
        dsq = (xx - cx)**2 + (yy - cy)**2
        hs = np.exp(-dsq / (2 * 8**2))
        for t in range(nt):
            f = 8.0 if 12<=t<=18 else (4.0 if 6<=t<=11 else 1.0)
            for iz in range(nz): wind[:,:,iz,t] += hs * f

        lu_t = np.transpose(landuse, (1,0))
        bp = np.transpose(city["population"].astype(np.float32), (1,0))
        rp = np.zeros((nx,ny,nt), dtype=np.float32)
        for t in range(nt):
            p = bp.copy()
            if 8<=t<=18: p[lu_t==2]*=5.0
            else: p[lu_t==2]*=0.1
            if 22<=t or t<=6: p[lu_t==1]*=4.0
            elif 9<=t<=17: p[lu_t==1]*=0.2
            rp[:,:,t] = p

        cm = DynamicCrashProbability()
        w2d = np.transpose(wind[:,:,0,:], (1,0,2))
        r2d = np.transpose(rain, (1,0,2))
        fw = cm.compute_wind_factor(w2d[:,:,np.newaxis,:])
        fr = cm.compute_rain_factor(r2d[:,:,np.newaxis,:])
        fo = np.ones((nx,ny,nz,nt), dtype=np.float32)
        pc = np.clip(cm.compute_pcrash(fw,fr,fo,dt=3600.0),0,1).astype(np.float32)

        rv = rp*0.1
        fm = DynamicFatalityModel()
        ef3d = fm.compute_fatality_consequence(rho_pop=rp, rho_vehicle=rv, flight_altitude=50.0)
        ef = np.broadcast_to(ef3d[:,:,np.newaxis,:], (nx,ny,nz,nt)).astype(np.float32)

        bt = np.transpose(bh, (1,0))
        pm = PropertyDamageModel(building_heights=bt, max_prop_damage=1000.0, log_normal_mu=3.04, log_normal_sigma=0.5)
        ep = pm.compute_property_consequence(flight_altitude=50.0).astype(np.float32)

        nm = DynamicNoiseCost(grid=grid)
        rn = nm.compute_noise_cost(landuse=lu_t, population_density=rp).astype(np.float32)

        obs = np.zeros((nx,ny,nz), dtype=np.float32)
        for iz in range(nz): obs[:,:,iz] = (bt>=(iz+1.0)*grid.spatial.dz).astype(np.float32)

        et = EnvTensor(p_crash=pc, fatality=ef, property=ep, noise=rn, obstacle=obs, grid=grid)

        # 对角线 OD
        z_level = min(nz//2, nz-1)
        t_start = min(12, nt-1)  # 确保 t 不越界
        start = (2, 2, z_level, t_start)
        goal = (nx-3, ny-3, z_level)
        r = run_td_riska_star(grid, et, start, goal)

        if r["status"] == "success":
            print(f"    dist={r['total_distance']:.1f}m  J={r['objective_cost']:.4f}  "
                  f"nodes={r['nodes_explored']}  time={r['runtime_ms']:.0f}ms")
        else:
            print(f"    FAILED")

        results.append({"grid": label, "cells": nx*ny*nz*nt, "status": r["status"],
                        "path_length": r.get("total_distance", 0),
                        "nodes_explored": r.get("nodes_explored", 0),
                        "runtime_ms": r.get("runtime_ms", 0)})

    return results

# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print("Micro-Scale Comprehensive Experiment Suite")
    print("=" * 60)

    # 1. 构建场景
    print("\n[Setup] Building scenario...")
    sc = build_micro_scenario()
    grid = sc["grid"]
    print(f"  Grid: {grid.shape}")

    print("[Setup] Building dynamic EnvTensor...")
    et = build_env_tensor(sc)
    print(f"  P_crash range: [{et.p_crash.min():.6f}, {et.p_crash.max():.6f}]")

    print("[Setup] Building static EnvTensor...")
    et_static = build_static_env_tensor(sc)

    ods = get_od_pairs(grid)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ===== A: 基线对比 =====
    baseline_results = run_baseline_comparison(grid, et, et_static, ods)

    # ===== B: 参数敏感性 =====
    sensitivity_results = run_sensitivity_analysis(grid, et, ods[4])  # 用 long_diag OD

    # ===== C: 统计显著性 =====
    stat_results = run_statistical_significance(grid, et, ods, n_runs=5)

    # ===== D: 计算 Scaling =====
    scaling_results = run_scaling_analysis()

    # ===== 保存所有结果 =====
    def save_csv(filename, data, header):
        lines = [",".join(header)]
        for d in data:
            lines.append(",".join(str(d.get(h, "")) for h in header))
        (OUTPUT_DIR / filename).write_text("\n".join(lines), encoding="utf-8")
        print(f"  Saved: {OUTPUT_DIR / filename}")

    save_csv("baseline_comparison.csv", baseline_results,
             ["od", "category", "algorithm", "status", "path_length", "objective_cost",
              "final_survival", "cum_fatality", "cum_noise", "runtime_ms", "nodes_explored"])

    save_csv("sensitivity_analysis.csv", sensitivity_results,
             ["param", "value", "status", "path_length", "objective_cost",
              "final_survival", "cum_fatality", "cum_noise", "runtime_ms", "nodes_explored"])

    save_csv("statistical_significance.csv", stat_results,
             ["od", "metric", "mean", "std", "n"])

    save_csv("scaling_analysis.csv", scaling_results,
             ["grid", "cells", "status", "path_length", "nodes_explored", "runtime_ms"])

    print("\n" + "=" * 60)
    print("ALL EXPERIMENTS COMPLETE")
    print(f"Results: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
