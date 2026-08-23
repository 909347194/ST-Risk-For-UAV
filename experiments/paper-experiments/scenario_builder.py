"""
Scenario Builder for EXP1 Experiments.

Handles:
1. Generate synthetic data matching the micro grid dimensions
2. Build risk tensors and EnvTensor
3. Provide OD pairs, weight presets, and utility functions
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


from core.grid_system import (
    GridSystem, SpatialGridConfig, TemporalGridConfig,
)
# EasyDict not needed
from core.p_crash import (
    DynamicCrashProbability,
)
from core.fatality import (
    DynamicFatalityModel,
)
from core.property import (
    PropertyDamageModel,
)
from core.noise import (
    DynamicNoiseCost,
)
from core.env_tensor import EnvTensor
from core.td_risk_astar import AStar4D


@dataclass
class MicroScenario:
    """Complete data container for micro-scale experiment."""
    landuse: np.ndarray           # (ny, nx) int32
    building_heights: np.ndarray  # (ny, nx) float32
    road_mask: np.ndarray         # (ny, nx) bool
    poi: Dict[str, np.ndarray]    # 5 categories, each (ny, nx) float32
    population: np.ndarray        # (ny, nx) float32
    wind_field: np.ndarray        # (ny, nx, nz, nt) float32
    rain_data: np.ndarray         # (ny, nx, nt) float32
    grid: GridSystem = field(repr=False)
    config_path: str = field(repr=False)


def load_micro_scenario(config_path: Optional[Path] = None) -> MicroScenario:
    """Build micro experiment scenario with temporal dynamics."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "configs" / "common.yaml"

    grid = GridSystem(
        spatial=SpatialGridConfig(nx=40, ny=40, nz=12, dx=10.0, dy=10.0, dz=10.0),
        temporal=TemporalGridConfig(nt=24, dt_minutes=60.0),
    )

    nx, ny, nz, nt = grid.shape

    from core.synthetic import (
        generate_synthetic_city,
    )
    city_data = generate_synthetic_city(nx=nx, ny=ny, nz=nz, nt=nt, seed=42)

    # --- Add temporal dynamics to wind and rain ---
    wind_field = city_data["wind_field"].astype(np.float32)
    rain_data = city_data["rain_data"].astype(np.float32)
    landuse = city_data["landuse"].astype(np.int32)

    # 1. Add wind hotspot at center (stronger during afternoon)
    cy, cx = ny // 2, nx // 2
    yy, xx = np.mgrid[0:ny, 0:nx]
    dist_sq = (xx - cx) ** 2 + (yy - cy) ** 2
    wind_hotspot = np.exp(-dist_sq / (2 * 8 ** 2))  # radius=8 cells

    for t in range(nt):
        hour = t  # 1h per step
        # Wind stronger in afternoon (12-18), calmer at night
        if 12 <= hour <= 18:
            factor = 8.0  # strong wind
        elif 6 <= hour <= 11:
            factor = 4.0  # moderate
        else:
            factor = 1.0  # calm at night
        for iz in range(nz):
            wind_field[:, :, iz, t] += wind_hotspot * factor

    # 2. Add rain hotspot (rain only during 14:00-20:00)
    rain_hotspot = np.exp(-dist_sq / (2 * 10 ** 2))  # radius=10 cells
    for t in range(nt):
        hour = t
        if 14 <= hour <= 20:
            rain_data[:, :, t] += rain_hotspot * 15.0  # 15 mm/h

    return MicroScenario(
        landuse=landuse,
        building_heights=city_data["building_heights"].astype(np.float32),
        road_mask=city_data["road_mask"],
        poi={k: v.astype(np.float32) for k, v in city_data["poi"].items()},
        population=city_data["population"].astype(np.float32),
        wind_field=wind_field,
        rain_data=rain_data,
        grid=grid,
        config_path=str(config_path),
    )


