import {
  listRolls,
  getRoll,
  createRoll,
  updateRoll,
  pullRoll,
  getRollLabelsPdf,
  listCompositions,
} from '../api.js';
import { dollarsToCents, formatCents } from '../money.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';

const EM_DASH = '—';

// ---------------------------------------------------------------------------
// Pure helpers (exported for testing). These operate on plain data only.
// ---------------------------------------------------------------------------

/** The six canonical roll denominations the add-roll form offers as a select. */
export const CANONICAL_DENOMINATIONS = [
  'cent',
  'nickel',
  'dime',
  'quarter',
  'half dollar',
  'dollar',
];

/** Standard mint/bank roll coin counts, keyed by canonical denomination. */
export const STANDARD_ROLL_COUNTS = {
  cent: 50,
  nickel: 40,
  dime: 50,
  quarter: 40,
  'half dollar': 20,
  dollar: 25,
};

/**
 * The standard roll count for a denomination string, or null when the
 * denomination is not one of the six canonical ones (free-text/exotic).
 */
export function standardRollCount(denomination) {
  if (denomination == null) return null;
  const key = String(denomination).trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(STANDARD_ROLL_COUNTS, key)
    ? STANDARD_ROLL_COUNTS[key]
    : null;
}

/** Human label for a roll's valuation basis ('melt'|'face'|null). */
export function basisLabel(basis) {
  if (basis === 'melt') return 'Melt';
  if (basis === 'face') return 'Face';
  return EM_DASH;
}

