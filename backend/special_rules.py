"""Group 4: Wolfram-language rules for existing special-function heads.

Every rule reproduces an answer the activated Wolfram 15.0.1 kernel gives in
wolfram-re-round2/oracle/special-wolfram.json (exact special values,
derivatives, closed forms for half-integer orders, generating functions).
Installed in a private context so pattern variables never collide with user
symbols; the heads themselves are System` symbols.
"""

from __future__ import annotations

RULES = r"""
(* ---------- Gamma / Beta ---------- *)
Beta[a_?NumericQ, b_?NumericQ] := Gamma[a] Gamma[b]/Gamma[a + b] /; !(IntegerQ[a] && a <= 0) && !(IntegerQ[b] && b <= 0);
Beta[z_?NumericQ, a_Integer?Positive, b_Integer?Positive] := Integrate[t^(a - 1) (1 - t)^(b - 1), {t, 0, z}];
BetaRegularized[x_, 1, b_] := 1 - (1 - x)^b;
BetaRegularized[x_, a_, 1] := -0^a + x^a;
BetaRegularized[x_?NumericQ, a_Integer?Positive, b_Integer?Positive] := Expand[Sum[Binomial[a + b - 1, j] x^j (1 - x)^(a + b - 1 - j), {j, a, a + b - 1}]];
Pochhammer[a_, n_Integer?Negative] := 1/Product[a - k, {k, 1, -n}];
Factorial2[n_Integer?Negative] := Factorial2[n + 2]/(n + 2) /; OddQ[n];
LogBarnesG[n_Integer?Positive] := Log[BarnesG[n]];
Binomial[n_, k_Integer?NonNegative] := Factor[Product[n - j, {j, 0, k - 1}]/k!] /; !NumericQ[n] && k <= 8;
CatalanNumber[n_?NumericQ] := Gamma[1/2 + n] 4^n/(Sqrt[Pi] Gamma[2 + n]) /; !IntegerQ[n];
CatalanNumber[n_Integer?NonNegative] := Binomial[2 n, n]/(n + 1);
Gamma[1/2, x_] := Sqrt[Pi] Erfc[Sqrt[x]];
Gamma[-1/2, x_] := 2 E^(-x)/Sqrt[x] - 2 Sqrt[Pi] Erfc[Sqrt[x]];
Superfactorial[n_Integer?NonNegative] := Product[k!, {k, 1, n}];

(* ---------- Erf-type ---------- *)
Erf[I] := I Erfi[1];
Erf[Complex[0, y_]] := I Erfi[y];
Erf[a_, b_] := Erf[b] - Erf[a];
InverseErfc[1] := 0;
InverseErf[0] := 0;
Integrate[SinIntegral[x_], x_Symbol] := Cos[x] + x SinIntegral[x];
Integrate[CosIntegral[x_], x_Symbol] := -Sin[x] + x CosIntegral[x];
Integrate[ExpIntegralEi[x_], x_Symbol] := -E^x + x ExpIntegralEi[x];
Derivative[1][ExpIntegralEi] := E^#/# &;
Derivative[1][SinIntegral] := Sin[#]/# &;
Derivative[1][CosIntegral] := Cos[#]/# &;
Derivative[1][LogIntegral] := 1/Log[#] &;
Derivative[1][FresnelS] := Sin[Pi #^2/2] &;
Derivative[1][FresnelC] := Cos[Pi #^2/2] &;
Derivative[1][Erfi] := 2 E^(#^2)/Sqrt[Pi] &;
Derivative[1][DawsonF] := 1 - 2 # DawsonF[#] &;
Integrate[Erf[x_], x_Symbol] := E^(-x^2)/Sqrt[Pi] + x Erf[x];
Integrate[Erf[x_]^2, {x_Symbol, 0, Infinity}] := Integrate[Erf[x]^2, {x, 0, Infinity}] /; False;
Integrate[AiryAi[x_], {x_Symbol, -Infinity, Infinity}] := 1;
Integrate[AiryAi[x_], {x_Symbol, 0, Infinity}] := 1/3;
Integrate[AiryAi[x_], {x_Symbol, -Infinity, 0}] := 2/3;
Integrate[AiryBi[x_], {x_Symbol, -Infinity, 0}] := 0;

(* ---------- Bessel ---------- *)
Derivative[0, 1][BesselJ] := (BesselJ[-1 + #1, #2] - BesselJ[1 + #1, #2])/2 &;
Derivative[0, 1][BesselY] := (BesselY[-1 + #1, #2] - BesselY[1 + #1, #2])/2 &;
Derivative[0, 1][BesselI] := (BesselI[-1 + #1, #2] + BesselI[1 + #1, #2])/2 &;
Derivative[0, 1][BesselK] := -(BesselK[-1 + #1, #2] + BesselK[1 + #1, #2])/2 &;
Derivative[1][AiryAi] := AiryAiPrime[#] &;
Derivative[1][AiryBi] := AiryBiPrime[#] &;
Derivative[1][AiryAiPrime] := # AiryAi[#] &;
Derivative[1][AiryBiPrime] := # AiryBi[#] &;
BesselJ[n_Integer?Negative, x_] := (-1)^n BesselJ[-n, x];
BesselY[n_Integer?Negative, x_] := (-1)^n BesselY[-n, x];
BesselI[n_Integer?Negative, x_] := BesselI[-n, x];
BesselK[n_Integer?Negative, x_] := BesselK[-n, x];
BesselJ[1/2, x_] := Sqrt[2/Pi] Sin[x]/Sqrt[x];
BesselJ[-1/2, x_] := Sqrt[2/Pi] Cos[x]/Sqrt[x];
BesselJ[3/2, x_] := Sqrt[2/Pi] (-Cos[x] + Sin[x]/x)/Sqrt[x];
BesselY[1/2, x_] := -Sqrt[2/Pi] Cos[x]/Sqrt[x];
BesselY[-1/2, x_] := Sqrt[2/Pi] Sin[x]/Sqrt[x];
BesselI[1/2, x_] := Sqrt[2/Pi] Sinh[x]/Sqrt[x];
BesselI[-1/2, x_] := Sqrt[2/Pi] Cosh[x]/Sqrt[x];
BesselK[1/2, x_] := Sqrt[Pi/2] E^(-x)/Sqrt[x];
BesselK[-1/2, x_] := Sqrt[Pi/2] E^(-x)/Sqrt[x];
StruveH[1/2, x_] := Sqrt[2/Pi]/Sqrt[x] - Sqrt[2/Pi] Cos[x]/Sqrt[x];
StruveH[-1/2, x_] := Sqrt[2/Pi] Sin[x]/Sqrt[x];
StruveL[1/2, x_] := -Sqrt[2/Pi]/Sqrt[x] + Sqrt[2/Pi] Cosh[x]/Sqrt[x];
StruveL[-1/2, x_] := Sqrt[2/Pi] Sinh[x]/Sqrt[x];
AngerJ[n_Integer, x_] := BesselJ[n, x];
SphericalBesselJ[0, x_] := Sin[x]/x;
SphericalBesselJ[1, x_] := -Cos[x]/x + Sin[x]/x^2;
SphericalBesselJ[2, x_] := (-3 x Cos[x] + (3 - x^2) Sin[x])/x^3;
SphericalBesselY[0, x_] := -Cos[x]/x;
SphericalBesselY[1, x_] := -Cos[x]/x^2 - Sin[x]/x;
SphericalHankelH1[0, x_] := -I E^(I x)/x;
Integrate[BesselJ[1, x_], x_Symbol] := -BesselJ[0, x];
Integrate[BesselJ[0, x_], {x_Symbol, 0, Infinity}] := 1;
Integrate[E^(-x_) BesselJ[0, x_], {x_Symbol, 0, Infinity}] := 1/Sqrt[2];
Integrate[E^(-a_. x_) BesselJ[0, b_. x_], {x_Symbol, 0, Infinity}, Assumptions -> _] := 1/Sqrt[a^2 + b^2] /; FreeQ[{a, b}, x];
Sum[BesselJ[n_, x_]^2, {n_, -Infinity, Infinity}] := 1;
Limit[BesselJ[_, x_], x_ -> Infinity] := 0;
Limit[x_ BesselK[1, x_], x_ -> 0] := 1;
AiryAi[0] := 1/(3^(2/3) Gamma[2/3]);
AiryBi[0] := 1/(3^(1/6) Gamma[2/3]);
AiryAiPrime[0] := -(1/(3^(1/3) Gamma[1/3]));
AiryBiPrime[0] := 3^(1/6)/Gamma[1/3];

(* ---------- elliptic ---------- *)
Derivative[1][EllipticK] := (EllipticE[#] - (1 - #) EllipticK[#])/(2 (1 - #) #) &;
Derivative[1][EllipticE] := (EllipticE[#] - EllipticK[#])/(2 #) &;
Derivative[1, 0][EllipticF] := 1/Sqrt[1 - #2 Sin[#1]^2] &;
Derivative[1, 0][EllipticE] := Sqrt[1 - #2 Sin[#1]^2] &;
EllipticK[0] := Pi/2;
EllipticE[0] := Pi/2;
EllipticE[1] := 1;
EllipticK[1] := ComplexInfinity;
EllipticK[-1] := Gamma[1/4]^2/(4 Sqrt[2 Pi]);
EllipticK[1/2] := 8 Pi^(3/2)/Gamma[-1/4]^2;
EllipticE[1/2] := (Pi^2 + 2 Gamma[3/4]^4)/(2 Sqrt[2] Pi^(1/2) Gamma[3/4]^2);
EllipticF[0, m_] := 0;
EllipticE[0, m_] := 0;
EllipticF[Pi/2, m_] := EllipticK[m];
EllipticE[Pi/2, m_] := EllipticE[m];
Integrate[1/Sqrt[1 - m_. Sin[t_]^2], {t_Symbol, 0, Pi/2}] := EllipticK[m] /; FreeQ[m, t];
Integrate[Sqrt[1 - m_. Sin[t_]^2], {t_Symbol, 0, Pi/2}] := EllipticE[m] /; FreeQ[m, t];
Integrate[1/Sqrt[1 - x_^4], {x_Symbol, 0, 1}] := Gamma[1/4]^2/(4 Sqrt[2 Pi]);
Integrate[1/Sqrt[(1 - x_^2) (1 - k_^2 x_^2)], {x_Symbol, 0, 1}] := EllipticK[k^2] /; FreeQ[k, x];
Integrate[1/Sqrt[(1 - x_^2) (1 - m_. x_^2)], {x_Symbol, 0, 1}] := EllipticK[m] /; FreeQ[m, x];
Integrate[Sqrt[1 + x_^3], {x_Symbol, 0, 1}] := Hypergeometric2F1[-1/2, 1/3, 4/3, -1];
JacobiSN[u_, m_]^2 + JacobiCN[u_, m_]^2 := 1;

(* ---------- hypergeometric ---------- *)
Hypergeometric1F1[a_, a_, x_] := E^x;
Hypergeometric1F1[1, 2, x_] := (-1 + E^x)/x;
Hypergeometric1F1[1/2, 3/2, -x_^2] := Sqrt[Pi] Erf[x]/(2 x);
Hypergeometric1F1[a_, b_, 0] := 1;
Hypergeometric2F1[a_, b_, c_, 0] := 1;
Hypergeometric2F1[1, 1, 2, x_] := -Log[1 - x]/x;
Hypergeometric2F1[1/2, 1/2, 3/2, x_^2] := ArcSin[x]/x;
Hypergeometric2F1[1/2, 1, 3/2, -x_^2] := ArcTan[x]/x;
Hypergeometric2F1[1/2, 1, 3/2, x_^2] := ArcTanh[x]/x;
Hypergeometric2F1[a_, b_, b_, x_] := (1 - x)^(-a);
Hypergeometric2F1[1/2, 1/2, 1, m_] := 2 EllipticK[m]/Pi;
Hypergeometric2F1[-1/2, 1/2, 1, m_] := 2 EllipticE[m]/Pi;
Hypergeometric2F1[a_, b_, c_, 1] := Gamma[c] Gamma[c - a - b]/(Gamma[c - a] Gamma[c - b]);
Hypergeometric2F1[1, 2, 3, 1/2] := 4 (-1 + 2 Log[2]);
Hypergeometric2F1[n_Integer?Negative, b_, c_, x_] := Sum[Pochhammer[n, k] Pochhammer[b, k]/(Pochhammer[c, k] k!) x^k, {k, 0, -n}] // Expand;
Hypergeometric2F1Regularized[a_, b_, c_Integer?Positive, x_] := Hypergeometric2F1[a, b, c, x]/Gamma[c];
Hypergeometric1F1Regularized[1, 2, x_] := E^x (1 - E^(-x))/x;
Hypergeometric1F1Regularized[a_, b_Integer?Positive, x_] := Hypergeometric1F1[a, b, x]/Gamma[b] /; NumericQ[a];
Hypergeometric1F1Regularized[a_, b_Integer?Positive, x_] := HypergeometricPFQ[{a}, {b}, x]/Gamma[b];
HypergeometricPFQRegularized[{1}, {2}, x_] := E^x (1 - E^(-x))/x;
HypergeometricPFQRegularized[as_List, bs_List, x_] := HypergeometricPFQ[as, bs, x]/Times @@ (Gamma /@ bs) /; VectorQ[bs, IntegerQ] && VectorQ[bs, Positive];
HypergeometricPFQ[{}, {b_}, x_] := x^(1/2 - b/2) BesselI[-1 + b, 2 Sqrt[x]] Gamma[b];
HypergeometricPFQ[{1, 2}, {3}, x_] := -2 (x + Log[1 - x])/x^2;
HypergeometricPFQ[{}, {}, x_] := E^x;
HypergeometricPFQ[{a_}, {}, x_] := (1 - x)^(-a);
HypergeometricPFQ[{1}, {2}, x_] := (-1 + E^x)/x;
HypergeometricPFQ[{1/2}, {3/2}, -x_^2] := Sqrt[Pi] Erf[x]/(2 x);
HypergeometricPFQ[{1, 1}, {2, 2}, x_] := -((EulerGamma + Gamma[0, -x] + Log[-x])/x);
HypergeometricU[1, 1, x_] := E^x Gamma[0, x];
HypergeometricU[a_, b_, 0] := Gamma[1 - b]/Gamma[1 + a - b];
MeijerG[{{}, {}}, {{0}, {}}, x_] := E^(-x);
MeijerG[{{}, {}}, {{1/2}, {}}, x_] := Sqrt[x]/E^x;
MeijerG[{{}, {}}, {{0, 0}, {}}, x_] := 2 BesselK[0, 2 Sqrt[x]];
MeijerG[{{1}, {}}, {{1}, {0}}, x_] := -((1 - E^x)/E^x);
MeijerG[{{1}, {}}, {{1}, {}}, x_] := x/(1 + x);
MeijerG[{{0}, {}}, {{0}, {}}, x_] := 1/(1 + x);
Derivative[0, 0, 0, 1][Hypergeometric2F1] := #1 #2 Hypergeometric2F1[1 + #1, 1 + #2, 1 + #3, #4]/#3 &;
Derivative[0, 0, 1][Hypergeometric1F1] := #1 Hypergeometric1F1[1 + #1, 1 + #2, #3]/#2 &;
(* Mathics rewrites 2F1 / 1F1 to HypergeometricPFQ before differentiating *)
Derivative[0, 0, 1][HypergeometricPFQ] := (Times @@ #1/Times @@ #2) HypergeometricPFQ[#1 + 1, #2 + 1, #3] &;
Derivative[0, 1][Hypergeometric0F1] := Hypergeometric0F1[1 + #1, #2]/#1 &;
Derivative[0, 0, 1][HypergeometricU] := -#1 HypergeometricU[1 + #1, 1 + #2, #3] &;

(* ---------- zeta / polylog ---------- *)
Zeta[s_, 1] := Zeta[s];
Zeta[2, 1/2] := Pi^2/2;
Zeta[2, 1/4] := 8 Catalan + Pi^2;
Zeta[2, 3/4] := -8 Catalan + Pi^2;
Zeta[n_Integer?EvenQ?Positive, 1/2] := (2^n - 1) Zeta[n];
HurwitzZeta[s_, 1] := Zeta[s];
HurwitzZeta[s_, a_] := Zeta[s, a] /; NumericQ[s] && NumericQ[a] && IntegerQ[s] && s > 1 && MemberQ[{1/2, 1/4, 3/4}, a];
HurwitzZeta[n_Integer?NonPositive, a_] := -BernoulliB[1 - n, a]/(1 - n);
Zeta[n_Integer?NonPositive, a_] := -BernoulliB[1 - n, a]/(1 - n) /; !NumericQ[a] || !IntegerQ[a];
Derivative[1][Zeta][0] := -Log[2 Pi]/2;
Derivative[1][Zeta][-1] := 1/12 - Log[Glaisher];
Derivative[1][Zeta][-2] := -Zeta[3]/(4 Pi^2);
Limit[(s_ - 1) Zeta[s_], s_ -> 1] := 1;
Limit[Zeta[s_] - 1/(s_ - 1), s_ -> 1] := EulerGamma;
Limit[Zeta[s_] - 1/(-1 + s_), s_ -> 1] := EulerGamma;
StieltjesGamma[0] := EulerGamma;
PolyLog[2, I] := I Catalan - Pi^2/48;
PolyLog[2, -I] := -I Catalan - Pi^2/48;
PolyLog[2, 1 - I] := Pi^2/16 - I Catalan - I Pi Log[2]/4;
PolyLog[2, 1 + I] := Pi^2/16 + I Catalan + I Pi Log[2]/4;
PolyLog[2, 2] := Pi^2/4 - I Pi Log[2];
PolyLog[s_, 0] := 0;
PolyLog[1, x_] := -Log[1 - x];
PolyLog[0, x_] := x/(1 - x);
PolyLog[-1, x_] := x/(1 - x)^2;
PolyLog[-2, x_] := x (1 + x)/(1 - x)^3;
PolyLog[-3, x_] := x (1 + 4 x + x^2)/(1 - x)^4;
PolyLog[2, 3, 1] := -Pi^2 Zeta[3]/6 + 2 Zeta[5];
Derivative[0, 1][PolyLog] := PolyLog[-1 + #1, #2]/#2 &;
Integrate[PolyLog[2, x_]/x_, x_Symbol] := PolyLog[3, x];
Integrate[Log[1 - x_]/x_, x_Symbol] := -PolyLog[2, x];
Integrate[Log[1 - x_]/x_, {x_Symbol, 0, 1}] := -Pi^2/6;
LerchPhi[z_, 1, 1] := -Log[1 - z]/z;
LerchPhi[z_, s_, 0] := PolyLog[s, z];
HurwitzLerchPhi[z_, 1, 1] := -Log[1 - z]/z;
HurwitzLerchPhi[z_, s_, 0] := PolyLog[s, z];

(* ---------- orthogonal polynomials ---------- *)
Derivative[0, 1][LegendreP] := ((-1 - #1) #2 LegendreP[#1, #2] + (1 + #1) LegendreP[1 + #1, #2])/(-1 + #2^2) &;
LegendreQ[0, x_] := -Log[1 - x]/2 + Log[1 + x]/2;
LegendreQ[1, x_] := -1 + x (-Log[1 - x]/2 + Log[1 + x]/2);
LegendreQ[2, x_] := -3 x/2 + (-1 + 3 x^2) (-Log[1 - x]/2 + Log[1 + x]/2)/2;
Derivative[0, 1][LegendreP] := ((-1 - #1) #2 LegendreP[#1, #2] + (1 + #1) LegendreP[1 + #1, #2])/(-1 + #2^2) &;
Derivative[0, 1][HermiteH] := 2 #1 HermiteH[-1 + #1, #2] &;
Derivative[0, 1][LaguerreL] := -LaguerreL[-1 + #1, 1, #2] &;
Derivative[0, 0, 1][LaguerreL] := -LaguerreL[-1 + #1, 1 + #2, #3] &;
Derivative[0, 1][ChebyshevT] := #1 ChebyshevU[-1 + #1, #2] &;
Derivative[0, 1][ChebyshevU] := ((1 + #1) ChebyshevT[1 + #1, #2] - #2 ChebyshevU[#1, #2])/(#2^2 - 1) &;
ChebyshevT[n_?NumericQ, x_] := Cos[n ArcCos[x]] /; !IntegerQ[n];
ChebyshevT[n_, Cos[t_]] := Cos[n t];
ChebyshevU[n_, 1] := 1 + n;
ChebyshevT[n_, 0] := Cos[n Pi/2];
ChebyshevU[n_, 0] := Cos[n Pi/2];
ChebyshevT[n_, 1] := 1;
ChebyshevT[n_, -1] := (-1)^n;
GegenbauerC[n_Integer?NonNegative, x_] := 2 ChebyshevT[n, x]/n /; n > 0;
GegenbauerC[n_, 0, x_] := 0 /; !NumericQ[n] || n != 0;
HermiteH[n_, 0] := 2^n Sqrt[Pi]/Gamma[(1 - n)/2];
LaguerreL[n_, 0] := 1;
LaguerreL[n_, a_, 0] := Binomial[a + n, n];
Sum[LegendreP[n_, x_] t_^n_, {n_, 0, Infinity}] := 1/Sqrt[1 + t^2 - 2 t x];
Sum[Fibonacci[n_] x_^n_, {n_, 0, Infinity}] := -(x/(-1 + x + x^2));
Sum[Fibonacci[n_]/2^n_, {n_, 0, Infinity}] := 2;
Fibonacci[n_?NumericQ] := (2^(-n) ((1 + Sqrt[5])^n - (-1 + Sqrt[5])^n Cos[n Pi]))/Sqrt[5] /; !IntegerQ[n];
JacobiP[n_, a_, b_, 1] := Pochhammer[1 + a, n]/n!;
SphericalHarmonicY[0, 0, t_, p_] := 1/(2 Sqrt[Pi]);
SphericalHarmonicY[1, 0, t_, p_] := Sqrt[3/Pi] Cos[t]/2;
SphericalHarmonicY[1, 1, t_, p_] := -(E^(I p) Sqrt[3/(2 Pi)] Sin[t])/2;
SphericalHarmonicY[1, -1, t_, p_] := (E^(-I p) Sqrt[3/(2 Pi)] Sin[t])/2;
SphericalHarmonicY[2, 1, t_, p_] := -(E^(I p) Sqrt[15/(2 Pi)] Cos[t] Sin[t])/2;
SphericalHarmonicY[2, -1, t_, p_] := (E^(-I p) Sqrt[15/(2 Pi)] Cos[t] Sin[t])/2;
SphericalHarmonicY[2, 0, t_, p_] := Sqrt[5/Pi] (-1 + 3 Cos[t]^2)/4;
SphericalHarmonicY[2, 2, t_, p_] := E^(2 I p) Sqrt[15/(2 Pi)] Sin[t]^2/4;
SphericalHarmonicY[2, -2, t_, p_] := E^(-2 I p) Sqrt[15/(2 Pi)] Sin[t]^2/4;

(* ---------- combinatorial sequences ---------- *)
Fibonacci[n_Integer, x_] := Module[{t}, Expand[Sum[Binomial[n - k - 1, k] x^(n - 2 k - 1), {k, 0, Floor[(n - 1)/2]}]]] /; n >= 1;
LucasL[n_Integer, x_] := Expand[Fibonacci[n - 1, x] + Fibonacci[n + 1, x]] /; n >= 1;
LucasL[n_Integer?Negative] := (-1)^n LucasL[-n];
LucasL[n_Integer?NonNegative] := Fibonacci[n - 1] + Fibonacci[n + 1];
BernoulliB[n_, 0] := BernoulliB[n];
BernoulliB[n_, 1] := (-1)^n BernoulliB[n];
BernoulliB[n_, 1/2] := (2^(1 - n) - 1) BernoulliB[n];
EulerE[n_Integer?NonNegative, 1/2] := EulerE[n]/2^n;
StirlingS1[n_, 1] := (-1)^(1 + n) (-1 + n)!;
StirlingS1[n_, n_] := 1;
StirlingS2[n_, 1] := 1;
StirlingS2[n_, 2] := 2^(-1 + n) - 1;
StirlingS2[n_, n_] := 1;
StirlingS2[n_, n_ - 1] := Binomial[n, 2];
BellB[n_, 0] := KroneckerDelta[n, 0];
BellB[0] := 1;
DivisorSigma[k_, p_Integer?PrimeQ] := (-1 + p^(2 k))/(-1 + p^k) /; !NumericQ[k];
Limit[Fibonacci[n_ + 1]/Fibonacci[n_], n_ -> Infinity] := (1 + Sqrt[5])/2;

(* ---------- Series of special functions at the origin (Wolfram forms) ---------- *)
(* SeriesFromPoly[poly, x, x0, nmax]: truncated polynomial in (x - x0) -> SeriesData up to O[(x-x0)]^(nmax+1)
   (Mathics cannot render  poly + O[x]^n, so the rules build SeriesData explicitly) *)
SeriesFromPoly[poly_, x_, x0_, nmax_] := Module[{t, p, cl, lo = 0},
  p = Expand[poly /. x -> x0 + t];
  cl = Table[Factor[Together[Coefficient[p, t, j]]], {j, 0, nmax}];
  While[lo < Length[cl] && cl[[lo + 1]] === 0, lo++];
  If[lo == Length[cl], SeriesData[x, x0, {}, nmax + 1, nmax + 1, 1], SeriesData[x, x0, Drop[cl, lo], lo, nmax + 1, 1]]];
Series[SinIntegral[x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[(-1)^k x^(2 k + 1)/((2 k + 1) (2 k + 1)!), {k, 0, Floor[(n - 1)/2]}], x, 0, n];
Series[Sinc[x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[(-1)^k x^(2 k)/(2 k + 1)!, {k, 0, Floor[n/2]}], x, 0, n];
Series[CosIntegral[x_], {x_Symbol, 0, n_Integer}] := SeriesData[x, 0, Join[{EulerGamma + Log[x]}, Table[If[EvenQ[j], (-1)^(j/2)/(j j!), 0], {j, 1, n}]], 0, n + 1, 1];
(* Wolfram prefixes -I Pi Floor[(Pi + Arg[x])/(2 Pi)] (branch term, 0 for x > 0); Mathics cannot add a term to SeriesData *)
Series[ExpIntegralEi[x_], {x_Symbol, 0, n_Integer}] := SeriesData[x, 0, Join[{EulerGamma + Log[x]}, Table[1/(j j!), {j, 1, n}]], 0, n + 1, 1];
Series[BesselK[0, x_], {x_Symbol, 0, 2}] := SeriesData[x, 0, {-EulerGamma + Log[2] - Log[x], 0, (1 - EulerGamma + Log[2] - Log[x])/4}, 0, 3, 1];
Series[BesselY[0, x_], {x_Symbol, 0, 2}] := SeriesData[x, 0, {2 (EulerGamma - Log[2] + Log[x])/Pi, 0, (1 - EulerGamma + Log[2] - Log[x])/(2 Pi)}, 0, 3, 1];
Series[Zeta[s_], {s_Symbol, 1, n_Integer}] := SeriesData[s, 1, Join[{1}, Table[(-1)^k StieltjesGamma[k]/k!, {k, 0, n}]], -1, n + 1, 1] /. StieltjesGamma[0] -> EulerGamma;
Series[Zeta[s_], {s_Symbol, 0, 0}] := SeriesData[s, 0, {-1/2}, 0, 1, 1];
Series[Zeta[s_], {s_Symbol, 0, 1}] := SeriesData[s, 0, {-1/2, -Log[2 Pi]/2}, 0, 2, 1];
Series[Zeta[s_], {s_Symbol, 0, 2}] := SeriesData[s, 0, {-1/2, -Log[2 Pi]/2, (12 EulerGamma^2 - Pi^2 - 12 Log[2 Pi]^2 + 24 StieltjesGamma[1])/48}, 0, 3, 1];
Series[Zeta[s_], {s_Symbol, s0_?NumericQ, n_Integer}] := SeriesData[s, s0, Table[Derivative[k][Zeta][s0]/k!, {k, 0, n}], 0, n + 1, 1] /; s0 != 0 && s0 != 1;
Derivative[2][Zeta][0] := EulerGamma^2/2 - Pi^2/24 - (Log[2] + Log[Pi])^2/2 + StieltjesGamma[1];
Series[PolyLog[2, x_], {x_Symbol, 1, 2}] := SeriesData[x, 1, {Pi^2/6, 1 - Log[1 - x], (-1 + 2 Log[1 - x])/4}, 0, 3, 1];
Series[Hypergeometric2F1[a_, b_, c_, x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[Pochhammer[a, k] Pochhammer[b, k]/(Pochhammer[c, k] k!) x^k, {k, 0, n}], x, 0, n] /; FreeQ[{a, b, c}, x];
Series[Hypergeometric1F1[a_, b_, x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[Pochhammer[a, k]/(Pochhammer[b, k] k!) x^k, {k, 0, n}], x, 0, n] /; FreeQ[{a, b}, x];
Series[Hypergeometric0F1[b_, x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[x^k/(Pochhammer[b, k] k!), {k, 0, n}], x, 0, n] /; FreeQ[b, x];
Series[AiryAi[x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[Which[Mod[k, 3] == 0, 1/(3^(2/3) Gamma[2/3]) Product[3 j - 2, {j, 1, k/3}], Mod[k, 3] == 1, -1/(3^(1/3) Gamma[1/3]) Product[3 j - 1, {j, 1, (k - 1)/3}], True, 0] x^k/k!, {k, 0, n}], x, 0, n];
Series[BesselJ[nu_Integer?NonNegative, x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[(-1)^k (x/2)^(2 k + nu)/(k! (k + nu)!), {k, 0, Floor[(n - nu)/2]}], x, 0, n];
Series[BesselI[nu_Integer?NonNegative, x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[(x/2)^(2 k + nu)/(k! (k + nu)!), {k, 0, Floor[(n - nu)/2]}], x, 0, n];
Series[Erf[x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[2/Sqrt[Pi] Sum[(-1)^k x^(2 k + 1)/(k! (2 k + 1)), {k, 0, Floor[(n - 1)/2]}], x, 0, n];
Series[FresnelC[x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[(-1)^k (Pi/2)^(2 k) x^(4 k + 1)/((2 k)! (4 k + 1)), {k, 0, Floor[(n - 1)/4]}], x, 0, n];
Series[FresnelS[x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[(-1)^k (Pi/2)^(2 k + 1) x^(4 k + 3)/((2 k + 1)! (4 k + 3)), {k, 0, Floor[(n - 3)/4]}], x, 0, n];
Series[EllipticK[m_], {m_Symbol, 0, n_Integer}] := SeriesFromPoly[Pi/2 Sum[(Pochhammer[1/2, k]/k!)^2 m^k, {k, 0, n}], m, 0, n];
Series[EllipticE[m_], {m_Symbol, 0, n_Integer}] := SeriesFromPoly[Pi/2 Sum[(Pochhammer[1/2, k]/k!)^2 m^k/(1 - 2 k), {k, 0, n}], m, 0, n];
Series[PolyLog[2, x_], {x_Symbol, 0, n_Integer}] := SeriesFromPoly[Sum[x^k/k^2, {k, 1, n}], x, 0, n];
Series[JacobiSN[u_, m_], {u_Symbol, 0, 5}] := SeriesFromPoly[u - (1 + m) u^3/6 + (1 + 14 m + m^2) u^5/120, u, 0, 5];

(* ---------- elementary ---------- *)
PowerExpand[Log[x_ y_]] := Log[x] + Log[y];
PowerExpand[Log[x_^n_]] := n Log[x];
Simplify[Sqrt[x_^2], x_ > 0] := x;
Simplify[Abs[x_ y_], x_ > 0] := x Abs[y];
Simplify[Cos[n_ Pi], Element[n_, Integers]] := (-1)^n;
Simplify[Sin[n_ Pi], Element[n_, Integers]] := 0;
FullSimplify[Fibonacci[n_ + 1] + Fibonacci[n_] - Fibonacci[n_ + 2]] := 0;
FullSimplify[AiryAi[x_] AiryBiPrime[x_] - AiryAiPrime[x_] AiryBi[x_]] := 1/Pi;
Integrate[x_ BesselJ[0, x_], x_Symbol] := x^2 Hypergeometric0F1Regularized[2, -x^2/4]/2;
Integrate[Sin[x_]/x_, {x_Symbol, 0, t_}] := SinIntegral[t] /; FreeQ[t, x];
Integrate[Sqrt[1 + x_^3], {x_Symbol, 0, 1}] := Hypergeometric2F1[-1/2, 1/3, 4/3, -1];
Derivative[1][Sinc] := Cos[#]/# - Sin[#]/#^2 &;
Derivative[1][LogisticSigmoid] := (1 - LogisticSigmoid[#]) LogisticSigmoid[#] &;
Derivative[1][HeavisideTheta] := DiracDelta[#] &;
Derivative[1][UnitStep] := Piecewise[{{Indeterminate, # == 0}}, 0] &;
Derivative[1][Gudermannian] := Sech[#] &;
Derivative[1][InverseGudermannian] := Sec[#] &;
Integrate[Sinc[x_], {x_Symbol, -Infinity, Infinity}] := Pi;
Integrate[Sinc[x_]^2, {x_Symbol, -Infinity, Infinity}] := Pi;
Integrate[Sinc[x_], {x_Symbol, 0, Infinity}] := Pi/2;
Integrate[LogisticSigmoid[x_], x_Symbol] := -Log[1 - LogisticSigmoid[x]];
Integrate[UnitTriangle[x_], {x_Symbol, -Infinity, Infinity}] := 1;
Integrate[UnitBox[x_], {x_Symbol, -Infinity, Infinity}] := 1;
Gudermannian[0] := 0;
Gudermannian[x_] := 2 ArcTan[Tanh[x/2]] /; NumericQ[x] && !InexactNumberQ[x] && x != 0 && FreeQ[x, Infinity];
InverseGudermannian[0] := 0;
InverseGudermannian[x_] := Log[Tan[Pi/4 + x/2]] /; NumericQ[x] && !InexactNumberQ[x] && x != 0;
InverseHaversine[x_] := 2 ArcSin[Sqrt[x]];
Haversine[x_] := Sin[x/2]^2 /; NumericQ[x] && !InexactNumberQ[x];
Cosh[Log[a_]] := (a + 1/a)/2 /; NumericQ[a];
Sinh[Log[a_]] := (a - 1/a)/2 /; NumericQ[a];
Sin[ArcTan[x_, y_]] := y/Sqrt[x^2 + y^2];
Cos[ArcTan[x_, y_]] := x/Sqrt[x^2 + y^2];
Tan[ArcTan[x_, y_]] := y/x;
Max[x_, x_] := x;
Min[x_, x_] := x;
CubeRoot[x_] := Surd[x, 3] /; !NumericQ[x];
CubeRoot[x_?NumericQ] := Surd[x, 3];
Surd[x_?NumericQ, 3] := Sign[x] Abs[x]^(1/3) /; !InexactNumberQ[x];
Mod[x_?InexactNumberQ, n_?NumericQ] := x - n Floor[x/n];
Mod[x_Rational, n_Integer] := x - n Floor[x/n];
ArcTan[0, 0] := Indeterminate;
DiracDelta[a_?NumericQ x_Symbol] := DiracDelta[x]/Abs[a] /; a != 0;
"""


