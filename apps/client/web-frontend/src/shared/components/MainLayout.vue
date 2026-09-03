// 主布局 — shared 组件，被所有模块共用

<template>
  <div class="layout">
    <nav class="sidebar">
      <RouterLink to="/">首页</RouterLink>
      <RouterLink to="/uavs">无人机管理</RouterLink>
      <RouterLink to="/agent">Agent</RouterLink>
      <RouterLink to="/monitoring">飞行监控</RouterLink>
      <RouterLink to="/planning">航线规划</RouterLink>
    </nav>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
