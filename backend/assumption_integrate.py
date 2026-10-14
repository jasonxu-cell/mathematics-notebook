"""Integrate with working Assumptions and closed-form fallbacks.

Gaps in the pinned Mathics3 10.0.1 engine that this override fills, in the
order they are tried after the native builtin returns unevaluated:

1. ``Assumptions -> cond`` crashes upstream (``get_ownvalues`` list handed to
   ``set_ownvalue``).  Fixed here, and the facts ``x > 0``, ``x >= 0``,
   ``x < 0``, ``-1 < a < 1``, ``Element[x, Reals]`` are turned into SymPy symbol
   assumptions so they actually reach the integrator.
2. Even-part decomposition over (-inf, inf):  ∫f = ∫₀^∞ (f(x)+f(-x)).
3. Bose/Fermi-type Mellin integrals  ∫₀^∞ x^s/(e^{c x} ∓ 1) dx
   = Γ(s+1) ζ(s+1)/c^{s+1}  (resp. with η for the + sign).
4. Log-power integrals on (0,1):  ∫₀¹ x^{p} ln^a x · ln^b(1-x)/(1-x)^q ...
   handled by expanding ln(1-x) / 1/(1-x) into power series and summing
   term-wise (every term is a Beta/zeta-type sum SymPy knows).
5. Polylog cleanup: results containing polylog(k, ±I) are converted to
   Dirichlet-beta closed forms (π³/8 etc.) when numerically exact.
6. Multi-dimensional integrals: iterate one variable at a time, re-applying
   the assumptions at each step and resolving Piecewise branches whose
   conditions are decided by those assumptions.

Every result is an exact SymPy closed form converted through ``from_sympy``;
numbers are only used to *check* polylog identities, never to produce output.
"""

from __future__ import annotations

import sympy

from mathics.builtin.numbers.calculus import Integrate
from mathics.core.convert.sympy import from_sympy
from mathics.core.symbols import Symbol
from mathics.core.systemsymbols import SymbolSimplify
from mathics.core.expression import Expression


# ---------------------------------------------------------------------------
# Assumptions -> SymPy facts
# ---------------------------------------------------------------------------

def _is_zero(e) -> bool:
    return e.get_int_value() == 0 or (e.is_numeric() and e.to_sympy() == 0)


def _facts_from_assumptions(assum) -> dict[str, dict]:
    """Map Mathics symbol name -> SymPy assumption kwargs / interval bounds."""
    facts: dict[str, dict] = {}

    def add(sym, **kw):
        if isinstance(sym, Symbol):
            facts.setdefault(sym.get_name(), {}).update(kw)

    def relation(head, a, b):
        # a <head> b, head in Less/LessEqual/Greater/GreaterEqual
        if _is_zero(b):
            add(a, **{"System`Greater": dict(positive=True), "System`GreaterEqual": dict(nonnegative=True),
                      "System`Less": dict(negative=True), "System`LessEqual": dict(nonpositive=True)}[head])
        elif _is_zero(a):
            add(b, **{"System`Greater": dict(negative=True), "System`GreaterEqual": dict(nonpositive=True),
                      "System`Less": dict(positive=True), "System`LessEqual": dict(nonnegative=True)}[head])
        else:
            # numeric bound on one side: record an interval (used to decide Piecewise)
            if isinstance(a, Symbol) and b.is_numeric():
                add(a, real=True)
                facts[a.get_name()].setdefault("_bounds", []).append((head, b.to_sympy(), "rhs"))
            elif isinstance(b, Symbol) and a.is_numeric():
                add(b, real=True)
                facts[b.get_name()].setdefault("_bounds", []).append((head, a.to_sympy(), "lhs"))
            else:
                add(a, real=True)
                add(b, real=True)

    def walk(e):
        if not isinstance(e, Expression):
            return
        head = e.get_head_name()
        el = e.elements
        if head == "System`And":
            for x in el:
                walk(x)
        elif head in ("System`Greater", "System`GreaterEqual", "System`Less", "System`LessEqual"):
            # chained a < b < c arrives as Less[a, b, c]
            for i in range(len(el) - 1):
                relation(head, el[i], el[i + 1])
        elif head == "System`Element" and len(el) == 2:
            dom = el[1].get_name()
            targets = el[0].elements if el[0].has_form("Alternatives", None) else (el[0],)
            kw = {"System`Reals": dict(real=True), "System`Integers": dict(integer=True),
                  "System`Rationals": dict(rational=True), "System`Complexes": dict(complex=True)}.get(dom)
            if kw:
                for t in targets:
                    add(t, **kw)

    walk(assum)
    return facts


