/**
 * Business Data pilot — bundled Persian organizational dataset plus a local
 * analytics engine.
 *
 * The Dream Next "Business Data Studio" uses this module in two ways:
 *
 * - Browser/echo mode: the dataset below powers the demo analytics so the
 *   studio is fully explorable with no Python sidecar running.
 * - Tauri mode: the studio calls the real `dataqa.*` bridge methods against
 *   the company's own files; this module only provides the KPI preview cards
 *   and the suggested questions.
 *
 * Everything is deterministic (seeded PRNG, fixed Jalali dates) and pure —
 * no Date.now()/Math.random() at module or call time — so React renders stay
 * pure and unit tests are stable.
 */

export interface BusinessCatalogItem {
  code: string;
  name: string;
  category: string;
  unit: string;
  spec: string;
  refPriceToman: number;
}

export interface BusinessMovement {
  id: number;
  /** Jalali date, e.g. '1405/06/12'. */
  date: string;
  item: string;
  category: string;
  flow: 'ورود' | 'خروج';
  qty: number;
  unit: string;
  project: string;
  person: string;
}

export interface BusinessStaff {
  name: string;
  role: string;
  project: string;
}

export interface BusinessAttendance {
  date: string;
  name: string;
  role: string;
  present: boolean;
}

export interface BusinessSale {
  id: number;
  date: string;
  item: string;
  qty: number;
  unitPriceToman: number;
  buyer: string;
}

/** A connected organizational dataset — the bundled pilot or a real CSV. */
export interface BusinessDataset {
  name: string;
  movements: readonly BusinessMovement[];
}

/** Ledger-only summary for real uploaded CSVs (no reference prices needed). */
export interface BusinessLedgerSummary {
  items: number;
  totalInQty: number;
  totalOutQty: number;
  movements: number;
  topItem: string;
  topItemQty: number;
}

export interface BusinessKpis {
  activeItems: number;
  totalStockValueToman: number;
  monthOutMovements: number;
  monthOutTopItem: string;
  deadStockItems: string[];
  attendanceRatePct: number;
  absentToday: string[];
  salesTotalToman: number;
  salesTopBuyer: string;
}

export interface BusinessInsight {
  /** Stable id for React keys. */
  id: string;
  question: string;
  answer: string;
  summary: string;
  grounded: boolean;
  columns: string[];
  rows: Array<Record<string, string | number>>;
  chart: { type: 'bar'; labels: string[]; values: number[]; unit: string } | null;
}

