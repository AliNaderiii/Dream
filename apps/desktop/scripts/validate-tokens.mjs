#!/usr/bin/env node
/** Strict Tokens Studio v2 + contrast gate for Dream's design source of truth. */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = resolve(APP, '../..');
const tokenPath = resolve(ROOT, 'docs/design/tokens/dream.tokens.json');
const cssPath = resolve(ROOT, 'docs/design/tokens/dream.css');
const document = JSON.parse(readFileSync(tokenPath, 'utf8'));
const css = readFileSync(cssPath, 'utf8');
const errors = [];

function flatten(node, prefix = '', output = new Map()) {
  for (const [key, value] of Object.entries(node)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && '$value' in value) output.set(path, value);
    else if (value && typeof value === 'object') flatten(value, path, output);
  }
  return output;
}

const TOKENS_STUDIO_SCHEMA = 'https://schemas.tokens.studio/latest/tokens.json';
const SUPPORTED_TYPES = new Set([
  'color',
  'dimension',
  'fontFamily',
  'number',
  'duration',
  'cubicBezier',
  'boxShadow',
]);

if (document.$schema !== TOKENS_STUDIO_SCHEMA) {
  errors.push(`$schema must equal ${TOKENS_STUDIO_SCHEMA}.`);
}
if (!Array.isArray(document.$themes) || document.$themes.length !== 12) {
  errors.push('Expected exactly 12 theme/accent combinations.');
}

const setNames = (document.$metadata?.tokenSetOrder ?? []);
const sets = new Map();
for (const name of setNames) {
  if (!document[name]) errors.push(`Metadata references missing set: ${name}`);
  else sets.set(name, flatten(document[name]));
}
for (const [name, tokens] of sets) {
  if (tokens.size === 0) errors.push(`Token set is empty: ${name}`);
  for (const [path, token] of tokens) {
    if (!token.$type) errors.push(`${name}:${path} is missing $type`);
    else if (!SUPPORTED_TYPES.has(token.$type)) {
      errors.push(`${name}:${path} uses unsupported Tokens Studio type ${token.$type}`);
    }
    if (token.$value === undefined) errors.push(`${name}:${path} is missing $value`);
    if (token.$type === 'cubicBezier' && (!Array.isArray(token.$value) || token.$value.length !== 4)) {
      errors.push(`${name}:${path} must contain four cubic-bezier coordinates`);
    }
    if (token.$type === 'fontFamily' && !Array.isArray(token.$value)) {
      errors.push(`${name}:${path} must contain a font-family array`);
    }
  }
}

const themeIds = new Set();
for (const theme of document.$themes ?? []) {
  if (!theme.id || !theme.name || !theme.group) errors.push('Every theme needs id, name, and group.');
  if (themeIds.has(theme.id)) errors.push(`Duplicate theme id: ${theme.id}`);
  themeIds.add(theme.id);
  for (const [setName, status] of Object.entries(theme.selectedTokenSets ?? {})) {
    if (!sets.has(setName)) errors.push(`${theme.name} references unknown set ${setName}`);
    if (status !== 'source' && status !== 'enabled') {
      errors.push(`${theme.name}:${setName} has unsupported selection status ${status}`);
    }
  }
}

function selectedTokens(theme) {
  const selected = new Map();
  for (const setName of Object.keys(theme.selectedTokenSets ?? {})) {
    const set = sets.get(setName);
    if (!set) {
      errors.push(`${theme.name} references missing set ${setName}`);
      continue;
    }
    for (const [path, value] of set) selected.set(path, value);
  }
  return selected;
}

function resolveValue(path, selected, stack = []) {
  if (stack.includes(path)) throw new Error(`Circular alias: ${[...stack, path].join(' → ')}`);
  const token = selected.get(path);
  if (!token) throw new Error(`Unresolved alias: ${path}`);
  const value = token.$value;
  if (typeof value !== 'string') return value;
  const match = /^\{([^}]+)\}$/.exec(value);
  return match ? resolveValue(match[1], selected, [...stack, path]) : value;
}

