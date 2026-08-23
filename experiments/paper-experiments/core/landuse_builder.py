"""
Landuse data processor.

Handles both real and synthetic landuse data:
- Real:      Shapefile/GeoTIFF -> aligned NumPy matrix
- Synthetic: Pre-built .npy from synthetic_data_factory -> validated matrix

Output:
    landuse_map.npy  shape (nx, ny), int32
    Encoding:
        0 = unassigned/open space
        1 = residential
        2 = commercial/office
        3 = school/hospital (institution)
        4 = industrial
        5 = road/transportation
        6 = green space/water
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np

from core.paths import DataPaths, get_data_paths, get_data_type


def load_landuse_map(
    paths: Optional[DataPaths] = None,
    grid_nx: Optional[int] = None,
    grid_ny: Optional[int] = None,
) -> np.ndarray:
    """
    Load landuse map from the current data type's processed directory.
    
    For synthetic data, reads landuse_map.npy directly.
    For real data, attempts to read from processed; if not found,
    tries to rasterize from raw shapefile.
    
    Args:
        paths: DataPaths instance. Uses current global data type if None.
        grid_nx: Grid X size (needed if rasterizing from shapefile).
        grid_ny: Grid Y size (needed if rasterizing from shapefile).
    
    Returns:
        (nx, ny) int32 landuse array.
    """
    paths = paths or get_data_paths()
    landuse_path = paths.landuse_map_path

    if landuse_path.exists():
        return np.load(landuse_path).astype(np.int32)

    # If not found in processed, try to build from raw data
    if get_data_type() == 'synthetic':
        raise FileNotFoundError(
            f"Landuse map not found at {landuse_path}. "
            "Run synthetic_data_factory.export_synthetic_data() first."
        )
    else:
        # Real data: rasterize from shapefile
        return _rasterize_landuse_from_shp(paths, grid_nx, grid_ny)


def _rasterize_landuse_from_shp(
    paths: DataPaths,
    nx: Optional[int],
    ny: Optional[int],
) -> np.ndarray:
    """
    Rasterize landuse shapefile to a grid-aligned NumPy matrix.
    
    Uses rasterio.features.rasterize to burn shapefile attributes
    into the target grid.
    """
    shp_path = paths.landuse_shp_path
    if shp_path is None or not shp_path.exists():
        raise FileNotFoundError(
            f"No landuse shapefile found in {paths.raw}. "
            "Provide a landuse .shp file or switch to synthetic mode."
        )

    try:
        import geopandas as gpd
        from rasterio.features import rasterize
    except ImportError as e:
        raise ImportError(
            "Rasterizing landuse requires geopandas and rasterio. "
            f"Install missing packages. Original error: {e}"
        )

    if nx is None or ny is None:
        raise ValueError("grid_nx and grid_ny are required for rasterization.")

    gdf = gpd.read_file(shp_path)
    if gdf.empty:
        raise ValueError(f"Landuse shapefile is empty: {shp_path}")

    # Determine landuse attribute column
    lu_col = _find_landuse_column(gdf)

    # Build (geometry, value) pairs for rasterization
    shapes = []
    for _, row in gdf.iterrows():
        val = _map_landuse_code(row[lu_col])
        if val is not None and row.geometry is not None:
            shapes.append((row.geometry, val))

    # Rasterize: output shape (ny, nx) — GIS convention (rows, cols)
    transform = _estimate_transform(gdf.total_bounds, nx, ny)
    out = rasterize(
        shapes,
        out_shape=(ny, nx),
        transform=transform,
        fill_value=0,
        dtype=np.int32,
    )

    # Transpose to (nx, ny) — our convention
    landuse = out.T.copy()

    # Save for future use
    paths.processed.mkdir(parents=True, exist_ok=True)
    np.save(paths.landuse_map_path, landuse)
    return landuse


def _find_landuse_column(gdf) -> str:
    """Find the column name that contains landuse classification."""
    candidates = ['landuse', 'land_use', 'lu_code', 'lu', 'type', 'category', 'class']
    for col in gdf.columns:
        if str(col).lower().replace(' ', '_') in candidates:
            return col
    # Fallback to first non-geometry column
    geom_types = gdf.geometry.geom_type
    for col in gdf.columns:
        if col != 'geometry' and col != gdf.geometry.name:
            return col
    raise ValueError("Could not identify landuse column in shapefile.")


def _map_landuse_code(raw_value) -> Optional[int]:
    """Map raw shapefile attribute to our standard landuse encoding."""
    val = str(raw_value).strip().lower()
    mapping = {
        '1': 1, 'residential': 1, '住宅': 1,
        '2': 2, 'commercial': 2, 'retail': 2, 'office': 2, '商业': 2,
        '3': 3, 'school': 3, 'hospital': 3, 'institution': 3, 'education': 3, '医疗': 3,
        '4': 4, 'industrial': 4, 'manufacturing': 4, '工业': 4,
        '5': 5, 'road': 5, 'transport': 5, '交通': 5,
        '6': 6, 'green': 6, 'park': 6, 'water': 6, '绿地': 6,
    }
    return mapping.get(val)


def _estimate_transform(bounds, nx: int, ny: int):
    """
    Estimate affine transform from bounding box and grid dimensions.
    Uses rasterio.transform.from_bounds.
    """
    from rasterio.transform import from_bounds
    minx, miny, maxx, maxy = bounds
    return from_bounds(minx, miny, maxx, maxy, nx, ny)


def save_landuse_map(
    landuse: np.ndarray,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save landuse map to the processed directory."""
    paths = paths or get_data_paths()
    out_path = paths.landuse_map_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, np.asarray(landuse, dtype=np.int32))
    return out_path
