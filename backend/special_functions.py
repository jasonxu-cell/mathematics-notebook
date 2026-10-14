"""Special functions that Wolfram's distribution contracts use but Mathics
10.0.1 lacks or leaves unevaluated numerically.

All of these follow the Wolfram argument conventions (verified against the
activated kernel; see wolfram-re-round2/oracle/dist-contracts-full.jsonl):

  GammaRegularized[a, z]      Q(a, z) = Gamma[a, z]/Gamma[a]
  GammaRegularized[a, z0, z1] P-style: (Gamma[a, z0] - Gamma[a, z1])/Gamma[a]
  InverseGammaRegularized[a, s]      solves GammaRegularized[a, z] == s
  InverseGammaRegularized[a, 0, s]   solves GammaRegularized[a, 0, z] == s
  BetaRegularized[z, a, b]    I_z(a, b)
  BetaRegularized[z0, z1, a, b]  I_{z1}(a, b) - I_{z0}(a, b)
  InverseBetaRegularized[s, a, b]      solves BetaRegularized[z, a, b] == s
  InverseBetaRegularized[z0, s, a, b]  solves BetaRegularized[z0, z, a, b] == s
  Beta[z, a, b]  incomplete beta;  Beta[z0, z1, a, b] generalized
  OwenT[h, a], MarcumQ[m, a, b], MarcumQ[m, a, b0, b1]
  Hypergeometric0F1Regularized, Hypergeometric2F1Regularized,
  HypergeometricPFQRegularized, HurwitzZeta, LogBarnesG, Sinc,
  FactorialPower[x, n], HurwitzLerchPhi

Symbolic arguments stay unevaluated (as in Wolfram); exact rationals are
kept exact where a closed form exists (GammaRegularized with integer a,
BetaRegularized with integer a,b), otherwise N[] produces the number.
"""

from __future__ import annotations

import math

import mpmath
import sympy

from mathics.core.atoms import Integer, Integer0, Integer1, MachineReal, Number, Rational, Real
from mathics.core.attributes import A_LISTABLE, A_NUMERIC_FUNCTION, A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.mpmath import from_mpmath
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.number import FP_MANTISA_BINARY_DIGITS, dps, min_prec
from mathics.core.symbols import Symbol, SymbolTrue, SymbolFalse
from mathics.core.systemsymbols import SymbolIndeterminate, SymbolInfinity


# ----------------------------------------------------------------- helpers --

def _numbers(*args):
    """All args Mathics Numbers?  (symbolic -> stay unevaluated)"""
    return all(isinstance(a, Number) for a in args)


def _is_numeric_constant(a):
    try:
        s = a.to_sympy()
    except Exception:
        return False
    return s is not None and getattr(s, "is_number", False) and not s.free_symbols


def _numerify(a):
    if isinstance(a, Number):
        return a
    try:
        return MachineReal(float(a.to_sympy()))
    except Exception:
        return a


def _machine(*args):
    return any(a.is_machine_precision() for a in args if isinstance(a, Number))


def _inexact(*args):
    return any(a.is_inexact() for a in args if isinstance(a, Number))


def _mp(fn, args, exact_hint=None):
    """Evaluate ``fn`` on mpmath values of ``args`` at the args' precision.

    exact_hint: optional callable returning an exact sympy value for exact
    arguments (or None); used so e.g. GammaRegularized[2, 0, 3] stays exact."""
    if not _numbers(*args):
        # exact numeric constants (Pi/2, Sqrt[2], ...) are fine when at least
        # one argument is inexact: numerify them at that precision
        if all(isinstance(a, Number) or _is_numeric_constant(a) for a in args) and _inexact(*args):
            args = tuple(_numerify(a) for a in args)
            if not _numbers(*args):
                return None
        else:
            return None
    if not _inexact(*args):
        if exact_hint is not None:
            try:
                ex = exact_hint(*[a.to_sympy() for a in args])
            except Exception:
                ex = None
            if ex is not None:
                return from_sympy(ex)
        return None  # exact arguments without closed form: leave for N[]
    if _machine(*args):
        prec = FP_MANTISA_BINARY_DIGITS
        vals = [a.round().get_float_value(permit_complex=True) for a in args]
        if None in vals:
            return None
        with mpmath.workprec(prec):
            try:
                r = fn(*vals)
            except (ValueError, ZeroDivisionError, TypeError, mpmath.libmp.NoConvergence):
                return None
            return _from_mp(r, None)
    prec = min_prec(*args)
    with mpmath.workprec(prec):
        vals = [a.to_mpmath(prec) for a in args]
        if None in vals:
            return None
        try:
            r = fn(*vals)
        except (ValueError, ZeroDivisionError, TypeError, mpmath.libmp.NoConvergence):
            return None
        return _from_mp(r, prec)


