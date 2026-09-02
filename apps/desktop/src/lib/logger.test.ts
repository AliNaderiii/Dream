import { afterEach, describe, expect, expectTypeOf, it, vi, type MockInstance } from 'vitest';

import { getLogLevel, log, setLogLevel, type Logger } from '@/lib/logger';

const ISO_TIMESTAMP = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/;

// Fake credentials are assembled from fragments so the repo's tracked-file
// secret scanner (tests/test_security_secrets.py) never matches the SOURCE
// literals, while the runtime values still exercise every redaction shape.
const SK_KEY = `sk-${'abcdefghij'.repeat(3)}`;

/** Captures one formatted line per record without touching real output. */
function capture(): { lines: Record<string, string[]>; spies: MockInstance[] } {
  const lines: Record<string, string[]> = { debug: [], info: [], warn: [], error: [] };
  const spies = (['debug', 'info', 'warn', 'error'] as const).map((level) =>
    vi.spyOn(console, level).mockImplementation((...args: unknown[]) => {
      lines[level].push(String(args[0]));
    }),
  );
  return { lines, spies };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  setLogLevel(null);
});

describe('logger public API', () => {
  it('exports the expected typed API', () => {
    expectTypeOf(log).toMatchTypeOf<Logger>();
    expect(typeof log.debug).toBe('function');
    expect(typeof log.info).toBe('function');
    expect(typeof log.warn).toBe('function');
    expect(typeof log.error).toBe('function');
    expect(typeof setLogLevel).toBe('function');
    expect(typeof getLogLevel).toBe('function');
  });

  it('defaults to verbose logging in development and warn in production', () => {
    expect(import.meta.env.DEV).toBe(true);
    expect(getLogLevel()).toBe('debug');
    vi.stubEnv('DEV', false);
    expect(getLogLevel()).toBe('warn');
    setLogLevel('error');
    expect(getLogLevel()).toBe('error');
    setLogLevel(null);
    expect(getLogLevel()).toBe('warn');
  });
});

