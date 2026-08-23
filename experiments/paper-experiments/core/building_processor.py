"""
Building height data processor.

Handles both real and synthetic building data:
- Real:      Shapefile with building footprints + height attributes -> aligned NumPy matrix
- Synthetic: Pre-built .npy from synthetic_data_factory -> validated matrix

Output:
    building_heights.npy  shape (nx, ny), float32 (height in meters)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np

from core.paths import DataPaths, get_data_paths, get_data_type
from core.landuse_builder import load_landuse_map


def load_building_heights(
    paths: Optional[DataPaths] = None,
    grid_nx: Optional[int] = None,
    grid_ny: Optional[int] = None,
    landuse: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Load building heights from the current data type's processed directory.
    
    For synthetic data, reads building_heights.npy directly.
    For real data, attempts to read from processed; if not found,
    tries to rasterize from raw shapefile.
    
    Args:
        paths: DataPaths instance. Uses current global data type if None.
        grid_nx: Grid X size (needed if rasterizing from shapefile).
        grid_ny: Grid Y size (needed if rasterizing from shapefile).
        landuse: Landuse map (used as fallback for synthetic estimation).
    
    Returns:
        (nx, ny) float32 building heights array.
    """
    paths = paths or get_data_paths()
    bldg_path = paths.building_heights_path

    if bldg_path.exists():
        return np.load(bldg_path).astype(np.float32)

    if get_data_type() == 'synthetic':
        raise FileNotFoundError(
            f"Building heights not found at {bldg_path}. "
            "Run synthetic_data_factory.export_synthetic_data() first."
        )
    else:
        return _rasterize_buildings_from_shp(paths, grid_nx, grid_ny)


def _rasterize_buildings_from_shp(
    paths: DataPaths,
    nx: Optional[int],
    ny: Optional[int],
) -> np.ndarray:
    """
    Rasterize building footprint shapefile to a grid-aligned NumPy matrix.
    
    Each grid cell records the maximum building height in that cell.
    """
    shp_path = paths.building_shp_path
    if shp_path is None or not shp_path.exists():
        raise FileNotFoundError(
            f"No building shapefile found in {paths.raw}. "
            "Provide a building .shp file or switch to synthetic mode."
        )

    try:
        import geopandas as gpd
        from rasterio.features import rasterize
    except ImportError as e:
        raise ImportError(
            "Rasterizing buildings requires geopandas and rasterio. "
            f"Original error: {e}"
        )

    if nx is None or ny is None:
        raise ValueError("grid_nx and grid_ny are required for rasterization.")

    gdf = gpd.read_file(shp_path)
    if gdf.empty:
        raise ValueError(f"Building shapefile is empty: {shp_path}")

    # Determine height column
    height_col = _find_height_column(gdf)
    default_height = gdf[height_col].median() if height_col else 15.0

    # Rasterize building footprints with heights
    transform = _estimate_transform(gdf.total_bounds, nx, ny)
    
    # Method: rasterize with merge strategy to keep max height per cell
    shapes = []
    for _, row in gdf.iterrows():
        if row.geometry is None:
            continue
        h = float(row[height_col]) if height_col else default_height
        shapes.append((row.geometry, h))

    # First pass: rasterize all buildings with a simple merge
    heights = rasterize(
        shapes,
        out_shape=(ny, nx),
        transform=transform,
        fill_value=0.0,
        dtype=np.float32,
        merge_alg=rasterize.MergeAlg.replace,
    )

    # If we have overlapping polygons, use max merge
    try:
        heights = rasterize(
            shapes,
            out_shape=(ny, nx),
            transform=transform,
            fill_value=0.0,
            dtype=np.float32,
            merge_alg=rasterize.MergeAlg.max,
        )
    except (ValueError, TypeError):
        pass  # fallback to basic rasterization

    # Transpose to (nx, ny) — our convention
    heights = heights.T.copy()

    # Save for future use
    paths.processed.mkdir(parents=True, exist_ok=True)
    np.save(paths.building_heights_path, heights)
    return heights


def estimate_building_heights_from_landuse(
    landuse: np.ndarray,
    paths: Optional[DataPaths] = None,
    *,
    save: bool = True,
) -> np.ndarray:
    """
    Generate an approximate building height map from landuse data.
    Useful when no building footprint data is available.
    
    Height rules:
        residential:  12-20m (4-6 floors)
        commercial:   20-40m (6-12 floors)
        institution:  15-25m (4-8 floors)
        industrial:   8-15m  (2-4 floors)
        road:         0m
        green/water:  0m
        unassigned:   0m
    """
    heights = np.zeros(landuse.shape, dtype=np.float32)
    rng = np.random.RandomState(42)

    # Assign base heights per landuse category
    heights[landuse == 1] = 15.0   # residential
    heights[landuse == 2] = 30.0   # commercial
    heights[landuse == 3] = 20.0   # institution
    heights[landuse == 4] = 10.0   # industrial
    # landuse 5 (road), 6 (green), 0 (unassigned) remain 0

    # Add small random variation
    mask = heights > 0
    heights[mask] += rng.uniform(-2, 5, size=mask.sum()).astype(np.float32)
    heights = np.clip(heights, 0, None)

    if save:
        paths = paths or get_data_paths()
        out_path = paths.building_heights_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(out_path, heights)

    return heights


def save_building_heights(
    heights: np.ndarray,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save building heights to the processed directory."""
    paths = paths or get_data_paths()
    out_path = paths.building_heights_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, np.asarray(heights, dtype=np.float32))
    return out_path


def _find_height_column(gdf) -> Optional[str]:
    """Find the column name that contains building height information."""
    candidates = [
        'height', 'building_height', 'bldg_height', 'h', 'height_m',
        'height_roof', 'roof_height', '楼层', '层数', 'floors',
        'num_floors', 'storeys',
    ]
    for col in gdf.columns:
        col_lower = str(col).lower().replace(' ', '_')
        if col_lower in candidates:
            return col
    return None


def _estimate_transform(bounds, nx: int, ny: int):
    """Estimate affine transform from bounding box and grid dimensions."""
    from rasterio.transform import from_bounds
    minx, miny, maxx, maxy = bounds
    return from_bounds(minx, miny, maxx, maxy, nx, ny)
