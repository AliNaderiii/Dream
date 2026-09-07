/**
 * Web Gateway settings UI — token management, effective bind state.
 *
 * Raw tokens are shown only once (after create/rotate). Stored token rows are
 * always masked and identified by a non-secret id. No token is ever placed in
 * a URL, QR payload, or link.
 *
 * Stacked full-width layout on narrow viewports so all content remains
 * reachable without horizontal scrolling or side-by-side truncation.
 */

import { Copy, Key, Plus, RefreshCw, Shield, Trash2, Wifi, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import type {
  GatewayBind,
  GatewayConnection,
  GatewayStatus,
  GatewayTokenInfo,
} from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

interface IssuedToken {
  token: string;
  scope: string;
  label: string;
}

export function GatewaySettings() {
  const { call } = useBridge();
  const [status, setStatus] = useState<GatewayStatus | null>(null);
  const [tokens, setTokens] = useState<GatewayTokenInfo[]>([]);
  const [connections] = useState<GatewayConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gatewayEnabled, setGatewayEnabled] = useState(true);
  const [newTokenResult, setNewTokenResult] = useState<IssuedToken | null>(null);
  const [copiedToken, setCopiedToken] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusResult, tokensResult] = await Promise.all([
        call<GatewayStatus>('gateway.status'),
        call<{ tokens: GatewayTokenInfo[] }>('gateway.get_tokens'),
      ]);
      setStatus(statusResult);
      setTokens(tokensResult.tokens);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load gateway state');
    } finally {
      setLoading(false);
    }
  }, [call]);

  useEffect(() => {
    let ignore = false;
    const run = async () => {
      if (!gatewayEnabled) return;
      setLoading(true);
      setError(null);
      try {
        const [statusResult, tokensResult] = await Promise.all([
          call<GatewayStatus>('gateway.status'),
          call<{ tokens: GatewayTokenInfo[] }>('gateway.get_tokens'),
        ]);
        if (!ignore) {
          setStatus(statusResult);
          setTokens(tokensResult.tokens);
        }
      } catch (err: unknown) {
        if (!ignore) setError(err instanceof Error ? err.message : 'Failed to load gateway state');
      } finally {
        if (!ignore) setLoading(false);
      }
    };
    void run();
    return () => {
      ignore = true;
    };
  }, [gatewayEnabled, call]);

  const handleCreateToken = async (scope: 'read' | 'write') => {
    setError(null);
    try {
      const result = await call<IssuedToken>('gateway.create_token', {
        scope,
        label: scope === 'write' ? 'Full Access' : 'Read Only',
      });
      setNewTokenResult(result);
      void refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create token');
    }
  };

  const handleRotateToken = async (tokenId: string) => {
    setError(null);
    try {
      const result = await call<{ token: string }>('gateway.rotate_token', {
        token: tokenId,
      });
      setNewTokenResult({ token: result.token, scope: 'write', label: 'Rotated' });
      void refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to rotate token');
    }
  };

  const handleRevokeToken = async (tokenId: string) => {
    setError(null);
    try {
      await call('gateway.revoke_token', { token: tokenId });
      setNewTokenResult(null);
      void refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to revoke token');
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedToken(text.slice(0, 12));
      setTimeout(() => setCopiedToken(null), 2000);
    } catch {
      // Fallback: select text
    }
  };

  const bind: GatewayBind | undefined = status?.bind;
  const connectUrl = bind ? `http://${bind.host}:${bind.port}/` : null;

  return (
    <section>
      <h2 className="pb-2 text-h2 font-semibold">Web Gateway</h2>

      {/* Enable toggle — stacked: description then button below at narrow widths */}
      <div className="border-b border-border-default py-3">
        <p className="text-body font-medium">Enable web gateway</p>
        <p className="text-caption text-fg-secondary">
          Access Dream from your phone, tablet, or another computer on your LAN
        </p>
        <Button
          size="sm"
          variant={gatewayEnabled ? 'primary' : 'secondary'}
          aria-pressed={gatewayEnabled}
          className="mt-2 w-full"
          onClick={() => setGatewayEnabled((v) => !v)}
        >
          {gatewayEnabled ? 'On' : 'Off'}
        </Button>
      </div>

      {gatewayEnabled && (
        <>
          {/* Status row — stacked: info then refresh below */}
          <div className="border-b border-border-default py-3">
            <p className="text-body font-medium">Status</p>
            <p className="text-caption text-fg-secondary">
              {status?.has_setup_token
                ? 'Gateway ready — connect using a bearer token'
                : 'No tokens configured — create one to enable access'}
            </p>
            {error && <p className="mt-1 text-caption text-danger-fg">{error}</p>}
            <Button
              size="sm"
              variant="secondary"
              className="mt-2 w-full"
              onClick={() => {
                void refresh();
              }}
              disabled={loading}
            >
              {loading ? '…' : <RefreshCw className="mr-1 size-3" />}
              <span className="ml-1">Refresh</span>
            </Button>
          </div>

          {/* Exposure row — full-width connection URL */}
          <div className="border-b border-border-default py-3">
            <p className="text-body font-medium mb-2">
              <Wifi className="mr-1 inline size-3" />
              Exposure
            </p>
            {bind ? (
              <div className="w-full space-y-1">
                <p className="w-full font-mono text-caption">{connectUrl}</p>
                <p className="text-caption text-fg-muted">
                  {bind.leaves_machine
                    ? 'This gateway is reachable from your LAN. Only the owner should have a token.'
                    : 'Loopback only: this gateway is reachable from this machine only.'}
                </p>
                {bind.leaves_machine && (
                  <p className="text-caption text-fg-muted">
                    The desktop is not served over trusted public TLS by default. Use it only on a
                    network you trust.
                  </p>
                )}
              </div>
            ) : (
              <p className="text-caption text-fg-muted">Gateway status unavailable.</p>
            )}
          </div>

          {/* Token management — stacked full-width rows */}
          <div className="border-b border-border-default py-3">
            <p className="text-body font-medium mb-2">
              <Key className="mr-1 inline size-3" />
              Authentication Tokens
            </p>

            {/* Existing tokens (masked metadata only) */}
            {tokens.length > 0 && (
              <div className="w-full mb-3 space-y-2">
                {tokens.map((row) => (
                  <div
                    key={row.id}
                    className="w-full flex flex-col gap-2 rounded-xs border border-border-default bg-surface-raised p-3"
                  >
                    <div className="w-full flex items-center gap-2">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-caption font-medium',
                          row.scope === 'write'
                            ? 'bg-success-fg/10 text-success-fg'
                            : 'bg-fg-muted/10 text-fg-muted',
                        )}
                      >
                        {row.scope === 'write' ? 'Full' : 'Read'}
                      </span>
                      <code className="ltr-island w-full truncate text-caption text-fg-muted">
                        {row.prefix}
                      </code>
                    </div>
                    <p className="text-caption text-fg-muted">
                      {row.label} &middot;{' '}
                      {row.last_used_at
                        ? `Last used ${new Date(row.last_used_at * 1000).toLocaleString()}`
                        : 'Never used'}
                    </p>
                    <div className="w-full flex items-center gap-2 justify-end">
                      <button
                        type="button"
                        onClick={() => {
                          void handleRotateToken(row.id);
                        }}
                        className="rounded-xs p-2 text-fg-muted hover:text-fg-primary"
                        title="Rotate (regenerate) token"
                      >
                        <RefreshCw className="size-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void handleRevokeToken(row.id);
                        }}
                        className="rounded-xs p-2 text-danger-fg hover:text-danger-fg"
                        title="Revoke token"
                      >
                        <Trash2 className="size-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Create new token — stacked full-width buttons */}
            <div className="w-full flex flex-col gap-2">
              <Button
                size="sm"
                className="w-full"
                onClick={() => {
                  void handleCreateToken('write');
                }}
              >
                <Plus className="mr-1 size-3" />
                New Full Access Token
              </Button>
              <Button
                size="sm"
                variant="secondary"
                className="w-full"
                onClick={() => {
                  void handleCreateToken('read');
                }}
              >
                <Plus className="mr-1 size-3" />
                New Read-Only Token
              </Button>
            </div>

            {/* Newly created/rotated token — shown exactly once */}
            {newTokenResult && (
              <div className="mt-3 rounded-xs border border-success-fg bg-success-fg/5 p-3 w-full">
                <p className="flex items-center gap-1 text-caption font-medium text-success-fg">
                  <Shield className="size-3" />
                  New token created — copy it now, it will not be shown again
                </p>
                <div className="mt-2 flex items-center gap-2 w-full">
                  <code className="ltr-island flex-1 min-w-0 truncate rounded-xs bg-surface px-2 py-1 text-caption">
                    {newTokenResult.token}
                  </code>
                  <button
                    type="button"
                    onClick={() => void copyToClipboard(newTokenResult.token)}
                    className="shrink-0 rounded-xs p-2 text-fg-muted hover:text-fg-primary"
                  >
                    {copiedToken === newTokenResult.token.slice(0, 12) ? (
                      <span className="text-caption text-success-fg">Copied!</span>
                    ) : (
                      <Copy className="size-3" />
                    )}
                  </button>
                </div>
                <p className="mt-1 text-caption text-fg-muted">
                  Scope: {newTokenResult.scope === 'write' ? 'Full Access' : 'Read Only'}
                </p>
              </div>
            )}
          </div>

          {/* Active connections — stacked full-width rows */}
          <div className="border-b border-border-default py-3">
            <p className="text-body font-medium mb-2">
              <Wifi className="mr-1 inline size-3" />
              Active Connections
            </p>
            {connections.length === 0 ? (
              <p className="text-caption text-fg-muted w-full">No active connections</p>
            ) : (
              <div className="w-full space-y-2">
                {connections.map((conn) => (
                  <div
                    key={conn.id}
                    className="w-full flex flex-col gap-1 rounded-xs border border-border-default p-3"
                  >
                    <div>
                      <p className="text-body font-medium">{conn.device}</p>
                      <p className="text-caption text-fg-muted">
                        {conn.ip} &middot; {conn.scope} &middot;{' '}
                        {new Date(conn.connected_at * 1000).toLocaleString()}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="w-full rounded-xs p-2 text-fg-muted hover:text-danger-fg"
                      title="Disconnect"
                    >
                      <X className="mr-1 size-3" />
                      Disconnect
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
