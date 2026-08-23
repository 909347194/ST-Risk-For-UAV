# 合成数据工厂 (Synthetic Data Factory) 用法指南

## 概述

`synthetic_data_factory` 是一个用于生成语义约束的合成城市数据的模块化工具包。它按照严格的生成顺序，从基础的土地利用开始，依次生成道路网络、建筑高度、POI密度、人口密度、气象数据等，确保各数据层之间的逻辑一致性。

该工厂支持完全可复现的数据生成，通过随机种子控制所有包含随机性的模块，使得相同种子值能够产生完全一致的结果，便于实验复现和敏感性分析。

## 核心特性

- **语义约束**：数据生成遵循城市规划逻辑（如CBD→商业环→住宅环→工业外围）
- **完全可复现**：所有随机模块支持种子控制，确保结果一致性
- **模块化设计**：各数据层独立实现，便于扩展和维护
- **多格式导出**：支持 NumPy、GeoTIFF、GeoJSON 等多种数据格式
- **自动校验**：内置数据验证机制，确保生成数据的合理性

## 安装依赖

```bash
# 基础依赖（必需）
pip install numpy

# GIS格式导出依赖（可选）
pip install rasterio geopandas shapely
```

## 快速开始

### 基本用法

```python
from methods.spatiotemporal_heterogeneity.utils.synthetic_data_factory import generate_synthetic_city

# 生成合成城市数据
nx, ny, nz, nt = 60, 60, 12, 96  # 空间和时间维度
city_data = generate_synthetic_city(nx, ny, nz, nt, seed=42)

print(f"土地利用形状: {city_data['landuse'].shape}")
print(f"道路掩码形状: {city_data['road_mask'].shape}")
print(f"建筑高度形状: {city_data['building_heights'].shape}")
print(f"人口密度形状: {city_data['population'].shape}")
print(f"风场形状: {city_data['wind_field'].shape}")
print(f"降雨场形状: {city_data['rain_data'].shape}")
print(f"OD对数量: {len(city_data['od_pairs'])}")
print(f"POI类型: {list(city_data['poi'].keys())}")
```

### 微观验证场景

```python
from methods.spatiotemporal_heterogeneity.utils.synthetic_data_factory import simulate_micro_synthetic_data

# 假设你有一个 GridSystem 对象
# grid = your_grid_system_instance
# synthetic_data = simulate_micro_synthetic_data(grid)
```

## 数据生成流程

合成数据工厂严格按照以下顺序生成数据，确保各层之间的依赖关系：

1. **土地利用 (Land Use)** - 基础母图（确定性 + 噪声）
   - 使用同心圆模型：CBD → 商业环 → 住宅环 → 工业外围
   - 通过 Perlin 噪声实现平滑边界过渡
   - 土地利用类型编码：
     - `0`: 未定义/空地
     - `1`: 住宅区 (Residential)
     - `2`: 商业/办公区 (Commercial/Office)
     - `3`: 学校/医院 (School/Hospital)
     - `4`: 工业区 (Industrial)
     - `5`: 道路 (Road)
     - `6`: 绿地/水域 (Green/Water)

2. **道路网络 (Road Network)** - 基于土地利用（确定性 + 随机支路）
   - 分层结构：主干道 → 次干道 → 支路
   - 确保城市各区域良好连接
   - 避免在绿地内生成道路

3. **建筑高度 (Building Heights)** - 基于土地利用 + 道路掩码（随机）
   - CBD 区域建筑最高，向外递减
   - 道路附近建筑密度更高
   - 工业区有特定建筑高度分布

4. **POI 密度 (POI Density)** - 基于土地利用 + 建筑高度（随机）
   - POI 类型：住宅、办公、学校、工业
   - POI 密度与建筑高度和土地利用类型相关

5. **人口密度 (Population Density)** - 基于土地利用 + POI + 道路掩码（确定性）
   - 住宅区人口密度最高
   - 商业区工作日白天人口密度高
   - 道路可达性影响人口分布

6. **气象数据 (Weather Data)** - 独立生成（随机）
   - 风场：三维时空风速场 `(ny, nx, nz, nt)`
   - 降雨场：二维时空降雨场 `(ny, nx, nt)`

7. **OD 对 (Origin-Destination Pairs)** - 独立生成（随机）
   - 起点和终点的坐标对列表
   - 用于路径规划和交通流模拟

8. **数据校验 (Validation)** - 验证所有约束（确定性）
   - 检查各数据层的一致性和合理性

## 可复现性控制

所有包含随机性的模块都支持 `seed` 参数控制：

- **相同种子**：保证每次生成完全相同的数据
- **不同种子**：产生不同的城市场景，用于敏感性分析
- **种子偏移**：不同子模块使用不同的种子偏移量，确保统计独立性

```python
# 敏感性分析示例
seeds = [42, 123, 456, 789]
for seed in seeds:
    data = generate_synthetic_city(60, 60, 12, 96, seed=seed)
    # 处理不同场景的数据...
```

## 数据导出

### 自动导出

