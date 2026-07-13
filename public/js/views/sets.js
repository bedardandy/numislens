import { listSets, getSetBoard, listCoins, assignToSet, getSetNeeds, getWantlistPdf } from '../api.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';
import { cacheSnapshot, readSnapshot, offlineBanner, isNetworkError } from '../offline.js';

const EM_DASH = '\u2014';

function display(value) {
  if (value == null || value === '') return EM_DASH;
  return String(value);
}

function yearMint(year, mint) {
  return String(year) + '-' + String(mint);
}

// ---------------------------------------------------------------------------
// Pure helpers (exported for testing).
// ---------------------------------------------------------------------------

/**
 * "filled/total (pct%)" completion caption. Computes the percentage (one
 * decimal) from filled/total when ``pct`` is not supplied, matching how the
 * ``/sets/{id}/needs`` endpoint rounds ``completion_pct``.
 */
export function formatCompletion(filled, total, pct) {
  const f = filled != null ? filled : 0;
  const t = total != null ? total : 0;
  const p = pct != null ? pct : t > 0 ? Math.round((1000 * f) / t) / 10 : 0;
  return `${f}/${t} (${p}%)`;
}

/** Star marker for a key-date missing slot, else empty string. */
export function keyDateMarker(missingItem) {
  return missingItem && missingItem.key_date ? '\u2605' : '';
}

/** "1921-D \u2014 MS64" style label for a missing slot (note omitted when blank). */
export function missingSlotLabel(missingItem) {
  if (missingItem == null) return EM_DASH;
  const base = yearMint(missingItem.year, missingItem.mint);
  const note = missingItem.note ? ` ${missingItem.note}` : '';
  return `${base}${note}`;
}

export async function renderSets(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Sets';
  el.appendChild(heading);

  let sets;
  try {
    sets = await listSets();
    await cacheSnapshot('sets', sets);
  } catch (err) {
    if (isNetworkError(err)) {
      const snap = await readSnapshot('sets');
      if (snap && Array.isArray(snap.data)) {
        el.appendChild(offlineBanner(snap.cachedAt));
        sets = snap.data;
      } else {
        const errDiv = document.createElement('div');
        errDiv.className = 'empty-state';
        errDiv.textContent = err.message;
        el.appendChild(errDiv);
        toast(err.message, 'error');
        return;
      }
    } else {
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      el.appendChild(errDiv);
      toast(err.message, 'error');
      return;
    }
  }

  if (sets.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No sets loaded yet.';
    el.appendChild(empty);
    return;
  }

  const list = document.createElement('ul');
  list.className = 'set-list';

  for (const set of sets) {
    const li = document.createElement('li');
    li.className = 'set-list-item';
    li.style.cursor = 'pointer';
    li.addEventListener('click', () =>
      navigate('#/sets/' + encodeURIComponent(set.id))
    );

    const nameDiv = document.createElement('div');
    nameDiv.className = 'set-list-name';
    const link = document.createElement('a');
    link.href = '#/sets/' + encodeURIComponent(set.id);
    link.textContent = set.name;
    link.addEventListener('click', (e) => e.stopPropagation());
    nameDiv.appendChild(link);
    li.appendChild(nameDiv);

    const total = set.total;
    const filled = set.filled;
    const pct = total > 0 ? Math.round((100 * filled) / total) : 0;

    const bar = document.createElement('div');
    bar.className = 'completion-bar';
    const fill = document.createElement('div');
    fill.className = 'completion-bar-fill';
    fill.style.width = pct + '%';
    bar.appendChild(fill);
    li.appendChild(bar);

    const caption = document.createElement('div');
    caption.className = 'completion-caption';
    caption.textContent = formatCompletion(filled, total);
    li.appendChild(caption);

    list.appendChild(li);
  }

  el.appendChild(list);
}

