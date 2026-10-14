/* ⌘K function reference palette. Pure ranking helpers are exported for tests;
   the browser mount renders an overlay over the notebook. */
(function (root) {
  'use strict';

  function rank(entry, query) {
    const name = entry.name.toLowerCase();
    if (name === query) return 0;
    if (name.startsWith(query)) return 1;
    if (name.includes(query)) return 2;
    if ((entry.summary || '').toLowerCase().includes(query)) return 3;
    return -1;
  }

  function filterFunctions(index, query, limit = 60) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return index.slice(0, limit);
    return index
      .map((entry) => [rank(entry, q), entry])
      .filter(([score]) => score >= 0)
      .sort(([a, x], [b, y]) => a - b || x.name.localeCompare(y.name))
      .slice(0, limit)
      .map(([, entry]) => entry);
  }

  function insertionFor(entry) {
    const signature = entry.signatures && entry.signatures[0];
    if (signature) {
      // Signatures with placeholder args ("Integrate[f, x]") insert as-is for
      // the user to fill in; doctest examples are concrete expressions.
      return signature;
    }
    return `${entry.name}[`;
  }

  function mount(options) {
    const onInsert = options.onInsert;
    const overlay = document.createElement('div');
    overlay.className = 'palette-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="palette" role="dialog" aria-label="函数参考">
        <div class="palette-search">
          <input type="text" placeholder="搜索函数，例如 laplace、graph、solve…" aria-label="搜索函数" spellcheck="false">
          <kbd>esc</kbd>
        </div>
        <div class="palette-body">
          <div class="palette-list" role="listbox"></div>
          <div class="palette-detail"></div>
        </div>
        <div class="palette-footer"><span><kbd>↑</kbd><kbd>↓</kbd> 选择</span><span><kbd>⏎</kbd> 插入到笔记本</span><span class="palette-count"></span></div>
      </div>`;
    document.body.append(overlay);
    const input = overlay.querySelector('input');
    const list = overlay.querySelector('.palette-list');
    const detail = overlay.querySelector('.palette-detail');
    const count = overlay.querySelector('.palette-count');
    let results = [];
    let selected = 0;

    function renderDetail(entry) {
      if (!entry) { detail.replaceChildren(); return; }
      const title = document.createElement('div'); title.className = 'palette-detail-name';
      const strong = document.createElement('strong'); strong.textContent = entry.name;
      const category = document.createElement('span'); category.className = 'palette-category'; category.textContent = entry.category || '';
      title.append(strong, category);
      const summary = document.createElement('p'); summary.className = 'palette-summary'; summary.textContent = entry.summary || '（暂无说明）';
      detail.replaceChildren(title, summary);
      (entry.signatures || []).forEach((signature) => {
        const code = document.createElement('code'); code.className = 'palette-signature'; code.textContent = signature; detail.append(code);
      });
    }

    function render() {
      list.replaceChildren(...results.map((entry, index) => {
        const item = document.createElement('div');
        item.className = `palette-item${index === selected ? ' selected' : ''}`;
        item.setAttribute('role', 'option');
        const name = document.createElement('strong'); name.textContent = entry.name;
        const summary = document.createElement('small'); summary.textContent = entry.summary || '';
        item.append(name, summary);
        item.addEventListener('click', () => { insert(entry); });
        item.addEventListener('mousemove', () => { if (selected !== index) { selected = index; render(); } });
        return item;
      }));
      count.textContent = `${results.length} 个函数`;
      renderDetail(results[selected]);
      list.querySelector('.selected')?.scrollIntoView({ block: 'nearest' });
    }

    function search() {
      results = filterFunctions(root.FUNCTION_INDEX || [], input.value);
      selected = 0;
      render();
    }

    function insert(entry) {
      if (!entry) return;
      close();
      onInsert(insertionFor(entry));
    }

    function open() {
      overlay.hidden = false;
      input.value = '';
      search();
      input.focus();
    }
    function close() { overlay.hidden = true; }

    input.addEventListener('input', search);
    input.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown') { event.preventDefault(); if (results.length) { selected = (selected + 1) % results.length; render(); } }
      else if (event.key === 'ArrowUp') { event.preventDefault(); if (results.length) { selected = (selected - 1 + results.length) % results.length; render(); } }
      else if (event.key === 'Enter') { event.preventDefault(); insert(results[selected]); }
      else if (event.key === 'Escape') { event.preventDefault(); close(); }
    });
    overlay.addEventListener('click', (event) => { if (event.target === overlay) close(); });
    return { open, close, get visible() { return !overlay.hidden; } };
  }

  const api = { filterFunctions, insertionFor, mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NotebookPalette = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