/** Deterministic PRNG (mulberry32) — same seed, same dataset, forever. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const BUSINESS_CATALOG: readonly BusinessCatalogItem[] = [
  {
    code: 'WH-001',
    name: 'میلگرد A3 سایز ۱۶',
    category: 'آهن‌آلات',
    unit: 'شاخه',
    spec: '۱۲ متر · بسته‌بندی کارخانه',
    refPriceToman: 1_850_000,
  },
  {
    code: 'WH-002',
    name: 'میلگرد A3 سایز ۲۰',
    category: 'آهن‌آلات',
    unit: 'شاخه',
    spec: '۱۲ متر · بسته‌بندی کارخانه',
    refPriceToman: 2_900_000,
  },
  {
    code: 'WH-003',
    name: 'تیرآهن IPE ۱۴',
    category: 'آهن‌آلات',
    unit: 'شاخه',
    spec: '۱۲ متر · نمره ۱۴',
    refPriceToman: 9_400_000,
  },
  {
    code: 'WH-004',
    name: 'سیمان تیپ ۲',
    category: 'مصالح پایه',
    unit: 'کیسه',
    spec: '۵۰ کیلوگرم · کارخانه تهران',
    refPriceToman: 96_000,
  },
  {
    code: 'WH-005',
    name: 'گچ ساختمانی',
    category: 'مصالح پایه',
    unit: 'کیسه',
    spec: '۲۵ کیلوگرم',
    refPriceToman: 78_000,
  },
  {
    code: 'WH-006',
    name: 'ماسه شسته',
    category: 'مصالح پایه',
    unit: 'متر مکعب',
    spec: 'دانه‌بندی میانه',
    refPriceToman: 640_000,
  },
  {
    code: 'WH-007',
    name: 'شن بتن',
    category: 'مصالح پایه',
    unit: 'متر مکعب',
    spec: 'دانه‌بندی درشت',
    refPriceToman: 720_000,
  },
  {
    code: 'WH-008',
    name: 'آجر فشاری ماشینی',
    category: 'مصالح پایه',
    unit: 'هزار عدد',
    spec: 'سوراخ‌دار ۱۰ سوراخ',
    refPriceToman: 4_200_000,
  },
  {
    code: 'WH-009',
    name: 'بتن آماده C30',
    category: 'مصالح پایه',
    unit: 'متر مکعب',
    spec: 'ردیف آماده پمپ',
    refPriceToman: 3_950_000,
  },
  {
    code: 'WH-010',
    name: 'ایزوگام دودی',
    category: 'عایق‌کاری',
    unit: 'رول',
    spec: '۱۰ متر مربع · لایه دودی',
    refPriceToman: 1_150_000,
  },
  {
    code: 'WH-011',
    name: 'لوله پلی‌اتیلن ۱۱۰',
    category: 'تأسیسات',
    unit: 'متر',
    spec: 'قطر ۱۱۰ میلی‌متر',
    refPriceToman: 310_000,
  },
  {
    code: 'WH-012',
    name: 'لوله فاضلاب PVC',
    category: 'تأسیسات',
    unit: 'متر',
    spec: 'قطر ۱۱۰ میلی‌متر',
    refPriceToman: 240_000,
  },
  {
    code: 'WH-013',
    name: 'کابل برق ۳×۲.۵',
    category: 'برق',
    unit: 'متر',
    spec: 'مس · عایق PVC',
    refPriceToman: 185_000,
  },
  {
    code: 'WH-014',
    name: 'کاشی کف ۶۰×۶۰',
    category: 'نازک‌کاری',
    unit: 'متر مربع',
    spec: 'درجه یک · طرح ساده',
    refPriceToman: 890_000,
  },
  {
    code: 'WH-015',
    name: 'شیشه دوجداره',
    category: 'نازک‌کاری',
    unit: 'متر مربع',
    spec: '۶ میلی‌متر + خلأ',
    refPriceToman: 1_480_000,
  },
  {
    code: 'WH-016',
    name: 'رنگ روغنی پایه روغنی',
    category: 'نازک‌کاری',
    unit: 'گالن',
    spec: '۴ کیلوگرم · سفید',
    refPriceToman: 1_020_000,
  },
];

export const BUSINESS_PROJECTS: readonly string[] = [
  'برج مسکونی آریا',
  'مجتمع تجاری پارس',
  'کارخانه شیشه نوین',
  'ویلای چالوس',
];

export const BUSINESS_STAFF: readonly BusinessStaff[] = [
  { name: 'علی رضایی', role: 'سرپرست پروژه', project: 'برج مسکونی آریا' },
  { name: 'محمدرضا کریمی', role: 'انباردار', project: 'انبار مرکزی' },
  { name: 'حسین احمدی', role: 'پیمانکار اجرا', project: 'مجتمع تجاری پارس' },
  { name: 'زهرا موسوی', role: 'سرپرست اجرا', project: 'کارخانه شیشه نوین' },
  { name: 'رضا قاسمی', role: 'انباردار', project: 'انبار مرکزی' },
  { name: 'مهدی نوری', role: 'تکنسین تأسیسات', project: 'برج مسکونی آریا' },
  { name: 'سارا محمدی', role: 'کارشناس تدارکات', project: 'دفتر مرکزی' },
  { name: 'امیر حسینی', role: 'پیمانکار سازه', project: 'ویلای چالوس' },
];

export const BUSINESS_BUYERS: readonly string[] = [
  'شرکت ساختمانی آرمان',
  'گروه صنعتی کویر',
  'ابنیه هوشمند پارس',
  'personal construction — مشتری جزء',
  'تعاونی مسکن کارکنان',
];

/** مرداد و شهریور ۱۴۰۵ — دو ماه گزارش روزانه. */
const DATES: readonly string[] = [
  '1405/05/15',
  '1405/05/16',
  '1405/05/17',
  '1405/05/18',
  '1405/05/19',
  '1405/05/20',
  '1405/05/21',
  '1405/05/22',
  '1405/05/23',
  '1405/05/24',
  '1405/05/25',
  '1405/05/26',
  '1405/05/27',
  '1405/05/28',
  '1405/05/29',
  '1405/05/30',
  '1405/06/01',
  '1405/06/02',
  '1405/06/03',
  '1405/06/04',
  '1405/06/05',
  '1405/06/06',
  '1405/06/07',
  '1405/06/08',
  '1405/06/09',
  '1405/06/10',
  '1405/06/11',
  '1405/06/12',
  '1405/06/13',
  '1405/06/14',
  '1405/06/15',
  '1405/06/16',
  '1405/06/17',
  '1405/06/18',
  '1405/06/19',
  '1405/06/20',
  '1405/06/21',
  '1405/06/22',
  '1405/06/23',
  '1405/06/24',
  '1405/06/25',
  '1405/06/26',
];

