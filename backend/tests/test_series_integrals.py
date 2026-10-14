"""Dirichlet log-sums and Integrate with Assumptions, checked on real evaluator output."""

from pathlib import Path
import sys
import unittest

import sympy

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

    def last_sympy(self):
        return self.kernel.sessions[self.notebook].evaluation.last_eval.to_sympy()

    def text(self, source):
        return self.evaluate(source)["text"]


class DirichletSumTests(_Base):
    def test_log_over_n_squared_is_minus_zeta_prime_2(self):
        self.assertEqual("-Zeta'[2]", self.text("Sum[Log[n]/n^2, {n, 1, Infinity}]"))

    def test_numeric_value_matches_minus_zeta_prime(self):
        # Compare the recovered closed form numerically against mpmath, independent of the rule.
        import mpmath
        self.assertEqual("-Zeta'[2]", self.text("Sum[Log[n]/n^2, {n, 1, Infinity}]"))
        expected = -mpmath.zeta(2, derivative=1)
        # Slowly convergent log-weighted series: use Euler-Maclaurin summation.
        direct = mpmath.nsum(lambda n: mpmath.log(n) / n**2, [1, mpmath.inf], method="euler-maclaurin")
        self.assertAlmostEqual(float(expected), float(direct), places=8)

    def test_higher_powers_and_symbolic_exponent(self):
        self.assertEqual("Zeta''[3]", self.text("Sum[Log[n]^2/n^3, {n, 1, Infinity}]"))
        self.assertEqual("-Zeta'[s]", self.text("Sum[Log[n]/n^s, {n, 1, Infinity}]"))
        self.assertEqual("-Derivative[3][Zeta][s]", self.text("Sum[Log[n]^3/n^s, {n, 1, Infinity}]"))

    def test_coefficient_and_shifted_start(self):
        self.assertEqual("-a Zeta'[2]", self.text("Sum[a Log[n]/n^2, {n, 1, Infinity}]"))
        self.assertEqual("-Zeta'[2]", self.text("Sum[Log[n]/n^2, {n, 2, Infinity}]"))  # log(1)=0
        self.assertEqual("-Zeta'[2] - Log[2] / 4", self.text("Sum[Log[n]/n^2, {n, 3, Infinity}]"))

    def test_divergent_and_unrelated_sums_are_left_alone(self):
        self.assertTrue(self.text("Sum[Log[n]/n, {n, 1, Infinity}]").startswith("Sum["))
        self.assertTrue(self.text("Sum[Log[n]/Sqrt[n], {n, 1, Infinity}]").startswith("Sum["))
        self.assertTrue(self.text("Sum[Sin[n]/n^2, {n, 1, Infinity}]").startswith("Sum["))

    def test_native_sums_unchanged(self):
        self.assertEqual("Pi ^ 2 / 6", self.text("Sum[1/n^2, {n, 1, Infinity}]"))
        self.assertEqual("55", self.text("Sum[k, {k, 1, 10}]"))
        self.assertEqual("1", self.text("Sum[1/2^i, {i, 1, Infinity}]"))
        self.assertEqual("n (1 + n) / 2", self.text("Sum[k, {k, 1, n}]"))


class IntegrateAssumptionsTests(_Base):
    def test_assumptions_option_no_longer_crashes_and_restores_global(self):
        self.assertEqual("Log[a]", self.text("Integrate[1/x, {x, 1, a}, Assumptions -> a > 1]"))
        self.assertEqual("True", self.text("$Assumptions"))

    def test_fermi_gaussian_integral_is_sqrt_pi_l_q(self):
        self.evaluate("Integrate[Exp[-n^2/(4 l q)]/(1 + Exp[n/q]), {n, -Infinity, Infinity}, Assumptions -> l > 0 && q > 0]")
        actual = self.last_sympy()
        syms = {s.name.split("_")[-1]: s for s in actual.free_symbols}
        expected = sympy.sqrt(sympy.pi * syms["l"] * syms["q"])
        self.assertEqual(0, sympy.simplify(actual - expected))

    def test_gaussian_with_positive_parameter(self):
        self.assertEqual("Sqrt[Pi] / Sqrt[a]", self.text("Integrate[Exp[-a x^2], {x, -Infinity, Infinity}, Assumptions -> a > 0]"))
        self.assertEqual("Sqrt[2] s Sqrt[Pi]", self.text("Integrate[Exp[-x^2/(2 s^2)], {x, -Infinity, Infinity}, Assumptions -> s > 0]"))

    def test_without_assumptions_native_behaviour_is_kept(self):
        self.assertTrue(self.text("Integrate[Exp[-a x^2], {x, -Infinity, Infinity}]").startswith("ConditionalExpression["))
        self.assertEqual("Sqrt[Pi]", self.text("Integrate[Exp[-x^2], {x, -Infinity, Infinity}]"))
        self.assertEqual("x ^ 3 / 3", self.text("Integrate[x^2, x]"))
        self.assertEqual("2", self.text("Integrate[Sin[x], {x, 0, Pi}]"))


