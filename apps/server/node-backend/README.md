# ST-Risk UAV Service — Node.js NestJS Backend

Agent 服务，基于 NestJS 构建，负责编排业务流程并调用 Python 后端完成算法计算。

## 技术栈

- **语言**：TypeScript ≥ 5.7
- **框架**：NestJS 11
- **包管理**：pnpm（monorepo workspace）
- **数据校验**：Zod
- **数据库**：PostgreSQL + PostGIS（空间数据）+ pgvector（向量搜索）
- **ORM**：Drizzle ORM
- **测试**：Jest

## 快速开始

```bash
# 安装依赖（monorepo 根目录执行）
pnpm install

# 启动开发服务
pnpm --filter @st-risk/node-backend dev

# 构建
pnpm --filter @st-risk/node-backend build

# 运行测试
pnpm --filter @st-risk/node-backend test
```

服务默认运行在 http://localhost:3000，API 前缀 `/api/v1`。

## 架构

### 与 Python 后端的关系

```mermaid
graph LR
    FE[前端] -->|HTTP| NODE[Node NestJS]
    NODE -->|HTTP| PY[Python FastAPI]
    NODE -->|DB| DB[(PostgreSQL)]

    subgraph Node 后端
        NODE
    end

    subgraph Python 后端
        PY
    end

    NODE -.->|共享类型| SHARED[shared-ts]
    FE -.->|共享类型| SHARED
```

- **Node 端**：Agent 编排、业务流程、数据持久化
- **Python 端**：算法计算（路径规划、任务分配、风险评估）
- **shared-ts**：前后端共享的类型定义和工具函数

### 分层总览

```mermaid
graph TB
    subgraph modules["modules/ (功能模块)"]
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
├── main.ts                          # NestJS 启动入口
│
├── app/                             # 应用层
│   └── app.module.ts                #   根模块
│
├── shared/                          # 横切关注点
│   └── pipes/
│       └── zod.pipe.ts              #   Zod 校验管道
│
├── clients/                         # 外部服务客户端
│   └── python-backend/
│       └── client.ts                #   调用 Python FastAPI
│
├── db/                              # 数据库层（Drizzle ORM）
│   ├── engine.ts                    #   数据库实例
│   └── models/                      #   ORM 模型
│       ├── uav.ts
│       └── task.ts
│
└── modules/                         # 功能模块（内聚）
    ├── common/                      #   公共模块
    │   ├── common.module.ts
    │   └── common.controller.ts     #     GET /health
    └── agent/                       #   Agent 模块
        ├── agent.module.ts
        ├── agent.controller.ts      #     POST /agent/execute
        ├── agent.service.ts         #     编排逻辑
        ├── dto/                     #     Zod 校验
        │   └── agent-task.dto.ts
        └── repositories/            #     数据访问
            └── agent.repo.ts
```

### 各层职责

| 层 | 目录 | 职责 |
|---|------|------|
| 模块 | `modules/` | 功能内聚：controller + service + repository + dto |
| 共享 | `shared/` | 横切关注点：pipes、guards、interceptors、filters |
| 客户端 | `clients/` | 调用外部服务（Python 后端） |
| 数据库 | `db/` | Drizzle ORM 引擎 + 模型 |
| 共享包 | `packages/shared-ts` | 前后端共享类型、枚举、工具 |

### 模块内聚原则

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

- `controller.ts` — 路由 + HTTP 处理
- `service.ts` — 业务编排
- `dto/` — Zod 请求校验
- `repositories/` — 数据访问

新增功能模块时，只需在 `modules/` 下创建新目录，包含上述四个文件即可。

## 开发新接口

以「无人机管理」模块为例，演示从零开发一个新模块的完整流程。

### 流程总览

```mermaid
flowchart TD
    A[1. 定义共享类型] --> B[2. 创建 DTO]
    B --> C[3. 实现 Repository]
    C --> D[4. 实现 Service]
    D --> E[5. 编写 Controller]
    E --> F[6. 注册 Module]
    F --> G[7. 测试验证]

    style A fill:#e1f5fe
    style B fill:#e1f5fe
    style C fill:#fff3e0
    style D fill:#fff3e0
    style E fill:#e8f5e9
    style F fill:#e8f5e9
    style G fill:#fce4ec
```

### 请求流转

