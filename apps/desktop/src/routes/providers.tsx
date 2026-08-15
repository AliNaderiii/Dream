/** Providers — placeholder shell; implemented in a later phase. */

import { Sparkles } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';

export function ProvidersRoute() {
  return (
    <EmptyState
      icon={Sparkles}
      title="Providers"
      description="Model providers, keychain-stored keys and connection tests. Built in P-05."
    />
  );
}
