/** Provider catalog, keychain-backed configuration, model selection, and probes. */

import * as Dialog from '@radix-ui/react-dialog';
import {
  Check,
  Cloud,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import type { ProviderDraft } from '@/stores/use-provider-store';
import { useProviderStore } from '@/stores/use-provider-store';
import type { Provider, ProviderCatalogEntry } from '@/types';
import { cn } from '@/utils/cn';

const fieldClass =
  'selectable h-9 w-full rounded-md border border-border-default bg-canvas px-3 text-body text-fg-primary outline-none focus:border-accent';

function draftForCatalog(entry: ProviderCatalogEntry): ProviderDraft {
  return {
    kind: entry.id,
    name: entry.name,
    endpoint: entry.endpoint,
    modelListUrl: entry.modelListUrl ?? '',
    models: entry.defaultModels,
    enabledModelIds: entry.defaultModels,
  };
}

function draftForProvider(provider: Provider): ProviderDraft {
  return {
    id: provider.id,
    kind: provider.kind as ProviderDraft['kind'],
    name: provider.name,
    endpoint: provider.endpoint ?? '',
    modelListUrl: provider.modelListUrl ?? '',
    models: provider.models.map((model) => model.id),
    enabledModelIds: provider.enabledModelIds,
  };
}

export function ProvidersRoute() {
  const { t } = useTranslation('providers');
  const { t: tc } = useTranslation('common');
  const providers = useProviderStore((state) => state.providers);
  const catalog = useProviderStore((state) => state.catalog);
  const loading = useProviderStore((state) => state.loading);
  const error = useProviderStore((state) => state.error);
  const load = useProviderStore((state) => state.load);
  const removeProvider = useProviderStore((state) => state.removeProvider);
  const testProvider = useProviderStore((state) => state.testProvider);
  const [editor, setEditor] = useState<ProviderDraft | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const configured = providers.filter((provider) => provider.kind !== 'echo');

  useEffect(() => {
    void load();
  }, [load]);

  const runTest = async (id: string) => {
    setBusyId(id);
    await testProvider(id);
    setBusyId(null);
  };

  return (
    <div className="mx-auto w-full max-w-6xl p-6 lg:p-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-h2 font-semibold">{t('title')}</h2>
            <Badge variant="neutral">{t('configured', { count: configured.length })}</Badge>
          </div>
          <p className="mt-1 max-w-2xl text-body text-fg-secondary">{t('subtitle')}</p>
        </div>
        <Button
          variant="primary"
          disabled={catalog.length === 0}
          onClick={() => catalog[0] && setEditor(draftForCatalog(catalog[0]))}
        >
          <Plus aria-hidden /> {t('add')}
        </Button>
      </div>

      <div className="mb-5 flex items-center gap-2 rounded-md border border-border-default bg-surface px-3 py-2 text-caption text-fg-secondary">
        <ShieldCheck className="size-4 shrink-0 text-success-fg" aria-hidden />
        Credentials are stored by Keychain Access, Windows Credential Manager, or Linux Secret
        Service via Python keyring.
      </div>

      {error && <p className="mb-4 rounded-md bg-warning-bg px-3 py-2 text-warning-fg">{error}</p>}

      {loading && configured.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-20 text-fg-muted">
          <LoaderCircle className="size-5 animate-spin" aria-hidden /> {t('loading')}
        </div>
      ) : configured.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-surface p-12 text-center">
          <KeyRound className="mx-auto mb-3 size-10 text-accent-text" aria-hidden />
          <h3 className="text-h3 font-semibold">{t('connectFirst')}</h3>
          <p className="mx-auto mt-1 max-w-md text-fg-secondary">{t('connectFirstDesc')}</p>
          <Button
            className="mt-5"
            variant="primary"
            disabled={catalog.length === 0}
            onClick={() => catalog[0] && setEditor(draftForCatalog(catalog[0]))}
          >
            <Plus aria-hidden /> {t('browseCatalog')}
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {configured.map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              busy={busyId === provider.id}
              onEdit={() => setEditor(draftForProvider(provider))}
              onDelete={() => setDeleteTarget(provider)}
              onTest={() => void runTest(provider.id)}
            />
          ))}
        </div>
      )}

      {editor && (
        <ProviderEditor
          draft={editor}
          catalog={catalog}
          onDraft={setEditor}
          onClose={() => setEditor(null)}
        />
      )}

      <Dialog.Root
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border-default bg-overlay p-5 shadow-e3">
            <Dialog.Title className="text-h3 font-semibold">
              {t('deleteTitle', { name: deleteTarget?.name })}
            </Dialog.Title>
            <Dialog.Description className="mt-2 text-fg-secondary">
              {t('deleteDesc')}
            </Dialog.Description>
            <div className="mt-5 flex justify-end gap-2">
              <Button onClick={() => setDeleteTarget(null)}>{tc('generic.cancel')}</Button>
              <Button
                variant="destructive"
                onClick={() => {
                  if (!deleteTarget) return;
                  setBusyId(deleteTarget.id);
                  void removeProvider(deleteTarget.id).finally(() => {
                    setBusyId(null);
                    setDeleteTarget(null);
                  });
                }}
              >
                <Trash2 aria-hidden /> {t('deleteProvider')}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function ProviderCard({
  provider,
  busy,
  onEdit,
  onDelete,
  onTest,
}: {
  provider: Provider;
  busy: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
}) {
  const connected = provider.status === 'connected';
  return (
    <article className="flex min-h-52 flex-col rounded-lg border border-border-default bg-surface p-4 shadow-e1">
      <div className="flex items-start gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
          {provider.local ? <Server aria-hidden /> : <Cloud aria-hidden />}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-h3 font-semibold">{provider.name}</h3>
          <p className="ltr-island truncate text-caption text-fg-muted">{provider.kind}</p>
        </div>
        <Badge variant={connected ? 'success' : provider.status === 'error' ? 'danger' : 'neutral'}>
          {connected ? (
            <Check aria-hidden />
          ) : provider.status === 'error' ? (
            <XCircle aria-hidden />
          ) : null}
          {provider.status === 'testing'
            ? 'Testing'
            : connected
              ? 'Connected'
              : provider.status === 'error'
                ? 'Error'
                : 'Disconnected'}
        </Badge>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-caption">
        <div>
          <dt className="text-fg-muted">Visible models</dt>
          <dd className="font-medium text-fg-primary">{provider.enabledModelIds.length}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">Credential</dt>
          <dd className="font-medium text-fg-primary">
            {provider.credentialConfigured || provider.local ? 'Configured' : 'Missing'}
          </dd>
        </div>
      </dl>
      {provider.latencyMs !== undefined && (
        <p className="mt-2 ltr-island text-caption text-fg-muted">{provider.latencyMs} ms</p>
      )}

      <div className="mt-auto flex gap-2 pt-4">
        <Button size="sm" className="flex-1" onClick={onTest} disabled={busy}>
          {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />}
          Test
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={onEdit}
          aria-label={`Edit ${provider.name}`}
        >
          <Pencil aria-hidden />
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={onDelete}
          aria-label={`Delete ${provider.name}`}
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
    </article>
  );
}

