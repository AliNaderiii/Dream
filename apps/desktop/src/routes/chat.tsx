/** Conversation view. Streaming, tool cards and approvals arrive in P-02. */

import { MessageSquare } from 'lucide-react';
import { useParams } from 'react-router-dom';

import { EmptyState } from '@/components/shared/empty-state';
import { useSessionStore } from '@/stores/use-session-store';

export function ChatRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const session = useSessionStore((s) => s.sessions.find((item) => item.id === sessionId));

  return (
    <div className="flex h-full flex-col">
      <EmptyState
        icon={MessageSquare}
        title={session ? session.title : 'Session not found'}
        description={
          session
            ? 'The conversation transcript, tool-call cards and approval sheet land in P-02.'
            : 'This session no longer exists. Start a new one from the sidebar.'
        }
      >
        {sessionId && <p className="ltr-island text-caption text-fg-muted">{sessionId}</p>}
      </EmptyState>
    </div>
  );
}
