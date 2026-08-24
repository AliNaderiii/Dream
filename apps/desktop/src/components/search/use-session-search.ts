/**
 * Data hook for the session-search dialog (MEM Stage F).
 *
 * Owns the index-health read, the debounced query, the fail-closed refusal
 * and the rebuild — so the dialog stays rendering. Reads are bounded
 * (15 s) and every effect is cancellable; state updates never happen after
 * an abort.
 */

import { useCallback, useEffect, useState } from 'react';

import { useBridge } from '@/lib/bridge/hooks';
import type { EchoSessionHit } from '@/lib/bridge/echo-search';

/** Wire shape returned by `search.sessions.status`. */
export interface IndexStatus {
  healthy: boolean;
  documents: number;
}

const READ_TIMEOUT_MS = 15_000;
const WRITE_TIMEOUT_MS = 10_000;
const QUERY_DEBOUNCE_MS = 250;

export interface SessionSearchState {
  status: IndexStatus | null;
  /** The raw query text, so the dialog input stays controlled. */
  query: string;
  results: EchoSessionHit[];
  searching: boolean;
  /** The fail-closed index refusal, when the index is corrupt. */
  refusal: string | null;
  error: string | null;
  rebuilding: boolean;
  rebuild: () => Promise<void>;
  runQuery: (query: string) => void;
}

/** Drives the search.sessions family while the dialog is open. */
export function useSessionSearch(open: boolean): SessionSearchState {
  const { client } = useBridge();
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [results, setResults] = useState<EchoSessionHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [retryToken, setRetryToken] = useState(0);
  // The raw query is state, not a ref — refs read during render are banned.
  const [query, setQuery] = useState('');

  const readStatus = useCallback(
    async (signal?: AbortSignal) => {
      const fresh = await client.call<IndexStatus>(
        'search.sessions.status',
        {},
        { timeoutMs: READ_TIMEOUT_MS, signal },
      );
      setStatus(fresh);
    },
    [client],
  );

  // Index health follows the dialog; a corrupt index refuses here already.
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const load = async () => {
      setRefusal(null);
      setError(null);
      try {
        await readStatus(controller.signal);
      } catch (err) {
        if (controller.signal.aborted) return;
        setRefusal(err instanceof Error ? err.message : String(err));
      }
    };
    // Deferred so no setState runs synchronously in the effect body.
    void Promise.resolve().then(() => void load());
    return () => controller.abort();
  }, [open, readStatus, rebuilding]);

  // Debounced, cancellable query. The raw text stays controlled by the
  // dialog input; the trimmed text drives the request.
  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    void retryToken;
    if (!trimmed) {
      const clear = () => {
        setResults([]);
        setSearching(false);
        setError(null);
      };
      // Deferred: no setState runs synchronously in the effect body.
      void Promise.resolve().then(clear);
      return;
    }
    const controller = new AbortController();
    void Promise.resolve().then(() => setSearching(true));
    const timer = setTimeout(() => {
      const run = async () => {
        try {
          const out = await client.call<{ results: EchoSessionHit[] }>(
            'search.sessions.query',
            { query: trimmed },
            { timeoutMs: READ_TIMEOUT_MS, signal: controller.signal },
          );
          if (controller.signal.aborted) return;
          setResults(out.results);
          setRefusal(null);
          setError(null);
        } catch (err) {
          if (controller.signal.aborted) return;
          setResults([]);
          const message = err instanceof Error ? err.message : String(err);
          const isRefusal = message.includes('rebuil') || message.includes('unreadable');
          setRefusal(isRefusal ? message : null);
          setError(isRefusal ? null : message);
        } finally {
          if (!controller.signal.aborted) setSearching(false);
        }
      };
      void run();
    }, QUERY_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [client, open, query, retryToken]);

  const rebuild = useCallback(async () => {
    setRebuilding(true);
    try {
      await client.call('search.sessions.rebuild', {}, { timeoutMs: WRITE_TIMEOUT_MS });
      setRefusal(null);
      await readStatus();
      // The pending query re-runs against the rebuilt index.
      setRetryToken((token) => token + 1);
    } finally {
      setRebuilding(false);
    }
  }, [client, readStatus]);

  return {
    status,
    query,
    results,
    searching,
    refusal,
    error,
    rebuilding,
    rebuild,
    runQuery: setQuery,
  };
}