export async function renderSetBoard(el, setId) {
  el.replaceChildren();

  const back = document.createElement('a');
  back.href = '#/sets';
  back.textContent = 'Back to sets';
  back.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/sets');
  });
  el.appendChild(back);

  const loading = document.createElement('p');
  loading.textContent = 'Loading\u2026';
  el.appendChild(loading);

  let board;
  let offlineCachedAt = null;
  try {
    board = await getSetBoard(setId);
    await cacheSnapshot('setboard:' + setId, board);
  } catch (err) {
    if (isNetworkError(err)) {
      const snap = await readSnapshot('setboard:' + setId);
      if (snap && snap.data) {
        board = snap.data;
        offlineCachedAt = snap.cachedAt;
      } else {
        el.replaceChildren();
        const backErr = document.createElement('a');
        backErr.href = '#/sets';
        backErr.textContent = 'Back to sets';
        backErr.addEventListener('click', (e) => {
          e.preventDefault();
          navigate('#/sets');
        });
        el.appendChild(backErr);
        const errDiv = document.createElement('div');
        errDiv.className = 'empty-state';
        errDiv.textContent = err.message;
        el.appendChild(errDiv);
        toast(err.message, 'error');
        return;
      }
    } else {
      el.replaceChildren();
      const backErr = document.createElement('a');
      backErr.href = '#/sets';
      backErr.textContent = 'Back to sets';
      backErr.addEventListener('click', (e) => {
        e.preventDefault();
        navigate('#/sets');
      });
      el.appendChild(backErr);
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      el.appendChild(errDiv);
      toast(err.message, 'error');
      return;
    }
  }

  el.replaceChildren();

  const backLink = document.createElement('a');
  backLink.href = '#/sets';
  backLink.textContent = 'Back to sets';
  backLink.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/sets');
  });
  el.appendChild(backLink);

  if (offlineCachedAt) {
    el.appendChild(offlineBanner(offlineCachedAt));
  }

  const title = document.createElement('h2');
  title.textContent = board.name;
  el.appendChild(title);

  const seriesP = document.createElement('p');
  seriesP.className = 'set-series';
  seriesP.textContent = display(board.series);
  el.appendChild(seriesP);

  const boardTotal = board.total;
  const boardFilled = board.filled;
  const boardPct =
    boardTotal > 0 ? Math.round((100 * boardFilled) / boardTotal) : 0;

  const boardBar = document.createElement('div');
  boardBar.className = 'completion-bar';
  const boardFill = document.createElement('div');
  boardFill.className = 'completion-bar-fill';
  boardFill.style.width = boardPct + '%';
  boardBar.appendChild(boardFill);
  el.appendChild(boardBar);

  const boardCaption = document.createElement('div');
  boardCaption.className = 'completion-caption';
  boardCaption.textContent = formatCompletion(boardFilled, boardTotal);
  el.appendChild(boardCaption);

  const needsActions = document.createElement('div');
  needsActions.className = 'settings-actions';

  const needsToggle = document.createElement('button');
  needsToggle.type = 'button';
  needsToggle.textContent = 'Needs';
  needsActions.appendChild(needsToggle);

  const wantlistBtn = document.createElement('button');
  wantlistBtn.type = 'button';
  wantlistBtn.textContent = 'Want list PDF';
  wantlistBtn.addEventListener('click', async () => {
    wantlistBtn.disabled = true;
    try {
      const blob = await getWantlistPdf(setId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `wantlist-${setId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Want list downloaded', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      wantlistBtn.disabled = false;
    }
  });
  needsActions.appendChild(wantlistBtn);
  el.appendChild(needsActions);

  const needsPanel = document.createElement('div');
  needsPanel.hidden = true;
  el.appendChild(needsPanel);

  needsToggle.addEventListener('click', async () => {
    if (!needsPanel.hidden) {
      needsPanel.hidden = true;
      return;
    }
    needsPanel.hidden = false;
    needsPanel.replaceChildren();
    const loadingP = document.createElement('p');
    loadingP.textContent = 'Loading needs…';
    needsPanel.appendChild(loadingP);
    try {
      const needs = await getSetNeeds(setId);
      needsPanel.replaceChildren();
      const summary = document.createElement('p');
      summary.className = 'muted';
      summary.textContent =
        `${formatCompletion(needs.filled, needs.total_slots, needs.completion_pct)} — ` +
        `${needs.key_dates_missing} key date${needs.key_dates_missing === 1 ? '' : 's'} missing`;
      needsPanel.appendChild(summary);

      if (!needs.missing.length) {
        const doneP = document.createElement('p');
        doneP.textContent = 'Nothing missing — set is complete.';
        needsPanel.appendChild(doneP);
      } else {
        const missingList = document.createElement('ul');
        missingList.className = 'count-list';
        for (const item of needs.missing) {
          const li = document.createElement('li');
          li.className = 'count-item';
          const label = document.createElement('div');
          const star = keyDateMarker(item);
          label.textContent = missingSlotLabel(item) + (star ? ' ' + star : '');
          li.appendChild(label);
          missingList.appendChild(li);
        }
        needsPanel.appendChild(missingList);
      }
    } catch (err) {
      needsPanel.replaceChildren();
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      needsPanel.appendChild(errDiv);
      toast(err.message, 'error');
    }
  });

  const grid = document.createElement('div');
  grid.className = 'album-grid';

  async function openAssignPicker(chip, slot) {
    const existing = chip.querySelector('.assign-picker');
    if (existing) {
      existing.remove();
      return;
    }

    const picker = document.createElement('div');
    picker.className = 'assign-picker';
    picker.textContent = 'Loading matches\u2026';
    chip.appendChild(picker);

    let matches;
    try {
      matches = await listCoins({
        series: board.series,
        year: slot.year,
        mintmark: slot.mint,
      });
    } catch (err) {
      toast(err.message, 'error');
      picker.remove();
      return;
    }

    picker.replaceChildren();

    if (!matches.length) {
      const emptyP = document.createElement('p');
      emptyP.textContent = 'No matching coins in inventory.';
      picker.appendChild(emptyP);
    } else {
      const assignList = document.createElement('ul');
      assignList.className = 'assign-list';

      for (const match of matches) {
        const item = document.createElement('li');
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent =
          match.accession_no + ' \u00b7 ' + display(match.grade_bucket);
        btn.addEventListener('click', async () => {
          if (!navigator.onLine) { toast('Assigning a coin requires a connection', 'error'); return; }
          try {
            await assignToSet(
              setId,
              { year: slot.year, mint: slot.mint, note: slot.note },
              match.accession_no
            );
            toast('Assigned', 'success');
            await renderSetBoard(el, setId);
          } catch (err) {
            toast(err.message, 'error');
          }
        });
        item.appendChild(btn);
        assignList.appendChild(item);
      }

      picker.appendChild(assignList);
    }

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => picker.remove());
    picker.appendChild(cancelBtn);
  }

  for (const slot of board.slots) {
    const filled = slot.accession != null;

    let chip;
    if (filled) {
      chip = document.createElement('a');
      chip.href = '#/coin/' + encodeURIComponent(slot.accession);
      chip.addEventListener('click', (e) => {
        e.preventDefault();
        navigate('#/coin/' + encodeURIComponent(slot.accession));
      });
    } else {
      chip = document.createElement('div');
    }

    chip.className =
      'slot-chip ' +
      (filled ? 'slot-chip--filled' : 'slot-chip--gap') +
      (slot.key_date ? ' slot-chip--key' : '');

    const yearMintEl = document.createElement('div');
    yearMintEl.className = 'slot-chip-yearmint';
    yearMintEl.textContent = yearMint(slot.year, slot.mint);
    chip.appendChild(yearMintEl);

    if (slot.key_date) {
      const keyMarker = document.createElement('span');
      keyMarker.className = 'slot-key-marker';
      keyMarker.textContent = '\u2605';
      keyMarker.title = 'Key date';
      chip.appendChild(keyMarker);
    }

    if (slot.note != null && slot.note !== '') {
      const noteBadge = document.createElement('span');
      noteBadge.className = 'slot-note-badge';
      noteBadge.textContent = slot.note;
      noteBadge.title = slot.note;
      chip.appendChild(noteBadge);
    }

    if (filled) {
      const meta = document.createElement('div');
      meta.className = 'slot-chip-meta';
      meta.textContent =
        display(slot.accession) + ' \u00b7 ' + display(slot.grade_bucket);
      chip.appendChild(meta);
    } else {
      const assignBtn = document.createElement('button');
      assignBtn.type = 'button';
      assignBtn.className = 'slot-assign-btn';
      assignBtn.textContent = 'Assign coin';
      assignBtn.addEventListener('click', () => openAssignPicker(chip, slot));
      chip.appendChild(assignBtn);
    }

    grid.appendChild(chip);
  }

  el.appendChild(grid);
}
