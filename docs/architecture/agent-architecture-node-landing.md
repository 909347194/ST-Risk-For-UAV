# 多警种无人机智能调度系统 — Agent 架构 Node 端落地分析

> 目的：把《Agent 架构最终定稿》中的设计，逐组件映射到 `apps/server/node-backend`（即设计里的 `node-backend/src`），核对现有仓库的真实状态，并锁定落地前的硬约束。本文不写实现代码，只做映射、差距分析和第一阶段文件级方案。

---

## 0. 结论先行（TL;DR）

架构完全可以在现有 node-backend 上落地，技术选型（NestJS + `@earendil-works/pi-agent-core` + `@earendil-works/pi-ai` + Drizzle）与设计一致。但落地前有 **4 个必须先解决的偏差/约束**：

1. **实际后端是 NestJS，不是 Express。** 设计文档与《后端技术选型建议》里写的是 "Express"，但 `package.json` 依赖的是 `@nestjs/core` + `@nestjs/platform-express`，`main.ts` 用 `NestFactory`。应以 **NestJS** 为准，回头更新选型文档。
2. **`pi-agent-core` 是 ESM-only，node-backend 当前 `tsconfig` 是 CommonJS。** 直接静态 `import { Agent } from '@earendil-works/pi-agent-core'` 在现有 CommonJS 构建下运行期会失败。Phase 1 推荐用**动态 `import()` 惰性加载**，避免一次性把整个应用转 ESM。
3. **`AgentTool.parameters` 用 TypeBox（`TSchema`），不是 zod。** 选型文档里的 `defineTool({ parameters: z.object(...) })` 示例不能直接套用：pi-agent-core 没有导出通用 `defineTool`，且其 `AgentTool<TParameters extends TSchema>` 要求 TypeBox schema。工具参数 schema 要改成 `Type.Object({...})`。
4. **现有 `Agent` 模块是单文件 stub，且 `AgentRepository` 是内存 `Map`。** 需按设计重构为 `agents/` + `orchestration/` + `registry/` + `contracts/` 多目录；持久化要落到 Drizzle 真实表（Plan / Run / WorkerExecution / Event）。

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
| `src/clients/python-backend/client.ts`         | `planPath / allocateTasks / assessRisk / evaluateAdaptability`                              | 正是设计里 Allocation / Route / Risk / Resource(Adaptability) Worker 要调用的 Python 客户端，应提升为 `services/python` |
| `src/db/engine.ts` + `models/`                 | Drizzle + Postgres；已有 `uavs / tasks / flightLogs`                                           | 缺 `plans / runs / worker_executions / events` 等表                                                       |
| `src/shared/pipes/zod.pipe.ts`                 | 通用 Zod 校验管道                                                                                 | 用于 Nest 控制器 DTO 校验（保留）；**不**用于 AgentTool 参数                                                            |
| `packages/shared-ts/src/**`                    | `UAV / Task / RiskAssessment / AdaptabilityResult / AgentTaskRequest / AgentTaskResponse` 等 | 缺 `WorkerTask / WorkerResult / Plan / Run` 等契约类型                                                       |
| 依赖                                             | 已装 `pi-agent-core@0.87.1`、`pi-ai@0.87.1`、`drizzle-orm`、`zod`                                | 与设计选型吻合；均未在源码中实际 import                                                                                |

> 注：你提到的《设计Agent架构》《Agent目录设计》两份文档在本次工作区未检索到（无 `.txt`、无同名 `.md`），本文基于对话中给出的定稿设计 + 代码核对得出。若这两份文件实际存在，落地前再交叉比对一次。

---

## 2. 设计组件 → Node 目录 / 类映射

下列路径以 `node-backend/src/` 为根，沿用现有 `@/* → src/*` 路径别名。

