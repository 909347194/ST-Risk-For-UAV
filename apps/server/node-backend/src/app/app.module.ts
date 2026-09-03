// 应用根模块

import { Module } from '@nestjs/common';
import { AgentModule, CommonModule } from '@/modules';
import { PythonBackendClient } from '@/clients';

@Module({
  imports: [CommonModule, AgentModule],
  providers: [
    {
      provide: PythonBackendClient,
      useFactory: () =>
        new PythonBackendClient({
          baseUrl: process.env.PYTHON_BACKEND_URL,
        }),
    },
  ],
  exports: [PythonBackendClient],
})
export class AppModule {}
