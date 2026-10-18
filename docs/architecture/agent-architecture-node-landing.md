# 多警种无人机智能调度系统 — Agent 架构 Node 端落地分析

> 目的：把《Agent 架构最终定稿》中的设计，逐组件映射到 `apps/server/node-backend`（即设计里的 `node-backend/src`），核对现有仓库的真实状态，并锁定落地前的硬约束。本文不写实现代码（示例只表达契约），只做映射、差距分析和第一阶段文件级方案。
>
> **v2 修订**：以 `@earendil-works/pi-agent-core@0.87.1` / `@earendil-works/pi-ai@0.87.1` 的发布产物（`.d.ts`、README）与本机实测为基准复核全文。**本项目是"在 pi 两个包上继续拓展"，凡 pi 已提供的原语必须优先复用，不自研平行机制**——这是本文新增第 2、7 节的由来。

---

## 0. 结论先行（TL;DR）

架构完全可以在现有 node-backend 上落地，技术选型（NestJS + `@earendil-works/pi-agent-core` + `@earendil-works/pi-ai` + Drizzle）与设计一致。但落地前有 **6 个必须先锁定的偏差/约束**：

1. **实际后端是 NestJS，不是 Express。** 设计文档与《后端技术选型建议》里写的是 "Express"，但 `package.json` 依赖的是 `@nestjs/core` + `@nestjs/platform-express`，`main.ts` 用 `NestFactory`。应以 **NestJS** 为准，回头更新选型文档。
2. **`pi-agent-core` / `pi-ai` 是 ESM-only，且 `exports` 只有 `"import"` 条件。** 实测（Node v22.23.1）：`require('@earendil-works/pi-ai')` 直接抛 `ERR_PACKAGE_PATH_NOT_EXPORTED`——CJS `require()` 连入口都解析不到。TS 把静态 `import` 降级为 `require` 后运行期必挂。Phase 1 必须用**动态 `import()` 惰性加载**（现 `runtime-loader.ts` 的 `new Function` 方案），这是唯一低风险解法。详见第 8 节。
3. **工具契约是 TypeBox，且要按 pi 的完整约定写。** `AgentTool<TParameters extends TSchema>` 的 `parameters` 必须 TypeBox；`label` **必填**；**工具失败要 `throw`**（运行时以 `isError: true` 交还模型自纠），不要把错误包进 `content`；`AgentToolResult` 还有 `terminate`（整批都 terminate 才提前停轮）。另外 **pi 运行时已按 TypeBox schema 自动校验工具参数**，zod 只负责业务边界（HTTP DTO、Python 响应、WorkerTask 构造）。详见第 6 节。
4. **设计里的 Replanner / Feedback Handler / 执行策略 / 并行调度 / 等待补充信息 / 执行追溯 / 流式推流，pi 全部有原生原语**：`finishTurn`、`afterToolCall`+`terminate`、`beforeToolCall`+`replay`、`toolExecution`/`executionMode`、`steer()`/`followUp()`、`subscribe` 事件流、`prepareRequest`+`Session`。落地原则：**把设计组件实现为 pi 钩子，而不是另起一套编排框架**。详见第 7 节。
5. **现有 `Agent` 模块是单文件 stub，且 `AgentRepository` 是内存 `Map`。** 需按设计重构为 `agents/` + `orchestration/` + `registry/` + `contracts/` 多目录；持久化要落到 Drizzle 真实表（Plan / Run / WorkerExecution / Event）。
6. **原有 `agents/` 三件套的 4 处与 pi 约定的偏差已修正**（缺 `model`、错误未 throw、id 未用 `uuidv7`、副作用工具未设 `executionMode`），见第 4 节；剩余跟进项（hooks 装配、`correlationId` 字段）随 Phase 1 做。

---

## 1. 现有仓库真实状态（核对结果）

| 路径                                             | 现状                                                                                          | 与设计的关系                                                                                                 |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `src/main.ts`                                  | NestJS 启动、全局前缀 `/api/v1`、CORS、优雅退出                                                          | 设计里的"调度业务 API 入口"载体                                                                                    |
| `src/app/app.module.ts`                        | 只导入 `CommonModule`、`AgentModule`                                                            | 需新增 `OrchestrationModule`、`RegistryModule`、`ContractsModule` 等                                         |
| `src/modules/agent/agent.controller.ts`        | `@Post('execute')`，用 `ZodValidationPipe`                                                    | 应下沉为 `api/` 下的调度 API，不再直接做编排                                                                           |
| `src/modules/agent/agent.service.ts`           | **TODO 占位**：只把结果存内存并返回 `status:'pending'`                                                   | 这是要被 `orchestration/planner-orchestrator.ts` + Planner Agent 取代的核心                                     |
| `src/modules/agent/agent.module.ts`            | 用 `useFactory` 直接 new `PythonBackendClient`                                                 | 注册方式可用，但应迁到 `services/`                                                                                |
| `src/modules/agent/repositories/agent.repo.ts` | **内存 `Map`**                                                                                | 设计要求的"可追溯执行记录"不能用内存，需换 Drizzle                                                                         |
| `src/agents/core/runtime-loader.ts`            | `new Function` 间接动态 `import()` 加载 pi 两包 + `createStreamFn`                                  | ✅ 方向正确（实测确认必要，见第 8 节）；`createStreamFn` 可简化为 pi 惯用的 `models.streamSimple.bind(models)`            |
| `src/agents/core/planner-tool.ts`              | `definePlannerTool` 工厂 + `toAgentToolResult` + `workerResultToToolResult`                          | ✅ TypeBox 契约正确；✅ 已按 pi 约定修正错误约定（failed→throw）+ `executionMode`/`replay`（见第 4 节）                                                                 |
| `src/agents/planner/planner.agent.ts`          | `new core.Agent({ streamFn, initialState: { systemPrompt, model, tools } })`                          | ✅ 已修正：`model` 经 options 注入 initialState，id 改 `uuidv7`（见第 4 节）                                                                    |
| `src/clients/python-backend/client.ts`         | `planPath / allocateTasks / assessRisk / evaluateAdaptability`                              | 正是设计里 Allocation / Route / Risk / Resource(Adaptability) Worker 要调用的 Python 客户端，应提升为 `services/python` |
| `src/db/engine.ts` + `models/`                 | Drizzle + Postgres；已有 `uavs / tasks / flightLogs` + `plans / runs / worker_executions / dispatch_events` | 缺 `final_plans / allocations`；转录持久化方案待定（见第 7.6 节）                                                        |
| `src/shared/pipes/zod.pipe.ts`                 | 通用 Zod 校验管道                                                                                 | 用于 Nest 控制器 DTO 校验（保留）；**不**用于 AgentTool 参数（pi 已按 TypeBox 自动校验）                                        |
| `src/contracts/*`                              | `WorkerTask` / `WorkerResult` / `WORKER_CONTRACT_VERSION`（含 `WorkerStatus` / `FeedbackType` 枚举）   | ✅ 与定稿一致；建议补 `timestamps`、`correlationId`，id 改用 pi 的 `uuidv7`                                             |
| `packages/shared-ts/src/**`                    | `UAV / Task / RiskAssessment / AdaptabilityResult / AgentTaskRequest / AgentTaskResponse` 等 | 缺 `WorkerTask / WorkerResult / Plan / Run` 等契约类型                                                       |
| 依赖                                             | 已声明 `pi-agent-core@0.87.1`、`pi-ai@0.87.1`、`drizzle-orm`、`zod`                                | 与设计选型吻合；除 `agents/` 三件套外尚未在源码中实际 import                                                                |

