"""Group 3 (probability distributions): contract-driven rules, special
functions, derived distributions, statistics.  Expected strings are the
InputForm the activated Wolfram 15.0.1 kernel returns (see
wolfram-re-round2/oracle/dist-contracts-full.jsonl and
dist-derived-wolfram.txt), rendered in the notebook's text form."""

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

    def num(self, source):
        return float(self.text("N[" + source + "]"))


class ContractRuleTests(_Base):
    def test_table_loads(self):
        from dist_contracts import CONTRACTS
        self.assertEqual(90, len(CONTRACTS))
        self.assertEqual(87, len({c["head"] for c in CONTRACTS}))

    def test_pdf_cdf_forms_match_kernel(self):
        self.assertEqual("Piecewise[{{b ^ (-a) E ^ (-x / b) x ^ (-1 + a) / Gamma[a], x > 0}}, 0]", self.text("PDF[GammaDistribution[a, b], x]"))
        self.assertEqual("Piecewise[{{E ^ (-l x) l, x ≥ 0}}, 0]", self.text("PDF[ExponentialDistribution[l], x]"))
        # Wolfram: Erfc[(m - x)/(Sqrt[2]*s)]/2 (Mathics rationalises 1/Sqrt[2])
        self.assertEqual("Erfc[Sqrt[2] (m - x) / (2 s)] / 2", self.text("CDF[NormalDistribution[m, s], x]"))
        self.assertEqual("Piecewise[{{1, 0 ≤ x ≤ 1}}, 0]", self.text("PDF[UniformDistribution[{0, 1}], x]"))
        self.assertEqual("1 / (Pi (1 + x ^ 2))", self.text("PDF[CauchyDistribution[], x]"))
        self.assertEqual("Piecewise[{{p ^ x Binomial[n, x] (1 - p) ^ (n - x), 0 ≤ x ≤ n}}, 0]", self.text("PDF[BinomialDistribution[n, p], x]"))

    def test_numeric_arguments_select_piecewise_branch(self):
        self.assertEqual("0", self.text("PDF[ExponentialDistribution[2], -1]"))
        self.assertEqual("E ^ (-2 l) l", self.text("PDF[ExponentialDistribution[l], 2]"))
        self.assertEqual("15 / 128", self.text("PDF[BinomialDistribution[10, 1/2], 3]"))
        self.assertEqual("17 / (2 E ^ 3)", self.text("CDF[PoissonDistribution[3], 2.5]"))
        self.assertEqual("15 / 16", self.text("CDF[GeometricDistribution[1/2], 3]"))  # support starts at 0
        self.assertEqual("1 / 2", self.text("CDF[NormalDistribution[0, 1], 0]"))
        self.assertAlmostEqual(0.933193, self.num("CDF[NormalDistribution[0, 1], 3/2]"), places=6)
        self.assertEqual("0.129518", self.text("PDF[NormalDistribution[0, 1], 1.5]"))

    def test_moments_and_shape(self):
        self.assertEqual("m", self.text("Mean[NormalDistribution[m, s]]"))
        self.assertEqual("n p", self.text("Mean[BinomialDistribution[n, p]]"))
        self.assertEqual("-1 + 1 / p", self.text("Mean[GeometricDistribution[p]]"))
        self.assertEqual("a - b EulerGamma", self.text("Mean[GumbelDistribution[a, b]]"))
        self.assertEqual("Piecewise[{{a k / (-1 + a), a > 1}}, Indeterminate]", self.text("Mean[ParetoDistribution[k, a]]"))
        self.assertEqual("Indeterminate", self.text("Mean[ParetoDistribution[1, 1/2]]"))
        self.assertEqual("5 / 3", self.text("Variance[StudentTDistribution[5]]"))
        self.assertEqual("Indeterminate", self.text("Variance[StudentTDistribution[1]]"))
        self.assertEqual("s", self.text("StandardDeviation[NormalDistribution[m, s]]"))
        self.assertEqual("Sqrt[E]", self.text("Mean[LogNormalDistribution[0, 1]]"))
        self.assertEqual("E ^ m", self.text("Median[LogNormalDistribution[m, s]]"))
        self.assertEqual("b Log[2] ^ (1 / a)", self.text("Median[WeibullDistribution[a, b]]"))
        self.assertEqual("0", self.text("Skewness[NormalDistribution[m, s]]"))
        self.assertEqual("3", self.text("Kurtosis[NormalDistribution[m, s]]"))
        self.assertEqual("Piecewise[{{3 + 6 / (-4 + n), n > 4}}, Indeterminate]", self.text("Kurtosis[StudentTDistribution[n]]"))
        self.assertAlmostEqual(0.940534, self.num("Median[FRatioDistribution[3, 4]]"), places=5)

    def test_raw_central_factorial_moments_and_cumulants(self):
        self.assertEqual("m ^ 2 + s ^ 2", self.text("Moment[NormalDistribution[m, s], 2]"))
        self.assertEqual("m ^ 3 + 3 m s ^ 2", self.text("Moment[NormalDistribution[m, s], 3]"))
        self.assertEqual("3", self.text("Moment[NormalDistribution[0, 1], 4]"))
        self.assertEqual("2 a b ^ 3 + 3 a ^ 2 b ^ 3 + a ^ 3 b ^ 3", self.text("Moment[GammaDistribution[a, b], 3]"))
        self.assertEqual("n p - n p ^ 2 + n ^ 2 p ^ 2", self.text("Moment[BinomialDistribution[n, p], 2]"))
        self.assertEqual("l + 3 l ^ 2 + l ^ 3", self.text("Moment[PoissonDistribution[l], 3]"))
        self.assertEqual("l ^ (-k) k!", self.text("Moment[ExponentialDistribution[l], k]"))
        self.assertEqual("(1 - 0 ^ (1 + k)) / (1 + k)", self.text("Moment[UniformDistribution[{0, 1}], k]"))
        self.assertEqual("3 s ^ 4", self.text("CentralMoment[NormalDistribution[m, s], 4]"))
        self.assertEqual("2 / l ^ 3", self.text("CentralMoment[ExponentialDistribution[l], 3]"))
        self.assertEqual("l", self.text("CentralMoment[PoissonDistribution[l], 3]"))
        self.assertEqual("s ^ 2", self.text("Cumulant[NormalDistribution[m, s], 2]"))
        self.assertEqual("l", self.text("Cumulant[PoissonDistribution[l], 3]"))
        self.assertEqual("2 / l ^ 3", self.text("Cumulant[ExponentialDistribution[l], 3]"))
        self.assertEqual("l ^ 2", self.text("FactorialMoment[PoissonDistribution[l], 2]"))
        self.assertEqual("-n p ^ 2 (1 - n)", self.text("FactorialMoment[BinomialDistribution[n, p], 2]"))
        # data versions keep working
        self.assertEqual("15 / 2", self.text("Moment[{1, 2, 3, 4}, 2]"))
        self.assertEqual("5 / 4", self.text("Cumulant[{1, 2, 3, 4}, 2]"))
        self.assertEqual("0", self.text("CentralMoment[{1, 2, 3, 4}, 3]"))

    def test_generating_functions_domain_assumptions(self):
        self.assertEqual("(1 - b t) ^ (-a)", self.text("MomentGeneratingFunction[GammaDistribution[a, b], t]"))
        self.assertEqual("E ^ (l (-1 + E ^ t))", self.text("MomentGeneratingFunction[PoissonDistribution[l], t]"))
        self.assertEqual("E ^ (-t Sign[t])", self.text("CharacteristicFunction[CauchyDistribution[0, 1], t]"))
        self.assertEqual("E ^ (I m t - s ^ 2 t ^ 2 / 2)", self.text("CharacteristicFunction[NormalDistribution[m, s], t]"))
        self.assertEqual("Piecewise[{{a (x / b) ^ (-1 + a) / b, x > 0}}, 0]", self.text("HazardFunction[WeibullDistribution[a, b], x]"))
        self.assertEqual("Piecewise[{{E ^ (-(x / b) ^ a), x > 0}}, 1]", self.text("SurvivalFunction[WeibullDistribution[a, b], x]"))
        self.assertEqual("0 ;; Infinity", self.text("DistributionDomain[PoissonDistribution[l]]"))
        self.assertEqual("0 ;; n", self.text("DistributionDomain[BinomialDistribution[n, p]]"))
        self.assertEqual("Interval[{-Infinity, Infinity}]", self.text("DistributionDomain[NormalDistribution[0, 1]]"))
        self.assertEqual("Interval[{a, b}]", self.text("DistributionDomain[UniformDistribution[{a, b}]]"))
        self.assertEqual("Element[m, Reals] ∧ s > 0", self.text("DistributionParameterAssumptions[NormalDistribution[m, s]]"))
        self.assertEqual("True", self.text("DistributionParameterQ[NormalDistribution[0, 1]]"))
        self.assertEqual("False", self.text("DistributionParameterQ[NormalDistribution[0, -1]]"))

    def test_quantiles(self):
        self.assertEqual("ConditionalExpression[m - Sqrt[2] s InverseErfc[2 q], 0 ≤ q ≤ 1]", self.text("InverseCDF[NormalDistribution[m, s], q]"))
        self.assertEqual("-Sqrt[2] InverseErfc[1 / 2]", self.text("Quantile[NormalDistribution[0, 1], 1/4]"))
        self.assertEqual("1.95996", self.text("Quantile[NormalDistribution[0, 1], 0.975]"))
        self.assertEqual("-b Log[2] + m", self.text("Quantile[LaplaceDistribution[m, b], 1/4]"))
        self.assertEqual("1", self.text("Quantile[CauchyDistribution[0, 1], 3/4]"))
        self.assertEqual("0", self.text("Quantile[GeometricDistribution[1/2], 1/2]"))
        self.assertEqual("3", self.text("Quantile[PoissonDistribution[3], 1/2]"))
        self.assertEqual("5", self.text("InverseCDF[BinomialDistribution[10, 1/2], 1/2]"))
        self.assertEqual("ConditionalExpression[Piecewise[{{-Log[1 - q] / l, q < 1}}, Infinity], 0 ≤ q ≤ 1]", self.text("Quantile[ExponentialDistribution[l], q]"))
        self.assertEqual("{2, 3, 4}", self.text("Quantile[{1, 2, 3, 4, 5}, {1/4, 1/2, 3/4}]"))

    def test_default_argument_forms(self):
        self.assertEqual("0", self.text("Mean[NormalDistribution[]]"))
        self.assertEqual("1 / 2", self.text("Mean[UniformDistribution[]]"))
        self.assertEqual("n / 2", self.text("Mean[UniformSumDistribution[n]]"))
        self.assertEqual("(n / (n + (-m + x) ^ 2 / s ^ 2)) ^ (1 / 2 + n / 2) / (Sqrt[n] s Beta[n / 2, 1 / 2])", self.text("PDF[StudentTDistribution[m, s, n], x]"))

    def test_user_symbols_are_not_captured_by_contract_parameters(self):
        self.assertEqual("12", self.text("n = 12; n"))
        self.assertEqual("n p", self.text("Clear[n]; Mean[BinomialDistribution[n, p]]"))
        self.assertEqual("m", self.text("Mean[NormalDistribution[m, s]]"))
        self.assertEqual("1 + m", self.text("Mean[NormalDistribution[m, s]] + 1"))


