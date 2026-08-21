/**
 * Council review button (S11) — a compact opt-in control for the chat
 * composer. It is *only* a button: pressing Send or Stop never starts a
 * council, and the demo / normal `conversation.send` path is untouched.
 *
 * The button uses the current textarea text, or, if the textarea is empty,
 * the most recent user message in this pane. It calls `council.run` with one
 * `{prompt}`, lets the sidecar pick echo members by default, and after a
 * successful run navigates to `/subagents` so the user can watch the
 * three-column widget. A ledger `refusal` is rendered inline as a banner
 * below the button (the pane's own transcript) and no winner is fabricated.
 */

import { Scale } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useTranslation } from '@/lib/i18n';
import { useBridge } from '@/lib/bridge/hooks';
import { Button } from '@/components/ui/button';
import { SafeIcon } from '@/utils/icons';
import type { CouncilDto } from '@/lib/bridge/types';
import type { Message } from '@/types';

interface CouncilButtonProps {
  /** Current composer text; the council uses this when it is non-empty. */
  input: string;
  /** Transcript messages for this pane — needed to fall back to the last user message. */
  messages: Message[];
  /** Disabled while the pane is already sending / streaming a normal turn. */
  disabled?: boolean;
}

export function CouncilButton({ input, messages, disabled }: CouncilButtonProps) {
  const { t } = useTranslation('chat');
  const { call } = useBridge();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pickPrompt = (): string => {
    const trimmed = input.trim();
    if (trimmed) return trimmed;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user' && messages[i].content.trim()) {
        return messages[i].content.trim();
      }
    }
    return '';
  };

  const run = async () => {
    if (busy || disabled) return;
    const prompt = pickPrompt();
    if (!prompt) {
      setError(t('councilEmpty'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await call<CouncilDto>('council.run', { prompt });
      if (result.refusal) {
        // The ledger refused the council — show it plainly, no winner.
        setError(`${t('councilRefusal')}: ${result.refusal}`);
        return;
      }
      // Successful run: take the user to the Subagents page, where the
      // three-column council widget already exists (S10).
      void navigate('/subagents');
    } catch (err) {
      setError(err instanceof Error ? `${t('councilError')}: ${err.message}` : t('councilError'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        size="icon"
        variant="secondary"
        onClick={() => void run()}
        disabled={busy || !!disabled}
        aria-label={t('councilButton')}
        title={t('councilButtonTitle')}
      >
        <SafeIcon icon={Scale} aria-hidden />
      </Button>
      {error && (
        <p
          role="alert"
          className="max-w-xs rounded-md bg-danger-bg px-2 py-1 text-micro text-danger-fg"
        >
          {error}
        </p>
      )}
    </div>
  );
}