> 注：你提到的《设计Agent架构》《Agent目录设计》两份文档在本次工作区未检索到（无 `.txt`、无同名 `.md`），本文基于对话中给出的定稿设计 + 代码核对得出。若这两份文件实际存在，落地前再交叉比对一次。

---

## 2. pi 两个包的基线与必须遵循的约定（拓展的前提）

**分工**：
- `pi-ai` = 模型接入层：Provider 体系与鉴权、`Models` 目录、流式协议、TypeBox 工具 schema 与校验、token/成本统计、faux 测试 Provider。
- `pi-agent-core` = Agent 运行时：状态化的 `Agent`（转录、工具执行、事件、steering/follow-up 队列）、低层 `agentLoop`、`harness/`（AgentHarness、session、skills、prompt templates、compaction）、telemetry。

**包形态**（0.87.1 实测）：两者均为 `"type": "module"`，`exports` 含 `"."`、`"./node"`（core，附 `NodeExecutionEnv`）、`./providers/*`、`./api/*`、`./utils/*` 等子路径（ai）；`pi-ai` 重导出 `Type` / `TSchema` / `Static`（typebox）与 `StringEnum`、`validateToolCall`、`uuidv7`；`pi-agent-core` 重导出 `uuidv7`，并传递依赖 `@earendil-works/pi-telemetry`（telemetry schema 原语）与 `@earendil-works/chord`（实验性 facet 服务）。

### 2.1 必须遵守的写法（"遵循 pi"清单）

| # | pi 约定 | 正确写法 / 说明 |
| --- | --- | --- |
| 1 | **Agent 构造签名** | `new Agent({ streamFn, initialState: { systemPrompt, model, tools, thinkingLevel?, messages? }, getApiKey?, beforeToolCall?, afterToolCall?, finishTurn?, prepareRequest?, prepareNextTurn?, toolExecution?, sessionId? })`。⚠️ `tools / systemPrompt / model` 都在 `initialState` 里，**不是**顶层参数 |
| 2 | **streamFn** | `models.streamSimple.bind(models)`（README 惯用法）；`model` 由 `models.getModel(provider, id)` 取得 |
| 3 | **工具定义** | 对象字面量（pi 无 `defineTool` 工厂）：`name / description / parameters(TypeBox)` + **`label`（必填，UI 用）** + `execute(toolCallId, params, signal?, onUpdate?)`；可选 `executionMode`、`prepareArguments`、`replay: 'never'|'safe'`、`constrainedSampling` |
| 4 | **工具失败要 `throw`** | 运行时捕获后以 `isError: true` 报告给模型，由模型自纠/重试；**不要**把错误编码进 `content`。成功才 `return { content, details }` |
| 5 | **`terminate` 语义** | `AgentToolResult.terminate`、`beforeToolCall`/`afterToolCall` 的 `terminate` 都只是"提示结束"，**整批工具结果全部 terminate 才真正提前停轮** |
| 6 | **工具参数校验** | 运行时按 TypeBox schema 自动校验（`beforeToolCall` 拿到的 `args` 已校验过）；手动循环用 `validateToolCall(tools, toolCall)`。schema 里的枚举用 `StringEnum([...])`（Google 兼容，勿用 `Type.Enum`） |
| 7 | **改系统提示词** | 不重建 Agent：追加 system message（`content` 增量 / `sections` 命名替换）；`agent.state.systemPrompt` 是只读回放 |
| 8 | **模型可热切换** | `agent.state.model = ...` / `state.thinkingLevel`；无需重建实例 |
| 9 | **ID 约定** | 用 pi 导出的 `uuidv7`（时间有序），不用 `randomUUID` |
| 10 | **鉴权** | Provider 自己解析凭证（环境变量、`CredentialStore`、OAuth）；`createModels({ credentials })` 注入持久化凭证存储；Agent 的 `getApiKey` **只**用于动态/易过期 token |
| 11 | **自定义消息** | 用 declaration merging 扩展 `CustomAgentMessages` 承载应用消息，在 `convertToLlm` 里过滤/转换 |
| 12 | **测试** | `pi-ai` 的 `fauxProvider()` + `fauxAssistantMessage/fauxToolCall/fauxText/fauxThinking` 做无真实 LLM 的确定性回放 |
| 13 | **可观测** | 用传递依赖 `pi-telemetry` 的 `defineTelemetrySchema` / span 原语（core 已带 `AGENT_TELEMETRY_SCHEMAS`、`startHarnessSpan`），不自研埋点格式 |

