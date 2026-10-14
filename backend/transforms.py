"""Integral and discrete transforms, aligned with Wolfram 15.0.1 conventions.

  LaplaceTransform / InverseLaplaceTransform     SymPy, dropping the implicit HeavisideTheta[t]
  FourierTransform family                        even/odd split -> cosine/sine transforms
                                                 (Wolfram's {0,1} convention is SymPy's
                                                 sine/cosine convention), plus distribution
                                                 table entries (constants, sign, pure trig)
                                                 and FourierParameters -> {a, b} scaling
  MellinTransform / InverseMellinTransform       SymPy; the inverse probes a short list of
                                                 fundamental-strip candidates
  Convolve                                       direct integration with UnitStep factors
                                                 folded into the integration bounds
  ZTransform                                     geometric-series closed forms:
                                                 f[n] decomposed as c * n^m * r^n * {1, cos, sin}
  InverseZTransform                              residues of F(z) z^(n-1) at nonzero poles,
                                                 KroneckerDelta terms for poles at z == 0

Everything goes through ``_conv`` (Mathics -> SymPy) which additionally maps
UnitStep / HeavisideTheta / DiracDelta / DiscreteDelta / KroneckerDelta heads
that stock Mathics3 10.0.1 does not convert.  Unsupported inputs stay
unevaluated (``None``) rather than risking a wrong answer.
"""

from __future__ import annotations

import sympy

from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import SympyExpression, from_sympy
from mathics.core.expression import Expression
from mathics.core.symbols import Symbol


# ---------------------------------------------------------------------------
# Mathics <-> SymPy conversion
# ---------------------------------------------------------------------------

def _has_unknown_head(s) -> bool:
    """True if a SymPy expression still carries unconverted Mathics heads."""
    return any(isinstance(a, SympyExpression) for a in sympy.preorder_traversal(s))


def _conv(e):
    """Mathics expression -> SymPy, with extra heads SymPy conversion misses."""
    if not isinstance(e, Expression):
        try:
            return e.to_sympy()
        except Exception:
            return None
    head = e.get_head_name()
    bare = head.split("`")[-1]
    if bare in ("UnitStep", "HeavisideTheta"):
        args = [_conv(x) for x in e.elements]
        if not args or any(a is None for a in args):
            return None
        steps = [sympy.Heaviside(a, 1) for a in args]
        return sympy.Mul(*steps) if len(steps) > 1 else steps[0]
    if bare == "DiracDelta" and len(e.elements) >= 1:
        args = [_conv(x) for x in e.elements]
        if any(a is None for a in args):
            return None
        return sympy.DiracDelta(*args)
    if bare in ("DiscreteDelta", "KroneckerDelta"):
        args = [_conv(x) for x in e.elements]
        if any(a is None for a in args):
            return None
        if len(args) == 1:
            args.append(sympy.S.Zero)
        return sympy.KroneckerDelta(*args)
    try:
        s = e.to_sympy()
    except Exception:
        s = None
    if s is not None and not _has_unknown_head(s):
        return s
    # Rebuild structural heads from converted elements (e.g. Times[UnitStep[..], E^-x]).
    builder = {"System`Times": sympy.Mul, "System`Plus": sympy.Add, "System`Power": sympy.Pow,
               "Global`Times": sympy.Mul, "Global`Plus": sympy.Add, "Global`Power": sympy.Pow}.get(head)
    if builder is None:
        return None
    args = [_conv(x) for x in e.elements]
    if any(a is None for a in args):
        return None
    return builder(*args)


def _usable(res, *hidden) -> bool:
    """Reject None, infinities, leftover integrals / transforms, and leaked variables."""
    if res is None or not isinstance(res, sympy.Basic):
        return False
    if res.has(sympy.oo) or res.has(-sympy.oo) or res.has(sympy.zoo) or res.has(sympy.nan):
        return False
    if res.has(sympy.Integral):
        return False
    if any(isinstance(a, sympy.integrals.transforms.IntegralTransform)
           for a in sympy.preorder_traversal(res)):
        return False
    if any(res.has(v) for v in hidden):
        return False
    return True


def _call_transform(fn, *args):
    """Call a SymPy integral transform; unwrap (value, cond) tuples; None on failure."""
    try:
        res = fn(*args, noconds=True)
    except TypeError:
        try:
            res = fn(*args)
        except Exception:
            return None
    except Exception:
        return None
    if isinstance(res, tuple):
        res = res[0] if res else None
    return res


# ---------------------------------------------------------------------------
# Result post-processing
# ---------------------------------------------------------------------------

