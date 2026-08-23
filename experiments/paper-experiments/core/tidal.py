"""
Spatiotemporal tidal models for population and traffic density.

Mass-Conservative Spatiotemporal Commuting Flow Model
======================================================

Implements a three-layer architecture:
  1. Spatial: Huff gravity decay field  G_bar_i^theta
  2. Temporal: smooth activation functions  phi_theta(t)  with Partition of Unity
  3. Assembly: mass-conservative density  rho(i,t) = (N_total/S_cell) * sum_theta phi_theta(t) * G_bar_i^theta

Key invariant (mass conservation):
    sum_i  rho(i,t) * S_cell  =  N_total   for all t

Data-provision responsibility:
    poi_counts.npz -> spatial influence maps
    base_pop_2d.npy -> only used for backward-compatible mode

Supports both synthetic and real data with automatic path switching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple, Union

import numpy as np

from core.grid_system import GridSystem, get_micro_grid
from core.poi_parser import POI_CATEGORIES, load_poi_counts
from core.population_resampler import load_base_population
from core.paths import DataPaths, get_data_paths, get_data_type


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "02_processed"
DEFAULT_RHO_POP_PATH = DEFAULT_PROCESSED_DIR / "rho_pop_3d.npy"
DEFAULT_RHO_VEHICLE_PATH = DEFAULT_PROCESSED_DIR / "rho_vehicle_3d.npy"


@dataclass
class TidalModelConfig:
    """Parameters for the mass-conservative POI tidal gravity model.

    Three configurable axes:
      1. Huff spatial gravity:  alpha (decay exponent), R0 (smooth radius)
      2. Temporal activation:   per-category peak times, widths, amplitudes
