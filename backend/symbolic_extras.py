"""Reduce over the reals, FullSimplify extras, Gamma reflection, PolyLog values,
Fibonacci/Lucas generating-function sums, and a small table of classical
definite integrals SymPy cannot do.

  Reduce[ineq, x, Reals]             polynomial/rational inequalities -> interval logic
  Reduce[eq, x]                      falls back to Solve for equations
  FullSimplify[e]                    native Simplify + sqrtdenest + gammasimp + expand_func
  Gamma[p] Gamma[1-p]                -> Pi / Sin[Pi p]   (reflection, rational p)
  PolyLog[2, 1/2], PolyLog[2, 1], PolyLog[2, -1], PolyLog[3, 1/2], ...   exact values
  Sum[Fibonacci[n] z^n, ...]         z/(1 - z - z^2) and variants
  Integrate table:                   ArcTan[x]/x on [0,1] -> Catalan
                                     Log[Sin[x]] on [0,Pi] -> -Pi Log[2]   (and [0,Pi/2] -> -Pi Log[2]/2)
                                     Sqrt[Tan[x]] on [0,Pi/2] -> Pi/Sqrt[2]
                                     Log[1+x]/(1+x^2) on [0,1] -> Pi Log[2]/8
                                     Log[Cos[x]] on [0,Pi/2] -> -Pi Log[2]/2
                                     x/Sin[x] on [0,Pi/2] -> 2 Catalan
"""

from __future__ import annotations

import sympy

from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED, A_LISTABLE, A_NUMERIC_FUNCTION
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol

from mathics.builtin.numbers.algebra import FullSimplify as _NativeFullSimplify
from mathics.builtin.specialfns.gamma import Gamma as _NativeGamma
from euler_sums_products import SumWithEulerSums
from assumption_integrate import IntegrateWithAssumptions


# ---------------------------------------------------------------------------
# Reduce
# ---------------------------------------------------------------------------

def _relational_to_mathics(rel):
    """SymPy boolean over one real symbol -> Mathics inequality expression."""
    if rel is sympy.true:
        return Symbol("System`True")
    if rel is sympy.false:
        return Symbol("System`False")
    if isinstance(rel, sympy.Or):
        return Expression(Symbol("System`Or"), *(_relational_to_mathics(a) for a in rel.args))
    if isinstance(rel, sympy.And):
        # try to fold a < x & x < b into a < x < b (Less[a, x, b])
        args = list(rel.args)
        if len(args) == 2:
            lo, hi = None, None
            var = None
            for a in args:
                if isinstance(a, (sympy.StrictGreaterThan, sympy.GreaterThan)) and isinstance(a.lhs, sympy.Symbol):
                    var, lo = a.lhs, (a.rhs, isinstance(a, sympy.StrictGreaterThan))
                elif isinstance(a, (sympy.StrictLessThan, sympy.LessThan)) and isinstance(a.lhs, sympy.Symbol):
                    var, hi = a.lhs, (a.rhs, isinstance(a, sympy.StrictLessThan))
                elif isinstance(a, (sympy.StrictLessThan, sympy.LessThan)) and isinstance(a.rhs, sympy.Symbol):
                    var, lo = a.rhs, (a.lhs, isinstance(a, sympy.StrictLessThan))
                elif isinstance(a, (sympy.StrictGreaterThan, sympy.GreaterThan)) and isinstance(a.rhs, sympy.Symbol):
                    var, hi = a.rhs, (a.lhs, isinstance(a, sympy.StrictGreaterThan))
            if lo and hi and lo[1] == hi[1]:
                head = "System`Less" if lo[1] else "System`LessEqual"
                return Expression(Symbol(head), from_sympy(lo[0]), from_sympy(var), from_sympy(hi[0]))
        return Expression(Symbol("System`And"), *(_relational_to_mathics(a) for a in args))
    return from_sympy(rel)


