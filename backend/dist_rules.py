"""Contract-driven distribution functions.

``dist_contracts.CONTRACTS`` holds, for 90 Wolfram distribution heads, the
exact InputForm the activated 15.0.1 kernel returns for PDF / CDF /
SurvivalFunction / HazardFunction / Mean / Variance / StandardDeviation /
Median / Skewness / Kurtosis / Quantile / MomentGeneratingFunction /
CharacteristicFunction / Moment / CentralMoment / Cumulant / FactorialMoment /
DistributionDomain / DistributionParameterAssumptions with symbolic
parameters.  This module parses those strings once and installs them as
rules, so e.g. ``PDF[GammaDistribution[a, b], x]`` returns
``Piecewise[{{x^(-1 + a)/(b^a E^(x/b) Gamma[a]), x > 0}}, 0]`` just like the
real kernel, for any parameter values (symbolic or numeric; Piecewise and
the special functions then evaluate as far as they can).

Layering: these rules are installed *after* ``distributions.py`` (the
SymPy.stats based implementation) and are tried first because they carry a
head-specific pattern; whatever the table does not cover (unsupported head,
Expectation/Probability of arbitrary expressions, RandomVariate, ...) still
falls through to the SymPy implementation.

Argument-count variants (NormalDistribution[], UniformDistribution[],
CauchyDistribution[], StudentTDistribution[m, s, n], Zipf/WaringYule/
Triangular with one or two arguments) follow Usage.m of the kernel.
"""

from __future__ import annotations

import re

from mathics.core.atoms import Integer, Integer0, Integer1, Rational
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol, SymbolTrue

from dist_contracts import CONTRACTS

# Field name in the contract -> (Wolfram function, extra argument symbol in the
# stored string or None)
_FIELD_FN = {
    "pdf": ("PDF", "x"),
    "cdf": ("CDF", "x"),
    "survival": ("SurvivalFunction", "x"),
    "hazard": ("HazardFunction", "x"),
    "quantile": ("Quantile", "qq"),
    "mgf": ("MomentGeneratingFunction", "tt"),
    "cf": ("CharacteristicFunction", "tt"),
    "moment": ("Moment", "kk"),
    "central_moment": ("CentralMoment", "kk"),
    "cumulant": ("Cumulant", "kk"),
    "factorial_moment": ("FactorialMoment", "kk"),
    "mean": ("Mean", None),
    "variance": ("Variance", None),
    "std": ("StandardDeviation", None),
    "median": ("Median", None),
    "skewness": ("Skewness", None),
    "kurtosis": ("Kurtosis", None),
    "domain": ("DistributionDomain", None),
    "assumptions": ("DistributionParameterAssumptions", None),
}

# Default argument forms Wolfram accepts (Usage.m): head -> list of
# (arity, template filling in defaults)
_DEFAULTS = {
    "NormalDistribution": {0: "NormalDistribution[0, 1]"},
    "UniformDistribution": {0: "UniformDistribution[{0, 1}]"},
    "CauchyDistribution": {0: "CauchyDistribution[0, 1]"},
    "LogisticDistribution": {0: "LogisticDistribution[0, 1]"},
    "LaplaceDistribution": {0: "LaplaceDistribution[0, 1]"},
    "GumbelDistribution": {0: "GumbelDistribution[0, 1]"},
    "ExtremeValueDistribution": {0: "ExtremeValueDistribution[0, 1]"},
    "StudentTDistribution": {},
    "LogNormalDistribution": {0: "LogNormalDistribution[0, 1]"},
    "MoyalDistribution": {0: "MoyalDistribution[0, 1]"},
    "SechDistribution": {0: "SechDistribution[0, 1]"},
    "ArcSinDistribution": {0: "ArcSinDistribution[{0, 1}]"},
    "UniformSumDistribution": {},
}

_LIST_RE = re.compile(r"^\{(.*)\}$")


def _param_pattern(args: str):
    """'m, s' -> 'm_, s_';  '{a, b}, c' -> '{a_, b_}, c_'; also the list of names."""
    names = re.findall(r"[A-Za-z]\w*", args)
    pat = re.sub(r"([A-Za-z]\w*)", r"\1_", args)
    return pat, names


# Fields whose contract form is a closed expression in the order kk; Wolfram
# returns the *expanded polynomial* for integer orders (Moment[Binomial, 3] =
# n p - 3 (1-n) n p^2 + ...).  For integer kk we therefore post-process with
# Expand (Pochhammer / factorials already expand to products).
_INTEGER_ORDER = {"moment", "central_moment", "cumulant"}
_EXPAND_HEADS = re.compile(r"Hypergeometric1F1|Hypergeometric2F1|HypergeometricPFQ|BellB|HurwitzLerchPhi|HurwitzZeta|Gamma\[|BernoulliB|Pochhammer|!")