def _retype(expr, facts):
    """Replace plain symbols by assumption-typed ones. Returns (expr, subs, bounds)."""
    subs, bounds = {}, {}
    for s in expr.free_symbols:
        name = getattr(s, "name", "")
        for k, kw in facts.items():
            if name == k or name.endswith(k.replace("`", "_")):
                clean = {a: b for a, b in kw.items() if not a.startswith("_")}
                new = sympy.Symbol(s.name, **clean) if clean else s
                subs[s] = new
                if "_bounds" in kw:
                    bounds[new] = kw["_bounds"]
                break
    return (expr.subs(subs) if subs else expr), subs, bounds


def _decide(cond, bounds) -> bool | None:
    """Try to decide a Piecewise condition from recorded numeric bounds."""
    if cond is sympy.true:
        return True
    if cond is sympy.false:
        return False
    try:
        for sym, bl in bounds.items():
            lo, hi = -sympy.oo, sympy.oo
            for head, val, side in bl:
                # normalise to lo < sym < hi
                if (head in ("System`Less", "System`LessEqual")) == (side == "rhs"):
                    hi = min(hi, val)
                else:
                    lo = max(lo, val)
            if lo == -sympy.oo and hi == sympy.oo:
                continue
            # test condition at a few interior points; if constant, accept
            pts = []
            if lo != -sympy.oo and hi != sympy.oo:
                pts = [lo + (hi - lo) * sympy.Rational(i, 4) for i in (1, 2, 3)]
            elif lo != -sympy.oo:
                pts = [lo + 1, lo + 10]
            else:
                pts = [hi - 1, hi - 10]
            vals = {bool(cond.subs(sym, p)) for p in pts}
            if len(vals) == 1:
                return vals.pop()
    except Exception:
        return None
    return None


def _sign_from_bounds(expr, bounds):
    """Decide the sign of `expr` on the box given by bounds, by sampling interior points."""
    if not bounds or not expr.free_symbols <= set(bounds):
        return None
    grids = []
    for sym in expr.free_symbols:
        lo, hi = -sympy.oo, sympy.oo
        for head, val, side in bounds[sym]:
            if (head in ("System`Less", "System`LessEqual")) == (side == "rhs"):
                hi = min(hi, val)
            else:
                lo = max(lo, val)
        if lo == -sympy.oo or hi == sympy.oo:
            return None
        grids.append((sym, [lo + (hi - lo) * sympy.Rational(i, 8) for i in range(1, 8)]))
    import itertools
    signs = set()
    for combo in itertools.product(*[g[1] for g in grids]):
        v = expr.subs(dict(zip([g[0] for g in grids], combo)))
        if not v.is_number:
            return None
        signs.add(1 if v > 0 else (-1 if v < 0 else 0))
    return signs.pop() if len(signs) == 1 else None


def _gaussian_retype(expr, v, bounds):
    """exp(c * v**2) with c decidably negative on the assumption box -> exp(-k v**2), k>0.

    Returns (new_expr, {k: -c}) or (expr, {}).
    """
    repl = {}
    def visit(e):
        if isinstance(e, sympy.exp):
            c, rest = e.args[0].as_independent(v, as_Add=False)
            if rest == v**2 and not c.has(v) and c.free_symbols:
                if _sign_from_bounds(c, bounds) == -1:
                    k = sympy.Dummy("k", positive=True)
                    repl[k] = -c
                    return sympy.exp(-k * v**2)
        return e
    new = expr.replace(lambda e: isinstance(e, sympy.exp), visit)
    return new, repl