| 设计组件                     | Node 落地位置                                                                                                    | 使用的原语 / 技术                                                                                                                 | 当前是否存在                      |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| **Planner Agent**        | `agents/planner/planner.agent.ts`                                                                            | `new Agent({ streamFn, tools, systemPrompt, model, getApiKey, beforeToolCall, afterToolCall, finishTurn })`（pi-agent-core） | 否（仅 stub）                   |
| Planner 提示词 / 决策整合       | `agents/planner/system-prompt.ts`、`agents/planner/result-aggregator.ts`                                      | 字符串/模板 + 结果归并                                                                                                              | 否                           |
| **Worker Agent / 执行器**   | `agents/workers/<x>/<x>.runtime.ts`（allocation / risk / route / resource / validation）                       | LLM 型：`Agent`；确定型：普通 class 实现 `WorkerRuntime` 接口                                                                           | 否                           |
| **Worker Registry**      | `registry/worker-registry.ts` + `registry/definitions/*.ts`                                                  | 内存 `Map<capability, WorkerDefinition>`，NestJS `onModuleInit` 静态注册                                                          | 否                           |
| **Worker Router**        | `orchestration/worker-router.ts`                                                                             | `dispatch(capability, task): Promise<WorkerResult>`，查 Registry → 取 RuntimeFactory → run                                    | 否                           |
| **Workflow Engine**      | `orchestration/workflow-engine.ts`                                                                           | DAG / 依赖 / 并行 / 终止条件（自研轻量）                                                                                                 | 否                           |
| **Feedback Handler**     | `orchestration/feedback-handler.ts`                                                                          | 把 WorkerResult.feedback 转成事件                                                                                               | 否                           |
| **Replanner**            | `orchestration/replanner.ts`                                                                                 | 综合全局状态决定重分配/重规划/重试/结束                                                                                                      | 否                           |
| **Planner Orchestrator** | `orchestration/planner-orchestrator.ts`                                                                      | 串起 API→Plan/Run→Planner.prompt→收集结果→持久化                                                                                    | 否（现 AgentService 占位）        |
| 执行上下文 / 执行策略             | `orchestration/execution-context.ts`、`execution-policy.ts`                                                   | 运行态对象 + 重试上限/超时策略                                                                                                          | 否                           |
| **A2A Contract**         | `contracts/worker-task.ts`、`contracts/worker-result.ts`、`contracts/runtime-schema.ts`、`contracts/version.ts` | TS interface（用定稿里的 `WorkerTask`/`WorkerResult`）+ zod 运行时校验                                                                 | 否                           |
| **Python 算法客户端**         | `services/python/python-client.ts`（由现有 `clients/python-backend` 提升）                                          | `fetch` 封装 + 超时                                                                                                            | 有（需改名/提级）                   |
| DB 业务服务                  | `services/db/*.repo.ts` + `db/models/*.ts` 扩展                                                                | Drizzle                                                                                                                    | 部分（仅 uav/task/flightLog）    |
| 领域模型                     | `domain/*.ts`                                                                                                | 警情 / 无人机 / 资源 / 任务 / 约束 / 调度方案                                                                                             | 部分（shared-ts 有基础 UAV/Task）  |
| LLM 配置                   | `infrastructure/llm/llm-config.ts`                                                                           | `Models.streamSimple` + `getApiKey`（pi-ai）                                                                                 | 否                           |
| 持久化 / 日志 / 监控            | `infrastructure/persistence/*`、`infrastructure/logging/*`                                                    | Drizzle + 日志                                                                                                               | 部分                          |
| 对外 API                   | `api/dispatch.controller.ts`、`api/dto/*.ts`                                                                  | `@Controller` + `ZodValidationPipe`                                                                                        | 部分（现 `agent.controller.ts`） |

**目录组织原则（与设计一致）：** Agent 专业能力在 `agents/workers/`；Agent 间调用与协同在 `orchestration/`；通信协议在 `contracts/`；算法与外部系统连接在 `services/`；不要把所有职责塞回 `agent.service.ts`。

---