class SpecialFunctionTests(_Base):
    def test_regularized_gamma_beta(self):
        self.assertEqual("GammaRegularized[2, 0, 3]", self.text("GammaRegularized[2, 0, 3]"))  # kernel keeps the 3-arg exact form
        self.assertEqual(0.80085, round(float(self.text("N[GammaRegularized[2, 0, 3]]")), 5))
        self.assertEqual("4 / E ^ 3", self.text("GammaRegularized[2, 3]"))
        self.assertEqual("11 / 27", self.text("BetaRegularized[1/3, 2, 3]"))
        self.assertAlmostEqual(0.974653, self.num("GammaRegularized[1/2, 0, 2.5]"), places=6)
        self.assertAlmostEqual(1.67834699, self.num("InverseGammaRegularized[2, 0, 1/2]"), places=4)
        self.assertAlmostEqual(0.385728, self.num("InverseBetaRegularized[1/2, 2, 3]"), places=6)
        self.assertAlmostEqual(0.413627, self.num("InverseBetaRegularized[1, -1/2, 3/2, 2]"), places=5)
        self.assertAlmostEqual(0.0339506, self.num("Beta[1/3, 2, 3]"), places=6)

    def test_owen_marcum_hypergeometric_misc(self):
        self.assertAlmostEqual(0.0784682, self.num("OwenT[1, 2]"), places=6)
        self.assertAlmostEqual(0.730988, self.num("MarcumQ[1, 1, 0, 2]"), places=5)
        self.assertAlmostEqual(1.59064, self.num("Hypergeometric0F1Regularized[2, 1]"), places=4)
        self.assertAlmostEqual(4.9348, self.num("HurwitzZeta[2, 1/2]"), places=3)
        self.assertAlmostEqual(6.0, self.num("HurwitzLerchPhi[1/2, -2, 0]"), places=9)
        self.assertAlmostEqual(0.693147, self.num("LogBarnesG[4]"), places=5)
        self.assertEqual("1", self.text("Sinc[0]"))
        self.assertEqual("2 / Pi", self.text("Sinc[Pi/2]"))
        self.assertEqual("20", self.text("FactorialPower[5, 2]"))
        self.assertAlmostEqual(0.476936, self.num("InverseErfc[1/2]"), places=6)
        self.assertAlmostEqual(-2.54264, self.num("ProductLog[-1, -0.2]"), places=4)
        self.assertEqual("15", self.text("5!!"))
        self.assertEqual("48", self.text("6!!"))

    def test_pochhammer_piecewise_erfc_conventions(self):
        self.assertEqual("a (1 + a)", self.text("Pochhammer[a, 2]"))
        self.assertEqual("360", self.text("Pochhammer[3, 4]"))
        self.assertEqual("Pochhammer[a, kk]", self.text("Pochhammer[a, kk]"))
        self.assertEqual("a", self.text("Piecewise[{{a, 2 > 1}}, b]"))
        self.assertEqual("Piecewise[{{2, x > 0}}, 3]", self.text("Piecewise[{{1+1, x > 0}}, 1+2]"))
        self.assertEqual("Piecewise[{{a, 0 ≤ n}}, 0]", self.text("Piecewise[{{a, 0 <= 0 <= n}}, 0]"))
        self.assertEqual("1 / 2", self.text("Integrate[Piecewise[{{x, x > 0}}, 0], {x, -1, 1}]"))
        self.assertEqual("Erfc[-x]", self.text("Erfc[-x]"))
        self.assertEqual("1", self.text("Erfc[0]"))
        self.assertEqual("0.15729920705028513066", self.text("N[Erfc[1], 20]"))