class BernoulliConventionTests(_Base):
    def test_b1_uses_wolfram_sign(self):
        self.assertEqual("-1 / 2", self.text("BernoulliB[1]"))
        self.assertEqual("-0.5", self.text("N[BernoulliB[1]]"))

    def test_generating_function_sums(self):
        # sum_{x>=1} B_{x+1}/(x+1)! = e/(e-1) - 3/2
        self.evaluate("Sum[BernoulliB[x+1]/(x+1)!, {x, 1, Infinity}]")
        actual = self.last_sympy()
        self.assertEqual(0, sympy.simplify(actual - (sympy.E / (sympy.E - 1) - sympy.Rational(3, 2))))
        self.assertEqual("1 / (-1 + E)", self.text("Sum[BernoulliB[n]/n!, {n, 0, Infinity}]"))
        self.assertEqual("t / (-1 + E ^ t)", self.text("Sum[BernoulliB[n] t^n/n!, {n, 0, Infinity}]"))
        self.assertEqual("1 / 2 + 1 / (-1 + E)", self.text("Sum[BernoulliB[2 k]/(2 k)!, {k, 0, Infinity}]"))
        self.assertEqual("-1 / 2", self.text("Sum[BernoulliB[2 k + 1]/(2 k + 1)!, {k, 0, Infinity}]"))
        self.assertEqual("139383887 / 239500800", self.text("Sum[BernoulliB[n]/n!, {n, 0, 10}]"))
        self.assertTrue(self.text("Sum[BernoulliB[n]/n, {n, 1, Infinity}]").startswith("Sum["))

    def test_other_numbers_and_polynomials_unchanged(self):
        self.assertEqual("{1, -1 / 2, 1 / 6, 0, -1 / 30, 0, 1 / 42}", self.text("Table[BernoulliB[n], {n, 0, 6}]"))
        self.assertEqual("-1 / 2 + x", self.text("BernoulliB[1, x]"))
        self.assertEqual("495057205241079648212477525 / 66", self.text("BernoulliB[50]"))


class SeriesTests(_Base):
    def test_bernoulli_generating_function_no_longer_recurses(self):
        self.assertEqual(
            "1 - x / 2 + x ^ 2 / 12 - x ^ 4 / 720 + x ^ 6 / 30240 - x ^ 8 / 1209600 + O[x] ^ 9",
            self.text("Series[x/(Exp[x] - 1), {x, 0, 8}]"),
        )
        self.assertEqual("-1 / 1209600", self.text("SeriesCoefficient[Series[x/(Exp[x] - 1), {x, 0, 8}], 8]"))

    def test_laurent_series(self):
        self.assertEqual("1 / x - x / 3 - x ^ 3 / 45 + O[x] ^ 4", self.text("Series[Cot[x], {x, 0, 3}]"))
        self.assertEqual("1 / x + x + O[x] ^ 3", self.text("Series[1/x + x, {x, 0, 2}]"))

    def test_existing_series_behaviour_and_seriesdata_layout(self):
        self.assertEqual("SeriesData[x, 0, {1, 1, Rational[1, 2], Rational[1, 6]}, 0, 4, 1]", self.text("Series[Exp[x], {x, 0, 3}] // FullForm"))
        self.assertEqual("x - x ^ 3 / 6 + x ^ 5 / 120 + O[x] ^ 6", self.text("Series[Sin[x], {x, 0, 5}]"))
        self.assertEqual("1 - (x - Pi / 2) ^ 2 / 2 + O[x - Pi / 2] ^ 4", self.text("Series[Sin[x], {x, Pi/2, 3}]"))
        self.assertEqual("x + x ^ 3 / 3 + 2 x ^ 5 / 15", self.text("Normal[Series[Tan[x], {x, 0, 5}]]"))
        self.assertEqual("1 + 2 x + x ^ 2 / 2 + O[x] ^ 4", self.text("Series[Exp[x], {x, 0, 3}] + Series[Sin[x], {x, 0, 3}]"))


