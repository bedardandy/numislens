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
