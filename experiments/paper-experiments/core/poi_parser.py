"""
OSM/GeoJSON POI (Point of Interest) parser module.

Rasterizes OSM-style POI features into five category count maps:

    residential, office, institution, transport, industrial

Supports both real and synthetic data with automatic path switching:

    Synthetic: data/02_processed/synthetic/poi_counts.npz
    Real:      data/02_processed/poi_counts.npz

Each stored array has shape (NX, NY), aligned with the tensor engine grid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

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
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "02_processed"
DEFAULT_POI_COUNTS_PATH = DEFAULT_PROCESSED_DIR / "poi_counts.npz"

# POI 五大类别定义
POI_CATEGORIES = ("residential", "office", "institution", "transport", "industrial")


def parse_osm_poi_geojson(
    geojson_path: Union[str, Path],
    grid: Optional[GridSystem] = None,
    city_bounds: Optional[Bounds] = None,
    output_path: Optional[Union[str, Path]] = None,
    *,
    source_crs: str = "EPSG:4326",
    bounds_crs: Optional[str] = None,
    save: bool = True,
    paths: Optional[DataPaths] = None,
) -> Dict[str, np.ndarray]:
    """
    Parse an OSM-style GeoJSON file and rasterize POI category counts.

    Uses the current data type's processed directory for output by default.

    Args:
        geojson_path: Path to input .geojson file
        grid: Target grid system, defaults to macro grid
        city_bounds: Optional geographic/projected bounds for coordinate mapping
        output_path: NPZ output path. If None, uses current data type's path
        source_crs: CRS of GeoJSON coordinates
        bounds_crs: CRS of city_bounds. If omitted, assumed same as source_crs
        save: If True, save results to output_path
        paths: DataPaths instance (uses current global data type if None)

    Returns:
        Dict mapping each category to its (nx, ny) count array
    """

    grid = grid or get_macro_grid()
    geojson_path = Path(geojson_path)
    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {geojson_path}")

    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.poi_counts_path

    counts = _empty_counts(grid)

    features_used = False
    try:
        # 尝试使用 geopandas 读取（支持 CRS 转换）
        records = _iter_records_geopandas(
            geojson_path,
            source_crs=source_crs,
            target_crs=bounds_crs or source_crs,
        )
    except ImportError:
        # 如果没有 geopandas，使用纯 JSON 解析
        records = _iter_records_json(geojson_path)

    for x, y, props in records:
        # 根据属性分类 POI
        category = classify_poi(props)
        if category is None:
            continue

        # 将坐标转换为网格索引
        index = coordinate_to_grid_index(x, y, grid, city_bounds=city_bounds)
        if index is None:
            continue

        ix, iy = index
        counts[category][ix, iy] += 1.0
        features_used = True

    if save:
        save_poi_counts(counts, output_path)

    if not features_used:
        print("警告：没有 POI 要素匹配到五个目标类别。")

    return counts


def create_synthetic_poi_counts(
    grid: Optional[GridSystem] = None,
    landuse: Optional[np.ndarray] = None,
    output_path: Optional[Union[str, Path]] = None,
    *,
    save: bool = True,
    paths: Optional[DataPaths] = None,
) -> Dict[str, np.ndarray]:
    """
    Create category count maps from a semantic landuse map.

    This is the synthetic counterpart to parse_osm_poi_geojson().

    Args:
        grid: Target grid, defaults to micro grid
        landuse: 2D landuse array
        output_path: NPZ output path. If None, uses current data type's path
        save: If True, save to output_path
        paths: DataPaths instance (uses current global data type if None)

    Returns:
        Dict with five category count arrays
    """

    grid = grid or get_micro_grid()
    nx, ny = grid.spatial.nx, grid.spatial.ny

    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.poi_counts_path

    if landuse is None:
        # 如果没有提供土地利用数据，使用默认布局
        landuse = _default_landuse_for_poi(nx, ny)
    else:
        landuse = np.asarray(landuse)
        if landuse.shape != (nx, ny):
            raise ValueError(f"landuse 的形状必须为 {(nx, ny)}，实际得到 {landuse.shape}")

    counts = _empty_counts(grid)
    # 根据土地利用类型分配 POI 计数
    counts["residential"][landuse == 1] = 1.0   # 住宅区
    counts["office"][landuse == 2] = 1.0        # 商业/办公区
    counts["institution"][landuse == 3] = 1.0   # 学校/医院等机构
    counts["industrial"][landuse == 4] = 1.0    # 工业区
    counts["transport"][landuse == 5] = 1.0     # 道路/交通设施

    # 添加几个明确的枢纽点，使潮汐模型具有集中的吸引子
    _add_point_if_inside(counts["transport"], nx // 2, ny // 2)      # 交通枢纽
    _add_point_if_inside(counts["office"], nx // 2, ny // 2 + 3)     # 办公中心
    _add_point_if_inside(counts["residential"], nx // 4, ny // 4)    # 住宅热点
    _add_point_if_inside(counts["institution"], max(1, nx // 6), ny // 2)  # 机构中心

    if save:
        save_poi_counts(counts, output_path)

    return counts


def classify_poi(properties: Mapping[str, Any]) -> Optional[str]:
    """
    将 OSM 标签/属性映射到五个聚合 POI 类别之一。

    类别遵循论文文档定义：
    residential（住宅）, office（办公）, institution（机构）, 
    transport（交通）, industrial（工业）

    Args:
        properties: OSM 要素的属性字典（tags）

    Returns:
        类别名称字符串，如果无法分类则返回 None
    """

    # 将所有键值转换为小写字符串，便于匹配
    props = {str(k).lower(): str(v).lower() for k, v in properties.items() if v is not None}

    landuse = props.get("landuse", "")
    building = props.get("building", "")
    amenity = props.get("amenity", "")
    office = props.get("office", "")
    shop = props.get("shop", "")
    railway = props.get("railway", "")
    aeroway = props.get("aeroway", "")
    public_transport = props.get("public_transport", "")
    highway = props.get("highway", "")
    industrial = props.get("industrial", "")

    # 1. 住宅类：住宅用地或住宅建筑
    if landuse == "residential" or building in {"residential", "apartments", "house", "dormitory"}:
        return "residential"

    # 2. 办公类：商业/零售用地、办公场所、商店、部分服务设施
    if (
        landuse in {"commercial", "retail"}
        or office not in {"", "no", "none"}
        or shop not in {"", "no", "none"}
        or amenity in {"bank", "cafe", "restaurant", "marketplace", "clinic"}
    ):
        return "office"

    # 3. 机构类：教育、医疗、政府、公共服务设施
    if amenity in {
        "school",
        "hospital",
        "university",
        "college",
        "kindergarten",
        "library",
        "townhall",
        "police",
        "fire_station",
        "courthouse",
    }:
        return "institution"

    # 4. 交通类：车站、机场、停车场、公交站点等
    if (
        amenity in {"bus_station", "ferry_terminal", "taxi", "parking"}
        or railway in {"station", "halt", "tram_stop", "subway_entrance"}
        or aeroway in {"airport", "terminal", "helipad"}
        or public_transport not in {"", "no", "none"}
        or highway in {"bus_stop", "motorway_junction"}
    ):
        return "transport"

    # 5. 工业类：工业用地、仓库、工厂建筑
    if landuse == "industrial" or building in {"industrial", "warehouse"} or industrial:
        return "industrial"

    # 无法分类
    return None


def coordinate_to_grid_index(
    x: float,
    y: float,
    grid: GridSystem,
    city_bounds: Optional[Bounds] = None,
) -> Optional[Tuple[int, int]]:
    """
    将要素坐标转换为网格索引 (ix, iy)。

    如果提供了 city_bounds，坐标将从边界线性映射到网格范围。
    否则，x/y 被解释为局部投影米坐标。

    Args:
        x: X 坐标
        y: Y 坐标
        grid: 目标网格系统
        city_bounds: 城市边界 (minx, miny, maxx, maxy)

    Returns:
        网格索引元组 (ix, iy)，如果超出范围则返回 None
    """

    nx, ny = grid.spatial.nx, grid.spatial.ny

    if city_bounds is None:
        # 直接使用局部坐标：假设 x/y 已经是米为单位
        ix = int(x / grid.spatial.dx)
        iy = int(y / grid.spatial.dy)
    else:
        # 从城市边界线性映射到网格索引
        minx, miny, maxx, maxy = city_bounds
        if maxx <= minx or maxy <= miny:
            raise ValueError(f"无效的城市边界: {city_bounds}")
        if x < minx or x > maxx or y < miny or y > maxy:
            return None  # 坐标超出边界范围
        ix = int((x - minx) / (maxx - minx) * nx)
        iy = int((y - miny) / (maxy - miny) * ny)

    # 处理边界情况：如果索引等于最大值，减 1 防止越界
    if ix == nx:
        ix = nx - 1
    if iy == ny:
        iy = ny - 1

    # 最终边界检查
    if ix < 0 or ix >= nx or iy < 0 or iy >= ny:
        return None

    return ix, iy


def save_poi_counts(
    counts: Mapping[str, np.ndarray],
    output_path: Optional[Union[str, Path]] = None,
    paths: Optional[DataPaths] = None,
) -> Path:
    """Save POI count rasters to a compressed .npz file."""

    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.poi_counts_path
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {category: np.asarray(counts[category], dtype=np.float32) for category in POI_CATEGORIES}
    arrays["categories"] = np.asarray(POI_CATEGORIES)
    np.savez_compressed(output_path, **arrays)
    return output_path


def load_poi_counts(
    input_path: Optional[Union[str, Path]] = None,
    paths: Optional[DataPaths] = None,
) -> Dict[str, np.ndarray]:
    """Load POI count maps from .npz file."""

    if input_path is None:
        paths = paths or get_data_paths()
        input_path = paths.poi_counts_path
    data = np.load(Path(input_path), allow_pickle=False)
    return {category: data[category].astype(np.float32, copy=False) for category in POI_CATEGORIES}


def build_poi_counts(
    geojson_path: Optional[Union[str, Path]] = None,
    grid: Optional[GridSystem] = None,
    city_bounds: Optional[Bounds] = None,
    landuse: Optional[np.ndarray] = None,
    output_path: Optional[Union[str, Path]] = None,
    *,
    synthetic_if_missing: bool = True,
    paths: Optional[DataPaths] = None,
) -> Dict[str, np.ndarray]:
    """
    Unified entry point for building POI counts.

    If geojson_path exists, parses real OSM/GeoJSON data.
    Otherwise, generates synthetic POI when synthetic_if_missing is True.

    Path switching is automatic based on set_data_type().

    Args:
        geojson_path: GeoJSON file path
        grid: Target grid system
        city_bounds: City bounds
        landuse: Landuse map (synthetic only)
        output_path: Output path (uses current data type if None)
        synthetic_if_missing: Generate synthetic if real data is missing
        paths: DataPaths instance (uses current global data type if None)

    Returns:
        Dict with five category count arrays
    """

    grid = grid or get_macro_grid()

    if output_path is None:
        paths = paths or get_data_paths()
        output_path = paths.poi_counts_path
    output_path = Path(output_path)

    if geojson_path is not None and Path(geojson_path).exists():
        return parse_osm_poi_geojson(
            geojson_path,
            grid=grid,
            city_bounds=city_bounds,
            output_path=output_path,
            paths=paths,
        )

    if synthetic_if_missing:
        return create_synthetic_poi_counts(
            grid=grid,
            landuse=landuse,
            output_path=output_path,
            paths=paths,
        )

    raise FileNotFoundError(f"GeoJSON POI file not available: {geojson_path}")


def _iter_records_geopandas(
    geojson_path: Path,
    *,
    source_crs: str,
    target_crs: str,
) -> Iterable[Tuple[float, float, Dict[str, Any]]]:
    """
    使用 geopandas 迭代 GeoJSON 记录（支持 CRS 转换）。

    Yields:
        (x, y, properties) 元组
    """
    import geopandas as gpd

    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs(source_crs)
    if target_crs is not None and str(gdf.crs) != str(target_crs):
        # 转换到目标 CRS
        gdf = gdf.to_crs(target_crs)

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        # 获取几何体的代表点（对于非点几何体）
        point = geom if geom.geom_type == "Point" else geom.representative_point()
        # 将属性转换为字符串键的字典
        props = {str(k): v for k, v in row.drop(labels=["geometry"]).to_dict().items()}
        yield float(point.x), float(point.y), props


def _iter_records_json(geojson_path: Path) -> Iterable[Tuple[float, float, Dict[str, Any]]]:
    """
    使用纯 JSON 解析迭代 GeoJSON 记录（不依赖 geopandas）。

    Yields:
        (x, y, properties) 元组
    """
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for feature in data.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        point = _representative_xy_from_geojson_geometry(geometry)
        if point is None:
            continue
        yield point[0], point[1], feature.get("properties", {}) or {}


def _representative_xy_from_geojson_geometry(geometry: Mapping[str, Any]) -> Optional[Tuple[float, float]]:
    """
    从 GeoJSON 几何体中提取代表性的 (x, y) 坐标。

    对于点几何体直接返回坐标；对于多边形/线等复杂几何体，
    计算所有坐标点的平均值作为代表点。

    Args:
        geometry: GeoJSON 几何体对象

    Returns:
        (x, y) 元组，如果无法提取则返回 None
    """
    coords = list(_flatten_coordinate_pairs(geometry.get("coordinates")))
    if not coords:
        return None
    arr = np.asarray(coords, dtype=np.float64)
    # 返回所有坐标的平均值
    return float(arr[:, 0].mean()), float(arr[:, 1].mean())


def _flatten_coordinate_pairs(coords: Any) -> Iterable[Tuple[float, float]]:
    """
    递归展平 GeoJSON 嵌套坐标结构为 (x, y) 对列表。

    处理 Point、LineString、Polygon、Multi* 等各种几何体类型。

    Args:
        coords: GeoJSON 坐标数组（可能是嵌套的）

    Yields:
        (x, y) 浮点数元组
    """
    if coords is None:
        return
    # 基础情况：这是一个 (x, y) 对
    if (
        isinstance(coords, (list, tuple))
        and len(coords) >= 2
        and isinstance(coords[0], (int, float))
        and isinstance(coords[1], (int, float))
    ):
        yield float(coords[0]), float(coords[1])
        return
    # 递归情况：遍历嵌套列表
    if isinstance(coords, (list, tuple)):
        for item in coords:
            yield from _flatten_coordinate_pairs(item)


def _empty_counts(grid: GridSystem) -> Dict[str, np.ndarray]:
    """为所有 POI 类别创建空的计数数组。"""
    shape = (grid.spatial.nx, grid.spatial.ny)
    return {category: np.zeros(shape, dtype=np.float32) for category in POI_CATEGORIES}


def _add_point_if_inside(array: np.ndarray, ix: int, iy: int):
    """
    在数组的指定位置增加计数（如果在边界内）。

    Args:
        array: 计数数组
        ix: X 方向索引
        iy: Y 方向索引
    """
    if 0 <= ix < array.shape[0] and 0 <= iy < array.shape[1]:
        array[ix, iy] += 3.0  # 增加权重，形成明显的热点


def _default_landuse_for_poi(nx: int, ny: int) -> np.ndarray:
    """
    符合 POI 验证场景的小型语义城市默认布局。

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
    # 测试代码：生成合成 POI 计数数据
    grid = get_micro_grid()
    counts = create_synthetic_poi_counts(grid=grid)
    print("POI 计数地图:")
    for category in POI_CATEGORIES:
        print(f"  {category:12s}: 形状={counts[category].shape}, 总和={counts[category].sum():.1f}")
    print(f"已保存到: {DEFAULT_POI_COUNTS_PATH}")
