"""Misc extras (backend/misc_extras.py), checked on real evaluator output.

Contracts follow Wolfram 15.0.1 (wolfram-re-round2/oracle/inputs-misc.txt).
SatisfiabilityQ intentionally evaluates here even though the 15.0.1 kernel
leaves it inert (SatisfiableQ is the evaluating head there).
"""

from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


_KERNEL = None


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Share one kernel across all classes in this module: Kernel spawns a
        # background spare-session warmer whose session construction races the
        # process-global Mathics builtin registry if a second Kernel is built
        # while it runs.  Tests already isolate state via per-test notebook_id.
        global _KERNEL
        if _KERNEL is None:
            _KERNEL = Kernel()
        cls.kernel = _KERNEL

    def setUp(self):
        self.notebook = self.id()

    def evaluate(self, source):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def text(self, source):
        return self.evaluate(source)["text"]


class ArgOptTests(_Base):
    def test_single_variable(self):
        self.assertEqual("1", self.text("ArgMin[x^2 - 2 x + 3, x]"))
        self.assertEqual("-3 / 4", self.text("ArgMax[-2 x^2 - 3 x + 5, x]"))
        self.assertEqual("2", self.text("ArgMax[-x^2 + 4 x + 1, x]"))
        self.assertEqual("3", self.text("ArgMax[x (6 - x), x]"))

    def test_multiple_variables_return_value_list(self):
        self.assertEqual("{1, 2}", self.text("ArgMin[(x - 1)^2 + (y - 2)^2, {x, y}]"))

    def test_constrained(self):
        self.assertEqual("{1, 1}", self.text("ArgMin[{x^2 + y^2, x + y >= 2}, {x, y}]"))
        # linear program; Wolfram picks the lexicographically smallest vertex
        self.assertEqual("{0, 5}", self.text("ArgMax[{x + 2 y, x + 2 y <= 10, x >= 0, y >= 0}, {x, y}]"))


class LinearProgrammingTests(_Base):
    def test_basic(self):
        self.assertEqual("{0, 3 / 2}", self.text("LinearProgramming[{1, 1}, {{1, 2}}, {3}]"))
        self.assertEqual("{0, 0, 2}", self.text("LinearProgramming[{1, 1, 1}, {{1, 2, 3}}, {6}]"))
        self.assertEqual("{2, 3}", self.text("LinearProgramming[{2, 3}, {{1, 1}, {1, 0}, {0, 1}}, {4, 2, 3}]"))
        self.assertEqual("{4, 0}", self.text("LinearProgramming[{1, 2}, {{1, 1}, {3, 1}}, {4, 9}]"))

    def test_sense_pairs(self):
        # {bi, -1} means m.x <= bi
        self.assertEqual("{0, 0}", self.text("LinearProgramming[{1, 1}, {{1, 1}}, {{2, -1}}]"))


class KnapsackSolveTests(_Base):
    def test_items_are_payoff_cost_pairs_with_unlimited_copies(self):
        self.assertEqual("{0, 0, 1}", self.text("KnapsackSolve[{{2, 3}, {3, 4}, {4, 5}}, 5]"))
        self.assertEqual("{0, 1, 0, 1}", self.text("KnapsackSolve[{{2, 3}, {3, 4}, {4, 5}, {5, 6}}, 10]"))
        self.assertEqual("{0, 4}", self.text("KnapsackSolve[{{5, 4}, {3, 2}}, 8]"))
        self.assertEqual("{10, 0}", self.text("KnapsackSolve[{{10, 1}, {1, 10}}, 10]"))

    def test_partial_capacity_and_ties(self):
        self.assertEqual("{2}", self.text("KnapsackSolve[{{2, 3}}, 7]"))
        self.assertEqual("{0, 4}", self.text("KnapsackSolve[{{2, 2}, {1, 1}}, 4]"))


class SolveValuesTests(_Base):
    def test_single_variable_flattens(self):
        self.assertEqual("{1, 2}", self.text("SolveValues[x^2 - 3 x + 2 == 0, x]"))
        self.assertEqual("{-I, I}", self.text("SolveValues[x^2 + 1 == 0, x]"))
        self.assertEqual("{0, 1}", self.text("SolveValues[x^2 == x, x]"))

    def test_multiple_variables_give_value_lists(self):
        self.assertEqual("{{2, 1}}", self.text("SolveValues[{x + y == 3, x - y == 1}, {x, y}]"))

    def test_domain_filter(self):
        self.assertEqual("{-1, 1}", self.text("SolveValues[x^2 - 1 == 0, x, Reals]"))
        self.assertEqual("{}", self.text("SolveValues[x^2 + 1 == 0, x, Reals]"))

    def test_nsolvevalues(self):
        self.assertEqual("{-1.41421, 1.41421}", self.text("NSolveValues[x^2 - 2 == 0, x]"))
        self.assertEqual("{-1.61803, 0.618034, 1.}", self.text("NSolveValues[x^3 - 2 x + 1 == 0, x]"))


