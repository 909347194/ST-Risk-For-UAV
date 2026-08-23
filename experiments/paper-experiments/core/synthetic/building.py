"""
建筑高度生成模块 - building.py

根据土地利用类型和道路掩码生成建筑高度场。

约束关系：
- 道路和绿地上的建筑高度必须为0
- 不同用地类型对应不同的建筑高度范围
- 学校建筑高度受限（<=60m）
- 商业区可建高层建筑（40-120m）
"""

import numpy as np


def create_buildings_conditioned_on_landuse(
    nx: int, ny: int, nz: int,
    landuse: np.ndarray,
    road_mask: np.ndarray,
    seed: int | None = None
) -> np.ndarray:
    """
    生成建筑高度 - 改进版（空间聚类 + 现实分布）
    
    参数：
        nx, ny, nz: 网格维度
        landuse: 土地利用矩阵 (ny, nx)
        road_mask: 道路掩码 (ny, nx)
        seed: 随机种子
    
    返回:
        建筑高度矩阵 (ny, nx)，单位：米
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random
    
    building_heights = np.zeros((ny, nx), dtype=float)
    
    # 计算到CBD中心的距离，实现高度递减
    y_coords, x_coords = np.ogrid[0:ny, 0:nx]
    center_y, center_x = ny // 2, nx // 2
    distance_to_center = np.sqrt((y_coords - center_y)**2 + (x_coords - center_x)**2)
    distance_norm = distance_to_center / distance_to_center.max()
    
    # 1. 住宅区 (1): 15-45m，但CBD附近更高
    mask = (landuse == 1) & ~road_mask
    if np.any(mask):
        base_heights = rng.uniform(15, 45, size=mask.sum())
        proximity_factor = 1 + 0.5 * (1 - distance_norm[mask])  # CBD附近更高
        building_heights[mask] = base_heights * proximity_factor
    
    # 2. 商业区 (2): 40-120m，CBD最高
    mask = (landuse == 2) & ~road_mask
    if np.any(mask):
        base_heights = rng.uniform(40, 120, size=mask.sum())
        proximity_factor = 1 + (1 - distance_norm[mask])  # CBD中心可达150m
        building_heights[mask] = np.minimum(base_heights * proximity_factor, 120)
    
    # 3. 学校/医院 (3): 10-60m，限制高度
    mask = (landuse == 3) & ~road_mask
    if np.any(mask):
        building_heights[mask] = rng.uniform(10, 60, size=mask.sum())
    
    # 4. 工业区 (4): 10-45m，外围较低
    mask = (landuse == 4) & ~road_mask
    if np.any(mask):
        base_heights = rng.uniform(10, 45, size=mask.sum())
        proximity_factor = 0.7 + 0.3 * (1 - distance_norm[mask])
        building_heights[mask] = base_heights * proximity_factor
    
    # 5. 绿地/水域 (6): 0高度
    mask = (landuse == 6)
    building_heights[mask] = 0.0
    
    # 6. 道路区域: 0高度
    building_heights[road_mask] = 0.0
    
    # 7. 添加小规模空间聚类变异（非学校区域）
    cluster_centers = rng.choice(ny*nx, size=int(ny*nx*0.05), replace=False)
    school_mask = (landuse == 3)
    for center_idx in cluster_centers:
        cy, cx = divmod(center_idx, nx)
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                ny_idx = cy + dy
                nx_idx = cx + dx
                if (0 <= ny_idx < ny and 0 <= nx_idx < nx 
                    and building_heights[ny_idx, nx_idx] > 0
                    and not school_mask[ny_idx, nx_idx]):
                    building_heights[ny_idx, nx_idx] *= 1.1
    
    return building_heights


if __name__ == "__main__":
    # 测试代码
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from landuse import create_landuse_master_plan
    from road import create_road_network
    
    nx, ny, nz = 60, 60, 12
    landuse = create_landuse_master_plan(nx, ny)
    road_mask = create_road_network(nx, ny, landuse)
    building_heights = create_buildings_conditioned_on_landuse(nx, ny, nz, landuse, road_mask, seed=42)
    
    print(f"建筑高度矩阵形状: {building_heights.shape}")
    print(f"平均建筑高度: {np.mean(building_heights[building_heights > 0]):.2f} m")
    print(f"最大建筑高度: {np.max(building_heights):.2f} m")
    
    # 验证约束
    green_mask = (landuse == 6)
    assert np.all(building_heights[green_mask] == 0), "❌ 绿地存在建筑"
    assert np.all(building_heights[road_mask] == 0), "❌ 道路上存在建筑"
    school_mask = (landuse == 3)
    assert np.all(building_heights[school_mask] <= 60), "❌ 学校建筑过高"
    print("✓ 所有约束校验通过")
