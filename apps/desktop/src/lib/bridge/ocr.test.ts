import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { ocrExtract, ocrExtractInvoice } from './ocr';

describe('ocr wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('returns a flagged demo result under the echo transport', async () => {
    const client = getBridgeClient();
    const result = await ocrExtract(client, 'C:\\reports\\daily.txt');
    expect(result.success).toBe(true);
    expect(result.demo).toBe(true);
    expect(result.language).toBe('fa');
    expect(result.cleaned_text).toContain('گزارش');
    expect(result.blocks_count).toBeGreaterThan(0);
  });

  it('shapes the demo invoice extraction with key-value fields', async () => {
    const client = getBridgeClient();
    const result = await ocrExtractInvoice(client, 'C:\\invoices\\inv-001.png');
    expect(result.demo).toBe(true);
    expect(result.document_type).toBe('invoice');
    expect(result.extracted_fields?.total_amount).toBeDefined();
    expect(result.extracted_fields?.date).toBeDefined();
  });

  it('rejects empty file paths before touching the transport', async () => {
    const client = getBridgeClient();
    await expect(ocrExtract(client, '   ')).rejects.toThrow(/empty/i);
    await expect(ocrExtractInvoice(client, '')).rejects.toThrow(/empty/i);
  });
});
