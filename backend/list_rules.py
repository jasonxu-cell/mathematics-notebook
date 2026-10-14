"""Group 5 (lists / strings / functional): heads and arities that Mathics 10.0.1
lacks, written as WL definitions whose results were checked line by line
against the activated Wolfram 15.0.1 kernel
(wolfram-re-round2/oracle/lists-wolfram.json, strings-wolfram.json).

The block is evaluated inside the private context MathematicsNotebook`Lists`
so pattern variables never collide with user symbols; the heads themselves
are created in System` first so that `Head[Subdivide[...]]` etc. behave."""

RULES = r"""
(* ---------- construction ---------- *)
Range[a_, b_] := Table[a + i, {i, 0, b - a}] /; !NumericQ[a] && NumericQ[b - a] && IntegerQ[b - a] && b - a >= 0;
Subdivide[n_Integer?Positive] := Range[0, n]/n;
Subdivide[xmax_, n_Integer?Positive] := Range[0, n] xmax/n;
Subdivide[xmin_, xmax_, n_Integer?Positive] := Table[Expand[xmin (n - i)/n + xmax i/n], {i, 0, n}];
Array[f_, n_Integer?Positive, {a_, b_}] := Table[f[a + (b - a) (i - 1)/(n - 1)], {i, n}] /; n > 1;
DiagonalMatrix[l_List, k_Integer] := Module[{n = Length[l] + Abs[k]}, Table[If[j - i == k, l[[If[k >= 0, i, j]]], 0], {i, n}, {j, n}]];
Differences[l_List] := Rest[l] - Most[l];
Differences[l_List, n_Integer?Positive] := Nest[Differences, l, n];
Differences[l_List, 0] := l;
Ratios[l_List] := Rest[l]/Most[l];
Ratios[l_List, n_Integer?Positive] := Nest[Ratios, l, n];
MinMax[l_List] := {Min[l], Max[l]};
MinMax[l_List, d_] := {Min[l] - d, Max[l] + d} /; !ListQ[d];
MinMax[l_List, {dl_, dh_}] := {Min[l] - dl, Max[l] + dh};
MinMax[l_List, Scaled[s_]] := Module[{mn = Min[l], mx = Max[l]}, {mn - s (mx - mn), mx + s (mx - mn)}];
Ordering[l_List] := Module[{p = Transpose[{l, Range[Length[l]]}]}, Last /@ SortBy[p, First]];
Ordering[l_List, n_Integer?Positive] := Take[Ordering[l], n];
Ordering[l_List, n_Integer?Negative] := Take[Ordering[l], n];
Ordering[l_List, All] := Ordering[l];
Ordering[l_List, n_, p_] := Module[{o = stableSortIdx[l, p]}, If[n === All, o, Take[o, n]]];
stableSortIdx[l_List, p_] := Module[{idx = Range[Length[l]], merge},
  merge[a_, b_] := Module[{i = 1, j = 1, out = {}},
    While[i <= Length[a] && j <= Length[b],
      If[TrueQ[p[l[[b[[j]]]], l[[a[[i]]]]]] && !TrueQ[p[l[[a[[i]]]], l[[b[[j]]]]]], AppendTo[out, b[[j]]]; j++, AppendTo[out, a[[i]]]; i++]];
    Join[out, Drop[a, i - 1], Drop[b, j - 1]]];
  msort[s_] := If[Length[s] <= 1, s, merge[msort[Take[s, Floor[Length[s]/2]]], msort[Drop[s, Floor[Length[s]/2]]]]];
  msort[idx]];
ReverseSortBy[l_List, f_] := Reverse[SortBy[l, f]];
NumericalSort[l_List] := Join[Sort[Select[l, NumericQ]], Sort[Select[l, !NumericQ[#] &]]];
TakeWhile[l_List, crit_] := Module[{i = 1}, While[i <= Length[l] && TrueQ[crit[l[[i]]]], i++]; Take[l, i - 1]];
LengthWhile[l_List, crit_] := Length[TakeWhile[l, crit]];
Extract[expr_, i_Integer] := expr[[i]];
Extract[expr_, i_Integer, h_] := h[expr[[i]]];
Extract[expr_, l_List, h_] := Extract[expr, l, h] = h @@ {Extract[expr, l]} /; VectorQ[l, IntegerQ];
Extract[expr_, {lists___List}, h_] := (h[Extract[expr, #]] &) /@ {lists};
Counts[l_List] := Association @@ (Rule @@@ Tally[l]);
CountsBy[l_List, f_] := Counts[f /@ l];
DeleteDuplicatesBy[l_List, f_] := Module[{seen = {}}, Select[l, If[MemberQ[seen, f[#]], False, AppendTo[seen, f[#]]; True] &]];
Join[a_List, b_List, n_Integer] := MapThread[Join, {a, b}] /; n == 2 && Length[a] == Length[b];
Join[a_List, b_List, n_Integer] := Module[{r = a}, Do[r[[i]] = Join[a[[i]], b[[i]]], {i, Length[b]}]; r] /; n == 2 && Length[b] < Length[a];
Insert[l_List, x_, n_Integer?Negative] := Insert[l, x, Length[l] + n + 2];
Insert[l_List, x_, {ns__Integer}] := Insert[l, x, {{ns}}];
Insert[l_List, x_, pos : {{_Integer} ..}] := Module[{p = Sort[First /@ pos, Greater], r = l}, Do[r = Insert[r, x, k], {k, p}]; r];
(* Riffle[l, x, {imin, imax, di}]: x is inserted at positions imin, imin+di, ... of
   the RESULT (imax = -1 means "up to the end, including a trailing one when the
   period lands there"); Riffle[l, x, n] = Riffle[l, x, {n, -2, n}] — no trailing x *)
Riffle[l_List, x_, n_Integer?Positive] := Riffle[l, x, {n, -2, n}];
Riffle[l_List, x_, {imin_Integer, imax_Integer, di_Integer}] := Module[{out = {}, xs = If[ListQ[x], x, {x}], i = 1, k = 0, j = 1, isX},
  isX = Function[pos, pos >= imin && Mod[pos - imin, di] == 0];
  While[j <= Length[l],
    If[isX[i], AppendTo[out, xs[[Mod[k, Length[xs]] + 1]]]; k++, AppendTo[out, l[[j]]]; j++];
    i++];
  If[imax == -1 && isX[i], AppendTo[out, xs[[Mod[k, Length[xs]] + 1]]]];
  out];
(* Partition with offsets {kl, kr} and padding (Wolfram semantics: the first
   sublist starts so that its kl-th element is l[[1]], the last one is the
   last whose kr-th element lies in l; padding cycles through pad, default
   the list itself; pad = {} means ragged sublists) *)
Partition[l_List, n_Integer, d_Integer, k_Integer] := Partition[l, n, d, {k, k}];
Partition[l_List, n_Integer, d_Integer, k_Integer, pad_] := Partition[l, n, d, {k, k}, pad];
Partition[l_List, n_Integer, d_Integer, {kl_Integer, kr_Integer}] := Partition[l, n, d, {kl, kr}, l];
Partition[l_List, n_Integer, d_Integer, {kl_Integer, kr_Integer}, pad_] := Module[{m = Length[l], p, out = {}, i, seg, ragged = pad === {}, kl1, kr1, padAt},
  p = Which[ragged, {}, ListQ[pad], pad, True, {pad}];
  kl1 = If[kl > 0, kl, n + kl + 1];   (* position (within a sublist) that must hold l[[1]] / the last element *)
  kr1 = If[kr > 0, kr, n + kr + 1];
  padAt = Function[j, If[pad === l, l[[Mod[j - 1, m] + 1]], p[[Mod[j - 1, Length[p]] + 1]]]];
  i = 2 - kl1;
  While[i + kr1 - 1 <= m,
    seg = Table[Which[1 <= j <= m, l[[j]], ragged, padMarker$, True, padAt[j]], {j, i, i + n - 1}];
    AppendTo[out, DeleteCases[seg, padMarker$]]; i += d];
  out];
(* Transpose[t, perm]: level k of t becomes level perm[[k]] of the result *)
Transpose[t_?ArrayQ, perm_List] := transposeLevels[t, perm] /; Length[perm] == ArrayDepth[t] && Sort[perm] == Range[Length[perm]];
transposeLevels[t_, perm_] := Module[{dims = Dimensions[t], newDims, idx},
  newDims = Table[dims[[Position[perm, k][[1, 1]]]], {k, Length[perm]}];
  idx = Table[Unique["i"], {Length[perm]}];
  Table[Evaluate[t[[Sequence @@ idx[[perm]]]]], Evaluate[Sequence @@ Transpose[{idx, newDims}]]]];
Thread[f_[args___], h_, n_Integer] := Module[{a = {args}, m}, m = Length[Select[Take[a, n], Head[#] === h &][[1]]];
  Table[f @@ Join[Table[If[Head[a[[j]]] === h, a[[j, i]], a[[j]]], {j, n}], Drop[a, n]], {i, m}]];
Distribute[f_[args___]] := Distribute[f[args], Plus];
Distribute[f_[args___], g_] := Distribute[f[args], g, f];
Distribute[f_[args___], g_, f_] := Distribute[f[args], g, f, g, f];
Distribute[f_[args___], g_, f_, gg_, ff_] := Module[{a = {args}, lists},
  lists = If[Head[#] === g, List @@ #, {#}] & /@ a;
  gg @@ (ff @@@ Tuples[lists])];
MapAll[f_, expr_] := Map[f, expr, {0, Infinity}];
(* FoldPair: f returns {output, newacc}; FoldPair gives the final accumulator,
   FoldPairList the outputs, FoldPair[f, x, l, g] gives g[{outputs, acc}] *)
FoldPairList[f_, x_, l_List] := Module[{acc = x, out = {}, r}, Do[r = f[acc, e]; AppendTo[out, r[[1]]]; acc = r[[2]], {e, l}]; out];
FoldPair[f_, x_, l_List] := Module[{acc = x, r}, Do[r = f[acc, e]; acc = r[[2]], {e, l}]; acc];
FoldPair[f_, x_, l_List, g_] := Module[{acc = x, r = {x, x}}, Do[r = f[acc, e]; acc = r[[2]], {e, l}]; g[r]];
NestWhileList[f_, x_, test_] := Module[{r = {x}, y = x}, While[TrueQ[test[y]], y = f[y]; AppendTo[r, y]]; r];
NestWhileList[f_, x_, test_, m_Integer] := Module[{r = {x}, y = x}, While[Length[r] < m || TrueQ[test @@ Take[r, -m]], y = f[y]; AppendTo[r, y]]; r];
NestWhileList[f_, x_, test_, m_Integer, max_Integer] := Module[{r = {x}, y = x, k = 0}, While[k < max && (Length[r] < m || TrueQ[test @@ Take[r, -m]]), y = f[y]; AppendTo[r, y]; k++]; r];
NestWhile[f_, x_, test_, m_Integer, max_Integer] := Last[NestWhileList[f, x, test, m, max]];
ComposeList[fs_List, x_] := FoldList[#2[#1] &, x, fs];
RightComposition[fs___][x___] := Fold[#2[#1] &, x, {fs}] /; Length[{x}] == 1;
RightComposition[f_, fs___][x__] := RightComposition[fs][f[x]];
RightComposition[][x_] := x;
SelectFirst[l_, crit_] := SelectFirst[l, crit, Missing["NotFound"]];
SelectFirst[l_, crit_, default_] := Module[{s = Select[l, crit, 1]}, If[Length[s] == 0, default, First[s]]];
Cases[l_, patt_, levelspec_, n_Integer] := Module[{c = Cases[l, patt, levelspec]}, Take[c, Min[n, Length[c]]]];
Take[l_List, UpTo[n_Integer]] := Take[l, Min[n, Length[l]]];
Drop[l_List, UpTo[n_Integer]] := Drop[l, Min[n, Length[l]]];
Permutations[l_List] := DeleteDuplicates[permutationsAll[l]] /; Length[l] != Length[DeleteDuplicates[l]];
permutationsAll[{}] := {{}};
permutationsAll[l_List] := Flatten[Table[Prepend[#, l[[i]]] & /@ permutationsAll[Delete[l, i]], {i, Length[l]}], 1];

(* ---------- structural predicates with level specs ---------- *)
MemberQ[expr_, patt_, lev_] := Length[Position[expr, patt, lev, Heads -> False]] > 0 /; !ListQ[lev] || Length[lev] <= 2;
MemberQ[expr_, patt_, lev_, Heads -> h_] := Length[Position[expr, patt, lev, Heads -> h]] > 0;
MemberQ[expr_, patt_] := Length[Cases[expr, patt, {1}]] > 0 /; !ListQ[expr];
FreeQ[expr_, patt_, lev_] := Length[Position[expr, patt, lev, Heads -> True]] == 0;
DeleteCases[expr_, patt_] := Head[expr] @@ DeleteCases[List @@ expr, patt] /; !ListQ[expr] && !AtomQ[expr];
DeleteCases[expr_, patt_, lev_] := Head[expr] @@ DeleteCases[List @@ expr, patt, lev] /; !ListQ[expr] && !AtomQ[expr];

(* ---------- strings ---------- *)
StringStartsQ[s_String, p_] := StringMatchQ[s, p ~~ ___];
StringStartsQ[l_List, p_] := StringStartsQ[#, p] & /@ l;
StringEndsQ[s_String, p_] := StringMatchQ[s, ___ ~~ p];
StringEndsQ[l_List, p_] := StringEndsQ[#, p] & /@ l;
StringPosition[s_String, p_String, Overlaps -> True] := MathematicsNotebook`StringOverlapHits[s, p];
StringPosition[s_String, p_String] := MathematicsNotebook`StringOverlapHits[s, p];
StringPosition[s_String, p_String, Overlaps -> False] := Module[{h = MathematicsNotebook`StringOverlapHits[s, p], out = {}, last = 0}, Do[If[x[[1]] > last, AppendTo[out, x]; last = x[[2]]], {x, h}]; out];
StringCount[s_String, p_] := Length[StringCases[s, p]];
StringCount[s_String, p_, opts___] := Length[StringCases[s, p, opts]];
StringDelete[s_String, p_] := StringReplace[s, p -> ""];
StringDelete[l_List, p_] := StringDelete[#, p] & /@ l;
StringPadLeft[s_String, n_Integer] := StringPadLeft[s, n, " "];
StringPadLeft[s_String, n_Integer, pad_String] := If[StringLength[s] >= n, StringTake[s, -n], StringTake[StringRepeat[pad, n], -(n - StringLength[s])] <> s];
StringPadRight[s_String, n_Integer] := StringPadRight[s, n, " "];
StringPadRight[s_String, n_Integer, pad_String] := If[StringLength[s] >= n, StringTake[s, n], s <> StringTake[StringRepeat[pad, n], n - StringLength[s]]];
StringPartition[s_String, n_Integer] := StringJoin /@ Partition[Characters[s], n];
StringPartition[s_String, n_Integer, d_Integer] := StringJoin /@ Partition[Characters[s], n, d];
StringRotateLeft[s_String] := StringRotateLeft[s, 1];
StringRotateLeft[s_String, n_Integer] := StringJoin[RotateLeft[Characters[s], n]];
StringRotateRight[s_String] := StringRotateRight[s, 1];
StringRotateRight[s_String, n_Integer] := StringJoin[RotateRight[Characters[s], n]];
StringReplacePart[s_String, new_String, {i_Integer, j_Integer}] := StringTake[s, i - 1] <> new <> StringDrop[s, j];
StringReplacePart[s_String, new_String, spans : {{_Integer, _Integer} ..}] := StringReplacePart[s, ConstantArray[new, Length[spans]], spans];
StringReplacePart[s_String, news_List, spans : {{_Integer, _Integer} ..}] := Module[{r = s, o = Reverse[Ordering[First /@ spans]]},
  Do[r = StringReplacePart[r, news[[k]], spans[[k]]], {k, o}]; r];
StringExtract[s_String, n_Integer] := StringSplit[s][[n]];
StringExtract[s_String, sep_, n_Integer] := StringSplit[s, sep][[n]];
StringExtract[s_String, sep1_, n1_Integer, sep2_, n2_Integer] := StringSplit[StringSplit[s, sep1][[n1]], sep2][[n2]];
Capitalize[s_String] := If[s === "", "", ToUpperCase[StringTake[s, 1]] <> StringDrop[s, 1]];
Decapitalize[s_String] := If[s === "", "", ToLowerCase[StringTake[s, 1]] <> StringDrop[s, 1]];
Capitalize[l_List] := Capitalize /@ l;
StringRiffle[m : {__List}] := StringRiffle[StringRiffle /@ m, "\n"];
StringRiffle[m : {__List}, sep_String] := StringRiffle[StringRiffle /@ m, sep];
StringRiffle[m : {__List}, {l_, m2_, r_}, inner_] := l <> StringRiffle[StringRiffle[#, inner] & /@ m, m2] <> r;
StringSplit[s_String, p_, n_Integer?Positive] := Module[{parts = StringSplit[s, p]}, If[Length[parts] <= n, parts, Join[Take[parts, n - 1], {StringJoin[Riffle[Drop[parts, n - 1], stringSplitSep[s, p]]]}]]];
stringSplitSep[s_String, p_String] := p;
stringSplitSep[s_String, p_] := First[StringCases[s, p], ""];
StringSplit[s_String, lhs_ -> rhs_] := Riffle[StringSplit[s, lhs], rhs];
StringSplit[s_String, lhs_ :> rhs_] := Riffle[StringSplit[s, lhs], rhs];
AlphabeticOrder[a_String, b_String] := Order[a, b];
AlphabeticOrder[l_List] := Order @@@ Partition[l, 2, 1];
Transliterate[s_String] := RemoveDiacritics[s];
TemplateApply[t_String, args_List] := StringTemplate[t] @@ args;
TemplateApply[t_String, a_Association] := StringTemplate[t][a];
StringTemplate[t_String][args___] := templateFill[t, {args}];
templateFill[t_String, {a_Association}] := templateJoin[t, Function[k, ToString[a[k]]]];
templateFill[t_String, args_List] := templateJoin[t, Function[k, ToString[args[[ToExpression[k]]]]]];
templateJoin[t_String, f_] := Module[{chars = Characters[t], out = "", key = "", inKey = False},
  Do[If[c === "`", If[inKey, out = out <> f[key]; key = ""]; inKey = !inKey, If[inKey, key = key <> c, out = out <> c]], {c, chars}]; out];
NameQ[s_String] := MemberQ[Names[s], s];
LongestCommonSubsequence[a_String, b_String] := Module[{ca = Characters[a], cb = Characters[b], best = "", m = StringLength[a], n = StringLength[b]},
  Do[Module[{k = 0}, While[i + k <= m && j + k <= n && ca[[i + k]] === cb[[j + k]], k++]; If[k > StringLength[best], best = StringTake[a, {i, i + k - 1}]]], {i, m}, {j, n}]; best];
LongestCommonSequence[a_String, b_String] := Module[{ca = Characters[a], cb = Characters[b], m, n, L, i, j, out = {}},
  m = Length[ca]; n = Length[cb]; L = ConstantArray[0, {m + 1, n + 1}];
  Do[L[[i + 1, j + 1]] = If[ca[[i]] === cb[[j]], L[[i, j]] + 1, Max[L[[i, j + 1]], L[[i + 1, j]]]], {i, m}, {j, n}];
  i = m; j = n;
  While[i > 0 && j > 0, Which[ca[[i]] === cb[[j]], PrependTo[out, ca[[i]]]; i--; j--, L[[i, j + 1]] >= L[[i + 1, j]], i--, True, j--]];
  StringJoin[out]];
SequenceAlignment[a_String, b_String] := Module[{ca = Characters[a], cb = Characters[b], m, n, S, i, j, pa = {}, pb = {}, out = {}, pending = {}},
  m = Length[ca]; n = Length[cb]; S = ConstantArray[0, {m + 1, n + 1}];
  Do[S[[i + 1, 1]] = -i, {i, m}]; Do[S[[1, j + 1]] = -j, {j, n}];
  Do[S[[i + 1, j + 1]] = Max[S[[i, j]] + If[ca[[i]] === cb[[j]], 1, -1], S[[i, j + 1]] - 1, S[[i + 1, j]] - 1], {i, m}, {j, n}];
  i = m; j = n;
  While[i > 0 || j > 0,
    Which[i > 0 && j > 0 && S[[i + 1, j + 1]] == S[[i, j]] + If[ca[[i]] === cb[[j]], 1, -1], PrependTo[pa, ca[[i]]]; PrependTo[pb, cb[[j]]]; i--; j--,
      i > 0 && S[[i + 1, j + 1]] == S[[i, j + 1]] - 1, PrependTo[pa, ca[[i]]]; PrependTo[pb, ""]; i--,
      True, PrependTo[pa, ""]; PrependTo[pb, cb[[j]]]; j--]];
  Module[{segs = {}, cur = {"", ""}, same = Null},
    Do[If[pa[[k]] === pb[[k]], If[same === False && cur =!= {"", ""}, AppendTo[segs, cur]; cur = {"", ""}]; same = True; cur = {cur[[1]] <> pa[[k]], cur[[2]] <> pb[[k]]},
        If[same === True && cur =!= {"", ""}, AppendTo[segs, cur[[1]]]; cur = {"", ""}]; same = False; cur = {cur[[1]] <> pa[[k]], cur[[2]] <> pb[[k]]}], {k, Length[pa]}];
    If[cur =!= {"", ""}, AppendTo[segs, If[same, cur[[1]], cur]]]; segs]];

(* ---------- pattern constructs missing from Mathics ---------- *)
(* PatternSequence[a, b] is flattened into the surrounding argument list; a repeated
   PatternSequence[...].. becomes a Condition on the whole sequence; KeyValuePattern
   on Associations is checked with Lookup *)
(* called from the Python MatchQ override (list_string_extras.MatchQWolfram) *)
matchPatternSeq[expr_, patt_] := MatchQ[expr, patt //. h_[a___, Verbatim[PatternSequence][s___], b___] /; h =!= Repeated && h =!= RepeatedNull :> h[a, s, b]];
matchRepeatedSeq[expr_, h_[a___, Verbatim[Repeated][Verbatim[PatternSequence][s___]], b___]] := Module[{n = Length[{s}], args = List @@ expr, pre = Length[{a}], post = Length[{b}], mid},
  mid = Take[args, {pre + 1, Length[args] - post}];
  Head[expr] === h && MatchQ[Take[args, pre], {a}] && MatchQ[Take[args, -post], {b}] && Mod[Length[mid], n] == 0 && AllTrue[Partition[mid, n], MatchQ[#, {s}] &]];
matchOrderlessSeq[expr_, h_[Verbatim[OrderlessPatternSequence][s___]]] := Module[{args = List @@ expr}, Head[expr] === h && Length[args] == Length[{s}] && AnyTrue[Permutations[args], MatchQ[#, {s}] &]];
matchKeyValue[a_Association, KeyValuePattern[rules_List]] := AllTrue[rules, MatchQ[a[#[[1]]], #[[2]]] &];
matchKeyValue[a_Association, KeyValuePattern[rule_]] := matchKeyValue[a, KeyValuePattern[{rule}]];
matchKeyValue[___] := False;
matchRepeatedSeq[___] := False;
matchOrderlessSeq[___] := False;

(* ---------- Boolean algebra ---------- *)
Implies[x_, True] := True;
Implies[False, y_] := True;
Implies[x_, False] := !x;
Implies[True, y_] := y;
Equivalent[a_, a_] := True;
BooleanTable[expr_, vars_List] := Table[expr /. Thread[vars -> t], {t, Tuples[{True, False}, Length[vars]]}] /; Length[vars] >= 1 && !ListQ[First[vars]];
BooleanTable[expr_, vs1_List, vs2_List] := Table[Table[expr /. Thread[Join[vs1, vs2] -> Join[a, b]], {b, Tuples[{True, False}, Length[vs2]]}], {a, Tuples[{True, False}, Length[vs1]]}];
BooleanTable[expr_] := BooleanTable[expr, booleanVars[expr]];
SatisfiabilityCount[expr_, vars_List] := Count[BooleanTable[expr, vars], True];
SatisfiabilityCount[expr_] := SatisfiabilityCount[expr, booleanVars[expr]];
SatisfiableQ[expr_, vars_List] := SatisfiabilityCount[expr, vars] > 0;
SatisfiableQ[expr_] := SatisfiableQ[expr, booleanVars[expr]];
TautologyQ[expr_, vars_List] := SatisfiabilityCount[expr, vars] == 2^Length[vars];
TautologyQ[expr_] := TautologyQ[expr, booleanVars[expr]];
SatisfiabilityInstances[expr_, vars_List] := Select[Tuples[{True, False}, Length[vars]], TrueQ[expr /. Thread[vars -> #]] &][[;; 1]];
SatisfiabilityInstances[expr_, vars_List, n_Integer] := Take[Select[Tuples[{True, False}, Length[vars]], TrueQ[expr /. Thread[vars -> #]] &], UpTo[n]];
booleanVars[expr_] := DeleteDuplicates[Cases[expr, _Symbol?(!MemberQ[{True, False}, #] &), {-1}]];
"""

