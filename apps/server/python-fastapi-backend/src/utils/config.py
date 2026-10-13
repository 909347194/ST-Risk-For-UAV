"""全局配置"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

# src/utils/config.py -> parents[2] = apps/server/python-fastapi-backend
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
# parents[5] = 仓库根 ST-Risk-For-UAV-1
_REPO_ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    """应用配置，优先读取环境变量"""

    app_name: str = "ST-Risk UAV Service"
    app_version: str = "0.1.0"
    debug: bool = False

    # 数据库
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/st_risk"

    # 存储后端：memory = 内存仓储（默认，无库可用）；db = PostgreSQL
    repository_backend: Literal["memory", "db"] = "memory"
    # 算法结果是否落库；off 时端点跳过写库（无库开发用）
    persist_results: bool = True

    # 路径规划默认参数
    default_grid_resolution: float = 1.0
    default_search_margin: float = 50.0

    # 风险评估阈值
    risk_collision_threshold: float = 0.7
    risk_weather_threshold: float = 0.6
    risk_battery_threshold: float = 0.8

    # 适配评估
    min_battery_reserve: float = 0.2  # 至少保留 20% 电量

    model_config = {
        "env_prefix": "UAV_",
        # 相对 cwd 解析会踩坑：按 README 在 backend 目录启动时读不到仓库根的 .env。
        # 改为按模块位置推导的绝对路径；后一个文件优先，故后端自有 .env 可覆盖根 .env。
        "env_file": (_REPO_ROOT / ".env", _BACKEND_ROOT / ".env"),
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
