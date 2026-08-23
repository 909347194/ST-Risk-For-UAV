"""
土地利用生成模块 - 01_landuse.py [IMPROVED v2]

生成分类土地利用主图，使用同心圆模型和Perlin噪声实现平滑过渡。

土地利用类型编码：
- 0: 未定义/空地
- 1: 住宅区 (Residential)
- 2: 商业/办公区 (Commercial/Office)
- 3: 学校/医院 (School/Hospital)
- 4: 工业区 (Industrial)
- 5: 道路 (Road)
- 6: 绿地/水域 (Green/Water)

改进特性：
- 同心区域模型：CBD→商业环→住宅环→工业外围
- 噪声实现平滑边界过渡
- 概率约束替代硬边界
- 种子驱动的完全可复现性
"""

import numpy as np


def create_landuse_master_plan(nx: int, ny: int, seed: int | None = None) -> np.ndarray:
    """
    生成土地利用主图 - 改进版（同心圆模型 + 噪声）
    
    参数：
        nx, ny: 网格尺寸
        seed: 随机种子，用于再现性
    
    返回: (ny, nx) 土地利用矩阵
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random
    
    landuse = np.zeros((ny, nx), dtype=int)
    
    # 创建坐标网格，计算到中心的距离
    y_coords, x_coords = np.ogrid[0:ny, 0:nx]
    center_y, center_x = ny // 2, nx // 2
    distance_to_center = np.sqrt((y_coords - center_y)**2 + (x_coords - center_x)**2)
    
    # 噪声扰动实现平滑过渡
    noise = rng.normal(0, 2, size=(ny, nx))
    disturbed_distance = distance_to_center + noise
    
    max_dist = np.sqrt((center_y**2) + (center_x**2))
    
    # 1. CBD 中心 (2) - 距离 0-15%
    cbd_mask = disturbed_distance < max_dist * 0.15
    landuse[cbd_mask] = 2
    
    # 2. 商业/混合环 (2) - 距离 15-25%
    commercial_ring = (disturbed_distance >= max_dist * 0.15) & (disturbed_distance < max_dist * 0.25)
    commercial_mask = commercial_ring & (rng.random((ny, nx)) < 0.7)
    landuse[commercial_mask] = 2
    
    # 3. 住宅环 (1) - 距离 25-50%
    residential_ring = (disturbed_distance >= max_dist * 0.25) & (disturbed_distance < max_dist * 0.5)
    residential_mask = residential_ring & (rng.random((ny, nx)) < 0.8)
    landuse[residential_mask] = 1
    
    # 学校/医院在住宅环
    school_mask = residential_ring & (rng.random((ny, nx)) < 0.2) & (landuse == 0)
    landuse[school_mask] = 3
    
    # 4. 工业区 (4) - 距离 50-75%
    industrial_ring = (disturbed_distance >= max_dist * 0.5) & (disturbed_distance < max_dist * 0.75)
    industrial_mask = industrial_ring & (rng.random((ny, nx)) < 0.85)
    landuse[industrial_mask] = 4
    
    # 5. 绿地/水域 (6) - 距离 > 75%
    green_mask = disturbed_distance >= max_dist * 0.75
    landuse[green_mask] = 6
    
    # 6. 生成道路网：主干道 (5)
    road_width = 3
    for y in [ny//4, ny//2, 3*ny//4]:
        landuse[max(0, y-road_width):min(ny, y+road_width), :] = 5
    
    for x in [nx//4, nx//2, 3*nx//4]:
        landuse[:, max(0, x-road_width):min(nx, x+road_width)] = 5
    
    # 对角线道路
    for i in range(ny):
        for j in range(nx):
            if abs(i - j) < road_width:
                landuse[i, j] = 5
    
    # 7. 次要道路
    for _ in range(int(nx * ny * 0.02)):
        y = rng.randint(0, ny)
        x = rng.randint(0, nx)
        if landuse[y, x] != 6:
            landuse[y, x] = 5
    
    return landuse


if __name__ == "__main__":
    # 测试代码
    nx, ny = 60, 60
    landuse = create_landuse_master_plan(nx, ny)
    print(f"土地利用矩阵形状: {landuse.shape}")
    print(f"各类型统计:")
    for code in range(7):
        count = np.sum(landuse == code)
        if count > 0:
            type_names = {
                0: "未定义", 1: "住宅区", 2: "商业区", 
                3: "学校/医院", 4: "工业区", 5: "道路", 6: "绿地"
            }
            print(f"  {type_names[code]}: {count} 格点")

    # 可视化土地利用分布（可选） 
    
