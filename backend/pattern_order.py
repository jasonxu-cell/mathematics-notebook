"""Rule-ordering fix (group 5): Wolfram ranks `f[x_, x_]` as more specific than
`f[x_, y_]` (and `f[x__Integer]` above `f[x__]` etc.) regardless of definition
order; Mathics' sort key gives both the same precedence, so the later one wins.

We extend the key tuple by a tiebreak:
  (number of distinct pattern names) - (number of Pattern occurrences)
i.e. repeated names (-1 per repeat) sort before all-distinct ones."""

from mathics.core import rules as _rules
from mathics.core.pattern import BasePattern


def _pattern_names(expr, out):
    from mathics.core.expression import Expression
    if isinstance(expr, Expression):
        head = expr.get_head_name()
        if head == "System`Pattern" and len(expr.elements) == 2:
            out.append(expr.elements[0].get_name())
        for e in expr.elements:
            _pattern_names(e, out)
        _pattern_names(expr.head, out)


def _repeat_score(pattern):
    names = []
    try:
        _pattern_names(pattern.expr, names)
    except Exception:
        return 0
    return len(set(names)) - len(names)  # 0 when all distinct, negative with repeats


_orig = _rules.Rule.pattern_precedence


def _pattern_precedence(self):
    base = _orig.fget(self) if isinstance(_orig, property) else _orig(self)
    return tuple(base) + (_repeat_score(self.pattern),)


def _install_nothing():
    """{1, Nothing, 2} -> {1, 2}: Nothing is removed whenever a list's elements
    are evaluated (Wolfram does this for every List, incl. Table results)."""
    from mathics.core import list as _list
    from mathics.core.systemsymbols import SymbolNothing
    orig = _list.ListExpression.rewrite_apply_eval_step

    def step(self, evaluation):
        res, flag = orig(self, evaluation)
        elems = res._elements if isinstance(res, _list.ListExpression) else None
        if elems and any(e is SymbolNothing for e in elems):
            new = _list.ListExpression(*[e for e in elems if e is not SymbolNothing])
            new._build_elements_properties()
            return new, flag
        return res, flag
    _list.ListExpression.rewrite_apply_eval_step = step


def _install_power_order():
    """Canonical ordering of Power[base, exp] with a symbolic exponent: the
    kernel sorts E^x, a^x as the monomial in the base (E^x before x, a^x
    before x), Mathics fell through to the generic expression key and put
    them after all symbols ({1, x, ..., E^x})."""
    from mathics.core import expression as _expr
    from mathics.core.keycomparable import Monomial
    from mathics.core.symbols import Symbol
    from mathics.core.systemsymbols import SymbolPower
    from mathics.core.atoms import Number
    from mathics.core.element import BaseElement
    orig_attr = _expr.Expression.element_order
    orig = orig_attr.fget if isinstance(orig_attr, property) else orig_attr

    try:
        from mathics.core.symbols import wma_str_sort_key
    except ImportError:
        from mathics.core.expression import wma_str_sort_key  # type: ignore
    from mathics.core.keycomparable import BASIC_EXPRESSION_ELT_ORDER

    def element_order(self):
        if self._head is SymbolPower and len(self._elements) == 2:
            base, exp = self._elements
            if isinstance(base, (Symbol, Number)) and not isinstance(exp, Number) and not exp.is_numeric():
                # kernel: {2^x, E^x, x, x^2}, {a, a^x, b, E^a, E^b, x^a} — a power with a
                # symbolic exponent sorts like its base symbol (E and numbers count as
                # symbols here, not numerics) with the exponent as tie-break, so it
                # lands right after the base and before any other expression.
                name = base.name if isinstance(base, Symbol) else str(base.value)
                if name == "System`E":
                    name = "Global`E"  # sorted by name among plain symbols (a < E < x), not as a numeric constant
                key = (BASIC_EXPRESSION_ELT_ORDER, Monomial({wma_str_sort_key(name): 1}), 0, name, 2,
                       exp.element_order if hasattr(exp, "element_order") else 0)
                return key
        return orig(self)
    _expr.Expression.element_order = property(element_order) if isinstance(orig_attr, property) else element_order


def _install_regex():
    """String-pattern compiler: NumberString must not match the empty string
    (kernel: StringCases["12 and 3.5", NumberString] -> {"12", "3.5"}) and
    PatternSequence[a, b] is just concatenation."""
    from mathics.core.convert import regex as _re
    from mathics.core.systemsymbols import SymbolNumberString
    _re.REGEXP_FOR_SYMBOLS[SymbolNumberString] = r"[-+]?(\d+(\.\d*)?|\.\d+)"
    orig = _re.to_regex_internal

    def to_regex_internal(expr, q, groups, abbreviated_patterns, show_message):
        if expr.has_form("PatternSequence", None):
            parts = [to_regex_internal(e, q, groups, abbreviated_patterns, show_message) for e in expr.elements]
            return None if any(p is None for p in parts) else "".join(parts)
        return orig(expr, q, groups, abbreviated_patterns, show_message)
    _re.to_regex_internal = to_regex_internal

    # StringReplace / StringCases accept lhs :> rhs as well as lhs -> rhs
    # (the native code only recognised Rule; RuleDelayed is evaluated per match anyway)
    from mathics.core.expression import Expression
    from mathics.core.symbols import Symbol
    from mathics.core.list import ListExpression
    from mathics.core.attributes import A_HOLD_REST
    import mathics.eval.strings as _es
    import mathics.builtin.string.patterns as _bp
    import mathics.builtin.string.operations as _bo
    orig_find = _es.eval_StringFind
    SymbolRule = Symbol("System`Rule")

    def eval_StringFind(self, string, rule, n, evaluation, options, cases):
        def conv(r):
            if r.has_form("RuleDelayed", 2):
                return Expression(SymbolRule, r.elements[0], r.elements[1])
            return r
        if rule.has_form("List", None):
            rule = ListExpression(*[conv(r) for r in rule.elements])
        else:
            rule = conv(rule)
        return orig_find(self, string, rule, n, evaluation, options, cases)
    _es.eval_StringFind = eval_StringFind
    for mod in (_bp, _bo):
        if hasattr(mod, "eval_StringFind"):
            mod.eval_StringFind = eval_StringFind


def install():
    if getattr(_rules.Rule, "_mn_patched", False):
        return
    _install_power_order()
    _install_regex()
    if isinstance(_orig, property):
        _rules.Rule.pattern_precedence = property(_pattern_precedence)
    else:
        _rules.Rule.pattern_precedence = _pattern_precedence
    _rules.Rule._mn_patched = True
    _install_nothing()
