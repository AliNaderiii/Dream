/**
 * Typed application logger — the single console sink for the Dream frontend.
 *
 * Every application module must import `log` from here instead of calling the
 * console directly. The console calls in `emit()` and its fallback are the only
 * permitted direct console usages in `apps/desktop/src`; they exist so that
 * `console.warn` / `console.error` output keeps reaching the WebView console
 * (and therefore the Rust `tauri-plugin-log` stdout capture on platforms that
 * forward it) in both development and production.
 *
 * Policy:
 * - `debug` / `info` are emitted only in Vite development mode
 *   (`import.meta.env.DEV`, statically replaced at build time).
 * - `warn` / `error` are always emitted, in development and production.
 * - Context values are redacted by key (token, secret, password, apiKey,
 *   authorization, cookie, …), credential-shaped string values are masked, and
 *   absolute filesystem paths are summarised to their final segment.
 * - Oversized values and lines are truncated, circular structures collapse to
 *   `"[circular]"`, and logging never throws.
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export type LogContext = Record<string, unknown>;

export interface Logger {
  debug(message: string, context?: LogContext): void;
  info(message: string, context?: LogContext): void;
  warn(message: string, context?: LogContext): void;
  error(message: string, error?: unknown, context?: LogContext): void;
}

/* ------------------------------------------------------------------ limits */

const PREFIX = '[dream]';
const REDACTED = '[REDACTED]';
const MAX_STRING_LENGTH = 512;
const MAX_ARRAY_ITEMS = 32;
const MAX_OBJECT_KEYS = 32;
const MAX_DEPTH = 3;
const MAX_LINE_LENGTH = 2048;

const LEVEL_RANK: Readonly<Record<LogLevel, number>> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

/* --------------------------------------------------------------- redaction */

// Keys whose values are treated as secrets regardless of the value shape.
// Deliberately broad: a redacted field costs one log line of detail, while a
// leaked credential costs an incident. `session` is included because session
// identifiers enable hijacking.
const SENSITIVE_KEY_PATTERN =
  /(token|secret|password|passwd|pwd|api[-_]?key|apikey|authorization|cookie|credential|private[-_]?key|access[-_]?key|session)/i;

// Keys whose string values look like filesystem locations. Absolute paths can
// embed usernames and machine layout, so only the final segment survives.
const PATH_KEY_PATTERN = /(?:path|paths|filename|filepath|directory|folder|cwd|dir|root)$/i;

// Credential-shaped values are masked even under innocuous keys: bearer
// headers, OpenAI-style `sk-` keys, GitHub tokens, Slack tokens, AWS access
// key ids and JWTs. Non-`g` key patterns above are matched with `.test`, this
// one only with `String.replace`, so regex statefulness never bites.
const SENSITIVE_VALUE_PATTERN =
  /\b(?:bearer\s+[a-z0-9._~+/=-]{8,}|sk-[a-z0-9_-]{16,}|ghp_[a-z0-9]{20,}|xox[baprs]-[a-z0-9-]{10,}|akia[0-9a-z]{12,}|eyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{4,})/gi;

function redactValues(text: string): string {
  return text.replace(SENSITIVE_VALUE_PATTERN, REDACTED);
}

/** Summarises absolute-looking paths to `<path>/<basename>`. */
function summarizePath(value: string): string {
  if (!/^(?:[a-z]:[\\/]|[\\/]{2}|\/|~)/i.test(value)) return value;
  const segments = value.split(/[\\/]/).filter((segment) => segment.length > 0);
  const basename = segments[segments.length - 1];
  return basename === undefined ? '<path>' : `<path>/${basename}`;
}