class DerivedDistributionTests(_Base):
    def test_truncated_censored(self):
        self.assertEqual("Piecewise[{{Sqrt[2] E ^ (-x ^ 2 / 2) / Sqrt[Pi], x > 0}}, 0]", self.text("PDF[TruncatedDistribution[{0, Infinity}, NormalDistribution[0, 1]], x]"))
        self.assertEqual("Piecewise[{{Erf[Sqrt[2] x / 2], x > 0}}, 0]", self.text("CDF[TruncatedDistribution[{0, Infinity}, NormalDistribution[0, 1]], x]"))
        self.assertEqual("Sqrt[2] / Sqrt[Pi]", self.text("Mean[TruncatedDistribution[{0, Infinity}, NormalDistribution[0, 1]]]"))
        self.assertEqual("15 / 8", self.text("Mean[TruncatedDistribution[{1, 3}, PoissonDistribution[2]]]"))
        self.assertEqual("Sqrt[2] / (2 Sqrt[Pi])", self.text("Mean[CensoredDistribution[{0, Infinity}, NormalDistribution[0, 1]]]"))

    def test_mixture_transformed_product(self):
        self.assertEqual("1", self.text("Mean[MixtureDistribution[{1, 1}, {NormalDistribution[0, 1], NormalDistribution[2, 1]}]]"))
        self.assertEqual("2", self.text("Variance[MixtureDistribution[{1, 1}, {NormalDistribution[0, 1], NormalDistribution[2, 1]}]]"))
        self.assertEqual("1 / 2", self.text("Probability[x > 0, x \\[Distributed] MixtureDistribution[{1, 1}, {NormalDistribution[-1, 1], NormalDistribution[1, 1]}]]"))
        self.assertEqual("Piecewise[{{Sqrt[2] E ^ (-y / 2) / (2 Sqrt[y] Sqrt[Pi]), y > 0}}, 0]", self.text("PDF[TransformedDistribution[x^2, x \\[Distributed] NormalDistribution[0, 1]], y]"))
        self.assertEqual("1", self.text("Mean[TransformedDistribution[2 x + 1, x \\[Distributed] NormalDistribution[0, 1]]]"))
        self.assertEqual("4", self.text("Variance[TransformedDistribution[2 x + 1, x \\[Distributed] NormalDistribution[0, 1]]]"))
        self.assertEqual("m ^ 2 + s ^ 2", self.text("Mean[TransformedDistribution[x^2, x \\[Distributed] NormalDistribution[m, s]]]"))
        self.assertEqual("{0, 1}", self.text("Mean[ProductDistribution[NormalDistribution[0, 1], ExponentialDistribution[1]]]"))
        self.assertEqual("NegativeBinomialDistribution[a, 1 / (1 + b)]", self.text("ParameterMixtureDistribution[PoissonDistribution[l], l \\[Distributed] GammaDistribution[a, b]]"))
        self.assertEqual("l m", self.text("Mean[CompoundPoissonDistribution[l, NormalDistribution[m, s]]]"))
        self.assertEqual("0", self.text("Mean[OrderDistribution[{NormalDistribution[0, 1], 3}, 2]]"))

    def test_probability_distribution_and_empirical(self):
        self.assertEqual("Piecewise[{{3 x ^ 2, 0 < x < 1}}, 0]", self.text("PDF[ProbabilityDistribution[3 x^2, {x, 0, 1}], x]"))
        self.assertEqual("3 / 4", self.text("Mean[ProbabilityDistribution[3 x^2, {x, 0, 1}]]"))
        self.assertEqual("3 / 80", self.text("Variance[ProbabilityDistribution[3 x^2, {x, 0, 1}]]"))
        self.assertEqual("2", self.text("Mean[ProbabilityDistribution[1/2^k, {k, 1, Infinity, 1}]]"))
        self.assertEqual("5 / 2", self.text("Mean[EmpiricalDistribution[{1, 2, 3, 4}]]"))
        self.assertEqual("5 / 4", self.text("Variance[EmpiricalDistribution[{1, 2, 3, 4}]]"))
        self.assertEqual("1 / 2", self.text("PDF[EmpiricalDistribution[{1, 2, 2, 3}], 2]"))

    def test_multivariate(self):
        self.assertEqual("E ^ (-x ^ 2 / 2 - y ^ 2 / 2) / (2 Pi)", self.text("PDF[MultinormalDistribution[{0, 0}, {{1, 0}, {0, 1}}], {x, y}]"))
        self.assertEqual("{0, 0}", self.text("Mean[MultinormalDistribution[{0, 0}, {{1, 0}, {0, 1}}]]"))
        self.assertEqual("{{1, r}, {r, 1}}", self.text("Covariance[MultinormalDistribution[{0, 0}, {{1, r}, {r, 1}}]]"))
        self.assertEqual("r", self.text("Expectation[x y, {x, y} \\[Distributed] MultinormalDistribution[{0, 0}, {{1, r}, {r, 1}}]]"))
        self.assertEqual("{m1, m2}", self.text("Mean[BinormalDistribution[{m1, m2}, {s1, s2}, r]]"))
        self.assertEqual("{n p1, n p2, n p3}", self.text("Mean[MultinomialDistribution[n, {p1, p2, p3}]]"))
        self.assertEqual("{a1 / (a1 + a2 + a3), a2 / (a1 + a2 + a3)}", self.text("Mean[DirichletDistribution[{a1, a2, a3}]]"))
        self.assertEqual("1", self.text("Mean[MarginalDistribution[MultinormalDistribution[{1, 2}, {{1, 0}, {0, 1}}], 1]]"))
        self.assertEqual("{2, 2}", self.text("RandomVariate[PoissonDistribution[3], {2, 2}] // Dimensions"))
        self.assertEqual("2", self.text("RandomVariate[MultinormalDistribution[{0, 0}, {{1, 0}, {0, 1}}]] // Length"))


