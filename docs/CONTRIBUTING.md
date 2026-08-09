# 协作指南 (Contributing Guide)

## 分支策略

采用 **GitHub Flow** 简化流程，适合中小团队快速迭代。

```
master (main) ──────────────────────────────────▶ 始终可部署
  │
  ├── feat/user-auth ────────────▶ 功能分支
  ├── feat/risk-model ───────────▶ 功能分支
  ├── fix/login-bug ─────────────▶ 修复分支
  └── docs/api-spec ─────────────▶ 文档分支
```

### 分支命名规范

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat/` | 新功能 | `feat/risk-calculation` |
| `fix/` | Bug 修复 | `fix/auth-token-expire` |
| `refactor/` | 重构 | `refactor/api-response-format` |
| `docs/` | 文档 | `docs/api-endpoints` |
| `chore/` | 构建/工具/依赖 | `chore/upgrade-fastapi` |
| `test/` | 测试补充 | `test/risk-model-unit` |

### 命名规则

```
<type>/<简短描述，用连字符分隔>
```

- 全小写，单词用 `-` 连接
- 描述不超过 5 个单词
- 示例：`feat/user-risk-score-api`

## 工作流程

### 1. 开始新功能

```bash
# 确保本地 master 最新
git checkout master
git pull origin master

# 创建功能分支
git checkout -b feat/my-feature

# 开发...
git add .
git commit -m "feat: add risk score calculation"
```

### 2. 提交规范 (Conventional Commits)

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Type 类型：**

| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 |
| `docs` | 文档 |
| `style` | 格式（不影响逻辑） |
| `refactor` | 重构 |
| `test` | 测试 |
| `chore` | 构建/工具变动 |

**Scope 范围（可选）：**

| scope | 对应模块 |
|-------|---------|
| `frontend` | apps/client/web-frontend |
| `python-api` | apps/server/python-fastapi-backend |
| `node-api` | apps/server/node-backend |
| `shared-ts` | packages/shared-ts |
| `shared-py` | packages/shared-py |
| `infra` | 基础设施 / CI / 部署 |

**示例：**

```
feat(python-api): add UAV trajectory risk endpoint
fix(frontend): correct map marker positioning
refactor(shared-ts): unify API response types
docs: update collaboration workflow
chore(infra): add Docker Compose for PostgreSQL
```

### 3. 推送与 PR

```bash
# 推送到远程
git push origin feat/my-feature

# 在 GitHub 上创建 Pull Request
```

**PR 标题格式**：与 commit message 格式一致

```
feat(python-api): add UAV trajectory risk endpoint
```

**PR 描述写清楚就行：**

```markdown
改了啥：xxx
影响范围：前端 / Python后端 / Node后端 / 共享包
关联 Issue：#123（如果有的话）
```

### 4. Code Review

- 小团队灵活处理：**自审通过即可合并**，重要改动 @队友 看一眼
- 使用 **Squash Merge** 保持 master 历史干净
- 合并后删除功能分支

### 5. 合并策略

```
功能分支 ──Squash Merge──▶ master
```

- 每个 PR 压缩为一条 commit 进入 master
- master 历史清晰，每个 commit 对应一个完整功能/修复

## 多人协作规则

### 模块分工

| 模块 | 主要负责人 |
|------|------------|
| apps/client/web-frontend | 前端 |
| apps/server/python-fastapi-backend | Python 后端 |
| apps/server/node-backend | Node 后端 |
| packages/shared-ts | 谁改谁负责 |
| packages/shared-py | 谁改谁负责 |
| docs / scripts | 全员 |

> **共享包改动前口头沟通一下就行**，不用走正式 Review 流程。

### 冲突预防

1. **Pull Before Push** — 每次开发前先 `git pull origin master`
2. **小步提交** — 避免一个 PR 改动过大，减少冲突概率
3. **及时合并** — PR 不要长时间挂着，尽快 Review 并合并
4. **模块隔离** — 各自负责的模块尽量不交叉修改

### 冲突解决

```bash
# 拉取最新 master
git fetch origin
git rebase origin/master

# 解决冲突后
git add .
git rebase --continue

# 强制推送更新 PR
git push --force-with-lease origin feat/my-feature
```

## 环境管理

### 本地开发

每人维护自己的本地环境，互不干扰：

```bash
# Python 环境 — uv 自动管理，无需手动创建 venv
uv sync

# Node 环境 — pnpm 自动管理
pnpm install
```

### 环境变量

- 使用 `.env` 文件管理本地配置（已在 `.gitignore` 中忽略）
- 提供 `.env.example` 作为模板
- **禁止提交任何密钥、Token、数据库密码**

```bash
# .env.example 示例
DATABASE_URL=postgresql://user:pass@localhost:5432/st_risk
PYTHON_API_PORT=8000
NODE_API_PORT=3000
```

## 数据库协作（PostgreSQL · 规划中）

- 使用 **migration 工具** 管理数据库结构变更（如 Alembic / Prisma / Drizzle）
- 每次 schema 变更必须提交 migration 文件
- 禁止直接手动改线上数据库结构
- 本地每人独立数据库实例，不共享

## 提交前检查清单

- [ ] 代码能跑（`pnpm dev` / `uv run`）
- [ ] 没把 `.env` 密钥啥的提交进去
- [ ] commit message 别太随意
- [ ] 改了共享包的话跟大家说一声
