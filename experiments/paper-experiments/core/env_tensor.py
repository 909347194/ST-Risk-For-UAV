"""
Environment tensor container for path-planning algorithms.

The algorithm layer consumes risk components produced by tensor_engine.  This
module keeps that boundary explicit: it validates component shapes, broadcasts
common tensor-engine outputs to (nx, ny, nz, nt), and exposes a small indexing
API for A*.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np


GridShape = Tuple[int, int, int, int]


class EnvTensor:
    """Container for individual risk tensors used during path planning."""

    def __init__(
        self,
        p_crash: np.ndarray,
        fatality: np.ndarray,
        property: np.ndarray,
        noise: np.ndarray,
        obstacle: Optional[np.ndarray] = None,
        grid: Optional[Any] = None,
    ):
        """
        Initialize a normalized environment tensor container.

        Args:
            p_crash: Crash probability component. Usually 4D.
            fatality: Fatality/exposure component. Supports 2D, 3D, or 4D.
            property: Property damage component. Supports 2D, 3D, or 4D.
            noise: Noise cost component. Supports 2D, 3D, or 4D.
            obstacle: Optional obstacle mask. Supports 2D, 3D, or 4D.
            grid: Optional GridSystem. Required when p_crash is not 4D.
        """
        shape = self._resolve_shape(p_crash, grid)
        self.nx, self.ny, self.nz, self.nt = shape

        self.p_crash = self._as_4d(p_crash, shape, "p_crash")
        self.fatality = self._as_4d(fatality, shape, "fatality")
        self.property = self._as_4d(property, shape, "property")
        self.noise = self._as_4d(noise, shape, "noise")
        self.obstacle = (
            self._as_4d(obstacle, shape, "obstacle").astype(bool)
            if obstacle is not None
            else None
        )

        self.validate_consistency()

    @property
    def shape(self) -> GridShape:
        """Return the canonical tensor shape."""
        return (self.nx, self.ny, self.nz, self.nt)

    def get_time_index(self, time_seconds: float, dt_resolution: float) -> int:
        """Convert absolute seconds to a valid discrete time slice index."""
        if dt_resolution <= 0:
            raise ValueError("dt_resolution must be positive")
        idx = int(time_seconds / dt_resolution)
        return int(np.clip(idx, 0, self.nt - 1))

    def risk_at(self, x: int, y: int, z: int, t: int) -> Dict[str, float]:
        """Return all risk components at one 4D grid coordinate."""
        if not self.in_bounds(x, y, z, t):
            raise IndexError(f"Coordinate out of bounds: {(x, y, z, t)}")
        return {
            "p_crash": float(self.p_crash[x, y, z, t]),
            "fatality": float(self.fatality[x, y, z, t]),
            "property": float(self.property[x, y, z, t]),
            "noise": float(self.noise[x, y, z, t]),
            "obstacle": bool(self.obstacle[x, y, z, t]) if self.obstacle is not None else False,
        }

    def in_bounds(self, x: int, y: int, z: int, t: int) -> bool:
        """Return True when a 4D coordinate is inside the tensor domain."""
        return 0 <= x < self.nx and 0 <= y < self.ny and 0 <= z < self.nz and 0 <= t < self.nt

    def validate_consistency(self) -> bool:
        """Validate shape and numeric consistency for all components."""
        expected = self.shape
        for name in ("p_crash", "fatality", "property", "noise"):
            tensor = getattr(self, name)
            if tensor.shape != expected:
                raise ValueError(f"{name} shape {tensor.shape} does not match {expected}")
            if not np.all(np.isfinite(tensor)):
                raise ValueError(f"{name} contains NaN or infinite values")

        if np.any((self.p_crash < 0.0) | (self.p_crash > 1.0)):
            raise ValueError("p_crash must be in [0, 1]")

        if self.obstacle is not None and self.obstacle.shape != expected:
            raise ValueError(f"obstacle shape {self.obstacle.shape} does not match {expected}")

        return True

    def summary(self) -> str:
        """Generate an ASCII summary suitable for logs on any terminal."""
        lines = [
            "=" * 60,
            "Environment Tensor Summary",
            "=" * 60,
            f"Grid Dimensions: {self.nx} x {self.ny} x {self.nz} x {self.nt}",
        ]
        for name in ("p_crash", "fatality", "property", "noise"):
            tensor = getattr(self, name)
            lines.append(
                f"{name:10s} range=[{np.min(tensor):.6g}, {np.max(tensor):.6g}] "
                f"mean={np.mean(tensor):.6g}"
            )
        if self.obstacle is not None:
            obs_count = int(np.count_nonzero(self.obstacle))
            pct = 100.0 * obs_count / self.obstacle.size
            lines.append(f"obstacle   blocked={obs_count} cells ({pct:.2f}%)")
        lines.append("=" * 60)
        return "\n".join(lines)

    @staticmethod
    def _resolve_shape(p_crash: np.ndarray, grid: Optional[Any]) -> GridShape:
        if grid is not None:
            return tuple(grid.shape)  # type: ignore[return-value]

        p_crash = np.asarray(p_crash)
        if p_crash.ndim != 4:
            raise ValueError("grid is required when p_crash is not 4D")
        return tuple(p_crash.shape)  # type: ignore[return-value]

    @staticmethod
    def _as_4d(tensor: np.ndarray, shape: GridShape, name: str) -> np.ndarray:
        arr = np.asarray(tensor, dtype=np.float32)
        nx, ny, nz, nt = shape

        if arr.shape == shape:
            return arr
        if arr.shape == (nx, ny):
            return np.broadcast_to(arr[:, :, None, None], shape).astype(np.float32, copy=True)
        if arr.shape == (nx, ny, nz):
            return np.broadcast_to(arr[:, :, :, None], shape).astype(np.float32, copy=True)
        if arr.shape == (nx, ny, nt):
            return np.broadcast_to(arr[:, :, None, :], shape).astype(np.float32, copy=True)

        raise ValueError(
            f"{name} shape {arr.shape} is not compatible with {shape}; "
            "expected (nx, ny), (nx, ny, nz), (nx, ny, nt), or (nx, ny, nz, nt)"
        )


class EnvTensorBuilder:
    """Builder that assembles tensor_engine components into an EnvTensor."""

    REQUIRED = ("p_crash", "fatality", "property", "noise")

    def __init__(self, grid: Optional[Any] = None):
        self.grid = grid
        self.components: Dict[str, np.ndarray] = {}

    def add_component(self, name: str, tensor: np.ndarray) -> "EnvTensorBuilder":
        """Add a named risk component and return self for chaining."""
        if name not in (*self.REQUIRED, "obstacle"):
            raise ValueError(f"Unknown EnvTensor component: {name}")
        self.components[name] = np.asarray(tensor)
        return self

    def add_components(self, components: Mapping[str, np.ndarray]) -> "EnvTensorBuilder":
        """Add multiple components from a mapping."""
        for name, tensor in components.items():
            self.add_component(name, tensor)
        return self

    def build(self) -> EnvTensor:
        """Build a validated EnvTensor from collected components."""
        missing = [name for name in self.REQUIRED if name not in self.components]
        if missing:
            raise ValueError(f"Missing required components: {missing}")

        return EnvTensor(
            p_crash=self.components["p_crash"],
            fatality=self.components["fatality"],
            property=self.components["property"],
            noise=self.components["noise"],
            obstacle=self.components.get("obstacle"),
            grid=self.grid,
        )

    def reset(self) -> None:
        """Clear all collected components."""
        self.components.clear()


def create_env_tensor_from_components(
    p_crash: np.ndarray,
    fatality: np.ndarray,
    property_risk: np.ndarray,
    noise: np.ndarray,
    obstacle: Optional[np.ndarray] = None,
    grid: Optional[Any] = None,
) -> EnvTensor:
    """Convenience function to create a validated EnvTensor."""
    builder = (
        EnvTensorBuilder(grid)
        .add_component("p_crash", p_crash)
        .add_component("fatality", fatality)
        .add_component("property", property_risk)
        .add_component("noise", noise)
    )
    if obstacle is not None:
        builder.add_component("obstacle", obstacle)
    return builder.build()
