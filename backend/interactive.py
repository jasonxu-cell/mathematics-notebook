"""A held, numeric Manipulate subset implemented over Mathics expression ASTs.

No source substitution or speculative body execution is used. The caller keeps
the bindings active through evaluation and display formatting, then restores
every original control-symbol definition in a finally block.
"""

import math
import re
from dataclasses import dataclass
from typing import Any

from mathics.core.atoms import String
from mathics.core.attributes import A_PROTECTED
from mathics.core.convert.python import from_python
from mathics.core.expression import Expression
from mathics.core.symbols import Symbol, SymbolNull
from mathics.eval.nevaluator import eval_N

from errors import RequestError


MAX_CONTROLS = 12
NUMERIC_HEADS = {
    "System`Plus", "System`Times", "System`Power", "System`Rational", "System`N",
    "System`Sin", "System`Cos", "System`Tan", "System`Exp", "System`Log",
    "System`Sqrt", "System`Abs",
}


@dataclass
class EvaluationPlan:
    original: Any
    query: Any
    bindings: dict
    controls: list


def is_manipulate(expression):
    return expression.get_head_name() in {"Global`Manipulate", "System`Manipulate"}


def numeric_constant(expression, evaluation):
    """Permit numeric literals/constants/arithmetic, not user code in ranges."""
    pending = [expression]
    while pending:
        node = pending.pop()
        if isinstance(node, Symbol):
            if node.get_name() not in {"System`Pi", "System`E"}:
                raise RequestError("unsupported_control", "Control bounds must be numeric constants; dependent or symbolic ranges are unsupported.")
        elif node.get_head_name() in {"System`Integer", "System`Real", "System`Rational"} and not getattr(node, "elements", ()):
            continue
        elif node.get_head_name() in NUMERIC_HEADS:
            pending.extend(node.elements)
        else:
            raise RequestError("unsupported_control", "Control bounds must be numeric constants without assignments or other side effects.")
    try:
        value = float(eval_N(expression, evaluation).to_python())
    except (TypeError, ValueError, OverflowError):
        raise RequestError("invalid_control", "Control bounds, initial values and steps must be finite real numbers.") from None
    if not math.isfinite(value):
        raise RequestError("invalid_control", "Control bounds, initial values and steps must be finite real numbers.")
    return value


_DISTRIBUTED_INFIX = re.compile(r"\\\[(Distributed|Conditioned)\]|[]")
# (chars:U+F3D2 / U+F3D3: the private-use code points Wolfram uses for \[Distributed] / \[Conditioned]
_INFIX_HEAD = {"Distributed": "Distributed", "Conditioned": "Conditioned", "": "Distributed", "": "Conditioned"}


def rewrite_distributed(source):
    """Rewrite  a \\[Distributed] b  as  Distributed[a, b]  (and likewise
    \\[Conditioned] b  as  Conditioned[a, b]).

    The pinned mathics-scanner has the named characters but no infix operator
    for them, so the parser rejects the notation Mathematica uses for
    Expectation / Probability.  The operand on each side is taken as the
    bracket-balanced run up to the enclosing comma or bracket, which covers
    the documented usage  x \\[Distributed] dist  inside an argument list.
    String literals are left untouched.
    """
    if not _DISTRIBUTED_INFIX.search(source):
        return source
    out = []
    i = 0
    n = len(source)
    in_string = False
    segment_start = 0
    while i < n:
        c = source[i]
        if in_string:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        m = _DISTRIBUTED_INFIX.match(source, i)
        if not m:
            i += 1
            continue
        # left operand: scan back over balanced brackets to a comma/open bracket
        j = i
        depth = 0
        while j > segment_start:
            ch = source[j - 1]
            if ch in ")]}":
                depth += 1
            elif ch in "([{":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                break
            j -= 1
        left = source[j:i].strip()
        # right operand: scan forward similarly
        k = m.end()
        depth = 0
        while k < n:
            ch = source[k]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                break
            k += 1
        right = source[m.end():k].strip()
        head = _INFIX_HEAD[m.group(1) or m.group(0)]
        out.append(source[segment_start:j])
        out.append(f"{head}[{left}, {right}]")
        segment_start = k
        i = k
    out.append(source[segment_start:])
    return "".join(out)


