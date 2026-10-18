// Worker Registry — capability → WorkerDefinition 内存注册表（V1 静态注册，不做远程注册中心）。
// 注册时机：NestJS onModuleInit 装配（见 registry/definitions/*.ts）。

import type { WorkerDefinition } from '@/agents/core/worker-runtime.interface';

export class WorkerRegistry {
  private readonly byCapability = new Map<string, WorkerDefinition>();

  /** 注册能力定义。重复注册同 capability 直接抛错（配置错误要早暴露）。 */
  register(definition: WorkerDefinition): void {
    if (this.byCapability.has(definition.capability)) {
      throw new Error(`capability already registered: ${definition.capability}`);
    }
    this.byCapability.set(definition.capability, definition);
  }

  /** 按能力标识查定义；未注册返回 undefined（由 Router 决定报错）。 */
  resolve(capability: string): WorkerDefinition | undefined {
    return this.byCapability.get(capability);
  }

  /** 全部已注册能力（供 Planner 提示词能力清单 / 运维查看）。 */
  list(): WorkerDefinition[] {
    return [...this.byCapability.values()];
  }
}
