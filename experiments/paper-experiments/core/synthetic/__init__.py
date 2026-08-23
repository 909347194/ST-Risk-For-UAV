"""
合成数据工厂 - 主入口模块

整合所有数据生成模块，提供统一的API接口。

数据生成流程（严格约束）：
1. 土地利用 (01_landuse) → 基础母图（确定性）
2. 道路网络 (02_road) → 基于土地利用（确定性）
3. 建筑高度 (03_building) → 基于土地利用 + 道路掩码（随机，seed）
4. POI密度 (04_poi) → 基于土地利用 + 建筑高度（随机，seed+1000）
5. 人口密度 (05_population) → 基于土地利用 + POI（确定性）
6. 气象数据 (06_weather) → 风场和降雨（随机，seed+3000/4000）
7. OD对 (07_od_pairs) → 独立生成起点终点（随机，seed+2000）
8. 数据校验 (08_validation) → 验证所有约束（确定性）

可复现性控制策略：
- 所有包含随机性的模块均支持 seed 参数
- 使用局部随机状态对象（np.random.RandomState），避免全局污染
- 不同子模块通过种子偏移量确保统计独立性
- 相同 seed 值保证每次生成完全一致的数据

使用示例：
    from synthetic_data_factory import generate_synthetic_city
    
    # 确定性模式：相同种子产生相同结果
    data = generate_synthetic_city(nx=60, ny=60, nz=12, nt=96, seed=42)
    
    # 敏感性分析：不同种子产生不同扰动场景
    for s in [42, 123, 456]:
        data = generate_synthetic_city(nx=60, ny=60, nz=12, nt=96, seed=s)
"""

import numpy as np
from typing import Dict, Any, Optional, Union
from pathlib import Path
import importlib
import datetime
import json

# 可选依赖导入
try:
    import rasterio
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    import geopandas as gpd
    from shapely.geometry import Point, LineString
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

HAS_GIS_LIBS = HAS_RASTERIO and HAS_GEOPANDAS

# 导入各数据层生成函数
from core.synthetic import landuse as _landuse
from core.synthetic import road as _road
from core.synthetic import building as _building
from core.synthetic import poi as _poi
from core.synthetic import population as _population
from core.synthetic import weather as _weather
from core.synthetic import od_pairs as _od_pairs
from core.synthetic import validation as _validation

# 提取函数
create_landuse_master_plan = _landuse.create_landuse_master_plan
create_road_network = _road.create_road_network
create_buildings_conditioned_on_landuse = _building.create_buildings_conditioned_on_landuse
create_poi_from_landuse = _poi.create_poi_from_landuse
create_population_static = _population.create_population_static
create_wind_field = _weather.create_wind_field
create_rain_field = _weather.create_rain_field
create_od_pairs = _od_pairs.create_od_pairs
validate_synthetic_city = _validation.validate_synthetic_city


