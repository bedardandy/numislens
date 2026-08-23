import {
  getAppraisalReport,
  getAppraisalReportPdf,
  exportCoinsCsv,
  exportListingsCsv,
} from '../api.js';
import { formatCents } from '../money.js';
import { toast } from '../app.js';

const EM_DASH = '—';
const MIDDOT = '·';
const MINUS = '−';

const METAL_NAMES = { XAG: 'Silver', XAU: 'Gold', XPT: 'Platinum' };

const BASIS_LABELS = {
  collectible: 'Collectible',
  reference: 'Reference',
  melt: 'Melt',
  face: 'Face',
  best: 'Best',
};

// ---------------------------------------------------------------------------
// Pure helpers (exported for testing). These operate on plain data only.
// ---------------------------------------------------------------------------

export function display(value) {
  return value == null || value === '' ? EM_DASH : String(value);
}

export function metalName(metal) {
  if (metal == null || metal === '') return EM_DASH;
  return METAL_NAMES[metal] || String(metal);
}

export function basisLabel(basis) {
  if (basis == null || basis === '') return EM_DASH;
  return BASIS_LABELS[basis] || String(basis);
}

export function formatYearMint(year, mintmark) {
  const hasYear = year != null && year !== '';
  const hasMint = mintmark != null && mintmark !== '';
  if (!hasYear && !hasMint) return EM_DASH;
  return `${hasYear ? String(year) : EM_DASH}${hasMint ? String(mintmark) : EM_DASH}`;
}

/**
 * Shapes a paired gain/loss cents value for display.
 * tone: 'gain' (>0), 'loss' (<0), 'flat' (0), or null for nullish input.
 */
export function formatGainLoss(cents) {
  if (cents == null || Number.isNaN(cents)) {
    return { display: EM_DASH, tone: null };
  }
  const tone = cents > 0 ? 'gain' : cents < 0 ? 'loss' : 'flat';
  const sign = cents > 0 ? '+' : cents < 0 ? MINUS : '';
  return { display: sign + formatCents(Math.abs(cents)), tone };
}

/**
 * Secondary line for a highlight row: shows melt vs collectible only when
 * both are present, so we never surface a single lonely figure.
 */
export function highlightSecondary(h) {
  if (h == null) return null;
  if (h.melt_cents == null || h.collectible_cents == null) return null;
  return `Melt ${formatCents(h.melt_cents)} ${MIDDOT} Collectible ${formatCents(h.collectible_cents)}`;
}

/**
 * One row of the appraisal worklist table: accession link text, identity,
 * grade, current best, potential, gap. Pure — exported for tests.
 */
export function worklistRowCells(w) {
  const grade = w.grade_bucket ? `[${w.grade_bucket}]` : EM_DASH;
  return [
    display(w.accession_no),
    display(w.identity),
    grade,
    formatCents(w.current_best_cents),
    formatCents(w.potential_cents),
    formatGainLoss(w.gap_cents).display,
  ];
}

/**
 * Provenance footnote lines for the reference datasets that informed a
 * report: "name — Source Name, retrieved YYYY-MM-DD (url)". Pure — exported
 * for tests.
 */
export function referenceSourceLines(references) {
  if (!Array.isArray(references)) return [];
  return references.map((r) => {
    const s = r.source || {};
    return `${display(r.name)} — ${display(s.name)}, retrieved ${display(s.retrieved)} (${display(s.url)})`;
  });
}

/** Filename-safe date (YYYY-MM-DD) from an ISO timestamp, else today (UTC). */
export function filenameDate(iso) {
  if (typeof iso === 'string') {
    const m = iso.match(/^(\d{4}-\d{2}-\d{2})/);
    if (m) return m[1];
  }
  return new Date().toISOString().slice(0, 10);
}

export function setRowCells(s) {
  return [
    display(s.name),
    `${display(s.filled)}/${display(s.total_slots)}`,
    display(s.owned_count),
    formatCents(s.value_cents),
  ];
}

export function mintRowCells(m) {
  return [display(m.mintmark), display(m.count), display(m.valued_count), formatCents(m.value_cents)];
}

export function seriesRowCells(s) {
  return [display(s.series), display(s.count), display(s.valued_count), formatCents(s.value_cents)];
}