def _even_parameter_retry(expr, v, lo, hi, piecewise):
    """SymPy proves convergence only for positive parameters (condition Abs(arg(b)) == 0).

    When the integrand is an even function of a *real* parameter b, the value for
    b < 0 equals the value for -b > 0, so integrate with b replaced by a positive
    symbol and substitute back. If the result is itself even in b, the plain
    symbol is returned; otherwise Abs(b) is used.
    """
    for sym in sorted(expr.free_symbols - {v}, key=lambda s: s.name):
        if sym.is_positive or sym.is_negative or not sym.is_real:
            continue
        if sympy.simplify(expr.subs(sym, -sym) - expr) != 0:
            continue
        pos = sympy.Dummy(sym.name, positive=True)
        try:
            r = sympy.integrate(expr.subs(sym, pos), (v, lo, hi))
        except (ValueError, NotImplementedError, TypeError, sympy.PolynomialError, RecursionError):
            continue
        if r is None or r.has(sympy.Integral, sympy.Piecewise, sympy.nan):
            continue
        back = r.subs(pos, sym)
        if sympy.simplify(back.subs(sym, -sym) - back) == 0:
            return back
        return r.subs(pos, sympy.Abs(sym))
    return piecewise


def _resolve_piecewise(expr, bounds):
    if not expr.has(sympy.Piecewise):
        return expr

    def fix(pw):
        for val, cond in pw.args:
            d = _decide(cond, bounds)
            if d is True:
                return val
            if d is None:
                return pw
        return pw

    return expr.replace(lambda e: isinstance(e, sympy.Piecewise), fix)


# ---------------------------------------------------------------------------
# Closed-form rules
# ---------------------------------------------------------------------------

def _rule_bose_fermi(f, x, a, b):
    """∫₀^∞ x^s / (e^{c x} - 1) = Γ(s+1) ζ(s+1) / c^{s+1};  (e^{c x}+1): η instead of ζ."""
    if not (a == 0 and b == sympy.oo):
        return None
    num, den = sympy.fraction(sympy.together(f))
    # numerator: coeff * x^s
    coeff, rest = num.as_independent(x, as_Add=False)
    if rest == 1:
        s = sympy.Integer(0)
    else:
        base, s = rest.as_base_exp()
        if base != x or s.has(x):
            return None
    # denominator: k*(exp(c x) ∓ 1)
    dcoeff, drest = den.as_independent(x, as_Add=False)
    drest = sympy.expand(drest)
    if not isinstance(drest, sympy.Add) or len(drest.args) != 2:
        return None
    sign = None
    c = None
    for term in drest.args:
        if term.is_number:
            sign = -1 if term == -1 else (1 if term == 1 else None)
        elif isinstance(term, sympy.exp):
            cc, cx = term.args[0].as_independent(x, as_Add=False)
            if cx != x or cc.has(x):
                return None
            c = cc
    if sign is None or c is None:
        return None
    if not ((s.is_positive and sign == -1) or (s.is_nonnegative and sign == 1)):
        if s.is_number and not ((s > 0 and sign == -1) or (s >= 0 and sign == 1)):
            return None
    if sign == -1:
        val = sympy.gamma(s + 1) * sympy.zeta(s + 1) / c ** (s + 1)
    else:
        val = sympy.gamma(s + 1) * sympy.dirichlet_eta(s + 1) / c ** (s + 1)
    return coeff / dcoeff * val


