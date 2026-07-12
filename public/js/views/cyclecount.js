import { getLocation } from '../api.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';

// Future work: emit a 'counted' event type to the daemon ledger; for now this is view-state only.

const EM_DASH = '\u2014';

function display(v) {
  return v == null || v === '' ? EM_DASH : String(v);
}

function yearMint(year, mint) {
  const y = year != null && year !== '' ? String(year) : '';
  const m = mint != null && mint !== '' ? String(mint) : '';
  if (!y && !m) return EM_DASH;
  return (y || EM_DASH) + (m ? '-' + m : '');
}

function makeBackLink() {
  const back = document.createElement('a');
  back.href = '#/locations';
  back.textContent = 'Back to locations';
  back.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/locations');
  });
  return back;
}

export async function renderCycleCount(el, locationId) {
  el.replaceChildren();
  el.appendChild(makeBackLink());

  const loading = document.createElement('p');
  loading.textContent = 'Loading\u2026';
  el.appendChild(loading);

  let data;
  try {
    data = await getLocation(locationId, false);
  } catch (err) {
    el.replaceChildren();
    el.appendChild(makeBackLink());
    const errDiv = document.createElement('div');
    errDiv.className = 'empty-state';
    errDiv.textContent = err.message;
    el.appendChild(errDiv);
    toast(err.message, 'error');
    return;
  }

  el.replaceChildren();
  el.appendChild(makeBackLink());

  const heading = document.createElement('h2');
  heading.textContent = 'Count: ' + display(data.path);
  el.appendChild(heading);

  const expected = data.contents || [];

  const state = new Map();
  for (const coin of expected) {
    state.set(coin.accession_no, 'unmarked');
  }

  const scanBar = document.createElement('div');
  scanBar.className = 'cyclecount-scan';

  const scanInput = document.createElement('input');
  scanInput.type = 'text';
  scanInput.placeholder = 'Scan or type accession, then Enter';

  const markPresentBtn = document.createElement('button');
  markPresentBtn.type = 'button';
  markPresentBtn.textContent = 'Mark present';

  function markScannedPresent() {
    const val = scanInput.value.trim();
    if (!val) return;

    const found = expected.find(
      (c) =>
        c.accession_no &&
        c.accession_no.toUpperCase() === val.toUpperCase(),
    );

    if (found) {
      state.set(found.accession_no, 'present');
      scanInput.value = '';
      rerender();
      toast('Marked present: ' + found.accession_no, 'success');
    } else {
      toast('Not in this box: ' + val, 'error');
    }
  }

  scanInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      markScannedPresent();
    }
  });
  markPresentBtn.addEventListener('click', markScannedPresent);

  scanBar.appendChild(scanInput);
  scanBar.appendChild(markPresentBtn);

  const listContainer = document.createElement('div');
  listContainer.id = 'cyclecount-list';

  const summaryContainer = document.createElement('div');
  summaryContainer.id = 'cyclecount-summary';

  function renderList() {
    listContainer.replaceChildren();

    if (expected.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'No coins recorded in this location.';
      listContainer.appendChild(empty);
      return;
    }

    const ul = document.createElement('ul');
    ul.className = 'count-list';

    for (const coin of expected) {
      const li = document.createElement('li');
      li.className = 'count-item';

      const status = state.get(coin.accession_no);
      if (status === 'present') {
        li.classList.add('count-item--present');
      } else if (status === 'missing') {
        li.classList.add('count-item--missing');
      }

      const label = document.createElement('div');
      label.textContent =
        coin.accession_no +
        ' \u2014 ' +
        display(coin.series) +
        ' ' +
        yearMint(coin.year, coin.mintmark);
      li.appendChild(label);

      const presentBtn = document.createElement('button');
      presentBtn.type = 'button';
      presentBtn.textContent = 'Present';
      presentBtn.addEventListener('click', () => {
        state.set(coin.accession_no, 'present');
        rerender();
      });

      const missingBtn = document.createElement('button');
      missingBtn.type = 'button';
      missingBtn.textContent = 'Missing';
      missingBtn.addEventListener('click', () => {
        state.set(coin.accession_no, 'missing');
        rerender();
      });

      li.appendChild(presentBtn);
      li.appendChild(missingBtn);
      ul.appendChild(li);
    }

    listContainer.appendChild(ul);
  }

  function renderSummary() {
    summaryContainer.replaceChildren();

    let present = 0;
    let missing = 0;
    let unmarked = 0;
    for (const v of state.values()) {
      if (v === 'present') present++;
      else if (v === 'missing') missing++;
      else if (v === 'unmarked') unmarked++;
    }
    const expectedN = expected.length;

    const counts = document.createElement('div');
    counts.textContent =
      'Expected: ' +
      expectedN +
      '; Present: ' +
      present +
      '; Missing: ' +
      missing;
    summaryContainer.appendChild(counts);

    if (unmarked > 0) {
      const unmarkedLine = document.createElement('div');
      unmarkedLine.style.color = 'var(--color-text-muted)';
      unmarkedLine.textContent = 'Unmarked: ' + unmarked;
      summaryContainer.appendChild(unmarkedLine);
    }

    const missingHeading = document.createElement('div');
    missingHeading.textContent = 'Missing coins:';
    summaryContainer.appendChild(missingHeading);

    const missingAccessions = [];
    for (const [accession, v] of state.entries()) {
      if (v === 'missing') missingAccessions.push(accession);
    }

    const missingList = document.createElement('div');
    if (missingAccessions.length === 0) {
      missingList.textContent = 'None marked missing.';
    } else {
      missingList.textContent = missingAccessions.join(', ');
    }
    summaryContainer.appendChild(missingList);

    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.textContent = 'Copy report';
    copyBtn.addEventListener('click', async () => {
      let p = 0;
      let m = 0;
      let u = 0;
      for (const v of state.values()) {
        if (v === 'present') p++;
        else if (v === 'missing') m++;
        else if (v === 'unmarked') u++;
      }
      const expN = expected.length;

      const missingLines = [];
      for (const [accession, v] of state.entries()) {
        if (v === 'missing') missingLines.push(accession);
      }

      const lines = [
        'NumisLens cycle count',
        'Location: ' + display(data.path),
        'Timestamp: ' + new Date().toISOString(),
        '',
        'Expected: ' + expN,
        'Present: ' + p,
        'Missing: ' + m + (u ? ' (Unmarked: ' + u + ')' : ''),
        '',
        'Missing coins:',
        missingLines.length ? missingLines.join('\n') : '(none)',
      ];
      const report = lines.join('\n');

      try {
        await navigator.clipboard.writeText(report);
        toast('Report copied', 'success');
      } catch {
        try {
          const ta = document.createElement('textarea');
          ta.value = report;
          ta.style.position = 'fixed';
          ta.style.left = '-9999px';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          toast('Report copied', 'success');
        } catch {
          toast('Copy failed', 'error');
        }
      }
    });
    summaryContainer.appendChild(copyBtn);
  }

  function rerender() {
    renderList();
    renderSummary();
  }

  el.appendChild(scanBar);
  el.appendChild(listContainer);
  el.appendChild(summaryContainer);
  rerender();
}
