"""
Weather data processor (wind & precipitation).

Handles both real and synthetic weather data:
- Real:      ERA5 NetCDF -> grid-aligned NumPy matrices
- Synthetic: Pre-built .npy from synthetic_data_factory -> validated matrices

Output:
    wind_field.npy  shape (nx, ny, nt), float32 (wind speed in m/s)
    rain_data.npy   shape (nx, ny, nt), float32 (rain intensity in mm/h)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np

from core.paths import DataPaths, get_data_paths, get_data_type


def load_wind_field(
    paths: Optional[DataPaths] = None,
    grid_nx: Optional[int] = None,
    grid_ny: Optional[int] = None,
    grid_nt: Optional[int] = None,
) -> np.ndarray:
    """
    Load wind field data from the current data type.
    
    For synthetic data, reads wind_field.npy from 03_tensors/synthetic/.
    For real data, reads from processed or raw ERA5 NetCDF.
    
    Args:
        paths: DataPaths instance. Uses current global data type if None.
        grid_nx: Grid X size (for real data interpolation).
        grid_ny: Grid Y size (for real data interpolation).
        grid_nt: Number of time steps (for real data interpolation).
    
    Returns:
        (nx, ny, nt) float32 wind speed array (m/s).
    """
    paths = paths or get_data_paths()

    if get_data_type() == 'synthetic':
        return _load_synthetic_wind(paths)
    else:
        return _load_real_wind(paths, grid_nx, grid_ny, grid_nt)


def _load_synthetic_wind(paths: DataPaths) -> np.ndarray:
    """Load pre-generated synthetic wind field from tensors directory."""
    wind_path = paths.synthetic_wind_path
    if not wind_path.exists():
        raise FileNotFoundError(
            f"Synthetic wind field not found at {wind_path}. "
            "Run synthetic_data_factory.export_synthetic_data() first."
        )
    return np.load(wind_path).astype(np.float32)


def _load_real_wind(
    paths: DataPaths,
    nx: Optional[int],
    ny: Optional[int],
    nt: Optional[int],
) -> np.ndarray:
    """
    Load and process real ERA5 wind data from NetCDF files.
    
    Reads wind components (u10, v10) and computes speed.
    Interpolates to the target grid if needed.
    """
    nc_path = paths.wind_nc_path
    if nc_path is None or not nc_path.exists():
        raise FileNotFoundError(
            f"No wind NetCDF file found in {paths.raw}. "
            "Provide ERA5 .nc data or switch to synthetic mode."
        )

    try:
        import xarray as xr
    except ImportError as e:
        raise ImportError(
            "Processing real wind data requires xarray. "
            f"Original error: {e}"
        )

    ds = xr.open_dataset(nc_path)

    # Compute wind speed from u10/v10 components
    if 'u10' in ds and 'v10' in ds:
        wspd = np.sqrt(ds['u10'].values ** 2 + ds['v10'].values ** 2)
    elif 'wind_speed' in ds:
        wspd = ds['wind_speed'].values
    elif 'si10' in ds:
        wspd = ds['si10'].values  # ERA5 instantaneous 10m wind gust
    else:
        raise KeyError(
            f"Could not find wind variables in {nc_path}. "
            f"Available: {list(ds.data_vars)}"
        )

    # Convert to float32 and squeeze extra dimensions
    wspd = np.nan_to_num(np.asarray(wspd, dtype=np.float32), nan=0.0)

    # If the data has spatial coords, interpolate to target grid
    if nx is not None and ny is not None and wspd.ndim >= 2:
        wspd = _interpolate_to_grid(wspd, nx, ny, ds)

    # If the data has time dimension, match nt
    if nt is not None and wspd.shape[-1] != nt:
        wspd = _resample_time(wspd, nt)

    # Ensure 3D shape (nx, ny, nt)
    if wspd.ndim == 2:
        if nt is not None:
            wspd = np.tile(wspd[:, :, np.newaxis], (1, 1, nt))
        else:
            wspd = wspd[:, :, np.newaxis]

    return wspd


def load_rain_data(
    paths: Optional[DataPaths] = None,
    grid_nx: Optional[int] = None,
    grid_ny: Optional[int] = None,
    grid_nt: Optional[int] = None,
) -> np.ndarray:
    """
    Load precipitation data from the current data type.
    
    For synthetic data, reads rain_data.npy from 03_tensors/synthetic/.
    For real data, reads from raw ERA5 NetCDF.
    
    Args:
        paths: DataPaths instance. Uses current global data type if None.
        grid_nx: Grid X size (for real data interpolation).
        grid_ny: Grid Y size (for real data interpolation).
        grid_nt: Number of time steps (for real data interpolation).
    
    Returns:
        (nx, ny, nt) float32 rain intensity array (mm/h).
    """
    paths = paths or get_data_paths()

    if get_data_type() == 'synthetic':
        return _load_synthetic_rain(paths)
    else:
        return _load_real_rain(paths, grid_nx, grid_ny, grid_nt)


def _load_synthetic_rain(paths: DataPaths) -> np.ndarray:
    """Load pre-generated synthetic rain data from tensors directory."""
    rain_path = paths.synthetic_rain_path
    if not rain_path.exists():
        raise FileNotFoundError(
            f"Synthetic rain data not found at {rain_path}. "
            "Run synthetic_data_factory.export_synthetic_data() first."
        )
    return np.load(rain_path).astype(np.float32)


def _load_real_rain(
    paths: DataPaths,
    nx: Optional[int],
    ny: Optional[int],
    nt: Optional[int],
) -> np.ndarray:
    """
    Load and process real ERA5 precipitation data from NetCDF.
    """
    nc_path = paths.rain_nc_path
    if nc_path is None or not nc_path.exists():
        raise FileNotFoundError(
            f"No precipitation NetCDF file found in {paths.raw}. "
            "Provide ERA5 .nc data or switch to synthetic mode."
        )

    try:
        import xarray as xr
    except ImportError as e:
        raise ImportError(
            "Processing real rain data requires xarray. "
            f"Original error: {e}"
        )

    ds = xr.open_dataset(nc_path)

    # Find precipitation variable
    rain_var = None
    for candidate in ['tp', 'precip', 'precipitation', 'rain', 'rainfall', 'pr']:
        if candidate in ds:
            rain_var = candidate
            break

    if rain_var is None:
        raise KeyError(
            f"Could not find precipitation variable in {nc_path}. "
            f"Available: {list(ds.data_vars)}"
        )

    rain = ds[rain_var].values

    # ERA5 total precipitation is in meters, convert to mm/h
    if rain_var == 'tp':
        rain = rain * 1000.0  # m -> mm

    rain = np.nan_to_num(np.asarray(rain, dtype=np.float32), nan=0.0)

    # Interpolate spatially
    if nx is not None and ny is not None and rain.ndim >= 2:
        rain = _interpolate_to_grid(rain, nx, ny, ds)

    # Resample temporally
    if nt is not None and rain.shape[-1] != nt:
        rain = _resample_time(rain, nt)

    # Ensure 3D shape (nx, ny, nt)
    if rain.ndim == 2:
        if nt is not None:
            rain = np.tile(rain[:, :, np.newaxis], (1, 1, nt))
        else:
            rain = rain[:, :, np.newaxis]

    return rain


def _interpolate_to_grid(
    data: np.ndarray,
    nx: int,
    ny: int,
    dataset,
) -> np.ndarray:
    """
    Simple bilinear-like interpolation to target grid.
    Uses scipy for interpolation if available.
    """
    try:
        from scipy.interpolate import RegularGridInterpolator
    except ImportError:
        # Fallback: simple slice/average if no scipy
        return data

    # Determine spatial dimensions
    if data.ndim == 3:
        # Assume (lat, lon, time) or (y, x, t)
        h, w = data.shape[0], data.shape[1]
    else:
        h, w = data.shape

    # Create original coordinate grid
    x_orig = np.linspace(0, 1, w)
    y_orig = np.linspace(0, 1, h)
    x_target = np.linspace(0, 1, nx)
    y_target = np.linspace(0, 1, ny)

    if data.ndim == 3:
        result = np.zeros((nx, ny, data.shape[2]), dtype=np.float32)
        for t in range(data.shape[2]):
            interp = RegularGridInterpolator((y_orig, x_orig), data[:, :, t])
            X, Y = np.meshgrid(x_target, y_target, indexing='ij')
            result[:, :, t] = interp((Y, X))
        return result
    else:
        interp = RegularGridInterpolator((y_orig, x_orig), data)
        X, Y = np.meshgrid(x_target, y_target, indexing='ij')
        return interp((Y, X)).astype(np.float32)


def _resample_time(data: np.ndarray, target_nt: int) -> np.ndarray:
    """
    Resample time dimension to match target number of steps.
    Uses linear interpolation.
    """
    if data.ndim < 3:
        return data

    current_nt = data.shape[-1]
    if current_nt == target_nt:
        return data

    from scipy.interpolate import interp1d

    x_old = np.linspace(0, 1, current_nt)
    x_new = np.linspace(0, 1, target_nt)

    # Reshape to (nx*ny, nt) for 1D interpolation
    ny_, nx_ = data.shape[0], data.shape[1]
    flat = data.reshape(-1, current_nt)

    f = interp1d(x_old, flat, kind='linear', axis=1, bounds_error=False, fill_value=0.0)
    resampled = f(x_new).astype(np.float32)

    return resampled.reshape(ny_, nx_, target_nt)


def save_wind_field(
    wind: np.ndarray,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save wind field to the tensors directory."""
    paths = paths or get_data_paths()
    out_path = paths.tensors / "wind_field.npy"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, np.asarray(wind, dtype=np.float32))
    return out_path


def save_rain_data(
    rain: np.ndarray,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save rain data to the tensors directory."""
    paths = paths or get_data_paths()
    out_path = paths.tensors / "rain_data.npy"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, np.asarray(rain, dtype=np.float32))
    return out_path
