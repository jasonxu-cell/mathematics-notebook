"""Interpolation / fitting builtins (backend/interpolation.py), checked on real
evaluator output.  Contracts follow Wolfram 15.0.1 (see
wolfram-re-round2/oracle/inputs-interpolation-wolfram.json).
"""

from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


_KERNEL = None


def _get_kernel():
    # Mathics 10 re-runs its builtin import on every Kernel() and that path is
    # flaky (intermittent IncompleteSyntaxError), so share one kernel for the
    # whole module; each test still gets a fresh session via its notebook id.
    global _KERNEL
    if _KERNEL is None:
        last = None
        for _ in range(5):
            try:
                _KERNEL = Kernel()
                break
            except Exception as exc:  # noqa: BLE001 - flaky re-init, retry
                last = exc
        else:
            raise last
    return _KERNEL


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = _get_kernel()

    def setUp(self):
        self.notebook = self.id()

    def evaluate(self, source):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def text(self, source):
        return self.evaluate(source)["text"]


class InterpolationTests(_Base):
    def test_returns_compact_interpolating_function(self):
        self.assertEqual("InterpolatingFunction[{{0., 3.}}, <>]",
                         self.text("Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}]"))
        self.assertEqual("InterpolatingFunction",
                         self.text("Head[Interpolation[{{0, 0}, {1, 1}, {2, 4}}]]"))

    def test_values_match_wolfram_hermite_default(self):
        # Wolfram 15: Interpolation[{{0,0},{1,1},{2,4},{3,9}}][1.5] == 2.25
        self.assertEqual("2.25", self.text("Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}][1.5]"))
        self.assertEqual("4.", self.text("Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}][2]"))
        # flat list: abscissae 1..n
        self.assertEqual("2.5625", self.text("Interpolation[{3, 1, 4, 1, 5}][2.5]"))
        # non-uniform non-polynomial data (local cubic Lagrange pieces)
        self.assertEqual("38.125", self.text("Interpolation[{{0, 0}, {1, 1}, {2, 16}, {3, 81}, {5, 625}}][2.5]"))

    def test_spline_method_uses_cubic_spline(self):
        self.assertEqual("38.6765",
                         self.text('Interpolation[{{0, 0}, {1, 1}, {2, 16}, {3, 81}, {5, 625}}, Method -> "Spline"][2.5]'))

    def test_interpolation_order_one_is_linear(self):
        self.assertEqual("2.5", self.text("Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}, InterpolationOrder -> 1][1.5]"))
        self.assertEqual("3.", self.text("Interpolation[{{1, 2}, {3, 4}}, InterpolationOrder -> 1][2]"))

    def test_extrapolation_warns_and_evaluates(self):
        # Wolfram 15 extrapolates with InterpolatingFunction::dmval
        self.assertEqual("25.", self.text("Interpolation[{{0, 0}, {1, 1}, {2, 4}}][5]"))

    def test_end_to_end_assign_apply_percent(self):
        self.evaluate("f = Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}]")
        self.assertEqual("2.25", self.text("f[1.5]"))
        self.evaluate("Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}]")
        self.assertEqual("2.25", self.text("%[1.5]"))

    def test_plot_accepts_interpolating_function(self):
        self.evaluate("f = Interpolation[{{0, 0}, {1, 1}, {2, 4}, {3, 9}}]")
        self.assertEqual("Graphics", self.text("Plot[f[x], {x, 0, 3}] // Head"))

    def test_non_numeric_data_unevaluated(self):
        self.assertTrue(self.text("Interpolation[{a, b}]").startswith("Interpolation["))


class ListInterpolationTests(_Base):
    def test_uniform_grid(self):
        self.assertEqual("InterpolatingFunction[{{1., 4.}}, <>]",
                         self.text("ListInterpolation[{0, 1, 4, 9}]"))
        self.assertEqual("2.25", self.text("ListInterpolation[{0, 1, 4, 9}][2.5]"))
        self.assertEqual("1.", self.text("ListInterpolation[{3, 1, 4, 1, 5}][4]"))

    def test_domain_and_order(self):
        self.assertEqual("2.25", self.text("ListInterpolation[{0, 1, 4, 9}, {{0, 3}}][1.5]"))
        self.assertEqual("2.5", self.text("ListInterpolation[{0, 1, 4, 9}, InterpolationOrder -> 1][2.5]"))

    def test_multidimensional_unevaluated(self):
        self.assertTrue(self.text("ListInterpolation[{{1, 2}, {3, 4}}]").startswith("ListInterpolation["))