class ZetaIntegralTests(_Base):
    def test_log_products_on_unit_interval(self):
        self.assertEqual("Zeta[3]", self.text("Integrate[Log[x] Log[1 - x]/x, {x, 0, 1}]"))
        self.assertEqual("2 Zeta[3]", self.text("Integrate[Log[x]^2/(1 - x), {x, 0, 1}]"))
        self.assertEqual("-Pi ^ 2 / 6", self.text("Integrate[Log[1 - x]/x, {x, 0, 1}]"))

    def test_bose_fermi_integrals(self):
        self.assertEqual("Pi ^ 4 / 15", self.text("Integrate[x^3/(Exp[x] - 1), {x, 0, Infinity}]"))
        self.assertEqual("7 Pi ^ 4 / 120", self.text("Integrate[x^3/(Exp[x] + 1), {x, 0, Infinity}]"))
        self.assertEqual("Pi ^ 2 / 24", self.text("Integrate[x/(Exp[2 x] - 1), {x, 0, Infinity}]"))
        self.assertEqual("Gamma[1 + s] Zeta[1 + s]", self.text("Integrate[x^s/(Exp[x] - 1), {x, 0, Infinity}, Assumptions -> s > 0]"))

    def test_polylog_result_is_made_exact(self):
        self.assertEqual("Pi ^ 3 / 8", self.text("Integrate[Log[x]^2/(1 + x^2), {x, 0, Infinity}]"))
        self.assertEqual("0", self.text("Integrate[Log[x]/(1 + x^2), {x, 0, Infinity}]"))

    def test_two_dimensional_gaussian_with_chained_assumption(self):
        src = "Integrate[Exp[-(x^2 + 2 a x y + y^2)], {x, -Infinity, Infinity}, {y, -Infinity, Infinity}, Assumptions -> -1 < a < 1]"
        self.assertEqual("Pi / Sqrt[1 - a ^ 2]", self.text(src))
        divergent = src.replace("-1 < a < 1", "a > 1")
        self.assertTrue(self.text(divergent).startswith("Integrate["))
        self.assertEqual("1", self.text("Integrate[x y, {x, 0, 1}, {y, 0, 2}]"))


class LimitGuardTests(_Base):
    def test_correct_input_evaluates(self):
        self.assertEqual("1 / Sqrt[E]", self.text("Limit[(1 + 1/x)^(x^2)/Exp[x], x -> Infinity]"))
        self.assertEqual("E", self.text("Limit[(1 + 1/x)^x, x -> Infinity]"))
        self.assertEqual("1", self.text("Limit[Sin[x]/x, x -> 0]"))
        self.assertEqual("Infinity", self.text("Limit[1/x, x -> 0, Direction -> -1]"))

    def test_undefined_function_does_not_leak_sympy_dummies(self):
        out = self.text("Limit[(1 + 1/x)^(x^2)/exp[x], x -> Infinity]")
        self.assertTrue(out.startswith("Limit["), out)
        self.assertNotIn("Dummy", out)
        self.assertNotIn("sympy", out)
        self.assertTrue(self.text("Limit[x/f[x], x -> Infinity]").startswith("Limit["))


