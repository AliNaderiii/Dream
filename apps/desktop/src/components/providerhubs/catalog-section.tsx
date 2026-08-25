import { Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/lib/i18n';
import { filterCatalog, type CatalogEntry } from '@/lib/bridge/providerhubs';

export function CatalogSection({ entries, locale }: { entries: CatalogEntry[]; locale: string }) {
  const { t } = useTranslation('providerhubs');
  const [query, setQuery] = useState('');
  const visible = useMemo(() => filterCatalog(entries, query), [entries, query]);

  return (
    <section aria-labelledby="providerhubs-catalog-title" className="flex flex-col gap-4">
      <div>
        <h3 id="providerhubs-catalog-title" className="text-h3 font-semibold text-fg-primary">
          {t('catalog.title')}
        </h3>
        <p className="text-caption text-fg-secondary">{t('catalog.subtitle')}</p>
      </div>
      <Input
        label={t('catalog.search')}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t('catalog.searchPlaceholder')}
        leading={<Search />}
      />
      <div className="grid gap-3 md:grid-cols-2">
        {visible.map((entry) => (
          <Card key={entry.id} aria-labelledby={`catalog-${entry.id}`}>
            <CardHeader>
              <h4 id={`catalog-${entry.id}`} className="text-body font-semibold text-fg-primary">
                {entry.name}
              </h4>
              <CardDescription>{entry.notes}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-2">
                <Badge variant={entry.local ? 'success' : 'neutral'}>
                  {entry.local ? t('catalog.local') : t('catalog.cloud')}
                </Badge>
                <Badge variant="neutral">{t(`cost.${entry.cost_tier}`)}</Badge>
                <Badge variant={entry.tool_calling ? 'success' : 'warning'}>
                  {entry.tool_calling ? t('toolCalling.native') : t('toolCalling.fallback')}
                </Badge>
              </div>
              <p className="text-caption text-fg-secondary">
                {locale === 'fa' ? entry.privacy_fa : entry.privacy_en}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
