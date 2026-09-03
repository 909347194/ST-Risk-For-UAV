// NestJS 启动入口

import { NestFactory } from '@nestjs/core';
import { AppModule } from './app';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.setGlobalPrefix('api/v1');
  const port = process.env.PORT || 3000;
  await app.listen(port);
  console.log(`Node backend running on http://localhost:${port}`);
}
bootstrap();