n      3. Mass conservation:     N_total (total population/vehicles)
    """

    # ── Huff spatial gravity parameters ──────────────────────────────
    huff_alpha: float = 2.0          # distance decay exponent (2 = planar energy dissipation)
    huff_R0_m: float = 10.0          # smooth radius R0 in meters (prevents singularity)

    # Per-category spatial spread sigma (meters) — used to derive per-POI weight W_j
    # when POI weights are not explicitly provided.
    population_sigma_m: Dict[str, float] = field(default_factory=lambda: {
        "residential": 400.0,
        "office": 350.0,
        "institution": 300.0,
        "transport": 250.0,
        "industrial": 500.0,
    })
    traffic_sigma_m: Dict[str, float] = field(default_factory=lambda: {
        "residential": 220.0,
        "office": 220.0,
        "institution": 180.0,
        "transport": 160.0,
        "industrial": 250.0,
    })

    # ── Temporal activation parameters ───────────────────────────────
    # Transition sharpness for sigmoid-based profiles
    lambda_t: float = 1.5            # sigmoid steepness

    # Office / industrial peak parameters
    office_start_hour: float = 8.0
    office_end_hour: float = 18.0
    office_amplitude: float = 0.90

    # Commercial double-peak GMM
    com_peak1_hour: float = 12.5
    com_peak1_sigma: float = 1.5
    com_peak1_amp: float = 0.80
    com_peak2_hour: float = 19.0
    com_peak2_sigma: float = 1.8
    com_peak2_amp: float = 0.70

    # Leisure / recreation single peak
    rec_peak_hour: float = 16.5
    rec_peak_sigma: float = 2.0
    rec_amplitude: float = 0.85

    # Institution (school / hospital) — daytime plateau
    inst_start_hour: float = 8.0
    inst_end_hour: float = 17.0
    inst_amplitude: float = 0.90

    # Transport — sharp commuting peaks
    trans_base: float = 0.20
    trans_peak1_hour: float = 8.25
    trans_peak1_sigma: float = 0.65
    trans_peak2_hour: float = 18.25
    trans_peak2_sigma: float = 0.75
    trans_peak_amp: float = 0.80

    # ── Mass conservation ────────────────────────────────────────────
    N_total_pop: float = 50000.0     # total resident population in study area
    N_total_veh: float = 15000.0     # total vehicles in study area

    # ── Legacy compatibility (fallback background terms) ─────────────
    population_background: float = 0.10
    traffic_background: float = 0.05
    population_weights: Dict[str, float] = field(default_factory=lambda: {
        "residential": 1.0, "office": 1.2, "institution": 1.5,
        "transport": 1.8, "industrial": 0.3,
    })
    traffic_weights: Dict[str, float] = field(default_factory=lambda: {
        "residential": 1.0, "office": 1.5, "institution": 0.8,
        "transport": 2.0, "industrial": 0.6,
    })


class SpatiotemporalTidalModel:
    """
    Mass-conservative spatiotemporal tidal density model.

    Three-layer architecture:
      Layer 1 — Spatial Huff gravity:   G_bar_i^theta
      Layer 2 — Temporal activation:    phi_theta(t)  (Partition of Unity)
      Layer 3 — Assembly:               rho(i,t) = (N_total/S_cell) * sum_theta phi_theta(t) * G_bar_i^theta

    Mass conservation invariant:
        sum_i  rho(i,t) * S_cell  =  N_total   for all t
    """

    def __init__(
        self,
        grid: Optional[GridSystem] = None,
        config: Optional[TidalModelConfig] = None,
    ):
        self.grid = grid or get_micro_grid()
        self.config = config or TidalModelConfig()

    # ==================================================================
    # Public API
    # ==================================================================

    def build_population_density(
        self,
        base_population: np.ndarray,
        poi_counts: Mapping[str, np.ndarray],
        *,
        normalize: bool = False,
        save_path: Optional[Union[str, Path]] = None,
    ) -> np.ndarray:
        """Build dynamic population density rho_pop[x, y, t] (mass-conservative)."""
        rho = self._build_density_conserved(
            poi_counts=poi_counts,
            N_total=self.config.N_total_pop,
            sigma_m=self.config.population_sigma_m,
            activation_fn=self._population_activation_all,
        )
        if normalize:
            rho = _minmax_normalize(rho)
        if save_path is not None:
            save_density(rho, save_path)
        return rho

    def build_vehicle_density(
        self,
        base_vehicle: np.ndarray,
        poi_counts: Mapping[str, np.ndarray],
        *,
        normalize: bool = False,
        save_path: Optional[Union[str, Path]] = None,
        road_mask: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Build dynamic traffic density rho_vehicle[x, y, t].

        If road_mask is provided, non-road cells are forced to zero.
        When mass-conservative mode is used, N_total_veh mass is distributed
        only over road cells.
        """
        rho = self._build_density_conserved(
            poi_counts=poi_counts,
            N_total=self.config.N_total_veh,
            sigma_m=self.config.traffic_sigma_m,
            activation_fn=self._traffic_activation_all,
            spatial_mask=road_mask,
        )
        if road_mask is not None:
            # Force non-road cells to zero
            mask_4d = road_mask[:, :, np.newaxis].astype(np.float32)
            rho = rho * mask_4d
        if normalize:
            rho = _minmax_normalize(rho)
        if save_path is not None:
            save_density(rho, save_path)
        return rho

    # ==================================================================
    # Layer 1: Huff spatial gravity field
    # ==================================================================

    def build_huff_influence_maps(
        self,
        poi_counts: Mapping[str, np.ndarray],
        sigma_m: Mapping[str, float],
    ) -> Dict[str, np.ndarray]:
        """Build normalized Huff gravity influence maps G_bar_i^theta.

        For each category theta:
          1. Treat each POI grid cell j with count c_j as a mass point with
             weight W_j = c_j * sigma_theta  (count scaled by category spread)
          2. Compute Huff gravity:  G_ij = W_j / (d_ij^2 + R0^2)^(alpha/2)
          3. Sum over all j in category theta:  G_i = sum_j G_ij
          4. Normalize to probability distribution:  G_bar_i = G_i / sum_k G_k

        Returns:
            Dict mapping category -> (nx, ny) float32 array with sum = 1.0
        """
        nx, ny = self.grid.spatial.nx, self.grid.spatial.ny
        dx = self.grid.spatial.dx
        alpha = self.config.huff_alpha
        R0 = self.config.huff_R0_m

        # Pre-compute coordinate grids (meters)
        x_coords = self.grid.x_coords  # (nx,)
        y_coords = self.grid.y_coords  # (ny,)
        XX, YY = np.meshgrid(x_coords, y_coords, indexing="ij")  # (nx, ny)

        influence_maps: Dict[str, np.ndarray] = {}

        for category in POI_CATEGORIES:
            counts = np.asarray(
                poi_counts.get(category, np.zeros((nx, ny))),
                dtype=np.float64,
            )
            if counts.shape != (nx, ny):
                raise ValueError(
                    f"poi_counts[{category}] shape {counts.shape} != ({nx}, {ny})"
                )

            # Find POI cells (non-zero count)
            poi_mask = counts > 0
            if not np.any(poi_mask):
                influence_maps[category] = np.zeros((nx, ny), dtype=np.float32)
                continue

            # Per-POI weights: W_j = count_j * sigma_category
            sigma_cat = float(sigma_m.get(category, 300.0))
            poi_weights = counts[poi_mask] * sigma_cat  # (n_poi,)

            # POI coordinates
            poi_ix, poi_iy = np.where(poi_mask)
            poi_x = x_coords[poi_ix]  # (n_poi,)
            poi_y = y_coords[poi_iy]  # (n_poi,)

            # Huff gravity: G_i = sum_j  W_j / (d_ij^2 + R0^2)^(alpha/2)
            # Vectorized over POIs using broadcasting
            # dist_sq: (nx, ny, n_poi)
            dist_sq = (
                (XX[:, :, np.newaxis] - poi_x[np.newaxis, np.newaxis, :]) ** 2
                + (YY[:, :, np.newaxis] - poi_y[np.newaxis, np.newaxis, :]) ** 2
            )
            gravity = poi_weights[np.newaxis, np.newaxis, :] / (
                (dist_sq + R0 ** 2) ** (alpha / 2.0)
            )  # (nx, ny, n_poi)
            G_i = np.sum(gravity, axis=2)  # (nx, ny)

            # Normalize to probability distribution: sum_i G_bar_i = 1.0
            total = float(G_i.sum())
            if total > 0:
                G_bar = (G_i / total).astype(np.float32)
            else:
                G_bar = np.zeros((nx, ny), dtype=np.float32)

            influence_maps[category] = G_bar

        return influence_maps

    # ==================================================================
    # Layer 2: Smooth temporal activation functions (Partition of Unity)
    # ==================================================================

    @staticmethod
    def _sigmoid(t: float, center: float, lam: float = 1.5) -> float:
        """Smooth sigmoid: 1 / (1 + exp(-lam * (t - center)))."""
        return float(1.0 / (1.0 + np.exp(-lam * (t - center))))

    @staticmethod
    def _gaussian(t: float, mean: float, sigma: float) -> float:
        """Gaussian peak."""
        return float(np.exp(-0.5 * ((t - mean) / sigma) ** 2))

    def _population_activation_raw(self, category: str, hour: float) -> float:
        """Un-normalized population activation tilde_phi_theta(t).

        Uses smooth, continuous mathematical functions:
          - Industrial/Office: product of two sigmoids (smooth step)
          - Commercial: double-peak GMM
          - Leisure: single-peak Gaussian
          - Institution: smooth plateau (sigmoid pair)
          - Transport: sharp dual Gaussian peaks
          - Residential: derived as complement (handled by Partition of Unity)
        """
        cfg = self.config
        lam = cfg.lambda_t
        t = float(hour)

        if category == "industrial":
            # Industrial/Office: smooth daytime plateau via sigmoid product
            return cfg.office_amplitude * self._sigmoid(t, cfg.office_start_hour, lam) \
                * self._sigmoid(-t, -cfg.office_end_hour, lam)

        if category == "office":
            # Commercial: double-peak GMM (lunch + evening)
            peak1 = cfg.com_peak1_amp * self._gaussian(t, cfg.com_peak1_hour, cfg.com_peak1_sigma)
            peak2 = cfg.com_peak2_amp * self._gaussian(t, cfg.com_peak2_hour, cfg.com_peak2_sigma)
            return peak1 + peak2

        if category == "institution":
            # Institution (school/hospital): smooth daytime plateau
            return cfg.inst_amplitude * self._sigmoid(t, cfg.inst_start_hour, lam) \
                * self._sigmoid(-t, -cfg.inst_end_hour, lam)

        if category == "transport":
            # Transport: sharp commuting peaks + baseline
            peak1 = cfg.trans_peak_amp * self._gaussian(t, cfg.trans_peak1_hour, cfg.trans_peak1_sigma)
            peak2 = cfg.trans_peak_amp * self._gaussian(t, cfg.trans_peak2_hour, cfg.trans_peak2_sigma)
            return cfg.trans_base + peak1 + peak2

        if category == "residential":
            # Residential: nighttime base + commuting shoulders
            night = self._sigmoid(-t, -7.0, lam) + self._sigmoid(t, 18.0, lam)
            commute = 0.35 * (
                self._gaussian(t, 8.0, 1.0) + self._gaussian(t, 18.5, 1.2)
            )
            return float(np.clip(0.25 + 0.50 * night + commute, 0.0, 1.0))

        return 0.0

    def _traffic_activation_raw(self, category: str, hour: float) -> float:
        """Un-normalized traffic activation tilde_phi_theta(t)."""
        cfg = self.config
        lam = cfg.lambda_t
        t = float(hour)

        if category == "transport":
            # Transport: sharp commuting peaks
            peak1 = cfg.trans_peak_amp * self._gaussian(t, cfg.trans_peak1_hour, cfg.trans_peak1_sigma)
            peak2 = cfg.trans_peak_amp * self._gaussian(t, cfg.trans_peak2_hour, cfg.trans_peak2_sigma)
            return cfg.trans_base + peak1 + peak2

        if category == "office":
            # Commercial: daytime + commuting
            plateau = 0.70 * self._sigmoid(t, 9.5, lam) * self._sigmoid(-t, -17.5, lam)
            peaks = 0.25 * (
                self._gaussian(t, 8.5, 0.8) + self._gaussian(t, 18.2, 0.8)
            )
            return 0.20 + plateau + peaks

        if category == "residential":
            # Residential: nighttime base + commuting peaks
            peaks = 0.35 * (
                self._gaussian(t, 7.8, 0.9) + self._gaussian(t, 18.5, 1.0)
            )
            night_base = 0.35 * self._sigmoid(-t, -7.0, lam) + 0.22 * self._sigmoid(t, 7.0, lam)
            return night_base + peaks

        if category == "institution":
            # Institution: daytime plateau
            return 0.65 * self._sigmoid(t, cfg.inst_start_hour, lam) \
                * self._sigmoid(-t, -cfg.inst_end_hour, lam) + 0.05

        if category == "industrial":
            # Industrial: daytime plateau
            return 0.45 * self._sigmoid(t, 7.0, lam) * self._sigmoid(-t, -19.0, lam) + 0.10

        return 0.0

    def _population_activation_all(self, hour: float) -> Dict[str, float]:
        """Return Partition-of-Unity normalized population activations for all categories."""
        raw = {cat: self._population_activation_raw(cat, hour) for cat in POI_CATEGORIES}
        total = sum(raw.values())
        if total > 0:
            return {cat: v / total for cat, v in raw.items()}
        # Fallback: uniform
        n = len(POI_CATEGORIES)
        return {cat: 1.0 / n for cat in POI_CATEGORIES}

    def _traffic_activation_all(self, hour: float) -> Dict[str, float]:
        """Return Partition-of-Unity normalized traffic activations for all categories."""
        raw = {cat: self._traffic_activation_raw(cat, hour) for cat in POI_CATEGORIES}
        total = sum(raw.values())
        if total > 0:
            return {cat: v / total for cat, v in raw.items()}
        n = len(POI_CATEGORIES)
        return {cat: 1.0 / n for cat in POI_CATEGORIES}

    # ==================================================================
    # Layer 3: Mass-conservative assembly
    # ==================================================================

    def _build_density_conserved(
        self,
        *,
        poi_counts: Mapping[str, np.ndarray],
        N_total: float,
        sigma_m: Mapping[str, float],
        activation_fn,
        spatial_mask: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Assemble mass-conservative density field.

        rho(i, t) = (N_total / S_cell) * sum_theta  phi_theta(t) * G_bar_i^theta

        If spatial_mask is provided, mass is distributed only over masked cells.
        """
        nx, ny = self.grid.spatial.nx, self.grid.spatial.ny
        nt = self.grid.temporal.nt
        S_cell = self.grid.spatial.dx * self.grid.spatial.dy

        # Layer 1: Huff influence maps  G_bar_i^theta  (sum = 1.0 per category)
        influence_maps = self.build_huff_influence_maps(poi_counts, sigma_m)

        # Assemble density
        density = np.zeros((nx, ny, nt), dtype=np.float64)

        for t_idx, hour in enumerate(np.mod(self.grid.time_hours, 24.0)):
            # Layer 2: Partition-of-Unity activations  phi_theta(t)  (sum = 1.0)
            phi = activation_fn(float(hour))

            # Layer 3: weighted sum of influence maps
            weighted_sum = np.zeros((nx, ny), dtype=np.float64)
            for category in POI_CATEGORIES:
                weighted_sum += phi[category] * influence_maps[category]

            density[:, :, t_idx] = (N_total / S_cell) * weighted_sum

        # Clean up numerical artifacts
        density = np.nan_to_num(density, nan=0.0, posinf=0.0, neginf=0.0)
        density[density < 0] = 0.0

        return density.astype(np.float32)

    # ==================================================================
    # Legacy compatibility (backward-compatible multiplicative mode)
    # ==================================================================

    def _build_density(
        self,
        *,
        base_map: np.ndarray,
        poi_counts: Mapping[str, np.ndarray],
        weights: Mapping[str, float],
        sigma_m: Mapping[str, float],
        background: float,
        profile_fn,
    ) -> np.ndarray:
        """Legacy multiplicative mode (backward compatible)."""
        base_map = np.asarray(base_map, dtype=np.float64)
        self._validate_xy(base_map, "base_map")

        nt = self.grid.temporal.nt
        density = np.zeros((self.grid.spatial.nx, self.grid.spatial.ny, nt), dtype=np.float64)
        influence_maps = self.build_huff_influence_maps(poi_counts, sigma_m)

        for t_idx, hour in enumerate(np.mod(self.grid.time_hours, 24.0)):
            phi = profile_fn(float(hour))
            multiplier = np.full(base_map.shape, float(background), dtype=np.float64)
            for category in POI_CATEGORIES:
                tau = phi.get(category, 0.0) if isinstance(phi, dict) else phi
                multiplier += weights.get(category, 0.0) * tau * influence_maps[category]
            density[:, :, t_idx] = base_map * multiplier

        density = np.nan_to_num(density, nan=0.0, posinf=0.0, neginf=0.0)
        density[density < 0] = 0.0
        return density.astype(np.float32)

    @property
    def _xy_shape(self) -> Tuple[int, int]:
        return (self.grid.spatial.nx, self.grid.spatial.ny)

    def _validate_xy(self, array: np.ndarray, name: str):
        if array.shape != self._xy_shape:
            raise ValueError(f"{name} must have shape {self._xy_shape}, got {array.shape}.")

    # ==================================================================
    # Verification
    # ==================================================================

    def verify_mass_conservation(
        self,
        density: np.ndarray,
        N_total: float,
        label: str = "population",
    ) -> Dict[str, float]:
        """Verify mass conservation: sum_i rho(i,t) * S_cell ≈ N_total for all t."""
        S_cell = self.grid.spatial.dx * self.grid.spatial.dy
        nx, ny = self.grid.spatial.nx, self.grid.spatial.ny
        total_per_t = np.sum(density.reshape(nx, ny, -1), axis=(0, 1)) * S_cell
        return {
            "label": label,
            "N_total_expected": N_total,
            "N_total_mean": float(np.mean(total_per_t)),
            "N_total_min": float(np.min(total_per_t)),
            "N_total_max": float(np.max(total_per_t)),
            "relative_error_max": float(np.max(np.abs(total_per_t - N_total) / N_total)),
        }


class SpatiotemporalTidalModelforPopulationDensity(SpatiotemporalTidalModel):
    """Backward-compatible class name for population density modeling."""

    def build(
        self,
        base_population: np.ndarray,
        poi_counts: Mapping[str, np.ndarray],
        **kwargs,
    ) -> np.ndarray:
        return self.build_population_density(base_population, poi_counts, **kwargs)


class SpatiotemporalTidalModelforTrafficDensity(SpatiotemporalTidalModel):
    """Backward-compatible class name for traffic density modeling."""

    def build(
        self,
        base_vehicle: np.ndarray,
        poi_counts: Mapping[str, np.ndarray],
        **kwargs,
    ) -> np.ndarray:
        return self.build_vehicle_density(base_vehicle, poi_counts, **kwargs)


# ======================================================================
# Legacy standalone activation functions (kept for backward compat)
# ======================================================================

def population_activation(category: str, hour: float) -> float:
    """Legacy: single-category activation. Use TidalModelConfig for new code."""
    _model = SpatiotemporalTidalModel()
    return _model._population_activation_raw(category, hour)


def traffic_activation(category: str, hour: float) -> float:
    """Legacy: single-category activation. Use TidalModelConfig for new code."""
    _model = SpatiotemporalTidalModel()
    return _model._traffic_activation_raw(category, hour)


def build_dynamic_population_density(
    base_pop_path: Optional[Union[str, Path]] = None,
    poi_counts_path: Optional[Union[str, Path]] = None,
    output_path: Optional[Union[str, Path]] = None,
    grid: Optional[GridSystem] = None,
    paths: Optional[DataPaths] = None,
    N_total: Optional[float] = None,
) -> np.ndarray:
    """Load processed inputs and save rho_pop[x, y, t] (mass-conservative)."""

    grid = grid or get_micro_grid()
    paths = paths or get_data_paths()

    base_pop = load_base_population(
        base_pop_path or paths.base_pop_path,
        paths=paths,
    )
    poi_counts = load_poi_counts(
        poi_counts_path or paths.poi_counts_path,
        paths=paths,
    )
    out = output_path or paths.rho_pop_path

    config = TidalModelConfig()
    if N_total is not None:
        config.N_total_pop = N_total
    model = SpatiotemporalTidalModel(grid=grid, config=config)
    return model.build_population_density(base_pop, poi_counts, save_path=out)


def build_dynamic_vehicle_density(
    base_vehicle: np.ndarray,
    poi_counts_path: Optional[Union[str, Path]] = None,
    output_path: Optional[Union[str, Path]] = None,
    grid: Optional[GridSystem] = None,
    paths: Optional[DataPaths] = None,
    N_total: Optional[float] = None,
    road_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Build and save rho_vehicle[x, y, t] from a base vehicle map."""

    grid = grid or get_micro_grid()
    paths = paths or get_data_paths()

    poi_counts = load_poi_counts(
        poi_counts_path or paths.poi_counts_path,
        paths=paths,
    )
    out = output_path or paths.rho_vehicle_path

    config = TidalModelConfig()
    if N_total is not None:
        config.N_total_veh = N_total
    model = SpatiotemporalTidalModel(grid=grid, config=config)
    return model.build_vehicle_density(
        base_vehicle, poi_counts, save_path=out, road_mask=road_mask,
    )


def save_density(
    density: np.ndarray,
    output_path: Optional[Union[str, Path]] = None,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save density array to the appropriate path."""
    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.processed
    output_path = Path(output_path)
    if output_path.suffix == '':
        output_path = output_path / "density.npy"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, np.asarray(density, dtype=np.float32))
    return output_path


def _gaussian_smooth(array: np.ndarray, sigma_cells: float) -> np.ndarray:
    """Gaussian smooth (kept as utility for backward compatibility)."""
    try:
        from scipy.ndimage import gaussian_filter
        return gaussian_filter(array, sigma=sigma_cells, mode="nearest")
    except ImportError:
        return _slow_gaussian_smooth(array, sigma_cells)


def _slow_gaussian_smooth(array: np.ndarray, sigma_cells: float) -> np.ndarray:
    """Small fallback used only when scipy is unavailable."""

    radius = max(1, int(3 * sigma_cells))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-0.5 * (x / sigma_cells) ** 2)
    kernel = kernel / kernel.sum()

    padded_x = np.pad(array, ((radius, radius), (0, 0)), mode="edge")
    temp = np.zeros_like(array, dtype=np.float64)
    for i in range(array.shape[0]):
        temp[i, :] = np.sum(padded_x[i:i + 2 * radius + 1, :] * kernel[:, None], axis=0)

    padded_y = np.pad(temp, ((0, 0), (radius, radius)), mode="edge")
    result = np.zeros_like(array, dtype=np.float64)
    for j in range(array.shape[1]):
        result[:, j] = np.sum(padded_y[:, j:j + 2 * radius + 1] * kernel[None, :], axis=1)
    return result


def _minmax_normalize(array: np.ndarray) -> np.ndarray:
    min_value = float(array.min())
    max_value = float(array.max())
    if max_value <= min_value:
        return np.zeros_like(array, dtype=np.float32)
    return ((array - min_value) / (max_value - min_value)).astype(np.float32)


if __name__ == "__main__":
    from core.poi_parser import create_synthetic_poi_counts
    from core.population_resampler import create_synthetic_base_population

    grid = get_micro_grid()
    base_pop = create_synthetic_base_population(grid=grid, save=False)
    poi_counts = create_synthetic_poi_counts(grid=grid, save=False)

    config = TidalModelConfig(N_total_pop=50000.0, N_total_veh=15000.0)
    model = SpatiotemporalTidalModel(grid=grid, config=config)

    # Build mass-conservative population density
    rho_pop = model.build_population_density(base_pop, poi_counts)
    print(f"rho_pop shape: {rho_pop.shape}")
    print(f"rho_pop range: [{rho_pop.min():.3f}, {rho_pop.max():.3f}]")

    # Verify mass conservation
    pop_check = model.verify_mass_conservation(rho_pop, config.N_total_pop, "population")
    print(f"Mass conservation (pop): N_expected={pop_check['N_total_expected']:.0f}, "
          f"N_mean={pop_check['N_total_mean']:.0f}, "
          f"rel_error_max={pop_check['relative_error_max']:.6f}")

    # Build mass-conservative traffic density
    rho_veh = model.build_vehicle_density(base_pop, poi_counts)
    print(f"rho_veh shape: {rho_veh.shape}")
    print(f"rho_veh range: [{rho_veh.min():.3f}, {rho_veh.max():.3f}]")

    veh_check = model.verify_mass_conservation(rho_veh, config.N_total_veh, "traffic")
    print(f"Mass conservation (veh): N_expected={veh_check['N_total_expected']:.0f}, "
          f"N_mean={veh_check['N_total_mean']:.0f}, "
          f"rel_error_max={veh_check['relative_error_max']:.6f}")
