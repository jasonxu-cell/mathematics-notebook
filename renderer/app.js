/* Independent notebook UI. All computation and file access cross the preload API. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const api = window.notebook;
  const uid = () => globalThis.crypto?.randomUUID?.() || `cell-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const examples = [
    ['ƒ', '因式分解', 'Factor[x^4 - 1]'],
    ['=', '求解方程', 'Solve[x^2 - 5 x + 6 == 0, x]'],
    ['∂', '符号求导', 'D[Sin[x^2], x]'],
    ['∫', '定积分', 'Integrate[Exp[-x^2], {x, -Infinity, Infinity}]'],
    ['∿', '绘制函数', 'Plot[Sin[x], {x, -2 Pi, 2 Pi}]']
  ];
  const advancedExamples = [
    ['▦', '矩阵与特征值', 'Eigenvalues[{{2, 1}, {1, 2}}]'],
    ['∂', '微分方程', 'DSolve[y\'[x] == y[x], y[x], x]'],
    ['μ', '描述统计', '{Mean[{1, 2, 3, 4, 5}], StandardDeviation[{1, 2, 3, 4, 5}]}'],
    ['◇', '三维曲面', 'Plot3D[Sin[x y], {x, -3, 3}, {y, -3, 3}]'],
    ['↔', '交互式函数', 'Manipulate[Plot[Sin[a x], {x, -Pi, Pi}], {{a, 1, "频率"}, 0.5, 3, 0.1}]'],
    ['◈', '交互式三维', 'Manipulate[Plot3D[Sin[a x y], {x, -2, 2}, {y, -2, 2}], {a, 0.5, 3}]']
  ];
  const makeCell = (type = 'input', source = '') => ({ id: uid(), type, source });
  const makeDocument = (demo = false) => ({
    format: 'mathematics-notebook', version: 1, id: uid(), title: demo ? '数学入门' : '未命名笔记本',
    cells: demo ? [makeCell('heading', '从好奇开始，探索数学'), makeCell('text', '写下表达式，按 Shift + Enter 运行。这里有五个小例子：从因式分解，到函数的可视化。'), ...examples.map(([, , source]) => makeCell('input', source))] : [makeCell('text', '在这里记录思路，或从下面的计算单元开始。'), makeCell()],
    updatedAt: new Date().toISOString()
  });
  const state = { document: makeDocument(true), path: null, dirty: false, busy: false, dynamic: false, activeId: null, queue: new Set(), runningId: null, stopped: false, canceling: false, health: null, stale: new Set(), fileBusy: false };
  const viewers = new Map(), viewStates = new Map();
  let draftTimer, toastTimer, statusInFlight = false, menuUnsubscribe, closeUnsubscribe, closing = false;
  let draftSaveChain = Promise.resolve(true);
  const errorMessage = (error) => String(error?.message || error).replace(/^Error invoking remote method '[^']+':\s*(?:Error:\s*)?/, '');

  function toast(message, error = false) {
    clearTimeout(toastTimer);
    $('toast').textContent = errorMessage(message);
    $('toast').classList.toggle('error', error);
    $('toast').hidden = false;
    toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 6500 : 3300);
  }
  function ensureApi() {
    if (!api) throw new Error('桌面桥接未连接。请使用 Electron 启动此应用。');
    return api;
  }
  function touch() {
    state.dirty = true;
    state.document.updatedAt = new Date().toISOString();
    updateHeader();
    clearTimeout(draftTimer);
    draftTimer = setTimeout(saveDraft, 450);
  }
  async function saveDraft() {
    if (!api?.storage) return false;
    let snapshot;
    try { snapshot = structuredClone(state.document); }
    catch (error) { $('file-status').textContent = `草稿保存失败：${errorMessage(error)}`; return false; }
    const operation = draftSaveChain.then(async () => {
      try { await api.storage.saveDraft(snapshot); return true; }
      catch (error) { $('file-status').textContent = `草稿保存失败：${errorMessage(error)}`; return false; }
    });
    draftSaveChain = operation;
    return operation;
  }
  async function closeRequested() {
    if (closing) return;
    closing = true;
    clearTimeout(draftTimer);
    dynamicCoordinator.clear();
    const saved = await saveDraft();
    try {
      if (!saved) toast('草稿保存失败，窗口仍保持打开。请稍后重试关闭。', true);
      await api.completeClose({ cancelled: !saved });
    } catch (error) { closing = false; toast(`无法完成关闭：${errorMessage(error)}`, true); }
    if (!saved) closing = false;
  }
  function updateHeader() {
    const title = state.document.title || '未命名笔记本';
    $('toolbar-title').textContent = title;
    $('sidebar-title').textContent = title;
    document.title = `${title}${state.dirty ? ' *' : ''} — Mathematics`;
    $('cell-count').textContent = `${state.document.cells.length} 个单元`;
    $('save-indicator').textContent = state.dirty ? '未保存' : state.path ? '已保存' : '草稿';
    $('save-indicator').classList.toggle('unsaved', state.dirty);
    $('file-status').textContent = state.path ? state.path.split(/[\\/]/).pop() : '本地草稿';
    $('file-status').title = state.path || '自动保存的本地草稿';
  }
  function updateControls() {
    $('stop-button').disabled = !state.busy || state.canceling;
    $('run-all-button').disabled = state.busy || state.canceling || state.fileBusy;
    $('run-all-button').lastChild.textContent = state.busy ? ' 运行中' : '运行全部';
    document.querySelectorAll('.cell-run').forEach((button) => { button.disabled = state.busy || state.canceling; });
    document.querySelectorAll('[data-action="open"], [data-action="new"], [data-action="reset"]').forEach((button) => { button.disabled = state.busy || state.canceling || state.fileBusy; });
    state.document.cells.forEach((cell) => {
      const root = cellElement(cell.id);
      if (!root) return;
      const badge = root.querySelector('.cell-busy-label');
      if (badge) {
        badge.textContent = state.runningId === cell.id ? '计算中…' : state.queue.has(cell.id) ? '等待运行' : '';
        badge.hidden = !badge.textContent;
      }
      const run = root.querySelector('.cell-run');
      if (run) {
        run.replaceChildren();
        if (state.runningId === cell.id) { const spinner = document.createElement('span'); spinner.className = 'spinning'; run.append(spinner); }
        else run.innerHTML = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 4 10 6-10 6V4Z"/></svg>';
      }
      const type = root.querySelector('.cell-toolbar select');
      if (type) type.disabled = state.runningId === cell.id || state.queue.has(cell.id);
      root.querySelectorAll('.interactive-controls input').forEach((input) => {
        input.disabled = state.canceling || closing || (state.busy && !state.dynamic) || state.stale.has(cell.id) || cell.result?.evaluatedSource !== cell.source;
      });
    });
  }
  const cellElement = (id) => Array.from($('cells').children).find((node) => node.dataset.cellId === id);
  function autosize(textarea) {
    textarea.style.height = '0px';
    textarea.style.height = `${Math.max(textarea.scrollHeight, textarea.dataset.type === 'input' ? 65 : 35)}px`;
  }
  function actionButton(label, title, action, id) {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = label; button.title = title; button.setAttribute('aria-label', title);
    button.dataset.action = action; button.dataset.cellId = id;
    return button;
  }
  function renderCell(cell) {
    const root = document.createElement('section');
    root.className = `cell ${cell.type}-cell${state.activeId === cell.id ? ' active' : ''}`;
    root.dataset.cellId = cell.id;
    const toolbar = document.createElement('div'); toolbar.className = 'cell-toolbar';
    const type = document.createElement('select'); type.setAttribute('aria-label', '单元类型');
    [['input', '计算'], ['text', '文字'], ['heading', '标题']].forEach(([value, label]) => { const option = document.createElement('option'); option.value = value; option.textContent = label; type.append(option); });
    type.value = cell.type;
    type.addEventListener('change', () => {
      if (state.runningId === cell.id || state.queue.has(cell.id)) { type.value = cell.type; toast('请先停止计算，再修改队列中的单元。'); return; }
      dynamicCoordinator.clear(cell.id);
      cell.type = type.value; delete cell.result; state.stale.delete(cell.id); touch(); renderCells(); focusCell(cell.id);
    });
    toolbar.append(type, actionButton('↑', '向上移动单元', 'move-up', cell.id), actionButton('↓', '向下移动单元', 'move-down', cell.id), actionButton('＋', '在下方添加计算单元', 'add-after', cell.id), actionButton('×', '删除单元', 'delete-cell', cell.id));
    root.append(toolbar);
    if (cell.type === 'input') {
      const header = document.createElement('div'); header.className = 'input-header';
      const label = document.createElement('span'); label.className = 'cell-label input-label'; label.textContent = `In[${cell.result?.line ?? '·'}]:=`;
      const caption = document.createElement('span'); caption.className = 'cell-caption'; caption.textContent = 'WOLFRAM LANGUAGE';
      const busy = document.createElement('span'); busy.className = 'cell-busy-label'; busy.hidden = true;
      header.append(label, caption, busy); root.append(header);
      const run = document.createElement('button'); run.className = 'cell-run'; run.dataset.action = 'run-cell'; run.dataset.cellId = cell.id; run.title = '运行单元（Shift + Enter）'; run.setAttribute('aria-label', '运行当前单元');
      root.append(run);
    }
    const source = document.createElement('textarea');
    source.className = 'cell-source'; source.value = cell.source; source.dataset.type = cell.type; source.spellcheck = false; source.rows = 1;
    source.setAttribute('aria-label', cell.type === 'input' ? 'Wolfram 语言表达式' : cell.type === 'heading' ? '标题内容' : '文字内容');
    source.placeholder = cell.type === 'input' ? '输入表达式，例如 2 + 2' : cell.type === 'heading' ? '写下一个标题' : '记录你的思路…';
    source.addEventListener('input', () => { cell.source = source.value; dynamicCoordinator.clear(cell.id); autosize(source); touch(); updateResultStaleness(cell); updateControls(); });
    source.addEventListener('focus', () => {
      state.activeId = cell.id;
      $('cells').querySelectorAll('.cell').forEach((node) => node.classList.toggle('active', node.dataset.cellId === cell.id));
    });
    source.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (cell.type === 'input') runCells([cell.id], true);
        else focusNextInput(cell.id);
      } else if (event.key === 'Tab' && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault(); const from = source.selectionStart; const to = source.selectionEnd;
        source.setRangeText('  ', from, to, 'end'); source.dispatchEvent(new Event('input'));
      }
    });
    root.append(source);
    if (cell.result && cell.type === 'input') root.append(renderResult(cell));
    return root;
  }
  function updateResultStaleness(cell) {
    const node = cellElement(cell.id)?.querySelector('.result-stale');
    if (node) node.hidden = !(state.stale.has(cell.id) || cell.result?.evaluatedSource !== cell.source);
  }
  function normalizeResult(result, source) {
    return {
      text: String(result.text ?? ''), ...(typeof result.latex === 'string' ? { latex: result.latex } : {}),
      ...(typeof result.svg === 'string' ? { svg: result.svg } : {}),
      ...(result.graphics3d && typeof result.graphics3d === 'object' ? { graphics3d: result.graphics3d } : {}),
      ...(result.interactive && typeof result.interactive === 'object' ? { interactive: result.interactive } : {}),
      ...(result.algebraic_roots && typeof result.algebraic_roots === 'object' ? { algebraic_roots: result.algebraic_roots } : {}),
      line: result.line, elapsed_ms: result.elapsed_ms, messages: Array.isArray(result.messages) ? result.messages : [],
      prints: Array.isArray(result.prints) ? result.prints : [], suppressed: !!result.suppressed, evaluatedSource: source
    };
  }
  function controlsFor(result) {
    const controls = result?.interactive?.controls;
    if (!Array.isArray(controls)) return [];
    const seen = new Set();
    return controls.slice(0, 12).filter((control) => {
      if (!control || typeof control.symbol !== 'string' || !control.symbol || control.symbol.length > 100 || seen.has(control.symbol)) return false;
      if (![control.min, control.max, control.step, control.value].every(Number.isFinite) || control.max <= control.min || control.step <= 0) return false;
      seen.add(control.symbol); return true;
    });
  }
  function renderInteractiveControls(cell) {
    const controls = controlsFor(cell.result);
    if (!controls.length) return null;
    const root = document.createElement('div'); root.className = 'interactive-controls';
    const header = document.createElement('div'); header.className = 'interactive-heading';
    const title = document.createElement('span'); title.textContent = '交互参数';
    const note = document.createElement('span'); note.className = 'interactive-state'; note.textContent = '数值滑条 · 局部参数'; header.append(title, note); root.append(header);
    controls.forEach((control) => {
      const row = document.createElement('label'); row.className = 'interactive-control';
      const name = document.createElement('span'); name.className = 'interactive-label'; name.textContent = String(control.label || control.symbol);
      const slider = document.createElement('input'); slider.type = 'range'; slider.min = control.min; slider.max = control.max; slider.step = control.step; slider.value = control.value; slider.dataset.controlSymbol = control.symbol; slider.setAttribute('aria-label', `${String(control.label || control.symbol)}参数`);
      const value = document.createElement('output'); value.className = 'interactive-value'; value.textContent = formatControlValue(Number(slider.value));
      const changed = () => {
        value.textContent = formatControlValue(Number(slider.value));
        if (state.stale.has(cell.id) || cell.result?.evaluatedSource !== cell.source || !state.document.cells.includes(cell) || state.canceling || closing) return;
        const values = Object.fromEntries(Array.from(root.querySelectorAll('input[data-control-symbol]')).map((input) => [input.dataset.controlSymbol, Number(input.value)]));
        note.textContent = '等待最新参数…';
        dynamicCoordinator.request({ key: cell.id, notebookId: state.document.id, source: cell.source, controls: values });
      };
      slider.addEventListener('input', changed); row.append(name, slider, value); root.append(row);
    });
    return root;
  }
  function formatControlValue(value) { return Number.isFinite(value) ? String(Number(value.toPrecision(5))) : '—'; }
  function disposeViewer(id) {
    const previous = viewers.get(id);
    if (previous) { viewStates.set(id, previous.getState()); previous.dispose(); viewers.delete(id); }
  }
  function sanitizeSvg(svg) {
    if (!globalThis.DOMPurify) throw new Error('图形安全过滤器未加载。');
    const cleaned = DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true }, FORBID_TAGS: ['foreignObject', 'script', 'iframe', 'object', 'embed', 'animate', 'animateMotion', 'animateTransform', 'set'], FORBID_ATTR: ['onload', 'onerror'] });
    const parsed = new DOMParser().parseFromString(cleaned, 'image/svg+xml');
    if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') throw new Error('图形内容不是有效的 SVG。');
    parsed.querySelectorAll('*').forEach((element) => {
      for (const attribute of Array.from(element.attributes)) {
        const name = attribute.name.toLowerCase(), value = attribute.value.trim();
        const references = Array.from(value.matchAll(/url\s*\(\s*["']?([^)'"\s]+)["']?\s*\)/gi));
        if (name.startsWith('on') || ((name === 'href' || name === 'xlink:href') && !value.startsWith('#')) || references.some((match) => !match[1].startsWith('#'))) element.removeAttribute(attribute.name);
      }
    });
    return document.importNode(parsed.documentElement, true);
  }
  function renderFormula(latex) {
    const math = document.createElement('div'); math.className = 'result-latex';
    try { katex.render(NotebookMathDisplay.latexForDisplay(latex), math, { displayMode: true, throwOnError: false, trust: false, strict: 'ignore', output: 'htmlAndMathml' }); }
    catch { math.className = 'result-text'; math.textContent = latex; }
    return math;
  }
  function renderAlgebraicRoots(result) {
    const roots = result.algebraic_roots;
    if (!globalThis.katex || !roots || !Array.isArray(roots.rows) || !roots.rows.length || roots.rows.length > 50
      || !Number.isInteger(roots.digits) || roots.digits < 2 || roots.digits > 30
      || !roots.rows.every(row => row && typeof row.exact_latex === 'string' && typeof row.approximate_latex === 'string'
        && row.exact_latex.length <= 100000 && row.approximate_latex.length <= 100000)) return null;
    const panel = document.createElement('div'); panel.className = 'algebraic-roots';
    const heading = document.createElement('div'); heading.className = 'roots-heading';
    heading.textContent = `${roots.rows.length} 个解 · 数值近似`;
    const precision = document.createElement('span'); precision.className = 'roots-precision'; precision.textContent = `${roots.digits} 位有效数字`;
    heading.append(precision); panel.append(heading);
    const makeRows = (field) => {
      const list = document.createElement('ol'); list.className = 'root-solutions';
      roots.rows.forEach((row, index) => {
        const item = document.createElement('li'); item.className = 'root-solution';
        const number = document.createElement('span'); number.className = 'root-number'; number.textContent = `${index + 1}`;
        item.append(number, renderFormula(row[field])); list.append(item);
      });
      return list;
    };
    panel.append(makeRows('approximate_latex'));
    const exact = document.createElement('details'); exact.className = 'root-exact';
    const toggle = document.createElement('summary'); toggle.textContent = '查看精确解';
    const note = document.createElement('p'); note.textContent = 'Root 表示精确的代数根，上方小数为近似值。';
    exact.append(toggle, note, makeRows('exact_latex')); panel.append(exact);
    return panel;
  }
  function renderResult(cell) {
    const result = cell.result;
    const root = document.createElement('div'); root.className = `cell-result${result.error ? ' error-result' : ''}`;
    const controls = renderInteractiveControls(cell); if (controls) root.append(controls);
    (Array.isArray(result.prints) ? result.prints : []).forEach((text) => { const item = document.createElement('pre'); item.className = 'result-print'; item.textContent = String(text); root.append(item); });
    (Array.isArray(result.messages) ? result.messages : []).forEach((message) => { const item = document.createElement('div'); item.className = `result-message${message.kind === 'error' ? ' error' : ''}`; item.textContent = String(message.text ?? message); root.append(item); });
    const row = document.createElement('div'); row.className = 'result-top';
    const label = document.createElement('span'); label.className = 'cell-label output-label'; label.textContent = result.error ? 'Error' : `Out[${result.line ?? '·'}]=`;
    const body = document.createElement('div'); body.className = 'result-body';
    if (!result.suppressed && !result.error) {
      const rootSolutions = renderAlgebraicRoots(result);
      if (rootSolutions) body.append(rootSolutions);
      else if (result.latex && globalThis.katex) {
        body.append(renderFormula(result.latex));
      } else if (result.text && !((result.svg || result.graphics3d) && /^-?Graphics(?:3D)?-?$/.test(result.text))) { const text = document.createElement('pre'); text.className = 'result-text'; text.textContent = result.text; body.append(text); }
      if (result.svg) {
        const graphic = document.createElement('div'); graphic.className = 'result-svg';
        try { graphic.append(sanitizeSvg(String(result.svg))); body.append(graphic); }
        catch (error) { const text = document.createElement('div'); text.className = 'result-message error'; text.textContent = `图形未显示：${error.message}`; body.append(text); }
      }
      if (result.graphics3d) {
        const graphic = document.createElement('div'); graphic.className = 'result-graphics3d';
        try {
          if (!globalThis.NotebookGraphics3D) throw new Error('三维查看器未加载。');
          viewers.set(cell.id, NotebookGraphics3D.mount(graphic, result.graphics3d, viewStates.get(cell.id)));
          body.append(graphic);
        } catch (error) { const text = document.createElement('div'); text.className = 'result-message error'; text.textContent = `三维图形未显示：${errorMessage(error)}`; body.append(text); }
      }
    } else if (result.suppressed) { const note = document.createElement('div'); note.className = 'suppressed-note'; note.textContent = '已完成 · 分号抑制了结果显示'; body.append(note); }
    if (result.error) { const text = document.createElement('pre'); text.className = 'result-text'; text.textContent = result.text; body.append(text); }
    row.append(label, body); root.append(row);
    const meta = document.createElement('div'); meta.className = 'result-meta';
    const stale = document.createElement('span'); stale.className = 'result-stale'; stale.textContent = state.stale.has(cell.id) ? '历史结果 · 需要重新求值恢复变量' : '输入已修改 · 需要重新求值'; stale.hidden = !(state.stale.has(cell.id) || result.evaluatedSource !== cell.source);
    const time = document.createElement('span'); time.textContent = Number.isFinite(result.elapsed_ms) ? `${result.elapsed_ms < 1000 ? Math.round(result.elapsed_ms) + ' ms' : (result.elapsed_ms / 1000).toFixed(2) + ' s'}` : '';
    meta.append(stale, time); root.append(meta);
    return root;
  }
  function renderCells() {
    for (const id of viewers.keys()) disposeViewer(id);
    $('cells').replaceChildren(...state.document.cells.map(renderCell));
    if (!state.document.cells.length) { const empty = document.createElement('div'); empty.className = 'empty-notebook'; empty.textContent = '添加一个单元，从第一个问题开始。'; $('cells').append(empty); }
    $('cells').querySelectorAll('textarea').forEach(autosize);
    updateHeader(); updateControls();
  }
  function refreshCell(cell, preserveControls = false) {
    const previous = cellElement(cell.id), focused = previous?.contains(document.activeElement), selection = focused && document.activeElement instanceof HTMLTextAreaElement ? [document.activeElement.selectionStart, document.activeElement.selectionEnd] : null;
    const existingControls = preserveControls ? previous?.querySelector('.interactive-controls') : null;
    disposeViewer(cell.id);
    const previousResult = previous?.querySelector('.cell-result');
    if (existingControls && previousResult && controlsFor(cell.result).length === existingControls.querySelectorAll('input').length && controlsFor(cell.result).every((control) => Array.from(existingControls.querySelectorAll('input')).some((input) => input.dataset.controlSymbol === control.symbol))) {
      const replacementResult = renderResult(cell);
      controlsFor(cell.result).forEach((control) => {
        const input = Array.from(existingControls.querySelectorAll('input')).find((item) => item.dataset.controlSymbol === control.symbol);
        if (input) { input.value = control.value; input.nextElementSibling.textContent = formatControlValue(Number(input.value)); }
      });
      existingControls.querySelector('.interactive-state').textContent = '已更新 · 局部参数';
      Array.from(previousResult.children).forEach((node) => { if (node !== existingControls) node.remove(); });
      Array.from(replacementResult.children).forEach((node) => { if (!node.classList.contains('interactive-controls')) previousResult.append(node); });
      previousResult.className = replacementResult.className;
      const inputLabel = previous.querySelector('.input-label'); if (inputLabel) inputLabel.textContent = `In[${cell.result?.line ?? '·'}]:=`;
      updateControls(); return;
    }
    const replacement = renderCell(cell);
    if (previous) previous.replaceWith(replacement); else renderCells();
    const source = replacement.querySelector('textarea'); autosize(source);
    if (selection) { source.focus({ preventScroll: true }); source.setSelectionRange(...selection); }
    updateControls();
  }
  function focusCell(id) {
    state.activeId = id;
    const root = cellElement(id), source = root?.querySelector('textarea');
    if (source) { source.focus({ preventScroll: true }); root.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  }
  function focusNextInput(id) {
    const index = state.document.cells.findIndex((cell) => cell.id === id);
    let next = state.document.cells.slice(index + 1).find((cell) => cell.type === 'input');
    if (!next) { next = makeCell(); state.document.cells.push(next); touch(); renderCells(); }
    focusCell(next.id);
  }
  function addCell(type, afterId, source = '') {
    const cell = makeCell(type, source);
    const after = state.document.cells.findIndex((item) => item.id === (afterId || state.activeId));
    state.document.cells.splice(after >= 0 ? after + 1 : state.document.cells.length, 0, cell);
    state.activeId = cell.id; touch(); renderCells(); focusCell(cell.id);
    return cell;
  }
  function editCell(action, id) {
    const index = state.document.cells.findIndex((cell) => cell.id === id);
    if (index < 0) return;
    if (state.runningId === id || state.queue.has(id)) { toast('请先停止计算，再修改队列中的单元。'); return; }
    if (action === 'delete-cell') {
      dynamicCoordinator.clear(id); disposeViewer(id); viewStates.delete(id);
      state.document.cells.splice(index, 1); state.stale.delete(id);
      state.activeId = state.document.cells[Math.min(index, state.document.cells.length - 1)]?.id || null;
    } else {
      const to = index + (action === 'move-up' ? -1 : 1);
      if (to < 0 || to >= state.document.cells.length) return;
      const [cell] = state.document.cells.splice(index, 1); state.document.cells.splice(to, 0, cell);
    }
    touch(); renderCells(); if (state.activeId) focusCell(state.activeId);
  }
  function notice(text) { $('session-notice-text').textContent = text; $('session-notice').hidden = false; }
  function markResultsStale() {
    dynamicCoordinator.clear();
    state.document.cells.forEach((cell) => { if (cell.result) state.stale.add(cell.id); });
    renderCells();
  }
  async function runCells(ids, advance = false) {
    if (state.busy || state.canceling) { toast('计算正在进行。可以等待完成，或点击停止。'); return; }
    const candidates = ids.filter((id) => state.document.cells.some((cell) => cell.id === id && cell.type === 'input' && cell.source.trim()));
    if (!candidates.length) { toast('先在计算单元中写下一个表达式。'); return; }
    if (!api?.kernel) { toast('内核连接不可用，请使用桌面应用启动。', true); return; }
    const notebookId = state.document.id;
    dynamicCoordinator.clear();
    state.busy = true; state.stopped = false; state.queue = new Set(candidates); updateControls();
    let failed = false;
    try {
      for (const id of candidates) {
        if (state.stopped || state.document.id !== notebookId) break;
        const cell = state.document.cells.find((item) => item.id === id);
        if (!cell || cell.type !== 'input') continue;
        const source = cell.source;
        state.queue.delete(id); state.runningId = id;
        $('activity-status').textContent = candidates.length > 1 ? `正在计算 ${candidates.indexOf(id) + 1} / ${candidates.length} 个单元` : '正在计算当前单元…';
        setKernelStatus('busy'); updateControls();
        try {
          const result = await api.kernel.evaluate({ source, notebookId });
          if (state.document.id !== notebookId || state.stopped) break;
          if (!result || typeof result !== 'object') throw new Error('内核返回了无效结果。');
          cell.result = normalizeResult(result, source);
          state.stale.delete(cell.id);
          refreshCell(cell); touch();
          $('last-duration').textContent = Number.isFinite(result.elapsed_ms) ? `${(result.elapsed_ms / 1000).toFixed(2)} s` : '完成';
          if (result.messages?.some((message) => message.kind === 'error')) {
            failed = true; state.stopped = true; $('activity-status').textContent = '出现计算错误，后续单元已停止'; break;
          }
        } catch (error) {
          failed = true; state.stopped = true;
          const message = errorMessage(error);
          if (/重置|清空|取消|超时/i.test(message)) { markResultsStale(); notice(`${message} 笔记内容与历史结果已保留；需要重新运行赋值单元。`); }
          cell.result = { text: message, error: true, messages: [], prints: [], evaluatedSource: source }; refreshCell(cell); touch();
          $('activity-status').textContent = /取消/.test(message) ? '计算已停止' : '计算未完成';
          if (!state.canceling) toast(message, true);
          break;
        }
      }
    } finally {
      state.busy = false; state.runningId = null; state.queue.clear(); updateControls();
      if (!failed && !state.stopped) $('activity-status').textContent = candidates.length > 1 ? `已完成 ${candidates.length} 个单元` : '计算完成';
      if (advance && !failed && !state.stopped && state.document.id === notebookId) focusNextInput(candidates[0]);
      pollStatus(); saveDraft(); dynamicCoordinator.schedule();
    }
  }
  async function cancel() {
    if (!state.busy || state.canceling) return;
    state.stopped = true; state.canceling = true; updateControls(); $('activity-status').textContent = '正在停止计算…';
    dynamicCoordinator.clear();
    try {
      await ensureApi().kernel.cancel();
      markResultsStale(); notice('计算已停止，内核已重置，会话变量已清空。笔记内容与历史结果已保留。');
      $('activity-status').textContent = '计算已停止 · 内核已重置';
    } catch (error) { toast(error.message, true); }
    finally { state.canceling = false; updateControls(); pollStatus(); }
  }
  function setKernelStatus(status, version) {
    const labels = { starting: 'Mathics 正在启动…', ready: `Mathics ${version || ''} · 就绪`.replace('  ', ' '), busy: 'Mathics · 计算中', error: 'Mathics · 连接异常', unavailable: '桌面内核未连接' };
    const color = status === 'ready' ? '#8baf6d' : status === 'busy' ? '#df8b56' : status === 'error' || status === 'unavailable' ? '#c69078' : '#c4b072';
    $('kernel-status').textContent = labels[status] || labels.starting;
    $('status-dot').style.background = color; $('engine-dot').style.background = color;
    $('engine-label').textContent = status === 'ready' ? 'Mathics 内核已就绪' : status === 'busy' ? 'Mathics 正在计算' : status === 'starting' ? '正在启动内核' : '内核连接不可用';
  }
  async function pollStatus() {
    if (statusInFlight) return;
    if (!api?.kernel) { setKernelStatus('unavailable'); return; }
    statusInFlight = true;
    try { state.health = await api.kernel.status(); setKernelStatus(state.busy ? 'busy' : state.health.status || (state.health.ready ? 'ready' : 'starting'), state.health.version); }
    catch (error) { setKernelStatus('error'); $('kernel-status').title = error.message; }
    finally { statusInFlight = false; }
  }
  function normalizeDocument(value) {
    if (!value || value.format !== 'mathematics-notebook' || value.version !== 1 || !Array.isArray(value.cells)) throw new Error('这不是受支持的 .mnb 笔记本。');
    const seen = new Set();
    const cells = value.cells.map((cell) => {
      if (!cell || !['input', 'text', 'heading'].includes(cell.type) || typeof cell.source !== 'string') throw new Error('笔记本包含无效单元。');
      const id = typeof cell.id === 'string' && !seen.has(cell.id) ? cell.id : uid(); seen.add(id);
      return { id, type: cell.type, source: cell.source, ...(cell.result && typeof cell.result === 'object' ? { result: cell.result } : {}), ...(cell.nbImport && typeof cell.nbImport === 'object' ? { nbImport: cell.nbImport } : {}) };
    });
    return { format: 'mathematics-notebook', version: 1, id: typeof value.id === 'string' ? value.id : uid(), title: typeof value.title === 'string' ? value.title : '未命名笔记本', cells, updatedAt: typeof value.updatedAt === 'string' ? value.updatedAt : new Date().toISOString() };
  }
  function loadDocument(documentValue, path = null, draft = false) {
    dynamicCoordinator.clear(); viewStates.clear();
    state.document = normalizeDocument(documentValue); state.path = path; state.dirty = draft; state.activeId = null; state.stale.clear();
    state.document.cells.forEach((cell) => { if (cell.result) state.stale.add(cell.id); });
    $('document-title').value = state.document.title;
    $('session-notice').hidden = true;
    if (state.stale.size) notice('已打开保存的笔记。显示的是历史结果；变量需要运行赋值单元后恢复。');
    renderCells(); $('notebook-scroll').scrollTop = 0; saveDraft();
  }
  async function save(saveAs = false) {
    if (state.fileBusy) return false;
    state.fileBusy = true; updateControls();
    try {
      const snapshot = structuredClone(state.document);
      const result = await ensureApi().files.save({ document: snapshot, path: state.path, saveAs });
      if (result.canceled) return false;
      state.path = result.path;
      state.dirty = JSON.stringify(snapshot) !== JSON.stringify(state.document);
      updateHeader(); await saveDraft(); toast('笔记本已保存。'); return true;
    } catch (error) { toast(error.message, true); return false; }
    finally { state.fileBusy = false; updateControls(); }
  }
  async function confirmSwitch() {
    if (!state.dirty) return true;
    const dialog = $('confirm-dialog');
    const choice = await new Promise((resolve) => {
      let settled = false;
      const finish = (value) => { if (settled) return; settled = true; dialog.removeEventListener('click', click); dialog.removeEventListener('cancel', cancelEvent); dialog.close(); resolve(value); };
      const click = (event) => { const action = event.target.closest('[data-confirm]'); if (action) finish(action.dataset.confirm); };
      const cancelEvent = (event) => { event.preventDefault(); finish('cancel'); };
      dialog.addEventListener('click', click); dialog.addEventListener('cancel', cancelEvent); dialog.showModal();
    });
    return choice === 'save' ? await save() : choice === 'discard';
  }
  async function open() {
    if (state.busy || state.canceling || state.fileBusy) { toast('请先停止当前计算，再打开其他笔记本。'); return; }
    if (!(await confirmSwitch())) return;
    try {
      const result = await ensureApi().files.open();
      if (!result.canceled) {
        const loaded = normalizeDocument(result.document);
        await api.kernel.reset({ notebookId: loaded.id });
        loadDocument(loaded, result.path); toast('笔记本已打开，内核从新会话开始。');
        if (Array.isArray(result.warnings) && result.warnings.length) notice(result.warnings.map(String).join(' '));
      }
    }
    catch (error) { toast(error.message, true); }
  }
  async function createNew() {
    if (state.busy || state.canceling || state.fileBusy) { toast('请先停止当前计算，再新建笔记本。'); return; }
    if (!(await confirmSwitch())) return;
    dynamicCoordinator.clear(); viewStates.clear();
    state.document = makeDocument(); state.path = null; state.dirty = false; state.stale.clear(); $('document-title').value = state.document.title; $('session-notice').hidden = true;
    renderCells(); touch(); focusCell(state.document.cells[1].id);
  }
  async function exportWL() {
    try {
      const escapeComment = (text) => text.replace(/\(\*/g, '( *').replace(/\*\)/g, '* )');
      const source = `(* ${escapeComment(state.document.title)} *)\n\n` + state.document.cells.map((cell) => cell.type === 'input' ? cell.source : `(* ${escapeComment(cell.source)} *)`).join('\n\n') + '\n';
      const result = await ensureApi().files.exportWL({ source, title: state.document.title });
      if (!result.canceled) toast('Wolfram 语言源码已导出。');
    } catch (error) { toast(error.message, true); }
  }
  async function exportNB() {
    try {
      if (!api?.files?.exportNB) throw new Error('此版本尚未连接 .nb 导出。');
      const result = await api.files.exportNB({ document: structuredClone(state.document) });
      if (!result.canceled) { toast('基础 .nb 文档已导出。'); if (Array.isArray(result.warnings) && result.warnings.length) notice(result.warnings.map(String).join(' ')); }
    } catch (error) { toast(error.message, true); }
  }
  async function reset() {
    if (state.busy) { toast('请先停止计算，再重置当前会话。'); return; }
    dynamicCoordinator.clear();
    try { await ensureApi().kernel.reset({ notebookId: state.document.id }); markResultsStale(); notice('当前笔记本的内核变量已清空。历史结果保留，运行单元可以重新计算。'); $('activity-status').textContent = '当前内核已重置'; pollStatus(); }
    catch (error) { toast(error.message, true); }
  }
  function toggleHelp(show) {
    const panel = $('help-panel'); panel.hidden = typeof show === 'boolean' ? !show : !panel.hidden; $('help-toggle').setAttribute('aria-expanded', String(!panel.hidden));
  }
  const dynamicCoordinator = new NotebookDynamic.DynamicCoordinator({
    run: (job) => ensureApi().kernel.evaluate({ source: job.source, notebookId: job.notebookId, controls: job.controls }),
    canRun: () => !state.busy && !state.canceling && !closing,
    valid: (job) => {
      const cell = state.document.cells.find((item) => item.id === job.key);
      return !closing && state.document.id === job.notebookId && cell?.type === 'input' && cell.source === job.source && !state.stale.has(cell.id);
    },
    onStart: (job) => {
      state.busy = true; state.dynamic = true; state.stopped = false; state.runningId = job.key;
      const controls = cellElement(job.key)?.querySelector('.interactive-state'); if (controls) controls.textContent = '正在更新…';
      $('activity-status').textContent = '正在计算最新交互参数…'; setKernelStatus('busy'); updateControls();
    },
    onResult: (job, result) => {
      if (!result || typeof result !== 'object') throw new Error('内核返回了无效的交互结果。');
      const cell = state.document.cells.find((item) => item.id === job.key);
      cell.result = normalizeResult(result, job.source); state.stale.delete(cell.id); refreshCell(cell, true); touch();
      $('last-duration').textContent = Number.isFinite(result.elapsed_ms) ? `${(result.elapsed_ms / 1000).toFixed(2)} s` : '完成';
      $('activity-status').textContent = '交互参数已更新';
      if (result.messages?.some((message) => message.kind === 'error')) dynamicCoordinator.clear(job.key);
    },
    onError: (job, error, current) => {
      const message = errorMessage(error);
      if (/重置|清空|取消|超时/i.test(message)) { markResultsStale(); notice(`${message} 历史内容已保留，重新运行单元可以恢复计算。`); }
      if (current) {
        const cell = state.document.cells.find((item) => item.id === job.key);
        if (cell) { cell.result = { text: message, error: true, messages: [], prints: [], evaluatedSource: job.source }; refreshCell(cell); touch(); }
        if (!state.canceling) toast(message, true);
        $('activity-status').textContent = '交互更新未完成';
      }
    },
    onFinish: () => {
      state.busy = false; state.dynamic = false; state.runningId = null; updateControls(); pollStatus(); saveDraft();
    }
  });
  async function action(name, id) {
    try {
      switch (name) {
        case 'new': await createNew(); break;
        case 'open': await open(); break;
        case 'save': await save(); break;
        case 'save-as': await save(true); break;
        case 'export': await exportWL(); break;
        case 'export-nb': await exportNB(); break;
        case 'compatibility': globalThis.MathematicsCompatibility?.open(); break;
        case 'run-all': await runCells(state.document.cells.filter((cell) => cell.type === 'input').map((cell) => cell.id)); break;
        case 'run-cell': await runCells([id]); break;
        case 'cancel': await cancel(); break;
        case 'reset': await reset(); break;
        case 'add-input': addCell('input'); break;
        case 'add-text': addCell('text'); break;
        case 'add-heading': addCell('heading'); break;
        case 'add-after': addCell('input', id); break;
        case 'delete-cell': case 'move-up': case 'move-down': editCell(name, id); break;
        case 'toggle-help': toggleHelp(); break;
        case 'help': toggleHelp(true); $('help-panel').scrollTop = 0; break;
        case 'top': $('notebook-scroll').scrollTo({ top: 0, behavior: 'smooth' }); break;
        case 'dismiss-notice': $('session-notice').hidden = true; break;
      }
    } catch (error) { toast(error.message, true); }
  }
  const palette = NotebookPalette.mount({
    onInsert: (text) => { addCell('input', state.activeId, text); toast('已插入函数表达式，Shift + Enter 运行。'); }
  });
  document.addEventListener('click', (event) => {
    const insert = event.target.closest('[data-insert]');
    if (insert) { addCell('input', state.activeId, insert.dataset.insert); return; }
    const button = event.target.closest('[data-action]');
    if (button && !button.disabled) action(button.dataset.action, button.dataset.cellId);
  });
  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && !event.altKey) {
      const key = event.key.toLowerCase();
      if (key === 's') { event.preventDefault(); action(event.shiftKey ? 'save-as' : 'save'); }
      else if (key === 'o') { event.preventDefault(); action('open'); }
      else if (key === 'n') { event.preventDefault(); action('new'); }
      else if (key === 'k') { event.preventDefault(); palette.open(); }
      else if (key === '.' && state.busy) { event.preventDefault(); action('cancel'); }
    }
  });
  $('document-title').addEventListener('input', (event) => { state.document.title = event.target.value; touch(); });
  function addExampleNavigation(items, targetId) { items.forEach(([icon, label, source]) => {
    const button = document.createElement('button'); const glyph = document.createElement('span'); glyph.className = 'example-icon'; glyph.textContent = icon; const text = document.createElement('span'); text.textContent = label; button.append(glyph, text);
    button.addEventListener('click', () => { const cell = state.document.cells.find((item) => item.type === 'input' && item.source === source); if (cell) focusCell(cell.id); else addCell('input', state.activeId, source); });
    $(targetId).append(button);
  }); }
  addExampleNavigation(examples, 'example-navigation');
  addExampleNavigation(advancedExamples, 'advanced-example-navigation');
  renderCells(); pollStatus();
  const statusTimer = setInterval(pollStatus, 4000);
  window.addEventListener('resize', () => { $('cells').querySelectorAll('textarea').forEach(autosize); });
  window.addEventListener('beforeunload', () => { clearInterval(statusTimer); clearTimeout(draftTimer); dynamicCoordinator.dispose(); for (const id of viewers.keys()) disposeViewer(id); menuUnsubscribe?.(); closeUnsubscribe?.(); });
  if (api?.onMenuAction) menuUnsubscribe = api.onMenuAction((menuAction) => { action(typeof menuAction === 'string' ? menuAction : menuAction?.action); });
  if (api?.onCloseRequested) closeUnsubscribe = api.onCloseRequested(closeRequested);
  if (api?.storage) api.storage.loadDraft().then((draft) => { if (draft && !state.dirty && !state.busy) loadDocument(draft, null, true); }).catch((error) => { toast(`无法读取草稿：${error.message}`, true); });
})();
