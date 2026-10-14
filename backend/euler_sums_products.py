"""Closed forms for Euler sums and rational infinite products that SymPy leaves open.

Sum:      Σ_{n≥1} c · H_n / n^q   (q ≥ 2 integer)
          = c · [ (1 + q/2) ζ(q+1) − ½ Σ_{k=1}^{q−2} ζ(k+1) ζ(q−k) ]      (Euler, 1775)
          e.g. q=2 → 2ζ(3),  q=3 → π⁴/72,  q=4 → 3ζ(5) − ζ(2)ζ(3).

Product:  Π_{n≥n₀} P(n)/Q(n) with P, Q polynomials of equal degree and
          leading coefficient whose root sums agree (so the product converges):
          = Π_j Γ(n₀ − q_j) / Π_i Γ(n₀ − p_i),   P = lc·Π(n − p_i), Q = lc·Π(n − q_j).
          e.g. Π(1 + 1/n²) = sinh π / π,   Π 4n²/(4n²−1) = π/2 (Wallis).

Both are registered on top of the overrides already installed for Sum, so the
Dirichlet / Bernoulli rules keep working; anything not matching falls through
to the native implementation unchanged.
"""

from __future__ import annotations

import sympy
from sympy import Symbol, oo

from mathics.builtin.arithmetic import Product
from mathics.core.convert.sympy import from_sympy

from dirichlet_sums import SumWithDirichletSeries


def _is_infinity(e, evaluation) -> bool:
    v = e.evaluate(evaluation)
    return v.get_name() == "System`Infinity" or (
        v.has_form("DirectedInfinity", 1) and v.elements[0].get_int_value() == 1
    )


def _summand(expr, i, evaluation):
    n = i.to_sympy()
    if not isinstance(n, Symbol):
        return None, None
    term = expr.evaluate(evaluation).to_sympy(convert_all_global_functions=True)
    if term is None or not isinstance(term, sympy.Expr):
        return None, None
    return term, n


# ---------------------------------------------------------------------------
# Euler sums
# ---------------------------------------------------------------------------

def euler_sum_closed_form(q: int):
    """Σ_{n≥1} H_n / n^q for integer q ≥ 2."""
    z = sympy.zeta
    total = (1 + sympy.Rational(q, 2)) * z(q + 1)
    total -= sympy.Rational(1, 2) * sum((z(k + 1) * z(q - k) for k in range(1, q - 1)), sympy.Integer(0))
    return sympy.expand_func(total)


def _match_euler_sum(term, n):
    """c * harmonic(n) * n**(-q)  ->  (c, q)"""
    coeff, rest = term.as_independent(n, as_Add=False)
    q = None
    seen_h = False
    for factor in sympy.Mul.make_args(rest):
        base, exp = factor.as_base_exp()
        if isinstance(base, sympy.harmonic) and base.args == (n,) and exp == 1:
            seen_h = True
        elif base == n and exp.is_Integer and exp < 0:
            q = -int(exp)
        elif base == 1 / n and exp.is_Integer and exp > 0:
            q = int(exp)
        else:
            return None
    if not seen_h or q is None or q < 2:
        return None
    return coeff, q


# ---------------------------------------------------------------------------
# Central binomial sums  Σ_{n≥1} (±1)^{n} / (n^q C(2n, n))
# ---------------------------------------------------------------------------
# Known closed forms (Lehmer 1985; Borwein–Broadhurst); each is verified to
# 40 digits in backend/tests.  Entries: (sign, q) -> SymPy expression.
_phi = sympy.GoldenRatio


def _central_binomial_table():
    pi, sqrt, log, zeta, Rational = sympy.pi, sympy.sqrt, sympy.log, sympy.zeta, sympy.Rational
    psi1 = lambda z: sympy.polygamma(1, z)
    return {
        (1, 0): Rational(1, 3) + 2 * sqrt(3) * pi / 27,
        (1, 1): sqrt(3) * pi / 9,
        (1, 2): pi**2 / 18,
        (1, 3): pi * sqrt(3) / 18 * (psi1(Rational(1, 3)) - psi1(Rational(2, 3))) - Rational(4, 3) * zeta(3),
        (1, 4): 17 * pi**4 / 3240,
        (-1, 1): 2 * sqrt(5) / 5 * log(_phi),          # Σ (-1)^{n-1}/(n C)   (sign refers to (-1)^{n-1})
        (-1, 2): 2 * log(_phi) ** 2,
        (-1, 3): Rational(2, 5) * zeta(3),
    }


