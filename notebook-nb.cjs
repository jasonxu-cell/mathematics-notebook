'use strict';

// A structural .nb reader. It never evaluates Wolfram Language or JavaScript.
const crypto = require('node:crypto');
const { validateDocument, MAX_SOURCE, MAX_ARCHIVE } = require('./notebook-model.cjs');
const { serializeDocument } = require('./disk-storage.cjs');

const MAX_BYTES = 8 * 1024 * 1024;
const MAX_DEPTH = 128;
const MAX_NODES = 250000;
const MAX_CELLS = 2000;
const SUBSET_WARNING = '.nb 导入支持文本和基础数学排版子集；分组会平铺，样式、交互控件和前端选项不复现。导入不会执行代码或初始化单元。';

class NotebookSyntaxError extends Error {
  constructor(message, offset) {
    super(`无效的 .nb 文件：${message}（位置 ${offset}）。`);
    this.name = 'NotebookSyntaxError';
  }
}

function parseNotebookSource(source) {
  if (typeof source !== 'string') throw new TypeError('.nb 内容必须是文本。');
  if (Buffer.byteLength(source, 'utf8') > MAX_BYTES) throw new Error('.nb 文件超过 8 MiB 限制。');
  let position = 0;
  let count = 0;
  const notices = new Set();
  const fail = message => { throw new NotebookSyntaxError(message, position); };
  const raw = node => source.slice(node.start, node.end);
  function track(node) {
    if (++count > MAX_NODES) fail('结构节点过多');
    return node;
  }
  function skip() {
    while (position < source.length) {
      if (/\s|\uFEFF/.test(source[position])) { position++; continue; }
      if (source.slice(position, position + 2) !== '(*') break;
      position += 2;
      let nesting = 1;
      while (position < source.length && nesting) {
        const pair = source.slice(position, position + 2);
        if (pair === '(*') {
          if (++nesting > MAX_DEPTH) fail('注释嵌套过深');
          position += 2;
        } else if (pair === '*)') { nesting--; position += 2; }
        else position++;
      }
      if (nesting) fail('注释未结束');
    }
  }
  function string() {
    const start = position++;
    let value = '';
    while (position < source.length) {
      const character = source[position++];
      if (character === '"') return track({ kind: 'string', value, start, end: position });
      if (character !== '\\') { value += character; continue; }
      if (position >= source.length) fail('字符串转义未结束');
      const escaped = source[position++];
      const simple = { '"': '"', '\\': '\\', n: '\n', r: '\r', t: '\t', b: '\b', f: '\f' };
      if (Object.hasOwn(simple, escaped)) { value += simple[escaped]; continue; }
      if (escaped === '\n') continue;
      if (escaped === '\r') { if (source[position] === '\n') position++; continue; }
      const widths = { ':': 4, '|': 6, '.': 2 };
      if (Object.hasOwn(widths, escaped)) {
        const digits = source.slice(position, position + widths[escaped]);
        if (!new RegExp(`^[0-9a-fA-F]{${widths[escaped]}}$`).test(digits)) fail('无效的字符编码转义');
        const point = parseInt(digits, 16);
        if (point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff)) fail('字符编码超出 Unicode 范围');
        value += String.fromCodePoint(point); position += widths[escaped]; continue;
      }
      if (escaped === '[') {
        const close = source.indexOf(']', position);
        if (close < 0 || !/^[A-Za-z][A-Za-z0-9]*$/.test(source.slice(position, close))) fail('命名字符转义未结束');
        value += `\\[${source.slice(position, close)}]`; position = close + 1;
        continue;
      }
      // Preserve unknown escapes literally instead of silently deleting '\'.
      value += `\\${escaped}`;
      notices.add('部分字符串转义不在支持子集中，已按原样保留；请检查显示和输入。');
    }
    fail('字符串未结束');
  }
  function expression(depth, close) {
    if (depth > MAX_DEPTH) fail('括号嵌套过深');
    skip();
    const start = position;
    const parts = [];
    while (position < source.length) {
      skip();
      const character = source[position];
      if (character === undefined || character === ',' || character === close) break;
      if (')]}' .includes(character)) fail('括号不匹配');
      if (character === '"') parts.push(string());
      else if ('[{('.includes(character)) parts.push(group(depth + 1));
      else {
        const atomStart = position;
        while (position < source.length && !/[\s\[\]{}(),"]/.test(source[position]) &&
               source.slice(position, position + 2) !== '(*') position++;
        if (position === atomStart) fail('无法读取结构');
        parts.push(track({ kind: 'atom', start: atomStart, end: position }));
      }
    }
    if (!parts.length) fail('缺少表达式');
    const end = parts.at(-1).end;
    if (parts.length === 1) return parts[0];
    if (parts.length === 2 && parts[0].kind === 'atom' && parts[1].kind === 'group' && parts[1].open === '[') {
      const head = raw(parts[0]);
      if (/^(?:System`)?[A-Za-z$][A-Za-z0-9$]*$/.test(head)) {
        return track({ kind: 'call', head: head.replace(/^System`/, ''), args: parts[1].args, start, end });
      }
    }
    return track({ kind: 'opaque', parts, start, end });
  }
  function group(depth) {
    if (depth > MAX_DEPTH) fail('括号嵌套过深');
    const start = position;
    const open = source[position++];
    const close = { '[': ']', '{': '}', '(': ')' }[open];
    const args = [];
    skip();
    if (source[position] !== close) {
      while (true) {
        args.push(expression(depth, close)); skip();
        if (source[position] === close) break;
        if (source[position] !== ',') fail('括号未结束');
        position++; skip();
        if (source[position] === close) fail('逗号后缺少表达式');
      }
    }
    if (source[position] !== close) fail('括号未结束');
    position++;
    return track({ kind: open === '{' ? 'list' : 'group', open, args, start, end: position });
  }
  skip();
  if (position === source.length) fail('文件为空');
  const node = expression(0, null); skip();
  if (position !== source.length) fail('顶层表达式后有额外内容');
  if (node.kind !== 'call' || node.head !== 'Notebook' || node.args[0]?.kind !== 'list') {
    fail('需要单个 Notebook[{Cell[...], ...}, options] 表达式');
  }
  return { node, raw, notices };
}