function buildMovements(): BusinessMovement[] {
  const rnd = mulberry32(1405);
  const out: BusinessMovement[] = [];
  let id = 1;
  // ورودها: خریدهای دوره — هر کالا ۲ تا ۴ ورود.
  for (const item of BUSINESS_CATALOG) {
    const deliveries = 2 + Math.floor(rnd() * 3);
    for (let d = 0; d < deliveries; d += 1) {
      const date = DATES[Math.floor(rnd() * DATES.length)];
      const qty = 20 + Math.floor(rnd() * 180);
      out.push({
        id: id++,
        date,
        item: item.name,
        category: item.category,
        flow: 'ورود',
        qty,
        unit: item.unit,
        project: 'انبار مرکزی',
        person: 'سارا محمدی',
      });
    }
  }
  // خروجها: حواله پروژه‌ها — آیتم‌های پرمصرف بیشتر تکرار می‌شوند.
  const hotItems = [
    'سیمان تیپ ۲',
    'میلگرد A3 سایز ۱۶',
    'ماسه شسته',
    'بتن آماده C30',
    'آجر فشاری ماشینی',
  ];
  for (let d = 0; d < 90; d += 1) {
    const useHot = rnd() < 0.62;
    const item = useHot
      ? BUSINESS_CATALOG.find((c) => c.name === hotItems[Math.floor(rnd() * hotItems.length)])
      : BUSINESS_CATALOG[Math.floor(rnd() * BUSINESS_CATALOG.length)];
    if (!item) continue;
    const date = DATES[Math.floor(rnd() * DATES.length)];
    const qty = 5 + Math.floor(rnd() * 60);
    const project = BUSINESS_PROJECTS[Math.floor(rnd() * BUSINESS_PROJECTS.length)];
    const person = BUSINESS_STAFF[Math.floor(rnd() * BUSINESS_STAFF.length)].name;
    out.push({
      id: id++,
      date,
      item: item.name,
      category: item.category,
      flow: 'خروج',
      qty,
      unit: item.unit,
      project,
      person,
    });
  }
  return out.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id - b.id));
}

export const BUSINESS_MOVEMENTS: readonly BusinessMovement[] = buildMovements();

function buildAttendance(): BusinessAttendance[] {
  const rnd = mulberry32(4105);
  const out: BusinessAttendance[] = [];
  for (const date of DATES) {
    for (const person of BUSINESS_STAFF) {
      // پنج‌شنبه‌ها (هر ۷ تاریخ یک‌بار) نیمه‌کار و برخی غایب.
      const r = rnd();
      out.push({
        date,
        name: person.name,
        role: person.role,
        present: r > 0.12,
      });
    }
  }
  return out;
}

