import { describe, expect, it } from 'vitest';
import { esc, fmtBytes, fmtTime, h } from './dom.js';

describe('h()', () => {
  it('creates an element with class, dataset and children', () => {
    const el = h(
      'div',
      { class: 'card x', dataset: { view: 'chat' } },
      'سلام',
      h('span', { text: 'دنیا' }),
    );
    expect(el.tagName).toBe('DIV');
    expect(el.className).toBe('card x');
    expect(el.dataset.view).toBe('chat');
    expect(el.textContent).toBe('سلامدنیا');
    expect(el.children.length).toBe(1);
  });

  it('wires event handlers', () => {
    let clicked = 0;
    const btn = h('button', { onclick: () => (clicked += 1) }, 'کلیک');
    btn.click();
    expect(clicked).toBe(1);
  });

  it('sets boolean attributes', () => {
    const btn = h('button', { disabled: true }, 'غیرفعال');
    expect(btn.hasAttribute('disabled')).toBe(true);
  });

  it('ignores null/undefined/false children', () => {
    const el = h('div', {}, null, undefined, false, 'فقط این');
    expect(el.textContent).toBe('فقط این');
  });
});

describe('esc()', () => {
  it('escapes HTML-significant characters', () => {
    expect(esc('<script>alert("x")</script>')).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;',
    );
    expect(esc("a'b&c")).toBe('a&#39;b&amp;c');
  });
});

describe('fmtBytes()', () => {
  it('formats engineering units without Persian digits', () => {
    expect(fmtBytes(512)).toBe('512 B');
    expect(fmtBytes(2048)).toBe('2.0 KB');
    expect(fmtBytes(145 * 1024 * 1024)).toBe('145 MB');
  });

  it('returns a dash for non-numbers', () => {
    expect(fmtBytes(NaN)).toBe('—');
    expect(fmtBytes(undefined)).toBe('—');
  });
});

describe('fmtTime()', () => {
  it('formats HH:MM with leading zeros', () => {
    const d = new Date(2026, 8, 22, 7, 5);
    expect(fmtTime(d)).toBe('07:05');
    expect(fmtTime(d.getTime())).toBe('07:05');
  });
});