def _map_heaviside(mexpr, target_name):
    """Mathics-level: System`Heaviside[x, h] -> System`<target>[x], recursively."""
    target = Symbol(f"System`{target_name}")
    heaviside = "System`Heaviside"

    def walk(e):
        if isinstance(e, Expression):
            if e.get_head_name() == heaviside and e.elements:
                return Expression(target, walk(e.elements[0]))
            return Expression(walk(e.head), *(walk(x) for x in e.elements))
        return e

    return walk(mexpr)


def _kd_single_arg(mexpr):
    """Mathics-level: KroneckerDelta[a, 0] -> KroneckerDelta[a] (Wolfram prints one arg)."""
    kd = "System`KroneckerDelta"

    def walk(e):
        if isinstance(e, Expression):
            if e.get_head_name() == kd and len(e.elements) == 2:
                first, second = e.elements
                if second.get_int_value() == 0:
                    return Expression(e.head, walk(first))
                if first.get_int_value() == 0:
                    return Expression(e.head, walk(second))
            return Expression(walk(e.head), *(walk(x) for x in e.elements))
        return e

    return walk(mexpr)


def _drop_heaviside_factor(res, t):
    """Drop a multiplicative Heaviside(t) factor (Wolfram omits the implicit one).

    Handles bare Heaviside(t), Mul forms, and sums where every term carries
    the same factor, e.g. Heaviside(t) - E^-t Heaviside(t).
    """
    def is_ht(fac):
        return isinstance(fac, sympy.Heaviside) and fac.args[0] == t

    if is_ht(res):
        return sympy.S.One
    if isinstance(res, sympy.Mul):
        keep = [fac for fac in res.args if not is_ht(fac)]
        if len(keep) != len(res.args):
            return sympy.Mul(*keep)
        return res
    if isinstance(res, sympy.Add):
        stripped = []
        for term in res.args:
            factors = sympy.Mul.make_args(term)
            if not any(is_ht(fac) for fac in factors):
                return res
            stripped.append(sympy.Mul(*[fac for fac in factors if not is_ht(fac)]))
        return sympy.Add(*stripped)
    return res


def _fix_deltas(expr, v):
    """DiracDelta(c*v + d) -> DiracDelta(v + d/c)/|c| for numeric nonzero c."""
    out = expr
    for d in list(out.atoms(sympy.DiracDelta)):
        u = d.args[0]
        if not u.has(v):
            continue
        c = u.coeff(v)
        if c is None or not c.is_Number or c == 0:
            continue
        r = u - c * v
        if r.has(v):
            continue
        out = out.subs(d, sympy.DiracDelta(v + r / c) / abs(c))
    return out


# ---------------------------------------------------------------------------
# Cosine / sine transforms (Wolfram {0,1} convention == SymPy convention),
# with table entries for the distribution cases SymPy cannot do.
# ---------------------------------------------------------------------------

def _match_scaled_trig(f, x, fn):
    """f = c*fn(b*x) with c, b free of x -> (c, b) or None."""
    wc = sympy.Wild("wc", exclude=[x])
    wb = sympy.Wild("wb", exclude=[x])
    m = f.match(wc * fn(wb * x))
    if m is None:
        return None
    c, b = m[wc], m[wb]
    if c.has(x) or b.has(x):
        return None
    return c, b


def _cosine_transform(f, x, k, complete=False):
    """Wolfram {0,1} cosine transform of f.

    sympy's transform silently picks a one-sided branch (k>0 or k<0), so the
    sympy call uses a positive dummy: with complete=False the result is the
    bare k>0 branch (Wolfram's own FourierCosTransform behaviour); with
    complete=True it is extended as an even function via k -> Abs[k].
    """
    if not f.has(x):
        return f * sympy.sqrt(2 * sympy.pi) * sympy.DiracDelta(k)
    m = _match_scaled_trig(f, x, sympy.cos)
    if m is not None:
        c, b = m
        return c * sympy.sqrt(sympy.pi / 2) * (sympy.DiracDelta(k - b) + sympy.DiracDelta(k + b))
    kp = sympy.Dummy("kp", positive=True)
    res = _call_transform(sympy.cosine_transform, f, x, kp)
    if not _usable(res, x):
        return None
    return res.subs(kp, sympy.Abs(k) if complete else k)


