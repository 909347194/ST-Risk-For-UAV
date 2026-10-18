// 调度意图 DTO（zod）— 对外 API 边界校验（ZodValidationPipe），不用于 AgentTool 参数。

import { z } from 'zod';

export const dispatchIntentSchema = z.object({
  /** 调度意图（人类语言，如"XX 区域火灾侦察"）。 */
  objective: z.string().min(1),
  /** 约束（时间窗/区域/资源限制等）。 */
  constraints: z.record(z.unknown()).optional(),
});

export type DispatchIntentDto = z.infer<typeof dispatchIntentSchema>;
