// Zod 校验管道 — 通用

import { PipeTransform, BadRequestException } from '@nestjs/common';
import { ZodSchema } from 'zod';

export class ZodValidationPipe implements PipeTransform {
  constructor(private schema: ZodSchema) {}

  transform(value: unknown) {
    const result = this.schema.safeParse(value);
    if (!result.success) {
      throw new BadRequestException({
        message: '参数校验失败',
        errors: result.error.flatten().fieldErrors,
      });
    }
    return result.data;
  }
}