class DSolveValueTests(_Base):
    def test_returns_expression_not_rules(self):
        self.assertEqual("E ^ x C[1]", self.text("DSolveValue[y'[x] == y[x], y[x], x]"))
        self.assertEqual("x ^ 2 + C[1]", self.text("DSolveValue[y'[x] == 2 x, y[x], x]"))

    def test_with_initial_conditions(self):
        self.assertEqual("E ^ x", self.text("DSolveValue[{y'[x] == y[x], y[0] == 1}, y[x], x]"))
        self.assertEqual("Sin[x]", self.text("DSolveValue[{y''[x] + y[x] == 0, y[0] == 0, y'[0] == 1}, y[x], x]"))

    def test_ndsolvevalue(self):
        self.assertEqual("2.71828", self.text("NDSolveValue[{y'[x] == y[x], y[0] == 1}, y[1], {x, 0, 1}]"))
        value = float(self.text("NDSolveValue[{y'[x] == Cos[x], y[0] == 0}, y[Pi], {x, 0, Pi}]").replace("×10^", "e"))
        self.assertAlmostEqual(0.0, value, places=6)


class LinearSolveFunctionTests(_Base):
    def test_bare_object_stays_unevaluated(self):
        self.assertEqual("LinearSolveFunction[{{1, 2}, {3, 4}}]",
                         self.text("LinearSolveFunction[{{1, 2}, {3, 4}}]"))

    def test_application_solves(self):
        self.assertEqual("{-4, 9 / 2}", self.text("LinearSolveFunction[{{1, 2}, {3, 4}}][{5, 6}]"))
        self.assertEqual("{2, 3}", self.text("LinearSolveFunction[{{2, 0}, {0, 2}}][{4, 6}]"))


class RecurrenceTableTests(_Base):
    def test_fibonacci(self):
        self.assertEqual("{1, 1, 2, 3, 5, 8, 13, 21, 34, 55}",
                         self.text("RecurrenceTable[{a[n] == a[n - 1] + a[n - 2], a[1] == 1, a[2] == 1}, a, {n, 1, 10}]"))

    def test_first_order(self):
        self.assertEqual("{1, 2, 4, 8, 16, 32}",
                         self.text("RecurrenceTable[{a[n] == 2 a[n - 1], a[0] == 1}, a, {n, 0, 5}]"))
        self.assertEqual("{1, 3, 6, 10, 15, 21}",
                         self.text("RecurrenceTable[{a[n] == a[n - 1] + n, a[1] == 1}, a, {n, 1, 6}]"))
        self.assertEqual("{1, 1, 2, 6, 24, 120}",
                         self.text("RecurrenceTable[{a[n] == n a[n - 1], a[0] == 1}, a, {n, 0, 5}]"))

    def test_missing_initial_condition_is_unevaluated(self):
        self.assertTrue(self.text("RecurrenceTable[{a[n] == a[n - 1] + a[n - 2], a[1] == 1}, a, {n, 1, 5}]")
                        .startswith("RecurrenceTable["))


class FindLinearRecurrenceTests(_Base):
    def test_classics(self):
        self.assertEqual("{1, 1}", self.text("FindLinearRecurrence[{1, 1, 2, 3, 5, 8, 13, 21}]"))
        self.assertEqual("{1, 1}", self.text("FindLinearRecurrence[{1, 1, 2, 3, 5, 8}]"))
        self.assertEqual("{2}", self.text("FindLinearRecurrence[{1, 2, 4, 8, 16, 32}]"))
        self.assertEqual("{3, -3, 1}", self.text("FindLinearRecurrence[{1, 4, 9, 16, 25, 36, 49}]"))

    def test_rational_coefficients(self):
        self.assertEqual("{3 / 2, -1 / 2}", self.text("FindLinearRecurrence[{1, 3/2, 7/4, 15/8, 31/16}]"))

    def test_no_recurrence_is_unevaluated(self):
        self.assertTrue(self.text("FindLinearRecurrence[{1, 2, 4, 7, 5, 3, 9}]")
                        .startswith("FindLinearRecurrence["))


class CalculusExtrasTests(_Base):
    def test_wronskian(self):
        self.assertEqual("x ^ 2", self.text("Wronskian[{x, x^2}, x]"))
        self.assertEqual("-1", self.text("Wronskian[{Sin[x], Cos[x]}, x]"))
        self.assertEqual("E ^ (2 x)", self.text("Wronskian[{Exp[x], x Exp[x]}, x]"))
        self.assertEqual("2", self.text("Wronskian[{1, x, x^2}, x]"))

    def test_residue(self):
        self.assertEqual("1", self.text("Residue[1/(x - 2), {x, 2}]"))
        self.assertEqual("-1", self.text("Residue[1/(x (x - 1)^2), {x, 1}]"))
        self.assertEqual("-1 / 6", self.text("Residue[Sin[x]/x^4, {x, 0}]"))
        self.assertEqual("1", self.text("Residue[1/Sin[x], {x, 0}]"))
        self.assertEqual("E", self.text("Residue[Exp[x]/(x - 1)^2, {x, 1}]"))


