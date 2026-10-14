"""Algebraic identities checked on real evaluator output, without source parsing."""

from pathlib import Path
import sys
import unittest

import sympy

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


class FactorExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel()

    def setUp(self):
        self.notebook = self.id()

    def request(self, source):
        return self.kernel.dispatch({"id":source,"op":"evaluate","source":source,"notebook_id":self.notebook})

    def evaluate(self, source):
        response = self.request(source)
        self.assertTrue(response["ok"], response)
        return response["result"]

    def last_sympy(self):
        # Convert the already evaluated output AST, never evaluate the source
        # again to obtain an expected result or to inspect its decomposition.
        return self.kernel.sessions[self.notebook].evaluation.last_eval.to_sympy()

    def test_quartic_sqrt2_has_the_correct_two_factors(self):
        result = self.evaluate("Factor[x^4 + 1, Extension -> Sqrt[2]]")
        actual = self.last_sympy()
        (x,) = actual.free_symbols
        expected_factors = [x*x - sympy.sqrt(2)*x + 1, x*x + sympy.sqrt(2)*x + 1]
        self.assertEqual(0, sympy.expand(actual - (x**4+1)))
        self.assertEqual(0, sympy.expand(actual - sympy.Mul(*expected_factors)))
        self.assertTrue(actual.is_Mul)
        self.assertEqual(2, len(actual.args))
        self.assertEqual({sympy.expand(factor) for factor in expected_factors}, {sympy.expand(factor) for factor in actual.args})
        self.assertIn("Sqrt[2]", result["text"])
        self.assertNotIn("Factor[", result["text"])
        self.assertIn("latex", result)

    def test_plain_factor_is_preserved(self):
        self.evaluate("Factor[x^2-1]")
        actual = self.last_sympy()
        (x,) = actual.free_symbols
        self.assertEqual(0, sympy.expand(actual-(x**2-1)))
        self.assertEqual(2, len(actual.args))
        self.assertEqual("(1 + x) ^ 2", self.evaluate("Factor[x^2+2 x+1]")["text"])

    def test_plain_factor_lists_equations_and_rational_expressions(self):
        result = self.evaluate("Factor[{x+x^2,2 x+2 y+2}]")
        self.assertIn("x (1 + x)", result["text"])
        self.assertIn("2 (1 + x + y)", result["text"])
        result = self.evaluate("Factor[x a == x b + x c]")
        self.assertIn("x (b + c)", result["text"])
        self.evaluate("Factor[(x^2-1)/(x^2+2 x+1)]")
        actual = self.last_sympy()
        (x,) = actual.free_symbols
        self.assertEqual(0, sympy.cancel(actual-(x-1)/(x+1)))

    def test_algebraic_list_and_complex_extension(self):
        self.evaluate("Factor[x^2-2,Extension->{Sqrt[2],Sqrt[3]}]")
        actual = self.last_sympy()
        (x,) = actual.free_symbols
        self.assertEqual(0, sympy.expand(actual-(x**2-2)))
        self.assertTrue(actual.is_Mul)
        self.evaluate("Factor[x^2+1,Extension->I]")
        actual = self.last_sympy()
        (x,) = actual.free_symbols
        self.assertEqual({x-sympy.I,x+sympy.I},set(actual.args))

    def test_rational_expression_with_extension(self):
        self.evaluate("Factor[(x^4+1)/(x^2-2),Extension->Sqrt[2]]")
        actual = self.last_sympy()
        (x,) = actual.free_symbols
        self.assertEqual(0,sympy.cancel(actual-(x**4+1)/(x**2-2)))
        self.assertTrue(actual.has(sympy.sqrt(2)))

    def test_polynomial_and_option_effects_run_once(self):
        self.evaluate("counter=0")
        result = self.evaluate('Factor[(counter++;Print["polynomial"];x^4+1),Extension->(counter++;Print["extension"];Sqrt[2])]')
        self.assertEqual(["polynomial","extension"],result["prints"])
        self.assertNotIn("Factor[",result["text"])
        self.assertEqual("2",self.evaluate("counter")["text"])

    def test_unsupported_options_and_fields_are_explicit_errors(self):
        cases = [
            ("Factor[x^2-1,Modulus->2]","unsupported_factor_option"),
            ("Factor[x^2-1,Extension->Sqrt[2],GaussianIntegers->True]","unsupported_factor_option"),
            ("Factor[x^2-1,Extension->a]","unsupported_factor_extension"),
            ("Factor[x^2-1,Extension->Pi]","unsupported_factor_extension"),
            ("Factor[x^2-1,Extension->1.4]","unsupported_factor_extension"),
            ("Factor[x^2-1,Extension->Automatic]","unsupported_factor_extension"),
            ("Factor[x^2-1,Extension->{}]","unsupported_factor_extension"),
            ("Factor[Sin[x],Extension->Sqrt[2]]","unsupported_factor_expression"),
        ]
        for source,code in cases:
            with self.subTest(source=source):
                response=self.request(source)
                self.assertFalse(response["ok"],response)
                self.assertEqual(code,response["error"]["code"])

    def test_extension_remains_available_after_reset(self):
        response=self.kernel.dispatch({"id":1,"op":"reset","notebook_id":self.notebook})
        self.assertTrue(response["ok"],response)
        result=self.evaluate("Factor[x^4+1,Extension->Sqrt[2]]")
        self.assertEqual(1,result["line"])
        self.assertNotIn("Factor[",result["text"])


if __name__ == "__main__":
    unittest.main()
