/**
 * Telegram report bot studio (v4.7).
 *
 * Controls the real long-polling bot inside the Python core: photo → Persian
 * OCR, voice → transcription, text → structured report — every path ends in a
 * Persian PDF sent straight back into the Telegram chat. In the browser
 * preview (echo transport) every state is a clearly-flagged demo.
 */

import { useEffect, useState } from 'react';
import { Bot, Radio, Send } from 'lucide-react';

import type { BridgeClient } from '@/lib/bridge/client';
import type { ReportBotStatus } from '@/lib/bridge/reportbot';
import { reportbotStart, reportbotStatus, reportbotStop } from '@/lib/bridge/reportbot';

const KIND_LABELS: Record<string, string> = {
  started: 'بات روشن شد',
  stopped: 'بات خاموش شد',
  help_sent: 'راهنما ارسال شد',
  photo_report: 'عکس → OCR → PDF',
  voice_report: 'صوت → رونویسی → PDF',
  text_report: 'متن → PDF',
  error: 'خطا',
  poll_error: 'خطای اتصال',
};

function describeEvent(kind: string, detail: Record<string, unknown>): string {
  const n = (key: string) => Number(detail[key] ?? 0);
  switch (kind) {
    case 'photo_report':
      return `${n('ocr_chars')} نویسه OCR · ${n('fields')} فیلد · ${n('pdf_pages')} صفحه PDF`;
    case 'voice_report':
      return `${n('duration_s')} ثانیه صوت · ${n('transcript_chars')} نویسه رونویسی`;
    case 'text_report':
      return `${n('text_chars')} نویسه متن · ${n('pdf_pages')} صفحه PDF`;
    case 'error':
    case 'poll_error':
      return typeof detail.message === 'string' ? detail.message : '';
    default:
      return '';
  }
}

