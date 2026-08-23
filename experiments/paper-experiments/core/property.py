"""
静态障碍物成本模型 - Static Obstacle Cost Models

包含两类成本：
1. 城市峡谷风险指数 (用于动态 P_crash 计算)
2. 财产损失风险成本 (待实现)

参考论文第 3.4 节：城市峡谷效应与建筑障碍物建模
"""

import numpy as np
from typing import Optional, Union
from pathlib import Path


class StaticBuildingObstacle:
    """
    静态建筑障碍物模型 - 用于计算城市峡谷风险指数 R_canyon
    
    根据论文公式 (3.4.2):
    R_canyon(x,y,z) = w_1 * (1 - SVF)^α + w_2 * (H_avg / (z + ε)) + w_3 * D_building
    
    其中:
    - SVF: 天空可视因子 (Sky View Factor), 0 ≤ SVF ≤ 1
    - H_avg: 周围建筑物平均高度 (m)
    - z: 无人机当前飞行高度 (m)
    - D_building: 到最近建筑物的归一化距离倒数
    - w_1, w_2, w_3: 权重系数 (w_1 + w_2 + w_3 = 1)
    - α: SVF 非线性指数 (建议 1-2)
    - ε: 防除零常数 (如 10^-6)
    
    最终风险放大系数:
    f_obs(x,y,z) = 1 + K_obs * R_canyon(x,y,z)
    """
    
    def __init__(
        self,
        svf: np.ndarray,
        building_heights: np.ndarray,
        dist_to_building: np.ndarray,
        config_path: Optional[str] = None,
        K_obs: float = 10.0,
        w_svf: float = 0.4,
        w_height_ratio: float = 0.4,
        w_proximity: float = 0.2,
        alpha_svf: float = 1.5,
        epsilon: float = 1e-6
    ):
        """
        初始化静态建筑障碍物模型
        
        Args:
            svf: 天空可视因子数组 (nx, ny) 或 (ny, nx)，值域 [0, 1]
            building_heights: 建筑高度矩阵 (nx, ny) 或 (ny, nx)，单位 m
            dist_to_building: 到最近建筑的距离场 (nx, ny, nz) 或 (ny, nx, nz)，单位 m
            config_path: YAML 配置文件路径（可选），优先从配置加载参数
            K_obs: 城市峡谷最大风险放大倍数（建议 5-20）
            w_svf: 天空遮挡项权重
            w_height_ratio: 相对高度比权重
            w_proximity: 建筑邻近度权重
            alpha_svf: SVF 非线性指数（建议 1-2）
            epsilon: 防止除零的极小常数
            
        Note:
            如果提供 config_path，将从 YAML 文件加载 urban_canyon 相关参数
            否则使用传入的参数值
        """
        # 从配置文件加载参数（如果提供）
        if config_path is not None:
            config = self._load_config_from_yaml(config_path)
            K_obs = config.get('K_obs', K_obs)
            w_svf = config.get('w_svf', w_svf)
            w_height_ratio = config.get('w_height_ratio', w_height_ratio)
            w_proximity = config.get('w_proximity', w_proximity)
            alpha_svf = config.get('alpha_svf', alpha_svf)
            epsilon = config.get('epsilon', epsilon)
        
        # 验证输入数据维度一致性
        assert svf.ndim == 2, f"SVF 应为 2D 数组，当前维度: {svf.ndim}"
        assert building_heights.ndim == 2, f"建筑高度应为 2D 数组，当前维度: {building_heights.ndim}"
        assert dist_to_building.ndim == 3, f"距离场应为 3D 数组，当前维度: {dist_to_building.ndim}"
        
        # 确保 SVF 值域合法
        assert np.all((svf >= 0) & (svf <= 1)), "SVF 值必须在 [0, 1] 范围内"
        
        # 存储输入数据
        self.svf = svf.astype(np.float64)
        self.building_heights = building_heights.astype(np.float64)
        self.dist_to_building = dist_to_building.astype(np.float64)
        
        # 存储模型参数
        self.K_obs = K_obs
        self.w_svf = w_svf
        self.w_height_ratio = w_height_ratio
        self.w_proximity = w_proximity
        self.alpha_svf = alpha_svf
        self.epsilon = epsilon
        
        # 验证权重和为 1
        weight_sum = w_svf + w_height_ratio + w_proximity
        if not np.isclose(weight_sum, 1.0, atol=1e-6):
            print(f"警告: 权重和 {weight_sum:.4f} 不等于 1，将自动归一化")
            norm_factor = weight_sum
            self.w_svf /= norm_factor
            self.w_height_ratio /= norm_factor
            self.w_proximity /= norm_factor
    
    def _load_config_from_yaml(self, config_path: str) -> dict:
        """
        从 YAML 配置文件加载城市峡谷参数
        
        Args:
            config_path: YAML 文件路径
            
        Returns:
            包含 urban_canyon 参数的字典
        """
        yaml_file = Path(config_path)
        if not yaml_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        try:
            import yaml
            with open(yaml_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # 提取 urban_canyon 参数
            urban_canyon_data = config_data.get('crash_probability', {}).get('urban_canyon', {})
            
            if not urban_canyon_data:
                print(f"警告: 配置文件中未找到 urban_canyon 参数，使用默认值")
                return {}
            
            return {
                'K_obs': urban_canyon_data.get('K_obs', self.K_obs),
                'w_svf': urban_canyon_data.get('w_svf', self.w_svf),
                'w_height_ratio': urban_canyon_data.get('w_height_ratio', self.w_height_ratio),
                'w_proximity': urban_canyon_data.get('w_proximity', self.w_proximity),
                'alpha_svf': urban_canyon_data.get('alpha_svf', self.alpha_svf),
                'epsilon': urban_canyon_data.get('epsilon', self.epsilon),
            }
        except ImportError:
            print("警告: 未安装 pyyaml 库，无法加载 YAML 配置，使用默认参数")
            return {}
    
    def compute_r_canyon(self, flight_altitude: Optional[Union[float, np.ndarray]] = None) -> np.ndarray:
        """
        计算城市峡谷风险指数 R_canyon
        
        公式:
        R_canyon = w_1 * (1 - SVF)^α + w_2 * (H_avg / (z + ε)) + w_3 * D_building
        
        Args:
            flight_altitude: 无人机飞行高度 (m)
                             - 如果为标量，对所有网格点使用相同高度
                             - 如果为数组，形状应为 (nx, ny) 或 (ny, nx)
                             - 如果为 None，使用建筑高度的平均值作为参考高度
        
        Returns:
            城市峡谷风险指数数组，形状与输入数据一致 (nx, ny) 或 (ny, nx)
        """
        # 确定飞行高度
        if flight_altitude is None:
            # 使用建筑平均高度作为参考
            avg_height = float(np.mean(self.building_heights[self.building_heights > 0]))
            flight_altitude = avg_height if avg_height > 0 else 30.0  # 默认 30m
        
        if isinstance(flight_altitude, (int, float)):
            # 标量高度，广播到所有位置
            z = np.full_like(self.building_heights, float(flight_altitude))
        else:
            # 数组高度，确保维度匹配
            z = np.asarray(flight_altitude, dtype=np.float64)
            assert z.shape == self.building_heights.shape, \
                f"飞行高度数组形状 {z.shape} 与建筑高度 {self.building_heights.shape} 不匹配"
        
        # 三项分量计算
        
        # 1. 天空遮挡项: (1 - SVF)^α
        # 反映 GPS 信号质量和视觉传感器视野受限程度
        sky_occlusion = np.power(1.0 - self.svf, self.alpha_svf)
        
        # 2. 相对高度比: H_avg / (z + ε)
        # 反映无人机相对于周围建筑的"淹没程度"
        height_ratio = self.building_heights / (z + self.epsilon)
        
        # 3. 建筑邻近度: D_building (已经是归一化的距离倒数)
        # 反映直接碰撞风险和气流扰动强度
        proximity = self.dist_to_building[:, :, 0] if self.dist_to_building.ndim == 3 else self.dist_to_building
        
        # 加权求和得到 R_canyon
        R_canyon = (
            self.w_svf * sky_occlusion +
            self.w_height_ratio * height_ratio +
            self.w_proximity * proximity
        )
        
        return R_canyon
    
    def compute_f_obs(self, flight_altitude: Optional[Union[float, np.ndarray]] = None) -> np.ndarray:
        """
        计算城市峡谷风险放大系数 f_obs
        
        公式:
        f_obs = 1 + K_obs * R_canyon
        
        Args:
            flight_altitude: 无人机飞行高度 (m)，同 compute_r_canyon
        
        Returns:
            风险放大系数数组，值域 [1, 1+K_obs]
        """
        R_canyon = self.compute_r_canyon(flight_altitude)
        
        # 归一化 R_canyon 到 [0, 1] 范围
        R_max = np.max(R_canyon)
        if R_max > 0:
            R_normalized = R_canyon / R_max
        else:
            R_normalized = np.zeros_like(R_canyon)
        
        # 计算风险放大系数
        f_obs = 1.0 + self.K_obs * R_normalized
        
        return f_obs
    
    def get_component_contributions(
        self, 
        flight_altitude: Optional[Union[float, np.ndarray]] = None
    ) -> dict:
        """
        获取三项分量的独立贡献（用于敏感性分析）
        
        Args:
            flight_altitude: 无人机飞行高度 (m)
        
        Returns:
            包含各分量贡献的字典:
            - sky_occlusion: 天空遮挡项贡献
            - height_ratio: 相对高度比贡献
            - proximity: 建筑邻近度贡献
            - R_canyon: 总风险指数
            - f_obs: 风险放大系数
        """
        if flight_altitude is None:
            avg_height = float(np.mean(self.building_heights[self.building_heights > 0]))
            flight_altitude = avg_height if avg_height > 0 else 30.0
        
        if isinstance(flight_altitude, (int, float)):
            z = np.full_like(self.building_heights, float(flight_altitude))
        else:
            z = np.asarray(flight_altitude, dtype=np.float64)
        
        # 计算各分量
        sky_occlusion = self.w_svf * np.power(1.0 - self.svf, self.alpha_svf)
        height_ratio = self.w_height_ratio * (self.building_heights / (z + self.epsilon))
        proximity = self.w_proximity * (
            self.dist_to_building[:, :, 0] if self.dist_to_building.ndim == 3 
            else self.dist_to_building
        )
        
        R_canyon = sky_occlusion + height_ratio + proximity
        
        # 归一化
        R_max = np.max(R_canyon)
        R_normalized = R_canyon / R_max if R_max > 0 else np.zeros_like(R_canyon)
        f_obs = 1.0 + self.K_obs * R_normalized
        
        return {
            'sky_occlusion': sky_occlusion,
            'height_ratio': height_ratio,
            'proximity': proximity,
            'R_canyon': R_canyon,
            'f_obs': f_obs,
        }
    
    def validate_boundary_conditions(self) -> dict:
        """
        验证边界条件（对应论文表 3.4.4）
        
        Returns:
            包含典型场景测试结果的字典
        """
        test_scenarios = {
            'open_area': {'svf': 1.0, 'H_avg': 0.0, 'D_build': 0.0},
            'low_density': {'svf': 0.8, 'H_avg': 10.0, 'D_build': 0.2},
            'medium_density': {'svf': 0.5, 'H_avg': 30.0, 'D_build': 0.5},
            'high_density': {'svf': 0.2, 'H_avg': 50.0, 'D_build': 0.8},
            'urban_canyon': {'svf': 0.0, 'H_avg': 80.0, 'D_build': 1.0},
        }
        
        results = {}
        z_test = 30.0  # 测试高度 30m
        
        for scenario, values in test_scenarios.items():
            # 手动计算 R_canyon
            R = (
                self.w_svf * np.power(1.0 - values['svf'], self.alpha_svf) +
                self.w_height_ratio * (values['H_avg'] / (z_test + self.epsilon)) +
                self.w_proximity * values['D_build']
            )
            
            # 归一化（假设最大值为高密度场景）
            R_norm = R / 1.0  # 简化归一化
            f_obs = 1.0 + self.K_obs * R_norm
            
            results[scenario] = {
                'R_canyon': R,
                'f_obs': f_obs,
                'description': self._get_scenario_description(scenario)
            }
        
        return results
    
    @staticmethod
    def _get_scenario_description(scenario: str) -> str:
        """获取场景描述"""
        descriptions = {
            'open_area': '开阔地 - 无放大',
            'low_density': '低密度区 - 轻度影响',
            'medium_density': '中密度区 - 中度影响',
            'high_density': '高密度区 - 显著影响',
            'urban_canyon': '城市峡谷 - 极高风险',
        }
        return descriptions.get(scenario, '未知场景')


class PropertyDamageModel:
    """
    财产损失评估模型
    
    根据论文第 3.X 节，财产损失成本应考虑:
    - 建筑价值分布（与高度、类型相关）
    - 撞击概率（来自 P_crash 模型）
    - 损坏程度评估（部分损坏 vs 完全损毁）
    
    核心公式:
    C_property(x,y,z,t) = P_crash(x,y,z,t) × V_building(x,y) × η_damage(H, type)
    
    其中:
    - P_crash: 坠机概率（来自 DynamicCrashProbability）
    - V_building: 建筑价值（与高度正相关）
    - η_damage: 损坏系数（0-1，取决于撞击能量和建筑类型）
    """
    
    def __init__(
        self,
        building_heights: np.ndarray,
        building_types: Optional[np.ndarray] = None,
        config_path: Optional[str] = None,
        max_prop_damage: float = 1000.0,
        log_normal_mu: float = 3.04,
        log_normal_sigma: float = 0.5
    ):
        """
        初始化财产损失评估模型
        
        Args:
            building_heights: 建筑高度矩阵 (nx, ny)，单位 m
            building_types: 建筑类型矩阵 (nx, ny)，可选
                           0: 住宅, 1: 商业, 2: 工业, 3: 公共设施
            config_path: YAML 配置文件路径（可选）
            max_prop_damage: 最大财产损失上限（货币单位）
            log_normal_mu: 建筑价值对数正态分布均值（基于新加坡/日本数据）
            log_normal_sigma: 建筑价值对数正态分布标准差
            
        Note:
            建筑价值估算采用对数正态分布模型:
            V_building ~ LogNormal(μ + α·ln(H), σ²)
            其中 H 为建筑高度，α 为高度弹性系数
        """
        # 从配置文件加载参数（如果提供）
        if config_path is not None:
            config = self._load_config_from_yaml(config_path)
            max_prop_damage = config.get('max_prop_damage', max_prop_damage)
            log_normal_mu = config.get('log_normal_mu', log_normal_mu)
            log_normal_sigma = config.get('log_normal_sigma', log_normal_sigma)
        
        # 验证输入数据
        assert building_heights.ndim == 2, f"建筑高度应为 2D 数组，当前维度: {building_heights.ndim}"
        assert np.all(building_heights >= 0), "建筑高度不能为负值"
        
        # 存储输入数据
        self.building_heights = building_heights.astype(np.float64)
        self.building_types = building_types
        self.nx, self.ny = building_heights.shape
        
        # 存储模型参数
        self.max_prop_damage = max_prop_damage
        self.log_normal_mu = log_normal_mu
        self.log_normal_sigma = log_normal_sigma
        
        # 预计算建筑价值（假设高度弹性系数 α=0.8）
        self.alpha_height = 0.8
        self.property_values = self._estimate_property_values()
        
        # 建筑类型价值乘数（如果有类型数据）
        if building_types is not None:
            self.type_multipliers = self._get_type_multipliers()
        else:
            self.type_multipliers = np.ones_like(building_heights)
    
    def _load_config_from_yaml(self, config_path: str) -> dict:
        """
        从 YAML 配置文件加载财产损失参数
        
        Args:
            config_path: YAML 文件路径
            
        Returns:
            包含 property_risk 参数的字典
        """
        yaml_file = Path(config_path)
        if not yaml_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        try:
            import yaml
            with open(yaml_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # 提取 property_risk 参数
            property_risk_data = config_data.get('property_risk', {})
            
            if not property_risk_data:
                print(f"警告: 配置文件中未找到 property_risk 参数，使用默认值")
                return {}
            
            return {
                'max_prop_damage': property_risk_data.get('max_prop_damage', self.max_prop_damage),
                'log_normal_mu': property_risk_data.get('log_normal_mu', self.log_normal_mu),
                'log_normal_sigma': property_risk_data.get('log_normal_sigma', self.log_normal_sigma),
            }
        except ImportError:
            print("警告: 未安装 pyyaml 库，无法加载 YAML 配置，使用默认参数")
            return {}
    
    def _estimate_property_values(self) -> np.ndarray:
        """
        估算建筑价值
        
        采用对数正态分布模型:
        ln(V) ~ N(μ + α·ln(H), σ²)
        
        Returns:
            建筑价值矩阵 (nx, ny)，已限制在 [0, max_prop_damage] 范围内
        """
        # 避免对零高度取对数
        heights_safe = np.where(
            self.building_heights > 0,
            self.building_heights,
            1.0  # 无建筑区域设为最小值
        )
        
        # 计算对数正态分布的参数
        mu_adjusted = self.log_normal_mu + self.alpha_height * np.log(heights_safe)
        
        # 生成建筑价值（使用中位数而非均值，更稳健）
        property_values = np.exp(mu_adjusted)
        
        # 应用建筑类型乘数
        property_values *= self._get_type_multipliers()
        
        # 限制在合理范围内
        property_values = np.clip(property_values, 0, self.max_prop_damage)
        
        # 无建筑区域价值为零
        property_values[self.building_heights == 0] = 0.0
        
        return property_values
    
    def _get_type_multipliers(self) -> np.ndarray:
        """
        获取建筑类型价值乘数
        
        Returns:
            价值乘数矩阵 (nx, ny)
        """
        if self.building_types is None:
            return np.ones_like(self.building_heights)
        
        # 定义不同类型建筑的相对价值
        # 0: 住宅, 1: 商业, 2: 工业, 3: 公共设施
        type_values = {
            0: 1.0,   # 住宅（基准）
            1: 1.5,   # 商业（较高价值）
            2: 0.8,   # 工业（较低价值密度）
            3: 1.2,   # 公共设施（中等价值）
        }
        
        multipliers = np.zeros_like(self.building_heights)
        for type_code, multiplier in type_values.items():
            multipliers[self.building_types == type_code] = multiplier
        
        return multipliers
    
    def compute_damage_coefficient(
        self,
        impact_energy: Optional[np.ndarray] = None,
        flight_altitude: Optional[Union[float, np.ndarray]] = None
    ) -> np.ndarray:
        """
        计算损坏系数 η_damage
        
        损坏程度取决于:
        1. 撞击能量（与无人机质量、速度相关）
        2. 建筑高度（越高越脆弱）
        3. 建筑类型（结构强度不同）
        
        Args:
            impact_energy: 撞击能量矩阵 (nx, ny)，单位 J
                          如果为 None，使用简化模型
            flight_altitude: 飞行高度 (m)，用于估算撞击速度
        
        Returns:
            损坏系数矩阵 (nx, ny)，值域 [0, 1]
            0: 无损坏, 1: 完全损毁
        """
        if impact_energy is None:
            # 简化模型：仅基于建筑高度
            # 假设：高楼更易受损（结构复杂、内部设备多）
            heights_normalized = self.building_heights / (np.max(self.building_heights) + 1e-6)
            eta_damage = 0.3 + 0.7 * heights_normalized  # 范围 [0.3, 1.0]
        else:
            # 完整模型：考虑撞击能量
            # 使用 Sigmoid 函数模拟损坏程度
            E_threshold = 1000.0  # 能量阈值（J）
            eta_damage = 1.0 / (1.0 + np.exp(-(impact_energy - E_threshold) / 500.0))
        
        # 无建筑区域损坏系数为零
        eta_damage[self.building_heights == 0] = 0.0
        
        return eta_damage
    
    def compute_property_consequence(
        self,
        impact_energy: Optional[np.ndarray] = None,
        flight_altitude: Optional[Union[float, np.ndarray]] = None,
    ) -> np.ndarray:
        """
        计算财产后果张量（不含坠机概率）。

        论文 §3 中，算法层统一处理概率乘法：
            δC_p = P_surv × P_crash × E_property
        因此模型层只输出 E_property = V_building × η_damage，
        由调用方（pipeline / algorithm）负责乘以概率。

        Returns:
            E_property: (nx, ny) 财产后果矩阵，单位：货币单位
        """
        eta_damage = self.compute_damage_coefficient(impact_energy, flight_altitude)
        return self.property_values * eta_damage

    def calculate_property_cost(
        self,
        p_crash: np.ndarray,
        impact_energy: Optional[np.ndarray] = None,
        flight_altitude: Optional[Union[float, np.ndarray]] = None
    ) -> np.ndarray:
        """
        计算期望财产损失成本
        
        核心公式:
        C_property = P_crash × V_building × η_damage
        
        Args:
            p_crash: 坠机概率矩阵 (nx, ny)，值域 [0, 1]
                    来自 DynamicCrashProbability.compute_pcrash()
            impact_energy: 撞击能量矩阵 (nx, ny)，可选
            flight_altitude: 飞行高度 (m)，可选
        
        Returns:
            期望财产损失成本矩阵 (nx, ny)，单位：货币单位
        """
        # 验证输入
        assert p_crash.shape == (self.nx, self.ny), \
            f"P_crash 形状 {p_crash.shape} 与建筑网格 {(self.nx, self.ny)} 不匹配"
        assert np.all((p_crash >= 0) & (p_crash <= 1)), "P_crash 必须在 [0, 1] 范围内"
        
        # 计算损坏系数
        eta_damage = self.compute_damage_coefficient(impact_energy, flight_altitude)
        
        # 计算期望损失
        C_property = p_crash * self.property_values * eta_damage
        
        return C_property
    
    def get_property_statistics(self) -> dict:
        """
        获取财产价值统计信息（用于调试和分析）
        
        Returns:
            包含统计信息的字典
        """
        non_zero_mask = self.building_heights > 0
        
        if not np.any(non_zero_mask):
            return {
                'total_buildings': 0,
                'avg_value': 0.0,
                'max_value': 0.0,
                'total_value': 0.0,
            }
        
        values = self.property_values[non_zero_mask]
        
        return {
            'total_buildings': int(np.sum(non_zero_mask)),
            'avg_value': float(np.mean(values)),
            'median_value': float(np.median(values)),
            'max_value': float(np.max(values)),
            'min_value': float(np.min(values)),
            'total_value': float(np.sum(values)),
        }


# 为了向后兼容，保留 PropertyCost 别名
PropertyCost = PropertyDamageModel