function truncate(text: string, limit: number = MAX_STRING_LENGTH): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…[truncated ${text.length - limit} chars]`;
}

/* ---------------------------------------------------------- safe serialize */

/**
 * Rewrites a value for logging: redacts secret keys, masks credential-shaped
 * strings, summarises paths, truncates and bounds depth. Never throws; hostile
 * values (throwing getters included) degrade to placeholder strings.
 */
function sanitize(value: unknown, key: string | null, depth: number, seen: Set<unknown>): unknown {
  try {
    if (value === null) return null;
    if (typeof value === 'string') {
      if (key !== null && SENSITIVE_KEY_PATTERN.test(key)) return REDACTED;
      const masked = key !== null && PATH_KEY_PATTERN.test(key) ? summarizePath(value) : value;
      return truncate(redactValues(masked));
    }
    if (
      typeof value === 'number' ||
      typeof value === 'boolean' ||
      typeof value === 'undefined' ||
      typeof value === 'bigint'
    ) {
      return typeof value === 'bigint' ? value.toString() : value;
    }
    if (typeof value === 'symbol') return value.toString();
    if (typeof value === 'function') return `[function ${value.name || 'anonymous'}]`;
    // Errors nested inside context get the same treatment as the error argument.
    if (value instanceof Error) return sanitizeError(value, seen);
    // Only plain objects and arrays remain.
    if (depth >= MAX_DEPTH) return '[max depth]';
    if (seen.has(value)) return '[circular]';
    seen.add(value);
    try {
      if (Array.isArray(value)) {
        const items = value
          .slice(0, MAX_ARRAY_ITEMS)
          .map((item: unknown) => sanitize(item, null, depth + 1, seen));
        if (value.length > MAX_ARRAY_ITEMS) {
          items.push(`[+${value.length - MAX_ARRAY_ITEMS} more]`);
        }
        return items;
      }
      const record: Record<string, unknown> = {};
      const keys = Object.keys(value);
      for (const entryKey of keys) {
        if (Object.keys(record).length >= MAX_OBJECT_KEYS) {
          record['…'] = `[+${keys.length - MAX_OBJECT_KEYS} more keys]`;
          break;
        }
        try {
          record[entryKey] = sanitize(
            (value as Record<string, unknown>)[entryKey],
            entryKey,
            depth + 1,
            seen,
          );
        } catch {
          record[entryKey] = '[unserializable]';
        }
      }
      return record;
    } finally {
      seen.delete(value);
    }
  } catch {
    return '[unserializable]';
  }
}

/**
 * Serializes the `error` argument. `Error` instances keep their name, message
 * and a truncated stack; `cause` chains are followed. Anything else is treated
 * as potentially hostile/secret-bearing data and passes through the same
 * redaction pipeline as context values.
 */
function sanitizeError(error: unknown, seen: Set<unknown>): unknown {
  if (!(error instanceof Error)) return sanitize(error, null, 0, seen);
  if (seen.has(error)) return '[circular]';
  seen.add(error);
  try {
    const detail: Record<string, unknown> = {
      name: truncate(redactValues(error.name)),
      message: truncate(redactValues(error.message)),
    };
    if (typeof error.stack === 'string' && error.stack.length > 0) {
      detail.stack = truncate(redactValues(error.stack));
    }
    const cause = (error as { cause?: unknown }).cause;
    if (cause !== undefined) detail.cause = sanitize(cause, null, 0, seen);
    return detail;
  } finally {
    seen.delete(error);
  }
}

/* ------------------------------------------------------------------- output */

/** JSON-encodes a record without ever throwing. */
function safeJson(value: Record<string, unknown>): string {
  try {
    return JSON.stringify(value) ?? '{}';
  } catch {
    return '{"context":"[unserializable]"}';
  }
}

function formatLine(
  level: LogLevel,
  message: string,
  error: unknown,
  context: LogContext | undefined,
): string {
  const seen = new Set<unknown>();
  const record: Record<string, unknown> = {};
  if (context) {
    // Read entries one key at a time: `Object.keys` never invokes getters, so
    // a single hostile accessor cannot destroy the rest of the record.
    const keys = Object.keys(context);
    for (const key of keys) {
      if (Object.keys(record).length >= MAX_OBJECT_KEYS) {
        record['…'] = `[+${keys.length - MAX_OBJECT_KEYS} more keys]`;
        break;
      }
      try {
        record[key] = sanitize(context[key], key, 0, seen);
      } catch {
        record[key] = '[unserializable]';
      }
    }
  }
  // The `error` argument owns the `error` key: the serialized error detail
  // replaces any same-named context entry so failures are never dropped.
  if (error !== undefined) record.error = sanitizeError(error, seen);

  const suffix = Object.keys(record).length > 0 ? ` ${safeJson(record)}` : '';
  const line = `${PREFIX} ${new Date().toISOString()} ${level} ${truncate(redactValues(message))}${suffix}`;
  return truncate(line, MAX_LINE_LENGTH);
}

/* The single console sink. See the module doc comment. */
function emit(
  level: LogLevel,
  message: string,
  error: unknown,
  context: LogContext | undefined,
): void {
  if (LEVEL_RANK[level] < LEVEL_RANK[getLogLevel()]) return;
  const sink =
    level === 'error'
      ? console.error
      : level === 'warn'
        ? console.warn
        : level === 'info'
          ? console.info
          : console.debug;
  try {
    sink(formatLine(level, message, error, context));
  } catch {
    // Logging must never propagate failures; fall back to a raw, unformatted
    // record so the failure itself stays observable.
    try {
      console.error(`${PREFIX} ${new Date().toISOString()} error log-formatting failed`, message);
    } catch {
      /* the console is unavailable — nothing further can be done */
    }
  }
}

/* --------------------------------------------------------------- public API */

let levelOverride: LogLevel | null = null;

/**
 * Returns the active minimum level: an explicit override when set, otherwise
 * the Vite environment default — verbose (`debug`) in development, `warn` in
 * production so warnings and errors always reach the console.
 */
export function getLogLevel(): LogLevel {
  if (levelOverride !== null) return levelOverride;
  // Vite statically replaces `import.meta.env.DEV`, so this collapses to a
  // constant (`false`) in production builds.
  return import.meta.env.DEV ? 'debug' : 'warn';
}

/**
 * Overrides the minimum log level at runtime, or restores the environment
 * default by passing `null`. Primarily a seam for tests and future runtime
 * configuration (e.g. a diagnostics setting).
 */
export function setLogLevel(level: LogLevel | null): void {
  levelOverride = level;
}

/** The shared application logger. */
export const log: Logger = {
  debug: (message, context) => emit('debug', message, undefined, context),
  info: (message, context) => emit('info', message, undefined, context),
  warn: (message, context) => emit('warn', message, undefined, context),
  error: (message, error, context) => emit('error', message, error, context),
};