```mermaid
sequenceDiagram
    participant Client
    participant Controller as controller.ts
    participant Pipe as Zod Pipe
    participant Service as service.ts
    participant Repo as repository.ts
    participant DB as PostgreSQL
    participant PyBackend as Python 后端

    Client->>Controller: POST /api/v1/uavs
    Controller->>Pipe: 校验请求体 (Zod)
    Pipe-->>Controller: 校验通过
    Controller->>Service: createUav(dto)
    Service->>Repo: save(uav)
    Repo->>DB: INSERT
    DB-->>Repo: 结果
    Repo-->>Service: UAV
    Service-->>Controller: UAV
    Controller-->>Client: 201 Created
```

### Step 1 — 定义共享类型

在 `packages/shared-ts/src/domain/models.ts` 中添加接口（如前后端都需要）：

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

在模块目录下创建 Zod 校验 schema：

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
import type { UAV } from '@st-risk/shared-ts';

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
import type { UAV } from '@st-risk/shared-ts';

@Injectable()
export class UavService {
  constructor(
    private readonly repo: UavRepository,
    private readonly pythonClient: PythonBackendClient,  // 按需调用 Python 端
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
  async create(@Body(new ZodValidationPipe(CreateUavDto)) body: Record<string, unknown>) {
    return this.uavService.createUav(body as CreateUavInput);
  }
}
```

### Step 6 — 注册 Module

```typescript
// src/modules/uav/uav.module.ts
import { Module } from '@nestjs/common';
import { UavController } from './uav.controller';
import { UavService } from './uav.service';
import { UavRepository } from './repositories/uav.repo';

@Module({
  controllers: [UavController],
  providers: [UavService, UavRepository],
  exports: [UavService],
})
export class UavModule {}
```

然后在 `app.module.ts` 中注册：

```typescript
// src/app/app.module.ts
import { UavModule } from '@/modules/uav/uav.module';

@Module({
  imports: [CommonModule, AgentModule, UavModule],  // ← 加上
  ...
})
export class AppModule {}
```

### Step 7 — 测试验证

```bash
# 启动开发服务
pnpm --filter @st-risk/node-backend dev

# 访问 Swagger 文档
open http://localhost:3000/api/docs
```

### 涉及文件清单

```mermaid
graph LR
    subgraph 新增/修改
        A[shared-ts/domain/models.ts]
        B[modules/uav/dto/create-uav.dto.ts]
        C[modules/uav/repositories/uav.repo.ts]
        D[modules/uav/uav.service.ts]
        E[modules/uav/uav.controller.ts]
        F[modules/uav/uav.module.ts]
        G[app/app.module.ts]
    end

    A -->|被引用| B
    A -->|被引用| C
    A -->|被引用| D
    B -->|被引用| E
    C -->|被引用| D
    D -->|被引用| E
    F -->|被注册| G

    style A fill:#e1f5fe
    style B fill:#fff3e0
    style C fill:#fff3e0
    style D fill:#fff3e0
    style E fill:#e8f5e9
    style F fill:#e8f5e9
    style G fill:#fce4ec
```

| 步骤 | 文件 | 动作 |
|------|------|------|
| 1 | `packages/shared-ts/src/domain/models.ts` | 修改 — 添加接口 |
| 2 | `modules/uav/dto/create-uav.dto.ts` | 新增 — Zod 校验 |
| 3 | `modules/uav/repositories/uav.repo.ts` | 新增 — 数据访问 |
| 4 | `modules/uav/uav.service.ts` | 新增 — 业务逻辑 |
| 5 | `modules/uav/uav.controller.ts` | 新增 — 路由处理器 |
| 6 | `modules/uav/uav.module.ts` | 新增 — 模块注册 |
| 7 | `app/app.module.ts` | 修改 — 导入新模块 |

---

## 共享类型

通过 `@st-risk/shared-ts` 包实现前后端类型共享：

```typescript
// 前端和 Node 后端使用同一套类型
import { UAV, UAVStatus, AllocateRequest } from '@st-risk/shared-ts';
```

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

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `3000` | 服务端口 |
| `PYTHON_BACKEND_URL` | `http://localhost:8000` | Python 后端地址 |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/st_risk` | PostgreSQL 连接 |

## 依赖

### 运行时

- @nestjs/common, @nestjs/core, @nestjs/platform-express
- @st-risk/shared-ts（workspace 内部包）
- drizzle-orm + postgres (PostgreSQL 驱动)
- PostGIS（空间数据）+ pgvector（向量搜索）
- zod
- rxjs, reflect-metadata

### 开发

- @nestjs/cli, @nestjs/testing
- drizzle-kit
- jest, ts-jest
- typescript