```python
from methods.spatiotemporal_heterogeneity.utils.synthetic_data_factory import export_synthetic_data

# 生成数据
city_data = generate_synthetic_city(60, 60, 12, 96, seed=42)

# 导出到默认目录
export_synthetic_data(city_data, seed=42)

# 导出到自定义目录
export_synthetic_data(city_data, output_dir="/path/to/custom/output", seed=42)
```

### 导出格式

导出功能支持三个阶段的数据存储：

1. **01_raw/synthetic**: 原生 GIS 格式
   - GeoTIFF 栅格文件 (`.tif`)
   - GeoJSON 矢量文件 (`.geojson`)

2. **02_processed/synthetic**: 标准化 NumPy 格式
   - 人口密度: `base_pop_2d.npy`
   - 建筑高度: `building_heights.npy`
   - POI 密度: `poi_counts.npz`
   - 土地利用: `landuse_map.npy`
   - 道路掩码: `road_mask.npy`
   - OD 对: `od_pairs.json`
   - 元数据: `metadata.json`

3. **03_tensors/synthetic**: 气象数据和成本张量
   - 风场: `wind_field.npy`
   - 降雨场: `rain_data.npy`

### 元数据

每次导出都会自动生成元数据文件 `metadata.json`，包含：

```json
{
  "generated_at": "2026-05-19T14:14:39.123456",
  "seed": 42,
  "source": "synthetic",
  "grid_dimensions": {
    "nx": 60,
    "ny": 60,
    "nz": 12,
    "nt": 96
  }
}
```

## API 参考

### 主要函数

#### `generate_synthetic_city(nx, ny, nz, nt, seed=42)`

生成完整的合成城市数据。

**参数:**
- `nx, ny, nz` (int): 空间网格维度
- `nt` (int): 时间步数
- `seed` (int, optional): 随机种子，默认为 42

**返回:**
字典包含以下键值对：
- `landuse`: 土地利用矩阵 `(ny, nx)`
- `road_mask`: 道路掩码 `(ny, nx)`
- `building_heights`: 建筑高度矩阵 `(ny, nx)`
- `poi`: POI 密度字典 `{residential, office, school, industrial}`
- `population`: 静态人口密度 `(ny, nx)`
- `wind_field`: 风场 `(ny, nx, nz, nt)`
- `rain_data`: 降雨场 `(ny, nx, nt)`
- `od_pairs`: OD 对列表

#### `simulate_micro_synthetic_data(grid)`

为微观验证场景生成合成数据。

**参数:**
- `grid`: GridSystem 对象，包含 `nx, ny, nz, nt` 属性

**返回:**
合成数据字典（同 `generate_synthetic_city`）

#### `export_synthetic_data(data, output_dir=None, seed=None, export_raw_gis=False, export_tensors=True)`

将合成数据导出到磁盘。

**参数:**
- `data`: `generate_synthetic_city()` 返回的数据字典
- `output_dir`: 输出目录路径（默认为项目内的 `02_processed/synthetic`）
- `seed`: 随机种子（用于创建带 seed 的子目录）
- `export_raw_gis`: 是否导出原生 GIS 格式
- `export_tensors`: 是否导出气象数据到 tensors 目录

## 使用场景

### 1. 算法开发与测试

```python
# 快速生成测试数据
test_data = generate_synthetic_city(30, 30, 6, 24, seed=123)
# 用于算法调试和性能测试
```

### 2. 敏感性分析

```python
# 生成多个不同场景
scenarios = []
for seed in range(100, 110):
    scenario = generate_synthetic_city(60, 60, 12, 96, seed=seed)
    scenarios.append(scenario)
# 分析算法在不同城市场景下的表现
```

### 3. 机理验证

```python
# 使用固定种子确保结果可复现
validation_data = generate_synthetic_city(50, 50, 10, 48, seed=42)
# 验证模型假设和理论机制
```

### 4. 教学演示

```python
# 生成简单的小规模数据用于教学
demo_data = generate_synthetic_city(20, 20, 4, 12, seed=42)
# 展示城市数据的空间分布特征
```

## 注意事项

1. **内存使用**: 大规模网格（如 nx, ny > 100）会消耗较多内存，建议根据硬件配置调整
2. **GIS 依赖**: 导出 GeoTIFF 和 GeoJSON 格式需要安装额外的 GIS 库
3. **数据维度**: 注意人口密度等数据的维度顺序为 `(ny, nx)`，与某些库的 `(nx, ny)` 顺序相反
4. **种子管理**: 在进行大规模实验时，合理规划种子值以避免重复

## 扩展开发

如需添加新的数据生成模块：

1. 在 `synthetic_data_factory` 目录下创建新的 Python 文件
2. 实现数据生成函数，遵循现有模块的接口规范
3. 在 `__init__.py` 中导入并导出新函数
4. 如果需要集成到主流程，在 `generate_synthetic_city` 函数中添加调用
5. 更新数据校验模块以包含新数据层的验证逻辑

---

*合成数据工厂 v1.0 - 为城市风险路径规划研究提供可靠的数据基础*