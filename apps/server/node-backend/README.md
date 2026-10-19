# ST-Risk UAV — Node.js NestJS Backend（Agent 编排服务）

本服务是系统的**认知与编排层**：理解调度意图、决策任务分解、委派专业 Worker、追踪执行状态。
一条铁律贯穿全栈：**所有数值算法封装在 Python 端，Node 只做编排与决策**。

Agent 认知与编排基于 **pi**（`@earendil-works/pi-agent-core` + `@earendil-works/pi-ai`）扩展：
凡 pi 已有原语（钩子/事件/队列/校验）一律复用，**不造平行框架**。
设计全文见 [`docs/architecture/agent-architecture-node-landing.md`](../../docs/architecture/agent-architecture-node-landing.md)。

## 技术栈

| 项 | 技术 |
|---|------|
| 语言 | TypeScript ≥ 5.7 |
| 框架 | NestJS 11 |
| Agent 运行时 | pi-agent-core 0.87（Agent / 工具执行 / 事件 / 钩子） |
| LLM 接入 | pi-ai 0.87（Provider / 鉴权 / TypeBox） |
| 数据校验 | TypeBox（工具参数）+ Zod（业务边界） |
| ORM | Drizzle ORM |
| 数据库 | PostgreSQL + PostGIS + pgvector |
| 测试 | Jest（fauxProvider 可无真实 LLM 回放） |
| 包管理 | pnpm（monorepo workspace） |

---

## Agent 架构讲解

### 一句话

> **Planner（LLM）只做决策，Worker（确定型）只做能力，capability 是解耦键，pi 钩子承载协同。**

### 角色与职责

```
                    ┌────────────────────────────────────────────┐
   POST /dispatch   │              PlannerOrchestrator           │
  ────────────────▶ │  Plan/Run 落库 · 装配 pi 三钩子 · 驱动 prompt │
                    └──────────────┬─────────────────────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │     Planner Agent（pi Agent） │  ← LLM：理解意图/拆解/综合
                    │  systemPrompt + model + tools │
                    └──────────────┬───────────────┘
             工具调用（LLM 决定）   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  PlannerTool（薄按钮）         │  ← 把模型参数包成 WorkerTask
                    └──────────────┬───────────────┘
                                   ▼ dispatch('allocation.assign')
                    ┌──────────────────────────────┐
                    │  WorkerRouter → WorkerRegistry │  ← capability → 谁实现
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  XxxWorkerRuntime（确定型）    │  ← 领域整形/选算法/结果解读
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  AlgorithmClient（唯一闸门）   │  ← 超时/校验/错误映射/关联ID
                    └──────────────┬───────────────┘
                                   ▼
                    Python FastAPI（Hungarian / A* / 风险评估 …）
```

| 角色 | 是什么 | 关键点 |
|---|---|---|
| **Planner Agent** | pi `Agent` 实例，LLM 认知 | `initialState: { systemPrompt, model, tools }`；经 `agent.prompt()` 驱动 |
| **PlannerTool** | LLM 的"按钮"（`AgentTool`） | 薄壳：只构造 `WorkerTask` 并 `dispatch`，**不** new Worker、不写通信代码 |
| **capability** | 能力标识字符串（如 `allocation.assign`） | **不是工具、不是请求**——是 Registry 里的解耦键 |
| **WorkerRegistry** | capability → WorkerDefinition | V1 静态注册（启动装配），重复注册直接抛错 |
| **WorkerRouter** | 按 capability 分发 | 回收结果过 zod 边界校验，脏数据炸在边界 |
| **WorkerRuntime** | 能力实现者（确定型 class） | 领域分析 → 确定性选算法 → 调 Python → 领域解读 |
| **A2A Contract** | `WorkerTask` / `WorkerResult` | 三态语义（success/partial/failed/need_input）+ feedback + `correlationId` 可回放 |
| **AlgorithmClient** | Python 服务唯一通信闸门 | 工具/Worker 都不直接 fetch Python |

### capability：解耦键（最易误解的概念）

capability 只是一个名字。它让**请求方不知道谁在干活，实现方不知道谁在请求**：

```
PlannerTool.execute ──dispatch('allocation.assign')──▶ Registry 查询（找谁实现）
                                                      ▼
                                            AllocationWorkerRuntime.run()
                                            （这层才决定调哪个算法、哪个 Python 端点）
```

