"""
4D A* path planning for the spatiotemporal heterogeneity model.

The planner consumes EnvTensor components from tensor_engine and searches in a
3D grid while advancing the absolute time slice according to physical flight
distance and UAV speed.
"""

from __future__ import annotations

import heapq
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np

from core.grid_system import GridSystem
from core.common import SearchNode
from core.env_tensor import EnvTensor


Coord3D = Tuple[int, int, int]
Coord4D = Tuple[int, int, int, int]


class AStar4D:
    """Risk-aware 4D A* planner for UAV navigation."""

    def __init__(
        self,
        grid: GridSystem,
        env_tensor: EnvTensor,
        config: Optional[Mapping[str, Any]] = None,
    ):
        self.grid = grid
        self.env_tensor = env_tensor
        self.config = config or {}

        self.nx, self.ny, self.nz, self.nt = grid.shape
        if env_tensor.shape != grid.shape:
            raise ValueError(f"EnvTensor shape {env_tensor.shape} does not match grid shape {grid.shape}")

        self.dx = float(grid.spatial.dx)
        self.dy = float(grid.spatial.dy)
        self.dz = float(grid.spatial.dz)

        self.uav_speed = float(self._cfg("uav_speed", "flight_parameters.cruise_speed", default=10.0))
        if self.uav_speed <= 0:
            raise ValueError("uav_speed must be positive")

        default_dt = float(grid.temporal.dt_minutes) * 60.0
        self.time_resolution = float(self._cfg("time_resolution", "time.dt", default=default_dt))
        if self.time_resolution <= 0:
            raise ValueError("time_resolution must be positive")

        self.w_fatality = float(self._cfg("w_fatality", "w_fatal", "default.w_fatal", default=1.0))
        self.w_property = float(self._cfg("w_property", "w_prop", "default.w_prop", default=1.0))
        self.w_noise = float(self._cfg("w_noise", "default.w_noise", default=1.0))
        self.w_distance = float(self._cfg("w_distance", "w_ops", "default.w_ops", default=0.4))

        # --- Normalization constants (论文 §3.4 单步无量纲化) ---
        # Omega_f = max(E_fatality), Omega_p = max(E_property), Omega_n = max(R_noise)
        # d_max = diagonal of one voxel
        self.d_max = float(np.sqrt(self.dx**2 + self.dy**2 + self.dz**2))
        self.omega_fatality = float(np.max(env_tensor.fatality)) if np.max(env_tensor.fatality) > 0 else 1.0
        self.omega_property = float(np.max(env_tensor.property)) if np.max(env_tensor.property) > 0 else 1.0
        self.omega_noise = float(np.max(env_tensor.noise)) if np.max(env_tensor.noise) > 0 else 1.0

        self.survival_threshold = float(self._cfg("survival_threshold", default=0.0))
        self.max_battery_time = float(self._cfg("max_battery_time", default=np.inf))
        self.max_iterations = int(self._cfg("max_iterations", default=1_000_000))
        self.max_labels_per_cell = int(self._cfg("max_labels_per_cell", default=8))

        self.max_climb_rate = self._optional_float(
            self._cfg("max_climb_rate", "flight_parameters.uav_constraints.max_climb_rate", default=None)
        )
        self.max_descent_rate = self._optional_float(
            self._cfg("max_descent_rate", "flight_parameters.uav_constraints.max_descent_rate", default=None)
        )

    def _cfg(self, *paths: str, default: Any = None) -> Any:
        """Read a flat or dotted config value from dict/EasyDict-like objects."""
        for path in paths:
            current: Any = self.config
            found = True
            for part in path.split("."):
                if isinstance(current, Mapping) and part in current:
                    current = current[part]
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    found = False
                    break
            if found:
                return current
        return default

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        return None if value is None else float(value)

    def _heuristic(self, pos: Coord3D, goal: Coord3D) -> float:
        """Admissible distance heuristic normalized by d_max (论文 §5.4 Eq.15)."""
        dist_x = (pos[0] - goal[0]) * self.dx
        dist_y = (pos[1] - goal[1]) * self.dy
        dist_z = (pos[2] - goal[2]) * self.dz
        euclidean = float(np.sqrt(dist_x**2 + dist_y**2 + dist_z**2))
        return self.w_distance * (euclidean / self.d_max)

    def _get_neighbors(self, x: int, y: int, z: int) -> List[Tuple[int, int, int, float]]:
        """Return valid 26-connected spatial neighbors and physical distances."""
        neighbors: List[Tuple[int, int, int, float]] = []
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for oz in (-1, 0, 1):
                    if ox == 0 and oy == 0 and oz == 0:
                        continue
                    nx, ny, nz = x + ox, y + oy, z + oz
                    if 0 <= nx < self.nx and 0 <= ny < self.ny and 0 <= nz < self.nz:
                        dist = float(np.sqrt((ox * self.dx) ** 2 + (oy * self.dy) ** 2 + (oz * self.dz) ** 2))
                        if self._vertical_rate_allowed(oz, dist):
                            neighbors.append((nx, ny, nz, dist))
        return neighbors

    def _vertical_rate_allowed(self, oz: int, dist: float) -> bool:
        if oz == 0:
            return True
        dt = dist / self.uav_speed
        vertical_rate = abs(oz * self.dz) / dt
        if oz > 0 and self.max_climb_rate is not None:
            return vertical_rate <= self.max_climb_rate
        if oz < 0 and self.max_descent_rate is not None:
            return vertical_rate <= self.max_descent_rate
        return True

    def _expand_node(
        self,
        current_node: SearchNode,
        neighbor_coords: Coord3D,
        dist: float,
    ) -> Optional[SearchNode]:
        """Expand one neighbor with state-vector risk accumulation.

        Follows the TD-RiskA* design (manuscript2 §6-§7):
        - Uses cumulative hazard rate H = -ln(P_surv) for numerical stability
        - Property damage is a discrete crash-event consequence (not continuous)
        - Noise is continuous exposure discounted by survival probability
        """
        x2, y2, z2 = neighbor_coords
        dt = dist / self.uav_speed

        # --- Online time sampling (§6) ---
        current_abs_time = float(current_node.state["absolute_time"])
        new_abs_time = current_abs_time + dt
        t2_idx = self.env_tensor.get_time_index(new_abs_time, self.time_resolution)

        risk = self.env_tensor.risk_at(x2, y2, z2, t2_idx)
        if risk["obstacle"]:
            return None

        # --- Cumulative hazard rate H (§4, §7) ---
        # H is additive: avoids numerical underflow from probability multiplication
        prior_H = float(current_node.state["cumulative_hazard"])
        p_crash_local = float(np.clip(risk["p_crash"], 0.0, 1.0))

        # Convert p_crash (already includes dt from tensor_engine) back to
        # a per-step hazard increment: h_step = -ln(1 - p_crash)
        # This is safe because p_crash ∈ [0, 1) after clipping.
        if p_crash_local >= 1.0:
            return None  # certain crash, prune
        h_step = -np.log(1.0 - p_crash_local)
        new_H = prior_H + h_step

        # Survival probability derived from H (for risk increments below)
        prior_survival = float(np.exp(-prior_H))
        new_survival = float(np.exp(-new_H))

        # --- Hard constraint: survival threshold (§5) ---
        if self.survival_threshold > 0.0 and new_survival < self.survival_threshold:
            return None

        # --- Hard constraint: battery time (§5) ---
        if new_abs_time > self.max_battery_time:
            return None

        # --- Risk increments (§7) ---
        # Fatality: conditional on survive-arrival AND crash-this-step
        delta_fatality = prior_survival * p_crash_local * float(risk["fatality"])
        # Property: conditional on survive-arrival AND crash-this-step (discrete event)
        delta_property = prior_survival * p_crash_local * float(risk["property"])
        # Noise: continuous exposure discounted by survival (no crash needed)
        delta_noise = prior_survival * float(risk["noise"]) * dt

        # --- Normalized single-step cost (论文 §3.4 Eq.10) ---
        # δJ = w_f*(δC_f/Ω_f) + w_p*(δC_p/Ω_p) + w_n*(δC_n/Ω_n) + w_d*(d/d_max)
        delta_J = (
            self.w_fatality * (delta_fatality / self.omega_fatality)
            + self.w_property * (delta_property / self.omega_property)
            + self.w_noise * (delta_noise / self.omega_noise)
            + self.w_distance * (dist / self.d_max)
        )

        new_state = {
            **current_node.state,
            "cum_distance": float(current_node.state["cum_distance"]) + dist,
            "cum_time": float(current_node.state["cum_time"]) + dt,
            "absolute_time": new_abs_time,
            "cumulative_hazard": new_H,
            "p_survival": new_survival,
            "cum_fatality": float(current_node.state["cum_fatality"]) + delta_fatality,
            "cum_property": float(current_node.state["cum_property"]) + delta_property,
            "cum_noise": float(current_node.state["cum_noise"]) + delta_noise,
            "cum_objective": float(current_node.state["cum_objective"]) + delta_J,
        }

        neighbor_node = SearchNode(x2, y2, z2, t2_idx, state_dict=new_state, parent=current_node)
        neighbor_node.g = float(new_state["cum_objective"])
        return neighbor_node

    def _objective_cost(self, state: Mapping[str, float]) -> float:
        """Return the normalized cumulative objective cost J."""
        return float(state.get("cum_objective", 0.0))

    def search(self, start_coords: Coord4D, goal_coords: Coord3D) -> Dict[str, Any]:
        """Perform TD-RiskA* search with Label-Setting mechanism.

        Per the design document (manuscript2 §10, supervisor's note):
        - Same spatial position (x,y,z) can be reached with different (t, H, J)
        - Multiple non-dominated labels coexist (Pareto-optimal)
        - A label is dominated if an existing label has <= t, <= H, and <= J
        """
        start_time = time.time()
        self._validate_start_goal(start_coords, goal_coords)

        start_x, start_y, start_z, start_t = start_coords
        start_state = {
            "absolute_time": start_t * self.time_resolution,
            "cumulative_hazard": 0.0,
            "cum_objective": 0.0,
        }
        start_node = SearchNode(start_x, start_y, start_z, start_t, state_dict=start_state)
        start_node.g = 0.0
        start_node.f = self._heuristic(start_node.pos_3d, goal_coords)

        if self.env_tensor.risk_at(start_x, start_y, start_z, start_t)["obstacle"]:
            return self._failed(start_time, 0, "start_in_obstacle")

        open_set: List[SearchNode] = [start_node]

        # Label-Setting: track the best label per spatial position (x,y,z).
        # Each entry stores {t, H, J} of the non-dominated label.
        # Because labels at the same (x,y,z) can be non-dominated, we keep
        # a list per position and check Pareto dominance.
        visited_labels: Dict[Coord3D, List[Dict[str, float]]] = {
            start_node.pos_3d: [{"t": float(start_t), "H": 0.0, "J": 0.0}]
        }

        iterations = 0
        total_labels = 1

        while open_set:
            iterations += 1
            if iterations > self.max_iterations:
                return self._failed(start_time, total_labels, "max_iterations")

            current = heapq.heappop(open_set)

            if current.pos_3d == goal_coords:
                return self._success(start_time, current, total_labels)

            for nx, ny, nz, dist in self._get_neighbors(current.x, current.y, current.z):
                neighbor = self._expand_node(current, (nx, ny, nz), dist)
                if neighbor is None:
                    continue

                # --- Label-Setting dominance check ---
                new_label = {
                    "t": float(neighbor.state["absolute_time"]),
                    "H": float(neighbor.state["cumulative_hazard"]),
                    "J": float(neighbor.g),
                }
                pos = neighbor.pos_3d
                labels_at_pos = visited_labels.get(pos, [])

                # Check if new label is dominated by any existing label
                dominated = False
                non_dominated = []
                for existing in labels_at_pos:
                    if (existing["t"] <= new_label["t"]
                            and existing["H"] <= new_label["H"]
                            and existing["J"] <= new_label["J"]):
                        dominated = True
                        break
                    # Keep existing labels that are NOT dominated by the new one
                    if not (new_label["t"] <= existing["t"]
                            and new_label["H"] <= existing["H"]
                            and new_label["J"] <= existing["J"]):
                        non_dominated.append(existing)

                if dominated:
                    continue

                # Enforce per-cell label cap to bound memory/runtime
                if len(non_dominated) >= self.max_labels_per_cell:
                    # Only admit if better than worst existing label by J
                    worst = max(non_dominated, key=lambda lbl: lbl["J"])
                    if new_label["J"] >= worst["J"]:
                        continue
                    non_dominated.remove(worst)

                # New label is non-dominated: register it and push to open set
                non_dominated.append(new_label)
                visited_labels[pos] = non_dominated
                total_labels += 1

                neighbor.f = neighbor.g + self._heuristic(neighbor.pos_3d, goal_coords)
                heapq.heappush(open_set, neighbor)

        return self._failed(start_time, total_labels, "open_set_exhausted")

    def _validate_start_goal(self, start: Coord4D, goal: Coord3D) -> None:
        sx, sy, sz, st = start
        gx, gy, gz = goal
        if not self.env_tensor.in_bounds(sx, sy, sz, st):
            raise ValueError(f"start_coords out of bounds: {start}")
        if not (0 <= gx < self.nx and 0 <= gy < self.ny and 0 <= gz < self.nz):
            raise ValueError(f"goal_coords out of bounds: {goal}")

    def _success(self, start_time: float, final_node: SearchNode, nodes_explored: int) -> Dict[str, Any]:
        path = []
        curr: Optional[SearchNode] = final_node
        while curr is not None:
            path.append({"coords": curr.coords, "state": dict(curr.state)})
            curr = curr.parent
        path.reverse()

        return {
            "status": "success",
            "path": path,
            "total_distance": final_node.state["cum_distance"],
            "total_time": final_node.state["cum_time"],
            "cum_fatality": final_node.state["cum_fatality"],
            "cum_property": final_node.state["cum_property"],
            "cum_noise": final_node.state["cum_noise"],
            "cumulative_hazard": final_node.state["cumulative_hazard"],
            "final_p_survival": final_node.state["p_survival"],
            "objective_cost": final_node.g,
            "time_cost": time.time() - start_time,
            "nodes_explored": nodes_explored,
        }

    @staticmethod
    def _failed(start_time: float, nodes_explored: int, reason: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "reason": reason,
            "time_cost": time.time() - start_time,
            "nodes_explored": nodes_explored,
        }


def run_example() -> Dict[str, Any]:
    """Run a small deterministic smoke example."""
    grid = GridSystem()
    rng = np.random.default_rng(42)
    p_crash = rng.random(grid.shape, dtype=np.float32) * 1e-5
    fatality = rng.random((grid.spatial.nx, grid.spatial.ny, grid.temporal.nt), dtype=np.float32) * 0.01
    property_risk = rng.random((grid.spatial.nx, grid.spatial.ny), dtype=np.float32) * 0.1
    noise = rng.random(grid.shape, dtype=np.float32) * 0.05

    env_tensor = EnvTensor(p_crash, fatality, property_risk, noise, grid=grid)
    planner = AStar4D(
        grid,
        env_tensor,
        {
            "uav_speed": 15.0,
            "w_distance": 0.4,
            "survival_threshold": 0.95,
            "max_battery_time": 3600.0,
            "max_labels_per_cell": 4,
        },
    )
    result = planner.search((0, 0, 5, 0), (grid.spatial.nx - 1, grid.spatial.ny - 1, 5))
    print(result["status"])
    return result


if __name__ == "__main__":
    run_example()