def _sine_transform(f, x, k, complete=False):
    """Wolfram {0,1} sine transform; complete=True extends oddly in k."""
    if not f.has(x):
        return f * sympy.sqrt(2 / sympy.pi) / k
    m = _match_scaled_trig(f, x, sympy.sin)
    if m is not None:
        c, b = m
        return c * sympy.sqrt(sympy.pi / 2) * (sympy.DiracDelta(k - b) - sympy.DiracDelta(k + b))
    m = _match_scaled_trig(f, x, sympy.sign)
    if m is not None:
        return m[0] * sympy.sqrt(2 / sympy.pi) / k
    if f.is_Mul or f.is_Pow:
        c, dep = f.as_independent(x, as_Add=False)
        if dep == 1 / x:
            return c * sympy.sqrt(sympy.pi / 2) * sympy.sign(k)
    kp = sympy.Dummy("kp", positive=True)
    res = _call_transform(sympy.sine_transform, f, x, kp)
    if not _usable(res, x):
        return None
    if complete:
        try:
            return sympy.simplify(sympy.sign(k) * res.subs(kp, sympy.Abs(k)))
        except Exception:
            return sympy.sign(k) * res.subs(kp, sympy.Abs(k))
    return res.subs(kp, k)


# ---------------------------------------------------------------------------
# Fourier family
# ---------------------------------------------------------------------------

def _fourier(f, x, v, a, b, inverse):
    """Wolfram FourierParameters {a, b} convention via even/odd decomposition."""
    if b == 0:
        return None
    bb = -b if inverse else b
    power = (1 + a) if inverse else (1 - a)
    scale = sympy.sqrt(abs(bb) / (2 * sympy.pi) ** power)
    if not f.has(x):
        # integral of c*e^(i b v x) dx = 2*pi*c*DiracDelta(v)/|b|
        return scale * 2 * sympy.pi * f / abs(bb) * sympy.DiracDelta(v)
    kp = sympy.Dummy("kp", positive=True)
    if f.has(sympy.DiracDelta):
        # delta inputs: even/odd decomposition produces Heaviside noise;
        # the direct transform handles them cleanly.
        g = _call_transform(sympy.fourier_transform, f, x, kp)
        if not _usable(g, x):
            return None
        res = scale * g.subs(kp, -bb * v / (2 * sympy.pi))
        res = _fix_deltas(res, v)
        return res if _usable(res, x) else None
    f_neg = f.subs(x, -x)
    fe = sympy.simplify((f + f_neg) / 2)
    fo = sympy.simplify(f - fe)
    k = sympy.Dummy("k", real=True)
    ce = se = None
    if fe != 0:
        ce = _cosine_transform(fe, x, k, complete=True)
    if fo != 0:
        se = _sine_transform(fo, x, k, complete=True)
    if (fe == 0 or ce is not None) and (fo == 0 or se is not None):
        res = scale * sympy.sqrt(2 * sympy.pi) * ((ce or 0) + sympy.I * (se or 0))
        res = res.subs(k, bb * v)
        res = _fix_deltas(res, v)
        return res if _usable(res, x) else None
    # Fallback: direct SymPy Fourier transform with frequency rescaling.
    # Only trust it for definite-parity inputs; sympy picks an arbitrary
    # one-sided branch otherwise.
    try:
        is_even = sympy.simplify(f_neg - f) == 0
        is_odd = not is_even and sympy.simplify(f_neg + f) == 0
    except Exception:
        return None
    if not (is_even or is_odd):
        return None
    g = _call_transform(sympy.fourier_transform, f, x, kp)
    if not _usable(g, x):
        return None
    gk = sympy.Dummy("gk", real=True)
    g = g.subs(kp, sympy.Abs(gk))
    if is_odd:
        g = sympy.sign(gk) * g
    res = scale * g.subs(gk, -bb * v / (2 * sympy.pi))
    res = _fix_deltas(res, v)
    return res if _usable(res, x) else None


def _fourier_params(params_expr):
    """Mathics option value {a, b} -> (a, b) as SymPy numbers, or None."""
    if not isinstance(params_expr, Expression) or not params_expr.has_form("List", 2):
        return None
    try:
        a = params_expr.elements[0].to_sympy()
        b = params_expr.elements[1].to_sympy()
    except Exception:
        return None
    if a is None or b is None or not a.is_Number or not b.is_Number:
        return None
    return a, b


def _fourier_eval(self, f, x, v, evaluation, options, inverse):
    if not isinstance(x, Symbol) or not isinstance(v, Symbol):
        return None
    x_s = x.to_sympy()
    v_s = v.to_sympy()
    if x_s is None or v_s is None:
        return None
    params = self.get_option(options, "FourierParameters", evaluation)
    ab = _fourier_params(params)
    if ab is None:
        return None
    f_s = _conv(f)
    if f_s is None:
        return None
    res = _fourier(f_s, x_s, v_s, ab[0], ab[1], inverse)
    if not _usable(res, x_s):
        return None
    return from_sympy(res)


