"""Interpolation, ListInterpolation, InterpolatingPolynomial, Fit, FindFit.

Contracts from Wolfram 15.0.1:

  Interpolation[{{x0, f0}, ...}]                 -> InterpolatingFunction[{{xmin, xmax}}, <>]
  Interpolation[{f1, f2, ...}]                   abscissae 1, 2, ... (InterpolationOrder -> 3 default)
  ListInterpolation[{f1, f2, ...}]               same on a uniform grid
  InterpolatingPolynomial[data, x]               Newton interpolating polynomial (symbolic)
  Fit[data, {1, x}, x]                           linear least squares, exact arithmetic
  FindFit[data, expr, {a, b}, x]                 numerical nonlinear least squares -> {a -> .., b -> ..}

The InterpolatingFunction object is the same lazy object ``numeric_extras``
defines for NDSolve: ``InterpolatingFunction[{{x0, x1}}, {xs, ys}]`` applied to
a number evaluates by interpolation.  Interpolation/ListInterpolation emit a
four-argument form carrying the interpolation order and method so order 1
stays linear and Method -> "Spline" uses a genuine cubic spline; the
two-argument evaluation rule in numeric_extras keeps handling NDSolve output.
The default (Hermite) evaluation is the piecewise Lagrange polynomial through
the k+1 surrounding nodes, which reproduces Wolfram 15 to machine precision.
Out-of-range arguments extrapolate with the dmval warning, as Wolfram does.
A compact OutputForm rule (``InterpolatingFunction[{{x0, x1}}, <>]``) matches
the Wolfram 15 text display for both arities; InputForm keeps the full data.
"""

from __future__ import annotations

import sympy

from mathics.core.atoms import Integer, MachineReal, String
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol
from mathics.core.systemsymbols import SymbolRule

from numeric_extras import InterpolatingFunction, SymbolInterpolatingFunction


# ---------------------------------------------------------------------------
# InterpolatingFunction: compact display + order-aware evaluation
# ---------------------------------------------------------------------------

