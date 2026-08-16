/**
 * In-memory connectivity gateway for the echo transport.
 *
 * The Python sidecar owns the real behaviour (`dream/connectivity/`); this
 * runtime reproduces the observable contract of the `gateway.*` methods — the
 * same wire shapes, the same platform catalog, the same secret-redaction rule
 * — so the Connectivity screen is fully exercisable in `npm run dev` and in
 * unit tests with no sidecar running.
 */

import { BridgeRpcError } from './errors';
import type {
  GatewayAdapterStatus,
  GatewayLinkedUser,
  GatewayLinkCodeResult,
  GatewayLogEntry,
  GatewayPlatform,
  GatewayPlatformConfig,
  GatewayPlatformField,
  GatewayPlatformName,
  GatewayStatusResult,
  RpcParams,
} from './types';
import { GATEWAY_PLATFORM_NAMES, RPC_ERROR } from './types';

const now = (): number => Date.now() / 1000;

/** ISO timestamp matching the sidecar's serialised `last_activity`. */
const nowIso = (): string => new Date().toISOString();

function invalidParams(message: string): BridgeRpcError {
  return new BridgeRpcError({ code: RPC_ERROR.INVALID_PARAMS, message });
}

function str(params: RpcParams, key: string, fallback = ''): string {
  const value = params[key];
  return typeof value === 'string' ? value : fallback;
}

/** Redaction marker, mirroring `REDACTED_VALUE` in `dream/connectivity/config.py`. */
const REDACTED_VALUE = '••••••••';

const SECRET_KEY_TOKENS = ['token', 'secret', 'password', 'key', 'credential'];

/** True when a config key name marks its value as a secret. */
export function isSecretKey(key: string): boolean {
  const lowered = key.toLowerCase();
  return SECRET_KEY_TOKENS.some((token) => lowered.includes(token));
}

/** Deep-copy a config, masking every secret-keyed value. */
export function redactConfig(config: Record<string, unknown>): Record<string, unknown> {
  const redacted: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(config)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      redacted[key] = redactConfig(value as Record<string, unknown>);
    } else if (isSecretKey(key)) {
      redacted[key] = value ? REDACTED_VALUE : '';
    } else {
      redacted[key] = value;
    }
  }
  return redacted;
}

/** The six-platform catalog, mirrored from `dream/connectivity/platforms.py`. */
const CATALOG: GatewayPlatform[] = [
  {
    name: 'telegram',
    label: 'Telegram',
    description: 'Long-polling bot over the Bot API; no inbound port needed.',
    privacy: 'plaintext',
    max_message_length: 4096,
    supports_inline: true,
    supports_attachments: false,
    fields: [
      {
        key: 'token',
        label: 'Bot token',
        type: 'secret',
        required: true,
        placeholder: '123456:ABC-DEF…',
      },
      {
        key: 'api_base_url',
        label: 'API base URL',
        type: 'text',
        placeholder: 'https://api.telegram.org',
      },
    ],
    enabled: false,
    configured: false,
  },
  {
    name: 'discord',
    label: 'Discord',
    description: 'Gateway WebSocket + REST; slash commands and threads.',
    privacy: 'plaintext',
    max_message_length: 2000,
    supports_inline: true,
    supports_attachments: true,
    fields: [
      { key: 'bot_token', label: 'Bot token', type: 'secret', required: true, placeholder: 'MT…' },
      {
        key: 'application_id',
        label: 'Application ID',
        type: 'text',
        placeholder: '123456789012345678',
      },
      {
        key: 'register_commands',
        label: 'Register slash commands on start',
        type: 'boolean',
        default: true,
      },
      {
        key: 'auto_thread',
        label: 'Auto-create a private thread per channel',
        type: 'boolean',
        default: false,
      },
    ],
    enabled: false,
    configured: false,
  },
  {
    name: 'slack',
    label: 'Slack',
    description: 'Socket Mode (app-level WebSocket); no public endpoint.',
    privacy: 'plaintext',
    max_message_length: 4000,
    supports_inline: true,
    supports_attachments: false,
    fields: [
      {
        key: 'app_token',
        label: 'App-level token (xapp-)',
        type: 'secret',
        required: true,
        placeholder: 'xapp-…',
      },
      {
        key: 'bot_token',
        label: 'Bot token (xoxb-)',
        type: 'secret',
        required: true,
        placeholder: 'xoxb-…',
      },
    ],
    enabled: false,
    configured: false,
  },
  {
    name: 'whatsapp',
    label: 'WhatsApp',
    description: 'Cloud API webhook server plus outbound message API.',
    privacy: 'plaintext',
    max_message_length: 4096,
    supports_inline: true,
    supports_attachments: true,
    fields: [
      {
        key: 'access_token',
        label: 'Access token',
        type: 'secret',
        required: true,
        placeholder: 'EAAG…',
      },
      {
        key: 'phone_number_id',
        label: 'Phone number ID',
        type: 'text',
        required: true,
        placeholder: '123456789012345',
      },
      {
        key: 'verify_token',
        label: 'Webhook verify token',
        type: 'secret',
        required: true,
        placeholder: 'shared-secret',
      },
      {
        key: 'app_secret',
        label: 'App secret (HMAC validation)',
        type: 'secret',
        placeholder: 'optional',
      },
      { key: 'port', label: 'Webhook port', type: 'number', default: 8478 },
      { key: 'path', label: 'Webhook path', type: 'text', default: '/webhook' },
    ],
    enabled: false,
    configured: false,
  },
  {
    name: 'signal',
    label: 'Signal',
    description: 'signal-cli JSON receive loop; end-to-end encrypted.',
    privacy: 'e2e',
    max_message_length: 4096,
    supports_inline: true,
    supports_attachments: false,
    fields: [
      {
        key: 'signal_cli_path',
        label: 'signal-cli binary',
        type: 'text',
        default: 'signal-cli',
        placeholder: '/usr/local/bin/signal-cli',
      },
      {
        key: 'account',
        label: 'Account number',
        type: 'text',
        required: true,
        placeholder: '+12025550123',
      },
    ],
    enabled: false,
    configured: false,
  },
  {
    name: 'email',
    label: 'Email',
    description: 'IMAP IDLE (with polling fallback) and SMTP replies.',
    privacy: 'plaintext',
    max_message_length: 4000,
    supports_inline: false,
    supports_attachments: true,
    fields: [
      {
        key: 'imap_host',
        label: 'IMAP host',
        type: 'text',
        required: true,
        placeholder: 'imap.example.com',
      },
      { key: 'imap_port', label: 'IMAP port', type: 'number', default: 993 },
      {
        key: 'imap_user',
        label: 'IMAP username',
        type: 'text',
        required: true,
        placeholder: 'you@example.com',
      },
      { key: 'imap_password', label: 'IMAP password', type: 'secret', required: true },
      {
        key: 'smtp_host',
        label: 'SMTP host',
        type: 'text',
        required: true,
        placeholder: 'smtp.example.com',
      },
      { key: 'smtp_port', label: 'SMTP port', type: 'number', default: 465 },
      { key: 'smtp_user', label: 'SMTP username', type: 'text' },
      { key: 'smtp_password', label: 'SMTP password', type: 'secret' },
      { key: 'mailbox', label: 'Mailbox', type: 'text', default: 'INBOX' },
      { key: 'poll_seconds', label: 'Poll interval (seconds)', type: 'number', default: 60 },
      { key: 'use_idle', label: 'Use IMAP IDLE', type: 'boolean', default: true },
    ],
    enabled: false,
    configured: false,
  },
];

