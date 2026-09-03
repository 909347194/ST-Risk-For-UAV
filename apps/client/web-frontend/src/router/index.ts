// Vue Router

import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', name: 'home', component: () => import('@/pages/HomePage.vue') },
        { path: 'uavs', name: 'uavs', component: () => import('@/pages/UavListPage.vue') },
        { path: 'monitoring', name: 'monitoring', component: () => import('@/pages/MonitoringPage.vue') },
        { path: 'planning', name: 'planning', component: () => import('@/pages/PlanningPage.vue') },
      ],
    },
  ],
});

export default router;
