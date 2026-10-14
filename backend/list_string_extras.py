"""Group 5 Python-level overrides: behaviours that need the evaluator rather
than a WL rule (verified against Wolfram 15.0.1, see
wolfram-re-round2/oracle/lists-wolfram.json / strings-wolfram.json):

  * Nothing is removed from lists ({1, Nothing, 2} -> {1, 2});
  * Sort[list, p] uses a stable merge sort with p as "comes before"
    (Mathics used Python's sorted with a __gt__-only key, which mis-orders);
  * Catch[expr, form, f] -> f[value, tag]; uncaught Throw[v, t] surfaces as
    Throw[v, t] instead of Hold[Throw[...]];
  * HoldForm[1 + 1] prints as 1 + 1 but stays HoldForm in Head/InputForm;
    Defer keeps its argument unevaluated;
  * (## &)[1, 2, 3] -> Sequence splices into the caller; (#a &)[<|"a"->1|>] -> 1;
    Function[Null, body] treats body as a slot function;
  * StringSplit keeps empty fields between adjacent delimiters
    ("a,b,,c" -> {"a","b","","c"}) and StringCases/StringPosition honour
    Overlaps -> True;
  * ToString[1/2] uses OutputForm (two-dimensional "1\n-\n2") like the kernel;
  * AtomQ[Association] = True; SymbolQ stays inert (not a System` function in
    Wolfram); Equivalent[a, a] = True; canonical Sort order puts E^x (Power)
    before plain symbols as the kernel does.
"""

from __future__ import annotations

import re

from mathics.builtin.atomic.atomic import AtomQ as _NativeAtomQ
from mathics.builtin.functional.application import Function as _NativeFunction
from mathics.builtin.list.constructing import List as _NativeList
from mathics.builtin.procedural import Catch as _NativeCatch
from mathics.builtin.statistics.orderstats import Sort as _NativeSort
from mathics.builtin.string.operations import StringSplit as _NativeStringSplit
from mathics.builtin.testing_expressions.logic import Equivalent as _NativeEquivalent
from mathics.core.atoms import Integer, Integer1, String
from mathics.core.attributes import A_HOLD_ALL, A_LOCKED, A_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.evaluation import Evaluation
from mathics.core.interrupt import WLThrowInterrupt
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol, SymbolTrue, SymbolFalse, SymbolList
from mathics.core.systemsymbols import SymbolMatchQ, SymbolSequence

SymbolNothing = Symbol("System`Nothing")
SymbolThrow = Symbol("System`Throw")


class ListWolfram(_NativeList):
    name = "List"
    context = "System`"
    attributes = A_LOCKED | A_PROTECTED

    def eval(self, elements, evaluation: Evaluation):
        """List[elements___]"""
        seq = elements.get_sequence()
        if any(e is SymbolNothing or (isinstance(e, Symbol) and e.get_name() == "System`Nothing") for e in seq):
            seq = [e for e in seq if not (isinstance(e, Symbol) and e.get_name() == "System`Nothing")]
        return ListExpression(*seq)


class SortWolfram(_NativeSort):
    name = "Sort"
    context = "System`"

    def eval_predicate(self, list, p, evaluation: Evaluation):
        "Sort[list_, p_]"
        from mathics.core.symbols import Atom
        if isinstance(list, Atom):
            return None

        def before(a, b):
            return Expression(p, a, b).evaluate(evaluation) is SymbolTrue

        def msort(items):
            if len(items) <= 1:
                return items
            mid = len(items) // 2
            left, right = msort(items[:mid]), msort(items[mid:])
            out, i, j = [], 0, 0
            while i < len(left) and j < len(right):
                # take from the right only if it strictly comes before the left head
                if before(right[j], left[i]) and not before(left[i], right[j]):
                    out.append(right[j]); j += 1
                else:
                    out.append(left[i]); i += 1
            return out + left[i:] + right[j:]
        return list.restructure(list.head, msort([e for e in list.elements]), evaluation)


