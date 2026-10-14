"""Derived distributions, generic Expectation/Probability via the PDF, and
descriptive-statistics / hypothesis-test functions.

Reference forms come from the activated Wolfram 15.0.1 kernel
(wolfram-re-round2/oracle/dist-derived-wolfram.txt).  Everything here is
expressed as Wolfram-language rules evaluated at registration (so the
symbolic machinery -- Integrate with Piecewise PDFs, Sum over discrete
supports, Erf/Erfc forms -- is the notebook's own) plus a few Python builtins
for the numeric tests that need scipy.stats.

Derived heads:
  TruncatedDistribution[{a, b}, d]      PDF = PDF[d]/(CDF[d,b]-CDF[d,a]) on [a,b]
  MixtureDistribution[{w..}, {d..}]      weighted PDF / CDF / moments
  TransformedDistribution[f[x], x \\[Distributed] d]   (monotone f and x^2)
  ProductDistribution[d1, d2, ...]       independent product
  ProbabilityDistribution[pdf, {x, a, b}] / {x, a, b, 1} (discrete)
  EmpiricalDistribution[data], OrderDistribution, MarginalDistribution,
  ParameterMixtureDistribution (Poisson/Gamma -> NegativeBinomial),
  CompoundPoissonDistribution (Mean), CensoredDistribution (Mean),
  MultinormalDistribution / BinormalDistribution / MultinomialDistribution /
  DirichletDistribution (PDF, Mean, Covariance, Variance),
  UniformSumDistribution PDF for integer n.

Expectation / Probability for any head with a PDF (continuous: Integrate the
PDF over the domain; discrete: Sum), incl. Conditioned.

Statistics: Entropy, MeanDeviation, MedianDeviation, InterquartileRange,
QuartileDeviation, QuartileSkewness, RootMeanSquare, ContraharmonicMean,
TrimmedMean, WinsorizedMean, Commonest, Standardize, Rescale, BinCounts,
BinLists, Covariance (matrix), KendallTau, SpearmanRho, CorrelationDistance,
Likelihood, LogLikelihood, ExpectedValue, DistributionParameterQ,
FindDistributionParameters, EstimatedDistribution, InverseSurvivalFunction,
NExpectation, NProbability, and the tests TTest, ZTest, VarianceTest, SignTest,
SignedRankTest, KolmogorovSmirnovTest, ShapiroWilkTest, AndersonDarlingTest,
PearsonChiSquareTest, IndependenceTest, LocationTest,
LocationEquivalenceTest, DistributionFitTest (p-values, as Wolfram returns).
"""

from __future__ import annotations

import math

from mathics.core.atoms import Integer, MachineReal, Real, String
from mathics.core.attributes import A_HOLD_REST, A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol, SymbolFalse, SymbolTrue

from dist_contracts import CONTRACTS

_DISCRETE = sorted({c["head"] for c in CONTRACTS if ";;" in c["domain"]})
_CONTINUOUS = sorted({c["head"] for c in CONTRACTS if ";;" not in c["domain"]})

# ---------------------------------------------------------------- WL rules --

