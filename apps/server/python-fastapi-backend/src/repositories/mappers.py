"""领域模型 ↔ ORM 模型映射

没有这一层，ORM 对象会一路漏进 service 与响应模型。集中在此，
service 只需面对领域模型。

几何列统一用 WKT 文本在 Python 侧进出：读写都用 ST_GeomFromText /
ST_AsText，避免在业务代码里处理 WKBElement。
"""

from src.db.models.adaptability import AdaptabilityResultModel
from src.db.models.monitoring import FlightSnapshotModel
from src.db.models.path_plan import PathPlanModel
from src.db.models.risk_record import RiskRecordModel
from src.db.models.uav import UAVModel
from src.domain.enums import UAVStatus
from src.domain.models import (
    UAV,
    AdaptabilityResult,
    PathPlan,
    Position,
    RiskAssessment,
    UAVHealthSnapshot,
)

# ── 几何 ─────────────────────────────────────────────

def position_to_wkt(pos: Position) -> str:
    """Position -> PostGIS 可解析的 WKT 文本（含 z）"""
    return f"POINT Z ({pos.x} {pos.y} {pos.z})"


def wkt_to_position(wkt: str) -> Position:
    """WKT 文本 -> Position

    支持 'POINT Z (x y z)' 与 'POINT(x y z)' 两种写法。
    """
    body = wkt[wkt.index("(") + 1: wkt.index(")")].replace(",", " ")
    parts = [float(v) for v in body.split()]
    return Position(x=parts[0], y=parts[1], z=parts[2] if len(parts) > 2 else 0.0)


# ── ① 无人机 ──────────────────────────────────────────

def uav_to_model(uav: UAV) -> UAVModel:
    return UAVModel(
        id=uav.id,
        position=position_to_wkt(uav.position),
        speed=uav.speed,
        max_payload=uav.max_payload,
        battery=uav.battery,
        status=uav.status.value,
    )


def uav_to_domain(row) -> UAV:
    """row 需提供 id / position_wkt(WKT 文本) / speed / max_payload / battery / status

    position 列由查询里的 ST_AsText(...) 别名 position_wkt 提供 ——
    不能直接读 row.position，那是 WKBElement 而非文本。
    """
    return UAV(
        id=row.id,
        position=wkt_to_position(row.position_wkt),
        speed=row.speed,
        max_payload=row.max_payload,
        battery=row.battery,
        status=UAVStatus(row.status),
    )


# ── ⑥ 监控快照 ────────────────────────────────────────

def snapshot_to_model(snap: UAVHealthSnapshot) -> FlightSnapshotModel:
    return FlightSnapshotModel(
        uav_id=snap.uav_id,
        ts=snap.timestamp,
        position=position_to_wkt(snap.position),
        battery_remaining=snap.battery_remaining,
        speed=snap.speed,
        heading=snap.heading,
        is_anomaly=snap.is_anomaly,
        anomaly_reasons=list(snap.anomaly_reasons),
    )


def snapshot_to_domain(row) -> UAVHealthSnapshot:
    """row 需提供 uav_id / ts / battery_remaining / speed / heading /
    is_anomaly / anomaly_reasons / position_wkt(WKT 文本)"""
    return UAVHealthSnapshot(
        uav_id=row.uav_id,
        position=wkt_to_position(row.position_wkt),
        battery_remaining=row.battery_remaining,
        speed=row.speed,
        heading=row.heading,
        timestamp=row.ts,
        is_anomaly=row.is_anomaly,
        anomaly_reasons=list(row.anomaly_reasons or []),
    )


# ── ③ 风险评估 ────────────────────────────────────────

def risk_to_model(assessment: RiskAssessment, weather_factor: float | None = None) -> RiskRecordModel:
    return RiskRecordModel(
        uav_id=assessment.uav_id,
        task_id=assessment.task_id,
        risk_level=assessment.risk_level.value,
        collision_risk=assessment.collision_risk,
        weather_risk=assessment.weather_risk,
        battery_risk=assessment.battery_risk,
        overall_score=assessment.overall_score,
        weather_factor=weather_factor,
        details=list(assessment.details),
    )


# ── ② 适配评估 ────────────────────────────────────────

def adaptability_to_model(result: AdaptabilityResult) -> AdaptabilityResultModel:
    return AdaptabilityResultModel(
        uav_id=result.uav_id,
        task_id=result.task_id,
        capable=result.capable,
        payload_ok=result.payload_ok,
        battery_ok=result.battery_ok,
        range_ok=result.range_ok,
        time_ok=result.time_ok,
        score=result.score,
        reasons=list(result.reasons),
    )


# ── ⑤ 航线规划 ────────────────────────────────────────

def plan_to_model(plan: PathPlan, algorithm: str, duration_ms: float | None = None) -> PathPlanModel:
    return PathPlanModel(
        uav_id=plan.uav_id,
        task_id=plan.task_id,
        algorithm=algorithm,
        waypoints=[{"x": w.position.x, "y": w.position.y, "z": w.position.z,
                    "arrival_time": w.arrival_time} for w in plan.waypoints],
        total_distance=plan.total_distance,
        estimated_time=plan.estimated_time,
        duration_ms=duration_ms,
    )
