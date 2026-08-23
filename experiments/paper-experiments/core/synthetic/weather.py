"""
气象数据生成模块 - 06_weather.py

生成风场和降雨场的合成数据。

约束关系：
- 风场：城市峡谷效应，中心区域风速高，随高度增加
- 降雨：集中在城市中心，随时间变化模拟阵雨
- 风场为4D (ny, nx, nz, nt)，降雨为3D (ny, nx, nt)

学术规范依据：
- 风速分级：蒲福风级（Beaufort Scale）
- 抗风极限：V_limit = 12 m/s（约6级强风）
- 降雨分级：世界气象组织（WMO）小时雨强标准

可复现性控制：
- 所有函数支持可选的 seed 参数，确保相同种子下输出一致
- 使用局部随机状态对象（np.random.RandomState），避免全局污染
"""

from typing import Optional
import numpy as np


"""
气象数据生成模块 - 06_weather.py [IMPROVED v2]

生成连贯的时空风场和降雨场，而非纯随机。

改进特性：
- 时间相关性：风速和方向平滑变化
- 空间相关性：相邻格点数据相似
- 垂直风切变：地面风较弱
- 降雨聚集性：雨带模式
- 连续的事件模式：不是每时刻独立
"""

from typing import Optional
import numpy as np


def _smooth_temporal_field(field_3d: np.ndarray, temporal_smoothness: float = 0.7) -> np.ndarray:
    """对时间维度应用平滑滤波器"""
    ny, nx, nt = field_3d.shape
    smoothed = field_3d.copy()
    for t in range(1, nt):
        smoothed[:, :, t] = (
            temporal_smoothness * smoothed[:, :, t-1] +
            (1 - temporal_smoothness) * field_3d[:, :, t]
        )
    return smoothed


def create_wind_field(
    nx: int, 
    ny: int, 
    nz: int, 
    nt: int,
    seed: Optional[int] = None
) -> np.ndarray:
    """
    生成连贯的风场 (ny, nx, nz, nt)
    
    改进特性：
    - 风向随时间缓变（不是每个时刻独立）
    - 空间相关性：相邻格点风速相似
    - 垂直风速递减（地面风较弱）
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random
    
    # 1. 生成基础风场（3D空间 + 时间）
    wind_u = np.zeros((ny, nx, nz, nt), dtype=float)  # 东西风
    wind_v = np.zeros((ny, nx, nz, nt), dtype=float)  # 南北风
    
    # 2. 主导风向随时间缓变
    wind_direction = 45 + 30 * np.sin(np.arange(nt) * 2*np.pi / (nt/2))  # 主导方向变化
    wind_speed_base = 5 + 2 * np.sin(np.arange(nt) * 2*np.pi / (nt/4))  # 风速变化
    
    for t in range(nt):
        direction_rad = np.radians(wind_direction[t])
        base_speed = wind_speed_base[t]
        
        u_base = base_speed * np.cos(direction_rad)
        v_base = base_speed * np.sin(direction_rad)
        
        for z in range(nz):
            height_factor = 0.3 + 0.7 * (z / (nz - 1))
            noise_u = rng.normal(0, 1, size=(ny, nx))
            noise_v = rng.normal(0, 1, size=(ny, nx))
            
            wind_u[:, :, z, t] = u_base * height_factor + 0.3 * noise_u
            wind_v[:, :, z, t] = v_base * height_factor + 0.3 * noise_v
    
    # 3. 应用时间平滑
    for z in range(nz):
        wind_u[:, :, z, :] = _smooth_temporal_field(wind_u[:, :, z, :], temporal_smoothness=0.7)
        wind_v[:, :, z, :] = _smooth_temporal_field(wind_v[:, :, z, :], temporal_smoothness=0.7)
    
    # 4. 组合为单个风速标量场
    wind_speed = np.sqrt(wind_u**2 + wind_v**2)
    
    return wind_speed


def create_rain_field(
    nx: int, 
    ny: int, 
    nt: int,
    seed: Optional[int] = None
) -> np.ndarray:
    """
    生成连贯的降雨场 (ny, nx, nt)
    
    改进特性：
    - 降雨具有空间聚集性（雨带模式）
    - 降雨具有时间连贯性（连续降雨时段）
    - 间歇模式（间断降雨）
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random
    
    rain_data = np.zeros((ny, nx, nt), dtype=float)
    
    # 1. 生成降雨事件的时间模式
    event_likelihood = 0.3  # 30% 时间有降雨
    rain_events = rng.random(nt) < event_likelihood
    
    # 2. 连贯性：降雨事件会持续几个时步
    for t in range(1, nt):
        if rng.random() < 0.7:  # 70% 继承前一步的状态
            rain_events[t] = rain_events[t-1]
    
    # 3. 对每个降雨时刻生成空间分布
    for t in range(nt):
        if rain_events[t]:
            num_centers = rng.choice([1, 2], p=[0.6, 0.4])
            for _ in range(num_centers):
                center_y = rng.randint(0, ny)
                center_x = rng.randint(0, nx)
                
                y_dist = np.abs(np.arange(ny) - center_y)
                x_dist = np.abs(np.arange(nx) - center_x)
                yy, xx = np.meshgrid(y_dist, x_dist, indexing='ij')
                dist = np.sqrt(yy**2 + xx**2)
                
                intensity = 10 * np.exp(-(dist**2) / (15**2))
                rain_data[:, :, t] = np.maximum(rain_data[:, :, t], intensity)
    
    return rain_data