def _rule_log_series(f, x, a, b):
    """∫₀¹ c · x^p · ln^k(x) · ln^m(1-x) / (1-x)^q  via series in (1-x) powers.

    Expands ln(1-x) = -Σ x^n/n and (1-x)^{-q} = Σ C(n+q-1,n) x^n (small m,q)
    then sums Σ_n coeff · ∫₀¹ x^{p+n} ln^k x = Σ_n coeff · (-1)^k k! /(p+n+1)^{k+1}.
    """
    if not (a == 0 and b == 1):
        return None
    coeff, rest = f.as_independent(x, as_Add=False)
    p, k, m, q = sympy.Integer(0), 0, 0, 0
    for factor in sympy.Mul.make_args(rest):
        base, e = factor.as_base_exp()
        if base == x:
            if e.has(x):
                return None
            p += e
        elif base == sympy.log(x) and e.is_Integer and e > 0:
            k += int(e)
        elif base == sympy.log(1 - x) and e.is_Integer and e > 0:
            m += int(e)
        elif base == 1 - x and e.is_Integer and e < 0:
            q += -int(e)
        elif base == x - 1 and e.is_Integer and e < 0:
            q += -int(e)
            coeff *= (-1) ** e
        else:
            return None
    if k == 0 and m == 0:
        return None  # ordinary Beta-type: let SymPy do it
    if m > 2 or q > 2 or k > 4:
        return None
    n = sympy.Dummy("n", integer=True, nonnegative=True)
    # power-series coefficients of ln^m(1-x) (1-x)^{-q}
    # Build as a finite symbolic sum: for m=0 -> C(n+q-1,n); for m=1,q=0 -> -1/n (n>=1);
    # for m=1,q=1 -> -H_n ; m=2,q=0 -> 2 H_{n-1}/n ; general small cases via known identities.
    if m == 0:
        cn = sympy.binomial(n + q - 1, n)
        n0 = 0
    elif m == 1 and q == 0:
        cn = -1 / n
        n0 = 1
    elif m == 1 and q == 1:
        cn = -sympy.harmonic(n)
        n0 = 1
    elif m == 2 and q == 0:
        cn = 2 * sympy.harmonic(n - 1) / n
        n0 = 2
    else:
        return None
    inner = (-1) ** k * sympy.factorial(k) / (p + n + 1) ** (k + 1)
    total = sympy.summation(sympy.simplify(cn * inner), (n, n0, sympy.oo))
    if total is None or total.has(sympy.Sum):
        # Try expanding harmonic sums into zeta values via known Euler sums.
        return None
    return coeff * total


def _rule_frullani_cos2(f, x, a, b):
    """∫₀^∞ (cos(p x) - cos(q x)) / x² dx = π (|q| - |p|) / 2  (p, q real).

    SymPy leaves this unevaluated when p, q are symbolic; the closed form is the
    standard Frullani-cosine identity. p, q must not contain x.
    """
    if not (a == 0 and b == sympy.oo):
        return None
    e = sympy.expand(f * x**2)
    terms = list(e.args) if isinstance(e, sympy.Add) else [e]
    if len(terms) != 2:
        return None
    coses = []
    for t in terms:
        sign, c = (1, t)
        if isinstance(t, sympy.Mul) and t.args[0] == -1 and len(t.args) == 2:
            sign, c = -1, t.args[1]
        if not isinstance(c, sympy.cos):
            return None
        coef, rem = c.args[0].as_independent(x, as_Add=False)
        if rem != x or coef.has(x):
            return None
        coses.append((sign, coef))
    if sorted(s for s, _ in coses) != [-1, 1]:
        return None
    pos = next(c for s, c in coses if s == 1)
    neg = next(c for s, c in coses if s == -1)
    return sympy.pi * (sympy.Abs(neg) - sympy.Abs(pos)) / 2


def _residue_real_line(R, trig, k, x):
    """∫_{-∞}^∞ R(x) · trig(k x) dx by residues, k > 0.

    R must be a proper rational function of x with constant coefficients whose
    denominator splits into simple roots; poles on the real axis are allowed
    only at x = 0 (indented: contributes iπ·Res). Returns None when the pattern
    does not apply.
    """
    R = sympy.cancel(R)
    num, den = sympy.fraction(R)
    if not (num.is_polynomial(x) and den.is_polynomial(x)):
        return None
    if sympy.degree(num, x) >= sympy.degree(den, x):
        return None
    if num.has(x) and num.free_symbols - {x} or den.free_symbols - {x}:
        return None  # constant coefficients only: Im(pole) must be decidable
    roots = sympy.roots(den, x)
    if sum(roots.values()) != sympy.degree(den, x):
        return None
    uhp, real_simple = [], []
    for r, m in roots.items():
        if m > 1:
            return None
        r = sympy.simplify(r)
        if sympy.im(r) == 0:
            if r != 0:
                return None
            real_simple.append(r)
        elif sympy.im(r) > 0:
            uhp.append(r)
    z = sympy.Dummy("z")
    ez = sympy.exp(sympy.I * k * z)
    Rz = R.subs(x, z)
    total = sympy.Integer(0)
    try:
        for p in uhp:
            total += 2 * sympy.I * sympy.pi * sympy.limit((z - p) * Rz * ez, z, p)
        for p in real_simple:
            total += sympy.I * sympy.pi * sympy.limit((z - p) * Rz * ez, z, p)
    except (ValueError, NotImplementedError, TypeError):
        return None
    total = sympy.simplify(total)
    return sympy.im(total) if trig == "sin" else sympy.re(total)


