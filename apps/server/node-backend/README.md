# ST-Risk UAV — Node.js NestJS Backend

Agent 服务，负责编排业务流程、数据持久化，并调用 Python 后端完成算法计算。

## 技术栈

| 项 | 技术 |
|---|------|
| 语言 | TypeScript ≥ 5.7 |
| 框架 | NestJS 11 |
| 数据校验 | Zod |
| ORM | Drizzle ORM |
| 数据库 | PostgreSQL + PostGIS + pgvector |
| 测试 | Jest |
| 包管理 | pnpm（monorepo workspace） |

## 快速开始

```bash
# 安装依赖（monorepo 根目录执行）
pnpm install

# 启动开发服务
pnpm run dev:node

# 构建
pnpm run build:node

# Lint
pnpm run lint:node

# 测试
pnpm run test:node

# 数据库迁移
pnpm run db:generate   # 生成迁移
pnpm run db:migrate    # 执行迁移
```

服务默认运行在 http://localhost:3000，API 前缀 `/api/v1`。

## 架构

### 请求流转

```mermaid
sequenceDiagram
    participant Client
    participant Controller as controller
    participant Pipe as Zod Pipe
    participant Service as service
    participant Repo as repository
    participant DB as PostgreSQL
    participant Py as Python 后端

    Client->>Controller: POST /api/v1/agent/execute
    Controller->>Pipe: 校验请求体 (Zod)
    Pipe-->>Controller: 通过
    Controller->>Service: executeTask(uavId, taskId, instruction)
    Service->>Repo: 查询/持久化
    Repo->>DB: SQL
    DB-->>Repo: 结果
    Service->>Py: 调用算法 (HTTP)
    Py-->>Service: 算法结果
    Service-->>Controller: 返回结果
    Controller-->>Client: JSON
```

### 分层总览

```mermaid
graph TB
    subgraph modules["modules/ — 功能模块"]
        M1[agent]
        M2[common]
    end

    subgraph layer["每个模块内聚"]
        C[controller] --> S[service]
        S --> R[repository]
        S -->|调用| CL[clients/]
        C -.->|校验| D[dto/ + Zod]
    end

    subgraph infra["基础设施"]
        CL -->|HTTP| PY[Python FastAPI]
        DB[db/ + Drizzle] --> R
        SHARED[shared-ts] -.->|类型| S
        SHARED -.->|类型| D
    end

    style modules fill:#e3f2fd
    style infra fill:#f3e5f5
```

### 目录结构

```
src/
├── main.ts                            # 启动入口（优雅启动/退出）
│
├── app/
│   ├── app.module.ts                  #   根模块
│   └── index.ts
│
├── shared/                            # 横切关注点
│   ├── pipes/
│   │   └── zod.pipe.ts               #   Zod 校验管道
│   └── index.ts
│
├── clients/                           # 外部服务客户端
│   ├── python-backend/
│   │   └── client.ts                  #   Python FastAPI HTTP 客户端
│   └── index.ts
│
├── db/                                # 数据库层（Drizzle ORM）
│   ├── engine.ts                      #   数据库实例
│   ├── index.ts
│   └── models/
│       ├── uav.ts                     #   UAV 表
│       ├── task.ts                    #   Task 表
│       ├── flight-log.ts             #   飞行轨迹表
│       └── index.ts
│
└── modules/                           # 功能模块（内聚）
    ├── common/
    │   ├── common.module.ts
    │   └── common.controller.ts       #   GET /health
    └── agent/
        ├── agent.module.ts
        ├── agent.controller.ts        #   POST /agent/execute
        ├── agent.service.ts           #   编排逻辑
        ├── dto/
        │   └── agent-task.dto.ts      #   Zod 校验
        └── repositories/
            └── agent.repo.ts
```

### 各层职责

| 层 | 目录 | 职责 |
|---|------|------|
| 模块 | `modules/` | 功能内聚：controller + service + repository + dto |
| 共享 | `shared/` | 横切关注点：pipes、guards、interceptors |
| 客户端 | `clients/` | 调用外部服务（Python 后端） |
| 数据库 | `db/` | Drizzle ORM 引擎 + 模型 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/agent/execute` | 执行 Agent 任务 |

### PythonBackendClient 方法

| 方法 | 说明 |
|------|------|
| `get<T>(path)` | 通用 GET 请求 |
| `post<T>(path, body)` | 通用 POST 请求 |
| `planPath(params)` | 调用航线规划 |
| `allocateTasks(params)` | 调用任务分配 |
| `assessRisk(params)` | 调用风险评估 |
| `evaluateAdaptability(params)` | 调用适配评估 |

## ORM 模型

```mermaid
erDiagram
    uavs {
        text id PK
        geometry position "POINT (PostGIS)"
        real speed
        real max_payload
        real battery
        text status
    }
    tasks {
        text id PK
        geometry position "POINT (PostGIS)"
        text priority
        real payload_weight
        integer time_limit
        text status
    }
    flight_logs {
        text id PK
        text uav_id FK
        geometry track "LINESTRING (PostGIS)"
        vector embedding "pgvector 128维"
        timestamp start_time
        timestamp end_time
        real total_distance
    }
```

## 模块内聚原则

每个功能模块内部包含完整的请求处理链：

```mermaid
graph LR
    subgraph modules/agent/
        C[controller.ts] -->|调用| S[service.ts]
        S -->|读写| R[repositories/]
        C -.->|校验| D[dto/]
    end

    S -->|调用| CL[clients/]
    R -->|使用| DB[db/]

    style modules/agent/ fill:#e8f5e9
