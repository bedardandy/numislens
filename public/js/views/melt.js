import { meltStatus, portfolioValue, updateMelt } from '../api.js';
import { toast } from '../app.js';

const EM_DASH = '\u2014';
const METAL_NAMES = { XAG: 'Silver', XAU: 'Gold', XPT: 'Platinum' };
const METALS = ['XAG', 'XAU', 'XPT'];

function display(v) {
  return v == null || v === '' ? EM_DASH : String(v);
}

export async function renderMelt(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Melt';
  el.appendChild(heading);

  const bannerArea = document.createElement('div');
  bannerArea.className = 'melt-banner-area';
  el.appendChild(bannerArea);

  const updateBar = document.createElement('div');
  updateBar.className = 'melt-update-bar';

  const updateBtn = document.createElement('button');
  updateBtn.type = 'button';
  updateBtn.textContent = 'Update spot prices';
  updateBar.appendChild(updateBtn);
  el.appendChild(updateBar);

  const content = document.createElement('div');
  content.className = 'melt-content';
  el.appendChild(content);

  function clearBanner() {
    bannerArea.replaceChildren();
  }

  function showErrorBanner(messages) {
    clearBanner();
    const banner = document.createElement('div');
    banner.className = 'melt-error-banner';
    banner.setAttribute('role', 'alert');
    for (const msg of messages) {
      const line = document.createElement('div');
      line.textContent = msg;
      banner.appendChild(line);
    }
    bannerArea.appendChild(banner);
  }

  updateBtn.addEventListener('click', async () => {
    const ok = window.confirm(
      'Live fetch from two sources; runs daily via timer — update manually only if needed.\n\nUpdate spot prices now?'
    );
    if (!ok) return;

    clearBanner();
    updateBtn.disabled = true;

    let res;
    try {
      res = await updateMelt();
    } catch (err) {
      showErrorBanner([err.message]);
      toast(err.message, 'error');
      updateBtn.disabled = false;
      return;
    }

    const errorKeys = Object.keys(res.errors || {});
    if (errorKeys.length) {
      const lines = errorKeys.map((metal) => `${metal}: ${res.errors[metal]}`);
      showErrorBanner(lines);
      toast(lines[0], 'error');
    }

    if (res.recorded?.length) {
      toast('Recorded: ' + res.recorded.join(', '), 'success');
    }

    await load();
    updateBtn.disabled = false;
  });

  async function load() {
    content.replaceChildren();
    const loading = document.createElement('p');
    loading.textContent = 'Loading\u2026';
    content.appendChild(loading);

    let status;
    let portfolio;
    try {
      [status, portfolio] = await Promise.all([meltStatus(), portfolioValue()]);
    } catch (err) {
      content.replaceChildren();
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      content.appendChild(errDiv);
      toast(err.message, 'error');
      return;
    }

    content.replaceChildren();

    const spotGrid = document.createElement('div');
    spotGrid.className = 'melt-spot-grid';

    for (const metal of METALS) {
      const card = document.createElement('div');
      card.className = 'spot-card';

      const metalLabel = document.createElement('div');
      metalLabel.className = 'spot-metal';
      metalLabel.textContent = (METAL_NAMES[metal] || metal) + ' (' + metal + ')';
      card.appendChild(metalLabel);

      const spot = status.spots[metal];
      if (spot == null) {
        const priceEl = document.createElement('div');
        priceEl.className = 'spot-price';
        priceEl.textContent = EM_DASH;
        card.appendChild(priceEl);

        const metaEl = document.createElement('div');
        metaEl.className = 'spot-meta';
        metaEl.textContent = 'No spot price yet';
        card.appendChild(metaEl);
      } else {
        const priceEl = document.createElement('div');
        priceEl.className = 'spot-price';
        priceEl.textContent = display(spot.price_display);
        card.appendChild(priceEl);

        const sourceEl = document.createElement('div');
        sourceEl.className = 'spot-meta';
        sourceEl.textContent = 'Source: ' + display(spot.source);
        card.appendChild(sourceEl);

        const fetchedEl = document.createElement('div');
        fetchedEl.className = 'spot-meta';
        fetchedEl.textContent = 'Fetched: ' + display(spot.fetched_at);
        card.appendChild(fetchedEl);
      }

      const d = status.delta ? status.delta[metal] : undefined;
      const deltaEl = document.createElement('div');
      if (d != null && d.pct != null) {
        const pct = d.pct;
        const alert = Math.abs(pct) > 3;
        deltaEl.className = 'spot-delta' + (alert ? ' spot-delta--alert' : '');
        deltaEl.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '% (24h)';
      } else {
        deltaEl.className = 'spot-delta';
        deltaEl.textContent = '\u0394 ' + EM_DASH;
      }
      card.appendChild(deltaEl);

      spotGrid.appendChild(card);
    }
    content.appendChild(spotGrid);

    const portfolioSection = document.createElement('div');
    portfolioSection.className = 'melt-portfolio';

    const portfolioHeading = document.createElement('h3');
    portfolioHeading.textContent = 'Portfolio melt';
    portfolioSection.appendChild(portfolioHeading);

    const totalEl = document.createElement('div');
    totalEl.className = 'melt-total';
    totalEl.textContent = display(status.portfolio.total_display);
    portfolioSection.appendChild(totalEl);

    const byMetalList = document.createElement('ul');
    byMetalList.className = 'melt-by-metal';

    const byMetal = status.portfolio.by_metal || {};
    const metalsWithData = METALS.filter((metal) => byMetal[metal] != null);

    if (!metalsWithData.length) {
      const emptyLi = document.createElement('li');
      emptyLi.className = 'muted';
      emptyLi.textContent = 'No precious-metal coins yet.';
      byMetalList.appendChild(emptyLi);
    } else {
      for (const metal of metalsWithData) {
        const li = document.createElement('li');
        li.textContent =
          (METAL_NAMES[metal] || metal) + ': ' + display(byMetal[metal].display);
        byMetalList.appendChild(li);
      }
    }
    portfolioSection.appendChild(byMetalList);
    content.appendChild(portfolioSection);

    const basisData = portfolio.value_est_by_basis || {};
    const basisEntries = Object.entries(basisData);

    if (!basisEntries.length) {
      const emptyP = document.createElement('p');
      emptyP.className = 'muted';
      emptyP.textContent = 'No estimated values recorded.';
      content.appendChild(emptyP);
    } else {
      const wrap = document.createElement('div');
      wrap.className = 'table-wrap';

      const table = document.createElement('table');
      table.className = 'coin-table';

      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      for (const label of ['Basis', 'Count', 'Value']) {
        const th = document.createElement('th');
        th.scope = 'col';
        th.textContent = label;
        headerRow.appendChild(th);
      }
      thead.appendChild(headerRow);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      for (const [basis, row] of basisEntries) {
        const tr = document.createElement('tr');

        const tdBasis = document.createElement('td');
        tdBasis.textContent = display(basis);
        tr.appendChild(tdBasis);

        const tdCount = document.createElement('td');
        tdCount.textContent = display(row.count);
        tr.appendChild(tdCount);

        const tdValue = document.createElement('td');
        tdValue.textContent = display(row.value_display);
        tr.appendChild(tdValue);

        tbody.appendChild(tr);
      }

      const totalRow = document.createElement('tr');
      const tdTotalLabel = document.createElement('td');
      tdTotalLabel.textContent = 'Total';
      totalRow.appendChild(tdTotalLabel);

      const tdBlank = document.createElement('td');
      tdBlank.textContent = EM_DASH;
      totalRow.appendChild(tdBlank);

      const tdTotalValue = document.createElement('td');
      tdTotalValue.textContent = display(portfolio.value_est_total_display);
      totalRow.appendChild(tdTotalValue);

      tbody.appendChild(totalRow);
      table.appendChild(tbody);
      wrap.appendChild(table);
      content.appendChild(wrap);
    }
  }

  await load();
}
