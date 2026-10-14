"""Algebra, linear-algebra and number-theory builtins missing from Mathics 10.0.1.

Contracts follow the installed Wolfram 15.0.1 ``Usage.m`` declarations (see
``wolfram-re-round2/catalog/impl-map.csv`` for the native entry points):

  CharacteristicPolynomial[m, x]           det(x I - m) as a polynomial in x
  JordanDecomposition[m]                   {s, j} with m == s.j.Inverse[s]
  PolynomialQuotient[p, q, x]              quotient, remainder dropped
  PolynomialRemainder[p, q, x]             remainder of p / q in x
  Resultant[p, q, x]                       resultant w.r.t. x; Resultant[p, q, x, Modulus -> n]
  GroebnerBasis[{polys}, {vars}]           reduced lex Gröbner basis (Wolfram's default order)
  TrigExpand[e]                            expand sin(a+b), sin(2a), products
  TrigReduce[e]                            products/powers -> combined arguments
  ChineseRemainder[{r1,..}, {m1,..}]       smallest non-negative x with x == r_i (mod m_i)
  RootApproximant[x] / RootApproximant[x, n]  algebraic number of degree <= n approximating x

Implementation is SymPy; results are converted with ``from_sympy`` so they print
in Mathics' canonical ordering.  Each function leaves non-matching input
unevaluated instead of raising.
"""

from __future__ import annotations

import sympy

from mathics.core.atoms import Integer
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.list import ListExpression


def _poly_args(*exprs):
    out = []
    for e in exprs:
        s = e.to_sympy()
        if s is None:
            return None
        out.append(s)
    return out


def _matrix(m):
    """Convert a Mathics rectangular list-of-lists into a sympy Matrix, or None."""
    if not m.has_form("List", None):
        return None
    rows = []
    for row in m.elements:
        if not row.has_form("List", None):
            return None
        r = []
        for el in row.elements:
            s = el.to_sympy()
            if s is None:
                return None
            r.append(s)
        rows.append(r)
    if not rows or any(len(r) != len(rows[0]) for r in rows):
        return None
    return sympy.Matrix(rows)


def _from_matrix(M):
    return ListExpression(*(ListExpression(*(from_sympy(M[i, j]) for j in range(M.cols))) for i in range(M.rows)))


class CharacteristicPolynomial(Builtin):
    """
    <dl><dt>'CharacteristicPolynomial[$m$, $x$]'
    <dd>gives the characteristic polynomial for the matrix $m$.</dl>
    >> CharacteristicPolynomial[{{1, 2}, {3, 4}}, x]
     = -2 - 5 x + x ^ 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "characteristic polynomial of a matrix"

    def eval(self, m, x, evaluation):
        "CharacteristicPolynomial[m_List, x_Symbol]"
        M = _matrix(m)
        if M is None or M.rows != M.cols:
            return None
        xs = x.to_sympy()
        return from_sympy(sympy.expand(M.charpoly(xs).as_expr()))


class JordanDecomposition(Builtin):
    """
    <dl><dt>'JordanDecomposition[$m$]'
    <dd>yields {$s$, $j$} with $m$ == $s$.$j$.Inverse[$s$] and $j$ in Jordan canonical form.</dl>
    >> JordanDecomposition[{{1, 1}, {0, 1}}]
     = {{{1, 0}, {0, 1}}, {{1, 1}, {0, 1}}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Jordan decomposition of a matrix"

    def eval(self, m, evaluation):
        "JordanDecomposition[m_List]"
        M = _matrix(m)
        if M is None or M.rows != M.cols:
            return None
        try:
            P, J = M.jordan_form()
        except Exception:
            return None
        return ListExpression(_from_matrix(P), _from_matrix(J))


class PolynomialQuotient(Builtin):
    """
    >> PolynomialQuotient[x^3 - 1, x - 1, x]
     = 1 + x + x ^ 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "quotient of polynomial division"

    def eval(self, p, q, x, evaluation):
        "PolynomialQuotient[p_, q_, x_Symbol]"
        a = _poly_args(p, q, x)
        if a is None:
            return None
        try:
            quo, _ = sympy.div(a[0], a[1], a[2])
        except (sympy.PolynomialError, ZeroDivisionError):
            return None
        return from_sympy(sympy.expand(quo))


class PolynomialRemainder(Builtin):
    """
    >> PolynomialRemainder[x^3 + 1, x - 1, x]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "remainder of polynomial division"

    def eval(self, p, q, x, evaluation):
        "PolynomialRemainder[p_, q_, x_Symbol]"
        a = _poly_args(p, q, x)
        if a is None:
            return None
        try:
            _, rem = sympy.div(a[0], a[1], a[2])
        except (sympy.PolynomialError, ZeroDivisionError):
            return None
        return from_sympy(sympy.expand(rem))


class Resultant(Builtin):
    """
    >> Resultant[x^2 + a, x^2 + b, x]
     = a ^ 2 - 2 a b + b ^ 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"Modulus": "0"}
    summary_text = "resultant of two polynomials"

    def eval(self, p, q, x, evaluation, options):
        "Resultant[p_, q_, x_Symbol, OptionsPattern[Resultant]]"
        a = _poly_args(p, q, x)
        if a is None:
            return None
        modulus = options.get("System`Modulus")
        mod = modulus.get_int_value() if modulus is not None else 0
        try:
            if mod:
                r = sympy.resultant(sympy.Poly(a[0], a[2], modulus=mod), sympy.Poly(a[1], a[2], modulus=mod))
                r = sympy.Integer(int(r) % mod) if r.is_number else r
            else:
                r = sympy.resultant(a[0], a[1], a[2])
        except (sympy.PolynomialError, ValueError):
            return None
        return from_sympy(sympy.expand(r))


class GroebnerBasis(Builtin):
    """
    >> GroebnerBasis[{x^2 + y^2 - 1, x - y}, {x, y}]
     = {-1 + 2 y ^ 2, x - y}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"MonomialOrder": "Lexicographic"}
    summary_text = "Gröbner basis of a polynomial system"

    def eval(self, polys, vars, evaluation, options):
        "GroebnerBasis[polys_List, vars_List, OptionsPattern[GroebnerBasis]]"
        ps = _poly_args(*polys.elements)
        vs = _poly_args(*vars.elements)
        if ps is None or vs is None or not all(isinstance(v, sympy.Symbol) for v in vs):
            return None
        order_name = options.get("System`MonomialOrder")
        order = {"System`Lexicographic": "lex", "System`DegreeLexicographic": "grlex",
                 "System`DegreeReverseLexicographic": "grevlex"}.get(order_name.get_name() if order_name else "", "lex")
        try:
            G = sympy.groebner(ps, *vs, order=order)
        except (sympy.PolynomialError, ValueError):
            return None
        # Wolfram lists the basis with the "smallest" polynomials first.
        exprs = [sympy.expand(g.as_expr()) for g in G.exprs]
        exprs.reverse()
        return ListExpression(*(from_sympy(e) for e in exprs))


