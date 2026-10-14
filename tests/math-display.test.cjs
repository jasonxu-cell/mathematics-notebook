'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { latexForDisplay } = require('../renderer/math-display.js');

test('scientific notation renders as mantissa times ten to the exponent', () => {
  assert.equal(latexForDisplay('1.234567\\text{*${}^{\\wedge}$}6'), '1.234567\\times10^{6}');
  assert.equal(latexForDisplay('1.\\text{*${}^{\\wedge}$}-6'), '1.\\times10^{-6}');
  assert.equal(latexForDisplay('-1.\\text{*${}^{\\wedge}$}-7'), '-1.\\times10^{-7}');
});

test('scientific notation rewrites every occurrence inside a list', () => {
  assert.equal(
    latexForDisplay('\\left\\{1.\\text{*${}^{\\wedge}$}-5, 2.\\text{*${}^{\\wedge}$}7\\right\\}'),
    '\\left\\{1.\\times10^{-5}, 2.\\times10^{7}\\right\\}'
  );
});

test('plain decimals and surrounding exponents stay untouched', () => {
  assert.equal(latexForDisplay('0.00001'), '0.00001');
  assert.equal(latexForDisplay('3.\\text{*${}^{\\wedge}$}7 x^2'), '3.\\times10^{7} x^2');
});

test('greek names and standalone I / E still convert after the rewrite', () => {
  assert.equal(latexForDisplay('\\text{alpha}'), '\\alpha');
  assert.equal(latexForDisplay('1.\\text{*${}^{\\wedge}$}-6 + E I'), '1.\\times10^{-6} + e i');
});
