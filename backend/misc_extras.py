"""Small high-frequency heads missing from Mathics (Wolfram 15.0.1 contracts).

Optimization wrappers     ArgMin / ArgMax, LinearProgramming, KnapsackSolve
Solve-value wrappers      SolveValues / NSolveValues / DSolveValue /
                          NDSolveValue / LinearSolveFunction
Recurrences               RecurrenceTable, FindLinearRecurrence
Small calculus            Wronskian, Residue, GeneratingFunction,
                          ExponentialGeneratingFunction
Logic                     SatisfiabilityQ
Lists                     MovingAverage, MovingMedian,
                          ExponentialMovingAverage, MaximalBy, MinimalBy

Behaviour pinned by differential testing against the real kernel
(wolfram-re-round2/oracle/inputs-misc.txt):

* ArgMin[f, x] returns the argument value (a scalar for one variable, a list
  of values for several), not the {value, rules} pair Minimize returns.
* KnapsackSolve takes items as {payoff, cost} pairs plus a cost bound,
  allows unlimited copies, and returns the copy counts in item order.
* SolveValues flattens single-variable solutions to a plain value list.
* DSolveValue returns the solution expression, not a rule list.
* FindLinearRecurrence stays unevaluated when no recurrence fits all terms.
* SatisfiabilityQ is inert in Wolfram 15.0.1 (SatisfiableQ evaluates); we
  still answer it, so those oracle entries classify as
  "evaluated_but_wolfram_inert" on purpose.

Anything unsupported returns None and the expression stays unevaluated.
"""

from __future__ import annotations

import sympy

from mathics.core.atoms import Integer, MachineReal
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol
from mathics.core.systemsymbols import SymbolRule

SymbolList = Symbol("System`List")
SymbolPlus = Symbol("System`Plus")
SymbolTimes = Symbol("System`Times")
SymbolTrue = Symbol("System`True")
SymbolFalse = Symbol("System`False")


# ---------------------------------------------------------------------------
# ArgMin / ArgMax
# ---------------------------------------------------------------------------

def _linprog_solve(c_obj, a_ub, b_ub, a_eq, b_eq, bounds):
    """Minimize c.x via HiGHS; ties are refined to the lexicographically
    smallest optimal solution (Wolfram's observed vertex choice)."""
    from scipy.optimize import linprog
    res = linprog(c_obj, A_ub=a_ub or None, b_ub=b_ub or None,
                  A_eq=a_eq or None, b_eq=b_eq or None,
                  bounds=bounds, method="highs")
    if not res.success:
        return None
    n = len(c_obj)
    a_eq = [list(r) for r in a_eq] + [list(c_obj)]
    b_eq = list(b_eq) + [float(res.fun)]
    x = list(res.x)
    for i in range(n):
        a2 = [list(r) for r in a_eq]
        b2 = list(b_eq)
        for j in range(i):
            row = [0.0] * n
            row[j] = 1.0
            a2.append(row)
            b2.append(float(x[j]))
        obj = [0.0] * n
        obj[i] = 1.0
        r = linprog(obj, A_ub=a_ub or None, b_ub=b_ub or None,
                    A_eq=a2, b_eq=b2, bounds=bounds, method="highs")
        if not r.success:
            break
        x[i] = r.x[i]
    return x


