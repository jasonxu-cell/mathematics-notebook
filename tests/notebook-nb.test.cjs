const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { fromNotebook, toNotebook, MAX_BYTES, MAX_DEPTH } = require('../notebook-nb.cjs');
const { validateDocument } = require('../notebook-model.cjs');

function input(boxes, options = '') {
  return `Notebook[{Cell[BoxData[${boxes}], "Input"${options}]}]`;
}

test('imports the independently authored fixture, flattens groups and retains history', () => {
  const source = fs.readFileSync(path.join(__dirname, '../examples/advanced.nb'), 'utf8');
  const { document, warnings } = fromNotebook(source, 'Advanced');
  const validated = validateDocument(document);
  assert.deepEqual(document.cells, validated.cells);
  assert.equal(document.id, validated.id);
  assert.equal(document.title, 'Advanced');
  assert.equal(document.cells[0].type, 'heading');
  assert.equal(document.cells[0].source, '基础 .nb 互操作示例');
  const algebra = document.cells.find(cell => cell.type === 'input' && cell.source.startsWith('Factor['));
  assert.equal(algebra.source, 'Factor[(x)^(2)-1]');
  assert.equal(algebra.result.text, '(x-1) (x+1)');
  assert.equal(algebra.result.suppressed, false);
  assert.ok(document.cells.some(cell => cell.source === '{{1,2},{3,4}}'));
  assert.ok(document.cells.some(cell => cell.source === 'Plot[Sin[x],{x,0,2 Pi}]'));
  assert.ok(warnings.some(warning => warning.includes('子集')));
  assert.ok(warnings.some(warning => warning.includes('初始化')));
  assert.ok(warnings.some(warning => warning.includes('平铺')));
});

test('supports plain text and Input/Code strings with quote and newline escapes', () => {
  const source = 'Notebook[{Cell["a\\n\\\"b\\\"\\\\c", "Text"], Cell["1+1", "Input"], Cell["2+2", "Code"]}]';
  const cells = fromNotebook(source).document.cells;
  assert.equal(cells[0].source, 'a\n"b"\\c');
  assert.equal(cells[1].type, 'input');
  assert.equal(cells[2].nbImport.style, 'Code');
  assert.equal(cells[1].result, undefined);
  assert.equal(cells[2].result, undefined);
});

test('nested comments and cache outlines never become cells; comment markers in strings remain text', () => {
  const source = '(* header (* inner "unterminated quote" *) *) Notebook[{Cell["(* literal *)", "Text"]}] (* Notebook[{Cell["fake", "Input"]}] *)';
  const cells = fromNotebook(source).document.cells;
  assert.equal(cells.length, 1);
  assert.equal(cells[0].source, '(* literal *)');
});

test('converts fractions, powers, roots, subscripts and rectangular grids', () => {
  const examples = [
    ['FractionBox[RowBox[{"a","+","b"}],"c"]', '(a+b)/(c)'],
    ['SuperscriptBox[RowBox[{"x","+","1"}],"2"]', '(x+1)^(2)'],
    ['SqrtBox["x"]', 'Sqrt[x]'],
    ['SubscriptBox["a","i"]', 'Subscript[a,i]'],
    ['GridBox[{{"a","b"},{"c","d"}},ColumnAlignments->Center]', '{{a,b},{c,d}}'],
    ['FormBox[SuperscriptBox["x","2"],StandardForm]', '(x)^(2)'],
  ];
  for (const [boxes, expected] of examples) assert.equal(fromNotebook(input(boxes)).document.cells[0].source, expected);
});

test('retains named and numeric Unicode escapes without JavaScript execution', () => {
  const cells = fromNotebook('Notebook[{Cell["\\:4e2d\\|01f600", "Text"],Cell[BoxData["\\[Alpha]+1"],"Input"]}]').document.cells;
  assert.equal(cells[0].source, '中😀');
  assert.equal(cells[1].source, '\\[Alpha]+1');
});

test('separates adjacent RowBox tokens and explicitly warns of interpretation limits', () => {
  const result = fromNotebook(input('RowBox[{"2","Pi"}]'));
  assert.equal(result.document.cells[0].source, '2 Pi');
  assert.ok(result.warnings.some(warning => warning.includes('隐式乘法')));
  const nested = fromNotebook(input('RowBox[{"x","*",RowBox[{"a","+","b"}]}]'));
  assert.ok(nested.warnings.some(warning => warning.includes('复杂分组')));
  assert.ok(nested.document.cells[0].nbImport.original.includes('RowBox'));
});

