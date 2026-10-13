"""pytest 公共配置占位

asyncio_mode = "auto"（见 pyproject.toml）已接管 async 测试的循环管理，
无需任何 fixture。

注意：pytest-asyncio 1.0 起不再识别自定义 event_loop fixture（写成
死代码）；如需会话级循环，用 pyproject 里的 asyncio_default_*_loop_scope。
"""