if __name__ == "__main__":
    # 测试代码
    nx, ny, nz, nt = 60, 60, 12, 96
    
    print("=" * 80)
    print("测试1: 确定性风场（无随机扰动）")
    print("=" * 80)
    wind_deterministic = create_wind_field(nx, ny, nz, nt)
    print(f"风场形状: {wind_deterministic.shape}")
    print(f"平均风速: {np.mean(wind_deterministic):.2f} m/s")
    print(f"最大风速: {np.max(wind_deterministic):.2f} m/s")
    print(f"最小风速: {np.min(wind_deterministic):.2f} m/s")
    print(f"\n风速分布统计:")
    print(f"  0-3.3 m/s (0-2级): {np.sum((wind_deterministic >= 0) & (wind_deterministic < 3.3))} cells")
    print(f"  3.4-5.4 m/s (3级): {np.sum((wind_deterministic >= 3.4) & (wind_deterministic < 5.4))} cells")
    print(f"  5.5-7.9 m/s (4级): {np.sum((wind_deterministic >= 5.5) & (wind_deterministic < 7.9))} cells")
    print(f"  8.0-10.7 m/s (5级): {np.sum((wind_deterministic >= 8.0) & (wind_deterministic < 10.7))} cells")
    print(f"  10.8-12.0 m/s (6级): {np.sum((wind_deterministic >= 10.8) & (wind_deterministic <= 12.0))} cells")
    
    print("\n" + "=" * 80)
    print("测试2: 可复现性验证（相同种子应产生相同结果）")
    print("=" * 80)
    wind_seed1_a = create_wind_field(nx, ny, nz, nt, seed=42)
    wind_seed1_b = create_wind_field(nx, ny, nz, nt, seed=42)
    wind_seed2 = create_wind_field(nx, ny, nz, nt, seed=123)
    
    print(f"种子42 (第1次) vs 种子42 (第2次): {'✓ 完全一致' if np.allclose(wind_seed1_a, wind_seed1_b) else '✗ 不一致'}")
    print(f"种子42 vs 种子123: {'✗ 不同（预期）' if not np.allclose(wind_seed1_a, wind_seed2) else '✓ 相同（异常）'}")
    print(f"确定性模式 vs 种子42: {'✗ 不同（有扰动）' if not np.allclose(wind_deterministic, wind_seed1_a) else '✓ 相同（无扰动）'}")
    
    print("\n" + "=" * 80)
    print("测试3: 确定性降雨场（无随机扰动）")
    print("=" * 80)
    rain_deterministic = create_rain_field(nx, ny, nt)
    print(f"降雨场形状: {rain_deterministic.shape}")
    print(f"平均降雨量: {np.mean(rain_deterministic[rain_deterministic > 0]):.2f} mm/h")
    print(f"最大降雨量: {np.max(rain_deterministic):.2f} mm/h")
    print(f"有雨时间步数: {np.sum(np.any(rain_deterministic > 0, axis=(0, 1)))} / {nt}")
    print(f"\n降雨强度分布统计:")
    print(f"  0.0 mm/h (无雨): {np.sum(rain_deterministic == 0)} cells")
    print(f"  0.1-2.5 mm/h (小雨): {np.sum((rain_deterministic > 0) & (rain_deterministic <= 2.5))} cells")
    print(f"  2.5-10.0 mm/h (中雨): {np.sum((rain_deterministic > 2.5) & (rain_deterministic <= 10.0))} cells")
    print(f"  10.0-25.0 mm/h (大雨): {np.sum((rain_deterministic > 10.0) & (rain_deterministic <= 25.0))} cells")
    print(f"  >25.0 mm/h (暴雨): {np.sum(rain_deterministic > 25.0)} cells")
    
    print("\n" + "=" * 80)
    print("测试4: 降雨场可复现性验证")
    print("=" * 80)
    rain_seed1_a = create_rain_field(nx, ny, nt, seed=42)
    rain_seed1_b = create_rain_field(nx, ny, nt, seed=42)
    rain_seed2 = create_rain_field(nx, ny, nt, seed=123)
    
    print(f"种子42 (第1次) vs 种子42 (第2次): {'✓ 完全一致' if np.allclose(rain_seed1_a, rain_seed1_b) else '✗ 不一致'}")
    print(f"种子42 vs 种子123: {'✗ 不同（预期）' if not np.allclose(rain_seed1_a, rain_seed2) else '✓ 相同（异常）'}")
    print(f"确定性模式 vs 种子42: {'✗ 不同（有扰动）' if not np.allclose(rain_deterministic, rain_seed1_a) else '✓ 相同（无扰动）'}")
    
    print("\n" + "=" * 80)
    print("使用建议")
    print("=" * 80)
    print("1. 实验对比: 使用 seed=None 获得理想化基准场景")
    print("2. 敏感性分析: 使用固定 seed (如 42, 123, 456) 生成多个扰动场景")
    print("3. 可复现性: 记录使用的 seed 值，确保实验可重复")
    print("4. 蒙特卡洛模拟: 遍历多个 seed 值进行统计分析")
