import { listSets, getSetBoard, listCoins, assignToSet } from '../api.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';

const EM_DASH = '\u2014';

function display(value) {
  if (value == null || value === '') return EM_DASH;
  return String(value);
}

function yearMint(year, mint) {
  return String(year) + '-' + String(mint);
}

export async function renderSets(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Sets';
  el.appendChild(heading);

  let sets;
  try {
    sets = await listSets();
  } catch (err) {
    const errDiv = document.createElement('div');
    errDiv.className = 'empty-state';
    errDiv.textContent = err.message;
    el.appendChild(errDiv);
    toast(err.message, 'error');
    return;
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
    caption.textContent = filled + ' / ' + total + ' slots';
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
  try {
    board = await getSetBoard(setId);
  } catch (err) {
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

  el.replaceChildren();

  const backLink = document.createElement('a');
  backLink.href = '#/sets';
  backLink.textContent = 'Back to sets';
  backLink.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/sets');
  });
  el.appendChild(backLink);

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
  boardCaption.textContent = boardFilled + ' / ' + boardTotal + ' slots';
  el.appendChild(boardCaption);

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