def _rule_rational_trig(f, x, a, b):
    """R(x)·Sin[k x] / Cos[k x] over (0,∞) or ℝ, R rational.

    SymPy grinds or gives up on these; they close via residues on the real
    line. Half-line cases require a definite parity (odd R with sin, even R
    with cos) so ∫₀^∞ = ½ ∫_{-∞}^∞.
    """
    trigs = [t for t in f.atoms(sympy.sin, sympy.cos)]
    if len(trigs) != 1:
        return None
    t = trigs[0]
    k, rem = t.args[0].as_independent(x, as_Add=False)
    if rem != x or k.has(x):
        return None
    name = "sin" if isinstance(t, sympy.sin) else "cos"
    sign = sympy.Integer(1)
    if k.is_number:
        if k == 0:
            return None
        if k.is_negative or (k < 0) == sympy.true:
            k = -k
            if name == "sin":
                sign = -sign
    elif not k.is_positive:
        return None
    rest = sympy.cancel(f / t)
    num, den = sympy.fraction(rest)
    if not (num.is_polynomial(x) and den.is_polynomial(x)):
        return None
    if a == -sympy.oo and b == sympy.oo:
        r = _residue_real_line(rest, name, k, x)
        return None if r is None else sympy.simplify(sign * r)
    if a == 0 and b == sympy.oo:
        r_odd = sympy.simplify(rest + rest.subs(x, -x)) == 0
        r_even = sympy.simplify(rest - rest.subs(x, -x)) == 0
        if (name == "sin" and r_odd) or (name == "cos" and r_even):
            r = _residue_real_line(rest, name, k, x)
            return None if r is None else sympy.simplify(sign * r / 2)
    return None


def _rule_tan_subst(f, x, a, b):
    """∫₀^π R(sin²x, cos²x) dx (and ∫₀^{π/2}) via u = tan x.

    Rational functions of the squared trig functions become rational in u on
    (0, ∞): sin²x = u²/(1+u²), cos²x = 1/(1+u²), dx = du/(1+u²). On (0, π) the
    integrand is symmetric about π/2, doubling the (0, π/2) value. SymPy
    integrates the resulting rational function reliably, avoiding the nested
    radicals its direct trig path produces.
    """
    if (a, b) not in ((0, sympy.pi), (0, sympy.pi / 2)):
        return None
    if not f.has(sympy.sin, sympy.cos):
        return None
    u = sympy.Dummy("u", positive=True)
    sub = f.subs({sympy.sin(x) ** 2: u**2 / (1 + u**2), sympy.cos(x) ** 2: 1 / (1 + u**2)})
    if sub.has(sympy.sin, sympy.cos, sympy.tan):
        return None
    factor = 2 if b == sympy.pi else 1
    try:
        r = sympy.integrate(sympy.cancel(sub / (1 + u**2)), (u, 0, sympy.oo))
    except (ValueError, NotImplementedError, TypeError, sympy.PolynomialError):
        return None
    if r is None or r.has(sympy.Integral, sympy.Piecewise, sympy.nan):
        return None
    return sympy.simplify(factor * r)


