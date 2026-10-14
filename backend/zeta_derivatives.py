"""Numeric and closed-form values of Zeta derivatives.

  N[Zeta'[s]], N[Zeta''[s]], ...      via mpmath zeta(s, derivative=k)
  Zeta'[2]  (exact)                   stays symbolic; FunctionExpand / FullSimplify
                                      rewrites it to the Glaisher form used by Wolfram:
                                      Zeta'[2] == Pi^2/6 (EulerGamma + Log[2 Pi] - 12 Log[Glaisher])
  Zeta'[0] == -Log[2 Pi]/2,  Zeta'[-1] == 1/12 - Log[Glaisher]
"""

from __future__ import annotations

import mpmath
import sympy

from mathics.core.atoms import MachineReal, PrecisionReal, Integer
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED, A_NUMERIC_FUNCTION, A_LISTABLE
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.symbols import Symbol

SymbolDerivative = Symbol("System`Derivative")
SymbolZeta = Symbol("System`Zeta")


def _zeta_deriv_value(k, s, prec_digits=None):
    if prec_digits:
        mpmath.mp.dps = prec_digits + 5
    else:
        mpmath.mp.dps = 20
    v = mpmath.zeta(s, derivative=k)
    return v


class ZetaDerivativeNumeric(Builtin):
    """Numeric Zeta derivatives.

    * Derivative[k][Zeta][s] with inexact s evaluates directly.
    * N[Derivative[k][Zeta][s], p] is routed here through an NValues rule on
      Derivative (looked up by the expression's lookup name before N descends
      into the head and turns k into 1.).
    """
    name = "Derivative"
    context = "System`"
    attributes = A_PROTECTED | A_READ_PROTECTED

    def eval(self, k, s, evaluation):
        "Derivative[k_Integer][Zeta][s_?InexactNumberQ]"
        return _zeta_deriv_mathics(k.get_int_value(), s, None)


class ZetaDerivativeN(Builtin):
    """Internal: ZetaDerivativeN[k, s, precision]."""
    attributes = A_PROTECTED | A_READ_PROTECTED

    def eval(self, k, s, p, evaluation):
        "ZetaDerivativeN[k_Integer, s_, p_]"
        pv = p.to_sympy() if p.get_name() != "System`MachinePrecision" else None
        digits = int(pv) if (pv is not None and pv.is_number) else None
        s_eval = Expression(Symbol("System`N"), s, p).evaluate(evaluation)
        return _zeta_deriv_mathics(k.get_int_value(), s_eval, digits)


def _zeta_deriv_mathics(kk, s, digits):
    if kk is None or kk < 0:
        return None
    sv = s.to_sympy()
    if sv is None or not sv.is_number:
        return None
    try:
        mpmath.mp.dps = (digits or 16) + 5
        sm = mpmath.mpmathify(complex(sympy.N(sv, (digits or 16) + 5))) if not sv.is_real else mpmath.mpf(str(sympy.N(sv, (digits or 16) + 5)))
        v = mpmath.zeta(sm, derivative=kk)
    except Exception:
        return None
    if isinstance(v, mpmath.mpc) and abs(v.imag) > 10 ** -(digits or 15):
        re_, im_ = (sympy.Float(str(v.real), digits), sympy.Float(str(v.imag), digits)) if digits else (sympy.Float(float(v.real)), sympy.Float(float(v.imag)))
        return from_sympy(re_ + sympy.I * im_)
    v = v.real if isinstance(v, mpmath.mpc) else v
    if digits:
        return PrecisionReal(sympy.Float(str(v), digits))
    return MachineReal(float(v))


# Closed forms (Wolfram FunctionExpand):  Zeta'[2], Zeta'[0], Zeta'[-1], Zeta'[-2]
_GLAISHER = sympy.Symbol("System`Glaisher")


def _closed_form(k, s):
    pi, log, E = sympy.pi, sympy.log, sympy.EulerGamma
    if k != 1:
        return None
    if s == 2:
        return pi**2 / 6 * (E + log(2 * pi) - 12 * log(_GLAISHER))
    if s == 0:
        return -log(2 * pi) / 2
    if s == -1:
        return sympy.Rational(1, 12) - log(_GLAISHER)
    if s == -2:
        return -sympy.zeta(3) / (4 * pi**2)
    return None


class FunctionExpandZeta(Builtin):
    """FunctionExpand[Zeta'[2]] etc. (extends more_builtins.FunctionExpand)."""
    name = "FunctionExpand"
    context = "System`"
    attributes = A_PROTECTED | A_READ_PROTECTED

    def eval(self, e, evaluation):
        "FunctionExpand[e_]"
        changed = [False]

        def fix(x):
            if (isinstance(x, Expression) and isinstance(x.head, Expression) and isinstance(x.head.head, Expression)
                    and x.head.head.head.get_name() == "System`Derivative"
                    and x.head.elements and x.head.elements[0].get_name() == "System`Zeta" and len(x.elements) == 1):
                k = x.head.head.elements[0].get_int_value()
                s = x.elements[0].to_sympy()
                cf = _closed_form(k, s) if (k is not None and s is not None) else None
                if cf is not None:
                    changed[0] = True
                    return from_sympy(cf)
            if isinstance(x, Expression):
                return Expression(fix(x.head), *(fix(el) for el in x.elements))
            return x

        out = fix(e)
        if changed[0]:
            return Expression(Symbol("System`Simplify"), out).evaluate(evaluation)
        # fall back to SymPy expand_func
        s = e.to_sympy()
        if s is None:
            return None
        try:
            r = sympy.expand_func(s)
            if r == s:
                r = sympy.gammasimp(s)
            return from_sympy(r)
        except Exception:
            return None


_NVALUE_RULE = (
    "Unprotect[Derivative]; "
    "N[Derivative[k_Integer][Zeta][s_?NumericQ], p_] ^:= ZetaDerivativeN[k, s, p]; "
    "N[Derivative[k_Integer][Zeta][s_?NumericQ]] ^:= ZetaDerivativeN[k, s, MachinePrecision]; "
    "Protect[Derivative];"
)


def register_zeta_derivatives(session):
    ZetaDerivativeNumeric(expression=False).contribute(session.definitions)
    ZetaDerivativeN(expression=False).contribute(session.definitions)
    FunctionExpandZeta(expression=False).contribute(session.definitions)
    for n in ("Derivative", "ZetaDerivativeN", "FunctionExpand", "Zeta"):
        session.definitions.clear_cache(f"System`{n}")
    # NValues are looked up on the expression's lookup name (Derivative) before
    # N[] descends into the head, so an upvalue-style N rule is the hook.
    session.evaluate(_NVALUE_RULE)