function channel(value) {
  const linear = value / 255;
  return linear <= 0.04045 ? linear / 12.92 : ((linear + 0.055) / 1.055) ** 2.4;
}
function luminance(hex) {
  const raw = hex.replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(raw)) throw new Error(`Contrast value is not 6-digit hex: ${hex}`);
  const [r, g, b] = [raw.slice(0, 2), raw.slice(2, 4), raw.slice(4, 6)].map((v) =>
    Number.parseInt(v, 16),
  );
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}
function contrast(a, b) {
  const [bright, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (bright + 0.05) / (dark + 0.05);
}

const textPairs = [
  ['color.text.primary', 'color.surface.base', 4.5],
  ['color.text.secondary', 'color.surface.base', 4.5],
  ['color.text.muted', 'color.surface.canvas', 4.5],
  ['color.accent.text', 'color.surface.base', 4.5],
  ['color.accent.fg', 'color.accent.solid', 4.5],
  ['color.status.success-fg', 'color.status.success-bg', 4.5],
  ['color.status.warning-fg', 'color.status.warning-bg', 4.5],
  ['color.status.danger-fg', 'color.status.danger-bg', 4.5],
  ['color.status.info-fg', 'color.status.info-bg', 4.5],
];

const rows = [];
for (const theme of document.$themes ?? []) {
  const selected = selectedTokens(theme);
  for (const path of selected.keys()) {
    try {
      resolveValue(path, selected);
    } catch (error) {
      errors.push(`${theme.name}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  for (const [fgPath, bgPath, minimum] of textPairs) {
    try {
      const fg = resolveValue(fgPath, selected);
      const bg = resolveValue(bgPath, selected);
      const ratio = contrast(fg, bg);
      rows.push({ theme: theme.name, pair: `${fgPath} / ${bgPath}`, ratio });
      if (ratio < minimum) {
        errors.push(`${theme.name}: ${fgPath} on ${bgPath} is ${ratio.toFixed(2)}:1 (< ${minimum}:1)`);
      }
    } catch (error) {
      errors.push(`${theme.name}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

const shellTokens = sets.get('core');
for (const [token, cssVariable] of [
  ['shell.rail', '--ds-shell-rail'],
  ['shell.sidebar', '--ds-shell-sidebar'],
  ['shell.pane-min-inline', '--ds-pane-min-inline'],
  ['shell.pane-min-block', '--ds-pane-min-block'],
  ['shell.statusbar', '--ds-shell-statusbar'],
  ['shell.titlebar', '--ds-shell-titlebar'],
  ['shell.mac-controls', '--ds-shell-mac-controls'],
]) {
  const value = shellTokens?.get(token)?.$value;
  if (!value || !css.includes(`${cssVariable}: ${value};`)) {
    errors.push(`Runtime CSS does not round-trip core.${token} to ${cssVariable}.`);
  }
}

for (const selector of ["[data-theme='light']", "[data-theme='warm']", "[data-theme='dark']"]) {
  if (!css.includes(selector)) errors.push(`Runtime CSS is missing ${selector}`);
}
for (const accent of ['ocean', 'forest', 'ember']) {
  if (!css.includes(`[data-accent='${accent}']`)) errors.push(`Runtime CSS is missing ${accent}`);
}

if (errors.length > 0) {
  console.error(`Token gate failed with ${errors.length} error(s):\n- ${errors.join('\n- ')}`);
  process.exit(1);
}

const tokenCount = [...sets.values()].reduce((total, set) => total + set.size, 0);
const lowest = [...rows].sort((a, b) => a.ratio - b.ratio).slice(0, 5);
console.log(
  `Tokens Studio schema-compatible import: PASS — ${sets.size} sets, ${tokenCount} tokens, ${document.$themes.length} themes.`,
);
console.log(`Contrast gate: PASS — ${rows.length} AA checks.`);
for (const row of lowest) console.log(`  ${row.ratio.toFixed(2)}:1  ${row.theme}  ${row.pair}`);

if (process.argv.includes('--contrast-table')) {
  console.log('\n| Theme | Direction | Semantic pair | Ratio |');
  console.log('| --- | --- | --- | ---: |');
  for (const row of rows.filter(({ theme }) => theme.endsWith('/ Violet'))) {
    for (const direction of ['LTR', 'RTL']) {
      console.log(`| ${row.theme} | ${direction} | ${row.pair} | ${row.ratio.toFixed(2)}:1 |`);
    }
  }
}