def build_env_tensor(scenario: MicroScenario, flight_altitude: float = 50.0) -> EnvTensor:
    """Build EnvTensor with mass-conservative tidal population dynamics."""
    grid = scenario.grid
    nx, ny, nz, nt = grid.shape
    config_path = scenario.config_path
    landuse = scenario.landuse

    # 1. P_crash(x,y,z,t)
    crash_model = DynamicCrashProbability(config_path=config_path)

    wind_2d = scenario.wind_field[:, :, 0, :]  # (ny, nx, nt)
    rain_2d = scenario.rain_data                # (ny, nx, nt)
    wind_2d = np.transpose(wind_2d, (1, 0, 2))  # -> (nx, ny, nt)
    rain_2d = np.transpose(rain_2d, (1, 0, 2))

    wind_3d = wind_2d[:, :, np.newaxis, :]  # (nx, ny, 1, nt)
    rain_3d = rain_2d[:, :, np.newaxis, :]

    f_wind = crash_model.compute_wind_factor(wind_3d)
    f_rain = crash_model.compute_rain_factor(rain_3d)
    f_obs = np.ones((nx, ny, nz, nt), dtype=np.float32)

    p_crash = crash_model.compute_pcrash(f_wind, f_rain, f_obs, dt=grid.temporal.dt_minutes * 60.0)
    p_crash = np.clip(p_crash, 0.0, 1.0).astype(np.float32)

    # 2. Mass-conservative tidal population density
    #    Uses POI Huff gravity + Partition of Unity activation
    base_pop = np.transpose(scenario.population, (1, 0))  # (ny,nx) -> (nx,ny)
    landuse_t = np.transpose(landuse, (1, 0))  # (ny,nx) -> (nx,ny)

    from core.tidal import (
        SpatiotemporalTidalModel, TidalModelConfig,
    )
    from core.poi_parser import create_synthetic_poi_counts

    poi_counts = create_synthetic_poi_counts(grid=grid, landuse=landuse_t, save=False)

    # Estimate N_total from base population (integral of density over area)
    S_cell = grid.spatial.dx * grid.spatial.dy
    N_total_pop = float(np.sum(base_pop)) * S_cell
    N_total_veh = N_total_pop * 0.3  # vehicles ~ 30% of population

    tidal_config = TidalModelConfig(
        N_total_pop=max(N_total_pop, 1000.0),
        N_total_veh=max(N_total_veh, 500.0),
    )
    tidal_model = SpatiotemporalTidalModel(grid=grid, config=tidal_config)

    # Build mass-conservative population density rho_pop(x, y, t)
    rho_pop_3d = tidal_model.build_population_density(base_pop, poi_counts)  # (nx, ny, nt)

    # Build mass-conservative traffic density rho_vehicle(x, y, t)
    rho_vehicle_3d = tidal_model.build_vehicle_density(base_pop, poi_counts)  # (nx, ny, nt)

    # 3. E_fatality(x,y,z,t) - with dynamic population
    fatality_model = DynamicFatalityModel(config_path=config_path)
    e_fatality_3d = fatality_model.compute_fatality_consequence(
        rho_pop=rho_pop_3d, rho_vehicle=rho_vehicle_3d, flight_altitude=flight_altitude,
    )
    e_fatality = np.broadcast_to(e_fatality_3d[:, :, np.newaxis, :], (nx, ny, nz, nt)).astype(np.float32)

    # 4. E_property(x,y)
    building_t = np.transpose(scenario.building_heights, (1, 0))
    prop_model = PropertyDamageModel(
        building_heights=building_t,
        max_prop_damage=1000.0, log_normal_mu=3.04, log_normal_sigma=0.5,
    )
    e_property = prop_model.compute_property_consequence(flight_altitude=flight_altitude).astype(np.float32)

    # 5. R_noise(x,y,z,t) - with dynamic population
    noise_model = DynamicNoiseCost(grid=grid, config_path=config_path)
    r_noise = noise_model.compute_noise_cost(
        landuse=landuse_t,
        population_density=rho_pop_3d,  # (nx, ny, nt) dynamic
    ).astype(np.float32)

    # 6. Obstacle mask
    obstacle = np.zeros((nx, ny, nz), dtype=np.float32)
    for iz in range(nz):
        z_height = (iz + 1.0) * grid.spatial.dz
        obstacle[:, :, iz] = (building_t >= z_height).astype(np.float32)

    return EnvTensor(
        p_crash=p_crash, fatality=e_fatality, property=e_property,
        noise=r_noise, obstacle=obstacle, grid=grid,
    )