def _lp_argopt(f, vars, evaluation, minimize):
    """Exact-rational fallback for linear objectives with linear constraints."""
    if f.has_form("List", None):
        obj, cons = f.elements[0], list(f.elements[1:])
    else:
        obj, cons = f, []
    vs = list(vars.elements) if vars.has_form("List", None) else [vars]
    if not vs or not all(isinstance(v, Symbol) for v in vs):
        return None
    vs_s = [v.to_sympy() for v in vs]
    obj_s = obj.to_sympy()
    if obj_s is None or any(v is None for v in vs_s):
        return None

    def linear_parts(g):
        g = sympy.expand(g)
        if not g.is_polynomial(*vs_s) or sympy.Poly(g, *vs_s).total_degree() > 1:
            return None
        coeffs = [float(g.coeff(v)) for v in vs_s]
        const = float(g.subs(dict(zip(vs_s, [0] * len(vs)))))
        return coeffs, const

    if linear_parts(obj_s) is None:
        return None
    c_obj, _ = linear_parts(obj_s)
    a_ub, b_ub, a_eq, b_eq = [], [], [], []
    for c in cons:
        head = c.get_head_name()
        if len(c.elements) != 2 or head not in (
                "System`LessEqual", "System`Less", "System`GreaterEqual",
                "System`Greater", "System`Equal"):
            return None
        lhs, rhs = (e.to_sympy() for e in c.elements)
        if lhs is None or rhs is None:
            return None
        parts = linear_parts(lhs - rhs)
        if parts is None:
            return None
        coeffs, const = parts
        if head in ("System`LessEqual", "System`Less"):
            a_ub.append(coeffs)
            b_ub.append(-const)
        elif head in ("System`GreaterEqual", "System`Greater"):
            a_ub.append([-v for v in coeffs])
            b_ub.append(const)
        else:
            a_eq.append(coeffs)
            b_eq.append(-const)
    from scipy.optimize import linprog  # noqa: F401 (kept import-local)
    x = _linprog_solve([v if minimize else -v for v in c_obj],
                       a_ub, b_ub, a_eq, b_eq, [(None, None)] * len(vs))
    if x is None:
        return None
    vals = [from_sympy(sympy.nsimplify(v, tolerance=1e-9)) for v in x]
    return vals[0] if isinstance(vars, Symbol) else ListExpression(*vals)


def _argopt(f, vars, evaluation, minimize):
    head = Symbol("System`Minimize" if minimize else "System`Maximize")
    res = Expression(head, f, vars).evaluate(evaluation)
    pairs = []
    if res.has_form("List", None):
        for p in res.elements:
            if (p.has_form("List", 2) and p.elements[1].has_form("List", None)
                    and all(r.get_head_name() == "System`Rule" and len(r.elements) == 2
                            for r in p.elements[1].elements)):
                pairs.append(p)
    if not pairs:
        return _lp_argopt(f, vars, evaluation, minimize)
    rules = {r.elements[0].get_name(): r.elements[1] for r in pairs[0].elements[1].elements}
    if isinstance(vars, Symbol):
        return rules.get(vars.get_name())
    if not vars.has_form("List", None):
        return None
    vals = [rules.get(v.get_name()) for v in vars.elements]
    if any(v is None for v in vals):
        return None
    return ListExpression(*vals)