def generate_synthetic_city(
    nx: int, ny: int, nz: int, nt: int,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    生成语义约束的合成城市数据；
    按顺序调用底层模块，从土地利用（母图）开始，依次生成道路、建筑、POI、人口以及气象场。

    参数：
        nx, ny, nz: 空间网格维度
        nt: 时间步数
        seed: 随机种子，用于结果复现。默认42确保可复现性
              - 设置固定值（如42）可保证每次生成相同的数据
              - 不同种子值产生不同的城市场景
    
    返回：
        包含所有合成数据的字典，键包括：
        - landuse: 土地利用 (ny, nx)
        - road_mask: 道路掩码 (ny, nx)
        - building_heights: 建筑高度 (ny, nx)
        - poi: POI密度字典 {residential, office, institution, transport, industrial}
        - population: 静态人口密度 (ny, nx)
        - wind_field: 风场 (ny, nx, nz, nt)
        - rain_data: 降雨场 (ny, nx, nt)
        - od_pairs: OD对列表
    """
    # 步骤1: 生成土地利用（基础母图，使用种子以支持平滑过渡的噪声）
    landuse = create_landuse_master_plan(nx, ny, seed=seed)
    
    # 步骤2: 生成道路网络（依赖土地利用，使用种子以支持随机支路）
    road_mask = create_road_network(nx, ny, landuse, seed=seed)
    
    # 步骤3: 生成建筑高度（依赖土地利用 + 道路掩码，有随机性）
    building_heights = create_buildings_conditioned_on_landuse(
        nx, ny, nz, landuse, road_mask, seed=seed
    )
    
    # 步骤4: 生成POI密度（依赖土地利用 + 建筑高度，有随机性）
    # 使用不同的种子偏移量避免与建筑高度使用相同的随机序列
    poi_seed = (seed + 1000) if seed is not None else None
    poi = create_poi_from_landuse(landuse, building_heights, seed=poi_seed)
    
    # 步骤5: 生成静态人口密度（依赖土地利用 + POI + 道路掩码，无随机性）
    population = create_population_static(landuse, poi, road_mask=road_mask)
    
    # 步骤6: 生成气象数据（独立生成，支持随机扰动）
    # 使用不同的种子偏移量避免与其他模块冲突
    wind_seed = (seed + 3000) if seed is not None else None
    rain_seed = (seed + 4000) if seed is not None else None
    wind_field = create_wind_field(nx, ny, nz, nt, seed=wind_seed)
    rain_data = create_rain_field(nx, ny, nt, seed=rain_seed)
    
    # 步骤7: 生成OD对（独立生成，有随机性）
    # 使用不同的种子偏移量
    od_seed = (seed + 2000) if seed is not None else None
    od_pairs = create_od_pairs(nx, ny, seed=od_seed)
    
    # 步骤8: 执行数据校验（验证所有约束）
    validate_synthetic_city(landuse, road_mask, building_heights, poi, population)
    
    return {
        'landuse': landuse,              # (ny, nx)
        'road_mask': road_mask,          # (ny, nx)
        'building_heights': building_heights,  # (ny, nx)
        'poi': poi,                      # dict of (ny, nx)
        'population': population,        # (ny, nx) - 静态平均密度
        'wind_field': wind_field,        # (ny, nx, nz, nt)
        'rain_data': rain_data,          # (ny, nx, nt)
        'od_pairs': od_pairs             # list of tuples
    }


def simulate_micro_synthetic_data(grid) -> Dict[str, np.ndarray]:
    """
    为微观验证场景生成合成数据（针对“微观验证”场景的快捷入口。）
    接收项目中的 GridSystem 对象作为输入，自动提取网格维度（nx, ny, nz, nt），
    然后调用 generate_synthetic_city。

    返回的数据特征：
    - 完全由算法生成，无需外部数据源
    - 适用于机理验证和算法调试
    - 数据结构与真实数据保持一致，便于对比实验
    
    参数：
        grid: GridSystem对象，包含nx, ny, nz, nt属性
    
    返回：
        合成数据字典
    """
    # 从网格对象获取形状
    nx, ny, nz = grid.spatial.nx, grid.spatial.ny, grid.spatial.nz
    nt = grid.temporal.nt
    
    # 生成完整的时空合成数据
    return generate_synthetic_city(nx, ny, nz, nt, seed=42)



def _save_as_geotiff(data_array: np.ndarray, output_path: Path, transform=None, crs="EPSG:4326"):
    """
    将 NumPy 数组保存为 GeoTIFF 格式
    
    参数：
        data_array: 二维或三维 NumPy 数组
        output_path: 输出文件路径
        transform: 仿射变换矩阵，若未提供则使用默认单位网格
        crs: 坐标参考系统
    """
    if not HAS_RASTERIO:
        raise ImportError("请安装 rasterio 以支持 GeoTIFF 导出: pip install rasterio")
    
    # 确保数据是 float32 以便存储
    if data_array.dtype != np.float32 and data_array.dtype != np.int32:
        data_array = data_array.astype(np.float32)
        
    height, width = data_array.shape[-2], data_array.shape[-1]
    
    # 此时可以安全使用 rasterio 和 from_bounds
    from rasterio.transform import from_bounds
    import rasterio as rio
    
    with rio.open(
        output_path, 'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1 if data_array.ndim == 2 else data_array.shape[0],
        dtype=data_array.dtype,
        crs=crs,
        transform=transform or from_bounds(0, 0, width, height, width, height),
    ) as dst:
        if data_array.ndim == 2:
            dst.write(data_array, 1)
        else:
            for i in range(data_array.shape[0]):
                dst.write(data_array[i], i + 1)


def _save_vector_geojson(geometries: list, properties: list, output_path: Path):
    """
    将几何对象和属性保存为 GeoJSON
    
    参数：
        geometries: Shapely 几何对象列表 (Point, LineString 等)
        properties: 对应的属性字典列表
        output_path: 输出路径
    """
    if not HAS_GEOPANDAS:
        raise ImportError("请安装 geopandas 和 shapely 以支持矢量数据导出")
        
    # 此时可以安全使用 gpd、Point 和 LineString
    import geopandas as gdf_module
    from shapely.geometry import Point as ShapelyPoint, LineString as ShapelyLineString
    
    gdf = gdf_module.GeoDataFrame(properties, geometry=geometries, crs="EPSG:4326")
    gdf.to_file(output_path, driver='GeoJSON')


def export_synthetic_data(data: Dict[str, Any], output_dir: Optional[Union[str, Path]] = None, seed: Optional[int] = None, export_raw_gis: bool = False, export_tensors: bool = True):
    """
    将合成数据导出到磁盘，支持三个阶段：
    1. 01_raw/synthetic: 原生 GIS 格式 (.tif, .geojson)
    2. 02_processed/synthetic: 标准化 NumPy 格式 (.npy, .npz)
    3. 03_tensors/synthetic: 气象数据和成本张量 (.npy)
    
    参数：
        data: generate_synthetic_city() 返回的数据字典
        output_dir: 输出目录（02_processed），如果为None则使用默认路径
        seed: 随机种子（用于在 03_tensors 中创建带 seed 的子目录）
        export_raw_gis: 是否导出原生 GIS 格式到 01_raw/synthetic
        export_tensors: 是否导出风、雨数据到 03_tensors/synthetic
    """
    if output_dir is None:
        output_path = Path(__file__).parent.parent.parent / "data" / "02_processed" / "synthetic"
    else:
        output_path = Path(output_dir)
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    # --- 1. 导出标准化 NumPy 格式 (02_processed) ---
    pop_data = data['population']
    if pop_data.ndim == 2 and pop_data.shape[0] != pop_data.shape[1]:
        pop_data = pop_data.T
    np.save(output_path / "base_pop_2d.npy", pop_data.astype(np.float32))
    
    np.save(output_path / "building_heights.npy", data['building_heights'].astype(np.float32))
    
    # POI 是浮点密度值，必须保存为 float32，不能转为 int32（会丢失小数部分）
    poi_dict = {k: v.astype(np.float32) for k, v in data['poi'].items()}
    np.savez(output_path / "poi_counts.npz", **poi_dict)
    
    np.save(output_path / "landuse_map.npy", data['landuse'].astype(np.int32))
    np.save(output_path / "road_mask.npy", data['road_mask'].astype(np.bool_))
    
    with open(output_path / "od_pairs.json", 'w') as f:
        json.dump(data['od_pairs'], f)

    # --- 2. 导出原生 GIS 格式 (01_raw/synthetic) ---
    if export_raw_gis:
        if not HAS_GIS_LIBS:
            print("⚠️ 跳过原生 GIS 导出：缺少 rasterio 或 geopandas 库")
        else:
            raw_path = Path(__file__).parent.parent.parent / "data" / "01_raw" / "synthetic"
            if seed is not None:
                raw_path = raw_path / f"seed_{seed}"
            raw_path.mkdir(parents=True, exist_ok=True)
            
            res = 10.0  # 假设分辨率
            # 在这里局部导入 from_bounds
            from rasterio.transform import from_bounds
            transform = from_bounds(0, 0, data['landuse'].shape[1]*res, data['landuse'].shape[0]*res, 
                                    data['landuse'].shape[1], data['landuse'].shape[0])
            
            # A. 栅格数据 (.tif)
            _save_as_geotiff(data['population'].T, raw_path / "population.tif", transform=transform)
            _save_as_geotiff(data['building_heights'], raw_path / "building_heights.tif", transform=transform)
            _save_as_geotiff(data['landuse'].astype(np.float32), raw_path / "landuse.tif", transform=transform)
            
            # B. 矢量数据 (.geojson)
            road_geoms = []
            road_props = []
            road_mask = data['road_mask']
            ny, nx = road_mask.shape
            
            # 局部导入 LineString
            from shapely.geometry import LineString
            for y in range(ny):
                for x in range(nx - 1):
                    if road_mask[y, x] and road_mask[y, x+1]:
                        p1 = (x * res, y * res)
                        p2 = ((x + 1) * res, y * res)
                        road_geoms.append(LineString([p1, p2]))
                        road_props.append({'type': 'road_segment', 'direction': 'horizontal'})
                
            for x in range(nx):
                for y in range(ny - 1):
                    if road_mask[y, x] and road_mask[y+1, x]:
                        p1 = (x * res, y * res)
                        p2 = (x * res, (y + 1) * res)
                        road_geoms.append(LineString([p1, p2]))
                        road_props.append({'type': 'road_segment', 'direction': 'vertical'})

            if road_geoms:
                _save_vector_geojson(road_geoms, road_props, raw_path / "roads.geojson")

            # 2. 提取 POI 点
            poi_geoms = []
            poi_props = []
            # 局部导入 Point
            from shapely.geometry import Point
            for poi_type, poi_grid in data['poi'].items():
                ys, xs = np.where(poi_grid > 0)
                for y, x in zip(ys, xs):
                    lon = x * res + res / 2
                    lat = y * res + res / 2
                    poi_geoms.append(Point(lon, lat))
                    poi_props.append({'poi_type': poi_type, 'density': float(poi_grid[y, x])})
            
            if poi_geoms:
                _save_vector_geojson(poi_geoms, poi_props, raw_path / "pois.geojson")

            print(f"✅ 原生 GIS 数据已导出至: {raw_path}")

    # --- 3. 导出气象数据到 03_tensors ---
    if export_tensors:
        tensor_path = Path(__file__).parent.parent.parent / "data" / "03_tensors" / "synthetic"
        if seed is not None:
            tensor_path = tensor_path / f"seed_{seed}"
        tensor_path.mkdir(parents=True, exist_ok=True)
        
        # 导出风场和降雨
        np.save(tensor_path / "wind_field.npy", data['wind_field'].astype(np.float32))
        np.save(tensor_path / "rain_data.npy", data['rain_data'].astype(np.float32))
        
        print(f"✅ 张量数据（风、雨）已导出至: {tensor_path}")

    # --- 4. 创建元数据 ---
    metadata = {
        "generated_at": str(datetime.datetime.now()),
        "seed": seed,
        "source": "synthetic",
        "grid_dimensions": {
            "nx": data['landuse'].shape[1], 
            "ny": data['landuse'].shape[0],
            "nz": data['wind_field'].shape[2],
            "nt": data['wind_field'].shape[3]
        }
    }
    with open(output_path / "metadata.json", 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 合成数据已导出至: {output_path}")


# 示例用法
if __name__ == "__main__":
    # 测试合成数据生成
    nx, ny, nz, nt = 60, 60, 12, 96
    city_data = generate_synthetic_city(nx, ny, nz, nt, seed=42)
   
    print("✅ 合成城市生成成功！")
    print(f"\n数据层统计:")
    print(f"  土地利用: {city_data['landuse'].shape}")
    print(f"  道路掩码: {city_data['road_mask'].shape}")
    print(f"  建筑高度: {city_data['building_heights'].shape}")
    print(f"  人口密度: {city_data['population'].shape}")
    print(f"  风场: {city_data['wind_field'].shape}")
    print(f"  降雨场: {city_data['rain_data'].shape}")
    print(f"  OD对数量: {len(city_data['od_pairs'])}")
    print(f"  POI类型: {list(city_data['poi'].keys())}")
