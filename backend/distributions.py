"""Symbolic probability distributions (Mathics 10.0.1 has none).

Contracts from Wolfram 15.0.1 Usage.m.  Distribution heads are inert symbolic
objects; the functions below recognise them and compute via ``sympy.stats``:

  PDF[dist, x]   CDF[dist, x]   SurvivalFunction[dist, x]   InverseCDF[dist, q]
  Mean / Variance / StandardDeviation / Median / Moment[dist, k]
  Expectation[expr, x \\[Distributed] dist]
  Probability[pred, x \\[Distributed] dist]
  RandomVariate[dist] / RandomVariate[dist, n]
  Quantile[dist, q]

Supported heads: NormalDistribution, UniformDistribution, ExponentialDistribution,
PoissonDistribution, BinomialDistribution, GammaDistribution, BetaDistribution,
ChiSquareDistribution, StudentTDistribution, CauchyDistribution,
LogNormalDistribution, GeometricDistribution, BernoulliDistribution,
WeibullDistribution, LaplaceDistribution, DiscreteUniformDistribution.

``Mean[NormalDistribution[m, s]]`` previously fell through to the list rule
``Total[list]/Length[list]`` and returned (m + s)/2; the distribution rules
below are registered ahead of the list rule so that no longer happens.
"""

from __future__ import annotations

import sympy
from sympy import stats as st

from mathics.core.atoms import Integer, MachineReal
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED, A_HOLD_REST
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol


# name -> (sympy constructor, arity list, is_discrete)
_DISTS = {
    "NormalDistribution": (lambda n, *a: st.Normal(n, *(a or (0, 1))), (0, 2), False),
    "UniformDistribution": (lambda n, *a: st.Uniform(n, *(a[0] if a else (0, 1))), (0, 1), False),
    "ExponentialDistribution": (lambda n, l: st.Exponential(n, l), (1,), False),
    "GammaDistribution": (lambda n, a, b: st.Gamma(n, a, b), (2,), False),
    "BetaDistribution": (lambda n, a, b: st.Beta(n, a, b), (2,), False),
    "ChiSquareDistribution": (lambda n, k: st.ChiSquared(n, k), (1,), False),
    "StudentTDistribution": (lambda n, *a: st.StudentT(n, a[-1]) if len(a) == 1 else None, (1,), False),
    "CauchyDistribution": (lambda n, *a: st.Cauchy(n, *(a or (0, 1))), (0, 2), False),
    "LogNormalDistribution": (lambda n, m, s: st.LogNormal(n, m, s), (2,), False),
    "WeibullDistribution": (lambda n, a, b: st.Weibull(n, b, a), (2,), False),
    "LaplaceDistribution": (lambda n, m, b: st.Laplace(n, m, b), (2,), False),
    "PoissonDistribution": (lambda n, l: st.Poisson(n, l), (1,), True),
    "BinomialDistribution": (lambda n, k, p: st.Binomial(n, k, p), (2,), True),
    # Wolfram's GeometricDistribution counts failures before the first success
    # (support 0, 1, ...); sympy's counts trials (support 1, 2, ...).
    "GeometricDistribution": (lambda n, p: st.Geometric(n, p) - 1, (1,), True),
    "BernoulliDistribution": (lambda n, p: st.Bernoulli(n, p), (1,), True),
    "DiscreteUniformDistribution": (lambda n, r: st.DiscreteUniform(n, list(range(int(r[0]), int(r[1]) + 1))), (1,), True),
}


