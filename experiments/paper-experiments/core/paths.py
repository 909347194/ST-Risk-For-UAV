"""
Centralized path management for data_provision.

Supports seamless switching between synthetic and real data paths.

Data directory structure:
    data/
        01_raw/               # Raw GIS inputs (real data)
            synthetic/         # Raw GIS inputs (synthetic data)
        02_processed/          # Processed NumPy matrices (real data)
            synthetic/         # Processed NumPy matrices (synthetic data)
        03_tensors/            # Tensor outputs (real data)
            synthetic/         # Tensor outputs (synthetic data)

Synthetic data paths always contain 'synthetic' in the directory structure.
Real data paths are the top-level directories.

Usage:
    from data_provision.paths import DataPaths, set_data_type, get_data_paths

    # Switch to synthetic mode
    set_data_type('synthetic')
    paths = get_data_paths()
    # paths.processed -> .../data/02_processed/synthetic/

    # Switch to real mode
    set_data_type('real')
    paths = get_data_paths()
    # paths.processed -> .../data/02_processed/
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

DataType = Literal['synthetic', 'real']

# Project root: methods/spatiotemporal_heterogeneity/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"

_current_data_type: DataType = 'real'


@dataclass
class DataPaths:
    """
    Structured paths for the current data type.
    
    Attributes:
        raw:       Path to 01_raw (with synthetic subdir if applicable)
        processed: Path to 02_processed (with synthetic subdir if applicable)
        tensors:   Path to 03_tensors (with synthetic subdir if applicable)
        project:   Path to the project root
        data_root: Path to the data directory
        data_type: Current data type ('synthetic' or 'real')
    """
    raw: Path
    processed: Path
    tensors: Path
    project: Path = PROJECT_ROOT
    data_root: Path = DATA_ROOT
    data_type: DataType = 'real'

    # ── Processed output files ──────────────────────────────────────────
    @property
    def base_pop_path(self) -> Path:
        """base_pop_2d.npy"""
        return self.processed / "base_pop_2d.npy"

    @property
    def poi_counts_path(self) -> Path:
        """poi_counts.npz"""
        return self.processed / "poi_counts.npz"

    @property
    def rho_pop_path(self) -> Path:
        """rho_pop_3d.npy"""
        return self.processed / "rho_pop_3d.npy"

    @property
    def rho_vehicle_path(self) -> Path:
        """rho_vehicle_3d.npy"""
        return self.processed / "rho_vehicle_3d.npy"

    @property
    def landuse_map_path(self) -> Path:
        """landuse_map.npy"""
        return self.processed / "landuse_map.npy"

    @property
    def building_heights_path(self) -> Path:
        """building_heights.npy"""
        return self.processed / "building_heights.npy"

    @property
    def road_mask_path(self) -> Path:
        """road_mask.npy"""
        return self.processed / "road_mask.npy"

    # ── Raw input files (real data) ─────────────────────────────────────
    @property
    def worldpop_tif_path(self) -> Optional[Path]:
        """WorldPop population GeoTIFF (real only)."""
        candidates = list(self.raw.glob("*worldpop*.tif")) + list(self.raw.glob("*population*.tif"))
        return candidates[0] if candidates else None

    @property
    def osm_poi_geojson_path(self) -> Optional[Path]:
        """OSM POI GeoJSON (real only)."""
        candidates = list(self.raw.glob("*poi*.geojson")) + list(self.raw.glob("*poi*.json"))
        return candidates[0] if candidates else None

    @property
    def landuse_shp_path(self) -> Optional[Path]:
        """Landuse shapefile (real only)."""
        candidates = list(self.raw.glob("*landuse*.shp")) + list(self.raw.glob("*land_use*.shp"))
        return candidates[0] if candidates else None

    @property
    def building_shp_path(self) -> Optional[Path]:
        """Building footprint shapefile (real only)."""
        candidates = list(self.raw.glob("*building*.shp"))
        return candidates[0] if candidates else None

    @property
    def road_shp_path(self) -> Optional[Path]:
        """Road network shapefile (real only)."""
        candidates = list(self.raw.glob("*road*.shp"))
        return candidates[0] if candidates else None

    @property
    def wind_nc_path(self) -> Optional[Path]:
        """Wind field NetCDF (real only)."""
        candidates = list(self.raw.glob("*wind*.nc")) + list(self.raw.glob("*wind*.grib"))
        return candidates[0] if candidates else None

    @property
    def rain_nc_path(self) -> Optional[Path]:
        """Rainfall NetCDF (real only)."""
        candidates = list(self.raw.glob("*rain*.nc")) + list(self.raw.glob("*precip*.nc"))
        return candidates[0] if candidates else None

    # ── Tensor input files (synthetic data) ─────────────────────────────
    @property
    def synthetic_wind_path(self) -> Path:
        """Synthetic wind_field.npy (synthetic only)."""
        return self.tensors / "wind_field.npy"

    @property
    def synthetic_rain_path(self) -> Path:
        """Synthetic rain_data.npy (synthetic only)."""
        return self.tensors / "rain_data.npy"


def set_data_type(data_type: DataType):
    """
    Set the global data type for all subsequent DataProvision operations.
    
    Args:
        data_type: 'synthetic' for synthetic data, 'real' for real data
    """
    global _current_data_type
    if data_type not in ('synthetic', 'real'):
        raise ValueError(f"data_type must be 'synthetic' or 'real', got '{data_type}'")
    _current_data_type = data_type


def get_data_type() -> DataType:
    """Get the current global data type."""
    return _current_data_type


def get_data_paths(data_type: Optional[DataType] = None) -> DataPaths:
    """
    Get the DataPaths for the specified (or current) data type.
    
    Args:
        data_type: If None, uses the current global data type setting.
    
    Returns:
        DataPaths instance with appropriate subdirectories.
    """
    dt = data_type if data_type is not None else _current_data_type
    
    if dt == 'synthetic':
        return DataPaths(
            raw=DATA_ROOT / "01_raw" / "synthetic",
            processed=DATA_ROOT / "02_processed" / "synthetic",
            tensors=DATA_ROOT / "03_tensors" / "synthetic",
            data_type='synthetic',
        )
    else:
        return DataPaths(
            raw=DATA_ROOT / "01_raw",
            processed=DATA_ROOT / "02_processed",
            tensors=DATA_ROOT / "03_tensors",
            data_type='real',
        )


def ensure_dirs(data_type: Optional[DataType] = None):
    """Create all necessary directories for the specified data type."""
    paths = get_data_paths(data_type)
    for d in [paths.raw, paths.processed, paths.tensors]:
        d.mkdir(parents=True, exist_ok=True)
