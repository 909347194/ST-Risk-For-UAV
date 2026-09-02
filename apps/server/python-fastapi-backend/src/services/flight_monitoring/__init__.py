"""⑥ 飞行监控模块"""
from src.services.flight_monitoring.service import (  # noqa: F401
    get_repository, record_snapshot, detect_anomalies,
    get_track, get_alerts, clear_alerts, get_active_count,
)