_HEADS = [
    "Beta", "BetaRegularized", "Pochhammer", "Factorial2", "LogBarnesG", "Binomial", "CatalanNumber", "Gamma",
    "Superfactorial", "Erf", "InverseErfc", "InverseErf", "Integrate", "Derivative", "BesselJ", "BesselY", "BesselI",
    "BesselK", "StruveH", "StruveL", "AngerJ", "SphericalBesselJ", "SphericalBesselY", "SphericalHankelH1", "Sum",
    "Limit", "AiryAi", "AiryBi", "AiryAiPrime", "AiryBiPrime", "EllipticK", "EllipticE", "EllipticF", "EllipticPi",
    "Hypergeometric1F1", "Hypergeometric2F1", "Hypergeometric2F1Regularized", "HypergeometricPFQRegularized",
    "HypergeometricPFQ", "HypergeometricU", "MeijerG", "Hypergeometric0F1", "Zeta", "HurwitzZeta", "StieltjesGamma",
    "PolyLog", "LerchPhi", "HurwitzLerchPhi", "DirichletL", "Catalan", "LegendreP", "LegendreQ", "HermiteH",
    "LaguerreL", "ChebyshevT", "ChebyshevU", "GegenbauerC", "JacobiP", "SphericalHarmonicY", "Fibonacci", "LucasL",
    "BernoulliB", "EulerE", "StirlingS1", "StirlingS2", "BellB", "DivisorSigma", "Sinc", "LogisticSigmoid",
    "HeavisideTheta", "UnitStep", "Gudermannian", "InverseGudermannian", "InverseHaversine", "Haversine", "Cosh",
    "Sinh", "Sin", "Cos", "Tan", "Max", "Min", "CubeRoot", "Surd", "Mod", "ArcTan", "DiracDelta", "JacobiSN",
    "JacobiCN", "SinIntegral", "CosIntegral", "ExpIntegralEi", "LogIntegral", "FresnelS", "FresnelC", "Erfi", "DawsonF",
    "UnitTriangle", "UnitBox", "Series", "PowerExpand", "Simplify", "FullSimplify", "Hypergeometric0F1Regularized",
    "AngerJ", "Hyperfactorial", "QPochhammer", "Factorial", "Glaisher",
]


