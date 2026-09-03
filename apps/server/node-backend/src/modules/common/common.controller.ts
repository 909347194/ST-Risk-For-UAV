// Common Controller

import { Controller, Get } from '@nestjs/common';

@Controller()
export class CommonController {
  @Get('health')
  health() {
    return { status: 'ok' };
  }
}