WL_RULES = r"""
(* ---------- helpers ---------- *)
DiscreteDistributionQ[d_] := MemberQ[{@@DISCRETE@@}, Head[d]] || MatchQ[d, ProbabilityDistribution[_, {_, _, _, _}]] || MatchQ[d, EmpiricalDistribution[_]] || MatchQ[d, TruncatedDistribution[_, dd_] /; DiscreteDistributionQ[dd]];
ContinuousDistributionQ[d_] := MemberQ[{@@CONTINUOUS@@}, Head[d]] || MatchQ[d, ProbabilityDistribution[_, {_, _, _}]] || MatchQ[d, TruncatedDistribution[_, dd_] /; ContinuousDistributionQ[dd]] || MatchQ[d, MixtureDistribution[_, {__?ContinuousDistributionQ}]] || MatchQ[d, TransformedDistribution[_, _]];
KnownDistributionQ[d_] := DiscreteDistributionQ[d] || ContinuousDistributionQ[d];
DomainBounds[d_] := Module[{dom = DistributionDomain[d]},
  Which[Head[dom] === Interval, dom[[1]], Head[dom] === Span, {dom[[1]], dom[[2]]}, True, {-Infinity, Infinity}]];
PiecewiseSupport[Piecewise[cases_, 0]] := Or @@ (#[[2]]& /@ cases);

(* ---------- TruncatedDistribution ---------- *)
DistributionDomain[TruncatedDistribution[{a_, b_}, d_]] := If[DiscreteDistributionQ[d], Span[a, b], Interval[{a, b}]];
TruncationWindow[x_, a_, b_, disc_] := Which[a === -Infinity && b === Infinity, True, b === Infinity, If[disc, x >= a, x > a], a === -Infinity, x <= b, disc, a <= x <= b, True, Inequality[a, Less, x, LessEqual, b]];
PDF[TruncatedDistribution[{a_, b_}, d_], x_] := Module[{disc = DiscreteDistributionQ[d], z, body},
  z = If[disc, CDF[d, b] - CDF[d, a - 1], CDF[d, b] - CDF[d, a]];
  body = Simplify[(PDF[d, x] /. Piecewise[{{v_, _}}, 0] :> v)/z];
  Piecewise[{{body, TruncationWindow[x, a, b, disc]}}, 0]];
CDF[TruncatedDistribution[{a_, b_}, d_], x_] := Module[{disc = DiscreteDistributionQ[d], lo, z, body},
  lo = If[disc, CDF[d, a - 1], CDF[d, a]]; z = CDF[d, b] - lo;
  body = Simplify[((CDF[d, x] /. Piecewise[{{v_, _}, ___}, 0] :> v) - lo)/z] /. (1 - Erfc[e_]) :> Erf[e] /. (Erfc[e_]/2 - 1/2) :> -Erf[e]/2;
  If[b === Infinity,
    Piecewise[{{body, TruncationWindow[x, a, b, disc]}}, 0],
    Piecewise[{{body, TruncationWindow[x, a, b, disc] && x < b}, {1, x >= b}}, 0]]];
(* ---------- CensoredDistribution:  E[Clip[X, {a, b}]] = a F(a) + E[X; a<X<b] + b (1 - F(b)) ---------- *)
Mean[CensoredDistribution[{a_, b_}, d_]] := Module[{Z = CDF[d, b] - CDF[d, a], inner},
  inner = Z Mean[TruncatedDistribution[{a, b}, d]];
  Simplify[If[a === -Infinity, 0, a CDF[d, a]] + inner + If[b === Infinity, 0, b (1 - CDF[d, b])]]];

(* ---------- MixtureDistribution ---------- *)
DistributionDomain[MixtureDistribution[w_List, ds_List]] := DistributionDomain[First[ds]];
PDF[MixtureDistribution[w_List, ds_List], x_] := Simplify[Total[w * (PDF[#, x]& /@ ds)]/Total[w]];
CDF[MixtureDistribution[w_List, ds_List], x_] := Simplify[Total[w * (CDF[#, x]& /@ ds)]/Total[w]];
Mean[MixtureDistribution[w_List, ds_List]] := Simplify[Total[w * (Mean /@ ds)]/Total[w]];
Variance[MixtureDistribution[w_List, ds_List]] := Module[{m = Mean[MixtureDistribution[w, ds]]},
  Simplify[Total[w * ((Variance[#] + Mean[#]^2)& /@ ds)]/Total[w] - m^2]];

(* ---------- TransformedDistribution ---------- *)
SetAttributes[TransformedDistribution, HoldAll];
(* affine transforms and x^2 / Exp[x] of a continuous variable: change of variables *)
PDF[TransformedDistribution[a_. x_Symbol + b_., Distributed[x_Symbol, d_]], y_] /; FreeQ[{a, b}, x] && ContinuousDistributionQ[d] :=
  Simplify[(PDF[d, x] /. x -> (y - b)/a) / Abs[a]];
PDF[TransformedDistribution[x_Symbol^2, Distributed[x_Symbol, d_]], y_] /; ContinuousDistributionQ[d] :=
  Piecewise[{{Simplify[((PDF[d, x] /. x -> Sqrt[y]) + (PDF[d, x] /. x -> -Sqrt[y]))/(2 Sqrt[y]), y > 0], y > 0}}, 0];
PDF[TransformedDistribution[Exp[x_Symbol], Distributed[x_Symbol, d_]], y_] /; ContinuousDistributionQ[d] :=
  Piecewise[{{Simplify[(PDF[d, x] /. x -> Log[y])/y, y > 0], y > 0}}, 0];
PDF[TransformedDistribution[x_Symbol + y_Symbol, Distributed[{x_Symbol, y_Symbol}, ProductDistribution[NormalDistribution[m1_, s1_], NormalDistribution[m2_, s2_]]]], z_] :=
  PDF[NormalDistribution[m1 + m2, Sqrt[s1^2 + s2^2]], z];
TransformedDistribution[a_. x_Symbol + b_., Distributed[x_Symbol, NormalDistribution[m_, s_]]] /; FreeQ[{a, b}, x] && a =!= 0 := NormalDistribution[a m + b, Abs[a] s];
TransformedDistribution[Exp[x_Symbol], Distributed[x_Symbol, NormalDistribution[m_, s_]]] := LogNormalDistribution[m, s];
TransformedDistribution[x_Symbol + y_Symbol, Distributed[{x_Symbol, y_Symbol}, ProductDistribution[NormalDistribution[m1_, s1_], NormalDistribution[m2_, s2_]]]] := NormalDistribution[m1 + m2, Sqrt[s1^2 + s2^2]];
Mean[TransformedDistribution[f_, Distributed[x_Symbol, d_]]] := Expectation[f, Distributed[x, d]];
Mean[TransformedDistribution[f_, Distributed[xs_List, d_]]] := Expectation[f, Distributed[xs, d]];
Variance[TransformedDistribution[f_, Distributed[x_Symbol, d_]]] := Simplify[Expectation[f^2, Distributed[x, d]] - Expectation[f, Distributed[x, d]]^2];
Variance[TransformedDistribution[f_, Distributed[xs_List, d_]]] := Simplify[Expectation[f^2, Distributed[xs, d]] - Expectation[f, Distributed[xs, d]]^2];

(* ---------- ProductDistribution ---------- *)
PDF[ProductDistribution[ds__], xs_List] := Module[{res}, res = Times @@ MapThread[PDF, {{ds}, xs}]; MergePiecewise[res]];
Mean[ProductDistribution[ds__]] := Mean /@ {ds};
Variance[ProductDistribution[ds__]] := Variance /@ {ds};
MergePiecewise[e_] := Module[{conds = Cases[e, Piecewise[{{_, c_}}, 0] :> c, {0, Infinity}], body},
  If[conds === {}, e,
    body = e /. Piecewise[{{v_, _}}, 0] :> v;
    Piecewise[{{Simplify[body], And @@ conds}}, 0]]];

(* ---------- ProbabilityDistribution ---------- *)
SetAttributes[ProbabilityDistribution, HoldRest];
DistributionDomain[ProbabilityDistribution[_, {x_, a_, b_}]] := Interval[{a, b}];
DistributionDomain[ProbabilityDistribution[_, {x_, a_, b_, 1}]] := Span[a, b];
PDF[ProbabilityDistribution[pdf_, {x_, a_, b_}], y_] := Piecewise[{{pdf /. x -> y, a < y < b}}, 0];
PDF[ProbabilityDistribution[pdf_, {x_, a_, b_}, Method -> "Normalize"], y_] := Module[{z = Integrate[pdf, {x, a, b}]}, Piecewise[{{Simplify[pdf/z] /. x -> y, a < y < b}}, 0]];
PDF[ProbabilityDistribution[pdf_, {x_, a_, b_, 1}], y_] := Piecewise[{{pdf /. x -> y, a <= y <= b}}, 0];
CDF[ProbabilityDistribution[pdf_, {x_, a_, b_}], y_] := Module[{t}, Piecewise[{{1, y >= b}, {Integrate[pdf /. x -> t, {t, a, y}], a < y < b}}, 0]];
CDF[ProbabilityDistribution[pdf_, {x_, a_, b_, 1}], y_] := Module[{t}, Piecewise[{{1, y >= b}, {Sum[pdf /. x -> t, {t, a, Floor[y]}], a <= y < b}}, 0]];
Mean[ProbabilityDistribution[pdf_, {x_, a_, b_}]] := Integrate[x pdf, {x, a, b}];
Mean[ProbabilityDistribution[pdf_, {x_, a_, b_, 1}]] := Sum[x pdf, {x, a, b}];
Variance[ProbabilityDistribution[pdf_, {x_, a_, b_}]] := Simplify[Integrate[x^2 pdf, {x, a, b}] - Integrate[x pdf, {x, a, b}]^2];
Variance[ProbabilityDistribution[pdf_, {x_, a_, b_, 1}]] := Simplify[Sum[x^2 pdf, {x, a, b}] - Sum[x pdf, {x, a, b}]^2];

(* ---------- EmpiricalDistribution ---------- *)
DistributionDomain[EmpiricalDistribution[data_List]] := Union[data];
PDF[EmpiricalDistribution[data_List], x_] := Module[{t = Tally[Sort[data]], n = Length[data]}, Total[(#[[2]]/n Boole[#[[1]] == x])& /@ t]];
CDF[EmpiricalDistribution[data_List], x_] := Module[{t = Tally[Sort[data]], n = Length[data]}, Total[(#[[2]]/n Boole[#[[1]] <= x])& /@ t]];
Mean[EmpiricalDistribution[data_List]] := Mean[data];
Variance[EmpiricalDistribution[data_List]] := Mean[(data - Mean[data])^2];
Median[EmpiricalDistribution[data_List]] := Quantile[data, 1/2];
Boole[True] := 1; Boole[False] := 0;

(* ---------- OrderDistribution ---------- *)
PDF[OrderDistribution[{d_, n_Integer}, k_Integer], x_] := Module[{f = PDF[d, x] /. Piecewise[{{v_, _}}, 0] :> v, F = CDF[d, x] /. Piecewise[{{v_, _}, ___}, 0] :> v, dom = DomainBounds[d]},
  Piecewise[{{Simplify[n! / ((k - 1)! (n - k)!) F^(k - 1) (1 - F)^(n - k) f], dom[[1]] < x < dom[[2]]}}, 0]];
Mean[OrderDistribution[{UniformDistribution[{a_, b_}], n_Integer}, k_Integer]] := a + (b - a) k/(n + 1);
(* middle order statistic of a symmetric distribution: the centre of symmetry *)
Mean[OrderDistribution[{d_, n_Integer}, k_Integer]] /; 2 k == n + 1 && MemberQ[{NormalDistribution, CauchyDistribution, LogisticDistribution, LaplaceDistribution, StudentTDistribution, SechDistribution, UniformDistribution}, Head[d]] := Median[d];

(* ---------- MarginalDistribution / ParameterMixture / CompoundPoisson ---------- *)
MarginalDistribution[MultinormalDistribution[mu_List, sigma_List], i_Integer] := NormalDistribution[mu[[i]], Sqrt[sigma[[i, i]]]];
MarginalDistribution[BinormalDistribution[{m1_, m2_}, {s1_, s2_}, r_], 1] := NormalDistribution[m1, s1];
MarginalDistribution[BinormalDistribution[{m1_, m2_}, {s1_, s2_}, r_], 2] := NormalDistribution[m2, s2];
MarginalDistribution[ProductDistribution[ds__], i_Integer] := {ds}[[i]];
ParameterMixtureDistribution[PoissonDistribution[l_Symbol], Distributed[l_Symbol, GammaDistribution[a_, b_]]] := NegativeBinomialDistribution[a, 1/(1 + b)];
ParameterMixtureDistribution[BinomialDistribution[n_, p_Symbol], Distributed[p_Symbol, BetaDistribution[a_, b_]]] := BetaBinomialDistribution[a, b, n];
Mean[ParameterMixtureDistribution[d_, Distributed[p_Symbol, dp_]]] := Expectation[Mean[d], Distributed[p, dp]];
Mean[CompoundPoissonDistribution[l_, d_]] := l Mean[d];
Variance[CompoundPoissonDistribution[l_, d_]] := l (Variance[d] + Mean[d]^2);

(* ---------- multivariate ---------- *)
PDF[MultinormalDistribution[mu_List, sigma_List], xs_List] := Module[{d = Length[mu], v = xs - mu},
  Simplify[Exp[-1/2 v . Inverse[sigma] . v] / ((2 Pi)^(d/2) Sqrt[Det[sigma]])]];
Mean[MultinormalDistribution[mu_List, sigma_List]] := mu;
Covariance[MultinormalDistribution[mu_List, sigma_List]] := sigma;
Variance[MultinormalDistribution[mu_List, sigma_List]] := Diagonal[sigma];
DistributionDomain[MultinormalDistribution[mu_List, sigma_List]] := Table[Interval[{-Infinity, Infinity}], {Length[mu]}];
PDF[BinormalDistribution[{m1_, m2_}, {s1_, s2_}, r_], {x_, y_}] := Exp[-(((x - m1)^2/s1^2) - (2 r (x - m1) (y - m2))/(s1 s2) + ((y - m2)^2/s2^2))/(2 (1 - r^2))]/(2 Pi Sqrt[1 - r^2] s1 s2);
PDF[BinormalDistribution[r_], {x_, y_}] := PDF[BinormalDistribution[{0, 0}, {1, 1}, r], {x, y}];
Mean[BinormalDistribution[{m1_, m2_}, {s1_, s2_}, r_]] := {m1, m2};
Covariance[BinormalDistribution[{m1_, m2_}, {s1_, s2_}, r_]] := {{s1^2, r s1 s2}, {r s1 s2, s2^2}};
Variance[BinormalDistribution[{m1_, m2_}, {s1_, s2_}, r_]] := {s1^2, s2^2};
PDF[MultinomialDistribution[n_, ps_List], xs_List] := Piecewise[{{Multinomial @@ xs Times @@ (ps^xs), Total[xs] == n && And @@ (# >= 0& /@ xs)}}, 0];
Mean[MultinomialDistribution[n_, ps_List]] := n ps;
Variance[MultinomialDistribution[n_, ps_List]] := n ps (1 - ps);
Mean[DirichletDistribution[as_List]] := Most[as]/Total[as];
PDF[DirichletDistribution[as_List], xs_List] /; Length[xs] == Length[as] - 1 := Module[{xl = Append[xs, 1 - Total[xs]]},
  Piecewise[{{Gamma[Total[as]]/Times @@ (Gamma /@ as) Times @@ (xl^(as - 1)), And @@ (# > 0& /@ xl)}}, 0]];
Mean[MultivariatePoissonDistribution[m_, ls_List]] := m + ls;
Mean[NegativeMultinomialDistribution[n_, ps_List]] := n ps/(1 - Total[ps]);
Mean[MultivariateHypergeometricDistribution[n_, ms_List]] := n ms/Total[ms];
Mean[MultivariateTDistribution[sigma_List, n_]] := Piecewise[{{Table[0, {Length[sigma]}], n > 1}}, Indeterminate];
Mean[CopulaDistribution[_, ds_List]] := Mean /@ ds;
Mean[StandbyDistribution[d_, ds_List]] := Mean[d] + Total[Mean /@ ds];
Mean[StandbyDistribution[d_, {ds__}, _]] := Mean[d] + Total[Mean /@ {ds}];

(* ---------- UniformSumDistribution PDF (Irwin-Hall) ---------- *)
PDF[UniformSumDistribution[n_Integer, {0, 1}], x_] /; n >= 1 := Piecewise[Join[{{0, x < 0}},
  Table[{Simplify[Sum[(-1)^k Binomial[n, k] (x - k)^(n - 1), {k, 0, j}]/(n - 1)!], If[j < n - 1, Inequality[j, LessEqual, x, Less, j + 1], j <= x <= j + 1]}, {j, 0, n - 1}]], 0];
CDF[UniformSumDistribution[n_Integer, {0, 1}], x_] /; n >= 1 := Piecewise[Join[{{0, x < 0}, {1, x > n}},
  Table[{Simplify[Sum[(-1)^k Binomial[n, k] (x - k)^n, {k, 0, j}]/n!], Inequality[j, LessEqual, x, Less, j + 1]}, {j, 0, n - 1}]], 0];

(* ---------- StudentT closed forms for small integer n ---------- *)
CDF[StudentTDistribution[1], x_] := 1/2 + ArcTan[x]/Pi;
CDF[StudentTDistribution[2], x_] := 1/2 + x/(2 Sqrt[2] Sqrt[1 + x^2/2]);
PDF[StudentTDistribution[1], x_] := 1/(Pi (1 + x^2));

(* ---------- Expectation / Probability without integration ----------
   Wolfram answers these from the distribution's moments, MGF and CDF, which
   is what the contract table provides; symbolic integration (sympy) is far
   too slow for Gaussian-type densities, so it is only the last resort (the
   sympy.stats builtin that these rules sit in front of).            *)
PolyExpectation[f_, d_, x_Symbol] := Module[{cl, r},
  If[!PolynomialQ[f, x], Return[$Failed]];
  cl = CoefficientList[Expand[f], x];
  r = Sum[cl[[i + 1]] If[i == 0, 1, Moment[d, i]], {i, 0, Length[cl] - 1}];
  If[FreeQ[r, Moment], MomentNormalForm[r], $Failed]];
ExpExpectation[Exp[a_. x_Symbol + b_.], d_, x_Symbol] := Module[{m = MomentGeneratingFunction[d, a]},
  If[FreeQ[m, MomentGeneratingFunction], Simplify[Exp[b] m], $Failed]];
ExpExpectation[t_^(x_Symbol), d_, x_Symbol] := ExpExpectation[Exp[Log[t] x], d, x] /. Exp[Log[t] y_] :> t^y;
ExpExpectation[_, _, _] := $Failed;
ClosedExpectation[f_, d_, x_Symbol] := Module[{r},
  r = PolyExpectation[f, d, x];
  If[r === $Failed, r = ExpExpectation[f, d, x]];
  If[r === $Failed && Head[f] === Times, r = Module[{parts = List @@ f, poly, rest},
     poly = Select[parts, PolynomialQ[#, x]&]; rest = Complement[parts, poly];
     If[Length[rest] == 1 && MatchQ[First[rest], Exp[_. x + _.]],
       Module[{a = Coefficient[Log[First[rest]], x], b = Log[First[rest]] /. x -> 0, mg, t},
         mg = MomentGeneratingFunction[d, t];
         If[FreeQ[mg, MomentGeneratingFunction],
           Simplify[Exp[b] (Sum[CoefficientList[Expand[Times @@ poly], x][[i + 1]] D[mg, {t, i}], {i, 0, Exponent[Times @@ poly, x]}] /. t -> a)], $Failed]],
       $Failed]]];
  r];
(* probabilities of intervals from the CDF; discrete CDF is right-continuous *)
IntervalProbability[d_, lo_, hi_, loOpen_, hiOpen_] := Module[{disc = DiscreteDistributionQ[d], Fhi, Flo},
  Fhi = If[hi === Infinity, 1, If[disc && hiOpen, CDF[d, hi - 1], CDF[d, hi]]];
  Flo = If[lo === -Infinity, 0, If[disc && !loOpen, CDF[d, lo - 1], CDF[d, lo]]];
  If[FreeQ[{Fhi, Flo}, CDF], PiecewiseDifference[Fhi, Flo], $Failed]];
(* 1 - Piecewise[{{v, c}}, 0]  ->  Piecewise[{{1 - v, c}}, 1], keeping the case structure Wolfram shows *)
PiecewiseDifference[a_, Piecewise[{{v_, c_}}, 0]] := Piecewise[{{Simplify[a - v], c}}, a];
PiecewiseDifference[Piecewise[{{v_, c_}}, 0], b_] := Piecewise[{{Simplify[v - b], c}}, Simplify[-b]];
PiecewiseDifference[a_, b_] := Simplify[a - b];
RegionProbability[x_Symbol == v_, d_, x_] := If[DiscreteDistributionQ[d], Assuming[ParamAssumptions[d], Simplify[PDF[d, v]]], 0];
ParamAssumptions[d_] := Module[{a = DistributionParameterAssumptions[d]}, If[Head[a] === DistributionParameterAssumptions, True, a]];
(* canonicalise an event in x to bounds: Abs[x - c] < r -> c - r < x < c + r,
   a < x < b chains, And of bounds; everything else is left to RegionProbability *)
CanonicalEvent[Abs[e_] < r_, x_] := And[CanonicalEvent[-r < e, x], CanonicalEvent[e < r, x]];
CanonicalEvent[Abs[e_] <= r_, x_] := And[CanonicalEvent[-r <= e, x], CanonicalEvent[e <= r, x]];
CanonicalEvent[Abs[e_] > r_, x_] := Or[CanonicalEvent[e > r, x], CanonicalEvent[e < -r, x]];
CanonicalEvent[Abs[e_] >= r_, x_] := Or[CanonicalEvent[e >= r, x], CanonicalEvent[e <= -r, x]];
(* linear relations  lhs ~ rhs  with x on either side: solve for x *)
CanonicalEvent[(rel : (Less | LessEqual | Greater | GreaterEqual))[lhs_, rhs_], x_] /; !MatchQ[lhs, x] && !MatchQ[rhs, x] && PolynomialQ[lhs - rhs, x] && Exponent[lhs - rhs, x] == 1 :=
  Module[{e = Expand[lhs - rhs], a, b},
    a = Coefficient[e, x, 1]; b = Coefficient[e, x, 0];
    (* a x + b ~ 0 *)
    Which[a === 0, rel[b, 0], TrueQ[a > 0], rel[x, -b/a], TrueQ[a < 0], FlipRel[rel][x, -b/a], True, rel[lhs, rhs]]];
FlipRel[Less] = Greater; FlipRel[LessEqual] = GreaterEqual; FlipRel[Greater] = Less; FlipRel[GreaterEqual] = LessEqual;
CanonicalEvent[c_And, x_] := And @@ (CanonicalEvent[#, x]& /@ (List @@ c));
CanonicalEvent[c_Or, x_] := Or @@ (CanonicalEvent[#, x]& /@ (List @@ c));
CanonicalEvent[Inequality[a_, Less, x_, Less, b_], x_] := And[x > a, x < b];
CanonicalEvent[Inequality[a_, LessEqual, x_, Less, b_], x_] := And[x >= a, x < b];
CanonicalEvent[Inequality[a_, Less, x_, LessEqual, b_], x_] := And[x > a, x <= b];
CanonicalEvent[Inequality[a_, LessEqual, x_, LessEqual, b_], x_] := And[x >= a, x <= b];
CanonicalEvent[c_, x_] := c;
EventProbability[c_, d_, x_Symbol] := Module[{reg, r},
  reg = CanonicalEvent[c, x];
  r = RegionProbability[reg, d, x];
  If[r === $Failed, r, Assuming[ParamAssumptions[d], SimplifyBranches[ExpandRegularized[r]]]]];
(* Wolfram's Probability expands GammaRegularized with integer first argument
   into the finite exponential sum: Q(n, z) = E^-z Sum z^k/k! *)
ExpandRegularized[e_] := e /. {GammaRegularized[n_Integer?Positive, z_] :> Exp[-z] Sum[z^k/k!, {k, 0, n - 1}],
                               GammaRegularized[n_Integer?Positive, 0, z_] :> 1 - Exp[-z] Sum[z^k/k!, {k, 0, n - 1}]};
(* Simplify applied inside Piecewise branches; whole-Piecewise Simplify in
   Mathics drops the case structure *)
SimplifyBranches[Piecewise[cases_, d_]] := Piecewise[Map[{Simplify[#[[1]]], #[[2]]}&, cases], Simplify[d]];
SimplifyBranches[e_] := Simplify[e];
RegionProbability[False, d_, x_] := 0;
RegionProbability[True, d_, x_] := 1;
RegionProbability[disj_Or, d_, x_] := Module[{ps = RegionProbability[#, d, x]& /@ (List @@ disj)}, If[FreeQ[ps, $Failed], Simplify[Total[ps]], $Failed]];
RegionProbability[x_Symbol < hi_, d_, x_] := IntervalProbability[d, -Infinity, hi, True, True];
RegionProbability[x_Symbol <= hi_, d_, x_] := IntervalProbability[d, -Infinity, hi, True, False];
RegionProbability[x_Symbol > lo_, d_, x_] := IntervalProbability[d, lo, Infinity, True, True];
RegionProbability[x_Symbol >= lo_, d_, x_] := IntervalProbability[d, lo, Infinity, False, True];
RegionProbability[lo_ < x_Symbol, d_, x_] := IntervalProbability[d, lo, Infinity, True, True];
RegionProbability[lo_ <= x_Symbol, d_, x_] := IntervalProbability[d, lo, Infinity, False, True];
RegionProbability[hi_ > x_Symbol, d_, x_] := IntervalProbability[d, -Infinity, hi, True, True];
RegionProbability[hi_ >= x_Symbol, d_, x_] := IntervalProbability[d, -Infinity, hi, True, False];
RegionProbability[Inequality[lo_, Less, x_Symbol, Less, hi_], d_, x_] := IntervalProbability[d, lo, hi, True, True];
RegionProbability[Inequality[lo_, LessEqual, x_Symbol, Less, hi_], d_, x_] := IntervalProbability[d, lo, hi, False, True];
RegionProbability[Inequality[lo_, Less, x_Symbol, LessEqual, hi_], d_, x_] := IntervalProbability[d, lo, hi, True, False];
RegionProbability[Inequality[lo_, LessEqual, x_Symbol, LessEqual, hi_], d_, x_] := IntervalProbability[d, lo, hi, False, False];
RegionProbability[Less[lo_, x_Symbol, hi_], d_, x_] := IntervalProbability[d, lo, hi, True, True];
RegionProbability[LessEqual[lo_, x_Symbol, hi_], d_, x_] := IntervalProbability[d, lo, hi, False, False];
RegionProbability[Greater[hi_, x_Symbol, lo_], d_, x_] := IntervalProbability[d, lo, hi, True, True];
RegionProbability[GreaterEqual[hi_, x_Symbol, lo_], d_, x_] := IntervalProbability[d, lo, hi, False, False];
(* And of one-sided bounds: keep the tightest; two lower bounds whose order
   is undecidable symbolically give up *)
(* each one-sided bound -> {"lo"|"hi", value, open?}; a chain is reduced to its tightest bounds *)
BoundOf[x_, x_ > v_] := {"lo", v, True};  BoundOf[x_, x_ >= v_] := {"lo", v, False};
BoundOf[x_, v_ < x_] := {"lo", v, True};  BoundOf[x_, v_ <= x_] := {"lo", v, False};
BoundOf[x_, x_ < v_] := {"hi", v, True};  BoundOf[x_, x_ <= v_] := {"hi", v, False};
BoundOf[x_, v_ > x_] := {"hi", v, True};  BoundOf[x_, v_ >= x_] := {"hi", v, False};
BoundOf[_, _] := $Failed;
RegionProbability[conj_And, d_, x_] := Module[{bs = BoundOf[x, #]& /@ (List @@ conj), los, his, lo, hi},
  If[MemberQ[bs, $Failed], Return[$Failed]];
  los = Cases[bs, {"lo", v_, o_} :> {v, o}]; his = Cases[bs, {"hi", v_, o_} :> {v, o}];
  lo = TightestBound[los, Max]; hi = TightestBound[his, Min];
  If[lo === $Failed || hi === $Failed, $Failed,
    IntervalProbability[d, If[lo === None, -Infinity, lo[[1]]], If[hi === None, Infinity, hi[[1]]], If[lo === None, True, lo[[2]]], If[hi === None, True, hi[[2]]]]]];
TightestBound[{}, _] := None;
TightestBound[{b_}, _] := b;
TightestBound[bs_List, f_] := Module[{vals = bs[[All, 1]], best},
  If[!VectorQ[vals, NumericQ], Return[$Failed]];
  best = f[vals];
  First[Select[bs, #[[1]] == best&]]];
RegionProbability[_, _, _] := $Failed;
(* Mathics does not support `body /; cond` inside Module, so the public rules
   use a whole-definition condition with a side-effect temp (tmp$). *)
Expectation[f_, Distributed[x_Symbol, d_?KnownDistributionQ]] := tmp$ /; (tmp$ = ClosedExpectation[f, d, x]) =!= $Failed;
Expectation[Conditioned[f_, cond_], Distributed[x_Symbol, d_?KnownDistributionQ]] := tmp$ /; (tmp$ = ConditionalExpectation[f, cond, d, x]) =!= $Failed;
ConditionalExpectation[f_, cond_, d_, x_] := Module[{t = TruncatedByCondition[cond, d, x]}, If[t === $Failed, $Failed, ClosedExpectation[f, t, x]]];
Probability[cond_, Distributed[x_Symbol, d_?KnownDistributionQ]] := tmp$ /; (tmp$ = EventProbability[cond, d, x]) =!= $Failed;
Probability[Conditioned[ev_, cond_], Distributed[x_Symbol, d_?KnownDistributionQ]] := tmp$ /; (tmp$ = ConditionalProbability[ev, cond, d, x]) =!= $Failed;
ConditionalProbability[ev_, cond_, d_, x_] := Module[{num = EventProbability[ev && cond, d, x], den = EventProbability[cond, d, x]},
  If[num === $Failed || den === $Failed || den === 0, $Failed, Simplify[num/den]]];
TruncatedByCondition[cond_, d_, x_Symbol] := Module[{reg = CanonicalEvent[cond, x]},
  Switch[reg,
    x > _, TruncatedDistribution[{reg[[2]], Infinity}, d], x >= _, TruncatedDistribution[{reg[[2]], Infinity}, d],
    x < _, TruncatedDistribution[{-Infinity, reg[[2]]}, d], x <= _, TruncatedDistribution[{-Infinity, reg[[2]]}, d],
    _ < x, TruncatedDistribution[{reg[[1]], Infinity}, d], _ <= x, TruncatedDistribution[{reg[[1]], Infinity}, d],
    And[x > _, x < _], TruncatedDistribution[{reg[[1, 2]], reg[[2, 2]]}, d],
    And[x >= _, x <= _], TruncatedDistribution[{reg[[1, 2]], reg[[2, 2]]}, d],
    _, $Failed]];
(* truncated moments: the conditional density is PDF/Z on the window; use the
   closed-form moments of the truncated normal / exponential, else fail *)
Moment[TruncatedDistribution[{a_, b_}, NormalDistribution[m_, s_]], 1] := Module[{al = (a - m)/s, be = (b - m)/s, phi, Z},
  phi[z_] := If[z === Infinity || z === -Infinity, 0, Exp[-z^2/2]/Sqrt[2 Pi]];
  Z = CDF[NormalDistribution[0, 1], be] - CDF[NormalDistribution[0, 1], al];
  Simplify[m + s (phi[al] - phi[be])/Z]];
Mean[TruncatedDistribution[{a_, b_}, NormalDistribution[m_, s_]]] := Moment[TruncatedDistribution[{a, b}, NormalDistribution[m, s]], 1];
Moment[TruncatedDistribution[{a_, b_}, NormalDistribution[m_, s_]], 2] := Module[{al = (a - m)/s, be = (b - m)/s, phi, Z, mu1},
  phi[z_] := If[z === Infinity || z === -Infinity, 0, Exp[-z^2/2]/Sqrt[2 Pi]];
  Z = CDF[NormalDistribution[0, 1], be] - CDF[NormalDistribution[0, 1], al];
  mu1 = (phi[al] - phi[be])/Z;
  Simplify[s^2 (1 + (If[al === -Infinity, 0, al phi[al]] - If[be === Infinity, 0, be phi[be]])/Z - mu1^2) + (m + s mu1)^2]];
Variance[TruncatedDistribution[{a_, b_}, NormalDistribution[m_, s_]]] := Simplify[Moment[TruncatedDistribution[{a, b}, NormalDistribution[m, s]], 2] - Moment[TruncatedDistribution[{a, b}, NormalDistribution[m, s]], 1]^2];
Moment[TruncatedDistribution[{a_, b_}, ExponentialDistribution[l_]], k_Integer] := Module[{lo = Max[a, 0], Z, t},
  Z = CDF[ExponentialDistribution[l], b] - CDF[ExponentialDistribution[l], lo];
  Simplify[Integrate[t^k l Exp[-l t], {t, lo, b}]/Z]];
Mean[TruncatedDistribution[{a_, b_}, ExponentialDistribution[l_]]] := Moment[TruncatedDistribution[{a, b}, ExponentialDistribution[l]], 1];
Mean[TruncatedDistribution[{a_, b_}, d_?DiscreteDistributionQ]] := Module[{Z = CDF[d, b] - CDF[d, a - 1]}, Simplify[Sum[k PDF[d, k], {k, a, b}]/Z]];
Variance[TruncatedDistribution[{a_, b_}, d_?DiscreteDistributionQ]] := Module[{Z = CDF[d, b] - CDF[d, a - 1], m}, m = Sum[k PDF[d, k], {k, a, b}]/Z; Simplify[Sum[k^2 PDF[d, k], {k, a, b}]/Z - m^2]];
Expectation[f_, Distributed[xs_List, MultinormalDistribution[mu_List, sigma_List]]] := tmp$ /; (tmp$ = GaussianExpectation[f, xs, mu, sigma]) =!= $Failed;
(* polynomial f of total degree <= 2:  E[x_i] = mu_i,  E[x_i x_j] = sigma_ij + mu_i mu_j *)
GaussianExpectation[f_, xs_List, mu_List, sigma_List] := Module[{terms, r},
  If[!PolynomialQ[f, xs] || Max[Total[Exponent[#, xs]]& /@ If[Head[Expand[f]] === Plus, List @@ Expand[f], {Expand[f]}]] > 2, $Failed,
    terms = If[Head[Expand[f]] === Plus, List @@ Expand[f], {Expand[f]}];
    r = Total[GaussianMonomial[#, xs, mu, sigma]& /@ terms];
    Simplify[r]]];
GaussianMonomial[t_, xs_, mu_, sigma_] := Module[{c = t /. (y_Symbol /; MemberQ[xs, y]) :> 1, exps, idx},
  exps = Exponent[t, #]& /@ xs;
  idx = Flatten[Table[ConstantArray[i, exps[[i]]], {i, Length[xs]}]];
  c * Switch[Length[idx],
    0, 1,
    1, mu[[idx[[1]]]],
    2, sigma[[idx[[1]], idx[[2]]]] + mu[[idx[[1]]]] mu[[idx[[2]]]],
    _, $Failed]];
Expectation[f_, Distributed[xs_List, ProductDistribution[ds__]]] := tmp$ /; (tmp$ = ProductExpectation[Expand[f], xs, {ds}]) =!= $Failed;
ProductExpectation[f_Plus, xs_, ds_] := Module[{ps = ProductExpectation[#, xs, ds]& /@ (List @@ f)}, If[FreeQ[ps, $Failed], Total[ps], $Failed]];
ProductExpectation[f_, xs_, ds_] := Module[{facs, c},
  c = f /. (y_Symbol /; MemberQ[xs, y]) :> 1;
  facs = Table[ClosedExpectation[Times @@ Cases[If[Head[f] === Times, List @@ f, {f}], e_ /; !FreeQ[e, xs[[i]]]], ds[[i]], xs[[i]]], {i, Length[xs]}];
  If[FreeQ[facs, $Failed], Simplify[c Times @@ facs], $Failed]];
Probability[cond_, Distributed[xs_List, d_]] := Expectation[Boole[cond], Distributed[xs, d]];
NExpectation[f_, spec_] := N[Expectation[f, spec]];
NProbability[cond_, spec_] := N[Probability[cond, spec]];
ExpectedValue[f_, d_, x_Symbol] := Expectation[f, Distributed[x, d]];

(* ---------- descriptive statistics ---------- *)
(* Wolfram keeps  -1/2 Log[2] + Log[4]  rather than collapsing to 3/2 Log[2] *)
Entropy[data_List] := Module[{t = Tally[data], n = Length[data]}, Total[(-#[[2]]/n Log[#[[2]]/n])& /@ t] /. Log[r_Rational] :> -Log[1/r] /; Numerator[r] == 1];
Entropy[b_, data_List] := Module[{t = Tally[data], n = Length[data]}, Total[(-#[[2]]/n Log[b, #[[2]]/n])& /@ t]];
MeanDeviation[data_List] := Mean[Abs[data - Mean[data]]];
MedianDeviation[data_List] := Median[Abs[data - Median[data]]];
InterquartileRange[data_List] := Module[{q = Quartiles[data]}, q[[3]] - q[[1]]];
QuartileDeviation[data_List] := Module[{q = Quartiles[data]}, (q[[3]] - q[[1]])/2];
QuartileSkewness[data_List] := Module[{q = Quartiles[data]}, (q[[1]] - 2 q[[2]] + q[[3]])/(q[[3]] - q[[1]])];
RootMeanSquare[data_List] := Sqrt[Mean[data^2]];
ContraharmonicMean[data_List] := Mean[data^2]/Mean[data];
TrimmedMean[data_List] := TrimmedMean[data, 1/20];
TrimmedMean[data_List, f_] := Module[{s = Sort[data], n = Length[data], k}, k = Floor[n f]; Mean[s[[k + 1 ;; n - k]]]];
TrimmedMean[data_List, {f1_, f2_}] := Module[{s = Sort[data], n = Length[data]}, Mean[s[[Floor[n f1] + 1 ;; n - Floor[n f2]]]]];
WinsorizedMean[data_List] := WinsorizedMean[data, 1/20];
WinsorizedMean[data_List, f_] := Module[{s = Sort[data], n = Length[data], k}, k = Floor[n f];
  If[k == 0, Mean[s], Mean[Join[Table[s[[k + 1]], {k}], s[[k + 1 ;; n - k]], Table[s[[n - k]], {k}]]]]];
Commonest[data_List] := Module[{t = Tally[data], m}, m = Max[t[[All, 2]]]; Cases[t, {v_, m} :> v]];
Commonest[data_List, n_Integer] := Take[SortBy[Tally[data], -#[[2]]&][[All, 1]], UpTo[n]];
Standardize[data_List] := (data - Mean[data])/StandardDeviation[data];
Standardize[data_List, f1_, f2_] := (data - f1[data])/f2[data];
Rescale[data_List] := Rescale[data, {Min[data], Max[data]}];
Rescale[x_, {a_, b_}] := (x - a)/(b - a);
Rescale[x_, {a_, b_}, {c_, d_}] := c + (x - a)/(b - a) (d - c);
Normalize[v_List, f_] := v/f[v];
BinCounts[data_List, {a_, b_, dx_}] := Table[Count[data, v_ /; lo <= v < lo + dx], {lo, a, b - dx, dx}];
BinCounts[data_List, dx_?NumericQ] := BinCounts[data, {Floor[Min[data], dx], Ceiling[Max[data] + dx, dx], dx}];
BinCounts[data_List] := BinCounts[data, 1];
BinLists[data_List, {a_, b_, dx_}] := Table[Cases[data, v_ /; lo <= v < lo + dx], {lo, a, b - dx, dx}];
BinLists[data_List, dx_?NumericQ] := BinLists[data, {Floor[Min[data], dx], Ceiling[Max[data] + dx, dx], dx}];
Covariance[m_List /; MatrixQ[m]] := Module[{cols = Transpose[m]}, Table[Covariance[cols[[i]], cols[[j]]], {i, Length[cols]}, {j, Length[cols]}]];
Covariance[m1_?MatrixQ, m2_?MatrixQ] := Module[{c1 = Transpose[m1], c2 = Transpose[m2]}, Table[Covariance[c1[[i]], c2[[j]]], {i, Length[c1]}, {j, Length[c2]}]];
Correlation[m_List /; MatrixQ[m]] := Module[{cols = Transpose[m]}, Table[Correlation[cols[[i]], cols[[j]]], {i, Length[cols]}, {j, Length[cols]}]];
KendallTau[x_List, y_List] := Module[{n = Length[x], s}, s = Sum[Sign[x[[i]] - x[[j]]] Sign[y[[i]] - y[[j]]], {i, 1, n}, {j, i + 1, n}]; s/Binomial[n, 2]];
Ranks[v_List] := Module[{s = Sort[v]}, (Mean[Flatten[Position[s, #]]])& /@ v];
SpearmanRho[x_List, y_List] := Correlation[Ranks[x], Ranks[y]];
CorrelationDistance[x_List, y_List] := 1 - Correlation[x, y];
Likelihood[d_, data_List] := Times @@ (PDF[d, #]& /@ data);
(* Log of a product/power/quotient expanded term by term (PowerExpand in Mathics
   does not touch Log), so LogLikelihood comes out as Wolfram prints it:
   -1/2 - Log[2] - Log[Pi],  -3 l + 2 Log[l] *)
ExpandLog[Log[a_ * b_]] := ExpandLog[Log[a]] + ExpandLog[Log[b]];
ExpandLog[Log[a_^b_]] := b ExpandLog[Log[a]];
ExpandLog[Log[E^b_]] := b;
ExpandLog[Log[Sqrt[a_]]] := ExpandLog[Log[a]]/2;
ExpandLog[Log[r_Rational]] := Log[Numerator[r]] - Log[Denominator[r]];
ExpandLog[Log[Times[a_, b__]]] := ExpandLog[Log[a]] + ExpandLog[Log[Times[b]]];
ExpandLog[Log[1]] := 0;
ExpandLog[Log[E]] := 1;
ExpandLog[e_] := e;
LogLikelihood[d_, data_List] := Module[{terms = Log[PDF[d, #]]& /@ data},
  Simplify[Expand[Total[ExpandLog /@ terms]]] /. Log[2 Pi] :> Log[2] + Log[Pi] /. Log[Pi^2] :> 2 Log[Pi]];
InverseSurvivalFunction[d_, q_] := Quantile[d, 1 - q] /. ConditionalExpression[v_, 0 <= 1 - q <= 1] :> ConditionalExpression[v, 0 <= q <= 1];
DistributionParameterQ[d_] := Module[{a = DistributionParameterAssumptions[d]},
  Which[Head[a] === DistributionParameterAssumptions, False, TrueQ[a], True, a === False, False, True, TrueQ[Simplify[a]]]];
"""


