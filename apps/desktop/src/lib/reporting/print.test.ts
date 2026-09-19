import { describe, expect, it } from 'vitest';

import { buildPrintHtml, escapeHtml, printReport } from './print';
import type { ReportContent } from './print';

describe('escapeHtml', () => {
  it('escapes the five dangerous characters', () => {
    expect(escapeHtml('<script>"a"&\'b\'</script>')).toBe(
      '&lt;script&gt;&quot;a&quot;&amp;&#39;b&#39;&lt;/script&gt;',
    );
  });
});

describe('buildPrintHtml', () => {
  const report: ReportContent = {
    title: 'گزارش داده کسب‌وکار — دریم',
    subtitle: 'تولیدشده توسط هسته دریم',
    sections: [
      {
        heading: 'خلاصه مدیریتی',
        paragraphs: ['درآمد <محرمانه> رشد داشت.'],
        kpis: [{ label: 'درآمد کل', value: '۴٫۸ میلیارد تومان' }],
      },
      {
        heading: 'جدول',
        table: {
          columns: ['ناحیه', 'درآمد'],
          rows: [['شمال', '۱۲۰']],
        },
      },
    ],
  };

  it('renders a standalone RTL A4 print document', () => {
    const html = buildPrintHtml(report);
    expect(html).toContain('<!doctype html>');
    expect(html).toContain('dir="rtl"');
    expect(html).toContain('@page');
    expect(html).toContain('size: A4');
    expect(html).toContain('<h1>گزارش داده کسب‌وکار — دریم</h1>');
  });

  it('escapes untrusted content in paragraphs and tables', () => {
    const html = buildPrintHtml(report);
    expect(html).toContain('درآمد &lt;محرمانه&gt; رشد داشت.');
    expect(html).not.toContain('<محرمانه>');
  });

  it('renders KPI cards and data tables', () => {
    const html = buildPrintHtml(report);
    expect(html).toContain('class="kpi-label"');
    expect(html).toContain('درآمد کل');
    expect(html).toContain('<table>');
    expect(html).toContain('<td>شمال</td>');
  });

  it('handles reports with no sections', () => {
    const html = buildPrintHtml({ title: 'خالی', sections: [] });
    expect(html).toContain('<h1>خالی</h1>');
    expect(html).not.toContain('<h2>');
  });
});

describe('printReport', () => {
  it('appends a hidden print iframe to the document', () => {
    const before = document.querySelectorAll('iframe').length;
    const launched = printReport({ title: 'گزارش', sections: [] });
    expect(launched).toBe(true);
    const frame = document.querySelector('iframe[title="dream-report-print"]');
    expect(frame).toBeTruthy();
    expect(frame?.getAttribute('srcdoc')).toContain('<!doctype html>');
    frame?.remove();
    expect(document.querySelectorAll('iframe').length).toBe(before);
  });
});
