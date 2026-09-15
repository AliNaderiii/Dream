/**
 * Typed client wrappers for Playwright & Autonomous Deep Web Browser Bridge RPC.
 */

import type { BridgeClient } from './client';
import * as echo from './echo-browser';

export interface PageElement {
  element_id: number;
  tag_name: string;
  text: string;
  selector: string;
  is_interactive: boolean;
  attributes?: Record<string, string>;
}

export interface PageSnapshot {
  url: string;
  title: string;
  content_markdown: string;
  elements: PageElement[];
  screenshot_path?: string;
  status_code: number;
  timestamp: number;
}

export interface BrowserSession {
  session_id: string;
  backend: 'playwright' | 'cdp' | 'stealth' | 'mock';
  is_active: boolean;
  current_url: string;
  page_title: string;
  actions_count: number;
  created_at: number;
}

export interface CrawlPage {
  url: string;
  title: string;
  depth: number;
  status_code: number;
  elements_count: number;
  content_preview: string;
  markdown: string;
}

export interface CrawlResult {
  status: string;
  root_url: string;
  goal: string;
  total_pages: number;
  pages: CrawlPage[];
  link_graph: Array<{ source: string; target: string; text?: string }>;
  synthesis: string;
}

export interface BrowserStatusResponse {
  status: string;
  session: BrowserSession;
  blocklist_count: number;
}

function echoOr<T>(
  client: BridgeClient,
  local: () => T,
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  if (client.transportKind === 'echo') {
    try {
      return Promise.resolve(local());
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  }
  return client.call<T>(method, params);
}

export function browserGetStatus(client: BridgeClient): Promise<BrowserStatusResponse> {
  return echoOr(client, () => echo.echoBrowserGetStatus(), 'browser.get_status', {});
}

export function browserLaunch(
  client: BridgeClient,
  backend = 'mock',
  headless = true,
): Promise<{ status: string; session: BrowserSession }> {
  return echoOr(client, () => echo.echoBrowserLaunch(backend, headless), 'browser.launch', {
    backend,
    headless,
  });
}

export function browserNavigate(
  client: BridgeClient,
  url: string,
): Promise<{ status: string; snapshot: PageSnapshot }> {
  return echoOr(client, () => echo.echoBrowserNavigate(url), 'browser.navigate', { url });
}

export function browserClick(
  client: BridgeClient,
  selector: string,
): Promise<{ status: string; result: { success: boolean; message: string } }> {
  return echoOr(client, () => echo.echoBrowserClick(selector), 'browser.click', { selector });
}

export function browserTypeText(
  client: BridgeClient,
  selector: string,
  text: string,
): Promise<{ status: string; result: { success: boolean; text: string } }> {
  return echoOr(client, () => echo.echoBrowserTypeText(selector, text), 'browser.type_text', {
    selector,
    text,
  });
}

export function browserScreenshot(
  client: BridgeClient,
  path?: string,
): Promise<{ status: string; screenshot_path: string; timestamp: number }> {
  return echoOr(client, () => echo.echoBrowserScreenshot(path), 'browser.screenshot', { path });
}

export function browserExtractContent(
  client: BridgeClient,
): Promise<{ status: string; snapshot: PageSnapshot }> {
  return echoOr(client, () => echo.echoBrowserExtractContent(), 'browser.extract_content', {});
}

export function browserDeepCrawl(
  client: BridgeClient,
  url: string,
  goal = 'Knowledge extraction',
  max_depth = 2,
  max_pages = 5,
): Promise<CrawlResult> {
  return echoOr(
    client,
    () => echo.echoBrowserDeepCrawl(url, goal, max_depth, max_pages),
    'browser.deep_crawl',
    { url, goal, max_depth, max_pages },
  );
}

export function browserClose(client: BridgeClient): Promise<{ status: string }> {
  return echoOr(client, () => echo.echoBrowserClose(), 'browser.close', {});
}

export function browserReset(client: BridgeClient): Promise<{ status: string }> {
  return echoOr(client, () => echo.echoBrowserReset(), 'browser.reset', {});
}
