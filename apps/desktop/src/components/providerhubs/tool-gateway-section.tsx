import { KeyRound, ShieldCheck } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/lib/i18n';
import type { GatewayState, GatewayToolId } from '@/lib/bridge/providerhubs';
import { updateGateway } from '@/lib/bridge/providerhubs';

export function ToolGatewaySection({
  gateway,
  onChange,
}: {
  gateway: GatewayState;
  onChange: (next: GatewayState) => void;
}) {
  const { t } = useTranslation('providerhubs');

  const setEnabled = async (enabled: boolean) => {
    onChange(await updateGateway({ enabled }));
  };

  const setTool = async (toolId: GatewayToolId, enabled: boolean) => {
    onChange(await updateGateway({ tool_id: toolId, tool_enabled: enabled }));
  };

  return (
    <section aria-labelledby="providerhubs-gateway-title" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="providerhubs-gateway-title" className="text-h3 font-semibold text-fg-primary">
            {t('gateway.title')}
          </h3>
          <p className="max-w-2xl text-caption text-fg-secondary">{t('gateway.subtitle')}</p>
        </div>
        <Badge variant="warning">{t('gateway.optional')}</Badge>
      </div>

      <Card>
        <CardHeader>
          <Switch
            checked={gateway.enabled}
            onCheckedChange={(checked) => void setEnabled(checked)}
            label={t('gateway.enable')}
            description={t('gateway.enableDesc')}
          />
          <CardDescription>{t('noCloudKey')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="flex items-center gap-2 text-caption text-fg-secondary">
            <ShieldCheck className="size-4 text-success-fg" aria-hidden />
            {gateway.enabled ? t('gateway.on') : t('gateway.off')}
          </p>
          <p className="flex items-center gap-2 text-caption text-fg-muted">
            <KeyRound className="size-4" aria-hidden />
            {t(gateway.auth === 'keychain' ? 'gateway.keychain' : 'gateway.noToken')}
          </p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {gateway.tools.map((tool) => (
              <li key={tool.id} className="rounded-lg border border-border-default p-3">
                <Switch
                  checked={tool.enabled && gateway.enabled}
                  onCheckedChange={(checked) => void setTool(tool.id, checked)}
                  disabled={!gateway.enabled}
                  label={t(`tools.${tool.id}`)}
                  description={t('gateway.byokHint')}
                />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
}
