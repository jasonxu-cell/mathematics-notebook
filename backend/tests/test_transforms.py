"""Transform builtins (backend/transforms.py), checked on real evaluator output.

Contracts follow Wolfram 15.0.1 (oracle: wolfram-re-round2/oracle/
inputs-transforms-wolfram.json).  Text forms follow the app's text rendering,
which differs cosmetically from Wolfram's InputForm (e.g. Sqrt[2] Sqrt[Pi]
for Sqrt[2 Pi]); the differential report covers algebraic equivalence.
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


class LaplaceTransformTests(_Base):
    def test_table_entries(self):
        self.assertEqual("1 / s", self.text("LaplaceTransform[1, t, s]"))
        self.assertEqual("1 / s ^ 2", self.text("LaplaceTransform[t, t, s]"))
        self.assertEqual("1 / (2 + s)", self.text("LaplaceTransform[E^(-2 t), t, s]"))
        self.assertEqual("1 / (1 + s ^ 2)", self.text("LaplaceTransform[Sin[t], t, s]"))
        self.assertEqual("s / (9 + s ^ 2)", self.text("LaplaceTransform[Cos[3 t], t, s]"))
        self.assertEqual("2 / (1 + s) ^ 3", self.text("LaplaceTransform[t^2 E^(-t), t, s]"))

    def test_dirac_and_unit_step(self):
        self.assertEqual("1", self.text("LaplaceTransform[DiracDelta[t], t, s]"))
        self.assertEqual("E ^ (-s) / s", self.text("LaplaceTransform[UnitStep[t - 1], t, s]"))

    def test_divergent_stays_unevaluated(self):
        self.assertTrue(self.text("LaplaceTransform[Exp[t^2], t, s]").startswith("LaplaceTransform["))


class InverseLaplaceTransformTests(_Base):
    def test_table_entries(self):
        self.assertEqual("1", self.text("InverseLaplaceTransform[1/s, s, t]"))
        self.assertEqual("E ^ (-a t)", self.text("InverseLaplaceTransform[1/(s + a), s, t]"))
        self.assertEqual("Cos[2 t]", self.text("InverseLaplaceTransform[s/(s^2 + 4), s, t]"))
        self.assertEqual("Sin[t]", self.text("InverseLaplaceTransform[1/(s^2 + 1), s, t]"))
        self.assertEqual("t ^ 2 / 2", self.text("InverseLaplaceTransform[1/s^3, s, t]"))
        self.assertEqual("1 - E ^ (-t)", self.text("InverseLaplaceTransform[1/(s (s + 1)), s, t]"))

    def test_shifted_step_keeps_heaviside_theta(self):
        self.assertEqual("HeavisideTheta[-1 + t]", self.text("InverseLaplaceTransform[E^(-s)/s, s, t]"))


class FourierTransformTests(_Base):
    def test_gaussian_and_exp_abs(self):
        self.assertEqual("Sqrt[2] E ^ (-w ^ 2 / 4) / 2", self.text("FourierTransform[Exp[-t^2], t, w]"))
        self.assertEqual("Sqrt[2] / (Sqrt[Pi] (1 + w ^ 2))", self.text("FourierTransform[Exp[-Abs[t]], t, w]"))

    def test_distributions(self):
        self.assertEqual("Sqrt[2] Sqrt[Pi] DiracDelta[w]", self.text("FourierTransform[1, t, w]"))
        self.assertEqual("Sqrt[2] / (2 Sqrt[Pi])", self.text("FourierTransform[DiracDelta[t], t, w]"))
        self.assertEqual("I Sqrt[2] / (w Sqrt[Pi])", self.text("FourierTransform[Sign[t], t, w]"))

    def test_trig_delta_comb(self):
        self.assertEqual("I / 2 Sqrt[2] Sqrt[Pi] (DiracDelta[-1 + w] - DiracDelta[1 + w])",
                         self.text("FourierTransform[Sin[t], t, w]"))

    def test_fourier_parameters(self):
        self.assertEqual("E ^ (-w ^ 2 / 4) Sqrt[Pi]",
                         self.text("FourierTransform[Exp[-t^2], t, w, FourierParameters -> {1, -1}]"))
        self.assertEqual("Sqrt[2] / (Sqrt[Pi] (1 + w ^ 2))",
                         self.text("FourierTransform[Exp[-Abs[t]], t, w, FourierParameters -> {0, -1}]"))


class InverseFourierTransformTests(_Base):
    def test_table_entries(self):
        self.assertEqual("Sqrt[2] E ^ (-t ^ 2 / 4) / 2", self.text("InverseFourierTransform[Exp[-w^2], w, t]"))
        self.assertEqual("Sqrt[2] Sqrt[Pi] DiracDelta[t]", self.text("InverseFourierTransform[1, w, t]"))
        self.assertEqual("Sqrt[2] / (2 Sqrt[Pi])", self.text("InverseFourierTransform[DiracDelta[w], w, t]"))
        self.assertEqual("Sqrt[2] / (Sqrt[Pi] (1 + t ^ 2))", self.text("InverseFourierTransform[Exp[-Abs[w]], w, t]"))

    def test_even_result_uses_abs(self):
        self.assertEqual("Sqrt[2] E ^ (-Abs[t]) Sqrt[Pi] / 2",
                         self.text("InverseFourierTransform[1/(1 + w^2), w, t]"))

    def test_shifted_delta_gives_complex_exponential(self):
        self.assertEqual("E ^ (-I a t)",
                         self.text("InverseFourierTransform[Sqrt[2 Pi] DiracDelta[w - a], w, t]"))


class FourierSinCosTransformTests(_Base):
    def test_cosine_transform(self):
        self.assertEqual("Sqrt[2] / (Sqrt[Pi] (1 + w ^ 2))", self.text("FourierCosTransform[Exp[-t], t, w]"))
        self.assertEqual("Sqrt[2] E ^ (-w ^ 2 / 4) / 2", self.text("FourierCosTransform[Exp[-t^2], t, w]"))
        self.assertEqual("Sqrt[2] Sqrt[Pi] (DiracDelta[-1 + w] + DiracDelta[1 + w]) / 2",
                         self.text("FourierCosTransform[Cos[t], t, w]"))

    def test_sine_transform(self):
        self.assertEqual("Sqrt[2] w / (Sqrt[Pi] (1 + w ^ 2))", self.text("FourierSinTransform[Exp[-t], t, w]"))
        self.assertEqual("Sqrt[2] E ^ (-w ^ 2 / 4) w / 4", self.text("FourierSinTransform[t Exp[-t^2], t, w]"))
        self.assertEqual("Sqrt[2] Sqrt[Pi] Sign[w] / 2", self.text("FourierSinTransform[1/t, t, w]"))


class MellinTransformTests(_Base):
    def test_table_entries(self):
        self.assertEqual("Gamma[s]", self.text("MellinTransform[Exp[-t], t, s]"))
        self.assertEqual("Pi / Sin[s Pi]", self.text("MellinTransform[1/(1 + t), t, s]"))
        self.assertEqual("Gamma[s / 2] / 2", self.text("MellinTransform[Exp[-t^2], t, s]"))
        self.assertEqual("Gamma[a + s]", self.text("MellinTransform[t^a Exp[-t], t, s]"))
        self.assertEqual("Gamma[s] Sin[s Pi / 2]", self.text("MellinTransform[Sin[t], t, s]"))

    def test_unit_step_bounded(self):
        self.assertEqual("-1 / s ^ 2", self.text("MellinTransform[Log[t] UnitStep[1 - t], t, s]"))


class InverseMellinTransformTests(_Base):
    def test_table_entries(self):
        self.assertEqual("E ^ (-t)", self.text("InverseMellinTransform[Gamma[s], s, t]"))
        self.assertEqual("1 / (1 + t)", self.text("InverseMellinTransform[Pi Csc[Pi s], s, t]"))
        self.assertEqual("E ^ (-t ^ 2)", self.text("InverseMellinTransform[Gamma[s/2]/2, s, t]"))
        self.assertEqual("Sin[t]", self.text("InverseMellinTransform[Gamma[s] Sin[Pi s/2], s, t]"))

    def test_heaviside_theta_result(self):
        self.assertEqual("t HeavisideTheta[1 - t]", self.text("InverseMellinTransform[1/(s + 1), s, t]"))


class ConvolveTests(_Base):
    def test_gaussian(self):
        self.assertEqual("Sqrt[2] E ^ (-y ^ 2 / 2) Sqrt[Pi] / 2",
                         self.text("Convolve[Exp[-x^2], Exp[-x^2], x, y]"))

    def test_unit_step_pairs(self):
        self.assertEqual("E ^ (-y) y UnitStep[y]",
                         self.text("Convolve[UnitStep[x] Exp[-x], UnitStep[x] Exp[-x], x, y]"))
        self.assertEqual("-E ^ (-y) UnitStep[y] + UnitStep[y]",
                         self.text("Convolve[UnitStep[x], UnitStep[x] Exp[-x], x, y]"))

    def test_dirac_identity(self):
        self.assertEqual("E ^ (-y ^ 2)", self.text("Convolve[DiracDelta[x], Exp[-x^2], x, y]"))

    def test_exp_abs_via_convolution_theorem(self):
        self.assertEqual("E ^ (-Abs[y]) (1 + Abs[y])",
                         self.text("Convolve[Exp[-Abs[x]], Exp[-Abs[x]], x, y]"))

    def test_divergent_stays_unevaluated(self):
        self.assertTrue(self.text("Convolve[1, 1, x, y]").startswith("Convolve["))


class ZTransformTests(_Base):
    def test_rational_and_exponential(self):
        self.assertEqual("z / (-1 + z)", self.text("ZTransform[1, n, z]"))
        self.assertEqual("-z / (a - z)", self.text("ZTransform[a^n, n, z]"))
        self.assertEqual("z / (-1 + z) ^ 2", self.text("ZTransform[n, n, z]"))
        self.assertEqual("z (1 + z) / (-1 + z) ^ 3", self.text("ZTransform[n^2, n, z]"))
        self.assertEqual("a z / (a - z) ^ 2", self.text("ZTransform[n a^n, n, z]"))
        self.assertEqual("-a z (a + z) / (a - z) ^ 3", self.text("ZTransform[n^2 a^n, n, z]"))

    def test_trig(self):
        self.assertEqual("z (z - Cos[w]) / (1 - 2 z Cos[w] + z ^ 2)", self.text("ZTransform[Cos[w n], n, z]"))
        self.assertEqual("z Sin[w] / (1 - 2 z Cos[w] + z ^ 2)", self.text("ZTransform[Sin[w n], n, z]"))

    def test_linearity_and_delta(self):
        self.assertEqual("z (-1 - z + z ^ 2) / ((-2 + z) (-1 + z) ^ 2)",
                         self.text("ZTransform[2^n + n, n, z]"))
        self.assertEqual("1", self.text("ZTransform[DiscreteDelta[n], n, z]"))


class InverseZTransformTests(_Base):
    def test_table_entries(self):
        self.assertEqual("a ^ n", self.text("InverseZTransform[z/(z - a), z, n]"))
        self.assertEqual("n", self.text("InverseZTransform[z/(z - 1)^2, z, n]"))
        self.assertEqual("n (-1 + n) / 2", self.text("InverseZTransform[z/(z - 1)^3, z, n]"))
        self.assertEqual("-1 + 2 ^ n", self.text("InverseZTransform[z/((z - 1) (z - 2)), z, n]"))

    def test_step_and_kronecker_forms(self):
        self.assertEqual("UnitStep[-1 + n]", self.text("InverseZTransform[1/(z - 1), z, n]"))
        self.assertEqual("KroneckerDelta[1 - n]", self.text("InverseZTransform[1/z, z, n]"))

    def test_complex_poles_give_trig(self):
        self.assertEqual("Sin[n Pi / 2]", self.text("InverseZTransform[z/(z^2 + 1), z, n]"))


if __name__ == "__main__":
    unittest.main()
