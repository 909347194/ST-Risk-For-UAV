// Agent Controller

import { Controller, Post, Body } from '@nestjs/common';
import { ZodValidationPipe } from '@/shared';
import { AgentService } from './agent.service';
import { AgentTaskDto } from './dto/agent-task.dto';

@Controller('agent')
export class AgentController {
  constructor(private readonly agentService: AgentService) {}

  @Post('execute')
  async executeTask(@Body(new ZodValidationPipe(AgentTaskDto)) body: Record<string, unknown>) {
    return this.agentService.executeTask(body.uavId as string, body.taskId as string, body.instruction as string);
  }
}
