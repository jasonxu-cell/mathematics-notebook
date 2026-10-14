/* Presentation only: retain the kernel's Wolfram Language source and results. */
(function (root) {
  'use strict';
  // Symbols spelled as Greek letter names (nu, alpha, Omega, …) display as the
  // letter itself, as they would after typing \[Nu] in Mathematica. Only exact
  // whole-name matches are converted; alpha1 or Beta[ ] (the function) are not.
  const GREEK = {
    alpha: '\\alpha', beta: '\\beta', gamma: '\\gamma', delta: '\\delta', epsilon: '\\epsilon',
    varepsilon: '\\varepsilon', zeta: '\\zeta', eta: '\\eta', theta: '\\theta', vartheta: '\\vartheta',
    iota: '\\iota', kappa: '\\kappa', lambda: '\\lambda', mu: '\\mu', nu: '\\nu', xi: '\\xi',
    omicron: 'o', pi: '\\pi', varpi: '\\varpi', rho: '\\rho', varrho: '\\varrho', sigma: '\\sigma',
    varsigma: '\\varsigma', tau: '\\tau', upsilon: '\\upsilon', phi: '\\phi', varphi: '\\varphi',
    chi: '\\chi', psi: '\\psi', omega: '\\omega',
    Gamma: '\\Gamma', Delta: '\\Delta', Theta: '\\Theta', Lambda: '\\Lambda', Xi: '\\Xi',
    Pi: '\\Pi', Sigma: '\\Sigma', Upsilon: '\\Upsilon', Phi: '\\Phi', Psi: '\\Psi', Omega: '\\Omega',
  };
  // Built-in function heads that happen to be Greek names must keep their text form.
  const BUILTIN_HEADS = new Set(['Gamma', 'Beta', 'Zeta', 'Pi', 'Xi', 'Psi']);
  function greekForDisplay(latex) {
    return latex.replace(/\\text\{([A-Za-z]+)\}(\s*\[)?/g, (match, name, bracket) => {
      if (!(name in GREEK)) return match;
      if (bracket && BUILTIN_HEADS.has(name)) return match;
      return GREEK[name] + (bracket || '');
    });
  }

  // Mathics boxes a Real in scientific notation as RowBox[man, "*^", exp],
  // whose TeX comes out as the literal `1.234\text{*${}^{\wedge}$}-5`. Show it
  // as 1.234 × 10⁻⁵, the way Mathematica typesets machine numbers.
  function scientificNotationForDisplay(latex) {
    return latex.replace(
      /(-?\d+(?:\.\d*)?)\\text\{\*\$\{\}\^\{\\wedge\}\$\}(-?\d+)/g,
      '$1\\times10^{$2}'
    );
  }

  function latexForDisplay(value) {
    const latex = greekForDisplay(scientificNotationForDisplay(String(value)));
    let output = '';
    for (let at = 0; at < latex.length;) {
      if (latex[at] === '\\') {
        const command = /^\\(?:[A-Za-z]+|[^])/u.exec(latex.slice(at))?.[0] || '\\';
        output += command;
        at += command.length;
        // Text, names and explicit font groups must keep their literal spelling.
        if (/^\\(?:text[A-Za-z]*|operatorname|mbox|hbox|mathrm|mathit|mathbf|mathsf|mathtt|mathbb|mathcal|mathfrak|mathscr)$/.test(command)) {
          const start = at;
          while (/\s/.test(latex[at] || '') && at < latex.length) at++;
          if (latex[at] === '*') at++;
          if (latex[at] === '{') {
            let depth = 1;
            at++;
            while (at < latex.length && depth > 0) {
              if (latex[at] === '\\') { at += Math.min(2, latex.length - at); continue; }
              if (latex[at] === '{') depth++;
              if (latex[at] === '}') depth--;
              at++;
            }
          }
          output += latex.slice(start, at);
        }
        continue;
      }
      // Standalone I / E are the imaginary unit and Euler's number: show them
      // as Mathematica does (i, e). Letters inside names stay untouched; the
      // kernel wraps multi-letter names such as ExpIntegralEi in \text{...},
      // which the branch above copies verbatim.
      const standalone = (latex[at] === 'I' || latex[at] === 'E')
        && !/[A-Za-z0-9]/.test(latex[at - 1] || '')
        && !/[A-Za-z0-9]/.test(latex[at + 1] || '');
      output += standalone ? latex[at].toLowerCase() : latex[at];
      at++;
    }
    return output;
  }
  const api = { latexForDisplay };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NotebookMathDisplay = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