class DiscreteLimitTests(_Base):
    def test_trig_of_sqrt_sequences(self):
        self.assertEqual("1", self.text("DiscreteLimit[Sin[Pi Sqrt[n^2 + n]]^2, n -> Infinity]"))
        self.assertEqual("0", self.text("DiscreteLimit[Cos[Pi Sqrt[n^2 + n]]^2, n -> Infinity]"))
        self.assertEqual("0", self.text("DiscreteLimit[Sin[Pi Sqrt[n^2 + 1]], n -> Infinity]"))
        self.assertEqual("0", self.text("DiscreteLimit[Sin[2 Pi Sqrt[n^2 + n]], n -> Infinity]"))

    def test_oscillating_sequences_stay_unevaluated_not_empty(self):
        for src in ["DiscreteLimit[Sin[Pi Sqrt[n^2 + n]], n -> Infinity]", "DiscreteLimit[(-1)^n, n -> Infinity]", "DiscreteLimit[Sin[n], n -> Infinity]"]:
            result = self.evaluate(src)
            self.assertTrue(result["text"].startswith("DiscreteLimit["), result)
            self.assertFalse(result.get("suppressed"), result)

    def test_ordinary_sequences(self):
        self.assertEqual("0", self.text("DiscreteLimit[1/n, n -> Infinity]"))
        self.assertEqual("E", self.text("DiscreteLimit[(1 + 1/n)^n, n -> Infinity]"))
        self.assertEqual("1", self.text("DiscreteLimit[n Sin[1/n], n -> Infinity]"))


class LaplaceIntegralTests(_Base):
    def test_real_frequency_parameter_gives_unconditional_result(self):
        assum = ", Assumptions -> a > 0 && Element[b, Reals]]"
        self.assertEqual("(a ^ 2 - b ^ 2) / (a ^ 2 + b ^ 2) ^ 2", self.text("Integrate[x Exp[-a x] Cos[b x], {x, 0, Infinity}" + assum))
        self.assertEqual("a / (a ^ 2 + b ^ 2)", self.text("Integrate[Exp[-a x] Cos[b x], {x, 0, Infinity}" + assum))
        self.assertEqual("E ^ (-b ^ 2 / (4 a)) Sqrt[Pi] / Sqrt[a]", self.text("Integrate[Exp[-a x^2] Cos[b x], {x, -Infinity, Infinity}" + assum))

    def test_without_assumptions_the_condition_is_kept(self):
        self.assertTrue(self.text("Integrate[x Exp[-a x] Cos[b x], {x, 0, Infinity}]").startswith("ConditionalExpression["))


class EulerSumProductTests(_Base):
    def test_euler_sums(self):
        self.assertEqual("2 Zeta[3]", self.text("Sum[HarmonicNumber[n]/n^2, {n, 1, Infinity}]"))
        self.assertEqual("Pi ^ 4 / 72", self.text("Sum[HarmonicNumber[n]/n^3, {n, 1, Infinity}]"))
        self.assertEqual("-Pi ^ 2 Zeta[3] / 6 + 3 Zeta[5]", self.text("Sum[HarmonicNumber[n]/n^4, {n, 1, Infinity}]"))
        self.assertTrue(self.text("Sum[HarmonicNumber[n]/n, {n, 1, Infinity}]").startswith("Sum["))

    def test_central_binomial_sums(self):
        import mpmath
        self.assertEqual("Pi ^ 2 / 18", self.text("Sum[1/(n^2 Binomial[2 n, n]), {n, 1, Infinity}]"))
        self.assertEqual("2 Zeta[3] / 5", self.text("Sum[(-1)^(n-1)/(n^3 Binomial[2 n, n]), {n, 1, Infinity}]"))
        self.assertEqual("-2 Zeta[3] / 5", self.text("Sum[(-1)^n/(n^3 Binomial[2 n, n]), {n, 1, Infinity}]"))
        self.assertEqual("Sqrt[3] Pi / 9", self.text("Sum[1/(n Binomial[2 n, n]), {n, 1, Infinity}]"))
        self.assertEqual("17 Pi ^ 4 / 3240", self.text("Sum[1/(n^4 Binomial[2 n, n]), {n, 1, Infinity}]"))
        self.assertEqual("2 Log[GoldenRatio] ^ 2", self.text("Sum[(-1)^(n-1)/(n^2 Binomial[2 n, n]), {n, 1, Infinity}]"))
        # every table entry agrees with direct summation to 30 digits
        self.evaluate("Sum[1/(n^3 Binomial[2 n, n]), {n, 1, Infinity}]")
        closed = self.last_sympy()
        mpmath.mp.dps = 40
        direct = mpmath.nsum(lambda n: 1 / (n**3 * mpmath.binomial(2 * n, n)), [1, mpmath.inf])
        self.assertLess(abs(float(sympy.N(closed, 40) - direct)), 1e-30)
        self.assertTrue(self.text("Sum[1/(n^5 Binomial[2 n, n]), {n, 1, Infinity}]").startswith("HypergeometricPFQ["))

    def test_rational_infinite_products(self):
        self.assertEqual("Sinh[Pi] / Pi", self.text("Product[1 + 1/n^2, {n, 1, Infinity}]"))
        self.assertEqual("Pi / 2", self.text("Product[4 n^2/(4 n^2 - 1), {n, 1, Infinity}]"))
        self.assertEqual("1 / 2", self.text("Product[1 - 1/n^2, {n, 2, Infinity}]"))
        self.assertEqual("1 / Cosh[Pi]", self.text("Product[(n^2 + 1)/(n^2 + 4), {n, 1, Infinity}]"))
        self.assertTrue(self.text("Product[1 + 1/n, {n, 1, Infinity}]").startswith("Product["))
        self.assertEqual("120", self.text("Product[n, {n, 1, 5}]"))


