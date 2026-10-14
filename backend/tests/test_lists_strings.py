"""Group 5 (lists / strings / functional / patterns).  Expected values are
what the activated Wolfram 15.0.1 kernel returns
(wolfram-re-round2/oracle/lists-wolfram.json, strings-wolfram.json),
rendered in the notebook's text form (strings without quotes)."""

from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel()

    def setUp(self):
        self.notebook = self.id()

    def text(self, source):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]["text"]


class ListConstructionTests(_Base):
    def test_missing_heads(self):
        self.assertEqual("{a, 1 + a, 2 + a, 3 + a}", self.text("Range[a, a + 3]"))
        self.assertEqual("{0, 1 / 4, 1 / 2, 3 / 4, 1}", self.text("Subdivide[0, 1, 4]"))
        self.assertEqual("{a, a / 2 + b / 2, b}", self.text("Subdivide[a, b, 2]"))
        self.assertEqual("{f[a], f[a + (-a + b) / 2], f[b]}", self.text("Array[f, 3, {a, b}]"))
        self.assertEqual("{{0, 1, 0}, {0, 0, 2}, {0, 0, 0}}", self.text("DiagonalMatrix[{1, 2}, 1]"))
        self.assertEqual("{3, 5, 7}", self.text("Differences[{1, 4, 9, 16}]"))
        self.assertEqual("{2, 2}", self.text("Differences[{1, 4, 9, 16}, 2]"))
        self.assertEqual("{2, 3, 4}", self.text("Ratios[{1, 2, 6, 24}]"))
        self.assertEqual("{1, 3}", self.text("MinMax[{3, 1, 2}]"))
        self.assertEqual("{0, 4}", self.text("MinMax[{3, 1, 2}, 1]"))
        self.assertEqual("{2, 3, 1}", self.text("Ordering[{3, 1, 2}]"))
        self.assertEqual("{1}", self.text("Ordering[{3, 1, 2}, -1]"))
        self.assertEqual("{1, 2, 3}", self.text("Ordering[{c, a, b}, All, Greater]"))  # stable: ties keep input order
        self.assertEqual("{1, 2}", self.text("TakeWhile[{1, 2, 3, 4, 1}, # < 3 &]"))
        self.assertEqual("b", self.text("Extract[{a, b, c}, 2]"))
        self.assertEqual("{g[a], g[b]}", self.text("Extract[f[a, b], {{1}, {2}}, g]"))
        self.assertEqual("<|a ⇾ 3, b ⇾ 1, c ⇾ 1|>", self.text("Counts[{a, b, a, c, a}]"))
        self.assertEqual("{{a, 1}, {b, 2}}", self.text("DeleteDuplicatesBy[{{a, 1}, {b, 2}, {a, 3}}, First]"))
        self.assertEqual("{{1, 2, 5, 6}, {3, 4}}", self.text("Join[{{1, 2}, {3, 4}}, {{5, 6}}, 2]"))
        self.assertEqual("{a, b, c, x}", self.text("Insert[{a, b, c}, x, -1]"))
        self.assertEqual("{x, a, b, x, c}", self.text("Insert[{a, b, c}, x, {{1}, {3}}]"))
        self.assertEqual("{a, b, x, c}", self.text("Riffle[{a, b, c}, x, 3]"))
        self.assertEqual("{a, x, b, y, c, z, d, x}", self.text("Riffle[{a, b, c, d}, {x, y, z}, {2, -1, 2}]"))
        self.assertEqual("{{1, 2}, {3, 4}, {5, 1}}", self.text("Partition[{1, 2, 3, 4, 5}, 2, 2, {1, 1}]"))
        self.assertEqual("{{1, 2}, {3, 4}, {5, x}}", self.text("Partition[{1, 2, 3, 4, 5}, 2, 2, 1, x]"))
        self.assertEqual("{{1, 2, 3}, {4, 5, 6}, {7, 8}}", self.text("Partition[Range[8], 3, 3, 1, {}]"))
        self.assertEqual("{{x, x, 1}, {x, 1, 2}, {1, 2, 3}, {2, 3, 4}, {3, 4, 5}, {4, 5, x}, {5, x, x}}",
                         self.text("Partition[Range[5], 3, 1, {-1, 1}, x]"))
        self.assertEqual("{{5, 1}, {2, 3}, {4, 5}}", self.text("Partition[Range[5], 2, 2, {2, 1}]"))
        self.assertEqual("{{{1, 3}, {2, 4}}, {{5, 7}, {6, 8}}}", self.text("Transpose[{{{1, 2}, {3, 4}}, {{5, 6}, {7, 8}}}, {1, 3, 2}]"))
        self.assertEqual("{f[a, {c, d}], f[b, {c, d}]}", self.text("Thread[f[{a, b}, {c, d}], List, 1]"))
        self.assertEqual("{{a, a, b}, {a, b, a}, {b, a, a}}", self.text("Permutations[{a, a, b}]"))
        self.assertEqual("{1, 3, a, x}", self.text('NumericalSort[{3, "a", 1, x}]'))

    def test_functional(self):
        self.assertEqual("f[a, c] + f[a, d] + f[b, c] + f[b, d]", self.text("Distribute[f[a + b, c + d]]"))
        self.assertEqual("{f[a, c], f[a, d], f[b, c], f[b, d]}", self.text("Distribute[f[{a, b}, {c, d}], List]"))
        self.assertEqual("g[h[a, c], h[b, c]]", self.text("Distribute[f[a + b, c], Plus, f, g, h]"))
        self.assertEqual("f[{f[a], f[{f[b]}]}]", self.text("MapAll[f, {a, {b}}]"))
        self.assertEqual("-6", self.text("FoldPair[{#1 + #2, #1 - #2} &, 0, {1, 2, 3}]"))
        self.assertEqual("{1, 1, 0}", self.text("FoldPairList[{#1 + #2, #1 - #2} &, 0, {1, 2, 3}]"))
        self.assertEqual("{100, 50, 25}", self.text("NestWhileList[#/2 &, 100, EvenQ]"))
        self.assertEqual("3", self.text("NestWhile[# + 1 &, 1, # < 5 &, 1, 2]"))
        self.assertEqual("{x, f[x], g[f[x]], h[g[f[x]]]}", self.text("ComposeList[{f, g, h}, x]"))
        self.assertEqual("g[f[x]]", self.text("(f /* g)[x]"))
        self.assertEqual("2", self.text("SelectFirst[{1, 2, 3, 4}, EvenQ]"))
        self.assertEqual("Missing[NotFound]", self.text("SelectFirst[{1, 3}, EvenQ]"))
        self.assertEqual("{2}", self.text("Cases[{1, 2, 3, 4}, _?EvenQ, 1, 1]"))
        self.assertEqual("{2, 4, 6}", self.text("Table[If[EvenQ[i], i, Nothing], {i, 6}]"))
        self.assertEqual("{1, 2}", self.text("{1, Nothing, 2}"))
        self.assertEqual("3", self.text("Function[Null, #1 + #2][1, 2]"))
        self.assertEqual("1", self.text('(#a &)[<|"a" -> 1|>]'))
        self.assertEqual("f[a, tag]", self.text("Catch[Throw[a, tag], _, f]"))
        self.assertEqual("{{2, a}, {1, b}}", self.text("Sort[{{2, a}, {1, b}}, #1[[2]] < #2[[2]] &]"))

    def test_rule_specificity(self):
        # f[x_, x_] beats f[x_, y_] whatever the definition order (Wolfram's ranking)
        self.assertEqual("{same, diff}", self.text("Clear[p]; p[x_, x_] := same; p[y_, z_] := diff; {p[a, a], p[a, b]}"))
        self.assertEqual("{double, single}", self.text("Clear[y1]; y1[x_, x_] := double; y1[x_, y_] := single; {y1[a, a], y1[a, b]}"))
        self.assertEqual("{int, int, any}", self.text("Clear[hh]; hh[x_Integer] := int; hh[x_] := any; hh[x_?EvenQ] := even; {hh[2], hh[3], hh[a]}"))

    def test_structural_predicates(self):
        self.assertEqual("True", self.text("MemberQ[a + b, b]"))
        self.assertEqual("True", self.text("MemberQ[{{1}, {2}}, 1, Infinity]"))
        self.assertEqual("True", self.text("MemberQ[f[x][y], f, Infinity, Heads -> True]"))
        self.assertEqual("True", self.text("FreeQ[f[g[x]], g, 1]"))
        self.assertEqual("f[1, 3]", self.text("DeleteCases[f[1, 2, 3], 2]"))
        self.assertEqual("a + c", self.text("DeleteCases[a + b + c, b]"))
        self.assertEqual("True", self.text("AtomQ[<|a -> 1|>]"))
        self.assertEqual("True", self.text("Equivalent[a, a]"))
        self.assertEqual("True", self.text("MatchQ[f[1, a], f[PatternSequence[_Integer, _Symbol]]]"))
        self.assertEqual("True", self.text("MatchQ[f[1, a, 2, b], f[PatternSequence[_Integer, _Symbol] ..]]"))
        self.assertEqual("True", self.text("MatchQ[g[a, b], g[OrderlessPatternSequence[b, a]]]"))
        self.assertEqual("True", self.text("MatchQ[<|a -> 1, b -> 2|>, KeyValuePattern[b -> 2]]"))
        self.assertEqual("False", self.text("MatchQ[<|a -> 1, b -> 2|>, KeyValuePattern[b -> 3]]"))

    def test_canonical_order(self):
        # kernel: symbolic powers sort with their base symbol (E counts as a symbol)
        self.assertEqual("{1, E ^ x, x, Cos[x], Log[x], Sin[x]}", self.text("Sort[{Sin[x], Cos[x], x, 1, Exp[x], Log[x]}]"))
        self.assertEqual("{2 ^ x, a ^ x, E ^ x, x, x ^ a, x ^ 2}", self.text("Sort[{x, E^x, 2^x, a^x, x^2, x^a}]"))
        self.assertEqual("1 + E ^ x + x", self.text("x + E^x + 1"))