export function metalRowCells(m) {
  return [metalName(m.metal), display(m.count), formatCents(m.melt_cents), formatCents(m.value_cents)];
}

export function rollRowCells(r) {
  return [
    display(r.roll_no),
    display(r.denomination),
    display(r.count),
    display(r.status),
    basisLabel(r.basis),
    formatCents(r.value_cents),
  ];
}

/** "Face $X · Melt $Y · Best $Z" summary line for the rolls totals. */
export function rollTotalsLine(totals) {
  return (
    `Face ${formatCents(totals.roll_face_total_cents)} ${MIDDOT} ` +
    `Melt ${formatCents(totals.roll_melt_total_cents)} ${MIDDOT} ` +
    `Best ${formatCents(totals.roll_best_total_cents)}`
  );
}

/**
 * Realized-P&L lines from the report's ``realized`` block. Returns [] when
 * nothing has been sold. Missing inputs are DISCLOSED, never imputed.
 */
export function realizedLines(realized) {
  if (realized == null || !realized.sold_count) return [];
  const gl = formatGainLoss(realized.realized_pnl_cents);
  const lines = [
    `${realized.sold_count} sold ${MIDDOT} proceeds ${formatCents(realized.proceeds_cents)} ` +
      `${MIDDOT} cost ${formatCents(realized.cost_basis_total_cents)} ` +
      `${MIDDOT} realized ${gl.display}`,
  ];
  if (realized.missing_cost_count > 0) {
    lines.push(
      `${realized.missing_cost_count} sold coin${realized.missing_cost_count === 1 ? '' : 's'} ` +
        'have no recorded cost basis — profit is not imputed for them'
    );
  }
  return lines;
}

// ---------------------------------------------------------------------------
// DOM building
// ---------------------------------------------------------------------------