def _from_mp(r, prec):
    if r is None:
        return None
    if isinstance(r, (int, float)):
        r = mpmath.mpf(r)
    if isinstance(r, mpmath.mpc):
        # chop round-off imaginary parts: relative to the working precision
        # (arbitrary-precision paths through complex intermediates leave ~1e-14)
        tol = max(1e-15, mpmath.mpf(2) ** (-(mpmath.mp.prec - 10)) if prec is None else mpmath.mpf(2) ** (-(prec - 10)))
        if abs(r.imag) <= max(tol, 1e-13) * max(1.0, abs(r.real)):
            r = r.real
    if mpmath.isinf(r):
        return SymbolInfinity if r > 0 else Expression(Symbol("System`Times"), Integer(-1), SymbolInfinity)
    if mpmath.isnan(r):
        return SymbolIndeterminate
    return from_mpmath(r, prec) if prec else from_mpmath(r)


class _NumFn(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED


# ----------------------------------------------------------- regularized --

def _gamma_reg_exact(a, z):
    # Q(a, z) exact for positive integer a: e^-z sum_{k<a} z^k/k!
    if a.is_Integer and a > 0 and z.is_Rational:
        return sympy.exp(-z) * sum(z**k / sympy.factorial(k) for k in range(int(a)))
    return None


class GammaRegularized(_NumFn):
    summary_text = "regularized incomplete gamma function Q(a, z)"

    def eval2(self, a, z, evaluation):
        "GammaRegularized[a_, z_]"
        if isinstance(z, Integer) and z.value == 0:
            return Integer1
        return _mp(lambda a_, z_: mpmath.gammainc(a_, z_, regularized=True), (a, z), _gamma_reg_exact)

    def eval3(self, a, z0, z1, evaluation):
        "GammaRegularized[a_, z0_, z1_]"
        if isinstance(z0, Number) and z0.to_sympy() == 0:
            if isinstance(z1, Number) and z1.to_sympy() == 0:
                return Integer0
            # P(a, z) = 1 - Q(a, z); the kernel keeps the exact 3-argument form
            # inert (GammaRegularized[3, 0, 2] stays as is), so no exact hint
            return _mp(lambda a_, z_: mpmath.gammainc(a_, 0, z_, regularized=True), (a, z1))
        return _mp(lambda a_, u, v: mpmath.gammainc(a_, u, v, regularized=True), (a, z0, z1))


class InverseGammaRegularized(_NumFn):
    summary_text = "inverse of GammaRegularized"

    @staticmethod
    def _solve(a, s, lower):
        # lower=True: find z with P(a, z) = s;  else Q(a, z) = s
        target = s if lower else 1 - s
        if target <= 0:
            return mpmath.mpf(0)
        if target >= 1:
            return mpmath.inf
        f = lambda z: mpmath.gammainc(a, 0, z, regularized=True) - target
        # P(a, z) is increasing in z: bracket by doubling, bisect, then polish.
        lo, hi = mpmath.mpf(0), max(mpmath.mpf(a), mpmath.mpf(1))
        while f(hi) < 0:
            hi *= 2
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid) < 0:
                lo = mid
            else:
                hi = mid
        try:
            return mpmath.findroot(f, (lo, hi), solver="secant")
        except Exception:
            return (lo + hi) / 2

    def eval2(self, a, s, evaluation):
        "InverseGammaRegularized[a_, s_]"
        return _mp(lambda a_, s_: self._solve(a_, s_, False), (a, s))

    def eval3(self, a, z0, s, evaluation):
        "InverseGammaRegularized[a_, z0_?(# == 0 &), s_]"
        return _mp(lambda a_, s_: self._solve(a_, s_, True), (a, s))


def _beta_reg_exact(z, a, b):
    if a.is_Integer and b.is_Integer and a > 0 and b > 0 and z.is_Rational:
        n = a + b - 1
        return sum(sympy.binomial(n, j) * z**j * (1 - z) ** (n - j) for j in range(int(a), int(n) + 1))
    return None


