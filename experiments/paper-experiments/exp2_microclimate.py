"""
Experiment 2: Microclimate-Terrain Interaction

Core question: Do wind/rain hotspots coupled with building canyons cause path deviation?

Design:
- Fixed OD, fixed time (t=12)
- 3 weather conditions: Calm, Wind Canyon, Heavy Rain
- Compare: Distance-only A* vs TD-RiskA*
"""

from __future__ import annotations

import json
import copy
from pathlib import Path

import numpy as np


from scenario_builder import (
    load_micro_scenario, build_env_tensor, build_planner_config,
    get_primary_od, extract_metrics, apply_wind_hotspot, apply_rain_hotspot,
)

from core.td_risk_astar import AStar4D

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CONDITIONS = {
    "calm": {"label": "Calm (Baseline)", "wind": 0.0, "rain": 0.0},
    "wind": {"label": "Wind Canyon (15 m/s)", "wind": 15.0, "rain": 0.0},
    "rain": {"label": "Heavy Rain (20 mm/h)", "wind": 0.0, "rain": 20.0},
}
CONDITION_COLORS = {"calm": "#2ECC71", "wind": "#E74C3C", "rain": "#3498DB"}

OUTPUT_DIR = Path(__file__).resolve().parent / "results" / "exp2_microclimate"
T_START = 12

def run_experiment():
    print("=" * 60)
    print("Experiment 2: Microclimate-Terrain Interaction")
    print("=" * 60)

    print("\n[1/4] Loading base scenario...")
    base_scenario = load_micro_scenario()
    grid = base_scenario.grid
    start, goal = get_primary_od(grid)

    print("\n[2/4] Building risk tensors for 3 conditions...")
    all_results = {}
    all_metrics = []

    for cond_key, cond_info in CONDITIONS.items():
        print("\n  === {} ===".format(cond_info["label"]))

        scenario = copy.deepcopy(base_scenario)

        if cond_info["wind"] > 0:
            cy, cx = scenario.wind_field.shape[0] // 2, scenario.wind_field.shape[1] // 2
            scenario.wind_field = apply_wind_hotspot(scenario.wind_field, (cy, cx), 8, cond_info["wind"])

        if cond_info["rain"] > 0:
            cy, cx = scenario.rain_data.shape[0] // 2, scenario.rain_data.shape[1] // 2
            scenario.rain_data = apply_rain_hotspot(scenario.rain_data, (cy, cx), 10, cond_info["rain"])

        env_tensor = build_env_tensor(scenario)

        # Distance-only A*
        print("    Distance-only A*...")
        config_dist = build_planner_config("default")
        config_dist["w_fatality"] = 0.0
        config_dist["w_property"] = 0.0
        config_dist["w_noise"] = 0.0
        config_dist["w_distance"] = 1.0
        planner_dist = AStar4D(grid, env_tensor, config_dist)
        result_dist = planner_dist.search((start[0], start[1], start[2], T_START), goal)
        all_results[(cond_key, "distance_only")] = result_dist
        m = extract_metrics(result_dist)
        m["condition"] = cond_key
        m["algorithm"] = "distance_only"
        all_metrics.append(m)
        print("      {} dist={:.1f}m surv={:.6f}".format(m["status"], m["path_length"], m["final_survival"]))

        # TD-RiskA*
        print("    TD-RiskA*...")
        config_risk = build_planner_config("default")
        planner_risk = AStar4D(grid, env_tensor, config_risk)
        result_risk = planner_risk.search((start[0], start[1], start[2], T_START), goal)
        all_results[(cond_key, "td_risk")] = result_risk
        m = extract_metrics(result_risk)
        m["condition"] = cond_key
        m["algorithm"] = "td_risk"
        all_metrics.append(m)
        print("      {} dist={:.1f}m surv={:.6f}".format(m["status"], m["path_length"], m["final_survival"]))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _save_metrics_csv(all_metrics)
    _plot_paths_comparison(all_results, base_scenario)
    _plot_metrics_table(all_metrics)

    print("\n[OK] Experiment 2 complete! Results: {}".format(OUTPUT_DIR))
    return all_results, all_metrics

