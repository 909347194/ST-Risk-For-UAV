"""
OD对生成模块 - 07_od_pairs.py

生成起点-终点对（Origin-Destination Pairs）。

约束关系：
- 起点固定在西南区域（住宅区为主）
- 终点固定在东北区域（商业/工业区为主）
- 确保路径穿过高风险区域，用于算法验证
"""

from typing import List, Tuple, Optional
import numpy as np


def create_od_pairs(
    nx: int, 
    ny: int, 
    num_pairs: int = 10,
    seed: Optional[int] = None
) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """
    生成起点-终点对
    
    参数：
        nx, ny: 网格维度
        num_pairs: OD对数量
        seed: 随机种子，用于结果复现。None表示不设置种子
    
    返回：
        OD对列表，每个元素为 ((start_x, start_y), (end_x, end_y))
        
    空间策略：
    - 起点：西南象限 (0 ~ nx//3, 0 ~ ny//3)，对应住宅区
    - 终点：东北象限 (2*nx//3 ~ nx, 2*ny//3 ~ ny)，对应商业/工业区
    - 保证路径穿越城市中心高风险区域
    """
    # 设置随机种子以保证可复现性
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random
    
    od_pairs = []
    
    for _ in range(num_pairs):
        # 起点：西南区域（住宅区）
        start_x = rng.randint(0, nx // 3)
        start_y = rng.randint(0, ny // 3)
        
        # 终点：东北区域（商业/工业区）
        end_x = rng.randint(2 * nx // 3, nx)
        end_y = rng.randint(2 * ny // 3, ny)
        
        od_pairs.append(((start_x, start_y), (end_x, end_y)))
    
    return od_pairs


if __name__ == "__main__":
    # 测试代码
    nx, ny = 60, 60
    od_pairs = create_od_pairs(nx, ny, num_pairs=10)
    
    print(f"生成 {len(od_pairs)} 个OD对:")
    for i, (start, end) in enumerate(od_pairs, 1):
        print(f"  OD-{i}: ({start[0]}, {start[1]}) → ({end[0]}, {end[1]})")
    
    # 验证约束
    for start, end in od_pairs:
        assert start[0] < nx // 3 and start[1] < ny // 3, "❌ 起点不在西南区域"
        assert end[0] >= 2 * nx // 3 and end[1] >= 2 * ny // 3, "❌ 终点不在东北区域"
    print("✓ OD对约束校验通过")
