/**
 * Echo runtime for the Document OCR bridge (`ocr.*`) — honest deterministic
 * demo results for the browser preview, where no Python sidecar is running.
 * Every demo result is flagged with `demo: true`.
 */

import type { OcrExtractResult } from './ocr';

const GENERAL_TEXT = [
  'گزارش روزانه پروژه — برج مسکونی آریا',
  'نیروهای حاضر: ۱۲ نفر · غایب: ۱ نفر',
  'فعالیت انجام‌شده: اجرای قالب‌بندی طبقه پنجم',
  'ورود مصالح: ۲۰۰ شاخه میلگرد A3 سایز ۱۶',
  'مشکل: تاخیر در تحویل بتن آماده',
].join('\n');

const INVOICE_TEXT = [
  'فاکتور فروش خدمات',
  'تاریخ: ۱۴۰۵/۰۶/۲۵',
  'مبلغ کل: ۱۵,۰۰۰,۰۰۰ تومان',
  'مالیات: ۱,۵۰۰,۰۰۰ تومان',
  'شبا: IR820120000000012345678901',
].join('\n');

/** Deterministic demo extraction for the echo transport. */
export function echoOcrExtract(filePath: string, documentType = 'general'): OcrExtractResult {
  const invoice = documentType.toLowerCase().includes('invoice');
  const cleanedText = invoice ? INVOICE_TEXT : GENERAL_TEXT;
  return {
    success: true,
    demo: true,
    file_path: filePath,
    document_type: invoice ? 'invoice' : 'general',
    cleaned_text: cleanedText,
    raw_text: cleanedText,
    language: 'fa',
    confidence: 0.91,
    blocks_count: cleanedText.split('\n').length,
    blocks: cleanedText.split('\n').map((text, idx) => ({
      text,
      confidence: 0.9,
      direction: 'rtl',
      line_number: idx + 1,
    })),
    extracted_fields: invoice
      ? {
          total_amount: '۱۵,۰۰۰,۰۰۰',
          date: '۱۴۰۵/۰۶/۲۵',
          tax: '۱,۵۰۰,۰۰۰',
          iban: 'IR820120000000012345678901',
        }
      : {
          'نیروهای حاضر': '۱۲',
          'ورود مصالح': '۲۰۰ شاخه میلگرد A3 سایز ۱۶',
        },
    tables: [],
    metadata: { engine: 'echo-demo', note: 'Browser preview — run the desktop app for live OCR' },
  };
}