def _save_metrics_csv(all_metrics):
    csv_path = OUTPUT_DIR / "metrics.csv"
    header = "condition,algorithm,status,path_length,final_survival,cum_fatality,cum_property,cum_noise,objective_cost,runtime_ms,nodes_explored"
    lines = [header]
    for m in all_metrics:
        lines.append("{},{},{},{:.4f},{:.6f},{:.8f},{:.8f},{:.6f},{:.6f},{:.1f},{}".format(
            m["condition"], m["algorithm"], m["status"],
            m["path_length"], m["final_survival"],
            m["cum_fatality"], m["cum_property"],
            m["cum_noise"], m["objective_cost"],
            m["runtime_ms"], m["nodes_explored"],
        ))
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    print("  [OK] Saved: {}".format(csv_path))

def _plot_paths_comparison(all_results, scenario):
    fig, axes = plt.subplots(1, 3, figsize=(20, 7), facecolor="white")

    for idx, (cond_key, cond_info) in enumerate(CONDITIONS.items()):
        ax = axes[idx]
        bh = scenario.building_heights
        ax.imshow(bh, cmap="YlOrRd", origin="lower", alpha=0.5, interpolation="bilinear")

        for algo_key, algo_label in [("distance_only", "Distance-only"), ("td_risk", "TD-RiskA*")]:
            result = all_results.get((cond_key, algo_key))
            if result is None or result["status"] != "success":
                continue
            path = result["path"]
            xs = [step["coords"][0] for step in path]
            ys = [step["coords"][1] for step in path]
            style = "--" if algo_key == "distance_only" else "-"
            lw = 2 if algo_key == "distance_only" else 2.5
            ax.plot(xs, ys, color=CONDITION_COLORS[cond_key], linestyle=style, linewidth=lw, label=algo_label, alpha=0.85)

        ax.scatter(2, 2, color="green", s=120, marker="o", edgecolors="black", zorder=5)
        ax.scatter(37, 37, color="red", s=120, marker="*", edgecolors="black", zorder=5)
        ax.set_title(cond_info["label"], fontsize=13, fontweight="bold")
        ax.set_xlabel("X", fontsize=10)
        ax.set_ylabel("Y", fontsize=10)
        ax.legend(fontsize=9, loc="upper left")

    fig.suptitle("Exp2: Microclimate-Terrain Path Comparison", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_paths_comparison.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  [OK] Saved: fig_paths_comparison.png")

def _plot_metrics_table(all_metrics):
    fig, ax = plt.subplots(figsize=(14, 5), facecolor="white")
    ax.axis("off")

    headers = ["Condition", "Algorithm", "Path(m)", "Survival", "Fatality", "Noise", "Runtime(ms)"]
    rows = []
    for m in all_metrics:
        rows.append([
            m["condition"], m["algorithm"],
            "{:.1f}".format(m["path_length"]) if m["status"] == "success" else "N/A",
            "{:.6f}".format(m["final_survival"]) if m["status"] == "success" else "N/A",
            "{:.8f}".format(m["cum_fatality"]) if m["status"] == "success" else "N/A",
            "{:.4f}".format(m["cum_noise"]) if m["status"] == "success" else "N/A",
            "{:.1f}".format(m["runtime_ms"]),
        ])

    table = ax.table(cellText=rows, colLabels=headers, cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.5)
    for j in range(len(headers)):
        table[0, j].set_facecolor("#2C3E50")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(len(rows)):
        for j in range(len(headers)):
            if i % 2 == 0:
                table[i + 1, j].set_facecolor("#ECF0F1")

    ax.set_title("Exp2: Microclimate-Terrain - Metrics", fontsize=13, fontweight="bold", pad=20)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_metrics_table.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  [OK] Saved: fig_metrics_table.png")

if __name__ == "__main__":
    run_experiment()
