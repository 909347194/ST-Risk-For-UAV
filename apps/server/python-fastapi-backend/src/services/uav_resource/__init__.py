"""① 无人机资源管理模块"""
from src.services.uav_resource.service import (  # noqa: F401
    get_repository, register_uav, get_uav, list_uavs,
    update_uav_status, remove_uav, update_position, get_snapshot,
)
