"""Functions added in 0.3: algebra, numerics, distributions, plots/regions, symbolic extras."""

from pathlib import Path
import sys
import unittest

import sympy

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel()

    def setUp(self):
        self.notebook = self.id()

    def evaluate(self, source):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def text(self, source):
        return self.evaluate(source)["text"]

    def last_sympy(self):
        return self.kernel.sessions[self.notebook].evaluation.last_eval.to_sympy()


class AlgebraExtrasTests(_Base):
    def test_polynomial_algebra(self):
        self.assertEqual("-2 - 5 x + x ^ 2", self.text("CharacteristicPolynomial[{{1, 2}, {3, 4}}, x]"))
        self.assertEqual("1 + x + x ^ 2", self.text("PolynomialQuotient[x^3 - 1, x - 1, x]"))
        self.assertEqual("2", self.text("PolynomialRemainder[x^3 + 1, x - 1, x]"))
        self.assertEqual("a ^ 2 - 2 a b + b ^ 2", self.text("Resultant[x^2 + a, x^2 + b, x]"))
        self.assertEqual("{-1 + 2 y ^ 2, x - y}", self.text("GroebnerBasis[{x^2 + y^2 - 1, x - y}, {x, y}]"))
        self.assertEqual("{{{1, 0}, {0, 1}}, {{1, 1}, {0, 1}}}", self.text("JordanDecomposition[{{1, 1}, {0, 1}}]"))

    def test_trig_and_number_theory(self):
        self.assertEqual("-Sin[x] ^ 3 + 3 Cos[x] ^ 2 Sin[x]", self.text("TrigExpand[Sin[3 x]]"))
        self.assertEqual("1 / 2 - Cos[2 x] / 2", self.text("TrigReduce[Sin[x]^2]"))
        self.assertEqual("23", self.text("ChineseRemainder[{2, 3, 2}, {3, 5, 7}]"))
        self.assertTrue(self.text("ChineseRemainder[{1, 2}, {2, 4}]").startswith("ChineseRemainder["))
        self.assertEqual("1 / 2 + Sqrt[5] / 2", self.text("RootApproximant[1.6180339887]"))
        self.assertEqual("Sqrt[2]", self.text("RootApproximant[1.4142135624]"))


class NumericExtrasTests(_Base):
    def test_dsolve_with_initial_conditions(self):
        self.assertEqual("{{y[x] ⇾ E ^ x}}", self.text("DSolve[{y'[x] == y[x], y[0] == 1}, y[x], x]"))
        self.assertEqual("{{y[x] ⇾ Sin[x]}}", self.text("DSolve[{y''[x] + y[x] == 0, y[0] == 0, y'[0] == 1}, y[x], x]"))
        self.assertEqual("{{y[x] ⇾ E ^ x C[1]}}", self.text("DSolve[y'[x] == y[x], y[x], x]"))

    def test_ndsolve_interpolating_function(self):
        self.evaluate("sol = NDSolve[{y'[x] == y[x], y[0] == 1}, y, {x, 0, 1}]")
        self.assertAlmostEqual(2.718281828, float(self.last_sympy_of("y[1] /. sol[[1]]")), places=6)
        self.evaluate("s2 = NDSolve[{y''[x] + y[x] == 0, y[0] == 0, y'[0] == 1}, y, {x, 0, Pi}]")
        self.assertAlmostEqual(1.0, float(self.last_sympy_of("y[Pi/2] /. s2[[1]]")), places=6)

    def last_sympy_of(self, src):
        self.evaluate(src)
        return self.last_sympy()

    def test_nsum_nminimize(self):
        self.assertEqual("1.64493", self.text("NSum[1/n^2, {n, 1, Infinity}]"))
        self.evaluate("NMinimize[(x - 1)^2 + (y - 2)^2, {x, y}]")
        val, rules = self.kernel.sessions[self.notebook].evaluation.last_eval.elements
        self.assertLess(abs(float(val.to_sympy())), 1e-8)
        self.assertEqual("{5., {x ⇾ 3.}}", self.text("NMaximize[-(x - 3)^2 + 5, x]"))
        self.assertEqual("{-0.25, {x ⇾ -1.5}}", self.text("NMinimize[x^2 + 3 x + 2, x]"))


