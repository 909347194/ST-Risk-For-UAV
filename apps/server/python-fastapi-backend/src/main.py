"""FastAPI 入口 — 优雅启动 / 退出"""

import os
import sys
import signal
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from src.utils.config import get_settings
from src.api.v1.api import api_v1_router


# ── 控制台输出工具 ──────────────────────────────────────────────
# 全部使用 ASCII 兼容字符，避免 Windows cmd / PowerShell 中文乱码

BANNER = r"""
 +----------------------------------------------+
 |     ST-Risk UAV -- Python Backend            |
 +----------------------------------------------+
"""


def _log(msg: str) -> None:
    """带时间戳的日志输出"""
    ts = datetime.now().strftime("%H:%M:%S")
    sys.stdout.write(f"  [{ts}] {msg}\n")
    sys.stdout.flush()


def _print_info(port: int, debug: bool) -> None:
    sys.stdout.write(BANNER + "\n")
    _log(f"[*] Service  : Python (FastAPI)")
    _log(f"[*] Port     : {port}")
    _log(f"[*] API      : http://localhost:{port}/api/v1")
    _log(f"[*] Docs     : http://localhost:{port}/docs")
    _log(f"[*] Debug    : {debug}")
    _log(f"[*] PID      : {os.getpid()}")
    sys.stdout.write("\n")
    _log("[OK] Server is ready. Press Ctrl+C to stop.")
    sys.stdout.write("\n")
    sys.stdout.flush()


def _print_shutdown(signal_name: str) -> None:
    sys.stdout.write("\n")
    _log(f"[!] Received {signal_name}. Shutting down gracefully...")
    sys.stdout.flush()


# ── Lifespan (startup / shutdown) ──────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """管理应用生命周期: startup -> yield -> shutdown"""

    settings = get_settings()
    port = int(settings.app_name and 8000) or 8000  # fallback

    # 尝试从环境变量读端口
    import os
    port = int(os.environ.get("PYTHON_API_PORT", os.environ.get("PORT", 8000)))

    _print_info(port, settings.debug)

    # ── startup 完成，进入运行阶段 ──
    yield

    # ── shutdown 阶段 ──
    _log("[*] Closing database connections...")
    # 在此添加资源清理逻辑，例如:
    # await database.disconnect()
    # await redis_client.close()
    _log("[OK] Cleanup done. Server stopped cleanly.")


# ── 创建 App ───────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        description="UAV task allocation and path planning service",
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    application.include_router(api_v1_router, prefix="/api/v1")

    return application


app = create_app()


# ── Windows 信号兼容 ────────────────────────────────────────────
# Windows 不支持 SIGTERM，用信号处理 + asyncio 保证 Ctrl+C 优雅退出

def _setup_signal_handlers() -> None:
    """注册信号处理器，确保 Ctrl+C 触发优雅关闭"""
    loop = asyncio.get_event_loop()

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: _print_shutdown(signal.Signals(s).name))
    # Windows: uvicorn 默认已处理 Ctrl+C，无需额外操作


# 当直接运行时（uvicorn src.main:app --reload）lifespan 自动生效
# 以下为独立运行入口: python -m src.main
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PYTHON_API_PORT", os.environ.get("PORT", 8000)))

    # 设置控制台编码为 UTF-8（Windows 兼容）
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
