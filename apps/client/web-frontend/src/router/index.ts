// Vue Router — 基于 modules 结构

import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/shared/components/MainLayout.vue'),
      children: [
        { path: '', name: 'home', component: () => import('@/modules/home/pages/HomePage.vue') },
        { path: 'uavs', name: 'uavs', component: () => import('@/modules/uav/pages/UavListPage.vue') },
        { path: 'agent', name: 'agent', component: () => import('@/modules/agent/pages/AgentPage.vue') },
        { path: 'monitoring', name: 'monitoring', component: () => import('@/modules/monitoring/pages/MonitoringPage.vue') },
        { path: 'planning', name: 'planning', component: () => import('@/modules/planning/pages/PlanningPage.vue') },
      ],
    },
  ],
});

export default router;
