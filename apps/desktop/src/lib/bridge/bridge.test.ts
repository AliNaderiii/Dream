import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BridgeClient, EchoBridgeTransport, tokenise } from '@/lib/bridge/client';
import type { BridgeTransport } from '@/lib/bridge/client';
import { BridgeRpcError, toBridgeError } from '@/lib/bridge/errors';
import { RPC_ERROR } from '@/lib/bridge/types';
import type { RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

class HangingTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  request<T>(): Promise<T> {
    return new Promise<T>(() => undefined);
  }
  onState(): () => void {
    return () => undefined;
  }
  reconnect(): void {}
}

class LateChunkTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private onChunk?: (chunk: StreamChunk) => void;

  request<T>(
    _id: RpcId,
    _method: string,
    _params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    this.onChunk = onChunk;
    return new Promise<T>(() => undefined);
  }

  emit(chunk: StreamChunk) {
    this.onChunk?.(chunk);
  }

  onState(): () => void {
    return () => undefined;
  }

  reconnect(): void {}
}

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

  it('bounds every call with a caller-adjustable timeout', async () => {
    const bounded = new BridgeClient(new HangingTransport());
    await expect(bounded.call('slow.method', {}, { timeoutMs: 5 })).rejects.toMatchObject({
      message: 'slow.method timed out after 5ms',
      kind: 'timeout',
      code: RPC_ERROR.INTERNAL_ERROR,
    });
  });

  it('cancels a bounded call through AbortSignal', async () => {
    const bounded = new BridgeClient(new HangingTransport());
    const controller = new AbortController();
    const pending = bounded.call('cancel.method', {}, { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({
      message: 'cancel.method was cancelled',
      kind: 'cancelled',
    });
  });

  it('rejects immediately when the signal is already aborted', async () => {
    const transport = new HangingTransport();
    const bounded = new BridgeClient(transport);
    const controller = new AbortController();
    controller.abort();
    const err = await bounded
      .call('pre.aborted', {}, { signal: controller.signal, timeoutMs: 10_000 })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(BridgeRpcError);
    expect((err as BridgeRpcError).isCancelled).toBe(true);
    expect((err as BridgeRpcError).isTimeout).toBe(false);
  });

  it('timeouts and cancellations are typed errors that reach error listeners', async () => {
    const bounded = new BridgeClient(new HangingTransport());
    const seen: BridgeRpcError[] = [];
    bounded.on((e) => {
      if (e.type === 'error') seen.push(e.error);
    });
    const controller = new AbortController();
    const cancelled = bounded.call('c', {}, { signal: controller.signal });
    controller.abort();
    await expect(cancelled).rejects.toBeInstanceOf(BridgeRpcError);
    await expect(bounded.call('t', {}, { timeoutMs: 1 })).rejects.toBeInstanceOf(BridgeRpcError);
    expect(seen.map((e) => e.kind)).toEqual(['cancelled', 'timeout']);
    expect(seen.every((e) => !e.isRetryable && !e.isApprovalRequired)).toBe(true);
  });

  it('bounds streams independently from calls', async () => {
    const bounded = new BridgeClient(new HangingTransport());
    await expect(bounded.stream('slow.stream', {}, { timeoutMs: 5 })).rejects.toMatchObject({
      message: 'slow.stream timed out after 5ms',
      kind: 'timeout',
    });
  });

  it('issues distinct increasing numeric ids below the shell reserved band', async () => {
    const ids: RpcId[] = [];
    const recording: BridgeTransport = {
      kind: 'echo',
      request<T>(id: RpcId): Promise<T> {
        ids.push(id);
        return Promise.resolve(null as T);
      },
      onState: () => () => undefined,
      reconnect: () => undefined,
    };
    const c = new BridgeClient(recording);
    await c.call('a');
    await c.call('b');
    await c.stream('c', {});
    expect(ids).toEqual([1, 2, 3]);
    for (const id of ids) {
      expect(typeof id).toBe('number');
      expect(Number.isSafeInteger(id)).toBe(true);
      expect(id as number).toBeLessThan(2 ** 62);
    }
  });

  it('cancels a stream and suppresses chunks that arrive after settlement', async () => {
    const transport = new LateChunkTransport();
    const bounded = new BridgeClient(transport);
    const controller = new AbortController();
    const chunks: string[] = [];
    const events: string[] = [];
    bounded.on((event) => {
      if (event.type === 'chunk') events.push(event.chunk.token);
    });
    const pending = bounded.stream(
      'cancel.stream',
      {},
      {
        signal: controller.signal,
        onChunk: (chunk) => chunks.push(chunk.token),
      },
    );
    controller.abort();
    await expect(pending).rejects.toMatchObject({ message: 'cancel.stream was cancelled' });
    transport.emit({ id: 'late', token: 'ignored' });
    expect(chunks).toEqual([]);
    expect(events).toEqual([]);
  });

  it('starts ready on the echo transport', () => {
    expect(client.state).toBe('ready');
    expect(client.isFallback).toBe(false); // transport was explicitly provided
  });

  it('isUsingFallback is false when echo is provided explicitly', () => {
    expect(client.isUsingFallback).toBe(false);
  });
});