def _needs_expansion(body):
    return bool(_EXPAND_HEADS.search(body))


def _wl_rules(contract):
    """Yield (lhs, rhs) Wolfram strings for every field of one contract."""
    head, args = contract["head"], contract["args"]
    pat, names = _param_pattern(args)
    dist = f"{head}[{pat}]"
    for field, (fn, var) in _FIELD_FN.items():
        body = contract.get(field)
        if body is None:
            continue
        if var is None:
            yield f"{fn}[{dist}]", body
        elif field in _INTEGER_ORDER:
            if _needs_expansion(body):
                yield f"{fn}[{dist}, {var}_Integer]", f"MomentNormalForm[{body}]"
            yield f"{fn}[{dist}, {var}_]", body
        else:
            # The free variable in the contract string must not collide with a
            # parameter name: `x` never does (contracts are extracted with x),
            # qq/tt/kk neither.
            yield f"{fn}[{dist}, {var}_]", body
    # Integer-order moments / central moments / cumulants not in the table but
    # derivable from the moment generating function (Wolfram's own route for
    # e.g. BinomialDistribution): M^(k)(0), the derivatives of log M, and
    # E[(X - mu)^k] by the binomial theorem.
    if "mgf" in contract:
        mgf = contract["mgf"]
        if "moment" not in contract:
            yield f"Moment[{dist}, kk_Integer?NonNegative]", f"MomentFromMGF[{mgf}, tt, kk]"
        if "cumulant" not in contract:
            yield f"Cumulant[{dist}, kk_Integer?Positive]", f"CumulantFromMGF[{mgf}, tt, kk]"
        if "central_moment" not in contract and "mean" in contract:
            yield (f"CentralMoment[{dist}, kk_Integer?NonNegative]",
                   f"CentralMomentFromMGF[{mgf}, tt, kk, {contract['mean']}]")


def _std_from_variance(contract):
    return "variance" in contract and "std" not in contract