class ExpectationProbabilityTests(_Base):
    def test_expectation_from_moments_and_mgf(self):
        self.assertEqual("m ^ 4 + 6 m ^ 2 s ^ 2 + 3 s ^ 4", self.text("Expectation[x^4, x \\[Distributed] NormalDistribution[m, s]]"))
        self.assertEqual("E ^ (m + s ^ 2 / 2)", self.text("Expectation[Exp[x], x \\[Distributed] NormalDistribution[m, s]]"))
        self.assertEqual("n p - n p ^ 2 + n ^ 2 p ^ 2", self.text("Expectation[x^2, x \\[Distributed] BinomialDistribution[n, p]]"))
        self.assertEqual("l ^ 2", self.text("Expectation[x (x - 1), x \\[Distributed] PoissonDistribution[l]]"))
        self.assertEqual("E ^ (l (-1 + t))", self.text("Expectation[t^x, x \\[Distributed] PoissonDistribution[l]]"))
        self.assertEqual("a b ^ 2 + a ^ 2 b ^ 2", self.text("Expectation[x^2, x \\[Distributed] GammaDistribution[a, b]]"))
        self.assertEqual("13", self.text("Expectation[x^3, x \\[Distributed] GeometricDistribution[1/2]]"))
        self.assertEqual("1 / 4", self.text("Expectation[x^3, x \\[Distributed] UniformDistribution[{0, 1}]]"))
        self.assertEqual("2 / Pi", self.text("Expectation[Sin[x], x \\[Distributed] UniformDistribution[{0, Pi}]]"))
        self.assertEqual("Sqrt[2] s / Sqrt[Pi]", self.text("Expectation[Abs[x], x \\[Distributed] NormalDistribution[0, s]]"))
        self.assertEqual("Sqrt[2] / (2 Sqrt[Pi])", self.text("Expectation[Max[x, 0], x \\[Distributed] NormalDistribution[0, 1]]"))
        self.assertEqual("1.", self.text("NExpectation[x^2, x \\[Distributed] NormalDistribution[0, 1]]"))

    def test_probability_from_cdf(self):
        self.assertEqual("(1 - p) ^ n", self.text("Probability[x == 0, x \\[Distributed] BinomialDistribution[n, p]]"))
        self.assertEqual("Piecewise[{{E ^ (-a l), a ≥ 0}}, 1]", self.text("Probability[x > a, x \\[Distributed] ExponentialDistribution[l]]"))
        self.assertEqual("E ^ (-l)", self.text("Probability[x > 1, x \\[Distributed] ExponentialDistribution[l]]"))
        self.assertEqual("E ^ (-2 l) (-1 + E ^ l)", self.text("Probability[1 < x < 2, x \\[Distributed] ExponentialDistribution[l]]"))
        self.assertEqual("1 - Erfc[Sqrt[2]]", self.text("Probability[Abs[x - m] < 2 s, x \\[Distributed] NormalDistribution[m, s]]"))
        self.assertEqual("Erfc[Sqrt[2] / 2] / 2", self.text("Probability[x > m + s, x \\[Distributed] NormalDistribution[m, s]]"))
        # Wolfram: (-1 + E^l - l)/E^l
        self.assertEqual("E ^ (-l) (-1 + E ^ l - l)", self.text("Probability[x >= 2, x \\[Distributed] PoissonDistribution[l]]"))
        self.assertEqual("1 / 4", self.text("Probability[x >= 2, x \\[Distributed] GeometricDistribution[1/2]]"))
        self.assertEqual("0.158655", self.text("NProbability[x > 1, x \\[Distributed] NormalDistribution[0, 1]]"))

    def test_conditioned(self):
        self.assertEqual("Erfc[Sqrt[2] / 2]", self.text("Probability[x > 1 \\[Conditioned] x > 0, x \\[Distributed] NormalDistribution[0, 1]]"))
        self.assertEqual("Sqrt[2] / Sqrt[Pi]", self.text("Expectation[x \\[Conditioned] x > 0, x \\[Distributed] NormalDistribution[0, 1]]"))