# Which parameter positions are scale/rate parameters (must be positive) and
# which are probabilities (in (0,1)).  Symbolic parameters in those slots get
# the matching SymPy assumptions so erf/erfc and sqrt(s^2) simplify as Wolfram does.
_POSITIVE_SLOTS = {
    "NormalDistribution": {1}, "ExponentialDistribution": {0}, "GammaDistribution": {0, 1},
    "BetaDistribution": {0, 1}, "ChiSquareDistribution": {0}, "StudentTDistribution": {0},
    "CauchyDistribution": {1}, "LogNormalDistribution": {1}, "WeibullDistribution": {0, 1},
    "LaplaceDistribution": {1}, "PoissonDistribution": {0}, "BinomialDistribution": {0},
}
_PROB_SLOTS = {"BinomialDistribution": {1}, "GeometricDistribution": {0}, "BernoulliDistribution": {0}}
_param_subs: dict = {}


def _type_param(short, i, s):
    if not isinstance(s, sympy.Symbol):
        return s
    if i in _POSITIVE_SLOTS.get(short, ()):
        if s.is_positive:
            return s
        t = sympy.Symbol(s.name, positive=True)
    elif i in _PROB_SLOTS.get(short, ()):
        t = sympy.Symbol(s.name, positive=True)
    else:
        if s.is_real:
            return s
        t = sympy.Symbol(s.name, real=True)
    _param_subs[t] = s
    return t


def _to_rv(dist, name="X"):
    """Mathics distribution expression -> sympy random variable, or None."""
    head = dist.get_head_name()
    short = head.split("`")[-1]
    if short not in _DISTS:
        return None
    ctor, arities, discrete = _DISTS[short]
    args = []
    for i, el in enumerate(dist.elements):
        if el.has_form("List", None):
            sub = [e.to_sympy() for e in el.elements]
            if any(s is None for s in sub):
                return None
            args.append(tuple(_type_param(short, i, s) for s in sub))
        else:
            s = el.to_sympy()
            if s is None:
                return None
            args.append(_type_param(short, i, s))
    if len(args) not in arities:
        return None
    try:
        rv = ctor(name, *args)
    except Exception:
        return None
    return rv


# Textbook moments for heads where sympy.stats returns unevaluated sums with
# symbolic parameters.  Keys: (head, statistic) -> lambda over the args.
_CLOSED = {
    ("BinomialDistribution", "mean"): lambda n, p: n * p,
    ("BinomialDistribution", "variance"): lambda n, p: n * p * (1 - p),
    ("GeometricDistribution", "mean"): lambda p: (1 - p) / p,
    ("GeometricDistribution", "variance"): lambda p: (1 - p) / p**2,
    ("PoissonDistribution", "mean"): lambda l: l,
    ("PoissonDistribution", "variance"): lambda l: l,
    ("BernoulliDistribution", "mean"): lambda p: p,
    ("BernoulliDistribution", "variance"): lambda p: p * (1 - p),
    ("ExponentialDistribution", "std"): lambda l: 1 / l,
    ("NormalDistribution", "std"): lambda m=0, s=1: s,
}


def _closed_stat(dist, stat):
    short = dist.get_head_name().split("`")[-1]
    fn = _CLOSED.get((short, stat))
    if fn is None:
        return None
    args = [el.to_sympy() for el in dist.elements]
    if any(a is None for a in args):
        return None
    try:
        return fn(*args)
    except TypeError:
        return None


def _simplify(e):
    try:
        e = sympy.simplify(e)
        # erf(z) + erfc(z) == 1 is not applied by simplify; do it by hand.
        if e.has(sympy.erfc):
            e = sympy.simplify(e.rewrite(sympy.erf))
        return e
    except Exception:
        return e


def _out(e, evaluation=None):
    if e is None:
        return None
    if isinstance(e, sympy.Piecewise):
        e = sympy.piecewise_fold(e)
    if isinstance(e, sympy.Basic) and _param_subs:
        # strip the temporary positivity typing before converting back
        e = e.subs({t: s for t, s in _param_subs.items() if e.has(t)})
    return from_sympy(e)