# Heads that must exist in System` before the rules are parsed (otherwise the
# definitions land in the private context).
_HEADS = [
    "Range", "Subdivide", "Array", "DiagonalMatrix", "Differences", "Ratios", "MinMax", "Ordering", "ReverseSortBy",
    "NumericalSort", "TakeWhile", "LengthWhile", "Extract", "Counts", "CountsBy", "DeleteDuplicatesBy", "Join", "Insert",
    "Riffle", "Partition", "Transpose", "Thread", "Distribute", "MapAll", "FoldPair", "NestWhileList", "NestWhile",
    "ComposeList", "RightComposition", "SelectFirst", "Cases", "Nothing", "Permutations",
    "StringStartsQ", "StringEndsQ", "StringCount", "StringDelete", "StringPadLeft", "StringPadRight", "StringPartition",
    "StringRotateLeft", "StringRotateRight", "StringReplacePart", "StringExtract", "Capitalize", "Decapitalize",
    "StringRiffle", "StringSplit", "AlphabeticOrder", "Transliterate", "TemplateApply", "StringTemplate", "NameQ",
    "LongestCommonSubsequence", "LongestCommonSequence", "SequenceAlignment",
    "Implies", "Equivalent", "BooleanTable", "SatisfiabilityCount", "SatisfiableQ", "TautologyQ", "SatisfiabilityInstances",
    "Scaled", "UpTo", "Missing", "MemberQ", "FreeQ", "DeleteCases", "Take", "Drop",
    "PatternSequence", "OrderlessPatternSequence", "KeyValuePattern", "MatchQ", "FoldPairList", "BooleanTable",
]


def _statements(code):
    out, buf, depth, i, n = [], [], 0, 0, len(code)
    in_str = False
    while i < n:
        if not in_str and code.startswith("(*", i):
            j = code.find("*)", i)
            i = j + 2 if j >= 0 else n
            continue
        c = code[i]
        if c == '"' and (i == 0 or code[i - 1] != "\\"):
            in_str = not in_str
        if not in_str:
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
                i += 1
                continue
        buf.append(c)
        i += 1
    s = "".join(buf).strip()
    if s:
        out.append(s)
    return out


def register_list_rules(session):
    for name in _HEADS:
        session.definitions.get_definition(f"System`{name}")
        session.definitions.clear_cache(f"System`{name}")
    session.evaluate("Unprotect[" + ", ".join(_HEADS) + "]")
    session.evaluate('Begin["MathematicsNotebook`Lists`"]')
    try:
        for stmt in _statements(RULES):
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
