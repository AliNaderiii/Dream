import { describe, expect, it } from 'vitest';

import {
  BUSINESS_ATTENDANCE,
  BUSINESS_CATALOG,
  BUSINESS_MOVEMENTS,
  BUSINESS_SALES,
  BUSINESS_SUGGESTED_QUESTIONS,
  businessAsk,
  businessKpis,
  businessStockBalance,
} from './business-data';

const JALALI_DATE = /^1405\/0[56]\/(0[1-9]|[12][0-9]|3[01])$/;

describe('business pilot dataset', () => {
  it('is deterministic across calls', () => {
    // The dataset is a module constant; rebuild the derived state twice and
    // compare to prove the seeded generator is stable.
    const first = [...businessStockBalance().entries()].map(([k, v]) => `${k}:${v.qty}`);
    const second = [...businessStockBalance().entries()].map(([k, v]) => `${k}:${v.qty}`);
    expect(first).toEqual(second);
    expect(first.length).toBe(BUSINESS_CATALOG.length);
  });

  it('keeps every movement tied to the catalog with a valid Jalali date', () => {
    const names = new Set(BUSINESS_CATALOG.map((c) => c.name));
    expect(BUSINESS_MOVEMENTS.length).toBeGreaterThan(80);
    for (const m of BUSINESS_MOVEMENTS) {
      expect(names.has(m.item)).toBe(true);
      expect(m.qty).toBeGreaterThan(0);
      expect(m.date).toMatch(JALALI_DATE);
      expect(['ورود', 'خروج']).toContain(m.flow);
    }
  });

  it('derives stock balance as inflow minus outflow', () => {
    const balances = businessStockBalance();
    for (const item of BUSINESS_CATALOG) {
      const inQty = BUSINESS_MOVEMENTS.filter(
        (m) => m.item === item.name && m.flow === 'ورود',
      ).reduce((s, m) => s + m.qty, 0);
      const outQty = BUSINESS_MOVEMENTS.filter(
        (m) => m.item === item.name && m.flow === 'خروج',
      ).reduce((s, m) => s + m.qty, 0);
      expect(balances.get(item.name)?.qty).toBe(inQty - outQty);
    }
  });

  it('computes executive KPIs from the dataset', () => {
    const kpis = businessKpis('1405/06/26');
    expect(kpis.activeItems).toBeGreaterThan(0);
    expect(kpis.totalStockValueToman).toBeGreaterThan(0);
    expect(kpis.monthOutMovements).toBe(
      BUSINESS_MOVEMENTS.filter((m) => m.flow === 'خروج' && m.date.startsWith('1405/06')).length,
    );
    const todayRows = BUSINESS_ATTENDANCE.filter((a) => a.date === '1405/06/26');
    const present = todayRows.filter((a) => a.present).length;
    expect(kpis.attendanceRatePct).toBe(Math.round((present / todayRows.length) * 100));
    expect(kpis.salesTotalToman).toBe(
      BUSINESS_SALES.reduce((s, s2) => s + s2.qty * s2.unitPriceToman, 0),
    );
  });
});

describe('businessAsk local analytics engine', () => {
  it('answers every suggested question with a grounded insight', () => {
    for (const question of BUSINESS_SUGGESTED_QUESTIONS) {
      const insight = businessAsk(question);
      expect(insight.grounded).toBe(true);
      expect(insight.answer.length).toBeGreaterThan(10);
      expect(insight.columns.length).toBeGreaterThan(0);
      expect(insight.rows.length).toBeGreaterThan(0);
      if (insight.chart) {
        expect(insight.chart.labels.length).toBe(insight.chart.values.length);
      }
    }
  });

  it('routes stock, value, attendance, dead-stock and sales questions', () => {
    expect(businessAsk('موجودی انبار چقدر است؟').id).toBe('stock');
    expect(businessAsk('ارزش ریالی موجودی؟').id).toBe('value');
    expect(businessAsk('حضور و غیاب امروز؟').id).toBe('attendance');
    expect(businessAsk('کالاهای راکد کدام‌اند؟').id).toBe('dead');
    expect(businessAsk('فروش این دوره؟').id).toBe('sales');
    // پرسش نامرتبط → خلاصه مدیریتی دوره (default).
    expect(businessAsk('یه گزارش کلی بده').id).toBe('consumption');
  });

  it('keeps evidence rows consistent with the announced columns', () => {
    const insight = businessAsk('موجودی فعلی انبار به تفکیک کالا چقدر است؟');
    for (const row of insight.rows) {
      for (const column of insight.columns) {
        expect(row[column]).toBeDefined();
      }
    }
  });
});