class GeneratingFunctionTests(_Base):
    def test_ordinary(self):
        self.assertEqual("-x / (-1 + x + x ^ 2)", self.text("GeneratingFunction[Fibonacci[n], n, x]"))
        self.assertEqual("x / (-1 + x) ^ 2", self.text("GeneratingFunction[n, n, x]"))
        self.assertEqual("-1 / (-1 + x)", self.text("GeneratingFunction[1, n, x]"))
        self.assertEqual("-1 / (-1 + a x)", self.text("GeneratingFunction[a^n, n, x]"))
        self.assertEqual("-x (1 + x) / (-1 + x) ^ 3", self.text("GeneratingFunction[n^2, n, x]"))

    def test_exponential(self):
        self.assertEqual("E ^ x", self.text("ExponentialGeneratingFunction[1, n, x]"))
        self.assertEqual("E ^ x x", self.text("ExponentialGeneratingFunction[n, n, x]"))
        self.assertEqual("-1 / (-1 + x)", self.text("ExponentialGeneratingFunction[n!, n, x]"))
        self.assertEqual("E ^ (2 x)", self.text("ExponentialGeneratingFunction[2^n, n, x]"))


class SatisfiabilityQTests(_Base):
    def test_boolean_satisfiability(self):
        self.assertEqual("True", self.text("SatisfiabilityQ[a && b, {a, b}]"))
        self.assertEqual("False", self.text("SatisfiabilityQ[a && Not[a], {a}]"))
        self.assertEqual("True", self.text("SatisfiabilityQ[a || b, {a, b}]"))
        self.assertEqual("True", self.text("SatisfiabilityQ[(a || b) && Not[a], {a, b}]"))


class MovingStatisticsTests(_Base):
    def test_moving_average(self):
        self.assertEqual("{3 / 2, 5 / 2, 7 / 2, 9 / 2}", self.text("MovingAverage[{1, 2, 3, 4, 5}, 2]"))
        self.assertEqual("{2, 3, 4}", self.text("MovingAverage[{1, 2, 3, 4, 5}, 3]"))
        self.assertEqual("{(a + b) / 2, (b + c) / 2, (c + d) / 2}", self.text("MovingAverage[{a, b, c, d}, 2]"))
        self.assertEqual("{1.5, 2.5, 3.5}", self.text("MovingAverage[{1., 2., 3., 4.}, 2]"))
        self.assertEqual("{}", self.text("MovingAverage[{1, 2}, 3]"))

    def test_moving_median(self):
        self.assertEqual("{2, 5, 3}", self.text("MovingMedian[{1, 5, 2, 8, 3}, 3]"))
        self.assertEqual("{2, 3 / 2, 3}", self.text("MovingMedian[{3, 1, 2, 4}, 2]"))

    def test_exponential_moving_average(self):
        self.assertEqual("{1, 3 / 2, 9 / 4, 25 / 8}", self.text("ExponentialMovingAverage[{1, 2, 3, 4}, 1/2]"))
        self.assertEqual("{2, 5 / 2, 31 / 8, 221 / 32}", self.text("ExponentialMovingAverage[{2, 4, 8, 16}, 1/4]"))
        self.assertEqual("{1., 1.5, 2.25, 3.125}", self.text("ExponentialMovingAverage[{1., 2., 3., 4.}, 0.5]"))


class ExtremalByTests(_Base):
    def test_all_extremes_in_original_order(self):
        self.assertEqual("{{3, 0}}", self.text("MaximalBy[{{1, 2}, {2, 1}, {3, 0}}, First]"))
        self.assertEqual("{{1, 2}}", self.text("MinimalBy[{{1, 2}, {2, 1}, {3, 0}}, First]"))
        self.assertEqual("{-3, 3}", self.text("MaximalBy[{1, -3, 3, 2}, Abs]"))
        self.assertEqual("{1}", self.text("MinimalBy[{1, -3, 3, 2}, Abs]"))
        self.assertEqual("{2, 2}", self.text("MaximalBy[{1, 2, 2, 1}, Identity]"))

    def test_count_form_sorts_by_value(self):
        self.assertEqual("{5, 4}", self.text("MaximalBy[Range[5], Identity, 2]"))
        self.assertEqual("{1, 2}", self.text("MinimalBy[Range[5], Identity, 2]"))


if __name__ == "__main__":
    unittest.main()
