export function flattenLocationTree(nodes, parentPath = '') {
  const map = new Map();
  for (const node of nodes) {
    const path = parentPath ? parentPath + ' > ' + node.label : node.label;
    map.set(node.id, path);
    if (node.children?.length) {
      for (const [id, childPath] of flattenLocationTree(node.children, path)) {
        map.set(id, childPath);
      }
    }
  }
  return map;
}

export function populateLocationSelect(select, locationPaths, opts = {}) {
  const { blank, selectedId } = opts;
  select.replaceChildren();
  if (blank) {
    const o = document.createElement('option');
    o.value = blank.value ?? '';
    o.textContent = blank.label;
    select.appendChild(o);
  }
  const entries = [...locationPaths.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  for (const [id, path] of entries) {
    const opt = document.createElement('option');
    opt.value = String(id);
    opt.textContent = path;
    if (selectedId != null && id === selectedId) opt.selected = true;
    select.appendChild(opt);
  }
}
