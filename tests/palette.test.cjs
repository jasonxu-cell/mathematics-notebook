'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { filterFunctions, insertionFor } = require('../renderer/palette.js');

const index = [
  { name: 'LaplaceTransform', summary: 'Laplace transform', signatures: ['LaplaceTransform[f, t, s]'], category: '积分变换' },
  { name: 'InverseLaplaceTransform', summary: 'inverse Laplace transform', signatures: [], category: '积分变换' },
  { name: 'Plot', summary: 'plot curves of one or more functions', signatures: ['Plot[f, {x, x_min, x_max}]'], category: '绘图' },
  { name: 'Factor', summary: 'factor a polynomial', signatures: [], category: '代数' },
];

test('exact and prefix matches rank before substring and summary matches', () => {
  const results = filterFunctions(index, 'lap');
  assert.equal(results[0].name, 'LaplaceTransform');
  assert.equal(results[1].name, 'InverseLaplaceTransform');
  assert.deepEqual(filterFunctions(index, 'plot').map((e) => e.name), ['Plot']);
});

test('filtering is case-insensitive and name matches beat summary matches', () => {
  const results = filterFunctions(index, 'TRANSFORM');
  assert.deepEqual(results.map((e) => e.name), ['InverseLaplaceTransform', 'LaplaceTransform']);
  // "factor" matches the Factor name (rank 1); a summary-only hit would rank 3.
  assert.deepEqual(filterFunctions(index, 'factor').map((e) => e.name), ['Factor']);
});

test('empty query returns the leading entries unfiltered', () => {
  assert.equal(filterFunctions(index, '').length, index.length);
  assert.equal(filterFunctions(index, '   ').length, index.length);
  assert.equal(filterFunctions([...index, ...index], '', 3).length, 3);
});

test('no match yields an empty list', () => {
  assert.deepEqual(filterFunctions(index, 'zzz-no-such-function'), []);
});

test('insertion prefers the first signature, falls back to an open call', () => {
  assert.equal(insertionFor(index[0]), 'LaplaceTransform[f, t, s]');
  assert.equal(insertionFor(index[3]), 'Factor[');
});