def _cleanup_closed_form(expr):
    """Denest / compress an exact closed form that native SymPy left ugly.

    Two cheap rewrites: sqrtdenest+simplify (nested radicals like
    √(30±12√6)) and rewrite(exp)+simplify (hyperbolic combinations like
    -π(2Sinh[1]²-Sinh[2])/8). A candidate replaces the input only if it has
    no free symbols, is numerically identical to 50 digits, and is strictly
    smaller by operation count.
    """
    if expr.free_symbols or not expr.is_number:
        return expr
    try:
        target = sympy.N(expr, 50)
    except Exception:
        return expr
    base_ops = sympy.count_ops(expr)
    best = expr
    candidates = []
    if expr.has(sympy.sinh, sympy.cosh, sympy.tanh):
        candidates.append(lambda: sympy.simplify(expr.rewrite(sympy.exp)))
    if expr.has(sympy.Pow):
        candidates.append(lambda: sympy.simplify(sympy.sqrtdenest(expr)))
    for make in candidates:
        try:
            cand = make()
        except Exception:
            continue
        if cand.free_symbols or not cand.is_number:
            continue
        if sympy.count_ops(cand) >= sympy.count_ops(best) or sympy.count_ops(cand) >= base_ops:
            continue
        try:
            if abs(sympy.N(cand - expr, 50)) < sympy.Float(10) ** -40:
                best = cand
        except Exception:
            continue
    return best


def _polylog_cleanup(expr):
    """Replace polylog(k, ±I) combinations by closed forms in π, Catalan, log 2, ζ(3).

    The identification is numeric (60 digits, PSLQ over a small constant basis)
    and is only accepted when the candidate reproduces the value to 45 digits;
    otherwise the polylog expression is returned unchanged.
    """
    if not expr.has(sympy.polylog) or expr.free_symbols:
        return expr
    try:
        value = sympy.N(expr, 60)
        re_, im_ = sympy.re(value), sympy.im(value)
        if abs(im_) > sympy.Float(10) ** -50:
            return expr
        cand = sympy.nsimplify(re_, [sympy.pi, sympy.Catalan, sympy.log(2), sympy.zeta(3)], tolerance=sympy.Float(10) ** -40, rational=False)
        if cand.has(sympy.polylog) or not cand.is_number or cand.has(sympy.Float):
            return expr
        if abs(sympy.N(cand, 60) - re_) < sympy.Float(10) ** -45:
            return cand
    except Exception:
        pass
    return expr


# ---------------------------------------------------------------------------

def _map_distributions(expr):
    """Mathics leaves DiracDelta / UnitStep / HeavisideTheta as opaque
    SympyExpression wrappers; rewrite them to SymPy's DiracDelta / Heaviside."""
    from mathics.core.convert.sympy import SympyExpression as SE

    def visit(e):
        if isinstance(e, SE):
            head = str(e.args[0]) if e.args else ""
            args = [visit(a) for a in e.args[1:]]
            if head.endswith("DiracDelta") and len(args) == 1:
                return sympy.DiracDelta(args[0])
            if (head.endswith("UnitStep") or head.endswith("HeavisideTheta")) and len(args) == 1:
                return sympy.Heaviside(args[0])
            return e
        if e.args:
            return e.func(*[visit(a) for a in e.args])
        return e

    try:
        return visit(expr)
    except Exception:
        return expr


def _finish(result, evaluation):
    """Convert a SymPy result back to Mathics, simplifying unless it has Abs.

    Mathics' Simplify converts symbols to SymPy with positive=True, silently
    rewriting Abs[a] -> a. For Abs-carrying results (e.g. the Frullani answer
    π(|b|-|a|)) that changes the meaning for negative parameters, so return
    the converted form directly.
    """
    out = from_sympy(result)
    if result.has(sympy.Abs):
        return out
    return Expression(SymbolSimplify, out).evaluate(evaluation)


def _contains_head(expr, name):
    if not isinstance(expr, Expression):
        return False
    if expr.get_head_name() == name:
        return True
    return any(_contains_head(e, name) for e in expr.elements)


def _has_symbols(expr):
    """True if expr contains a user (Global`) symbol."""
    if isinstance(expr, Symbol):
        return expr.get_name().startswith("Global`")
    if isinstance(expr, Expression):
        return _has_symbols(expr.head) or any(_has_symbols(e) for e in expr.elements)
    return False