class BetaRegularized(_NumFn):
    summary_text = "regularized incomplete beta function I_z(a, b)"

    def eval3(self, z, a, b, evaluation):
        "BetaRegularized[z_, a_, b_]"
        return _mp(lambda z_, a_, b_: mpmath.betainc(a_, b_, 0, z_, regularized=True), (z, a, b), _beta_reg_exact)

    def eval4(self, z0, z1, a, b, evaluation):
        "BetaRegularized[z0_, z1_, a_, b_]"
        def exact(z0_, z1_, a_, b_):
            u, v = _beta_reg_exact(z0_, a_, b_), _beta_reg_exact(z1_, a_, b_)
            return None if u is None or v is None else sympy.expand(v - u)
        return _mp(lambda z0_, z1_, a_, b_: mpmath.betainc(a_, b_, z0_, z1_, regularized=True), (z0, z1, a, b), exact)


class InverseBetaRegularized(_NumFn):
    summary_text = "inverse of BetaRegularized"

    @staticmethod
    def _solve(s, a, b, z0=None):
        # I_z(a,b) is increasing on [0,1]; solve I_z = target by bisection,
        # then polish with the secant method.
        target = s if z0 is None else s + mpmath.betainc(a, b, 0, z0, regularized=True)
        if target <= 0:
            return mpmath.mpf(0)
        if target >= 1:
            return mpmath.mpf(1)
        f = lambda z: mpmath.betainc(a, b, 0, z, regularized=True) - target
        lo, hi = mpmath.mpf(0), mpmath.mpf(1)
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid) < 0:
                lo = mid
            else:
                hi = mid
        try:
            return mpmath.findroot(f, (lo, hi), solver="secant")
        except Exception:
            return (lo + hi) / 2

    def eval3(self, s, a, b, evaluation):
        "InverseBetaRegularized[s_, a_, b_]"
        return _mp(lambda s_, a_, b_: self._solve(s_, a_, b_), (s, a, b))

    def eval4(self, z0, s, a, b, evaluation):
        "InverseBetaRegularized[z0_, s_, a_, b_]"
        return _mp(lambda z0_, s_, a_, b_: self._solve(s_, a_, b_, z0_), (z0, s, a, b))


class BetaIncomplete(Builtin):
    """Beta[z, a, b] and Beta[z0, z1, a, b] numeric (the native class handles
    the 2-argument form and crashes on inexact 3-argument input)."""
    name = "Beta"
    context = "System`"
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED

    def eval3(self, z, a, b, evaluation):
        "Beta[z_?InexactNumberQ, a_?NumberQ, b_?NumberQ]"
        return _mp(lambda z_, a_, b_: mpmath.betainc(a_, b_, 0, z_), (z, a, b))

    def eval3b(self, z, a, b, evaluation):
        "Beta[z_?NumberQ, a_?InexactNumberQ, b_?NumberQ]"
        return _mp(lambda z_, a_, b_: mpmath.betainc(a_, b_, 0, z_), (z, a, b))

    def eval3c(self, z, a, b, evaluation):
        "Beta[z_?NumberQ, a_?NumberQ, b_?InexactNumberQ]"
        return _mp(lambda z_, a_, b_: mpmath.betainc(a_, b_, 0, z_), (z, a, b))

    def eval4(self, z0, z1, a, b, evaluation):
        "Beta[z0_?NumberQ, z1_?NumberQ, a_?NumberQ, b_?NumberQ]"
        if not _inexact(z0, z1, a, b):
            return None
        return _mp(lambda z0_, z1_, a_, b_: mpmath.betainc(a_, b_, z0_, z1_), (z0, z1, a, b))


# --------------------------------------------------------------- others --

class OwenT(_NumFn):
    summary_text = "Owen's T function"

    def eval(self, h, a, evaluation):
        "OwenT[h_, a_]"
        if isinstance(a, Integer) and a.value == 0:
            return Integer0

        def owen(h_, a_):
            f = lambda x: mpmath.exp(-h_**2 * (1 + x**2) / 2) / (1 + x**2)
            return mpmath.quad(f, [0, a_]) / (2 * mpmath.pi)
        return _mp(owen, (h, a))


