"""Polynomial and algebraic number-theory builtins missing from Mathics 10.0.1.

Contracts follow Wolfram 15.0.1:

  PolynomialQuotientRemainder[p, q, x]   {quotient, remainder} of p / q in x
  PolynomialExtendedGCD[p, q, x]         {g, {s, t}} with g == s p + t q, g primitive
  Subresultants[p, q, x]                 principal subresultant coefficients
  SymmetricPolynomial[k, {vars}]          k-th elementary symmetric polynomial
  SymmetricReduction[f, {vars}]          {symmetric part, remainder}
  SymmetricReduction[f, {vars}, {svars}] symmetric part written in the svars
  NRoots[lhs == rhs, x] / NRoots[p, x]   Or chain of machine-precision roots
  CountRoots[poly, {x, a, b}]            real roots in the interval, with multiplicity
  FrobeniusNumber[{a, ...}]              largest integer not a non-negative combination
  FrobeniusSolve[{a, ...}, M]            non-negative integer solutions of a.x == M

Implementation is SymPy plus small exact algorithms (Frobenius numbers use the
shortest-path residue method).  Non-matching or oversized input is left
unevaluated instead of raising.
"""

from __future__ import annotations

import heapq

import sympy

from mathics.core.atoms import Integer, Real
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol
from mathics.core.systemsymbols import SymbolEqual, SymbolInfinity, SymbolOr


def _poly_args(*exprs):
    out = []
    for e in exprs:
        s = e.to_sympy()
        if s is None:
            return None
        out.append(s)
    return out


def _int_list(l):
    vals = [e.get_int_value() for e in l.elements]
    if any(v is None for v in vals):
        return None
    return vals


