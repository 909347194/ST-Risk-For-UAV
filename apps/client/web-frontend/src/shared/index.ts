// shared — 跨模块共享（准入标准：被 2+ 个 modules 引用）
//
// 规则：
// - shared 不能引用 modules 或 api（保持纯净）
// - 只有被多个模块复用的组件/逻辑才放这里
// - 业务组件永远留在 modules 内部

export * from './components';
export * from './composables';
export * from './stores';