class TrigExpand(Builtin):
    """
    >> TrigExpand[Sin[3 x]]
     = 3 Cos[x] ^ 2 Sin[x] - Sin[x] ^ 3
    """
    attributes = A_PROTECTED
    summary_text = "expand trigonometric functions"

    def eval(self, e, evaluation):
        "TrigExpand[e_]"
        s = e.to_sympy()
        if s is None:
            return None
        return from_sympy(_trig_expand(s))


def _trig_expand(e):
    """sin(n x) -> sin(x + (n-1) x) -> sum formulas, repeated; keeps Wolfram's
    mixed sin/cos form (3 cos²x sin x − sin³x) instead of SymPy's sin-only form."""
    from sympy.simplify.fu import TR10

    def is_multiple(t):
        if not isinstance(t, (sympy.sin, sympy.cos)):
            return False
        c = t.args[0].as_coeff_Mul()[0]
        return c.is_Integer and abs(c) > 1

    def split(t):
        c, rest = t.args[0].as_coeff_Mul()
        s = 1 if c > 0 else -1
        return t.func(sympy.Add(s * rest, (c - s) * rest, evaluate=False))

    for _ in range(40):
        new = sympy.expand(TR10(e.replace(is_multiple, split)))
        if new == e:
            break
        e = new
    return e


class TrigReduce(Builtin):
    """
    >> TrigReduce[Sin[x]^2]
     = 1 / 2 - Cos[2 x] / 2
    """
    attributes = A_PROTECTED
    summary_text = "combine trigonometric products and powers"

    def eval(self, e, evaluation):
        "TrigReduce[e_]"
        s = e.to_sympy()
        if s is None:
            return None
        from sympy.simplify.fu import TR8
        return from_sympy(sympy.expand(TR8(sympy.expand(s))))


class ChineseRemainder(Builtin):
    """
    >> ChineseRemainder[{2, 3, 2}, {3, 5, 7}]
     = 23
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    messages = {"nolist": "The arguments must be lists of integers of equal length."}
    summary_text = "solve simultaneous congruences"

    def eval(self, rs, ms, evaluation):
        "ChineseRemainder[rs_List, ms_List]"
        r = [e.get_int_value() for e in rs.elements]
        m = [e.get_int_value() for e in ms.elements]
        if any(v is None for v in r + m) or len(r) != len(m) or not m:
            return None
        try:
            res = sympy.ntheory.modular.crt(m, r)
        except (ValueError, ZeroDivisionError):
            return None
        if res is None:
            return None  # inconsistent congruences: Wolfram also returns unevaluated
        return Integer(int(res[0]))


class RootApproximant(Builtin):
    """
    >> RootApproximant[1.6180339887]
     = 1 / 2 + Sqrt[5] / 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find an algebraic number approximating a real"

    def eval(self, x, evaluation):
        "RootApproximant[x_?NumericQ]"
        return self._approx(x, 4, evaluation)

    def eval_deg(self, x, n, evaluation):
        "RootApproximant[x_?NumericQ, n_Integer]"
        d = n.get_int_value()
        if d is None or d < 1:
            return None
        return self._approx(x, d, evaluation)

    @staticmethod
    def _approx(x, maxdeg, evaluation):
        v = x.to_sympy()
        if v is None:
            return None
        try:
            val = sympy.Float(sympy.N(v, 30), 30)
        except Exception:
            return None
        import mpmath
        mpmath.mp.dps = 30
        t = mpmath.mpf(str(val))
        # Machine reals carry ~16 digits but the user usually typed fewer;
        # Wolfram accepts "simple" polynomials whose root matches to ~1e-10
        # relative and prefers small coefficients. Try tight tolerance first.
        z = sympy.Symbol("z")
        for tol_exp in (12, 10, 8):
            tol = abs(t) * mpmath.mpf(10) ** -tol_exp
            for deg in range(1, maxdeg + 1):
                coeffs = mpmath.findpoly(t, deg, maxcoeff=1000, tol=tol)
                if not coeffs:
                    continue
                poly = sum(int(c) * z ** (deg - i) for i, c in enumerate(coeffs))
                try:
                    roots = sympy.Poly(poly, z).all_roots()
                except Exception:
                    continue
                best = min(roots, key=lambda r: abs(complex(sympy.N(r, 30)) - complex(t)))
                if abs(complex(sympy.N(best, 30)) - complex(t)) < float(tol) * 10:
                    return from_sympy(sympy.radsimp(best) if deg <= 2 else best)
        return None