### 2.2 何时用 `Agent`，何时用 `AgentHarness`

- **Phase 1 用 `Agent` 就够**：状态化转录 + 工具执行 + 事件流，是设计里 Planner 的最小载体。
- **`AgentHarness` 是进阶扩展点**：其 `AgentHarnessTool<TContext>` 在 `execute(toolCallId, params, onUpdate, toolContext, invocation, context)` 里**注入工具上下文**（如 `{ workerRouter, runId }`），还有 skills / prompt templates / compaction / session 集成。当工具需要注入上下文而不想用闭包、或需要长会话压缩时再升级；对应 `harness/tools` 内置 `createBashTool / createEditTool / createReadTool / createWriteTool` 的工厂风格。

---

## 3. 设计组件 → pi 原语 → Node 落地（三列映射）

下列路径以 `node-backend/src/` 为根，沿用现有 `@/* → src/*` 路径别名。**pi 原语列是落地时的首选实现载体**。

| 设计组件                     | pi 原语（首选）                                                                                            | Node 落地位置                                                                                            | 当前是否存在                      |
| ------------------------ | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------- |
| **Planner Agent**        | `Agent`（`initialState: { systemPrompt, model, tools }` + `streamFn`）                                    | `agents/planner/planner.agent.ts`                                                                      | 是（stub，缺 model）              |
| Planner 提示词 / 决策整合       | system message `sections` 动态更新；`result-aggregator` 自研归并                                                | `agents/planner/system-prompt.ts`、`agents/planner/result-aggregator.ts`                              | 否                           |
| **Planner 工具（委派 Worker）** | `AgentTool`（TypeBox `parameters`，`execute` 内调 Router）                                                    | `agents/planner/tools/*.tool.ts`、`agents/core/planner-tool.ts`                                       | 是（仅 assign_tasks）             |
| **Worker Agent / 执行器**   | LLM 型：`Agent`；确定型：普通 class 实现 `WorkerRuntime` 接口（pi 不强制一切皆 Agent）                                          | `agents/workers/<x>/<x>.runtime.ts`（allocation / risk / route / resource / validation）              | 否                           |
| **Worker Registry**      | 无 pi 对应（应用层概念），NestJS `onModuleInit` 静态注册                                                               | `registry/worker-registry.ts` + `registry/definitions/*.ts`                                          | 否                           |
| **Worker Router**        | 无 pi 对应（应用层），在工具 `execute` 内被调用                                                                         | `orchestration/worker-router.ts`                                                                     | 否                           |
| **Workflow Engine**      | `toolExecution: 'parallel'` / per-tool `executionMode`（一批工具调用的天然并发）；顺序依赖才自研轻量 DAG                        | `orchestration/workflow-engine.ts`                                                                   | 否                           |
| **Feedback Handler**     | `afterToolCall`（结果后处理/落库）+ `AgentToolResult.terminate` + `CustomAgentMessages`（反馈入转录）                 | `orchestration/feedback-handler.ts`（作为 hook 实现被装配）                                                    | 否                           |
| **Replanner**            | `finishTurn`（`{ action: 'continue' | 'end' }`）+ `prepareNextTurn(WithContext)`（下一轮注入消息/换模型）             | `orchestration/replanner.ts`（作为 hook 实现被装配）                                                          | 否                           |
| **执行策略 / 权限门**           | `beforeToolCall`（`{ block, reason, terminate }`）+ `AgentTool.replay` + `executionMode`                  | `orchestration/execution-policy.ts`（作为 hook 实现被装配）                                                   | 否                           |
| **Planner Orchestrator** | 装配 `Agent` + 三个 hook + `subscribe` 落库/推流；`agent.prompt()` 驱动                                           | `orchestration/planner-orchestrator.ts`                                                              | 否（现 AgentService 占位）        |
| 执行上下文                    | `AgentContext` / `AgentTurnContext`（pi 自带）；应用层补充 runId 等                                                 | `agents/core/planner-context.ts`                                                                     | 否                           |
| **A2A Contract**         | 无 pi 对应（Agent↔Worker 间协议）；工具参数侧用 TypeBox，Worker 侧用 zod                                                      | `contracts/worker-task.ts`、`contracts/worker-result.ts`、`contracts/runtime-schema.ts`、`contracts/version.ts` | 是（接口已定）                     |
| **Python 算法客户端**         | 无 pi 对应（普通 HTTP 适配器）                                                                                   | `services/python/python-client.ts`（由现有 `clients/python-backend` 提升）                                  | 有（需改名/提级）                   |
| DB 业务服务                  | Drizzle；转录持久化可选实现 pi `Session`/`SessionRepo`（`harness/session`）                                            | `services/db/*.repo.ts` + `db/models/*.ts` 扩展                                                        | 部分                          |
| 领域模型                     | —                                                                                                    | `domain/*.ts`                                                                                        | 部分（shared-ts 有基础 UAV/Task）  |
| LLM 配置                   | pi-ai `createModels()` + `models.setProvider(...Provider())` + `getModel` + Provider 自带鉴权                | `infrastructure/llm/llm-config.ts`                                                                   | 否                           |
| 持久化 / 日志 / 监控            | `pi-telemetry` span schema（监控）；Drizzle（持久化）                                                              | `infrastructure/persistence/*`、`infrastructure/logging/*`                                            | 部分                          |
| 对外 API                   | `@Controller` + `ZodValidationPipe`（zod 只在这里和边界用）                                                        | `api/dispatch.controller.ts`、`api/dto/*.ts`                                                          | 部分（现 `agent.controller.ts`） |

**目录组织原则（与设计一致）：** Agent 专业能力在 `agents/workers/`；Agent 间调用与协同在 `orchestration/`；通信协议在 `contracts/`；算法与外部系统连接在 `services/`；不要把所有职责塞回 `agent.service.ts`。

---

## 4. 现有 `agents/` 代码审查（对照 pi 约定的逐条结论）

### 4.1 `agents/core/runtime-loader.ts` — ✅ 保留，微调（未改）