## 3. 关键调用链落地：Planner 通过 Tool 委派 Worker

这是设计里"Planner 不直接持有 Worker 具体类"的核心，对应 pi-agent-core 的真实用法：

```
API → PlannerOrchestrator
        │ 创建 Plan + Run，构造 Planner Agent
        ▼
   Planner Agent.prompt(调度意图)
        │ LLM 决定需要某项能力，发起工具调用
        ▼
   PlannerTool.execute(args)          // 例如 assignTasksTool
        │ 把模型参数包成 WorkerTask
        ▼
   WorkerRouter.dispatch('allocation.assign', task)
        │ 查 Registry 找到 allocation-worker 的 RuntimeFactory
        ▼
   AllocationWorkerRuntime.run(task)
        │ 领域分析 → AlgorithmSelector → pythonClient.allocateTasks
        ▼
   WorkerResult → Router → Tool 返回 AgentToolResult
        ▼
   Planner Agent 看到结果，决定下一步（继续 / 调整 / 结束）
```

要点（均来自 pi-agent-core 类型定义，可直接落地）：

- Planner 的"工具"就是 pi-agent-core 的 `AgentTool`：含 `name / description / parameters(TypeBox) / execute(toolCallId, params, signal, onUpdate) → AgentToolResult`。
- `execute` 内部**只做一件事**：构造 `WorkerTask` 并调用 `workerRouter.dispatch(...)`，把 `WorkerResult` 包成 `AgentToolResult`。它**不** new `AllocationWorker`。
- `WorkerRouter` 持有 Registry 引用，`dispatch` 按 `capability` 查到 `WorkerDefinition`，用其 `runtimeFactory` 取/建运行时实例，调用 `runtime.run(task)`，拿到 `WorkerResult` 返回。
- Worker 是否需要 LLM：由 `WorkerDefinition.runtimeFactory` 决定——返回 `Agent` 实例（LLM 型）或确定型执行器（纯计算/查询/校验），两者都实现统一的 `WorkerRuntime.run(task): Promise<WorkerResult>` 接口，从而被 Contract 一致调用。

---

## 4. 三处必须锁定的技术契约

### 4.1 工具参数用 TypeBox，不用 zod

`AgentTool<TParameters extends TSchema>` 的 `parameters` 必须是 TypeBox schema（pi-ai 导出 `Type`）。示例：

```typescript
import { Type } from '@earendil-works/pi-ai';
import type { AgentTool } from '@earendil-works/pi-agent-core';

export const assignTasksTool: AgentTool<typeof AssignParams> = {
  name: 'assign_tasks',
  label: '任务分配',
  description: '将任务分配给可用无人机，返回分配方案',
  parameters: Type.Object({
    uavIds: Type.Array(Type.String()),
    taskIds: Type.Array(Type.String()),
    algorithm: Type.Optional(Type.String()),
  }),
  execute: async (_toolCallId, params, signal) => {
    const result = await workerRouter.dispatch('allocation.assign', buildTask(params));
    return { content: [{ type: 'text', text: JSON.stringify(result.result) }], details: result };
  },
};
```

注意：pi-agent-core 的 `harness/tools` 只导出 bash/edit/read/write，**没有通用 `defineTool` 工厂**，工具按上面的对象字面量手写即可。

### 4.2 边界运行时校验用 zod，与 TypeBox 不冲突

- **TypeBox**：给 LLM 看的工具参数 schema（Agent 调用前由运行时做 schema 校验）。
- **zod**：在 Contract 边界做运行时校验——校验"模型实际吐出来的参数是否可信"、校验 `WorkerResult`、校验 Python 服务响应。设计明确说"TS 接口本身不能验证模型实际返回的数据"，这一步必须补。放在 `contracts/runtime-schema.ts`，由 Router/Orchestrator 在分发与回收时调用。

### 4.3 WorkerTask / WorkerResult 落地