class MarcumQ(_NumFn):
    summary_text = "generalized Marcum Q function"

    @staticmethod
    def _q(m, a, b):
        # Q_m(a, b) = int_b^inf x (x/a)^(m-1) exp(-(x^2+a^2)/2) I_{m-1}(a x) dx
        if a == 0:
            return mpmath.gammainc(m, b**2 / 2, regularized=True)
        f = lambda x: x * (x / a) ** (m - 1) * mpmath.exp(-(x**2 + a**2) / 2) * mpmath.besseli(m - 1, a * x)
        return mpmath.quad(f, [b, mpmath.inf])

    def eval3(self, m, a, b, evaluation):
        "MarcumQ[m_, a_, b_]"
        return _mp(self._q, (m, a, b))

    def eval4(self, m, a, b0, b1, evaluation):
        "MarcumQ[m_, a_, b0_, b1_]"
        return _mp(lambda m_, a_, u, v: self._q(m_, a_, u) - self._q(m_, a_, v), (m, a, b0, b1))


class Hypergeometric0F1Regularized(_NumFn):
    summary_text = "regularized confluent hypergeometric limit function"

    def eval(self, b, z, evaluation):
        "Hypergeometric0F1Regularized[b_, z_]"
        return _mp(lambda b_, z_: mpmath.hyp0f1(b_, z_) / mpmath.gamma(b_), (b, z))


class Hypergeometric2F1Regularized(_NumFn):
    summary_text = "regularized Gauss hypergeometric function"

    def eval(self, a, b, c, z, evaluation):
        "Hypergeometric2F1Regularized[a_, b_, c_, z_]"
        return _mp(lambda a_, b_, c_, z_: mpmath.hyp2f1(a_, b_, c_, z_) / mpmath.gamma(c_), (a, b, c, z))


