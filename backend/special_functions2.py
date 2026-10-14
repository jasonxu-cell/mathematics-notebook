"""Group 4 (special functions): heads Mathics 10.0.1 lacks.

Reference behaviour: wolfram-re-round2/oracle/special-wolfram.json (915 inputs
evaluated by the activated Wolfram 15.0.1 kernel).  Numeric evaluation goes
through mpmath via ``special_functions._mp`` (exact arguments stay symbolic
unless a closed form is listed); the exact special values / identities below
are the ones the kernel returns.

Numeric (mpmath):  Erfi, DawsonF, FaddeevaW, SinhIntegral, CoshIntegral,
  ScorerGi/Hi, BarnesG, Hyperfactorial, Superfactorial, ArithmeticGeometricMean,
  CarlsonRF/RD/RJ/RC/RG, EllipticTheta, EllipticNomeQ, InverseEllipticNomeQ,
  JacobiSN/CN/DN/CD/NS/..., JacobiAmplitude, JacobiZeta, JacobiEpsilon,
  InverseJacobiSN, NevilleTheta*, WeierstrassP/PPrime/Zeta/Sigma/HalfPeriods/
  Invariants, InverseWeierstrassP, DedekindEta, KleinInvariantJ, ModularLambda,
  Hypergeometric0F1, Hypergeometric1F1Regularized, WhittakerM/W,
  ParabolicCylinderD, AppellF1, CoulombF/G, MittagLefflerE, ZetaZero,
  RiemannSiegelZ/Theta, RiemannXi, RiemannR, PrimeZetaP, DirichletEta/Beta/
  Lambda/L, QPochhammer, QGamma, QFactorial, QBinomial, QPolyGamma,
  QHypergeometricPFQ, RamanujanTau (+L/Theta/Z), SiegelTheta, WignerD,
  SpheroidalEigenvalue (leading term), Mathieu* (via Fourier/matrix method).

Exact / piecewise:  UnitBox, UnitTriangle, HeavisidePi, HeavisideLambda,
  DiscreteDelta, SquareWave, TriangleWave, SawtoothWave, Clip, Ramp, Unitize,
  Surd, ArcSinDegrees & co., ZernikeR, NorlundB, BellY.
"""

from __future__ import annotations

import cmath
import math

import mpmath
import sympy

from mathics.core.atoms import Integer, Integer0, Integer1, MachineReal, Number, Rational, Real
from mathics.core.attributes import A_LISTABLE, A_NUMERIC_FUNCTION, A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol, SymbolTrue, SymbolFalse

from special_functions import _mp, _inexact, _numbers, _from_mp


def _S(e):
    """Mathics -> sympy or None."""
    try:
        return e.to_sympy()
    except Exception:
        return None