- ✅ `new Function('specifier', 'return import(specifier)')` 间接动态 import：实测证明必要（第 8 节），且 `import type` 擦除不产生运行时依赖。
- 🔧 `createStreamFn(models)` 里的签名断言可简化为 pi 惯用的 `models.streamSimple.bind(models)`；若保留封装，避免用 `as` 覆盖参数类型掩盖不匹配。
- 💡 可补一个 `loadProvider(name)` 辅助（provider 也是 ESM 子路径 `@earendil-works/pi-ai/providers/*`，同样要动态 import）。

### 4.2 `agents/core/planner-tool.ts` — ✅ 契约正确，✅ 错误约定已修正（2026-10-18）

- ✅ `parameters` 用 TypeBox、`label` 必填、`execute(toolCallId, params, signal)` 签名正确；`definePlannerTool` 作为薄工厂可以（pi 无 `defineTool`，手写对象字面量或薄工厂都行）。
- ✅ **已修**：新增 `workerResultToToolResult(result)` 统一收敛 WorkerResult→工具结果：`failed` → **throw**（`[workerType] code: message`，运行时以 `isError: true` 交还模型）；`need_input` → `terminate: true`；`success`/`partial` → 正常 `content + details`。保留 `toAgentToolResult` 供非 Worker 场景的成功包装。
- ✅ **已修**：`PlannerToolConfig` 增加 `executionMode: 'sequential' | 'parallel'` 与 `replay: 'never' | 'safe'`（透传给 `AgentTool`）；`execute` 签名补上 pi 的第 4 参 `onUpdate`（长耗时调用可回传进度）。
- 🔧 可选跟进：对严格 JSON 参数开 `constrainedSampling: { type: 'json_schema', strict: 'prefer' }`，减少参数重试。

### 4.3 `agents/planner/planner.agent.ts` — ✅ 缺 model 已修正（2026-10-18）

- ✅ **已修**：`CreatePlannerAgentOptions` 增加必填 `model: Model<any>`（由调用方 `models.getModel(provider, id)` 取得），注入 `initialState`——`AgentState.model` 是每轮请求必用的模型对象。
- ✅ **已修**：`taskId` 改用 pi 导出的 `ai.uuidv7()`（时间有序）；`assign_tasks` 工具设 `executionMode: 'sequential'` + `replay: 'never'`；结果转换改走 `workerResultToToolResult`（throw 约定）。
- 🔧 待做（Phase 1 编排层）：`beforeToolCall / afterToolCall / finishTurn` 从 Orchestrator 注入，而不是写死在构造里（见第 7 节）。

### 4.4 `contracts/*` — ✅ 保留，补字段

- ✅ `WorkerTask / WorkerResult / WorkerStatus / FeedbackType / WORKER_CONTRACT_VERSION` 与定稿一致。
- 🔧 建议加 `timestamps`（createdAt/startedAt/finishedAt）、`correlationId`（与 pi 的 `toolCallId` 对齐，用于把工具调用 ↔ WorkerTask ↔ 落库记录串起来）。

---

## 5. 关键调用链落地：Planner 通过 Tool 委派 Worker（pi 视角）

这是设计里"Planner 不直接持有 Worker 具体类"的核心，对应 pi-agent-core 的真实用法（括号内是 pi 生命周期点）：

```
API → PlannerOrchestrator
        │ 创建 Plan + Run，装配 Planner Agent（Agent + 3 hooks + subscribe 落库）
        ▼
   agent.prompt(调度意图)                       （agent_start → turn_start → message_*）
        │ LLM 决定需要某项能力，发起工具调用
        ▼
   [beforeToolCall] 执行策略门：block / terminate   （args 已按 TypeBox 校验通过）
        ▼
   PlannerTool.execute(toolCallId, params, signal, onUpdate)
        │ 把模型参数包成 WorkerTask（uuidv7 + correlationId=toolCallId）
        ▼
   WorkerRouter.dispatch('allocation.assign', task)
        │ 查 Registry 找到 allocation-worker 的 RuntimeFactory
        ▼
   AllocationWorkerRuntime.run(task)
        │ 领域分析 → AlgorithmSelector → pythonClient.allocateTasks
        ▼
   WorkerResult ──失败则 throw（isError 交还模型）──→ 成功则 { content, details, terminate? }
        ▼
   [afterToolCall] 落 worker_executions / feedback → dispatch_events
        ▼
   [finishTurn] Replanner 决策：{ action: 'continue' | 'end' }
        ▼
   agent_end → Orchestrator 汇总 → 持久化 → 返回/SSE 收尾
```

要点（均来自 pi-agent-core 0.87.1 类型定义与 README，可直接落地）：

- Planner 的"工具"就是 pi 的 `AgentTool`：`name / label / description / parameters(TypeBox) / execute(toolCallId, params, signal, onUpdate) → AgentToolResult`；失败 **throw**。
- `execute` 内部**只做一件事**：构造 `WorkerTask` 并调用 `workerRouter.dispatch(...)`，把 `WorkerResult` 包成 `AgentToolResult`。它**不** new `AllocationWorker`。
- `WorkerRouter` 持有 Registry 引用，`dispatch` 按 `capability` 查到 `WorkerDefinition`，用其 `runtimeFactory` 取/建运行时实例，调用 `runtime.run(task)`，拿到 `WorkerResult` 返回。
- Worker 是否需要 LLM：由 `WorkerDefinition.runtimeFactory` 决定——返回 `Agent` 实例（LLM 型）或确定型执行器（纯计算/查询/校验），两者都实现统一的 `WorkerRuntime.run(task): Promise<WorkerResult>` 接口，从而被 Contract 一致调用。**pi 不要求一切皆 Agent**：确定型 Worker 就是普通 class，别为每个算法建 Agent。

---

## 6. 三处必须锁定的技术契约

### 6.1 工具契约：TypeBox + pi 完整字段 + throw 约定

