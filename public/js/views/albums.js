import {
  listAlbumImports,
  getAlbumImport,
  createAlbumImport,
  discardAlbumImport,
  uploadAlbumPages,
  fetchAlbumPageImage,
  patchAlbumSlot,
  commitAlbumImport,
  getWantlistPdf,
} from '../api.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';

const EM_DASH = '—';

// ---------------------------------------------------------------------------
// Pure helpers (exported for testing). These operate on plain data only.
// ---------------------------------------------------------------------------

/** CSS class for a slot chip given its fill_state ('filled'|'empty'|'uncertain'). */
export function slotChipClass(fillState) {
  if (fillState === 'filled') return 'slot-chip--filled';
  if (fillState === 'uncertain') return 'slot-chip--uncertain';
  return 'slot-chip--gap';
}

/** Cycles a slot's fill_state on tap: filled -> empty -> uncertain -> filled. */
export function nextFillState(fillState) {
  if (fillState === 'filled') return 'empty';
  if (fillState === 'empty') return 'uncertain';
  return 'filled';
}

/** "1914-D" / "1914" style label for a slot's year+mint. Mirrors set-board's yearMint. */
export function slotLabel(slot) {
  if (slot == null || slot.year == null) return (slot && slot.label_text) || EM_DASH;
  const mint = slot.mint ? '-' + String(slot.mint) : '';
  return String(slot.year) + mint;
}

/** Formats a 0..1 fraction as a whole-number percent string, e.g. 0.8234 -> "82%". */
export function formatPercent(fraction) {
  if (fraction == null || Number.isNaN(fraction)) return EM_DASH;
  return Math.round(fraction * 100) + '%';
}

/** "Analyzed" / "Pending analysis" badge text for a page. */
export function pageAnalysisLabel(page) {
  return page && page.analyzed_at != null ? 'Analyzed' : 'Pending analysis';
}

// ---------------------------------------------------------------------------
// DOM building
// ---------------------------------------------------------------------------

function display(value) {
  if (value == null || value === '') return EM_DASH;
  return String(value);
}

export async function renderAlbums(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Album imports';
  el.appendChild(heading);

  const intro = document.createElement('p');
  intro.className = 'muted';
  intro.textContent =
    'Photograph coin album/folder pages, review the parsed slots, then commit into a real set.';
  el.appendChild(intro);

  const newForm = document.createElement('div');
  newForm.className = 'settings-actions';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.placeholder = 'Import name (optional)';
  nameInput.style.flex = '1 1 12rem';
  newForm.appendChild(nameInput);
  const newBtn = document.createElement('button');
  newBtn.type = 'button';
  newBtn.textContent = 'New import';
  newBtn.addEventListener('click', async () => {
    newBtn.disabled = true;
    try {
      const created = await createAlbumImport(nameInput.value.trim() || undefined);
      navigate('#/album/' + encodeURIComponent(created.import_id));
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      newBtn.disabled = false;
    }
  });
  newForm.appendChild(newBtn);
  el.appendChild(newForm);

  const listSection = document.createElement('div');
  listSection.style.marginTop = 'var(--space-lg)';
  el.appendChild(listSection);

  let imports;
  try {
    imports = await listAlbumImports();
  } catch (err) {
    const errDiv = document.createElement('div');
    errDiv.className = 'empty-state';
    errDiv.textContent = err.message;
    listSection.appendChild(errDiv);
    toast(err.message, 'error');
    return;
  }

  if (!imports.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No album imports yet.';
    listSection.appendChild(empty);
    return;
  }

  const list = document.createElement('ul');
  list.className = 'set-list';
  for (const imp of imports) {
    const li = document.createElement('li');
    li.className = 'set-list-item';
    li.style.cursor = 'pointer';
    li.addEventListener('click', () => navigate('#/album/' + encodeURIComponent(imp.id)));

    const nameDiv = document.createElement('div');
    nameDiv.className = 'set-list-name';
    const link = document.createElement('a');
    link.href = '#/album/' + encodeURIComponent(imp.id);
    link.textContent = display(imp.name) === EM_DASH ? `Import #${imp.id}` : imp.name;
    link.addEventListener('click', (e) => e.stopPropagation());
    nameDiv.appendChild(link);
    li.appendChild(nameDiv);

    const caption = document.createElement('div');
    caption.className = 'completion-caption';
    caption.textContent = `${display(imp.status)} · ${display(imp.page_count)} page${imp.page_count === 1 ? '' : 's'} · ${display(imp.created_at)}`;
    li.appendChild(caption);

    list.appendChild(li);
  }
  listSection.appendChild(list);
}