class _ScipyTest(Builtin):
    """Base for the scipy-backed hypothesis tests: returns the p-value."""
    attributes = A_PROTECTED | A_READ_PROTECTED

    @staticmethod
    def _floats(lst):
        out = []
        for el in lst.elements:
            v = el.to_python(n_evaluation=None)
            if isinstance(v, (int, float)):
                out.append(float(v))
            else:
                try:
                    out.append(float(el.to_sympy()))
                except Exception:
                    return None
        return out


def _p(v):
    return MachineReal(float(v))


class TTest(_ScipyTest):
    def eval1(self, data, evaluation):
        "TTest[data_List]"
        from scipy import stats
        if data.elements and data.elements[0].has_form("List", None):
            a, b = self._floats(data.elements[0]), self._floats(data.elements[1])
            if a is None or b is None:
                return None
            return _p(stats.ttest_ind(a, b, equal_var=True).pvalue)
        xs = self._floats(data)
        if xs is None:
            return None
        return _p(stats.ttest_1samp(xs, 0).pvalue)

    def eval2(self, data, mu, evaluation):
        "TTest[data_List, mu_?NumericQ]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        return _p(stats.ttest_1samp(xs, float(mu.to_sympy())).pvalue)


class LocationTest(_ScipyTest):
    rules = {"LocationTest[data_List]": "TTest[data]", "LocationTest[data_List, mu_]": "TTest[data, mu]"}


