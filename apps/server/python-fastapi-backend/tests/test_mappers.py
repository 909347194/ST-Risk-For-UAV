"""映射层 —— 领域模型 ↔ ORM 模型往返"""

from src.domain.enums import RiskLevel, UAVStatus
from src.domain.models import UAV, Position, RiskAssessment, UAVHealthSnapshot
from src.repositories import mappers


def test_position_wkt_roundtrip_keeps_z():
    """z 分量必须保留 —— POINT_Z 的意义就在这里"""
    pos = Position(x=1.5, y=-2.25, z=30.0)
    assert mappers.wkt_to_position(mappers.position_to_wkt(pos)) == pos


def test_position_wkt_format():
    assert mappers.position_to_wkt(Position(x=1.0, y=2.0, z=3.0)) == "POINT Z (1.0 2.0 3.0)"


def test_uav_to_model_maps_columns():
    uav = UAV(id="uav-1", position=Position(x=1.0, y=2.0, z=3.0),
              speed=10.0, max_payload=5.0, battery=900.0,
              status=UAVStatus.IN_FLIGHT)
    m = mappers.uav_to_model(uav)
    assert m.id == "uav-1"
    assert m.speed == 10.0
    assert m.max_payload == 5.0
    assert m.battery == 900.0
    assert m.status == "in_flight"          # 枚举落库为字符串值
    assert "POINT Z (1.0 2.0 3.0)" in str(m.position)


def test_uav_status_enum_maps_to_value_not_name():
    """落库必须是 'in_flight' 而不是 'IN_FLIGHT'"""
    uav = UAV(id="u", position=Position(x=0, y=0, z=0), speed=1.0,
              max_payload=1.0, battery=1.0, status=UAVStatus.RETURNING)
    assert mappers.uav_to_model(uav).status == "returning"


def test_snapshot_to_model_keeps_reasons_list():
    snap = UAVHealthSnapshot(uav_id="uav-1", position=Position(x=0, y=0, z=50),
                             battery_remaining=8.0, speed=31.0, heading=90.0,
                             timestamp=12.5, is_anomaly=True,
                             anomaly_reasons=["电量过低", "速度异常"])
    m = mappers.snapshot_to_model(snap)
    assert m.uav_id == "uav-1"
    assert m.ts == 12.5
    assert m.is_anomaly is True
    assert m.anomaly_reasons == ["电量过低", "速度异常"]


def test_risk_to_model_flattens_fields():
    assessment = RiskAssessment(uav_id="uav-1", task_id="task-1",
                                risk_level=RiskLevel.HIGH,
                                collision_risk=0.8, weather_risk=0.2,
                                battery_risk=0.3, overall_score=0.6,
                                details=["碰撞风险偏高"])
    m = mappers.risk_to_model(assessment, weather_factor=0.4)
    assert m.risk_level == "high"
    assert m.overall_score == 0.6
    assert m.weather_factor == 0.4
    assert m.details == ["碰撞风险偏高"]