function fromNotebook(source, title = '导入的笔记本') {
  const { node, raw, notices } = parseNotebookSource(source);
  const warnings = new Set([SUBSET_WARNING, ...notices]);
  const cells = [];
  let cellCount = 0;
  let lastInput = null;
  const warn = message => warnings.add(message);
  const isCall = (value, head) => value?.kind === 'call' && value.head === head;
  function unsupported(box, reason = '') {
    throw new Error(reason || `不支持 ${box?.head || '该内容结构'}`);
  }
  function boxText(box) {
    if (box.kind === 'string') {
      if (/\\[<>!()]/.test(box.value)) unsupported(box, '包含未支持的字符串排版转义');
      return box.value;
    }
    if (isCall(box, 'BoxData') && box.args.length === 1) return boxText(box.args[0]);
    if (isCall(box, 'FormBox')) {
      const form = box.args[1] && raw(box.args[1]);
      if (form !== 'StandardForm' && form !== 'System`StandardForm') unsupported(box, '非 StandardForm 的语义未确定');
      return boxText(box.args[0]);
    }
    if (isCall(box, 'RowBox') && box.args.length === 1 && box.args[0].kind === 'list') {
      if (box.args[0].args.some(element => isCall(element, 'RowBox'))) {
        warn('嵌套 RowBox 按显示顺序转为输入文本；复杂分组需核对，原始 Cell 保存在导入记录中。');
      }
      let text = '';
      for (const element of box.args[0].args) {
        const part = boxText(element);
        if (/[\p{L}\p{N}$`_\])]/u.test(text.at(-1) || '') && /^[\p{L}\p{N}$`_(]/u.test(part)) {
          text += ' ';
          warn('相邻 RowBox 字符串按分开的输入记号保留（如 2 Pi）；请检查隐式乘法或符号名称。');
        }
        text += part;
      }
      return text;
    }
    if (isCall(box, 'FractionBox') && box.args.length === 2) return `(${boxText(box.args[0])})/(${boxText(box.args[1])})`;
    if (isCall(box, 'SuperscriptBox') && box.args.length === 2) {
      const exponent = boxText(box.args[1]);
      if (/[′″‴'†]/u.test(exponent) || /\\\[(?:Prime|DoublePrime|TriplePrime|Dagger)\]/.test(exponent)) {
        unsupported(box, '导数或共轭上标的语义未确定');
      }
      return `(${boxText(box.args[0])})^(${exponent})`;
    }
    if (isCall(box, 'SqrtBox') && box.args.length === 1) return `Sqrt[${boxText(box.args[0])}]`;
    if (isCall(box, 'SubscriptBox') && box.args.length === 2) return `Subscript[${boxText(box.args[0])},${boxText(box.args[1])}]`;
    if (isCall(box, 'GridBox') && box.args[0]?.kind === 'list') {
      const rows = box.args[0].args;
      if (!rows.every(row => row.kind === 'list') ||
          rows.some(row => row.args.length !== (rows[0]?.args.length || 0))) unsupported(box, 'GridBox 必须是矩形基础表格');
      if (box.args.length > 1) warn('GridBox 的排版选项已忽略，基础表格转换为嵌套列表。');
      return `{${rows.map(row => `{${row.args.map(boxText).join(',')}}`).join(',')}}`;
    }
    unsupported(box);
  }
  function plainText(content) {
    if (content.kind === 'string') return content.value;
    if (isCall(content, 'TextData') && content.args.length === 1) {
      const items = content.args[0].kind === 'list' ? content.args[0].args : [content.args[0]];
      return items.map(plainText).join('');
    }
    if (isCall(content, 'StyleBox') && content.args.length) {
      warn('文字样式已转换为纯文本。'); return plainText(content.args[0]);
    }
    if (isCall(content, 'Cell') && content.args.length) return plainText(content.args[0]);
    return boxText(content);
  }
  function append(type, text, original, style) {
    if (cells.length >= MAX_CELLS) throw new Error('.nb 单元格过多（最多 2000 个）。');
    if (text.length > MAX_SOURCE) throw new Error('.nb 单个单元格内容超过 100000 字符限制。');
    if (original.length > MAX_ARCHIVE) throw new Error('.nb 单个单元格的原始归档过长。');
    const cell = {
      id: crypto.randomUUID(), type, source: text,
      nbImport: { original, style, source: text },
    };
    cells.push(cell); lastInput = type === 'input' ? cell : null;
    return cell;
  }
  function visit(value, depth = 0) {
    if (depth > MAX_DEPTH) throw new Error('.nb 单元分组嵌套过深。');
    if (isCall(value, 'CellGroupData') && value.args[0]?.kind === 'list') {
      warn('CellGroupData 已按原顺序平铺；折叠状态未保留。');
      for (const item of value.args[0].args) visit(item, depth + 1);
      return;
    }
    if (!isCall(value, 'Cell')) {
      warn('发现非 Cell 内容，已保留为不可执行的原始文本。');
      append('text', raw(value), raw(value), 'Text'); return;
    }
    if (++cellCount > MAX_CELLS) throw new Error('.nb 单元格过多（最多 2000 个）。');
    const content = value.args[0];
    if (!content) throw new Error('.nb 的 Cell 缺少内容。');
    if (isCall(content, 'CellGroupData')) { visit(content, depth + 1); return; }
    const style = value.args[1]?.kind === 'string' ? value.args[1].value : 'Text';
    const original = raw(value);
    // This only observes an option name. No option or initialization expression
    // is ever evaluated, imported as a handler, or re-emitted on export.
    if (value.args.some(arg => /\b(?:InitializationCell|CellEvaluationFunction|CellEventActions|CellProlog|CellEpilog)\b/.test(raw(arg)))) {
      warn('单元格的初始化/事件求值选项已禁用；仅保留内容，需要手动选择求值。');
    }
    let text;
    try { text = ['Input', 'Code', 'Output'].includes(style) ? boxText(content) : plainText(content); }
    catch (error) {
      warn(`${style} 单元格未转换：${error.message}；完整原始 Cell 已保留为不可执行文本。`);
      append('text', original, original, style); return;
    }
    if (text.length > MAX_SOURCE) throw new Error('.nb 单个单元格内容超过 100000 字符限制。');
    if (original.length > MAX_ARCHIVE) throw new Error('.nb 单个单元格的原始归档过长。');
    if (['Print', 'Message'].includes(style) && lastInput) {
      const result = lastInput.result ||= { text: '', suppressed: false, prints: [], messages: [] };
      if (style === 'Print') result.prints.push(text);
      else result.messages.push({ kind: 'message', text });
      lastInput.nbImport.outputs ||= [];
      lastInput.nbImport.outputs.push({ original, text });
      warn('保存的 Print/Message 已作为历史文本保留；导入不会执行其内容。');
      return;
    }
    if (style === 'Output' && lastInput) {
      const previous = lastInput.result?.text;
      const combined = previous ? `${previous}\n\n${text}` : text;
      if (combined.length > MAX_SOURCE) {
        warn('输出历史较长，后续 Output 已保留为独立文本单元格。');
        append('text', text, original, style); return;
      }
      const result = lastInput.result ||= { text: '', suppressed: false, prints: [], messages: [] };
      result.text = combined; result.suppressed = false;
      lastInput.nbImport.outputs ||= [];
      lastInput.nbImport.outputs.push({ original, text });
      warn('保存的 Output 已作为历史文本保留；它不证明本次运行产生了相同结果。');
      return;
    }
    if (['Input', 'Code'].includes(style)) append('input', text, original, style);
    else if (['Title', 'Section', 'Subtitle', 'Subsection', 'Subsubsection'].includes(style)) append('heading', text, original, style);
    else {
      if (!['Text', 'Output', 'Print', 'Message'].includes(style)) warn(`样式 ${style} 已转换为纯文本。`);
      append('text', text, original, style);
      if (style === 'Output') warn('没有对应输入的 Output 已作为普通历史文本保留。');
    }
  }
  for (const cell of node.args[0].args) visit(cell);
  if (cells.length > MAX_CELLS) throw new Error('.nb 单元格过多（最多 2000 个）。');
  const document = validateDocument({ format: 'mathematics-notebook', version: 1,
    id: crypto.randomUUID(), title, cells });
  // Archival source plus decoded text can be larger than the original .nb.
  // Check the largest normal save representation before changing app state.
  try { serializeDocument(document, true); }
  catch { throw new Error('.nb 转换后的笔记本超过 8 MiB 保存限制；请减少单元格或历史输出后再导入。'); }
  return { document, warnings: [...warnings] };
}

function quoteWolfram(text) {
  return '"' + text.replace(/[\\"\n\r\t\b\f\u0000-\u001f]/g, character => {
    const escapes = { '\\': '\\\\', '"': '\\"', '\n': '\\n', '\r': '\\r', '\t': '\\t', '\b': '\\b', '\f': '\\f' };
    return escapes[character] || `\\:${character.charCodeAt(0).toString(16).padStart(4, '0')}`;
  }) + '"';
}

function toNotebook(document) {
  const value = validateDocument(document);
  const exported = [];
  function pushHistory(text, style) {
    if (typeof text !== 'string') throw new Error(`导出的 ${style} 历史文本无效。`);
    if (text.length > MAX_SOURCE) throw new Error('导出的输出文本过长。');
    exported.push(`Cell[${quoteWolfram(text)}, ${quoteWolfram(style)}]`);
    if (exported.length > MAX_CELLS) throw new Error('导出含输出的 .nb 超过 2000 个单元格限制。');
  }
  for (const cell of value.cells) {
    const imported = cell.nbImport;
    const unchanged = imported && imported.source === cell.source;
    if (cell.type === 'input') {
      const style = unchanged && imported.style === 'Code' ? 'Code' : 'Input';
      exported.push(`Cell[BoxData[${quoteWolfram(cell.source)}], ${quoteWolfram(style)}, InitializationCell -> False]`);
      if (cell.result?.prints !== undefined && !Array.isArray(cell.result.prints)) throw new Error('导出的 Print 历史无效。');
      if (cell.result?.messages !== undefined && !Array.isArray(cell.result.messages)) throw new Error('导出的 Message 历史无效。');
      for (const printed of cell.result?.prints || []) pushHistory(printed, 'Print');
      for (const message of cell.result?.messages || []) pushHistory(typeof message === 'string' ? message : message?.text, 'Message');
      if (typeof cell.result?.text === 'string' && !cell.result.suppressed && cell.result.text) {
        pushHistory(cell.result.text, 'Output');
      }
    } else {
      const safeStyles = new Set(['Title', 'Subtitle', 'Section', 'Subsection', 'Subsubsection']);
      const style = cell.type === 'heading' ? (unchanged && safeStyles.has(imported.style) ? imported.style : 'Section') : 'Text';
      // Source preservation is archival text, never a re-injected Cell/Box AST.
      exported.push(`Cell[${quoteWolfram(cell.source)}, ${quoteWolfram(style)}]`);
    }
    if (exported.length > MAX_CELLS) throw new Error('导出含输出的 .nb 超过 2000 个单元格限制。');
  }
  const source = '(* Independent Mathematics Notebook export: text/basic math subset. *)\n' +
    `Notebook[{\n${exported.join(',\n')}\n}, WindowTitle -> ${quoteWolfram(value.title)}, StyleDefinitions -> "Default.nb"]\n`;
  if (Buffer.byteLength(source, 'utf8') > MAX_BYTES) throw new Error('导出的 .nb 文件超过 8 MiB 限制。');
  return source;
}

module.exports = { fromNotebook, toNotebook, MAX_BYTES, MAX_DEPTH, MAX_CELLS, NotebookSyntaxError };