好处：Python 端点改名/拆分只改 Worker 一处；`validation.check` 这类纯规则能力不需要 Python；
一个能力可以编排多个算法端点（如 `route.plan` 先查风险再算航线）。
**加工具 = 加一个薄按钮（几行），≠ 加通信代码。**

### 一次调度的完整时序

```mermaid
sequenceDiagram
    participant API as POST /dispatch
    participant ORC as PlannerOrchestrator
    participant AG as Planner Agent (pi)
    participant H as pi 三钩子
    participant T as PlannerTool
    participant R as Router/Registry
    participant W as WorkerRuntime
    participant PY as Python FastAPI
    participant DB as PostgreSQL

    API->>ORC: 调度意图
    ORC->>DB: 创建 Plan + Run
    ORC->>H: 装配 beforeToolCall/afterToolCall/finishTurn
    ORC->>AG: agent.prompt(意图)
    AG->>H: beforeToolCall（策略门：取消/白名单/重试上限）
    AG->>T: execute(toolCallId, params, signal)
    T->>R: dispatch('allocation.assign', WorkerTask)
    R->>W: run(task)
    W->>PY: AlgorithmClient.allocateTasks()
    PY-->>W: 分配结果
    W-->>T: WorkerResult
    T-->>AG: AgentToolResult（failed 则 throw 交还模型）
    AG->>H: afterToolCall（落 worker_executions + feedback 事件）
    AG->>H: finishTurn（Replanner：continue/end 否决）
    AG-->>ORC: agent_end
    ORC->>DB: 汇总持久化 → 返回
```

### 协同组件 = pi 原语（不自研平行框架）

| 设计组件 | pi 原语 | 我们的实现 |
|---|---|---|
| Replanner | `finishTurn` → `{action:'continue'\|'end'}` | `orchestration/replanner.ts` |
| Feedback Handler / 审计 | `afterToolCall` + `terminate` | `orchestration/feedback-handler.ts` |
| 执行策略 / 权限门 | `beforeToolCall`（block/terminate） | `orchestration/execution-policy.ts` |
| Worker 并行 | `toolExecution:'parallel'` / `executionMode` | 工具声明 |
| 人机回环 / 等待补充信息 | `steer()` / `followUp()` | Phase 1 接入 |
| 执行追溯 + 流式推流 | `subscribe` 事件流 | → `worker_executions` / SSE |
| 转录持久化 | `prepareRequest` + `Session` | Phase 1 用 JSONB 快照 |

**决策权划分（定稿）**：Replanner 是"刹车"不是"方向盘"——只做预算/安全类否决
（maxTurns、超时、预算），**正向决策全部归 Planner**。

### 工具契约六约定（写工具前必读）

1. 参数用 **TypeBox**（`Type.Object`），pi 运行时自动校验；zod 只管业务边界（HTTP DTO / Python 响应）
2. **失败必须 `throw`**——运行时以 `isError:true` 交还模型自纠；别把错误包进 `content`
3. `need_input` → 结果带 `terminate: true`（注意 pi 语义：**整批工具结果全 terminate 才停轮**）
4. 有副作用的派发工具 → `executionMode: 'sequential'` + `replay: 'never'`
5. id 用 pi 导出的 **`uuidv7`**（时间有序）
6. `correlationId` = pi `toolCallId`——「工具调用 ↔ WorkerTask ↔ 落库记录」三方关联

### 设计红线（不可违背）

- **算法全部在 Python**：Node 不写数值算法；Worker 只做编排与领域解读
- **工具不直接 fetch Python**：通信只走 `AlgorithmClient` 一个闸门
- **不信任 Planner 输出**：最终方案必须过 validation 硬闸门（确定性校验）才可下发
- **一切可回放**：每次工具执行落 `worker_executions`，每次反馈落 `dispatch_events`

---

## 目录结构

