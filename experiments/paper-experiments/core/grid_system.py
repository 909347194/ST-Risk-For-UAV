"""
时空异质性模型 - 网格系统

定义四维时空网格结构（X、Y、Z、T），并提供用于坐标转换与网格运算的实用函数。

网格结构：
- 空间维度：(NX, NY, NZ) - 三维体素网格
- 时间维度：NT - 时间步数
- 总维度：NX × NY × NZ × NT - 四维张量

核心功能：
1. 提供空间和时间坐标轴的生成与管理
2. 支持世界坐标与网格索引的双向转换
3. 支持从配置文件动态初始化网格参数
4. 为风险张量计算提供基础网格框架
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Tuple, Optional, Union
from pathlib import Path


@dataclass
class SpatialGridConfig:
    """
    空间网格配置类
    
    定义三维空间网格的维度和分辨率参数。
    
    属性：
        nx, ny, nz: X、Y、Z 方向的网格单元数量
        dx, dy, dz: X、Y、Z 方向的物理分辨率（米）
    """
    nx: int = 60   # X方向网格单元数
    ny: int = 60   # Y方向网格单元数
    nz: int = 12    # Z方向网格单元数（垂直层数）
    
    # 物理尺寸（单位：米）
    dx: float = 10.0   # 水平X方向分辨率
    dy: float = 10.0   # 水平Y方向分辨率
    dz: float = 10.0   # 垂直Z方向分辨率
    
    @property
    def total_cells(self) -> int:
        """计算空间网格的总单元数"""
        return self.nx * self.ny * self.nz


@dataclass
class TemporalGridConfig:
    """
    时间网格配置类
    
    定义时间维度的离散化参数，每个时间片对应一个独立的风险快照。
    
    属性：
        nt: 时间片总数
        dt_minutes: 每个时间片的时长（分钟）
    """
    nt: int = 96              # 时间片总数（24小时 × 4片/小时）
    dt_minutes: float = 15.0  # 时间步长（分钟）
    
    @property
    def dt_hours(self) -> float:
        """将时间步长转换为小时单位"""
        return self.dt_minutes / 60.0
    
    @property
    def total_hours(self) -> float:
        """计算总仿真时长（小时）"""
        return self.nt * self.dt_hours


@dataclass
class GridSystem:
    """
    完整的四维时空网格系统
    
    提供坐标轴生成和辅助方法，支持四维张量运算。
    
    核心职责：
    1. 管理空间和时间坐标数组（懒加载缓存）
    2. 提供网格形状查询接口
    3. 支持世界坐标与网格索引的双向转换
    4. 创建空的四维张量容器
    
    坐标系统设计：
    - X/Y方向：从0开始，符合GIS标准 (中心点 = (i + 0.5) * resolution)
    - Z方向：保持安全高度偏移 (中心点 = (k + 1.0) * dz)
    
    使用示例：
        >>> grid = GridSystem()
        >>> print(grid.shape)  # (40, 40, 12, 96)
        >>> print(grid.x_coords[:3])  # [5.0, 15.0, 25.0]  (从0开始)
        >>> print(grid.z_heights[:3])  # [10.0, 20.0, 30.0]  (安全高度)
        >>> print(grid.time_hours)  # [0.0, 0.25, 0.50, ..., 23.75]
    """
    spatial: SpatialGridConfig = field(default_factory=SpatialGridConfig)
    temporal: TemporalGridConfig = field(default_factory=TemporalGridConfig)
    
    # 缓存的坐标数组（懒加载初始化，避免重复计算）
    _x_coords: Optional[np.ndarray] = field(default=None, repr=False)
    _y_coords: Optional[np.ndarray] = field(default=None, repr=False)
    _z_heights: Optional[np.ndarray] = field(default=None, repr=False)
    _time_hours: Optional[np.ndarray] = field(default=None, repr=False)
    
    @property
    def shape(self) -> Tuple[int, int, int, int]:
        """
        返回四维张量的形状
        
        Returns:
            元组 (NX, NY, NZ, NT)
        """
        return (self.spatial.nx, self.spatial.ny, self.spatial.nz, self.temporal.nt)
    
    @property
    def x_coords(self) -> np.ndarray:
        """
        生成X轴坐标数组（每个网格单元的中心点坐标）
        
        计算逻辑：
        - 第i个单元的X坐标 = (i + 0.5) * dx
        - 第一个单元中心在 0.5*dx，对应范围 [0, dx)
        - 符合GIS/遥感行业标准（ArcGIS, QGIS等）
        - 空间范围从0开始，更直观
        
        Returns:
            长度为 NX 的一维数组，单位为米
        """
        if self._x_coords is None:
            self._x_coords = (np.arange(self.spatial.nx) + 0.5) * self.spatial.dx
        return self._x_coords
    
    @property
    def y_coords(self) -> np.ndarray:
        """
        生成Y轴坐标数组（每个网格单元的中心点坐标）
        
        计算逻辑：
        - 第j个单元的Y坐标 = (j + 0.5) * dy
        - 第一个单元中心在 0.5*dy，对应范围 [0, dy)
        - 符合GIS/遥感行业标准（ArcGIS, QGIS等）
        - 空间范围从0开始，更直观
        
        Returns:
            长度为 NY 的一维数组，单位为米
        """
        if self._y_coords is None:
            self._y_coords = (np.arange(self.spatial.ny) + 0.5) * self.spatial.dy
        return self._y_coords
    
    @property
    def z_heights(self) -> np.ndarray:
        """
        生成Z轴高度数组（每层的中心高度）
        
        计算逻辑：
        - 第k层的高度 = (k + 1.0) * dz
        - 第一层从 dz 开始（地面以上，保证无人机安全飞行高度）
        - Z方向与X/Y不同，体现垂直方向的安全约束
        
        Returns:
            长度为 NZ 的一维数组，单位为米
        """
        if self._z_heights is None:
            self._z_heights = (np.arange(self.spatial.nz) + 1.0) * self.spatial.dz
        return self._z_heights
    
    @property
    def time_hours(self) -> np.ndarray:
        """
        生成时间轴数组（以小时为单位）
        
        时间语义：
        - 每个时间片代表一个"出发时刻对应的风险切片"
        - 不是连续时间序列，而是离散的风险快照
        - 例如：t=0 表示 0:00 出发的风险分布，t=1 表示 0:15 出发的风险分布
        
        计算逻辑：
        - 第t个时间片的小时数 = t * dt_hours
        - 范围：[0.0, 0.25, 0.50, ..., 23.75]
        
        Returns:
            长度为 NT 的一维数组，单位为小时
        """
        if self._time_hours is None:
            self._time_hours = np.arange(self.temporal.nt) * self.temporal.dt_hours
        return self._time_hours
    
    def create_empty_tensor(self, dtype=np.float32) -> np.ndarray:
        """
        创建空的四维张量（用于存储风险值、代价等数据）
        
        Args:
            dtype: 数据类型，默认为 float32
            
        Returns:
            形状为 (NX, NY, NZ, NT) 的全零数组
        """
        return np.zeros(self.shape, dtype=dtype)
    
    def get_altitude_layer(self, altitude_m: float) -> int:
        """
        根据给定高度获取对应的网格层索引
        
        计算步骤：
        1. 将高度除以垂直分辨率得到理论层号
        2. 减去1以对齐网格索引（因为第一层从dz开始）
        3. 使用 clip 确保索引在有效范围内 [0, NZ-1]
        
        Args:
            altitude_m: 高度值（米）
            
        Returns:
            层索引（从0开始）
        """
        layer = int(altitude_m / self.spatial.dz) - 1
        return np.clip(layer, 0, self.spatial.nz - 1)
    
    def get_time_index(self, hour: float) -> int:
        """
        根据给定小时数获取对应的时间片索引
        
        计算步骤：
        1. 将小时数除以时间步长得到理论时间索引
        2. 使用 clip 确保索引在有效范围内 [0, NT-1]
        
        Args:
            hour: 时间（小时，范围0-24）
            
        Returns:
            时间索引（从0开始）
        """
        idx = int(hour / self.temporal.dt_hours)
        return np.clip(idx, 0, self.temporal.nt - 1)
    
    def world_to_grid(self, x: float, y: float, z: float) -> Tuple[int, int, int]:
        """
        将世界坐标转换为网格索引
        
        转换逻辑：
        - X方向：ix = floor(x / dx)，X/Y从0开始无需偏移
        - Y方向：iy = floor(y / dy)，X/Y从0开始无需偏移
        - Z方向：调用 get_altitude_layer(z)，Z从dz开始需要偏移
        - 对所有索引进行边界裁剪，确保不越界
        
        示例（dx=dy=dz=10m）：
        - 世界坐标 (5m, 15m, 25m) → 索引 (0, 1, 1)
          - ix = int(5/10) = 0   (落在[0-10)m，中心5m)
          - iy = int(15/10) = 1  (落在[10-20)m，中心15m)
          - iz = int(25/10)-1 = 1 (落在[10-20)m，中心20m)
        
        Args:
            x, y, z: 世界坐标（米）
            
        Returns:
            元组 (ix, iy, iz)，表示网格索引
        """
        # X/Y方向：从0开始，直接除法取整
        ix = int(x / self.spatial.dx)
        iy = int(y / self.spatial.dy)
        
        # Z方向：从dz开始，需要减1偏移
        iz = self.get_altitude_layer(z)
        
        # 边界保护：确保索引在有效范围内
        ix = np.clip(ix, 0, self.spatial.nx - 1)
        iy = np.clip(iy, 0, self.spatial.ny - 1)
        iz = np.clip(iz, 0, self.spatial.nz - 1)
        
        return ix, iy, iz
    
    def grid_to_world(self, ix: int, iy: int, iz: int) -> Tuple[float, float, float]:
        """
        将网格索引转换为世界坐标（单元中心点）
        
        转换逻辑：
        - X坐标：x = (ix + 0.5) * dx，X/Y从0开始，中心在半格位置
        - Y坐标：y = (iy + 0.5) * dy，X/Y从0开始，中心在半格位置
        - Z坐标：z = (iz + 1.0) * dz，Z从dz开始，保持安全高度
        
        示例（dx=dy=dz=10m）：
        - 索引 (0, 1, 1) → 世界坐标 (5m, 15m, 20m)
          - x = (0 + 0.5) * 10 = 5m
          - y = (1 + 0.5) * 10 = 15m
          - z = (1 + 1.0) * 10 = 20m
        
        Args:
            ix, iy, iz: 网格索引
            
        Returns:
            元组 (x, y, z)，表示世界坐标（米）
        """
        # X/Y方向：从0开始，中心点在 (index + 0.5) * resolution
        x = (ix + 0.5) * self.spatial.dx
        y = (iy + 0.5) * self.spatial.dy
        
        # Z方向：从dz开始，中心点在 (index + 1.0) * resolution
        z = (iz + 1.0) * self.spatial.dz
        
        return x, y, z
    
    def summary(self) -> str:
        """
        生成网格系统的可读摘要信息
        
        包含内容：
        - 空间维度及分辨率
        - 时间维度及时步长
        - 总单元数和仿真时长
        - 高度和时间范围
        
        Returns:
            格式化的字符串摘要
        """
        lines = [
            "=" * 60,
            "时空网格系统摘要",
            "=" * 60,
            f"空间维度: {self.spatial.nx} × {self.spatial.ny} × {self.spatial.nz}",
            f"  分辨率: {self.spatial.dx}m × {self.spatial.dy}m × {self.spatial.dz}m",
            f"  总单元数: {self.spatial.total_cells:,}",
            f"时间维度: {self.temporal.nt} 个时间片",
            f"  时间步长: {self.temporal.dt_minutes} 分钟 ({self.temporal.dt_hours} 小时)",
            f"  总时长: {self.temporal.total_hours} 小时",
            f"四维张量形状: {self.shape}",
            f"高度范围: {self.spatial.dz}m - {self.spatial.nz * self.spatial.dz}m",
            f"时间范围: 0.0h - {self.temporal.total_hours}h",
            "=" * 60,
        ]
        return "\n".join(lines)


def create_grid_from_config(config_path: Optional[Union[str, Path]] = None) -> GridSystem:
    """
    从 YAML 配置文件创建网格系统
    
    加载步骤：
    1. 确定配置文件路径（默认或指定）
    2. 读取并解析 YAML 文件为 EasyDict 对象
    3. 选择场景配置（优先 macro_case_study，其次 micro_validation）
    4. 提取空间网格参数（支持直接读取或自动计算）
    5. 提取时间网格参数（从顶层 time 配置读取）
    6. 构建并返回 GridSystem 实例
    
    Args:
        config_path: 配置文件路径。如果为 None，使用默认的 micro_experiment.yaml。
        
    Returns:
        配置好的 GridSystem 实例
    """
    # 步骤1：确定配置文件路径
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "configs" / "micro_experiment.yaml"
    
    try:
        # 步骤2：导入依赖并读取配置文件
        import yaml
        from .load_config import EasyDict, _convert_to_easy_dict
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 步骤3：将字典转换为 EasyDict（支持点语法访问）
        config = _convert_to_easy_dict(config_data)
        
        # 步骤4：选择场景配置
        # 优先级：macro_case_study > micro_validation > 根配置
        if 'macro_case_study' in config:
            scenario = config.macro_case_study
        elif 'micro_validation' in config:
            scenario = config.micro_validation
        else:
            scenario = config
        
        # 步骤5：提取空间网格参数
        if hasattr(scenario, 'spatial_grid'):
            # 支持两种配置方式：
            # 方式1：直接指定 nx, ny, nz
            # 方式2：通过空间范围和分辨率自动计算
            spatial_cfg = SpatialGridConfig(
                nx=scenario.spatial_grid.nx if hasattr(scenario.spatial_grid, 'nx') else 
                   int((scenario.spatial_grid.x_max - scenario.spatial_grid.x_min) / scenario.spatial_grid.resolution_xy),
                ny=scenario.spatial_grid.ny if hasattr(scenario.spatial_grid, 'ny') else 
                   int((scenario.spatial_grid.y_max - scenario.spatial_grid.y_min) / scenario.spatial_grid.resolution_xy),
                nz=scenario.spatial_grid.nz if hasattr(scenario.spatial_grid, 'nz') else 
                   int((scenario.spatial_grid.z_max - scenario.spatial_grid.z_min) / scenario.spatial_grid.resolution_z),
                dx=scenario.spatial_grid.resolution_xy,
                dy=scenario.spatial_grid.resolution_xy,
                dz=scenario.spatial_grid.resolution_z
            )
        else:
            # 如果没有空间配置，使用默认值
            spatial_cfg = SpatialGridConfig()
        
        # 步骤6：提取时间网格参数
        # 注意：time 配置在根级别，不在场景内部
        temporal_cfg = TemporalGridConfig()
        if hasattr(config, 'time'):
            temporal_cfg = TemporalGridConfig(
                nt=config.time.total_slices if hasattr(config.time, 'total_slices') else 96,
                dt_minutes=config.time.slice_minutes if hasattr(config.time, 'slice_minutes') else 15.0
            )
        
        # 步骤7：构建并返回 GridSystem
        return GridSystem(spatial=spatial_cfg, temporal=temporal_cfg)
    
    except Exception as e:
        # 异常处理：加载失败时使用默认配置
        print(f"警告: 无法从 {config_path} 加载配置: {e}")
        print("使用默认网格配置。")
        return GridSystem()


# 便捷函数：快速获取默认网格系统
def get_micro_grid() -> GridSystem:
    """
    获取默认网格系统（微观验证尺度）
    区域：400x400x120m;
    单元：10mx10mx10m;
    96个时间片，15分钟时间步长;    
    Returns:
        默认的 GridSystem 实例
    """
    return GridSystem()

def get_macro_grid() -> GridSystem:
    """
    获取默认网格系统（宏观案例尺度）
    区域：5000x5000x120m;
    单元：50mx50mx10m;
    96个时间片，15分钟时间步长;    
    Returns:
        默认的 GridSystem 实例
    """
    return GridSystem(
        spatial=SpatialGridConfig(
            nx=100, ny=100, nz=12,
            dx=50.0, dy=50.0, dz=10.0
        ),

        temporal=TemporalGridConfig(
            nt=96, dt_minutes=15.0
        )
    )

if __name__ == "__main__":
    # ==================== 测试网格系统 ====================
    print("测试网格系统")
    print("=" * 60)
    
    # 步骤1：创建默认网格
    grid = get_micro_grid()
    
    # 步骤2：打印网格摘要
    print(grid.summary())
    
    # 步骤3：测试坐标数组生成
    print("\n坐标数组:")
    print(f"  X坐标（前5个）: {grid.x_coords[:5]}  (从0开始，中心在5m, 15m, ...)")
    print(f"  Y坐标（前5个）: {grid.y_coords[:5]}  (从0开始，中心在5m, 15m, ...)")
    print(f"  Z高度（前5个）: {grid.z_heights[:5]}  (安全高度，从10m开始)")
    print(f"  时间轴（前10个）: {grid.time_hours[:10]}")
    
    # 步骤4：测试坐标转换功能
    print("\n坐标转换测试:")
    print(f"  世界坐标 (100, 200, 50) -> 网格索引: {grid.world_to_grid(100, 200, 50)}")
    print(f"  网格索引 (2, 4, 5) -> 世界坐标: {grid.grid_to_world(2, 4, 5)}")
    print(f"  验证往返转换: {grid.world_to_grid(*grid.grid_to_world(2, 4, 5))}")
    print(f"  高度 50m -> 层索引: {grid.get_altitude_layer(50)}")
    print(f"  时间 8.5小时 -> 时间索引: {grid.get_time_index(8.5)}")
    
    # 步骤5：测试张量创建
    tensor = grid.create_empty_tensor()
    print(f"\n空张量形状: {tensor.shape}")
    print(f"空张量大小: {tensor.nbytes / (1024**2):.2f} MB")