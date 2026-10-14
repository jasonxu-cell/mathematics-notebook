const crypto = require('node:crypto');

const MAX_SOURCE = 100000;
// A quoted Wolfram character can require six source characters (\:0000).
// Archive limits must include escaping and Cell wrappers, not just plain text.
const MAX_ARCHIVE = MAX_SOURCE * 6 + 4096;

function validateDocument(value) {
  if (!value || value.format !== 'mathematics-notebook' || value.version !== 1 || !Array.isArray(value.cells)) {
    throw new Error('这不是受支持的 Mathematics Notebook 文件。');
  }
  if (value.cells.length > 2000) throw new Error('笔记本单元格过多（最多 2000 个）。');
  const ids = new Set();
  const cells = value.cells.map(cell => {
    if (!cell || !['input', 'text', 'heading'].includes(cell.type) || typeof cell.source !== 'string') {
      throw new Error('笔记本包含无效单元格。');
    }
    if (cell.source.length > MAX_SOURCE) throw new Error('单个输入过长。');
    const id = typeof cell.id === 'string' && cell.id.length < 100 ? cell.id : crypto.randomUUID();
    if (ids.has(id)) throw new Error('笔记本包含重复单元格 ID。');
    ids.add(id);
    let nbImport;
    if (cell.nbImport && typeof cell.nbImport === 'object' && !Array.isArray(cell.nbImport)) {
      const entry = cell.nbImport;
      if (typeof entry.original !== 'string' || entry.original.length > MAX_ARCHIVE || typeof entry.source !== 'string' || entry.source.length > MAX_SOURCE || typeof entry.style !== 'string' || entry.style.length > 200) throw new Error('笔记本包含无效的导入记录。');
      nbImport = { original: entry.original, source: entry.source, style: entry.style };
      if (entry.outputs !== undefined) {
        if (!Array.isArray(entry.outputs) || entry.outputs.length > 2000 || entry.outputs.some(output => !output || typeof output.original !== 'string' || output.original.length > MAX_ARCHIVE || typeof output.text !== 'string' || output.text.length > MAX_SOURCE)) throw new Error('笔记本包含无效的输出导入记录。');
        nbImport.outputs = entry.outputs.map(output => ({ original: output.original, text: output.text }));
      }
    }
    return { id, type: cell.type, source: cell.source, ...(cell.result ? { result: cell.result } : {}), ...(nbImport ? { nbImport } : {}) };
  });
  return {
    format: 'mathematics-notebook', version: 1,
    id: typeof value.id === 'string' && value.id.length < 100 ? value.id : crypto.randomUUID(),
    title: typeof value.title === 'string' ? value.title.slice(0, 200) : '未命名笔记本',
    cells, updatedAt: new Date().toISOString(),
  };
}

function fromWolframLanguage(source, title) {
  if (source.length > MAX_SOURCE) throw new Error('导入的源文件过长。');
  return validateDocument({ format: 'mathematics-notebook', version: 1, title, cells: [
    { id: crypto.randomUUID(), type: 'input', source },
  ] });
}

module.exports = { validateDocument, fromWolframLanguage, MAX_SOURCE, MAX_ARCHIVE };
