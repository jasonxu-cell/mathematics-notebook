"""Small, explicit compatibility additions to the pinned open-source engine."""

import sympy

from mathics.builtin.numbers.algebra import Factor
from mathics.core.convert.sympy import from_sympy

from errors import RequestError


class FactorWithExtension(Factor):
    """Preserve native Factor and add exact algebraic Extension fields."""

    name = "Factor"
    context = "System`"
    # Inspect every supplied option ourselves so an unsupported option is a
    # protocol error, rather than a warning plus an unevaluated Factor result.
    options = {"Extension": "None", "$OptionSyntax": "Ignore"}

    def eval(self, expr, evaluation, options):
        "Factor[expr_, OptionsPattern[Factor]]"
        unknown = set(options) - {"System`Extension"}
        if unknown:
            names = ", ".join(sorted(name.rsplit("`", 1)[-1] for name in unknown))
            raise RequestError("unsupported_factor_option", f"Factor supports only the Extension option in this backend; unsupported: {names}.")
        extension = options["System`Extension"]
        if extension.get_name() == "System`None":
            return super().eval(expr, evaluation)
        # Arguments and ordinary Rule RHSs have already been evaluated by
        # Mathics. Conversion operates on their ASTs and never reparses source
        # or executes either the polynomial or the option expression again.
        values = extension.elements if extension.has_form("List", None) else (extension,)
        if not values or len(values) > 8:
            raise RequestError("unsupported_factor_extension", "Extension requires one to eight exact algebraic numbers.")
        converted = []
        for value in values:
            number = value.to_sympy()
            if (number is None or not isinstance(number, sympy.Expr)
                    or number.is_algebraic is not True or number.free_symbols
                    or number.has(sympy.Float)):
                raise RequestError("unsupported_factor_extension", "Extension requires exact algebraic numbers, such as Sqrt[2], I, or a list of them.")
            converted.append(number)
        polynomial = expr.to_sympy()
        if polynomial is None or not isinstance(polynomial, sympy.Expr):
            raise RequestError("unsupported_factor_expression", "Factor with Extension requires a polynomial or rational expression convertible to SymPy.")
        numerator, denominator = polynomial.as_numer_denom()
        if not numerator.is_polynomial() or not denominator.is_polynomial():
            raise RequestError("unsupported_factor_expression", "Factor with Extension supports polynomial and rational expressions.")
        try:
            factored = sympy.factor(polynomial, extension=converted)
        except (sympy.PolynomialError, ValueError, TypeError, NotImplementedError) as exc:
            raise RequestError("factor_extension_error", f"Algebraic field factorization failed: {exc}") from exc
        return from_sympy(factored)


def register_compatibility(session):
    import pattern_order
    pattern_order.install()  # Wolfram's specificity ordering for f[x_, x_] vs f[x_, y_]
    from algebra_extras import (CharacteristicPolynomial, ChineseRemainder, GroebnerBasis, JordanDecomposition,
                                PolynomialQuotient, PolynomialRemainder, Resultant, RootApproximant, TrigExpand, TrigReduce)
    from bernoulli import register_bernoulli
    from discrete_limit import register_discrete_limit
    from dist_derived import register_dist_derived
    from dist_rules import register_dist_rules
    from distributions import register_distributions
    from euler_sums_products import ProductWithGammaClosedForms
    from limit_guard import register_limit
    from more_builtins import register_more_builtins
    from numeric_extras import register_numeric_extras
    from plots_regions import register_plots_regions
    from result_polish import register_result_polish
    from series_expand import register_series
    from special_functions import register_special_functions
    from special_functions2 import register_special_functions2
    from special_rules import register_special_rules
    from symbolic_extras import register_symbolic_extras
    from zeta_derivatives import register_zeta_derivatives

    FactorWithExtension(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Factor")
    session.definitions.clear_cache("System`Extension")
    # Sum chain:  SumWithFibonacci > SumWithEulerSums > SumWithDirichletSeries > native
    # Integrate chain:  IntegrateWithTable > IntegrateWithAssumptions > native
    # Both outermost classes are registered by register_symbolic_extras.
    register_symbolic_extras(session)
    ProductWithGammaClosedForms(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`Product")
    register_bernoulli(session)
    register_series(session)
    register_limit(session)
    register_discrete_limit(session)
    register_numeric_extras(session)
    register_distributions(session)
    register_plots_regions(session)
    for cls in (CharacteristicPolynomial, ChineseRemainder, GroebnerBasis, JordanDecomposition,
                PolynomialQuotient, PolynomialRemainder, Resultant, RootApproximant, TrigExpand, TrigReduce):
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
    register_more_builtins(session)
    register_zeta_derivatives(session)   # after more_builtins: replaces its FunctionExpand
    # Outermost overrides (RSolve, DSolve, Sum) — must come after everything they wrap.
    register_result_polish(session)
    # Distribution contracts from the real kernel (0.4): special functions the
    # contract forms need, then the per-head rules.  These are plain WL
    # downvalues, so they take precedence over the sympy.stats builtins from
    # register_distributions, which remain the fallback for anything not in
    # the table (Expectation of arbitrary expressions, RandomVariate, ...).
    register_special_functions(session)
    register_dist_rules(session)
    register_dist_derived(session)
    # Group 4: special functions missing from Mathics + Wolfram's exact rules
    register_special_functions2(session)
    register_special_rules(session)
    # Group 5: list / string / functional heads missing from Mathics
    from list_string_extras import register_list_string_extras
    register_list_string_extras(session)
    from list_rules import register_list_rules
    register_list_rules(session)
    # Group 6: graph builtins (pure Python, no networkx)
    from graphs import register_graphs
    register_graphs(session)
    # Group 7: integral transforms, interpolation/fitting, graph batch 2,
    # polynomial/root extras, small high-frequency heads
    from transforms import register_transforms
    register_transforms(session)
    from interpolation import register_interpolation
    register_interpolation(session)
    from graphs2 import register_graphs2
    register_graphs2(session)
    from polynomial_extras import register_polynomial_extras
    register_polynomial_extras(session)
    from misc_extras import register_misc_extras
    register_misc_extras(session)
