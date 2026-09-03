"""全局配置"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，优先读取环境变量"""

    app_name: str = "ST-Risk UAV Service"
    app_version: str = "0.1.0"
    debug: bool = False

    # 数据库
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/st_risk"

    # 路径规划默认参数
    default_grid_resolution: float = 1.0
    default_search_margin: float = 50.0

    # 风险评估阈值
    risk_collision_threshold: float = 0.7
    risk_weather_threshold: float = 0.6
    risk_battery_threshold: float = 0.8

    # 适配评估
    min_battery_reserve: float = 0.2  # 至少保留 20% 电量

    model_config = {"env_prefix": "UAV_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