# ---------------------------------------------------------------------------
# Convolve:  int f(tau) g(y - tau) d tau  over the real line
# ---------------------------------------------------------------------------

def _convolve_term(term, tau, y_s):
    """Integrate one product term, folding Heaviside factors into the bounds."""
    lows, highs, rest = [], [], sympy.S.One
    for fac in sympy.Mul.make_args(term):
        if isinstance(fac, sympy.Heaviside):
            u = fac.args[0]
            c = u.coeff(tau)
            if c is None or (u - c * tau).has(tau) or not (c.is_real and c.is_number) or c == 0:
                return None
            bound = -(u - c * tau) / c
            (lows if c > 0 else highs).append(bound)
        else:
            rest *= fac

    def unique(bounds):
        out = []
        for b in bounds:
            if any(sympy.simplify(b - o) == 0 for o in out):
                continue
            out.append(b)
        return out

    lows, highs = unique(lows), unique(highs)
    if len(lows) > 1 or len(highs) > 1:
        return None
    lo = lows[0] if lows else -sympy.oo
    hi = highs[0] if highs else sympy.oo
    try:
        res = sympy.integrate(rest, (tau, lo, hi))
    except Exception:
        return None
    if not _usable(res, tau):
        return None
    if lows and highs:
        res = res * sympy.Heaviside(hi - lo, 1)
    return res


def _convolve_fourier(f_s, g_s, x_s, y_s):
    """Fallback via the convolution theorem: conv = sqrt(2 pi) IFT(F f * F g)."""
    if f_s.has(sympy.DiracDelta) or g_s.has(sympy.DiracDelta):
        return None
    w = sympy.Dummy("w")
    F = _fourier(f_s, x_s, w, sympy.S.Zero, sympy.S.One, inverse=False)
    G = _fourier(g_s, x_s, w, sympy.S.Zero, sympy.S.One, inverse=False)
    if F is None or G is None or F.has(sympy.DiracDelta) or G.has(sympy.DiracDelta):
        return None
    try:
        prod = sympy.simplify(F * G)
    except Exception:
        return None
    res = _fourier(prod, w, y_s, sympy.S.Zero, sympy.S.One, inverse=True)
    if res is None:
        return None
    res = sympy.sqrt(2 * sympy.pi) * res
    try:
        res = sympy.simplify(res.rewrite(sympy.exp))
    except Exception:
        pass
    # NOTE: results containing Abs (e.g. Convolve[Exp[-Abs[x]], ...]) are left
    # in Abs form.  Wolfram prints an equivalent Piecewise, but Mathics'
    # Piecewise evaluator drops undecidable branches, so emitting Piecewise
    # here would silently lose a branch.
    return res if _usable(res) else None


def _convolve(f_s, g_s, x_s, y_s):
    tau = sympy.Dummy("tau")
    integrand = f_s.subs(x_s, tau) * g_s.subs(x_s, y_s - tau)
    terms = sympy.Add.make_args(sympy.expand(integrand))
    total = sympy.S.Zero
    for term in terms:
        res = _convolve_term(term, tau, y_s)
        if res is None:
            total = None
            break
        total += res
    if total is not None:
        try:
            total = sympy.simplify(total)
        except Exception:
            pass
        if _usable(total, tau):
            return total
    return _convolve_fourier(f_s, g_s, x_s, y_s)


# ---------------------------------------------------------------------------
# ZTransform: decompose f[n] into c * n^m * r^n * {1, cos(w n), sin(w n)}
# ---------------------------------------------------------------------------

def _z_geometric(r, m, z):
    """Sum_{n>=0} n^m r^n z^-n  ==  (-z d/dz)^m [z/(z - r)]."""
    g = z / (z - r)
    for _ in range(m):
        g = sympy.cancel(-z * sympy.diff(g, z))
    return g


def _z_trig_base(r, w, z, is_cos):
    """Sum_{n>=0} r^n cos(w n) z^-n  (or sin), closed form."""
    c, s = sympy.cos(w), sympy.sin(w)
    den = z ** 2 - 2 * r * c * z + r ** 2
    return z * (z - r * c) / den if is_cos else r * s * z / den


