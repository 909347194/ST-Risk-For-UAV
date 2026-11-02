# TODO — ST-Risk-For-UAV / Node 编排层剩余缺口

> 维护背景：本文件汇总 `node-backend`（NestJS + pi-agent-core + Drizzle/PostgreSQL）自
> Phase 1 闭环落地（2026-10-19）与 SSE 推流/旧 agent 模块拆除（2026-10-28）之后，仍待补齐的缺口。
> 按「Phase / 优先级」组织。已完成项列在末尾「已完成」备查。
>
> 关联文档：
> - 架构落地映射：`docs/architecture/agent-architecture-node-landing.md`
> - DB 最小设计定稿（2026-10-19，8 表方案）：见 `.workbuddy/memory/2026-10-19.md` §DB 最小设计
> - 2026-10-28 架构审计与推流落地记录：见 `.workbuddy/memory/2026-10-28.md`

---

## P0 — Phase 1 收尾（阻塞「端到端可见」，但工作量小）

### [P0-1] 前端接通调度 API + SSE 推流
- **现状**：`apps/client/web-frontend/src/api/node/index.ts:11` 仍调用 **已删除** 的
  `POST /agent/execute`（`AgentTaskRequest` / `AgentTaskResponse` 来自旧 `@st-risk/shared-ts`，
  后端 `modules/agent` 已于 2026-10-28 拆除）；`apps/client/web-frontend/src/modules/agent/pages/AgentPage.vue`
  是纯占位（`<p>TODO: Agent 任务提交与结果展示</p>`）。
- **后端已具备**（无需改后端）：
  - `POST /api/v1/dispatch` → `202 + { planId, runId }`（`DispatchController.dispatch` → `PlannerOrchestrator.start`，非阻塞）
  - `GET /api/v1/dispatch/:runId/events` → SSE（先回放历史再实时流，run_end 自动关闭）
- **前端要做**：
  1. `nodeApi` 新增 `dispatch(intent)` 调 `POST /dispatch`、`streamEvents(runId)` 用 `EventSource('/api/v1/dispatch/${runId}/events')`。
  2. 废弃/删除 `executeAgentTask` 与 `@st-risk/shared-ts` 里的 `AgentTaskRequest/Response`（旧契约，已无后端对应）。
  3. `AgentPage.vue` 实现：输入框（objective + 可选 constraints/timeoutMs）→ `dispatch()` 拿 runId →
     打开 `EventSource` → `onmessage` 渲染事件时间线（run_start → agent_start/turn_* → tool_execution_* → run_end）。
- **验收**：浏览器提交一次火灾侦察意图，可在页面实时看到工具调用进度与终态（completed / failed + 拦截原因）。
- **注意**：前端是独立构建（不随 node-backend 编译），旧 `/agent/execute` 不会在后端编译期报错，但运行时必 404——属硬断点。

### [P0-2] 补 `allocations` 表 + `worker_executions.correlation_id` 列（已批准的最小 DB 变更）
- **现状**：DB 模型目录 `apps/server/node-backend/src/db/models/` 仍只有
  `uav / task / flight-log / plan / run / worker-execution / dispatch-event`；**无 `allocations` 表、无 `correlation_id` 列**。
  尚无任何 drizzle 迁移 SQL（`db:generate` 未跑）。
- **设计定稿**（2026-10-19，用户拍板：表不过多、不冗余）：
  - 新增唯一表 `allocations`：`unique (run_id, task_id)`，存「分配决策」这个唯一无家业务事实，
    给 validation 闸门在 DB 层兜底（详见 memory）。
  - `worker_executions` 补 `correlation_id` 列 = pi `toolCallId`，串联 pi 工具调用与落库记录。
  - 砍掉的 5 张提案表（llm_calls / risk_assessments / path_plans / obstacles / run_transcripts）**不建**，
    其数据分别由 turn_end usage、worker_executions.details、runs.payload 承接。
- **动作**：写 `db/models/allocation.ts` → 更新 `db/models/index.ts` 导出 →
  `pnpm db:generate` 出迁移 → `pnpm db:migrate`（需用户先起 PostgreSQL，见 [INF-1]）。
