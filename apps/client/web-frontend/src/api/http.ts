// Axios 实例工厂 — 按后端创建独立实例

import axios from 'axios';
import type { AxiosInstance } from 'axios';

export function createHttpClient(baseURL: string, timeout = 10000): AxiosInstance {
  return axios.create({ baseURL, timeout });
}