def _z_term(term, n, z):
    """One summand -> (closed form) or None."""
    # Discrete deltas: KroneckerDelta(n - k) -> z^-k
    if term.has(sympy.KroneckerDelta):
        coeff, dep = term.as_independent(n, as_Add=False)
        if isinstance(dep, sympy.KroneckerDelta):
            a, b = dep.args
            shift = a if not a.has(n) else b
            other = b if not a.has(n) else a
            if other == n and shift.is_integer and shift >= 0:
                return coeff * z ** (-int(shift))
        return None
    # A single trig factor of affine argument times n^m r^n.
    trig = None
    rest = term
    for fac in sympy.Mul.make_args(term):
        if isinstance(fac, (sympy.cos, sympy.sin)) and fac.args[0].has(n):
            alpha = fac.args[0].coeff(n)
            if alpha is None or (fac.args[0] - alpha * n).has(n) or (fac.args[0] - alpha * n) != 0:
                return None
            trig = (isinstance(fac, sympy.cos), alpha)
            rest = term / fac
            break
    coeff, dep = rest.as_independent(n, as_Add=False)
    m = 0
    r = sympy.S.One
    for fac in sympy.Mul.make_args(dep):
        if fac == n:
            m += 1
        elif fac.is_Pow and fac.base == n and fac.exp.is_integer and fac.exp >= 0:
            m += int(fac.exp)
        elif fac.is_Pow and not fac.base.has(n):
            ex = fac.exp
            alpha = ex.coeff(n)
            remainder = ex - alpha * n if alpha is not None else ex
            if alpha is None or remainder.has(n):
                return None
            r *= fac.base ** alpha
            if remainder:
                coeff *= fac.base ** remainder
        elif isinstance(fac, sympy.exp):
            ex = fac.args[0]
            alpha = ex.coeff(n)
            remainder = ex - alpha * n if alpha is not None else ex
            if alpha is None or remainder.has(n):
                return None
            r *= sympy.E ** alpha
            if remainder:
                coeff *= sympy.E ** remainder
        elif fac.has(n):
            return None
        else:
            coeff *= fac
    if trig is not None:
        is_cos, w = trig
        g = _z_trig_base(r, w, z, is_cos)
        for _ in range(m):
            g = sympy.cancel(-z * sympy.diff(g, z))
        return coeff * g
    return coeff * _z_geometric(r, m, z)


def _z_transform(f_s, n_s, z_s):
    total = sympy.S.Zero
    for term in sympy.Add.make_args(sympy.expand(f_s)):
        part = _z_term(term, n_s, z_s)
        if part is None:
            return None
        total += part
    try:
        total = sympy.cancel(total)
        num, den = sympy.fraction(total)
        total = sympy.factor(num) / sympy.factor(den)
    except Exception:
        pass
    return total if _usable(total, n_s) else None


# ---------------------------------------------------------------------------
# InverseZTransform: residues of F(z) z^(n-1)
# ---------------------------------------------------------------------------

def _trigify(e, n):
    """Rewrite concrete complex exponentials of n as cos/sin pairs.

    Handles both p**(a n + b) with p a concrete complex number and
    exp(I*(a n + b)) with real a, b.  Returns (result, changed).
    """
    repl = {}
    for p in e.atoms(sympy.Pow):
        base, ex = p.as_base_exp()
        if base is sympy.E:
            continue
        if ex.has(n) and base.is_number and base.has(sympy.I):
            r = sympy.Abs(base)
            th = sympy.arg(base)
            repl[p] = r ** ex * (sympy.cos(th * ex) + sympy.I * sympy.sin(th * ex))
    for a in e.atoms(sympy.exp):
        ex = a.args[0]
        if not ex.has(n):
            continue
        alpha = ex.coeff(n)
        if alpha is None:
            continue
        beta = ex - alpha * n
        if beta.has(n):
            continue
        ai, bi = sympy.im(alpha), sympy.im(beta)
        if sympy.re(alpha) == 0 and sympy.re(beta) == 0 and (ai != 0 or bi != 0):
            repl[a] = (sympy.cos(ai * n) + sympy.I * sympy.sin(ai * n)) * \
                      (sympy.cos(bi) + sympy.I * sympy.sin(bi))
    if not repl:
        return e, False
    # xreplace: exact structural replacement; subs does clever Pow matching
    # that mangles reciprocal/negated exponents here.
    try:
        return sympy.expand(e.xreplace(repl)), True
    except Exception:
        return e.xreplace(repl), True