直接采用定稿给出的两个 interface（`taskId / planId / runId / workerType / capability / objective / input / attempt / schemaVersion` 与 `status / result / feedback / error`），并：

- 加 `timestamps`、`correlationId`、运行指标字段；
- 每个领域定义强类型 `input/output`；
- 用 zod 为 `WorkerResult` 写一份校验 schema（特别是 `status` 与 `feedback.type` 的枚举）。

---

## 5. ESM / CJS 落地约束（重要）

`pi-agent-core@0.87.1` 的 `package.json` 是 `"type": "module"` 且只导出 ESM（`.js`），**没有 CJS 构建**。而 node-backend 当前：

```jsonc
// tsconfig.json
"module": "commonjs",
"paths": { "@/*": ["src/*"] }
```

CommonJS 下静态 `import { Agent } from '@earendil-works/pi-agent-core'` 运行期会报 ERR_REQUIRE_ESM。两种解法：

- **方案 A（推荐 Phase 1，低风险）：动态 `import()` 惰性加载。** 只在 `agents/core/runtime-loader.ts`（或各 Worker runtime 工厂）内 `const { Agent } = await import('@earendil-works/pi-agent-core')`。Agent 运行时本就是按请求/按 Run 创建的，惰性加载不影响启动。其余 NestJS 代码保持 CommonJS，改动最小。
- **方案 B（彻底）：整个 node-backend 转 ESM。** `package.json` 加 `"type": "module"`，`tsconfig` 改 `"module": "nodenext"` / `"moduleResolution": "nodenext"`，并适配 NestJS 的 ESM 构建（需 `nest build` 的 ESM 配置、相对导入在部分场景补 `.js`）。收益是类型一致、无动态 import，但波及面大，建议作为后续工程化阶段（第五阶段）再做。

**Phase 1 选方案 A。**

---

## 6. 数据库持久化差距

设计要求的"可追溯真实状态"与现有内存 `Map` 不兼容。现有 Drizzle 表：`uavs / tasks / flightLogs`。需新增（建议放 `db/models/` 并在 `db:generate` 出迁移）：

| 表                             | 用途                                                                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `plans`                       | 一次调度计划（目标、约束、创建时间、状态）                                                                                              |
| `runs`                        | 执行 Run（关联 plan，状态机 `CREATED/PLANNING/EXECUTING/VALIDATING/COMPLETED/FAILED/CANCELLED` + replan/wait_info 等扩展状态或事件） |
| `worker_executions`           | 每次 Worker 调用记录（taskId、capability、attempt、status、耗时、feedback）                                                       |
| `dispatch_events`             | 执行事件流（重规划、重试、取消、等待补充信息）                                                                                            |
| `final_plans` / `allocations` | 最终方案与分配结果（关联 run）                                                                                                  |

`AgentTaskResponse.status: string` 这种弱类型要从 shared-ts 收敛为受控枚举。

---

## 7. 第一阶段逐文件落地方案（按"先核对、再逐文件实现"）

目标：跑通最小闭环（Runtime Factory + Planner + Allocation Worker + Router + 一个 Python 调用），用户提交调度请求后 Planner 能委派、拿结构化结果、返回。

**新增 / 重构文件清单（Phase 1）：**

