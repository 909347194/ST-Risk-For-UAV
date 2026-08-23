"""
人口密度生成模块 - 05_population.py

基于POI和土地利用生成静态平均人口密度场。

约束关系：
- 人口密度与POI密度成正比
- 不同用地类型有不同的人口系数
- 道路和绿地人口极少或为零
- 返回二维静态密度，动态变化由其他模块处理
"""

import numpy as np
from typing import Dict


def create_population_static(
    landuse: np.ndarray,
    poi: Dict[str, np.ndarray],
    road_mask: np.ndarray | None = None
) -> np.ndarray:
    """
    生成静态平均人口密度场
    
    参数：
        landuse: 土地利用矩阵 (ny, nx)
        poi: POI密度字典
        road_mask: 道路掩码 (ny, nx)，可选。若提供则强制道路上人口为0
    
    返回：
        二维人口密度场 (ny, nx)，表示长期平均人口密度
    """
    ny, nx = landuse.shape
    population = np.zeros((ny, nx), dtype=float)
    
    # 住宅区：基础人口密度较高（系数0.6）
    residential_mask = (landuse == 1)
    if np.any(residential_mask):
        population[residential_mask] = poi['residential'][residential_mask] * 0.6
    
    # 办公区：中等人口密度（系数0.5）
    office_mask = (landuse == 2)
    if np.any(office_mask):
        population[office_mask] = poi['office'][office_mask] * 0.5
    
    # 学校/医院：白天有人口聚集（系数0.4）
    institution_mask = (landuse == 3)
    if np.any(institution_mask):
        population[institution_mask] = poi['institution'][institution_mask] * 0.4
    
    # 工业区：较低人口密度（系数0.3）
    industrial_mask = (landuse == 4)
    if np.any(industrial_mask):
        population[industrial_mask] = poi['industrial'][industrial_mask] * 0.3
    
    # 道路区域：极低人口密度（通行功能）
    road_landuse_mask = (landuse == 5)
    population[road_landuse_mask] = 0.05
    
    # 绿地/水域：无人居住
    green_mask = (landuse == 6)
    population[green_mask] = 0.0
    
    # 如果提供了外部道路掩码，强制覆盖为0（更精确的道路范围）
    if road_mask is not None:
        population[road_mask] = 0.0
    
    return population


if __name__ == "__main__":
    # 测试代码
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    
    from landuse import create_landuse_master_plan
    from road import create_road_network
    from building import create_buildings_conditioned_on_landuse
    from poi import create_poi_from_landuse
    
    nx, ny, nz = 60, 60, 12
    landuse = create_landuse_master_plan(nx, ny)
    road_mask = create_road_network(nx, ny, landuse)
    building_heights = create_buildings_conditioned_on_landuse(nx, ny, nz, landuse, road_mask)
    poi = create_poi_from_landuse(landuse, building_heights)
    population = create_population_static(landuse, poi)
    
    print(f"人口密度矩阵形状: {population.shape}")
    print(f"总人口格点数: {np.sum(population > 0)}")
    print(f"平均人口密度: {np.mean(population[population > 0]):.3f}")
    print(f"最大人口密度: {np.max(population):.3f}")
    
    # 验证约束
    green_mask = (landuse == 6)
    assert np.all(population[green_mask] == 0), "❌ 绿地存在人口"
    print("✓ 人口密度约束校验通过")
