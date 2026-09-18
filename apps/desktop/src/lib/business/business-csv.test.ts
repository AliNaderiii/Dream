import { describe, expect, it } from 'vitest';

import { BUSINESS_MOVEMENTS } from './business-data';
import { businessAsk, businessLedgerSummary, businessStockBalance } from './business-data';
import { businessCsvSample, parseBusinessCsv } from './business-csv';

const MINIMAL_CSV = [
  'تاریخ,کالا,نوع,تعداد,واحد,پروژه,فرد',
  '1405/07/01,میلگرد ۱۸,ورود,50,شاخه,انبار مرکزی,سارا محمدی',
  '1405/07/02,میلگرد ۱۸,خروج,20,شاخه,برج آریا,علی رضایی',
  '1405/07/03,سیمان تیپ ۳,ورود,100,کیسه,انبار مرکزی,سارا محمدی',
].join('\n');

const ENGLISH_CSV = [
  'date,item,flow,qty,unit',
  '2026-10-01,Rebar 16,in,50,piece',
  '2026-10-02,Rebar 16,out,20,piece',
].join('\n');

describe('parseBusinessCsv', () => {
  it('parses a Persian warehouse ledger with all optional columns', () => {
    const result = parseBusinessCsv(MINIMAL_CSV, 'انبار تست');
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.dataset.movements).toHaveLength(3);
    expect(result.dataset.name).toBe('انبار تست');
    const first = result.dataset.movements[0];
    expect(first.item).toBe('میلگرد ۱۸');
    expect(first.flow).toBe('ورود');
    expect(first.qty).toBe(50);
    expect(first.project).toBe('انبار مرکزی');
  });

  it('parses English headers and inflow/outflow aliases', () => {
    const result = parseBusinessCsv(ENGLISH_CSV);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.dataset.movements).toHaveLength(2);
    expect(result.dataset.movements[1]?.flow).toBe('خروج');
    expect(result.dataset.movements[0]?.project).toBe('نامشخص');
  });

  it('rejects files that miss the required schema with an actionable error', () => {
    const result = parseBusinessCsv('a,b,c\n1,2,3');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toContain('تاریخ');
    expect(result.error).toContain('کالا');
  });

  it('handles BOM, Persian digits, thousands separators and quoted fields', () => {
    const csv = ['تاریخ,کالا,نوع,تعداد', '1405/07/01,"میلگرد, A3",ورود,۱٬۲۵۰'].join('\n');
    const result = parseBusinessCsv(`\uFEFF${csv}`);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.dataset.movements[0]?.item).toBe('میلگرد, A3');
    expect(result.dataset.movements[0]?.qty).toBe(1250);
  });

  it('round-trips the generated sample CSV through the parser', () => {
    const sample = businessCsvSample(BUSINESS_MOVEMENTS);
    const result = parseBusinessCsv(sample, 'نمونه رسمی');
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.dataset.movements).toHaveLength(BUSINESS_MOVEMENTS.length);
  });

  it('skips incomplete rows instead of failing the whole file', () => {
    const csv = [
      'تاریخ,کالا,نوع,تعداد',
      '1405/07/01,میلگرد,ورود,10',
      '1405/07/02,,ورود,10',
      '1405/07/03,سیمان,ورود,متن',
    ].join('\n');
    const result = parseBusinessCsv(csv);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.dataset.movements).toHaveLength(1);
  });
});

describe('dataset-aware analytics', () => {
  it('computes stock balance and ledger summary from a real dataset', () => {
    const parsed = parseBusinessCsv(MINIMAL_CSV, 'انبار تست');
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    const balances = businessStockBalance(parsed.dataset);
    expect(balances.get('میلگرد ۱۸')?.qty).toBe(30);
    expect(balances.get('سیمان تیپ ۳')?.qty).toBe(100);

    const summary = businessLedgerSummary(parsed.dataset);
    expect(summary.items).toBe(2);
    expect(summary.totalInQty).toBe(150);
    expect(summary.totalOutQty).toBe(20);
    expect(summary.topItem).toBe('میلگرد ۱۸');
    expect(summary.movements).toBe(3);
  });

  it('answers stock questions grounded in the uploaded dataset', () => {
    const parsed = parseBusinessCsv(MINIMAL_CSV, 'انبار تست');
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    const insight = businessAsk('موجودی انبار چقدر است؟', parsed.dataset);
    expect(insight.grounded).toBe(true);
    expect(insight.rows).toHaveLength(2);
    expect(insight.rows[0]?.کالا).toBe('سیمان تیپ ۳');
  });

  it('answers honestly when the uploaded ledger has no reference prices', () => {
    const parsed = parseBusinessCsv(MINIMAL_CSV, 'انبار تست');
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    const insight = businessAsk('ارزش ریالی موجودی؟', parsed.dataset);
    expect(insight.summary).toContain('بدون قیمت مرجع');
  });

  it('declares attendance and sales unavailable for a movements-only dataset', () => {
    const parsed = parseBusinessCsv(MINIMAL_CSV, 'انبار تست');
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(businessAsk('حضور و غیاب امروز؟', parsed.dataset).grounded).toBe(false);
    expect(businessAsk('فروش این دوره؟', parsed.dataset).grounded).toBe(false);
  });

  it('falls back to the pilot dataset when none is provided', () => {
    const insight = businessAsk('موجودی فعلی انبار به تفکیک کالا چقدر است؟');
    expect(insight.rows.length).toBeGreaterThan(5);
  });
});
