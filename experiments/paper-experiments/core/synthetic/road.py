"""
道路网络生成模块 - 02_road.py [IMPROVED v2]

基于土地利用生成分层道路网络（主干道 + 次干道 + 支路）。

改进特性：
- 分层结构：主干道（arterial）、次干道（secondary）、支路（local）
- 连通性：确保城市各区域良好连接
- 避免绿地内道路
"""

import numpy as np


def create_road_network(nx: int, ny: int, landuse: np.ndarray, seed: int | None = None) -> np.ndarray:
    """
    生成分层道路网络
    
    参数：
        nx, ny: 网格尺寸
        landuse: 土地利用矩阵 (ny, nx)
        seed: 随机种子
    
    返回:
        道路掩码 (ny, nx) bool，True表示道路
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random
    
    road_mask = np.zeros((ny, nx), dtype=bool)
    
    # 1. 主干道（arterial roads）- 宽度3
    arterial_width = 3
    
    # 水平主干道
    for y in [ny//3, ny//2, 2*ny//3]:
        y_start = max(0, y - arterial_width//2)
        y_end = min(ny, y + arterial_width//2 + 1)
        road_mask[y_start:y_end, :] = True
    
    # 竖向主干道
    for x in [nx//3, nx//2, 2*nx//3]:
        x_start = max(0, x - arterial_width//2)
        x_end = min(nx, x + arterial_width//2 + 1)
        road_mask[:, x_start:x_end] = True
    
    # 2. 次干道（secondary roads）- 宽度2，在非绿地区域
    secondary_width = 2
    for y in np.linspace(0, ny-1, 6, dtype=int):
        for x in np.linspace(0, nx-1, 6, dtype=int):
            if landuse[y, x] != 6:
                y_start = max(0, y - secondary_width//2)
                y_end = min(ny, y + secondary_width//2 + 1)
                x_start = max(0, x - secondary_width//2)
                x_end = min(nx, x + secondary_width//2 + 1)
                road_mask[y_start:y_end, x_start:x_end] = True
    
    # 3. 支路（local streets）- 宽度1
    for y in range(10, ny, 10):
        for x in range(10, nx, 10):
            if landuse[y, x] in [1, 4]:
                road_mask[max(0,y-1):min(ny,y+2), x] = True
                road_mask[y, max(0,x-1):min(nx,x+2)] = True
    
    # 4. 清除绿地内的道路
    green_mask = (landuse == 6)
    road_mask[green_mask] = False
    
    return road_mask


if __name__ == "__main__":
    # 测试代码
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    
    from landuse import create_landuse_master_plan
    
    nx, ny = 60, 60
    landuse = create_landuse_master_plan(nx, ny)
    road_mask = create_road_network(nx, ny, landuse)
    
    print(f"道路掩码形状: {road_mask.shape}")
    print(f"道路格点数量: {np.sum(road_mask)}")
    print(f"道路覆盖率: {np.sum(road_mask) / (nx * ny) * 100:.2f}%")
