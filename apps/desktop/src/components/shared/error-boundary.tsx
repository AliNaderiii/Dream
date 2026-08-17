/**
 * React error boundary.
 *
 * A class component is required here: `componentDidCatch` / `getDerivedStateFromError`
 * have no hook equivalent. This is the one documented exception to the
 * functional-components rule.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { RotateCcw, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { i18n } from '@/lib/i18n';

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional custom fallback; receives the error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Forwarded to the Rust log plugin via the console bridge.
    console.error('[dream] render error:', error, info.componentStack);
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <div
        role="alert"
        className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
      >
        <TriangleAlert className="size-6 text-danger-fg" aria-hidden />
        <h2 className="text-h2 font-semibold">{i18n.t('error.title', { ns: 'common' })}</h2>
        <p className="max-w-md text-body text-fg-secondary">
          {i18n.t('error.body', { ns: 'common' })}
        </p>
        <pre className="ltr-island selectable max-w-lg overflow-auto rounded-md bg-surface-2 p-3 text-start text-code text-fg-secondary">
          {error.message}
        </pre>
        <Button variant="primary" onClick={this.reset}>
          <RotateCcw aria-hidden />
          {i18n.t('error.retry', { ns: 'common' })}
        </Button>
      </div>
    );
  }
}