class LocationEquivalenceTest(_ScipyTest):
    def eval(self, data, evaluation):
        "LocationEquivalenceTest[data_List]"
        from scipy import stats
        groups = [self._floats(g) for g in data.elements]
        if any(g is None for g in groups):
            return None
        return _p(stats.f_oneway(*groups).pvalue)


class ZTest(_ScipyTest):
    def eval(self, data, evaluation):
        "ZTest[data_List]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None or len(xs) < 2:
            return None
        n = len(xs)
        mean = sum(xs) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))
        z = mean / (sd / math.sqrt(n))
        return _p(2 * stats.norm.sf(abs(z)))


class VarianceTest(_ScipyTest):
    def eval(self, data, evaluation):
        "VarianceTest[data_List]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None or len(xs) < 2:
            return None
        n = len(xs)
        mean = sum(xs) / n
        s2 = sum((x - mean) ** 2 for x in xs) / (n - 1)
        chi = (n - 1) * s2 / 1.0  # H0: variance == 1
        p = 2 * min(stats.chi2.cdf(chi, n - 1), stats.chi2.sf(chi, n - 1))
        return _p(p)


class SignTest(_ScipyTest):
    def eval(self, data, evaluation):
        "SignTest[data_List]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        pos = sum(1 for x in xs if x > 0)
        neg = sum(1 for x in xs if x < 0)
        return _p(stats.binomtest(pos, pos + neg, 0.5).pvalue)