class PolynomialQuotientRemainder(Builtin):
    """
    >> PolynomialQuotientRemainder[x^3 - 1, x - 1, x]
     = {1 + x + x ^ 2, 0}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "quotient and remainder of polynomial division"

    def eval(self, p, q, x, evaluation):
        "PolynomialQuotientRemainder[p_, q_, x_Symbol]"
        a = _poly_args(p, q, x)
        if a is None:
            return None
        try:
            quo, rem = sympy.div(a[0], a[1], a[2])
        except (sympy.PolynomialError, ZeroDivisionError):
            return None
        return ListExpression(from_sympy(sympy.expand(quo)), from_sympy(sympy.expand(rem)))


class PolynomialExtendedGCD(Builtin):
    """
    >> PolynomialExtendedGCD[x^2 - 1, x^3 - 1, x]
     = {-1 + x, {-x, 1}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "extended greatest common divisor of polynomials"

    def eval(self, p, q, x, evaluation):
        "PolynomialExtendedGCD[p_, q_, x_Symbol]"
        a = _poly_args(p, q, x)
        if a is None:
            return None
        try:
            s, t, g = sympy.gcdex(a[0], a[1], a[2])
            if g == 0:
                return None
            # SymPy returns a monic gcd over QQ; Wolfram returns the primitive
            # gcd (integer content removed, positive leading coefficient).
            content, _ = sympy.Poly(g, a[2]).primitive()
            scale = 1 / content

            def ratio(v):
                num, den = sympy.fraction(sympy.together(v))
                return num / sympy.expand(den)

            s, t, g = ratio(s * scale), ratio(t * scale), sympy.expand(g * scale)
        except (sympy.PolynomialError, ZeroDivisionError):
            return None
        return ListExpression(from_sympy(g), ListExpression(from_sympy(s), from_sympy(t)))


def _subresultant_polys(f, g, x):
    """Subresultant polynomials S_k(f, g) for k = min(m, n)-1 ... 0, from
    Sylvester submatrices (Gathen & Gerhard, Modern Computer Algebra, sec. 6.10).
    Requires deg f >= deg g."""
    m, n = sympy.degree(f, x), sympy.degree(g, x)
    if m < n:
        f, g, m, n = g, f, n, m
    f = sympy.Poly(f, x)
    g = sympy.Poly(g, x)
    out = []
    for k in range(n - 1, -1, -1):
        size = m + n - 2 * k
        cols = m + n - k  # powers x^(m+n-k-1) ... x^0
        rows = []
        for shift in range(n - 1 - k, -1, -1):
            rows.append([(f * sympy.Poly(x ** shift, x)).nth(m + n - k - 1 - j) for j in range(cols)])
        for shift in range(m - 1 - k, -1, -1):
            rows.append([(g * sympy.Poly(x ** shift, x)).nth(m + n - k - 1 - j) for j in range(cols)])
        # S_k = sum_j s(k, j) x^j; s(k, j) = det of `rows` restricted to all
        # columns except x^k .. x^0, with column x^j re-appended last.
        keep = list(range(cols - k - 1))  # columns of x^(m+n-k-1) .. x^(k+1)
        poly = 0
        for j in range(k, -1, -1):
            sel = keep + [cols - 1 - j]
            M = sympy.Matrix(size, size, lambda r, c, rows=rows, sel=sel: rows[r][sel[c]])
            poly += M.det() * x ** j
        out.append(sympy.expand(poly))
    return out


class Subresultants(Builtin):
    """
    >> Subresultants[x^2 + a, x + b, x]
     = {a + b ^ 2, 1}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "principal subresultant coefficients of two polynomials"

    def eval(self, p, q, x, evaluation):
        "Subresultants[p_, q_, x_Symbol]"
        a = _poly_args(p, q, x)
        if a is None:
            return None
        try:
            m, n = sympy.degree(a[0], a[2]), sympy.degree(a[1], a[2])
            if m < 0 or n < 0:
                return None
            f, g = (a[0], a[1]) if m >= n else (a[1], a[0])
            m, n = max(m, n), min(m, n)
            f = sympy.Poly(f, a[2])
            g = sympy.Poly(g, a[2])
            if n == 0:
                return ListExpression(from_sympy(sympy.resultant(f, g, a[2])))
            # Wolfram gives the principal subresultant coefficients:
            # {psc_0 == Resultant, psc_1, ..., psc_{n-1}, leading coefficient of g}.
            pscs = []
            for k, s_k in enumerate(reversed(_subresultant_polys(f, g, a[2]))):
                pscs.append(sympy.expand(sympy.Poly(s_k, a[2]).nth(k)))
            pscs.append(sympy.expand(g.LC()))
        except (sympy.PolynomialError, ValueError, sympy.DomainError):
            return None
        return ListExpression(*(from_sympy(s) for s in pscs))


class SymmetricPolynomial(Builtin):
    """
    >> SymmetricPolynomial[2, {x, y, z}]
     = x y + x z + y z
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "elementary symmetric polynomial"

    def eval(self, k, vars, evaluation):
        "SymmetricPolynomial[k_Integer, vars_List]"
        vs = _poly_args(*vars.elements)
        n = k.get_int_value()
        if vs is None or n is None or not all(isinstance(v, sympy.Symbol) for v in vs):
            return None
        if n < 0 or n > len(vs):
            return None
        from sympy.polys.specialpolys import symmetric_poly
        return from_sympy(sympy.expand(symmetric_poly(n, *vs)))


class SymmetricReduction(Builtin):
    """
    >> SymmetricReduction[x^2 + y^2, {x, y}]
     = {-2 x y + (x + y) ^ 2, 0}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "symmetric reduction of a polynomial"

    def eval(self, f, vars, evaluation):
        "SymmetricReduction[f_, vars_List]"
        return self._reduce(f, vars, None)

    def eval_svars(self, f, vars, svars, evaluation):
        "SymmetricReduction[f_, vars_List, svars_List]"
        return self._reduce(f, vars, svars)

    @staticmethod
    def _reduce(f, vars, svars):
        fs = f.to_sympy()
        vs = _poly_args(*vars.elements)
        if fs is None or vs is None or not all(isinstance(v, sympy.Symbol) for v in vs):
            return None
        from sympy.polys.polyfuncs import symmetrize
        try:
            sym_part, rem, mapping = symmetrize(fs, *vs, formal=True)
        except (sympy.PolynomialError, ValueError):
            return None
        sym_expr = sym_part.as_expr() if hasattr(sym_part, "as_expr") else sym_part
        if svars is not None:
            sv = _poly_args(*svars.elements)
            if sv is None or len(sv) != len(mapping) or not all(isinstance(s, sympy.Symbol) for s in sv):
                return None
            sym_expr = sym_expr.subs({formal: target for (formal, _), target in zip(mapping, sv)}, simultaneous=True)
        else:
            sym_expr = sym_expr.subs({formal: val for formal, val in mapping}, simultaneous=True)
        rem_expr = rem.as_expr() if hasattr(rem, "as_expr") else rem
        # keep the symmetric part in elementary-symmetric form (no expand):
        # Wolfram returns e.g. {(x + y)^2 - 2 x y, 0}, not the expanded square.
        return ListExpression(from_sympy(sym_expr), from_sympy(rem_expr))


class NRoots(Builtin):
    """
    <dl><dt>'NRoots[$lhs$ == $rhs$, $x$]'
    <dd>gives the numerical roots of a polynomial equation.</dl>
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical roots of a polynomial"

    def eval(self, lhs, rhs, x, evaluation):
        "NRoots[lhs_ == rhs_, x_Symbol]"
        return self._roots(lhs, rhs, x)

    def eval_poly(self, p, x, evaluation):
        "NRoots[p_, x_Symbol]"
        # Wolfram also accepts a bare polynomial, meaning p == 0.  This rule
        # can match an Equal expression too, so dispatch defensively.
        if p.has_form("Equal", 2):
            return self._roots(p.elements[0], p.elements[1], x)
        return self._roots(p, Integer(0), x)

    @staticmethod
    def _roots(lhs, rhs, x):
        a = _poly_args(lhs, rhs, x)
        if a is None:
            return None
        try:
            poly = sympy.Poly(a[0] - a[1], a[2])
            if not poly.is_univariate:
                return None
            # Square-free factorization keeps repeated roots exact: plain
            # nroots on (x+1)^2 returns a spurious complex pair.
            roots = []
            for fac, mult in poly.sqf_list()[1]:
                for r in sympy.nroots(fac, n=15, maxsteps=50):
                    roots.extend([r] * mult)
            # Wolfram sorts by real part, then imaginary part.
            roots.sort(key=lambda r: (float(sympy.re(r)), float(sympy.im(r))))
        except (sympy.PolynomialError, ValueError, sympy.NoRootsError, ZeroDivisionError):
            return None
        items = [Expression(SymbolEqual, x, from_sympy(r)) for r in roots]
        if len(items) == 1:
            return items[0]
        return Expression(SymbolOr, *items)


class CountRoots(Builtin):
    """
    >> CountRoots[x^2 - 5, {x, 0, 3}]
     = 1
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "count the real roots of a polynomial in an interval"

    def eval(self, p, x, a, b, evaluation):
        "CountRoots[p_, {x_Symbol, a_, b_}]"
        args = _poly_args(p, x, a, b)
        if args is None:
            return None
        f, xs, lo, hi = args
        try:
            poly = sympy.Poly(f, xs)
            if not poly.is_univariate:
                return None
            # Wolfram counts roots with multiplicity; sympy.count_roots counts
            # distinct roots, so sum over square-free factors.
            n = 0
            for fac, mult in poly.sqf_list()[1]:
                n += mult * sympy.count_roots(fac, lo, hi)
        except (sympy.PolynomialError, ValueError, NotImplementedError, sympy.DomainError):
            return None
        return Integer(int(n))


class FrobeniusNumber(Builtin):
    """
    >> FrobeniusNumber[{3, 5}]
     = 7
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Frobenius number of a set of integers"

    MAX_MODULUS = 100000

    def eval(self, l, evaluation):
        "FrobeniusNumber[l_List]"
        coins = _int_list(l)
        if coins is None or len(coins) < 2 or any(c <= 0 for c in coins):
            return None
        from math import gcd
        g = coins[0]
        for c in coins[1:]:
            g = gcd(g, c)
        if g != 1:
            return SymbolInfinity
        if len(coins) == 2:
            return Integer(coins[0] * coins[1] - coins[0] - coins[1])
        modulus = min(coins)
        if modulus > self.MAX_MODULUS:
            return None
        # d[r] = smallest representable value congruent to r (mod modulus);
        # the Frobenius number is max(d) - modulus.
        inf = float("inf")
        d = [inf] * modulus
        d[0] = 0
        heap = [(0, 0)]
        while heap:
            val, r = heapq.heappop(heap)
            if val > d[r]:
                continue
            for c in coins:
                nr = (r + c) % modulus
                nv = val + c
                if nv < d[nr]:
                    d[nr] = nv
                    heapq.heappush(heap, (nv, nr))
        return Integer(int(max(d)) - modulus)


class FrobeniusSolve(Builtin):
    """
    >> FrobeniusSolve[{2, 3}, 6]
     = {{0, 2}, {3, 0}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "solve the Frobenius coin equation"

    MAX_SOLUTIONS = 10000

    def eval(self, l, m, evaluation):
        "FrobeniusSolve[l_List, m_Integer]"
        return self._solve(l, m.get_int_value(), None)

    def eval_max(self, l, m, k, evaluation):
        "FrobeniusSolve[l_List, m_Integer, k_Integer]"
        mx = k.get_int_value()
        if mx is None or mx < 0:
            return None
        return self._solve(l, m.get_int_value(), mx)

    def _solve(self, l, target, max_solutions):
        coins = _int_list(l)
        if coins is None or target is None or not coins or any(c <= 0 for c in coins):
            return None
        if target < 0:
            return ListExpression()  # Wolfram gives {} for a negative target
        limit = min(max_solutions, self.MAX_SOLUTIONS) if max_solutions is not None else self.MAX_SOLUTIONS
        # cheapest feasibility pre-check on size: bounded recursion below
        solutions = []
        aborted = []

        def rec(i, rest, prefix):
            if len(solutions) >= limit:
                aborted.append(True)
                return
            if i == len(coins) - 1:
                if rest % coins[i] == 0:
                    solutions.append(prefix + [rest // coins[i]])
                return
            c = coins[i]
            for v in range(rest // c + 1):
                rec(i + 1, rest - v * c, prefix + [v])
                if aborted:
                    return

        rec(0, target, [])
        if aborted and max_solutions is None:
            return None  # too many solutions: leave unevaluated
        return ListExpression(*(ListExpression(*(Integer(v) for v in sol)) for sol in solutions))


def register_polynomial_extras(session):
    classes = (PolynomialQuotientRemainder, PolynomialExtendedGCD, Subresultants,
               SymmetricPolynomial, SymmetricReduction, NRoots, CountRoots,
               FrobeniusNumber, FrobeniusSolve)
    for cls in classes:
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
