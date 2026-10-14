"""DiscreteLimit that reduces trig arguments modulo π·n before asking SymPy.

The upstream builtin calls ``sympy.limit_seq`` and, when that raises, returns
``None`` *inside a path that has already replaced the summand*, so the notebook
shows an empty result flagged as "suppressed".  Two fixes:

* Never return an empty result: anything SymPy cannot do comes back as the
  unevaluated ``DiscreteLimit[...]``, like Mathematica.
* Sequences of the form ``trig(π·g(n))`` with ``g(n) = n + h(n)``, ``h`` bounded,
  are rewritten using ``sin(πn + πh) = (−1)^n sin(πh)``, ``cos(πn + πh) =
  (−1)^n cos(πh)``, ``tan(πn + πh) = tan(πh)``.  If the sign factors cancel
  (even powers, products of pairs) the limit of the reduced expression is
  returned; if they do not and the reduced limit is non-zero the sequence has
  no limit, so the expression is left unevaluated.

Example:  DiscreteLimit[Sin[π √(n²+n)]², n → ∞] = 1, because
          √(n²+n) = n + ½ − 1/(8n) + … and sin²(πn + π/2 − …) → cos²(0) = 1.
"""

from __future__ import annotations

import sympy

from mathics.builtin.numbers.calculus import DiscreteLimit
from mathics.core.convert.sympy import from_sympy


def _reduce_mod_pi_n(expr, n):
    """Return (reduced_expr, sign_parity) where expr == (-1)^(sign_parity*n) * reduced for integer n."""
    sgn = sympy.Dummy("sgn")

    def visit(t):
        arg = t.args[0]
        g = sympy.simplify(arg / sympy.pi)
        if not g.has(n):
            return t
        try:
            k = sympy.limit(g - n, n, sympy.oo)
        except Exception:
            return t
        if k is None or not k.is_finite:
            # maybe g ~ m*n for integer m
            try:
                m = sympy.limit(g / n, n, sympy.oo)
            except Exception:
                return t
            if not (m.is_Integer and m != 0):
                return t
            h = g - m * n
            try:
                if not sympy.limit(h, n, sympy.oo).is_finite:
                    return t
            except Exception:
                return t
            parity = int(m) % 2
        else:
            h = g - n
            parity = 1
        reduced = t.func(sympy.pi * h)
        if isinstance(t, sympy.tan) or parity == 0:
            return reduced
        return sgn * reduced

    new = expr.replace(lambda t: isinstance(t, (sympy.sin, sympy.cos, sympy.tan)), visit)
    return new, sgn


class DiscreteLimitReduced(DiscreteLimit):
    name = "DiscreteLimit"
    context = "System`"

    def eval(self, f, n, n0, evaluation, options={}):
        "DiscreteLimit[f_, n_->n0_, OptionsPattern[DiscreteLimit]]"
        f_s = f.to_sympy(convert_all_global_functions=True)
        n_s = n.to_sympy()
        n0_s = n0.to_sympy()
        if f_s is None or n_s is None or n0_s != sympy.oo:
            return None
        n_int = sympy.Dummy(n_s.name, integer=True, positive=True)
        f_s = f_s.subs(n_s, n_int)

        def finite_limit(e):
            for fn in (lambda: sympy.limit_seq(e, n_int), lambda: sympy.limit(e, n_int, sympy.oo)):
                try:
                    r = fn()
                except Exception:
                    continue
                if r is None or isinstance(r, (sympy.Limit, sympy.AccumBounds)) or r.has(sympy.Limit, sympy.nan, sympy.AccumBounds):
                    continue
                if any(isinstance(s, sympy.Dummy) for s in r.free_symbols):
                    continue
                return r
            return None

        r = finite_limit(f_s)
        if r is not None:
            return from_sympy(r)

        reduced, sgn = _reduce_mod_pi_n(f_s, n_int)
        if reduced == f_s:
            return None
        # expand only the polynomial structure in sgn, never the trig arguments
        reduced = sympy.expand(reduced, deep=False, trig=False, log=False, power_base=False, power_exp=False, mul=True, multinomial=True)
        if reduced.has(sgn):
            # sign factors survive only if the (-1)^n dependence is real
            even = reduced.subs(sgn, 1)
            odd = reduced.subs(sgn, -1)
            if sympy.simplify(even - odd) != 0:
                le, lo = finite_limit(even), finite_limit(odd)
                if le is not None and lo is not None and sympy.simplify(le - lo) == 0:
                    return from_sympy(le)
                return None  # oscillates: no limit
            reduced = even
        r = finite_limit(reduced)
        return from_sympy(r) if r is not None else None


def register_discrete_limit(session):
    DiscreteLimitReduced(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`DiscreteLimit")
