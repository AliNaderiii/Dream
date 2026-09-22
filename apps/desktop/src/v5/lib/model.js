/**
 * Direct model client (BYOK) — the honest chat path.
 *
 * The Python core has no LLM-chat bridge method (its gateway credentials
 * cannot travel over RPC by design), so — exactly like Open Science Desktop —
 * the workbench talks to the model provider directly from the app:
 *
 *   - provider "ollama": POST {baseUrl}/api/chat        {model, messages}
 *   - provider "openai": POST {baseUrl}/v1/chat/completions (Bearer key)
 *
 * Credentials live only in the app's localStorage, on the user's machine.
 * No streaming, no simulation: a real HTTP call or a real, clear error.
 */

export class ModelError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ModelError';
  }
}

/**
 * @param {{provider:string, baseUrl:string, apiKey:string, model:string}} cfg
 * @param {Array<{role:'system'|'user'|'assistant', content:string}>} messages
 * @returns {Promise<{text:string, engine:string, latencyMs:number}>}
 */
export async function chatComplete(cfg, messages) {
  if (!cfg || cfg.provider === 'none' || !cfg.model) {
    throw new ModelError('مدلی تنظیم نشده — از «تنظیمات → مدل» یک مدل وصل کنید.');
  }
  const base = (cfg.baseUrl || '').trim().replace(/\/+$/, '');
  if (!base) {
    throw new ModelError('آدرس سرور مدل خالی است — در تنظیمات وارد کنید.');
  }
  const started = performance.now();
  let res;
  try {
    if (cfg.provider === 'ollama') {
      res = await fetch(`${base}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: cfg.model, messages, stream: false }),
      });
    } else {
      res = await fetch(`${base}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {}),
        },
        body: JSON.stringify({ model: cfg.model, messages }),
      });
    }
  } catch (e) {
    throw new ModelError(
      `اتصال به سرور مدل برقرار نشد (${base}) — Ollama را با «ollama serve» روشن کنید یا آدرس/کلید را بررسی کنید.`,
    );
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new ModelError(`سرور مدل خطای HTTP ${res.status} داد. ${detail.slice(0, 180)}`);
  }
  const data = await res.json().catch(() => null);
  const text =
    cfg.provider === 'ollama'
      ? data?.message?.content
      : data?.choices?.[0]?.message?.content;
  if (!text) {
    throw new ModelError('پاسخ مدل خالی یا غیرمنتظره بود.');
  }
  return {
    text: String(text).trim(),
    engine: `${cfg.provider === 'ollama' ? 'Ollama' : 'API'} · ${cfg.model}`,
    latencyMs: Math.round(performance.now() - started),
  };
}