async function buildPageThumb(importId, page) {
  const wrap = document.createElement('div');
  wrap.style.cssText =
    'display:flex;flex-direction:column;gap:var(--space-xs);padding:var(--space-sm);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);';

  const img = document.createElement('img');
  img.style.cssText = 'max-height:140px;width:auto;border-radius:var(--radius-sm);object-fit:contain;background:var(--color-bg);';
  img.alt = page.page_title || `Page ${page.seq}`;
  wrap.appendChild(img);
  try {
    const blob = await fetchAlbumPageImage(importId, page.page_id);
    img.src = URL.createObjectURL(blob);
  } catch {
    /* leave broken image */
  }

  const title = document.createElement('div');
  title.textContent = display(page.page_title);
  wrap.appendChild(title);

  const badge = document.createElement('div');
  badge.className = 'muted';
  badge.style.fontSize = 'var(--font-size-sm)';
  badge.textContent = pageAnalysisLabel(page);
  wrap.appendChild(badge);

  return wrap;
}

function buildSlotChip(importId, slot, onChanged) {
  const chip = document.createElement('button');
  chip.type = 'button';
  chip.className = 'slot-chip ' + slotChipClass(slot.fill_state);

  const label = document.createElement('div');
  label.className = 'slot-chip-yearmint';
  label.textContent = slotLabel(slot);
  chip.appendChild(label);

  const meta = document.createElement('div');
  meta.className = 'slot-chip-meta';
  meta.textContent = slot.fill_state;
  chip.appendChild(meta);

  chip.addEventListener('click', async () => {
    const next = nextFillState(slot.fill_state);
    chip.disabled = true;
    try {
      await patchAlbumSlot(importId, slot.slot_id, next);
      if (typeof onChanged === 'function') await onChanged();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      chip.disabled = false;
    }
  });

  return chip;
}

