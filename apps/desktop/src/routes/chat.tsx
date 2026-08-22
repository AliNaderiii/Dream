/** Multi-pane conversation workspace. */

import { lazy, Suspense, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useLayoutStore } from '@/stores/use-layout-store';
import { useSessionStore } from '@/stores/use-session-store';

const PaneWorkspace = lazy(() =>
  import('@/components/panes/pane-workspace').then((module) => ({ default: module.PaneWorkspace })),
);

export function ChatRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const session = useSessionStore((state) => state.sessions.find((item) => item.id === sessionId));
  const assignSession = useLayoutStore((state) => state.assignSession);

  useEffect(() => {
    if (sessionId) assignSession(sessionId);
  }, [assignSession, sessionId]);

  return (
    <div className="size-full min-h-0 overflow-hidden">
      {session && <h2 className="sr-only">{session.title}</h2>}
      <Suspense fallback={<div className="size-full" aria-busy="true" />}>
        <PaneWorkspace />
      </Suspense>
    </div>
  );
}
