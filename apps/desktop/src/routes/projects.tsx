/** Projects — placeholder shell; implemented in a later phase. */

import { FolderKanban } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';
import { useTranslation } from '@/lib/i18n';

export function ProjectsRoute() {
  const { t } = useTranslation('common');
  return (
    <EmptyState
      icon={FolderKanban}
      title={t('projects.title')}
      description={t('projects.description')}
    />
  );
}