class ArgMin(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "argument that minimizes a function"

    def eval(self, f, vars, evaluation):
        "ArgMin[f_, vars_]"
        try:
            return _argopt(f, vars, evaluation, True)
        except Exception:
            return None


class ArgMax(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "argument that maximizes a function"

    def eval(self, f, vars, evaluation):
        "ArgMax[f_, vars_]"
        try:
            return _argopt(f, vars, evaluation, False)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# LinearProgramming / KnapsackSolve
# ---------------------------------------------------------------------------

def _float_vector(exprs):
    out = []
    for e in exprs:
        s = e.to_sympy()
        if s is None or not s.is_number:
            return None
        out.append(float(s))
    return out


def _float_matrix(m):
    rows = []
    for row in m.elements:
        if not row.has_form("List", None):
            return None
        r = _float_vector(row.elements)
        if r is None:
            return None
        rows.append(r)
    return rows


class LinearProgramming(Builtin):
    """Minimize c.x subject to m.x >= b and x >= 0; b entries may be
    {bi, si} pairs with si > 0, == 0, < 0 meaning >=, ==, <=."""

    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "linear programming in matrix form"

    def eval(self, c, m, b, evaluation):
        "LinearProgramming[c_List, m_List, b_List]"
        try:
            c_f = _float_vector(c.elements)
            m_f = _float_matrix(m)
            if c_f is None or m_f is None or any(len(r) != len(c_f) for r in m_f):
                return None
            a_ub, b_ub, a_eq, b_eq = [], [], [], []
            for row, bi in zip(m_f, b.elements):
                if bi.has_form("List", 2):
                    sense = bi.elements[1].get_int_value()
                    if sense is None:
                        return None
                    vals = _float_vector(bi.elements[:1])
                    if vals is None:
                        return None
                    bv = vals[0]
                    if sense > 0:
                        a_ub.append([-v for v in row])
                        b_ub.append(-bv)
                    elif sense < 0:
                        a_ub.append(row)
                        b_ub.append(bv)
                    else:
                        a_eq.append(row)
                        b_eq.append(bv)
                else:
                    s = bi.to_sympy()
                    if s is None or not s.is_number:
                        return None
                    a_ub.append([-v for v in row])
                    b_ub.append(-float(s))
            from scipy.optimize import linprog  # noqa: F401 (kept import-local)
            x = _linprog_solve(c_f, a_ub, b_ub, a_eq, b_eq, [(0, None)] * len(c_f))
            if x is None:
                return None
            return ListExpression(*(from_sympy(sympy.nsimplify(v, tolerance=1e-9)) for v in x))
        except Exception:
            return None


class KnapsackSolve(Builtin):
    """Items are {payoff, cost} pairs; unlimited copies; maximize total
    payoff with total cost <= maxcost; returns copy counts per item."""

    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "unbounded knapsack problem"

    def eval(self, items, maxcost, evaluation):
        "KnapsackSolve[items_List, maxcost_]"
        try:
            pairs = []
            for it in items.elements:
                if not it.has_form("List", 2):
                    return None
                p, w = (e.get_int_value() for e in it.elements)
                if p is None or w is None or w <= 0:
                    return None
                pairs.append((p, w))
            cap = maxcost.get_int_value()
            if cap is None or cap < 0 or not pairs:
                return None
            n = len(pairs)
            # dp[c] = (best payoff, counts) for exact cost c; update on ties so
            # later items are preferred (matches the observed kernel choices).
            dp = [None] * (cap + 1)
            dp[0] = (0, [0] * n)
            for i, (p, w) in enumerate(pairs):
                for c in range(w, cap + 1):
                    prev = dp[c - w]
                    if prev is None:
                        continue
                    cand = prev[0] + p
                    if dp[c] is None or cand >= dp[c][0]:
                        vec = prev[1][:]
                        vec[i] += 1
                        dp[c] = (cand, vec)
            best = None
            for c in range(cap + 1):
                if dp[c] is not None and (best is None or dp[c][0] > best[0]):
                    best = dp[c]
            if best is None:
                return None
            return ListExpression(*(Integer(v) for v in best[1]))
        except Exception:
            return None


# ---------------------------------------------------------------------------
# SolveValues / NSolveValues
# ---------------------------------------------------------------------------

def _rules_to_values(res, vars):
    """{{x -> a}, {x -> b}} -> {a, b} (single var) or {{a, b}, ...} (list)."""
    if not res.has_form("List", None):
        return None
    single = isinstance(vars, Symbol)
    if not single and not vars.has_form("List", None):
        return None
    names = [vars.get_name()] if single else [v.get_name() for v in vars.elements]
    out = []
    for sol in res.elements:
        if not sol.has_form("List", None):
            return None
        rules = {}
        for r in sol.elements:
            if r.get_head_name() != "System`Rule" or len(r.elements) != 2:
                return None
            rules[r.elements[0].get_name()] = r.elements[1]
        vals = [rules.get(nm) for nm in names]
        if any(v is None for v in vals):
            return None
        out.append(vals[0] if single else ListExpression(*vals))
    return ListExpression(*out)


def _domain_filter(values, dom):
    """Keep solutions whose values all lie in Reals / Integers / Complexes."""
    name = dom.get_name()
    if name not in ("System`Reals", "System`Integers", "System`Complexes"):
        return None
    if name == "System`Complexes":
        return values
    out = []
    for sol in values.elements:
        vals = sol.elements if sol.has_form("List", None) else (sol,)
        ok = True
        for v in vals:
            s = v.to_sympy()
            if s is None:
                return None
            if name == "System`Reals" and not (s.is_real or (s.is_number and s == sympy.re(s))):
                ok = False
                break
            if name == "System`Integers" and not s.is_integer:
                ok = False
                break
        if ok:
            out.append(sol)
    return ListExpression(*out)


class SolveValues(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "solutions of equations as values instead of rules"

    def eval(self, eqns, vars, evaluation):
        "SolveValues[eqns_, vars_]"
        try:
            res = Expression(Symbol("System`Solve"), eqns, vars).evaluate(evaluation)
            return _rules_to_values(res, vars)
        except Exception:
            return None

    def eval_domain(self, eqns, vars, dom, evaluation):
        "SolveValues[eqns_, vars_, dom_Symbol]"
        try:
            res = Expression(Symbol("System`Solve"), eqns, vars).evaluate(evaluation)
            values = _rules_to_values(res, vars)
            if values is None:
                return None
            return _domain_filter(values, dom)
        except Exception:
            return None


class NSolveValues(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical solutions of equations as values instead of rules"

    def eval(self, eqns, vars, evaluation):
        "NSolveValues[eqns_, vars_]"
        try:
            res = Expression(Symbol("System`NSolve"), eqns, vars).evaluate(evaluation)
            return _rules_to_values(res, vars)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# DSolveValue / NDSolveValue / LinearSolveFunction
# ---------------------------------------------------------------------------

class DSolveValue(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "solution of a differential equation as an expression"

    def eval(self, eqn, y, x, evaluation):
        "DSolveValue[eqn_, y_, x_]"
        try:
            res = Expression(Symbol("System`DSolve"), eqn, y, x).evaluate(evaluation)
            if not res.has_form("List", None) or not res.elements:
                return None
            vals = []
            for sol in res.elements:
                if not sol.has_form("List", None) or len(sol.elements) != 1:
                    return None
                r = sol.elements[0]
                if r.get_head_name() != "System`Rule" or len(r.elements) != 2:
                    return None
                vals.append(r.elements[1])
            return vals[0] if len(vals) == 1 else ListExpression(*vals)
        except Exception:
            return None


def _ode_function_names(eqns):
    """Symbols used as function heads in ODEs / initial conditions."""
    names = []

    def add(sym):
        if isinstance(sym, Symbol) and sym.get_name() not in names:
            names.append(sym.get_name())

    def scan(e):
        if not isinstance(e, Expression):
            return
        head = e.get_head_name()
        if head == "System`Equal" and len(e.elements) == 2:
            scan(e.elements[0])
            scan(e.elements[1])
            return
        h = e.head
        if isinstance(h, Symbol) and not head.startswith("System`"):
            add(h)
        elif (isinstance(h, Expression) and isinstance(h.head, Expression)
              and h.head.head.get_name() == "System`Derivative"):
            add(h.head.elements[0])

    for eq in eqns.elements:
        scan(eq)
    return names


class NDSolveValue(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "numerical solution of a differential equation as a value"

    def eval(self, eqns, expr, rng, evaluation):
        "NDSolveValue[eqns_List, expr_, rng_List]"
        try:
            names = _ode_function_names(eqns)
            if not names:
                return None
            y = Symbol(names[0]) if len(names) == 1 else ListExpression(*(Symbol(n) for n in names))
            res = Expression(Symbol("System`NDSolve"), eqns, y, rng).evaluate(evaluation)
            if not res.has_form("List", None) or not res.elements:
                return None
            rules = res.elements[0]
            return Expression(Symbol("System`ReplaceAll"), expr, rules).evaluate(evaluation)
        except Exception:
            return None


class LinearSolveFunction(Builtin):
    """Stored LU factorization; applying it to a vector solves the system."""

    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "reusable linear solver"

    def eval_apply(self, m, b, evaluation):
        "LinearSolveFunction[m_List][b_]"
        try:
            return Expression(Symbol("System`LinearSolve"), m, b).evaluate(evaluation)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# RecurrenceTable / FindLinearRecurrence
# ---------------------------------------------------------------------------

def _contains_head(e, name):
    if e.get_head_name() == name:
        return True
    if isinstance(e, Expression):
        if isinstance(e.head, Expression) and _contains_head(e.head, name):
            return True
        return any(_contains_head(el, name) for el in e.elements)
    return False


class RecurrenceTable(Builtin):
    """RecurrenceTable[{a[n] == f, a[k0] == v0, ...}, a, {n, nmin, nmax}]
    generates values by iterating the recurrence."""

    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "table of values from a recurrence relation"

    def eval(self, eqns, a, rng, evaluation):
        "RecurrenceTable[eqns_, a_Symbol, rng_List]"
        try:
            if not rng.has_form("List", 3):
                return None
            n, nmin, nmax = rng.elements
            if not isinstance(n, Symbol):
                return None
            lo, hi = nmin.get_int_value(), nmax.get_int_value()
            if lo is None or hi is None:
                return None
            if hi < lo:
                return ListExpression()
            eq_list = eqns.elements if eqns.has_form("List", None) else (eqns,)
            fname = a.get_name()
            rec, ics = None, {}
            for e in eq_list:
                if e.get_head_name() != "System`Equal" or len(e.elements) != 2:
                    return None
                lhs, rhs = e.elements
                if lhs.get_head_name() != fname or len(lhs.elements) != 1:
                    return None
                arg = lhs.elements[0]
                k = arg.get_int_value()
                if k is not None:
                    ics[k] = rhs
                elif isinstance(arg, Symbol) and arg.get_name() == n.get_name():
                    rec = rhs
                else:
                    return None
            if rec is None:
                return None
            vals = dict(ics)
            out = []
            for k in range(lo, hi + 1):
                if k in ics:
                    v = ics[k]
                else:
                    # substitute n -> k first so a[n-1] collapses to a[k-1],
                    # then replace the known values.
                    v = Expression(Symbol("System`ReplaceAll"), rec,
                                   Expression(SymbolRule, n, Integer(k))).evaluate(evaluation)
                    rules = [Expression(SymbolRule, Expression(a, Integer(j)), vals[j])
                             for j in vals]
                    v = Expression(Symbol("System`ReplaceAll"), v,
                                   ListExpression(*rules)).evaluate(evaluation)
                    if _contains_head(v, fname):
                        return None
                    vals[k] = v
                out.append(v)
            return ListExpression(*out)
        except Exception:
            return None


def _berlekamp_massey(seq):
    """Shortest LFSR over QQ; returns (L, C) with sum_i C[i] s[n-i] == 0."""
    C, B, L, m, b = [sympy.Rational(1)], [sympy.Rational(1)], 0, 1, sympy.Rational(1)
    for n in range(len(seq)):
        d = seq[n] + sum(C[i] * seq[n - i] for i in range(1, L + 1))
        if d == 0:
            m += 1
        elif 2 * L <= n:
            T = C[:]
            coef = d / b
            C += [sympy.Rational(0)] * (len(B) + m - len(C))
            for i in range(len(B)):
                C[i + m] -= coef * B[i]
            L, B, b, m = n + 1 - L, T, d, 1
        else:
            coef = d / b
            C += [sympy.Rational(0)] * (len(B) + m - len(C))
            for i in range(len(B)):
                C[i + m] -= coef * B[i]
            m += 1
    return L, C


class FindLinearRecurrence(Builtin):
    """Berlekamp-Massey over the rationals; the candidate is verified
    against every given term and rejected (unevaluated) on mismatch."""

    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "coefficients of a minimal linear recurrence"

    def eval(self, lst, evaluation):
        "FindLinearRecurrence[lst_List]"
        try:
            seq = []
            for e in lst.elements:
                s = e.to_sympy()
                if s is None or not isinstance(s, (sympy.Integer, sympy.Rational)):
                    return None
                seq.append(sympy.Rational(s))
            if len(seq) < 2:
                return None
            L, C = _berlekamp_massey(seq)
            if L == 0:
                return ListExpression()
            if len(seq) < 2 * L:
                return None
            coeffs = [-C[i] for i in range(1, L + 1)]
            for i in range(L, len(seq)):
                if seq[i] != sum(coeffs[j] * seq[i - 1 - j] for j in range(L)):
                    return None
            return ListExpression(*(from_sympy(c) for c in coeffs))
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Wronskian / Residue
# ---------------------------------------------------------------------------

class Wronskian(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Wronskian determinant of a list of functions"

    def eval(self, funcs, x, evaluation):
        "Wronskian[funcs_List, x_Symbol]"
        try:
            fs = [f.to_sympy() for f in funcs.elements]
            x_s = x.to_sympy()
            if any(f is None for f in fs) or x_s is None:
                return None
            w = sympy.simplify(sympy.wronskian(fs, x_s))
            return from_sympy(w)
        except Exception:
            return None


class Residue(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "residue of an expression at a point"

    def eval(self, f, spec, evaluation):
        "Residue[f_, spec_List]"
        try:
            if not spec.has_form("List", 2):
                return None
            x, x0 = spec.elements
            if not isinstance(x, Symbol):
                return None
            f_s, x_s, x0_s = f.to_sympy(), x.to_sympy(), x0.to_sympy()
            if f_s is None or x_s is None or x0_s is None:
                return None
            return from_sympy(sympy.residue(f_s, x_s, x0_s))
        except Exception:
            return None


# ---------------------------------------------------------------------------
# GeneratingFunction / ExponentialGeneratingFunction
# ---------------------------------------------------------------------------

def _strip_piecewise(s):
    """Replace Piecewise branches by their generic-domain value (Wolfram
    drops convergence conditions); returns None if a Sum survives."""
    if isinstance(s, sympy.Piecewise):
        for val, _ in s.args:
            if not val.has(sympy.Sum):
                return _strip_piecewise(val)
        return None
    if not s.is_Atom and s.args:
        args = [_strip_piecewise(a) for a in s.args]
        if any(a is None for a in args):
            return None
        return s.func(*args)
    return s


def _generating_function(expr, n, x, exponential):
    if not isinstance(n, Symbol) or not isinstance(x, Symbol):
        return None
    e_s, x_s = expr.to_sympy(), x.to_sympy()
    if e_s is None or x_s is None:
        return None
    n_plain = n.to_sympy()
    n_s = sympy.Symbol(n_plain.name, integer=True, nonnegative=True)
    e_s = e_s.subs(n_plain, n_s)
    if e_s.has(sympy.fibonacci):
        phi = sympy.GoldenRatio
        rt5 = sympy.sqrt(5)
        e_s = e_s.replace(sympy.fibonacci, lambda k: (phi ** k - (1 - phi) ** k) / rt5)
    term = e_s * x_s ** n_s
    if exponential:
        term = term / sympy.factorial(n_s)
    try:
        s = sympy.summation(term, (n_s, 0, sympy.oo))
    except Exception:
        return None
    s = _strip_piecewise(s)
    if not isinstance(s, sympy.Expr) or s.has(sympy.Sum) or s.has(n_s):
        return None
    return from_sympy(sympy.simplify(sympy.together(s)))


class GeneratingFunction(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "ordinary generating function of a sequence"

    def eval(self, expr, n, x, evaluation):
        "GeneratingFunction[expr_, n_Symbol, x_Symbol]"
        try:
            return _generating_function(expr, n, x, False)
        except Exception:
            return None


class ExponentialGeneratingFunction(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "exponential generating function of a sequence"

    def eval(self, expr, n, x, evaluation):
        "ExponentialGeneratingFunction[expr_, n_Symbol, x_Symbol]"
        try:
            return _generating_function(expr, n, x, True)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# SatisfiabilityQ
# ---------------------------------------------------------------------------

class SatisfiabilityQ(Builtin):
    """NB: inert in Wolfram 15.0.1 (SatisfiableQ evaluates there); we answer
    it anyway via sympy's SAT solver."""

    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test whether a Boolean expression is satisfiable"

    _CONNECTIVES = {
        "System`And": sympy.And,
        "System`Or": sympy.Or,
        "System`Not": sympy.Not,
        "System`Xor": sympy.Xor,
        "System`Equivalent": sympy.Equivalent,
        "System`Implies": sympy.Implies,
        "System`Nand": sympy.Nand,
        "System`Nor": sympy.Nor,
    }

    def _to_logic(self, expr):
        name = expr.get_head_name()
        if name in ("System`True",):
            return sympy.true
        if name in ("System`False",):
            return sympy.false
        if isinstance(expr, Symbol):
            s = expr.to_sympy()
            return sympy.Symbol(s.name) if s is not None else None
        if isinstance(expr, Expression) and name in self._CONNECTIVES and expr.elements:
            args = [self._to_logic(e) for e in expr.elements]
            if any(a is None for a in args):
                return None
            return self._CONNECTIVES[name](*args)
        return None

    def eval(self, expr, vars, evaluation):
        "SatisfiabilityQ[expr_, vars_]"
        try:
            e_s = self._to_logic(expr)
            if e_s is None:
                return None
            from sympy.logic.inference import satisfiable
            return SymbolTrue if satisfiable(e_s) is not False else SymbolFalse
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Moving statistics / extremal-by
# ---------------------------------------------------------------------------

class MovingAverage(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "moving average of a list"

    def eval(self, lst, n, evaluation):
        "MovingAverage[lst_List, n_Integer]"
        try:
            k = n.get_int_value()
            if not k or k < 1:
                return None
            elems = lst.elements
            if k > len(elems):
                return ListExpression()
            mean = Symbol("System`Mean")
            return ListExpression(*(
                Expression(mean, ListExpression(*elems[i:i + k])).evaluate(evaluation)
                for i in range(len(elems) - k + 1)))
        except Exception:
            return None


class MovingMedian(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "moving median of a list"

    def eval(self, lst, n, evaluation):
        "MovingMedian[lst_List, n_Integer]"
        try:
            k = n.get_int_value()
            if not k or k < 1:
                return None
            elems = lst.elements
            if k > len(elems):
                return ListExpression()
            median = Symbol("System`Median")
            return ListExpression(*(
                Expression(median, ListExpression(*elems[i:i + k])).evaluate(evaluation)
                for i in range(len(elems) - k + 1)))
        except Exception:
            return None


class ExponentialMovingAverage(Builtin):
    """y[0] = x[0];  y[t] = alpha x[t] + (1 - alpha) y[t-1]."""

    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "exponential moving average of a list"

    def eval(self, lst, alpha, evaluation):
        "ExponentialMovingAverage[lst_List, alpha_]"
        try:
            elems = lst.elements
            if not elems:
                return ListExpression()
            one_minus = Expression(SymbolPlus, Integer(1),
                                   Expression(SymbolTimes, Integer(-1), alpha)).evaluate(evaluation)
            out = [elems[0]]
            cur = elems[0]
            for e in elems[1:]:
                cur = Expression(SymbolPlus,
                                 Expression(SymbolTimes, alpha, e),
                                 Expression(SymbolTimes, one_minus, cur)).evaluate(evaluation)
                out.append(cur)
            return ListExpression(*out)
        except Exception:
            return None


def _extremal_by(lst, f, count, evaluation, maximal):
    elems = list(lst.elements)
    keys = []
    for e in elems:
        s = Expression(f, e).evaluate(evaluation).to_sympy()
        if s is None:
            return None
        if s.is_number:
            c = complex(s)
            keys.append((0, c.real, c.imag))
        else:
            keys.append((1, repr(sympy.default_sort_key(s))))
    if not keys:
        return ListExpression()
    if count is None:
        best = max(keys) if maximal else min(keys)
        return ListExpression(*(e for e, k in zip(elems, keys) if k == best))
    order = sorted(range(len(elems)), key=lambda i: keys[i], reverse=maximal)
    return ListExpression(*(elems[i] for i in order[:count]))


class MaximalBy(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "elements with maximal function values"

    def eval(self, lst, f, evaluation):
        "MaximalBy[lst_List, f_]"
        try:
            return _extremal_by(lst, f, None, evaluation, True)
        except Exception:
            return None

    def eval_n(self, lst, f, n, evaluation):
        "MaximalBy[lst_List, f_, n_Integer]"
        try:
            count = n.get_int_value()
            if count is None or count < 0:
                return None
            return _extremal_by(lst, f, count, evaluation, True)
        except Exception:
            return None


class MinimalBy(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "elements with minimal function values"

    def eval(self, lst, f, evaluation):
        "MinimalBy[lst_List, f_]"
        try:
            return _extremal_by(lst, f, None, evaluation, False)
        except Exception:
            return None

    def eval_n(self, lst, f, n, evaluation):
        "MinimalBy[lst_List, f_, n_Integer]"
        try:
            count = n.get_int_value()
            if count is None or count < 0:
                return None
            return _extremal_by(lst, f, count, evaluation, False)
        except Exception:
            return None


def register_misc_extras(session):
    classes = (ArgMin, ArgMax, LinearProgramming, KnapsackSolve, SolveValues,
               NSolveValues, DSolveValue, NDSolveValue, LinearSolveFunction,
               RecurrenceTable, FindLinearRecurrence, Wronskian, Residue,
               GeneratingFunction, ExponentialGeneratingFunction, SatisfiabilityQ,
               MovingAverage, MovingMedian, ExponentialMovingAverage,
               MaximalBy, MinimalBy)
    for cls in classes:
        cls(expression=False).contribute(session.definitions)
    for cls in classes:
        session.definitions.clear_cache(f"System`{cls.__name__}")