def _inverse_z(F, z, n):
    try:
        F = sympy.cancel(F)
        num, den = sympy.fraction(F)
        pnum = sympy.Poly(num, z)
        pden = sympy.Poly(den, z)
    except Exception:
        return None
    if pnum.degree() > pden.degree():
        return None
    roots = sympy.roots(den, z)
    if sum(roots.values()) < pden.degree():
        return None
    poles, zero_mult = {}, 0
    for rt, mult in roots.items():
        if rt == 0:
            zero_mult = mult
        elif rt.has(z) or rt.has(n):
            return None
        else:
            poles[rt] = mult

    # Laurent coefficients at z == 0: F = sum_k c_k z^-k + G (G regular at 0).
    cks = {}
    G = F
    if zero_mult:
        H = sympy.cancel(z ** zero_mult * F)
        try:
            series = sympy.series(H, z, 0, zero_mult).removeO().expand()
            hp = sympy.Poly(series, z)
            for k in range(1, zero_mult + 1):
                cks[k] = hp.nth(zero_mult - k)
            G = sympy.cancel(F - sum(c * z ** (-k) for k, c in cks.items()))
        except Exception:
            return None

    # A(n) = sum of residues of F z^(n-1) at nonzero poles (valid for n >= 1).
    A = sympy.S.Zero
    for p, mult in poles.items():
        try:
            g = sympy.cancel((z - p) ** mult * F) * z ** (n - 1)
            term = sympy.diff(g, z, mult - 1) / sympy.factorial(mult - 1)
            A += term.subs(z, p)
        except Exception:
            return None
    try:
        A = sympy.simplify(A)
    except Exception:
        pass
    A, changed = _trigify(A, n)
    if changed:
        try:
            A = sympy.cancel(sympy.trigsimp(A))
        except Exception:
            pass

    # f[0]: residues of G/z at nonzero poles (mind the multiplicities) plus G(0).
    try:
        f0 = G.subs(z, 0)
        for p, mult in poles.items():
            g = sympy.cancel((z - p) ** mult * G / z)
            f0 += sympy.diff(g, z, mult - 1).subs(z, p) / sympy.factorial(mult - 1)
        f0 = sympy.simplify(f0)
    except Exception:
        return None

    deltas = sum((c * sympy.KroneckerDelta(k - n, 0) for k, c in cks.items() if c != 0),
                 sympy.S.Zero)
    try:
        plain = sympy.simplify(A.subs(n, 0) - f0) == 0
    except Exception:
        plain = False
    if plain or (A == 0 and f0 == 0):
        res = A + deltas
    else:
        res = A * sympy.Heaviside(n - 1, 1) + f0 * sympy.KroneckerDelta(n, 0) + deltas
    return res if _usable(res, z) else None


# ---------------------------------------------------------------------------
# Builtins
# ---------------------------------------------------------------------------

class LaplaceTransform(Builtin):
    """
    <dl><dt>'LaplaceTransform[$f$, $t$, $s$]'<dd>Laplace transform of $f$.</dl>
    >> LaplaceTransform[Sin[t], t, s]
     = 1 / (1 + s ^ 2)
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Laplace transform"

    def eval(self, f, t, s, evaluation):
        "LaplaceTransform[f_, t_Symbol, s_Symbol]"
        t_s, s_s = t.to_sympy(), s.to_sympy()
        f_s = _conv(f)
        if t_s is None or s_s is None or f_s is None:
            return None
        res = _call_transform(sympy.laplace_transform, f_s, t_s, s_s)
        if not _usable(res, t_s):
            return None
        return from_sympy(res)


class InverseLaplaceTransform(Builtin):
    """
    <dl><dt>'InverseLaplaceTransform[$F$, $s$, $t$]'<dd>inverse Laplace transform.</dl>
    >> InverseLaplaceTransform[1/(s^2 + 1), s, t]
     = Sin[t]
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "inverse Laplace transform"

    def eval(self, f, s, t, evaluation):
        "InverseLaplaceTransform[f_, s_Symbol, t_Symbol]"
        s_s, t_s = s.to_sympy(), t.to_sympy()
        f_s = _conv(f)
        if s_s is None or t_s is None or f_s is None:
            return None
        res = _call_transform(sympy.inverse_laplace_transform, f_s, s_s, t_s)
        if not _usable(res, s_s):
            return None
        res = _drop_heaviside_factor(res, t_s)
        try:
            res = sympy.expand(sympy.cancel(res))
        except Exception:
            pass
        return _map_heaviside(from_sympy(res), "HeavisideTheta")


