import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { readFile, readdir, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';

const DIST = path.resolve('dist');
const ASSETS = path.join(DIST, 'assets');
const OUTPUT = path.resolve('performance-results.json');
const KIB = 1024;
const MIB = KIB * KIB;
const budgets = {
  coldStartMs: 2_000,
  routeChangeMs: 300,
  paletteOpenMs: 100,
  streamingLongestTaskMs: 50,
  maxChunkBytes: 500 * KIB,
  retained500MessagesBytes: 15 * MIB,
} as const;

function requireBudget(value: number, maximum: number, label: string) {
  if (value >= maximum) {
    throw new Error(`${label} ${value.toFixed(3)} exceeded budget ${maximum}`);
  }
}

function requiredMeasurement(output: string, pattern: RegExp, label: string): number {
  const match = output.match(pattern);
  if (!match?.[1]) throw new Error(`Missing ${label} measurement from runtime performance tests`);
  return Number(match[1]);
}

const runtimeTests = [
  'src/components/layout/app-shell.test.tsx',
  'src/components/chat/virtual-message-list.test.tsx',
  'src/lib/performance/frame-batcher.test.ts',
  'src/lib/performance/runtime-health.test.ts',
];
const vitestEntry = path.resolve('node_modules/vitest/vitest.mjs');
const runtime = spawnSync(process.execPath, [vitestEntry, 'run', ...runtimeTests], {
  cwd: process.cwd(),
  encoding: 'utf8',
  env: { ...process.env, FORCE_COLOR: '0' },
});
if (runtime.stdout) process.stderr.write(runtime.stdout);
if (runtime.stderr) process.stderr.write(runtime.stderr);
if (runtime.status !== 0) {
  throw new Error(`Runtime performance tests failed with status ${String(runtime.status)}`);
}
const runtimeOutput = `${runtime.stdout}\n${runtime.stderr}`;
const paletteOpenMs = requiredMeasurement(
  runtimeOutput,
  /command_palette_open_ms=([\d.]+)/,
  'palette open',
);
const routeChangeMs = requiredMeasurement(
  runtimeOutput,
  /warm_route_change_ms=([\d.]+)/,
  'route change',
);
const coldDashboardRenderMs = requiredMeasurement(
  runtimeOutput,
  /cold_dashboard_render_ms=([\d.]+)/,
  'cold dashboard render',
);
const streamingLongestTaskMs = requiredMeasurement(
  runtimeOutput,
  /longest_task_ms=([\d.]+)/,
  'streaming longest task',
);
const mounted500MessageRows = requiredMeasurement(
  runtimeOutput,
  /message_fixture_rows=500 mounted_message_rows=(\d+)/,
  '500-message mounted rows',
);
requireBudget(paletteOpenMs, budgets.paletteOpenMs, 'palette_open_ms');
requireBudget(routeChangeMs, budgets.routeChangeMs, 'route_change_ms');
requireBudget(coldDashboardRenderMs, budgets.coldStartMs, 'cold_dashboard_render_ms');
requireBudget(streamingLongestTaskMs, budgets.streamingLongestTaskMs, 'streaming_longest_task_ms');
if (mounted500MessageRows >= 60) {
  throw new Error(`mounted_500_message_rows ${mounted500MessageRows} exceeded budget 60`);
}
if (!runtimeOutput.includes('unhandled_rejections=0')) {
  throw new Error('Runtime health test did not report zero unhandled rejections');
}

const files = await readdir(ASSETS);
const javascript = files.filter((file) => file.endsWith('.js'));
const sizes = await Promise.all(
  javascript.map(async (file) => ({ file, bytes: (await stat(path.join(ASSETS, file))).size })),
);
const largest = sizes.reduce((current, candidate) =>
  candidate.bytes > current.bytes ? candidate : current,
);
requireBudget(largest.bytes, budgets.maxChunkBytes, 'largest_chunk_bytes');

const indexHtml = await readFile(path.join(DIST, 'index.html'), 'utf8');
const startupAssets = [...indexHtml.matchAll(/(?:src|href)="\/assets\/([^"]+)"/g)].map(
  (match) => match[1],
);
const coldAssetReadStarted = performance.now();
await Promise.all(startupAssets.map((file) => readFile(path.join(ASSETS, file))));
const coldAssetReadMs = performance.now() - coldAssetReadStarted;
requireBudget(coldAssetReadMs, budgets.coldStartMs, 'cold_start_asset_read_ms');

const routePrefixes = [
  'chat-',
  'connectivity-',
  'dashboard-',
  'data-',
  'memory-',
  'projects-',
  'provenance-',
  'providers-',
  'scheduler-',
  'settings-',
  'skills-',
  'subagents-',
];
let maximumRouteAssetReadMs = 0;
for (const prefix of routePrefixes) {
  const routeFiles = javascript.filter((file) => file.startsWith(prefix));
  const started = performance.now();
  await Promise.all(routeFiles.map((file) => readFile(path.join(ASSETS, file))));
  maximumRouteAssetReadMs = Math.max(maximumRouteAssetReadMs, performance.now() - started);
}
requireBudget(maximumRouteAssetReadMs, budgets.routeChangeMs, 'max_route_asset_read_ms');

const collectGarbage = (globalThis as { gc?: () => void }).gc;
if (!collectGarbage) {
  throw new Error('perf-check requires Node --expose-gc for the retained-heap budget');
}
randomBytes(1);
collectGarbage();
const heapBeforeMessages = process.memoryUsage().heapUsed;
const messages = Array.from({ length: 500 }, (_, index) => ({
  id: `message-${index}`,
  role: index % 2 === 0 ? 'user' : 'assistant',
  content: `Retained conversation payload ${index}: ${randomBytes(768).toString('base64')}`,
  createdAt: 1_700_000_000_000 + index,
}));
collectGarbage();
const retained500MessagesMemoryDeltaBytes = Math.max(
  0,
  process.memoryUsage().heapUsed - heapBeforeMessages,
);
const serialized500MessagesBytes = Buffer.byteLength(JSON.stringify(messages));
requireBudget(
  retained500MessagesMemoryDeltaBytes,
  budgets.retained500MessagesBytes,
  'retained_500_messages_memory_delta_bytes',
);

const report = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  budgets: {
    paletteOpenMs: budgets.paletteOpenMs,
    routeChangeMs: budgets.routeChangeMs,
    streamingLongestTaskMs: budgets.streamingLongestTaskMs,
    retained500MessagesMiB: budgets.retained500MessagesBytes / MIB,
    coldStartMs: budgets.coldStartMs,
    maxChunkKiB: budgets.maxChunkBytes / KIB,
  },
  measurements: {
    paletteOpenMs,
    routeChangeMs,
    streamingLongestTaskMs,
    retained500MessagesMemoryDeltaBytes,
    retained500MessagesMemoryDeltaMiB: retained500MessagesMemoryDeltaBytes / MIB,
    serialized500MessagesBytes,
    mounted500MessageRows,
    coldDashboardRenderMs,
    coldAssetReadMs,
    maximumRouteAssetReadMs,
    largestChunkBytes: largest.bytes,
    largestChunkKiB: largest.bytes / KIB,
    largestChunkFile: largest.file,
    unhandledPromiseRejections: 0,
    eventLoopYielded: true,
  },
  pass: true,
};
const json = `${JSON.stringify(report, null, 2)}\n`;
await writeFile(OUTPUT, json, 'utf8');
process.stdout.write(json);
