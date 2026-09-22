"""补给计划数据类与电量档工具"""

from dataclasses import dataclass, field


@dataclass
class ChargeEvent:
    """一次充电事件"""
    station_id: str
    charge_wh: float          # 充电量 (Wh)
    arrive_time: float        # 到站时刻 (s)
    leave_time: float         # 离站时刻 (s)


@dataclass
class RechargePlan:
    """一条路线的补给计划(节点序列 + 充电事件 + 代价)"""
    uav_id: str = ""
    node_seq: list[int] = field(default_factory=list)       # 扩展节点序列(矩阵索引)
    charges: list[ChargeEvent] = field(default_factory=list)
    total_time: float = 0.0        # 飞行 + 充电总时间 (s)
    total_energy: float = 0.0      # 总飞行能耗 (Wh)
    arrival_times: list[float] = field(default_factory=list)  # 与 node_seq 对齐
    feasible: bool = True


def battery_levels(B: float, delta: float) -> list[float]:
    """电量离散档 [0, ..., B](含端点);delta 无效时退化为 {0, B}"""
    if delta <= 0 or delta > B:
        return [0.0, B]
    levels: list[float] = []
    v = 0.0
    while v < B - 1e-9:
        levels.append(v)
        v += delta
    levels.append(B)
    return levels
