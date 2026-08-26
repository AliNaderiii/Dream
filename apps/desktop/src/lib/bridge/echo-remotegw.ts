/** Deterministic echo runtime for remotegw.* */

export interface RemoteBind {
  host: string;
  port: number;
  kind: 'loopback' | 'lan';
  leaves_machine: boolean;
}

export interface RemoteStatus {
  running: boolean;
  bind: RemoteBind;
  leaves_machine: boolean;
  auth: 'bearer';
  query_tokens: false;
  tokens: Array<{ prefix: string; scope: string; label: string }>;
}

const LOOPBACK: RemoteBind = {
  host: '127.0.0.1',
  port: 8765,
  kind: 'loopback',
  leaves_machine: false,
};

let running = false;
const tokens: Array<{ prefix: string; scope: string; label: string }> = [
  { prefix: 'drm_echo_demo...', scope: 'read', label: 'Phone [read]' },
];

export function echoRemoteStatus(): RemoteStatus {
  return {
    running,
    bind: { ...LOOPBACK },
    leaves_machine: false,
    auth: 'bearer',
    query_tokens: false,
    tokens: tokens.map((row) => ({ ...row })),
  };
}

export function echoRemotePreview(host?: string, lan = false) {
  if (host && !host.startsWith('127.') && !lan) {
    throw new Error('LAN bind requires --lan');
  }
  if (host === '8.8.8.8' || host === '1.1.1.1' || host === '0.0.0.0') {
    throw new Error('WAN / public bind is refused');
  }
  const bind =
    host && lan ? { host, port: 8765, kind: 'lan' as const, leaves_machine: true } : LOOPBACK;
  return {
    url: `http://${bind.host}:${bind.port}/`,
    qr: `http://${bind.host}:${bind.port}/`,
    token_in_qr: false,
    leaves_machine: bind.leaves_machine,
    bind,
    hint_en: 'Paste the token once in Authorization: Bearer. It is not in the QR.',
    hint_fa: 'توکن را یک‌بار در Authorization: Bearer بچسبانید. داخل QR نیست.',
  };
}

export function echoRemoteStart() {
  running = true;
  return { started: true, bind: { ...LOOPBACK }, leaves_machine: false };
}

export function echoRemoteStop() {
  running = false;
  return { stopped: true };
}

export function echoRemoteIssue(scope = 'read', label = 'Remote') {
  const prefix = `drm_echo_${tokens.length}...`;
  tokens.push({ prefix, scope, label: `${label} [${scope}]` });
  return {
    token: 'drm_EXAMPLE_not_a_real_key',
    prefix,
    scope,
    coarse: scope === 'read' ? 'read' : 'write',
    label: `${label} [${scope}]`,
    leaves_machine: false,
  };
}

export function resetEchoRemote(): void {
  running = false;
  tokens.splice(1);
}
