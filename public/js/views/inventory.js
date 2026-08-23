import { listCoinsPage, locationTree } from '../api.js';
import { toast } from '../app.js';
import { cacheSnapshot, readSnapshot, offlineBanner, isNetworkError } from '../offline.js';
import { navigate } from '../router.js';
import { flattenLocationTree, populateLocationSelect } from '../tree.js';

const EM_DASH = '\u2014';
const PAGE_SIZE = 50;
const DISPOSITIONS = ['owned', 'for_sale', 'sold', 'discarded'];

function display(value) {
  if (value == null || value === '') return EM_DASH;
  return String(value);
}

function formatYearMint(year, mintmark) {
  const hasYear = year != null && year !== '';
  const hasMint = mintmark != null && mintmark !== '';
  if (!hasYear && !hasMint) return EM_DASH;
  return `${hasYear ? String(year) : EM_DASH}${hasMint ? String(mintmark) : EM_DASH}`;
}

function buildFilterParams(seriesInput, yearInput, mintmarkInput, locationSelect, dispositionSelect) {
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

  const dispVal = dispositionSelect ? dispositionSelect.value : '';
  if (dispVal && DISPOSITIONS.includes(dispVal)) params.disposition = dispVal;

  return params;
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
    await cacheSnapshot('locations:tree', data);
  } catch {
    const snap = await readSnapshot('locations:tree');
    if (snap && snap.data && snap.data.tree) locationPaths = flattenLocationTree(snap.data.tree);
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
  populateLocationSelect(locationSelect, locationPaths, { blank: { value: '', label: 'All locations' } });
  locationLabel.appendChild(locationSelect);
  filterBar.appendChild(locationLabel);

  const dispositionLabel = document.createElement('label');
  dispositionLabel.textContent = 'Status';
  const dispositionSelect = document.createElement('select');
  dispositionSelect.name = 'disposition';
  const allDispOption = document.createElement('option');
  allDispOption.value = '';
  allDispOption.textContent = 'All statuses';
  dispositionSelect.appendChild(allDispOption);
  for (const d of DISPOSITIONS) {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d.replace('_', ' ');
    dispositionSelect.appendChild(opt);
  }
  dispositionLabel.appendChild(dispositionSelect);
  filterBar.appendChild(dispositionLabel);

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

  let accumulated = [];
  let totalMatching = 0;

  function renderAccumulated(filtered) {
    if (!accumulated.length) {
      renderEmptyState(resultsContainer, filtered);
      return;
    }
    renderCoinTable(resultsContainer, accumulated, locationPaths);
    if (accumulated.length < totalMatching) {
      const moreWrap = document.createElement('div');
      moreWrap.style.cssText = 'display:flex;justify-content:center;margin-top:var(--space-md);';
      const moreBtn = document.createElement('button');
      moreBtn.type = 'button';
      moreBtn.textContent = `Load more (${accumulated.length} of ${totalMatching})`;
      moreBtn.addEventListener('click', () => loadCoins({ append: true }));
      moreBtn.addEventListener('click', () => moreBtn.remove(), { once: true });
      moreWrap.appendChild(moreBtn);
      resultsContainer.appendChild(moreWrap);
    }
    if (!filtered && totalMatching === accumulated.length) {
      cacheSnapshot('coins', accumulated);
    }
  }

  async function loadCoins({ append = false } = {}) {
    const params = buildFilterParams(seriesInput, yearInput, mintmarkInput, locationSelect, dispositionSelect);
    const filtered = Object.keys(params).length > 0;
    const offset = append ? accumulated.length : 0;
    if (!append) accumulated = [];

    try {
      const { coins, total } = await listCoinsPage(params, PAGE_SIZE, offset);
      totalMatching = total;
      accumulated = accumulated.concat(coins);
      if (accumulated.length) {
        renderAccumulated(filtered);
      } else {
        renderEmptyState(resultsContainer, filtered);
      }
    } catch (err) {
      if (isNetworkError(err)) {
        const snap = await readSnapshot('coins');
        if (snap && Array.isArray(snap.data)) {
          resultsContainer.replaceChildren();
          resultsContainer.appendChild(offlineBanner(snap.cachedAt));
          if (snap.data.length) {
            const holder = document.createElement('div');
            renderCoinTable(holder, snap.data, locationPaths);
            resultsContainer.appendChild(holder);
          } else {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'No cached coins.';
            resultsContainer.appendChild(empty);
          }
          return;
        }
      }
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
    dispositionSelect.value = '';
    loadCoins();
  });

  await loadCoins();
}