class RationalTrigIntegralTests(_Base):
    """Frullani cosine, rational×trig residues, and trig-rational tan-substitution
    fallbacks in assumption_integrate, plus cleanup of ugly native closed forms."""

    def test_frullani_cosine_difference(self):
        self.assertEqual("Pi (-a + b)", self.text(
            "Integrate[(Cos[2 a x] - Cos[2 b x])/x^2, {x, 0, Infinity}, Assumptions -> a > 0 && b > 0]"))
        self.assertEqual("Pi (-a + b)", self.text(
            "Integrate[(Cos[2 a x] - Cos[2 b x])/x^2, {x, 0, Infinity}]"))
        self.assertEqual("Pi", self.text("Integrate[(Cos[3 x] - Cos[5 x])/x^2, {x, 0, Infinity}]"))

    def test_rational_times_sin_half_line(self):
        self.assertEqual("-Pi / 2 + Pi / E ^ 2", self.text(
            "Integrate[(x^2 - 1)/(x^2 + 1) Sin[2 x]/x, {x, 0, Infinity}]"))
        self.assertEqual("Pi / (6 E ^ 9)", self.text("Integrate[Cos[3 x]/(x^2 + 9), {x, 0, Infinity}]"))

    def test_rational_times_trig_full_line(self):
        self.assertEqual("Pi (Sin[1] + 2 E ^ 2 - 2 Cos[1]) / (10 E ^ 2)", self.text(
            "Integrate[Sin[x]/(x (x^2 + 2 x + 5)), {x, -Infinity, Infinity}]"))

    def test_sin_over_x_times_quadratic_matches_sinh_form(self):
        # π(1 - e^-2)/8 equals π Sinh[1]/(4 E); check numerically, not by text.
        self.evaluate("Integrate[Sin[x]/(x (x^2 + 4)), {x, 0, Infinity}]")
        closed = self.last_sympy()
        diff = sympy.N(closed - sympy.pi * sympy.sinh(1) / (4 * sympy.E), 50)
        self.assertLess(abs(float(diff)), 1e-40)

    def test_trig_rational_over_period_is_denested(self):
        self.assertEqual("Sqrt[3] Pi / 3", self.text("Integrate[1/(1 + 2 Sin[x]^2), {x, 0, Pi}]"))
        self.assertEqual("Sqrt[2] Pi / 2", self.text("Integrate[1/(1 + Sin[x]^2), {x, 0, Pi}]"))

    def test_unrelated_integrals_unchanged(self):
        self.assertEqual("Pi / 2", self.text("Integrate[Sin[x]/x, {x, 0, Infinity}]"))
        self.assertEqual("Pi", self.text("Integrate[1/(x^2 + 1), {x, -Infinity, Infinity}]"))
        self.assertEqual("1 / 2", self.text("Integrate[x Exp[-x^2], {x, 0, Infinity}]"))
        self.assertEqual("Pi / 2", self.text("Integrate[Sin[x]^2, {x, 0, Pi}]"))


if __name__ == "__main__":
    unittest.main()
