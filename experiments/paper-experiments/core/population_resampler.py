"""
Population data processor (WorldPop / synthetic base population).

Converts raw population data into the unified 2D grid format used by the
spatiotemporal risk tensor engine:

    rho_base[x, y] -> shape (NX, NY)

Supports two workflows with automatic path switching:
1. Real data:     Use rasterio to clip and resample WorldPop GeoTIFF raster
2. Synthetic data: Generate semantically-consistent base population from landuse

Path output (automatic based on set_data_type()):
    Synthetic: data/02_processed/synthetic/base_pop_2d.npy
    Real:      data/02_processed/base_pop_2d.npy
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np

try:
    from core.grid_system import GridSystem, get_macro_grid, get_micro_grid
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.grid_system import GridSystem, get_macro_grid, get_micro_grid

from core.paths import DataPaths, get_data_paths, get_data_type, set_data_type

Bounds = Tuple[float, float, float, float]  # Bounds: minx, miny, maxx, maxy

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Backward-compatible constants (real data paths by default)
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "02_processed"
DEFAULT_BASE_POP_PATH = DEFAULT_PROCESSED_DIR / "base_pop_2d.npy"


def resample_worldpop_to_grid(
    tif_path: Union[str, Path],
    grid: Optional[GridSystem] = None,
    city_bounds: Optional[Bounds] = None,
    output_path: Optional[Union[str, Path]] = None,
    *,
    bounds_crs: Optional[str] = None,
    resampling: str = "bilinear",
    flip_y: bool = True,
    preserve_total: bool = False,
    save: bool = True,
    paths: Optional[DataPaths] = None,
) -> np.ndarray:
    """
    Clip and resample a WorldPop GeoTIFF to the target grid.

    Uses the current data type's processed directory for output by default.
    Call set_data_type('real') or set_data_type('synthetic') to switch.

    Args:
        tif_path: Path to WorldPop .tif raster file
        grid: Target grid system, defaults to macro grid
        city_bounds: Optional clipping bounds (minx, miny, maxx, maxy)
        output_path: NPY output path. If None, uses the current data type's path
        bounds_crs: CRS of city_bounds, e.g. "EPSG:4326"
        resampling: Resampling method: nearest, bilinear, cubic, average
        flip_y: Flip raster rows so y-index 0 corresponds to the southern side
        preserve_total: Scale resampled map to preserve total population
        save: If True, save to output_path
        paths: DataPaths instance (uses current global data type if None)

    Returns:
        (nx, ny) float32 array
    """

    grid = grid or get_macro_grid()
    tif_path = Path(tif_path)
    if not tif_path.exists():
        raise FileNotFoundError(f"WorldPop raster not found: {tif_path}")

    # Use data-type-aware path if output_path not specified
    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.base_pop_path
    output_path = Path(output_path)

    try:
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds
    except ImportError as exc:
        raise ImportError(
            "resample_worldpop_to_grid requires rasterio. "
            "Install rasterio or use create_synthetic_base_population()."
        ) from exc

    resampling_method = _get_rasterio_resampling(Resampling, resampling)
    nx, ny = grid.spatial.nx, grid.spatial.ny

    with rasterio.open(tif_path) as src:
        read_kwargs = {
            "indexes": 1,
            "out_shape": (ny, nx),
            "resampling": resampling_method,
            "masked": True,
        }

        source_for_sum = None
        if city_bounds is not None:
            # 如果提供了城市边界，先进行裁剪
            bounds = city_bounds
            if bounds_crs is not None and src.crs is not None:
                # 如果边界 CRS 与栅格 CRS 不同，进行坐标转换
                bounds = transform_bounds(bounds_crs, src.crs, *city_bounds)
            window = from_bounds(*bounds, transform=src.transform)
            read_kwargs["window"] = window
            if preserve_total:
                # 如果需要保持总人口数，读取裁剪区域用于后续计算
                source_for_sum = src.read(1, window=window, masked=True)
        elif preserve_total:
            # 如果没有指定边界但需要保持总人口，读取整个栅格
            source_for_sum = src.read(1, masked=True)

        data = src.read(**read_kwargs)

    # 将掩码数组转换为普通数组，填充值为 0.0
    arr = np.asarray(data.filled(0.0), dtype=np.float64)
    # 处理 NaN 和无穷大值
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    # 确保所有值为非负数
    arr[arr < 0] = 0.0

    if preserve_total and source_for_sum is not None:
        # 保持总人口数守恒：计算源数据和目标数据的总和比例
        source_sum = float(np.asarray(source_for_sum.filled(0.0)).sum())
        target_sum = float(arr.sum())
        if source_sum > 0 and target_sum > 0:
            # 按比例缩放，使重采样后的人口总数与原始数据一致
            arr *= source_sum / target_sum

    if flip_y:
        # 翻转 Y 轴以匹配局部网格约定（y-index 0 对应南侧）
        arr = arr[::-1, :]

    # rasterio 返回 (rows_y, cols_x)；张量约定是 (x, y)，因此需要转置
    base_pop = arr.T.astype(np.float32, copy=False)
    _validate_grid_shape(base_pop, grid)

    if save:
        save_base_population(base_pop, output_path)

    return base_pop


def create_synthetic_base_population(
    grid: Optional[GridSystem] = None,
    landuse: Optional[np.ndarray] = None,
    output_path: Optional[Union[str, Path]] = None,
    *,
    save: bool = True,
    paths: Optional[DataPaths] = None,
) -> np.ndarray:
    """
    Create a semantically-consistent base population map for micro-validation.

    Landuse-driven population density rules:
        residential > commercial/school > industrial > road > green/water.
    Gaussian hotspots add meaningful gradients for path planning experiments.

    Args:
        grid: Target grid, defaults to micro grid
        landuse: 2D landuse array (1=residential, 2=commercial, 3=institution,
                 4=industrial, 5=road, 6=green/water, 0=unassigned)
        output_path: NPY output path. If None, uses current data type's path.
        save: If True, save to output_path
        paths: DataPaths instance (uses current global data type if None)

    Returns:
        (nx, ny) float32 array
    """

    grid = grid or get_micro_grid()
    nx, ny = grid.spatial.nx, grid.spatial.ny

    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.base_pop_path
    output_path = Path(output_path)

    if landuse is None:
        # 如果没有提供土地利用数据，使用默认的城市布局
        landuse = _default_landuse_for_population(nx, ny)
    else:
        landuse = np.asarray(landuse)
        if landuse.shape != (nx, ny):
            raise ValueError(f"landuse 的形状必须为 {(nx, ny)}，实际得到 {landuse.shape}")

    # 初始化基础人口数组
    base = np.zeros((nx, ny), dtype=np.float64)

    # 每个输出单元的人数，用作后续张量模块中的密度代理
    base[landuse == 1] = 80.0    # 住宅区：高密度
    base[landuse == 2] = 65.0    # 商业/办公区：中高密度
    base[landuse == 3] = 45.0    # 学校/医院：中等密度
    base[landuse == 4] = 18.0    # 工业区：低密度
    base[landuse == 5] = 25.0    # 道路/交通/商业前沿：中低密度
    base[landuse == 6] = 2.0     # 绿地/水域：极低密度
    base[landuse == 0] = 5.0     # 未指定/开放空间：低密度

    # 创建坐标网格用于计算高斯热点
    x = np.arange(nx)
    y = np.arange(ny)
    X, Y = np.meshgrid(x, y, indexing="ij")

    # 定义热点参数：(中心x, 中心y, 振幅, 标准差)
    hotspots = [
        (0.25 * nx, 0.25 * ny, 45.0, 7.0),  # 住宅区中心热点
        (0.50 * nx, 0.50 * ny, 55.0, 5.0),  # 商业中心热点
        (0.25 * nx, 0.15 * ny, 30.0, 4.0),  # 学校/医院中心热点
    ]
    for cx, cy, amplitude, sigma in hotspots:
        # 计算每个位置到热点中心的距离平方
        dist_sq = (X - cx) ** 2 + (Y - cy) ** 2
        # 添加高斯分布的人口密度增量
        base += amplitude * np.exp(-dist_sq / (2 * sigma ** 2))

    # 确保所有值为非负数，并转换为 float32
    base = np.clip(base, 0.0, None).astype(np.float32)

    if save:
        save_base_population(base, output_path)

    return base


def save_base_population(
    base_population: np.ndarray,
    output_path: Optional[Union[str, Path]] = None,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save base population array as .npy and return path."""

    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.base_pop_path
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, np.asarray(base_population, dtype=np.float32))
    return output_path