export async function renderAlbumDetail(el, importId) {
  el.replaceChildren();

  const back = document.createElement('a');
  back.href = '#/albums';
  back.textContent = 'Back to album imports';
  back.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/albums');
  });
  el.appendChild(back);

  const loading = document.createElement('p');
  loading.textContent = 'Loading…';
  el.appendChild(loading);

  let imp;
  try {
    imp = await getAlbumImport(importId);
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
  title.textContent = imp.name || `Import #${imp.id}`;
  el.appendChild(title);

  const statusP = document.createElement('p');
  statusP.className = 'muted';
  statusP.textContent = `Status: ${display(imp.status)}`;
  el.appendChild(statusP);

  const isTerminal = imp.status === 'committed' || imp.status === 'discarded';

  if (imp.status === 'committed' && imp.set_id != null) {
    const summaryDiv = document.createElement('div');
    summaryDiv.className = 'empty-state';
    summaryDiv.style.textAlign = 'left';
    const p = document.createElement('p');
    p.textContent = 'This import has been committed.';
    summaryDiv.appendChild(p);
    const setLink = document.createElement('a');
    setLink.href = '#/sets/' + encodeURIComponent(imp.set_id);
    setLink.textContent = 'View set';
    setLink.className = 'btn';
    setLink.addEventListener('click', (e) => {
      e.preventDefault();
      navigate('#/sets/' + encodeURIComponent(imp.set_id));
    });
    summaryDiv.appendChild(setLink);
    el.appendChild(summaryDiv);
    return;
  }

  if (imp.status === 'discarded') {
    const discardedDiv = document.createElement('div');
    discardedDiv.className = 'empty-state';
    discardedDiv.textContent = 'This import was discarded.';
    el.appendChild(discardedDiv);
    return;
  }

  // --- Upload pages ----------------------------------------------------------
  if (!isTerminal) {
    const uploadHeading = document.createElement('h3');
    uploadHeading.textContent = 'Upload pages';
    el.appendChild(uploadHeading);

    const uploadInput = document.createElement('input');
    uploadInput.type = 'file';
    uploadInput.accept = 'image/*';
    uploadInput.capture = 'environment';
    uploadInput.multiple = true;
    el.appendChild(uploadInput);

    const uploadStatus = document.createElement('p');
    uploadStatus.className = 'muted';
    el.appendChild(uploadStatus);

    uploadInput.addEventListener('change', async () => {
      const files = Array.from(uploadInput.files || []);
      if (!files.length) return;
      uploadStatus.textContent = 'Uploading…';
      try {
        const result = await uploadAlbumPages(importId, files);
        const added = result.added ? result.added.length : 0;
        const dupes = result.duplicates ? result.duplicates.length : 0;
        uploadStatus.textContent =
          `Uploaded ${added} page${added === 1 ? '' : 's'}` +
          (dupes ? ` — ${dupes} duplicate${dupes === 1 ? '' : 's'} skipped` : '');
        toast('Pages uploaded', 'success');
        await renderAlbumDetail(el, importId);
      } catch (err) {
        uploadStatus.textContent = '';
        toast(err.message, 'error');
      }
    });
  }

  // --- Pages list --------------------------------------------------------
  const pages = Array.isArray(imp.pages) ? imp.pages : [];
  if (pages.length) {
    const pagesHeading = document.createElement('h3');
    pagesHeading.textContent = 'Pages';
    el.appendChild(pagesHeading);

    const anyPending = pages.some((p) => p.analyzed_at == null);
    if (anyPending) {
      const hint = document.createElement('p');
      hint.className = 'muted';
      hint.textContent =
        `Some pages are still pending analysis — run: python -m numislens_vision.albums ${importId}`;
      el.appendChild(hint);
    }

    const grid = document.createElement('div');
    grid.style.cssText =
      'display:grid;grid-template-columns:repeat(auto-fill,minmax(9rem,1fr));gap:var(--space-sm);margin-bottom:var(--space-lg);';
    el.appendChild(grid);
    for (const page of pages) {
      grid.appendChild(await buildPageThumb(importId, page));
    }
  }

  // --- Merged slots (read-only summary) -----------------------------------
  const merged = Array.isArray(imp.merged_slots) ? imp.merged_slots : [];
  if (merged.length) {
    const mergedHeading = document.createElement('h3');
    mergedHeading.textContent = 'Merged slots (read-only summary)';
    el.appendChild(mergedHeading);

    const mergedGrid = document.createElement('div');
    mergedGrid.className = 'album-grid';
    for (const slot of merged) {
      const chip = document.createElement('div');
      chip.className = 'slot-chip ' + slotChipClass(slot.fill_state);
      const label = document.createElement('div');
      label.className = 'slot-chip-yearmint';
      label.textContent = slotLabel(slot);
      chip.appendChild(label);
      const meta = document.createElement('div');
      meta.className = 'slot-chip-meta';
      meta.textContent = slot.fill_state;
      chip.appendChild(meta);
      mergedGrid.appendChild(chip);
    }
    el.appendChild(mergedGrid);
  }

  // --- Per-page slots (interactive; PATCH needs slot_id) ------------------
  if (!isTerminal && pages.some((p) => Array.isArray(p.slots) && p.slots.length)) {
    const reviewHeading = document.createElement('h3');
    reviewHeading.textContent = 'Review slots (tap to cycle filled → empty → uncertain)';
    el.appendChild(reviewHeading);

    for (const page of pages) {
      if (!Array.isArray(page.slots) || !page.slots.length) continue;
      const pageSection = document.createElement('div');
      pageSection.style.marginBottom = 'var(--space-md)';
      const pageLabel = document.createElement('div');
      pageLabel.className = 'muted';
      pageLabel.textContent = page.page_title || `Page ${page.seq}`;
      pageSection.appendChild(pageLabel);

      const pageGrid = document.createElement('div');
      pageGrid.className = 'album-grid';
      for (const slot of page.slots) {
        pageGrid.appendChild(
          buildSlotChip(importId, slot, () => renderAlbumDetail(el, importId)),
        );
      }
      pageSection.appendChild(pageGrid);
      el.appendChild(pageSection);
    }
  }

  // --- Match candidates ----------------------------------------------------
  const candidates = Array.isArray(imp.match_candidates) ? imp.match_candidates : [];
  const candidatesHeading = document.createElement('h3');
  candidatesHeading.textContent = 'Match to a set';
  el.appendChild(candidatesHeading);

  const candidateForm = document.createElement('div');
  candidateForm.style.cssText = 'display:flex;flex-direction:column;gap:var(--space-sm);margin-bottom:var(--space-md);';

  const radioName = 'match-candidate-' + importId;
  let customRadio = null;
  const customNameInput = document.createElement('input');
  customNameInput.type = 'text';
  customNameInput.placeholder = 'Custom set name';
  customNameInput.style.display = 'none';

  if (candidates.length) {
    for (const cand of candidates) {
      const row = document.createElement('label');
      row.style.cssText = 'display:flex;align-items:center;gap:var(--space-sm);font-weight:normal;';
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = radioName;
      radio.value = cand.manifest_id;
      row.appendChild(radio);
      const text = document.createElement('span');
      text.textContent = `${cand.name} — score ${formatPercent(cand.score)}, coverage ${formatPercent(cand.coverage)}`;
      row.appendChild(text);
      candidateForm.appendChild(row);
    }
  } else {
    const noneP = document.createElement('p');
    noneP.className = 'muted';
    noneP.textContent = 'No matching set manifests found — use a custom name.';
    candidateForm.appendChild(noneP);
  }

  const customRow = document.createElement('label');
  customRow.style.cssText = 'display:flex;align-items:center;gap:var(--space-sm);font-weight:normal;';
  customRadio = document.createElement('input');
  customRadio.type = 'radio';
  customRadio.name = radioName;
  customRadio.value = '__custom__';
  if (!candidates.length) customRadio.checked = true;
  customRow.appendChild(customRadio);
  const customLabelText = document.createElement('span');
  customLabelText.textContent = 'Custom set name:';
  customRow.appendChild(customLabelText);
  candidateForm.appendChild(customRow);
  candidateForm.appendChild(customNameInput);

  function syncCustomInput() {
    customNameInput.style.display = customRadio.checked ? '' : 'none';
  }
  candidateForm.addEventListener('change', syncCustomInput);
  syncCustomInput();

  el.appendChild(candidateForm);

  // --- Commit controls -------------------------------------------------------
  if (!isTerminal) {
    const commitHeading = document.createElement('h3');
    commitHeading.textContent = 'Commit';
    el.appendChild(commitHeading);

    const commitForm = document.createElement('div');
    commitForm.className = 'settings-form';

    const createCoinsLabel = document.createElement('label');
    createCoinsLabel.style.cssText = 'display:flex;align-items:center;gap:var(--space-sm);font-weight:normal;';
    const createCoinsCheckbox = document.createElement('input');
    createCoinsCheckbox.type = 'checkbox';
    createCoinsCheckbox.checked = true;
    createCoinsLabel.appendChild(createCoinsCheckbox);
    createCoinsLabel.appendChild(document.createTextNode('Create coins for filled slots'));
    commitForm.appendChild(createCoinsLabel);

    const locationLabelInput = document.createElement('input');
    locationLabelInput.type = 'text';
    locationLabelInput.placeholder = 'Location label (optional)';
    const locLabelWrap = document.createElement('label');
    locLabelWrap.textContent = 'Location label';
    commitForm.appendChild(locLabelWrap);
    commitForm.appendChild(locationLabelInput);

    const uncertainSelect = document.createElement('select');
    for (const [value, text] of [
      ['block', 'Block commit if any slot is uncertain'],
      ['empty', 'Treat uncertain slots as empty'],
    ]) {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = text;
      uncertainSelect.appendChild(opt);
    }
    const uncertainWrap = document.createElement('label');
    uncertainWrap.textContent = 'Uncertain slot policy';
    commitForm.appendChild(uncertainWrap);
    commitForm.appendChild(uncertainSelect);

    const commitError = document.createElement('div');
    commitError.className = 'melt-error-banner';
    commitError.style.display = 'none';
    commitForm.appendChild(commitError);

    const commitActions = document.createElement('div');
    commitActions.className = 'settings-actions';
    const commitBtn = document.createElement('button');
    commitBtn.type = 'button';
    commitBtn.textContent = 'Commit import';
    commitActions.appendChild(commitBtn);
    commitForm.appendChild(commitActions);

    const commitResult = document.createElement('div');
    commitForm.appendChild(commitResult);

    commitBtn.addEventListener('click', async () => {
      const selected = candidateForm.querySelector(`input[name="${radioName}"]:checked`);
      const body = {
        create_coins: createCoinsCheckbox.checked,
        uncertain_policy: uncertainSelect.value,
      };
      if (locationLabelInput.value.trim()) body.location_label = locationLabelInput.value.trim();

      if (!selected || selected.value === '__custom__') {
        const customName = customNameInput.value.trim();
        if (!customName) {
          toast('Pick a matching set or enter a custom set name', 'error');
          return;
        }
        body.custom_name = customName;
      } else {
        body.manifest_id = selected.value;
      }

      commitError.style.display = 'none';
      commitBtn.disabled = true;
      try {
        const result = await commitAlbumImport(importId, body);
        commitResult.replaceChildren();
        const summary = document.createElement('div');
        summary.className = 'empty-state';
        summary.style.textAlign = 'left';
        summary.appendChild(
          Object.assign(document.createElement('p'), {
            textContent: `Committed: ${result.filled}/${result.total_slots} slots filled, ${result.coins_created.length} coin(s) created.`,
          }),
        );
        const setLink = document.createElement('a');
        setLink.href = '#/sets/' + encodeURIComponent(result.set_id);
        setLink.className = 'btn';
        setLink.textContent = 'View set';
        setLink.addEventListener('click', (e) => {
          e.preventDefault();
          navigate('#/sets/' + encodeURIComponent(result.set_id));
        });
        summary.appendChild(setLink);

        const wantBtn = document.createElement('button');
        wantBtn.type = 'button';
        wantBtn.textContent = 'Want list PDF';
        wantBtn.style.marginLeft = 'var(--space-sm)';
        wantBtn.addEventListener('click', async () => {
          try {
            const blob = await getWantlistPdf(result.set_id);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `wantlist-${result.set_key}.pdf`;
            a.click();
            URL.revokeObjectURL(url);
          } catch (err) {
            toast(err.message, 'error');
          }
        });
        summary.appendChild(wantBtn);

        commitResult.appendChild(summary);
        toast('Import committed', 'success');
      } catch (err) {
        if (err.status === 409) {
          commitError.textContent = err.message;
          commitError.style.display = 'block';
        } else {
          toast(err.message, 'error');
        }
      } finally {
        commitBtn.disabled = false;
      }
    });

    el.appendChild(commitForm);

    const discardBtn = document.createElement('button');
    discardBtn.type = 'button';
    discardBtn.textContent = 'Discard import';
    discardBtn.style.marginTop = 'var(--space-md)';
    discardBtn.addEventListener('click', async () => {
      if (!window.confirm('Discard this import? This cannot be undone.')) return;
      try {
        await discardAlbumImport(importId);
        toast('Import discarded', 'info');
        navigate('#/albums');
      } catch (err) {
        toast(err.message, 'error');
      }
    });
    el.appendChild(discardBtn);
  }
}