```typescript
import { Type } from '@earendil-works/pi-ai';
import type { AgentTool } from '@earendil-works/pi-agent-core';

const assignTasksTool: AgentTool<typeof AssignTasksParams> = {
  name: 'assign_tasks',
  label: '任务分配',                       // 必填（UI 展示）
  description: '将任务分配给可用无人机，返回分配方案。调用 allocation.assign 能力。',
  parameters: Type.Object({               // 给 LLM 的参数声明；运行时自动按此校验
    uavIds: Type.Array(Type.String()),
    taskIds: Type.Array(Type.String()),
    algorithm: Type.Optional(Type.String()),
  }, { additionalProperties: false }),
  executionMode: 'sequential',            // 有副作用的派发 → 串行；纯查询工具可 'parallel'
  replay: 'never',                        // 派发副作用不可重放（可选）
  execute: async (toolCallId, params, signal, onUpdate) => {
    const workerResult = await workerRouter.dispatch('allocation.assign', buildTask(params, toolCallId));
    if (workerResult.status === 'failed') {
      // pi 约定：失败 throw，运行时以 isError:true 报告给模型，由模型自纠
      throw new Error(`allocation.assign failed: ${workerResult.error?.message}`);
    }
    return {
      content: [{ type: 'text', text: JSON.stringify(workerResult.result) }],
      details: workerResult,
      terminate: workerResult.status === 'need_input',  // 需人工补充信息 → 提示停轮
    };
  },
};
```

注意：
- pi 没有通用 `defineTool` 工厂（harness/tools 只有 `createBashTool/createEditTool/createReadTool/createWriteTool`）；对象字面量或自己的薄工厂皆可。
- `onUpdate` 可流式回传中间进度（对应 `tool_execution_update` 事件，适合长耗时 Python 调用）。
- 需要给工具注入上下文（router/runId）时：闭包（Phase 1）或升级 `AgentHarnessTool<TContext>`（第 2.2 节）。

### 6.2 校验边界：TypeBox 管工具参数，zod 管业务边界

- **TypeBox**：工具参数 schema。**pi 运行时在执行前自动校验**（`beforeToolCall` 收到的 `args` 已通过校验）；校验失败由运行时回错误工具结果给模型重试。枚举用 `StringEnum`。
- **zod**：只在 pi 之外的边界做运行时校验——HTTP DTO（`ZodValidationPipe`）、Python 服务响应、以及 Orchestrator 侧构造 `WorkerTask` 时对领域 `input` 的兜底校验。放在 `contracts/runtime-schema.ts`。设计说的"TS 接口本身不能验证模型实际返回的数据"由这两层共同覆盖，但**不要**用 zod 重复校验工具参数。

### 6.3 WorkerTask / WorkerResult 落地

沿用定稿 interface（`taskId / planId / runId / workerType / capability / objective / input / attempt / schemaVersion` 与 `status / result / feedback / error`），并：

- id 统一 `uuidv7`（pi 导出）；`taskId` 与 pi `toolCallId` 用 `correlationId` 字段对齐；
- 加 `timestamps`、运行指标字段；
- 每个领域定义强类型 `input/output`；
- 用 zod 为 `WorkerResult` 写校验 schema（`status` 与 `feedback.type` 已是受控枚举 ✓）。

---

## 7. pi 原语 → 架构组件映射细则（"遵循 pi"的核心章节）

**总原则：设计里的协同组件，实现为 `Agent` 的钩子/事件/队列的组合，而不是自研一套平行的 Agent 调度框架。**

### 7.1 Replanner = `finishTurn`（+ `prepareNextTurn`）— ✅ 已实现 `orchestration/replanner.ts`（`createFinishTurnHook`）

> **决策权切分（2026-10-18 用户定稿）：Replanner 只做预算/安全类的否决（maxTurns、超时、预算），不做正面调度——正向决策全部归 Planner。** 即 Replanner 是"刹车"不是"方向盘"。`createFinishTurnHook` 即按此实现：默认 `undefined`（放权 pi 正常调度），只在越界时 `end`。

```typescript
finishTurn: async ({ message, toolResults }) => {
  // ⚠️ error / aborted 是硬退出，必须先守卫（README 明确要求）
  if (message.stopReason === 'error' || message.stopReason === 'aborted') return;
  return await replanner.shouldContinue({ message, toolResults })
    ? { action: 'continue' }   // 保证再发一次请求（可被 toolResult/队列调度满足）
    : { action: 'end' };       // turn_end 后结束，不轮询队列
}
```

- `{ action: 'continue' }` 无条件返回会**死循环**（`finishTurn` 会在下一轮后再执行）——Replanner 的判定必须有收敛条件（最大轮次/预算）。
- 需要在下一轮注入补充信息/换模型时用 `prepareNextTurn(WithContext)` → 返回 `AgentLoopTurnUpdate { messages?, model?, context? }`。
- 这就是设计里"重分配/重规划/重试/结束"的决策点：决策结果同时写 `dispatch_events`。

### 7.2 Feedback Handler = `afterToolCall` + `terminate` + 自定义消息 — ✅ 已实现 `orchestration/feedback-handler.ts`（`createAfterToolCallHook` + `ToolExecutionTracker`）

```typescript
afterToolCall: async ({ toolCall, result, isError, args }) => {
  await workerExecutions.record({ toolCallId: toolCall.id, args, result, isError });  // → worker_executions
  const fb = (result.details as WorkerResult)?.feedback;
  if (fb && fb.type !== 'none') await events.append(runId, fb.type, fb);             // → dispatch_events
  return isError ? undefined : undefined;   // 可改写 result.details / 标 isError / 设 terminate
}
```

- Worker 的 `feedback`（replan / reallocate / reroute / reassess_risk / need_information）转成事件流记录；模型侧可通过 `CustomAgentMessages` 把反馈作为自定义消息入转录（`convertToLlm` 里过滤或转述）。
- `need_input` → 工具结果 `terminate: true`（批次全 terminate 才停轮），Run 状态进"等待补充信息"。

### 7.3 执行策略 = `beforeToolCall`（+ `executionMode` / `replay`）— ✅ 已实现 `orchestration/execution-policy.ts`（`createBeforeToolCallHook`）

