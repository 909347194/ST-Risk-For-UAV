// modules — 业务模块（内聚：pages + components + composables + stores）
//
// 规则：
// - modules 之间禁止互相引用
// - modules 可以引用 api、shared、shared/stores
// - 每个模块通过 composables 调用 api，严禁直接使用 Axios

export * as home from './home';
export * as uav from './uav';
export * as agent from './agent';
export * as monitoring from './monitoring';
export * as planning from './planning';