def load_base_population(
    input_path: Optional[Union[str, Path]] = None,
    paths: Optional[DataPaths] = None,
) -> np.ndarray:
    """Load processed base population from .npy file."""

    if input_path is None:
        paths = paths or get_data_paths()
        input_path = paths.base_pop_path
    return np.load(Path(input_path)).astype(np.float32, copy=False)


def build_base_population(
    worldpop_tif: Optional[Union[str, Path]] = None,
    grid: Optional[GridSystem] = None,
    city_bounds: Optional[Bounds] = None,
    landuse: Optional[np.ndarray] = None,
    output_path: Optional[Union[str, Path]] = None,
    *,
    synthetic_if_missing: bool = True,
    paths: Optional[DataPaths] = None,
) -> np.ndarray:
    """
    Unified entry point for building base population.

    If worldpop_tif is provided and exists, processes real data.
    Otherwise, generates synthetic data when synthetic_if_missing is True.

    Path switching is automatic based on set_data_type().

    Args:
        worldpop_tif: WorldPop GeoTIFF path
        grid: Target grid system
        city_bounds: City bounds
        landuse: Landuse map (synthetic only)
        output_path: Output path (uses current data type if None)
        synthetic_if_missing: Generate synthetic data if real is missing
        paths: DataPaths instance (uses current global data type if None)

    Returns:
        Base population array
    """

    grid = grid or get_macro_grid()

    # Determine output path based on data type
    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.base_pop_path
    output_path = Path(output_path)

    if worldpop_tif is not None and Path(worldpop_tif).exists():
        return resample_worldpop_to_grid(
            worldpop_tif,
            grid=grid,
            city_bounds=city_bounds,
            output_path=output_path,
            paths=paths,
        )

    if synthetic_if_missing:
        return create_synthetic_base_population(
            grid=grid,
            landuse=landuse,
            output_path=output_path,
            paths=paths,
        )

    raise FileNotFoundError(f"WorldPop raster not available: {worldpop_tif}")