export const BUSINESS_ATTENDANCE: readonly BusinessAttendance[] = buildAttendance();

function buildSales(): BusinessSale[] {
  const rnd = mulberry32(905);
  const sellable = BUSINESS_CATALOG.filter((c) =>
    [
      'میلگرد A3 سایز ۱۶',
      'میلگرد A3 سایز ۲۰',
      'سیمان تیپ ۲',
      'ایزوگام دودی',
      'کاشی کف ۶۰×۶۰',
      'شیشه دوجداره',
      'کابل برق ۳×۲.۵',
    ].includes(c.name),
  );
  const out: BusinessSale[] = [];
  let id = 1;
  for (let i = 0; i < 38; i += 1) {
    const item = sellable[Math.floor(rnd() * sellable.length)];
    if (!item) continue;
    out.push({
      id: id++,
      date: DATES[Math.floor(rnd() * DATES.length)],
      item: item.name,
      qty: 3 + Math.floor(rnd() * 40),
      unitPriceToman: item.refPriceToman,
      buyer: BUSINESS_BUYERS[Math.floor(rnd() * BUSINESS_BUYERS.length)],
    });
  }
  return out.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id - b.id));
}

export const BUSINESS_SALES: readonly BusinessSale[] = buildSales();

const faNum = (n: number): string => n.toLocaleString('fa-IR');

/** موجودی فعلی هر کالا = مجموع ورود − مجموع خروج (پایلوت یا داده واقعی CSV). */
export function businessStockBalance(
  dataset?: BusinessDataset,
): Map<string, { qty: number; unit: string; valueToman: number }> {
  const movements = dataset?.movements ?? BUSINESS_MOVEMENTS;
  const priceByName = new Map(BUSINESS_CATALOG.map((c) => [c.name, c.refPriceToman]));
  const agg = new Map<string, { qty: number; unit: string }>();
  for (const m of movements) {
    const entry = agg.get(m.item) ?? { qty: 0, unit: m.unit };
    entry.qty += m.flow === 'ورود' ? m.qty : -m.qty;
    agg.set(m.item, entry);
  }
  const out = new Map<string, { qty: number; unit: string; valueToman: number }>();
  for (const [name, e] of agg) {
    out.set(name, {
      qty: e.qty,
      unit: e.unit,
      valueToman: Math.max(0, e.qty) * (priceByName.get(name) ?? 0),
    });
  }
  return out;
}

/** خلاصه دفتر حرکات برای داده واقعی — بدون نیاز به قیمت مرجع. */
export function businessLedgerSummary(dataset: BusinessDataset): BusinessLedgerSummary {
  let totalInQty = 0;
  let totalOutQty = 0;
  const outByItem = new Map<string, number>();
  const items = new Set<string>();
  for (const m of dataset.movements) {
    items.add(m.item);
    if (m.flow === 'ورود') totalInQty += m.qty;
    else {
      totalOutQty += m.qty;
      outByItem.set(m.item, (outByItem.get(m.item) ?? 0) + m.qty);
    }
  }
  const top = [...outByItem.entries()].sort((a, b) => b[1] - a[1])[0];
  return {
    items: items.size,
    totalInQty,
    totalOutQty,
    movements: dataset.movements.length,
    topItem: top?.[0] ?? '—',
    topItemQty: top?.[1] ?? 0,
  };
}