```
src/
├── main.ts                        # 启动入口（优雅启动/退出，全局前缀 /api/v1）
├── app/app.module.ts              # 根模块（Common + Agent + Dispatch）
│
├── agents/                        # Agent 专业能力
│   ├── core/
│   │   ├── runtime-loader.ts      #   pi 两包动态 import（ESM-only 解法，见下）
│   │   ├── planner-tool.ts        #   AgentTool 工厂 + workerResultToToolResult（throw 约定）
│   │   ├── worker-runtime.interface.ts  # WorkerRuntime / WorkerDefinition 契约
│   │   └── planner-context.ts     #   PlannerRunContext（预算/安全参数）
│   ├── planner/
│   │   ├── planner.agent.ts       #   装配 pi Agent（initialState + 三钩子注入）
│   │   ├── system-prompt.ts       #   Planner 系统提示词
│   │   └── tools/assign-tasks.tool.ts  # 委派 allocation.assign 的薄按钮
│   └── workers/allocation/
│       ├── allocation.runtime.ts  #   allocation.assign 确定型执行器
│       └── algorithm-selector.ts  #   确定性选算法（禁止 LLM 参与）
│
├── orchestration/                 # Agent 间协同（pi 钩子工厂，不自研框架）
│   ├── planner-orchestrator.ts    #   API→Plan/Run→prompt→收集→持久化
│   ├── worker-router.ts           #   dispatch(capability) + zod 边界校验
│   ├── execution-policy.ts        #   = pi beforeToolCall（取消/白名单/重试上限）
│   ├── feedback-handler.ts        #   = pi afterToolCall（落库+反馈事件）+ 计时
│   └── replanner.ts               #   = pi finishTurn（只否决：maxTurns/超时/预算）
│
├── registry/                      # capability → Worker 定义（V1 静态注册）
│   ├── worker-registry.ts
│   └── definitions/allocation.def.ts
│
├── contracts/                     # A2A 协议
│   ├── worker-task.ts / worker-result.ts   # WorkerTask / WorkerResult + 枚举
│   ├── runtime-schema.ts          #   zod 边界校验（Router/网关回收处）
│   └── version.ts                 #   schemaVersion
│
├── services/
│   ├── python/python-client.ts    #   AlgorithmClient（Python 唯一闸门）
│   └── db/dispatch.repo.ts        #   Plan/Run/WorkerExecution/DispatchEvent 仓储
│
├── api/                           # 对外 HTTP
│   ├── dispatch.controller.ts     #   POST /api/v1/dispatch
│   ├── dispatch.module.ts         #   装配：Registry/Router/Orchestrator/闸门
│   └── dto/dispatch.dto.ts        #   zod DTO
│
├── infrastructure/llm/llm-config.ts   # pi-ai Models/Model 装配
├── db/                            # Drizzle：uavs/tasks/flight_logs/plans/runs/
│                                  #          worker_executions/dispatch_events
├── modules/                       # 旧功能模块（agent/common；agent 为遗留占位，待新编排接管）
└── shared/                        # ZodValidationPipe 等横切关注点
```

### ESM/CJS 构建约束（重要）

pi 两包是 **ESM-only** 且 `exports` 只有 `"import"` 条件——CJS `require()` 直接
`ERR_PACKAGE_PATH_NOT_EXPORTED`（Node 22 实测）。解法已收口在 `agents/core/runtime-loader.ts`：
**间接动态 `import()`**（`new Function` 触发原生 ESM import），类型用 `import type` 擦除。
新代码引用 pi 运行时值（Agent/Type/uuidv7…）一律经 `loadPiRuntime()`，禁止静态 import。

---

## 数据流转与持久化

| 表 | 记录什么 | 写入时机 |
|---|---|---|
| `plans` | 一次调度计划（目标/约束/状态） | Orchestrator 接单 |
| `runs` | 一次执行（状态机 created→planning→executing→validating→completed / failed / cancelled） | Orchestrator 接单/收尾 |
| `worker_executions` | 每次工具执行（capability/attempt/status/耗时/feedback） | `afterToolCall` 钩子 |
| `dispatch_events` | 事件流（replan/reallocate/…/need_information） | `afterToolCall` 钩子（feedback 转事件） |

