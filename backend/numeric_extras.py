"""DSolve with initial conditions, NDSolve, NSum, NMinimize/NMaximize.

Contracts from the installed Wolfram 15.0.1 Usage.m:

  DSolve[{eqn, y[x0] == a, y'[x0] == b, ...}, y[x], x]   symbolic ODE + ICs
  NDSolve[{eqns, ics}, y, {x, x0, x1}]                  -> {{y -> InterpolatingFunction[...]}}
  NSum[f, {n, nmin, nmax}]                              numerical sum (nmax may be Infinity)
  NMinimize[f, {x, y, ...}] / NMaximize                 -> {fmin, {x -> .., y -> ..}}
  NMinimize[{f, cons}, vars]                             with constraints

NDSolve returns a genuine ``InterpolatingFunction[{{x0, x1}}, <data>]`` object
whose head is given DownValues so ``y[0.5] /. sol`` evaluates by cubic
interpolation of the SciPy solution.  Mathics has no InterpolatingFunction; this
module defines a minimal one with the same calling convention.
"""

from __future__ import annotations

import sympy

from mathics.core.atoms import Integer, MachineReal, Real
from mathics.core.attributes import A_HOLD_ALL, A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol, SymbolList
from mathics.core.systemsymbols import SymbolRule

from mathics.builtin.numbers.diffeqns import DSolve

SymbolInterpolatingFunction = Symbol("System`InterpolatingFunction")
SymbolFunction = Symbol("System`Function")
SymbolSlot = Symbol("System`Slot")


# ---------------------------------------------------------------------------
# DSolve with initial / boundary conditions
# ---------------------------------------------------------------------------

def _is_derivative_of(expr, func_name):
    """True for Derivative[k][f][...] (head-of-head is the Derivative symbol)."""
    h = expr.head
    if not isinstance(h, Expression) or not h.elements:
        return False
    hh = h.head
    return (isinstance(hh, Expression) and hh.head.get_name() == "System`Derivative"
            and h.elements[0].get_name() == func_name)


def _derivative_order(expr):
    return expr.head.head.elements[0].get_int_value() or 1


def _split_ics(eqns, func_head_name):
    """Separate the ODE(s) from conditions like y[0] == 1, y'[0] == 2."""
    odes, ics = [], []
    for e in eqns:
        if e.get_head_name() != "System`Equal" or len(e.elements) != 2:
            return None
        lhs = e.elements[0]
        is_ic = False
        if lhs.get_head_name() == func_head_name and all(el.is_numeric() for el in lhs.elements):
            is_ic = True
        elif _is_derivative_of(lhs, func_head_name) and all(el.is_numeric() for el in lhs.elements):
            is_ic = True
        (ics if is_ic else odes).append(e)
    return odes, ics


class DSolveWithConditions(DSolve):
    name = "DSolve"
    context = "System`"

    def eval(self, eqn, y, x, evaluation):
        "DSolve[eqn_, y_, x_]"
        if not eqn.has_form("List", None):
            return super().eval(eqn, y, x, evaluation)
        if not isinstance(x, Symbol):
            return super().eval(eqn, y, x, evaluation)
        func = y if not isinstance(y, Symbol) else Expression(y, x)
        f_name = func.get_head_name()
        split = _split_ics(eqn.elements, f_name)
        if split is None:
            return super().eval(eqn, y, x, evaluation)
        odes, ics = split
        if len(odes) != 1:
            return super().eval(eqn, y, x, evaluation)
        conv = {"converted_functions": {f_name}}
        sym_func = func.to_sympy(**conv)
        sym_eq = odes[0].to_sympy(**conv)
        x_s = x.to_sympy()
        if sym_func is None or sym_eq is None:
            return None
        fn = sym_func.func
        ics_s = {}
        for c in ics:
            lhs, rhs = c.elements
            r = rhs.to_sympy()
            if r is None:
                return None
            if lhs.get_head_name() == f_name:
                ics_s[fn(lhs.elements[0].to_sympy())] = r
            else:
                order = _derivative_order(lhs)
                pt = lhs.elements[0].to_sympy()
                ics_s[sympy.Derivative(fn(x_s), (x_s, order)).subs(x_s, pt)] = r
        try:
            sol = sympy.dsolve(sym_eq, sym_func, ics=ics_s)
        except (ValueError, NotImplementedError, TypeError, AttributeError, KeyError):
            return None
        sols = sol if isinstance(sol, list) else [sol]
        out = []
        for s in sols:
            conv_s = from_sympy(s)
            if isinstance(y, Symbol):
                out.append(ListExpression(Expression(SymbolRule, y, Expression(SymbolFunction, ListExpression(x), conv_s.elements[1]))))
            else:
                out.append(ListExpression(Expression(SymbolRule, *conv_s.elements)))
        return ListExpression(*out)