class DistributionDomain(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "domain of a distribution"


class DistributionParameterAssumptions(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "parameter assumptions of a distribution"


class HazardFunction(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "hazard function PDF/SurvivalFunction"


class MomentGeneratingFunction(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "moment generating function"


class CharacteristicFunction(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "characteristic function"


class Cumulant(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "cumulant of a distribution or data"
    rules = {
        # Sample cumulants, as Wolfram: k1 = mean, k2 = central moment 2, k3 = cm3,
        # k4 = cm4 - 3 cm2^2 (population versions, matching Cumulant[{1,2,3,4}, 2] == 5/4).
        "Cumulant[list_List, 1]": "Mean[list]",
        "Cumulant[list_List, 2]": "CentralMoment[list, 2]",
        "Cumulant[list_List, 3]": "CentralMoment[list, 3]",
        "Cumulant[list_List, 4]": "CentralMoment[list, 4] - 3 CentralMoment[list, 2]^2",
    }


class FactorialMoment(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "factorial moment"
    rules = {
        "FactorialMoment[list_List, r_Integer]": "Mean[FactorialPower[#, r]& /@ list]",
    }


class MomentData(Builtin):
    """Moment[list, r] for data (raw moment); the distribution branch lives in
    distributions.py / the contract rules."""
    name = "Moment"
    context = "System`"
    attributes = A_PROTECTED | A_READ_PROTECTED
    rules = {
        "Moment[list_List, r_]": "Mean[list^r]",
    }


class Conditioned(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "conditional event (x \\[Conditioned] cond)"


_INSTALLED = False


def register_dist_rules(session):
    """Install every contract as a Wolfram-level rule (via the session parser)."""
    global _INSTALLED
    for cls in (DistributionDomain, DistributionParameterAssumptions, HazardFunction,
                MomentGeneratingFunction, CharacteristicFunction, Cumulant,
                FactorialMoment, MomentData, Conditioned):
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{getattr(cls, 'name', None) or cls.__name__}")

    protected = {"PDF", "CDF", "SurvivalFunction", "HazardFunction", "Quantile", "Mean", "Variance",
                 "StandardDeviation", "Median", "Skewness", "Kurtosis", "Moment", "CentralMoment",
                 "Cumulant", "FactorialMoment", "MomentGeneratingFunction", "CharacteristicFunction",
                 "DistributionDomain", "DistributionParameterAssumptions", "HurwitzLerchPhi", "InverseCDF",
                 "UniformSumDistribution"}
    heads = sorted({c["head"] for c in CONTRACTS})
    # The distribution heads must exist in System` *before* the rules are
    # parsed, so that both the rule patterns (parsed in the private context
    # below) and user input resolve to the same System`Head symbol.
    for name in heads + ["Distributed", "Conditioned", "Interval", "MomentNormalForm", "MomentFromMGF",
                         "CumulantFromMGF", "CentralMomentFromMGF"]:
        session.definitions.get_definition(f"System`{name}")
        session.definitions.clear_cache(f"System`{name}")
    session.evaluate("Unprotect[" + ", ".join(sorted(protected)) + "]")
    # Everything below is evaluated inside a private context (not on
    # $ContextPath) so that the helper heads, their pattern variables and the
    # parameter symbols in the contract bodies never collide with user
    # symbols: a user's `n` stays Global`n.  System functions (Piecewise,
    # Erfc, ...) and the pre-created heads still resolve through $ContextPath.
    lines = [
        # Wolfram keeps product forms (a (1 + a) (2 + a) b^3) but expands the
        # results of special-function identities (Hypergeometric1F1 with
        # negative integer parameter, BellB, HurwitzLerchPhi, ...):
        # polynomial results are expanded (Moment[Binomial]), rational ones
        # factored (CentralMoment[Beta]).
        "MomentNormalForm[Piecewise[cases_, d_]] := Piecewise[Map[{MomentNormalForm[#[[1]]], #[[2]]}&, cases], MomentNormalForm[d]]",
        "MomentNormalForm[e_] := Module[{r = Together[Expand[e]]}, If[FreeQ[r, Plus] || Head[r] === Plus, Expand[r], If[Denominator[r] === 1, Expand[r], Factor[r]]]]",
        # HurwitzLerchPhi[z, -n, 0] = PolyLog[-n, z]: a rational function of z
        "HurwitzLerchPhi[z_, s_Integer?NonPositive, 0] := Factor[PolyLog[s, z]]",
        "MomentFromMGF[m_, t_, k_] := Expand[D[m, {t, k}] /. t -> 0]",
        "CumulantFromMGF[m_, t_, k_] := Expand[Simplify[D[Log[m], {t, k}] /. t -> 0]]",
        "CentralMomentFromMGF[m_, t_, k_, mu_] := Expand[Sum[Binomial[k, j] (-mu)^(k - j) MomentFromMGF[m, t, j], {j, 0, k}]]",
    ]
    for c in CONTRACTS:
        for lhs, rhs in _wl_rules(c):
            lines.append(f"{lhs} := {rhs}")
        if _std_from_variance(c):
            pat, _ = _param_pattern(c["args"])
            lines.append(f"StandardDeviation[{c['head']}[{pat}]] := Sqrt[{c['variance']}]")
    # InverseCDF is Quantile for the table heads
    lines.append("InverseCDF[d_?(MemberQ[{" + ", ".join(heads) + "}, Head[#]]&), q_] := Quantile[d, q]")
    # default-argument forms
    for head, forms in _DEFAULTS.items():
        for arity, full in forms.items():
            if arity == 0:
                lines.append(f"{head}[] := {full}")
    # StudentTDistribution[m, s, n] is the location-scale form (Usage.m)
    lines.append("PDF[StudentTDistribution[m_, s_, n_], x_] := (n/(n + (-m + x)^2/s^2))^((1 + n)/2)/(Sqrt[n]*s*Beta[n/2, 1/2])")
    lines.append("CDF[StudentTDistribution[m_, s_, n_], x_] := CDF[StudentTDistribution[n], (x - m)/s]")
    lines.append("Mean[StudentTDistribution[m_, s_, n_]] := Piecewise[{{m, n > 1}}, Indeterminate]")
    lines.append("Variance[StudentTDistribution[m_, s_, n_]] := Piecewise[{{(n*s^2)/(-2 + n), n > 2}}, Indeterminate]")
    lines.append("Median[StudentTDistribution[m_, s_, n_]] := m")
    lines.append("DistributionDomain[StudentTDistribution[m_, s_, n_]] := Interval[{-Infinity, Infinity}]")
    # UniformSumDistribution[n] == UniformSumDistribution[n, {0, 1}]
    lines.append("UniformSumDistribution[n_] := UniformSumDistribution[n, {0, 1}]")
    session.evaluate('Begin["MathematicsNotebook`Distributions`"]')
    try:
        for line in lines:
            session.evaluate(line)
    finally:
        session.evaluate("End[]")
    session.evaluate("Protect[" + ", ".join(sorted(protected)) + "]")
    for name in list(protected) + heads + ["InverseCDF", "Conditioned", "Distributed"]:
        session.definitions.clear_cache(f"System`{name}")
    # A trailing `;` in the registration code leaves CompoundExpression's
    # predetermined_out set; it would otherwise become the user's Out[1].
    session.evaluation.predetermined_out = None
    session.last_result = None
    _INSTALLED = True