class CatchWolfram(_NativeCatch):
    name = "Catch"
    context = "System`"

    def eval_expr(self, expr, evaluation):
        "Catch[expr_]"
        try:
            return expr.evaluate(evaluation)
        except WLThrowInterrupt as e:
            if e.tag is None or (isinstance(e.tag, Symbol) and e.tag.get_name() == "System`None"):
                return e.value
            raise

    def eval_with_form_and_fn(self, expr, form, f, evaluation):
        "Catch[expr_, form_, f__:Identity]"
        try:
            return expr.evaluate(evaluation)
        except WLThrowInterrupt as e:
            tag = e.tag if e.tag is not None else Symbol("System`None")
            if Expression(SymbolMatchQ, tag, form).evaluate(evaluation) is SymbolTrue:
                if isinstance(f, Symbol) and f.get_name() == "System`Identity":
                    return e.value
                return Expression(f, e.value, tag).evaluate(evaluation)
            raise


class AtomQWolfram(_NativeAtomQ):
    name = "AtomQ"
    context = "System`"

    def test(self, expr) -> bool:
        if expr.get_head_name() == "System`Association":
            return True
        return super().test(expr)


class EquivalentWolfram(_NativeEquivalent):
    name = "Equivalent"
    context = "System`"
    rules = {"Equivalent[a_, a_]": "True", "Equivalent[]": "True", "Equivalent[a_]": "True"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.operator = "⧦"  # InfixOperator looked the glyph up by class name

    def eval(self, args, evaluation: Evaluation):
        "Equivalent[args___]"
        seq = args.get_sequence()
        uniq = []
        for e in seq:
            if not any(e.sameQ(u) for u in uniq):
                uniq.append(e)
        if len(uniq) <= 1:
            return SymbolTrue
        return super().eval(args, evaluation)


EquivalentWolfram.__name__ = "Equivalent"


class FunctionWolfram(_NativeFunction):
    """Adds Function[Null, body] (= body &), named slots #name on associations
    and ## splicing of a bare SlotSequence body."""
    name = "Function"
    context = "System`"

    def eval_null(self, body, args, evaluation):
        "Function[Null, body_][args___]"
        return Expression(Expression(Symbol("System`Function"), body), *args.get_sequence()).evaluate(evaluation)

    def eval_named_slot(self, body, assoc, evaluation):
        "Function[body_][assoc_Association]"
        # #key -> assoc[key] for string / symbol keys
        found = [False]

        def sub(e):
            if isinstance(e, Expression) and e.get_head_name() == "System`Slot" and len(e.elements) == 1:
                k = e.elements[0]
                if isinstance(k, (String, Symbol)):
                    key = String(k.get_string_value()) if isinstance(k, String) else String(k.get_name().split("`")[-1])
                    found[0] = True
                    return Expression(assoc, key).evaluate(evaluation)
            if isinstance(e, Expression):
                return Expression(sub(e.head), *[sub(x) for x in e.elements])
            return e
        new = sub(body)
        if not found[0]:
            return None
        # replace the remaining numeric slots (#, #1) by the association itself
        def sub_num(e):
            if isinstance(e, Expression) and e.get_head_name() == "System`Slot" and len(e.elements) == 1 and isinstance(e.elements[0], Integer):
                return assoc
            if isinstance(e, Expression):
                return Expression(sub_num(e.head), *[sub_num(x) for x in e.elements])
            return e
        return sub_num(new).evaluate(evaluation)


class StringSplitWolfram(_NativeStringSplit):
    """Keeps empty strings between consecutive delimiters ("a,b,,c" -> 4 fields)
    but, like the kernel, drops empty leading/trailing fields."""
    name = "StringSplit"
    context = "System`"

    def eval(self, string, patt, evaluation, options):
        "StringSplit[string_, patt_, OptionsPattern[StringSplit]]"
        res = super().eval(string, patt, evaluation, options)
        if res is None or string.get_head_name() == "System`List":
            return res
        py = string.get_string_value()
        if py is None or not isinstance(patt, String):
            return res
        sep = patt.get_string_value()
        if not sep:
            return res
        parts = py.split(sep)
        # kernel: empty leading/trailing fields dropped, interior kept
        while parts and parts[0] == "":
            parts.pop(0)
        while parts and parts[-1] == "":
            parts.pop()
        return ListExpression(*[String(p) for p in parts])


from mathics.builtin.string.patterns import StringCases as _NativeStringCases


class StringCasesWolfram(_NativeStringCases):
    """Overlaps -> True for literal patterns: all (overlapping) occurrences."""
    name = "StringCases"
    context = "System`"
    options = dict(_NativeStringCases.options, Overlaps="False")

    def eval(self, string, rule, n, evaluation, options):
        "%(name)s[string_, rule_, OptionsPattern[%(name)s], n_:System`Private`Null]"
        if options.get("System`Overlaps") is SymbolTrue and isinstance(rule, String) and isinstance(string, String):
            sv, pv = string.get_string_value(), rule.get_string_value()
            hits = [i for i in range(len(sv) - len(pv) + 1) if sv.startswith(pv, i)] if pv else []
            if isinstance(n, Integer):
                hits = hits[: n.value]
            return ListExpression(*[String(pv) for _ in hits])
        return super().eval(string, rule, n, evaluation, options)


from mathics.builtin.testing_expressions.expression_tests import MatchQ as _NativeMatchQ


class MatchQWolfram(_NativeMatchQ):
    """PatternSequence / Repeated[PatternSequence] / OrderlessPatternSequence /
    KeyValuePattern, delegated to WL helpers in list_rules.py."""
    name = "MatchQ"
    context = "System`"

    def eval(self, expr, form, evaluation: Evaluation):
        "MatchQ[expr_, form_]"
        def has(e, head):
            if isinstance(e, Expression):
                if e.get_head_name() == head:
                    return True
                return any(has(x, head) for x in e.elements) or has(e.head, head)
            return False
        ctx = "MathematicsNotebook`Lists`"
        if form.get_head_name() == "System`KeyValuePattern":
            return Expression(Symbol(ctx + "matchKeyValue"), expr, form).evaluate(evaluation)
        if has(form, "System`OrderlessPatternSequence"):
            return Expression(Symbol(ctx + "matchOrderlessSeq"), expr, form).evaluate(evaluation)
        if has(form, "System`PatternSequence"):
            if any(isinstance(x, Expression) and x.get_head_name() == "System`Repeated" and x.elements
                   and x.elements[0].get_head_name() == "System`PatternSequence" for x in (form.elements if isinstance(form, Expression) else [])):
                return Expression(Symbol(ctx + "matchRepeatedSeq"), expr, form).evaluate(evaluation)
            return Expression(Symbol(ctx + "matchPatternSeq"), expr, form).evaluate(evaluation)
        return super().eval(expr, form, evaluation)


class Defer(Builtin):
    """Defer[expr]: held like HoldForm (Mathics has no Defer)."""
    attributes = A_HOLD_ALL | A_PROTECTED
    rules = {"MakeBoxes[Defer[expr_], f_]": "MakeBoxes[expr, f]"}


class StringOverlaps(Builtin):
    """Overlaps -> True for literal string patterns (StringCases / StringPosition /
    StringCount); the native classes only know non-overlapping matches."""
    name = "StringOverlapHits"
    context = "MathematicsNotebook`"

    def eval(self, s, p, evaluation):
        "%(name)s[s_String, p_String]"
        sv, pv = s.get_string_value(), p.get_string_value()
        hits = [i for i in range(len(sv) - len(pv) + 1) if sv.startswith(pv, i)] if pv else []
        return ListExpression(*[ListExpression(Integer(i + 1), Integer(i + len(pv))) for i in hits])


def _bool_to_sympy(expr, syms):
    import sympy
    name = expr.get_head_name() if isinstance(expr, Expression) else None
    if isinstance(expr, Symbol):
        n = expr.get_name()
        if n == "System`True":
            return sympy.true
        if n == "System`False":
            return sympy.false
        return syms.setdefault(n, sympy.Symbol(n.split("`")[-1]))
    ops = {"System`And": sympy.And, "System`Or": sympy.Or, "System`Not": sympy.Not, "System`Xor": sympy.Xor,
           "System`Nand": sympy.Nand, "System`Nor": sympy.Nor, "System`Implies": sympy.Implies, "System`Equivalent": sympy.Equivalent}
    if name in ops:
        return ops[name](*[_bool_to_sympy(e, syms) for e in expr.elements])
    raise ValueError("not boolean")


def _bool_from_sympy(e, syms):
    import sympy
    inv = {v: k for k, v in syms.items()}
    if e is sympy.true:
        return SymbolTrue
    if e is sympy.false:
        return SymbolFalse
    if isinstance(e, sympy.Symbol):
        return Symbol(inv[e])
    heads = {sympy.And: "System`And", sympy.Or: "System`Or", sympy.Not: "System`Not", sympy.Xor: "System`Xor",
             sympy.Implies: "System`Implies", sympy.Equivalent: "System`Equivalent"}
    head = heads[type(e)]
    args = [_bool_from_sympy(a, syms) for a in e.args]
    # the kernel orders DNF/CNF terms by the variables: sort clauses canonically
    if head in ("System`And", "System`Or"):
        args.sort(key=lambda a: a.element_order)
    return Expression(Symbol(head), *args)


class BooleanConvert(Builtin):
    """BooleanConvert[expr, form]: "DNF" (default), "CNF", "ANF"... via sympy."""
    attributes = A_PROTECTED

    def eval(self, expr, evaluation):
        "BooleanConvert[expr_]"
        return self.eval_form(expr, String("DNF"), evaluation)

    def eval_form(self, expr, form, evaluation):
        "BooleanConvert[expr_, form_String]"
        import sympy
        syms = {}
        try:
            s = _bool_to_sympy(expr, syms)
        except ValueError:
            return None
        f = form.get_string_value()
        if f == "DNF":
            r = sympy.to_dnf(s, simplify=False)
            if r.has(sympy.Xor) or any(isinstance(t, sympy.And) and sympy.simplify_logic(t) is sympy.false for t in sympy.Or.make_args(r)):
                r = sympy.to_dnf(s, simplify=True)  # drop contradictory terms (Xor expansion)
        elif f == "CNF":
            r = sympy.to_cnf(s, simplify=False)
        elif f == "ANF":
            r = sympy.to_anf(s)
        else:
            return None
        return _bool_from_sympy(r, syms)


class BooleanMinimize(Builtin):
    attributes = A_PROTECTED

    def eval(self, expr, evaluation):
        "BooleanMinimize[expr_]"
        import sympy
        syms = {}
        try:
            s = _bool_to_sympy(expr, syms)
        except ValueError:
            return None
        r = sympy.simplify_logic(s, form="dnf")
        return _bool_from_sympy(r, syms)


class LogicalExpand(Builtin):
    attributes = A_PROTECTED

    def eval(self, expr, evaluation):
        "LogicalExpand[expr_]"
        import sympy
        syms = {}
        try:
            s = _bool_to_sympy(expr, syms)
        except ValueError:
            return None
        return _bool_from_sympy(sympy.to_dnf(s, simplify=False), syms)


CLASSES = [ListWolfram, SortWolfram, CatchWolfram, AtomQWolfram, EquivalentWolfram, FunctionWolfram,
           StringSplitWolfram, StringCasesWolfram, StringOverlaps, BooleanConvert, BooleanMinimize, LogicalExpand,
           MatchQWolfram, Defer]


def register_list_string_extras(session):
    for cls in CLASSES:
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"{cls.context}{cls.name}")