describe('BridgeClient echo fallback (S15)', () => {
  it('memory.list works via echo transport', async () => {
    const transport = new EchoBridgeTransport();
    const client = new BridgeClient(transport);

    // Echo should handle memory.list
    const result = await client.call<{ memories: unknown[] }>('memory.list');
    expect(result.memories).toBeDefined();
    expect(Array.isArray(result.memories)).toBe(true);
    // Echo has seed memories
    expect(result.memories.length).toBeGreaterThan(0);
  });

  it('conversation.send works via echo transport', async () => {
    const transport = new EchoBridgeTransport();
    const client = new BridgeClient(transport);

    // Create a session first
    const { session_id } = await client.call<{ session_id: string }>('session.create');

    // Echo should handle conversation.send
    const result = await client.call<{ reply: string }>('conversation.send', {
      session_id,
      message: 'Hello',
    });

    // Echo reply format
    expect(result.reply).toBe('Echo: Hello');
  });

  it('session.create works via echo transport', async () => {
    const transport = new EchoBridgeTransport();
    const client = new BridgeClient(transport);

    const result = await client.call<{ session_id: string }>('session.create');
    expect(result.session_id).toBeDefined();
    expect(result.session_id).toMatch(/^echo-\d+$/);
  });

  it('skill.list works via echo transport', async () => {
    const transport = new EchoBridgeTransport();
    const client = new BridgeClient(transport);

    const result = await client.call<{ skills: unknown[] }>('skill.list');
    expect(result.skills).toBeDefined();
    expect(Array.isArray(result.skills)).toBe(true);
    // Echo has seed skills
    expect(result.skills.length).toBeGreaterThan(0);
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

  it('classifies shell transport errors from data.kind without changing codes', () => {
    // What the Rust shell serialises for not-connected / sidecar restarted.
    const notConnected = toBridgeError({
      code: RPC_ERROR.INTERNAL_ERROR,
      message: 'bridge is not connected',
      data: { kind: 'transport' },
    });
    expect(notConnected.kind).toBe('transport');
    expect(notConnected.isTransport).toBe(true);
    expect(notConnected.code).toBe(RPC_ERROR.INTERNAL_ERROR);
    expect(notConnected.isRetryable).toBe(false);

    // A sidecar INTERNAL_ERROR with the same code but no tag stays `rpc`.
    const handler = toBridgeError({ code: RPC_ERROR.INTERNAL_ERROR, message: 'boom' });
    expect(handler.kind).toBe('rpc');
    expect(handler.isTransport).toBe(false);

    // Unknown tags (future shells) fall back to `rpc`, never throw.
    const odd = toBridgeError({ code: -32603, message: 'x', data: { kind: 42 } });
    expect(odd.kind).toBe('rpc');

    // Structured data such as approval_id is preserved alongside the kind.
    const approval = toBridgeError({
      code: RPC_ERROR.APPROVAL_REQUIRED,
      message: 'approve',
      data: { approval_id: 'a1' },
    });
    expect(approval.kind).toBe('rpc');
    expect(approval.approvalId).toBe('a1');
  });

  it('a string thrown by a Tauri command is an untyped rpc error', () => {
    const err = toBridgeError('window not found');
    expect(err.kind).toBe('rpc');
    expect(err.message).toBe('window not found');
  });
});

interface StreamChunkLike {
  id: unknown;
  token: string;
}
