/** Deterministic echo runtime for browse.* */

export interface BrowseLink {
  url: string;
  host: string;
}

export interface BrowseDraft {
  draft_id: string;
  url: string;
  status: 'APPROVAL_PENDING' | 'fetched' | 'refused' | 'denied';
  yolo: false;
  chrome_profile: false;
  computer_use: false;
  hosted_fetch: boolean;
  excerpt: string;
  title: string;
  links: BrowseLink[];
  truncated: boolean;
}

const drafts: BrowseDraft[] = [];

function requireUrl(url: string): string {
  const raw = url.trim();
  if (!raw) throw new Error('url must be a public http(s) address of at most 2048 characters');
  if (/^(file|javascript|data|chrome|about):/i.test(raw)) {
    throw new Error('only public http(s) URLs are allowed');
  }
  if (/@/.test(raw.split('/')[2] ?? '')) throw new Error('credentials in URL are refused');
  if (/https?:\/\/(localhost|127\.0\.0\.1|169\.254\.|192\.168\.|10\.\d)/i.test(raw)) {
    throw new Error('localhost and internal hosts are refused');
  }
  if (!/^https?:\/\//i.test(raw)) throw new Error('only public http(s) URLs are allowed');
  return raw;
}

export function echoBrowsePropose(url: string, yolo = false) {
  if (yolo) throw new Error('YOLO cannot open pages');
  const address = requireUrl(url);
  const draft: BrowseDraft = {
    draft_id: `brw_echo_${drafts.length + 1}`,
    url: address,
    status: 'APPROVAL_PENDING',
    yolo: false,
    chrome_profile: false,
    computer_use: false,
    hosted_fetch: false,
    excerpt: '',
    title: 'example.com',
    links: [],
    truncated: false,
  };
  drafts.push(draft);
  return draft;
}

export function echoBrowseList() {
  return { drafts: drafts.map((row) => ({ ...row })), count: drafts.length };
}

export function echoBrowseGet(draftId: string) {
  const row = drafts.find((item) => item.draft_id === draftId);
  if (!row) throw new Error('no browse draft');
  return row;
}

export function echoBrowseApprove(draftId: string, approved = false) {
  if (!approved) throw new Error('missing approver — refuse');
  const row = drafts.find((item) => item.draft_id === draftId);
  if (!row) throw new Error('no browse draft');
  row.status = 'fetched';
  row.hosted_fetch = false;
  row.title = 'Echo page';
  row.excerpt = `Echo page for ${row.url}`;
  row.links = [{ url: 'https://example.com/next', host: 'example.com' }];
  return row;
}

export function echoBrowseDeny(draftId: string) {
  const index = drafts.findIndex((row) => row.draft_id === draftId);
  if (index < 0) throw new Error('no browse draft');
  const [row] = drafts.splice(index, 1);
  return {
    applied: false,
    draft_id: draftId,
    url: row.url,
    status: 'denied' as const,
    hosted_fetch: false,
    chrome_profile: false as const,
    computer_use: false as const,
    yolo: false as const,
  };
}

export function echoBrowseFollow(draftId: string, url: string, yolo = false) {
  const row = echoBrowseGet(draftId);
  if (row.status !== 'fetched') throw new Error('only fetched pages expose followable links');
  const allowed = row.links.some((item) => item.url === url);
  if (!allowed) throw new Error('url is not an extracted link from this page');
  return echoBrowsePropose(url, yolo);
}

export function resetEchoBrowse(): void {
  drafts.length = 0;
}