class SignedRankTest(_ScipyTest):
    """Wolfram uses the normal approximation with continuity correction
    (SignedRankTest[{1,2,3,4,5}] == 0.0590582...)."""

    def eval(self, data, evaluation):
        "SignedRankTest[data_List]"
        return self._test(data, 0.0)

    def eval2(self, data, mu, evaluation):
        "SignedRankTest[data_List, mu_?NumericQ]"
        return self._test(data, float(mu.to_sympy()))

    def _test(self, data, mu):
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        return _p(stats.wilcoxon([x - mu for x in xs], method="approx", correction=True).pvalue)


def _fitted_normal_cdf(xs):
    from scipy import stats
    mean = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
    return stats.norm(mean, sd).cdf


def _ks_statistic(xs, cdf):
    n = len(xs)
    s = sorted(xs)
    F = [float(cdf(x)) for x in s]
    return max(max((i + 1) / n - F[i], F[i] - i / n) for i in range(n))


class KolmogorovSmirnovTest(_ScipyTest):
    """Statistic as Wolfram (D_n); p-value from the exact finite-n
    Kolmogorov distribution (scipy kstwo).  Wolfram's p-values for very small
    samples come from its own tables and differ in the 2nd-3rd digit."""

    def eval1(self, data, evaluation):
        "KolmogorovSmirnovTest[data_List]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        d = _ks_statistic(xs, _fitted_normal_cdf(xs))
        return _p(stats.kstwo.sf(d, len(xs)))

    def eval2(self, data, dist, evaluation):
        "KolmogorovSmirnovTest[data_List, dist_]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        cdf = _scipy_cdf(dist, evaluation)
        if cdf is None:
            return None
        d = _ks_statistic(xs, cdf)
        return _p(stats.kstwo.sf(d, len(xs)))


