"""Builtins found missing by differential testing against the real kernel
(wolfram-re-round2/oracle/extended-diff.json).  Thin SymPy wrappers; each one
follows the installed Usage.m contract and returns unevaluated on bad input.
"""

from __future__ import annotations

import sympy

from mathics.core.atoms import Integer, MachineReal
from mathics.core.attributes import A_LISTABLE, A_PROTECTED, A_READ_PROTECTED, A_NUMERIC_FUNCTION, A_HOLD_ALL
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol, SymbolTrue, SymbolFalse

SymbolRule = Symbol("System`Rule")


def _s(e):
    v = e.to_sympy()
    return v if isinstance(v, sympy.Basic) else None


def _ints(*es):
    out = [e.get_int_value() for e in es]
    return None if any(v is None for v in out) else out


def _matrix(m):
    if not m.has_form("List", None):
        return None
    rows = []
    for row in m.elements:
        if not row.has_form("List", None):
            return None
        r = [_s(el) for el in row.elements]
        if any(x is None for x in r):
            return None
        rows.append(r)
    if not rows or any(len(r) != len(rows[0]) for r in rows):
        return None
    return sympy.Matrix(rows)


def _from_matrix(M):
    return ListExpression(*(ListExpression(*(from_sympy(M[i, j]) for j in range(M.cols))) for i in range(M.rows)))


def _bool(b):
    return SymbolTrue if b else SymbolFalse


# ---------------------------------------------------------------------------
# polynomial algebra
# ---------------------------------------------------------------------------

class Discriminant(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, p, x, evaluation):
        "Discriminant[p_, x_Symbol]"
        ps, xs = _s(p), _s(x)
        if ps is None:
            return None
        try:
            return from_sympy(sympy.expand(sympy.discriminant(ps, xs)))
        except Exception:
            return None


class PolynomialGCD(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, ps, evaluation):
        "PolynomialGCD[ps__]"
        vals = [_s(e) for e in ps.get_sequence()]
        if any(v is None for v in vals):
            return None
        try:
            g = vals[0]
            for v in vals[1:]:
                g = sympy.gcd(g, v)
            return from_sympy(sympy.factor_terms(g))
        except Exception:
            return None


class PolynomialLCM(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, ps, evaluation):
        "PolynomialLCM[ps__]"
        vals = [_s(e) for e in ps.get_sequence()]
        if any(v is None for v in vals):
            return None
        try:
            g = vals[0]
            for v in vals[1:]:
                g = sympy.lcm(g, v)
            return from_sympy(sympy.factor(g))
        except Exception:
            return None


class FactorTerms(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, p, evaluation):
        "FactorTerms[p_]"
        ps = _s(p)
        if ps is None:
            return None
        try:
            return from_sympy(sympy.factor_terms(ps))
        except Exception:
            return None


class TrigFactor(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, e, evaluation):
        "TrigFactor[e_]"
        s = _s(e)
        if s is None:
            return None
        from sympy.simplify.fu import TR9, TR10i, TR11
        try:
            r = sympy.factor(TR10i(TR9(s)))
            # expand double angles so the factored form uses single-angle trig
            # (Wolfram: Sin[x] + Sin[3 x] -> 4 Cos[x]^2 Sin[x])
            r2 = sympy.factor(TR11(r))
            return from_sympy(r2 if sympy.count_ops(r2) <= sympy.count_ops(r) + 1 else r)
        except Exception:
            return None


class TrigToExp(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, e, evaluation):
        "TrigToExp[e_]"
        s = _s(e)
        if s is None:
            return None
        try:
            return from_sympy(sympy.expand(s.rewrite(sympy.exp)))
        except Exception:
            return None


class ExpToTrig(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, e, evaluation):
        "ExpToTrig[e_]"
        s = _s(e)
        if s is None:
            return None
        try:
            r = s.rewrite(sympy.cos)
            return from_sympy(sympy.expand(r))
        except Exception:
            return None


class FunctionExpand(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, e, evaluation):
        "FunctionExpand[e_]"
        s = _s(e)
        if s is None:
            return None
        try:
            r = sympy.expand_func(s)
            if r == s:
                r = sympy.gammasimp(s)
            return from_sympy(r)
        except Exception:
            return None


