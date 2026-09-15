import { describe, expect, it } from 'vitest';
import {
  browserClick,
  browserClose,
  browserDeepCrawl,
  browserExtractContent,
  browserGetStatus,
  browserLaunch,
  browserNavigate,
  browserReset,
  browserScreenshot,
  browserTypeText,
} from './browser';
import { BridgeClient, EchoBridgeTransport } from './client';

const mockClient = new BridgeClient(new EchoBridgeTransport());

describe('Browser Bridge Client (Echo Mode)', () => {
  it('fetches browser status and launches new session', async () => {
    const status = await browserGetStatus(mockClient);
    expect(status.status).toBe('healthy');
    expect(status.session.is_active).toBe(true);

    const launched = await browserLaunch(mockClient, 'mock', true);
    expect(launched.status).toBe('launched');
    expect(launched.session.backend).toBe('mock');
  });

  it('navigates to URL and extracts semantic DOM snapshot', async () => {
    const nav = await browserNavigate(mockClient, 'https://docs.dream.dev');
    expect(nav.status).toBe('navigated');
    expect(nav.snapshot.url).toBe('https://docs.dream.dev');
    expect(nav.snapshot.elements.length).toBeGreaterThan(0);

    const extracted = await browserExtractContent(mockClient);
    expect(extracted.status).toBe('extracted');
    expect(extracted.snapshot.title).toBeDefined();
  });

  it('performs interactive click and type simulator actions', async () => {
    const clickRes = await browserClick(mockClient, "button:has-text('Submit')");
    expect(clickRes.status).toBe('clicked');
    expect(clickRes.result.success).toBe(true);

    const typeRes = await browserTypeText(mockClient, "input[name='search']", 'agent mesh');
    expect(typeRes.status).toBe('typed');
    expect(typeRes.result.text).toBe('agent mesh');

    const shotRes = await browserScreenshot(mockClient);
    expect(shotRes.status).toBe('captured');
    expect(shotRes.screenshot_path).toBeDefined();
  });

  it('runs autonomous deep web crawl', async () => {
    const crawl = await browserDeepCrawl(mockClient, 'https://dream.dev', 'API Reference', 2, 3);
    expect(crawl.status).toBe('crawled');
    expect(crawl.total_pages).toBeGreaterThanOrEqual(1);
    expect(crawl.pages.length).toBeGreaterThanOrEqual(1);
    expect(crawl.synthesis).toContain('Autonomous crawl');
  });

  it('closes and resets browser state', async () => {
    const closeRes = await browserClose(mockClient);
    expect(closeRes.status).toBe('closed');

    const resetRes = await browserReset(mockClient);
    expect(resetRes.status).toBe('reset');
  });
});
