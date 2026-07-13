import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CANONICAL_DENOMINATIONS,
  STANDARD_ROLL_COUNTS,
  standardRollCount,
  basisLabel,
  statusLabel,
  nonstandardNote,
  rollTitle,
  parseQuickLines,
} from '../../public/js/views/rolls.js';

const EM_DASH = '—';

test('CANONICAL_DENOMINATIONS lists the six standard denominations', () => {
  assert.deepEqual(CANONICAL_DENOMINATIONS, [
    'cent',
    'nickel',
    'dime',
    'quarter',
    'half dollar',
    'dollar',
  ]);
});

test('standardRollCount looks up known denominations case-insensitively', () => {
  assert.equal(standardRollCount('cent'), 50);
  assert.equal(standardRollCount('Nickel'), 40);
  assert.equal(standardRollCount('DIME'), 50);
  assert.equal(standardRollCount('quarter'), 40);
  assert.equal(standardRollCount('half dollar'), 20);
  assert.equal(standardRollCount(' dollar '), 25);
});

test('standardRollCount returns null for exotic/unknown denominations', () => {
  assert.equal(standardRollCount('large cent'), null);
  assert.equal(standardRollCount(''), null);
  assert.equal(standardRollCount(null), null);
  assert.equal(standardRollCount(undefined), null);
});

test('STANDARD_ROLL_COUNTS matches the daemon core module map', () => {
  assert.deepEqual(STANDARD_ROLL_COUNTS, {
    cent: 50,
    nickel: 40,
    dime: 50,
    quarter: 40,
    'half dollar': 20,
    dollar: 25,
  });
});

test('basisLabel maps roll valuation basis', () => {
  assert.equal(basisLabel('melt'), 'Melt');
  assert.equal(basisLabel('face'), 'Face');
  assert.equal(basisLabel(null), EM_DASH);
  assert.equal(basisLabel(undefined), EM_DASH);
});

test('statusLabel title-cases roll status', () => {
  assert.equal(statusLabel('unopened'), 'Unopened');
  assert.equal(statusLabel('searching'), 'Searching');
  assert.equal(statusLabel('searched'), 'Searched');
  assert.equal(statusLabel('exhausted'), 'Exhausted');
  assert.equal(statusLabel(null), EM_DASH);
  assert.equal(statusLabel(''), EM_DASH);
});

test('nonstandardNote only warns when nonstandard is true', () => {
  assert.equal(nonstandardNote(true), '⚠ nonstandard count');
  assert.equal(nonstandardNote(false), '');
  assert.equal(nonstandardNote(undefined), '');
});

test('rollTitle shapes denomination x count', () => {
  assert.equal(rollTitle({ denomination: 'cent', count: 50 }), 'cent × 50');
  assert.equal(rollTitle({ denomination: null, count: null }), `${EM_DASH} × ${EM_DASH}`);
  assert.equal(rollTitle({}), `${EM_DASH} × ${EM_DASH}`);
  assert.equal(rollTitle(null), `${EM_DASH} × ${EM_DASH}`);
});

test('parseQuickLines splits, trims, and drops empty lines', () => {
  assert.deepEqual(
    parseQuickLines('1943 steel cent\n  1955 D Lincoln cent  \n\n1921 Morgan dollar'),
    ['1943 steel cent', '1955 D Lincoln cent', '1921 Morgan dollar'],
  );
  assert.deepEqual(parseQuickLines(''), []);
  assert.deepEqual(parseQuickLines('   \n  \n'), []);
  assert.deepEqual(parseQuickLines(null), []);
  assert.deepEqual(parseQuickLines(undefined), []);
});