class Reduce(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "reduce equations and inequalities"

    def eval_reals(self, expr, x, evaluation):
        "Reduce[expr_, x_Symbol, Reals]"
        return self._reduce(expr, x, evaluation, real=True)

    def eval(self, expr, x, evaluation):
        "Reduce[expr_, x_Symbol]"
        return self._reduce(expr, x, evaluation, real=False)

    @staticmethod
    def _reduce(expr, x, evaluation, real):
        head = expr.get_head_name()
        xs = sympy.Symbol(x.to_sympy().name, real=True)
        if head in ("System`Equal",):
            s = expr.to_sympy()
            if s is None:
                return None
            try:
                sols = sympy.solve(s.subs(x.to_sympy(), xs), xs)
            except Exception:
                return None
            if real:
                sols = [r for r in sols if r.is_real is not False]
            if not sols:
                return Symbol("System`False")
            parts = [Expression(Symbol("System`Equal"), x, from_sympy(r)) for r in sols]
            return parts[0] if len(parts) == 1 else Expression(Symbol("System`Or"), *parts)
        if head in ("System`Less", "System`LessEqual", "System`Greater", "System`GreaterEqual", "System`And", "System`Or", "System`Unequal"):
            from distributions import _predicate_to_sympy
            s = _predicate_to_sympy(expr)
            if s is None:
                return None
            s = s.subs(x.to_sympy(), xs)
            try:
                r = sympy.reduce_inequalities(s, xs)
            except Exception:
                return None
            r = r.subs(xs, x.to_sympy())
            return _relational_to_mathics(r)
        return None


# ---------------------------------------------------------------------------
# FullSimplify
# ---------------------------------------------------------------------------

_JACOBI_RULES = (
    "JacobiSN[u_, m_]^2 + JacobiCN[u_, m_]^2 -> 1",
    "JacobiDN[u_, m_]^2 + m_ JacobiSN[u_, m_]^2 -> 1",
    "a_. JacobiSN[u_, m_]^2 + a_. JacobiCN[u_, m_]^2 -> a",
    "1 - JacobiSN[u_, m_]^2 -> JacobiCN[u, m]^2",
    "1 - JacobiCN[u_, m_]^2 -> JacobiSN[u, m]^2",
    "1 - m_ JacobiSN[u_, m_]^2 -> JacobiDN[u, m]^2",
)


def _jacobi_identities(expr, evaluation):
    """Apply the Jacobi elliptic Pythagorean identities; None if nothing changed."""
    if not any(h in str(expr) for h in ("JacobiSN", "JacobiCN", "JacobiDN")):
        return None
    rules = Expression(Symbol("System`List"), *(evaluation.parse(r) for r in _JACOBI_RULES))
    new = Expression(Symbol("System`ReplaceRepeated"), expr, rules).evaluate(evaluation)
    return None if new.sameQ(expr) else new


class FullSimplify(_NativeFullSimplify):
    name = "FullSimplify"
    context = "System`"

    def eval(self, expr, evaluation, options={}):
        "%(name)s[expr_, OptionsPattern[]]"
        # Jacobi elliptic identities (sympy has no JacobiSN etc.):
        #   sn^2 + cn^2 = 1,  dn^2 + m sn^2 = 1   (Wolfram FullSimplify gives 1)
        jac = _jacobi_identities(expr, evaluation)
        if jac is not None:
            expr = jac
        native = super().eval(expr, evaluation, options)
        if native is None:
            native = expr
        s = native.to_sympy()
        if s is None or not isinstance(s, sympy.Expr):
            return native
        best = s
        # Nested radicals: prefer the denested form when it is not longer
        # (Wolfram: Sqrt[2 + Sqrt[3]] -> (1 + Sqrt[3])/Sqrt[2]).
        candidates = []
        for fn in (sympy.sqrtdenest, lambda e: sympy.radsimp(sympy.sqrtdenest(e)), sympy.gammasimp, sympy.expand_func, sympy.simplify):
            try:
                candidates.append(fn(s))
            except Exception:
                continue
        for cand in candidates:
            if cand != s and not cand.has(sympy.Integral, sympy.Sum) and sympy.count_ops(cand) <= sympy.count_ops(best) + 2 and _simpler_radicals(cand, best):
                best = cand
        return from_sympy(best) if best is not s else native


def _simpler_radicals(cand, cur):
    """True if cand has fewer nested radicals than cur, or equal nesting and fewer ops."""
    def depth(e):
        if isinstance(e, sympy.Pow) and e.exp.is_Rational and not e.exp.is_Integer:
            return 1 + max([depth(a) for a in e.args] + [0])
        return max([depth(a) for a in e.args] + [0]) if e.args else 0
    dc, du = depth(cand), depth(cur)
    if dc < du:
        return True
    return dc == du and sympy.count_ops(cand) < sympy.count_ops(cur)


# ---------------------------------------------------------------------------
# Gamma reflection via a Times upvalue-style rule
# ---------------------------------------------------------------------------

from mathics.builtin.arithfns.basic import Times as _NativeTimes
from mathics.core.atoms import Rational as MRational


class GammaReflection(_NativeTimes):
    """Native Times plus the reflection formula:
    Gamma[p] Gamma[1-p] -> Pi/Sin[Pi p] for rational p in (0,1)."""
    name = "Times"
    context = "System`"

    def eval(self, elements, evaluation):
        "Times[elements___]"
        seq = elements.get_sequence()
        gammas = [(i, e) for i, e in enumerate(seq)
                  if e.get_head_name() == "System`Gamma" and len(e.elements) == 1 and isinstance(e.elements[0], MRational)]
        if len(gammas) >= 2:
            for a in range(len(gammas)):
                for b in range(a + 1, len(gammas)):
                    p = gammas[a][1].elements[0].to_sympy()
                    q = gammas[b][1].elements[0].to_sympy()
                    if p + q == 1 and 0 < p < 1:
                        rest = [e for i, e in enumerate(seq) if i not in (gammas[a][0], gammas[b][0])]
                        refl = from_sympy(sympy.pi / sympy.sin(sympy.pi * p))
                        return Expression(Symbol("System`Times"), *rest, refl).evaluate(evaluation)
        return super().eval(elements, evaluation)


# ---------------------------------------------------------------------------
# PolyLog exact values
# ---------------------------------------------------------------------------

from mathics.builtin.specialfns.zeta import PolyLog as _NativePolyLog


class PolyLogValues(_NativePolyLog):
    """Native PolyLog evaluates everything numerically through mpmath, even
    exact arguments. Keep exact arguments symbolic and apply known values."""
    name = "PolyLog"
    context = "System`"

    def eval(self, n, z, evaluation):
        "PolyLog[n_, z_]"
        if n.is_machine_precision() or z.is_machine_precision():
            return super().eval(n, z, evaluation)
        ns, zs = n.to_sympy(), z.to_sympy()
        if ns is None or zs is None:
            return None
        if ns == 3 and zs == sympy.Rational(1, 2):
            return from_sympy(sympy.Rational(7, 8) * sympy.zeta(3) - sympy.pi**2 * sympy.log(2) / 12 + sympy.log(2) ** 3 / 6)
        try:
            v = sympy.expand_func(sympy.polylog(ns, zs))
        except Exception:
            return None
        if isinstance(v, sympy.polylog):
            return None  # stays symbolic
        return from_sympy(v)

    rules = {
        "PolyLog[2, 1]": "Pi^2/6",
        "PolyLog[2, -1]": "-Pi^2/12",
        "PolyLog[2, 1/2]": "Pi^2/12 - Log[2]^2/2",
        "PolyLog[2, 0]": "0",
        "PolyLog[3, 1]": "Zeta[3]",
        "PolyLog[3, -1]": "-3 Zeta[3]/4",
        "PolyLog[3, 1/2]": "7 Zeta[3]/8 - Pi^2 Log[2]/12 + Log[2]^3/6",
        "PolyLog[s_Integer, 1] /; s > 1": "Zeta[s]",
        "PolyLog[s_Integer, -1] /; s > 1": "-(1 - 2^(1 - s)) Zeta[s]",
        "PolyLog[1, z_]": "-Log[1 - z]",
        "PolyLog[0, z_]": "z/(1 - z)",
        "PolyLog[s_, 0]": "0",
    }


# ---------------------------------------------------------------------------
# Fibonacci / Lucas generating-function sums
# ---------------------------------------------------------------------------

def _match_fib_series(term, n):
    """c * fibonacci(n) * z**n  (or lucas)  ->  (c, z, kind)"""
    coeff, rest = term.as_independent(n, as_Add=False)
    kind = None
    z = None
    for factor in sympy.Mul.make_args(rest):
        base, exp = factor.as_base_exp()
        if isinstance(base, sympy.fibonacci) and base.args == (n,) and exp == 1:
            kind = "F"
        elif isinstance(base, sympy.lucas) and base.args == (n,) and exp == 1:
            kind = "L"
        elif not base.has(n) and exp == n:
            z = base
        elif not base.has(n) and exp == -n:
            z = 1 / base
        else:
            return None
    if kind is None or z is None:
        return None
    return coeff, z, kind


class SumWithFibonacci(SumWithEulerSums):
    name = "Sum"
    context = "System`"

    def eval_iter_nostep(self, expr, i, imin, imax, evaluation):
        "%(name)s[expr_, {i_Symbol, imin_, imax_}]"
        from euler_sums_products import _is_infinity
        if _is_infinity(imax, evaluation):
            n = i.to_sympy()
            start = imin.evaluate(evaluation).get_int_value()
            term = expr.evaluate(evaluation).to_sympy(convert_all_global_functions=True)
            if isinstance(n, sympy.Symbol) and start is not None and term is not None:
                m = _match_fib_series(term, n)
                if m is not None:
                    c, z, kind = m
                    if z.is_number and abs(z) < (sympy.sqrt(5) - 1) / 2:
                        gf = z / (1 - z - z**2) if kind == "F" else (2 - z) / (1 - z - z**2)
                        head = sum(((sympy.fibonacci(k) if kind == "F" else sympy.lucas(k)) * z**k for k in range(0, start)), sympy.Integer(0))
                        return from_sympy(sympy.nsimplify(c * (gf - head)))
        return super().eval_iter_nostep(expr, i, imin, imax, evaluation)


# ---------------------------------------------------------------------------
# Classical definite integral table
# ---------------------------------------------------------------------------

def _table_rule(f, x, a, b):
    """Known closed forms SymPy 1.14 cannot evaluate. Match after normalisation."""
    pi = sympy.pi
    f = sympy.simplify(f)
    cases = [
        (sympy.atan(x) / x, 0, 1, sympy.Catalan),
        (sympy.log(sympy.sin(x)), 0, pi, -pi * sympy.log(2)),
        (sympy.log(sympy.sin(x)), 0, pi / 2, -pi * sympy.log(2) / 2),
        (sympy.log(sympy.cos(x)), 0, pi / 2, -pi * sympy.log(2) / 2),
        (sympy.sqrt(sympy.tan(x)), 0, pi / 2, pi / sympy.sqrt(2)),
        (sympy.log(1 + x) / (1 + x**2), 0, 1, pi * sympy.log(2) / 8),
        (x / sympy.sin(x), 0, pi / 2, 2 * sympy.Catalan),
        (sympy.log(x) / (1 + x**2), 0, 1, -sympy.Catalan),
        (sympy.log(x) * sympy.log(1 - x), 0, 1, 2 - pi**2 / 6),
        (sympy.log(1 - x) / x, 0, 1, -pi**2 / 6),
        (sympy.log(1 + x) / x, 0, 1, pi**2 / 12),
        (sympy.asin(x) / x, 0, 1, pi * sympy.log(2) / 2),
        (x * sympy.log(sympy.sin(x)), 0, pi, -pi**2 * sympy.log(2) / 2),
        # Wolfram returns the hypergeometric closed form, not a float
        (sympy.sqrt(1 + x**3), 0, 1, sympy.hyper([-sympy.Rational(1, 2), sympy.Rational(1, 3)], [sympy.Rational(4, 3)], -1)),
        (1 / sympy.sqrt(1 - x**4), 0, 1, sympy.gamma(sympy.Rational(1, 4)) ** 2 / (4 * sympy.sqrt(2 * pi))),
    ]
    for g, lo, hi, val in cases:
        if lo == a and hi == b:
            coeff, rest = f.as_independent(x, as_Add=False)
            if sympy.simplify(rest - g) == 0:
                return coeff * val
    return None


class IntegrateWithTable(IntegrateWithAssumptions):
    name = "Integrate"
    context = "System`"

    def eval(self, f, xs, evaluation, options):  # type: ignore[override]
        "Integrate[f_, xs__, OptionsPattern[]]"
        # Consult the table first: SymPy's manualintegrate can spend minutes on
        # some of these (Log[1+x]/(1+x^2)) before giving up.
        seq = xs.get_sequence()
        assum = options.get("System`Assumptions")
        no_assum = assum is None or (isinstance(assum, Symbol) and assum.get_name() in ("System`$Assumptions", "System`True"))
        if len(seq) == 1 and seq[0].has_form("List", 3) and no_assum:
            var, a, b = seq[0].elements
            f_s, v_s = f.to_sympy(), var.to_sympy()
            a_s, b_s = a.evaluate(evaluation).to_sympy(), b.evaluate(evaluation).to_sympy()
            if all(t is not None for t in (f_s, v_s, a_s, b_s)) and isinstance(f_s, sympy.Expr):
                try:
                    r = _table_rule(f_s, v_s, a_s, b_s)
                except Exception:
                    r = None
                if r is not None:
                    return from_sympy(r)
        return super().eval(f, xs, evaluation, options)

    @staticmethod
    def _integrate_one(expr, v, a, b, bounds):
        r = IntegrateWithAssumptions._integrate_one(expr, v, a, b, bounds)
        if r is not None:
            return r
        try:
            return _table_rule(expr, v, a, b)
        except Exception:
            return None


def register_symbolic_extras(session):
    # GammaReflection (Times override) is intentionally not registered: the
    # kernel leaves Gamma[1/4] Gamma[3/4] alone and only FullSimplify /
    # FunctionExpand give Sqrt[2] Pi (verified against Wolfram 15.0.1).
    for cls in (Reduce, FullSimplify, PolyLogValues, SumWithFibonacci, IntegrateWithTable):
        cls(expression=False).contribute(session.definitions)
    for name in ("Reduce", "FullSimplify", "Gamma", "PolyLog", "Sum", "Integrate", "Times"):
        session.definitions.clear_cache(f"System`{name}")
