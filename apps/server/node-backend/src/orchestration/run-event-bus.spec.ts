// RunEventBus 单元测试 — SSE 推流总线语义（回放/实时/终态关闭/多订阅者）。

import { firstValueFrom } from 'rxjs';
import { take, toArray } from 'rxjs/operators';

import { RunEventBus } from '@/orchestration/run-event-bus';
import type { RunStreamEvent } from '@/orchestration/run-event-bus';

/** 收集流上的全部事件直到 complete。 */
function collect(bus: RunEventBus, runId: string): Promise<RunStreamEvent[]> {
  return new Promise((resolve) => {
    const events: RunStreamEvent[] = [];
    bus.stream(runId).subscribe({
      next: (event) => events.push(event),
      complete: () => resolve(events),
    });
  });
}

describe('RunEventBus', () => {
  it('订阅前的历史事件会回放（前端晚到也能看全程）', async () => {
    const bus = new RunEventBus();
    bus.publish('r1', { type: 'run_start', data: { planId: 'p1' } });
    bus.publish('r1', { type: 'agent_start' });

    // 未终态的流不关闭，取前 2 条验证回放（toArray 把 take(2) 的两值收成数组）
    const events = await firstValueFrom(bus.stream('r1').pipe(take(2), toArray()));
    expect(events).toHaveLength(2);
    expect(events[0].type).toBe('run_start');
    expect(events[0].data).toEqual({ planId: 'p1' });
    expect(events[1].type).toBe('agent_start');
  });

  it('run_end 后流自动关闭，且迟到的订阅者只拿到回放', async () => {
    const bus = new RunEventBus();
    bus.publish('r1', { type: 'run_start' });
    bus.publish('r1', { type: 'run_end', data: { status: 'completed' } });

    const events = await collect(bus, 'r1');
    expect(events.map((e) => e.type)).toEqual(['run_start', 'run_end']);
    expect(events[1].data).toEqual({ status: 'completed' });
    expect(events[0].runId).toBe('r1');
    expect(events[0].timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it('先订阅后发布：实时事件按序到达，run_end 关闭', async () => {
    const bus = new RunEventBus();
    const received = collect(bus, 'r1');

    bus.publish('r1', { type: 'run_start' });
    bus.publish('r1', { type: 'tool_execution_start', data: { toolName: 'assign_tasks' } });
    bus.publish('r1', { type: 'run_end', data: { status: 'completed' } });

    const events = await received;
    expect(events.map((e) => e.type)).toEqual(['run_start', 'tool_execution_start', 'run_end']);
  });

  it('运行中订阅：先回放历史再接实时', async () => {
    const bus = new RunEventBus();
    bus.publish('r1', { type: 'run_start' });

    const received = collect(bus, 'r1');
    bus.publish('r1', { type: 'turn_start' });
    bus.publish('r1', { type: 'run_end' });

    const events = await received;
    expect(events.map((e) => e.type)).toEqual(['run_start', 'turn_start', 'run_end']);
  });

  it('多订阅者（多浏览器标签）互不影响，都能收到实时事件', async () => {
    const bus = new RunEventBus();
    const a = collect(bus, 'r1');
    const b = collect(bus, 'r1');

    bus.publish('r1', { type: 'run_start' });
    bus.publish('r1', { type: 'run_end' });

    const [eventsA, eventsB] = await Promise.all([a, b]);
    expect(eventsA.map((e) => e.type)).toEqual(['run_start', 'run_end']);
    expect(eventsB.map((e) => e.type)).toEqual(['run_start', 'run_end']);
  });

  it('事件载荷透传：data 原样到达（缺省不带 data 字段）', async () => {
    const bus = new RunEventBus();
    const received = collect(bus, 'r1');

    bus.publish('r1', { type: 'turn_start' });
    bus.publish('r1', { type: 'tool_execution_end', data: { toolName: 'assign_tasks', isError: false } });
    bus.publish('r1', { type: 'run_end', data: { status: 'completed' } });

    const events = await received;
    expect(events[0]).not.toHaveProperty('data');
    expect(events[1].data).toEqual({ toolName: 'assign_tasks', isError: false });
  });
});
