"""Limit that never leaks SymPy internals.

When the expression contains an undefined function (``exp[x]`` typed in lower
case, ``f[x]``, ...), SymPy's ``limit`` can return a partially evaluated object
built from internal ``Dummy`` symbols, e.g.

    Infinity / Sign[exp[sympy`dummy`Dummy$6640530]]

Mathics converts that back verbatim.  Mathematica returns the Limit
unevaluated in this situation.  This override keeps the native Limit and only
rejects results that contain Dummy symbols, unevaluated ``Limit`` objects or
NaN, returning ``None`` so the expression stays as typed.
"""

from __future__ import annotations

import sympy

from mathics.builtin.numbers.calculus import Limit
from mathics.core.convert.sympy import from_sympy


class LimitWithoutLeaks(Limit):
    name = "Limit"
    context = "System`"

    def eval(self, expr, x, x0, evaluation, options={}):
        "Limit[expr_, x_->x0_, OptionsPattern[Limit]]"
        e_s, x_s, x0_s = expr.to_sympy(), x.to_sympy(), x0.to_sympy()
        if e_s is None or x_s is None or x0_s is None:
            return None
        direction = self.get_option(options, "Direction", evaluation)
        value = direction.get_int_value()
        if value == -1:
            dir_sympy = "+"
        elif value == 1:
            dir_sympy = "-"
        else:
            evaluation.message("Limit", "ldir", direction)
            return None
        try:
            result = sympy.limit(e_s, x_s, x0_s, dir_sympy)
        except (sympy.PoleError, RuntimeError, NotImplementedError, TypeError, ValueError, RecursionError):
            return None
        if result is None:
            return None
        if result.has(sympy.Limit) or result.has(sympy.nan):
            return None
        out = from_sympy(result)
        # Mathics wraps unknown heads in SympyExpression and converts SymPy
        # Dummy symbols into Mathics symbols named sympy`dummy`Dummy$NNN; the
        # original variable is also sometimes left unsubstituted. Reject both.
        leaked = any(
            name.startswith("sympy`dummy`") or name == x.get_name()
            for name in _symbol_names(out)
        )
        return None if leaked else out


def _symbol_names(expr):
    from mathics.core.symbols import Symbol as MSymbol
    from mathics.core.expression import Expression as MExpr

    if isinstance(expr, MSymbol):
        yield expr.get_name()
    elif isinstance(expr, MExpr):
        yield from _symbol_names(expr.head)
        for el in expr.elements:
            yield from _symbol_names(el)


def register_limit(session):
    LimitWithoutLeaks(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Limit")
