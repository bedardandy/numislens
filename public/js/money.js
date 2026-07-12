/**
 * Parses UI dollar input into cents (integer). Not for business logic.
 * @param {string|number} input
 * @returns {number|null}
 */
export function dollarsToCents(input) {
  const trimmed = String(input).trim();
  if (trimmed === '') {
    return null;
  }

  let amount = trimmed;
  if (amount.startsWith('$')) {
    amount = amount.slice(1);
  }
  amount = amount.replace(/,/g, '');

  const match = amount.match(/^(\d*)(?:\.(\d{1,2}))?$/);
  if (!match || (match[1] === '' && !match[2])) {
    throw new Error('Invalid dollar amount: ' + input);
  }

  const dollarsPart = match[1] === '' ? '0' : match[1];
  const centsPart = (match[2] ?? '').padEnd(2, '0');

  return Number.parseInt(dollarsPart, 10) * 100 + Number.parseInt(centsPart, 10);
}

const EM_DASH = '—';

function groupThousands(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Formats an integer cent amount as a US dollar display string, e.g.
 * 123456 -> "$1,234.56", -700 -> "-$7.00". Returns an em dash for nullish
 * input. Locale-independent (manual grouping) so it is deterministic.
 * @param {number|null|undefined} cents
 * @returns {string}
 */
export function formatCents(cents) {
  if (cents == null || Number.isNaN(cents)) return EM_DASH;
  const neg = cents < 0;
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100);
  const rem = abs % 100;
  return (neg ? '-$' : '$') + groupThousands(String(dollars)) + '.' + String(rem).padStart(2, '0');
}