export function TelegramBotStudio({ client }: { client: BridgeClient }) {
  const demo = client.transportKind === 'echo';
  const [token, setToken] = useState('');
  const [relayUrl, setRelayUrl] = useState('');
  const [status, setStatus] = useState<ReportBotStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initial state read — setState only ever lands in the async callback.
  useEffect(() => {
    let cancelled = false;
    void reportbotStatus(client)
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch(() => {
        /* status polling is best-effort */
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  // Live event log while a real bot is running (demo states never poll).
  useEffect(() => {
    if (!status?.running || status.demo) return;
    const timer = setInterval(() => {
      void reportbotStatus(client)
        .then((next) => setStatus(next))
        .catch(() => {
          /* keep the last known state */
        });
    }, 2000);
    return () => clearInterval(timer);
  }, [status?.running, status?.demo, client]);

  const handleStart = () => {
    const trimmed = token.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    void reportbotStart(client, trimmed, relayUrl)
      .then((next) => setStatus(next))
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => setBusy(false));
  };

  const handleStop = () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    void reportbotStop(client)
      .then((next) => setStatus(next))
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => setBusy(false));
  };

  const running = status?.running ?? false;
  const events = [...(status?.events ?? [])].reverse().slice(0, 12);

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-4" dir="rtl">
      {/* Pipeline banner */}
      <div className="flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 p-3">
        <Bot className="size-4 shrink-0 text-sky-300" aria-hidden="true" />
        <p className="text-[11px] leading-relaxed text-sky-100">
          زنجیره گزارش خودکار: <b>عکس → OCR فارسی</b> · <b>صوت → رونویسی</b> ·{' '}
          <b>متن → گزارش ساخت‌یافته</b> — خروجی هر مسیر، PDF فارسی با حروف متصل است که همان‌جا در چت
          تلگرام تحویل داده می‌شود. همه پردازش‌ها محلی است.
        </p>
      </div>

      {/* Control row */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-white/[0.08] bg-zinc-950/40 p-3.5">
        <input
          value={token}
          onChange={(e) => setToken(e.target.value)}
          type="password"
          placeholder="123456789:AA… — توکن BotFather"
          className="min-w-52 flex-1 rounded-lg border border-white/10 bg-zinc-900 px-2.5 py-1.5 font-mono text-[11px] text-zinc-300 placeholder-zinc-600 focus:outline-none"
          dir="ltr"
          aria-label="BotFather token"
        />
        <input
          value={relayUrl}
          onChange={(e) => setRelayUrl(e.target.value)}
          type="text"
          placeholder="https://relay.example — پایه API جایگزین (اختیاری)"
          className="min-w-44 flex-1 rounded-lg border border-white/10 bg-zinc-900 px-2.5 py-1.5 font-mono text-[11px] text-zinc-300 placeholder-zinc-600 focus:outline-none"
          dir="ltr"
          aria-label="Optional relay API base URL"
        />
        {running ? (
          <button
            onClick={handleStop}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-1.5 text-[11px] font-bold text-rose-200 transition-all hover:bg-rose-500/20 disabled:opacity-40"
          >
            <Radio className="size-3.5" aria-hidden="true" />
            {busy ? '…' : 'توقف بات'}
          </button>
        ) : (
          <button
            onClick={handleStart}
            disabled={!token.trim() || busy}
            className="flex items-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-[11px] font-bold text-sky-200 transition-all hover:bg-sky-500/20 disabled:opacity-40"
          >
            <Send className="size-3.5" aria-hidden="true" />
            {busy ? 'در حال راه‌اندازی…' : 'راه‌اندازی بات'}
          </button>
        )}
      </div>

      {/* Status chips */}
      <div className="flex flex-wrap items-center gap-2 font-mono text-[10px]">
        <span
          className={`rounded-md border px-2 py-1 ${
            running
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-white/10 bg-zinc-900 text-zinc-400'
          }`}
        >
          {running ? '● RUNNING' : '○ STOPPED'}
        </span>
        {status?.connected && (
          <span className="rounded-md border border-sky-500/40 bg-sky-500/10 px-2 py-1 text-sky-300">
            ● POLLING
          </span>
        )}
        {status?.token_fingerprint && (
          <span
            className="rounded-md border border-white/10 bg-zinc-900 px-2 py-1 text-zinc-400"
            dir="ltr"
          >
            TOKEN {status.token_fingerprint}
          </span>
        )}
        <span className="rounded-md border border-white/10 bg-zinc-900 px-2 py-1 text-zinc-400">
          UPDATES {status?.updates_processed ?? 0}
        </span>
        {(demo || status?.demo) && (
          <span className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-300">
            DEMO · بات واقعی در اپ دسکتاپ اجرا می‌شود
          </span>
        )}
      </div>

      {error && (
        <p
          className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2.5 font-mono text-[10px] text-rose-300"
          dir="ltr"
        >
          ⚠ {error}
        </p>
      )}

      {/* Event log */}
      <div className="flex-1 rounded-xl border border-white/[0.08] bg-zinc-950/40 p-3">
        <p className="mb-2 font-mono text-[10px] text-zinc-500" dir="ltr">
          EVENT LOG · reportbot.status · last {events.length}
        </p>
        {events.length === 0 ? (
          <p className="py-6 text-center text-[11px] text-zinc-500">
            بات هنوز پیامی پردازش نکرده — توکن BotFather را وارد و «راه‌اندازی بات» را بزنید.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {events.map((event, index) => (
              <li
                key={`${event.ts}-${index}`}
                className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-zinc-900/60 px-2.5 py-1.5"
              >
                <span
                  className={`size-1.5 shrink-0 rounded-full ${
                    event.kind === 'error' || event.kind === 'poll_error'
                      ? 'bg-rose-400'
                      : event.kind === 'photo_report' ||
                          event.kind === 'voice_report' ||
                          event.kind === 'text_report'
                        ? 'bg-emerald-400'
                        : 'bg-zinc-500'
                  }`}
                  aria-hidden="true"
                />
                <span className="shrink-0 text-[11px] font-bold text-zinc-200">
                  {KIND_LABELS[event.kind] ?? event.kind}
                </span>
                {describeEvent(event.kind, event.detail) && (
                  <span className="truncate text-[10px] text-zinc-500">
                    {describeEvent(event.kind, event.detail)}
                  </span>
                )}
                <span className="ms-auto shrink-0 font-mono text-[9px] text-zinc-600" dir="ltr">
                  {event.chat_id != null ? `chat ${event.chat_id}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="font-mono text-[9px] text-zinc-600" dir="ltr">
        REPORTBOT BRIDGE · reportbot.start / stop / status · long polling · token redacted
      </p>
    </div>
  );
}
