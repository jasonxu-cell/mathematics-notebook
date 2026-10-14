"""Closed forms for Dirichlet-type series that SymPy's summation() leaves unevaluated.

Wolfram evaluates  Sum[Log[n]^k / n^s, {n, 1, Infinity}]  to  (-1)^k Zeta^(k)[s]
(and the leading-coefficient / shifted-start variants).  SymPy 1.14 has no such
rule, so the pinned Mathics engine returns the sum unchanged.  This module adds
exactly that family on top of the native Sum, leaving every other sum untouched.

Mathematical basis:  zeta(s) = sum n^-s  =>  d^k/ds^k zeta(s) = sum (-ln n)^k n^-s,
valid for Re(s) > 1 (absolute convergence).  For symbolic s the result is
returned unconditionally, as Wolfram does; for numeric s <= 1 the sum is left
unevaluated because it diverges.
"""

from __future__ import annotations

import sympy
from sympy import Symbol, oo

from mathics.builtin.arithmetic import Sum
from mathics.core.atoms import Integer
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.symbols import Symbol as MSymbol, SymbolPlus, SymbolTimes

SymbolDerivative = MSymbol("System`Derivative")
SymbolZeta = MSymbol("System`Zeta")


def _match_log_power(term: sympy.Expr, n: Symbol):
    """Return (coefficient, k, s) if term == coefficient * log(n)**k * n**(-s), else None.

    coefficient and s must be free of n; k is a non-negative integer.
    """
    coeff, rest = term.as_independent(n, as_Add=False)
    k = sympy.Integer(0)
    s = None
    for factor in sympy.Mul.make_args(rest):
        base, exp = factor.as_base_exp()
        if base == sympy.log(n):
            if not (exp.is_Integer and exp >= 0):
                return None
            k += exp
        elif base == n or base == 1 / n:
            # SymPy may present n^-s as (1/n)^s when s is symbolic.
            if exp.has(n) or s is not None:
                return None
            s = -exp if base == n else exp
        else:
            return None
    if s is None:
        return None
    return coeff, int(k), sympy.simplify(s)


def _closed_form(coeff: sympy.Expr, k: int, s: sympy.Expr, start: sympy.Expr):
    """Mathics expression  coeff * ((-1)^k Derivative[k][Zeta][s] - skipped head terms).

    Built directly as a Mathics expression: from_sympy cannot convert SymPy's
    Subs(Derivative(zeta(t), t), t, 2) form, and Mathics renders
    Derivative[k][Zeta][s] as Zeta'[s] / Zeta''[s] exactly like Wolfram.
    """
    if s.is_number:
        if not (s.is_real and s > 1):
            return None  # divergent (or complex with Re<=1): leave unevaluated
    zeta_k = Expression(Expression(Expression(SymbolDerivative, Integer(k)), SymbolZeta), from_sympy(s))
    sign = Integer(1) if k % 2 == 0 else Integer(-1)
    result = Expression(SymbolTimes, sign, zeta_k)
    # subtract the terms n = 1 .. start-1 when the lower bound is a small integer > 1
    if start != 1:
        if not (start.is_Integer and 1 < start <= 64):
            return None
        head = sum((sympy.log(m) ** k * sympy.Integer(m) ** (-s) for m in range(2, int(start))), sympy.Integer(0))  # log(1) = 0
        result = Expression(SymbolPlus, result, Expression(SymbolTimes, Integer(-1), from_sympy(head)))
    if coeff != 1:
        result = Expression(SymbolTimes, from_sympy(coeff), result)
    return result


def _match_bernoulli_egf(term: sympy.Expr, n: Symbol):
    """Match  c * bernoulli(u) * t**u / factorial(u)  with u = l*n + m (l in {1,2}).

    Returns (c, l, m, t) or None.  t is 1 when there is no power factor.
    """
    coeff, rest = term.as_independent(n, as_Add=False)
    u = None
    t = sympy.Integer(1)
    fact_seen = False
    bern_seen = False
    for factor in sympy.Mul.make_args(rest):
        base, exp = factor.as_base_exp()
        if isinstance(base, sympy.functions.combinatorial.numbers.bernoulli) and exp == 1 and len(base.args) == 1:
            if bern_seen:
                return None
            bern_seen = True
            arg = base.args[0]
        elif isinstance(base, sympy.factorial) and exp == -1:
            if fact_seen:
                return None
            fact_seen = True
            arg = base.args[0]
        elif not base.has(n) and exp.has(n):
            # t**u
            if t != 1:
                return None
            t = base
            arg = exp
        else:
            return None
        if u is None:
            u = arg
        elif sympy.simplify(u - arg) != 0:
            return None
    if not (bern_seen and fact_seen) or u is None:
        return None
    poly = sympy.Poly(sympy.expand(u), n)
    if poly.degree() != 1:
        return None
    l, m = poly.all_coeffs()
    if not (l.is_Integer and m.is_Integer and l in (1, 2) and m >= 0):
        return None
    return coeff, int(l), int(m), t


