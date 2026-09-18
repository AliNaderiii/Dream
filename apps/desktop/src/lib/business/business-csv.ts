/**
 * Business CSV — real organizational data ingestion for the Business Data
 * Studio (P8 / v4.2).
 *
 * Parses a warehouse-movement CSV (Persian or English headers) into the
 * studio's dataset shape so every KPI and natural-language answer is computed
 * from the company's own file instead of the bundled pilot dataset.
 *
 * The parser is deliberately dependency-free and deterministic: RFC-4180-style
 * quoting, BOM tolerance, and strict schema validation with actionable errors.
 */

import type { BusinessDataset, BusinessMovement } from './business-data';

export type ParseBusinessCsvResult =
  { ok: true; dataset: BusinessDataset } | { ok: false; error: string };

/** Accepted header spellings per logical column (Persian + English). */
const HEADER_ALIASES: Readonly<Record<string, readonly string[]>> = {
  date: ['تاریخ', 'تاريخ', 'date'],
  item: ['کالا', 'كالا', 'نام کالا', 'شرح کالا', 'item', 'product'],
  flow: ['نوع', 'گردش', 'نوع حرکت', 'flow', 'type'],
  qty: ['تعداد', 'كميت', 'کمیت', 'مقدار', 'qty', 'quantity'],
  unit: ['واحد', 'unit'],
  project: ['پروژه', 'project'],
  person: ['فرد', 'شخص', 'گزارش‌دهنده', 'person'],
};

const FLOW_OUT = new Set(['خروج', 'خروجی', 'مصرف', 'حواله', 'out', 'outflow', 'issue']);

/** Parse one RFC-4180 CSV line, honoring double-quoted fields. */
function splitCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (inQuotes) {
      if (char === '"') {
        if (line[i + 1] === '"') {
          current += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        current += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ',') {
      fields.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  fields.push(current);
  return fields.map((field) => field.trim());
}

function normalizeHeader(header: string): string {
  return header
    .replace(/\u200c/g, ' ') // ZWNJ → space so "گزارش‌دهنده" matches its alias
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function mapHeaders(headers: string[]): Record<string, number> | null {
  const mapping: Record<string, number> = {};
  for (const [logical, aliases] of Object.entries(HEADER_ALIASES)) {
    const index = headers.findIndex((header) =>
      aliases.some((alias) => normalizeHeader(header) === normalizeHeader(alias)),
    );
    if (index >= 0) mapping[logical] = index;
  }
  // تاریخ، کالا و تعداد حداقلِ لازم برای تحلیل حرکات‌اند.
  if (mapping.date === undefined || mapping.item === undefined || mapping.qty === undefined) {
    return null;
  }
  return mapping;
}

function parseQty(raw: string): number | null {
  const cleaned = raw
    .replace(/[٬,،\s]/g, '') // Persian thousands separators
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)));
  const value = Number(cleaned);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/**
 * Parse a warehouse-movement CSV into a studio dataset. Returns a typed error
 * with the expected schema so the UI can show an actionable message.
 */
export function parseBusinessCsv(text: string, name = 'CSV سازمانی'): ParseBusinessCsvResult {
  const cleaned = text.replace(/^\uFEFF/, '').trim();
  if (!cleaned) return { ok: false, error: 'فایل CSV خالی است.' };

  const lines = cleaned.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) {
    return { ok: false, error: 'حداقل یک ردیف سطرِ سرآیند و یک ردیف داده لازم است.' };
  }

  const headers = splitCsvLine(lines[0]);
  const mapping = mapHeaders(headers);
  if (!mapping) {
    return {
      ok: false,
      error:
        'سرآیندهای لازم پیدا نشد. ستون‌های «تاریخ»، «کالا» و «تعداد» الزامی‌اند؛ ستون‌های «نوع» (ورود/خروج)، «واحد»، «پروژه» و «فرد» اختیاری‌اند.',
    };
  }

  const movements: BusinessMovement[] = [];
  for (let i = 1; i < lines.length; i += 1) {
    const cells = splitCsvLine(lines[i]);
    const cell = (key: string): string => {
      const index = mapping[key];
      return index === undefined ? '' : (cells[index] ?? '');
    };

    const item = cell('item');
    const qty = parseQty(cell('qty'));
    const date = cell('date');
    if (!item || qty === null || !date) continue; // ردیف‌های ناقص به‌صورت امن رد می‌شوند.

    const rawFlow = cell('flow');
    const flow: 'ورود' | 'خروج' = FLOW_OUT.has(rawFlow) ? 'خروج' : 'ورود';

    movements.push({
      id: i,
      date,
      item,
      category: 'دسته‌بندی نشده',
      flow,
      qty,
      unit: cell('unit') || 'عدد',
      project: cell('project') || 'نامشخص',
      person: cell('person') || 'نامشخص',
    });
  }

  if (movements.length === 0) {
    return {
      ok: false,
      error: 'هیچ ردیف قابل‌پردازشی یافت نشد؛ ستون‌های تاریخ/کالا/تعداد را بررسی کنید.',
    };
  }

  return { ok: true, dataset: { name, movements } };
}

/** CSV-escape a single field. */
function csvEscape(value: string | number): string {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Serialize the pilot movements as a sample CSV (round-trips through the parser). */
export function businessCsvSample(pilotMovements: readonly BusinessMovement[]): string {
  const header = 'تاریخ,کالا,نوع,تعداد,واحد,پروژه,فرد';
  const rows = pilotMovements.map((m) =>
    [m.date, m.item, m.flow, m.qty, m.unit, m.project, m.person].map(csvEscape).join(','),
  );
  return [header, ...rows].join('\n');
}

/** Trigger a browser download of the sample CSV (no-op outside browsers). */
export function downloadBusinessCsvSample(pilotMovements: readonly BusinessMovement[]): void {
  if (typeof document === 'undefined') return;
  const blob = new Blob([`\uFEFF${businessCsvSample(pilotMovements)}`], {
    type: 'text/csv;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'dream-warehouse-sample.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}
