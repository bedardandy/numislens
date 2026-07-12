import assert from 'node:assert/strict';
import { dollarsToCents } from '../../public/js/money.js';

assert.equal(dollarsToCents('45'), 4500);
assert.equal(dollarsToCents('45.5'), 4550);
assert.equal(dollarsToCents('45.05'), 4505);
assert.equal(dollarsToCents('0.07'), 7);
assert.equal(dollarsToCents('1,234.56'), 123456);
assert.equal(dollarsToCents('$45'), 4500);
assert.equal(dollarsToCents(''), null);
assert.equal(dollarsToCents('   '), null);

assert.throws(() => dollarsToCents('45.123'));
assert.throws(() => dollarsToCents('abc'));

console.log('money.test OK');