describe('level filtering', () => {
  it('emits debug and info records in development', () => {
    const { lines } = capture();
    log.debug('spin-up details', { requestId: 'r-1' });
    log.info('workspace changed', { workspaceId: 'ws-7' });
    expect(lines.debug).toHaveLength(1);
    expect(lines.info).toHaveLength(1);
    expect(lines.debug[0]).toContain('spin-up details');
    expect(lines.info[0]).toContain('workspace changed');
  });

  it('keeps warnings and errors visible in production', () => {
    vi.stubEnv('DEV', false);
    const { lines } = capture();
    log.debug('hidden in production');
    log.info('hidden in production');
    log.warn('bridge reconnecting', { attempt: 2 });
    log.error('bridge request failed', new Error('socket closed'), { requestId: 'r-1' });
    expect(lines.debug).toHaveLength(0);
    expect(lines.info).toHaveLength(0);
    expect(lines.warn).toHaveLength(1);
    expect(lines.error).toHaveLength(1);
    expect(lines.warn[0]).toContain('bridge reconnecting');
    expect(lines.error[0]).toContain('bridge request failed');
  });

  it('honors an explicit minimum level override', () => {
    setLogLevel('error');
    const { lines } = capture();
    log.debug('filtered');
    log.info('filtered');
    log.warn('filtered');
    log.error('kept');
    expect(lines.debug).toHaveLength(0);
    expect(lines.info).toHaveLength(0);
    expect(lines.warn).toHaveLength(0);
    expect(lines.error).toHaveLength(1);
  });

  it('routes each level to the matching console method', () => {
    const { spies } = capture();
    log.debug('d');
    log.info('i');
    log.warn('w');
    log.error('e');
    for (const spy of spies) expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe('line formatting', () => {
  it('uses a stable prefix, ISO timestamp, level, message and JSON context', () => {
    const { lines } = capture();
    log.warn('workspace changed', { workspaceId: 'ws-7', attempt: 2 });
    expect(lines.warn[0]).toMatch(
      new RegExp(
        `^\\[dream\\] ${ISO_TIMESTAMP.source} warn workspace changed \\{"workspaceId":"ws-7","attempt":2\\}$`,
      ),
    );
  });

  it('omits the context suffix when nothing was provided', () => {
    const { lines } = capture();
    log.error('something failed');
    expect(lines.error[0]).toMatch(
      new RegExp(`^\\[dream\\] ${ISO_TIMESTAMP.source} error something failed$`),
    );
  });
});

describe('redaction', () => {
  it('redacts sensitive keys at the top level and nested', () => {
    const { lines } = capture();
    log.info('auth flow', {
      token: 'tok_abc123',
      password: 'hunter2',
      secret: 's3cr3t',
      apiKey: 'key_1',
      authorization: 'Bearer abcdefgh',
      cookie: 'session=1',
      clientSecret: 'cs_9',
      nested: { accessToken: 'at_2', safe: 'visible' },
    });
    const line = lines.info[0];
    expect(line).toContain('[REDACTED]');
    expect(line).toContain('"safe":"visible"');
    expect(line).not.toContain('tok_abc123');
    expect(line).not.toContain('hunter2');
    expect(line).not.toContain('s3cr3t');
    expect(line).not.toContain('key_1');
    expect(line).not.toContain('abcdefgh');
    expect(line).not.toContain('session=1');
    expect(line).not.toContain('cs_9');
    expect(line).not.toContain('at_2');
  });

  it('masks credential-shaped values even under innocuous keys', () => {
    const { lines } = capture();
    log.warn('provider call', {
      header: 'Bearer eyJhbGciOi.eyJzdWIiOiIxIn0.SflKxwRJSM',
      model: SK_KEY,
    });
    const line = lines.warn[0];
    expect(line).not.toContain('eyJhbGciOi');
    expect(line).not.toContain(SK_KEY);
    expect(line).toContain('[REDACTED]');
    expect(line).toContain('"header"');
  });

  it('summarises absolute filesystem paths to their final segment', () => {
    const { lines } = capture();
    log.info('workspace selected', {
      workspaceRoot: '/home/alice/.dream/agents',
      path: 'C:\\Users\\bob\\secrets.json',
    });
    const line = lines.info[0];
    expect(line).toContain('<path>/agents');
    expect(line).toContain('<path>/secrets.json');
    expect(line).not.toContain('/home/alice');
    expect(line).not.toContain('C:\\Users');
  });

  it('redacts credential-shaped content inside messages and error text', () => {
    const { lines } = capture();
    log.error(`request failed: Bearer ${SK_KEY.slice(3)}`, new Error(`key ${SK_KEY} rejected`));
    const line = lines.error[0];
    expect(line).not.toContain(SK_KEY);
    expect(line).toContain('[REDACTED]');
  });
});

describe('truncation and hostile values', () => {
  it('truncates oversized string values and total lines', () => {
    const { lines } = capture();
    log.warn('long value', { blob: 'x'.repeat(5_000) });
    expect(lines.warn[0]).toContain('…[truncated 4488 chars]');
    expect(lines.warn[0].length).toBeLessThanOrEqual(2048);

    log.info(
      'wide context',
      Object.fromEntries(Array.from({ length: 80 }, (_, i) => [`k${i}`, i])),
    );
    expect(lines.info[0]).toContain('[+48 more keys]');
  });

  it('never throws on circular context', () => {
    const { lines } = capture();
    const circular: Record<string, unknown> = { name: 'loop' };
    circular.self = circular;
    expect(() => log.warn('circular context', circular)).not.toThrow();
    expect(lines.warn[0]).toContain('"self":"[circular]"');
  });

  it('never throws on throwing getters, bigints, symbols or deep nesting', () => {
    const { lines } = capture();
    const hostile: Record<string, unknown> = {
      get explodes(): string {
        throw new Error('getter boom');
      },
      count: 1n,
      flag: Symbol('debug-flag'),
      render: () => null,
    };
    let deep: unknown = { leaf: true };
    for (let i = 0; i < 10; i += 1) deep = { child: deep };
    hostile.deep = deep;
    expect(() => log.error('hostile context', hostile)).not.toThrow();
    const line = lines.error[0];
    expect(line).toContain('[unserializable]');
    expect(line).toContain('"count":"1"');
    expect(line).toContain('"flag":"Symbol(debug-flag)"');
    expect(line).toContain('[max depth]');
  });
});

describe('error serialization', () => {
  it('preserves Error name and message with a truncated stack', () => {
    const { lines } = capture();
    const failure = new Error('bridge handshake refused');
    log.error('bridge request failed', failure, { requestId: 'r-9' });
    const line = lines.error[0];
    expect(line).toContain('"name":"Error"');
    expect(line).toContain('"message":"bridge handshake refused"');
    expect(line).toContain('"stack"');
    expect(line).toContain('"requestId":"r-9"');
  });

  it('lets the error argument own the error key', () => {
    const { lines } = capture();
    log.error('shadowed key', new Error('actual'), { error: 'caller supplied' });
    expect(lines.error[0]).toContain('"message":"actual"');
    expect(lines.error[0]).not.toContain('caller supplied');
  });

  it('accepts strings, plain objects and null safely', () => {
    const { lines } = capture();
    log.error('string error', 'plain failure');
    log.error('object error', { code: 'ECONNREFUSED', apiKey: 'leaky' });
    log.error('null error', null);
    expect(lines.error[0]).toContain('"error":"plain failure"');
    expect(lines.error[1]).toContain('"code":"ECONNREFUSED"');
    expect(lines.error[1]).toContain('[REDACTED]');
    expect(lines.error[1]).not.toContain('leaky');
    expect(lines.error[2]).toContain('"error":null');
  });

  it('follows error cause chains without losing the primary detail', () => {
    const { lines } = capture();
    const root = new Error('spawn failed');
    const wrapped = new Error('sidecar unavailable', { cause: root });
    log.error('bridge start failed', wrapped);
    const line = lines.error[0];
    expect(line).toContain('"message":"sidecar unavailable"');
    expect(line).toContain('"cause"');
    expect(line).toContain('spawn failed');
  });
});