function makeTable(headers, rows) {
  const wrap = document.createElement('div');
  wrap.className = 'table-wrap';

  const table = document.createElement('table');
  table.className = 'coin-table';

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const label of headers) {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = label;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  for (const cells of rows) {
    const tr = document.createElement('tr');
    for (const cell of cells) {
      const td = document.createElement('td');
      td.textContent = cell;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function makeGroupSection(title, headers, items, rowFn) {
  if (!Array.isArray(items) || items.length === 0) return null;
  const section = document.createElement('section');
  section.className = 'report-group';

  const h = document.createElement('h3');
  h.textContent = title;
  section.appendChild(h);

  section.appendChild(makeTable(headers, items.map(rowFn)));
  return section;
}

function buildBreakdownCards(breakdown) {
  const grid = document.createElement('div');
  grid.className = 'melt-spot-grid';

  const cards = [
    { label: 'Collectible', data: breakdown.collectible },
    { label: 'Melt makes sense', data: breakdown.melt },
    { label: 'Face value', data: breakdown.face },
  ];

  for (const { label, data } of cards) {
    const card = document.createElement('div');
    card.className = 'spot-card';

    const labelEl = document.createElement('div');
    labelEl.className = 'spot-metal';
    labelEl.textContent = label;
    card.appendChild(labelEl);

    const valueEl = document.createElement('div');
    valueEl.className = 'spot-price';
    valueEl.textContent = data ? formatCents(data.total_cents) : EM_DASH;
    card.appendChild(valueEl);

    const countEl = document.createElement('div');
    countEl.className = 'spot-meta';
    const count = data ? data.count : 0;
    countEl.textContent = `${display(count)} coin${count === 1 ? '' : 's'}`;
    card.appendChild(countEl);

    grid.appendChild(card);
  }

  return grid;
}

function buildHighlightsTable(highlights) {
  const wrap = document.createElement('div');
  wrap.className = 'table-wrap';

  const table = document.createElement('table');
  table.className = 'coin-table';

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const label of ['#', 'Accession', 'Series', 'Year-Mint', 'Grade', 'Basis', 'Best']) {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = label;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  highlights.forEach((h, i) => {
    const acc = h.accession_no;
    const tr = document.createElement('tr');

    const secondary = highlightSecondary(h);
    if (secondary) tr.title = secondary;

    const tdRank = document.createElement('td');
    tdRank.textContent = String(i + 1);
    tr.appendChild(tdRank);

    const tdAcc = document.createElement('td');
    const link = document.createElement('a');
    link.href = `#/coin/${encodeURIComponent(acc)}`;
    link.textContent = display(acc);
    tdAcc.appendChild(link);
    tr.appendChild(tdAcc);

    const tdSeries = document.createElement('td');
    tdSeries.textContent = display(h.series);
    tr.appendChild(tdSeries);

    const tdYearMint = document.createElement('td');
    tdYearMint.textContent = formatYearMint(h.year, h.mintmark);
    tr.appendChild(tdYearMint);

    const tdGrade = document.createElement('td');
    tdGrade.textContent = display(h.grade_bucket);
    tr.appendChild(tdGrade);

    const tdBasis = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'report-basis-badge';
    badge.textContent = basisLabel(h.best_basis);
    tdBasis.appendChild(badge);
    tr.appendChild(tdBasis);

    const tdBest = document.createElement('td');
    tdBest.appendChild(document.createTextNode(formatCents(h.best_cents)));
    if (secondary) {
      const sub = document.createElement('div');
      sub.className = 'muted';
      sub.style.fontSize = 'var(--font-size-sm)';
      sub.textContent = secondary;
      tdBest.appendChild(sub);
    }
    tr.appendChild(tdBest);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function buildFooter(report) {
  const footer = document.createElement('section');
  footer.className = 'report-footer';

  const h = document.createElement('h3');
  h.textContent = 'Provenance';
  footer.appendChild(h);

  const spot = report.spot || {};
  const metals = Object.keys(spot);
  if (metals.length) {
    const spotList = document.createElement('ul');
    spotList.className = 'melt-by-metal';
    for (const metal of metals) {
      const s = spot[metal] || {};
      const li = document.createElement('li');
      li.textContent =
        `${metalName(metal)}: ${formatCents(s.price_usd_cents)} ` +
        `(${display(s.source)}, fetched ${display(s.fetched_at)})`;
      spotList.appendChild(li);
    }
    footer.appendChild(spotList);
  }

  const gen = document.createElement('p');
  gen.className = 'muted';
  gen.textContent = `Generated ${display(report.generated_at)} ${MIDDOT} top ${display(report.top_n)}`;
  footer.appendChild(gen);

  // Curated reference datasets that informed this run — every non-melt
  // figure traces to a cited input.
  const refLines = referenceSourceLines(report.references);
  if (refLines.length) {
    const refHeading = document.createElement('p');
    refHeading.textContent = 'Reference data:';
    refHeading.style.fontWeight = '600';
    footer.appendChild(refHeading);
    const refList = document.createElement('ul');
    refList.className = 'melt-by-metal';
    for (const line of refLines) {
      const li = document.createElement('li');
      li.textContent = line;
      refList.appendChild(li);
    }
    footer.appendChild(refList);
    const refNote = document.createElement('p');
    refNote.className = 'muted';
    refNote.textContent =
      'Reference figures are retail-guide ballparks for triage — verify ' +
      'before any sale. They are never written onto coins.';
    footer.appendChild(refNote);
  }

  const dq = report.data_quality || {};
  const notes = [];
  if (dq.stale_count) {
    notes.push(`${dq.stale_count} spot price${dq.stale_count === 1 ? '' : 's'} may be stale`);
  }
  if (Array.isArray(dq.metals_missing_spot) && dq.metals_missing_spot.length) {
    notes.push(`No spot price for ${dq.metals_missing_spot.map(metalName).join(', ')}`);
  }
  if (dq.rolls_unvalued_count) {
    notes.push(
      `${dq.rolls_unvalued_count} roll${dq.rolls_unvalued_count === 1 ? '' : 's'} have no basis for a value — not included in roll totals`,
    );
  }
  for (const note of notes) {
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = note;
    footer.appendChild(p);
  }

  return footer;
}

export async function renderReport(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Appraisal Report';
  el.appendChild(heading);

  const actionBar = document.createElement('div');
  actionBar.className = 'melt-update-bar';
  const downloadBtn = document.createElement('button');
  downloadBtn.type = 'button';
  downloadBtn.textContent = 'Download PDF';
  actionBar.appendChild(downloadBtn);
  const csvBtn = document.createElement('button');
  csvBtn.type = 'button';
  csvBtn.textContent = 'Export CSV';
  csvBtn.title = 'Every coin as CSV — spreadsheets, estate sharing, re-import';
  actionBar.appendChild(csvBtn);
  const listingsBtn = document.createElement('button');
  listingsBtn.type = 'button';
  listingsBtn.textContent = 'Export listings';
  listingsBtn.title = 'Staging CSV for coins marked for sale (marketplace upload prep)';
  actionBar.appendChild(listingsBtn);
  el.appendChild(actionBar);

  const content = document.createElement('div');
  content.className = 'report-content';
  el.appendChild(content);

  let currentReport = null;

  downloadBtn.addEventListener('click', async () => {
    downloadBtn.disabled = true;
    try {
      const blob = await getAppraisalReportPdf();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `numislens-appraisal-${filenameDate(currentReport?.generated_at)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Appraisal PDF downloaded', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      downloadBtn.disabled = false;
    }
  });

  csvBtn.addEventListener('click', async () => {
    csvBtn.disabled = true;
    try {
      const blob = await exportCoinsCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `numislens-coins-${filenameDate(new Date().toISOString())}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Coins CSV downloaded', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      csvBtn.disabled = false;
    }
  });

  listingsBtn.addEventListener('click', async () => {
    listingsBtn.disabled = true;
    try {
      const blob = await exportListingsCsv('for_sale');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `numislens-listings-${filenameDate(new Date().toISOString())}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Listings CSV downloaded', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      listingsBtn.disabled = false;
    }
  });

  async function load() {
    content.replaceChildren();
    const loading = document.createElement('p');
    loading.textContent = 'Loading…';
    content.appendChild(loading);

    let report;
    try {
      report = await getAppraisalReport();
    } catch (err) {
      content.replaceChildren();
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      content.appendChild(errDiv);
      toast(err.message, 'error');
      return;
    }

    currentReport = report;
    content.replaceChildren();

    const totals = report.totals || {};
    const breakdown = report.breakdown || {};
    const groups = report.groups || {};

    // --- Headline ---------------------------------------------------------
    const headline = document.createElement('div');
    headline.className = 'report-headline';

    const totalEl = document.createElement('div');
    totalEl.className = 'melt-total';
    totalEl.textContent = formatCents(totals.best_total_cents);
    headline.appendChild(totalEl);

    const subEl = document.createElement('div');
    subEl.className = 'spot-meta';
    subEl.textContent =
      `${display(totals.valued_count)} of ${display(totals.coin_count)} coins valued`;
    headline.appendChild(subEl);

    if (totals.cost_basis_count > 0) {
      const gl = formatGainLoss(totals.gain_loss_cents);
      const glEl = document.createElement('div');
      glEl.className = 'report-gainloss';
      glEl.textContent = `Gain/loss ${gl.display} on ${display(totals.cost_basis_count)} coin${totals.cost_basis_count === 1 ? '' : 's'} with cost basis`;
      if (gl.tone === 'gain') glEl.style.color = 'var(--color-success)';
      else if (gl.tone === 'loss') glEl.style.color = 'var(--color-error)';
      headline.appendChild(glEl);
    }
    content.appendChild(headline);

    // --- Breakdown cards --------------------------------------------------
    content.appendChild(buildBreakdownCards(breakdown));

    // --- Realized (sold coins) --------------------------------------------
    const rLines = realizedLines(report.realized);
    if (rLines.length) {
      const realizedEl = document.createElement('p');
      realizedEl.className = 'muted';
      const gl = formatGainLoss(report.realized.realized_pnl_cents);
      for (let i = 0; i < rLines.length; i++) {
        const line = document.createElement('span');
        line.textContent = rLines[i];
        line.style.display = 'block';
        if (i === 0 && gl.tone) {
          line.style.color =
            gl.tone === 'gain' ? 'var(--color-success)'
            : gl.tone === 'loss' ? 'var(--color-error)' : '';
        }
        realizedEl.appendChild(line);
      }
      content.appendChild(realizedEl);
    }

    const unvaluedCount = breakdown.unvalued?.count ?? totals.unvalued_count ?? 0;
    if (unvaluedCount > 0) {
      const note = document.createElement('p');
      note.className = 'muted';
      note.textContent =
        `${unvaluedCount} coin${unvaluedCount === 1 ? '' : 's'} have no basis for a value — not included in totals`;
      content.appendChild(note);
    }

    // --- Top highlights ---------------------------------------------------
    const highlights = Array.isArray(report.highlights) ? report.highlights : [];
    if (highlights.length) {
      const hHeading = document.createElement('h3');
      hHeading.textContent = 'Top highlights';
      content.appendChild(hHeading);
      content.appendChild(buildHighlightsTable(highlights));
    }

    // --- Appraisal worklist ------------------------------------------------
    const worklist = Array.isArray(report.worklist) ? report.worklist : [];
    if (worklist.length) {
      const wHeading = document.createElement('h3');
      wHeading.textContent = 'Appraisal worklist — what deserves eyes first';
      content.appendChild(wHeading);
      const wNote = document.createElement('p');
      wNote.className = 'muted';
      wNote.textContent =
        'Identities flagged by the curated reference data (key dates etc.) ' +
        'whose current value falls short. Potential is the identity\u2019s top ' +
        'catalog level \u2014 an attention signal from cited data, not a promise; ' +
        'grade decides where a coin actually lands.';
      content.appendChild(wNote);

      const wWrap = document.createElement('div');
      wWrap.className = 'table-wrap';
      const wTable = document.createElement('table');
      wTable.className = 'coin-table';
      const wHead = document.createElement('thead');
      const wHeadRow = document.createElement('tr');
      for (const label of ['Accession', 'Identity', 'Grade', 'Now', 'Potential', 'Gap']) {
        const th = document.createElement('th');
        th.scope = 'col';
        th.textContent = label;
        wHeadRow.appendChild(th);
      }
      wHead.appendChild(wHeadRow);
      wTable.appendChild(wHead);
      const wBody = document.createElement('tbody');
      for (const w of worklist) {
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        const acc = w.accession_no;
        tr.addEventListener('click', () => { window.location.hash = `#/coin/${encodeURIComponent(acc)}`; });
        const cells = worklistRowCells(w);
        cells.forEach((cell, idx) => {
          const td = document.createElement('td');
          if (idx === 0) {
            const link = document.createElement('a');
            link.href = `#/coin/${encodeURIComponent(acc)}`;
            link.textContent = cell;
            link.addEventListener('click', (e) => e.stopPropagation());
            td.appendChild(link);
          } else {
            td.textContent = cell;
          }
          if (idx === 5) {
            const tone = w.gap_cents > 0 ? 'var(--color-success)' : '';
            if (tone) td.style.color = tone;
          }
          tr.appendChild(td);
        });
        if (w.location_path) tr.title = 'Location: ' + w.location_path;
        wBody.appendChild(tr);
      }
      wTable.appendChild(wBody);
      wWrap.appendChild(wTable);
      content.appendChild(wWrap);
    }

    // --- Groups -----------------------------------------------------------
    const groupSections = [
      makeGroupSection('Sets', ['Set', 'Filled', 'Owned', 'Value'], groups.sets, setRowCells),
      makeGroupSection('Mints', ['Mintmark', 'Count', 'Valued', 'Value'], groups.mints, mintRowCells),
      makeGroupSection('Series', ['Series', 'Count', 'Valued', 'Value'], groups.series, seriesRowCells),
      makeGroupSection('Metals', ['Metal', 'Count', 'Melt', 'Value'], groups.metals, metalRowCells),
    ];
    for (const section of groupSections) {
      if (section) content.appendChild(section);
    }

    // --- Rolls --------------------------------------------------------------
    if (totals.roll_count > 0) {
      const rollsSection = makeGroupSection(
        'Rolls',
        ['Roll', 'Denomination', 'Count', 'Status', 'Basis', 'Value'],
        groups.rolls,
        rollRowCells,
      );
      if (rollsSection) content.appendChild(rollsSection);

      const rollTotalsP = document.createElement('p');
      rollTotalsP.className = 'muted';
      rollTotalsP.textContent = rollTotalsLine(totals);
      content.appendChild(rollTotalsP);

      const grandTotalDiv = document.createElement('div');
      grandTotalDiv.className = 'melt-total';
      grandTotalDiv.textContent = `GRAND TOTAL ${formatCents(totals.grand_total_cents)}`;
      content.appendChild(grandTotalDiv);
    }

    // --- Provenance footer ------------------------------------------------
    content.appendChild(buildFooter(report));
  }

  await load();
}
