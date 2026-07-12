import { locationTree, getLocation, createLocation } from '../api.js';
import { toast } from '../app.js';
import { navigate } from '../router.js';
import { cacheSnapshot, readSnapshot, offlineBanner, isNetworkError } from '../offline.js';

const LOCATION_KINDS = ['cabinet', 'box', 'tray', 'slot', 'album', 'page', 'row', 'pocket'];

const EM_DASH = '\u2014';

function appendField(form, labelText, control) {
  const label = document.createElement('label');
  label.textContent = labelText;
  form.appendChild(label);
  form.appendChild(control);
}

export async function renderLocations(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Locations';
  el.appendChild(heading);

  const treeEl = document.createElement('div');
  const detailEl = document.createElement('div');
  el.appendChild(treeEl);
  el.appendChild(detailEl);

  async function reload() {
    let data;
    try {
      data = await locationTree();
      await cacheSnapshot('locations:tree', data);
    } catch (err) {
      if (isNetworkError(err)) {
        const snap = await readSnapshot('locations:tree');
        if (snap && snap.data && Array.isArray(snap.data.tree)) {
          treeEl.replaceChildren();
          treeEl.appendChild(offlineBanner(snap.cachedAt));
          const nodes = snap.data.tree;
          if (nodes.length) {
            treeEl.appendChild(buildTreeList(nodes));
          } else {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'No cached locations.';
            treeEl.appendChild(empty);
          }
          detailEl.replaceChildren();
          return;
        }
      }
      treeEl.replaceChildren();
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      treeEl.appendChild(errDiv);
      toast(err.message, 'error');
      return;
    }

    const nodes = data.tree || [];

    if (nodes.length === 0) {
      treeEl.replaceChildren();
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent =
        'No locations yet. Create your first cabinet or box to start organizing.';
      treeEl.appendChild(empty);
      treeEl.appendChild(makeCreateForm(null));
      detailEl.replaceChildren();
      return;
    }

    treeEl.replaceChildren();
    treeEl.appendChild(buildTreeList(nodes));
    treeEl.appendChild(makeCreateForm(null));
  }

  function buildTreeList(nodes) {
    const ul = document.createElement('ul');
    ul.style.cssText =
      'list-style:none;padding-left:var(--space-md);margin:0;';

    for (const node of nodes) {
      const li = document.createElement('li');

      const badge = document.createElement('span');
      badge.textContent = node.kind;
      badge.style.cssText =
        'display:inline-block;padding:var(--space-xs) var(--space-sm);margin-right:var(--space-sm);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-sm);font-size:var(--font-size-sm);color:var(--color-text-muted);';
      li.appendChild(badge);

      const labelBtn = document.createElement('button');
      labelBtn.type = 'button';
      labelBtn.textContent = node.label;
      labelBtn.style.cssText =
        'background:transparent;border:none;color:var(--color-accent);cursor:pointer;padding:0;font-size:var(--font-size-base);';
      labelBtn.addEventListener('click', () => selectNode(node));
      li.appendChild(labelBtn);

      if (node.children?.length) {
        li.appendChild(buildTreeList(node.children));
      }

      ul.appendChild(li);
    }

    return ul;
  }

  async function selectNode(node) {
    detailEl.replaceChildren();

    const loading = document.createElement('p');
    loading.textContent = 'Loading\u2026';
    detailEl.appendChild(loading);

    let direct;
    let recursive;
    try {
      [direct, recursive] = await Promise.all([
        getLocation(node.id, false),
        getLocation(node.id, true),
      ]);
    } catch (err) {
      detailEl.replaceChildren();
      const errDiv = document.createElement('div');
      errDiv.className = 'empty-state';
      errDiv.textContent = err.message;
      detailEl.appendChild(errDiv);
      toast(err.message, 'error');
      return;
    }

    detailEl.replaceChildren();

    const breadcrumb = document.createElement('div');
    breadcrumb.style.cssText =
      'font-weight:600;font-size:var(--font-size-lg);margin-bottom:var(--space-md);';
    breadcrumb.textContent = direct.path || EM_DASH;
    detailEl.appendChild(breadcrumb);

    const directCoins = direct.contents || [];
    const totalCoins = (recursive.contents || []).length;
    const descendants = totalCoins - directCoins.length;

    const summary = document.createElement('p');
    summary.textContent =
      directCoins.length +
      ' coin(s) here, ' +
      descendants +
      ' in sub-locations';
    detailEl.appendChild(summary);

    if (directCoins.length) {
      const coinList = document.createElement('ul');
      for (const c of directCoins) {
        const item = document.createElement('li');
        const link = document.createElement('a');
        const accession = c.accession_no;
        link.href = '#/coin/' + encodeURIComponent(accession);
        link.textContent = accession + ' \u2014 ' + (c.series || EM_DASH);
        link.addEventListener('click', (e) => {
          e.preventDefault();
          navigate('#/coin/' + encodeURIComponent(accession));
        });
        item.appendChild(link);
        coinList.appendChild(item);
      }
      detailEl.appendChild(coinList);
    }

    const countBtn = document.createElement('button');
    countBtn.type = 'button';
    countBtn.textContent = 'Count this box';
    countBtn.addEventListener('click', () => navigate('#/count/' + encodeURIComponent(node.id)));
    detailEl.appendChild(countBtn);

    detailEl.appendChild(makeCreateForm(node.id));
  }

  function makeCreateForm(parentId) {
    const form = document.createElement('form');
    form.className = 'settings-form';
    form.addEventListener('submit', (e) => e.preventDefault());

    const title = document.createElement('h3');
    title.textContent =
      parentId == null ? 'Add top-level location' : 'Add child location';
    form.appendChild(title);

    const kindSelect = document.createElement('select');
    for (const kind of LOCATION_KINDS) {
      const opt = document.createElement('option');
      opt.value = kind;
      opt.textContent = kind;
      kindSelect.appendChild(opt);
    }
    appendField(form, 'Kind', kindSelect);

    const labelInput = document.createElement('input');
    labelInput.type = 'text';
    labelInput.placeholder = 'Label, e.g. B2';
    appendField(form, 'Label', labelInput);

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.textContent = 'Add location';
    addBtn.addEventListener('click', async () => {
      const kind = kindSelect.value;
      const label = labelInput.value.trim();
      if (!label) {
        toast('Enter a label', 'error');
        return;
      }

      addBtn.disabled = true;
      try {
        await createLocation(kind, label, parentId);
        toast('Location created', 'success');
        await reload();
      } catch (err) {
        toast(err.message, 'error');
        addBtn.disabled = false;
      }
    });
    form.appendChild(addBtn);

    return form;
  }

  await reload();
}
