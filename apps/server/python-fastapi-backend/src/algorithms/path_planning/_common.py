"""路径规划公共校验"""

BOUNDS_KEYS = ("x_min", "x_max", "y_min", "y_max")


def validate_bounds(bounds: dict) -> None:
    """校验规划区域边界 — 缺键或非数值以 ValueError 明确拒绝

    在算法入口处拦下，避免残缺/类型错误的 bounds 在下游以
    KeyError / TypeError 冒泡成 500（调用方无法据此定位问题）。
    端点负责把 ValueError 映射为 400。
    """
    missing = [k for k in BOUNDS_KEYS if k not in bounds]
    if missing:
        raise ValueError(f"bounds 缺少必需键: {missing}，需要: {list(BOUNDS_KEYS)}")

    invalid = [k for k in BOUNDS_KEYS if not isinstance(bounds[k], (int, float))]
    if invalid:
        raise ValueError(f"bounds 各项必须为数值，非法: {invalid}")