def _get_rasterio_resampling(resampling_enum, name: str):
    """获取 rasterio 的重采样方法枚举值。"""

    normalized = name.lower()
    if not hasattr(resampling_enum, normalized):
        valid = [item for item in ("nearest", "bilinear", "cubic", "average")]
        raise ValueError(f"不支持的重采样方法 '{name}'。请使用以下之一: {valid}.")
    return getattr(resampling_enum, normalized)


def _validate_grid_shape(array: np.ndarray, grid: GridSystem):
    """验证数组形状是否与网格系统匹配。"""

    expected = (grid.spatial.nx, grid.spatial.ny)
    if array.shape != expected:
        raise ValueError(f"期望数组形状为 {expected}，实际得到 {array.shape}。")


def _default_landuse_for_population(nx: int, ny: int) -> np.ndarray:
    """
    符合微观验证场景的小型语义城市默认布局。

    创建一个简化的城市结构：
    - 左上象限：住宅区
    - 中心附近：商业区
    - 上部中间：学校/医院
    - 右下象限：工业区
    - 中部横条：道路
    - 右下角：绿地/水域

    Args:
        nx: 网格 X 方向大小
        ny: 网格 Y 方向大小

    Returns:
        二维土地利用数组
    """

    landuse = np.zeros((nx, ny), dtype=np.int32)
    landuse[: nx // 2, : ny // 2] = 1  # 左上象限：住宅区
    landuse[nx // 2 - 5: nx // 2 + 5, ny // 2 - 5: ny // 2 + 5] = 2  # 中心：商业区
    landuse[: max(4, nx // 6), ny // 2 - 5: ny // 2 + 5] = 3  # 上部中间：学校/医院
    landuse[nx // 2:, ny // 2:] = 4  # 右下象限：工业区
    landuse[nx // 2 - 2: nx // 2 + 2, :] = 5  # 中部横条：道路
    landuse[-5:, -5:] = 6  # 右下角：绿地/水域
    return landuse


if __name__ == "__main__":
    # 测试代码：生成合成基础人口数据
    grid = get_micro_grid()
    base_pop = create_synthetic_base_population(grid=grid)
    print(f"base_pop 形状: {base_pop.shape}")
    print(f"base_pop 范围: [{base_pop.min():.2f}, {base_pop.max():.2f}]")
    print(f"已保存到: {DEFAULT_BASE_POP_PATH}")
