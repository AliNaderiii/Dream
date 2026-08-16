import { describe, expect, it } from 'vitest';

import { coerceFieldValues, fieldAsText, initialConfig } from './config-fields';
import type { GatewayPlatform } from '@/lib/bridge/types';

const telegram: GatewayPlatform = {
  name: 'telegram',
  label: 'Telegram',
  description: 'test',
  privacy: 'plaintext',
  max_message_length: 4096,
  supports_inline: true,
  supports_attachments: false,
  fields: [
    { key: 'token', label: 'Bot token', type: 'secret', required: true },
    { key: 'api_base_url', label: 'API base URL', type: 'text' },
  ],
  enabled: false,
  configured: false,
};

const whatsapp: GatewayPlatform = {
  name: 'whatsapp',
  label: 'WhatsApp',
  description: 'test',
  privacy: 'plaintext',
  max_message_length: 4096,
  supports_inline: true,
  supports_attachments: true,
  fields: [
    { key: 'port', label: 'Webhook port', type: 'number', default: 8478 },
    { key: 'path', label: 'Webhook path', type: 'text', default: '/webhook' },
    { key: 'auto_thread', label: 'Auto thread', type: 'boolean', default: false },
  ],
  enabled: false,
  configured: false,
};

describe('config field helpers', () => {
  it('seeds the form from catalog defaults, never from stored secrets', () => {
    const values = initialConfig(whatsapp);
    expect(values['port']).toBe(8478);
    expect(values['path']).toBe('/webhook');
    expect(values['auto_thread']).toBe(false);
    expect(initialConfig(telegram)['token']).toBe('');
  });

  it('coerces numbers, booleans, and strings back to typed values', () => {
    const values = coerceFieldValues(whatsapp, {
      port: '9000',
      path: ' /webhook ',
      auto_thread: true,
    });
    expect(values['port']).toBe(9000);
    expect(values['path']).toBe('/webhook');
    expect(values['auto_thread']).toBe(true);
    // Invalid numbers fall back to the catalog default.
    expect(coerceFieldValues(whatsapp, { port: 'nope' })['port']).toBe(8478);
  });

  it('trims string values and passes non-strings through', () => {
    expect(coerceFieldValues(telegram, { token: '  abc  ' })['token']).toBe('abc');
    expect(coerceFieldValues(telegram, { token: 42 })['token']).toBe(42);
  });

  it('renders raw values as input text', () => {
    expect(fieldAsText('hello')).toBe('hello');
    expect(fieldAsText(8478)).toBe('8478');
    expect(fieldAsText(true)).toBe('true');
    expect(fieldAsText(null)).toBe('');
    expect(fieldAsText(undefined)).toBe('');
    expect(fieldAsText({})).toBe('');
  });
});