const SECRET_FIELDS: Record<string, string[]> = Object.fromEntries(
  CATALOG.map((platform) => [
    platform.name,
    platform.fields.filter((field) => field.type === 'secret').map((field) => field.key),
  ]),
);

/** Deterministic sample traffic so the log viewer renders without a sidecar. */
function seedLog(): GatewayLogEntry[] {
  const rows: Array<[GatewayPlatformName, 'in' | 'out', string, string]> = [
    ['telegram', 'in', '42', 'Can you remind me to water the plants at 6?'],
    ['telegram', 'out', '42', 'Reminder set for 18:00. 🌱'],
    ['discord', 'in', 'user-7', '/dream summarise today\u2019s notes'],
    ['discord', 'out', 'user-7', 'Done — three sessions, two new memories.'],
    ['slack', 'in', 'U1', 'What is the status of the deployment?'],
    ['slack', 'out', 'U1', 'All green; the last schedule run succeeded.'],
    ['whatsapp', 'in', '+15551234567', 'سلام! چه خبر؟'],
    ['whatsapp', 'out', '+15551234567', 'سلام! همه‌چیز آماده است.'],
    ['signal', 'in', '+12025550123', ''],
    ['signal', 'out', '+12025550123', ''],
    ['email', 'in', 'user@example.com', 'Subject: weekend report — please review'],
    ['email', 'out', 'user@example.com', 'Re: Dream — reviewed, two edits suggested.'],
  ];
  const start = now() - rows.length * 300;
  return rows.map(([platform, direction, user, text], index) => ({
    platform,
    direction,
    user_id: user,
    text,
    timestamp: new Date((start + index * 300) * 1000).toISOString(),
    message_id: `echo-${platform}-${index}`,
    attachments: 0,
  }));
}

let linkCodeCounter = 0;

/**
 * Echo stand-in for the connectivity gateway: platform catalog + config,
 * adapter statuses, linked users, link codes, and the message log.
 */
export class EchoGatewayRuntime {
  private configs = new Map<GatewayPlatformName, Record<string, unknown>>();
  private statuses = new Map<GatewayPlatformName, GatewayAdapterStatus>();
  private linked: GatewayLinkedUser[] = [];
  private log: GatewayLogEntry[] = seedLog();
  private running = false;
  private startedAt: number | null = null;
  private pendingCodes = new Map<GatewayPlatformName, GatewayLinkCodeResult>();

  constructor() {
    for (const platform of CATALOG) {
      this.statuses.set(platform.name, {
        platform: platform.name,
        running: false,
        connected: false,
        last_activity: null,
        error: null,
        detail: '',
      });
    }
  }

