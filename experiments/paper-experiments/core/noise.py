"""
动态社会噪声成本张量模块。

实现论文中使用的滋扰成本模型：

    Cost_noise(i, z, t)
        = I_noise(z) * rho_pop(i, t) * S_landuse(i) * T_penalty(i, t)

该模型将噪声视为正常飞行期间的确定性社会外部性。
在最终成本融合阶段，不应将其与坠机概率相乘。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple, Union

import numpy as np
import yaml

from core.grid_system import GridSystem, get_micro_grid, get_macro_grid


# 土地利用值类型：支持整数编码、字符串标签或 NumPy 整数类型
LanduseValue = Union[int, str, np.integer]


@dataclass
class NoiseConfig:
    """
    社会噪声成本配置类。

    土地利用分类遵循5类学术框架体系：

    1. 自然与开阔空间 (natural_open)
       - 水域、森林、公园、荒地
       - 低人类干扰区，噪声敏感度接近零

    2. 工业与物流区 (industrial_logistics)
       - 工厂、仓库、港口、建筑工地
       - 高背景噪声容忍区，敏感度低

    3. 基础设施与交通走廊 (infrastructure_transport)
       - 高速公路、铁路、立交桥、停车场
       - 具有交通背景噪声的动态噪声走廊

    4. 商业与行政混合区 (commercial_administrative)
       - 写字楼、购物中心、政务大厅
       - 中度敏感，昼间活跃模式

    5a. 居住区 (residential)
       - 住宅小区、公寓楼
       - 夜间极端敏感（睡眠保护）

    5b. 宁静服务区 (quiet_service)
       - 学校、医院、诊所、大学、图书馆
       - 昼间极端敏感（教学/医疗需要安静环境）

    S-T惩罚矩阵捕捉了各区域类型基于人类活动模式的噪声敏感度时间变化。
    """

    # ========== 基础物理参数 ==========
    reference_intensity: float = 55.0  # 参考噪声强度（分贝），用于计算高度衰减
    horizontal_distance: float = 10.0   # 水平距离参数 d（米），避免除零
    daytime_start: float = 7.0         # 昼间开始时间（小时），默认 07:00
    daytime_end: float = 20.0          # 昼间结束时间（小时），默认 20:00

    # ========== 土地利用敏感度系数 S_landuse ==========
    # 反映不同用地类型对无人机噪声的敏感程度（无量纲权重）
    landuse_sensitivity: Dict[str, float] = field(default_factory=lambda: {
        # 1. 自然与开阔空间：几乎无常住人口，对噪声不敏感
        "natural_open": 0.0,
        # 2. 工业与物流区：高背景噪声容忍，敏感度极低
        "industrial_logistics": 0.2,
        # 3. 基础设施与交通走廊：交通干线屏蔽效应，敏感度较低
        "infrastructure_transport": 0.3,
        # 4. 商业与行政混合区：中度敏感，昼间人口密集
        "commercial_administrative": 0.6,
        # 5a. 居住区：夜间极端敏感（睡眠保护）
        "residential": 1.0,
        # 5b. 宁静服务区：昼间极端敏感（教学/医疗需要安静）
        "quiet_service": 2.0,
    })

    # ========== 时间惩罚矩阵 T_penalty (S-T矩阵) ==========
    # 格式：(昼间惩罚系数, 夜间惩罚系数)
    # 反映不同用地类型在昼夜时段的敏感度差异
    # 参考论文 Table 6: 空间-时间敏感度矩阵
    time_penalty: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        # 1. 自然与开阔空间：昼夜均不敏感
        "natural_open": (1.0, 1.0),
        # 2. 工业与物流区：昼间有工人作业，夜间几乎无人
        "industrial_logistics": (1.0, 0.5),
        # 3. 基础设施与交通走廊：交通干线昼夜都有背景噪声
        "infrastructure_transport": (1.0, 1.5),
        # 4. 商业与行政混合区：昼间人口密集，夜间人口流失
        "commercial_administrative": (1.0, 1.5),
        # 5a. 居住区：夜间极端敏感（睡眠保护需求）
        "residential": (1.5, 10.0),
        # 5b. 宁静服务区：昼间极端敏感（教学/医疗需要安静环境）
        "quiet_service": (10.0, 10.0),
    })

    # ========== 土地利用编码映射表 ==========
    # 将数字编码或字符串标签映射到标准类别名称
    landuse_code_map: Dict[LanduseValue, str] = field(default_factory=lambda: {
        # === 数字编码映射（合成城市数据使用）===
        # 1. 自然与开阔空间
        0: "natural_open",      # 水域/森林/公园/荒地
        6: "natural_open",      # 备用编码
        
        # 2. 工业与物流区
        4: "industrial_logistics",  # 工厂/仓库/港口/工地
        
        # 3. 基础设施与交通走廊
        5: "infrastructure_transport",  # 铁路/高速/立交桥/停车场
        
        # 4. 商业与行政混合区
        2: "commercial_administrative",  # 写字楼/购物中心/政务大厅
        
        # 5a. 居住区
        1: "residential",       # 住宅区
        
        # 5b. 宁静服务区
        3: "quiet_service",     # 学校/医院/疗养院
        
        # === 字符串别名映射（OSM标签/真实数据使用）===
        # 1. 自然与开阔空间
        "green": "natural_open",
        "water": "natural_open",
        "forest": "natural_open",
        "park": "natural_open",
        "vacant": "natural_open",
        "natural": "natural_open",
        "leisure_park": "natural_open",
        
        # 2. 工业与物流区
        "industrial": "industrial_logistics",
        "factory": "industrial_logistics",
        "warehouse": "industrial_logistics",
        "port": "industrial_logistics",
        "construction": "industrial_logistics",
        "landuse_industrial": "industrial_logistics",
        "landuse_construction": "industrial_logistics",
        
        # 3. 基础设施与交通走廊
        "highway": "infrastructure_transport",
        "railway": "infrastructure_transport",
        "road": "infrastructure_transport",
        "transit": "infrastructure_transport",
        "parking": "infrastructure_transport",
        "interchange": "infrastructure_transport",
        
        # 4. 商业与行政混合区
        "commercial": "commercial_administrative",
        "retail": "commercial_administrative",
        "office": "commercial_administrative",
        "shopping": "commercial_administrative",
        "mall": "commercial_administrative",
        "government": "commercial_administrative",
        "administrative": "commercial_administrative",
        "landuse_commercial": "commercial_administrative",
        "landuse_retail": "commercial_administrative",
        
        # 5a. 居住区
        "residential": "residential",
        "housing": "residential",
        "apartment": "residential",
        "landuse_residential": "residential",
        
        # 5b. 宁静服务区
        "school": "quiet_service",
        "hospital": "quiet_service",
        "clinic": "quiet_service",
        "university": "quiet_service",
        "library": "quiet_service",
        "nursing_home": "quiet_service",
        "amenity_school": "quiet_service",
        "amenity_hospital": "quiet_service",
    })

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> "NoiseConfig":
        """
        从 YAML 配置文件加载可选的噪声参数。

        当前配置文件存储紧凑的 noise_sensitivity 部分。
        当仅提供全局昼间/夜间值时，此加载器保留论文中的逐用地类型 S-T 矩阵，
        仅覆盖匹配的用地类型基础敏感度。

        Args:
            yaml_path: YAML 配置文件路径

        Returns:
            NoiseConfig 实例

        Raises:
            FileNotFoundError: 配置文件不存在时抛出
        """
        # 步骤1: 验证配置文件存在性
        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            raise FileNotFoundError(f"配置文件未找到: {yaml_path}")

        # 步骤2: 读取 YAML 配置数据
        with open(yaml_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

        # 步骤3: 创建默认配置实例
        config = cls()
        noise_data = config_data.get("noise_sensitivity", {})

        # 步骤4: 提取用地敏感度配置并建立别名映射
        landuse_s = noise_data.get("landuse_s", {})
        alias_to_name = {
            # 1. 自然与开阔空间
            "forest": "natural_open",
            "water": "natural_open",
            "green_water": "natural_open",
            "park": "natural_open",
            "vacant": "natural_open",
            "natural": "natural_open",
            
            # 2. 工业与物流区
            "industrial": "industrial_logistics",
            "factory": "industrial_logistics",
            "warehouse": "industrial_logistics",
            "construction": "industrial_logistics",
            
            # 3. 基础设施与交通走廊
            "road": "infrastructure_transport",
            "road_commercial": "infrastructure_transport",
            "highway": "infrastructure_transport",
            "railway": "infrastructure_transport",
            "transit": "infrastructure_transport",
            
            # 4. 商业与行政混合区
            "commercial": "commercial_administrative",
            "retail": "commercial_administrative",
            "office": "commercial_administrative",
            
            # 5a. 居住区
            "residential": "residential",
            "housing": "residential",
            
            # 5b. 宁静服务区
            "school_hospital": "quiet_service",
            "school": "quiet_service",
            "hospital": "quiet_service",
            "clinic": "quiet_service",
            "university": "quiet_service",
        }

        # 步骤5: 遍历配置项，覆盖对应的敏感度值
        for raw_key, value in landuse_s.items():
            key = alias_to_name.get(str(raw_key), None)
            if key is not None:
                config.landuse_sensitivity[key] = float(value)

        return config


class DynamicNoiseCost:
    """生成4维社会噪声成本张量的核心类。

    输出张量形状: (nx, ny, nz, nt)
    分别对应: X轴网格数 × Y轴网格数 × Z轴高度层数 × T轴时间片数
    """

    def __init__(
        self,
        grid: Optional[GridSystem] = None,
        config: Optional[NoiseConfig] = None,
        config_path: Optional[Union[str, Path]] = None,
    ):
        """
        初始化动态噪声成本计算器。

        Args:
            grid: 网格系统实例，默认为微观验证网格
            config: 噪声配置对象，提供则直接使用
            config_path: 配置文件路径，提供则从 YAML 加载配置
        """
        # 步骤1: 初始化网格系统（默认使用微观验证网格）
        self.grid = grid or get_micro_grid()
        
        # 步骤2: 根据优先级加载配置：config_path > config > 默认配置
        if config_path is not None:
            self.config = NoiseConfig.from_yaml(config_path)
        else:
            self.config = config or NoiseConfig()

    def compute_noise_intensity(self) -> np.ndarray:
        """
        计算高度衰减项 I_noise(z)。

        使用论文中的反平方衰减公式：

            I_noise(z) = L_ref / (z^2 + d^2)

        其中：
            L_ref: 参考噪声强度（默认 55 dB）
            z: 飞行高度（米）
            d: 水平距离参数（默认 10 米，避免除零）

        Returns:
            1D 数组，形状为 (nz,)，表示每个高度层的噪声强度
        """
        # 步骤1: 获取所有高度层坐标（转换为 float64 保证精度）
        z = self.grid.z_heights.astype(np.float64)
        
        # 步骤2: 获取水平距离参数
        d = float(self.config.horizontal_distance)
        
        # 步骤3: 应用反平方衰减公式计算各高度层的噪声强度
        return self.config.reference_intensity / (np.square(z) + d * d)

    def canonicalize_landuse(self, landuse: np.ndarray) -> np.ndarray:
        """
        将土地利用编码或标签转换为标准类别名称。

        功能说明：
        - 统一处理数字编码和字符串标签两种输入格式
        - 通过 landuse_code_map 映射表进行标准化转换
        - 确保后续计算使用一致的类别标识符

        Args:
            landuse: 2D 数组 (nx, ny)，包含整数编码或字符串标签

        Returns:
            对象数组，形状为 (nx, ny)，元素为标准类别名称字符串

        Raises:
            ValueError: 遇到未定义的用地类型值时抛出
        """
        # 步骤1: 转换为 NumPy 数组并验证空间维度
        landuse = np.asarray(landuse)
        self._validate_xy_shape(landuse, "landuse")

        # 步骤2: 创建空对象数组用于存储标准化结果
        canonical = np.empty(landuse.shape, dtype=object)
        
        # 步骤3: 遍历所有唯一的用地类型值
        for raw_value in np.unique(landuse):
            # 处理 NumPy 标量类型，转换为 Python 原生类型
            key: LanduseValue
            if isinstance(raw_value, np.generic):
                key = raw_value.item()
            else:
                key = raw_value

            # 步骤4: 检查映射表中是否存在该值
            if key not in self.config.landuse_code_map:
                raise ValueError(
                    f"未知的用地类型值 {raw_value!r}。"
                    "请在 NoiseConfig.landuse_code_map 中添加该映射关系。"
                )

            # 步骤5: 将所有等于该值的网格单元映射为标准类别名称
            canonical[landuse == raw_value] = self.config.landuse_code_map[key]

        return canonical

    def compute_landuse_sensitivity(self, landuse: np.ndarray) -> np.ndarray:
        """
        计算空间敏感度系数 S_landuse(i)。

        功能说明：
        - 根据用地类型查找对应的敏感度系数
        - 生成与空间网格同形状的2D敏感度分布图
        - 反映不同区域对无人机噪声的静态敏感程度

        Args:
            landuse: 2D 用地类型编码或标签地图，形状 (nx, ny)

        Returns:
            2D 浮点数组，形状 (nx, ny)，表示每个网格单元的敏感度系数
        """
        # 步骤1: 标准化用地类型标签
        canonical = self.canonicalize_landuse(landuse)
        
        # 步骤2: 初始化敏感度数组（默认值为0）
        sensitivity = np.zeros(canonical.shape, dtype=np.float32)

        # 步骤3: 遍历所有用地类型，填充对应的敏感度值
        for name, value in self.config.landuse_sensitivity.items():
            sensitivity[canonical == name] = float(value)

        return sensitivity

    def compute_time_penalty(self, landuse: np.ndarray) -> np.ndarray:
        """
        计算 S-T 矩阵查表 T_penalty(i, t)。

        功能说明：
        - 根据用地类型和时间片查找对应的时间惩罚系数
        - 昼间定义为 [daytime_start, daytime_end)，默认 07:00-20:00
        - 生成3D时空惩罚张量，捕捉敏感度的时间异质性

        Args:
            landuse: 2D 用地类型编码或标签地图，形状 (nx, ny)

        Returns:
            3D 浮点数组，形状 (nx, ny, nt)，表示每个网格单元在各时间片的惩罚系数
        """
        # 步骤1: 标准化用地类型标签
        canonical = self.canonicalize_landuse(landuse)
        nx, ny = canonical.shape
        nt = self.grid.temporal.nt
        
        # 步骤2: 初始化惩罚张量（默认值为1.0，表示无惩罚）
        penalty = np.ones((nx, ny, nt), dtype=np.float32)

        # 步骤3: 计算每个时间片是否为昼间
        hours = np.mod(self.grid.time_hours, 24.0)  # 处理跨天情况
        is_day = (
            (hours >= self.config.daytime_start)
            & (hours < self.config.daytime_end)
        )

        # 步骤4: 遍历所有用地类型，填充昼夜惩罚系数
        for name, (day_value, night_value) in self.config.time_penalty.items():
            # 创建当前用地类型的空间掩码
            mask = canonical == name
            if not np.any(mask):
                continue  # 跳过不存在的用地类型

            # 步骤4a: 先全部设置为夜间惩罚系数
            penalty[mask, :] = float(night_value)
            
            # 步骤4b: 对昼间时间片覆盖为昼间惩罚系数
            for time_idx, day_flag in enumerate(is_day):
                if day_flag:
                    penalty[:, :, time_idx][mask] = float(day_value)

        return penalty

    def compute_noise_cost(
        self,
        landuse: np.ndarray,
        population_density: np.ndarray,
        normalize: bool = False,
        dtype=np.float32,
    ) -> np.ndarray:
        """
        计算完整的4维社会噪声成本张量。

        核心公式：
            Cost_noise(i, z, t) = I_noise(z) * rho_pop(i, t) * S_landuse(i) * T_penalty(i, t)

        计算步骤：
        1. 广播人口密度到4D网格
        2. 计算空间敏感度 S_landuse
        3. 计算时间惩罚 T_penalty
        4. 计算高度衰减 I_noise
        5. 逐项相乘得到噪声成本张量
        6. 处理异常值（NaN/Inf）
        7. 可选的归一化处理

        Args:
            landuse: 2D 用地类型编码或标签地图，形状 (nx, ny)
            population_density: 人口密度，支持以下形状：
                - (nx, ny): 静态人口地图（推荐）
                  → 广播后所有高度、所有时间相同
                - (nx, ny, nt): 动态2D人口地图（推荐）
                  → 广播后同一时间片内所有高度相同，但随时间变化
                  → 适用于 WorldPop、手机信令等主流数据源
                - (nx, ny, nz, nt): 动态3D人口地图（可选）
                  → 不同高度有不同的人口暴露
                  → 需要建筑楼层人口分布数据（较少见）
            
            注意：由于真实世界的人口数据通常没有高度维度，
                 推荐使用 (nx, ny) 或 (nx, ny, nt) 格式。
                 系统会自动通过广播机制扩展到4D。
            
            normalize: 是否进行 min-max 归一化到 [0, 1]
            dtype: 输出数据类型

        Returns:
            4D 数组，形状 (nx, ny, nz, nt)，表示噪声成本张量
        
        示例：
            # 使用2D动态人口（最常见场景）
            population_2d_time = np.ones((nx, ny, nt)) * 100  # 每格100人
            population_2d_time[:, :, night_hours] = 150       # 夜间人口增加（回家）
            noise_cost = model.compute_noise_cost(landuse, population_2d_time)
            # 结果：同一时间片内，所有高度的噪声成本相同
            #       但不同时间片的噪声成本不同（捕捉昼夜差异）
        """
        # 步骤1: 将人口密度广播为4D格式 (nx, ny, nz, nt)
        population_4d = self._as_population_4d(population_density)
        
        # 步骤2: 计算三个核心分量
        s_landuse = self.compute_landuse_sensitivity(landuse)      # 空间敏感度 S(i)
        t_penalty = self.compute_time_penalty(landuse)             # 时间惩罚 T(i,t)
        i_noise = self.compute_noise_intensity()                   # 高度衰减 I(z)

        # 步骤3: 通过广播机制逐项相乘，生成4D噪声成本张量
        # 
        # 维度对齐说明（以动态2D人口为例）：
        #   I_noise:     (1, 1, nz, 1)    - 仅在Z轴变化（高度衰减）
        #   population:  (nx, ny, nz, nt) - 全维度（由2D/3D输入广播而来）
        #                * 若输入为 (nx, ny): 所有高度、时间相同
        #                * 若输入为 (nx, ny, nt): 同时间片内所有高度相同
        #                * 若输入为 (nx, ny, nz, nt): 各高度可不同
        #   S_landuse:   (nx, ny, 1, 1)   - 仅在XY平面变化（用地类型敏感度）
        #   T_penalty:   (nx, ny, 1, nt)  - 在XYT维度变化（时间惩罚与高度无关）
        #
        # 物理意义：
        #   Cost_noise(x, y, z, t) = I(z) × ρ_pop(x,y,z,t) × S(x,y) × T(x,y,t)
        #   - I(z): 越高噪声越小（反平方衰减）
        #   - ρ_pop: 该位置的暴露人口（可能随高度变化，但通常假设相同）
        #   - S(x,y): 该地块的用地类型决定基础敏感度
        #   - T(x,y,t): 该地块在不同时间的敏感度变化（昼夜差异）
        noise_cost = (
            i_noise[np.newaxis, np.newaxis, :, np.newaxis]
            * population_4d
            * s_landuse[:, :, np.newaxis, np.newaxis]
            * t_penalty[:, :, np.newaxis, :]
        )

        # 步骤4: 处理数值异常（NaN替换为0，正无穷替换为最大值，负无穷替换为0）
        noise_cost = np.nan_to_num(
            noise_cost,
            nan=0.0,
            posinf=float(np.finfo(np.float32).max),
            neginf=0.0,
        )

        # 步骤5: 可选的归一化处理
        if normalize:
            noise_cost = self._minmax_normalize(noise_cost)

        return noise_cost.astype(dtype, copy=False)

    def get_component_summary(
        self,
        landuse: np.ndarray,
        population_density: np.ndarray,
    ) -> str:
        """
        返回简短的文本摘要，适用于实验日志记录。

        功能说明：
        - 显示各分量的统计范围
        - 便于快速诊断数据异常
        - 记录关键指标用于实验对比

        Args:
            landuse: 2D 用地类型地图
            population_density: 人口密度数据

        Returns:
            格式化的摘要字符串
        """
        # 步骤1: 计算完整噪声成本及各分量
        noise = self.compute_noise_cost(landuse, population_density, normalize=False)
        s_landuse = self.compute_landuse_sensitivity(landuse)
        t_penalty = self.compute_time_penalty(landuse)
        i_noise = self.compute_noise_intensity()

        # 步骤2: 构建摘要信息行
        lines = [
            "=" * 70,
            "动态社会噪声成本摘要",
            "=" * 70,
            f"网格形状: {self.grid.shape}",
            f"I_noise 范围: [{i_noise.min():.6f}, {i_noise.max():.6f}]",
            f"S_landuse 范围: [{s_landuse.min():.3f}, {s_landuse.max():.3f}]",
            f"T_penalty 范围: [{t_penalty.min():.3f}, {t_penalty.max():.3f}]",
            f"人口数据形状: {np.asarray(population_density).shape}",
            f"噪声成本范围: [{noise.min():.6f}, {noise.max():.6f}]",
            f"噪声成本均值: {noise.mean():.6f}",
            "=" * 70,
        ]
        return "\n".join(lines)

    def _as_population_4d(self, population_density: np.ndarray) -> np.ndarray:
        """
        将人口密度广播为网格形状 (nx, ny, nz, nt)。

        功能说明：
        - 支持三种输入格式的自动检测和转换
        - 保持人口数据的原始分布特征
        - 通过广播机制扩展到4D空间
        
        重要说明：
        由于真实世界的人口数据（如 WorldPop、人口普查）通常没有高度维度，
        推荐使用 2D 格式输入。广播后的行为如下：
        
        1. 静态2D (nx, ny):
           → 所有高度层、所有时间片的人口密度相同
           → 适用于粗略估算或数据缺失场景
        
        2. 动态2D (nx, ny, nt):  
           → 同一时间片内，所有高度层的人口密度相同
           → 不同时间片可以有不同的密度（捕捉昼夜潮汐）
           → 适用于大多数实际应用场景
        
        3. 动态3D (nx, ny, nz, nt):
           → 不同高度层可以有不同的人口密度
           → 需要建筑楼层级别的精细数据（较少见）
           → 仅在有精确的垂直人口分布数据时使用

        Args:
            population_density: 人口密度数组，支持以下形状：
                - (nx, ny): 静态2D地图
                - (nx, ny, nt): 动态2D地图（随时间变化）
                - (nx, ny, nz, nt): 动态3D地图（随高度和时间变化）

        Returns:
            4D 数组，形状 (nx, ny, nz, nt)
            
        示例：
            # 动态2D人口：白天商业区人多，晚上住宅区人多
            pop = np.ones((nx, ny, nt)) * 50
            pop[commercial_area, daytime] = 200  # 商业区白天200人
            pop[residential_area, nighttime] = 150  # 住宅区夜间150人
            pop_4d = model._as_population_4d(pop)
            # 结果：pop_4d[x, y, :, t] 在所有高度 z 上相同
        """
        pop = np.asarray(population_density, dtype=np.float64)
        nx, ny, nz, nt = self.grid.shape

        # 情况1: 静态2D人口地图 (nx, ny) -> 广播到 (nx, ny, nz, nt)
        # 特点：所有高度、所有时间的人口密度完全相同
        if pop.shape == (nx, ny):
            return np.broadcast_to(
                pop[:, :, np.newaxis, np.newaxis],
                (nx, ny, nz, nt),
            ).copy()

        # 情况2: 动态2D人口地图 (nx, ny, nt) -> 广播到 (nx, ny, nz, nt)
        # 特点：同一时间片内所有高度相同，但随时间变化
        if pop.shape == (nx, ny, nt):
            return np.broadcast_to(
                pop[:, :, np.newaxis, :],
                (nx, ny, nz, nt),
            ).copy()

        # 情况3: 已经是4D格式 (nx, ny, nz, nt) -> 直接返回
        # 特点：不同高度可以有不同的人口分布（需要精细数据支持）
        if pop.shape == (nx, ny, nz, nt):
            return pop

        # 异常情况：形状不匹配
        raise ValueError(
            "population_density 的形状必须为 "
            f"(nx, ny)、(nx, ny, nt) 或 (nx, ny, nz, nt)；"
            f"实际得到 {pop.shape}，"
            f"期望 ({nx}, {ny})、({nx}, {ny}, {nt}) 或 ({nx}, {ny}, {nz}, {nt})。"
        )

    def _validate_xy_shape(self, array: np.ndarray, name: str):
        """
        验证数组的空间维度是否与网格系统匹配。

        Args:
            array: 待验证的数组
            name: 数组名称（用于错误提示）

        Raises:
            ValueError: 形状不匹配时抛出
        """
        expected = (self.grid.spatial.nx, self.grid.spatial.ny)
        if array.shape != expected:
            raise ValueError(f"{name} 的形状必须为 {expected}；实际得到 {array.shape}。")

    @staticmethod
    def _minmax_normalize(tensor: np.ndarray) -> np.ndarray:
        """
        对张量进行 min-max 归一化到 [0, 1] 区间。

        公式：
            normalized = (tensor - min) / (max - min)

        Args:
            tensor: 输入张量

        Returns:
            归一化后的张量，形状不变
        """
        min_val = float(np.min(tensor))
        max_val = float(np.max(tensor))
        
        # 边界情况：最大值等于最小值时返回零数组
        if max_val <= min_val:
            return np.zeros_like(tensor)
        
        return (tensor - min_val) / (max_val - min_val)


def get_micro_grid_noise_model(
    config_path: Optional[Union[str, Path]] = None,
) -> DynamicNoiseCost:
    """
    微观验证场景的噪声模型工厂函数。

    Args:
        config_path: 可选的配置文件路径

    Returns:
        配置好的 DynamicNoiseCost 实例
    """
    return DynamicNoiseCost(grid=get_micro_grid(), config_path=config_path)


def get_macro_grid_noise_model(
    config_path: Optional[Union[str, Path]] = None,
) -> DynamicNoiseCost:
    """
    宏观案例研究场景的噪声模型工厂函数。

    Args:
        config_path: 可选的配置文件路径

    Returns:
        配置好的 DynamicNoiseCost 实例
    """
    return DynamicNoiseCost(grid=get_macro_grid(), config_path=config_path)


if __name__ == "__main__":
    """
    主程序入口：演示噪声成本张量的计算流程。
    
    测试场景：
    - 使用微观验证网格 (60×60×12×96)
    - 构建包含5类用地的合成城市场景
    - 设置差异化的人口密度分布
    - 计算并输出归一化噪声成本张量
    """
    # 步骤1: 初始化网格系统和噪声模型
    grid = get_micro_grid()
    model = DynamicNoiseCost(grid=grid)

    # 步骤2: 获取网格维度
    nx, ny, nz, nt = grid.shape
    
    # 步骤3: 创建土地利用地图（根据新的5类分类体系）
    landuse = np.zeros((nx, ny), dtype=np.int32)
    landuse[: nx // 2, : ny // 2] = 1           # 5a. 居住区（住宅区）
    landuse[nx // 2 :, ny // 2 :] = 4           # 2. 工业与物流区（工业区）
    landuse[10:20, 10:20] = 3                   # 5b. 宁静服务区（学校/医院）
    landuse[25:35, 25:35] = 2                   # 4. 商业与行政混合区（商业区）
    landuse[5:15, 30:40] = 0                    # 1. 自然与开阔空间（水域/森林）
    landuse[30:38, 5:15] = 5                    # 3. 基础设施与交通走廊（主干道）

    # 步骤4: 创建动态人口密度分布（随用地类型变化）
    population = np.ones((nx, ny, nt), dtype=np.float32)
    population[landuse == 1, :] = 50.0          # 居住区：高人口密度
    population[landuse == 3, :] = 30.0          # 学校/医院：中等人口密度
    population[landuse == 2, :] = 40.0          # 商业区：中高人口密度
    population[landuse == 4, :] = 15.0          # 工业区：低人口密度

    # 步骤5: 计算归一化噪声成本张量
    noise_cost = model.compute_noise_cost(landuse, population, normalize=True)
    
    # 步骤6: 输出组件摘要和统计信息
    print(model.get_component_summary(landuse, population))
    print(f"归一化噪声张量形状: {noise_cost.shape}")
    print(f"归一化范围: [{noise_cost.min():.4f}, {noise_cost.max():.4f}]")