- **验收**：`drizzle-kit` 生成迁移文件；`allocations` 表存在且 `(run_id, task_id)` 唯一。

### [P0-3] 架构文档 §3 组件表「当前是否存在」列已过期，需更新
- **现状**：`docs/architecture/agent-architecture-node-landing.md:83-103` 的映射表里
  「Planner Orchestrator = 否（现 AgentService 占位）」「对外 API = 部分（现 agent.controller.ts）」
  已不成立；SSE 推流在 7.6 节仍标「可选」。
- **动作**：把上述两行改为「已落地（`orchestration/planner-orchestrator.ts` / `api/dispatch.controller.ts`）」，
  SSE 行改为「已落地（NestJS @Sse + RunEventBus，非阻塞 start + ReplaySubject 回放）」。
  同时第 36 行「缺 final_plans / allocations」更新为「allocations 已批准待建（见 P0-2）」。

---

## P1 — Phase 2 能力补全（Worker 1/5）

### [P1-1] 补齐 risk / route / resource / validation 四个 Worker
- **现状**：`registry/definitions/` 仅 `allocation.def.ts`（1/5）；`api/dispatch.module.ts:32`
  留 `// TODO Phase 2：注册 risk / route / resource / validation 能力`（useFactory 内仅 register allocation）。
- **动作**：每个能力 = 一个 `*.def.ts`（`capability` 串 + `WorkerRuntime` 实现）+ 在 `dispatch.module.ts`
  的 `useFactory` 里补一行 `registry.register(xxxWorkerDefinition(python))`。
  - `risk.assess`（风险评估）→ Python `/api/v1/risk/*`
  - `route.plan`（路径规划）→ Python `/api/v1/paths/plan`
  - `resource.query`（资源/无人机状态查询）
  - `validation.check`（确定性最终校验，可考虑复用 `orchestration/validation-gate.ts` 逻辑后移为 Worker）
- **注意**：因果定序（先 risk 后 allocation）当前建议由 Planner 分轮发起（架构文档 7.5），不必先建 DAG 组件。
- **验收**：`WorkerRouter.listCapabilities()` 返回 5 项；system-prompt 里的 capability 列表自动带出。

### [P1-2] 人工接管入口（pi `steer()` / `followUp()` 目前无 HTTP 出口）
- **现状**：四样兑底里的「人工接管」后端无入口；pi 提供 `steeringMode` / `followUpMode` 队列与
  `agent.steer()` / `agent.followUp()`，但 `DispatchController` 没有对应端点，run 终态后无法把人类决策喂回 Agent。
- **动作**：`DispatchController` 新增
  - `POST /dispatch/:runId/steer`（steeringMode 队列：覆盖工具调用/给方向）
  - `POST /dispatch/:runId/followUp`（followUpMode 队列：补充信息后继续）
  由 `PlannerOrchestrator` 把指令转交运行中的 `Agent` 实例（需先解决 Agent 实例按 runId 的引用持有，
  当前实例在 `runLoop` 闭包内，start() 非阻塞后需存一份 `Map<runId, Agent>` 供接管）。
- **验收**：run 在 executing/validating 状态可注入人类指令并影响下一轮决策；写入 dispatch_events 留痕。

---

## P2 — 治理 / 观测 / 编排增强

### [P2-1] pi-telemetry：LLM token / cost 计量
- **现状**：pi 有 telemetry 钩子，但全程未接入；LLM 用量只在 turn_end 事件 payload 里（设计约定），
  无统一归集、无成本看板。
- **动作**：在 `createPlannerModel` 装配处挂 telemetry，把每 turn 的 usage 落到 `worker_executions` 或专用统计；
  先内部计数，再做看板（避免过早建 llm_calls 表——已砍）。
- **验收**：一次 dispatch 可汇总 input/output token 与估算成本。

