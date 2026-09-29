// NestJS 启动入口 — 优雅启动 / 退出

import * as readline from "readline";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app";

// ── 控制台输出工具 ──────────────────────────────────────────────
const BANNER = `
 ╔══════════════════════════════════════════╗
 ║     ST-Risk UAV — Node Backend           ║
 ╚══════════════════════════════════════════╝
`;

function printInfo(port: number | string) {
    // 使用 ASCII 兼容字符，避免 Windows cmd 中文乱码
    console.log(BANNER);
    console.log(`  [*] Service  : Node (NestJS)`);
    console.log(`  [*] Port     : ${port}`);
    console.log(`  [*] API      : http://localhost:${port}/api/v1`);
    console.log(`  [*] Env      : ${process.env.NODE_ENV || "development"}`);
    console.log(`  [*] PID      : ${process.pid}`);
    console.log();
    console.log("  [OK] Server is ready. Press Ctrl+C to stop.");
    console.log();
}

function printShutdown(signal: string) {
    console.log();
    console.log(`  [!] Received ${signal}. Shutting down gracefully...`);
}

// ── Bootstrap ──────────────────────────────────────────────────
async function bootstrap() {
    // 确保 stdout 使用 UTF-8（Windows 兼容）
    if (process.stdout.setDefaultEncoding) {
        process.stdout.setDefaultEncoding("utf-8");
    }

    const app = await NestFactory.create(AppModule, {
        logger: ["log", "error", "warn"],
    });

    app.setGlobalPrefix("api/v1");

    // 启用 CORS
    app.enableCors();

    const port = process.env.PORT || process.env.NODE_API_PORT || 3000;

    await app.listen(port as number);

    printInfo(port);

    // ── 优雅退出 ────────────────────────────────────────────────
    let shuttingDown = false;

    const gracefulShutdown = async (signal: string) => {
        if (shuttingDown) return;
        shuttingDown = true;

        printShutdown(signal);

        try {
            await app.close();
            console.log("  [OK] Server stopped cleanly.");
            process.exit(0);
        } catch (err) {
            console.error("  [ERR] Error during shutdown:", err);
            process.exit(1);
        }
    };

    process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
    process.on("SIGINT", () => gracefulShutdown("SIGINT"));

    // Windows: Ctrl+C 在某些终端发 SIGINT，某些发不到，补一个 readline 兜底
    if (process.platform === "win32") {
        const rl = readline.createInterface({ input: process.stdin });
        rl.on("SIGINT", () => gracefulShutdown("SIGINT"));
    }
}

bootstrap().catch((err) => {
    console.error("  [FATAL] Failed to start server:", err);
    process.exit(1);
});
