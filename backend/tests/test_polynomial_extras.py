"""Polynomial / number-theory extras (backend/polynomial_extras.py), checked on
real evaluator output.  Contracts follow Wolfram 15.0.1 (see
wolfram-re-round2/oracle/inputs-polynomial-wolfram.json).
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


class PolynomialQuotientRemainderTests(_Base):
    def test_exact_division(self):
        self.assertEqual("{1 + x + x ^ 2, 0}", self.text("PolynomialQuotientRemainder[x^3 - 1, x - 1, x]"))

    def test_with_remainder(self):
        self.assertEqual("{2 + x, -1 - 4 x}", self.text("PolynomialQuotientRemainder[x^3 + 2 x^2 - 3 x + 1, x^2 + 1, x]"))
        self.assertEqual("{1 + 2 x, 0}", self.text("PolynomialQuotientRemainder[2 x^2 + 3 x + 1, x + 1, x]"))

    def test_symbolic_coefficients(self):
        self.assertEqual("{a + c + x, a c + b + c ^ 2}", self.text("PolynomialQuotientRemainder[x^2 + a x + b, x - c, x]"))

    def test_degree_too_low(self):
        self.assertEqual("{0, 1}", self.text("PolynomialQuotientRemainder[1, x, x]"))

    def test_non_polynomial_is_unevaluated(self):
        self.assertTrue(self.text("PolynomialQuotientRemainder[Sin[x], x, x]").startswith("PolynomialQuotientRemainder["))


class PolynomialExtendedGCDTests(_Base):
    def test_basic(self):
        self.assertEqual("{-1 + x, {-x, 1}}", self.text("PolynomialExtendedGCD[x^2 - 1, x^3 - 1, x]"))
        self.assertEqual("{1 + x, {1 / 2, -1 / 2}}", self.text("PolynomialExtendedGCD[x^2 + 2 x + 1, x^2 - 1, x]"))

    def test_primitive_normalization(self):
        # content is removed from the gcd and the Bezout coefficients follow
        self.assertEqual("{-1 + x, {0, 1 / 4}}", self.text("PolynomialExtendedGCD[2 x^2 - 2, 4 x - 4, x]"))

    def test_coprime(self):
        self.assertEqual("{1, {1, -1}}", self.text("PolynomialExtendedGCD[x - 1, x - 2, x]"))

    def test_bezout_identity(self):
        self.assertEqual("0", self.text(
            "With[{r = PolynomialExtendedGCD[6 x^2 + 5 x - 6, 9 x^2 - 4, x]}, "
            "Expand[r[[1]] - (r[[2, 1]] (6 x^2 + 5 x - 6) + r[[2, 2]] (9 x^2 - 4))]]"))


class SubresultantsTests(_Base):
    def test_principal_subresultant_coefficients(self):
        # {Resultant, psc_1, ..., psc_{n-1}, leading coefficient of the divisor}
        self.assertEqual("{a + b ^ 2, 1}", self.text("Subresultants[x^2 + a, x + b, x]"))
        self.assertEqual("{17, 3}", self.text("Subresultants[2 x^2 + 1, 3 x - 2, x]"))
        self.assertEqual("{4 p ^ 3 + 27 q ^ 2, 6 p, 3}", self.text("Subresultants[x^3 + p x + q, 3 x^2 + p, x]"))

    def test_common_factor_gives_zeros(self):
        self.assertEqual("{0, 1}", self.text("Subresultants[x^3 - 1, x - 1, x]"))
        self.assertEqual("{0, 0, 1}", self.text("Subresultants[x^4 - 1, x^2 - 1, x]"))

    def test_first_element_is_resultant(self):
        self.assertEqual(self.text("Subresultants[x^3 + 2 x - 1, x^2 - 3, x][[1]]"),
                         self.text("Resultant[x^3 + 2 x - 1, x^2 - 3, x]"))


class SymmetricPolynomialTests(_Base):
    def test_elementary(self):
        self.assertEqual("x + y + z", self.text("SymmetricPolynomial[1, {x, y, z}]"))
        self.assertEqual("x y + x z + y z", self.text("SymmetricPolynomial[2, {x, y, z}]"))
        self.assertEqual("x y z", self.text("SymmetricPolynomial[3, {x, y, z}]"))
        self.assertEqual("a b", self.text("SymmetricPolynomial[2, {a, b}]"))

    def test_zeroth_is_one(self):
        self.assertEqual("1", self.text("SymmetricPolynomial[0, {x, y}]"))

    def test_out_of_range_is_unevaluated(self):
        self.assertTrue(self.text("SymmetricPolynomial[3, {x, y}]").startswith("SymmetricPolynomial["))


class SymmetricReductionTests(_Base):
    def test_symmetric_polynomial(self):
        self.assertEqual("{-2 x y + (x + y) ^ 2, 0}", self.text("SymmetricReduction[x^2 + y^2, {x, y}]"))
        self.assertEqual("{(x + y) ^ 3, 0}", self.text("SymmetricReduction[(x + y)^3, {x, y}]"))

    def test_renaming_variables(self):
        self.assertEqual("{s1 ^ 2 - 2 s2, 0}", self.text("SymmetricReduction[x^2 + y^2 + z^2, {x, y, z}, {s1, s2, s3}]"))

    def test_remainder(self):
        self.assertEqual("{1 + x y, 0}", self.text("SymmetricReduction[x y + 1, {x, y}]"))


class NRootsTests(_Base):
    def test_real_roots(self):
        self.assertEqual("x ⩵ -2. ∨ x ⩵ -1. ∨ x ⩵ 1. ∨ x ⩵ 2.", self.text("NRoots[x^4 - 5 x^2 + 4 == 0, x]"))

    def test_complex_roots(self):
        self.assertEqual("x ⩵ -0.5 - 0.866025 I ∨ x ⩵ -0.5 + 0.866025 I", self.text("NRoots[x^2 + x + 1 == 0, x]"))

    def test_equation_form(self):
        self.assertEqual("x ⩵ -2.23607 ∨ x ⩵ 2.23607", self.text("NRoots[x^2 - 5 == 0, x]"))

    def test_polynomial_form(self):
        self.assertEqual("x ⩵ -2.23607 ∨ x ⩵ 2.23607", self.text("NRoots[x^2 - 5, x]"))

    def test_repeated_root(self):
        self.assertEqual("x ⩵ -1. ∨ x ⩵ -1.", self.text("NRoots[x^2 + 2 x + 1 == 0, x]"))


class CountRootsTests(_Base):
    def test_interval(self):
        self.assertEqual("1", self.text("CountRoots[x^2 - 5, {x, 0, 3}]"))
        self.assertEqual("3", self.text("CountRoots[x^3 - 6 x^2 + 11 x - 6, {x, 0, 4}]"))
        self.assertEqual("4", self.text("CountRoots[x^4 - 5 x^2 + 4, {x, -3, 3}]"))
        self.assertEqual("0", self.text("CountRoots[x^2 + 1, {x, -1, 1}]"))

    def test_infinite_intervals(self):
        self.assertEqual("3", self.text("CountRoots[x^3 - x, {x, -Infinity, Infinity}]"))
        self.assertEqual("2", self.text("CountRoots[x^3 - 2 x + 1, {x, 0, Infinity}]"))

    def test_multiplicity_counts(self):
        # Wolfram counts roots with multiplicity
        self.assertEqual("3", self.text("CountRoots[(x - 1)^2 (x - 2), {x, 0, 3}]"))

    def test_endpoints_included(self):
        self.assertEqual("2", self.text("CountRoots[x^2 - 1, {x, -1, 1}]"))
        self.assertEqual("1", self.text("CountRoots[x^2 - 1, {x, -1, 0}]"))


class FrobeniusNumberTests(_Base):
    def test_two_coins(self):
        self.assertEqual("7", self.text("FrobeniusNumber[{3, 5}]"))

    def test_three_coins(self):
        self.assertEqual("11", self.text("FrobeniusNumber[{4, 6, 9}]"))
        self.assertEqual("8", self.text("FrobeniusNumber[{3, 7, 11}]"))
        self.assertEqual("43", self.text("FrobeniusNumber[{6, 9, 20}]"))
        self.assertEqual("9", self.text("FrobeniusNumber[{5, 6, 7}]"))

    def test_not_coprime_is_infinity(self):
        self.assertEqual("Infinity", self.text("FrobeniusNumber[{2, 4}]"))


class FrobeniusSolveTests(_Base):
    def test_enumeration(self):
        self.assertEqual("{{0, 2}, {3, 0}}", self.text("FrobeniusSolve[{2, 3}, 6]"))
        self.assertEqual("{{0, 0, 2}, {1, 1, 1}, {2, 2, 0}, {5, 0, 0}}", self.text("FrobeniusSolve[{2, 3, 5}, 10]"))

    def test_no_solution(self):
        self.assertEqual("{}", self.text("FrobeniusSolve[{3, 5}, 7]"))
        self.assertEqual("{}", self.text("FrobeniusSolve[{2, 4}, 3]"))
        self.assertEqual("{}", self.text("FrobeniusSolve[{2, 3}, -1]"))

    def test_non_integer_target_is_unevaluated(self):
        self.assertTrue(self.text("FrobeniusSolve[{2, 3}, 6.5]").startswith("FrobeniusSolve["))

    def test_max_solutions(self):
        # NB: Wolfram returns the same solution SET prefix semantics ("at most k
        # solutions") but in its own internal order ({{5,0,0},{0,0,2},{1,1,1}});
        # we enumerate lexicographically and take the first k.
        self.assertEqual("{{0, 0, 2}, {1, 1, 1}, {2, 2, 0}}", self.text("FrobeniusSolve[{2, 3, 5}, 10, 3]"))


if __name__ == "__main__":
    unittest.main()
