# src/spatiotemporal_heterogeneity/core/models/dynamic_crash_prob.py
# 生成 4D P_crash 概率场张量 (结合风、雨、城市峡谷)
"""
Dynamic Crash Probability Model based on Cox Proportional Hazards Model.

Implements: P_crash = 1 - exp(-λ_base × Φ × Δt)
where Φ = f_wind × f_rain × f_obs
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional
import yaml
from pathlib import Path


@dataclass
class WindConfig:
    """Wind influence configuration."""
    V_limit: float = 12.0
    k_w: float = 3.0
    theta: float = 2.0


@dataclass
class RainConfig:
    """Rain influence configuration."""
    gamma_rain: float = 0.005


@dataclass
class UrbanCanyonConfig:
    """Urban canyon influence configuration."""
    K_obs: float = 10.0
    w_svf: float = 0.4
    w_height_ratio: float = 0.4
    w_proximity: float = 0.2
    alpha_svf: float = 1.5


@dataclass
class CrashProbConfig:
    """Configuration for crash probability model."""
    lambda_base: float = 1e-5
    wind: Optional[WindConfig] = None
    rain: Optional[RainConfig] = None
    urban_canyon: Optional[UrbanCanyonConfig] = None
    
    def __post_init__(self):
        if self.wind is None:
            self.wind = WindConfig()
        if self.rain is None:
            self.rain = RainConfig()
        if self.urban_canyon is None:
            self.urban_canyon = UrbanCanyonConfig()
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'CrashProbConfig':
        """Load configuration from YAML file."""
        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")
        
        with open(yaml_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        crash_prob_data = config_data.get('crash_probability', {})
        
        # Extract parameters
        lambda_base = crash_prob_data.get('lambda_base', 1e-5)
        
        # Wind parameters
        wind_data = crash_prob_data.get('wind', {})
        wind_config = WindConfig(
            V_limit=wind_data.get('V_limit', 12.0),
            k_w=wind_data.get('k_w', 3.0),
            theta=wind_data.get('theta', 2.0)
        )
        
        # Rain parameters
        rain_data = crash_prob_data.get('rain', {})
        rain_config = RainConfig(
            gamma_rain=rain_data.get('gamma_rain', 0.005)
        )
        
        # Urban canyon parameters
        urban_data = crash_prob_data.get('urban_canyon', {})
        urban_config = UrbanCanyonConfig(
            K_obs=urban_data.get('K_obs', 10.0),
            w_svf=urban_data.get('w_svf', 0.4),
            w_height_ratio=urban_data.get('w_height_ratio', 0.4),
            w_proximity=urban_data.get('w_proximity', 0.2),
            alpha_svf=urban_data.get('alpha_svf', 1.5)
        )
        
        return cls(
            lambda_base=lambda_base,
            wind=wind_config,
            rain=rain_config,
            urban_canyon=urban_config
        )


class DynamicCrashProbability:
    """Computes spatiotemporally varying crash probability."""
    
    def __init__(self, config: Optional[CrashProbConfig] = None, config_path: Optional[str] = None):
        if config_path:
            self.config = CrashProbConfig.from_yaml(config_path)
        else:
            self.config = config or CrashProbConfig()
    
    def compute_wind_factor(self, wind_speed: np.ndarray) -> np.ndarray:
        """
        Compute wind influence factor.
        
        f_wind = exp[k_w × (v/V_limit)^θ] if v < V_limit
        f_wind = +∞ otherwise
        """
        assert self.config.wind is not None
        ratio = wind_speed / self.config.wind.V_limit
        return np.where(
            ratio >= 1.0,
            np.inf,
            np.exp(self.config.wind.k_w * np.power(ratio, self.config.wind.theta))
        )
    
    def compute_rain_factor(self, rain_intensity: np.ndarray) -> np.ndarray:
        """Compute rain influence factor: f_rain = 1 + γ × I²"""
        assert self.config.rain is not None
        return 1.0 + self.config.rain.gamma_rain * np.square(rain_intensity)
    
    def compute_urban_factor(
        self,
        svf: np.ndarray,
        building_heights: np.ndarray,
        flight_altitude: float,
        dist_to_building: np.ndarray
    ) -> np.ndarray:
        """Compute urban canyon influence factor."""
        assert self.config.urban_canyon is not None
        epsilon = 1e-6
        
        term1 = self.config.urban_canyon.w_svf * np.power(1.0 - svf, self.config.urban_canyon.alpha_svf)
        term2 = self.config.urban_canyon.w_height_ratio * (building_heights / (flight_altitude + epsilon))
        term3 = self.config.urban_canyon.w_proximity * (1.0 / (dist_to_building + epsilon))
        
        R_canyon = term1 + term2 + term3
        R_normalized = np.clip(R_canyon / np.max(R_canyon), 0.0, 1.0)
        
        return 1.0 + self.config.urban_canyon.K_obs * R_normalized
    
    def compute_pcrash(
        self,
        f_wind: np.ndarray,
        f_rain: np.ndarray,
        f_obs: np.ndarray,
        dt: float = 1.0
    ) -> np.ndarray:
        """
        Compute crash probability field.
        
        P_crash = 1 - exp(-λ_base × Φ × Δt)
        """
        Phi = f_wind * f_rain * f_obs
        
        return np.where(
            np.isinf(Phi),
            1.0,
            1.0 - np.exp(-self.config.lambda_base * Phi * dt)
        )


def get_micro_grid_p_crash_model(config_path: Optional[str] = None) -> DynamicCrashProbability:
    """Factory function to create micro-level crash probability model."""
    return DynamicCrashProbability(config_path=config_path)

def get_macro_grid_p_crash_model(config_path: Optional[str] = None) -> DynamicCrashProbability:
    """Factory function to create macro-level crash probability model."""
    return DynamicCrashProbability(config_path=config_path)