def prepare_evaluation(session, source, overrides):
    # Matches evaluate_as_in_cli's parse/reset stage, but retains the source AST
    # before an unsupported native Manipulate head could evaluate its body.
    session.evaluation.out = []
    session.evaluation.iteration_count = 0
    query = session.evaluation.parse(rewrite_distributed(source))
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise RequestError("invalid_controls", "controls must be an object mapping control symbols to numbers.")
    if query is None:
        return EvaluationPlan(None, None, {}, [])

    pending = [query]
    manipulates = []
    while pending:
        node = pending.pop()
        if is_manipulate(node):
            manipulates.append(node)
        pending.extend(getattr(node, "elements", ()))
    if not manipulates:
        if overrides:
            raise RequestError("invalid_controls", "Control values were supplied for a cell without a top-level Manipulate.")
        return EvaluationPlan(query, query, {}, [])
    if len(manipulates) != 1:
        raise RequestError("unsupported_manipulate", "This numeric subset supports one top-level Manipulate per cell, without nested Manipulate.")

    manipulate = manipulates[0]
    suppressed = False
    if manipulate is not query:
        if (query.get_head_name() != "System`CompoundExpression" or len(query.elements) != 2
                or query.elements[0] is not manipulate or query.elements[1] is not SymbolNull):
            raise RequestError("unsupported_manipulate", "Manipulate must be the top-level expression, optionally followed by one semicolon.")
        suppressed = True
    if len(manipulate.elements) < 2:
        raise RequestError("invalid_control", "Manipulate requires an expression and at least one numeric control.")
    if len(manipulate.elements) - 1 > MAX_CONTROLS:
        raise RequestError("invalid_control", f"At most {MAX_CONTROLS} numeric controls are supported.")

    controls = []
    bindings = {}
    for specification in manipulate.elements[1:]:
        if not specification.has_form("List", 3, 4):
            raise RequestError("unsupported_control", "Supported controls are {symbol,min,max[,step]} and {{symbol,initial[,label]},min,max[,step]}; Manipulate options and other control types are unsupported.")
        variable = specification.elements[0]
        initial = None
        label = None
        if variable.has_form("List", 2, 3):
            initial = variable.elements[1]
            if len(variable.elements) == 3:
                label_value = variable.elements[2]
                if not isinstance(label_value, String):
                    raise RequestError("unsupported_control", "Control labels must be strings.")
                label = label_value.get_string_value()
            variable = variable.elements[0]
        if not isinstance(variable, Symbol) or variable.get_name().startswith("System`"):
            raise RequestError("invalid_control", "Each control must name an unprotected user symbol.")
        full_name = variable.get_name()
        if session.definitions.get_attributes(full_name) & A_PROTECTED:
            raise RequestError("invalid_control", "Each control must name an unprotected user symbol.")
        key = full_name.removeprefix("Global`")
        if full_name in bindings:
            raise RequestError("invalid_control", f"Duplicate control symbol: {key}.")
        minimum = numeric_constant(specification.elements[1], session.evaluation)
        maximum = numeric_constant(specification.elements[2], session.evaluation)
        span = maximum - minimum
        if minimum >= maximum or not math.isfinite(span):
            raise RequestError("invalid_control", f"Control {key} requires a finite range with min < max.")
        explicit_step = len(specification.elements) == 4
        step = numeric_constant(specification.elements[3], session.evaluation) if explicit_step else span / 100
        if step <= 0 or step > span or not math.isfinite(step):
            raise RequestError("invalid_control", f"Control {key} requires a positive finite step no larger than its range.")
        value = numeric_constant(initial, session.evaluation) if initial is not None else minimum
        if key in overrides:
            value = overrides[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise RequestError("invalid_controls", f"Control {key} requires a finite numeric value.")
            value = float(value)
        if not minimum <= value <= maximum:
            raise RequestError("invalid_controls", f"Control {key} is outside its declared range.")
        if explicit_step and not math.isclose((value - minimum) / step, round((value - minimum) / step), rel_tol=0, abs_tol=1e-7):
            raise RequestError("invalid_controls", f"Control {key} does not lie on its declared step grid.")
        bindings[full_name] = from_python(int(value) if value.is_integer() else value)
        controls.append({"symbol": key, "label": label if label is not None else key, "min": minimum, "max": maximum, "step": step, "value": value})
    unknown = set(overrides) - {control["symbol"] for control in controls}
    if unknown:
        raise RequestError("invalid_controls", f"Unknown control symbols: {', '.join(sorted(map(str, unknown)))}.")
    body = manipulate.elements[0]
    if suppressed:
        body = Expression(Symbol("System`CompoundExpression"), body, SymbolNull)
    return EvaluationPlan(query, body, bindings, controls)
