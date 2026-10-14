"""Group 4 (special functions).  Expected values are what the activated
Wolfram 15.0.1 kernel returns (wolfram-re-round2/oracle/special-wolfram.json,
special-extra-wolfram.txt), rendered in the notebook's text form."""

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

    def evaluate(self, source):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def text(self, source):
        return self.evaluate(source)["text"]

    def num(self, source, places=5):
        # N[..., 12] so that rounding to `places` is not limited by the 6-digit display
        return round(float(self.text("N[" + source + ", 12]")), places)

    def cnum(self, source):
        return complex(self.text("N[" + source + ", 12]").replace(" I", "j").replace(" ", ""))


class NumericCoverageTests(_Base):
    """Heads Mathics 10.0.1 lacked; values from the kernel."""

    def test_error_and_exponential_integrals(self):
        self.assertEqual(1.65043, self.num("Erfi[1]"))
        self.assertEqual(0.53808, self.num("DawsonF[1]"))
        self.assertEqual(1.05725, self.num("SinhIntegral[1]"))
        self.assertEqual(0.83787, self.num("CoshIntegral[1]"))
        self.assertEqual(0.23522, self.num("ScorerGi[1]"))
        self.assertEqual(0.97221, self.num("ScorerHi[1]"))
        self.assertEqual("I Erfi[1]", self.text("Erf[I]"))

    def test_gamma_family(self):
        self.assertEqual("12", self.text("BarnesG[5]"))
        self.assertEqual(0.94757, self.num("BarnesG[2.5]"))
        self.assertEqual("27648", self.text("Hyperfactorial[4]"))
        self.assertEqual("Superfactorial[4]", self.text("Superfactorial[4]"))  # inert in Wolfram
        self.assertEqual("1 / ((-2 + a) (-1 + a))", self.text("Pochhammer[a, -2]"))
        self.assertEqual("-1", self.text("Factorial2[-3]"))
        self.assertEqual("945", self.text("Factorial2[9]"))
        self.assertEqual(199.33317, self.num("Factorial2[15/2]"))
        self.assertEqual("8 / (3 Pi)", self.text("CatalanNumber[1/2]"))
        self.assertEqual("n (-1 + n) / 2", self.text("Binomial[n, 2]"))
        self.assertEqual("1 / 12", self.text("Beta[2, 3]"))
        self.assertEqual("Pi", self.text("Beta[1/2, 1/2]"))
        self.assertEqual("11 / 192", self.text("Beta[1/2, 2, 3]"))
        self.assertEqual("1 - (1 - x) ^ 2", self.text("BetaRegularized[x, 1, 2]"))

    def test_wolfram_keeps_these_inert(self):
        # Mathics' SymPy path would evaluate these; the kernel does not.
        self.assertEqual("Gamma[2, x]", self.text("Gamma[2, x]"))
        self.assertEqual("4 / E ^ 3", self.text("Gamma[2, 3]"))            # positive integer a, numeric z evaluates
        self.assertEqual("79 / (8 Sqrt[E])", self.text("Gamma[4, 1/2]"))
        self.assertEqual("Gamma[1 / 2, 3]", self.text("Gamma[1/2, 3]"))
        self.assertEqual("Gamma[3, 0, 2]", self.text("Gamma[3, 0, 2]"))
        self.assertEqual("GammaRegularized[3, 0, 2]", self.text("GammaRegularized[3, 0, 2]"))
        self.assertEqual("E ^ (-x)", self.text("Gamma[1, x]"))
        self.assertEqual("Gamma[1 / 4] Gamma[3 / 4]", self.text("Gamma[1/4] Gamma[3/4]"))  # reflection only under FullSimplify
        self.assertEqual("Sqrt[2] Pi", self.text("FullSimplify[Gamma[1/4] Gamma[3/4]]"))
        self.assertEqual("PolyGamma[0, 1 / 2]", self.text("PolyGamma[1/2]"))
        self.assertEqual("PolyGamma[2, 1]", self.text("PolyGamma[2, 1]"))
        self.assertEqual("PolyGamma[2, 3]", self.text("PolyGamma[2, 3]"))
        self.assertEqual("Pi ^ 2 / 6", self.text("PolyGamma[1, 1]"))
        self.assertEqual("-5 / 4 + Pi ^ 2 / 6", self.text("PolyGamma[1, 3]"))  # odd order at (half-)integers evaluates
        self.assertEqual("-4 + Pi ^ 2 / 2", self.text("PolyGamma[1, 3/2]"))
        self.assertEqual("-6 + Pi ^ 4 / 15", self.text("PolyGamma[3, 2]"))
        self.assertEqual("PolyGamma[1, 1 / 4]", self.text("PolyGamma[1, 1/4]"))
        self.assertEqual("-EulerGamma", self.text("PolyGamma[1]"))
        self.assertEqual("Tan[Pi / 8]", self.text("Tan[Pi/8]"))
        self.assertEqual("2 - Sqrt[3]", self.text("Tan[Pi/12]"))
        self.assertEqual("ArcSinh[1]", self.text("ArcSinh[1]"))
        self.assertEqual("ArcCosh[2]", self.text("ArcCosh[2]"))
        self.assertEqual("0", self.text("ArcCosh[1]"))
        self.assertEqual("I / 2 Pi", self.text("ArcCosh[0]"))  # kernel InputForm: (I/2)*Pi
        self.assertEqual("HankelH1[0, x]", self.text("HankelH1[0, x]"))
        self.assertEqual("LaguerreL[1 / 2, x]", self.text("LaguerreL[1/2, x]"))
        self.assertEqual("LaguerreL[n, 0]", self.text("LaguerreL[n, 0]"))
        self.assertEqual("EllipticK[1 / 2]", self.text("EllipticK[1/2]"))
        self.assertEqual("EllipticE[1 / 2]", self.text("EllipticE[1/2]"))
        self.assertEqual("StirlingS2[n, 2]", self.text("StirlingS2[n, 2]"))
        self.assertEqual("ChebyshevT[n, Cos[t]]", self.text("ChebyshevT[n, Cos[t]]"))
        self.assertEqual("ChebyshevT[n, 1]", self.text("ChebyshevT[n, 1]"))
        self.assertEqual("Cos[n Pi / 2]", self.text("ChebyshevT[n, 0]"))
        self.assertEqual("LegendreP[n, -1]", self.text("LegendreP[n, -1]"))
        self.assertEqual("LegendreP[n, x]", self.text("LegendreP[n, x]"))
        self.assertEqual("JacobiP[n, a, b, 1]", self.text("JacobiP[n, a, b, 1]"))
        self.assertEqual("SphericalBesselJ[1, x]", self.text("SphericalBesselJ[1, x]"))
        self.assertEqual("Gudermannian[1]", self.text("Gudermannian[1]"))
        self.assertEqual("Haversine[x]", self.text("Haversine[x]"))
        self.assertEqual("QPochhammer[a, q, 3]", self.text("QPochhammer[a, q, 3]"))
        self.assertEqual("PolyLog[2, 2]", self.text("PolyLog[2, 2]"))
        self.assertEqual("BernoulliB[n, 1]", self.text("BernoulliB[n, 1]"))
        self.assertEqual("2 ^ (-n) EulerE[n]", self.text("EulerE[n, 1/2]"))  # = EulerE[n]/2^n (renderer keeps negative symbolic powers)
        self.assertEqual("HermiteH[-1, x]", self.text("HermiteH[-1, x]"))
        self.assertEqual("Hypergeometric2F1[a, b, c, x]", self.text("Hypergeometric2F1[a, b, c, x]"))
        self.assertEqual("Hypergeometric2F1[a, b, c, 1]", self.text("Hypergeometric2F1[a, b, c, 1]"))
        self.assertEqual("a b Hypergeometric2F1[1 + a, 1 + b, 1 + c, x] / c", self.text("D[Hypergeometric2F1[a, b, c, x], x]"))
        self.assertEqual("Sin[x] / x", self.text("Hypergeometric0F1[3/2, -x^2/4]"))
        self.assertEqual("Hypergeometric0F1[2, x]", self.text("Hypergeometric0F1[2, x]"))
        self.assertEqual("x", self.text("Max[x, x]"))
        self.assertEqual("Max[x, y]", self.text("Max[x, y, x]"))
        self.assertEqual("Factorial2[1 / 2]", self.text("Factorial2[1/2]"))
        self.assertEqual("ComplexInfinity", self.text("Factorial2[-2]"))
        self.assertEqual("1 / 3", self.text("Factorial2[-5]"))
        self.assertEqual("-3 x Sqrt[1 - x ^ 2]", self.text("LegendreP[2, 1, x]"))
        self.assertEqual("-15 x (-1 + x ^ 2)", self.text("LegendreP[3, 2, x]"))
        self.assertEqual("-E ^ (-x) (1 - E ^ x)", self.text("MeijerG[{{1}, {}}, {{1}, {0}}, x]"))  # = -((1 - E^x)/E^x)
        self.assertEqual(0.86466, self.num("MeijerG[{{1}, {}}, {{1}, {0}}, 2]"))

    def test_numeric_after_inert(self):
        self.assertEqual(0.93052, self.num("Gamma[2.5, 1.5]"))
        self.assertEqual(0.70316, self.num("PolyGamma[0, 2.5]"))
        self.assertEqual(complex(0.765198, 0.088257), round(self.cnum("HankelH1[0, 1]").real, 6) + 1j * round(self.cnum("HankelH1[0, 1]").imag, 6))
        self.assertEqual(0.88137, self.num("ArcSinh[1]"))
        self.assertEqual(0.21583, self.num("LaguerreL[1/2, 1.3]"))
        self.assertEqual(2.31079, self.num("EllipticPi[1/3, 1/2]"))
        self.assertEqual(1.20680, self.num("EllipticPi[1/3, 1, 1/2]"))
        self.assertEqual(-0.53382, self.num("LegendreQ[1/2, 0.3]"))
        self.assertEqual(0.00388, self.num("PolyLog[2, 3, 1/2]"))
        self.assertEqual(-0.07282, self.num("StieltjesGamma[1]"))
        self.assertEqual(0.54564, self.num("HermiteH[-1, 0.5]"))
        self.assertEqual("{1.30836, 0.654182 + 1.22937 I}", self.text("N[WeierstrassHalfPeriods[{1, 2}]]"))
        self.assertEqual("{1.23680 - 0.811833 I, 1.23680 + 0.811833 I}".replace("1.23680", "1.2368"), self.text("N[WeierstrassHalfPeriods[{-1, -1}]]"))

    def test_elliptic(self):
        self.assertEqual(1.45679, self.num("ArithmeticGeometricMean[1, 2]"))
        self.assertEqual("a", self.text("ArithmeticGeometricMean[a, a]"))
        self.assertEqual(0.72695, self.num("CarlsonRF[1, 2, 3]"))
        self.assertEqual(0.23985, self.num("CarlsonRJ[1, 2, 3, 4]"))
        self.assertEqual("1", self.text("CarlsonRF[1, 1, 1]"))
        self.assertEqual(0.80300, self.num("JacobiSN[1, 1/2]"))
        self.assertEqual(0.59598, self.num("JacobiCN[1, 1/2]"))
        self.assertEqual(0.82316, self.num("JacobiDN[1, 1/2]"))
        self.assertEqual("Sin[u]", self.text("JacobiSN[u, 0]"))
        self.assertEqual("Tanh[u]", self.text("JacobiSN[u, 1]"))
        self.assertEqual("JacobiCN[u, m] JacobiDN[u, m]", self.text("D[JacobiSN[u, m], u]"))
        self.assertEqual("1", self.text("FullSimplify[JacobiSN[u, m]^2 + JacobiCN[u, m]^2]"))
        self.assertEqual("1", self.text("FullSimplify[JacobiDN[u, m]^2 + m JacobiSN[u, m]^2]"))
        self.assertEqual(0.93232, self.num("JacobiAmplitude[1, 1/2]"))
        self.assertEqual(0.13824, self.num("JacobiZeta[1, 1/2]"))   # first argument is the amplitude
        self.assertEqual(0.87228, self.num("JacobiEpsilon[1, 1/2]"))
        self.assertEqual(0.53562, self.num("InverseJacobiSN[1/2, 1/2]"))
        self.assertEqual(2.12894, self.num("EllipticTheta[3, 0, 1/2]"))
        self.assertEqual(1.22568, self.num("EllipticTheta[1, 1, 0.3]"))
        self.assertEqual("E ^ (-Pi)", self.text("EllipticNomeQ[1/2]"))
        self.assertEqual(0.80240, self.num("InverseEllipticNomeQ[0.1]"))
        self.assertEqual(0.88832, self.num("NevilleThetaS[1, 1/2]"))
        self.assertEqual(1.10625, self.num("NevilleThetaN[1, 1/2]"))
        self.assertEqual("(EllipticE[m] - EllipticK[m] (1 - m)) / (2 m (1 - m))", self.text("D[EllipticK[m], m]"))
        self.assertEqual("EllipticK[m]", self.text("EllipticPi[0, m]"))

    def test_weierstrass_and_modular(self):
        self.assertEqual(1.12365, self.num("WeierstrassP[1, {1, 2}]"))
        self.assertEqual(-1.59726, self.num("WeierstrassPPrime[1, {1, 2}]"))
        self.assertEqual(0.96878, self.num("WeierstrassZeta[1, {1, 2}]"))
        self.assertEqual(0.99345, self.num("WeierstrassSigma[1, {1, 2}]"))
        self.assertEqual(1.90163, self.num("InverseWeierstrassP[2, {1, 2}]"))
        self.assertEqual(0.76823, self.num("DedekindEta[I]"))
        self.assertEqual("Gamma[1 / 4] / (2 Pi ^ (3 / 4))", self.text("DedekindEta[I]"))
        self.assertEqual("1", self.text("KleinInvariantJ[I]"))
        self.assertEqual("1 / 2", self.text("ModularLambda[I]"))

    def test_hypergeometric(self):
        self.assertEqual("Cosh[2 Sqrt[x]]", self.text("Hypergeometric0F1[1/2, x]"))
        self.assertEqual("1", self.text("Hypergeometric0F1[b, 0]"))
        self.assertEqual(1.59064, self.num("Hypergeometric0F1[2, 1]"))
        self.assertEqual("(-1 + E ^ x) / x", self.text("Hypergeometric1F1[1, 2, x]"))
        self.assertEqual("-Log[1 - x] / x", self.text("Hypergeometric2F1[1, 1, 2, x]"))
        self.assertEqual("4 (-1 + 2 Log[2])", self.text("Hypergeometric2F1[1, 2, 3, 1/2]"))
        self.assertEqual("1 - 6 x + 9 x ^ 2 - 4 x ^ 3", self.text("Hypergeometric2F1[-3, 2, 1, x]"))
        self.assertEqual(-0.04620, self.num("Hypergeometric1F1[2.5, 1.5, -3.2]"))
        self.assertEqual(0.60653, self.num("WhittakerM[1, 1/2, 1]"))
        self.assertEqual(0.77880, self.num("ParabolicCylinderD[1, 1]"))
        self.assertEqual(1.41340, self.num("AppellF1[1, 1, 1, 2, 1/3, 1/4]"))
        self.assertEqual(0.66178, self.num("CoulombF[0, 1, 2]"))
        self.assertEqual(5.00898, self.num("MittagLefflerE[1/2, 1]"))
        self.assertEqual("E ^ x", self.text("MittagLefflerE[1, x]"))
        self.assertEqual("E ^ (-x)", self.text("MeijerG[{{}, {}}, {{0}, {}}, x]"))
        self.assertEqual("1 + a b / c x + a b (1 + a) (1 + b) / (2 c (1 + c)) x ^ 2 + O[x] ^ 3", self.text("Series[Hypergeometric2F1[a, b, c, x], {x, 0, 2}]"))

    def test_zeta_polylog(self):
        self.assertEqual("Pi ^ 2 / 2", self.text("Zeta[2, 1/2]"))
        self.assertEqual("8 Catalan + Pi ^ 2", self.text("Zeta[2, 1/4]"))
        self.assertEqual("Zeta[s]", self.text("HurwitzZeta[s, 1]"))
        self.assertEqual("-Log[2 Pi] / 2", self.text("Zeta'[0]"))
        self.assertEqual("1 / 12 - Log[Glaisher]", self.text("Zeta'[-1]"))
        self.assertEqual("1", self.text("Limit[(s - 1) Zeta[s], s -> 1]"))
        self.assertEqual("EulerGamma", self.text("Limit[Zeta[s] - 1/(s - 1), s -> 1]"))
        self.assertEqual("1 / (s - 1) + EulerGamma + -StieltjesGamma[1] (s - 1) + O[s - 1] ^ 2", self.text("Series[Zeta[s], {s, 1, 1}]"))
        self.assertEqual("0.5 + 21.022 I", self.text("N[ZetaZero[2]]"))
        self.assertEqual(0.45225, self.num("PrimeZetaP[2]"))
        self.assertEqual(168.35945, self.num("RiemannR[1000]"))
        self.assertEqual("Log[2]", self.text("DirichletEta[1]"))
        self.assertEqual("Pi ^ 2 / 12", self.text("DirichletEta[2]"))
        self.assertEqual("Catalan", self.text("DirichletBeta[2]"))
        self.assertEqual("Pi ^ 3 / 32", self.text("DirichletBeta[3]"))
        self.assertEqual(0.91597, self.num("DirichletBeta[2]"))
        self.assertEqual(0.91597, self.num("DirichletL[4, 2, 2]"))
        self.assertEqual(0.60460, self.num("DirichletL[3, 2, 1]"))
        self.assertEqual("I Catalan - Pi ^ 2 / 48", self.text("PolyLog[2, I]"))
        self.assertEqual("x (1 + x) / (1 - x) ^ 3", self.text("PolyLog[-2, x]"))
        self.assertEqual("-Log[1 - x] / x", self.text("D[PolyLog[2, x], x]"))
        self.assertEqual("-PolyLog[2, x]", self.text("Integrate[Log[1 - x]/x, x]"))
        self.assertEqual("-Log[1 - z] / z", self.text("LerchPhi[z, 1, 1]"))

    def test_orthogonal_polynomials(self):
        self.assertEqual("-3 x Sqrt[1 - x ^ 2]", self.text("LegendreP[2, 1, x]"))
        self.assertEqual("-15 x (-1 + x ^ 2)", self.text("LegendreP[3, 2, x]"))
        self.assertEqual("-3 Sqrt[3] / 4", self.text("LegendreP[2, 1, 1/2]"))
        self.assertEqual("-3 x / 2 + 5 x ^ 3 / 2", self.text("LegendreP[3, x]"))
        self.assertEqual(0.70094, self.num("LegendreP[1/2, 0.3]"))
        self.assertEqual("-1 + x (-Log[1 - x] / 2 + Log[1 + x] / 2)", self.text("LegendreQ[1, x]"))
        self.assertEqual("2 n HermiteH[-1 + n, x]", self.text("D[HermiteH[n, x], x]"))
        self.assertEqual(0.03420, self.num("HermiteH[-3, 1]"))
        self.assertEqual("-LaguerreL[-1 + n, 1, x]", self.text("D[LaguerreL[n, x], x]"))
        self.assertEqual("n ChebyshevU[-1 + n, x]", self.text("D[ChebyshevT[n, x], x]"))
        self.assertEqual("Cos[ArcCos[x] / 2]", self.text("ChebyshevT[1/2, x]"))
        self.assertEqual("2 (-3 x + 4 x ^ 3) / 3", self.text("GegenbauerC[3, x]"))
        self.assertEqual("1 / Sqrt[1 + t ^ 2 - 2 t x]", self.text("Sum[LegendreP[n, x] t^n, {n, 0, Infinity}]"))
        self.assertEqual("r (-2 + 3 r ^ 2)", self.text("ZernikeR[3, 1, r]"))
        self.assertEqual("Cos[t]", self.text("WignerD[{1, 0, 0}, 0, t, 0]"))
        self.assertEqual(0.87758, self.num("WignerD[{1, 0, 0}, 0, 0.5, 0]"))

    def test_mathieu_spheroidal(self):
        self.assertEqual(2.37920, self.num("MathieuCharacteristicA[1, 2]"))
        self.assertEqual(-1.39068, self.num("MathieuCharacteristicB[1, 2]"))
        self.assertEqual("r ^ 2", self.text("MathieuCharacteristicA[r, 0]"))
        self.assertEqual("Cos[Sqrt[a] z]", self.text("MathieuC[a, 0, z]"))
        self.assertEqual(0.81580, self.num("MathieuC[2.3791998804886862, 2, 1]"))
        # non-characteristic a: kernel's complex Floquet normalisation (reverse engineered,
        # see wolfram-re-round2/REPORT.md); agreement ~1e-6
        self.assertEqual((1.0, 0.753124), tuple(round(v, 6) for v in (self.cnum("MathieuCharacteristicExponent[1, 2]").real, self.cnum("MathieuCharacteristicExponent[1, 2]").imag)))
        self.assertEqual(1.57943, self.num("MathieuCharacteristicExponent[3, 2]"))
        c = self.cnum("MathieuC[1, 2, 1]")
        self.assertAlmostEqual(0.38081826, c.real, places=4)
        self.assertAlmostEqual(1.70429659, c.imag, places=4)
        s = self.cnum("MathieuS[1, 2, 1]")
        self.assertAlmostEqual(1.53729588, s.real, places=4)
        self.assertAlmostEqual(-0.34350262, s.imag, places=4)
        s2 = self.cnum("MathieuS[2, -1.5, 1]")
        self.assertAlmostEqual(0.93339425, s2.real, places=4)
        self.assertAlmostEqual(0.69260092, s2.imag, places=4)
        self.assertEqual(1.59308, self.num("SpheroidalEigenvalue[1, 0, 1]"))
        self.assertEqual("6", self.text("SpheroidalEigenvalue[2, 1, 0]"))
        self.assertEqual(0.51751, self.num("SpheroidalPS[1, 0, 1, 0.5]"))
        self.assertEqual(-1.31533, self.num("SpheroidalPS[2, 1, 1, 0.5]"))
        self.assertEqual(0.45604, self.num("SpheroidalS1[1, 0, 1, 2]"))
        # second kind (DLMF 30.8.9 with analytically continued Ferrers Q, verified on 90 kernel values)
        self.assertEqual(-0.56787, self.num("SpheroidalQS[1, 0, 1, 0.5]"))
        self.assertEqual(-1.46476, self.num("SpheroidalQS[1, 1, 1, 0.5]"))
        self.assertEqual(14.04270, self.num("SpheroidalQS[2, 2, 1, 0.9]"))
        self.assertEqual(-0.97919, self.num("SpheroidalS2[1, 1, 1, 1.5]"))
        self.assertEqual(-0.43844, self.num("SpheroidalS2[1, 0, 1, 2]"))
        q = self.cnum("SpheroidalQS[1, 0, 1, 1.5]")
        self.assertAlmostEqual(0.28731, q.real, places=5)
        self.assertAlmostEqual(-1.98653, q.imag, places=5)

    def test_combinatorial_and_q(self):
        self.assertEqual("1 + x ^ 2", self.text("Fibonacci[3, x]"))
        self.assertEqual("3 x + x ^ 3", self.text("LucasL[3, x]"))
        self.assertEqual("-4", self.text("LucasL[-3]"))
        self.assertEqual("-x / (-1 + x + x ^ 2)", self.text("Sum[Fibonacci[n] x^n, {n, 0, Infinity}]"))
        self.assertEqual("(1 + Sqrt[5]) / 2", self.text("Limit[Fibonacci[n + 1]/Fibonacci[n], n -> Infinity]"))
        self.assertEqual("0", self.text("FullSimplify[Fibonacci[n + 1] + Fibonacci[n] - Fibonacci[n + 2]]"))
        self.assertEqual("-115920", self.text("RamanujanTau[10]"))
        self.assertEqual(0.14637, self.num("RamanujanTauL[2]"))
        self.assertEqual(-0.84343, self.num("RamanujanTauZ[10]"))
        self.assertEqual("1 + q", self.text("QGamma[3, q]"))
        self.assertEqual(0.38266, self.num("QPochhammer[1/2, 1/3]"))
        self.assertEqual(0.81005, self.num("QHypergeometricPFQ[{1/2}, {1/3}, 1/4, 1/5]"))
        self.assertEqual("-a / 12 + a ^ 2 / 4 - a x + x ^ 2", self.text("NorlundB[2, a, x]"))
        self.assertEqual("4 a c + 3 b ^ 2", self.text("BellY[4, 2, {a, b, c}]"))
        self.assertEqual("(-1 + 7 ^ (2 k)) / (-1 + 7 ^ k)", self.text("DivisorSigma[k, p] /. p -> 7"))

    def test_piecewise_elementary(self):
        self.assertEqual("1", self.text("UnitBox[1/2]"))
        self.assertEqual("0", self.text("UnitBox[1]"))
        self.assertEqual("1 / 2", self.text("UnitTriangle[1/2]"))
        self.assertEqual("-1", self.text("SquareWave[3/4]"))
        self.assertEqual("1", self.text("TriangleWave[1/4]"))
        self.assertEqual("1 / 2", self.text("SawtoothWave[{0, 2}, 1/4]"))
        self.assertEqual("2", self.text("Clip[3, {0, 2}]"))
        self.assertEqual("a", self.text("Clip[-3, {0, 2}, {a, b}]"))
        self.assertEqual("2", self.text("Ramp[2]"))
        self.assertEqual("-2", self.text("Surd[-8, 3]"))
        self.assertEqual("Surd[x, 3]", self.text("CubeRoot[x]"))
        self.assertEqual("30", self.text("ArcSinDegrees[1/2]"))
        self.assertEqual("1", self.text("Integrate[UnitTriangle[x], {x, -Infinity, Infinity}]"))
        self.assertEqual("Pi", self.text("Integrate[Sinc[x], {x, -Infinity, Infinity}]"))
        self.assertEqual("-Sin[x] / x ^ 2 + Cos[x] / x", self.text("D[Sinc[x], x]"))
        self.assertEqual("DiracDelta[x]", self.text("D[HeavisideTheta[x], x]"))
        self.assertEqual("DiracDelta[x] / 2", self.text("Simplify[DiracDelta[2 x]]"))
        self.assertEqual("5 / 4", self.text("Cosh[Log[2]]"))
        self.assertEqual("y / Sqrt[x ^ 2 + y ^ 2]", self.text("Sin[ArcTan[x, y]]"))
        self.assertEqual("Indeterminate", self.text("ArcTan[0, 0]"))
        self.assertEqual("1.5", self.text("Mod[7.5, 2]"))
        self.assertEqual("Log[x] + Log[y]", self.text("PowerExpand[Log[x y]]"))
        self.assertEqual("x", self.text("Simplify[Sqrt[x^2], x > 0]"))
        self.assertEqual("(-1) ^ n", self.text("Simplify[Cos[n Pi], Element[n, Integers]]"))

    def test_series_of_special_functions(self):
        self.assertEqual("x - x ^ 3 / 18 + x ^ 5 / 600 - x ^ 7 / 35280 + O[x] ^ 8", self.text("Series[SinIntegral[x], {x, 0, 7}]"))
        self.assertEqual("1 - x ^ 2 / 6 + x ^ 4 / 120 - x ^ 6 / 5040 + O[x] ^ 7", self.text("Series[Sinc[x], {x, 0, 6}]"))
        self.assertEqual("EulerGamma + Log[x] - x ^ 2 / 4 + x ^ 4 / 96 + O[x] ^ 5", self.text("Series[CosIntegral[x], {x, 0, 4}]"))
        self.assertEqual("1 - x ^ 2 / 4 + x ^ 4 / 64 - x ^ 6 / 2304 + O[x] ^ 7", self.text("Series[BesselJ[0, x], {x, 0, 6}]"))
        self.assertEqual("Pi / 2 + Pi / 8 m + 9 Pi / 128 m ^ 2 + 25 Pi / 512 m ^ 3 + O[m] ^ 4", self.text("Series[EllipticK[m], {m, 0, 3}]"))
        self.assertEqual("u + (-(1 + m) / 6) u ^ 3 + (1 + 14 m + m ^ 2) / 120 u ^ 5 + O[u] ^ 6", self.text("Series[JacobiSN[u, m], {u, 0, 5}]"))

    def test_bessel_airy(self):
        self.assertEqual("(BesselY[-1 + n, x] - BesselY[1 + n, x]) / 2", self.text("D[BesselY[n, x], x]"))
        self.assertEqual("Sqrt[2] Sin[x] / (Sqrt[x] Sqrt[Pi])", self.text("BesselJ[1/2, x]"))
        self.assertEqual("BesselJ[2, x]", self.text("AngerJ[2, x]"))
        self.assertEqual("1 / 3", self.text("Integrate[AiryAi[x], {x, 0, Infinity}]"))
        self.assertEqual("1 / Pi", self.text("FullSimplify[AiryAi[x] AiryBiPrime[x] - AiryAiPrime[x] AiryBi[x]]"))
        self.assertEqual("x ^ 2 Hypergeometric0F1Regularized[2, -x ^ 2 / 4] / 2", self.text("Integrate[x BesselJ[0, x], x]"))
        self.assertEqual("SinIntegral[t]", self.text("Integrate[Sin[x]/x, {x, 0, t}]"))
        self.assertEqual("E ^ x / x", self.text("D[ExpIntegralEi[x], x]"))
        self.assertEqual("x SinIntegral[x] + Cos[x]", self.text("Integrate[SinIntegral[x], x]"))


if __name__ == "__main__":
    unittest.main()