function ProviderEditor({
  draft,
  catalog,
  onDraft,
  onClose,
}: {
  draft: ProviderDraft;
  catalog: ProviderCatalogEntry[];
  onDraft: (draft: ProviderDraft | null) => void;
  onClose: () => void;
}) {
  const saveProvider = useProviderStore((state) => state.saveProvider);
  const fetchModels = useProviderStore((state) => state.fetchModels);
  const testProvider = useProviderStore((state) => state.testProvider);
  const [credential, setCredential] = useState('');
  const [showCredential, setShowCredential] = useState(false);
  const [pasteDetected, setPasteDetected] = useState(false);
  const [customModels, setCustomModels] = useState('');
  const [busy, setBusy] = useState<'save' | 'test' | 'models' | null>(null);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const entry = catalog.find((item) => item.id === draft?.kind);
  const isEdit = Boolean(draft?.id);
  const needsCredential = entry?.authType === 'api_key' || entry?.authType === 'custom';

  const save = async (): Promise<Provider | null> => {
    if (!draft) return null;
    setBusy('save');
    setResult(null);
    try {
      const models = [
        ...new Set([
          ...draft.models,
          ...customModels
            .split(/[,\n]/)
            .map((item) => item.trim())
            .filter(Boolean),
        ]),
      ];
      const enabledModelIds = [...new Set([...draft.enabledModelIds, ...models])];
      const provider = await saveProvider(
        { ...draft, models, enabledModelIds },
        credential || undefined,
      );
      onDraft(draftForProvider(provider));
      setCredential('');
      setResult({ ok: true, message: 'Provider saved. Credential is in the OS keychain.' });
      return provider;
    } catch {
      setResult({
        ok: false,
        message: 'Could not save the provider. Check its fields and keychain access.',
      });
      return null;
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    let id = draft?.id;
    if (!id) id = (await save())?.id;
    if (!id) return;
    setBusy('test');
    const outcome = await testProvider(id);
    setBusy(null);
    setResult({
      ok: outcome.ok,
      message: outcome.ok
        ? `Connected${outcome.latencyMs !== undefined ? ` in ${outcome.latencyMs} ms` : ''}.`
        : (outcome.detail ?? 'Connection failed.'),
    });
  };

  const discover = async () => {
    let id = draft?.id;
    if (!id) id = (await save())?.id;
    if (!id) return;
    setBusy('models');
    try {
      const models = await fetchModels(id, true);
      onDraft(draft ? { ...draft, id, models, enabledModelIds: models } : null);
      setResult({ ok: true, message: `Found ${models.length} models.` });
    } catch {
      setResult({ ok: false, message: 'Could not fetch models. Defaults remain available.' });
    } finally {
      setBusy(null);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void save().then((provider) => provider && onClose());
  };

  return (
    <Dialog.Root open onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Content className="fixed inset-y-4 end-4 z-50 flex w-[min(38rem,calc(100%-2rem))] flex-col overflow-hidden rounded-xl border border-border-default bg-overlay shadow-e3">
          <div className="flex items-start border-b border-border-default p-5">
            <div className="flex-1">
              <Dialog.Title className="text-h2 font-semibold">
                {isEdit ? 'Edit provider' : 'Add provider'}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-fg-secondary">
                Only non-secret metadata is saved in Dream. Credentials are sent directly to the
                keychain.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Close provider editor">
                <X aria-hidden />
              </Button>
            </Dialog.Close>
          </div>

          {draft && (
            <form
              onSubmit={submit}
              className="selectable min-h-0 flex-1 space-y-5 overflow-y-auto p-5"
            >
              <label className="block text-caption font-medium text-fg-secondary">
                Provider type
                <select
                  className={cn(fieldClass, 'mt-1')}
                  value={draft.kind}
                  disabled={isEdit}
                  onChange={(event) => {
                    const selected = catalog.find((item) => item.id === event.target.value);
                    if (selected) onDraft(draftForCatalog(selected));
                  }}
                >
                  {catalog.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-caption font-medium text-fg-secondary">
                  Display name
                  <input
                    className={cn(fieldClass, 'mt-1')}
                    required
                    value={draft.name}
                    onChange={(event) => onDraft({ ...draft, name: event.target.value })}
                  />
                </label>
                <label className="block text-caption font-medium text-fg-secondary">
                  Endpoint
                  <input
                    className={cn(fieldClass, 'mt-1 ltr-island')}
                    required={draft.kind === 'vllm'}
                    value={draft.endpoint}
                    onChange={(event) => onDraft({ ...draft, endpoint: event.target.value })}
                    placeholder="https://…/v1"
                  />
                </label>
              </div>

              {needsCredential && (
                <label className="block text-caption font-medium text-fg-secondary">
                  {isEdit ? 'Replace API key (leave blank to keep current)' : 'API key'}
                  <div className="relative mt-1">
                    <input
                      type={showCredential ? 'text' : 'password'}
                      className={cn(fieldClass, 'ltr-island pe-10')}
                      value={credential}
                      required={!isEdit && entry?.authType === 'api_key'}
                      autoComplete="off"
                      spellCheck={false}
                      onPaste={() => setPasteDetected(true)}
                      onChange={(event) => setCredential(event.target.value)}
                    />
                    <button
                      type="button"
                      className="absolute inset-y-0 end-0 flex w-9 items-center justify-center text-fg-muted hover:text-fg-primary"
                      onClick={() => setShowCredential((value) => !value)}
                      aria-label={showCredential ? 'Hide API key' : 'Show API key'}
                    >
                      {showCredential ? (
                        <EyeOff className="size-4" aria-hidden />
                      ) : (
                        <Eye className="size-4" aria-hidden />
                      )}
                    </button>
                  </div>
                  {pasteDetected && (
                    <span className="mt-1 flex items-center gap-1 text-micro text-success-fg">
                      <Check className="size-3" aria-hidden /> Pasted — it will only be sent to the
                      OS keychain.
                    </span>
                  )}
                </label>
              )}

              <div>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-body font-medium">Models in pane menus</h3>
                    <p className="text-caption text-fg-muted">
                      Choose which models appear in every pane’s selector.
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void discover()}
                    disabled={busy !== null}
                  >
                    {busy === 'models' ? (
                      <LoaderCircle className="animate-spin" aria-hidden />
                    ) : (
                      <RefreshCw aria-hidden />
                    )}
                    Fetch models
                  </Button>
                </div>
                <div className="mt-3 max-h-52 space-y-1 overflow-y-auto rounded-md border border-border-default bg-canvas p-2">
                  {draft.models.length === 0 ? (
                    <p className="p-3 text-center text-caption text-fg-muted">
                      No models yet. Fetch or add one below.
                    </p>
                  ) : (
                    draft.models.map((model) => (
                      <label
                        key={model}
                        className="flex items-center gap-2 rounded-sm px-2 py-1.5 text-caption hover:bg-surface-2"
                      >
                        <input
                          type="checkbox"
                          checked={draft.enabledModelIds.includes(model)}
                          onChange={(event) =>
                            onDraft({
                              ...draft,
                              enabledModelIds: event.target.checked
                                ? [...draft.enabledModelIds, model]
                                : draft.enabledModelIds.filter((item) => item !== model),
                            })
                          }
                        />
                        <span className="ltr-island min-w-0 truncate">{model}</span>
                      </label>
                    ))
                  )}
                </div>
                <label className="mt-3 block text-caption font-medium text-fg-secondary">
                  Custom models (comma or line separated)
                  <textarea
                    rows={2}
                    value={customModels}
                    onChange={(event) => setCustomModels(event.target.value)}
                    className="selectable mt-1 w-full resize-y rounded-md border border-border-default bg-canvas px-3 py-2 ltr-island outline-none focus:border-accent"
                    placeholder="organization/custom-model"
                  />
                </label>
              </div>

              {result && (
                <p
                  role="status"
                  className={cn(
                    'flex items-center gap-2 rounded-md px-3 py-2 text-caption',
                    result.ok ? 'bg-success-bg text-success-fg' : 'bg-danger-bg text-danger-fg',
                  )}
                >
                  {result.ok ? (
                    <Check className="size-4" aria-hidden />
                  ) : (
                    <XCircle className="size-4" aria-hidden />
                  )}
                  {result.message}
                </p>
              )}

              <div className="sticky bottom-0 flex justify-end gap-2 border-t border-border-default bg-overlay pt-4">
                <Button type="button" onClick={onClose}>
                  Cancel
                </Button>
                <Button type="button" disabled={busy !== null} onClick={() => void test()}>
                  {busy === 'test' ? (
                    <LoaderCircle className="animate-spin" aria-hidden />
                  ) : (
                    <RefreshCw aria-hidden />
                  )}
                  Test connection
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  disabled={busy !== null || draft.enabledModelIds.length === 0}
                >
                  {busy === 'save' && <LoaderCircle className="animate-spin" aria-hidden />}
                  Save provider
                </Button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
