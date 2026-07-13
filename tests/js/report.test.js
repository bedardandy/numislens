import test from 'node:test';
import assert from 'node:assert/strict';

import { formatCents } from '../../public/js/money.js';
import {
  basisLabel,
  metalName,
  formatYearMint,
  formatGainLoss,
  highlightSecondary,
  filenameDate,
  setRowCells,
  mintRowCells,
  seriesRowCells,
  metalRowCells,
  rollRowCells,
  rollTotalsLine,
} from '../../public/js/views/report.js';
import {
  formatCompletion,
  keyDateMarker,
  missingSlotLabel,
} from '../../public/js/views/sets.js';

const EM_DASH = '—';

test('formatCents formats integer cents as USD', () => {
  assert.equal(formatCents(0), '$0.00');
  assert.equal(formatCents(7), '$0.07');
  assert.equal(formatCents(4500), '$45.00');
  assert.equal(formatCents(123456), '$1,234.56');
  assert.equal(formatCents(1000000000), '$10,000,000.00');
});

test('formatCents handles negatives and nullish', () => {
  assert.equal(formatCents(-700), '-$7.00');
  assert.equal(formatCents(null), EM_DASH);
  assert.equal(formatCents(undefined), EM_DASH);
  assert.equal(formatCents(NaN), EM_DASH);
});

test('basisLabel maps known codes and passes through unknown', () => {
  assert.equal(basisLabel('collectible'), 'Collectible');
  assert.equal(basisLabel('melt'), 'Melt');
  assert.equal(basisLabel('face'), 'Face');
  assert.equal(basisLabel('best'), 'Best');
  assert.equal(basisLabel('weird'), 'weird');
  assert.equal(basisLabel(null), EM_DASH);
  assert.equal(basisLabel(''), EM_DASH);
});

test('metalName maps metal codes', () => {
  assert.equal(metalName('XAG'), 'Silver');
  assert.equal(metalName('XAU'), 'Gold');
  assert.equal(metalName('XPT'), 'Platinum');
  assert.equal(metalName('XYZ'), 'XYZ');
  assert.equal(metalName(null), EM_DASH);
});

test('formatYearMint combines year and mintmark', () => {
  assert.equal(formatYearMint(1921, 'D'), '1921D');
  assert.equal(formatYearMint(1921, null), '1921' + EM_DASH);
  assert.equal(formatYearMint(null, 'S'), EM_DASH + 'S');
  assert.equal(formatYearMint(null, null), EM_DASH);
  assert.equal(formatYearMint('', ''), EM_DASH);
});

test('formatGainLoss signs and tones', () => {
  assert.deepEqual(formatGainLoss(1000), { display: '+$10.00', tone: 'gain' });
  assert.deepEqual(formatGainLoss(-2500), { display: '−$25.00', tone: 'loss' });
  assert.deepEqual(formatGainLoss(0), { display: '$0.00', tone: 'flat' });
  assert.deepEqual(formatGainLoss(null), { display: EM_DASH, tone: null });
  assert.deepEqual(formatGainLoss(NaN), { display: EM_DASH, tone: null });
});

test('highlightSecondary only when both melt and collectible exist', () => {
  assert.equal(
    highlightSecondary({ melt_cents: 500, collectible_cents: 3000 }),
    'Melt $5.00 · Collectible $30.00'
  );
  assert.equal(highlightSecondary({ melt_cents: 500, collectible_cents: null }), null);
  assert.equal(highlightSecondary({ melt_cents: null, collectible_cents: 3000 }), null);
  assert.equal(highlightSecondary({}), null);
  assert.equal(highlightSecondary(null), null);
});

test('filenameDate extracts YYYY-MM-DD from ISO', () => {
  assert.equal(filenameDate('2026-07-12T15:04:05Z'), '2026-07-12');
  assert.equal(filenameDate('2026-07-12'), '2026-07-12');
  assert.match(filenameDate(null), /^\d{4}-\d{2}-\d{2}$/);
  assert.match(filenameDate('not-a-date'), /^\d{4}-\d{2}-\d{2}$/);
});

test('setRowCells shapes a set group row', () => {
  assert.deepEqual(
    setRowCells({ name: 'Mercury Dimes', filled: 12, total_slots: 77, owned_count: 15, value_cents: 250000 }),
    ['Mercury Dimes', '12/77', '15', '$2,500.00']
  );
  assert.deepEqual(
    setRowCells({ name: null, filled: 0, total_slots: 50, owned_count: 0, value_cents: 0 }),
    [EM_DASH, '0/50', '0', '$0.00']
  );
});

test('mintRowCells shapes a mint group row', () => {
  assert.deepEqual(
    mintRowCells({ mintmark: 'D', count: 40, valued_count: 30, value_cents: 999 }),
    ['D', '40', '30', '$9.99']
  );
});

test('seriesRowCells shapes a series group row', () => {
  assert.deepEqual(
    seriesRowCells({ series: 'Morgan Dollar', count: 5, valued_count: 5, value_cents: 100000 }),
    ['Morgan Dollar', '5', '5', '$1,000.00']
  );
});

test('metalRowCells shapes a metal group row', () => {
  assert.deepEqual(
    metalRowCells({ metal: 'XAG', count: 20, melt_cents: 45000, value_cents: 60000 }),
    ['Silver', '20', '$450.00', '$600.00']
  );
});

test('rollRowCells shapes a roll group row', () => {
  assert.deepEqual(
    rollRowCells({
      roll_no: 'NR-000001',
      denomination: 'cent',
      count: 50,
      status: 'unopened',
      basis: 'melt',
      value_cents: 12345,
    }),
    ['NR-000001', 'cent', '50', 'unopened', 'Melt', '$123.45']
  );
});

test('rollTotalsLine summarizes face/melt/best roll totals', () => {
  assert.equal(
    rollTotalsLine({
      roll_face_total_cents: 5000,
      roll_melt_total_cents: 12000,
      roll_best_total_cents: 12000,
    }),
    'Face $50.00 · Melt $120.00 · Best $120.00'
  );
});

test('formatCompletion shapes filled/total (pct%) computing pct when omitted', () => {
  assert.equal(formatCompletion(12, 77), '12/77 (15.6%)');
  assert.equal(formatCompletion(0, 50), '0/50 (0%)');
  assert.equal(formatCompletion(50, 50), '50/50 (100%)');
  assert.equal(formatCompletion(0, 0), '0/0 (0%)');
  assert.equal(formatCompletion(null, null), '0/0 (0%)');
});

test('formatCompletion uses a supplied pct verbatim (matches /needs completion_pct)', () => {
  assert.equal(formatCompletion(12, 77, 15.6), '12/77 (15.6%)');
});

test('keyDateMarker stars only key-date missing slots', () => {
  assert.equal(keyDateMarker({ key_date: true }), '★');
  assert.equal(keyDateMarker({ key_date: false }), '');
  assert.equal(keyDateMarker(null), '');
});

test('missingSlotLabel formats year-mint with an optional note', () => {
  assert.equal(missingSlotLabel({ year: 1932, mint: 'D', note: '' }), '1932-D');
  assert.equal(missingSlotLabel({ year: 1932, mint: 'D', note: 'doubled die' }), '1932-D doubled die');
  assert.equal(missingSlotLabel(null), '—');
});