test('unknown or semantically ambiguous boxes retain the full original Cell as non-executable text', () => {
  for (const boxes of ['TemplateBox[{"x"},"unknown"]', 'InterpretationBox["safe",Run["danger"]]',
    'FormBox["x",TraditionalForm]', 'SuperscriptBox["f","\\[Prime]"]', 'GridBox[{{"1"},{"2","3"}}]']) {
    const source = input(boxes);
    const result = fromNotebook(source);
    assert.equal(result.document.cells[0].type, 'text');
    assert.equal(result.document.cells[0].source, `Cell[BoxData[${boxes}], "Input"]`);
    assert.ok(result.warnings.some(warning => warning.includes('原始 Cell')));
  }
});

test('rich text flattens supported text styles and inline Cells', () => {
  const source = 'Notebook[{Cell[TextData[{"A", StyleBox["B",Bold],Cell[BoxData[SuperscriptBox["x","2"]]]}],"Text"]}]';
  assert.equal(fromNotebook(source).document.cells[0].source, 'AB(x)^(2)');
});

test('Output history is text only, preserves multiple outputs and handles orphan output', () => {
  const source = 'Notebook[{Cell["orphan","Output"],Cell[BoxData["x+1"],"Input"],Cell[BoxData["2"],"Output"],Cell["3","Output"]}]';
  const cells = fromNotebook(source).document.cells;
  assert.equal(cells.length, 2);
  assert.equal(cells[0].type, 'text');
  assert.equal(cells[1].result.text, '2\n\n3');
  assert.equal(cells[1].nbImport.outputs.length, 2);
});

test('exports Print and Message history as quoted cells and reimports text without execution', () => {
  const prints = ['a "quoted" print', 'Run["not executed"] (* literal *)'];
  const messages = [{ kind: 'message', text: 'Power::infy: warning \\ path' }];
  const document = validateDocument({ format: 'mathematics-notebook', version: 1, title: 'History', cells: [
    { id: 'history', type: 'input', source: '1+1', result: { text: '2', prints, messages, suppressed: false } },
  ] });
  const source = toNotebook(document);
  assert.match(source, /, "Print"\]/);
  assert.match(source, /, "Message"\]/);
  assert.ok(source.includes('Run[\\"not executed\\"]'));
  const reread = fromNotebook(source).document;
  assert.equal(reread.cells.length, 1);
  assert.deepEqual(reread.cells[0].result.prints, prints);
  assert.deepEqual(reread.cells[0].result.messages.map(message => message.text), messages.map(message => message.text));
  assert.equal(reread.cells[0].result.text, '2');
  assert.equal(reread.cells[0].nbImport.outputs.length, 4);
});

test('rejects an import whose decoded text and archival records exceed native save capacity', () => {
  const source = `Notebook[{${Array(80).fill(`Cell["${'x'.repeat(40000)}","Text"]`).join(',')}}]`;
  assert.ok(Buffer.byteLength(source) < MAX_BYTES);
  assert.throws(() => fromNotebook(source), /转换后.*8 MiB/);
});

test('valid near-limit text survives export wrapping and quoted archive reimport', () => {
  const original = 'x'.repeat(99990);
  const document = validateDocument({ format: 'mathematics-notebook', version: 1, title: 'Long text', cells: [
    { id: 'long-text', type: 'text', source: original },
  ] });
  const source = toNotebook(document);
  const reread = fromNotebook(source).document;
  assert.equal(reread.cells[0].source, original);
  assert.ok(reread.cells[0].nbImport.original.length > 100000);
  assert.equal(fromNotebook(toNotebook(reread)).document.cells[0].source, original);
});

test('import never evaluates initialization cells, notebook event handlers or payload strings', () => {
  const childProcess = require('node:child_process');
  const saved = { exec: childProcess.exec, spawn: childProcess.spawn, eval: global.eval };
  childProcess.exec = childProcess.spawn = global.eval = () => { throw new Error('Execution is forbidden'); };
  try {
    const source = 'Notebook[{Cell[BoxData[RowBox[{"Run","[","\\\"touch /tmp/notebook-payload\\\"","]"}]],"Input",InitializationCell->True,CellProlog:>Run["anything"]]},NotebookEventActions->{"WindowOpen":>Run["anything"]}]';
    const imported = fromNotebook(source);
    assert.equal(imported.document.cells[0].type, 'input');
    assert.ok(imported.warnings.some(warning => warning.includes('初始化')));
    const exported = toNotebook(imported.document);
    assert.ok(exported.includes('InitializationCell -> False'));
    assert.ok(!exported.includes('InitializationCell->True'));
    assert.ok(!exported.includes('NotebookEventActions'));
    assert.ok(!exported.includes('CellProlog'));
  } finally { childProcess.exec = saved.exec; childProcess.spawn = saved.spawn; global.eval = saved.eval; }
});

