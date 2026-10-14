'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { DynamicCoordinator } = require('../renderer/dynamic-coordinator.js');
const { normalizeGeometry } = require('../renderer/graphics3d.js');

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function harness(t) {
  const requests = [], applied = [], errors = [];
  let active = 0, maximumActive = 0, allowed = true, source = 'a^2';
  const coordinator = new DynamicCoordinator({
    // Control transport completion explicitly. A long debounce prevents real
    // timers racing the assertions; flush() advances each dispatch boundary.
    delay: 10_000,
    run(job) {
      active++; maximumActive = Math.max(maximumActive, active);
      const pending = deferred();
      requests.push({ job, ...pending });
      return pending.promise.finally(() => { active--; });
    },
    canRun: () => allowed,
    valid: (job) => job.source === source,
    onStart() {},
    onResult: (job, result) => applied.push({ job, result }),
    onError: (job, error, current) => errors.push({ job, error, current }),
    onFinish() {}
  });
  t.after(() => coordinator.dispose());
  const request = (value, requestSource = source) => coordinator.request({ key: 'cell-1', notebookId: 'notebook-1', source: requestSource, controls: { a: value } });
  return { coordinator, requests, applied, errors, request, setAllowed: (value) => { allowed = value; }, setSource: (value) => { source = value; }, maximumActive: () => maximumActive };
}

test('rapid changes send one request containing the latest parameter snapshot', async (t) => {
  const h = harness(t);
  const controls = { a: 1 };
  h.coordinator.request({ key: 'cell-1', notebookId: 'notebook-1', source: 'a^2', controls });
  controls.a = 99;
  h.request(2); h.request(3);
  const dispatch = h.coordinator.flush();
  assert.equal(h.requests.length, 1);
  assert.deepEqual(h.requests[0].job.controls, { a: 3 });
  h.requests[0].resolve({ text: '9' }); await dispatch;
  assert.deepEqual(h.applied.map((item) => item.result.text), ['9']);
});

test('requests wait for an external notebook run and never overlap one another', async (t) => {
  const h = harness(t);
  h.setAllowed(false); h.request(1); await h.coordinator.flush();
  assert.equal(h.requests.length, 0);
  h.setAllowed(true);
  const first = h.coordinator.flush();
  h.request(2); await h.coordinator.flush(); await h.coordinator.flush();
  assert.equal(h.requests.length, 1);
  h.requests[0].resolve({ text: '1' }); await first;
  const second = h.coordinator.flush();
  assert.equal(h.requests.length, 2);
  h.requests[1].resolve({ text: '4' }); await second;
  assert.equal(h.maximumActive(), 1);
});

test('a running old response is discarded and only the latest replacement is applied', async (t) => {
  const h = harness(t);
  h.request(1); const first = h.coordinator.flush();
  h.request(2); h.request(4);
  h.requests[0].resolve({ text: 'obsolete' }); await first;
  assert.equal(h.applied.length, 0);
  const latest = h.coordinator.flush();
  assert.equal(h.requests.length, 2);
  assert.deepEqual(h.requests[1].job.controls, { a: 4 });
  h.requests[1].resolve({ text: '16' }); await latest;
  assert.deepEqual(h.applied.map((item) => item.result.text), ['16']);
});

test('editing source invalidates a running response and a pending request', async (t) => {
  const h = harness(t);
  h.request(1); const running = h.coordinator.flush();
  h.request(2); h.setSource('a^3');
  h.requests[0].resolve({ text: 'old source' }); await running;
  await h.coordinator.flush();
  assert.equal(h.applied.length, 0);
  assert.equal(h.requests.length, 1);
  h.request(3); const current = h.coordinator.flush();
  h.requests[1].resolve({ text: '27' }); await current;
  assert.deepEqual(h.applied.map((item) => item.result.text), ['27']);
  assert.equal(h.applied[0].job.source, 'a^3');
});

test('cancel clears pending updates and suppresses the response still in flight', async (t) => {
  const h = harness(t);
  h.request(1); const running = h.coordinator.flush();
  h.request(2); h.request(3); h.coordinator.clear();
  assert.equal(h.coordinator.pending.size, 0);
  assert.equal(h.coordinator.timer, null);
  h.requests[0].resolve({ text: 'cancelled work' }); await running;
  await h.coordinator.flush();
  assert.equal(h.requests.length, 1);
  assert.equal(h.applied.length, 0);
  h.request(4); const afterCancel = h.coordinator.flush();
  h.requests[1].resolve({ text: '16' }); await afterCancel;
  assert.deepEqual(h.applied.map((item) => item.result.text), ['16']);
});

test('transport rejection stops the failed request and permits the next update', async (t) => {
  const h = harness(t);
  h.request(1); const first = h.coordinator.flush();
  h.requests[0].reject(new Error('kernel unavailable')); await first;
  assert.equal(h.errors.length, 1);
  assert.equal(h.errors[0].current, true);
  h.request(2); const second = h.coordinator.flush();
  h.requests[1].resolve({ text: '4' }); await second;
  assert.deepEqual(h.applied.map((item) => item.result.text), ['4']);
});

test('geometry keeps data coordinates and remaps colors after invalid faces are removed', () => {
  const geometry = normalizeGeometry({
    vertices: [[0, 0, 0], [2, 0, 0], [0, 3, 4]],
    faces: [[0, 1, 9], [0, 1, 2]],
    lines: [[[0, 0, 0], [5, 2, 1]]], points: [[-1, 0, 0]],
    colors: { faces: [[0, 0, 1], [1, 0, 0]], lines: [[0, 1, 0]], points: [[1, 1, 0]] }
  });
  assert.deepEqual(geometry.faces, [[0, 1, 2]]);
  assert.deepEqual(geometry.vertices[2], [0, 3, 4]);
  assert.deepEqual(geometry.colors.faces, [[1, 0, 0]]);
  assert.deepEqual(geometry.bounds, [[-1, 5], [0, 3], [0, 4]]);
});

test('geometry rejects empty, nonfinite, and oversized data', () => {
  assert.throws(() => normalizeGeometry({}), /没有可显示/);
  assert.throws(() => normalizeGeometry({ points: [[NaN, 0, 1], [Infinity, 0, 1]] }), /没有可显示/);
  assert.throws(() => normalizeGeometry({ vertices: Array(50_001).fill([0, 0, 0]) }), /显示上限/);
  assert.throws(() => normalizeGeometry({ lines: [Array(50_001).fill([0, 0, 0])] }), /显示上限/);
});
