import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { pdfExportReport } from './pdf';
import type { PdfReport } from './pdf';

const REPORT: PdfReport = {
  title: 'گزارش داده کسب‌وکار — دریم',
  sections: [
    {
      heading: 'خلاصه مدیریتی',
      paragraphs: ['درآمد کل با رشد ۱۲ درصدی همراه بوده است.'],
      kpis: [{ label: 'درآمد کل', value: '۴٫۸ میلیارد تومان' }],
    },
  ],
};

describe('pdf bridge client (echo transport)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('returns an honestly-flagged demo result in the browser preview', async () => {
    const client = getBridgeClient();
    expect(client.transportKind).toBe('echo');
    const res = await pdfExportReport(client, REPORT, 'dream-report.pdf');
    expect(res.success).toBe(true);
    expect(res.demo).toBe(true);
    expect(res.file_path).toBe('dream-report.pdf');
    expect(res.note).toContain('Python core');
  });

  it('rejects an empty output path before touching the transport', async () => {
    const client = getBridgeClient();
    await expect(pdfExportReport(client, REPORT, '   ')).rejects.toThrow(
      'output path must not be empty',
    );
  });

  it('rejects a path without a .pdf extension', async () => {
    const client = getBridgeClient();
    await expect(pdfExportReport(client, REPORT, 'report.txt')).rejects.toThrow(
      'output path must end with .pdf',
    );
    await expect(pdfExportReport(client, REPORT, 'report.PDF')).resolves.toMatchObject({
      demo: true,
    });
  });
});
