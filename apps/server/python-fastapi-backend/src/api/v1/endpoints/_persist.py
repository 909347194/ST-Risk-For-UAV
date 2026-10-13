"""结果落库辅助 —— 统一处理「未启用持久化」的分支

持久化在两种情况下跳过：
  1. UAV_REPOSITORY_BACKEND != 'db'（无库，走内存）
  2. UAV_PERSIST_RESULTS=off（显式关闭）

两种情况都返回 None，调用方直接忽略返回值。写库异常不在此捕获 ——
让它冒泡成 500，避免静默丢失实验数据。
"""

from src.repositories import factory
from src.utils.config import get_settings


def result_repo(name: str):
    if not get_settings().persist_results:
        return None
    return factory.get_result_repository(name)
