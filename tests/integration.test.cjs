const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { KernelClient } = require('../kernel-client.cjs');
const { validateDocument, fromWolframLanguage } = require('../notebook-model.cjs');
const { atomicWrite, serializeDocument } = require('../disk-storage.cjs');
const fs = require('node:fs/promises');
const os = require('node:os');

test('document roundtrip preserves source and output; duplicate IDs are rejected', () => {
  const input = { format: 'mathematics-notebook', version: 1, id: 'book', title: '符号计算', cells: [
    { id: 'one', type: 'input', source: 'Factor[x^4-1]', result: { text: '(-1+x)(1+x)(1+x^2)' } },
    { id: 'two', type: 'text', source: '中文说明' },
  ] };
  const restored = validateDocument(JSON.parse(JSON.stringify(input)));
  assert.deepEqual(restored.cells, input.cells);
  assert.equal(restored.title, input.title);
  assert.throws(() => validateDocument({ ...input, cells: [input.cells[0], input.cells[0]] }), /重复/);
  assert.throws(() => validateDocument({ ...input, version: 2 }), /受支持/);
  assert.equal(fromWolframLanguage('x = 7;\nx^2', '计算.wl').cells[0].source, 'x = 7;\nx^2');
});

test('real kernel IPC, watchdog, cancellation and session reset', { timeout: 90000 }, async () => {
  const root = path.resolve(__dirname, '..');
  const client = new KernelClient({
    command: path.join(root, '.venv/bin/python'), args: [path.join(root, 'backend/kernel.py')],
    cwd: root, timeoutMs: 10000,
  });
  try {
    const status = await client.status();
    assert.equal(status.version, '10.0.1');
    assert.equal(status.ready, true);
    await client.request('evaluate', { source: 'watchdogToken = 23;', notebook_id: 'book' });
    assert.equal((await client.request('evaluate', { source: 'watchdogToken + 1', notebook_id: 'book' })).text, '24');
    client.options.timeoutMs = 700;
    await assert.rejects(client.request('evaluate', { source: 'Pause[5]; 99', notebook_id: 'book' }), /超时.*变量已清空/);
    client.options.timeoutMs = 10000;
    const afterTimeout = await client.request('evaluate', { source: 'watchdogToken', notebook_id: 'book' });
    assert.equal(afterTimeout.text, 'watchdogToken');
    await client.request('evaluate', { source: 'cancelToken = 42;', notebook_id: 'book' });
    const running = client.request('evaluate', { source: 'Pause[5]; 99', notebook_id: 'book' });
    const rejection = assert.rejects(running, /取消.*变量已清空/);
    await new Promise(resolve => setTimeout(resolve, 100));
    const busy = await client.status();
    assert.equal(busy.status, 'busy');
    await client.cancel();
    await rejection;
    assert.equal((await client.request('evaluate', { source: 'cancelToken', notebook_id: 'book' })).text, 'cancelToken');
    const result = await client.request('evaluate', { source: '2 + 3', notebook_id: 'book' });
    assert.equal(result.text, '5');
    assert.equal(result.line, 2);
  } finally { client.dispose(); }
});

test('overlapping disk writes preserve latest content and leave no temporary files', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'mathematics-storage-'));
  try {
    const destination = path.join(directory, 'draft.mnb');
    await Promise.all(Array.from({ length: 50 }, (_, index) => atomicWrite(destination, `${index}\n`)));
    assert.equal(await fs.readFile(destination, 'utf8'), '49\n');
    assert.deepEqual(await fs.readdir(directory), ['draft.mnb']);
    assert.throws(() => serializeDocument({ text: 'x'.repeat(8 * 1024 * 1024) }), /8 MB/);
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});
