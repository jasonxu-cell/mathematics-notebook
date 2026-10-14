"""Post-processing that brings results closer to Wolfram's preferred forms.

Found by differential testing against the real kernel (wolfram-re-round2/oracle):

* RSolve: SymPy returns Binet's formula; Wolfram returns Fibonacci[n] / LucasL[n].
  A solution of the form (c1 phi^n + c2 psi^n) is matched against Fibonacci and
  Lucas sequences by exact comparison at n = 0..7, and rewritten when it agrees.
* DSolve: Sqrt[nu^2] in Bessel orders becomes nu (Wolfram assumes the generic
  branch for a symbolic order).
* Sum: a Piecewise whose first branch has a convergence condition on the free
  parameter (Abs[x] <= 1, x != 1 ...) is reduced to that branch, as Wolfram
  reports the generic-domain result without the condition.
"""

from __future__ import annotations

import sympy

from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.symbols import Symbol

from mathics.builtin.recurrence import RSolve as _NativeRSolve
from numeric_extras import DSolveWithConditions
from symbolic_extras import SumWithFibonacci


def _rewrite_binet(expr, n):
    """c1 phi^n + c2 psi^n  ->  a Fibonacci(n) + b Lucas(n) when exact."""
    if not expr.has(sympy.sqrt(5)):
        return expr
    F = sympy.fibonacci
    L = sympy.lucas
    samples = [sympy.nsimplify(sympy.simplify(expr.subs(n, k))) for k in range(0, 6)]
    if any(s.free_symbols for s in samples):
        return expr
    # Solve a*F(k) + b*L(k) == sample(k) from k=0,1 then verify on the rest
    a, b = sympy.symbols("a b")
    sol = sympy.solve([a * F(0) + b * L(0) - samples[0], a * F(1) + b * L(1) - samples[1]], [a, b], dict=True)
    if not sol:
        return expr
    av, bv = sol[0][a], sol[0][b]
    if all(sympy.simplify(av * F(k) + bv * L(k) - samples[k]) == 0 for k in range(2, 6)):
        out = av * F(n) + bv * L(n)
        return sympy.simplify(out) if (av == 0 or bv == 0) else out
    return expr


class RSolveWithFibonacci(_NativeRSolve):
    name = "RSolve"
    context = "System`"

    def eval(self, eqns, a, n, evaluation):
        "RSolve[eqns_, a_, n_]"
        native = super().eval(eqns, a, n, evaluation)
        if native is None or not isinstance(n, Symbol):
            return native
        n_s = sympy.Symbol(n.to_sympy().name, integer=True, nonnegative=True)

        def fix(e):
            if e.get_head_name() == "System`Rule" and len(e.elements) == 2:
                rhs = e.elements[1].to_sympy()
                if rhs is not None and isinstance(rhs, sympy.Expr):
                    new = _rewrite_binet(rhs.subs(n.to_sympy(), n_s), n_s).subs(n_s, n.to_sympy())
                    if new != rhs:
                        return Expression(Symbol("System`Rule"), e.elements[0], from_sympy(new))
                return e
            if isinstance(e, Expression):
                return Expression(e.head, *(fix(x) for x in e.elements))
            return e

        return fix(native)


class DSolvePolished(DSolveWithConditions):
    name = "DSolve"
    context = "System`"

    def eval(self, eqn, y, x, evaluation):
        "DSolve[eqn_, y_, x_]"
        native = super().eval(eqn, y, x, evaluation)
        if native is None:
            return native

        def fix(e):
            if e.get_head_name() == "System`Sqrt" and len(e.elements) == 1:
                inner = e.elements[0]
                if inner.get_head_name() == "System`Power" and len(inner.elements) == 2 and inner.elements[1].get_int_value() == 2 and isinstance(inner.elements[0], Symbol):
                    return inner.elements[0]
            if e.get_head_name() == "System`Power" and len(e.elements) == 2:
                base, exp = e.elements
                if exp.to_sympy() == sympy.Rational(1, 2) and base.get_head_name() == "System`Power" and len(base.elements) == 2 and base.elements[1].get_int_value() == 2 and isinstance(base.elements[0], Symbol):
                    return base.elements[0]
            if isinstance(e, Expression):
                return Expression(fix(e.head) if isinstance(e.head, Expression) else e.head, *(fix(x) for x in e.elements))
            return e

        return fix(native)


class SumPolished(SumWithFibonacci):
    name = "Sum"
    context = "System`"

    def eval_iter_nostep(self, expr, i, imin, imax, evaluation):
        "%(name)s[expr_, {i_Symbol, imin_, imax_}]"
        r = super().eval_iter_nostep(expr, i, imin, imax, evaluation)
        if r is not None and r.get_head_name() == "System`Piecewise" and r.elements:
            cases = r.elements[0]
            if cases.has_form("List", None) and cases.elements:
                first = cases.elements[0]
                if first.has_form("List", 2):
                    value, cond = first.elements
                    # keep the generic-domain value, drop the convergence condition
                    if not (isinstance(value, Expression) and value.get_head_name() == "System`Sum"):
                        return value
        return r


def register_result_polish(session):
    for cls in (RSolveWithFibonacci, DSolvePolished, SumPolished):
        cls(expression=False).contribute(session.definitions)
    for name in ("RSolve", "DSolve", "Sum"):
        session.definitions.clear_cache(f"System`{name}")
