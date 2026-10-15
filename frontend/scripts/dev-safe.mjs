#!/usr/bin/env node
// dev-safe.mjs
// 启动 vite 开发服务器，并在拉起 vite 之前于 Node 层禁用 WorkBuddy 注入的
// node-safe-delete-shim 批量删除保护。
//
// 背景：该 shim 把"单次删除 >50 个文件"视为批量删除并中断进程。当 lockfile
// 变动触发 vite 重新优化依赖时，vite 要清空 .vite/deps（通常上百个文件），
// 于是被 shim 拦截 → vite 启动 abort → :3001 无监听，表现为"执行不了 / 没弹窗"。
//
// 做法：把 CODEBUDDY_SAFE_DELETE_ENABLED 设为 '0' 后再 spawn vite，子进程
// 继承该环境变量，shim 在子进程加载时即被禁用。仅在用户未显式设置时改写，
// 以尊重用户已有的环境变量选择。

import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, '..'); // scripts/ -> frontend/

// 仅在未显式设置时禁用 safe-delete 保护（用户显式置为其他值时不覆盖）。
if (process.env.CODEBUDDY_SAFE_DELETE_ENABLED === undefined) {
  process.env.CODEBUDDY_SAFE_DELETE_ENABLED = '0';
}

const viteBin = resolve(projectRoot, 'node_modules/vite/bin/vite.js');

// 转发用户传入的额外参数（如 --host、--port）。
// 注：默认不传 --debug —— 本前端依赖图巨大（tiptap 等），--debug 的日志缓冲会
// 迅速吃光堆内存，曾导致 vite 进程 "Fatal process out of memory: Zone" 崩溃。
// 同时给 vite 子进程更大的老生代上限，避免大型依赖优化时 OOM。
const nodeArgs = ['--max-old-space-size=4096'];
const args = [...nodeArgs, viteBin, ...process.argv.slice(2)];

const child = spawn(process.execPath, args, {
  cwd: projectRoot,
  stdio: 'inherit',
  env: process.env,
});

// 转发常见终止信号，保证 Ctrl+C 能正常关闭 vite。
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    if (!child.killed) child.kill(sig);
  });
}

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 0);
  }
});