```typescript
beforeToolCall: async ({ toolCall, args }) => {
  if (await runs.isCancelled(runId)) return { block: true, reason: 'run cancelled', terminate: true };
  if (!policy.allow(toolCall.name))    return { block: true, reason: 'capability not permitted' };
  if (attempts.get(toolCall.name) >= MAX_RETRY) return { block: true, reason: 'retry limit reached' };
}
```

- `block` 会以错误工具结果回给模型（模型可换路）；`terminate: true` 参与批次提前终止。
- 重试上限/超时这类"执行策略"常量放 `orchestration/execution-policy.ts`，但**执行点**是这个 hook。

### 7.4 Workflow 并行 = `toolExecution` / `executionMode`

- 一条 assistant 消息里的多个工具调用默认 **`toolExecution: 'parallel'`** 并发执行（事件按完成序，toolResult 按源序）——Worker 并行调度免费获得。
- 有副作用/写库的工具设 `executionMode: 'sequential'`，整批退化串行。
- 因果顺序/依赖图（如"先 risk 后 allocation"）仍由 Workflow Engine 或 **Planner 自己分轮发起**（推荐后者：LLM 天然按轮次定序，少一个自研 DAG 组件）。

### 7.5 等待补充信息 / 人机回环 = `steer()` / `followUp()`

- `steer(msg)`：打断当前执行（"停！先做这个"）；`followUp(msg)`：Agent 自然停下后追加（"另外再…"）。
- `need_information` 场景：Run 进入等待态 → 人工/API 补充信息 → 用 `followUp`/`steer` 注入 → `agent.continue()`。**不需要自研消息注入机制。**

### 7.6 执行追溯与流式推流 = `subscribe` 事件流

`agent.subscribe(listener)` 的 `AgentEvent` 直接映射到落库与 SSE：

| pi 事件                            | 落库                                        | 推流（SSE/WebSocket） |
| -------------------------------- | ----------------------------------------- | --------------- |
| `agent_start` / `agent_end`      | `runs.status`（PLANNING→…→COMPLETED/FAILED） | 首尾事件            |
| `turn_start` / `turn_end`        | `dispatch_events`（轮次记录）                    | 轮次进度            |
| `message_update`（含 `assistantMessageEvent`） | —                                  | **文本增量**（前端打字机） |
| `message_end`                    | 转录快照（见下）                                  | 完整消息            |
| `tool_execution_start/update/end` | `worker_executions`（起止时间、耗时、结果、isError）   | 工具执行进度          |

- `subscribe` 的 listener **按注册序被 await**，属于 run settlement 的一部分——落库放 listener 里可以拿到"事件已持久化"的保证；`agent_end` 后 `waitForIdle()` 收尾。
- 首版交互形态（第 11 节问题 1）因此有明确答案：**同步收尾 + 事件 SSE** 皆可，二者不冲突。

### 7.7 转录持久化 = `prepareRequest` + pi `Session`

- README 惯用法：`agent.prepareRequest = async ({ context }) => ({ context: { ...context, messages: await session.loadModelContext() } })`——每轮请求前装载权威上下文（可做裁剪/恢复）。
- pi 的 `harness/session` 提供 `Session / SessionRepo / StorageBackedSession / MemorySessionRepo / JsonlSessionRepo`（SQLite 后端在独立包 `@earendil-works/pi-session-backend-sqlite-node`）。选择：
  - **Phase 1 简化**：`agent.state.messages` 快照序列化进 `runs` 表（JSONB）；
  - **Phase 4+**：实现 Drizzle/Postgres 版 `SessionRepo`（或先用 `JsonlSessionRepo`），获得分支/提交/压缩等 pi 语义。
- `transformContext`（裁剪/压缩）与 `convertToLlm`（自定义消息→LLM 消息）是转录处理的两个标准扩展点；长会话压缩可直接用 core 导出的 `compact / shouldCompact / DEFAULT_COMPACTION_SETTINGS`。

### 7.8 可观测 = `pi-telemetry`

core 已导出 `AGENT_TELEMETRY_SCHEMAS / AI_TELEMETRY_SCHEMA / HARNESS_TELEMETRY_SCHEMA / startHarnessSpan / defineTelemetrySchema`。执行监控（Worker 耗时、LLM token/成本）优先用这套 schema 原语落指标，别自研埋点格式。

---

### 7.9 应用层通信闸门：capability 与 AlgorithmClient（2026-10-18 定稿）

**capability 是什么（易误解，先定义）**：一个字符串形式的**能力标识**（如 `allocation.assign` / `risk.assess` / `route.plan`），是 Registry 里的解耦键。**它不是工具，也不是请求**——工具（`AgentTool`）是 LLM 请求能力的入口；向 Python 发 HTTP 只是某个 capability 实现内部的最后一步。

```
PlannerTool.execute ──dispatch('allocation.assign')──▶ Registry 查询（capability → 谁实现）
                                                      ▼
                                            XxxWorkerRuntime.run(task)   ← 领域语义（选算法/整形/解读）
                                                      ▼
                                            AlgorithmClient（★唯一闸门）  ← 超时/校验/错误映射/关联 ID
                                                      ▼
                                            Python FastAPI（算法本体）
```

**为什么工具不直接 fetch Python**：工具是 LLM 触发的、参数是模型生成的——超时/重试/响应校验/错误翻译/落库关联写在 N 个工具里 = N 份不一致；收在 `AlgorithmClient` 一个门里 = 写一次全链路受益（"不重复造轮子"的落地形式）。