class Dt(Builtin):
    """Total derivative: Dt[f] -> Sum_i D[f, x_i] Dt[x_i]; Dt[f, x] -> total derivative w.r.t. x."""
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, f, evaluation):
        "Dt[f_]"
        s = _s(f)
        if s is None:
            return None
        total = sympy.Integer(0)
        for v in sorted(s.free_symbols, key=lambda t: t.name):
            dv = Expression(Symbol("System`Dt"), from_sympy(v))
            total_m = from_sympy(sympy.diff(s, v))
            total = total + sympy.Symbol("__dt_" + v.name) * sympy.diff(s, v)
        out = from_sympy(total)
        # replace placeholder symbols by Dt[var]
        def fix(e):
            if isinstance(e, Symbol) and e.get_name().split("`")[-1].startswith("__dt_"):
                name = e.get_name().split("__dt_")[-1]
                return Expression(Symbol("System`Dt"), Symbol(name if "`" in name else "Global`" + name.split("_")[-1]))
            if isinstance(e, Expression):
                return Expression(fix(e.head), *(fix(x) for x in e.elements))
            return e
        return fix(out)


# ---------------------------------------------------------------------------
# number theory / bits
# ---------------------------------------------------------------------------

class ExtendedGCD(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, a, b, evaluation):
        "ExtendedGCD[a_Integer, b_Integer]"
        x, y = a.get_int_value(), b.get_int_value()
        s, t, g = sympy.gcdex(x, y)
        return ListExpression(Integer(int(g)), ListExpression(Integer(int(s)), Integer(int(t))))


class MultiplicativeOrder(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, k, n, evaluation):
        "MultiplicativeOrder[k_Integer, n_Integer]"
        try:
            return Integer(int(sympy.n_order(k.get_int_value(), n.get_int_value())))
        except Exception:
            return None