### [P2-2] Workflow Engine / Result Aggregator（因果定序 + 多 Agent 扇出）
- **现状**：完全由 Planner 分轮 `prompt` 自定序；无独立组件（架构文档确认「首版靠 LLM 轮次定序，少一个自研 DAG」）。
- **触发条件**：当任务需要明确并行扇出 / 跨 Agent 协作（如多 Planner 分区域）时再引入，切勿预建。
- **动作（届时）**：评估是把聚合放进 `PlannerOrchestrator` 还是独立 `workflow-engine` 模块；复用现有 `subscribe` 事件流。

### [P2-3] 转录/历史查询 API（runs.payload 与 dispatch_events 的可读出口）
- **现状**：转录快照写进 `runs.payload`、轮次/工具事件写 `dispatch_events`，但无「按 runId 回看全过程」的只读 API。
- **动作**：`GET /dispatch/:runId`（终态 + payload + 事件流回放）供前端详情页 / 调试用；可复用 `RunEventBus` 之外的 DB 回查。

---

## INF — 基础设施（用户环境相关，不阻塞代码层）

### [INF-1] 本地 PostgreSQL 启动 + 迁移
- **现状**：本机 Docker Desktop 未运行（用户明确不启动）；DB 落库验证留待用户自行跑。
- **动作（用户侧）**：`docker compose up -d postgres` → `pnpm db:migrate` → `pnpm dev`。
- **注意**：代码层已确保离线可跑（faux provider 测试 + 内存 repo 替身冒烟），无需 DB 即可验证闭环与 SSE。

### [INF-2] PostGIS geometry / pgvector 预留
- **现状**：`uavs / tasks` 等的空间字段、向量召回预留，未启用（无 `.sql`、无扩展迁移）。
- **触发条件**：真实地理围栏 / 语义检索需求出现时再开；当前用 jsonb 承载坐标足够。

---

## 已完成（备查，不要再列为待办）

- ✅ Phase 1 闭环（`planner-orchestrator.ts`：createPlannerModel→createPlannerAgent→prompt→subscribe 落库 +
  Run 硬超时 + validation 硬闸门），jest 51→59 全绿，真实 DeepSeek 冒烟通过（2026-10-19）。
- ✅ 拆除旧死代码 `modules/agent`（controller/service/module/repo/ dto），API 入口收敛为唯一 `DispatchModule`（2026-10-28）。
- ✅ SSE 推流：`RunEventBus`（ReplaySubject 回放 + 500 缓冲 + 60s 清理）+ `DispatchController.@Sse` +
  `PlannerOrchestrator.start()` 非阻塞 202 + 后端 2 个测试套件（run-event-bus.spec / planner-loop.faux SSE 用例）全绿（2026-10-28）。
- ✅ tsc 0 错误；eslint 0 错误（仅既有 no-console / no-explicit-any 警告）。
- ✅ DB 最小设计定稿：8 表（现有 7 + allocations），砍掉 5 张提案表（2026-10-19，用户拍板）。

---

## 优先级速查

| 编号 | 内容 | 优先级 | 阻塞面 | 工作量 |
|------|------|--------|--------|--------|
| P0-1 | 前端接通 dispatch + SSE | P0 | 端到端不可见 | 中 |
| P0-2 | allocations 表 + correlation_id | P0 | 业务事实无家 / 闸门 DB 兜底 | 小 |
| P0-3 | 架构文档 §3 过期更新 | P0 | 文档误导 | 小 |
| P1-1 | risk/route/resource/validation 四 Worker | P1 | 能力只 1/5 | 大 |
| P1-2 | 人工接管 steer/followUp 端点 | P1 | 兑底缺入口 | 中 |
| P2-1 | LLM token/cost 计量 | P2 | 无观测 | 中 |
| P2-2 | Workflow Engine / 聚合 | P2 | 并行/跨 Agent（暂无需求） | 大 |
| P2-3 | 历史/转录查询 API | P2 | 无回看 | 小 |
| INF-1 | 本地 PG 启动 + 迁移 | 环境 | DB 落库验证 | —（用户侧） |
| INF-2 | PostGIS / pgvector 预留 | 环境 | 空间/向量（暂无需求） | — |
