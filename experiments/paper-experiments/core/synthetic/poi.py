"""
POI密度场生成模块 - 04_poi.py

从土地利用和建筑高度生成兴趣点（POI）密度场。

POI五类定义（与 data_provision/poi_parser.py 一致）：
- residential: 住宅POI
- office: 办公/商业POI
- institution: 机构POI（学校、医院等）
- transport: 交通POI（道路、车站等）
- industrial: 工业POI

约束关系：
- POI类型与土地利用严格对应
- 住宅POI仅出现在住宅区 (landuse==1)
- 办公POI仅出现在商业区 (landuse==2)
- 机构POI仅出现在教育/医疗区 (landuse==3)
- 交通POI仅出现在道路区 (landuse==5)
- 工业POI仅出现在工业区 (landuse==4)
- 密度值基于随机分布，模拟真实城市的不均匀性
"""

from typing import Dict, Optional
import numpy as np

# POI五类定义（与 data_provision/poi_parser.py 保持一致）
POI_CATEGORIES = ("residential", "office", "institution", "transport", "industrial")


def create_poi_from_landuse(
    landuse: np.ndarray, 
    building_heights: np.ndarray,
    seed: Optional[int] = None
) -> Dict[str, np.ndarray]:
    """
    从土地利用和建筑生成POI密度场
    
    参数：
        landuse: 土地利用矩阵 (ny, nx)
        building_heights: 建筑高度矩阵 (ny, nx)
        seed: 随机种子，用于结果复现。None表示不设置种子
    
    返回：
        POI密度字典，每个值为二维密度场 (ny, nx)
        包含: residential, office, institution, transport, industrial
    """
    # 设置随机种子以保证可复现性
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random
    
    poi = {
        'residential': np.zeros_like(landuse, dtype=float),
        'office': np.zeros_like(landuse, dtype=float),
        'institution': np.zeros_like(landuse, dtype=float),
        'transport': np.zeros_like(landuse, dtype=float),
        'industrial': np.zeros_like(landuse, dtype=float)
    }
    
    # 住宅POI - 基于住宅区生成密度
    residential_mask = (landuse == 1)
    if np.any(residential_mask):
        poi['residential'][residential_mask] = rng.uniform(0.5, 1.0, size=residential_mask.sum())
    
    # 办公POI - 基于商业区生成密度
    office_mask = (landuse == 2)
    if np.any(office_mask):
        poi['office'][office_mask] = rng.uniform(0.7, 1.0, size=office_mask.sum())
    
    # 机构POI - 基于学校/医院区域生成密度
    institution_mask = (landuse == 3)
    if np.any(institution_mask):
        poi['institution'][institution_mask] = rng.uniform(0.6, 0.9, size=institution_mask.sum())
    
    # 交通POI - 基于道路区域生成密度
    transport_mask = (landuse == 5)
    if np.any(transport_mask):
        poi['transport'][transport_mask] = rng.uniform(0.3, 0.7, size=transport_mask.sum())
    
    # 工业POI - 基于工业区生成密度
    industrial_mask = (landuse == 4)
    if np.any(industrial_mask):
        poi['industrial'][industrial_mask] = rng.uniform(0.4, 0.8, size=industrial_mask.sum())
    
    return poi


if __name__ == "__main__":
    # 测试代码
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    
    from landuse import create_landuse_master_plan
    from road import create_road_network
    from building import create_buildings_conditioned_on_landuse
    
    nx, ny, nz = 60, 60, 12
    landuse = create_landuse_master_plan(nx, ny)
    road_mask = create_road_network(nx, ny, landuse)
    building_heights = create_buildings_conditioned_on_landuse(nx, ny, nz, landuse, road_mask)
    poi = create_poi_from_landuse(landuse, building_heights)
    
    print("POI密度场统计 (5类):")
    for poi_type in POI_CATEGORIES:
        density = poi[poi_type]
        non_zero = np.sum(density > 0)
        if non_zero > 0:
            print(f"  {poi_type}: {non_zero} 个格点, "
                  f"平均密度: {np.mean(density[density > 0]):.3f}, "
                  f"最大密度: {np.max(density):.3f}")
        else:
            print(f"  {poi_type}: 0 个格点")
    
    # 验证约束：工业区不应有住宅POI
    industrial_mask = (landuse == 4)
    assert np.all(poi['residential'][industrial_mask] == 0), "❌ 工业区出现住宅POI"
    
    # 验证约束：道路区应有交通POI
    road_mask_check = (landuse == 5)
    if np.any(road_mask_check):
        assert np.any(poi['transport'][road_mask_check] > 0), "❌ 道路区缺少交通POI"
    
    print("\n✓ 所有POI约束校验通过")
