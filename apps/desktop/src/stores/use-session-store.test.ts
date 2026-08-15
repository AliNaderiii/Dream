import { beforeEach, describe, expect, it } from 'vitest';

import { useSessionStore } from '@/stores/use-session-store';

describe('useSessionStore', () => {
  beforeEach(() => {
    useSessionStore.setState({ sessions: [], activeSessionId: null, searchQuery: '' });
  });

  it('creates a session and makes it active', () => {
    const session = useSessionStore.getState().createSession('Research notes');

    expect(useSessionStore.getState().sessions).toHaveLength(1);
    expect(useSessionStore.getState().activeSessionId).toBe(session.id);
    expect(session.title).toBe('Research notes');
  });

  it('puts the newest session first', () => {
    const first = useSessionStore.getState().createSession('First');
    const second = useSessionStore.getState().createSession('Second');

    expect(useSessionStore.getState().sessions.map((s) => s.id)).toEqual([second.id, first.id]);
  });

  it('renames a session', () => {
    const session = useSessionStore.getState().createSession('Draft');
    useSessionStore.getState().renameSession(session.id, 'Final');

    expect(useSessionStore.getState().sessions[0].title).toBe('Final');
  });

  it('clears the active id when the active session is deleted', () => {
    const session = useSessionStore.getState().createSession();
    useSessionStore.getState().deleteSession(session.id);

    expect(useSessionStore.getState().sessions).toHaveLength(0);
    expect(useSessionStore.getState().activeSessionId).toBeNull();
  });

  it('filters sessions case-insensitively', () => {
    useSessionStore.getState().createSession('Persian grammar');
    useSessionStore.getState().createSession('Budget model');
    useSessionStore.getState().setSearchQuery('PERSIAN');

    const filtered = useSessionStore.getState().filteredSessions();
    expect(filtered).toHaveLength(1);
    expect(filtered[0].title).toBe('Persian grammar');
  });
});