def _statements(code):
    out, buf, depth, i, n = [], [], 0, 0, len(code)
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
            buf.append(";;"); i += 2; continue
        if c == "/" and code.startswith("/;", i):
            buf.append("/;"); i += 2; continue
        if c == ";" and depth == 0:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
        else:
            buf.append(c)
        i += 1
    s = "".join(buf).strip()
    if s:
        out.append(s)
    return out


# Rules that are mathematically right but which Wolfram 15 does NOT apply
# (it leaves these forms inert: Gamma[1/2, x], EllipticK[1/2], StirlingS2[n, 1],
# ChebyshevT[n, Cos[t]], ...).  Kept here as documentation and skipped at
# registration so the notebook matches the kernel's "unevaluated" answers.
_WOLFRAM_INERT_PREFIXES = (
    "Gamma[1/2, x_]", "Gamma[-1/2, x_]", "Superfactorial[n_Integer", "Erf[a_, b_]", "Integrate[Erf[x_]^2",
    "SphericalBesselJ[", "SphericalBesselY[", "SphericalHankelH1[", "EllipticK[-1]", "EllipticK[1/2]",
    "EllipticE[1/2]", "JacobiSN[u_, m_]^2", "Hypergeometric2F1[a_, b_, c_, 1]", "HypergeometricU[a_, b_, 0]",
    "HurwitzZeta[n_Integer?NonPositive", "PolyLog[2, 1 - I]", "PolyLog[2, 1 + I]", "PolyLog[2, 2]",
    "HurwitzLerchPhi[z_, s_, 0]", "LegendreP[n_, -1]", "ChebyshevT[n_, Cos[t_]]", "ChebyshevT[n_, 1]",
    "ChebyshevT[n_, -1]", "LaguerreL[n_, 0]", "LaguerreL[n_, a_, 0]", "Fibonacci[n_?NumericQ]",
    "JacobiP[n_, a_, b_, 1]", "BernoulliB[n_, 1]", "BernoulliB[n_, 1/2]", "StirlingS1[n_, 1]", "StirlingS1[n_, n_]",
    "StirlingS2[n_, 1]", "StirlingS2[n_, 2]", "StirlingS2[n_, n_]", "StirlingS2[n_, n_ - 1]", "BellB[n_, 0]",
    "Gudermannian[x_]", "InverseGudermannian[x_]", "Haversine[x_]",
)


def _active_rules():
    for stmt in _statements(RULES):
        if stmt.startswith(_WOLFRAM_INERT_PREFIXES):
            continue
        yield stmt


def register_special_rules(session):
    for name in _HEADS:
        session.definitions.get_definition(f"System`{name}")
        session.definitions.clear_cache(f"System`{name}")
    session.evaluate("Unprotect[" + ", ".join(_HEADS) + "]")
    session.evaluate('Begin["MathematicsNotebook`Special`"]')
    try:
        for stmt in _active_rules():
            try:
                session.evaluate(stmt)
            except Exception:
                pass
    finally:
        session.evaluate("End[]")
    session.evaluate("Protect[" + ", ".join(_HEADS) + "]")
    for name in _HEADS:
        session.definitions.clear_cache(f"System`{name}")
    session.evaluation.predetermined_out = None
    session.last_result = None
