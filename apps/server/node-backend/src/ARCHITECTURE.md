# Node 后端分层架构（目标结构）

> 依据「Planner Agent + 专业 Worker Agent + Worker Registry + A2A Contract」架构设计。
> 本文件只描述目录职责与迁移映射；各目录当前仅有 `.gitkeep` 占位，按阶段逐步填充。

## 职责边界（总原则）

- **Node 后端**：Agent 认知、协同、任务编排、业务服务
- **Python 后端**：确定性优化算法与数值计算（Hungarian / DE / ALNS / A* 等）
- **数据库**：真实业务状态

## 顶层分层

| 目录 | 职责 |
| --- | --- |
| `api/` | 对外 HTTP 接口：routes / controllers / middlewares / validators |
| `agents/` | Planner 与各类 Worker Agent（core / planner / workers / registry） |
| `orchestration/` | 多 Agent 协同控制：编排、路由、反馈、重规划、执行策略 |
| `contracts/` | Agent 间统一任务/结果协议（含运行时 Schema 校验） |
| `domain/` | 调度领域模型与业务规则（tasks / uavs / risks / allocation / routes / dispatch） |
| `services/` | 应用服务与外部适配（dispatch/task/uav/risk 服务、python-algorithm.client） |
| `infrastructure/` | 技术基础设施：database / llm / persistence / logging / cache / config |
| `shared/` | 跨模块共享基础：errors / types / utils / constants / pipes |
| `app/` `main.ts` | **现有 NestJS 入口与装配（保留，不重复建入口）** |

## 现有目录 → 目标位置（迁移映射，暂不动）

| 现有 | 说明 | 建议去向 |
| --- | --- | --- |
| `app/` | AppModule 装配 | 保留为 Nest 装配层，逐步 import 新模块 |
| `modules/agent/` | Agent 模块（controller/service/repo） | 拆分到 `agents/planner|workers/` + `api/controllers` + `agents/registry` |
| `modules/common/` | 公共控制器 | `api/` |
| `clients/python-backend/` | Python 后端客户端 | `services/`（python-algorithm.client） |
| `db/` | engine + models | `infrastructure/database/` + `domain/` |
| `shared/pipes/` | Zod 校验管道 | 保留在 `shared/` |

## 关键设计要点（落地时遵循）

1. **Planner 只做决策**：通过 `orchestration/` 提交任务与接收结果，不硬编码 Worker 细节。
2. **四个协同组件职责分开**：Worker Registry（有哪些 Worker）/ Worker Router（交给谁）/ Workflow Engine（按什么顺序）/ Replanner（失败如何调整）——不合并成一个巨大 service。
3. **Worker = 领域能力，不是算法**：Hungarian / DE 等是 Worker 可调用的算法工具，经由 `services/` 下的 Python 客户端统一访问；不要再造 `HungarianAgent`。
4. **统一 Contract**：所有 Worker 输入输出走 `contracts/` 的强类型协议，模型 JSON 与 Python 响应需运行时 Schema 校验。
5. **分阶段实施**：阶段1 基础骨架（agents/core + planner + contracts + orchestration + python client）→ 阶段2 Allocation Worker → 阶段3 多 Worker 协同 → 阶段4 反馈闭环（feedback/replanner/validation）→ 阶段5 工程化（infrastructure 补齐）。