class DistributionTests(_Base):
    def test_moments_fix_the_mean_bug(self):
        self.assertEqual("m", self.text("Mean[NormalDistribution[m, s]]"))
        self.assertEqual("s ^ 2", self.text("Variance[NormalDistribution[m, s]]"))
        self.assertEqual("l", self.text("Variance[PoissonDistribution[l]]"))
        self.assertEqual("n p", self.text("Mean[BinomialDistribution[n, p]]"))
        self.assertEqual("1 / l", self.text("StandardDeviation[ExponentialDistribution[l]]"))
        self.assertEqual("Log[2] / l", self.text("Median[ExponentialDistribution[l]]"))
        # list statistics unchanged
        self.assertEqual("22", self.text("Mean[{1, 2, 3, 4, 100}]"))
        self.assertEqual("32 / 7", self.text("Variance[{2, 4, 4, 4, 5, 5, 7, 9}]"))
        self.assertEqual("7 / 2", self.text("Median[{3, 1, 4, 1, 5, 9, 2, 6}]"))

    def test_pdf_cdf(self):
        self.assertEqual("Sqrt[2] E ^ (-x ^ 2 / 2) / (2 Sqrt[Pi])", self.text("PDF[NormalDistribution[0, 1], x]"))
        self.assertEqual("0.975002", self.text("CDF[NormalDistribution[0, 1], 1.96]"))
        self.assertEqual("1 - 1 / E ^ 2", self.text("CDF[ExponentialDistribution[1], 2]"))
        self.assertEqual("319 / 512", self.text("CDF[BinomialDistribution[10, 1/2], 5]"))
        self.assertEqual("9 / (2 E ^ 3)", self.text("PDF[PoissonDistribution[3], 2]"))
        self.assertEqual("1.95996", self.text("InverseCDF[NormalDistribution[0, 1], 0.975]"))

    def test_expectation_probability_with_distributed_notation(self):
        self.assertEqual("1", self.text("Expectation[x^2, x \\[Distributed] NormalDistribution[0, 1]]"))
        self.assertEqual("3", self.text("Expectation[x^4, x \\[Distributed] NormalDistribution[0, 1]]"))
        self.assertEqual("E ^ (m + s ^ 2 / 2)", self.text("Expectation[Exp[x], x \\[Distributed] NormalDistribution[m, s]]"))
        # Wolfram: (1 - Erf[1/Sqrt[2]])/2; the contract CDF yields the Erfc form
        self.assertEqual("Erfc[Sqrt[2] / 2] / 2", self.text("Probability[x > 1, x \\[Distributed] NormalDistribution[0, 1]]"))
        self.assertEqual("1 / E", self.text("Probability[x > 1, x \\[Distributed] ExponentialDistribution[1]]"))
        self.assertEqual("1 / (2 E)", self.text("Probability[x == 2, x \\[Distributed] PoissonDistribution[1]]"))
        self.evaluate("Probability[x > 1 && x < 2, x \\[Distributed] NormalDistribution[0, 1]]")
        self.assertAlmostEqual(0.135905, float(sympy.N(self.last_sympy())), places=5)


class PlotsRegionsTests(_Base):
    def test_contour_plot_renders(self):
        r = self.evaluate("ContourPlot[x^2 + y^2, {x, -2, 2}, {y, -2, 2}]")
        self.assertTrue(r.get("svg"))
        r = self.evaluate("ContourPlot[{x^2 + y^2 == 1, y == x^2}, {x, -2, 2}, {y, -2, 2}]")
        self.assertTrue(r.get("svg"))

    def test_region_measures(self):
        self.assertEqual("4 Pi", self.text("Area[Disk[{0, 0}, 2]]"))
        self.assertEqual("12", self.text("Area[Rectangle[{0, 0}, {3, 4}]]"))
        self.assertEqual("6", self.text("Area[Polygon[{{0, 0}, {4, 0}, {4, 3}}]]"))
        self.assertEqual("4 Pi / 3", self.text("RegionMeasure[Ball[{0, 0, 0}, 1]]"))
        self.assertEqual("4 Pi / 3", self.text("Volume[Ball[{0, 0, 0}, 1]]"))
        self.assertEqual("5", self.text("RegionMeasure[Line[{{0, 0}, {3, 4}}]]"))