```
src/
  api/
    dispatch.controller.ts        // POST /api/v1/dispatch，Zod DTO 校验
    dto/dispatch.dto.ts           // 调度意图入参（zod）
  agents/
    core/
      runtime-loader.ts           // 动态 import pi-agent-core（方案 A）
      worker-runtime.interface.ts // WorkerRuntime.run(task): Promise<WorkerResult>
      planner-context.ts          // Planner 运行上下文类型
    planner/
      planner.agent.ts            // 构造 Agent + 注册 Planner 工具集
      system-prompt.ts            // Planner 系统提示词
      tools/assign-tasks.tool.ts  // Planner 工具：委派 allocation.assign
    workers/allocation/
      allocation.runtime.ts       // Allocation Worker 运行时（领域分析+算法选择+pythonClient）
      algorithm-selector.ts       // Hungarian/DE/ALNS 选择逻辑（先接 Hungarian）
  registry/
    worker-registry.ts            // capability → WorkerDefinition 内存注册表
    definitions/allocation.def.ts// allocation-worker 定义 + runtimeFactory
  orchestration/
    planner-orchestrator.ts       // 替代现 AgentService：API→Plan/Run→Planner.prompt→收集→持久化
    worker-router.ts              // dispatch(capability, task)
  contracts/
    worker-task.ts                // WorkerTask interface（定稿）
    worker-result.ts              // WorkerResult interface（定稿）
    runtime-schema.ts             // zod 校验：模型参数 / WorkerResult / Python 响应
    version.ts                    // schemaVersion 常量
  services/
    python/python-client.ts       // 由 clients/python-backend 提升改名
  infrastructure/llm/
    llm-config.ts                 // Models.streamSimple + getApiKey 封装（streamFn）
  db/models/
    plan.ts / run.ts / worker-execution.ts / dispatch-event.ts  // 新增表
```


```

**保留 / 微调：**
- `main.ts`、`app/app.module.ts`（在 `onModuleInit` 静态注册 Registry，装配 OrchestrationModule）。
- `shared/pipes/zod.pipe.ts`（继续用于控制器 DTO）。
- `clients/python-backend` 内容迁到 `services/python`（删除旧位置避免重复）。

**删除 / 废弃：**
- `modules/agent/agent.service.ts` 的 TODO 占位逻辑（由 `planner-orchestrator.ts` 接管）。
- `modules/agent/repositories/agent.repo.ts` 内存 Map（由 Drizzle repo 取代）。

---

## 8. 落地风险与待确认项

1. **dispatch 同步还是异步流式？** 火灾侦察这类可能耗时。Phase 1 可先同步（Planner 跑完一轮返回），后续用 `Agent.subscribe` 事件流 + SSE 推前端。需确认首版交互形态。
2. **Worker 是否真要 LLM？** V1 可让 Allocation / Route / Risk / Resource / Validation 全部为**确定型执行器**（纯调 Python + 规则），只有 Planner 用 LLM。这能最快跑通闭环，也符合"不为每个算法建 Agent"。建议 V1 这样。
3. **Registry 是否需要远程注册中心？** 设计已明确：V1 静态注册（NestJS 启动装配），不做独立注册服务。
4. **Run 状态机具体取值**：设计给了 `CREATED/PLANNING/EXECUTING/VALIDATING/COMPLETED/FAILED/CANCELLED`，replan / wait_info 建议用 `dispatch_events` 事件表达，而非新增状态值——需确认。
5. **重试上限 / 超时**：放到 `execution-policy.ts`，Phase 1 先给常量，Phase 4 接入 Feedback/Replanner。
6. **共享类型归属**：`WorkerTask/WorkerResult/Plan/Run` 放 node 端 `contracts/`，还是放 `packages/shared-ts`？若前端也要展示执行状态，建议放 shared-ts；若仅后端内部用，放 contracts/ 即可。需确认。

---

## 9. 一句话定调

> 现有 node-backend 的依赖（NestJS + pi-agent-core + pi-ai + Drizzle + zod）与定稿架构完全对齐；落地的实质工作是**按 `agents/`、`orchestration/`、`registry/`、`contracts/`、`services/`、`infrastructure/` 重构目录**，把内存 stub 换成"Planner(Agent) 持工具 → 工具调 Router → Router 查 Registry 取 WorkerRuntime → WorkerRuntime 调 Python/规则 → 统一 WorkerResult 回 Planner"的闭环，并把真实状态落到 Drizzle。开工前先锁死第 4 节的 TypeBox 工具契约、第 5 节的 ESM 惰性加载、第 6 节的持久化表三件事。
```
