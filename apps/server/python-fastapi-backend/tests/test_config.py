"""配置层契约"""

from pathlib import Path

from src.utils.config import Settings


def test_env_file_path_is_absolute_and_cwd_independent():
    """env_file 必须由模块位置推导，而不是相对 cwd"""
    env_files = Settings.model_config["env_file"]
    assert isinstance(env_files, (tuple, list)), "应为多文件元组"
    for f in env_files:
        assert Path(f).is_absolute(), f"{f} 不是绝对路径"


def test_repository_backend_defaults_to_memory(monkeypatch):
    """默认必须是内存实现 —— 无库环境下服务要能起来"""
    monkeypatch.delenv("UAV_REPOSITORY_BACKEND", raising=False)
    assert Settings(_env_file=None).repository_backend == "memory"


def test_persist_results_defaults_to_true(monkeypatch):
    monkeypatch.delenv("UAV_PERSIST_RESULTS", raising=False)
    assert Settings(_env_file=None).persist_results is True


def test_backend_root_env_is_last_priority():
    """后端自有 .env 优先级应高于仓库根 .env"""
    env_files = [Path(f) for f in Settings.model_config["env_file"]]
    assert env_files[-1].name == ".env"
    assert env_files[-1].parent.name == "python-fastapi-backend"
