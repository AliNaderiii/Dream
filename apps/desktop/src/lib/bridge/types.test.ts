import { describe, expect, it } from 'vitest';

import { BRIDGE_CONNECTION_STATES, normalizeBridgeState } from './types';

describe('normalizeBridgeState', () => {
  it('accepts a bare-string payload (what the Rust supervisor actually emits)', () => {
    expect(normalizeBridgeState('restarting')).toBe('restarting');
    expect(normalizeBridgeState('connecting')).toBe('connecting');
    expect(normalizeBridgeState('ready')).toBe('ready');
    expect(normalizeBridgeState('reconnecting')).toBe('reconnecting');
    expect(normalizeBridgeState('disconnected')).toBe('disconnected');
  });

  it('accepts the { state: string } envelope form (older/future builds)', () => {
    expect(normalizeBridgeState({ state: 'restarting' })).toBe('restarting');
    expect(normalizeBridgeState({ state: 'ready' })).toBe('ready');
    expect(normalizeBridgeState({ state: 'disconnected' })).toBe('disconnected');
  });

  it('keeps the Rust "restarting" state as the UI restarting state', () => {
    expect(normalizeBridgeState('restarting')).toBe('restarting');
    expect(normalizeBridgeState({ state: 'restarting' })).toBe('restarting');
  });

  it('fails closed to disconnected for any untrusted/unknown payload', () => {
    expect(normalizeBridgeState(undefined)).toBe('disconnected');
    expect(normalizeBridgeState(null)).toBe('disconnected');
    expect(normalizeBridgeState(42)).toBe('disconnected');
    expect(normalizeBridgeState({})).toBe('disconnected');
    expect(normalizeBridgeState({ state: 123 })).toBe('disconnected');
    expect(normalizeBridgeState({ state: 'typo' })).toBe('disconnected');
    expect(normalizeBridgeState([])).toBe('disconnected');
    expect(normalizeBridgeState('RESTARTING')).toBe('disconnected');
  });

  it('never returns a value outside BridgeConnectionState', () => {
    const samples = [
      'restarting',
      'connecting',
      'ready',
      'reconnecting',
      'disconnected',
      undefined,
      null,
      7,
      { state: 'nope' },
    ];
    for (const sample of samples) {
      expect(BRIDGE_CONNECTION_STATES).toContain(normalizeBridgeState(sample));
    }
  });
});
