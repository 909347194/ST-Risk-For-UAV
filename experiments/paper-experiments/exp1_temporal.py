"""
Experiment 1: Temporal Adaptability

Core question: Does the same OD pair produce different paths at different departure times?

Design:
- Fixed OD: SW corner -> NE corner
- 4 departure times: t in {8, 12, 18, 22}
- Algorithm: TD-RiskA* (full risk)
- Weight: default preset

Expected:
- 08:00: Avoid transport POI hotspots (commute)
- 12:00: Avoid institution POI areas (school/hospital)
- 18:00: Avoid office->residential commute corridors
- 22:00: Strongly avoid residential areas (night noise penalty x10)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


from scenario_builder import (
    load_micro_scenario, build_env_tensor, build_planner_config,
    get_primary_od, extract_metrics, extract_path_along_metric,
)

from core.td_risk_astar import AStar4D

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TIME_SLOTS = [8, 12, 18, 22]
TIME_LABELS = {8: "08:00 (Morning Rush)", 12: "12:00 (Noon)", 18: "18:00 (Evening Rush)", 22: "22:00 (Night)"}
TIME_COLORS = {8: "#E74C3C", 12: "#F39C12", 18: "#3498DB", 22: "#8E44AD"}

OUTPUT_DIR = Path(__file__).resolve().parent / "results" / "exp1_temporal"

def run_experiment():
    print("=" * 60)
    print("Experiment 1: Temporal Adaptability")
    print("=" * 60)

    print("\n[1/4] Loading micro scenario...")
    scenario = load_micro_scenario()
    print("  Grid: {}".format(scenario.grid.shape))

    print("\n[2/4] Building risk tensors...")
    env_tensor = build_env_tensor(scenario)
    print(env_tensor.summary())

    start, goal = get_primary_od(scenario.grid)
    print("\n[3/4] OD pair: start={}, goal={}".format(start, goal))

    print("\n[4/4] Running TD-RiskA* (4 time slots)...")
    results = {}
    all_metrics = []

    for t_start in TIME_SLOTS:
        label = TIME_LABELS[t_start]
        print("\n  --- {} ---".format(label))

        config = build_planner_config("default")
        planner = AStar4D(scenario.grid, env_tensor, config)

        start_with_t = (start[0], start[1], start[2], t_start)
        result = planner.search(start_with_t, goal)

        metrics = extract_metrics(result)
        metrics["t_start"] = t_start
        metrics["label"] = label
        all_metrics.append(metrics)
        results[t_start] = result

        print("    Status: {}".format(metrics["status"]))
        if metrics["status"] == "success":
            print("    Path length: {:.1f} m".format(metrics["path_length"]))
            print("    Survival: {:.6f}".format(metrics["final_survival"]))
            print("    Cum noise: {:.6f}".format(metrics["cum_noise"]))
            print("    Cum fatality: {:.8f}".format(metrics["cum_fatality"]))
            print("    Objective: {:.6f}".format(metrics["objective_cost"]))
            print("    Runtime: {:.1f} ms".format(metrics["runtime_ms"]))
            print("    Nodes: {}".format(metrics["nodes_explored"]))
        else:
            print("    Reason: {}".format(metrics.get("reason", "N/A")))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _save_metrics_csv(all_metrics)
    _save_paths_json(results)

    print("\nGenerating figures...")
    _plot_paths_2d(results, scenario)
    _plot_cumulative_curves(results, scenario)
    _plot_metrics_table(all_metrics)

    print("\n[OK] Experiment 1 complete! Results saved to: {}".format(OUTPUT_DIR))
    return results, all_metrics

def _save_metrics_csv(all_metrics):
    csv_path = OUTPUT_DIR / "metrics.csv"
    header = "t_start,label,status,path_length,final_survival,cum_fatality,cum_property,cum_noise,objective_cost,runtime_ms,nodes_explored"
    lines = [header]
    for m in all_metrics:
        lines.append(
            "{},{},{},{:.4f},{:.6f},{:.8f},{:.8f},{:.6f},{:.6f},{:.1f},{}".format(
                m["t_start"], m["label"], m["status"],
                m["path_length"], m["final_survival"],
                m["cum_fatality"], m["cum_property"],
                m["cum_noise"], m["objective_cost"],
                m["runtime_ms"], m["nodes_explored"],
            )
        )
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    print("  [OK] Saved: {}".format(csv_path))

def _save_paths_json(results):
    paths_data = {}
    for t_start, result in results.items():
        if result["status"] == "success":
            paths_data[str(t_start)] = {
                "coords": [step["coords"] for step in result["path"]],
                "states": [step["state"] for step in result["path"]],
            }
    json_path = OUTPUT_DIR / "paths.json"
    json_path.write_text(json.dumps(paths_data, indent=2), encoding="utf-8")
    print("  [OK] Saved: {}".format(json_path))

def _plot_paths_2d(results, scenario):
    fig, ax = plt.subplots(figsize=(10, 10), facecolor="white")

    bh = scenario.building_heights
    im = ax.imshow(bh, cmap="YlOrRd", origin="lower", alpha=0.6, interpolation="bilinear")
    plt.colorbar(im, ax=ax, shrink=0.7, label="Building Height (layers)")

    for t_start in TIME_SLOTS:
        result = results.get(t_start)
        if result is None or result["status"] != "success":
            continue
        path = result["path"]
        xs = [step["coords"][0] for step in path]
        ys = [step["coords"][1] for step in path]
        color = TIME_COLORS[t_start]
        label = TIME_LABELS[t_start]
        ax.plot(xs, ys, color=color, linewidth=2.5, label=label, alpha=0.9)
        ax.scatter(xs[0], ys[0], color=color, s=100, marker="o", edgecolors="black", zorder=5)
        ax.scatter(xs[-1], ys[-1], color=color, s=100, marker="*", edgecolors="black", zorder=5)

    ax.set_xlabel("X (grid cells)", fontsize=12)
    ax.set_ylabel("Y (grid cells)", fontsize=12)
    ax.set_title("Exp1: Paths at Different Departure Times", fontsize=14, fontweight="bold")
    ax.legend(loc="upper left", fontsize=10, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_paths_2d.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  [OK] Saved: fig_paths_2d.png")

def _plot_cumulative_curves(results, scenario):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="white")

    metrics_to_plot = [
        ("p_survival", "Survival Probability", axes[0, 0]),
        ("cum_noise", "Cumulative Noise Cost", axes[0, 1]),
        ("cum_fatality", "Cumulative Expected Fatality", axes[1, 0]),
        ("cumulative_hazard", "Cumulative Hazard Rate H", axes[1, 1]),
    ]

    for metric_key, title, ax in metrics_to_plot:
        for t_start in TIME_SLOTS:
            result = results.get(t_start)
            if result is None or result["status"] != "success":
                continue
            distances, values = extract_path_along_metric(result, metric_key)
            color = TIME_COLORS[t_start]
            label = TIME_LABELS[t_start]
            ax.plot(distances, values, color=color, linewidth=2, label=label)

        ax.set_xlabel("Cumulative Distance (m)", fontsize=10)
        ax.set_ylabel(title, fontsize=10)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Exp1: Cumulative Metrics Along Path", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_cumulative_curves.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  [OK] Saved: fig_cumulative_curves.png")

def _plot_metrics_table(all_metrics):
    fig, ax = plt.subplots(figsize=(12, 4), facecolor="white")
    ax.axis("off")

    headers = ["Time", "Path(m)", "Survival", "Fatality", "Noise", "Runtime(ms)"]
    rows = []
    for m in all_metrics:
        rows.append([
            m["label"],
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
        table[0, j].set_facecolor("#3498DB")
        table[0, j].set_text_props(color="white", fontweight="bold")

    for i in range(len(rows)):
        for j in range(len(headers)):
            if i % 2 == 0:
                table[i + 1, j].set_facecolor("#ECF0F1")

    ax.set_title("Exp1: Temporal Adaptability - Metrics", fontsize=13, fontweight="bold", pad=20)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fig_metrics_table.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  [OK] Saved: fig_metrics_table.png")

if __name__ == "__main__":
    run_experiment()
