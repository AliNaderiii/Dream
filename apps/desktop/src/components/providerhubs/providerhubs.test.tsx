import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoProviderHubs } from '@/lib/bridge/echo-providerhubs';
import { i18n } from '@/lib/i18n';
import { useAppStore } from '@/stores/use-app-store';

import { ProviderHubsPanel } from './providerhubs-panel';

describe('Provider hubs panel', () => {
  beforeEach(async () => {
    resetBridgeClient();
    resetEchoProviderHubs();
    useAppStore.setState({ locale: 'en' });
    await i18n.changeLanguage('en');
  });

  it('shows local runtimes, route priority, and a successful Ollama doctor test', async () => {
    const { container } = render(<ProviderHubsPanel />);

    expect(await screen.findByRole('heading', { name: 'Local runtimes' })).toBeInTheDocument();
    expect(screen.getByText('hosted → aval → ollama → byok → echo')).toBeInTheDocument();
    expect(screen.getByText('Ollama recommended')).toBeInTheDocument();
    expect(screen.getByText('Local runtime detected')).toBeInTheDocument();
    expect(screen.getByText('Fallback parser')).toBeInTheDocument();
    expect(screen.getByText('Reduced reliability')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Test Ollama' }));
    expect(await screen.findByText(/Probe succeeded in 6 ms/)).toBeInTheDocument();

    const report = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(report.violations).toEqual([]);
  });

  it('toggles the optional gateway and diagnoses missing vLLM tools', async () => {
    render(<ProviderHubsPanel />);
    expect(await screen.findByRole('tab', { name: 'Tool gateway' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Tool gateway' }));
    expect(await screen.findByText(/Never required to run locally/)).toBeInTheDocument();
    expect(screen.getByText('No cloud key is required to run locally.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch', { name: 'Enable tool gateway' }));
    expect(await screen.findByText(/Gateway on/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Diagnostics' }));
    fireEvent.change(screen.getByLabelText('Runtime'), { target: { value: 'vllm' } });
    fireEvent.click(screen.getByRole('button', { name: 'Diagnose tool calling' }));
    expect(await screen.findByText('Tool calls appear as text')).toBeInTheDocument();
    expect(
      screen.getByText(/--enable-auto-tool-choice --tool-call-parser qwen/),
    ).toBeInTheDocument();
  });

  it('filters the catalog and keeps Persian privacy copy in fa', async () => {
    useAppStore.setState({ locale: 'fa' });
    render(<ProviderHubsPanel />);

    expect((await screen.findAllByText('داده روی همین دستگاه می‌ماند.')).length).toBeGreaterThan(0);
    expect(screen.getByText(/نخستین مسیر سالم برنده است/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Catalog' }));
    const search = await screen.findByLabelText('Search catalog');
    fireEvent.change(search, { target: { value: 'hosted' } });
    expect(
      await screen.findByText('در صورت استفاده از این مسیر، درخواست‌ها این دستگاه را ترک می‌کنند.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Ollama' })).not.toBeInTheDocument();
  });

  it('ships a complete Persian providerhubs bundle', () => {
    expect(i18n.t('hubTitle', { ns: 'providerhubs', lng: 'fa' })).toBe('زمان‌اجراهای محلی');
    expect(i18n.t('noCloudKey', { ns: 'providerhubs', lng: 'fa' })).toBe(
      'برای اجرای محلی به کلید ابری نیاز نیست.',
    );
  });
});