test('roundtrips supported documents, titles, styles, exact input and history as text', () => {
  const original = fromNotebook('Notebook[{Cell["Heading","Title"],Cell["text\\n中文","Text"],Cell[BoxData["f[x_]:=x^2"],"Code"],Cell["Null","Output"]}]', 'A "quoted" title').document;
  const serialized = toNotebook(original);
  const reread = fromNotebook(serialized, original.title).document;
  assert.deepEqual(reread.cells.map(c => [c.type, c.source, c.result?.text]), original.cells.map(c => [c.type, c.source, c.result?.text]));
  assert.equal(reread.cells[0].nbImport.style, 'Title');
  assert.equal(reread.cells[2].nbImport.style, 'Code');
  assert.ok(serialized.includes('WindowTitle -> "A \\"quoted\\" title"'));
});

test('an unsupported archived Cell is exported as a quoted Text cell, never an active box', () => {
  const imported = fromNotebook(input('ButtonBox["click",ButtonFunction:>Run["danger"]]'));
  const exported = toNotebook(imported.document);
  const reread = fromNotebook(exported);
  assert.equal(reread.document.cells[0].type, 'text');
  assert.equal(reread.document.cells[0].source, imported.document.cells[0].source);
});

test('empty notebooks and System context heads are accepted', () => {
  assert.equal(fromNotebook('Notebook[{}]').document.cells.length, 0);
  assert.equal(fromNotebook('System`Notebook[{System`Cell["a","Text"]}]').document.cells[0].source, 'a');
});

test('malformed files fail instead of yielding partial notebooks', () => {
  for (const source of ['', 'Notebook[', 'Notebook[{Cell["x","Text"]}', 'Notebook[{Cell["x","Text"]},]',
    'Notebook[{Cell["unterminated,"Text"]}]', '(* comment', 'Notebook[{Cell[]}]',
    'Notebook[{},]', 'Notebook[{}]; Run["anything"]', 'Run[Notebook[{}]]', 'Notebook[{Cell["x","Text"]]]',
    'Notebook[{Cell["\\:zzzz","Text"]}]', 'Notebook[{Cell["\\|ffffff","Text"]}]']) {
    assert.throws(() => fromNotebook(source), undefined, source);
  }
});

test('file byte, nesting, comment and cell size limits fail safely', () => {
  assert.throws(() => fromNotebook(' '.repeat(MAX_BYTES + 1)), /8 MiB/);
  assert.throws(() => fromNotebook(`Notebook[{Cell["${'中'.repeat(100001)}","Text"]}]`), /100000/);
  assert.throws(() => fromNotebook(`Notebook[{${'{'.repeat(MAX_DEPTH)}'a'${'}'.repeat(MAX_DEPTH)}}]`), /嵌套/);
  assert.throws(() => fromNotebook(`${'(*'.repeat(MAX_DEPTH + 1)}${'*)'.repeat(MAX_DEPTH + 1)} Notebook[{}]`), /注释嵌套/);
  assert.throws(() => fromNotebook(`Notebook[{${Array(2001).fill('Cell["a","Text"]').join(',')}}]`), /2000/);
  assert.throws(() => fromNotebook(`Notebook[{${Array(2001).fill('unknown').join(',')}}]`), /2000/);
  assert.throws(() => fromNotebook(`Notebook[{},TaggingRules->{${Array(250001).fill('0').join(',')}}]`), /结构节点/);
  assert.equal(fromNotebook(`Notebook[{${Array(2000).fill('Cell["a","Text"]').join(',')}}]`).document.cells.length, 2000);
});

test('export escapes control characters and rejects oversized output/cell collections', () => {
  const doc = validateDocument({ format: 'mathematics-notebook', version: 1, title: 'T', cells: [{ id: 'c', type: 'text', source: '\u0000\b\f\t\r\n"\\' }] });
  assert.equal(fromNotebook(toNotebook(doc)).document.cells[0].source, doc.cells[0].source);
  const long = validateDocument({ format: 'mathematics-notebook', version: 1, cells: [{ id: 'c', type: 'input', source: '1', result: { text: 'a'.repeat(100001) } }] });
  assert.throws(() => toNotebook(long), /输出文本过长/);
  const tooMany = validateDocument({ format: 'mathematics-notebook', version: 1, cells: Array.from({ length: 2000 }, (_, i) => ({ id: String(i), type: 'input', source: '1', result: { text: '1' } })) });
  assert.throws(() => toNotebook(tooMany), /2000/);
});
