"""pytest 公共配置

asyncio_mode = "auto"（见 pyproject.toml）已接管 async 测试的循环管理，
无需任何 fixture。

注意：pytest-asyncio 1.0 起不再识别自定义 event_loop fixture（写成
死代码）；如需会话级循环，用 pyproject 里的 asyncio_default_*_loop_scope。
"""

import os

# 默认套件固定用内存后端 —— 与 pyproject addopts 排除 integration 同一思路：
# 默认 pytest 不连库。本机 .env 可能设了 UAV_REPOSITORY_BACKEND=db，
# 不强制的话 TestClient / 服务层用例会误连真库（污染数据且依赖库在线）。
# 真库用例走 `-m integration`，那批用例自建引擎、不读此设置。
# 环境变量优先级高于 .env，故这里赋值即可覆盖 .env。
os.environ["UAV_REPOSITORY_BACKEND"] = "memory"
