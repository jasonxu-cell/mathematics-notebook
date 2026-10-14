const fs = require('node:fs/promises');
const crypto = require('node:crypto');

const queues = new Map();
const MAX_DOCUMENT_BYTES = 8 * 1024 * 1024;

function serializeDocument(document, pretty = false) {
  const data = JSON.stringify(document, null, pretty ? 2 : undefined) + '\n';
  if (Buffer.byteLength(data, 'utf8') > MAX_DOCUMENT_BYTES) {
    throw new Error('笔记本过大（最多 8 MB），请减少单元或图形输出后保存。');
  }
  return data;
}

function atomicWrite(destination, data) {
  const previous = queues.get(destination) || Promise.resolve();
  const operation = previous.catch(() => {}).then(async () => {
    const temporary = `${destination}.tmp-${crypto.randomUUID()}`;
    try {
      await fs.writeFile(temporary, data, { mode: 0o600 });
      await fs.rename(temporary, destination);
    } finally { await fs.rm(temporary, { force: true }); }
  });
  queues.set(destination, operation);
  const finished = () => { if (queues.get(destination) === operation) queues.delete(destination); };
  operation.then(finished, finished);
  return operation;
}

async function drainWrites() { await Promise.allSettled([...queues.values()]); }

module.exports = { atomicWrite, serializeDocument, drainWrites, MAX_DOCUMENT_BYTES };