class InterpolatingFunctionWithOrder(InterpolatingFunction):
    """Adds a four-argument form carrying the interpolation order and method,
    plus the compact Wolfram-style display.  Subclasses numeric_extras' builtin so the
    two-argument NDSolve evaluation rule keeps working (Builtin.contribute
    replaces the whole definition for a name)."""
    name = "InterpolatingFunction"

    formats = {
        ("OutputForm", "InterpolatingFunction[dom_List, _List]"):
            'StringJoin["InterpolatingFunction[", ToString[dom], ", <>]"]',
        ("OutputForm", "InterpolatingFunction[dom_List, _List, _Integer, _String]"):
            'StringJoin["InterpolatingFunction[", ToString[dom], ", <>]"]',
    }

    messages = {
        "dmval": ("Input value `1` lies outside the range of data in the "
                  "interpolating function. Extrapolation will be used."),
    }

    def eval_apply_order(self, dom, data, order, method, t, evaluation):
        "InterpolatingFunction[dom_List, data_List, order_Integer, method_String][t_?NumericQ]"
        import numpy as np
        try:
            xs = np.array([float(e.to_python()) for e in data.elements[0].elements])
            ys = np.array([float(e.to_python()) for e in data.elements[1].elements])
            tv = float(t.to_sympy())
            k = order.get_int_value()
            mth = method.get_string_value()
        except Exception:
            return None
        lo, hi = min(xs[0], xs[-1]), max(xs[0], xs[-1])
        if tv < lo or tv > hi:
            evaluation.message("InterpolatingFunction", "dmval", t)
        srt = np.argsort(xs)
        xs, ys = xs[srt], ys[srt]
        n = len(xs)
        k = min(k, n - 1)
        if k <= 1:
            # piecewise linear; beyond the range extend the boundary segment
            i = int(np.searchsorted(xs, tv, side="right")) - 1
            i = min(max(i, 0), n - 2)
            x0, x1 = xs[i], xs[i + 1]
            v = ys[i] + (ys[i + 1] - ys[i]) * (tv - x0) / (x1 - x0)
            return MachineReal(float(v))
        if mth == "Spline" and k >= 3:
            from scipy.interpolate import CubicSpline
            cs = CubicSpline(xs, ys, extrapolate=True)
            return MachineReal(float(cs(tv)))
        # Hermite (default): on each interval the piece is the Lagrange
        # polynomial through the k+1 surrounding nodes, window starting at
        # i-(k-1)//2 clamped to the ends — this reproduces Wolfram's
        # Method -> "Hermite" to machine precision.
        i = int(np.searchsorted(xs, tv, side="right")) - 1
        i = min(max(i, 0), n - 2)
        start = min(max(i - (k - 1) // 2, 0), n - k - 1)
        xw = xs[start:start + k + 1]
        yw = ys[start:start + k + 1]
        for j in range(k + 1):
            if tv == xw[j]:
                return MachineReal(float(yw[j]))
        # barycentric weights
        w = np.ones(k + 1)
        for a in range(k + 1):
            for b in range(k + 1):
                if a != b:
                    w[a] *= xw[a] - xw[b]
        w = 1.0 / w
        num = np.sum(w * yw / (tv - xw))
        den = np.sum(w / (tv - xw))
        return MachineReal(float(num / den))


# ---------------------------------------------------------------------------
# data parsing helpers
# ---------------------------------------------------------------------------

def _points_1d(data):
    """(xs, ys) as sympy values from {{x, f}, ...} or a flat list (x = 1..n)."""
    if not data.has_form("List", None) or not data.elements:
        return None
    els = data.elements
    if all(e.has_form("List", 2) for e in els):
        xs, ys = [], []
        for e in els:
            a, b = e.elements[0].to_sympy(), e.elements[1].to_sympy()
            if a is None or b is None:
                return None
            xs.append(a)
            ys.append(b)
        return xs, ys
    if any(e.has_form("List", None) for e in els):
        return None
    ys = []
    for e in els:
        b = e.to_sympy()
        if b is None:
            return None
        ys.append(b)
    return [sympy.Integer(i + 1) for i in range(len(ys))], ys


def _numeric_points(data):
    pts = _points_1d(data)
    if pts is None:
        return None
    xs, ys = pts
    try:
        xs_f = [float(x) for x in xs]
        ys_f = [float(y) for y in ys]
    except (TypeError, ValueError):
        return None
    if len(xs_f) < 2 or len(set(xs_f)) != len(xs_f):
        return None
    return xs_f, ys_f


def _ifun_expression(xs_f, ys_f, order, method):
    pairs = sorted(zip(xs_f, ys_f))
    xs_f = [p[0] for p in pairs]
    ys_f = [p[1] for p in pairs]
    dom = ListExpression(ListExpression(MachineReal(min(xs_f)), MachineReal(max(xs_f))))
    data = ListExpression(
        ListExpression(*(MachineReal(v) for v in xs_f)),
        ListExpression(*(MachineReal(v) for v in ys_f)),
    )
    return Expression(SymbolInterpolatingFunction, dom, data, Integer(order), String(method))


# ---------------------------------------------------------------------------
# Interpolation / ListInterpolation
# ---------------------------------------------------------------------------

def _order_option(options, evaluation):
    order = options.get("System`InterpolationOrder")
    if isinstance(order, Integer):
        k = order.get_int_value()
        if k is not None and k >= 1:
            return k
    return None


def _method_option(options):
    m = options.get("System`Method")
    if isinstance(m, String):
        v = m.get_string_value()
    elif isinstance(m, Symbol):
        v = m.get_name().split("`")[-1]
    else:
        return "Hermite"
    return v if v in ("Hermite", "Spline") else "Hermite"


class Interpolation(Builtin):
    """
    >> f = Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}]
     = InterpolatingFunction[{{0., 3.}}, <>]
    >> f[1.5]
     = 2.25
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"InterpolationOrder": "3", "Method": "Automatic"}
    summary_text = "construct an interpolating function from data"

    def eval(self, data, evaluation, options):
        "Interpolation[data_List, OptionsPattern[Interpolation]]"
        k = _order_option(options, evaluation)
        if k is None:
            return None
        pts = _numeric_points(data)
        if pts is None:
            return None
        xs_f, ys_f = pts
        return _ifun_expression(xs_f, ys_f, min(k, len(xs_f) - 1), _method_option(options))


class ListInterpolation(Builtin):
    """
    >> f = ListInterpolation[{0, 1, 4, 9}]
     = InterpolatingFunction[{{1., 4.}}, <>]
    >> f[2.5]
     = 2.25
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"InterpolationOrder": "3", "Method": "Automatic"}
    summary_text = "construct an interpolating function from an array of values"

    def eval(self, data, evaluation, options):
        "ListInterpolation[data_List, OptionsPattern[ListInterpolation]]"
        return self._build(data, None, evaluation, options)

    def eval_domain(self, data, domain, evaluation, options):
        "ListInterpolation[data_List, domain_List, OptionsPattern[ListInterpolation]]"
        return self._build(data, domain, evaluation, options)

    def _build(self, data, domain, evaluation, options):
        k = _order_option(options, evaluation)
        if k is None:
            return None
        if not data.has_form("List", None) or not data.elements:
            return None
        if any(e.has_form("List", None) for e in data.elements):
            return None  # multidimensional arrays are out of scope
        ys_f = []
        for e in data.elements:
            v = e.to_sympy()
            if v is None:
                return None
            try:
                ys_f.append(float(v))
            except (TypeError, ValueError):
                return None
        n = len(ys_f)
        if n < 2:
            return None
        if domain is None:
            xs_f = [float(i + 1) for i in range(n)]
        else:
            if not domain.has_form("List", 1):
                return None
            rng = domain.elements[0]
            if not rng.has_form("List", 2):
                return None
            try:
                a = float(rng.elements[0].to_sympy())
                b = float(rng.elements[1].to_sympy())
            except Exception:
                return None
            step = (b - a) / (n - 1)
            xs_f = [a + i * step for i in range(n)]
        return _ifun_expression(xs_f, ys_f, min(k, n - 1), _method_option(options))


# ---------------------------------------------------------------------------
# InterpolatingPolynomial
# ---------------------------------------------------------------------------

class InterpolatingPolynomial(Builtin):
    """
    >> InterpolatingPolynomial[{{1, 2}, {2, 5}, {3, 10}}, x]
     = 1 + x^2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "polynomial interpolating a set of data"

    def eval(self, data, x, evaluation):
        "InterpolatingPolynomial[data_List, x_Symbol]"
        pts = _points_1d(data)
        if pts is None:
            return None
        xs, ys = pts
        x_s = x.to_sympy()
        try:
            poly = sympy.interpolate(list(zip(xs, ys)), x_s)
        except Exception:
            return None
        return from_sympy(sympy.expand(poly))


# ---------------------------------------------------------------------------
# Fit / FindFit
# ---------------------------------------------------------------------------

def _fit_columns(data, nvars):
    """(X rows, y values) as sympy; flat data means x = 1..n with one variable."""
    if not data.has_form("List", None) or not data.elements:
        return None
    els = data.elements
    if all(e.has_form("List", nvars + 1) for e in els):
        rows, ys = [], []
        for e in els:
            row = [el.to_sympy() for el in e.elements]
            if any(v is None for v in row):
                return None
            rows.append(row[:-1])
            ys.append(row[-1])
        return rows, ys
    if nvars == 1 and not any(e.has_form("List", None) for e in els):
        ys = [e.to_sympy() for e in els]
        if any(v is None for v in ys):
            return None
        return [[sympy.Integer(i + 1)] for i in range(len(ys))], ys
    return None


def _fit_vars(vars):
    vs = list(vars.elements) if vars.has_form("List", None) else [vars]
    if not vs or not all(isinstance(v, Symbol) for v in vs):
        return None
    return vs


class Fit(Builtin):
    """
    >> Fit[{{0, 1}, {1, 3}, {2, 5}}, {1, x}, x]
     = 1. + 2. x

    Wolfram 15 always uses machine arithmetic for Fit (integer data gives
    floating coefficients with rounding noise); numpy lstsq does the same.
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "linear least-squares fit"

    def eval(self, data, funs, vars, evaluation):
        "Fit[data_List, funs_List, vars_]"
        vs = _fit_vars(vars)
        if vs is None or not funs.has_form("List", None) or not funs.elements:
            return None
        vs_s = [v.to_sympy() for v in vs]
        basis = [f.to_sympy() for f in funs.elements]
        if any(b is None for b in basis):
            return None
        cols = _fit_columns(data, len(vs))
        if cols is None:
            return None
        rows, ys = cols
        try:
            design = [[b.subs(dict(zip(vs_s, row))) for b in basis] for row in rows]
        except Exception:
            return None
        import numpy as np
        try:
            A = np.array([[float(v) for v in row] for row in design])
            b = np.array([float(y) for y in ys])
        except (TypeError, ValueError):
            return None
        try:
            coef, *_ = np.linalg.lstsq(A, b, rcond=None)
        except Exception:
            return None
        result = sum(float(c) * f for c, f in zip(coef, basis))
        return from_sympy(sympy.expand(result))


class FindFit(Builtin):
    """
    >> FindFit[{{0, 1}, {1, 3}, {2, 5}}, a x + b, {a, b}, x]
     = {a -> 2., b -> 1.}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical nonlinear least-squares fit"

    def eval(self, data, expr, pars, vars, evaluation):
        "FindFit[data_List, expr_, pars_List, vars_]"
        vs = _fit_vars(vars)
        if vs is None or not pars.has_form("List", None) or not pars.elements:
            return None
        ps, p0 = [], []
        for p in pars.elements:
            if isinstance(p, Symbol):
                ps.append(p)
                p0.append(1.0)
            elif p.has_form("List", None) and 2 <= len(p.elements) <= 4 and isinstance(p.elements[0], Symbol):
                ps.append(p.elements[0])
                try:
                    p0.append(float(p.elements[1].to_sympy()))
                except Exception:
                    return None
            else:
                return None
        vs_s = [v.to_sympy() for v in vs]
        ps_s = [p.to_sympy() for p in ps]
        model = expr.to_sympy()
        if model is None:
            return None
        cols = _fit_columns(data, len(vs))
        if cols is None:
            return None
        rows, ys = cols
        import numpy as np
        try:
            X = np.array([[float(v) for v in row] for row in rows]).T
            Y = np.array([float(y) for y in ys])
        except (TypeError, ValueError):
            return None
        try:
            fun = sympy.lambdify(vs_s + ps_s, model, modules=["numpy", "math"])
        except Exception:
            return None

        def f(xdata, *params):
            return fun(*xdata, *params)

        from scipy.optimize import curve_fit, minimize
        try:
            popt, _ = curve_fit(f, X, Y, p0=p0, maxfev=10000,
                                xtol=1e-15, ftol=1e-15, gtol=1e-15)
        except Exception:
            return None
        # polish to full machine convergence (Wolfram's optimizer ends within
        # ~1e-9 of the exact minimizer; plain curve_fit stops earlier)
        def ss(p):
            return float(np.sum((np.asarray(f(X, *p), dtype=float) - Y) ** 2))
        try:
            r = minimize(ss, popt, method="Nelder-Mead",
                         options=dict(xatol=1e-16, fatol=1e-20, maxfev=20000))
            if r.fun < ss(popt):
                popt = r.x
        except Exception:
            pass
        return ListExpression(*(Expression(SymbolRule, p, MachineReal(float(v)))
                                for p, v in zip(ps, popt)))


def register_interpolation(session):
    for cls in (InterpolatingFunctionWithOrder, Interpolation,
                ListInterpolation, InterpolatingPolynomial, Fit, FindFit):
        cls(expression=False).contribute(session.definitions)
    for name in ("InterpolatingFunction", "Interpolation", "ListInterpolation",
                 "InterpolatingPolynomial", "Fit", "FindFit"):
        session.definitions.clear_cache(f"System`{name}")
