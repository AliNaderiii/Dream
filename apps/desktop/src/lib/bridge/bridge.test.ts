import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BridgeClient, EchoBridgeTransport, tokenise } from '@/lib/bridge/client';
import { BridgeRpcError, toBridgeError } from '@/lib/bridge/errors';
import { RPC_ERROR } from '@/lib/bridge/types';

describe('tokenise', () => {
  it('splits on word boundaries and rejoins exactly', () => {
    expect(tokenise('hello world')).toEqual(['hello ', 'world']);
    expect(tokenise('سلام دنیا')).toEqual(['سلام ', 'دنیا']);
    expect(''.concat(...tokenise('one two three'))).toBe('one two three');
  });

  it('hard-splits over-long runs', () => {
    const long = 'x'.repeat(30);
    const pieces = tokenise(long, 12);
    expect(pieces.length).toBe(3);
    expect(pieces.join('')).toBe(long);
  });
});

describe('EchoBridgeTransport', () => {
  let t: EchoBridgeTransport;

  beforeEach(() => {
    t = new EchoBridgeTransport();
  });

  it('creates, lists, gets, renames, and deletes sessions', async () => {
    const created = await t.request('id', 'session.create', { title: 'Hi' });
    const sid = (created as { session_id: string }).session_id;

    const listed = await t.request('id', 'session.list', {});
    expect((listed as { sessions: { id: string }[] }).sessions[0].id).toBe(sid);

    const got = await t.request('id', 'session.get', { session_id: sid });
    expect((got as { title: string }).title).toBe('Hi');

    const renamed = await t.request('id', 'session.rename', {
      session_id: sid,
      title: 'Yo',
    });
    expect((renamed as { title: string }).title).toBe('Yo');

    await t.request('id', 'session.delete', { session_id: sid });
    const after = await t.request('id', 'session.list', {});
    expect((after as { sessions: unknown[] }).sessions).toHaveLength(0);
  });

  it('streams a conversation and resolves with the final turn', async () => {
    const created = await t.request('1', 'session.create', {});
    const sid = (created as { session_id: string }).session_id;
    const chunks: StreamChunkLike[] = [];
    const result = await t.request<{ reply: string }>(
      '2',
      'conversation.send',
      { session_id: sid, message: 'hello there' },
      (c) => chunks.push(c),
    );
    expect(result.reply).toBe('Echo: hello there');
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks.map((c) => c.token).join('')).toBe('Echo: hello there');
  });

  it('rejects unknown methods with METHOD_NOT_FOUND', async () => {
    await expect(t.request('id', 'bogus.method', {})).rejects.toMatchObject({
      code: RPC_ERROR.METHOD_NOT_FOUND,
    });
  });

  it('answers health, version, provider, and tool.list', async () => {
    expect((await t.request<{ status: string }>('id', 'health.check', {})).status).toBe('ok');
    expect((await t.request<{ protocol: string }>('id', 'sidecar.version', {})).protocol).toBe(
      '1.0',
    );
    const providers = await t.request<{ default: string }>('id', 'provider.list', {});
    expect(providers.default).toBe('echo');
    const tools = await t.request<{ tools: { name: string }[] }>('id', 'tool.list', {});
    expect(tools.tools.map((t2) => t2.name)).toContain('calculate');
  });
});

describe('BridgeClient', () => {
  let client: BridgeClient;

  beforeEach(() => {
    client = new BridgeClient(new EchoBridgeTransport());
  });

  it('call returns the result and increments request ids', async () => {
    const transport = new EchoBridgeTransport();
    const spy = vi.spyOn(transport, 'request');
    const client = new BridgeClient(transport);
    await client.call('health.check');
    await client.call('health.check');
    // The first two calls use ids 1 and 2.
    expect(spy.mock.calls[0]?.[0]).toBe(1);
    expect(spy.mock.calls[1]?.[0]).toBe(2);
  });

  it('stream routes chunks through onChunk and the event emitter', async () => {
    const transport = new EchoBridgeTransport();
    const client = new BridgeClient(transport);
    const viaEvent: string[] = [];
    const viaCallback: string[] = [];
    const off = client.on((e) => {
      if (e.type === 'chunk') viaEvent.push(e.chunk.token);
    });
    const created = await client.call<{ session_id: string }>('session.create');
    const result = await client.stream<{ reply: string }>(
      'conversation.send',
      { session_id: created.session_id, message: 'abc' },
      { onChunk: (c) => viaCallback.push(c.token) },
    );
    expect(result.reply).toBe('Echo: abc');
    // Each chunk is delivered through both the event emitter and the callback.
    expect(viaEvent.join('')).toBe('Echo: abc');
    expect(viaCallback.join('')).toBe('Echo: abc');
    off();
  });

  it('emits an error event and rejects on failure', async () => {
    const errors: BridgeRpcError[] = [];
    client.on((e) => {
      if (e.type === 'error') errors.push(e.error);
    });
    await expect(client.call('bogus.method')).rejects.toBeInstanceOf(BridgeRpcError);
    expect(errors).toHaveLength(1);
    expect(errors[0].code).toBe(RPC_ERROR.METHOD_NOT_FOUND);
  });

  it('starts ready on the echo transport', () => {
    expect(client.state).toBe('ready');
    expect(client.isFallback).toBe(false); // transport was explicitly provided
  });
});

describe('BridgeRpcError', () => {
  it('classifies retryable and approval errors', () => {
    const rl = new BridgeRpcError({ code: RPC_ERROR.RATE_LIMITED, message: 'slow down' });
    expect(rl.isRetryable).toBe(true);
    expect(rl.isApprovalRequired).toBe(false);

    const appr = new BridgeRpcError({
      code: RPC_ERROR.APPROVAL_REQUIRED,
      message: 'needs approval',
      data: { approval_id: 'appr_123', risk: 'dangerous' },
    });
    expect(appr.isApprovalRequired).toBe(true);
    expect(appr.approvalId).toBe('appr_123');
    expect(appr.isRetryable).toBe(false);
  });

  it('toBridgeError normalises strings and objects', () => {
    expect(toBridgeError('boom').code).toBe(RPC_ERROR.INTERNAL_ERROR);
    expect(toBridgeError({ code: -32602, message: 'bad params' }).code).toBe(-32602);
    const existing = new BridgeRpcError({ code: -1, message: 'x' });
    expect(toBridgeError(existing)).toBe(existing);
  });
});

interface StreamChunkLike {
  id: unknown;
  token: string;
}