class _DistFunction(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED


class PDF(_DistFunction):
    summary_text = "probability density function"

    def eval(self, dist, x, evaluation):
        "PDF[dist_, x_]"
        rv = _to_rv(dist)
        if rv is None:
            return None
        xs = x.to_sympy()
        if xs is None:
            return None
        try:
            d = st.density(rv)(xs)
        except Exception:
            return None
        return _out(_simplify(d))

    def eval_pure(self, dist, evaluation):
        "PDF[dist_]"
        rv = _to_rv(dist)
        if rv is None:
            return None
        t = sympy.Dummy("t")
        try:
            d = st.density(rv)(t)
        except Exception:
            return None
        body = from_sympy(_simplify(d)).replace_vars({t.name: Expression(Symbol("System`Slot"), Integer(1))})
        return Expression(Symbol("System`Function"), body)


class CDF(_DistFunction):
    summary_text = "cumulative distribution function"

    def eval(self, dist, x, evaluation):
        "CDF[dist_, x_]"
        rv = _to_rv(dist)
        if rv is None:
            return None
        xs = x.to_sympy()
        if xs is None:
            return None
        try:
            c = _cdf_at(rv, xs)
        except Exception:
            return None
        return _out(_simplify(c))


def _cdf_at(rv, xs):
    """CDF value; sympy's cdf() of a discrete RV is a dict/lambda hybrid, so use P(X <= x)."""
    c = st.cdf(rv)
    if callable(c):
        try:
            return c(xs)
        except TypeError:
            pass
    return st.P(rv <= xs)


class SurvivalFunction(_DistFunction):
    summary_text = "survival function 1 - CDF"

    def eval(self, dist, x, evaluation):
        "SurvivalFunction[dist_, x_]"
        rv = _to_rv(dist)
        if rv is None:
            return None
        xs = x.to_sympy()
        if xs is None:
            return None
        try:
            c = _cdf_at(rv, xs)
        except Exception:
            return None
        return _out(_simplify(1 - c))


class InverseCDF(_DistFunction):
    summary_text = "inverse cumulative distribution function"

    def eval(self, dist, q, evaluation):
        "InverseCDF[dist_, q_]"
        rv = _to_rv(dist)
        if rv is None:
            return None
        qs = q.to_sympy()
        if qs is None:
            return None
        try:
            r = st.quantile(rv)(qs)
        except Exception:
            return None
        return _out(_simplify(r))


from mathics.builtin.statistics.orderstats import Quantile as _NativeQuantile


class Quantile(_NativeQuantile):
    """Quantile for distributions; list quantiles keep the native rules."""
    name = "Quantile"
    context = "System`"

    def eval_dist(self, dist, q, evaluation):
        "Quantile[dist_?(MemberQ[{NormalDistribution, UniformDistribution, ExponentialDistribution, GammaDistribution, BetaDistribution, ChiSquareDistribution, StudentTDistribution, CauchyDistribution, LogNormalDistribution, WeibullDistribution, LaplaceDistribution, PoissonDistribution, BinomialDistribution, GeometricDistribution, BernoulliDistribution, DiscreteUniformDistribution}, Head[#]]&), q_?NumericQ]"
        rv = _to_rv(dist)
        if rv is None:
            return None
        qs = q.to_sympy()
        short = dist.get_head_name().split("`")[-1]
        if _DISTS[short][2]:
            return _discrete_quantile(rv, qs, short)
        try:
            r = st.quantile(rv)(qs)
        except Exception:
            return None
        return _out(_simplify(r))


def _discrete_quantile(rv, qs, short):
    """Smallest integer k with CDF(k) >= q (Wolfram's convention for discrete
    distributions); sympy's quantile leaks a Dummy for these."""
    try:
        qv = float(qs)
    except Exception:
        return None
    if not 0 <= qv <= 1:
        return None
    lo = 0
    if short == "DiscreteUniformDistribution":
        try:
            lo = int(min(rv.pspace.domain.set))
        except Exception:
            lo = 0
    k = lo
    for _ in range(100000):
        try:
            c = float(st.P(rv <= k))
        except Exception:
            return None
        if c >= qv - 1e-12:
            return Integer(k)
        k += 1
    return None


from mathics.builtin.statistics.location import Mean as _NativeMean, Median as _NativeMedian
from mathics.builtin.statistics.dependency import Variance as _NativeVariance, StandardDeviation as _NativeStd
from mathics.builtin.statistics.shape import Skewness as _NativeSkew, Kurtosis as _NativeKurt

_HEAD_TEST = "(MemberQ[{%s}, Head[#]]&)" % ", ".join(_DISTS)


def _dist_rule(name, fn, base):
    """Subclass the native list-statistics builtin and add a distribution branch.

    The branch pattern is head-restricted so it only fires for distribution
    objects; the native list rules are inherited unchanged."""

    stat_key = {"Mean": "mean", "Variance": "variance", "StandardDeviation": "std"}.get(name)

    def eval_dist(self, dist, evaluation):
        if stat_key:
            closed = _closed_stat(dist, stat_key)
            if closed is not None:
                return _out(_simplify(closed))
        rv = _to_rv(dist)
        if rv is None:
            return None
        try:
            v = fn(rv)
        except Exception:
            return None
        if isinstance(v, sympy.Expr) and v.has(sympy.Sum, sympy.Integral):
            return None
        return _out(_simplify(v))

    # Mathics reads the pattern from the method docstring; build it explicitly
    # because %(name)s substitution is not applied to dynamically created classes.
    eval_dist.__doc__ = f"{name}[dist_?{_HEAD_TEST}]"

    # Native rules such as Mean[list_] match any head (which is how
    # Mean[NormalDistribution[m, s]] became (m+s)/2). Restrict them to lists.
    rules = {
        k.replace("list_]", "list_List]").replace("[list_,", "[list_List,"): v
        for k, v in getattr(base, "rules", {}).items()
    }
    return type(name, (base,), {"name": name, "context": "System`", "rules": rules, "eval_dist": eval_dist, "__doc__": base.__doc__})


Mean = _dist_rule("Mean", st.E, _NativeMean)
Variance = _dist_rule("Variance", st.variance, _NativeVariance)
StandardDeviation = _dist_rule("StandardDeviation", st.std, _NativeStd)
Median = _dist_rule("Median", lambda rv: st.quantile(rv)(sympy.Rational(1, 2)), _NativeMedian)
Skewness = _dist_rule("Skewness", st.skewness, _NativeSkew)
Kurtosis = _dist_rule("Kurtosis", st.kurtosis, _NativeKurt)


class Moment(_DistFunction):
    def eval(self, dist, k, evaluation):
        "Moment[dist_, k_Integer]"
        if dist.has_form("List", None):
            return None
        rv = _to_rv(dist)
        if rv is None:
            return None
        try:
            v = st.moment(rv, k.get_int_value())
        except Exception:
            return None
        return _out(_simplify(v))


def _bind(spec):
    """x \\[Distributed] dist  ->  (x symbol, rv) or None."""
    if spec.get_head_name() != "System`Distributed" or len(spec.elements) != 2:
        return None
    x, dist = spec.elements
    if not isinstance(x, Symbol):
        return None
    rv = _to_rv(dist, x.get_name().split("`")[-1])
    if rv is None:
        return None
    return x, rv


class Expectation(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED | A_HOLD_REST
    summary_text = "expectation of an expression under a distribution"

    def eval(self, expr, spec, evaluation):
        "Expectation[expr_, spec_]"
        b = _bind(spec.evaluate(evaluation))
        if b is None:
            return None
        x, rv = b
        es = expr.to_sympy()
        if es is None:
            return None
        es = es.subs(x.to_sympy(), rv)
        try:
            v = st.E(es)
        except Exception:
            return None
        if isinstance(v, sympy.Expr) and v.has(sympy.Integral, sympy.Sum):
            return None
        return _out(_simplify(v))


def _predicate_to_sympy(pred):
    """Mathics And/Or/Not/relations -> SymPy boolean (Mathics' own to_sympy wraps And opaquely)."""
    head = pred.get_head_name()
    if head == "System`And":
        parts = [_predicate_to_sympy(e) for e in pred.elements]
        return None if any(p is None for p in parts) else sympy.And(*parts)
    if head == "System`Or":
        parts = [_predicate_to_sympy(e) for e in pred.elements]
        return None if any(p is None for p in parts) else sympy.Or(*parts)
    if head == "System`Not" and len(pred.elements) == 1:
        p = _predicate_to_sympy(pred.elements[0])
        return None if p is None else sympy.Not(p)
    s = pred.to_sympy()
    return s if isinstance(s, sympy.core.relational.Relational) else None


class Probability(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED | A_HOLD_REST
    summary_text = "probability of an event under a distribution"

    def eval(self, pred, spec, evaluation):
        "Probability[pred_, spec_]"
        b = _bind(spec.evaluate(evaluation))
        if b is None:
            return None
        x, rv = b
        ps = _predicate_to_sympy(pred)
        if ps is None:
            return None
        ps = ps.subs(x.to_sympy(), rv)
        try:
            v = st.P(ps)
        except Exception:
            # And of two one-sided relations: P(a < X < b) = CDF(b) - CDF(a)
            v = None
            if isinstance(ps, sympy.And) and len(ps.args) == 2:
                try:
                    lo = hi = None
                    for r in ps.args:
                        if isinstance(r, (sympy.StrictGreaterThan, sympy.GreaterThan)) and r.lhs == rv:
                            lo = r.rhs
                        elif isinstance(r, (sympy.StrictLessThan, sympy.LessThan)) and r.lhs == rv:
                            hi = r.rhs
                        elif isinstance(r, (sympy.StrictLessThan, sympy.LessThan)) and r.rhs == rv:
                            lo = r.lhs
                        elif isinstance(r, (sympy.StrictGreaterThan, sympy.GreaterThan)) and r.rhs == rv:
                            hi = r.lhs
                    if lo is not None and hi is not None:
                        v = st.P(rv <= hi) - st.P(rv <= lo)
                except Exception:
                    v = None
            if v is None:
                return None
        if isinstance(v, sympy.Expr) and v.has(sympy.Integral, sympy.Sum):
            return None
        return _out(_simplify(v))


class RandomVariate(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "pseudorandom sample from a distribution"

    def eval(self, dist, evaluation):
        "RandomVariate[dist_]"
        vals = _sample(dist, 1)
        if vals is None:
            return None
        return _num(vals[0])

    def eval_n(self, dist, n, evaluation):
        "RandomVariate[dist_, n_Integer]"
        count = n.get_int_value()
        if count is None or count < 0 or count > 10**6:
            return None
        vals = _sample(dist, count)
        if vals is None:
            return None
        return ListExpression(*(_num(v) for v in vals))

    def eval_shape(self, dist, shape, evaluation):
        "RandomVariate[dist_, shape_List]"
        dims = [d.get_int_value() for d in shape.elements]
        if any(d is None or d < 0 for d in dims) or not dims:
            return None
        total = 1
        for d in dims:
            total *= d
        if total > 10**6:
            return None
        vals = _sample(dist, total)
        if vals is None:
            return None
        flat = [_num(v) for v in vals]

        def build(items, ds):
            if len(ds) == 1:
                return ListExpression(*items)
            step = len(items) // ds[0]
            return ListExpression(*(build(items[i * step:(i + 1) * step], ds[1:]) for i in range(ds[0])))
        return build(flat, dims)


def _sample(dist, count):
    short = dist.get_head_name().split("`")[-1]
    if short in ("MultinormalDistribution", "BinormalDistribution", "ProductDistribution", "MultinomialDistribution",
                 "DirichletDistribution", "DiscreteUniformDistribution", "UniformDistribution", "MixtureDistribution",
                 "EmpiricalDistribution") or short not in _DISTS:
        vals = _sample_numpy(dist, short, count)
        if vals is not None:
            return vals
    rv = _to_rv(dist)
    if rv is None:
        return None
    try:
        if short == "GeometricDistribution":
            # rv is sympy Geometric - 1 (an Add, not samplable); sample the base
            base = st.Geometric("X", dist.elements[0].to_sympy())
            return [int(v) - 1 for v in st.sample(base, size=count)]
        return list(st.sample(rv, size=count))
    except Exception:
        return None


def _floats(expr):
    try:
        if expr.has_form("List", None):
            return [_floats(e) for e in expr.elements]
        return float(expr.to_sympy())
    except Exception:
        return None


def _sample_numpy(dist, short, count):
    """numpy-based sampling for heads sympy.stats cannot sample (multivariate,
    mixtures, ...).  Vector-valued samples are returned as lists."""
    import numpy as np
    rng = np.random.default_rng()
    els = dist.elements
    try:
        if short == "MultinormalDistribution":
            mu, sigma = _floats(els[0]), _floats(els[1])
            return [list(v) for v in rng.multivariate_normal(mu, sigma, size=count)]
        if short == "BinormalDistribution":
            if len(els) == 3:
                (m1, m2), (s1, s2), r = _floats(els[0]), _floats(els[1]), _floats(els[2])
            else:
                (m1, m2), (s1, s2), r = (0, 0), (1, 1), _floats(els[0])
            cov = [[s1 * s1, r * s1 * s2], [r * s1 * s2, s2 * s2]]
            return [list(v) for v in rng.multivariate_normal([m1, m2], cov, size=count)]
        if short == "MultinomialDistribution":
            n, ps = _floats(els[0]), _floats(els[1])
            return [list(v) for v in rng.multinomial(int(n), ps, size=count)]
        if short == "DirichletDistribution":
            return [list(v)[:-1] for v in rng.dirichlet(_floats(els[0]), size=count)]
        if short == "ProductDistribution":
            cols = [_sample(d, count) for d in els]
            if any(c is None for c in cols):
                return None
            return [list(t) for t in zip(*cols)]
        if short == "UniformDistribution":
            a, b = _floats(els[0]) if els else (0.0, 1.0)
            return list(rng.uniform(a, b, size=count))
        if short == "DiscreteUniformDistribution":
            a, b = _floats(els[0])
            return [int(v) for v in rng.integers(int(a), int(b) + 1, size=count)]
        if short == "MixtureDistribution":
            w = _floats(els[0])
            comps = list(els[1].elements)
            tot = sum(w)
            picks = rng.choice(len(comps), size=count, p=[x / tot for x in w])
            out = []
            for i in picks:
                s = _sample(comps[i], 1)
                if s is None:
                    return None
                out.append(s[0])
            return out
        if short == "EmpiricalDistribution":
            data = _floats(els[0])
            return list(rng.choice(data, size=count))
    except Exception:
        return None
    return None


def _num(v):
    if isinstance(v, list):
        return ListExpression(*(_num(x) for x in v))
    try:
        f = float(v)
    except Exception:
        return from_sympy(sympy.sympify(v))
    if f.is_integer() and abs(f) < 2**53 and isinstance(v, (int,)) or (hasattr(v, "dtype") and "int" in str(getattr(v, "dtype", ""))):
        return Integer(int(f))
    return MachineReal(f)


def register_distributions(session):
    for cls in (PDF, CDF, SurvivalFunction, InverseCDF, Quantile, Mean, Variance, StandardDeviation, Median, Skewness, Kurtosis, Moment, Expectation, Probability, RandomVariate):
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
    # Distribution heads and Distributed must exist as inert protected symbols.
    for name in list(_DISTS) + ["Distributed"]:
        sym = f"System`{name}"
        session.definitions.get_definition(sym)
        session.definitions.clear_cache(sym)
