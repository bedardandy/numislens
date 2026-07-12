import {
  getCoin,
  getLocation,
  locationTree,
  moveCoin,
  fetchBlob,
} from '../api.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';

const EM_DASH = '\u2014';

function display(value) {
  if (value == null || value === '') return EM_DASH;
  return String(value);
}

/** Flatten {tree:[{id,kind,label,children},...]} into Map<location_id, full path>. */
function flattenLocationTree(nodes, parentPath = '') {
  const map = new Map();
  for (const node of nodes) {
    const path = parentPath ? `${parentPath} > ${node.label}` : node.label;
    map.set(node.id, path);
    if (node.children?.length) {
      for (const [id, childPath] of flattenLocationTree(node.children, path)) {
        map.set(id, childPath);
      }
    }
  }
  return map;
}

function addDetailRow(dl, label, value) {
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

function makeBackLink() {
  const back = document.createElement('a');
  back.href = '#/';
  back.textContent = 'Back to inventory';
  back.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/');
  });
  return back;
}

async function loadImageStrip(container, accession, images) {
  container.replaceChildren();

  if (!images?.length) {
    const muted = document.createElement('p');
    muted.style.color = 'var(--color-text-muted)';
    muted.style.fontSize = 'var(--font-size-sm)';
    muted.textContent = 'No photos yet.';
    container.appendChild(muted);
    return;
  }

  const strip = document.createElement('div');
  strip.className = 'image-strip';

  for (const img of images) {
    try {
      const blob = await fetchBlob(
        `/api/v1/coins/${encodeURIComponent(accession)}/images/${img.content_hash}`,
      );
      const url = URL.createObjectURL(blob);
      const image = document.createElement('img');
      image.src = url;
      image.alt = img.kind ?? '';
      strip.appendChild(image);
    } catch {
      /* skip failed images */
    }
  }

  if (strip.childElementCount === 0) {
    const muted = document.createElement('p');
    muted.style.color = 'var(--color-text-muted)';
    muted.style.fontSize = 'var(--font-size-sm)';
    muted.textContent = 'No photos yet.';
    container.appendChild(muted);
  } else {
    container.appendChild(strip);
  }
}

export async function renderCoin(el, accession) {
  el.replaceChildren();

  const loading = document.createElement('p');
  loading.textContent = 'Loading\u2026';
  el.appendChild(loading);

  let coin;
  try {
    coin = await getCoin(accession);
  } catch (err) {
    el.replaceChildren();
    const errDiv = document.createElement('div');
    errDiv.className = 'empty-state';
    errDiv.textContent = err.message;
    errDiv.appendChild(document.createElement('br'));
    errDiv.appendChild(makeBackLink());
    el.appendChild(errDiv);
    toast(err.message, 'error');
    return;
  }

  el.replaceChildren();

  el.appendChild(makeBackLink());

  const title = document.createElement('h2');
  title.textContent = display(coin.accession_no);
  el.appendChild(title);

  const locationEl = document.createElement('div');
  locationEl.className = 'coin-location';
  locationEl.style.cssText =
    'margin:var(--space-md) 0 var(--space-lg);padding:var(--space-sm) var(--space-md);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);font-weight:600;font-size:var(--font-size-lg);';

  if (coin.location_id != null) {
    locationEl.textContent = 'Loading location\u2026';
    el.appendChild(locationEl);
    try {
      const loc = await getLocation(coin.location_id);
      locationEl.textContent = loc?.path != null && loc.path !== '' ? loc.path : EM_DASH;
    } catch {
      locationEl.textContent = EM_DASH;
    }
  } else {
    locationEl.textContent = EM_DASH;
    el.appendChild(locationEl);
  }

  const imageContainer = document.createElement('div');
  el.appendChild(imageContainer);
  await loadImageStrip(imageContainer, accession, coin.coin_images);

  const dl = document.createElement('dl');
  dl.className = 'coin-detail';

  addDetailRow(dl, 'Series', coin.series);
  addDetailRow(dl, 'Year', coin.year);
  addDetailRow(dl, 'Mintmark', coin.mintmark);
  addDetailRow(dl, 'Denomination', coin.denomination);
  addDetailRow(dl, 'Country', coin.country);
  addDetailRow(dl, 'Composition ID', coin.composition_id);
  addDetailRow(dl, 'Weight (g)', coin.weight_g);
  addDetailRow(dl, 'Diameter (mm)', coin.diameter_mm);
  addDetailRow(dl, 'Grade bucket', coin.grade_bucket);
  addDetailRow(dl, 'Grade source', coin.grade_source);
  addDetailRow(dl, 'TPG cert', coin.tpg_cert);
  addDetailRow(dl, 'Cost basis', coin.cost_basis_display);
  // Phase 3a: full appraisal history is not exposed by the API; only latest value fields below.
  addDetailRow(dl, 'Estimated value', coin.value_est_display);
  addDetailRow(dl, 'Value basis', coin.value_basis);
  addDetailRow(dl, 'Appraisal confidence', coin.appraisal_confidence);
  addDetailRow(dl, 'Last appraised', coin.last_appraised);
  addDetailRow(dl, 'Acquired date', coin.acquired_date);
  addDetailRow(dl, 'Acquired source', coin.acquired_source);
  addDetailRow(dl, 'Created at', coin.created_at);
  addDetailRow(dl, 'Notes', coin.notes);

  el.appendChild(dl);

  const actions = document.createElement('div');
  actions.className = 'detail-actions';

  const movePicker = document.createElement('div');
  movePicker.style.cssText =
    'display:none;flex-wrap:wrap;gap:var(--space-sm);align-items:center;width:100%;';

  const moveSelect = document.createElement('select');
  const confirmMoveBtn = document.createElement('button');
  confirmMoveBtn.type = 'button';
  confirmMoveBtn.textContent = 'Confirm move';

  movePicker.appendChild(moveSelect);
  movePicker.appendChild(confirmMoveBtn);

  const moveBtn = document.createElement('button');
  moveBtn.type = 'button';
  moveBtn.textContent = 'Move';
  moveBtn.addEventListener('click', async () => {
    if (movePicker.style.display !== 'none') {
      movePicker.style.display = 'none';
      return;
    }

    moveSelect.replaceChildren();
    try {
      const data = await locationTree();
      const paths = data?.tree ? flattenLocationTree(data.tree) : new Map();
      const entries = [...paths.entries()].sort((a, b) => a[1].localeCompare(b[1]));
      for (const [id, path] of entries) {
        const opt = document.createElement('option');
        opt.value = String(id);
        opt.textContent = path;
        if (coin.location_id != null && id === coin.location_id) opt.selected = true;
        moveSelect.appendChild(opt);
      }
      movePicker.style.display = 'flex';
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  confirmMoveBtn.addEventListener('click', async () => {
    const selectedId = parseInt(moveSelect.value, 10);
    if (Number.isNaN(selectedId)) return;

    confirmMoveBtn.disabled = true;
    try {
      await moveCoin(accession, selectedId);
      toast('Moved', 'success');
      await renderCoin(el, accession);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      confirmMoveBtn.disabled = false;
    }
  });

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

  const photosBtn = document.createElement('button');
  photosBtn.type = 'button';
  photosBtn.textContent = 'Add photos';
  photosBtn.disabled = true;
  photosBtn.title = 'Coming in Phase 3b';

  actions.appendChild(moveBtn);
  actions.appendChild(printBtn);
  actions.appendChild(photosBtn);
  actions.appendChild(movePicker);
  el.appendChild(actions);
}