class HypergeometricPFQRegularized(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "regularized generalized hypergeometric function"

    def eval(self, ps, qs, z, evaluation):
        "HypergeometricPFQRegularized[ps_List, qs_List, z_]"
        els = list(ps.elements) + list(qs.elements) + [z]
        if not _numbers(*els) or not _inexact(*els):
            return None
        np_ = len(ps.elements)

        def f(*vals):
            p, q, zz = vals[:np_], vals[np_:-1], vals[-1]
            r = mpmath.hyper(list(p), list(q), zz)
            for qq in q:
                r /= mpmath.gamma(qq)
            return r
        return _mp(f, tuple(els))


class HurwitzZeta(_NumFn):
    summary_text = "Hurwitz zeta function"

    def eval(self, s, a, evaluation):
        "HurwitzZeta[s_, a_]"
        return _mp(lambda s_, a_: mpmath.zeta(s_, a_), (s, a))


class HurwitzLerchPhi(_NumFn):
    summary_text = "Hurwitz-Lerch transcendent"

    def eval(self, z, s, a, evaluation):
        "HurwitzLerchPhi[z_, s_, a_]"

        def phi(z_, s_, a_):
            if a_ == 0:
                # Wolfram's convention: the k = 0 term (0^-s) is dropped,
                # Phi(z, s, 0) = sum_{k>=1} z^k / k^s = polylog(s, z)
                return mpmath.polylog(s_, z_)
            return mpmath.lerchphi(z_, s_, a_)
        return _mp(phi, (z, s, a))


class LogBarnesG(_NumFn):
    summary_text = "logarithm of the Barnes G-function"

    def eval(self, z, evaluation):
        "LogBarnesG[z_]"
        return _mp(lambda z_: mpmath.log(mpmath.barnesg(z_)), (z,))


class Sinc(_NumFn):
    summary_text = "sinc function Sin[z]/z"
    rules = {"Sinc[0]": "1"}

    def eval(self, z, evaluation):
        "Sinc[z_?NumericQ]"
        if not _inexact(z):
            zs = z.to_sympy()
            if zs is None or zs == 0:
                return None
            return from_sympy(sympy.sin(zs) / zs)
        return _mp(lambda z_: mpmath.sinc(z_) if hasattr(mpmath, "sinc") else mpmath.sin(z_) / z_, (z,))


class FactorialPower(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    summary_text = "falling factorial x (x-1) ... (x-n+1)"

    def eval(self, x, n, evaluation):
        "FactorialPower[x_, n_Integer]"
        k = n.get_int_value()
        if k is None or k < 0:
            return None
        xs = x.to_sympy()
        if xs is None:
            return None
        return from_sympy(sympy.expand(sympy.ff(xs, k)))


class InverseErfcNumeric(Builtin):
    """N[InverseErfc[x]] for 0 < x < 2 (the native class only has the exact
    special values)."""
    name = "InverseErfc"
    context = "System`"
    attributes = A_LISTABLE | A_PROTECTED

    def eval(self, z, evaluation):
        "InverseErfc[z_?InexactNumberQ]"
        def f(z_):
            if z_ <= 0 or z_ >= 2:
                raise ValueError
            return mpmath.erfinv(1 - z_)
        return _mp(f, (z,))


class ProductLogNumeric(Builtin):
    """ProductLog[k, z] numeric branch values (native class is 1-argument only)."""
    name = "ProductLog"
    context = "System`"
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED

    def eval(self, k, z, evaluation):
        "ProductLog[k_Integer, z_?InexactNumberQ]"
        kk = k.get_int_value()
        return _mp(lambda z_: mpmath.lambertw(z_, k=kk), (z,))


class Factorial2Exact(Builtin):
    """n!! exact for integers (the native implementation returns a float)."""
    name = "Factorial2"
    context = "System`"
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED

    def eval(self, n, evaluation):
        "Factorial2[n_Integer]"
        v = n.get_int_value()
        if v is None or v < -1:
            return None
        return Integer(int(sympy.factorial2(v)))


from mathics.builtin.specialfns.gamma import Pochhammer as _NativePochhammer
from mathics.builtin.numeric import Piecewise as _NativePiecewise
from mathics.builtin.specialfns.erf import Erfc as _NativeErfc


class PochhammerWolfram(_NativePochhammer):
    """Pochhammer[a, n] for integer n expands to the product a (a+1) ... (a+n-1)
    as Wolfram does (the native rule rewrites to a factorial quotient)."""
    name = "Pochhammer"
    context = "System`"
    rules = {
        "Pochhammer[0, 0]": "1",
        "Derivative[1,0][Pochhammer]": "(Pochhammer[#1, #2]*(-PolyGamma[0, #1] + PolyGamma[0, #1 + #2]))&",
        "Derivative[0,1][Pochhammer]": "(Pochhammer[#1, #2]*PolyGamma[0, #1 + #2])&",
    }

    def eval_int(self, a, n, evaluation):
        "Pochhammer[a_, n_Integer]"
        k = n.get_int_value()
        if k is None:
            return None
        if isinstance(a, Number) and not a.is_inexact():
            return from_sympy(sympy.rf(a.to_sympy(), k))
        if isinstance(a, Number):
            return _mp(lambda a_: mpmath.rf(a_, k), (a,))
        if k < 0 or k > 64:
            return None
        if k == 0:
            return Integer1
        factors = [a if i == 0 else Expression(Symbol("System`Plus"), Integer(i), a) for i in range(k)]
        return Expression(Symbol("System`Times"), *factors)

    def eval_num(self, a, n, evaluation):
        "Pochhammer[a_?NumberQ, n_?NumberQ]"
        if not _inexact(a, n):
            try:
                return from_sympy(sympy.rf(a.to_sympy(), n.to_sympy()))
            except Exception:
                return None
        return _mp(lambda a_, n_: mpmath.rf(a_, n_), (a, n))


_CHAIN_HEADS = {"System`Less", "System`LessEqual", "System`Greater", "System`GreaterEqual"}


def _reduce_chain(cond, evaluation):
    """A chained comparison such as 0 <= 0 <= n evaluates its numeric links;
    `0 <= 0 <= n` -> `0 <= n`, `True && c` -> `c`, `1 < 2 < 3` -> True."""
    if not isinstance(cond, Expression):
        return cond
    head = cond.get_head_name()
    if head in _CHAIN_HEADS and len(cond.elements) > 2:
        kept = []
        els = cond.elements
        decided = False
        for i in range(len(els) - 1):
            pair = Expression(cond.head, els[i], els[i + 1]).evaluate(evaluation)
            if pair is SymbolTrue:
                decided = True
                continue
            if pair is SymbolFalse:
                return SymbolFalse
            kept.append(pair)
        if not decided:
            return cond  # keep Wolfram's chained form a <= x <= b
        if not kept:
            return SymbolTrue
        if len(kept) == 1:
            return kept[0]
        # the remaining links are consecutive: rebuild as a chain
        chain = [kept[0].elements[0]] + [p.elements[1] for p in kept]
        return Expression(cond.head, *chain)
    if head == "System`And":
        parts = [_reduce_chain(e, evaluation) for e in cond.elements]
        if any(p is SymbolFalse for p in parts):
            return SymbolFalse
        parts = [p for p in parts if p is not SymbolTrue]
        if not parts:
            return SymbolTrue
        if len(parts) == 1:
            return parts[0]
        return Expression(Symbol("System`And"), *parts)
    return cond


class PiecewiseWolfram(_NativePiecewise):
    """Piecewise with Wolfram semantics: the values and conditions are
    evaluated, conditions that are True/False select/drop branches, and a
    single remaining True branch collapses to its value."""
    name = "Piecewise"
    context = "System`"
    attributes = A_PROTECTED

    def eval(self, items, evaluation):
        "Piecewise[items__]"
        seq = items.get_sequence()
        if len(seq) not in (1, 2) or not seq[0].has_form("List", None):
            return None
        default = seq[1] if len(seq) == 2 else Integer0
        kept = []
        changed = len(seq) == 1
        for case in seq[0].elements:
            if not case.has_form("List", 2):
                return None
            value, cond = case.elements
            new_cond = _reduce_chain(cond.evaluate(evaluation), evaluation)
            if new_cond is SymbolFalse:
                changed = True
                continue
            if new_cond is SymbolTrue:
                return value.evaluate(evaluation)
            new_value = value.evaluate(evaluation)
            if new_value is not value and not new_value.sameQ(value):
                changed = True
            if new_cond is not cond and not new_cond.sameQ(cond):
                changed = True
            kept.append(Expression(Symbol("System`List"), new_value, new_cond))
        if not kept:
            return default.evaluate(evaluation)
        new_default = default.evaluate(evaluation)
        if new_default is not default and not new_default.sameQ(default):
            changed = True
        if not changed:
            return None  # nothing changed; leave as is (no re-evaluation loop)
        return Expression(Symbol("System`Piecewise"), Expression(Symbol("System`List"), *kept), new_default)


class ErfcWolfram(_NativeErfc):
    """Keep Erfc[-x] as is (Wolfram does not rewrite it to 2 - Erfc[x])."""
    name = "Erfc"
    context = "System`"
    rules = {
        "Derivative[1][Erfc]": "-2 Exp[-#^2] / Sqrt[Pi] &",
        "Erfc[0]": "1",
        "Erfc[Infinity]": "0",
        "Erfc[-Infinity]": "2",
        "Erfc[DirectedInfinity[1]]": "0",
        "Erfc[DirectedInfinity[-1]]": "2",
    }

    def eval(self, z, evaluation):
        "Erfc[z__]"
        args = z.get_sequence()
        if len(args) != 1:
            return None
        (z,) = args
        if isinstance(z, Number) and z.is_inexact():
            return _mp(mpmath.erfc, (z,))
        return None


CLASSES = (
    PochhammerWolfram, PiecewiseWolfram, ErfcWolfram,
    GammaRegularized, InverseGammaRegularized, BetaRegularized, InverseBetaRegularized,
    BetaIncomplete, OwenT, MarcumQ, Hypergeometric0F1Regularized,
    Hypergeometric2F1Regularized, HypergeometricPFQRegularized, HurwitzZeta,
    HurwitzLerchPhi, LogBarnesG, Sinc, FactorialPower, InverseErfcNumeric,
    ProductLogNumeric, Factorial2Exact,
)


def _patch_beta_from_sympy():
    """Mathics 10.0.1's Beta.from_sympy has the signature (sympy_name, elements)
    but the converter calls from_sympy(elements) -> TypeError whenever a
    sympy ``beta``/``betainc`` comes back (PDF[StudentTDistribution], ...).
    Re-bind it with the expected signature."""
    from mathics.core.convert.sympy import sympy_to_mathics

    beta = sympy_to_mathics.get("beta")
    if beta is None:
        return

    def from_sympy(elements):
        return Expression(Symbol("System`Beta"), *elements)

    beta.from_sympy = from_sympy
    for name in ("beta", "betainc"):
        if name in sympy_to_mathics:
            sympy_to_mathics[name].from_sympy = from_sympy


def register_special_functions(session):
    _patch_beta_from_sympy()
    for cls in CLASSES:
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.name if hasattr(cls, 'name') and cls.name else cls.__name__}")