/** شاخص‌های کلیدی مدیریتی — همان چیزی که مدیر ارشد در «یک نگاه» می‌خواهد. */
export function businessKpis(today = '1405/06/26', dataset?: BusinessDataset): BusinessKpis {
  const movements = dataset?.movements ?? BUSINESS_MOVEMENTS;
  const balances = businessStockBalance(dataset);
  const activeItems = [...balances.values()].filter((b) => b.qty > 0).length;
  const totalStockValueToman = [...balances.values()].reduce((sum, b) => sum + b.valueToman, 0);

  const month = today.slice(0, 7); // '1405/06'
  const monthOut = movements.filter((m) => m.flow === 'خروج' && m.date.startsWith(month));
  const outByItem = new Map<string, number>();
  for (const m of monthOut) outByItem.set(m.item, (outByItem.get(m.item) ?? 0) + m.qty);
  const monthOutTopItem = [...outByItem.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—';

  const deadStockItems = [...balances.entries()]
    .filter(
      ([name, b]) => b.qty > 0 && !movements.some((m) => m.item === name && m.flow === 'خروج'),
    )
    .map(([name]) => name);

  const todayRows = BUSINESS_ATTENDANCE.filter((a) => a.date === today);
  const presentCount = todayRows.filter((a) => a.present).length;
  const attendanceRatePct = todayRows.length
    ? Math.round((presentCount / todayRows.length) * 100)
    : 0;
  const absentToday = todayRows.filter((a) => !a.present).map((a) => a.name);

  const salesTotalToman = BUSINESS_SALES.reduce((sum, s) => sum + s.qty * s.unitPriceToman, 0);
  const byBuyer = new Map<string, number>();
  for (const s of BUSINESS_SALES)
    byBuyer.set(s.buyer, (byBuyer.get(s.buyer) ?? 0) + s.qty * s.unitPriceToman);
  const salesTopBuyer = [...byBuyer.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—';

  return {
    activeItems,
    totalStockValueToman,
    monthOutMovements: monthOut.length,
    monthOutTopItem,
    deadStockItems,
    attendanceRatePct,
    absentToday,
    salesTotalToman,
    salesTopBuyer,
  };
}

/** پرسش‌های پیشنهادی برای شروع کار با استودیو. */
export const BUSINESS_SUGGESTED_QUESTIONS: readonly string[] = [
  'موجودی فعلی انبار به تفکیک کالا چقدر است؟',
  'پرمصرف‌ترین کالای این ماه کدام بوده؟',
  'ارزش ریالی موجودی انبار چقدر است؟',
  'وضعیت حضور و غیاب نیروها امروز چطور بود؟',
  'کالاهای راکد کدام‌اند؟',
  'مجموع فروش و بزرگ‌ترین مشتری چه بوده؟',
];

/**
 * موتور تحلیل محلی (حالت نمایشی مرورگر) — خانواده‌های پرسش را با کلیدواژه
 * تشخیص می‌دهد و از روی همین مجموعه‌داده پاسخ می‌سازد. در حالت دسکتاپ همین
 * پرسش‌ها از مسیر واقعی `dataqa.ask` به هسته پایتون می‌روند.
 */
export function businessAsk(question: string, dataset?: BusinessDataset): BusinessInsight {
  const q = question.trim();
  const balances = businessStockBalance(dataset);
  const movements = dataset?.movements ?? BUSINESS_MOVEMENTS;

  if (/موجودی|انبار|اشتاک|stock/i.test(q) && !/ارزش|ریال|تومان/.test(q)) {
    const rows = [...balances.entries()]
      .sort((a, b) => b[1].qty - a[1].qty)
      .slice(0, 10)
      .map(([name, b]) => ({ کالا: name, موجودی: b.qty, واحد: b.unit }));
    const top = rows.slice(0, 6);
    return {
      id: 'stock',
      question: q,
      answer: `موجودی فعلی انبار مرکزی برای ${faNum(balances.size)} قلم کالا محاسبه شد. پر موجودیت‌ترین کالا «${top[0]?.کالا ?? '—'}» با ${faNum(top[0]?.موجودی ?? 0)} ${top[0]?.واحد ?? ''} است.`,
      summary: 'گزارش موجودی به تفکیک کالا',
      grounded: true,
      columns: ['کالا', 'موجودی', 'واحد'],
      rows,
      chart: {
        type: 'bar',
        labels: top.map((r) => String(r.کالا)),
        values: top.map((r) => Number(r.موجودی)),
        unit: 'مقدار',
      },
    };
  }

  if (/ارزش|ریال|تومان|مالی/.test(q)) {
    const rows = [...balances.entries()]
      .sort((a, b) => b[1].valueToman - a[1].valueToman)
      .slice(0, 10)
      .map(([name, b]) => ({
        کالا: name,
        'ارزش (میلیون تومان)': Math.round(b.valueToman / 1_000_000),
      }));
    const total = rows.reduce((s, r) => s + Number(r['ارزش (میلیون تومان)']), 0);
    if (dataset && total === 0) {
      const qtyRows = [...balances.entries()]
        .sort((a, b) => b[1].qty - a[1].qty)
        .slice(0, 10)
        .map(([name, b]) => ({ کالا: name, موجودی: b.qty, واحد: b.unit }));
      return {
        id: 'value',
        question: q,
        answer:
          'قیمت مرجع کالاهای این فایل در کاتالوگ پایلوت موجود نیست، بنابراین ارزش ریالی قابل محاسبه نیست. موجودی عددی هر کالا در جدول ضمیمه است؛ با افزودن ستون قیمت به داده سازمانی، این تحلیل فعال می‌شود.',
        summary: 'موجودی عددی (بدون قیمت مرجع)',
        grounded: true,
        columns: ['کالا', 'موجودی', 'واحد'],
        rows: qtyRows,
        chart: {
          type: 'bar',
          labels: qtyRows.slice(0, 6).map((r) => String(r.کالا)),
          values: qtyRows.slice(0, 6).map((r) => Number(r.موجودی)),
          unit: 'مقدار',
        },
      };
    }
    return {
      id: 'value',
      question: q,
      answer: `ارزش کل موجودی انبار (بر اساس قیمت مرجع خرید) حدود ${faNum(total)} میلیون تومان برآورد می‌شود؛ سهم اصلی با «${rows[0]?.کالا ?? '—'}» است.`,
      summary: 'ارزش ریالی موجودی',
      grounded: true,
      columns: ['کالا', 'ارزش (میلیون تومان)'],
      rows,
      chart: {
        type: 'bar',
        labels: rows.slice(0, 6).map((r) => String(r.کالا)),
        values: rows.slice(0, 6).map((r) => Number(r['ارزش (میلیون تومان)'])),
        unit: 'میلیون تومان',
      },
    };
  }

  if (/حضور|غیاب|غایب|نیرو|کارکنان|پرسنل/.test(q)) {
    if (dataset) {
      return {
        id: 'attendance',
        question: q,
        answer:
          'داده حضور و غیاب در فایل حرکات انبارِ بارگذاری‌شده موجود نیست. برای این تحلیل، فایل حضور و غیاب (تاریخ، نام، وضعیت) را جداگانه بارگذاری کنید.',
        summary: 'داده موجود نیست',
        grounded: false,
        columns: [],
        rows: [],
        chart: null,
      };
    }
    const kpis = businessKpis();
    const rows = BUSINESS_ATTENDANCE.filter((a) => a.date === '1405/06/26').map((a) => ({
      نام: a.name,
      نقش: a.role,
      وضعیت: a.present ? 'حاضر' : 'غایب',
    }));
    return {
      id: 'attendance',
      question: q,
      answer: `نرخ حضور امروز ${faNum(kpis.attendanceRatePct)}٪ بوده است. ${kpis.absentToday.length ? `غایبان: ${kpis.absentToday.join('، ')}.` : 'همه نیروها حاضرند.'}`,
      summary: 'حضور و غیاب امروز',
      grounded: true,
      columns: ['نام', 'نقش', 'وضعیت'],
      rows,
      chart: null,
    };
  }

  if (/راکد|بی‌حرکت|dead/.test(q)) {
    const kpis = businessKpis('1405/06/26', dataset);
    const rows = kpis.deadStockItems.map((name) => ({
      کالا: name,
      'موجودی (واحد)': balances.get(name)?.qty ?? 0,
      'آخرین خروج': 'ندارد',
    }));
    return {
      id: 'dead',
      question: q,
      answer: kpis.deadStockItems.length
        ? `${faNum(kpis.deadStockItems.length)} قلم کالا در دوره گزارش هیچ خروجی نداشته‌اند: ${kpis.deadStockItems.join('، ')}. پیشنهاد: بازنگری برنامه خرید یا انتقال بین پروژه‌ها.`
        : 'هیچ کالای راکدی شناسایی نشد.',
      summary: 'کالاهای بدون مصرف',
      grounded: true,
      columns: ['کالا', 'موجودی (واحد)', 'آخرین خروج'],
      rows,
      chart: null,
    };
  }

  if (/فروش|مشتری|خریدار|فاکتور/.test(q)) {
    if (dataset) {
      return {
        id: 'sales',
        question: q,
        answer:
          'داده فروش در فایل حرکات انبارِ بارگذاری‌شده موجود نیست. برای این تحلیل، فایل فاکتورها (تاریخ، کالا، تعداد، مبلغ، مشتری) را جداگانه بارگذاری کنید.',
        summary: 'داده موجود نیست',
        grounded: false,
        columns: [],
        rows: [],
        chart: null,
      };
    }
    const byBuyer = new Map<string, number>();
    for (const s of BUSINESS_SALES)
      byBuyer.set(s.buyer, (byBuyer.get(s.buyer) ?? 0) + s.qty * s.unitPriceToman);
    const rows = [...byBuyer.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([buyer, total]) => ({
        مشتری: buyer,
        'مبلغ (میلیون تومان)': Math.round(total / 1_000_000),
      }));
    const total = BUSINESS_SALES.reduce((s, s2) => s + s2.qty * s2.unitPriceToman, 0);
    return {
      id: 'sales',
      question: q,
      answer: `مجموع فروش دوره ${faNum(Math.round(total / 1_000_000))} میلیون تومان در ${faNum(BUSINESS_SALES.length)} فاکتور ثبت شده است. بزرگ‌ترین مشتری: «${rows[0]?.مشتری ?? '—'}».`,
      summary: 'فروش به تفکیک مشتری',
      grounded: true,
      columns: ['مشتری', 'مبلغ (میلیون تومان)'],
      rows,
      chart: {
        type: 'bar',
        labels: rows.slice(0, 5).map((r) => String(r.مشتری)),
        values: rows.slice(0, 5).map((r) => Number(r['مبلغ (میلیون تومان)'])),
        unit: 'میلیون تومان',
      },
    };
  }

  // پیش‌فرض و «پرمصرف/خروج/مصرف»: مصرف دوره به تفکیک کالا.
  const month = '1405/06';
  const outByItem = new Map<string, number>();
  for (const m of movements) {
    const inScope = dataset ? true : m.date.startsWith(month);
    if (m.flow === 'خروج' && inScope) {
      outByItem.set(m.item, (outByItem.get(m.item) ?? 0) + m.qty);
    }
  }
  const ranked = [...outByItem.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  const rows = ranked.map(([name, qty]) => ({ کالا: name, 'مصرف شهریور': qty }));
  const kpis = businessKpis();
  return {
    id: 'consumption',
    question: q,
    answer: `در شهریور ۱۴۰۵ مجموعاً ${faNum(kpis.monthOutMovements)} حواله خروج صادر شده و پرمصرف‌ترین کالا «${ranked[0]?.[0] ?? '—'}» با ${faNum(ranked[0]?.[1] ?? 0)} واحد بوده است. نرخ حضور نیروها ${faNum(kpis.attendanceRatePct)}٪ گزارش شده.`,
    summary: 'خلاصه مدیریتی دوره',
    grounded: true,
    columns: ['کالا', 'مصرف شهریور'],
    rows,
    chart: {
      type: 'bar',
      labels: ranked.slice(0, 6).map(([name]) => name),
      values: ranked.slice(0, 6).map(([, qty]) => qty),
      unit: 'مقدار',
    },
  };
}
