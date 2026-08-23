"""
数据校验模块 - 08_validation.py

执行合成城市数据的合理性校验，确保各图层之间的约束一致性。

校验规则：
1. 绿地/水域上不能有建筑
2. 道路上不能有建筑
3. 学校建筑高度不超过60m
4. 工业区不能出现住宅POI
5. 绿地和道路上人口密度为0或极低
"""

import numpy as np
from typing import Dict


def validate_synthetic_city(
    landuse: np.ndarray,
    road_mask: np.ndarray,
    building_heights: np.ndarray,
    poi: Dict[str, np.ndarray],
    population: np.ndarray = None
):
    """
    执行合成城市的合理性校验
    
    参数：
        landuse: 土地利用矩阵 (ny, nx)
        road_mask: 道路掩码 (ny, nx)
        building_heights: 建筑高度矩阵 (ny, nx)
        poi: POI密度字典
        population: 人口密度矩阵 (ny, nx)，可选
    """
    ny, nx = landuse.shape
    
    # 1. 绿地/水域建筑高度必须为0
    green_mask = (landuse == 6)
    if np.any(green_mask):
        assert np.all(building_heights[green_mask] == 0), "❌ 绿地存在建筑"
    
    # 2. 道路上建筑高度必须为0
    if np.any(road_mask):
        assert np.all(building_heights[road_mask] == 0), "❌ 道路上存在建筑"
    
    # 3. 学校建筑高度不应过高 (<=60m)
    school_mask = (landuse == 3)
    if np.any(school_mask):
        assert np.all(building_heights[school_mask] <= 60), "❌ 学校建筑过高"
    
    # 4. 工业区不应产生住宅POI
    industrial_mask = (landuse == 4)
    if np.any(industrial_mask):
        assert np.all(poi['residential'][industrial_mask] == 0), "❌ 工业区出现住宅POI"
    
    # 5. 绿地和道路上人口密度应为0或极低（如果提供了人口数据）
    if population is not None:
        if np.any(green_mask):
            assert np.all(population[green_mask] == 0), "❌ 绿地存在人口"
        if np.any(road_mask):
            assert np.all(population[road_mask] <= 0.1), "❌ 道路上人口密度过高"
    
    print("[OK] 合成城市数据校验通过")


if __name__ == "__main__":
    # 测试代码
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    
    from landuse import create_landuse_master_plan
    from road import create_road_network
    from building import create_buildings_conditioned_on_landuse
    from poi import create_poi_from_landuse
    from population import create_population_static
    
    nx, ny, nz = 60, 60, 12
    landuse = create_landuse_master_plan(nx, ny)
    road_mask = create_road_network(nx, ny, landuse)
    building_heights = create_buildings_conditioned_on_landuse(nx, ny, nz, landuse, road_mask)
    poi = create_poi_from_landuse(landuse, building_heights)
    population = create_population_static(landuse, poi)
    
    validate_synthetic_city(landuse, road_mask, building_heights, poi, population)