class IntegrateWithAssumptions(Integrate):
    name = "Integrate"
    context = "System`"

    def eval(self, f, xs, evaluation, options):  # type: ignore[override]
        "Integrate[f_, xs__, OptionsPattern[]]"
        local = options.get("System`Assumptions")
        has_local = local is not None and not (isinstance(local, Symbol) and local.get_name() == "System`$Assumptions")
        if not has_local:
            return self._fallbacks(f, xs, evaluation, options, {})
        defs = evaluation.definitions
        try:
            saved = defs.get_ownvalue("System`$Assumptions")
        except ValueError:
            saved = None
        assuming = local.evaluate(evaluation)
        defs.set_ownvalue("System`$Assumptions", assuming)
        try:
            facts = _facts_from_assumptions(assuming)
            opts = dict(options)
            opts.pop("System`Assumptions", None)
            return self._fallbacks(f, xs, evaluation, opts, facts)
        finally:
            defs.set_ownvalue("System`$Assumptions", saved if saved is not None else Symbol("System`True"))

    # ------------------------------------------------------------------
    def _fallbacks(self, f, xs, evaluation, options, facts):
        seq = xs.get_sequence()
        multi = len(seq) > 1
        native = None
        # Native Mathics mis-orders iterated integrals (it integrates the first
        # variable first, so Integrate[f, {x,0,1}, {y,0,x}] keeps a free x) and
        # treats DiracDelta / UnitStep as constants. Skip it in those cases.
        distributional = _contains_head(f, "System`DiracDelta") or _contains_head(f, "System`UnitStep") or _contains_head(f, "System`HeavisideTheta")
        if not multi and not distributional:
            fast = self._fast_rules(f, seq[0], evaluation, facts)
            if fast is not None:
                return fast
            native = super().eval(f, xs, evaluation, options)
            head = native.get_head_name() if isinstance(native, Expression) else None
            if native is not None and head not in ("System`Integrate", "System`ConditionalExpression", "System`Piecewise"):
                # A machine-precision Complex from an exact integrand means the
                # upstream code evalf'd a polylog(k, ±I) expression it could not
                # simplify. Retry exactly below; otherwise accept the native result.
                degraded = (
                    native.get_head_name() in ("System`Complex", "System`Real")
                    and not f.is_machine_precision()
                    and not any(e.is_machine_precision() for s in seq for e in s.elements)
                )
                has_inner_integral = native.has_form("Times", None) and any(
                    e.get_head_name() == "System`Integrate" for e in native.elements
                )
                # A closed form in PolyLog[k, ±I] etc. with no free symbols can
                # usually be identified as a π / Catalan / ζ constant.
                has_numeric_polylog = _contains_head(native, "System`PolyLog") and not _has_symbols(native)
                if not degraded and not has_inner_integral and not has_numeric_polylog:
                    return self._clean_native(native)
            if native is not None and head in ("System`ConditionalExpression", "System`Piecewise") and not facts:
                return native

        specs = []
        for spec in seq:
            if not spec.has_form("List", 3) or not spec.elements[0].get_name():
                return native
            var, a, b = spec.elements
            v_s, a_s, b_s = var.to_sympy(), a.evaluate(evaluation).to_sympy(), b.evaluate(evaluation).to_sympy()
            if any(t is None for t in (v_s, a_s, b_s)):
                return native
            specs.append((v_s, a_s, b_s))
        f_sympy = f.to_sympy(convert_all_global_functions=True)
        if f_sympy is None or not isinstance(f_sympy, sympy.Expr):
            return native
        f_sympy = _map_distributions(f_sympy)

        f_sympy, subs, bounds = _retype(f_sympy, facts)
        specs = [(subs.get(v, v), a, b) for v, a, b in specs]

        result = f_sympy
        # innermost variable is the first spec in Wolfram's Integrate[f, {x..}, {y..}]? No:
        # Integrate[f, {x,..}, {y,..}] integrates y first (innermost is last). Follow that.
        for v_s, a_s, b_s in reversed(specs):
            result = self._integrate_one(result, v_s, a_s, b_s, bounds)
            if result is None:
                return native
            result = _resolve_piecewise(result, bounds)
            if result.has(sympy.Integral):
                return native

        if result.has(sympy.Piecewise):
            return native
        result = _polylog_cleanup(result)
        back = {v: k for k, v in subs.items()}
        result = sympy.powsimp(sympy.powdenest(result, force=True), force=True).subs(back)
        result = sympy.powsimp(result, force=True)
        out = _finish(result, evaluation)
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _fast_rules(f, spec, evaluation, facts):
        """Cheap closed-form rules, tried before the native builtin.

        The matched families (Frullani cosine, rational×trig by residues,
        trig-rational via u = tan x) are exactly the ones where the native
        SymPy path burns tens of seconds to minutes before failing. Nonmatching
        integrands are rejected in milliseconds.
        """
        if not spec.has_form("List", 3) or not spec.elements[0].get_name():
            return None
        var, a, b = spec.elements
        v_s, a_s, b_s = var.to_sympy(), a.evaluate(evaluation).to_sympy(), b.evaluate(evaluation).to_sympy()
        if any(t is None for t in (v_s, a_s, b_s)):
            return None
        f_sympy = f.to_sympy(convert_all_global_functions=True)
        if f_sympy is None or not isinstance(f_sympy, sympy.Expr):
            return None
        f_sympy = _map_distributions(f_sympy)
        f_sympy, subs, bounds = _retype(f_sympy, facts)
        v_s = subs.get(v_s, v_s)
        for rule in (_rule_frullani_cos2, _rule_rational_trig, _rule_tan_subst):
            try:
                r = rule(f_sympy, v_s, a_s, b_s)
            except Exception:
                r = None
            if r is not None and not r.has(sympy.Integral, sympy.Sum, sympy.Piecewise, sympy.nan):
                back = {v: k for k, v in subs.items()}
                r = sympy.powsimp(sympy.powdenest(r, force=True), force=True).subs(back)
                r = sympy.powsimp(r, force=True)
                return _finish(r, evaluation)
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _clean_native(native):
        """Native SymPy results can be correct but needlessly nested (radicals,
        hyperbolic combinations). Prefer a numerically identical smaller form."""
        try:
            s = native.to_sympy()
        except Exception:
            return native
        if s is None or not isinstance(s, sympy.Expr):
            return native
        cleaned = _cleanup_closed_form(s)
        if cleaned is s or cleaned == s:
            return native
        try:
            return from_sympy(cleaned)
        except Exception:
            return native

    # ------------------------------------------------------------------
    @staticmethod
    def _integrate_one(expr, v, a, b, bounds):
        def try_int(e, lo, hi):
            try:
                r = sympy.integrate(e, (v, lo, hi))
            except (ValueError, NotImplementedError, TypeError, sympy.PolynomialError, RecursionError):
                return None
            if r is None or r.has(sympy.nan):
                return None
            if isinstance(r, sympy.Piecewise):
                # the fallback branch of a convergence Piecewise is an Integral;
                # try the even-parameter argument before giving up on it
                r = _even_parameter_retry(e, v, lo, hi, r)
            if r.has(sympy.Integral):
                return None
            return r

        # Cheap pattern rules first: they bail in milliseconds when the
        # integrand does not match, and the matching cases are exactly the ones
        # where sympy.integrate churns for minutes or returns nested radicals.
        for rule in (_rule_frullani_cos2, _rule_rational_trig, _rule_tan_subst):
            try:
                r = rule(expr, v, a, b)
            except Exception:
                r = None
            if r is not None and not r.has(sympy.Integral, sympy.Sum, sympy.Piecewise, sympy.nan):
                return r

        # Assumption-driven gaussian retyping first: it avoids SymPy's
        # Piecewise/polar_lift output for exp((a^2-1) x^2) when -1 < a < 1.
        expr_g, repl = _gaussian_retype(sympy.simplify(expr) if expr.has(sympy.erfc, sympy.erf) else expr, v, bounds)
        if repl:
            r = try_int(expr_g, a, b)
            if r is not None and not r.has(sympy.Piecewise):
                return r.subs(repl)
        r = try_int(expr, a, b)
        if r is not None:
            return r
        for rule in (_rule_bose_fermi, _rule_log_series):
            try:
                r = rule(expr, v, a, b)
            except Exception:
                r = None
            if r is not None and not r.has(sympy.Sum, sympy.Integral):
                return r
        if a == -sympy.oo and b == sympy.oo:
            even = sympy.simplify(expr + expr.subs(v, -v))
            r = try_int(even, 0, sympy.oo)
            if r is not None:
                return r
        return None


def register_assumption_integrate(session):
    IntegrateWithAssumptions(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Integrate")
