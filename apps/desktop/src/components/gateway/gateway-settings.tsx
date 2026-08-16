/**
 * Web Gateway settings UI — token management, connection list, QR code.
 */

import {
  Copy,
  Eye,
  EyeOff,
  Key,
  Plus,
  QrCode,
  RefreshCw,
  Shield,
  Trash2,
  Wifi,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import type { GatewayConnection, GatewayStatus, GatewayTokenFull } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

export function GatewaySettings() {
  const { call } = useBridge();
  const [status, setStatus] = useState<GatewayStatus | null>(null);
  const [tokens, setTokens] = useState<Record<string, GatewayTokenFull>>({});
  const [connections] = useState<GatewayConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gatewayEnabled, setGatewayEnabled] = useState(true);
  const [showTokenValues, setShowTokenValues] = useState(false);
  const [newTokenResult, setNewTokenResult] = useState<{ token: string; scope: string } | null>(null);
  const [copiedToken, setCopiedToken] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusResult, tokensResult] = await Promise.all([
        call<GatewayStatus>('gateway.status'),
        call<{ tokens: Record<string, GatewayTokenFull> }>('gateway.get_tokens'),
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
    if (gatewayEnabled) void refresh();
  }, [gatewayEnabled, refresh]);

  const handleCreateToken = async (scope: 'read' | 'write') => {
    setError(null);
    try {
      const result = await call<{ token: string; scope: string }>('gateway.create_token', {
        scope,
        label: scope === 'write' ? 'Full Access' : 'Read Only',
      });
      setNewTokenResult(result);
      void refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create token');
    }
  };

  const handleRotateToken = async (tokenValue: string) => {
    setError(null);
    try {
      const result = await call<{ token: string }>('gateway.rotate_token', {
        token: tokenValue,
      });
      setNewTokenResult({ token: result.token, scope: 'write' });
      void refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to rotate token');
    }
  };

  const handleRevokeToken = async (tokenValue: string) => {
    setError(null);
    try {
      await call('gateway.revoke_token', { token: tokenValue });
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

  // Build a connection URL for the QR code.
  const connectionUrl = (() => {
    if (!status?.has_setup_token) return null;
    const tokenEntries = Object.entries(tokens);
    if (tokenEntries.length === 0) return null;
    const [firstToken] = tokenEntries[0];
    // Use local IP: this would need to be resolved dynamically.
    return `http://${firstToken}@dream.local:9090`;
  })();

  return (
    <section>
      <h2 className="pb-2 text-h2 font-semibold">Web Gateway</h2>

      <div className="flex items-center justify-between border-b border-border-default py-3">
        <div>
          <p className="text-body font-medium">Enable web gateway</p>
          <p className="text-caption text-fg-secondary">
            Access Dream from your phone, tablet, or another computer on your LAN
          </p>
        </div>
        <Button
          size="sm"
          variant={gatewayEnabled ? 'primary' : 'secondary'}
          aria-pressed={gatewayEnabled}
          onClick={() => setGatewayEnabled((v) => !v)}
        >
          {gatewayEnabled ? 'On' : 'Off'}
        </Button>
      </div>

      {/* Gateway status */}
      {gatewayEnabled && (
        <>
          <div className="border-b border-border-default py-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-body font-medium">Status</p>
                <p className="text-caption text-fg-secondary">
                  {status?.has_setup_token
                    ? 'Gateway ready — connect from your LAN'
                    : 'No tokens configured — create one to enable access'}
                </p>
              </div>
              <Button size="sm" variant="secondary" onClick={refresh} disabled={loading}>
                {loading ? '…' : <RefreshCw className="size-3" />}
                <span className="ml-1">Refresh</span>
              </Button>
            </div>
            {error && <p className="mt-1 text-caption text-danger-fg">{error}</p>}
          </div>

          {/* Token management */}
          <div className="border-b border-border-default py-3">
            <p className="text-body font-medium mb-2">
              <Key className="mr-1 inline size-3" />
              Authentication Tokens
            </p>

            {/* Existing tokens */}
            {Object.entries(tokens).length > 0 && (
              <div className="mb-3 space-y-2">
                {Object.entries(tokens).map(([tokenValue, info]) => (
                  <div
                    key={tokenValue}
                    className="flex items-center gap-2 rounded-xs border border-border-default bg-surface-raised p-2"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-caption font-medium',
                            info.scope === 'write'
                              ? 'bg-success-fg/10 text-success-fg'
                              : 'bg-fg-muted/10 text-fg-muted',
                          )}
                        >
                          {info.scope === 'write' ? 'Full' : 'Read'}
                        </span>
                        {showTokenValues ? (
                          <code className="ltr-island truncate text-caption text-fg-primary">
                            {tokenValue}
                          </code>
                        ) : (
                          <code className="ltr-island text-caption text-fg-muted">
                            {tokenValue.slice(0, 16)}•••••••••
                          </code>
                        )}
                      </div>
                      <p className="text-caption text-fg-muted">
                        {info.label} &middot;{' '}
                        {info.last_used_at
                          ? `Last used ${new Date(info.last_used_at * 1000).toLocaleString()}`
                          : 'Never used'}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => void copyToClipboard(tokenValue)}
                        className="rounded-xs p-1 text-fg-muted hover:text-fg-primary"
                        title="Copy token"
                      >
                        {copiedToken === tokenValue.slice(0, 12) ? (
                          <span className="text-caption text-success-fg">Copied!</span>
                        ) : (
                          <Copy className="size-3" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRotateToken(tokenValue)}
                        className="rounded-xs p-1 text-fg-muted hover:text-fg-primary"
                        title="Rotate (regenerate) token"
                      >
                        <RefreshCw className="size-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRevokeToken(tokenValue)}
                        className="rounded-xs p-1 text-danger-fg hover:text-danger-fg"
                        title="Revoke token"
                      >
                        <Trash2 className="size-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Show/hide tokens toggle */}
            {Object.keys(tokens).length > 0 && (
              <button
                type="button"
                onClick={() => setShowTokenValues((v) => !v)}
                className="mb-2 flex items-center gap-1 text-caption text-fg-muted hover:text-fg-primary"
              >
                {showTokenValues ? (
                  <EyeOff className="size-3" />
                ) : (
                  <Eye className="size-3" />
                )}
                {showTokenValues ? 'Hide tokens' : 'Show tokens'}
              </button>
            )}

            {/* Create new token */}
            <div className="flex gap-2">
              <Button size="sm" onClick={() => handleCreateToken('write')}>
                <Plus className="mr-1 size-3" />
                New Full Access Token
              </Button>
              <Button size="sm" variant="secondary" onClick={() => handleCreateToken('read')}>
                <Plus className="mr-1 size-3" />
                New Read-Only Token
              </Button>
            </div>

            {/* Newly created token display */}
            {newTokenResult && (
              <div className="mt-3 rounded-xs border border-success-fg bg-success-fg/5 p-3">
                <p className="flex items-center gap-1 text-caption font-medium text-success-fg">
                  <Shield className="size-3" />
                  New token created — copy it now, it will not be shown again
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <code className="ltr-island flex-1 truncate rounded-xs bg-surface px-2 py-1 text-caption">
                    {newTokenResult.token}
                  </code>
                  <button
                    type="button"
                    onClick={() => void copyToClipboard(newTokenResult.token)}
                    className="rounded-xs p-1 text-fg-muted hover:text-fg-primary"
                  >
                    <Copy className="size-3" />
                  </button>
                </div>
                <p className="mt-1 text-caption text-fg-muted">
                  Scope: {newTokenResult.scope === 'write' ? 'Full Access' : 'Read Only'}
                </p>
              </div>
            )}
          </div>

          {/* Active connections */}
          <div className="border-b border-border-default py-3">
            <p className="text-body font-medium mb-2">
              <Wifi className="mr-1 inline size-3" />
              Active Connections
            </p>
            {connections.length === 0 ? (
              <p className="text-caption text-fg-muted">No active connections</p>
            ) : (
              <div className="space-y-2">
                {connections.map((conn) => (
                  <div
                    key={conn.id}
                    className="flex items-center justify-between rounded-xs border border-border-default p-2"
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
                      className="rounded-xs p-1 text-fg-muted hover:text-danger-fg"
                      title="Disconnect"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* QR Code */}
          {connectionUrl && (
            <div className="py-3">
              <p className="text-body font-medium mb-2">
                <QrCode className="mr-1 inline size-3" />
                Quick Connect
              </p>
              <p className="text-caption text-fg-secondary mb-2">
                Scan this QR code with your phone camera to connect automatically
              </p>
              <div className="inline-flex flex-col items-center gap-2 rounded-xs border border-border-default bg-surface-raised p-4">
                <div className="flex h-32 w-32 items-center justify-center bg-white text-black">
                  <QrCode className="size-24 text-black" />
                </div>
                <p className="text-caption text-fg-muted">
                  Or visit{' '}
                  <a
                    href={connectionUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent-fg underline"
                  >
                    {connectionUrl}
                  </a>
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}