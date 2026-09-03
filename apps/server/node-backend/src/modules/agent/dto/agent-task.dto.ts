// Agent DTO — Zod 校验

import { z } from 'zod';

export const AgentTaskDto = z.object({
  uavId: z.string(),
  taskId: z.string(),
  instruction: z.string(),
  params: z.record(z.unknown()).optional(),
});

export type AgentTaskInput = z.infer<typeof AgentTaskDto>;