def _match_central_binomial(term, n):
    """c · (−1)^{n+k} · n^{−q} / binomial(2n, n)  ->  (c, sign_of_(-1)^(n-1), q)."""
    coeff, rest = term.as_independent(n, as_Add=False)
    q = 0
    sign = 1
    seen_binom = False
    for factor in sympy.Mul.make_args(rest):
        base, exp = factor.as_base_exp()
        if isinstance(base, sympy.binomial) and exp == -1:
            top, bot = base.args
            if bot != n or sympy.expand(top - 2 * n) != 0:
                return None
            seen_binom = True
        elif base == n and exp.is_Integer and exp <= 0:
            q += -int(exp)
        elif base == -1 and exp.has(n):
            # (-1)^(n + k) = (-1)^(k+1) · (-1)^(n-1): alternating, with a constant sign.
            k = sympy.expand(exp - (n - 1))
            if not k.is_Integer:
                return None
            sign = -1
            if k % 2 == 1:
                coeff = -coeff
        else:
            return None
    if not seen_binom:
        return None
    return coeff, sign, q


class SumWithEulerSums(SumWithDirichletSeries):
    name = "Sum"
    context = "System`"

    def eval_iter_nostep(self, expr, i, imin, imax, evaluation):
        "%(name)s[expr_, {i_Symbol, imin_, imax_}]"
        if _is_infinity(imax, evaluation) and imin.evaluate(evaluation).get_int_value() == 1:
            term, n = _summand(expr, i, evaluation)
            if term is not None:
                m = _match_euler_sum(term, n)
                if m is not None:
                    coeff, q = m
                    return from_sympy(coeff * euler_sum_closed_form(q))
                cb = _match_central_binomial(term, n)
                if cb is not None:
                    coeff, sign, q = cb
                    closed = _central_binomial_table().get((sign, q))
                    if closed is not None:
                        return from_sympy(coeff * closed)
        return super().eval_iter_nostep(expr, i, imin, imax, evaluation)


# ---------------------------------------------------------------------------
# Infinite products of rational functions
# ---------------------------------------------------------------------------

def rational_product_closed_form(term, n, start):
    num, den = sympy.fraction(sympy.together(term))
    try:
        P, Q = sympy.Poly(num, n), sympy.Poly(den, n)
    except sympy.PolynomialError:
        return None
    if P.degree() != Q.degree() or P.degree() < 1 or P.LC() != Q.LC():
        return None
    pr, qr = sympy.roots(P), sympy.roots(Q)
    if sum(pr.values()) != P.degree() or sum(qr.values()) != Q.degree():
        return None  # not fully factorable
    if sympy.simplify(sum(m * r for r, m in pr.items()) - sum(m * r for r, m in qr.items())) != 0:
        return None  # product diverges (or needs an exponential correction)
    for r in list(pr) + list(qr):
        # a root at an integer >= start makes a term zero or infinite
        if r.is_integer and r >= start:
            return None
    val = sympy.Integer(1)
    for r, m in qr.items():
        val *= sympy.gamma(start - r) ** m
    for r, m in pr.items():
        val /= sympy.gamma(start - r) ** m
    val = sympy.simplify(sympy.gammasimp(val))
    if val.has(sympy.gamma):
        val = sympy.simplify(sympy.expand_func(val))
    return val


class ProductWithGammaClosedForms(Product):
    name = "Product"
    context = "System`"

    def eval_iter_nostep(self, expr, i, imin, imax, evaluation):
        "%(name)s[expr_, {i_Symbol, imin_, imax_}]"
        if _is_infinity(imax, evaluation):
            start = imin.evaluate(evaluation).to_sympy()
            term, n = _summand(expr, i, evaluation)
            if term is not None and start is not None and start.is_Integer:
                try:
                    closed = rational_product_closed_form(term, n, start)
                except Exception:
                    closed = None
                if closed is not None and closed.is_finite is not False:
                    return from_sympy(closed)
        return super().eval_iter_nostep(expr, i, imin, imax, evaluation)


def register_euler_sums_products(session):
    SumWithEulerSums(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Sum")
    ProductWithGammaClosedForms(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Product")