class SymbolicExtrasTests(_Base):
    def test_reduce_reals(self):
        self.assertEqual("2 < x ∨ x < 1", self.text("Reduce[x^2 - 3 x + 2 > 0, x, Reals]"))
        self.assertEqual("(-2) < x < 2", self.text("Reduce[x^2 < 4, x, Reals]"))
        self.assertEqual("x ⩵ -2 ∨ x ⩵ 2", self.text("Reduce[x^2 == 4, x]"))
        self.assertEqual("False", self.text("Reduce[x^2 + 1 == 0, x, Reals]"))

    def test_fullsimplify_gamma_polylog(self):
        self.evaluate("FullSimplify[Sqrt[2 + Sqrt[3]]]")
        self.assertEqual(0, sympy.simplify(self.last_sympy() - (1 + sympy.sqrt(3)) / sympy.sqrt(2)))
        self.assertEqual("1", self.text("FullSimplify[Sin[x]^2 + Cos[x]^2]"))
        # kernel: plain product stays inert, FullSimplify applies the reflection formula
        self.assertEqual("Gamma[1 / 3] Gamma[2 / 3]", self.text("Gamma[1/3] Gamma[2/3]"))
        self.assertEqual("2 Sqrt[3] Pi / 3", self.text("FullSimplify[Gamma[1/3] Gamma[2/3]]"))
        self.assertEqual("Sqrt[2] Pi", self.text("FullSimplify[Gamma[1/4] Gamma[3/4]]"))
        self.assertEqual("Sqrt[Pi]", self.text("Gamma[1/2]"))
        self.assertEqual("12 x", self.text("3 4 x"))
        self.assertEqual("Pi ^ 2 / 12 - Log[2] ^ 2 / 2", self.text("PolyLog[2, 1/2]"))
        self.assertEqual("Pi ^ 2 / 6", self.text("PolyLog[2, 1]"))
        self.assertEqual("0.582241", self.text("PolyLog[2, 0.5]"))

    def test_fibonacci_sums_and_integral_table(self):
        self.assertEqual("2", self.text("Sum[Fibonacci[n]/2^n, {n, 1, Infinity}]"))
        self.assertEqual("3 / 5", self.text("Sum[Fibonacci[n]/3^n, {n, 0, Infinity}]"))
        self.assertEqual("Catalan", self.text("Integrate[ArcTan[x]/x, {x, 0, 1}]"))
        self.assertEqual("-Pi Log[2]", self.text("Integrate[Log[Sin[x]], {x, 0, Pi}]"))
        self.assertEqual("Sqrt[2] Pi / 2", self.text("Integrate[Sqrt[Tan[x]], {x, 0, Pi/2}]"))
        self.assertEqual("Pi Log[2] / 8", self.text("Integrate[Log[1 + x]/(1 + x^2), {x, 0, 1}]"))


class ResultPolishTests(_Base):
    """Forms chosen to match the real Wolfram kernel (see wolfram-re-round2/oracle)."""

    def test_rsolve_recognises_fibonacci_and_lucas(self):
        self.assertEqual("{{a[n] ⇾ Fibonacci[n]}}", self.text("RSolve[{a[n] == a[n-1] + a[n-2], a[0] == 0, a[1] == 1}, a[n], n]"))
        self.assertEqual("{{a[n] ⇾ LucasL[n]}}", self.text("RSolve[{a[n] == a[n-1] + a[n-2], a[0] == 2, a[1] == 1}, a[n], n]"))
        self.assertEqual("{{a[n] ⇾ -1 + 2 ^ n C[0]}}", self.text("RSolve[a[n+1] == 2 a[n] + 1, a[n], n]"))

    def test_bessel_order_is_not_wrapped_in_sqrt(self):
        self.assertEqual("{{y[x] ⇾ BesselJ[nu, x] C[1] + BesselY[nu, x] C[2]}}",
                         self.text("DSolve[x^2 y''[x] + x y'[x] + (x^2 - nu^2) y[x] == 0, y[x], x]"))

    def test_power_series_sum_drops_convergence_condition(self):
        self.assertEqual("-Log[1 - x]", self.text("Sum[x^n/n, {n, 1, Infinity}]"))
        self.assertEqual("-1 / (-1 + x)", self.text("Sum[x^n, {n, 0, Infinity}]"))


if __name__ == "__main__":
    unittest.main()