class StringTests(_Base):
    def test_missing_heads(self):
        self.assertEqual("True", self.text('StringStartsQ["hello", "he"]'))
        self.assertEqual("2", self.text('StringCount["hello", "l"]'))
        self.assertEqual("5", self.text('StringCount["banana", "a" | "n"]'))
        self.assertEqual("acac", self.text('StringDelete["abcabc", "b"]'))
        self.assertEqual("   ab", self.text('StringPadLeft["ab", 5]'))
        self.assertEqual("ab...", self.text('StringPadRight["ab", 5, "."]'))
        self.assertEqual("bc", self.text('StringPadLeft["abc", 2]'))
        self.assertEqual("{ab, cd, ef}", self.text('StringPartition["abcdef", 2]'))
        self.assertEqual("{ab, bc, cd, de}", self.text('StringPartition["abcde", 2, 1]'))
        self.assertEqual("bca", self.text('StringRotateLeft["abc"]'))
        self.assertEqual("aX", self.text('StringReplacePart["abc", "X", {2, 3}]'))
        self.assertEqual("XbY", self.text('StringReplacePart["abc", {"X", "Y"}, {{1, 1}, {3, 3}}]'))
        self.assertEqual("b", self.text('StringExtract["a b c", 2]'))
        self.assertEqual("Hello world", self.text('Capitalize["hello world"]'))
        self.assertEqual("{a, b, , c}", self.text('StringSplit["a,b,,c", ","]'))
        self.assertEqual("{a, b c}", self.text('StringSplit["a b c", " ", 2]'))
        self.assertEqual("{a, |, b}", self.text('StringSplit["a-b", "-" -> "|"]'))
        self.assertEqual("{aa, aa, aa}", self.text('StringCases["aaaa", "aa", Overlaps -> True]'))
        self.assertEqual("{{1, 2}, {2, 3}}", self.text('StringPosition["aaa", "aa"]'))
        self.assertEqual("{{1, 2}}", self.text('StringPosition["aaa", "aa", Overlaps -> False]'))
        self.assertEqual("{12, 3.5}", self.text('StringCases["12 and 3.5", NumberString]'))
        self.assertEqual("{ab}", self.text('StringCases["ab", PatternSequence["a", "b"]]'))
        self.assertEqual("hell0 w0rld", self.text('StringReplace["hello world", "o" ~~ x_ :> "0" <> x]'))
        self.assertEqual("{1, 2}", self.text('StringCases["a1b2", x : DigitCharacter :> ToExpression[x]]'))
        self.assertEqual("Hello W", self.text('StringTemplate["Hello `name`"][<|"name" -> "W"|>]'))
        self.assertEqual("1 + 2", self.text('StringTemplate["`1` + `2`"][1, 2]'))
        self.assertEqual("ab", self.text('LongestCommonSubsequence["abcbd", "bdcab"]'))
        self.assertEqual("bcb", self.text('LongestCommonSequence["abcbd", "bdcab"]'))
        self.assertEqual("1", self.text('AlphabeticOrder["a", "b"]'))
        self.assertEqual("True", self.text('NameQ["Sin"]'))

    def test_boolean(self):
        self.assertEqual("a ∧ b ∨ a ∧ c", self.text("BooleanConvert[a && (b || c)]"))
        self.assertEqual("a ∧ !b ∨ b ∧ !a", self.text("BooleanConvert[Xor[a, b]]"))
        self.assertEqual("a", self.text("BooleanMinimize[(a && b) || (a && !b)]"))
        self.assertEqual("!a ∨ !b", self.text("LogicalExpand[!(a && b)]"))
        self.assertEqual("{True, False, False, False}", self.text("BooleanTable[a && b, {a, b}]"))
        self.assertEqual("False", self.text("SatisfiableQ[a && !a]"))
        self.assertEqual("True", self.text("TautologyQ[a || !a]"))
        self.assertEqual("3", self.text("SatisfiabilityCount[a || b, {a, b}]"))
        self.assertEqual("{{True, True}}", self.text("SatisfiabilityInstances[a && b, {a, b}]"))
        self.assertEqual("True", self.text("Implies[x, True]"))


if __name__ == "__main__":
    unittest.main()