# ---------------------------------------------------------------------------
# NDSolve -> InterpolatingFunction
# ---------------------------------------------------------------------------

class InterpolatingFunction(Builtin):
    """
    'InterpolatingFunction[{{x0, x1}}, data]' represents a numerical solution;
    apply it to a number to interpolate.
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical interpolating function (from NDSolve)"

    def eval_apply(self, dom, data, t, evaluation):
        "InterpolatingFunction[dom_List, data_List][t_?NumericQ]"
        import numpy as np
        try:
            xs = np.array([float(e.to_python()) for e in data.elements[0].elements])
            ys = np.array([float(e.to_python()) for e in data.elements[1].elements])
            tv = float(t.to_sympy())
        except Exception:
            return None
        lo, hi = xs[0], xs[-1]
        if tv < min(lo, hi) - 1e-12 or tv > max(lo, hi) + 1e-12:
            evaluation.message("InterpolatingFunction", "dmval", t)
            return None
        from scipy.interpolate import CubicSpline
        order = np.argsort(xs)
        cs = CubicSpline(xs[order], ys[order])
        return MachineReal(float(cs(tv)))

    messages = {"dmval": "Input value `1` lies outside the range of data in the interpolating function."}


def _mathics_list_of_reals(values):
    return ListExpression(*(MachineReal(float(v)) for v in values))


class NDSolve(Builtin):
    """
    >> sol = NDSolve[{y'[x] == y[x], y[0] == 1}, y, {x, 0, 1}]; (y[1] /. sol[[1]])
     = 2.71828
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"MaxSteps": "10000", "PrecisionGoal": "Automatic", "AccuracyGoal": "Automatic"}
    messages = {
        "ndinnt": "Initial conditions must be numeric.",
        "ndode": "Could not convert the equations to a first-order system.",
    }
    summary_text = "numerical solution of ordinary differential equations"

    def eval(self, eqns, y, rng, evaluation, options):
        "NDSolve[eqns_List, y_, rng_List, OptionsPattern[NDSolve]]"
        if not rng.has_form("List", 3):
            return None
        x, x0, x1 = rng.elements
        if not isinstance(x, Symbol):
            return None
        funcs = y.elements if y.has_form("List", None) else (y,)
        if not all(isinstance(f, Symbol) for f in funcs):
            return None
        names = [f.get_name() for f in funcs]
        conv = {"converted_functions": set(names)}
        x_s = x.to_sympy()
        try:
            t0, t1 = float(x0.to_sympy()), float(x1.to_sympy())
        except Exception:
            return None

        # Build sympy ODE system and ICs.
        odes, ics = [], {}
        for e in eqns.elements:
            if e.get_head_name() != "System`Equal":
                return None
            lhs, rhs = e.elements
            head = lhs.get_head_name()
            if head in names and lhs.elements and lhs.elements[0].is_numeric():
                v = rhs.to_sympy()
                if v is None or not v.is_number:
                    evaluation.message("NDSolve", "ndinnt")
                    return None
                ics[(head, 0)] = float(v)
            elif (any(_is_derivative_of(lhs, n) for n in names) and lhs.elements and lhs.elements[0].is_numeric()):
                order = _derivative_order(lhs)
                v = rhs.to_sympy()
                if v is None or not v.is_number:
                    evaluation.message("NDSolve", "ndinnt")
                    return None
                ics[(lhs.head.elements[0].get_name(), order)] = float(v)
            else:
                s = e.to_sympy(**conv)
                if s is None:
                    return None
                odes.append(s)

        fns = {n: sympy.Function(n.split("`")[-1]) for n in names}
        # Mathics converts y[x] with converted_functions to Function(name)(x); fetch actual funcs
        actual = {}
        for ode in odes:
            for f in ode.atoms(sympy.Function):
                nm = f.func.__name__
                for n in names:
                    if nm == n or nm.endswith(n.split("`")[-1]) or n.endswith(nm):
                        actual[n] = f.func
        if len(actual) != len(names):
            return None

        # Reduce to first-order system: state vector = [y, y', ..., y^(k-1)] per function
        orders = {}
        for n in names:
            k = 0
            for ode in odes:
                for d in ode.atoms(sympy.Derivative):
                    if d.expr.func == actual[n]:
                        k = max(k, sum(c for _, c in d.variable_count))
            orders[n] = max(k, 1)
        state = []
        for n in names:
            for j in range(orders[n]):
                state.append((n, j))
        syms = {st: sympy.Symbol(f"_s{i}") for i, st in enumerate(state)}
        # Solve each ODE for the highest derivative
        rhs_exprs = {}
        for n in names:
            top = sympy.Derivative(actual[n](x_s), (x_s, orders[n]))
            sol = None
            for ode in odes:
                eq = ode.lhs - ode.rhs if isinstance(ode, sympy.Eq) else ode
                if eq.has(top):
                    try:
                        s = sympy.solve(eq, top)
                    except Exception:
                        s = []
                    if s:
                        sol = s[0]
                        break
            if sol is None:
                evaluation.message("NDSolve", "ndode")
                return None
            # substitute lower derivatives / functions by state symbols
            for m in names:
                for j in range(orders[m] - 1, -1, -1):
                    target = sympy.Derivative(actual[m](x_s), (x_s, j)) if j else actual[m](x_s)
                    sol = sol.subs(target, syms[(m, j)])
            rhs_exprs[n] = sol
        f_lambdas = []
        for (n, j) in state:
            if j < orders[n] - 1:
                f_lambdas.append(syms[(n, j + 1)])
            else:
                f_lambdas.append(rhs_exprs[n])
        try:
            F = sympy.lambdify([x_s] + [syms[s] for s in state], f_lambdas, modules=["numpy", "math"])
        except Exception:
            return None
        y0 = []
        for (n, j) in state:
            if (n, j) not in ics:
                evaluation.message("NDSolve", "ndinnt")
                return None
            y0.append(ics[(n, j)])

        import numpy as np
        from scipy.integrate import solve_ivp
        try:
            res = solve_ivp(lambda t, s: np.array(F(t, *s), dtype=float), (t0, t1), y0, rtol=1e-9, atol=1e-11, dense_output=True, max_step=abs(t1 - t0) / 50)
        except Exception:
            return None
        if not res.success:
            return None
        ts = np.linspace(t0, t1, 401)
        vals = res.sol(ts)
        rules = []
        for i, n in enumerate(names):
            idx = state.index((n, 0))
            data = ListExpression(_mathics_list_of_reals(ts), _mathics_list_of_reals(vals[idx]))
            ifun = Expression(SymbolInterpolatingFunction, ListExpression(ListExpression(MachineReal(t0), MachineReal(t1))), data)
            rules.append(Expression(SymbolRule, funcs[i], ifun))
        return ListExpression(ListExpression(*rules))


# ---------------------------------------------------------------------------
# NSum
# ---------------------------------------------------------------------------

class NSum(Builtin):
    """
    >> NSum[1/n^2, {n, 1, Infinity}]
     = 1.64493
    """
    attributes = A_HOLD_ALL | A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical summation"

    def eval(self, f, spec, evaluation):
        "NSum[f_, spec_List]"
        if not spec.has_form("List", 3):
            return None
        n, a, b = spec.elements
        if not isinstance(n, Symbol):
            return None
        n_s = n.to_sympy()
        f_s = f.evaluate(evaluation).to_sympy(convert_all_global_functions=True)
        a_e, b_e = a.evaluate(evaluation), b.evaluate(evaluation)
        if f_s is None:
            return None
        import mpmath
        try:
            g = sympy.lambdify(n_s, f_s, modules=["mpmath"])
        except Exception:
            return None
        lo = a_e.to_sympy()
        inf = b_e.get_name() == "System`Infinity" or (b_e.has_form("DirectedInfinity", 1))
        try:
            if inf:
                val = mpmath.nsum(lambda k: g(k), [int(lo), mpmath.inf])
            else:
                hi = b_e.to_sympy()
                val = mpmath.fsum(g(k) for k in range(int(lo), int(hi) + 1))
        except Exception:
            return None
        v = complex(val)
        if abs(v.imag) < 1e-15 * max(1.0, abs(v.real)):
            return MachineReal(v.real)
        return from_sympy(sympy.Float(v.real) + sympy.I * sympy.Float(v.imag))


# ---------------------------------------------------------------------------
# NMinimize / NMaximize
# ---------------------------------------------------------------------------

def _nopt(f, vars, evaluation, sign):
    if vars.has_form("List", None):
        vs = list(vars.elements)
    else:
        vs = [vars]
    if not all(isinstance(v, Symbol) for v in vs):
        return None
    cons = []
    if f.has_form("List", None):
        obj = f.elements[0]
        cons = list(f.elements[1:])
    else:
        obj = f
    vs_s = [v.to_sympy() for v in vs]
    obj_s = obj.to_sympy()
    if obj_s is None:
        return None
    import numpy as np
    from scipy.optimize import differential_evolution, minimize
    try:
        fun = sympy.lambdify(vs_s, sign * obj_s, modules=["numpy", "math"])
    except Exception:
        return None
    # constraints: inequalities g >= 0 or equalities; bounds from a <= x <= b patterns
    bounds = [[-10.0, 10.0] for _ in vs]
    scipy_cons = []
    for c in cons:
        head = c.get_head_name()
        el = c.elements
        if head in ("System`GreaterEqual", "System`Greater", "System`LessEqual", "System`Less") and len(el) == 2:
            lhs, rhs = el[0].to_sympy(), el[1].to_sympy()
            if lhs is None or rhs is None:
                return None
            g = (lhs - rhs) if head.startswith("System`Greater") else (rhs - lhs)
            # simple bound?
            if lhs in vs_s and rhs.is_number:
                i = vs_s.index(lhs)
                if head.startswith("System`Greater"):
                    bounds[i][0] = float(rhs)
                else:
                    bounds[i][1] = float(rhs)
            elif rhs in vs_s and lhs.is_number:
                i = vs_s.index(rhs)
                if head.startswith("System`Greater"):
                    bounds[i][1] = float(lhs)
                else:
                    bounds[i][0] = float(lhs)
            else:
                gl = sympy.lambdify(vs_s, g, modules=["numpy", "math"])
                scipy_cons.append({"type": "ineq", "fun": lambda p, gl=gl: gl(*p)})
        elif head == "System`Equal" and len(el) == 2:
            lhs, rhs = el[0].to_sympy(), el[1].to_sympy()
            gl = sympy.lambdify(vs_s, lhs - rhs, modules=["numpy", "math"])
            scipy_cons.append({"type": "eq", "fun": lambda p, gl=gl: gl(*p)})
        elif head in ("System`LessEqual", "System`Less") and len(el) == 3 and el[1] in vs:
            i = vs.index(el[1])
            bounds[i] = [float(el[0].to_sympy()), float(el[2].to_sympy())]
        else:
            return None
    try:
        if scipy_cons:
            x0 = np.array([(b[0] + b[1]) / 2 for b in bounds])
            r = minimize(lambda p: fun(*p), x0, bounds=bounds, constraints=scipy_cons, method="SLSQP")
            best = r
        else:
            r = differential_evolution(lambda p: fun(*p), bounds, tol=1e-12, seed=0, polish=True)
            best = minimize(lambda p: fun(*p), r.x, method="BFGS")
            if not best.success or best.fun > r.fun:
                best = r
    except Exception:
        return None
    val = sign * float(best.fun)
    rules = ListExpression(*(Expression(SymbolRule, v, MachineReal(float(p))) for v, p in zip(vs, best.x)))
    return ListExpression(MachineReal(val), rules)


class NMinimize(Builtin):
    """
    >> NMinimize[(x - 1)^2 + (y - 2)^2, {x, y}]
     = {0., {x -> 1., y -> 2.}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical global minimization"

    def eval(self, f, vars, evaluation):
        "NMinimize[f_, vars_]"
        return _nopt(f, vars, evaluation, 1)


class NMaximize(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical global maximization"

    def eval(self, f, vars, evaluation):
        "NMaximize[f_, vars_]"
        return _nopt(f, vars, evaluation, -1)


def register_numeric_extras(session):
    for cls in (DSolveWithConditions, InterpolatingFunction, NDSolve, NSum, NMinimize, NMaximize):
        cls(expression=False).contribute(session.definitions)
    for name in ("DSolve", "InterpolatingFunction", "NDSolve", "NSum", "NMinimize", "NMaximize"):
        session.definitions.clear_cache(f"System`{name}")