**AlgorithmClient 四件套（实现规范）**：
1. **协议**：HTTP/JSON（FastAPI 现状即够，不上 gRPC/队列）。
2. **双端校验**：Python pydantic（算法世界真相源）+ Node zod 镜像（`contracts/`）；响应必须过 zod 再进 WorkerResult，防 schema 漂移。
3. **错误映射**：400/422 → `retryable:false`（模型参数错，throw 交还 LLM）；5xx/连接拒绝 → `retryable:true`；超时 → `retryable:true` + `code:'TIMEOUT'`。
4. **三根管道贯通**：`AbortSignal`（pi `execute` 的 signal → fetch，`agent.abort()` 真取消）；**per-algorithm 超时**（A* 秒回，DE/ALNS 可能分钟级，重算法走异步任务+轮询）；`X-Correlation-Id`（= toolCallId，与 `worker_executions` 串联回放）。

**新增算法固定 5 步（做成无聊流程）**：① Python 加算法+route+pydantic → ② `contracts/` 加 zod schema → ③ `AlgorithmClient` 加类型化方法 → ④ WorkerRuntime 封装 + Registry 注册 capability → ⑤（可选）加 Planner 工具委派该 capability。**加工具 = 加薄按钮（几行），≠ 加通信代码。**

**现状核对**：现有 `clients/python-backend/client.ts` 4 条路径与 FastAPI 实际前缀吻合（`/api/v1/paths/plan`、`/tasks/allocate`、`/risk/assess`、`/adaptability/evaluate`）✓；待改：业务方法参数 `Record<string, unknown>` 弱类型、统一 10s 超时、缺 AbortSignal 贯通、错误映射过薄。

---

## 8. ESM / CJS 落地约束（实测更新）

两个包均 `"type": "module"` 且 **`exports` 只有 `"import"` 条件，没有 `"require"` / `"default"`**。本机实测（Node v22.23.1，npm 安装两个 0.87.1 tarball）：

| 操作                                       | 结果                                          |
| ---------------------------------------- | ------------------------------------------- |
| `require('@earendil-works/pi-ai')`（CJS） | ❌ `ERR_PACKAGE_PATH_NOT_EXPORTED`（解析不到入口） |
| `require('@earendil-works/pi-agent-core')` | ❌ 同上                                      |
| `import('@earendil-works/pi-ai')`（动态 ESM） | ✅ 正常，`Type.Object` 可用                     |

结论：
- TS（`module: commonjs`）把静态 `import` 降级为 `require` → 运行期必挂。**方案 A（动态 `import()` 惰性加载）不是"低风险备选"，而是当前构建形态下的唯一可行解**。现 `runtime-loader.ts` 的 `new Function` 间接 import 实测有效，保留。
- `import type` 是编译期擦除，`types` 条件正常解析，类型检查不受影响。
- 注意 Node 版本：即使在支持 `require(esm)` 的 Node 22.12+，也**过不了 `exports` 条件这一关**（实测如此）；`engines: ">=20.0.0"` 下方案 A 都成立。
- **方案 B（彻底转 ESM）** 仍建议作为第五阶段工程化目标：`"type": "module"` + `tsconfig module/moduleResolution: "nodenext"` + 相对导入补 `.js` + `nest build` ESM 适配。收益：静态 import、类型一致、可 tree-shake；波及面大，不在 Phase 1 做。

---

## 9. 数据库持久化差距

设计要求的"可追溯真实状态"与现有内存 `Map` 不兼容。现有 Drizzle 表：`uavs / tasks / flightLogs / plans / runs / worker_executions / dispatch_events`。仍需补（建议放 `db/models/` 并在 `db:generate` 出迁移）：

| 表                             | 用途                                                            |
| ----------------------------- | ------------------------------------------------------------- |
| `final_plans` / `allocations` | 最终方案与分配结果（关联 run）                                             |
| `run_transcripts`（或 `messages`） | Agent 转录持久化（Phase 1 可用 `runs.context_json` 快照代替；Phase 4 接 pi Session 语义） |

- `AgentTaskResponse.status: string` 这种弱类型要从 shared-ts 收敛为受控枚举。
- `worker_executions` 建议与 pi `toolCallId` 对齐一列，保证「工具调用 ↔ WorkerTask ↔ 落库记录」三方可关联（第 6.3 节 `correlationId`）。

---

## 10. 第一阶段逐文件落地方案（按"先核对、再逐文件实现"）

目标：跑通最小闭环（Runtime Factory + Planner + Allocation Worker + Router + 一个 Python 调用），用户提交调度请求后 Planner 能委派、拿结构化结果、返回。

**新增 / 重构文件清单（Phase 1）：**

```
src/
  api/
    dispatch.controller.ts        // POST /api/v1/dispatch，Zod DTO 校验
    dto/dispatch.dto.ts           // 调度意图入参（zod）
  agents/
    core/
      runtime-loader.ts           // 动态 import pi 两包（方案 A，已存在）+ loadProvider 辅助
      worker-runtime.interface.ts // WorkerRuntime.run(task): Promise<WorkerResult>
      planner-context.ts          // Planner 运行上下文类型（runId 等应用上下文）
    planner/
      planner.agent.ts            // 装配 Agent：initialState{systemPrompt, model, tools} + hooks（✅ model 已修）
      system-prompt.ts            // Planner 系统提示词（后续用 system message sections 动态更新）
      tools/assign-tasks.tool.ts  // Planner 工具：委派 allocation.assign（含 executionMode/throw 约定）
  registry/
    worker-registry.ts            // capability → WorkerDefinition 内存注册表
    definitions/allocation.def.ts// allocation-worker 定义 + runtimeFactory
  orchestration/
    planner-orchestrator.ts       // 替代现 AgentService：装配 Agent+hooks+subscribe，驱动 prompt()
    worker-router.ts              // dispatch(capability, task)
    execution-policy.ts           // ✅ createBeforeToolCallHook：取消/白名单/重试上限（Phase 1 常量）
    feedback-handler.ts           // ✅ createAfterToolCallHook + ToolExecutionTracker：worker_executions + dispatch_events 落库
    replanner.ts                  // ✅ createFinishTurnHook：finishTurn 决策（maxTurns 收敛 + shouldContinue）
  contracts/
    worker-task.ts / worker-result.ts   // 已有；补 timestamps/correlationId
    runtime-schema.ts             // zod 校验：领域 input / WorkerResult / Python 响应
    version.ts                    // 已有
  services/
    python/python-client.ts       // 由 clients/python-backend 提升改名
    db/*.repo.ts                  // runs/worker_executions/dispatch_events 写入
  infrastructure/llm/
    llm-config.ts                 // createModels() + setProvider(...)Provider() + getModel + 鉴权（pi auth）
  db/models/
    plan.ts / run.ts / worker-execution.ts / dispatch-event.ts  // 已有，按第 9 节补字段
  tests/
    planner-loop.faux.spec.ts     // fauxProvider() 回放：Planner→工具→结果 闭环
```

