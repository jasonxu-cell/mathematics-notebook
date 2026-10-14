"""Optional readable approximations of already evaluated algebraic solutions.

This is a display adapter, not another Solve call. Mathics 10.0.1 constructs
Root[f, i] from SymPy CRootOf(f, i - 1); the same index is used here so each
approximation stays paired with its original exact root. No user source or
user-defined functions are evaluated by this module.
"""

from __future__ import annotations

import sympy
import time


DIGITS = 12
MAX_ROOTS = 20
MAX_DEGREE = 12
MAX_NODES = 4096
MAX_COEFFICIENT_BITS = 128
MAX_PREVIEW_SECONDS = 3.0
_SLOT = sympy.Symbol("algebraic_display_slot")


class _Unsupported(ValueError):
    pass


class _Converter:
    def __init__(self):
        self.started = time.perf_counter()
        self.remaining = MAX_NODES
        self.root_count = 0
        self.polynomials = {}

    def visit(self):
        self.check_time()
        self.remaining -= 1
        if self.remaining < 0:
            raise _Unsupported("Display expression is too large.")

    def check_time(self):
        # A cooperative budget between bounded operations. The worker's
        # existing parent-enforced wall-clock timeout remains the hard limit.
        if time.perf_counter() - self.started > MAX_PREVIEW_SECONDS:
            raise _Unsupported("Display preview exceeded its soft time budget.")

    @staticmethod
    def rational(node):
        if node.get_head_name() not in ("System`Integer", "System`Rational"):
            raise _Unsupported("Only rational polynomial coefficients are supported.")
        value = node.to_sympy()
        if not isinstance(value, sympy.Rational):
            raise _Unsupported("Invalid rational coefficient.")
        if max(abs(int(value.p)).bit_length(), int(value.q).bit_length()) > MAX_COEFFICIENT_BITS:
            raise _Unsupported("Polynomial coefficient is too large.")
        return value

    def polynomial(self, node):
        self.visit()
        head = node.get_head_name()
        args = getattr(node, "elements", ())
        if head in ("System`Integer", "System`Rational"):
            result = sympy.Poly(self.rational(node), _SLOT, domain="QQ")
        elif head == "System`Slot" and len(args) == 1 and args[0].get_int_value() == 1:
            result = sympy.Poly(_SLOT, _SLOT, domain="QQ")
        elif head in ("System`Plus", "System`Times") and args:
            result = sympy.Poly(0 if head == "System`Plus" else 1, _SLOT, domain="QQ")
            for arg in args:
                item = self.polynomial(arg)
                if head == "System`Times" and result.degree() + item.degree() > MAX_DEGREE:
                    raise _Unsupported("Polynomial degree is too large.")
                result = result + item if head == "System`Plus" else result * item
        elif head == "System`Power" and len(args) == 2:
            exponent = args[1].get_int_value()
            if exponent is None or not 0 <= exponent <= MAX_DEGREE:
                raise _Unsupported("Unsupported polynomial exponent.")
            base = self.polynomial(args[0])
            if base.degree() * exponent > MAX_DEGREE:
                raise _Unsupported("Polynomial degree is too large.")
            result = base ** exponent
        else:
            raise _Unsupported("Unsupported polynomial syntax.")
        if result.degree() > MAX_DEGREE:
            raise _Unsupported("Polynomial degree is too large.")
        for coefficient in result.all_coeffs():
            if max(abs(int(coefficient.p)).bit_length(), int(coefficient.q).bit_length()) > MAX_COEFFICIENT_BITS:
                raise _Unsupported("Expanded polynomial coefficient is too large.")
        return result

    def number(self, node):
        self.visit()
        head = node.get_head_name()
        args = getattr(node, "elements", ())
        if head in ("System`Integer", "System`Rational"):
            return self.rational(node)
        if head == "System`Complex":
            return self.number(node.real) + sympy.I * self.number(node.imag)
        if head == "System`Root" and len(args) == 2:
            self.root_count += 1
            if self.root_count > MAX_ROOTS:
                raise _Unsupported("Too many algebraic roots for a display preview.")
            function, index = args
            if function.get_head_name() != "System`Function" or len(function.elements) != 1:
                raise _Unsupported("Only a polynomial Slot[1] function is supported.")
            # Identical Root polynomials occur once per solution; validate and
            # expand their AST only once within this one display conversion.
            if function not in self.polynomials:
                self.polynomials[function] = self.polynomial(function.elements[0])
            poly = self.polynomials[function]
            ordinal = index.get_int_value()
            if ordinal is None or not 1 <= ordinal <= poly.degree() <= MAX_DEGREE:
                raise _Unsupported("Invalid algebraic root index or degree.")
            return sympy.CRootOf(poly.as_expr(), _SLOT, ordinal - 1)
        if head in ("System`Plus", "System`Times") and args:
            values = [self.number(arg) for arg in args]
            return sympy.Add(*values) if head == "System`Plus" else sympy.Mul(*values)
        if head == "System`Power" and len(args) == 2:
            exponent = self.rational(args[1])
            if abs(exponent) > MAX_DEGREE or exponent.q > 16:
                raise _Unsupported("Unsupported numeric exponent.")
            return self.number(args[0]) ** exponent
        raise _Unsupported("The solution contains unsupported numeric syntax.")


def solution_preview(expression, evaluation):
    """Return optional rows, or None while leaving the exact result untouched.

The accepted shape is a nonempty List[List[Rule[symbol, numeric expression]]]
containing at least one actual System`Root. Strings, similarly named heads,
parameterized solutions and non-polynomial Root functions are never guessed.
"""
    try:
        if expression.get_head_name() != "System`List" or not 1 <= len(expression.elements) <= MAX_ROOTS:
            return None
        converter = _Converter()
        converted_rows = []
        rule_count = 0
        for row in expression.elements:
            if row.get_head_name() != "System`List" or not row.elements:
                return None
            converted = []
            for rule in row.elements:
                rule_count += 1
                if rule_count > MAX_ROOTS or rule.get_head_name() != "System`Rule" or len(rule.elements) != 2:
                    return None
                variable, value = rule.elements
                if variable.get_head_name() != "System`Symbol":
                    return None
                converted.append((variable, converter.number(value)))
            converted_rows.append((row, converted))
        if not converter.root_count:
            return None
        rows = []
        approximations = {}
        for exact_row, values in converted_rows:
            approximate = []
            for variable, value in values:
                converter.check_time()
                for root in value.atoms(sympy.CRootOf):
                    if root not in approximations:
                        # eval_approx uses the individual CRootOf isolating
                        # interval to validate its secant iteration. Unlike a
                        # separately sorted nroots list, root indices remain
                        # exact; unlike evalf's rational bisection, ordinary
                        # fifth/tenth-degree display stays quick.
                        approximations[root] = root.eval_approx(DIGITS + 3)
                    converter.check_time()
                number = value.xreplace(approximations).evalf(DIGITS)
                if number.free_symbols or number.is_finite is not True or number.has(sympy.CRootOf):
                    return None
                label = evaluation.format_output(variable, "latex")
                if not isinstance(label, str) or not label.strip():
                    return None
                approximate.append(label + r" \approx " + sympy.latex(number))
            exact_latex = evaluation.format_output(exact_row, "latex")
            if not isinstance(exact_latex, str) or not exact_latex.strip():
                return None
            rows.append({"exact_latex": exact_latex, "approximate_latex": r",\quad ".join(approximate)})
        return {"digits": DIGITS, "total": len(rows), "rows": rows}
    except Exception:
        # Optional presentation must never turn successful exact evaluation
        # into an error or replace its existing text/LaTeX/history result.
        return None
