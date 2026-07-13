import test from 'node:test';
import assert from 'node:assert/strict';

import {
  slotChipClass,
  nextFillState,
  slotLabel,
  formatPercent,
  pageAnalysisLabel,
} from '../../public/js/views/albums.js';

const EM_DASH = '—';

test('slotChipClass maps fill_state to a chip class', () => {
  assert.equal(slotChipClass('filled'), 'slot-chip--filled');
  assert.equal(slotChipClass('empty'), 'slot-chip--gap');
  assert.equal(slotChipClass('uncertain'), 'slot-chip--uncertain');
  assert.equal(slotChipClass('weird'), 'slot-chip--gap');
  assert.equal(slotChipClass(null), 'slot-chip--gap');
});

test('nextFillState cycles filled -> empty -> uncertain -> filled', () => {
  assert.equal(nextFillState('filled'), 'empty');
  assert.equal(nextFillState('empty'), 'uncertain');
  assert.equal(nextFillState('uncertain'), 'filled');
  // Any other/unknown state also lands back on filled (never stuck).
  assert.equal(nextFillState('weird'), 'filled');
});

test('slotLabel formats year-mint, falling back to label_text or an em dash', () => {
  assert.equal(slotLabel({ year: 1914, mint: 'D' }), '1914-D');
  assert.equal(slotLabel({ year: 1914, mint: null }), '1914');
  assert.equal(slotLabel({ year: null, label_text: '1921 D' }), '1921 D');
  assert.equal(slotLabel({ year: null, label_text: '' }), EM_DASH);
  assert.equal(slotLabel(null), EM_DASH);
});

test('formatPercent rounds a 0..1 fraction to a whole-number percent', () => {
  assert.equal(formatPercent(0.8234), '82%');
  assert.equal(formatPercent(1), '100%');
  assert.equal(formatPercent(0), '0%');
  assert.equal(formatPercent(null), EM_DASH);
  assert.equal(formatPercent(undefined), EM_DASH);
  assert.equal(formatPercent(NaN), EM_DASH);
});

test('pageAnalysisLabel reports analyzed vs pending', () => {
  assert.equal(pageAnalysisLabel({ analyzed_at: '2026-07-13T00:00:00Z' }), 'Analyzed');
  assert.equal(pageAnalysisLabel({ analyzed_at: null }), 'Pending analysis');
  assert.equal(pageAnalysisLabel({}), 'Pending analysis');
});