class PrimitiveRoot(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "PrimitiveRoot[n_Integer]"
        try:
            r = sympy.primitive_root(n.get_int_value())
        except Exception:
            return None
        return Integer(int(r)) if r is not None else None


class PrimitiveRootList(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "PrimitiveRootList[n_Integer]"
        m = n.get_int_value()
        if m is None or m < 1 or m > 10**6:
            return None
        try:
            if not sympy.ntheory.residue_ntheory.is_primitive_root(sympy.primitive_root(m), m):
                return ListExpression()
        except Exception:
            return ListExpression()
        roots = [g for g in range(1, m) if sympy.gcd(g, m) == 1 and sympy.ntheory.residue_ntheory.is_primitive_root(g, m)]
        return ListExpression(*(Integer(g) for g in roots))


def _bitop(name, fn, unary=False):
    class _B(Builtin):
        attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
        def eval(self, args, evaluation):
            "%(name)s[args__Integer]"
            vals = _ints(*args.get_sequence())
            if vals is None:
                return None
            if unary:
                return Integer(fn(vals[0])) if len(vals) == 1 else None
            acc = vals[0]
            for v in vals[1:]:
                acc = fn(acc, v)
            return Integer(acc)
    _B.__name__ = name
    _B.name = name
    return _B


BitAnd = _bitop("BitAnd", lambda a, b: a & b)
BitOr = _bitop("BitOr", lambda a, b: a | b)
BitXor = _bitop("BitXor", lambda a, b: a ^ b)
BitNot = _bitop("BitNot", lambda a: ~a, unary=True)


class BitShiftLeft(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, k, evaluation):
        "BitShiftLeft[n_Integer, k_Integer]"
        a, b = _ints(n, k)
        return Integer(a << b) if b >= 0 else Integer(a >> -b)


class BitShiftRight(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, k, evaluation):
        "BitShiftRight[n_Integer, k_Integer]"
        a, b = _ints(n, k)
        return Integer(a >> b) if b >= 0 else Integer(a << -b)


class SquareFreeQ(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "SquareFreeQ[n_Integer]"
        v = n.get_int_value()
        if v == 0:
            return SymbolFalse
        return _bool(all(e == 1 for e in sympy.factorint(abs(v)).values()))


class PerfectNumberQ(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "PerfectNumberQ[n_Integer]"
        v = n.get_int_value()
        return _bool(v > 0 and sympy.divisor_sigma(v) == 2 * v)


class PartitionsQ(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "PartitionsQ[n_Integer]"
        v = n.get_int_value()
        if v is None or v < 0:
            return None
        return Integer(int(sympy.npartitions(v)) if False else _partitions_distinct(v))


def _partitions_distinct(n):
    # q(n): partitions into distinct parts, via Euler's recurrence with pentagonal-free DP
    q = [0] * (n + 1)
    q[0] = 1
    for part in range(1, n + 1):
        for total in range(n, part - 1, -1):
            q[total] += q[total - part]
    return q[n]


class Convergents(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, x, n, evaluation):
        "Convergents[x_, n_Integer]"
        xs = _s(x)
        k = n.get_int_value()
        if xs is None or k is None or k < 1:
            return None
        try:
            cf = sympy.continued_fraction_iterator(xs)
            terms = []
            for _ in range(k):
                terms.append(next(cf))
        except Exception:
            return None
        convs = list(sympy.continued_fraction_convergents(terms))
        return ListExpression(*(from_sympy(c) for c in convs))

    def eval_list(self, cf, evaluation):
        "Convergents[cf_List]"
        terms = _ints(*cf.elements)
        if terms is None:
            return None
        return ListExpression(*(from_sympy(c) for c in sympy.continued_fraction_convergents(terms)))


# ---------------------------------------------------------------------------
# special functions / distributions-as-functions
# ---------------------------------------------------------------------------

class KroneckerDelta(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    rules = {"KroneckerDelta[]": "1"}
    def eval(self, args, evaluation):
        "KroneckerDelta[args__]"
        seq = args.get_sequence()
        vals = [_s(e) for e in seq]
        if any(v is None for v in vals):
            return None
        if all(v.is_number for v in vals):
            return Integer(1 if all(v == vals[0] for v in vals) else 0)
        if len(vals) == 2:
            r = sympy.KroneckerDelta(vals[0], vals[1])
            return from_sympy(r) if not isinstance(r, sympy.KroneckerDelta) else None
        return None


class HeavisideTheta(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    def eval(self, x, evaluation):
        "HeavisideTheta[x_]"
        v = _s(x)
        if v is None or not v.is_number or v == 0:
            return None
        return Integer(1 if v > 0 else 0)


class DiracDelta(Builtin):
    attributes = A_LISTABLE | A_PROTECTED | A_READ_PROTECTED
    def eval(self, x, evaluation):
        "DiracDelta[x_]"
        v = _s(x)
        if v is None or not v.is_number or v == 0:
            return None
        return Integer(0)


def _mpfun(name, fn, sym=None):
    class _M(Builtin):
        attributes = A_LISTABLE | A_NUMERIC_FUNCTION | A_PROTECTED | A_READ_PROTECTED
        def eval(self, x, evaluation):
            "%(name)s[x_]"
            v = _s(x)
            if v is None:
                return None
            if sym is not None:
                try:
                    r = sym(v)
                    if v.is_number and not x.is_machine_precision():
                        if not isinstance(r, type(sym(sympy.Symbol("_z")))):
                            return from_sympy(r)
                        return None
                    if x.is_machine_precision():
                        return MachineReal(float(sympy.N(r)))
                    return from_sympy(r) if not isinstance(r, type(sym(sympy.Symbol("_z")))) else None
                except Exception:
                    return None
            return None
    _M.__name__ = name
    _M.name = name
    return _M


SinIntegral = _mpfun("SinIntegral", None, sympy.Si)
CosIntegral = _mpfun("CosIntegral", None, sympy.Ci)
LogIntegral = _mpfun("LogIntegral", None, sympy.li)


class GeometricMean(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, li, evaluation):
        "GeometricMean[li_List]"
        vals = [_s(e) for e in li.elements]
        if not vals or any(v is None for v in vals):
            return None
        prod = sympy.Integer(1)
        for v in vals:
            prod *= v
        return from_sympy(sympy.root(prod, len(vals)))


class HarmonicMean(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, li, evaluation):
        "HarmonicMean[li_List]"
        vals = [_s(e) for e in li.elements]
        if not vals or any(v is None for v in vals):
            return None
        return from_sympy(sympy.simplify(len(vals) / sum(1 / v for v in vals)))


# ---------------------------------------------------------------------------
# linear algebra
# ---------------------------------------------------------------------------

class Minors(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, m, evaluation):
        "Minors[m_List]"
        M = _matrix(m)
        if M is None or M.rows != M.cols:
            return None
        n = M.rows
        # Verified against Wolfram 15.0.1: Minors[{{1,2},{3,4}}] == {{1,2},{3,4}},
        # i.e. entry (i,j) uses the row subset omitting row n-1-i... in practice the
        # (n-1)-subsets enumerated in lexicographic order, rows x cols.
        import itertools
        subsets = list(itertools.combinations(range(n), n - 1))
        out = sympy.Matrix(n, n, lambda i, j: M.extract(list(subsets[i]), list(subsets[j])).det())
        return _from_matrix(out)


class SingularValueList(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, m, evaluation):
        "SingularValueList[m_List]"
        M = _matrix(m)
        if M is None:
            return None
        try:
            vals = sorted((v for v in M.singular_values() if v != 0), key=lambda v: -float(sympy.N(v)))
        except Exception:
            return None
        return ListExpression(*(from_sympy(sympy.simplify(v)) for v in vals))


class LUDecomposition(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, m, evaluation):
        "LUDecomposition[m_List]"
        M = _matrix(m)
        if M is None or M.rows != M.cols:
            return None
        try:
            L, U, perm = M.LUdecomposition()
        except Exception:
            return None
        # Wolfram packs L (below diagonal) and U (on/above) into one matrix, with a 1-based permutation and condition number
        n = M.rows
        packed = sympy.Matrix(n, n, lambda i, j: L[i, j] if i > j else U[i, j])
        p = list(range(n))
        for a, b in perm:
            p[a], p[b] = p[b], p[a]
        return ListExpression(_from_matrix(packed), ListExpression(*(Integer(i + 1) for i in p)), Integer(1))


class CholeskyDecomposition(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, m, evaluation):
        "CholeskyDecomposition[m_List]"
        M = _matrix(m)
        if M is None or M.rows != M.cols:
            return None
        try:
            L = M.cholesky()
        except Exception:
            return None
        return _from_matrix(L.T.applyfunc(sympy.simplify))  # Wolfram returns upper-triangular U with U^T U = m


class HilbertMatrix(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "HilbertMatrix[n_Integer]"
        k = n.get_int_value()
        if k is None or k < 1 or k > 200:
            return None
        return _from_matrix(sympy.Matrix(k, k, lambda i, j: sympy.Rational(1, i + j + 1)))


class ToeplitzMatrix(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "ToeplitzMatrix[n_Integer]"
        k = n.get_int_value()
        if k is None or k < 1 or k > 200:
            return None
        return _from_matrix(sympy.Matrix(k, k, lambda i, j: abs(i - j) + 1))

    def eval_list(self, c, evaluation):
        "ToeplitzMatrix[c_List]"
        vals = [_s(e) for e in c.elements]
        k = len(vals)
        return _from_matrix(sympy.Matrix(k, k, lambda i, j: vals[abs(i - j)]))


class HankelMatrix(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, n, evaluation):
        "HankelMatrix[n_Integer]"
        k = n.get_int_value()
        if k is None or k < 1 or k > 200:
            return None
        return _from_matrix(sympy.Matrix(k, k, lambda i, j: (i + j + 1) if i + j < k else 0))


class ArrayFlatten(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, blocks, evaluation):
        "ArrayFlatten[blocks_List]"
        rows = []
        try:
            for brow in blocks.elements:
                mats = []
                for b in brow.elements:
                    if b.has_form("List", None):
                        M = _matrix(b)
                        if M is None:
                            return None
                        mats.append(M)
                    else:
                        mats.append(("scalar", _s(b)))
                # determine block sizes
                h = max((m.rows for m in mats if isinstance(m, sympy.Matrix)), default=None)
                if h is None:
                    return None
                fixed = []
                for m in mats:
                    if isinstance(m, sympy.Matrix):
                        fixed.append(m)
                    else:
                        fixed.append(None)
                rows.append(fixed)
            # column widths
            ncols = len(rows[0])
            widths = [None] * ncols
            heights = [None] * len(rows)
            for i, r in enumerate(rows):
                for j, m in enumerate(r):
                    if m is not None:
                        widths[j] = m.cols
                        heights[i] = m.rows
            full = []
            for i, r in enumerate(rows):
                parts = []
                for j, m in enumerate(r):
                    if m is None:
                        m = sympy.zeros(heights[i], widths[j])
                    parts.append(m)
                full.append(sympy.Matrix.hstack(*parts))
            return _from_matrix(sympy.Matrix.vstack(*full))
        except Exception:
            return None


# ---------------------------------------------------------------------------
# solving
# ---------------------------------------------------------------------------

class Roots(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, eq, x, evaluation):
        "Roots[eq_Equal, x_Symbol]"
        lhs, rhs = (_s(e) for e in eq.elements)
        xs = _s(x)
        if lhs is None or rhs is None:
            return None
        try:
            sols = sympy.roots(sympy.Poly(lhs - rhs, xs))
        except Exception:
            return None
        if not sols:
            return None
        items = []
        for r, mult in sorted(sols.items(), key=lambda kv: (sympy.re(kv[0]), sympy.im(kv[0]))):
            items.extend([Expression(Symbol("System`Equal"), x, from_sympy(r))] * mult)
        return items[0] if len(items) == 1 else Expression(Symbol("System`Or"), *items)


class NSolve(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, eqs, vars, evaluation):
        "NSolve[eqs_, vars_]"
        eq_list = eqs.elements if eqs.has_form("List", None) else (eqs,)
        var_list = vars.elements if vars.has_form("List", None) else (vars,)
        exprs = []
        for e in eq_list:
            if e.get_head_name() != "System`Equal" or len(e.elements) != 2:
                return None
            l, r = (_s(t) for t in e.elements)
            if l is None or r is None:
                return None
            exprs.append(l - r)
        vs = [_s(v) for v in var_list]
        if any(v is None for v in vs):
            return None
        sols = None
        try:
            if len(exprs) == 1 and len(vs) == 1 and exprs[0].is_polynomial(vs[0]):
                rts = sympy.Poly(exprs[0], vs[0]).nroots(n=15)
                sols = [{vs[0]: r} for r in rts]
            else:
                raw = sympy.solve(exprs, vs, dict=True)
                sols = [{k: sympy.N(v, 15) for k, v in s.items()} for s in raw]
        except Exception:
            sols = None
        if not sols:
            # transcendental single equation: scan for sign changes then refine
            if len(exprs) == 1 and len(vs) == 1:
                f = sympy.lambdify(vs[0], exprs[0], "math")
                found = []
                import math
                prev = None
                for i in range(-200, 201):
                    xx = i / 10
                    try:
                        val = f(xx)
                    except Exception:
                        prev = None
                        continue
                    if prev is not None and prev[1] * val < 0:
                        try:
                            root = sympy.nsolve(exprs[0], vs[0], (prev[0] + xx) / 2)
                            if all(abs(root - r) > 1e-9 for r in found):
                                found.append(root)
                        except Exception:
                            pass
                    prev = (xx, val)
                if found:
                    sols = [{vs[0]: r} for r in sorted(found, key=lambda r: float(sympy.re(r)))]
        if not sols:
            return None

        def num(v):
            c = complex(v)
            if abs(c.imag) < 1e-12 * max(1, abs(c.real)):
                return MachineReal(c.real)
            return from_sympy(sympy.Float(c.real) + sympy.I * sympy.Float(c.imag))

        return ListExpression(*(ListExpression(*(Expression(SymbolRule, var_list[i], num(s[vs[i]])) for i in range(len(vs)) if vs[i] in s)) for s in sols))


class Eliminate(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, eqs, vars, evaluation):
        "Eliminate[eqs_, vars_]"
        eq_list = eqs.elements if eqs.has_form("List", None) else (eqs,)
        var_list = vars.elements if vars.has_form("List", None) else (vars,)
        exprs = []
        for e in eq_list:
            if e.get_head_name() != "System`Equal":
                return None
            l, r = (_s(t) for t in e.elements)
            exprs.append(l - r)
        vs = [_s(v) for v in var_list]
        try:
            all_syms = sorted(set().union(*(e.free_symbols for e in exprs)), key=lambda s: s.name)
            keep = [s for s in all_syms if s not in vs]
            G = sympy.groebner(exprs, *vs, *keep, order="lex")
            elim = [g for g in G.exprs if not any(g.has(v) for v in vs)]
        except Exception:
            return None
        if not elim:
            return SymbolTrue
        # Wolfram moves the parameter-only terms to the right-hand side: -1 + 2 x == a
        parts = []
        for g in elim:
            g = sympy.expand(g)
            # g has no eliminated vars; split into (terms with remaining unknowns) == -(parameter terms)
            unknown_syms = [s for s in g.free_symbols if s not in vs]
            lhs = sympy.Integer(0)
            rhs = sympy.Integer(0)
            for term in sympy.Add.make_args(g):
                if any(term.has(u) for u in unknown_syms[:1]):
                    lhs += term
                else:
                    rhs -= term
            if lhs == 0:
                lhs, rhs = g, sympy.Integer(0)
            # normalise sign so the leading unknown has positive coefficient
            lead = next((u for u in unknown_syms), None)
            if lead is not None and sympy.Poly(lhs, lead).LC() < 0:
                lhs, rhs = -lhs, -rhs
            parts.append(Expression(Symbol("System`Equal"), from_sympy(lhs), from_sympy(rhs)))
        return parts[0] if len(parts) == 1 else Expression(Symbol("System`And"), *parts)


class FindInstance(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    def eval(self, expr, vars, evaluation):
        "FindInstance[expr_, vars_]"
        return self._find(expr, vars, None, evaluation)

    def eval_dom(self, expr, vars, dom, evaluation):
        "FindInstance[expr_, vars_, dom_Symbol]"
        return self._find(expr, vars, dom.get_name(), evaluation)

    @staticmethod
    def _find(expr, vars, dom, evaluation):
        from distributions import _predicate_to_sympy
        var_list = vars.elements if vars.has_form("List", None) else (vars,)
        vs = [_s(v) for v in var_list]
        if dom == "System`Integers":
            vs_t = [sympy.Symbol(v.name, integer=True) for v in vs]
        elif dom == "System`Reals":
            vs_t = [sympy.Symbol(v.name, real=True) for v in vs]
        else:
            vs_t = vs
        cond = _predicate_to_sympy(expr) if expr.get_head_name() != "System`Equal" else _s(expr)
        if cond is None:
            return None
        cond = cond.subs(dict(zip(vs, vs_t)))
        sol = None
        try:
            if isinstance(cond, sympy.Eq) or isinstance(cond, sympy.core.relational.Relational) and isinstance(cond, sympy.Equality):
                sols = sympy.solve(cond, vs_t, dict=True)
                sol = sols[0] if sols else None
            elif dom == "System`Integers":
                # brute-force small box for integer feasibility
                import itertools
                f = sympy.lambdify(vs_t, cond, "math")
                for combo in itertools.product(range(-30, 31), repeat=len(vs_t)):
                    try:
                        if f(*combo):
                            sol = dict(zip(vs_t, [sympy.Integer(c) for c in combo]))
                            break
                    except Exception:
                        continue
            else:
                from sympy.solvers.inequalities import reduce_inequalities
                r = reduce_inequalities(cond, vs_t[0]) if len(vs_t) == 1 else None
                if r is not None and r is not sympy.false:
                    # pick a point in the first interval
                    s = sympy.solveset(r, vs_t[0], sympy.S.Reals)
                    if isinstance(s, sympy.Interval):
                        a, b = s.start, s.end
                        pt = (a + b) / 2 if a.is_finite and b.is_finite else (a + 1 if a.is_finite else (b - 1 if b.is_finite else 0))
                        sol = {vs_t[0]: pt}
        except Exception:
            sol = None
        if not sol:
            return ListExpression()
        rules = [Expression(SymbolRule, var_list[i], from_sympy(sol[vs_t[i]])) for i in range(len(vs)) if vs_t[i] in sol]
        return ListExpression(ListExpression(*rules))


def register_more_builtins(session):
    classes = (Discriminant, PolynomialGCD, PolynomialLCM, FactorTerms, TrigFactor, TrigToExp, ExpToTrig, FunctionExpand, Dt,
               ExtendedGCD, MultiplicativeOrder, PrimitiveRoot, PrimitiveRootList, BitAnd, BitOr, BitXor, BitNot, BitShiftLeft, BitShiftRight,
               SquareFreeQ, PerfectNumberQ, PartitionsQ, Convergents, KroneckerDelta, HeavisideTheta, DiracDelta,
               SinIntegral, CosIntegral, LogIntegral, GeometricMean, HarmonicMean,
               Minors, SingularValueList, LUDecomposition, CholeskyDecomposition, HilbertMatrix, ToeplitzMatrix, HankelMatrix, ArrayFlatten,
               Roots, NSolve, Eliminate, FindInstance)
    for cls in classes:
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
