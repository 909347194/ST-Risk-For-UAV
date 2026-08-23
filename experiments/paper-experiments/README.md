# TD-RiskA* Paper Experiments

论文《顾及风险时空异质性的城市低空无人机航路规划》实验代码。

## 目录结构

```
paper-experiments/
├── core/                  # 核心算法库
│   ├── grid_system.py     # §3 四维时空网格
│   ├── common.py          # §3 SearchNode 状态向量
│   ├── env_tensor.py      # §3 风险张量容器
│   ├── p_crash.py         # §4 坠机概率 (Cox PH)
│   ├── fatality.py        # §4 致死风险
│   ├── property.py        # §4 财产损失
│   ├── noise.py           # §4 噪声社会影响
│   ├── tidal.py           # §4 人口/车辆潮汐模型
│   ├── td_risk_astar.py   # §5 TD-RiskA* 算法
│   ├── paths.py           # 数据路径管理
│   ├── poi_parser.py      # POI 数据解析
│   ├── population_resampler.py
│   ├── building_processor.py
│   ├── landuse_builder.py
│   ├── road_processor.py
│   ├── weather_processor.py
│   └── synthetic/         # 合成数据工厂
│
├── configs/               # 实验配置
│   ├── common.yaml        # 公共参数
│   ├── micro.yaml         # 微观实验
│   └── macro.yaml         # 宏观案例
│
├── scenario_builder.py    # 实验场景构建器
├── exp1_temporal.py       # §6 时间适应性
├── exp2_microclimate.py   # §6 微气候地形
├── exp3_pareto.py         # §6 噪声-安全 Pareto
├── exp4_storm.py          # §6 暴风雨剪枝效率
├── exp5_comprehensive.py  # §6 综合实验
│
├── data/                  # 数据 (gitignore)
├── results/               # 实验输出 (gitignore)
└── pyproject.toml         # Python 依赖
```

## 快速开始

```bash
cd experiments/paper-experiments

# 安装依赖
uv sync

# 运行实验
uv run python exp1_temporal.py
uv run python exp5_comprehensive.py
```

## 对应论文章节

| 脚本 | 论文章节 | 验证内容 |
|------|----------|----------|
| exp1 | §6.x | 不同出发时刻产生不同路径 |
| exp2 | §6.x | 风/雨/峡谷对路径的影响 |
| exp3 | §6.x | 噪声-安全 Pareto 前沿 |
| exp4 | §6.x | 暴风雨场景剪枝效率 |
| exp5 | §6.x | 基线对比 + 参数敏感性 + 计算 scaling |