def get_primary_od(grid: GridSystem, z_level: int = 5):
    """Get primary test OD pair: SW corner -> NE corner."""
    start = (2, 2, z_level, 0)
    goal = (grid.spatial.nx - 3, grid.spatial.ny - 3, z_level)
    return start, goal


def get_weight_presets() -> Dict[str, Dict[str, float]]:
    """Return 4 weight presets."""
    return {
        "default": {"w_distance": 0.4, "w_fatality": 0.3, "w_property": 0.15, "w_noise": 0.15},
        "emergency": {"w_distance": 0.8, "w_fatality": 0.1, "w_property": 0.05, "w_noise": 0.05},
        "quiet_night": {"w_distance": 0.2, "w_fatality": 0.2, "w_property": 0.1, "w_noise": 0.5},
        "strict_safety": {"w_distance": 0.0, "w_fatality": 0.7, "w_property": 0.2, "w_noise": 0.1},
    }


def build_planner_config(
    weight_preset: str = "default",
    max_labels_per_cell: int = 8,
    survival_threshold: float = 0.01,
) -> Dict[str, Any]:
    """Build AStar4D config dict."""
    presets = get_weight_presets()
    weights = presets.get(weight_preset, presets["default"])

    return {
        "uav_speed": 10.0,
        "w_distance": weights["w_distance"],
        "w_fatality": weights["w_fatality"],
        "w_property": weights["w_property"],
        "w_noise": weights["w_noise"],
        "survival_threshold": survival_threshold,
        "max_battery_time": float("inf"),
        "max_iterations": 500_000,
        "max_labels_per_cell": max_labels_per_cell,
        "max_climb_rate": 5.0,
        "max_descent_rate": 5.0,
    }


def apply_wind_hotspot(wind_field, center, radius, max_speed):
    """Add Gaussian wind speed hotspot."""
    ny, nx, nz, nt = wind_field.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    dist_sq = (xx - center[1]) ** 2 + (yy - center[0]) ** 2
    hotspot = max_speed * np.exp(-dist_sq / (2 * radius ** 2))
    for iz in range(nz):
        for it in range(nt):
            wind_field[:, :, iz, it] += hotspot
    return wind_field


def apply_rain_hotspot(rain_data, center, radius, max_intensity):
    """Add Gaussian rainfall hotspot."""
    ny, nx, nt = rain_data.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    dist_sq = (xx - center[1]) ** 2 + (yy - center[0]) ** 2
    hotspot = max_intensity * np.exp(-dist_sq / (2 * radius ** 2))
    for it in range(nt):
        rain_data[:, :, it] += hotspot
    return rain_data


def extract_metrics(result: Dict[str, Any]) -> Dict[str, float]:
    """Extract metrics from search result."""
    if result["status"] != "success":
        return {
            "status": result["status"],
            "reason": result.get("reason", "N/A"),
            "path_length": float("inf"),
            "final_survival": 0.0,
            "cum_fatality": float("inf"),
            "cum_property": float("inf"),
            "cum_noise": float("inf"),
            "objective_cost": float("inf"),
            "runtime_ms": result.get("time_cost", 0) * 1000,
            "nodes_explored": result.get("nodes_explored", 0),
        }

    return {
        "status": "success",
        "reason": "N/A",
        "path_length": result["total_distance"],
        "final_survival": result["final_p_survival"],
        "cum_fatality": result["cum_fatality"],
        "cum_property": result["cum_property"],
        "cum_noise": result["cum_noise"],
        "objective_cost": result["objective_cost"],
        "runtime_ms": result["time_cost"] * 1000,
        "nodes_explored": result["nodes_explored"],
    }


def extract_path_along_metric(result, metric_key):
    """Extract cumulative distance-metric curve along path."""
    if result["status"] != "success":
        return [], []

    distances = [0.0]
    values = [0.0]

    for step in result["path"]:
        state = step["state"]
        distances.append(state["cum_distance"])
        values.append(state.get(metric_key, 0.0))

    return distances, values
