"""Series via SymPy's series(), falling back to the native Mathics expansion.

Mathics 10.0.1 builds ``Series[f, {x, x0, n}]`` by differentiating ``f`` n times
symbolically and substituting ``x -> x0`` into each derivative.  That fails in
two common situations Mathematica handles:

* removable singularities such as ``x/(Exp[x] - 1)`` at 0 — every derivative is
  0/0 at the expansion point and the evaluator recurses until
  ``RecursionError``;
* poles such as ``1/x + x`` — the native code has no Laurent-series path.

SymPy's ``series(f, x, x0, n)`` handles both and returns ``a_k (x-x0)^k`` terms
with integer ``k`` (possibly negative) plus ``O((x-x0)^n)``.  This override
converts that into the ``SeriesData[x, x0, {coeffs}, nmin, nmax, 1]`` form the
rest of Mathics expects, and only when the SymPy result is a clean power
series; anything else (fractional powers, logs, symbolic order) is left to the
native builtin so existing behaviour is unchanged.
"""

from __future__ import annotations

import sympy

from mathics.builtin.numbers.calculus import Series
from mathics.core.atoms import Integer
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol as MSymbol

SymbolSeriesData = MSymbol("System`SeriesData")


def _power_series_terms(expr: sympy.Expr, x: sympy.Symbol, x0: sympy.Expr):
    """Return ({k: coeff}, order_n) if expr is  sum a_k (x-x0)^k + O((x-x0)^n)  with integer k."""
    order_n = None
    terms = {}
    shift = x - x0
    for term in sympy.Add.make_args(expr):
        if isinstance(term, sympy.Order):
            # O((x-x0)**n) or O(1) ; Order.expr is the leading power
            oexpr = term.expr
            if oexpr == 1:
                order_n = 0
            else:
                base, exp = oexpr.as_base_exp()
                if base != shift or not exp.is_Integer:
                    return None
                order_n = int(exp)
            continue
        coeff, rest = term.as_independent(x, as_Add=False)
        if rest == 1:
            k = 0
        else:
            base, exp = rest.as_base_exp()
            if base != shift or not exp.is_Integer:
                return None
            k = int(exp)
        if coeff.has(x):
            return None
        terms[k] = terms.get(k, 0) + coeff
    # SymPy drops the O-term when the expansion is exact (e.g. 1/x + x); the
    # caller then supplies the requested order.
    return terms, order_n


class SeriesWithSympy(Series):
    name = "Series"
    context = "System`"

    def eval_series(self, f, x, x0, n, evaluation):
        """Series[f_, {x_Symbol, x0_, n_Integer}]"""
        sym = self._sympy_series(f, x, x0, n, evaluation)
        if sym is not None:
            return sym
        return super().eval_series(f, x, x0, n, evaluation)

    def _sympy_series(self, f, x, x0, n, evaluation):
        order = n.get_int_value()
        if order is None or order < 0 or order > 200:
            return None
        f_eval = f.evaluate(evaluation)
        f_s = f_eval.to_sympy(convert_all_global_functions=True)
        x_s = x.to_sympy()
        x0_s = x0.evaluate(evaluation).to_sympy()
        if any(v is None for v in (f_s, x_s, x0_s)) or not isinstance(f_s, sympy.Expr) or not isinstance(x_s, sympy.Symbol):
            return None
        if not f_s.has(x_s):
            return None
        try:
            # Mathematica's n is the highest power kept; SymPy's n is the order of the O-term.
            expanded = sympy.series(f_s, x_s, x0_s, order + 1)
        except (ValueError, NotImplementedError, TypeError, ZeroDivisionError, sympy.PoleError, RecursionError):
            return None
        if expanded is None or expanded.has(sympy.nan, sympy.zoo):
            return None
        parsed = _power_series_terms(sympy.expand(expanded), x_s, x0_s)
        if parsed is None:
            return None
        terms, order_n = parsed
        if order_n is None:
            # Exact expansion: truncate to the requested order ourselves
            # (native Series mis-renders an all-zero truncation such as x^7 to O[x]^4).
            order_n = order + 1
            terms = {k: c for k, c in terms.items() if k < order_n}
        if not terms:
            nmin = order_n
            coeffs = []
        else:
            nmin = min(terms)
            if nmin > order_n:
                return None
            coeffs = [terms.get(k, sympy.Integer(0)) for k in range(nmin, order_n)]
        return Expression(
            SymbolSeriesData,
            x,
            from_sympy(x0_s),
            ListExpression(*(from_sympy(sympy.nsimplify(c) if c.is_number else c) for c in coeffs)),
            Integer(nmin),
            Integer(order_n),
            Integer(1),
        )


def register_series(session):
    SeriesWithSympy(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Series")