  /** No timers to tear down; kept for parity with the subagent runtime. */
  dispose(): void {
    /* no-op */
  }

  // -- public config ---------------------------------------------------- //

  private publicConfig(name: GatewayPlatformName): GatewayPlatformConfig {
    const config = this.configs.get(name) ?? {};
    const redacted = redactConfig(config);
    const required = CATALOG.find((p) => p.name === name)!.fields.filter((field) => field.required);
    const configured = required.every((field) => {
      const value = config[field.key];
      return typeof value === 'string'
        ? value.trim() !== ''
        : value !== undefined && value !== null;
    });
    return {
      ...redacted,
      enabled: config['enabled'] === true,
      configured,
      secret_fields: [...(SECRET_FIELDS[name] ?? [])],
    };
  }

  private catalogWithConfig(): GatewayPlatform[] {
    return CATALOG.map((platform) => {
      const publicConfig = this.publicConfig(platform.name);
      return {
        ...platform,
        enabled: publicConfig.enabled,
        configured: publicConfig.configured,
      };
    });
  }

  // -- gateway.* handlers ------------------------------------------------ //

  platforms(): GatewayPlatform[] {
    return this.catalogWithConfig();
  }

  /** Recompute each adapter's observable state from config + running flag. */
  private refreshStatuses(): void {
    for (const platform of CATALOG) {
      const publicConfig = this.publicConfig(platform.name);
      const status = this.statuses.get(platform.name)!;
      status.error = null;
      if (!publicConfig.enabled) {
        status.running = false;
        status.connected = false;
        status.detail = 'disabled';
      } else if (!publicConfig.configured) {
        status.running = false;
        status.connected = false;
        status.detail = 'missing configuration';
      } else if (!this.running) {
        status.running = false;
        status.connected = false;
        status.detail = 'stopped';
      } else {
        status.last_activity = nowIso();
        status.running = true;
        status.connected = true;
        status.detail = '';
      }
    }
  }

  status(): GatewayStatusResult {
    this.refreshStatuses();
    return {
      running: this.running,
      started_at: this.startedAt,
      adapters: [...this.statuses.values()].map((status) => ({ ...status })),
      linked_users: this.linked.map((user) => ({ ...user })),
      messages: {
        inbound: this.log.filter((entry) => entry.direction === 'in').length,
        outbound: this.log.filter((entry) => entry.direction === 'out').length,
      },
      rate_limit: { limits: {}, default: 20, active: {} },
    };
  }

  start(): GatewayStatusResult {
    this.running = true;
    this.startedAt = this.startedAt ?? now();
    return this.status();
  }

  stop(): GatewayStatusResult {
    this.running = false;
    return this.status();
  }

  configure(platform: GatewayPlatformName, values: RpcParams): GatewayPlatformConfig {
    const merged = { ...(this.configs.get(platform) ?? {}) };
    for (const [key, value] of Object.entries(values)) {
      if (value === null) delete merged[key];
      else if (value === '' && isSecretKey(key) && key in merged)
        continue; // keep stored secret
      else merged[key] = value;
    }
    this.configs.set(platform, merged);
    return this.publicConfig(platform);
  }

  logs(
    platform: GatewayPlatformName | null,
    limit: number | null,
  ): { platform: GatewayPlatformName | null; entries: GatewayLogEntry[]; total: number } {
    const rows = platform ? this.log.filter((entry) => entry.platform === platform) : [...this.log];
    const bounded = (limit ?? 100) > 0 ? rows.slice(0, limit ?? 100) : rows;
    return { platform, entries: bounded, total: bounded.length };
  }

  linkCode(platform: GatewayPlatformName): GatewayLinkCodeResult {
    const existing = this.pendingCodes.get(platform);
    if (existing && existing.expires_at > now()) return { ...existing };
    const code: GatewayLinkCodeResult = {
      platform,
      code: String(100000 + (++linkCodeCounter % 900000)).padStart(6, '0'),
      issued_at: now(),
      expires_at: now() + 600,
      user_id: null,
    };
    this.pendingCodes.set(platform, code);
    return { ...code };
  }

  linkedUsers(platform?: string | null): GatewayLinkedUser[] {
    return platform
      ? this.linked.filter((user) => user.platform === platform).map((user) => ({ ...user }))
      : this.linked.map((user) => ({ ...user }));
  }

  unlinkUser(platform: string, userId: string): boolean {
    const before = this.linked.length;
    this.linked = this.linked.filter(
      (user) => !(user.platform === platform && user.user_id === userId),
    );
    return this.linked.length < before;
  }
}

/** `gateway.*` param validation shared by the echo handler and its tests. */
export function requireGatewayPlatform(params: RpcParams): GatewayPlatformName {
  const platform = str(params, 'platform');
  if (!GATEWAY_PLATFORM_NAMES.includes(platform as GatewayPlatformName)) {
    throw invalidParams(`platform must be one of ${GATEWAY_PLATFORM_NAMES.join(', ')}`);
  }
  return platform as GatewayPlatformName;
}

export type { GatewayPlatformField };
