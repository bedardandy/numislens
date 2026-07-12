import { listCoins, locationTree } from '../api.js';
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

function formatYearMint(year, mintmark) {
  const hasYear = year != null && year !== '';
  const hasMint = mintmark != null && mintmark !== '';
  if (!hasYear && !hasMint) return EM_DASH;
  return `${hasYear ? String(year) : EM_DASH}${hasMint ? String(mintmark) : EM_DASH}`;
}

function buildFilterParams(seriesInput, yearInput, mintmarkInput, locationSelect) {
  const params = {};
  const series = seriesInput.value.trim();
  if (series) params.series = series;

  const yearVal = yearInput.value.trim();
  if (yearVal) {
    const y = parseInt(yearVal, 10);
    if (!Number.isNaN(y)) params.year = y;
  }

  const mintmark = mintmarkInput.value.trim();
  if (mintmark) params.mintmark = mintmark;

  const locVal = locationSelect.value;
  if (locVal) {
    const lid = parseInt(locVal, 10);
    if (!Number.isNaN(lid)) params.location_id = lid;
  }

  return params;
}

function populateLocationSelect(select, locationPaths) {
  const blank = document.createElement('option');
  blank.value = '';
  blank.textContent = 'All locations';
  select.appendChild(blank);

  const entries = [...locationPaths.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  for (const [id, path] of entries) {
    const opt = document.createElement('option');
    opt.value = String(id);
    opt.textContent = path;
    select.appendChild(opt);
  }
}

function renderCoinTable(container, coins, locationPaths) {
  container.replaceChildren();

  if (!coins.length) return;

  const wrap = document.createElement('div');
  wrap.className = 'table-wrap';

  const table = document.createElement('table');
  table.className = 'coin-table';

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const label of ['Accession', 'Series', 'Year-Mint', 'Grade', 'Value', 'Location']) {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = label;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  for (const coin of coins) {
    const acc = coin.accession_no;
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => navigate(`#/coin/${encodeURIComponent(acc)}`));

    const tdAcc = document.createElement('td');
    const link = document.createElement('a');
    link.href = `#/coin/${encodeURIComponent(acc)}`;
    link.textContent = display(acc);
    link.addEventListener('click', (e) => e.stopPropagation());
    tdAcc.appendChild(link);
    tr.appendChild(tdAcc);

    const tdSeries = document.createElement('td');
    tdSeries.textContent = display(coin.series);
    tr.appendChild(tdSeries);

    const tdYearMint = document.createElement('td');
    tdYearMint.textContent = formatYearMint(coin.year, coin.mintmark);
    tr.appendChild(tdYearMint);

    const tdGrade = document.createElement('td');
    tdGrade.textContent = display(coin.grade_bucket);
    tr.appendChild(tdGrade);

    const tdValue = document.createElement('td');
    tdValue.textContent = display(coin.value_est_display);
    tr.appendChild(tdValue);

    const tdLoc = document.createElement('td');
    if (coin.location_id != null && locationPaths.has(coin.location_id)) {
      tdLoc.textContent = locationPaths.get(coin.location_id);
    } else {
      tdLoc.textContent = EM_DASH;
    }
    tr.appendChild(tdLoc);

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);
}

function renderEmptyState(container, filtered) {
  container.replaceChildren();
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.textContent = filtered
    ? 'No coins match these filters.'
    : 'Your collection is empty. Add coins in Phase 3b.';
  container.appendChild(empty);
}

export async function renderInventory(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Inventory';
  el.appendChild(heading);

  let locationPaths = new Map();
  try {
    const data = await locationTree();
    if (data?.tree) locationPaths = flattenLocationTree(data.tree);
  } catch {
    /* list coins anyway; location column shows em-dash */
  }

  const filterBar = document.createElement('div');
  filterBar.className = 'filter-bar';

  const seriesLabel = document.createElement('label');
  seriesLabel.textContent = 'Series';
  const seriesInput = document.createElement('input');
  seriesInput.type = 'text';
  seriesInput.name = 'series';
  seriesLabel.appendChild(seriesInput);
  filterBar.appendChild(seriesLabel);

  const yearLabel = document.createElement('label');
  yearLabel.textContent = 'Year';
  const yearInput = document.createElement('input');
  yearInput.type = 'number';
  yearInput.name = 'year';
  yearLabel.appendChild(yearInput);
  filterBar.appendChild(yearLabel);

  const mintmarkLabel = document.createElement('label');
  mintmarkLabel.textContent = 'Mintmark';
  const mintmarkInput = document.createElement('input');
  mintmarkInput.type = 'text';
  mintmarkInput.name = 'mintmark';
  mintmarkLabel.appendChild(mintmarkInput);
  filterBar.appendChild(mintmarkLabel);

  const locationLabel = document.createElement('label');
  locationLabel.textContent = 'Location';
  const locationSelect = document.createElement('select');
  locationSelect.name = 'location_id';
  populateLocationSelect(locationSelect, locationPaths);
  locationLabel.appendChild(locationSelect);
  filterBar.appendChild(locationLabel);

  const applyBtn = document.createElement('button');
  applyBtn.type = 'button';
  applyBtn.textContent = 'Apply';
  filterBar.appendChild(applyBtn);

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.textContent = 'Clear';
  filterBar.appendChild(clearBtn);

  el.appendChild(filterBar);

  const resultsContainer = document.createElement('div');
  resultsContainer.className = 'inventory-results';
  el.appendChild(resultsContainer);

  async function loadCoins() {
    const params = buildFilterParams(seriesInput, yearInput, mintmarkInput, locationSelect);
    const filtered = Object.keys(params).length > 0;

    try {
      const coins = await listCoins(params);
      if (!coins.length) {
        renderEmptyState(resultsContainer, filtered);
      } else {
        renderCoinTable(resultsContainer, coins, locationPaths);
      }
    } catch (err) {
      resultsContainer.replaceChildren();
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      resultsContainer.appendChild(errDiv);
      toast(err.message, 'error');
    }
  }

  applyBtn.addEventListener('click', () => loadCoins());

  clearBtn.addEventListener('click', () => {
    seriesInput.value = '';
    yearInput.value = '';
    mintmarkInput.value = '';
    locationSelect.value = '';
    loadCoins();
  });

  await loadCoins();
}
