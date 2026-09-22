import { afterEach, describe, expect, it, vi } from 'vitest';
import { chatComplete, ModelError } from './model.js';

const CFG_OLLAMA = {
  provider: 'ollama',
  baseUrl: 'http://localhost:11434',
  apiKey: '',
  model: 'qwen2.5:7b',
};
const CFG_OPENAI = {
  provider: 'openai',
  baseUrl: 'https://api.example.com',
  apiKey: 'sk-test',
  model: 'gpt-x',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('chatComplete', () => {
  it('posts to Ollama /api/chat and returns message.content', async () => {
    const fetchMock = vi.fn(async (url, init) => {
      expect(url).toBe('http://localhost:11434/api/chat');
      const body = JSON.parse(init.body);
      expect(body.model).toBe('qwen2.5:7b');
      expect(body.messages).toHaveLength(1);
      expect(body.stream).toBe(false);
      return new Response(JSON.stringify({ message: { content: 'سلام' } }), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const out = await chatComplete(CFG_OLLAMA, [{ role: 'user', content: 'سلام' }]);
    expect(out.text).toBe('سلام');
    expect(out.engine).toContain('Ollama');
    expect(out.latencyMs).toBeGreaterThanOrEqual(0);
  });

  it('posts to OpenAI-compatible /v1/chat/completions with bearer auth', async () => {
    const fetchMock = vi.fn(async (url, init) => {
      expect(url).toBe('https://api.example.com/v1/chat/completions');
      expect(init.headers.Authorization).toBe('Bearer sk-test');
      const body = JSON.parse(init.body);
      expect(body.model).toBe('gpt-x');
      return new Response(JSON.stringify({ choices: [{ message: { content: 'پاسخ' } }] }), {
        status: 200,
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const out = await chatComplete(CFG_OPENAI, [{ role: 'user', content: 'hi' }]);
    expect(out.text).toBe('پاسخ');
  });

  it('rejects with a Persian ModelError when no model is configured', async () => {
    await expect(chatComplete({ provider: 'none' }, [])).rejects.toBeInstanceOf(ModelError);
    await expect(chatComplete(null, [])).rejects.toThrow(/مدلی تنظیم نشده/);
  });

  it('rejects when the base URL is empty', async () => {
    await expect(chatComplete({ ...CFG_OLLAMA, baseUrl: '' }, [])).rejects.toThrow(
      /آدرس سرور مدل خالی/,
    );
  });

  it('surfaces HTTP errors honestly', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('boom', { status: 500 })),
    );
    await expect(chatComplete(CFG_OLLAMA, [])).rejects.toThrow(/HTTP 500/);
  });

  it('surfaces connection failures with a fix hint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    await expect(chatComplete(CFG_OLLAMA, [])).rejects.toThrow(/ollama serve/);
  });

  it('rejects on empty model responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({}), { status: 200 })),
    );
    await expect(chatComplete(CFG_OLLAMA, [])).rejects.toThrow(/پاسخ مدل خالی/);
  });
});
