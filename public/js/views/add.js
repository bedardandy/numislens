import { listCompositions, createCoin, locationTree, fetchBlob } from '../api.js';
import { flattenLocationTree, populateLocationSelect } from '../tree.js';
import { dollarsToCents } from '../money.js';
import { renderPhotoCapture } from '../photo.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';

const GRADE_BUCKETS = ['AG', 'G', 'VG', 'F', 'VF', 'XF', 'AU', 'UNC', 'PROOF'];
const VALUE_BASES = ['melt', 'numismatic', 'hybrid'];

function appendField(form, labelText, control) {
  const label = document.createElement('label');
  label.textContent = labelText;
  form.appendChild(label);
  form.appendChild(control);
}

function renderSuccessStep(el, accession) {
  el.replaceChildren();

  const title = document.createElement('h2');
  title.style.cssText = 'font-size:var(--font-size-xl);';
  title.textContent = `${accession} created`;
  el.appendChild(title);

  const subheading = document.createElement('h3');
  subheading.textContent = 'Add photos';
  el.appendChild(subheading);

  const photoContainer = document.createElement('div');
  el.appendChild(photoContainer);
  renderPhotoCapture(photoContainer, accession, {});

  const actions = document.createElement('div');
  actions.className = 'detail-actions';

  const viewBtn = document.createElement('button');
  viewBtn.type = 'button';
  viewBtn.textContent = 'View coin';
  viewBtn.addEventListener('click', () => {
    navigate(`#/coin/${encodeURIComponent(accession)}`);
  });
  actions.appendChild(viewBtn);

  const printBtn = document.createElement('button');
  printBtn.type = 'button';
  printBtn.textContent = 'Print label';
  printBtn.addEventListener('click', async () => {
    printBtn.disabled = true;
    try {
      const blob = await fetchBlob(
        `/api/v1/labels.pdf?accessions=${encodeURIComponent(accession)}`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${accession}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Label downloaded', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      printBtn.disabled = false;
    }
  });
  actions.appendChild(printBtn);

  const anotherBtn = document.createElement('button');
  anotherBtn.type = 'button';
  anotherBtn.textContent = 'Add another';
  anotherBtn.addEventListener('click', () => renderAdd(el));
  actions.appendChild(anotherBtn);

  el.appendChild(actions);
}

export async function renderAdd(el) {
  el.replaceChildren();

  const pageHeading = document.createElement('h2');
  pageHeading.textContent = 'Add coin';
  el.appendChild(pageHeading);

  let compositions = [];
  try {
    const data = await listCompositions();
    compositions = Array.isArray(data) ? data : [];
  } catch (err) {
    const errDiv = document.createElement('div');
    errDiv.className = 'empty-state';
    errDiv.textContent = err.message;
    el.appendChild(errDiv);
    toast(err.message, 'error');
  }

  const form = document.createElement('form');
  form.className = 'settings-form';
  form.addEventListener('submit', (e) => e.preventDefault());

  const seriesInput = document.createElement('input');
  seriesInput.type = 'text';
  seriesInput.name = 'series';
  appendField(form, 'Series', seriesInput);

  const yearInput = document.createElement('input');
  yearInput.type = 'number';
  yearInput.name = 'year';
  appendField(form, 'Year', yearInput);

  const mintmarkInput = document.createElement('input');
  mintmarkInput.type = 'text';
  mintmarkInput.name = 'mintmark';
  appendField(form, 'Mintmark', mintmarkInput);

  const denominationInput = document.createElement('input');
  denominationInput.type = 'text';
  denominationInput.name = 'denomination';
  appendField(form, 'Denomination', denominationInput);

  const countryInput = document.createElement('input');
  countryInput.type = 'text';
  countryInput.name = 'country';
  countryInput.value = 'US';
  appendField(form, 'Country', countryInput);

  const compositionSelect = document.createElement('select');
  compositionSelect.name = 'composition_id';
  const compositionBlank = document.createElement('option');
  compositionBlank.value = '';
  compositionBlank.textContent = '\u2014 None \u2014';
  compositionSelect.appendChild(compositionBlank);
  for (const comp of compositions) {
    const opt = document.createElement('option');
    opt.value = String(comp.id);
    opt.textContent = `${comp.name} (${comp.metal || 'base metal'})`;
    compositionSelect.appendChild(opt);
  }
  appendField(form, 'Composition', compositionSelect);

  const gradeSelect = document.createElement('select');
  gradeSelect.name = 'grade_bucket';
  const gradeUnknown = document.createElement('option');
  gradeUnknown.value = '';
  gradeUnknown.textContent = 'Unknown';
  gradeUnknown.selected = true;
  gradeSelect.appendChild(gradeUnknown);
  for (const grade of GRADE_BUCKETS) {
    const opt = document.createElement('option');
    opt.value = grade;
    opt.textContent = grade;
    gradeSelect.appendChild(opt);
  }
  appendField(form, 'Grade', gradeSelect);

  const costBasisInput = document.createElement('input');
  costBasisInput.type = 'text';
  costBasisInput.name = 'cost_basis';
  costBasisInput.inputMode = 'decimal';
  costBasisInput.placeholder = '0.00';
  const costWrap = document.createElement('span');
  costWrap.style.cssText =
    'display:flex;align-items:center;gap:var(--space-xs);';
  const costPrefix = document.createElement('span');
  costPrefix.textContent = '$';
  costWrap.appendChild(costPrefix);
  costWrap.appendChild(costBasisInput);
  appendField(form, 'Cost basis', costWrap);

  const acquiredDateInput = document.createElement('input');
  acquiredDateInput.type = 'date';
  acquiredDateInput.name = 'acquired_date';
  appendField(form, 'Acquired date', acquiredDateInput);

  const acquiredSourceInput = document.createElement('input');
  acquiredSourceInput.type = 'text';
  acquiredSourceInput.name = 'acquired_source';
  appendField(form, 'Acquired source', acquiredSourceInput);

  const valueBasisLabel = document.createElement('label');
  valueBasisLabel.textContent = 'Value basis';
  form.appendChild(valueBasisLabel);

  const valueBasisRow = document.createElement('div');
  valueBasisRow.style.cssText =
    'display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-sm);';

  const valueBasisSelect = document.createElement('select');
  valueBasisSelect.name = 'value_basis';
  for (const basis of VALUE_BASES) {
    const opt = document.createElement('option');
    opt.value = basis;
    opt.textContent = basis;
    valueBasisSelect.appendChild(opt);
  }
  valueBasisRow.appendChild(valueBasisSelect);

  const valueBasisNote = document.createElement('span');
  valueBasisNote.style.cssText =
    'color:var(--color-text-muted);font-size:var(--font-size-sm);';
  valueBasisRow.appendChild(valueBasisNote);

  form.appendChild(valueBasisRow);

  const locationSelect = document.createElement('select');
  locationSelect.name = 'location_id';
  populateLocationSelect(locationSelect, new Map(), {
    blank: { value: '', label: 'No location' },
  });
  appendField(form, 'Location', locationSelect);

  const notesInput = document.createElement('textarea');
  notesInput.name = 'notes';
  notesInput.rows = 3;
  appendField(form, 'Notes', notesInput);

  function applyValueBasisDefault() {
    const selectedId = compositionSelect.value;
    let comp = null;
    if (selectedId !== '') {
      const id = parseInt(selectedId, 10);
      comp = compositions.find((c) => c.id === id) ?? null;
    }

    if (
      comp != null &&
      comp.precious_weight_ozt != null &&
      comp.precious_weight_ozt > 0
    ) {
      valueBasisSelect.value = 'melt';
      valueBasisNote.textContent = 'Auto: melt (composition has precious metal)';
    } else {
      valueBasisSelect.value = 'numismatic';
      valueBasisNote.textContent = 'Auto: numismatic (no precious metal)';
    }
  }

  compositionSelect.addEventListener('change', () => applyValueBasisDefault());
  applyValueBasisDefault();

  const actions = document.createElement('div');
  actions.className = 'settings-actions';

  const createBtn = document.createElement('button');
  createBtn.type = 'button';
  createBtn.textContent = 'Create coin';
  createBtn.addEventListener('click', async () => {
    if (!navigator.onLine) { toast('Adding a coin requires a connection', 'error'); return; }
    const body = {};

    const series = seriesInput.value.trim();
    if (series) body.series = series;

    const yearVal = yearInput.value;
    if (yearVal) {
      const y = parseInt(yearVal, 10);
      if (!Number.isNaN(y)) body.year = y;
    }

    const mintmark = mintmarkInput.value.trim();
    if (mintmark) body.mintmark = mintmark;

    const denomination = denominationInput.value.trim();
    if (denomination) body.denomination = denomination;

    const country = countryInput.value.trim();
    if (country) body.country = country;

    const compVal = compositionSelect.value;
    if (compVal !== '') {
      const cid = parseInt(compVal, 10);
      if (!Number.isNaN(cid)) body.composition_id = cid;
    }

    const gradeVal = gradeSelect.value;
    if (gradeVal !== '') {
      body.grade_bucket = gradeVal;
      body.grade_source = 'human';
    }

    if (acquiredDateInput.value) body.acquired_date = acquiredDateInput.value;

    const acquiredSource = acquiredSourceInput.value.trim();
    if (acquiredSource) body.acquired_source = acquiredSource;

    body.value_basis = valueBasisSelect.value;

    const locVal = locationSelect.value;
    if (locVal !== '') {
      const lid = parseInt(locVal, 10);
      if (!Number.isNaN(lid)) body.location_id = lid;
    }

    const notes = notesInput.value.trim();
    if (notes) body.notes = notes;

    try {
      const cents = dollarsToCents(costBasisInput.value);
      if (cents != null) body.cost_basis_cents = cents;
    } catch {
      toast('Invalid cost basis — enter a dollar amount like 45.00', 'error');
      return;
    }

    createBtn.disabled = true;
    try {
      const response = await createCoin(body);
      if (response?.accession_no) {
        renderSuccessStep(el, response.accession_no);
      } else {
        toast('Unexpected response from server', 'error');
        createBtn.disabled = false;
      }
    } catch (err) {
      toast(err.message, 'error');
      createBtn.disabled = false;
    }
  });
  actions.appendChild(createBtn);
  form.appendChild(actions);

  el.appendChild(form);

  try {
    const data = await locationTree();
    if (data?.tree) {
      populateLocationSelect(locationSelect, flattenLocationTree(data.tree), {
        blank: { value: '', label: 'No location' },
      });
    }
  } catch {
    /* leave lone No location option */
  }
}
