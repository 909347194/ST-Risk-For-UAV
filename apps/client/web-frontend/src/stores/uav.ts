// Pinia Store — 无人机状态管理

import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { UAV } from '@st-risk/shared-ts';
import { nodeApi } from '@/api';

export const useUavStore = defineStore('uav', () => {
  const uavs = ref<UAV[]>([]);
  const loading = ref(false);

  async function fetchUavs(status?: string) {
    loading.value = true;
    try {
      uavs.value = await nodeApi.listUavs(status);
    } finally {
      loading.value = false;
    }
  }

  async function createUav(data: Parameters<typeof nodeApi.createUav>[0]) {
    const result = await nodeApi.createUav(data);
    uavs.value.push(result.uav);
    return result;
  }

  return { uavs, loading, fetchUavs, createUav };
});
