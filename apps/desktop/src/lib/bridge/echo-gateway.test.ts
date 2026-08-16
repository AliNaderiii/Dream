import { describe, expect, it } from 'vitest';

import {
  EchoGatewayRuntime,
  isSecretKey,
  redactConfig,
  requireGatewayPlatform,
} from './echo-gateway';
import { GATEWAY_PLATFORM_NAMES } from './types';

describe('secret redaction helpers', () => {
  it('masks values whose key name marks them as secrets', () => {
    const redacted = redactConfig({
      token: 'abc',
      app_secret: 'xyz',
      password: 'pw',
      api_key: 'k',
      note: 'visible',
      nested: { inner_token: 't', kept: 1 },
    });
    expect(redacted['token']).toBe('••••••••');
    expect(redacted['app_secret']).toBe('••••••••');
    expect(redacted['password']).toBe('••••••••');
    expect(redacted['api_key']).toBe('••••••••');
    expect(redacted['note']).toBe('visible');
    expect((redacted['nested'] as Record<string, unknown>)['inner_token']).toBe('••••••••');
    expect((redacted['nested'] as Record<string, unknown>)['kept']).toBe(1);
    expect(redactConfig({ token: '' })['token']).toBe('');
  });

  it('recognises secret key names case-insensitively', () => {
    expect(isSecretKey('Bot_Token')).toBe(true);
    expect(isSecretKey('imap_password')).toBe(true);
    expect(isSecretKey('note')).toBe(false);
  });

  it('validates gateway platform params', () => {
    expect(requireGatewayPlatform({ platform: 'telegram' })).toBe('telegram');
    expect(() => requireGatewayPlatform({})).toThrow();
    expect(() => requireGatewayPlatform({ platform: 'carrier-pigeon' })).toThrow();
  });
});

describe('EchoGatewayRuntime', () => {
  it('reports the six-platform catalog with public config', () => {
    const runtime = new EchoGatewayRuntime();
    const platforms = runtime.platforms();
    expect(platforms.map((p) => p.name)).toEqual([...GATEWAY_PLATFORM_NAMES]);
    expect(platforms[4].privacy).toBe('e2e'); // signal
    expect(platforms[0].enabled).toBe(false);
    runtime.dispose();
  });

  it('configure stores secrets locally but only returns the redacted view', () => {
    const runtime = new EchoGatewayRuntime();
    const config = runtime.configure('telegram', {
      token: '123456:ABCDEF',
      enabled: true,
    });
    expect(config['token']).toBe('••••••••');
    expect(config['enabled']).toBe(true);
    expect(config['configured']).toBe(true);
    // A blank secret keeps the stored one (leave-unchanged semantics).
    runtime.configure('telegram', { token: '' });
    const again = runtime.configure('telegram', { enabled: false });
    expect(again['token']).toBe('••••••••');
    runtime.dispose();
  });

  it('start honours enabled + configured, stop brings everything down', () => {
    const runtime = new EchoGatewayRuntime();
    runtime.configure('telegram', { token: 't', enabled: true });
    runtime.configure('discord', { bot_token: 't', enabled: true }); // unconfigured? token set → configured
    runtime.configure('email', { enabled: true }); // no required fields → not configured
    const started = runtime.start();
    expect(started.running).toBe(true);
    const byName = Object.fromEntries(started.adapters.map((a) => [a.platform, a]));
    expect(byName['telegram'].running).toBe(true);
    expect(byName['email'].running).toBe(false);
    expect(byName['email'].detail).toBe('missing configuration');
    expect(byName['signal'].detail).toBe('disabled');
    const stopped = runtime.stop();
    expect(stopped.running).toBe(false);
    expect(stopped.adapters.every((a) => !a.running)).toBe(true);
    runtime.dispose();
  });

  it('issues stable link codes and manages linked users', () => {
    const runtime = new EchoGatewayRuntime();
    const first = runtime.linkCode('telegram');
    expect(first.code).toMatch(/^\d{6}$/);
    expect(runtime.linkCode('telegram').code).toBe(first.code); // stable while pending
    expect(runtime.linkedUsers()).toEqual([]);
    // Simulating the sidecar's /link redemption: the echo runtime does not
    // redeem codes itself, but unlink reports the registry truthfully.
    expect(runtime.unlinkUser('telegram', '42')).toBe(false);
    runtime.dispose();
  });

  it('serves the seeded message log filtered per platform', () => {
    const runtime = new EchoGatewayRuntime();
    const all = runtime.logs(null, 100);
    expect(all.total).toBeGreaterThan(0);
    expect(all.entries.every((e) => e.timestamp)).toBe(true);
    const telegram = runtime.logs('telegram', 100);
    expect(telegram.entries.length).toBeGreaterThan(0);
    expect(telegram.entries.every((e) => e.platform === 'telegram')).toBe(true);
    // Signal rows exist but carry no content (e2e stripping).
    const signal = runtime.logs('signal', 100);
    expect(signal.entries.length).toBeGreaterThan(0);
    expect(signal.entries.every((e) => e.text === '')).toBe(true);
    runtime.dispose();
  });
});
