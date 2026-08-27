/** Deterministic echo runtime for gws.* */

export interface GwsStatus {
  connected: boolean;
  network: boolean;
  redirect_uri: string;
  scopes: string[];
  writes: false;
}

let connected = false;

export function echoGwsStatus(): GwsStatus {
  return {
    connected,
    network: true,
    redirect_uri: 'http://127.0.0.1:17463/callback',
    scopes: ['gmail.readonly', 'calendar.readonly', 'drive.readonly'],
    writes: false,
  };
}

export function echoGwsBegin() {
  return {
    authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=echo',
    state: 'state_echo',
    redirect_uri: 'http://127.0.0.1:17463/callback',
  };
}

export function echoGwsComplete(state: string, code: string) {
  if (state !== 'state_echo') throw new Error('invalid OAuth state');
  if (!code.trim()) throw new Error('authorization code is required');
  if (code.includes('evil.example')) throw new Error('OAuth redirect must be loopback');
  connected = true;
  return { connected: true, scopes: echoGwsStatus().scopes };
}

export function echoGwsDisconnect() {
  connected = false;
  return { connected: false };
}

export function resetEchoGws(): void {
  connected = false;
}
