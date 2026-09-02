"""几何与通用工具"""

import math

from src.models.models import Position


def distance(a: Position, b: Position) -> float:
    """欧氏距离"""
    return math.sqrt(
        (a.x - b.x) ** 2
        + (a.y - b.y) ** 2
        + (a.z - b.z) ** 2
    )


def distance_2d(a: Position, b: Position) -> float:
    """二维平面距离（忽略高度）"""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def heading(from_pos: Position, to_pos: Position) -> float:
    """航向角（弧度，正北为 0，顺时针）"""
    dx = to_pos.x - from_pos.x
    dy = to_pos.y - from_pos.y
    return math.atan2(dx, dy)


def interpolate(a: Position, b: Position, t: float) -> Position:
    """线性插值，t ∈ [0, 1]"""
    return Position(
        x=a.x + (b.x - a.x) * t,
        y=a.y + (b.y - a.y) * t,
        z=a.z + (b.z - a.z) * t,
    )


def clamp(value: float, lo: float, hi: float) -> float:
    """限幅"""
    return max(lo, min(hi, value))