class FourierTransform(Builtin):
    """
    <dl><dt>'FourierTransform[$f$, $t$, $w$]'<dd>Fourier transform, default
    FourierParameters {0, 1}.</dl>
    >> FourierTransform[Exp[-t^2], t, w]
     = Sqrt[2] E ^ (-w ^ 2 / 4) / 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"FourierParameters": "{0, 1}"}
    summary_text = "Fourier transform"

    def eval(self, f, t, w, evaluation, options):
        "FourierTransform[f_, t_Symbol, w_Symbol, OptionsPattern[FourierTransform]]"
        return _fourier_eval(self, f, t, w, evaluation, options, inverse=False)


class InverseFourierTransform(Builtin):
    """
    <dl><dt>'InverseFourierTransform[$F$, $w$, $t$]'<dd>inverse Fourier transform.</dl>
    >> InverseFourierTransform[Exp[-w^2], w, t]
     = Sqrt[2] E ^ (-t ^ 2 / 4) / 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"FourierParameters": "{0, 1}"}
    summary_text = "inverse Fourier transform"

    def eval(self, f, w, t, evaluation, options):
        "InverseFourierTransform[f_, w_Symbol, t_Symbol, OptionsPattern[InverseFourierTransform]]"
        return _fourier_eval(self, f, w, t, evaluation, options, inverse=True)


class FourierCosTransform(Builtin):
    """
    <dl><dt>'FourierCosTransform[$f$, $t$, $w$]'<dd>Fourier cosine transform.</dl>
    >> FourierCosTransform[Exp[-t], t, w]
     = Sqrt[2] / (Sqrt[Pi] (1 + w ^ 2))
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"FourierParameters": "{0, 1}"}
    summary_text = "Fourier cosine transform"

    def eval(self, f, t, w, evaluation, options):
        "FourierCosTransform[f_, t_Symbol, w_Symbol, OptionsPattern[FourierCosTransform]]"
        return _sin_cos_eval(self, f, t, w, evaluation, options, is_cos=True)


class FourierSinTransform(Builtin):
    """
    <dl><dt>'FourierSinTransform[$f$, $t$, $w$]'<dd>Fourier sine transform.</dl>
    >> FourierSinTransform[Exp[-t], t, w]
     = Sqrt[2] w / (Sqrt[Pi] (1 + w ^ 2))
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    options = {"FourierParameters": "{0, 1}"}
    summary_text = "Fourier sine transform"

    def eval(self, f, t, w, evaluation, options):
        "FourierSinTransform[f_, t_Symbol, w_Symbol, OptionsPattern[FourierSinTransform]]"
        return _sin_cos_eval(self, f, t, w, evaluation, options, is_cos=False)


def _sin_cos_eval(self, f, t, w, evaluation, options, is_cos):
    if not isinstance(t, Symbol) or not isinstance(w, Symbol):
        return None
    t_s, w_s = t.to_sympy(), w.to_sympy()
    if t_s is None or w_s is None:
        return None
    params = self.get_option(options, "FourierParameters", evaluation)
    ab = _fourier_params(params)
    if ab is None:
        return None
    a, b = ab
    if b == 0:
        return None
    f_s = _conv(f)
    if f_s is None:
        return None
    k = sympy.Dummy("k")
    res = _cosine_transform(f_s, t_s, k) if is_cos else _sine_transform(f_s, t_s, k)
    if not _usable(res, t_s):
        return None
    # Wolfram {a,b}: 2 sqrt(|b|) (2 pi)^((a-1)/2) int f cos/sin(b w t) dt
    ratio = sympy.sqrt(abs(b)) * (2 * sympy.pi) ** (a / 2)
    res = ratio * res.subs(k, b * w_s)
    res = _fix_deltas(res, w_s)
    if not _usable(res, t_s):
        return None
    return from_sympy(res)


