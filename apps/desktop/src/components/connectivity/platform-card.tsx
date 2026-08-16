/**
 * One platform card on the Connectivity screen: status badge, enable
 * toggle, link-code flow, and a "Configure" expand.
 */

import {
  Check,
  Copy,
  KeyRound,
  Lock,
  MessageSquare,
  Paperclip,
  Radio,
  Settings2,
} from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/utils/cn';

import type {
  GatewayAdapterStatus,
  GatewayLinkCodeResult,
  GatewayPlatform,
} from '@/lib/bridge/types';

/** How the card renders one adapter's observable state. */
function statusBadge(
  status: GatewayAdapterStatus | undefined,
  enabled: boolean,
): {
  variant: 'success' | 'warning' | 'danger' | 'neutral' | 'info';
  label: string;
} {
  if (!enabled) return { variant: 'neutral', label: 'Disabled' };
  if (!status) return { variant: 'info', label: 'Unknown' };
  if (status.error) return { variant: 'danger', label: 'Error' };
  if (status.running && status.connected) return { variant: 'success', label: 'Connected' };
  if (status.running) return { variant: 'warning', label: 'Starting' };
  if (status.detail === 'missing configuration') {
    return { variant: 'warning', label: 'Needs config' };
  }
  return { variant: 'neutral', label: 'Stopped' };
}

interface PlatformCardProps {
  platform: GatewayPlatform;
  status?: GatewayAdapterStatus;
  expanded: boolean;
  linkCode?: GatewayLinkCodeResult;
  /** Toggle the whole adapter on/off via gateway.configure. */
  onToggleEnabled: (platform: GatewayPlatform, enabled: boolean) => void;
  onToggleExpanded: () => void;
  onIssueLinkCode: () => void;
}

export function PlatformCard({
  platform,
  status,
  expanded,
  linkCode,
  onToggleEnabled,
  onToggleExpanded,
  onIssueLinkCode,
}: PlatformCardProps) {
  const [copied, setCopied] = useState(false);
  const badge = statusBadge(status, platform.enabled);

  const copyCode = () => {
    if (!linkCode) return;
    navigator.clipboard
      .writeText(linkCode.code)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {
        /* clipboard unavailable in some embedded views */
      });
  };

  return (
    <div
      data-testid={`platform-card-${platform.name}`}
      className={cn(
        'flex flex-col gap-3 rounded-lg border p-4',
        expanded ? 'border-accent bg-surface' : 'border-border-default bg-surface',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <Radio className="size-5 text-fg-secondary" aria-hidden />
          <h3 className="text-body-lg font-semibold">{platform.label}</h3>
          <Badge variant={badge.variant}>{badge.label}</Badge>
          {platform.privacy === 'e2e' && (
            <Badge variant="info">
              <Lock className="size-3" aria-hidden />
              E2E
            </Badge>
          )}
        </div>
        {/* Enable toggle */}
        <button
          type="button"
          role="switch"
          aria-checked={platform.enabled}
          aria-label={`${platform.label} enabled`}
          onClick={() => onToggleEnabled(platform, !platform.enabled)}
          className={cn(
            'relative h-5 w-9 shrink-0 rounded-full transition-colors duration-fast',
            platform.enabled ? 'bg-accent' : 'bg-surface-2',
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 size-4 rounded-full bg-white shadow transition-all duration-fast',
            )}
            style={{ insetInlineStart: platform.enabled ? '1.125rem' : '0.125rem' }}
            aria-hidden
          />
        </button>
      </div>

      <p className="text-body text-fg-secondary">{platform.description}</p>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-micro text-fg-muted">
        <span className="inline-flex items-center gap-1">
          <MessageSquare className="size-3.5" aria-hidden />
          {platform.max_message_length} chars
        </span>
        {platform.supports_attachments && (
          <span className="inline-flex items-center gap-1">
            <Paperclip className="size-3.5" aria-hidden />
            attachments
          </span>
        )}
        {!platform.supports_inline && (
          <span className="inline-flex items-center gap-1">poll-only</span>
        )}
      </div>

      {status?.error && (
        <p className="rounded-md bg-danger-bg px-2 py-1 text-caption text-danger-fg">
          {status.error}
        </p>
      )}
      {status?.detail === 'missing configuration' && (
        <p className="rounded-md bg-warning-bg px-2 py-1 text-caption text-warning-fg">
          Required fields are missing — open Configure to set them.
        </p>
      )}

      {linkCode && (
        <div className="flex items-center justify-between gap-2 rounded-md border border-border-default bg-sunken px-3 py-2">
          <span className="text-caption text-fg-secondary">
            Link code
            <span className="ms-2 font-mono text-body font-semibold tracking-widest text-fg-primary">
              {linkCode.code}
            </span>
          </span>
          <Button variant="ghost" size="icon-sm" onClick={copyCode} aria-label="Copy link code">
            {copied ? <Check className="size-4 text-success-fg" /> : <Copy className="size-4" />}
          </Button>
        </div>
      )}

      <div className="mt-1 flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onToggleExpanded}>
          <Settings2 className="size-4" aria-hidden />
          {expanded ? 'Hide config' : 'Configure'}
        </Button>
        <Button variant="ghost" size="sm" onClick={onIssueLinkCode}>
          <KeyRound className="size-4" aria-hidden />
          Link code
        </Button>
      </div>
    </div>
  );
}