class InterpolatingPolynomialTests(_Base):
    def test_pair_and_flat_forms(self):
        self.assertEqual("1 + x ^ 2", self.text("InterpolatingPolynomial[{{1, 2}, {2, 5}, {3, 10}}, x]"))
        self.assertEqual("1 + x ^ 2", self.text("InterpolatingPolynomial[{2, 5, 10}, x]"))
        self.assertEqual("3 - t", self.text("InterpolatingPolynomial[{{-1, 4}, {2, 1}}, t]"))
        self.assertEqual("x", self.text("InterpolatingPolynomial[{1, 2, 3}, x]"))

    def test_symbolic_values(self):
        self.assertEqual("2 a - a x - b + b x",
                         self.text("InterpolatingPolynomial[{{1, a}, {2, b}}, x]"))


class FitTests(_Base):
    def test_linear_exact_data(self):
        # Wolfram 15 Fit always uses machine arithmetic
        self.assertEqual("1. + 2. x", self.text("Fit[{{0, 1}, {1, 3}, {2, 5}}, {1, x}, x]"))
        self.assertEqual("5.", self.text("Fit[{{0, 1}, {1, 3}, {2, 5}}, {1, x}, x] /. x -> 2"))

    def test_flat_list_and_quadratic(self):
        self.assertEqual("4.", self.text("Fit[{1, 4, 9, 16}, {1, x, x^2}, x] /. x -> 2"))
        self.assertEqual("5.375", self.text("Fit[{{1, 2}, {3, 4}, {5, 7}}, {1, x, x^2}, x] /. x -> 4"))
        self.assertEqual("1.9375", self.text("Fit[{{0, 1}, {1, 2}, {2, 2}, {3, 4}}, {1, x, x^2}, x] /. x -> 1.5"))

    def test_multivariate(self):
        self.assertEqual("5.", self.text("Fit[{{1, 1, 3}, {2, 1, 5}, {3, 2, 9}}, {1, x, y}, {x, y}] /. {x -> 2, y -> 1}"))

    def test_bad_data_unevaluated(self):
        self.assertTrue(self.text("Fit[{{1, 2}, {3}}, {1, x}, x]").startswith("Fit["))


class FindFitTests(_Base):
    def test_linear(self):
        out = self.text("FindFit[{{0, 1}, {1, 3}, {2, 5}}, a x + b, {a, b}, x]")
        self.assertTrue(out.startswith("{") and "a" in out and "b" in out, out)
        self.assertEqual("2.", self.text("a /. FindFit[{{0, 1}, {1, 3}, {2, 5}, {3, 7}}, a x + b, {a, b}, x]"))
        self.assertEqual("1.", self.text("b /. FindFit[{{0, 1}, {1, 3}, {2, 5}, {3, 7}}, a x + b, {a, b}, x]"))

    def test_start_values_and_flat_data(self):
        self.assertEqual("2.", self.text("a /. FindFit[{{0, 1}, {1, 3}, {2, 5}, {3, 7}}, a x + b, {{a, 0}, {b, 0}}, x]"))
        self.assertEqual("1.7", self.text("a /. FindFit[{1, 2, 3, 5, 8}, a x + b, {a, b}, x]"))

    def test_nonlinear_exponential(self):
        # Wolfram 15: a -> 0.9983168020298491, b -> 1.0008344899752004
        self.assertEqual("0.998317", self.text("a /. FindFit[{{0, 1}, {1, 2.7}, {2, 7.4}, {3, 20.1}}, a Exp[b x], {a, b}, x]"))
        self.assertEqual("1.00083", self.text("b /. FindFit[{{0, 1}, {1, 2.7}, {2, 7.4}, {3, 20.1}}, a Exp[b x], {a, b}, x]"))


class NDSolveRegressionTests(_Base):
    """The shared InterpolatingFunction object keeps working for NDSolve."""

    def test_ndsolve_still_evaluates(self):
        self.evaluate("sol = NDSolve[{y'[x] == y[x], y[0] == 1}, y, {x, 0, 1}]")
        self.assertEqual("1.64872", self.text("y[0.5] /. sol[[1]]"))

    def test_ndsolve_display_is_compact(self):
        out = self.text("NDSolve[{y'[x] == y[x], y[0] == 1}, y, {x, 0, 1}]")
        self.assertEqual("{{y ⇾ InterpolatingFunction[{{0., 1.}}, <>]}}", out)


if __name__ == "__main__":
    unittest.main()