def _bernoulli_closed_form(coeff, l, m, t, start):
    """sum_{n>=start} B_u t^u / u!  with u = l n + m, from the generating function
    t/(e^t - 1) = sum_u B_u t^u/u!  (B_1 = -1/2 convention, matching this app's BernoulliB)."""
    if not (start.is_Integer and 0 <= start <= 64):
        return None
    first_u = l * int(start) + m
    if t == 1:
        t = sympy.Integer(1)
    if l == 1:
        total = t / (sympy.exp(t) - 1) if t != 1 else 1 / (sympy.E - 1)
        skipped = range(0, first_u)
    else:  # l == 2: even or odd indices only
        if m % 2 == 0:
            # sum over even u: t/(e^t-1) + t/2
            total = t / (sympy.exp(t) - 1) + t / 2 if t != 1 else 1 / (sympy.E - 1) + sympy.Rational(1, 2)
            skipped = range(0, first_u, 2)
        else:
            # odd u >= 3 are all zero; only u = 1 contributes B_1 = -1/2
            total = -t / 2 if t != 1 else sympy.Rational(-1, 2)
            skipped = range(1, first_u, 2)
    head = sum((sympy.bernoulli(u) * t**u / sympy.factorial(u) for u in skipped), sympy.Integer(0))
    # SymPy >= 1.12 uses B_1 = +1/2; this app's BernoulliB uses -1/2, so correct the head term.
    if 1 in skipped:
        head = head - t  # (+1/2 -> -1/2) * t^1 / 1!
    result = coeff * (total - head)
    # Prefer  rational + c/(e^t - 1)  over SymPy's merged fraction, e.g.
    # e/(e-1) - 3/2 rather than (-3+e)/(2(1-e)).  apart() needs a symbolic
    # generator: use exp(t) for symbolic t, E for t == 1, and for other numeric
    # t substitute a dummy for exp(t) first (exp(2) is not a valid generator).
    try:
        if t == 1:
            result = sympy.expand(sympy.apart(sympy.together(result), sympy.E))
        elif t.free_symbols:
            result = sympy.expand(sympy.apart(sympy.together(result), sympy.exp(t)))
        else:
            u = sympy.Dummy("u")
            r = sympy.together(result).subs(sympy.exp(t), u)
            result = sympy.expand(sympy.apart(r, u)).subs(u, sympy.exp(t))
    except (sympy.PolynomialError, NotImplementedError, ValueError):
        result = sympy.simplify(result)
    return from_sympy(result)


class SumWithDirichletSeries(Sum):
    """Native Sum, plus closed forms for Log[n]^k / n^s (Zeta derivatives)
    and Bernoulli exponential generating functions."""

    name = "Sum"
    context = "System`"

    def eval_iter_nostep(self, expr, i, imin, imax, evaluation):
        "%(name)s[expr_, {i_Symbol, imin_, imax_}]"
        closed = self._dirichlet(expr, i, imin, imax, evaluation)
        if closed is not None:
            return closed
        return super().eval_iter_nostep(expr, i, imin, imax, evaluation)

    def _dirichlet(self, expr, i, imin, imax, evaluation):
        imax_eval = imax.evaluate(evaluation)
        if imax_eval.get_name() != "System`Infinity" and not (
            imax_eval.has_form("DirectedInfinity", 1) and imax_eval.elements[0].get_int_value() == 1
        ):
            return None
        imin_eval = imin.evaluate(evaluation)
        start = imin_eval.to_sympy()
        if start is None or not isinstance(start, sympy.Expr):
            return None
        n = i.to_sympy()
        if not isinstance(n, Symbol):
            return None
        # The summand is held (Sum is HoldAll); evaluate it the way Sum would
        # before conversion so user definitions are honoured.
        summand = expr.evaluate(evaluation)
        term = summand.to_sympy(convert_all_global_functions=True)
        if term is None or not isinstance(term, sympy.Expr):
            return None
        matched = _match_log_power(term, n)
        if matched is not None:
            coeff, k, s = matched
            if k == 0:
                return None  # plain zeta sums already work natively
            return _closed_form(coeff, k, s, start)
        bern = _match_bernoulli_egf(term, n)
        if bern is not None:
            coeff, l, m, t = bern
            return _bernoulli_closed_form(coeff, l, m, t, start)
        return None


def register_dirichlet_sums(session):
    SumWithDirichletSeries(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Sum")