/** Title-cases a roll status ('unopened' -> 'Unopened'). */
export function statusLabel(status) {
  if (status == null || status === '') return EM_DASH;
  const s = String(status);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Short warning text for a roll whose count differs from the denomination's standard. */
export function nonstandardNote(nonstandard) {
  return nonstandard ? '⚠ nonstandard count' : '';
}

/** "Denomination × count" display line, e.g. "cent × 50". */
export function rollTitle(roll) {
  const denom = roll && roll.denomination != null ? String(roll.denomination) : EM_DASH;
  const count = roll && roll.count != null ? roll.count : EM_DASH;
  return `${denom} × ${count}`;
}

/**
 * Splits a quick-add textarea into one trimmed, non-empty string per line —
 * the shape the roll pull endpoint's ``quick`` array expects.
 */
export function parseQuickLines(text) {
  if (typeof text !== 'string') return [];
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

// ---------------------------------------------------------------------------
// DOM building
// ---------------------------------------------------------------------------

function display(value) {
  if (value == null || value === '') return EM_DASH;
  return String(value);
}

function appendField(form, labelText, control) {
  const label = document.createElement('label');
  label.textContent = labelText;
  form.appendChild(label);
  form.appendChild(control);
}

function buildAddRollForm(el, compositions, onCreated) {
  const heading = document.createElement('h3');
  heading.textContent = 'Add roll';
  el.appendChild(heading);

  const form = document.createElement('form');
  form.className = 'settings-form';
  form.addEventListener('submit', (e) => e.preventDefault());

  const denomSelect = document.createElement('select');
  denomSelect.name = 'denomination';
  for (const denom of CANONICAL_DENOMINATIONS) {
    const opt = document.createElement('option');
    opt.value = denom;
    opt.textContent = denom;
    denomSelect.appendChild(opt);
  }
  const otherOpt = document.createElement('option');
  otherOpt.value = '__other__';
  otherOpt.textContent = 'Other…';
  denomSelect.appendChild(otherOpt);
  appendField(form, 'Denomination', denomSelect);

  const denomFreeTextLabel = document.createElement('label');
  denomFreeTextLabel.textContent = 'Denomination (free text)';
  denomFreeTextLabel.style.display = 'none';
  form.appendChild(denomFreeTextLabel);
  const denomFreeText = document.createElement('input');
  denomFreeText.type = 'text';
  denomFreeText.name = 'denomination_other';
  denomFreeText.placeholder = 'e.g. large cent';
  denomFreeText.style.display = 'none';
  form.appendChild(denomFreeText);

  const countInput = document.createElement('input');
  countInput.type = 'number';
  countInput.name = 'count';
  countInput.min = '1';
  appendField(form, 'Count', countInput);

  function applyDenomChange() {
    const isOther = denomSelect.value === '__other__';
    denomFreeTextLabel.style.display = isOther ? '' : 'none';
    denomFreeText.style.display = isOther ? '' : 'none';
    const std = standardRollCount(denomSelect.value);
    if (!isOther && std != null) countInput.value = String(std);
  }
  denomSelect.addEventListener('change', applyDenomChange);
  applyDenomChange();

  const seriesInput = document.createElement('input');
  seriesInput.type = 'text';
  seriesInput.name = 'series';
  appendField(form, 'Series', seriesInput);

  const yearInput = document.createElement('input');
  yearInput.type = 'number';
  yearInput.name = 'year';
  appendField(form, 'Year', yearInput);

  const compositionSelect = document.createElement('select');
  compositionSelect.name = 'composition_name';
  const compBlank = document.createElement('option');
  compBlank.value = '';
  compBlank.textContent = '— None —';
  compositionSelect.appendChild(compBlank);
  for (const comp of compositions) {
    const opt = document.createElement('option');
    opt.value = comp.name;
    opt.textContent = `${comp.name} (${comp.metal || 'base metal'})`;
    compositionSelect.appendChild(opt);
  }
  appendField(form, 'Composition', compositionSelect);

  const variantInput = document.createElement('input');
  variantInput.type = 'text';
  variantInput.name = 'variant';
  appendField(form, 'Variant', variantInput);

  const costInput = document.createElement('input');
  costInput.type = 'text';
  costInput.name = 'cost_basis';
  costInput.inputMode = 'decimal';
  costInput.placeholder = '0.00';
  appendField(form, 'Cost basis ($)', costInput);

  const acquiredDateInput = document.createElement('input');
  acquiredDateInput.type = 'date';
  acquiredDateInput.name = 'acquired_date';
  appendField(form, 'Acquired date', acquiredDateInput);

  const acquiredSourceInput = document.createElement('input');
  acquiredSourceInput.type = 'text';
  acquiredSourceInput.name = 'acquired_source';
  appendField(form, 'Acquired source', acquiredSourceInput);

  const notesInput = document.createElement('textarea');
  notesInput.name = 'notes';
  notesInput.rows = 2;
  appendField(form, 'Notes', notesInput);

  const actions = document.createElement('div');
  actions.className = 'settings-actions';

  const createBtn = document.createElement('button');
  createBtn.type = 'button';
  createBtn.textContent = 'Create roll';
  createBtn.addEventListener('click', async () => {
    const denomination =
      denomSelect.value === '__other__' ? denomFreeText.value.trim() : denomSelect.value;
    if (!denomination) {
      toast('Denomination is required', 'error');
      return;
    }
    const countVal = parseInt(countInput.value, 10);
    if (Number.isNaN(countVal) || countVal < 1) {
      toast('Count must be a whole number ≥ 1', 'error');
      return;
    }

    const body = { denomination, count: countVal };

    const series = seriesInput.value.trim();
    if (series) body.series = series;

    if (yearInput.value) {
      const y = parseInt(yearInput.value, 10);
      if (!Number.isNaN(y)) body.year = y;
    }

    if (compositionSelect.value) body.composition_name = compositionSelect.value;

    const variant = variantInput.value.trim();
    if (variant) body.variant = variant;

    try {
      const cents = dollarsToCents(costInput.value);
      if (cents != null) body.cost_basis_cents = cents;
    } catch {
      toast('Invalid cost basis — enter a dollar amount like 25.00', 'error');
      return;
    }

    if (acquiredDateInput.value) body.acquired_date = acquiredDateInput.value;

    const acquiredSource = acquiredSourceInput.value.trim();
    if (acquiredSource) body.acquired_source = acquiredSource;

    const notes = notesInput.value.trim();
    if (notes) body.notes = notes;

    createBtn.disabled = true;
    try {
      const roll = await createRoll(body);
      toast(`${roll.roll_no} created`, 'success');
      if (typeof onCreated === 'function') await onCreated();
      form.reset();
      applyDenomChange();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      createBtn.disabled = false;
    }
  });
  actions.appendChild(createBtn);
  form.appendChild(actions);

  el.appendChild(form);
}

function buildRollRow(roll, selectedSet) {
  const tr = document.createElement('tr');

  const tdSelect = document.createElement('td');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.setAttribute('aria-label', `Select ${roll.roll_no}`);
  checkbox.addEventListener('change', () => {
    if (checkbox.checked) selectedSet.add(roll.roll_no);
    else selectedSet.delete(roll.roll_no);
  });
  tdSelect.appendChild(checkbox);
  tr.appendChild(tdSelect);

  const tdRoll = document.createElement('td');
  const link = document.createElement('a');
  link.href = `#/roll/${encodeURIComponent(roll.roll_no)}`;
  link.textContent = display(roll.roll_no);
  tdRoll.appendChild(link);
  tr.appendChild(tdRoll);

  const tdTitle = document.createElement('td');
  tdTitle.textContent = rollTitle(roll);
  tr.appendChild(tdTitle);

  const tdVariant = document.createElement('td');
  tdVariant.textContent = display(roll.variant);
  tr.appendChild(tdVariant);

  const tdStatus = document.createElement('td');
  const chip = document.createElement('span');
  chip.className = 'status-chip status-chip--' + (roll.status || 'unknown');
  chip.textContent = statusLabel(roll.status);
  tdStatus.appendChild(chip);
  tr.appendChild(tdStatus);

  const tdValue = document.createElement('td');
  tdValue.appendChild(document.createTextNode(formatCents(roll.best_cents)));
  if (roll.best_cents != null) {
    const badge = document.createElement('span');
    badge.className = 'report-basis-badge';
    badge.style.marginLeft = 'var(--space-xs)';
    badge.textContent = basisLabel(roll.basis);
    tdValue.appendChild(badge);
  }
  if (roll.nonstandard) {
    const note = document.createElement('div');
    note.className = 'muted';
    note.style.fontSize = 'var(--font-size-sm)';
    note.textContent = nonstandardNote(roll.nonstandard);
    tdValue.appendChild(note);
  }
  tr.appendChild(tdValue);

  return tr;
}

export async function renderRolls(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Rolls';
  el.appendChild(heading);

  const intro = document.createElement('p');
  intro.className = 'muted';
  intro.textContent =
    'Bulk mint/bank rolls held as one unit until pulled apart. Valued only when a face or melt basis is known.';
  el.appendChild(intro);

  let compositions = [];
  try {
    const data = await listCompositions();
    compositions = Array.isArray(data) ? data : [];
  } catch {
    /* composition select just stays empty */
  }

  const listSection = document.createElement('div');
  el.appendChild(listSection);

  buildAddRollForm(el, compositions, () => loadRolls());

  async function loadRolls() {
    listSection.replaceChildren();

    const actionBar = document.createElement('div');
    actionBar.className = 'melt-update-bar';
    const printBtn = document.createElement('button');
    printBtn.type = 'button';
    printBtn.textContent = 'Print labels';
    actionBar.appendChild(printBtn);
    listSection.appendChild(actionBar);

    let rolls;
    try {
      rolls = await listRolls();
    } catch (err) {
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      listSection.appendChild(errDiv);
      toast(err.message, 'error');
      return;
    }

    const selectedSet = new Set();

    printBtn.addEventListener('click', async () => {
      printBtn.disabled = true;
      try {
        const blob = await getRollLabelsPdf(selectedSet.size ? [...selectedSet] : undefined);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'numislens-roll-labels.pdf';
        a.click();
        URL.revokeObjectURL(url);
        toast('Roll labels downloaded', 'success');
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        printBtn.disabled = false;
      }
    });

    if (!rolls.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'No rolls yet.';
      listSection.appendChild(empty);
      return;
    }

    const wrap = document.createElement('div');
    wrap.className = 'table-wrap';
    const table = document.createElement('table');
    table.className = 'coin-table';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const label of ['', 'Roll', 'Denom × Count', 'Variant', 'Status', 'Value']) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = label;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (const roll of rolls) {
      tbody.appendChild(buildRollRow(roll, selectedSet));
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    listSection.appendChild(wrap);
  }

  await loadRolls();
}

export async function renderRollDetail(el, rollNo) {
  el.replaceChildren();

  const back = document.createElement('a');
  back.href = '#/rolls';
  back.textContent = 'Back to rolls';
  back.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/rolls');
  });
  el.appendChild(back);

  const loading = document.createElement('p');
  loading.textContent = 'Loading…';
  el.appendChild(loading);

  let roll;
  try {
    roll = await getRoll(rollNo);
  } catch (err) {
    el.replaceChildren();
    el.appendChild(back);
    const errDiv = document.createElement('div');
    errDiv.className = 'empty-state';
    errDiv.textContent = err.message;
    el.appendChild(errDiv);
    toast(err.message, 'error');
    return;
  }

  el.replaceChildren();
  el.appendChild(back);

  const title = document.createElement('h2');
  title.textContent = display(roll.roll_no);
  el.appendChild(title);

  const subtitle = document.createElement('p');
  subtitle.className = 'muted';
  subtitle.textContent = rollTitle(roll);
  el.appendChild(subtitle);

  const dl = document.createElement('dl');
  dl.className = 'coin-detail';

  function addRow(label, value) {
    const row = document.createElement('div');
    row.className = 'detail-row';
    const dt = document.createElement('dt');
    dt.textContent = label;
    row.appendChild(dt);
    const dd = document.createElement('dd');
    dd.textContent = display(value);
    row.appendChild(dd);
    dl.appendChild(row);
  }

  addRow('Denomination', roll.denomination);
  addRow('Country', roll.country);
  addRow('Count remaining', roll.count);
  addRow('Series', roll.series);
  addRow('Year', roll.year);
  addRow('Composition', roll.composition_name);
  addRow('Variant', roll.variant);
  addRow('Status', statusLabel(roll.status));
  addRow('Face value', formatCents(roll.face_cents));
  addRow('Melt value', formatCents(roll.melt_cents));
  addRow('Best value', formatCents(roll.best_cents));
  addRow('Basis', basisLabel(roll.basis));
  if (roll.nonstandard) addRow('Nonstandard', nonstandardNote(roll.nonstandard));
  addRow('Cost basis', roll.cost_basis_cents != null ? formatCents(roll.cost_basis_cents) : null);
  addRow('Acquired date', roll.acquired_date);
  addRow('Acquired source', roll.acquired_source);
  addRow('Location', roll.location_id);
  addRow('Notes', roll.notes);
  addRow('Created at', roll.created_at);

  el.appendChild(dl);

  // --- Status editor -------------------------------------------------------
  const statusHeading = document.createElement('h3');
  statusHeading.textContent = 'Update status';
  el.appendChild(statusHeading);

  const statusForm = document.createElement('div');
  statusForm.className = 'settings-actions';

  const statusSelect = document.createElement('select');
  for (const s of ['unopened', 'searching', 'searched', 'exhausted']) {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = statusLabel(s);
    if (s === roll.status) opt.selected = true;
    statusSelect.appendChild(opt);
  }
  statusForm.appendChild(statusSelect);

  const statusBtn = document.createElement('button');
  statusBtn.type = 'button';
  statusBtn.textContent = 'Save status';
  statusBtn.addEventListener('click', async () => {
    statusBtn.disabled = true;
    try {
      await updateRoll(rollNo, { status: statusSelect.value });
      toast('Status updated', 'success');
      await renderRollDetail(el, rollNo);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      statusBtn.disabled = false;
    }
  });
  statusForm.appendChild(statusBtn);
  el.appendChild(statusForm);

  // --- Pull coins ------------------------------------------------------------
  const pullHeading = document.createElement('h3');
  pullHeading.textContent = 'Pull coins from roll';
  el.appendChild(pullHeading);

  if (roll.status === 'exhausted' || roll.count === 0) {
    const exhaustedP = document.createElement('p');
    exhaustedP.className = 'muted';
    exhaustedP.textContent = 'This roll is exhausted — nothing left to pull.';
    el.appendChild(exhaustedP);
  } else {
    const pullForm = document.createElement('form');
    pullForm.className = 'settings-form';
    pullForm.addEventListener('submit', (e) => e.preventDefault());

    const pullCountInput = document.createElement('input');
    pullCountInput.type = 'number';
    pullCountInput.min = '1';
    pullCountInput.max = String(roll.count);
    appendField(pullForm, `Count to pull (max ${roll.count})`, pullCountInput);

    const quickTextarea = document.createElement('textarea');
    quickTextarea.rows = 4;
    quickTextarea.placeholder = 'One quick-add line per coin, e.g.\n1943 steel cent\n1955 D Lincoln cent';
    appendField(pullForm, 'Quick-add captures (optional, one per line)', quickTextarea);

    const pullActions = document.createElement('div');
    pullActions.className = 'settings-actions';
    const pullBtn = document.createElement('button');
    pullBtn.type = 'button';
    pullBtn.textContent = 'Pull';
    pullActions.appendChild(pullBtn);
    pullForm.appendChild(pullActions);

    const resultDiv = document.createElement('div');
    pullForm.appendChild(resultDiv);

    pullBtn.addEventListener('click', async () => {
      const count = parseInt(pullCountInput.value, 10);
      if (Number.isNaN(count) || count < 1) {
        toast('Pull count must be a whole number ≥ 1', 'error');
        return;
      }
      const quick = parseQuickLines(quickTextarea.value);

      pullBtn.disabled = true;
      try {
        const response = await pullRoll(rollNo, count, quick.length ? quick : undefined);
        resultDiv.replaceChildren();
        if (response.coins_created && response.coins_created.length) {
          const p = document.createElement('p');
          p.textContent = 'Created: ';
          for (const acc of response.coins_created) {
            const a = document.createElement('a');
            a.href = `#/coin/${encodeURIComponent(acc)}`;
            a.textContent = acc;
            a.style.marginRight = 'var(--space-sm)';
            p.appendChild(a);
          }
          resultDiv.appendChild(p);
        }
        toast(`Pulled ${count} from ${rollNo}`, 'success');
        await renderRollDetail(el, rollNo);
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        pullBtn.disabled = false;
      }
    });

    el.appendChild(pullForm);
  }
}