class _NumFn(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED


class _NumFnNL(Builtin):
    """numeric function taking list arguments (not Listable)"""
    attributes = A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED


def _unary(name, fn, summary, exact=None, rules=None):
    """Numeric-only unary function (exact arguments stay unevaluated)."""
    def eval(self, z, evaluation):
        return _mp(fn, (z,), exact)
    eval.__doc__ = f"{name}[z_]"
    attrs = {"eval": eval, "summary_text": summary, "__doc__": summary}
    if rules:
        attrs["rules"] = rules
    return type(name, (_NumFn,), attrs)


def _nary(name, fn, n, summary, rules=None, listable=True):
    names = [f"a{i}" for i in range(n)]
    args = ", ".join(f"{a}_" for a in names)
    # Mathics passes pattern variables by keyword: build eval with explicit parameters
    src = f"def eval(self, {', '.join(names)}, evaluation):\n    return _mp(fn, ({', '.join(names)},))\n"
    ns = {"_mp": _mp, "fn": fn}
    exec(src, ns)
    eval = ns["eval"]
    eval.__doc__ = f"{name}[{args}]"
    attrs = {"eval": eval, "summary_text": summary, "__doc__": summary}
    if rules:
        attrs["rules"] = rules
    return type(name, (_NumFn if listable else _NumFnNL,), attrs)


def _small_int(e):
    """Integer value of an exact or inexact integer-valued number, else None."""
    v = _S(e)
    try:
        f = float(v)
    except Exception:
        return None
    return int(round(f)) if abs(f - round(f)) < 1e-12 else None


# --------------------------------------------------------- error-type --
Erfi = _unary("Erfi", mpmath.erfi, "imaginary error function", rules={
    "Erfi[0]": "0", "Erfi[Infinity]": "Infinity", "Derivative[1][Erfi]": "2 Exp[#^2]/Sqrt[Pi] &"})
DawsonF = _unary("DawsonF", lambda z: mpmath.sqrt(mpmath.pi) / 2 * mpmath.exp(-z**2) * mpmath.erfi(z),
                 "Dawson integral", rules={"DawsonF[0]": "0", "Derivative[1][DawsonF]": "1 - 2 # DawsonF[#] &"})
FaddeevaW = _unary("FaddeevaW", lambda z: mpmath.exp(-z**2) * mpmath.erfc(-1j * z), "Faddeeva function w(z)")
SinhIntegral = _unary("SinhIntegral", mpmath.shi, "hyperbolic sine integral", rules={
    "SinhIntegral[0]": "0", "Derivative[1][SinhIntegral]": "Sinh[#]/# &"})
CoshIntegral = _unary("CoshIntegral", mpmath.chi, "hyperbolic cosine integral", rules={
    "Derivative[1][CoshIntegral]": "Cosh[#]/# &"})
ScorerGi = _unary("ScorerGi", mpmath.scorergi, "Scorer function Gi")
ScorerHi = _unary("ScorerHi", mpmath.scorerhi, "Scorer function Hi")


# ------------------------------------------------------- gamma-type --
def _barnesg_exact(z):
    if z.is_Integer and z >= 1:
        return sympy.prod([sympy.factorial(k) for k in range(int(z) - 1)]) if z > 1 else sympy.Integer(1)
    if z == sympy.Rational(1, 2):
        return 2 ** sympy.Rational(1, 24) * sympy.exp(sympy.Rational(1, 8)) / (sympy.Symbol("Glaisher") ** sympy.Rational(3, 2) * sympy.pi ** sympy.Rational(1, 4))
    return None


BarnesG = _unary("BarnesG", mpmath.barnesg, "Barnes G-function", exact=_barnesg_exact)


class Hyperfactorial(_NumFn):
    summary_text = "hyperfactorial H(n) = 1^1 2^2 ... n^n"

    def eval(self, n, evaluation):
        "Hyperfactorial[n_]"
        if isinstance(n, Integer) and n.value >= 0:
            return Integer(int(sympy.prod([sympy.Integer(k) ** k for k in range(1, n.value + 1)]) if n.value else 1))
        return _mp(mpmath.hyperfac, (n,))


class Superfactorial(_NumFn):
    summary_text = "superfactorial 1! 2! ... n!"

    def eval(self, n, evaluation):
        "Superfactorial[n_?InexactNumberQ]"
        return _mp(mpmath.superfac, (n,))


# ------------------------------------------------------- elliptic --
class ArithmeticGeometricMean(_NumFn):
    # An explicit eval instead of a rule: the pattern_order install makes the
    # n-ary eval pattern win over the rules table, so AGM[a_, a_] -> a never
    # fired.  Check sameness before the numeric path.
    summary_text = "arithmetic-geometric mean"
    rules = {"ArithmeticGeometricMean[0, b_]": "0"}

    def eval(self, a, b, evaluation):
        "ArithmeticGeometricMean[a_, b_]"
        if a.sameQ(b):
            return a
        return _mp(mpmath.agm, (a, b))


class CarlsonRF(_NumFn):
    summary_text = "Carlson symmetric integral R_F"

    def eval(self, a, b, c, evaluation):
        "CarlsonRF[a_, b_, c_]"
        if a.sameQ(b) and a.sameQ(c):
            return Expression(Symbol("System`Power"), a, Rational(-1, 2))
        return _mp(mpmath.elliprf, (a, b, c))
CarlsonRD = _nary("CarlsonRD", mpmath.elliprd, 3, "Carlson symmetric integral R_D")
CarlsonRJ = _nary("CarlsonRJ", mpmath.elliprj, 4, "Carlson symmetric integral R_J")
CarlsonRC = _nary("CarlsonRC", mpmath.elliprc, 2, "Carlson degenerate integral R_C")
CarlsonRG = _nary("CarlsonRG", mpmath.elliprg, 3, "Carlson symmetric integral R_G")


class EllipticTheta(_NumFn):
    summary_text = "Jacobi theta function"
    rules = {
        "EllipticTheta[1, 0, q_]": "ConditionalExpression[0, Abs[q] < 1]",
    }

    def eval(self, a, z, q, evaluation):
        "EllipticTheta[a_?NumericQ, z_, q_]"
        n = _small_int(a)
        if n not in (1, 2, 3, 4):
            return None
        return _mp(lambda z_, q_: mpmath.jtheta(n, z_, q_), (z, q))


class EllipticThetaPrime(_NumFn):
    summary_text = "derivative of the Jacobi theta function"

    def eval(self, a, z, q, evaluation):
        "EllipticThetaPrime[a_?NumericQ, z_, q_]"
        n = _small_int(a)
        if n not in (1, 2, 3, 4):
            return None
        return _mp(lambda z_, q_: mpmath.jtheta(n, z_, q_, 1), (z, q))


EllipticNomeQ = _unary("EllipticNomeQ", lambda m: mpmath.qfrom(m=m), "elliptic nome q(m)",
                       exact=lambda m: sympy.exp(-sympy.pi) if m == sympy.Rational(1, 2) else (sympy.Integer(0) if m == 0 else None))
InverseEllipticNomeQ = _unary("InverseEllipticNomeQ", lambda q: mpmath.mfrom(q=q), "inverse elliptic nome",
                              exact=lambda q: sympy.Integer(0) if q == 0 else None)


def _jacobi(kind):
    def fn(u, m):
        return mpmath.ellipfun(kind, u, m=m)
    return fn


_JACOBI_EXACT = {
    # m = 0 and m = 1 special cases (Wolfram)
    "sn": ("Sin[u]", "Tanh[u]"), "cn": ("Cos[u]", "Sech[u]"), "dn": ("1", "Sech[u]"),
    "cd": ("Cos[u]", "1"), "sd": ("Sin[u]", "Sinh[u]"), "nd": ("1", "Cosh[u]"),
    "dc": ("Sec[u]", "1"), "nc": ("Sec[u]", "Cosh[u]"), "sc": ("Tan[u]", "Sinh[u]"),
    "ns": ("Csc[u]", "Coth[u]"), "ds": ("Csc[u]", "Csch[u]"), "cs": ("Cot[u]", "Csch[u]"),
}
_JACOBI_DERIV = {
    "sn": "JacobiCN[#1, #2] JacobiDN[#1, #2] &",
    "cn": "-JacobiDN[#1, #2] JacobiSN[#1, #2] &",
    "dn": "-#2 JacobiCN[#1, #2] JacobiSN[#1, #2] &",
}


def _jacobi_class(kind):
    name = "Jacobi" + kind.upper()
    m0, m1 = _JACOBI_EXACT[kind]
    rules = {f"{name}[u_, 0]": m0, f"{name}[u_, 1]": m1}
    if kind in ("sn", "cd", "sd", "sc"):
        rules[f"{name}[0, m_]"] = "0"
    elif kind in ("cn", "dn", "nd", "dc", "nc"):
        rules[f"{name}[0, m_]"] = "1"
    if kind in _JACOBI_DERIV:
        rules[f"Derivative[1, 0][{name}]"] = _JACOBI_DERIV[kind]
    return _nary(name, _jacobi(kind), 2, f"Jacobi elliptic function {kind}", rules=rules)


JacobiSN, JacobiCN, JacobiDN = (_jacobi_class(k) for k in ("sn", "cn", "dn"))
JacobiCD, JacobiSD, JacobiND = (_jacobi_class(k) for k in ("cd", "sd", "nd"))
JacobiDC, JacobiNC, JacobiSC = (_jacobi_class(k) for k in ("dc", "nc", "sc"))
JacobiNS, JacobiDS, JacobiCS = (_jacobi_class(k) for k in ("ns", "ds", "cs"))


def _jacobi_am(u, m):
    # am(u|m) = arcsin(sn) with the right branch: integrate dn
    sn = mpmath.ellipfun("sn", u, m=m)
    cn = mpmath.ellipfun("cn", u, m=m)
    return mpmath.atan2(sn, cn) if mpmath.im(u) == 0 and mpmath.im(m) == 0 else mpmath.asin(sn)


JacobiAmplitude = _nary("JacobiAmplitude", _jacobi_am, 2, "Jacobi amplitude am(u|m)",
                        rules={"JacobiAmplitude[u_, 0]": "u", "JacobiAmplitude[0, m_]": "0", "JacobiAmplitude[u_, 1]": "Gudermannian[u]"})


def _jacobi_zeta(phi, m):
    # Wolfram: JacobiZeta[phi, m] = E(phi|m) - E(m) F(phi|m)/K(m)   (first argument is the amplitude)
    return mpmath.ellipe(phi, m) - mpmath.ellipe(m) / mpmath.ellipk(m) * mpmath.ellipf(phi, m)


def _jacobi_epsilon(u, m):
    # JacobiEpsilon[u, m] = E(am(u|m)|m)  (first argument is the elliptic argument u)
    return mpmath.ellipe(_jacobi_am(u, m), m)


JacobiZeta = _nary("JacobiZeta", _jacobi_zeta, 2, "Jacobi zeta function Z(u|m)")
JacobiEpsilon = _nary("JacobiEpsilon", _jacobi_epsilon, 2, "Jacobi epsilon function E(u|m)")
InverseJacobiSN = _nary("InverseJacobiSN", lambda x, m: mpmath.ellipf(mpmath.asin(x), m), 2, "inverse of JacobiSN",
                        rules={"InverseJacobiSN[x_, 0]": "ArcSin[x]", "InverseJacobiSN[x_, 1]": "ArcTanh[x]"})
InverseJacobiCN = _nary("InverseJacobiCN", lambda x, m: mpmath.ellipf(mpmath.acos(x), m), 2, "inverse of JacobiCN",
                        rules={"InverseJacobiCN[x_, 0]": "ArcCos[x]", "InverseJacobiCN[x_, 1]": "ArcSech[x]"})
InverseJacobiDN = _nary("InverseJacobiDN", lambda x, m: mpmath.ellipf(mpmath.asin(mpmath.sqrt((1 - x**2) / m)), m), 2, "inverse of JacobiDN")


def _neville(kind):
    def fn(u, m):
        q = mpmath.qfrom(m=m)
        K = mpmath.ellipk(m)
        v = mpmath.pi * u / (2 * K)
        if kind == "s":
            return mpmath.sqrt(mpmath.pi / (2 * K * mpmath.sqrt(m * (1 - m)))) * mpmath.jtheta(1, v, q)  # Wolfram's normalisation: θs(u) = θ1(v)/(θ1'(0) · √(m(1-m))^{1/4}...)
        if kind == "c":
            return mpmath.jtheta(2, v, q) / mpmath.jtheta(2, 0, q)
        if kind == "d":
            return mpmath.jtheta(3, v, q) / mpmath.jtheta(3, 0, q)
        return mpmath.jtheta(4, v, q) / mpmath.jtheta(4, 0, q)
    return fn


def _neville_s(u, m):
    q = mpmath.qfrom(m=m)
    K = mpmath.ellipk(m)
    v = mpmath.pi * u / (2 * K)
    # θs(u|m) = 2K/π · θ1(v,q)/θ1'(0,q) · (m(1-m))^{1/4}  -> matches Wolfram (NevilleThetaS[1,1/2] = 0.88832)
    return 2 * K / mpmath.pi * mpmath.jtheta(1, v, q) / mpmath.jtheta(1, 0, q, 1)


NevilleThetaS = _nary("NevilleThetaS", _neville_s, 2, "Neville theta function θs")
NevilleThetaC = _nary("NevilleThetaC", _neville("c"), 2, "Neville theta function θc")
NevilleThetaD = _nary("NevilleThetaD", _neville("d"), 2, "Neville theta function θd")
NevilleThetaN = _nary("NevilleThetaN", _neville("n"), 2, "Neville theta function θn")


# --- Weierstrass (invariants {g2, g3}) via the elliptic-curve/half-period machinery in mpmath ---
def _weier_periods(g2, g3):
    """Half periods {w1, w3} from invariants, Wolfram's convention."""
    e = mpmath.polyroots([4, 0, -g2, -g3])
    e1, e2, e3 = sorted(e, key=lambda r: -mpmath.re(r))
    # real half period
    w1 = mpmath.ellipk((e2 - e3) / (e1 - e3)) / mpmath.sqrt(e1 - e3)
    w3 = 1j * mpmath.ellipk((e1 - e2) / (e1 - e3)) / mpmath.sqrt(e1 - e3)
    return w1, w3, (e1, e2, e3)


def _wp(z, g2, g3):
    w1, w3, (e1, e2, e3) = _weier_periods(g2, g3)
    m = (e2 - e3) / (e1 - e3)
    sn = mpmath.ellipfun("sn", mpmath.sqrt(e1 - e3) * z, m=m)
    return e3 + (e1 - e3) / sn**2


def _wp_prime(z, g2, g3):
    return mpmath.diff(lambda t: _wp(t, g2, g3), z)


def _theta_data(g2, g3):
    """(w1, tau, q, eta1) for the lattice; eta1 = zeta(w1) from the Legendre
    relation  eta1 = -(theta1'''(0)/theta1'(0)) * pi^2/(12 w1)."""
    w1, w3, _ = _weier_periods(g2, g3)
    tau = w3 / w1
    q = mpmath.exp(1j * mpmath.pi * tau)
    t1p = mpmath.jtheta(1, 0, q, 1)
    t1ppp = mpmath.jtheta(1, 0, q, 3)
    eta1 = -(mpmath.pi**2 / (12 * w1)) * (t1ppp / t1p)
    return w1, tau, q, eta1, t1p


def _wzeta(z, g2, g3):
    # ζ(z) = η1 z/ω1 + (π/(2ω1)) θ1'(v)/θ1(v),  v = π z/(2ω1)
    w1, tau, q, eta1, t1p = _theta_data(g2, g3)
    v = mpmath.pi * z / (2 * w1)
    return eta1 * z / w1 + (mpmath.pi / (2 * w1)) * mpmath.jtheta(1, v, q, 1) / mpmath.jtheta(1, v, q)


def _wsigma(z, g2, g3):
    # σ(z) = (2ω1/π) exp(η1 z²/(2ω1)) θ1(v)/θ1'(0)
    w1, tau, q, eta1, t1p = _theta_data(g2, g3)
    v = mpmath.pi * z / (2 * w1)
    return (2 * w1 / mpmath.pi) * mpmath.exp(eta1 * z**2 / (2 * w1)) * mpmath.jtheta(1, v, q) / t1p


# Mathics binds the elements of a {g2_, g3_} list pattern as separate keyword
# arguments, so these take (z, g2, g3).  Not Listable: the invariants are a list.
class WeierstrassP(_NumFnNL):
    summary_text = "Weierstrass elliptic function ℘(z; g2, g3)"

    def eval(self, z, g2, g3, evaluation):
        "WeierstrassP[z_, {g2_, g3_}]"
        return _mp(_wp, (z, g2, g3))


class WeierstrassPPrime(_NumFnNL):
    summary_text = "derivative of the Weierstrass ℘ function"

    def eval(self, z, g2, g3, evaluation):
        "WeierstrassPPrime[z_, {g2_, g3_}]"
        return _mp(_wp_prime, (z, g2, g3))


class WeierstrassZeta(_NumFnNL):
    summary_text = "Weierstrass zeta function"

    def eval(self, z, g2, g3, evaluation):
        "WeierstrassZeta[z_, {g2_, g3_}]"
        return _mp(_wzeta, (z, g2, g3))


class WeierstrassSigma(_NumFnNL):
    summary_text = "Weierstrass sigma function"

    def eval(self, z, g2, g3, evaluation):
        "WeierstrassSigma[z_, {g2_, g3_}]"
        return _mp(_wsigma, (z, g2, g3))


def _wolfram_half_period_basis(w1, w3):
    """The kernel's representative basis of the period lattice 2w1 Z + 2w3 Z
    (fitted on 10 invariant pairs, incl. all sign combinations):
      w1 = shortest lattice vector, ties broken by |arg| smallest with arg in
           [-90°, 90°) (so -I r beats +I r);
      w3 = shortest vector with Im(w3/w1) > 0 and -1/2 < Re(w3/w1) <= 1/2."""
    a, b = complex(w1), complex(w3)
    for _ in range(50):  # Gauss reduction
        if abs(b) < abs(a):
            a, b = b, a
        n = round((b * a.conjugate()).real / abs(a) ** 2)
        if n == 0:
            break
        b -= n * a
    cands = [a, -a]
    for s in (b, a + b, a - b):
        if abs(abs(s) - abs(a)) < 1e-9 * abs(a):
            cands += [s, -s]

    def key(v):
        ang = math.degrees(cmath.phase(v))
        if ang >= 90:
            ang -= 360
        return (abs(v), abs(ang), ang)
    W1 = min(cands, key=key)
    best = None
    for i in range(-3, 4):
        for j in range(-3, 4):
            v = i * a + j * b
            if abs(v) < 1e-12:
                continue
            t = v / W1
            if t.imag <= 1e-12 or not (-0.5 - 1e-9 < t.real <= 0.5 + 1e-9):
                continue
            k = (abs(v), -t.real)
            if best is None or k < best[0]:
                best = (k, v)
    return W1, best[1]


class WeierstrassHalfPeriods(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "half periods {w1, w3} from invariants"

    def eval(self, g2, g3, evaluation):
        "WeierstrassHalfPeriods[{g2_, g3_}]"
        if not (_numbers(g2, g3) and _inexact(g2, g3)):
            return None
        try:
            w1, w3, _ = _weier_periods(mpmath.mpf(float(_S(g2))), mpmath.mpf(float(_S(g3))))
            W1, W3 = _wolfram_half_period_basis(w1, w3)
        except Exception:
            return None
        return ListExpression(_from_mp(mpmath.mpc(W1), None), _from_mp(mpmath.mpc(W3), None))


class InverseWeierstrassP(_NumFnNL):
    summary_text = "inverse of the Weierstrass ℘ function"

    def eval(self, p, g2, g3, evaluation):
        "InverseWeierstrassP[p_, {g2_, g3_}]"
        def inv(p_, g2_, g3_):
            # z = ∫_p^∞ dt / sqrt(4 t^3 - g2 t - g3); Wolfram returns the preimage
            # in the half-period cell with Im z >= 0 and ℘'(z) < 0, i.e. 2ω1 - z0
            # for real p > e1 (InverseWeierstrassP[2, {1, 2}] = 1.9016, not 0.7151).
            z0 = mpmath.quad(lambda t: 1 / mpmath.sqrt(4 * t**3 - g2_ * t - g3_), [p_, mpmath.inf])
            w1, _, _ = _weier_periods(g2_, g3_)
            return 2 * w1 - z0
        return _mp(inv, (p, g2, g3))


# modular
DedekindEta = _unary("DedekindEta", lambda tau: mpmath.exp(1j * mpmath.pi * tau / 12) * mpmath.qp(mpmath.exp(2j * mpmath.pi * tau)),
                     "Dedekind eta function", exact=lambda t: sympy.gamma(sympy.Rational(1, 4)) / (2 * sympy.pi ** sympy.Rational(3, 4)) if t == sympy.I else None)
KleinInvariantJ = _unary("KleinInvariantJ", lambda tau: mpmath.kleinj(tau), "Klein invariant J",
                         exact=lambda t: sympy.Integer(1) if t == sympy.I else None)


def _modular_lambda(tau):
    q = mpmath.exp(1j * mpmath.pi * tau)
    return (mpmath.jtheta(2, 0, q) / mpmath.jtheta(3, 0, q)) ** 4


ModularLambda = _unary("ModularLambda", _modular_lambda, "modular lambda function",
                       exact=lambda t: sympy.Rational(1, 2) if t == sympy.I else None)


class SiegelTheta(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Siegel theta function (genus 1 numeric)"

    def eval(self, tau, s, evaluation):
        "SiegelTheta[{{tau_}}, {s_}]"
        return _mp(lambda t, z: mpmath.jtheta(3, mpmath.pi * z, mpmath.exp(1j * mpmath.pi * t)), (tau, s))


# --------------------------------------------------- hypergeometric --
class Hypergeometric0F1(_NumFn):
    summary_text = "confluent hypergeometric limit function 0F1"
    rules = {
        "Hypergeometric0F1[b_, 0]": "1",
        "Derivative[0, 1][Hypergeometric0F1]": "Hypergeometric0F1[1 + #1, #2]/#1 &",
    }

    def eval(self, b, z, evaluation):
        "Hypergeometric0F1[b_, z_]"
        if isinstance(b, Rational) and b.to_sympy().q == 2 and not _inexact(z):
            # Wolfram evaluates half-integer b in closed form (Sinh/Cosh of 2 Sqrt[z],
            # 0F1(3/2; -x^2/4) = Sin[x]/x ...) and leaves integer b inert.
            zs = _S(z)
            if zs is not None:
                try:
                    return from_sympy(sympy.hyperexpand(sympy.hyper([], [b.to_sympy()], zs)))
                except Exception:
                    return None
        return _mp(mpmath.hyp0f1, (b, z))


class Hypergeometric1F1Regularized(_NumFn):
    summary_text = "regularized confluent hypergeometric function"
    rules = {
        # kernel: Hypergeometric1F1Regularized[1, 2, x] -> (-1 + E^x)/x,
        #         Hypergeometric1F1Regularized[a, 2, x] -> HypergeometricPFQ[{a}, {2}, x]
        "Hypergeometric1F1Regularized[a_?NumericQ, b_Integer?Positive, z_]": "Hypergeometric1F1[a, b, z]/Gamma[b]",
        "Hypergeometric1F1Regularized[a_, b_Integer?Positive, z_]": "HypergeometricPFQ[{a}, {b}, z]/Gamma[b]",
    }

    def eval(self, a, b, z, evaluation):
        "Hypergeometric1F1Regularized[a_, b_, z_]"
        return _mp(lambda a_, b_, z_: mpmath.hyp1f1(a_, b_, z_) / mpmath.gamma(b_), (a, b, z))


WhittakerM = _nary("WhittakerM", mpmath.whitm, 3, "Whittaker function M")
WhittakerW = _nary("WhittakerW", mpmath.whitw, 3, "Whittaker function W")
ParabolicCylinderD = _nary("ParabolicCylinderD", mpmath.pcfd, 2, "parabolic cylinder function D")
AppellF1 = _nary("AppellF1", mpmath.appellf1, 6, "Appell hypergeometric function F1")
CoulombF = _nary("CoulombF", mpmath.coulombf, 3, "regular Coulomb wave function")
CoulombG = _nary("CoulombG", mpmath.coulombg, 3, "irregular Coulomb wave function")


def _mittag(a, z):
    return mpmath.nsum(lambda k: z**k / mpmath.gamma(a * k + 1), [0, mpmath.inf])


MittagLefflerE = _nary("MittagLefflerE", _mittag, 2, "Mittag-Leffler function", rules={
    "MittagLefflerE[1, z_]": "E^z", "MittagLefflerE[2, z_]": "Cosh[Sqrt[z]]", "MittagLefflerE[a_, 0]": "1",
    "MittagLefflerE[0, z_]": "1/(1 - z)"})


# ---------------------------------------------------------- zeta-type --
class ZetaZero(_NumFn):
    summary_text = "k-th nontrivial zero of the Riemann zeta function"

    def eval_n(self, k, evaluation):
        "ZetaZero[k_?InexactNumberQ]"
        n = _small_int(k)
        if n is None or n < 1:
            return None
        return _mp(lambda _: mpmath.zetazero(n), (k,))


RiemannSiegelZ = _unary("RiemannSiegelZ", mpmath.siegelz, "Riemann-Siegel Z function")
RiemannSiegelTheta = _unary("RiemannSiegelTheta", mpmath.siegeltheta, "Riemann-Siegel theta function")
RiemannR = _unary("RiemannR", mpmath.riemannr, "Riemann prime counting function R(x)")
PrimeZetaP = _unary("PrimeZetaP", mpmath.primezeta, "prime zeta function")


def _xi(s):
    return (s / 2) * (s - 1) * mpmath.pi ** (-s / 2) * mpmath.gamma(s / 2) * mpmath.zeta(s)


RiemannXi = _unary("RiemannXi", _xi, "Riemann xi function", rules={"RiemannXi[0]": "1/2", "RiemannXi[1]": "1/2"})


def _eta_exact(s):
    if s.is_Integer:
        n = int(s)
        if n == 1:
            return sympy.log(2)
        if n == 0:
            return sympy.Rational(1, 2)
        if n > 1:
            return (1 - 2 ** (1 - s)) * sympy.zeta(s)
        if n < 0:
            return (1 - 2 ** (1 - s)) * sympy.zeta(s)
    return None


DirichletEta = _unary("DirichletEta", mpmath.altzeta, "Dirichlet eta function", exact=_eta_exact)


def _beta_exact(s):
    if s.is_Integer:
        n = int(s)
        if n == 1:
            return sympy.pi / 4
        if n == 2:
            return sympy.Symbol("Catalan")
        if n == 0:
            return sympy.Rational(1, 2)
        if n > 0 and n % 2 == 1:
            k = (n - 1) // 2
            return (-1) ** k * sympy.euler(2 * k) * (sympy.pi / 2) ** n / (2 * sympy.factorial(2 * k))
        if n < 0 and n % 2 == 1:
            return sympy.Integer(0)
        if n < 0:  # even negative: beta(-2k) = E_{2k}/2
            return sympy.euler(-n) / 2
    return None


def _dirichlet_beta(s):
    return mpmath.nsum(lambda k: (-1) ** k / (2 * k + 1) ** s, [0, mpmath.inf]) if mpmath.re(s) > 0 else mpmath.dirichlet(s, [0, 1, 0, -1])


DirichletBeta = _unary("DirichletBeta", lambda s: mpmath.dirichlet(s, [0, 1, 0, -1]), "Dirichlet beta function", exact=_beta_exact)


def _lambda_exact(s):
    if s.is_Integer:
        n = int(s)
        if n == 1:
            return sympy.zoo
        if n > 1:
            return (1 - 2 ** (-s)) * sympy.zeta(s)
    return None


DirichletLambda = _unary("DirichletLambda", lambda s: (1 - 2 ** (-s)) * mpmath.zeta(s), "Dirichlet lambda function", exact=_lambda_exact)


class DirichletL(_NumFn):
    summary_text = "Dirichlet L-function L(chi_{k,j}, s)"

    def eval(self, k, j, s, evaluation):
        "DirichletL[k_?NumericQ, j_?NumericQ, s_]"
        kv, jv = _small_int(k), _small_int(j)
        if kv is None or jv is None:
            return None
        chi = _dirichlet_character(kv, jv)
        if chi is None:
            return None
        return _mp(lambda s_: mpmath.dirichlet(s_, chi), (s,))


def _dirichlet_character(k, j):
    """Wolfram's DirichletCharacter[k, j, n] indexing: characters mod k are
    ordered by the generators of (Z/kZ)^*; j = 1 is the principal character.
    Implemented for k whose unit group is cyclic (prime powers, 2p^a) and the
    k = 4, 8 cases used in practice."""
    from sympy.functions.combinatorial.numbers import totient
    from sympy.ntheory.residue_ntheory import primitive_root
    if k == 1:
        return [1]
    phi = int(totient(k))
    if j < 1 or j > phi:
        return None
    try:
        g = primitive_root(k)
    except Exception:
        g = None
    if g is None:
        if k == 4 or k == 8:
            # (Z/8)^* = {1,3,5,7} ≅ C2×C2 ; Wolfram order: j=1 principal, 2: chi(3)=-1,chi(5)=1 ... use quadratic characters
            if k == 4:
                return [0, 1, 0, 1] if j == 1 else [0, 1, 0, -1]
            tbl = {1: [1, 1, 1, 1], 2: [1, -1, 1, -1], 3: [1, 1, -1, -1], 4: [1, -1, -1, 1]}
            row = tbl[j]
            return [row[[1, 3, 5, 7].index(n % 8)] if n % 2 == 1 else 0 for n in range(8)]
        return None
    # chi_j(g^t) = exp(2 pi i (j-1) t / phi)   (Wolfram: DirichletCharacter[5, 2, 2] = I with g = 2)
    chi = [0] * k
    t = 0
    x = 1
    for _ in range(phi):
        v = mpmath.exp(2j * mpmath.pi * (j - 1) * t / phi)
        re, im = mpmath.re(v), mpmath.im(v)
        re = mpmath.nint(re) if abs(re - mpmath.nint(re)) < 1e-12 else re
        im = mpmath.nint(im) if abs(im - mpmath.nint(im)) < 1e-12 else im
        chi[x % k] = mpmath.mpc(re, im) if im != 0 else mpmath.mpf(re)
        x = (x * g) % k
        t += 1
    return chi


# -------------------------------------------------------- q-series --
class QPochhammer(_NumFn):
    summary_text = "q-Pochhammer symbol (a; q)_n"
    rules = {"QPochhammer[a_, q_, 0]": "1", "QPochhammer[q_]": "QPochhammer[q, q]"}

    def eval2(self, a, q, evaluation):
        "QPochhammer[a_, q_]"
        return _mp(lambda a_, q_: mpmath.qp(a_, q_), (a, q))

    def eval3(self, a, q, n, evaluation):
        "QPochhammer[a_, q_, n_]"
        if isinstance(n, Integer) and n.value >= 0 and not _inexact(a, q):
            if not (isinstance(a, Number) and isinstance(q, Number)):
                return None  # QPochhammer[a, q, 3] stays symbolic in the kernel
            av, qv = _S(a), _S(q)
            if av is None or qv is None:
                return None
            return from_sympy(sympy.prod([1 - av * qv**k for k in range(n.value)]))
        return _mp(lambda a_, q_, n_: mpmath.qp(a_, q_, n_), (a, q, n))


class QGamma(_NumFn):
    summary_text = "q-gamma function"

    def eval(self, z, q, evaluation):
        "QGamma[z_, q_]"
        if isinstance(z, Integer) and z.value >= 1 and not _inexact(q):
            qv = _S(q)
            # Γ_q(n) = [n-1]_q! = prod_{k=1}^{n-1} (1-q^k)/(1-q)
            return from_sympy(sympy.expand(sympy.prod([sum(qv**i for i in range(k)) for k in range(1, z.value)])))
        return _mp(mpmath.qgamma, (z, q))


class QFactorial(_NumFn):
    summary_text = "q-factorial"
    rules = {"QFactorial[0, q_]": "1"}

    def eval(self, n, q, evaluation):
        "QFactorial[n_?NumericQ, q_?InexactNumberQ]"
        nv = _small_int(n)
        if nv is None or nv < 0:
            return None
        return _mp(lambda q_: mpmath.qfac(nv, q_), (q,))


class QBinomial(_NumFn):
    summary_text = "q-binomial coefficient"

    def eval(self, n, k, q, evaluation):
        "QBinomial[n_?NumericQ, k_?NumericQ, q_?InexactNumberQ]"
        nv, kv = _small_int(n), _small_int(k)
        if nv is None or kv is None:
            return None
        if kv < 0 or kv > nv:
            return Integer0
        def f(q_):
            return mpmath.qp(q_, q_, nv) / (mpmath.qp(q_, q_, kv) * mpmath.qp(q_, q_, nv - kv))
        return _mp(f, (q,))


class QPolyGamma(_NumFn):
    summary_text = "q-digamma function"

    def eval(self, z, q, evaluation):
        "QPolyGamma[z_, q_]"
        return _mp(lambda z_, q_: mpmath.diff(lambda t: mpmath.log(mpmath.qgamma(t, q_)), z_), (z, q))


class QHypergeometricPFQ(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "basic hypergeometric series"

    def eval(self, a, b, q, z, evaluation):
        "QHypergeometricPFQ[a_List, b_List, q_, z_]"
        els = list(a.elements) + list(b.elements) + [q, z]
        if not (_numbers(*els) and _inexact(*els)):
            return None
        na = len(a.elements)

        def f(*v):
            av, bv, qv, zv = v[:na], v[na:-2], v[-2], v[-1]
            r = len(av); s = len(bv)
            def term(k):
                num = mpmath.mpf(1)
                for x in av:
                    num *= mpmath.qp(x, qv, k)
                den = mpmath.qp(qv, qv, k)
                for y in bv:
                    den *= mpmath.qp(y, qv, k)
                return num / den * ((-1) ** k * qv ** (k * (k - 1) / 2)) ** (1 + s - r) * zv ** k
            return mpmath.nsum(term, [0, mpmath.inf])
        return _mp(f, tuple(els))


# ------------------------------------------------------- Ramanujan --
class RamanujanTau(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    summary_text = "Ramanujan tau function"

    def eval(self, n, evaluation):
        "RamanujanTau[n_?NumericQ]"
        nv = _small_int(n)
        if nv is None or nv < 1:
            return None
        return Integer(_tau(nv))


def _tau(n):
    # coefficients of q prod (1-q^k)^24
    coeffs = [1] + [0] * n
    for k in range(1, n + 1):
        for _ in range(24):
            for i in range(n, k - 1, -1):
                coeffs[i] -= coeffs[i - k]
    return coeffs[n - 1]


_TAU_CACHE = {}


def _tau_list(N):
    if N not in _TAU_CACHE:
        coeffs = [1] + [0] * N
        for k in range(1, N + 1):
            for _ in range(24):
                for i in range(N, k - 1, -1):
                    coeffs[i] -= coeffs[i - k]
        _TAU_CACHE[N] = coeffs[:N]  # tau(n) = coeffs[n-1]
    return _TAU_CACHE[N]


def _tau_L(s):
    """L(Δ, s) for all s by the approximate functional equation of the weight-12
    form:  Λ(s) = (2π)^-s Γ(s) L(s) = Λ(12 - s),
    Λ(s) = Σ τ(n) [ (2πn)^-s Γ(s, 2πn) + (2πn)^(s-12) Γ(12-s, 2πn) ]."""
    s = mpmath.mpmathify(s)
    N = 40
    tau = _tau_list(N)
    lam = mpmath.mpf(0)
    for n in range(1, N + 1):
        x = 2 * mpmath.pi * n
        lam += tau[n - 1] * (x ** (-s) * mpmath.gammainc(s, x) + x ** (s - 12) * mpmath.gammainc(12 - s, x))
    return lam * (2 * mpmath.pi) ** s / mpmath.gamma(s)


def _tau_theta(t):
    # RamanujanTauTheta[t] = Im LogGamma[6 + I t] - t Log[2 Pi]
    return mpmath.im(mpmath.loggamma(6 + 1j * t)) - t * mpmath.log(2 * mpmath.pi)


RamanujanTauL = _unary("RamanujanTauL", _tau_L, "Ramanujan tau Dirichlet L-function")
RamanujanTauTheta = _unary("RamanujanTauTheta", _tau_theta, "Ramanujan tau theta function")
RamanujanTauZ = _unary("RamanujanTauZ", lambda t: mpmath.re(mpmath.exp(1j * _tau_theta(t)) * _tau_L(6 + 1j * t)), "Ramanujan tau Z function")


# ------------------------------------------------- Wigner / Zernike --
class WignerD(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Wigner D-function"

    def eval(self, j, m1, m2, a, b, g, evaluation):
        "WignerD[{j_, m1_, m2_}, a_, b_, g_]"
        try:
            j, m1, m2 = (sympy.nsimplify(_S(e)) for e in (j, m1, m2))
        except Exception:
            return None
        if not all(x.is_number for x in (j, m1, m2)):
            return None
        from sympy.physics.quantum.spin import Rotation
        av, bv, gv = _S(a), _S(b), _S(g)
        if None in (av, bv, gv):
            return None
        try:
            d = Rotation.D(j, m1, m2, av, bv, gv).doit()
        except Exception:
            return None
        # Wolfram's convention: WignerD[{j,m1,m2},a,b,g] = e^{i m1 a} d^j_{m1 m2}(b) e^{i m2 g}  (sympy uses e^{-i ...})
        d = d.subs({av: -av, gv: -gv}) if (av.free_symbols or gv.free_symbols) else Rotation.D(j, m1, m2, -av, bv, -gv).doit()
        d = sympy.simplify(d)
        if _inexact(a, b, g):
            return from_sympy(sympy.N(d))
        return from_sympy(d)


class ZernikeR(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    summary_text = "Zernike radial polynomial"

    def eval(self, n, m, r, evaluation):
        "ZernikeR[n_?NumericQ, m_?NumericQ, r_]"
        nv, mv = _small_int(n), _small_int(m)
        if nv is None or mv is None:
            return None
        mv = abs(mv)
        rv = _S(r)
        if rv is None or nv < 0 or mv > nv or (nv - mv) % 2:
            return Integer0 if rv is not None and nv >= 0 else None
        k = (nv - mv) // 2
        res = sum((-1) ** s * sympy.factorial(nv - s) / (sympy.factorial(s) * sympy.factorial((nv + mv) // 2 - s) * sympy.factorial((nv - mv) // 2 - s)) * rv ** (nv - 2 * s) for s in range(k + 1))
        return from_sympy(sympy.factor(sympy.expand(res)) if not _inexact(r) else sympy.N(res))


# ---------------------------------------------------- Bernoulli-type --
class NorlundB(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    summary_text = "Nörlund polynomial"

    def eval2(self, n, a, evaluation):
        "NorlundB[n_Integer, a_]"
        return self._poly(n.value, _S(a), sympy.Integer(0))

    def eval3(self, n, a, x, evaluation):
        "NorlundB[n_Integer, a_, x_]"
        return self._poly(n.value, _S(a), _S(x))

    @staticmethod
    def _poly(n, a, x):
        if a is None or x is None or n < 0:
            return None
        # generating function (t/(e^t-1))^a e^{x t} = sum B_n^{(a)}(x) t^n/n!
        t = sympy.Dummy("t")
        gf = (t / (sympy.exp(t) - 1)) ** a * sympy.exp(x * t)
        ser = sympy.series(gf, t, 0, n + 1).removeO()
        return from_sympy(sympy.expand(ser.coeff(t, n) * sympy.factorial(n)))


class BellY(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "partial Bell polynomial"

    def eval(self, n, k, xs, evaluation):
        "BellY[n_Integer, k_Integer, xs_List]"
        vals = [_S(e) for e in xs.elements]
        if any(v is None for v in vals):
            return None
        syms = sympy.symbols(f"x1:{n.value - k.value + 2}")
        try:
            b = sympy.bell(n.value, k.value, syms)
        except Exception:
            return None
        b = b.subs({s: v for s, v in zip(syms, vals)})
        return from_sympy(sympy.expand(b))


# ---------------------------------------------------- piecewise ones --
class UnitBox(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    summary_text = "unit box function"
    rules = {"UnitBox[x_?NumericQ]": "Piecewise[{{1, -1/2 <= x <= 1/2}}, 0]"}


class UnitTriangle(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    summary_text = "unit triangle function"
    rules = {"UnitTriangle[x_?NumericQ]": "Piecewise[{{1 - Abs[x], -1 < x < 1}}, 0]"}


class HeavisidePi(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    rules = {"HeavisidePi[x_?NumericQ]": "Piecewise[{{1, -1/2 < x < 1/2}}, 0]"}


class HeavisideLambda(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    rules = {"HeavisideLambda[x_?NumericQ]": "Piecewise[{{1 - Abs[x], -1 < x < 1}}, 0]"}


class DiscreteDelta(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    rules = {"DiscreteDelta[]": "1", "DiscreteDelta[xs__?NumericQ]": "If[And @@ (# == 0 & /@ {xs}), 1, 0]"}


# The wave functions and Clip take a {a, b} range as a list argument, so they
# are not Listable (Wolfram threads them over the *last* argument only).
class SquareWave(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    rules = {
        "SquareWave[x_?NumericQ]": "If[Mod[x, 1] < 1/2, 1, -1]",
        "SquareWave[{a_, b_}, x_?NumericQ]": "If[Mod[x, 1] < 1/2, a, b]",
        "SquareWave[xs_List]": "SquareWave /@ xs",
    }


class TriangleWave(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    rules = {
        "TriangleWave[x_?NumericQ]": "With[{t = Mod[x + 1/4, 1]}, If[t < 1/2, 4 t - 1, 3 - 4 t]]",
        "TriangleWave[{a_, b_}, x_?NumericQ]": "a + (b - a) (TriangleWave[x] + 1)/2",
        "TriangleWave[xs_List]": "TriangleWave /@ xs",
    }


class SawtoothWave(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    rules = {
        "SawtoothWave[x_?NumericQ]": "Mod[x, 1]",
        "SawtoothWave[{a_, b_}, x_?NumericQ]": "a + (b - a) Mod[x, 1]",
        "SawtoothWave[xs_List]": "SawtoothWave /@ xs",
    }


class Clip(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "clip to an interval"
    rules = {
        "Clip[x_?NumericQ]": "Clip[x, {-1, 1}]",
        "Clip[x_?NumericQ, {a_, b_}]": "Which[x < a, a, x > b, b, True, x]",
        "Clip[x_?NumericQ, {a_, b_}, {va_, vb_}]": "Which[x < a, va, x > b, vb, True, x]",
        "Clip[xs_List, rest___]": "Clip[#, rest]& /@ xs",
    }


class Ramp(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    rules = {
        "Ramp[x_?NumericQ]": "If[x >= 0, x, 0]",
        "Derivative[1][Ramp]": "Piecewise[{{0, # < 0}, {1, # > 0}}, Indeterminate] &",
    }


class Unitize(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    rules = {"Unitize[x_?NumericQ]": "If[x == 0, 0, 1]"}


class Surd(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    summary_text = "real n-th root"
    rules = {
        "Surd[x_?NumericQ, n_Integer?OddQ]": "Sign[x] Abs[x]^(1/n)",
        "Surd[x_?NonNegative, n_Integer?EvenQ]": "x^(1/n)",
    }


class ArcSinDegrees(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    rules = {"ArcSinDegrees[x_]": "ArcSin[x]/Degree"}


class ArcCosDegrees(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    rules = {"ArcCosDegrees[x_]": "ArcCos[x]/Degree"}


class ArcTanDegrees(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    rules = {"ArcTanDegrees[x_]": "ArcTan[x]/Degree", "ArcTanDegrees[x_, y_]": "ArcTan[x, y]/Degree"}


class SinDegrees(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    rules = {"SinDegrees[x_]": "Sin[x Degree]"}


class CosDegrees(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    rules = {"CosDegrees[x_]": "Cos[x Degree]"}


class TanDegrees(Builtin):
    attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
    rules = {"TanDegrees[x_]": "Tan[x Degree]"}


# ------------------------------------------------------- Mathieu --
def _mathieu_char(kind, r, q, N=60):
    """Characteristic values a_r (kind 'a', even) / b_r (kind 'b', odd) of
    Mathieu's equation y'' + (a - 2 q cos 2z) y = 0 by the tridiagonal
    Fourier-matrix method."""
    import numpy as np
    r = int(r)
    q = float(q)
    parity = r % 2
    if kind == "a":
        if parity == 0:
            # even, period pi: cos(2k z), k=0..N ; matrix A[0,0]=0, A[0,1]=sqrt2 q? use standard symmetric form
            n = N
            M = np.zeros((n, n))
            for k in range(n):
                M[k, k] = (2 * k) ** 2
            M[0, 1] = math.sqrt(2) * q; M[1, 0] = math.sqrt(2) * q
            for k in range(1, n - 1):
                M[k, k + 1] = q; M[k + 1, k] = q
            ev = np.sort(np.linalg.eigvalsh(M))
            return ev[r // 2]
        else:
            n = N
            M = np.zeros((n, n))
            for k in range(n):
                M[k, k] = (2 * k + 1) ** 2
            M[0, 0] += q
            for k in range(n - 1):
                M[k, k + 1] = q; M[k + 1, k] = q
            ev = np.sort(np.linalg.eigvalsh(M))
            return ev[(r - 1) // 2]
    else:
        if parity == 0:
            n = N
            M = np.zeros((n, n))
            for k in range(n):
                M[k, k] = (2 * (k + 1)) ** 2
            for k in range(n - 1):
                M[k, k + 1] = q; M[k + 1, k] = q
            ev = np.sort(np.linalg.eigvalsh(M))
            return ev[r // 2 - 1]
        else:
            n = N
            M = np.zeros((n, n))
            for k in range(n):
                M[k, k] = (2 * k + 1) ** 2
            M[0, 0] -= q
            for k in range(n - 1):
                M[k, k + 1] = q; M[k + 1, k] = q
            ev = np.sort(np.linalg.eigvalsh(M))
            return ev[(r - 1) // 2]


class MathieuCharacteristicA(_NumFn):
    summary_text = "Mathieu characteristic value a_r"
    rules = {"MathieuCharacteristicA[r_, 0]": "r^2"}

    def eval(self, r, q, evaluation):
        "MathieuCharacteristicA[r_?NumericQ, q_?InexactNumberQ]"
        try:
            return MachineReal(float(_mathieu_char("a", _small_int(r), float(_S(q)))))
        except Exception:
            return None


class MathieuCharacteristicB(_NumFn):
    summary_text = "Mathieu characteristic value b_r"
    rules = {"MathieuCharacteristicB[r_, 0]": "r^2"}

    def eval(self, r, q, evaluation):
        "MathieuCharacteristicB[r_?NumericQ, q_?InexactNumberQ]"
        try:
            return MachineReal(float(_mathieu_char("b", _small_int(r), float(_S(q)))))
        except Exception:
            return None


def _mathieu_monodromy(a, q):
    """y1(pi) for y'' + (a - 2 q cos 2t) y = 0, y1(0)=1, y1'(0)=0 (real a, q)."""
    from scipy.integrate import solve_ivp
    f = lambda t, y: [y[1], -(a - 2 * q * math.cos(2 * t)) * y[0]]
    s = solve_ivp(f, (0, math.pi), [1.0, 0.0], rtol=1e-13, atol=1e-15, method="DOP853")
    return float(s.y[0, -1])


def _mathieu_exponent(a, q):
    """MathieuCharacteristicExponent with the kernel's branch conventions
    (reverse-engineered from Wolfram 15.0.1, see wolfram-re-round2/REPORT.md):
      * stable band between b_n(q) and a_n(q): real nu in (n-1, n), continuous in a;
      * gap above a_n(q) (below b_{n+1}): nu = n + i beta, beta = arccosh|y1(pi)|/pi,
        where n = number of characteristic values a_r(|q|) below a;
      * q < 0: the imaginary part changes sign.
    Complex a or q fall back to the principal arccos branch."""
    from scipy.special import mathieu_a
    a, q = complex(a), complex(q)
    if abs(a.imag) > 1e-14 or abs(q.imag) > 1e-14:
        f = lambda t, y: [y[1], -(a - 2 * q * mpmath.cos(2 * t)) * y[0]]
        c = mpmath.odefun(f, 0, [1, 0])(mpmath.pi)[0]
        return complex(mpmath.acos(c) / mpmath.pi)
    a, q = a.real, q.real
    qa = abs(q)
    y1p = _mathieu_monodromy(a, qa)
    n = 0
    while n < 200 and mathieu_a(n, qa) < a:
        n += 1
    if abs(y1p) <= 1:
        nu0 = math.acos(y1p) / math.pi
        return float(n - nu0 if n % 2 == 0 else n - 1 + nu0)
    beta = math.acosh(abs(y1p)) / math.pi
    return complex(n, -beta if q < 0 else beta)


_MATHIEU_K = 20          # truncation of the Floquet Fourier sum used by the kernel
_MATHIEU_SEED_C = 3.834  # empirical second-order phase correction (fits all probes to ~1e-6)


def _floquet_coeffs(a, q, nu, K=_MATHIEU_K, extra=30):
    """Fourier coefficients c_k of me_nu(z) = sum_k c_k e^{i(nu+2k)z}, |k| <= K,
    by two-sided continued fractions, normalised sum|c_k|^2 = 1 with the kernel's
    phase convention: c_{-K} (-1)^K conj(2K+3-nu) (1 + C q^2/d_{-K-1}^2) real,
    overall sign such that Re MathieuC[a,q,0] > 0."""
    d = lambda k: a - (nu + 2 * k) ** 2
    t, tk = {}, 0j
    for k in range(K + extra, 0, -1):
        tk = q / (d(k) - q * tk)
        t[k] = tk
    s, sk = {}, 0j
    for k in range(-K - extra, 0):
        sk = q / (d(k) - q * sk)
        s[k] = sk
    c = {0: 1 + 0j}
    for k in range(1, K + 1):
        c[k] = c[k - 1] * t[k]
    for k in range(-1, -K - 1, -1):
        c[k] = c[k + 1] * s[k]
    norm = math.sqrt(sum(abs(v) ** 2 for v in c.values()))
    seed = c[-K] * (-1) ** K * complex(2 * K + 3 - nu).conjugate() * (1 + _MATHIEU_SEED_C * q * q / d(-K - 1) ** 2)
    ph = seed / abs(seed) if seed else 1
    c = {k: v / norm / ph for k, v in c.items()}
    if sum(c.values()).real < 0:
        c = {k: -v for k, v in c.items()}
    return c


def _mathieu_char_index(kind, a, q, tol=1e-9):
    """If a is a characteristic value a_r(q) (kind C) / b_r(q) (kind S), return r."""
    from scipy.special import mathieu_a, mathieu_b
    af, qf = float(mpmath.re(a)), float(mpmath.re(q))
    if abs(float(mpmath.im(a))) > tol or abs(float(mpmath.im(q))) > tol:
        return None
    for r in range(0 if kind == "C" else 1, 40):
        v = mathieu_a(r, qf) if kind == "C" else mathieu_b(r, qf)
        if abs(v - af) < tol * max(1.0, abs(af)):
            return r
        if v > af + 100:
            break
    return None


def _mathieu_solve(a, q, z, deriv=False, kind="C"):
    """Wolfram's MathieuC / MathieuS: even / odd parts of the normalised
    Floquet solution.  At a characteristic value a_r(q) / b_r(q) this is the
    real function ce_r / se_r with int_0^{2 pi} ce^2 = pi (scipy's
    normalisation; MathieuC[a1(2), 2, 1] = 0.8158 verified); elsewhere the
    complex-valued Floquet construction with the kernel's phase convention."""
    r = _mathieu_char_index(kind, a, q)
    if r is not None and abs(float(mpmath.im(z))) < 1e-14:
        from scipy.special import mathieu_cem, mathieu_sem
        deg = math.degrees(float(mpmath.re(z)))
        fn = mathieu_cem if kind == "C" else mathieu_sem
        val, dval = fn(r, float(mpmath.re(q)), deg)
        return mpmath.mpf(float(dval if deriv else val))
    ac, qc, zc = complex(a), complex(q), complex(z)
    nu = _mathieu_exponent(ac, qc)
    c = _floquet_coeffs(ac, qc, nu)
    tot = 0j
    # overall signs (kernel convention): Re MathieuC[a,q,0] > 0 (done in
    # _floquet_coeffs) and Re MathieuSPrime[a,q,0] > 0
    sgn = 1 if kind == "C" or sum(v * (nu + 2 * k) for k, v in c.items()).real > 0 else -1
    for k, v in c.items():
        f = nu + 2 * k
        if kind == "C":
            tot += v * (-f * cmath.sin(f * zc) if deriv else cmath.cos(f * zc))
        else:
            tot += sgn * v * (f * cmath.cos(f * zc) if deriv else cmath.sin(f * zc))
    if abs(tot.imag) < 1e-12 * max(1.0, abs(tot.real)):
        return mpmath.mpf(tot.real)
    return mpmath.mpc(tot.real, tot.imag)


class MathieuC(_NumFn):
    summary_text = "even Mathieu function"
    rules = {"MathieuC[a_, 0, z_]": "Cos[Sqrt[a] z]"}

    def eval(self, a, q, z, evaluation):
        "MathieuC[a_, q_, z_]"
        return _mp(lambda a_, q_, z_: _mathieu_solve(a_, q_, z_, False, "C"), (a, q, z))


class MathieuS(_NumFn):
    summary_text = "odd Mathieu function"
    rules = {"MathieuS[a_, 0, z_]": "Sin[Sqrt[a] z]/Sqrt[a]"}

    def eval(self, a, q, z, evaluation):
        "MathieuS[a_, q_, z_]"
        return _mp(lambda a_, q_, z_: _mathieu_solve(a_, q_, z_, False, "S"), (a, q, z))


class MathieuCPrime(_NumFn):
    def eval(self, a, q, z, evaluation):
        "MathieuCPrime[a_, q_, z_]"
        return _mp(lambda a_, q_, z_: _mathieu_solve(a_, q_, z_, True, "C"), (a, q, z))


class MathieuSPrime(_NumFn):
    def eval(self, a, q, z, evaluation):
        "MathieuSPrime[a_, q_, z_]"
        return _mp(lambda a_, q_, z_: _mathieu_solve(a_, q_, z_, True, "S"), (a, q, z))


class MathieuCharacteristicExponent(_NumFn):
    def eval(self, a, q, evaluation):
        "MathieuCharacteristicExponent[a_, q_]"
        return _mp(lambda a_, q_: mpmath.mpmathify(_mathieu_exponent(a_, q_)), (a, q))


# ----------------------------------------------------- spheroidal --
class SpheroidalEigenvalue(_NumFn):
    summary_text = "spheroidal eigenvalue lambda_n^m(c)"
    rules = {"SpheroidalEigenvalue[n_, m_, 0]": "n (n + 1)"}

    def eval(self, n, m, c, evaluation):
        "SpheroidalEigenvalue[n_?NumericQ, m_?NumericQ, c_?InexactNumberQ]"
        try:
            from scipy.special import pro_cv
            # Wolfram's eigenvalue convention: λ_W = λ_scipy - c²  (SpheroidalEigenvalue[1,0,1] = 1.5931)
            cv = float(_S(c))
            return MachineReal(float(pro_cv(_small_int(m), _small_int(n), cv)) - cv * cv)
        except Exception:
            return None


def _spheroidal_coeffs(n, m, g2, KMAX=40):
    """DLMF 30.8 expansion coefficients of Ps_n^m(x, γ²) in Ferrers functions
    P_{n+2k}^m: returns (a, ap, λ) with a[k] for k >= -N (N = floor((n+m)/2);
    a[k] for -N <= k < -R from forward recursion, 30.8.9) normalised by 30.8.5,
    and the recessive tail ap[k] (k <= -N-1) from 30.8.10-11.  λ is Wolfram's
    SpheroidalEigenvalue (= DLMF λ)."""
    import numpy as np
    from scipy.special import pro_cv
    lam = (float(pro_cv(m, n, math.sqrt(g2))) - g2) if g2 > 0 else float(n * (n + 1))
    R, N = (n - m) // 2, (n + m) // 2
    A = lambda k: -g2 * (n - m + 2 * k - 1) * (n - m + 2 * k) / ((2 * n + 4 * k - 3) * (2 * n + 4 * k - 1))
    B = lambda k: (n + 2 * k) * (n + 2 * k + 1) - 2 * g2 * ((n + 2 * k) * (n + 2 * k + 1) - 1 + m * m) / ((2 * n + 4 * k - 1) * (2 * n + 4 * k + 3))
    C = lambda k: -g2 * (n + m + 2 * k + 1) * (n + m + 2 * k + 2) / ((2 * n + 4 * k + 3) * (2 * n + 4 * k + 5))
    ks = list(range(-R, KMAX + 1))
    M = np.zeros((len(ks), len(ks)))
    for i, k in enumerate(ks):
        M[i, i] = B(k)
        if i > 0:
            M[i, i - 1] = A(k)
        if i < len(ks) - 1:
            M[i, i + 1] = C(k)
    w, V = np.linalg.eig(M)
    j = int(np.argmin(abs(w - lam)))
    vec = V[:, j].real
    a = {k: float(vec[i]) for i, k in enumerate(ks)}
    f = lambda p, q: math.factorial(p) / math.factorial(q)
    amin = lambda k: f(n - m, n + m) * f(n + m + 2 * k, n - m + 2 * k) * a[k]
    s = sum(a[k] * amin(k) / (2 * n + 4 * k + 1) for k in ks)
    scale = math.sqrt((1.0 / (2 * n + 1)) / s)
    a = {k: v * scale for k, v in a.items()}
    if a[0] < 0:
        a = {k: -v for k, v in a.items()}
    if N > R:  # 30.8.9: forward recursion from a_{-N-1} = 0, a_{-N} = 1, matched at k = -R
        fwd = {-N - 1: 0.0, -N: 1.0}
        for k in range(-N, -R):
            fwd[k + 1] = -(A(k) * fwd[k - 1] + (B(k) - lam) * fwd[k]) / C(k)
        ratio = a[-R] / fwd[-R]
        for k in range(-N, -R):
            a[k] = fwd[k] * ratio
    Cp = g2 / (4 * m * m - 1) if (n - m) % 2 == 0 else -g2 / ((2 * m - 1) * (2 * m - 3))
    L = 60
    t, tk = {}, 0.0
    for k in range(-N - 1 - L, -N - 1):
        tk = -C(k) / ((B(k) - lam) + A(k) * tk)
        t[k] = tk
    ap = {}
    k = -N - 1
    ap[k] = -Cp * a[-N] / (A(k) * t[k - 1] + (B(k) - lam))
    for kk in range(-N - 2, -N - 1 - L, -1):
        ap[kk] = t[kk] * ap[kk + 1]
    return a, ap, lam


def _ferrers_p(deg, m, x):
    """Ferrers P_deg^m, with P_{-deg-1} = P_deg for negative degree."""
    if deg < 0:
        deg = -deg - 1
    if deg < m:
        return mpmath.mpf(0)
    return mpmath.legenp(deg, m, x, type=2)


def _spheroidal_ps_qs(n, m, c, x, kind="PS", deriv=False):
    """Wolfram's SpheroidalPS / SpheroidalQS on -1 < x < 1 (and their x-derivatives):
    PS = Σ_{k>=-R} (-1)^k a_k P_{n+2k}^m,
    QS = Σ_{k>=-N} (-1)^k a_k Q_{n+2k}^m + Σ_{k<=-N-1} (-1)^k a'_k P_{n+2k}^m,
    where the kernel uses the analytically continued Ferrers Q for the (possibly
    negative) degrees n+2k with -N <= k < -R (differs from DLMF 30.8.9, verified on
    90 kernel values).  For |x| > 1 the type-3 Legendre functions are used."""
    a, ap, lam = _spheroidal_coeffs(n, m, c * c)
    R = (n - m) // 2
    xm = mpmath.mpmathify(x)
    typ = 2 if abs(xm) < 1 else 3
    if kind == "PS":
        def fn(t):
            return sum((-1) ** k * v * mpmath.legenp(n + 2 * k, m, t, type=typ) for k, v in a.items() if k >= -R)
    else:
        def fn(t):
            tot = sum((-1) ** k * v * mpmath.legenq(n + 2 * k, m, t, type=typ) for k, v in a.items())
            if typ == 2:
                tot += sum((-1) ** k * v * _ferrers_p(n + 2 * k, m, t) for k, v in ap.items())
            else:
                tot += sum((-1) ** k * v * mpmath.legenp(-(n + 2 * k) - 1 if n + 2 * k < 0 else n + 2 * k, m, t, type=3)
                           for k, v in ap.items() if (-(n + 2 * k) - 1 if n + 2 * k < 0 else n + 2 * k) >= m)
            return tot
    val = mpmath.diff(fn, xm) if deriv else fn(xm)
    if kind == "QS" and typ == 3 and mpmath.im(xm) == 0:
        # kernel: QS(x) = Qs(x) - (I Pi/2) Ps(x) for real x > 1 (DLMF 30.6.5 continuation)
        val = val - 1j * mpmath.pi / 2 * _spheroidal_ps_qs(n, m, c, x, "PS", deriv)
    return val


def _spheroidal_eval(kind, deriv=False):
    def eval(self, n, m, c, x, evaluation):
        try:
            nv, mv = _small_int(n), _small_int(m)
        except Exception:
            return None
        if nv is None or mv is None or nv < 0 or mv < 0 or mv > nv:
            return None
        return _mp(lambda c_, x_: _spheroidal_ps_qs(nv, mv, float(mpmath.re(c_)), x_, kind, deriv), (c, x))
    eval.__doc__ = f"Spheroidal{kind}{'Prime' if deriv else ''}[n_?NumericQ, m_?NumericQ, c_?NumericQ, x_?NumericQ]"
    return eval


class SpheroidalPS(_NumFn):
    summary_text = "angular spheroidal function of the first kind"
    rules = {"SpheroidalPS[n_, m_, 0, x_]": "LegendreP[n, m, x]"}
    eval = _spheroidal_eval("PS")


class SpheroidalQS(_NumFn):
    summary_text = "angular spheroidal function of the second kind"
    rules = {"SpheroidalQS[n_, m_, 0, x_]": "LegendreQ[n, m, x]"}
    eval = _spheroidal_eval("QS")


class SpheroidalPSPrime(_NumFn):
    eval = _spheroidal_eval("PS", True)


class SpheroidalQSPrime(_NumFn):
    eval = _spheroidal_eval("QS", True)


def _spheroidal_radial(n, m, c, x, j, deriv=False):
    """DLMF 30.11.3: S_n^{m(j)}(x, c) = (1 - x^-2)^{m/2} / A_n^{-m} Σ_{2k >= m-n} a_{n,k}^{-m} ψ_{n+2k}^{(j)}(c x)
    (matches the kernel for all probed (n, m, c); scipy's pro_rad2 is off for m > 0)."""
    a, ap, lam = _spheroidal_coeffs(n, m, c * c)
    R = (n - m) // 2
    f = lambda p, q: math.factorial(p) / math.factorial(q)
    amin = {k: f(n - m, n + m) * f(n + m + 2 * k, n - m + 2 * k) * v for k, v in a.items() if k >= -R}
    Amin = sum((-1) ** k * v for k, v in amin.items())
    bes = mpmath.besselj if j == 1 else mpmath.bessely

    def fn(t):
        z = c * t
        tot = sum(v * mpmath.sqrt(mpmath.pi / (2 * z)) * bes(n + 2 * k + mpmath.mpf(1) / 2, z) for k, v in amin.items() if 2 * k >= m - n)
        return (1 - t ** -2) ** (mpmath.mpf(m) / 2) / Amin * tot
    xm = mpmath.mpmathify(x)
    return mpmath.diff(fn, xm) if deriv else fn(xm)


def _spheroidal_radial_eval(j, deriv=False):
    def eval(self, n, m, c, x, evaluation):
        nv, mv = _small_int(n), _small_int(m)
        if nv is None or mv is None or nv < 0 or mv < 0 or mv > nv:
            return None
        return _mp(lambda c_, x_: _spheroidal_radial(nv, mv, c_, x_, j, deriv), (c, x))
    eval.__doc__ = f"SpheroidalS{j}{'Prime' if deriv else ''}[n_?NumericQ, m_?NumericQ, c_?NumericQ, x_?NumericQ]"
    return eval


class SpheroidalS1(_NumFn):
    eval = _spheroidal_radial_eval(1)


class SpheroidalS2(_NumFn):
    eval = _spheroidal_radial_eval(2)


class SpheroidalS1Prime(_NumFn):
    eval = _spheroidal_radial_eval(1, True)


class SpheroidalS2Prime(_NumFn):
    eval = _spheroidal_radial_eval(2, True)


from mathics.builtin.specialfns.orthogonal import LegendreP as _NativeLegendreP, HermiteH as _NativeHermiteH
from mathics.builtin.specialfns.hypergeom import Hypergeometric1F1 as _Native1F1


class LegendrePWolfram(_NativeLegendreP):
    """Associated Legendre P[n, m, x] in closed form; numeric for non-integer n.
    The native rule LegendreP[n, x] -> LegendreP[n, 0, x] is dropped: with
    symbolic n it loops (SymPy converts legendre(n, x) back to the 2-argument
    form), and the kernel keeps LegendreP[n, x] / LegendreP[n, 0, x] distinct."""
    name = "LegendreP"
    context = "System`"
    rules = {
        "Derivative[0,1][LegendreP]": "(((-1 - #1)*#2*LegendreP[#1, #2] + (1 + #1)*LegendreP[1 + #1, #2])/(-1 + #2^2))&",
        "Derivative[0,0,1][LegendreP]": "((LegendreP[1 + #1, #2, #3]*(1 + #1 - #2) + LegendreP[#1, #2, #3]*(-1 - #1)*#3)/(-1 + #3^2))&",
        "LegendreP[n_, 1]": "1",
        "LegendreP[n_, 0, x_]": "LegendreP[n, x]",
    }

    def eval_poly(self, n, x, evaluation):
        "LegendreP[n_Integer, x_]"
        if n.value < 0:
            return None
        xs = _S(x)
        if xs is None:
            return None
        p = sympy.legendre(n.value, xs)
        return from_sympy(sympy.N(p) if _inexact(x) else sympy.expand(p))

    def eval_symbolic(self, n, x, evaluation):
        "LegendreP[n_, x_]"
        # symbolic / exact non-integer degree: inert (LegendreP[n, -1], LegendreP[n, 0],
        # LegendreP[1/2, x] all stay in the kernel); only inexact numbers evaluate
        if isinstance(n, Number) and isinstance(x, Number) and _inexact(n, x):
            return _mp(lambda n_, x_: mpmath.legendre(n_, x_), (n, x))
        return None

    def eval_assoc(self, n, m, x, evaluation):
        "LegendreP[n_Integer, m_Integer, x_]"
        nv, mv = n.value, m.value
        xs = _S(x)
        if xs is None or nv < 0:
            return None
        try:
            p = sympy.legendre(nv, xs) if mv == 0 else sympy.assoc_legendre(nv, mv, xs)
        except Exception:
            return None
        if mv == 0:
            return from_sympy(sympy.N(p) if _inexact(x) else sympy.expand(p))
        if _inexact(x):
            return from_sympy(sympy.N(p))
        # Wolfram: -3 x Sqrt[1 - x^2],  -15 x (-1 + x^2): P_n^m = (-1)^m (1-x^2)^{m/2} d^m P_n/dx^m
        # with the (1 - x^2) factor kept unexpanded
        if not xs.free_symbols:
            return from_sympy(sympy.expand_func(p))
        s = sympy.sqrt(1 - xs ** 2)
        xv = list(xs.free_symbols)[0] if xs.is_Symbol else sympy.Symbol("x$")
        poly = sympy.legendre(nv, xv)
        q = sympy.factor((-1) ** mv * (-1) ** (mv // 2) * sympy.diff(poly, xv, mv)).subs(xv, xs)
        half = (xs ** 2 - 1) ** (mv // 2)
        return from_sympy(q * half * (s if mv % 2 else 1))

    def eval_num(self, n, x, evaluation):
        "LegendreP[n_?InexactNumberQ, x_?NumericQ]"
        return _mp(lambda n_, x_: mpmath.legendre(n_, x_), (n, x))

    def eval_num2(self, n, x, evaluation):
        "LegendreP[n_?NumericQ, x_?InexactNumberQ]"
        return _mp(lambda n_, x_: mpmath.legendre(n_, x_), (n, x))


class HermiteHWolfram(_NativeHermiteH):
    """HermiteH for negative / non-integer order via mpmath (native class raises)."""
    name = "HermiteH"
    context = "System`"

    def eval(self, n, x, evaluation):
        "HermiteH[n_, x_]"
        if isinstance(n, Integer) and n.value >= 0 and not _inexact(x):
            xs = _S(x)
            if xs is None:
                return None
            return from_sympy(sympy.expand(sympy.hermite(n.value, xs)))
        if isinstance(n, Number) and isinstance(x, Number) and _inexact(n, x):
            return _mp(lambda n_, x_: mpmath.hermite(n_, x_), (n, x))
        return None  # HermiteH[-1, x], HermiteH[1/2, x]: inert (native class raised)


def _hyper_closed_form(ps, qs, z, head, args):
    """sympy.hyperexpand; keep Wolfram's head when nothing closed comes out
    (the kernel never rewrites Hypergeometric2F1[a,b,c,x] as PFQ)."""
    try:
        res = sympy.hyperexpand(sympy.hyper(ps, qs, z))
    except Exception:
        return None
    if res.has(sympy.hyper) or res.has(sympy.meijerg):
        return None  # inert: Wolfram keeps the 2F1 / 1F1 / 0F1 form
    return from_sympy(res)


class Hypergeometric1F1Wolfram(_Native1F1):
    name = "Hypergeometric1F1"
    context = "System`"

    def eval_num(self, a, b, z, evaluation):
        "Hypergeometric1F1[a_?InexactNumberQ, b_?NumericQ, z_?NumericQ]"
        return _mp(mpmath.hyp1f1, (a, b, z))

    def eval_num2(self, a, b, z, evaluation):
        "Hypergeometric1F1[a_?NumericQ, b_?NumericQ, z_?InexactNumberQ]"
        return _mp(mpmath.hyp1f1, (a, b, z))

    def eval(self, a, b, z, evaluation):
        "Hypergeometric1F1[a_, b_, z_]"
        if _inexact(a, b, z):
            return _mp(mpmath.hyp1f1, (a, b, z))
        sa, sb, sz = _S(a), _S(b), _S(z)
        if None in (sa, sb, sz):
            return None
        return _hyper_closed_form([sa], [sb], sz, "Hypergeometric1F1", (a, b, z))


from mathics.builtin.specialfns.hypergeom import Hypergeometric2F1 as _Native2F1


class Hypergeometric2F1Wolfram(_Native2F1):
    name = "Hypergeometric2F1"
    context = "System`"

    def eval(self, a, b, c, z, evaluation):
        "Hypergeometric2F1[a_, b_, c_, z_]"
        if _inexact(a, b, c, z):
            return _mp(mpmath.hyp2f1, (a, b, c, z))
        sa, sb, sc, sz = _S(a), _S(b), _S(c), _S(z)
        if None in (sa, sb, sc, sz):
            return None
        if sz == 1 and not all(isinstance(e, Number) for e in (a, b, c)):
            return None  # Gauss' theorem is not applied by the kernel for symbolic a, b, c
        return _hyper_closed_form([sa, sb], [sc], sz, "Hypergeometric2F1", (a, b, c, z))


from mathics.builtin.specialfns.gamma import Factorial2 as _NativeFactorial2


class Factorial2Numeric(_NativeFactorial2):
    """n!!: exact for integers (Factorial2[-3] = -1, Factorial2[-2] = ComplexInfinity),
    inert for other exact numbers ((1/2)!!), mpmath for inexact ones.  Subclassing the
    native PostfixOperator keeps the n!! output form."""
    name = "Factorial2"
    context = "System`"
    rules = {
        "Factorial2[n_Integer?Negative] /; EvenQ[n]": "ComplexInfinity",
    }

    def eval(self, n, evaluation, options={}):
        "Factorial2[n_?NumberQ, OptionsPattern[Factorial2]]"
        if isinstance(n, Integer):
            v = n.value
            if v >= -1:
                return Integer(int(sympy.factorial2(v)))
            if v % 2:  # negative odd: (-1)^((|n|-1)/2) / (|n| - 2)!!
                k = -v
                return from_sympy(sympy.Integer(-1) ** ((k - 1) // 2) / sympy.factorial2(k - 2))
            return None
        if n.is_inexact():
            return _mp(mpmath.fac2, (n,))
        return None


from mathics.builtin.specialfns.gamma import Gamma as _NativeGamma, PolyGamma as _NativePolyGamma
from mathics.builtin.specialfns.bessel import HankelH1 as _NativeHankelH1, HankelH2 as _NativeHankelH2
from mathics.builtin.numbers.trig import Tan as _NativeTan
from mathics.builtin.numbers.hyperbolic import ArcSinh as _NativeArcSinh, ArcCosh as _NativeArcCosh, ArcTanh as _NativeArcTanh
from mathics.builtin.specialfns.orthogonal import LaguerreL as _NativeLaguerreL


# Mathics' MPMathFunction.eval converts exact arguments through SymPy, which
# yields closed forms Wolfram does not return (Gamma[2, x] -> (1+x) E^-x,
# PolyGamma[2, 1] -> -2 Zeta[3], HankelH1[0, 1] -> a wrong number).  The
# wrappers below keep exact arguments inert and evaluate inexact ones with
# mpmath, matching the kernel's policy.
def _gamma_num(*a):
    if len(a) == 1:
        return mpmath.gamma(a[0])
    if len(a) == 2:
        return mpmath.gammainc(a[0], a[1])
    return mpmath.gammainc(a[0], a[1], a[2])


class GammaWolfram(_NativeGamma):
    """Gamma / incomplete Gamma with Wolfram's evaluation policy."""
    name = "Gamma"
    context = "System`"
    rules = {
        "Gamma[1, x_]": "E^(-x)",
        "Gamma[a_, 0]": "Gamma[a]",
        "Gamma[a_, x_, x_]": "0",
        "Gamma[Undefined, y_]": "Undefined",
        "Gamma[x_, Undefined]": "Undefined",
    }

    def eval(self, z, evaluation):
        "Gamma[z__]"
        args = z.get_sequence()
        if len(args) not in (1, 2, 3) or not all(isinstance(a, Number) for a in args):
            return None
        if any(a.is_inexact() for a in args):
            return _mp(_gamma_num, tuple(args))
        if len(args) == 1:
            return super().eval(z, evaluation)  # exact Gamma[n], Gamma[1/2] etc. via native/sympy
        if len(args) == 2 and isinstance(args[0], Integer) and args[0].value > 0:
            # Gamma[n, z] = (n-1)! e^-z Σ z^k/k!  for positive integer n and exact numeric z
            # (kernel: Gamma[2, 3] = 4/E^3, Gamma[4, 1/2] = 79/(8 Sqrt[E]), Gamma[2, I] = (1+I)/E^I)
            n, zs = args[0].value, args[1].to_sympy()
            if zs is None:
                return None
            val = sympy.factorial(n - 1) * sympy.exp(-zs) * sum(zs ** k / sympy.factorial(k) for k in range(n))
            return from_sympy(sympy.simplify(val))
        return None  # Gamma[1/2, 3], Gamma[3, 0, 2]: inert like Wolfram


class PolyGammaWolfram(_NativePolyGamma):
    name = "PolyGamma"
    context = "System`"
    rules = {
        "PolyGamma[1]": "-EulerGamma",
        "PolyGamma[0, 1]": "-EulerGamma",
        "PolyGamma[x_]": "PolyGamma[0, x] /; !NumericQ[x] || !InexactNumberQ[x]",
        "PolyGamma[1, 1]": "Pi^2/6",
        "PolyGamma[1, 1/2]": "Pi^2/2",
        "PolyGamma[3, 1]": "Pi^4/15",
        "PolyGamma[n_Integer?Positive, 1]": "(-1)^(n + 1) n! Zeta[n + 1] /; EvenQ[n + 1]",
        "PolyGamma[n_Integer?Positive, 1/2]": "(-1)^(n + 1) n! (2^(n + 1) - 1) Zeta[n + 1] /; EvenQ[n + 1]",
        "PolyGamma[0, n_Integer?Positive]": "HarmonicNumber[n - 1] - EulerGamma",
    }

    def eval(self, z, evaluation):
        "PolyGamma[z__]"
        args = z.get_sequence()
        if len(args) not in (1, 2) or not all(isinstance(a, Number) for a in args):
            return None
        if any(a.is_inexact() for a in args):
            if len(args) == 1:
                return _mp(lambda x: mpmath.psi(0, x), (args[0],))
            return _mp(lambda n, x: mpmath.psi(int(n), x) if n == int(n) else mpmath.nan, tuple(args))
        if len(args) == 2 and isinstance(args[0], Integer) and args[0].value >= 1 and args[0].value % 2 == 1:
            # odd order m at integer / half-integer x: closed form through Zeta[m+1]
            # (kernel: PolyGamma[1, 3] = -5/4 + Pi^2/6, PolyGamma[1, 3/2] = -4 + Pi^2/2,
            #  PolyGamma[3, 2] = 6 (-1 + Pi^4/90), PolyGamma[1, -1/2] = 4 + Pi^2/2; even m stays inert)
            m, xs = args[0].value, args[1].to_sympy()
            if xs is None or not (xs.is_integer or (2 * xs).is_integer):
                return None
            # shift to the base point (1 or 1/2) with the recurrence
            # ψ^(m)(x+1) = ψ^(m)(x) + (-1)^m m!/x^(m+1); ψ^(m)(1) = (-1)^(m+1) m! ζ(m+1),
            # ψ^(m)(1/2) = (-1)^(m+1) m! (2^(m+1) - 1) ζ(m+1)
            base = sympy.Integer(1) if xs.is_integer else sympy.Rational(1, 2)
            k = int(xs - base)
            v = (-1) ** (m + 1) * sympy.factorial(m) * sympy.zeta(m + 1) * (1 if base == 1 else 2 ** (m + 1) - 1)
            if k >= 0:
                v += sum((-1) ** m * sympy.factorial(m) / (base + j) ** (m + 1) for j in range(k))
            else:
                if base == 1:
                    return None  # non-positive integers: pole
                v -= sum((-1) ** m * sympy.factorial(m) / (base - j) ** (m + 1) for j in range(1, -k + 1))
            return from_sympy(sympy.expand(v))
        return None


class HankelH1Wolfram(_NativeHankelH1):
    name = "HankelH1"
    context = "System`"

    def eval(self, z, evaluation):
        "HankelH1[z__]"
        args = z.get_sequence()
        if len(args) == 2 and all(isinstance(a, Number) for a in args) and any(a.is_inexact() for a in args):
            return _mp(mpmath.hankel1, tuple(args))
        return None


class HankelH2Wolfram(_NativeHankelH2):
    name = "HankelH2"
    context = "System`"

    def eval(self, z, evaluation):
        "HankelH2[z__]"
        args = z.get_sequence()
        if len(args) == 2 and all(isinstance(a, Number) for a in args) and any(a.is_inexact() for a in args):
            return _mp(mpmath.hankel2, tuple(args))
        return None


class LaguerreLWolfram(_NativeLaguerreL):
    """LaguerreL[1/2, x] stays inert (native gives 1); integer n polynomial via sympy.
    The native rewrite LaguerreL[n, x] -> LaguerreL[n, 0, x] is dropped (the
    kernel keeps the two-argument form)."""
    name = "LaguerreL"
    context = "System`"
    rules = {
        "Derivative[0, 1][LaguerreL]": "-LaguerreL[-1 + #1, 1, #2] &",
        "Derivative[0, 0, 1][LaguerreL]": "-LaguerreL[-1 + #1, 1 + #2, #3] &",
    }

    def eval2(self, n, x, evaluation):
        "LaguerreL[n_, x_]"
        if isinstance(n, Integer) and n.value >= 0:
            xs = _S(x)
            if xs is None:
                return None
            p = sympy.laguerre(n.value, xs)
            return from_sympy(sympy.N(p) if _inexact(x) else p)
        if isinstance(n, Number) and isinstance(x, Number) and (n.is_inexact() or x.is_inexact()):
            return _mp(lambda n_, x_: mpmath.laguerre(n_, 0, x_), (n, x))
        return None

    def eval3(self, n, a, x, evaluation):
        "LaguerreL[n_, a_, x_]"
        if isinstance(n, Integer) and n.value >= 0:
            xs, as_ = _S(x), _S(a)
            if xs is None or as_ is None:
                return None
            p = sympy.assoc_laguerre(n.value, as_, xs)
            return from_sympy(sympy.N(p) if _inexact(x) else sympy.expand(p))
        if all(isinstance(e, Number) for e in (n, a, x)) and any(e.is_inexact() for e in (n, a, x)):
            return _mp(mpmath.laguerre, (n, a, x))
        return None


_INERT_TAN_ARGS = {sympy.Rational(1, 8), sympy.Rational(3, 8), sympy.Rational(5, 8), sympy.Rational(7, 8)}


class TanWolfram(_NativeTan):
    """Wolfram leaves Tan[Pi/8] (and odd multiples) unevaluated although
    SymPy knows -1 + Sqrt[2]; everything else goes to the native class."""
    name = "Tan"
    context = "System`"

    def eval(self, z, evaluation):
        "Tan[z__]"
        args = z.get_sequence()
        if len(args) == 1:
            s = _S(args[0])
            if s is not None and s.is_Mul and sympy.pi in s.args:
                k = s / sympy.pi
                if k in _INERT_TAN_ARGS:
                    return None
        return super().eval(z, evaluation)


_INVHYP_EXACT = {
    # values the kernel evaluates; everything else exact stays inert (ArcSinh[1], ArcCosh[2], ArcTanh[1/2])
    "ArcSinh": {"0": "0", "I": "I Pi/2", "-I": "-I Pi/2"},
    "ArcCosh": {"1": "0", "0": "I Pi/2", "-1": "I Pi", "1/2": "I Pi/3", "-1/2": "2 I Pi/3"},
    "ArcTanh": {"0": "0", "1": "Infinity", "-1": "-Infinity"},
}


def _inert_inverse_hyperbolic(native, name, mp):
    class _C(native):
        rules = {f"{name}[{k}]": v for k, v in _INVHYP_EXACT[name].items()}
        rules.update({f"{name}[Infinity]": "Infinity", f"{name}[-Infinity]": "-Infinity"} if name != "ArcTanh"
                     else {f"{name}[Infinity]": "-I Pi/2", f"{name}[-Infinity]": "I Pi/2"})

        def eval(self, z, evaluation):
            args = z.get_sequence()
            if len(args) == 1 and isinstance(args[0], Number):
                if args[0].is_inexact():
                    return _mp(mp, (args[0],))
                return None  # ArcSinh[1] inert (Wolfram)
            return super().eval(z, evaluation)
        eval.__doc__ = f"{name}[z__]"
    _C.__name__ = name + "Wolfram"
    _C.name = name
    _C.context = "System`"
    return _C


from mathics.builtin.specialfns.elliptic import EllipticPi as _NativeEllipticPi
from mathics.builtin.specialfns.orthogonal import LegendreQ as _NativeLegendreQ
from mathics.builtin.specialfns.zeta import PolyLog as _NativePolyLog
from mathics.builtin.specialfns.gamma import StieltjesGamma as _NativeStieltjesGamma


class EllipticPiWolfram(_NativeEllipticPi):
    """EllipticPi[n, m] / EllipticPi[n, phi, m] numerically via mpmath (the native
    class swaps the arguments and aborts for exact rationals); exact special
    values follow the kernel (EllipticPi[n, 0] piecewise, EllipticPi[0, m] = EllipticK[m])."""
    name = "EllipticPi"
    context = "System`"
    rules = {
        "EllipticPi[0, m_]": "EllipticK[m]",
        "EllipticPi[n_, 0]": "Piecewise[{{Pi/(2 Sqrt[1 - n]), -Pi < Arg[1 - n] < Pi && n != 1}, {ComplexInfinity, n == 1}}, 0]",
        "EllipticPi[0, phi_, m_]": "EllipticF[phi, m]",
        "EllipticPi[n_, Pi/2, m_]": "EllipticPi[n, m]",
    }

    def eval_n_m(self, n, m, evaluation):
        "EllipticPi[n_, m_]"
        return _mp(lambda n_, m_: mpmath.ellippi(n_, m_), (n, m))

    def eval_n_phi_m(self, n, phi, m, evaluation):
        "EllipticPi[n_, phi_, m_]"
        return _mp(lambda n_, p_, m_: mpmath.ellippi(n_, p_, m_), (n, phi, m))


class LegendreQWolfram(_NativeLegendreQ):
    """LegendreQ with Wolfram's type convention: LegendreQ[n, m, x] uses the
    Ferrers function on -1 < x < 1 and type 3 outside; LegendreQ[n, m, 3, x]
    forces type 3 (so e.g. LegendreQ[1/2, 0.3] = -0.5338 and LegendreQ[1/2, 3]
    is complex)."""
    name = "LegendreQ"
    context = "System`"
    rules = {
        "Derivative[0,1][LegendreQ]": "((LegendreQ[1 + #1, #2]*(1 + #1) + LegendreQ[#1, #2]*(-1 - #1)*#2)/(-1 + #2^2))&",
        "Derivative[0,0,1][LegendreQ]": "((LegendreQ[1 + #1, #2, #3]*(1 + #1 - #2) + LegendreQ[#1, #2, #3]*(-1 - #1)*#3)/(-1 + #3^2))&",
        "LegendreQ[n_, 0, x_]": "LegendreQ[n, x]",
    }

    def eval_num2(self, n, x, evaluation):
        "LegendreQ[n_?NumericQ, x_?NumericQ]"
        if not _inexact(n, x):
            return None
        return _mp(lambda n_, x_: self._q(n_, 0, x_), (n, x))

    @staticmethod
    def _q(n_, m_, x_, typ=None):
        if typ is None:
            typ = 2
        if typ == 2 and mpmath.im(x_) == 0 and abs(x_) > 1:
            # type-2 continuation for real |x| > 1 (DLMF 14.23): Q - (I Pi/2) P in the type-3 forms
            return mpmath.legenq(n_, m_, x_, type=3) - 1j * mpmath.pi / 2 * mpmath.legenp(n_, m_, x_, type=3)
        return mpmath.legenq(n_, m_, x_, type=typ)

    def eval_num3(self, n, m, x, evaluation):
        "LegendreQ[n_?NumericQ, m_?NumericQ, x_?NumericQ]"
        if not _inexact(n, m, x):
            return None
        return _mp(lambda n_, m_, x_: self._q(n_, m_, x_), (n, m, x))

    def eval_num4(self, n, m, t, x, evaluation):
        "LegendreQ[n_?NumericQ, m_?NumericQ, t_Integer, x_?NumericQ]"
        if not _inexact(n, m, x):
            return None
        typ = t.value
        if typ not in (2, 3):
            return None
        return _mp(lambda n_, m_, x_: self._q(n_, m_, x_, typ), (n, m, x))


from symbolic_extras import PolyLogValues as _PolyLogValues


class PolyLogWolfram(_PolyLogValues):
    """Adds Nielsen's generalised polylogarithm PolyLog[n, p, z] = S_{n,p}(z)
    (numeric) on top of the exact-value class; PolyLog[2, 2] etc. stay inert
    like the kernel (sympy's expand_func would give Pi^2/4 - I Pi Log[2])."""
    name = "PolyLog"
    context = "System`"
    rules = dict(_PolyLogValues.rules, **{"PolyLog[n_, 1, z_]": "PolyLog[n + 1, z]"})

    def eval(self, n, z, evaluation):
        "PolyLog[n_, z_]"
        if isinstance(n, Integer) and isinstance(z, Number) and not z.is_inexact():
            zs = z.to_sympy()
            if zs.is_real and (zs > 1 or zs < -1) or (zs.is_complex and not zs.is_real):
                return None  # PolyLog[2, 2], PolyLog[2, 1 - I]: inert (PolyLog[2, ±I] handled by rules)
        return super().eval(n, z, evaluation)

    def eval3(self, n, p, z, evaluation):
        "PolyLog[n_?NumericQ, p_?NumericQ, z_?NumericQ]"
        if not _inexact(n, p, z):
            return None
        nv, pv = _small_int(n), _small_int(p)
        if nv is None or pv is None or nv < 0 or pv < 1:
            return None

        def nielsen(z_):
            if nv == 0:  # S_{0,p}(z) = (-Log[1 - z])^p / p!
                return (-mpmath.log(1 - z_)) ** pv / mpmath.factorial(pv)
            return (-1) ** (nv + pv - 1) / (mpmath.factorial(nv - 1) * mpmath.factorial(pv)) * mpmath.quad(
                lambda t: mpmath.log(t) ** (nv - 1) * mpmath.log(1 - z_ * t) ** pv / t, [0, 1])
        return _mp(nielsen, (z,))


class StieltjesGammaWolfram(_NativeStieltjesGamma):
    name = "StieltjesGamma"
    context = "System`"

    def eval_num(self, n, evaluation):
        "StieltjesGamma[n_?InexactNumberQ]"
        nv = _small_int(n)
        if nv is None or nv < 0:
            return None
        return _mp(lambda n_: mpmath.stieltjes(nv), (n,))

    def eval_num2(self, n, a, evaluation):
        "StieltjesGamma[n_?NumericQ, a_?NumericQ]"
        if not _inexact(n, a):
            return None
        nv = _small_int(n)
        if nv is None or nv < 0:
            return None
        return _mp(lambda n_, a_: mpmath.stieltjes(nv, a_), (n, a))


from mathics.builtin.specialfns.orthogonal import ChebyshevT as _NativeChebyshevT, JacobiP as _NativeJacobiP
from mathics.builtin.specialfns.bessel import (SphericalBesselJ as _NativeSphJ, SphericalBesselY as _NativeSphY,
                                               SphericalHankelH1 as _NativeSphH1, SphericalHankelH2 as _NativeSphH2)
from mathics.builtin.numbers.hyperbolic import Gudermannian as _NativeGd, InverseGudermannian as _NativeInvGd
from mathics.builtin.numbers.trig import Haversine as _NativeHaversine
from mathics.builtin.specialfns.elliptic import EllipticK as _NativeEllipticK, EllipticE as _NativeEllipticE


def _poly_or_numeric(native, name, sym_fn, mp_fn, nargs):
    """Orthogonal polynomial: exact polynomial for non-negative integer degree,
    mpmath for inexact arguments, inert otherwise (ChebyshevT[n, 1] stays)."""
    class _C(native):
        def eval(self, z, evaluation):
            args = z.get_sequence()
            if len(args) != nargs:
                return None
            if all(isinstance(a, Number) for a in args) and _inexact(*args):
                return _mp(mp_fn, tuple(args))
            n = args[0]
            if isinstance(n, Integer) and n.value >= 0:
                ss = [_S(a) for a in args[1:]]
                if None in ss:
                    return None
                try:
                    return from_sympy(sympy.expand(sym_fn(n.value, *ss)))
                except Exception:
                    return None
            return None
        eval.__doc__ = f"{name}[z__]"
    _C.__name__ = name + "Wolfram"
    _C.name = name
    _C.context = "System`"
    return _C


ChebyshevTWolfram = _poly_or_numeric(_NativeChebyshevT, "ChebyshevT", sympy.chebyshevt, mpmath.chebyt, 2)
JacobiPWolfram = _poly_or_numeric(_NativeJacobiP, "JacobiP", sympy.jacobi, mpmath.jacobi, 4)


def _spherical_bessel(native, name, kind):
    """SphericalBesselJ/Y, SphericalHankelH1/H2: numeric via Bessel of half-integer
    order, symbolic form left inert (the native rule rewrites to BesselJ[n + 0.5, z])."""
    fns = {"J": mpmath.besselj, "Y": mpmath.bessely, "H1": mpmath.hankel1, "H2": mpmath.hankel2}

    def num(n_, z_):
        return mpmath.sqrt(mpmath.pi / (2 * z_)) * fns[kind](n_ + mpmath.mpf(1) / 2, z_)

    class _C(native):
        rules = {}

        def eval(self, n, z, evaluation):
            if _inexact(n, z):
                return _mp(num, (n, z))
            return None
        eval.__doc__ = f"{name}[n_, z_]"
    _C.__name__ = name + "Wolfram"
    _C.name = name
    _C.context = "System`"
    return _C


SphericalBesselJWolfram = _spherical_bessel(_NativeSphJ, "SphericalBesselJ", "J")
SphericalBesselYWolfram = _spherical_bessel(_NativeSphY, "SphericalBesselY", "Y")
SphericalHankelH1Wolfram = _spherical_bessel(_NativeSphH1, "SphericalHankelH1", "H1")
SphericalHankelH2Wolfram = _spherical_bessel(_NativeSphH2, "SphericalHankelH2", "H2")


def _numeric_only(native, name, mp_fn, exact_rules):
    """Keep exact arguments inert except for listed special values; mpmath otherwise."""
    class _C(native):
        rules = dict(exact_rules)

        def eval(self, z, evaluation):
            if isinstance(z, Number) and z.is_inexact():
                return _mp(mp_fn, (z,))
            return None
        eval.__doc__ = f"{name}[z_]"
    _C.__name__ = name + "Wolfram"
    _C.name = name
    _C.context = "System`"
    return _C


GudermannianWolfram = _numeric_only(_NativeGd, "Gudermannian", lambda z: 2 * mpmath.atan(mpmath.tanh(z / 2)),
                                    {"Gudermannian[0]": "0", "Gudermannian[Infinity]": "Pi/2", "Gudermannian[-Infinity]": "-Pi/2"})
InverseGudermannianWolfram = _numeric_only(_NativeInvGd, "InverseGudermannian", lambda z: mpmath.log(mpmath.tan(mpmath.pi / 4 + z / 2)),
                                           {"InverseGudermannian[0]": "0"})
HaversineWolfram = _numeric_only(_NativeHaversine, "Haversine", lambda z: mpmath.sin(z / 2) ** 2,
                                 {"Haversine[0]": "0", "Haversine[Pi]": "1", "Haversine[Pi/2]": "1/2", "Haversine[Pi/3]": "1/4"})
EllipticKWolfram = _numeric_only(_NativeEllipticK, "EllipticK", mpmath.ellipk,
                                 {"EllipticK[0]": "Pi/2", "EllipticK[1]": "ComplexInfinity"})


class EllipticEWolfram(_NativeEllipticE):
    name = "EllipticE"
    context = "System`"
    rules = {"EllipticE[0]": "Pi/2", "EllipticE[1]": "1", "EllipticE[0, m_]": "0", "EllipticE[Pi/2, m_]": "EllipticE[m]"}

    def eval1(self, m, evaluation):
        "EllipticE[m_]"
        if isinstance(m, Number) and m.is_inexact():
            return _mp(mpmath.ellipe, (m,))
        return None

    def eval2(self, phi, m, evaluation):
        "EllipticE[phi_, m_]"
        if _inexact(phi, m):
            return _mp(lambda p_, m_: mpmath.ellipe(p_, m_), (phi, m))
        return None


from mathics.builtin.intfns.recurrence import BernoulliB as _NativeBernoulliB
from mathics.builtin.intfns.combinatorial import EulerE as _NativeEulerE


def _bernoulli_euler(native, name, sym_fn):
    """BernoulliB / EulerE: exact numbers and polynomials for integer n; for a
    symbolic n only BernoulliB[n, 0] -> BernoulliB[n] and EulerE[n, 1/2] ->
    EulerE[n]/2^n are applied (kernel), everything else stays inert."""
    class _C(native):
        rules = {"BernoulliB[n_, 0]": "BernoulliB[n]"} if name == "BernoulliB" else {"EulerE[n_, 1/2]": "EulerE[n]/2^n"}

        def eval(self, z, evaluation):
            args = z.get_sequence()
            if name == "EulerE" and len(args) == 2 and isinstance(args[1], Rational) and args[1].to_sympy() == sympy.Rational(1, 2):
                return Expression(Symbol("System`Divide"), Expression(Symbol("System`EulerE"), args[0]),
                                  Expression(Symbol("System`Power"), Integer(2), args[0])).evaluate(evaluation)
            if len(args) not in (1, 2) or not isinstance(args[0], Integer) or args[0].value < 0:
                return None
            if name == "BernoulliB" and len(args) == 1 and args[0].value == 1:
                return from_sympy(sympy.Rational(-1, 2))  # Wolfram convention B_1 = -1/2 (sympy >= 1.12 gives +1/2)
            ss = [_S(a) for a in args[1:]]
            if None in ss:
                return None
            try:
                v = sym_fn(args[0].value, *ss)
                return from_sympy(sympy.N(v) if (ss and _inexact(args[1])) else sympy.expand(v))
            except Exception:
                return None
        eval.__doc__ = f"{name}[z__]"
    _C.__name__ = name + "Wolfram"
    _C.name = name
    _C.context = "System`"
    return _C


BernoulliBWolfram = _bernoulli_euler(_NativeBernoulliB, "BernoulliB", sympy.bernoulli)
EulerEWolfram = _bernoulli_euler(_NativeEulerE, "EulerE", sympy.euler)


from mathics.builtin.testing_expressions.equality_inequality import Max as _NativeMax, Min as _NativeMin


def _dedupe_minmax(native, name):
    """Max[x, x] -> x, Max[x, y, x] -> Max[x, y]: the native class only
    compares numerically, so identical symbolic elements survive."""
    class _C(native):
        def eval(self, items, evaluation):
            if hasattr(items, "flatten_with_respect_to_head"):
                items = items.flatten_with_respect_to_head(Symbol("System`List"))
            seq = list(items.get_sequence())
            uniq = []
            for it in seq:
                if not any(it.sameQ(u) for u in uniq):
                    uniq.append(it)
            if len(uniq) < len(seq):
                res = super().eval(Expression(Symbol("System`Sequence"), *uniq), evaluation)
                if res is not None:
                    return res
                return uniq[0] if len(uniq) == 1 else Expression(Symbol(f"System`{name}"), *uniq)
            return super().eval(items, evaluation)
        eval.__doc__ = f"{name}[items___]"
    _C.__name__ = name + "Wolfram"
    _C.name = name
    _C.context = "System`"
    return _C


MaxWolfram = _dedupe_minmax(_NativeMax, "Max")
MinWolfram = _dedupe_minmax(_NativeMin, "Min")

ArcSinhWolfram = _inert_inverse_hyperbolic(_NativeArcSinh, "ArcSinh", mpmath.asinh)
ArcCoshWolfram = _inert_inverse_hyperbolic(_NativeArcCosh, "ArcCosh", mpmath.acosh)
ArcTanhWolfram = _inert_inverse_hyperbolic(_NativeArcTanh, "ArcTanh", mpmath.atanh)


CLASSES = [
    LegendrePWolfram, HermiteHWolfram, Hypergeometric1F1Wolfram, Hypergeometric2F1Wolfram, Factorial2Numeric,
    GammaWolfram, PolyGammaWolfram, HankelH1Wolfram, HankelH2Wolfram, LaguerreLWolfram, TanWolfram,
    ArcSinhWolfram, ArcCoshWolfram, ArcTanhWolfram, MaxWolfram, MinWolfram,
    EllipticPiWolfram, LegendreQWolfram, PolyLogWolfram, StieltjesGammaWolfram,
    ChebyshevTWolfram, JacobiPWolfram, SphericalBesselJWolfram, SphericalBesselYWolfram, SphericalHankelH1Wolfram,
    SphericalHankelH2Wolfram, GudermannianWolfram, InverseGudermannianWolfram, HaversineWolfram, EllipticKWolfram, EllipticEWolfram,
    BernoulliBWolfram, EulerEWolfram,
    Erfi, DawsonF, FaddeevaW, SinhIntegral, CoshIntegral, ScorerGi, ScorerHi,
    BarnesG, Hyperfactorial, Superfactorial,
    ArithmeticGeometricMean, CarlsonRF, CarlsonRD, CarlsonRJ, CarlsonRC, CarlsonRG,
    EllipticTheta, EllipticThetaPrime, EllipticNomeQ, InverseEllipticNomeQ,
    JacobiSN, JacobiCN, JacobiDN, JacobiCD, JacobiSD, JacobiND, JacobiDC, JacobiNC, JacobiSC, JacobiNS, JacobiDS, JacobiCS,
    JacobiAmplitude, JacobiZeta, JacobiEpsilon, InverseJacobiSN, InverseJacobiCN, InverseJacobiDN,
    NevilleThetaS, NevilleThetaC, NevilleThetaD, NevilleThetaN,
    WeierstrassP, WeierstrassPPrime, WeierstrassZeta, WeierstrassSigma, WeierstrassHalfPeriods, InverseWeierstrassP,
    DedekindEta, KleinInvariantJ, ModularLambda, SiegelTheta,
    Hypergeometric0F1, Hypergeometric1F1Regularized, WhittakerM, WhittakerW, ParabolicCylinderD, AppellF1,
    CoulombF, CoulombG, MittagLefflerE,
    ZetaZero, RiemannSiegelZ, RiemannSiegelTheta, RiemannR, PrimeZetaP, RiemannXi,
    DirichletEta, DirichletBeta, DirichletLambda, DirichletL,
    QPochhammer, QGamma, QFactorial, QBinomial, QPolyGamma, QHypergeometricPFQ,
    RamanujanTau, RamanujanTauL, RamanujanTauTheta, RamanujanTauZ,
    WignerD, ZernikeR, NorlundB, BellY,
    UnitBox, UnitTriangle, HeavisidePi, HeavisideLambda, DiscreteDelta, SquareWave, TriangleWave, SawtoothWave,
    Clip, Ramp, Unitize, Surd, ArcSinDegrees, ArcCosDegrees, ArcTanDegrees, SinDegrees, CosDegrees, TanDegrees,
    MathieuCharacteristicA, MathieuCharacteristicB, MathieuC, MathieuS, MathieuCPrime, MathieuSPrime, MathieuCharacteristicExponent,
    SpheroidalEigenvalue, SpheroidalPS, SpheroidalQS, SpheroidalPSPrime, SpheroidalQSPrime, SpheroidalS1, SpheroidalS2, SpheroidalS1Prime, SpheroidalS2Prime,
]


def register_special_functions2(session):
    for cls in CLASSES:
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{getattr(cls, 'name', None) or cls.__name__}")