```

新增功能模块时，在 `modules/` 下创建目录，包含 controller + service + dto + repositories 四个文件，然后在 `app.module.ts` 注册即可。

## 开发新接口

以「无人机管理」模块为例。

### 流程

```mermaid
flowchart TD
    A[1. 定义共享类型] --> B[2. 创建 DTO]
    B --> C[3. 实现 Repository]
    C --> D[4. 实现 Service]
    D --> E[5. 编写 Controller]
    E --> F[6. 注册 Module]
    F --> G[7. 测试验证]

    style A fill:#e1f5fe
    style B fill:#fff3e0
    style C fill:#fff3e0
    style D fill:#fff3e0
    style E fill:#e8f5e9
    style F fill:#e8f5e9
    style G fill:#fce4ec
```

### Step 1 — 定义共享类型

```typescript
// packages/shared-ts/src/domain/models.ts
export interface UAV {
  id: string;
  position: Position;
  speed: number;
  maxPayload: number;
  battery: number;
  status: UAVStatus;
}
```

### Step 2 — 创建 DTO

```typescript
// src/modules/uav/dto/create-uav.dto.ts
import { z } from 'zod';

export const CreateUavDto = z.object({
  id: z.string(),
  x: z.number(),
  y: z.number(),
  z: z.number().default(0),
  speed: z.number().positive(),
  maxPayload: z.number().nonnegative(),
  battery: z.number().positive(),
});

export type CreateUavInput = z.infer<typeof CreateUavDto>;
```

### Step 3 — 实现 Repository

```typescript
// src/modules/uav/repositories/uav.repo.ts
import { Injectable } from '@nestjs/common';
import { db } from '@/db';
import { uavs } from '@/db/models';

@Injectable()
export class UavRepository {
  async save(uav: UAV): Promise<UAV> {
    await db.insert(uavs).values(uav);
    return uav;
  }
  async findById(id: string): Promise<UAV | null> {
    const result = await db.select().from(uavs).where(eq(uavs.id, id));
    return result[0] ?? null;
  }
}
```

### Step 4 — 实现 Service

```typescript
// src/modules/uav/uav.service.ts
import { Injectable } from '@nestjs/common';
import { PythonBackendClient } from '@/clients';
import { UavRepository } from './repositories/uav.repo';

@Injectable()
export class UavService {
  constructor(
    private readonly repo: UavRepository,
    private readonly pythonClient: PythonBackendClient,
  ) {}

  async createUav(data: CreateUavInput): Promise<UAV> {
    const uav: UAV = { ...data, status: UAVStatus.IDLE };
    return this.repo.save(uav);
  }
}
```

### Step 5 — 编写 Controller

```typescript
// src/modules/uav/uav.controller.ts
import { Controller, Post, Body } from '@nestjs/common';
import { ZodValidationPipe } from '@/shared';
import { UavService } from './uav.service';
import { CreateUavDto } from './dto/create-uav.dto';

@Controller('uavs')
export class UavController {
  constructor(private readonly uavService: UavService) {}

  @Post()
  async create(@Body(new ZodValidationPipe(CreateUavDto)) body: CreateUavInput) {
    return this.uavService.createUav(body);
  }
}
```

### Step 6 — 注册 Module

```typescript
// src/modules/uav/uav.module.ts
@Module({
  controllers: [UavController],
  providers: [UavService, UavRepository],
  exports: [UavService],
})
export class UavModule {}

// src/app/app.module.ts — 加入 imports
@Module({
  imports: [CommonModule, AgentModule, UavModule],
})
export class AppModule {}
```

### 涉及文件

| 步骤 | 文件 | 动作 |
|------|------|------|
| 1 | `packages/shared-ts/src/domain/models.ts` | 修改 — 添加接口 |
| 2 | `modules/uav/dto/create-uav.dto.ts` | 新增 — Zod 校验 |
| 3 | `modules/uav/repositories/uav.repo.ts` | 新增 — 数据访问 |
| 4 | `modules/uav/uav.service.ts` | 新增 — 业务逻辑 |
| 5 | `modules/uav/uav.controller.ts` | 新增 — 路由 |
| 6 | `modules/uav/uav.module.ts` | 新增 — 模块注册 |
| 7 | `app/app.module.ts` | 修改 — 导入新模块 |

---

## 共享类型

通过 `@st-risk/shared-ts` 包实现前后端类型共享：

```mermaid
graph LR
    subgraph shared-ts
        E[enums/] --- D[domain/]
        D --- A[api/]
        A --- U[utils/]
    end

    FE[前端] -->|import| shared-ts
    NODE[Node 后端] -->|import| shared-ts
    PY[Python 后端] -.->|对应| D
```

```typescript
import { UAV, UAVStatus, Task, TaskPriority } from '@st-risk/shared-ts';
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `3000` | 服务端口 |
| `NODE_API_PORT` | `3000` | 备选端口变量 |
| `PYTHON_BACKEND_URL` | `http://localhost:8000` | Python 后端地址 |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/st_risk` | PostgreSQL 连接 |

## 依赖

### 运行时

- @nestjs/common, @nestjs/core, @nestjs/platform-express
- @st-risk/shared-ts（workspace 内部包）
- drizzle-orm + postgres
- zod, rxjs, reflect-metadata

### 开发

- @nestjs/cli, @nestjs/testing
- drizzle-kit
- jest, ts-jest
- eslint, @eslint/js, typescript-eslint
- typescript