class StatisticsTests(_Base):
    def test_descriptive(self):
        self.assertEqual("3 Log[2] / 2", self.text("Simplify[Entropy[{1, 2, 2, 3}]]"))  # Wolfram: -Log[2]/2 + Log[4]
        self.assertEqual("1", self.text("MeanDeviation[{1, 2, 3, 4}]"))
        self.assertEqual("1", self.text("MedianDeviation[{1, 2, 3, 4}]"))
        self.assertEqual("4", self.text("InterquartileRange[{1, 2, 3, 4, 5, 6, 7, 8}]"))
        self.assertEqual("2", self.text("QuartileDeviation[{1, 2, 3, 4, 5, 6, 7, 8}]"))
        self.assertEqual("Sqrt[42] / 3", self.text("RootMeanSquare[{1, 2, 3}]"))  # Wolfram: Sqrt[14/3]
        self.assertEqual("7 / 3", self.text("ContraharmonicMean[{1, 2, 3}]"))
        self.assertEqual("3", self.text("TrimmedMean[{1, 2, 3, 4, 100}, 0.2]"))
        self.assertEqual("3", self.text("WinsorizedMean[{1, 2, 3, 4, 100}, 0.2]"))
        self.assertEqual("{2, 3}", self.text("Commonest[{1, 2, 2, 3, 3}]"))
        self.assertEqual("{-1, 0, 1}", self.text("Standardize[{1, 2, 3}]"))
        self.assertEqual("{0, 1 / 2, 1}", self.text("Rescale[{1, 2, 3}]"))
        self.assertEqual("0", self.text("Rescale[5, {0, 10}, {-1, 1}]"))
        self.assertEqual("{1, 3, 1}", self.text("BinCounts[{1, 2, 2, 3, 5}, {0, 6, 2}]"))
        self.assertEqual("{{1}, {2, 2, 3}, {5}}", self.text("BinLists[{1, 2, 2, 3, 5}, {0, 6, 2}]"))
        self.assertEqual("{{4, 5}, {5, 19 / 3}}", self.text("Covariance[{{1, 2}, {3, 4}, {5, 7}}]"))
        self.assertEqual("2 / 3", self.text("KendallTau[{1, 2, 3, 4}, {1, 3, 2, 4}]"))
        self.assertEqual("4 / 5", self.text("SpearmanRho[{1, 2, 3, 4}, {1, 3, 2, 4}]"))

    def test_likelihood_and_fitting(self):
        self.assertEqual("-1 / 2 - Log[2] - Log[Pi]", self.text("LogLikelihood[NormalDistribution[0, 1], {0, 1}]"))
        self.assertEqual("-3 l + 2 Log[l]", self.text("LogLikelihood[ExponentialDistribution[l], {1, 2}]"))
        self.assertEqual("{m ⇾ 3., s ⇾ 1.41421}", self.text("FindDistributionParameters[{1, 2, 3, 4, 5}, NormalDistribution[m, s]]"))
        self.assertEqual("ExponentialDistribution[0.333333]", self.text("EstimatedDistribution[{1, 2, 3, 4, 5}, ExponentialDistribution[l]]"))

    def test_hypothesis_tests_return_wolfram_p_values(self):
        self.assertAlmostEqual(0.0132356, self.num("TTest[{1, 2, 3, 4, 5}]"), places=6)
        self.assertAlmostEqual(0.2301996, self.num("TTest[{1, 2, 3, 4, 5}, 2]"), places=6)
        self.assertAlmostEqual(0.3465935, self.num("TTest[{{1, 2, 3, 4, 5}, {2, 3, 4, 5, 6}}]"), places=5)
        self.assertAlmostEqual(0.0000220905, self.num("ZTest[{1, 2, 3, 4, 5}]"), places=9)
        self.assertAlmostEqual(0.0625, self.num("SignTest[{1, 2, 3, 4, 5}]"), places=6)
        self.assertAlmostEqual(0.9675002, self.num("ShapiroWilkTest[{1, 2, 3, 4, 5}]"), places=3)  # scipy's Royston approximation
        # Wolfram 0.993723 (its small-sample tables); exact finite-n Kolmogorov distribution gives 0.985778
        self.assertAlmostEqual(0.985778, self.num("KolmogorovSmirnovTest[{0.1, 0.5, 0.9}, UniformDistribution[{0, 1}]]"), places=5)
        self.assertAlmostEqual(0.9970371, self.num("AndersonDarlingTest[{1, 2, 3, 4, 5}, NormalDistribution[3, Sqrt[2]]]"), places=5)
        self.assertAlmostEqual(0.5319484, self.num("PearsonChiSquareTest[{1, 2, 3, 4, 5}, NormalDistribution[3, Sqrt[2]]]"), places=6)
        self.assertAlmostEqual(0.0590582, self.num("SignedRankTest[{1, 2, 3, 4, 5}]"), places=6)
        self.assertAlmostEqual(0.0808554, self.num("VarianceTest[{1, 2, 3, 4, 5}]"), places=6)
        self.assertAlmostEqual(0.2, self.num("IndependenceTest[{1, 2, 3, 4}, {1, 3, 2, 4}]"), places=6)


if __name__ == "__main__":
    unittest.main()