class ShapiroWilkTest(_ScipyTest):
    def eval(self, data, evaluation):
        "ShapiroWilkTest[data_List]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        return _p(stats.shapiro(xs).pvalue)


def _ad_statistic(xs, cdf):
    n = len(xs)
    F = [float(cdf(x)) for x in sorted(xs)]
    return -n - sum((2 * i + 1) * (math.log(F[i]) + math.log(1 - F[n - 1 - i])) for i in range(n)) / n


def _ad_cdf(n, z):
    """Marsaglia & Marsaglia (2004): CDF of the Anderson-Darling statistic for
    a fully specified continuous distribution, with the finite-n fix."""
    if z < 2:
        x = z**-0.5 * math.exp(-1.2337141 / z) * (2.00012 + (0.247105 - (0.0649821 - (0.0347962 - (0.011672 - 0.00168691 * z) * z) * z) * z) * z)
    else:
        x = math.exp(-math.exp(1.0776 - (2.30695 - (0.43424 - (0.082433 - (0.008056 - 0.0003146 * z) * z) * z) * z) * z))
    if x > 0.8:
        fix = (-130.2137 + (745.2337 - (1705.091 - (1950.646 - (1116.360 - 255.7844 * x) * x) * x) * x) * x) / n
    else:
        c = 0.01265 + 0.1757 / n
        if x < c:
            t = x / c
            t = math.sqrt(t) * (1 - t) * (49 * t - 102)
            fix = t * (0.0037 / n**3 + 0.00078 / n**2 + 0.00006 / n)
        else:
            t = (x - c) / (0.8 - c)
            t = -0.00022633 + (6.54034 - (14.6538 - (14.458 - (8.259 - 1.91864 * t) * t) * t) * t) * t
            fix = t * (0.04213 + 0.01365 / n) / n
    return min(max(x + fix, 0.0), 1.0)


