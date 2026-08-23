"""
Dynamic fatality consequence model.

Computes E_fatality(x, y, z) = S_hit × [ρ_pop(x,y,t) × R_f^p(z) + ρ_veh(x,y,t) × R_f^v]

Per paper §4.1.2:
- Pedestrian fatality rate R_f^p uses a sigmoid function of impact energy
- Vehicle fatality rate R_f^v uses a statistical average
- The model outputs the raw consequence tensor; probability multiplication
  (P_surv × P_crash) is handled by the algorithm layer.

Usage:
    from tensor_engine.dynamic_fatality import DynamicFatalityModel

    model = DynamicFatalityModel(config_path='configs/common.yaml')
    e_fatality = model.compute_fatality_consequence(
        rho_pop=rho_pop_3d,          # (nx, ny, nt)
        rho_vehicle=rho_vehicle_3d,   # (nx, ny, nt)
        flight_altitude=50.0,         # meters
    )
    # e_fatality shape: (nx, ny, nt)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np


@dataclass
class FatalityConfig:
    """Parameters for the fatality rate model."""
    lethal_alpha: float = 1_000_000.0   # α: lethal energy parameter
    lethal_beta: float = 100.0          # β: energy threshold
    impact_area: float = 5.0            # S_hit: impact area radius (m)
    vehicle_fatality_rate: float = 0.01 # R_f^v: statistical average
    uav_mass: float = 2.0               # kg
    min_altitude: float = 10.0          # m, below which impact energy saturates

    @classmethod
    def from_yaml(cls, config_path: Union[str, Path]) -> "FatalityConfig":
        """Load from common.yaml."""
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        fatal = cfg.get("fatal_risk", {})
        uav = cfg.get("uav_constraints", {})

        return cls(
            lethal_alpha=fatal.get("lethal_alpha", cls.lethal_alpha),
            lethal_beta=fatal.get("lethal_beta", cls.lethal_beta),
            impact_area=uav.get("impact_area", cls.impact_area),
            vehicle_fatality_rate=fatal.get("vehicle_fatality_rate", cls.vehicle_fatality_rate),
            uav_mass=fatal.get("uav_mass", cls.uav_mass),
            min_altitude=uav.get("min_altitude", cls.min_altitude),
        )


class DynamicFatalityModel:
    """
    Computes the fatality consequence tensor E_fatality(x, y, z, t).

    The output is a raw consequence measure (expected fatalities per crash),
    NOT multiplied by P_crash or P_surv. The algorithm layer handles those.
    """

    def __init__(
        self,
        config: Optional[FatalityConfig] = None,
        config_path: Optional[Union[str, Path]] = None,
    ):
        if config_path is not None:
            self.config = FatalityConfig.from_yaml(config_path)
        else:
            self.config = config or FatalityConfig()

    def compute_pedestrian_fatality_rate(
        self, flight_altitude: Union[float, np.ndarray]
    ) -> Union[float, np.ndarray]:
        """
        Compute pedestrian fatality rate R_f^p using the sigmoid model (eq. 10).

        R_f^p = 1 / (1 + sqrt(α/β) × (β/E_imp)^(1/(4×S_c)))

        where E_imp = m × v_imp^2 / 2, and v_imp accounts for air drag.
        """
        cfg = self.config
        # Terminal velocity under drag (simplified: v_imp ≈ sqrt(2gh) for low drag)
        g = 9.81
        h = np.maximum(np.asarray(flight_altitude, dtype=np.float64), cfg.min_altitude)
        # Simplified impact velocity (no drag for clarity)
        v_imp = np.sqrt(2.0 * g * h)
        E_imp = 0.5 * cfg.uav_mass * v_imp ** 2

        # Sigmoid fatality rate
        alpha_over_beta = cfg.lethal_alpha / cfg.lethal_beta
        energy_ratio = cfg.lethal_beta / np.maximum(E_imp, 1e-6)
        exponent = 1.0 / (4.0 * cfg.impact_area)  # S_c ≈ impact_area as proxy
        R_f = 1.0 / (1.0 + np.sqrt(alpha_over_beta) * np.power(energy_ratio, exponent))
        return np.clip(R_f, 0.0, 1.0)

    def compute_fatality_consequence(
        self,
        rho_pop: np.ndarray,
        rho_vehicle: Optional[np.ndarray] = None,
        flight_altitude: float = 50.0,
    ) -> np.ndarray:
        """
        Compute E_fatality(x, y, t) — the fatality consequence tensor.

        E_fatality = S_hit × [ρ_pop × R_f^p + ρ_veh × R_f^v]

        Args:
            rho_pop: Dynamic population density (nx, ny, nt) [people/m²]
            rho_vehicle: Dynamic vehicle density (nx, ny, nt) [vehicles/m²]
            flight_altitude: UAV flight altitude (m)

        Returns:
            E_fatality: (nx, ny, nt) expected fatalities per crash
        """
        cfg = self.config
        S_hit = cfg.impact_area  # Impact area in m²

        R_f_ped = self.compute_pedestrian_fatality_rate(flight_altitude)
        e_ped = S_hit * rho_pop * R_f_ped

        if rho_vehicle is not None:
            e_veh = S_hit * rho_vehicle * cfg.vehicle_fatality_rate
            return e_ped + e_veh
        return e_ped
