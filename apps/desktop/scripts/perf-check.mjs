/**
 * Performance gate for the v5 workbench (vanilla ES modules).
 *
 * Replaces the React-era runtime suites. What it measures is real:
 * - cold start: parse + eval of every built chunk inside a fresh JSDOM
 *   (the closest CI-able proxy to "the WebView opens the app");
 * - bundle weight: max chunk / total JS / total CSS against budgets.
 *
 * Contract unchanged: run with
 *   node --expose-gc scripts/perf-check.mjs
 * after `npm run build`; writes performance-results.json and exits non-zero
 * when a budget is exceeded.
 */
import { readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { JSDOM } from 'jsdom';

const DIST = path.resolve('dist');
const ASSETS = path.join(DIST, 'assets');
const OUTPUT = path.resolve('performance-results.json');
const KIB = 1024;

const budgets = {
  coldStartMs: 2_000,
  maxChunkBytes: 500 * KIB,
  totalJsBytes: 1_500 * KIB,
  totalCssBytes: 200 * KIB,
};

function requireBudget(value, maximum, label) {
  if (value >= maximum) {
    throw new Error(`${label} ${value.toFixed(3)} exceeded budget ${maximum}`);
  }
}

async function main() {
  const entries = await readdir(ASSETS);
  const jsFiles = entries.filter((name) => name.endsWith('.js'));
  const cssFiles = entries.filter((name) => name.endsWith('.css'));
  if (jsFiles.length === 0) {
    throw new Error('no built JS chunks under dist/assets — run `npm run build` first');
  }

  const jsSizes = await Promise.all(
    jsFiles.map(async (name) => (await readFile(path.join(ASSETS, name))).byteLength),
  );
  const cssSizes = await Promise.all(
    cssFiles.map(async (name) => (await readFile(path.join(ASSETS, name))).byteLength),
  );
  const totalJs = jsSizes.reduce((a, b) => a + b, 0);
  const totalCss = cssSizes.reduce((a, b) => a + b, 0);
  const maxChunk = Math.max(...jsSizes);

  // Cold start: fresh JSDOM per chunk set, eval in document order (index last
  // is not required — modules were bundled into a single graph).
  const dom = new JSDOM(
    '<!doctype html><html lang="fa" dir="rtl"><body><div id="root"></div></body></html>',
    {
      url: 'http://localhost/',
      pretendToBeVisual: true,
      runScripts: 'outside-only',
    },
  );
  const started = performance.now();
  let evalError = null;
  for (const name of jsFiles) {
    const code = await readFile(path.join(ASSETS, name), 'utf8');
    try {
      dom.window.eval(code);
    } catch (error) {
      evalError ??= error;
    }
  }
  const coldStartMs = performance.now() - started;
  const mounted = dom.window.document.querySelector('.app');

  // Stop the app's polling timers so this process can exit cleanly.
  dom.window.close();

  if (evalError) {
    // The bundle must actually boot outside a real WebView, or the gate is a lie.
    throw new Error(`cold start failed: bundled chunk threw: ${String(evalError)}`);
  }
  if (!mounted) {
    throw new Error('cold start failed: the app shell did not mount into #root');
  }

  requireBudget(coldStartMs, budgets.coldStartMs, 'coldStartMs');
  requireBudget(maxChunk, budgets.maxChunkBytes, 'maxChunkBytes');
  requireBudget(totalJs, budgets.totalJsBytes, 'totalJsBytes');
  requireBudget(totalCss, budgets.totalCssBytes, 'totalCssBytes');

  const results = {
    cold_start_ms: Number(coldStartMs.toFixed(1)),
    max_chunk_bytes: maxChunk,
    total_js_bytes: totalJs,
    total_css_bytes: totalCss,
    chunk_count: jsFiles.length,
    css_count: cssFiles.length,
    budgets: {
      cold_start_ms: budgets.coldStartMs,
      max_chunk_bytes: budgets.maxChunkBytes,
      total_js_bytes: budgets.totalJsBytes,
      total_css_bytes: budgets.totalCssBytes,
    },
    measured_on: new Date().toISOString(),
    note: 'v5 vanilla workbench: JSDOM cold start + bundle weight budgets.',
  };
  await writeFile(OUTPUT, `${JSON.stringify(results, null, 2)}\n`, 'utf8');
  console.log(
    `[perf] cold start ${results.cold_start_ms}ms · max chunk ${(maxChunk / KIB).toFixed(1)} KiB · JS ${(totalJs / KIB).toFixed(1)} KiB · CSS ${(totalCss / KIB).toFixed(1)} KiB`,
  );
}

await main();
