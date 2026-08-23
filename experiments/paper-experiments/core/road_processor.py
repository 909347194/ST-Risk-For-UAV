"""
Road network data processor.

Handles both real and synthetic road data:
- Real:      Shapefile with road network -> rasterized NumPy mask
- Synthetic: Pre-built .npy from synthetic_data_factory -> validated matrix

Output:
    road_mask.npy  shape (nx, ny), bool (True = road cell)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np

from core.paths import DataPaths, get_data_paths, get_data_type


def load_road_mask(
    paths: Optional[DataPaths] = None,
    grid_nx: Optional[int] = None,
    grid_ny: Optional[int] = None,
) -> np.ndarray:
    """
    Load road mask from the current data type's processed directory.
    
    For synthetic data, reads road_mask.npy directly.
    For real data, attempts to read from processed; if not found,
    tries to rasterize from raw shapefile.
    
    Args:
        paths: DataPaths instance. Uses current global data type if None.
        grid_nx: Grid X size (needed if rasterizing from shapefile).
        grid_ny: Grid Y size (needed if rasterizing from shapefile).
    
    Returns:
        (nx, ny) bool road mask array.
    """
    paths = paths or get_data_paths()
    road_path = paths.road_mask_path

    if road_path.exists():
        return np.load(road_path).astype(np.bool_)

    if get_data_type() == 'synthetic':
        raise FileNotFoundError(
            f"Road mask not found at {road_path}. "
            "Run synthetic_data_factory.export_synthetic_data() first."
        )
    else:
        return _rasterize_road_from_shp(paths, grid_nx, grid_ny)


def _rasterize_road_from_shp(
    paths: DataPaths,
    nx: Optional[int],
    ny: Optional[int],
) -> np.ndarray:
    """
    Rasterize road network shapefile to a grid-aligned boolean mask.
    """
    shp_path = paths.road_shp_path
    if shp_path is None or not shp_path.exists():
        raise FileNotFoundError(
            f"No road shapefile found in {paths.raw}. "
            "Provide a road .shp file or switch to synthetic mode."
        )

    try:
        import geopandas as gpd
        from rasterio.features import rasterize
    except ImportError as e:
        raise ImportError(
            "Rasterizing roads requires geopandas and rasterio. "
            f"Original error: {e}"
        )

    if nx is None or ny is None:
        raise ValueError("grid_nx and grid_ny are required for rasterization.")

    gdf = gpd.read_file(shp_path)
    if gdf.empty:
        raise ValueError(f"Road shapefile is empty: {shp_path}")

    # Determine the road width in pixels (default 1 cell)
    road_width = _estimate_road_width_pixels(gdf, nx, ny)

    transform = _estimate_transform(gdf.total_bounds, nx, ny)
    shapes = [(row.geometry, 1) for _, row in gdf.iterrows() if row.geometry is not None]

    mask = rasterize(
        shapes,
        out_shape=(ny, nx),
        transform=transform,
        fill_value=0,
        dtype=np.uint8,
    )

    # Transpose to (nx, ny) — our convention
    return mask.T.astype(np.bool_)


def _rasterize_road_from_mask(
    paths: DataPaths,
    nx: Optional[int],
    ny: Optional[int],
) -> np.ndarray:
    """
    Fallback: create a simple road grid pattern when no shapefile is available.
    Uses a Manhattan-style grid with main roads every 10 cells.
    """
    mask = np.zeros((nx or 60, ny or 60), dtype=np.bool_)
    nx_, ny_ = mask.shape

    # Main roads every 10 cells
    mask[::10, :] = True
    mask[:, ::10] = True

    # Secondary roads every 5 cells (offset from main)
    mask[5::10, :] = True
    mask[:, 5::10] = True

    paths.processed.mkdir(parents=True, exist_ok=True)
    np.save(paths.road_mask_path, mask)
    return mask


def _estimate_road_width_pixels(gdf, nx: int, ny: int) -> int:
    """Estimate road width in grid cells from shapefile attributes."""
    for col in gdf.columns:
        col_lower = str(col).lower()
        if 'width' in col_lower or 'road_width' in col_lower:
            try:
                avg_width = gdf[col].astype(float).median()
                # Assume ~100m extent and 50m resolution for macro grid
                return max(1, int(avg_width / 50))
            except (ValueError, TypeError):
                pass
    return 1  # default: 1 pixel


def save_road_mask(
    mask: np.ndarray,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save road mask to the processed directory."""
    paths = paths or get_data_paths()
    out_path = paths.road_mask_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, np.asarray(mask, dtype=np.bool_))
    return out_path


def _estimate_transform(bounds, nx: int, ny: int):
    """Estimate affine transform from bounding box and grid dimensions."""
    from rasterio.transform import from_bounds
    minx, miny, maxx, maxy = bounds
    return from_bounds(minx, miny, maxx, maxy, nx, ny)