class MellinTransform(Builtin):
    """
    <dl><dt>'MellinTransform[$f$, $t$, $s$]'<dd>Mellin transform.</dl>
    >> MellinTransform[Exp[-t], t, s]
     = Gamma[s]
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Mellin transform"

    def eval(self, f, t, s, evaluation):
        "MellinTransform[f_, t_Symbol, s_Symbol]"
        t_s, s_s = t.to_sympy(), s.to_sympy()
        f_s = _conv(f)
        if t_s is None or s_s is None or f_s is None:
            return None
        res = _call_transform(sympy.mellin_transform, f_s, t_s, s_s)
        if not _usable(res, t_s):
            return None
        return from_sympy(_gamma_normalize(res, s_s))


def _gamma_normalize(res, s):
    """Fold gamma(1 - w) via reflection, then gammasimp (Legendre duplication).

    Turns sympy's 2^s sqrt(pi) gamma(1/2+s/2)/(2 gamma(1-s/2)) style answers
    into Wolfram's gamma(s) sin(pi s/2) style.
    """
    if not res.has(sympy.gamma):
        return res
    out = res
    for g in sorted(out.atoms(sympy.gamma), key=str):
        w = 1 - g.args[0]
        try:
            positive = sympy.expand(w).coeff(s) > 0
        except Exception:
            positive = False
        if w.has(s) and positive:
            out = out.subs(g, sympy.pi / (sympy.gamma(w) * sympy.sin(sympy.pi * w)))
    if out is res:
        return res
    try:
        return sympy.gammasimp(out)
    except Exception:
        return out


class InverseMellinTransform(Builtin):
    """
    <dl><dt>'InverseMellinTransform[$F$, $s$, $t$]'<dd>inverse Mellin transform.</dl>
    >> InverseMellinTransform[Gamma[s], s, t]
     = E ^ (-t)
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "inverse Mellin transform"

    _STRIPS = ((0, sympy.oo), (0, 1), (-1, 0), (1, 2), (-1, 1), (0, 2))

    def eval(self, f, s, t, evaluation):
        "InverseMellinTransform[f_, s_Symbol, t_Symbol]"
        s_s, t_s = s.to_sympy(), t.to_sympy()
        f_s = _conv(f)
        if s_s is None or t_s is None or f_s is None:
            return None
        res = None
        for strip in self._STRIPS:
            try:
                cand = sympy.inverse_mellin_transform(f_s, s_s, t_s, strip)
            except Exception:
                continue
            if _usable(cand, s_s):
                res = cand
                break
        if res is None:
            return None
        return _map_heaviside(from_sympy(res), "HeavisideTheta")


class Convolve(Builtin):
    """
    <dl><dt>'Convolve[$f$, $g$, $x$, $y$]'<dd>convolution integral of $f$ and $g$.</dl>
    >> Convolve[UnitStep[x] Exp[-x], UnitStep[x] Exp[-x], x, y]
     = E ^ (-y) y UnitStep[y]
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "convolution of two functions"

    def eval(self, f, g, x, y, evaluation):
        "Convolve[f_, g_, x_Symbol, y_Symbol]"
        if not isinstance(x, Symbol) or not isinstance(y, Symbol):
            return None
        x_s, y_s = x.to_sympy(), y.to_sympy()
        f_s, g_s = _conv(f), _conv(g)
        if x_s is None or y_s is None or f_s is None or g_s is None:
            return None
        res = _convolve(f_s, g_s, x_s, y_s)
        if res is None:
            return None
        return _map_heaviside(from_sympy(res), "UnitStep")


class ZTransform(Builtin):
    """
    <dl><dt>'ZTransform[$f$, $n$, $z$]'<dd>Z transform (sum over n >= 0 of f[n] z^-n).</dl>
    >> ZTransform[a^n, n, z]
     = -z / (a - z)
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Z transform"

    def eval(self, f, n, z, evaluation):
        "ZTransform[f_, n_Symbol, z_Symbol]"
        n_s, z_s = n.to_sympy(), z.to_sympy()
        f_s = _conv(f)
        if n_s is None or z_s is None or f_s is None:
            return None
        res = _z_transform(f_s, n_s, z_s)
        if res is None:
            return None
        return from_sympy(res)


class InverseZTransform(Builtin):
    """
    <dl><dt>'InverseZTransform[$F$, $z$, $n$]'<dd>inverse Z transform.</dl>
    >> InverseZTransform[z/(z - a), z, n]
     = a ^ n
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "inverse Z transform"

    def eval(self, f, z, n, evaluation):
        "InverseZTransform[f_, z_Symbol, n_Symbol]"
        z_s, n_s = z.to_sympy(), n.to_sympy()
        f_s = _conv(f)
        if z_s is None or n_s is None or f_s is None:
            return None
        res = _inverse_z(f_s, z_s, n_s)
        if res is None:
            return None
        out = from_sympy(res)
        out = _map_heaviside(out, "UnitStep")
        return _kd_single_arg(out)


def register_transforms(session):
    for cls in (LaplaceTransform, InverseLaplaceTransform,
                FourierTransform, InverseFourierTransform,
                FourierCosTransform, FourierSinTransform,
                MellinTransform, InverseMellinTransform,
                Convolve, ZTransform, InverseZTransform):
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
