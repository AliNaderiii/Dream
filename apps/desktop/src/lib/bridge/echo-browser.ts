/**
 * Offline Echo implementation for Playwright & Autonomous Browser Automation subsystem.
 */

import type { BrowserSession, BrowserStatusResponse, CrawlResult, PageSnapshot } from './browser';

let currentSession: BrowserSession = {
  session_id: 'b_sess_echo_01',
  backend: 'mock',
  is_active: true,
  current_url: 'https://docs.dream-ai.dev',
  page_title: 'Dream AI Autonomous Browser',
  actions_count: 3,
  created_at: Date.now() / 1000 - 3600,
};

let lastSnapshot: PageSnapshot = {
  url: 'https://docs.dream-ai.dev',
  title: 'Dream AI Framework Documentation',
  content_markdown:
    '# Dream AI Autonomous Framework\n\nWelcome to the Dream autonomous agent suite.\n\n## Core Subsystems\n\n- **Swarm Neural Mesh**: Decentralized collaborative agents.\n- **Polyglot Sandbox**: Safe multi-language isolated execution.\n- **Deep Web Crawler**: Intelligent Playwright DOM perception.',
  elements: [
    {
      element_id: 1,
      tag_name: 'a',
      text: 'API Reference',
      selector: "a[href='/api']",
      is_interactive: true,
      attributes: { href: 'https://docs.dream-ai.dev/api' },
    },
    {
      element_id: 2,
      tag_name: 'input',
      text: 'Search docs...',
      selector: "input[name='q']",
      is_interactive: true,
      attributes: { type: 'text', name: 'q', placeholder: 'Search docs...' },
    },
    {
      element_id: 3,
      tag_name: 'button',
      text: 'Search',
      selector: "button:has-text('Search')",
      is_interactive: true,
    },
  ],
  screenshot_path: '/tmp/dream_screenshot_echo.png',
  status_code: 200,
  timestamp: Date.now() / 1000,
};

export function echoBrowserGetStatus(): BrowserStatusResponse {
  return {
    status: currentSession.is_active ? 'healthy' : 'inactive',
    session: { ...currentSession },
    blocklist_count: 24,
  };
}

export function echoBrowserLaunch(
  backend = 'mock',
  _headless = true,
): { status: string; session: BrowserSession } {
  currentSession = {
    session_id: `b_sess_${Math.random().toString(36).substring(2, 8)}`,
    backend: backend as BrowserSession['backend'],
    is_active: true,
    current_url: 'about:blank',
    page_title: 'Blank Page',
    actions_count: 0,
    created_at: Date.now() / 1000,
  };
  return {
    status: 'launched',
    session: { ...currentSession },
  };
}

export function echoBrowserNavigate(url: string): { status: string; snapshot: PageSnapshot } {
  if (!url || url.includes('127.0.0.1') || url.includes('localhost')) {
    throw new Error('Access to local/internal host is refused (SSRF protection)');
  }

  currentSession.current_url = url;
  currentSession.actions_count += 1;
  currentSession.page_title = `${new URL(url.startsWith('http') ? url : `https://${url}`).hostname} - Dream Explorer`;

  lastSnapshot = {
    url,
    title: currentSession.page_title,
    content_markdown: `# ${currentSession.page_title}\n\nRetrieved content from ${url}.\n\n- Discovered interactive endpoints.\n- Semantic text extracted cleanly without tracking tags.`,
    elements: [
      {
        element_id: 1,
        tag_name: 'a',
        text: 'Home Navigation',
        selector: "a[href='/']",
        is_interactive: true,
        attributes: { href: `${url}/` },
      },
      {
        element_id: 2,
        tag_name: 'input',
        text: 'Input Keyword',
        selector: "input[name='search']",
        is_interactive: true,
        attributes: { name: 'search', type: 'text' },
      },
      {
        element_id: 3,
        tag_name: 'button',
        text: 'Submit Action',
        selector: "button:has-text('Submit')",
        is_interactive: true,
      },
    ],
    screenshot_path: `/tmp/shot_${Date.now()}.png`,
    status_code: 200,
    timestamp: Date.now() / 1000,
  };

  return {
    status: 'navigated',
    snapshot: { ...lastSnapshot },
  };
}

export function echoBrowserClick(selector: string): {
  status: string;
  result: { success: boolean; message: string };
} {
  currentSession.actions_count += 1;
  return {
    status: 'clicked',
    result: {
      success: true,
      message: `Successfully clicked selector '${selector}'`,
    },
  };
}

export function echoBrowserTypeText(
  _selector: string,
  text: string,
): { status: string; result: { success: boolean; text: string } } {
  currentSession.actions_count += 1;
  return {
    status: 'typed',
    result: {
      success: true,
      text,
    },
  };
}

export function echoBrowserScreenshot(path?: string): {
  status: string;
  screenshot_path: string;
  timestamp: number;
} {
  currentSession.actions_count += 1;
  return {
    status: 'captured',
    screenshot_path: path || `/tmp/shot_${Date.now()}.png`,
    timestamp: Date.now() / 1000,
  };
}

export function echoBrowserExtractContent(): { status: string; snapshot: PageSnapshot } {
  return {
    status: 'extracted',
    snapshot: { ...lastSnapshot },
  };
}

export function echoBrowserDeepCrawl(
  url: string,
  goal = 'Knowledge extraction',
  max_depth = 2,
  max_pages = 4,
): CrawlResult {
  if (!url || url.includes('127.0.0.1') || url.includes('localhost')) {
    throw new Error('Access to local/internal host is refused (SSRF protection)');
  }

  const pages = [
    {
      url,
      title: 'Root Documentation Index',
      depth: 1,
      status_code: 200,
      elements_count: 8,
      content_preview: 'Introduction and architectural overview of Dream system modules.',
      markdown: '# Root Documentation\n\nOverview of the autonomous agent platform.',
    },
    {
      url: `${url}/guide/getting-started`,
      title: 'Getting Started Guide',
      depth: Math.min(2, max_depth),
      status_code: 200,
      elements_count: 5,
      content_preview: 'Step by step installation and configuration instructions.',
      markdown: '# Getting Started\n\nHow to initialize and configure local models.',
    },
    {
      url: `${url}/api/reference`,
      title: 'Full API Reference',
      depth: Math.min(2, max_depth),
      status_code: 200,
      elements_count: 12,
      content_preview: 'Complete RPC bridge specification and data contracts.',
      markdown: '# API Reference\n\nDetailed parameters for all bridge endpoints.',
    },
  ].slice(0, max_pages);

  return {
    status: 'crawled',
    root_url: url,
    goal,
    total_pages: pages.length,
    pages,
    link_graph: [
      { source: url, target: `${url}/guide/getting-started`, text: 'Getting Started' },
      { source: url, target: `${url}/api/reference`, text: 'API Docs' },
    ],
    synthesis: `Autonomous crawl of ${url} completed: Extracted ${pages.length} pages and synthesized key resources for goal '${goal}'.`,
  };
}

export function echoBrowserClose(): { status: string } {
  currentSession.is_active = false;
  return { status: 'closed' };
}

export function echoBrowserReset(): { status: string } {
  currentSession = {
    session_id: 'b_sess_reset_01',
    backend: 'mock',
    is_active: true,
    current_url: 'about:blank',
    page_title: 'Blank Page',
    actions_count: 0,
    created_at: Date.now() / 1000,
  };
  return { status: 'reset' };
}