class AndersonDarlingTest(_ScipyTest):
    def eval1(self, data, evaluation):
        "AndersonDarlingTest[data_List]"
        xs = self._floats(data)
        if xs is None:
            return None
        n = len(xs)
        a2 = _ad_statistic(xs, _fitted_normal_cdf(xs))
        a2s = a2 * (1 + 0.75 / n + 2.25 / n**2)
        # parameters estimated: D'Agostino & Stephens (1986) normal case
        if a2s >= 0.6:
            p = math.exp(1.2937 - 5.709 * a2s + 0.0186 * a2s**2)
        elif a2s >= 0.34:
            p = math.exp(0.9177 - 4.279 * a2s - 1.38 * a2s**2)
        elif a2s >= 0.2:
            p = 1 - math.exp(-8.318 + 42.796 * a2s - 59.938 * a2s**2)
        else:
            p = 1 - math.exp(-13.436 + 101.14 * a2s - 223.73 * a2s**2)
        return _p(min(max(p, 0.0), 1.0))

    def eval2(self, data, dist, evaluation):
        "AndersonDarlingTest[data_List, dist_]"
        xs = self._floats(data)
        if xs is None:
            return None
        cdf = _scipy_cdf(dist, evaluation)
        if cdf is None:
            return None
        return _p(1 - _ad_cdf(len(xs), _ad_statistic(xs, cdf)))


class CramerVonMisesTest(_ScipyTest):
    def eval1(self, data, evaluation):
        "CramerVonMisesTest[data_List]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        return _p(stats.cramervonmises(xs, _fitted_normal_cdf(xs)).pvalue)

    def eval2(self, data, dist, evaluation):
        "CramerVonMisesTest[data_List, dist_]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        cdf = _scipy_cdf(dist, evaluation)
        if cdf is None:
            return None
        return _p(stats.cramervonmises(xs, cdf).pvalue)


class DistributionFitTest(_ScipyTest):
    """Wolfram's automatic choice for a normal fit is the Kolmogorov-Smirnov test."""
    rules = {
        "DistributionFitTest[data_List]": "KolmogorovSmirnovTest[data]",
        "DistributionFitTest[data_List, dist_]": "KolmogorovSmirnovTest[data, dist]",
    }


class PearsonChiSquareTest(_ScipyTest):
    @staticmethod
    def _chi(xs, ppf, estimated):
        from scipy import stats
        n = len(xs)
        k = 4  # Wolfram: 4 equiprobable bins for small samples
        edges = [ppf(i / k) for i in range(1, k)]
        counts = [0] * k
        for x in xs:
            counts[sum(1 for e in edges if x > e)] += 1
        expected = n / k
        chi = sum((c - expected) ** 2 / expected for c in counts)
        return _p(stats.chi2.sf(chi, k - 1 - estimated))

    def eval1(self, data, evaluation):
        "PearsonChiSquareTest[data_List]"
        from scipy import stats
        xs = self._floats(data)
        if xs is None:
            return None
        mean = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
        return self._chi(xs, stats.norm(mean, sd).ppf, 2)

    def eval2(self, data, dist, evaluation):
        "PearsonChiSquareTest[data_List, dist_]"
        xs = self._floats(data)
        if xs is None:
            return None
        ppf = _scipy_ppf(dist, evaluation)
        if ppf is None:
            return None
        return self._chi(xs, ppf, 0)


class IndependenceTest(_ScipyTest):
    def eval(self, x, y, evaluation):
        "IndependenceTest[x_List, y_List]"
        from scipy import stats
        xs, ys = self._floats(x), self._floats(y)
        if xs is None or ys is None:
            return None
        return _p(stats.pearsonr(xs, ys).pvalue)