`correlationId`（= pi `toolCallId`）把「工具调用 ↔ WorkerTask ↔ 落库记录」串成可回放链路。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/dispatch` | 提交调度意图（`{ objective, constraints? }`）→ 创建 Plan+Run，启动 Planner 闭环 |
| POST | `/api/v1/agent/execute` | （遗留占位，待 dispatch 接管） |

### AlgorithmClient（Python 闸门）

| 方法 | 对应 Python 端点 | 说明 |
|---|---|---|
| `allocateTasks(req)` | `POST /api/v1/tasks/allocate` | 任务分配（Hungarian/Auction） |
| `planPath(req)` | `POST /api/v1/paths/plan` | 航线规划（A-star/RRT） |
| `assessRisk(req)` | `POST /api/v1/risk/assess` | 风险评估 |
| `evaluateAdaptability(req)` | `POST /api/v1/adaptability/evaluate` | 适配评估 |

统一提供：per-method 超时、`AbortSignal` 贯通（`agent.abort()` 真取消）、`X-Correlation-Id` 透传、错误映射
（`AlgorithmError { code, retryable }`：400/422→不重试，5xx/网络/超时→可重试）、响应 zod 校验。
**Python 端接口契约（实现者直接照做）**：[`docs/architecture/python-api-contract.md`](../../docs/architecture/python-api-contract.md)

## 新增一个能力（固定 5 步）

以新增 `risk.assess` 为例：

| 步 | 位置 | 做什么 |
|---|---|---|
| 1 | Python `api/v1/endpoints/` | 加 route + pydantic schema（算法本体） |
| 2 | `contracts/`（或 client 内 schema） | 加 zod 请求/响应 schema |
| 3 | `services/python/python-client.ts` | 加类型化方法 `assessRisk()`（已存在则跳过） |
| 4 | `agents/workers/risk/` + `registry/definitions/` | WorkerRuntime 实现 + `registry.register(...)` |
| 5 | `agents/planner/tools/` | （可选）加 Planner 工具委派该 capability |

第 5 步的工具永远只是第 4 步之上的薄壳。**加工具 ≠ 加通信代码。**

## 快速开始

```bash
# 安装依赖（monorepo 根目录执行）
pnpm install

pnpm run dev:node      # 启动开发服务（:3000，前缀 /api/v1）
pnpm run build:node    # 构建
pnpm run lint:node     # Lint
pnpm run test:node     # 测试（Jest，23+ 用例）
pnpm run db:generate   # 生成 Drizzle 迁移
pnpm run db:migrate    # 执行迁移
```

## 测试

```bash
pnpm run test:node
```

- 工具契约：`agents/core/planner-tool.spec.ts`（throw/terminate 约定锁死）
- pi 三钩子：`orchestration/hooks.spec.ts`（策略门/落库/Replanner 否决）
- 解耦与边界：`orchestration/worker-router.spec.ts`（capability 分发 + zod 拦脏数据）
- 工具上下文：`agents/planner/tools/assign-tasks.tool.spec.ts`（planId/runId/correlationId 绑定）
- 提示词：`agents/planner/system-prompt.spec.ts`（动态能力清单）
- LLM 闭环测试用 pi-ai `fauxProvider()` 做无真实 LLM 的确定性回放（Phase 1）

## 当前状态与待办

**已就绪**：目录骨架完整、契约与钩子落地、AlgorithmClient 闸门、Registry/Router、
Plan/Run 落库、29 单测、README/架构文档同步。

**审查 4 问题已修复（2026-10-19）**：①工具 `planId/runId` 从 `runContext` 绑定（不再空串）
②system-prompt 能力清单由 `router.listCapabilities()` 动态生成 ③策略常量收敛到
`EXECUTION_POLICY_DEFAULTS` ④contracts 改 zod 单源（类型 `z.infer` 推导，无双份维护）。

**Phase 1 待接**（均有 TODO 标注）：
1. `infrastructure/llm`：provider 动态注册（`createPlannerModel`）
2. `planner-orchestrator`：LLM 闭环（createPlannerAgent → prompt → subscribe 事件流 → SSE）
3. Run 硬超时 → `agent.abort()` 降级人工；validation 硬闸门接入

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` / `NODE_API_PORT` | `3000` | 服务端口 |
| `PYTHON_BACKEND_URL` | `http://localhost:8000` | Python 算法服务地址 |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/st_risk` | PostgreSQL 连接 |

## 依赖

- 运行时：@nestjs/*、@earendil-works/pi-agent-core、@earendil-works/pi-ai、drizzle-orm + postgres、zod、rxjs
- 开发：@nestjs/cli、jest + ts-jest、eslint、typescript、drizzle-kit