**保留 / 微调：**
- `main.ts`、`app/app.module.ts`（在 `onModuleInit` 静态注册 Registry，装配 OrchestrationModule）。
- `shared/pipes/zod.pipe.ts`（继续用于控制器 DTO；不再用于工具参数）。
- `clients/python-backend` 内容迁到 `services/python`（删除旧位置避免重复）。

**删除 / 废弃：**
- `modules/agent/agent.service.ts` 的 TODO 占位逻辑（由 `planner-orchestrator.ts` 接管）。
- `modules/agent/repositories/agent.repo.ts` 内存 Map（由 Drizzle repo 取代）。

---

## 11. 风险与待确认项（pi 已给答案的直接标注）

1. **dispatch 同步还是异步流式？** ✅ pi 已给答案：`await agent.prompt()` 同步收尾 + `subscribe` 事件流推 SSE（`message_update` 打字机、`tool_execution_*` 进度）两者并行不冲突。首版建议「HTTP 同步返回终态 + 可选 SSE 过程流」。
2. **Worker 是否真要 LLM？** ✅ pi 不要求一切皆 Agent。V1 让 Allocation / Route / Risk / Resource / Validation 全部为**确定型执行器**（纯调 Python + 规则），只有 Planner 用 LLM——最快跑通闭环，也符合"不为每个算法建 Agent"。
3. **Registry 是否需要远程注册中心？** 设计已明确：V1 静态注册（NestJS 启动装配），不做独立注册服务。
4. **Run 状态机具体取值**：replan / wait_info 建议用 `dispatch_events` 事件表达（pi 的事件/队列语义天然支持，见 7.5），而非新增状态值——需确认。
5. **重试上限 / 超时**：实现载体是 `beforeToolCall`（第 7.3 节），常量放 `execution-policy.ts`，Phase 1 先给常量，Phase 4 接入 Feedback/Replanner。
6. **共享类型归属**：`WorkerTask/WorkerResult/Plan/Run` 放 node 端 `contracts/`，还是放 `packages/shared-ts`？若前端也要展示执行状态，建议放 shared-ts；若仅后端内部用，放 contracts/ 即可。需确认。
7. **转录持久化路线**：Phase 1 `runs.context_json` 快照 vs 直接实现 pi `SessionRepo`（第 7.7 节）。倾向前者起步，接口按 pi `Session` 语义留好，避免 Phase 4 返工——需确认。

---

## 12. 一句话定调

> 本项目是在 **pi-agent-core + pi-ai 之上拓展**：`Agent`（工具执行/事件/队列）+ pi-ai（Provider/鉴权/TypeBox）是地基，**Replanner = `finishTurn`、Feedback = `afterToolCall`、执行策略 = `beforeToolCall`、并行 = `toolExecution`、等待补充 = `steer`/`followUp`、追溯与推流 = `subscribe`、转录 = `prepareRequest` + `Session`**——设计组件逐一落成 pi 钩子，只有 Registry / Router / Workflow 依赖 / A2A Contract / Python 适配是真正要自研的应用层。开工前锁死三件事：TypeBox 工具契约（含 throw/terminate 约定）、动态 import 加载（实测唯一可行）、按第 7 节把 Replanner/Feedback/策略落成 pi 钩子（原 4 处代码偏差已修正，见第 4 节）。

---

## 13. 架构评审结论与设计定调（2026-10-18，存档）

**总评 8/10：方向合理，骨架不需推翻；真正风险不在结构，在可靠性与依赖。**

**做对了的（保持不变）**：
1. 「LLM 只做 Planner + 数值优化全在 Python 确定型 Worker」——把两类不确定性隔开，算法可复现，LLM 只管认知与编排；
2. 控制流归 Planner 多轮决策，不自研 DAG 引擎；
3. A2A Contract 的 `status/feedback/error` 三态语义 + `correlationId` 可回放；
4. 协同组件全部映射 pi 原语（升级 = 改适配，不是改架构）。

**结构性待补（落地时解决）**：
1. **Planner 失败兑底缺失（最大的洞）**：不要信任 Planner 输出，用确定性闸门兑住——validation 硬闸门（最终方案必须过确定性校验）+ `beforeToolCall` 策略门 + 人工接管（`steer/followUp`）+ Run 硬超时（`abort()`）。四样都有现成挂载点，不需要新组件；
2. **三组件决策权**：Replanner 只做否决（见 7.1 用户定稿），Workflow 只管并行扇出，正向决策全归 Planner；
3. **A2A 名不副实**：当前是进程内契约——若预期未来跨进程，补序列化/幂等/超时假设；否则改名 Internal Contract，别为想象中的分布式预留复杂度。

**非结构性风险**：LLM 延迟 vs 调度实时性（Run 硬超时 + 降级人工）；pi 0.87.x 演进快（类型引用收口 `agents/core` + `orchestration` 两个薄层，锁小版本）；ESM-only 长期摩擦（转 ESM 别无限期拖）；Prompt 注入面（警情文本进上下文 → 白名单 + validation 硬闸门兑住）。

**两条用户定调（不可违背）**：
1. **Replanner 只做预算/安全类否决（maxTurns/超时/预算），不做正面调度——正向决策全部归 Planner**（"刹车"不是"方向盘"）；
2. **所有算法全部封装在 Python 端**，Node 只做编排；Agent 工具经「Tool → Router → WorkerRuntime → AlgorithmClient → FastAPI」唯一链路访问算法，工具不直接 fetch Python（详见 7.9）。