class FindDistributionParameters(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED

    def eval(self, data, dist, evaluation):
        "FindDistributionParameters[data_List, dist_]"
        fit = _fit(data, dist)
        if fit is None:
            return None
        return ListExpression(*(Expression(Symbol("System`Rule"), sym, MachineReal(v)) for sym, v in fit))


class EstimatedDistribution(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED

    def eval(self, data, dist, evaluation):
        "EstimatedDistribution[data_List, dist_]"
        fit = _fit(data, dist)
        if fit is None:
            return None
        subs = {sym.get_name(): MachineReal(v) for sym, v in fit}
        return dist.replace_vars(subs)


def _fit(data, dist):
    """Maximum-likelihood estimates for the common families (closed forms as
    Wolfram reports them: Normal uses the unbiased s, Exponential 1/mean)."""
    xs = _ScipyTest._floats(data)
    if xs is None or not xs:
        return None
    head = dist.get_head_name().split("`")[-1]
    params = [e for e in dist.elements if isinstance(e, Symbol)]
    n = len(xs)
    mean = sum(xs) / n
    if head == "NormalDistribution" and len(dist.elements) == 2:
        # maximum likelihood: population standard deviation (Wolfram: s -> 1.41421 for 1..5)
        sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / n)
        vals = [mean, sd]
    elif head == "ExponentialDistribution":
        vals = [1 / mean]
    elif head == "PoissonDistribution":
        vals = [mean]
    elif head == "UniformDistribution":
        return None
    elif head == "GeometricDistribution":
        vals = [1 / (1 + mean)]
    elif head == "BernoulliDistribution":
        vals = [mean]
    elif head == "LogNormalDistribution" and len(dist.elements) == 2:
        logs = [math.log(x) for x in xs]
        lm = sum(logs) / n
        vals = [lm, math.sqrt(sum((v - lm) ** 2 for v in logs) / (n - 1))]
    elif head == "GammaDistribution":
        from scipy import stats
        a, loc, scale = stats.gamma.fit(xs, floc=0)
        vals = [a, scale]
    elif head == "WeibullDistribution":
        from scipy import stats
        c, loc, scale = stats.weibull_min.fit(xs, floc=0)
        vals = [c, scale]
    else:
        return None
    out = []
    for e, v in zip(dist.elements, vals):
        if isinstance(e, Symbol):
            out.append((e, v))
    return out


def _scipy_dist(dist, evaluation):
    from scipy import stats
    head = dist.get_head_name().split("`")[-1]
    try:
        args = [float(e.to_sympy()) for e in dist.elements if not e.has_form("List", None)]
        lists = [[float(x.to_sympy()) for x in e.elements] for e in dist.elements if e.has_form("List", None)]
    except Exception:
        return None
    if head == "NormalDistribution":
        return stats.norm(*(args or [0, 1]))
    if head == "UniformDistribution":
        a, b = lists[0] if lists else (0, 1)
        return stats.uniform(a, b - a)
    if head == "ExponentialDistribution":
        return stats.expon(scale=1 / args[0])
    if head == "GammaDistribution":
        return stats.gamma(args[0], scale=args[1])
    if head == "LogNormalDistribution":
        m, s = args or (0, 1)
        return stats.lognorm(s, scale=math.exp(m))
    if head == "WeibullDistribution":
        return stats.weibull_min(args[0], scale=args[1])
    if head == "CauchyDistribution":
        return stats.cauchy(*(args or [0, 1]))
    if head == "LogisticDistribution":
        return stats.logistic(*(args or [0, 1]))
    if head == "StudentTDistribution" and len(args) == 1:
        return stats.t(args[0])
    if head == "ChiSquareDistribution":
        return stats.chi2(args[0])
    if head == "BetaDistribution":
        return stats.beta(args[0], args[1])
    return None


def _scipy_cdf(dist, evaluation):
    d = _scipy_dist(dist, evaluation)
    return None if d is None else d.cdf


def _scipy_ppf(dist, evaluation):
    d = _scipy_dist(dist, evaluation)
    return None if d is None else d.ppf


CLASSES = (TTest, LocationTest, LocationEquivalenceTest, ZTest, VarianceTest, SignTest, SignedRankTest,
           KolmogorovSmirnovTest, ShapiroWilkTest, AndersonDarlingTest, CramerVonMisesTest, DistributionFitTest,
           PearsonChiSquareTest, IndependenceTest, FindDistributionParameters, EstimatedDistribution)

_WL_HEADS = ["TruncatedDistribution", "CensoredDistribution", "MixtureDistribution", "TransformedDistribution",
             "ProductDistribution", "ProbabilityDistribution", "EmpiricalDistribution", "OrderDistribution",
             "MarginalDistribution", "ParameterMixtureDistribution", "CompoundPoissonDistribution",
             "MultinormalDistribution", "BinormalDistribution", "MultinomialDistribution", "DirichletDistribution",
             "MultivariatePoissonDistribution", "NegativeMultinomialDistribution",
             "MultivariateHypergeometricDistribution", "MultivariateTDistribution", "CopulaDistribution",
             "StandbyDistribution", "Entropy", "MeanDeviation", "MedianDeviation", "InterquartileRange",
             "QuartileDeviation", "QuartileSkewness", "RootMeanSquare", "ContraharmonicMean", "TrimmedMean",
             "WinsorizedMean", "Commonest", "Standardize", "Rescale", "BinCounts", "BinLists", "KendallTau",
             "SpearmanRho", "CorrelationDistance", "Likelihood", "LogLikelihood", "InverseSurvivalFunction",
             "DistributionParameterQ", "NExpectation", "NProbability", "ExpectedValue", "DiscreteDistributionQ",
             "ContinuousDistributionQ", "KnownDistributionQ", "DomainBounds", "PolyExpectation", "ExpExpectation",
             "ClosedExpectation", "IntervalProbability", "EventProbability", "RegionProbability",
             "TruncatedByCondition", "TruncationWindow", "GaussianExpectation", "ProductExpectation",
             "ExpandRegularized", "SimplifyBranches", "CanonicalEvent", "BoundOf", "TightestBound", "FlipRel",
             "PiecewiseDifference", "ParamAssumptions", "ConditionalExpectation", "ConditionalProbability",
             "GaussianMonomial", "Normalize",
             "MergePiecewise", "Boole", "Covariance", "Correlation", "Expectation", "Probability", "PDF", "CDF",
             "Mean", "Variance", "Median", "Moment", "DistributionDomain"]


def register_dist_derived(session):
    for cls in CLASSES:
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
    for name in _WL_HEADS:
        session.definitions.get_definition(f"System`{name}")
        session.definitions.clear_cache(f"System`{name}")
    protect = [h for h in _WL_HEADS]
    session.evaluate("Unprotect[" + ", ".join(protect) + "]")
    code = WL_RULES.replace("@@DISCRETE@@", ", ".join(_DISCRETE)).replace("@@CONTINUOUS@@", ", ".join(_CONTINUOUS))
    session.evaluate('Begin["MathematicsNotebook`Derived`"]')
    try:
        for stmt in _statements(code):
            session.evaluate(stmt)
    finally:
        session.evaluate("End[]")
    session.evaluate("Protect[" + ", ".join(protect) + "]")
    for name in _WL_HEADS:
        session.definitions.clear_cache(f"System`{name}")
    session.evaluation.predetermined_out = None
    session.last_result = None


def _statements(code):
    """Split the rule block on top-level `;` + newline, skipping comments."""
    out = []
    buf = []
    depth = 0
    i = 0
    n = len(code)
    while i < n:
        if code.startswith("(*", i):
            j = code.find("*)", i)
            i = j + 2 if j >= 0 else n
            continue
        c = code[i]
        if c in "[({":
            depth += 1
        elif c in "])}":
            depth -= 1
        if c == ";" and code.startswith(";;", i):
            buf.append(";;")
            i += 2
            continue
        if c == "/" and code.startswith("/;", i):
            buf.append("/;")
            i += 2
            continue
        if c == ";" and depth == 0:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(c)
        i += 1
    stmt = "".join(buf).strip()
    if stmt:
        out.append(stmt)
    return out
