"""Real-engine regressions for readable, exact-preserving Root solutions."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import sympy

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from algebraic_roots import DIGITS, solution_preview
from kernel import Kernel


class AlgebraicRootDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel()

    def setUp(self):
        self.notebook = self._testMethodName

    def evaluate(self, source):
        response = self.kernel.dispatch({"id": 1, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def test_fifth_and_tenth_degree_all_roots_keep_indices_and_small_residual(self):
        for degree in (5, 10):
            with self.subTest(degree=degree):
                result = self.evaluate(f"Solve[x^{degree}-5 x+6==0,x]")
                preview = result["algebraic_roots"]
                self.assertEqual(DIGITS, preview["digits"])
                self.assertEqual(degree, preview["total"])
                self.assertEqual(degree, len(preview["rows"]))
                self.assertIn("Root[", result["text"])
                self.assertIn(r"\text{Root}", result["latex"])
                session = self.kernel.sessions[self.notebook]
                exact = session.evaluation.last_eval
                roots = []
                for index, (row, display) in enumerate(zip(exact.elements, preview["rows"]), start=1):
                    root = row.elements[0].elements[1]
                    self.assertEqual(index, root.elements[1].get_int_value())
                    # Mathics' native conversion is independent of the display
                    # converter and documents its own Root index convention.
                    native = root.to_sympy()
                    self.assertEqual(index - 1, native.index)
                    number = native.eval_approx(DIGITS + 3)
                    roots.append(complex(number))
                    self.assertLess(abs(complex(number) ** degree - 5 * complex(number) + 6), 1e-10)
                    self.assertEqual("x " + r"\approx " + sympy.latex(number.evalf(DIGITS)), display["approximate_latex"])
                    self.assertEqual(session.evaluation.format_output(row, "latex"), display["exact_latex"])
                self.assertEqual(degree, len({(round(root.real, 9), round(root.imag, 9)) for root in roots}))

    def test_input_side_effect_once_and_out_remains_exact(self):
        self.evaluate("counter=0")
        result = self.evaluate('Solve[x^5-5 x+(counter++;Print["once"];6)==0,x]')
        self.assertEqual(["once"], result["prints"])
        self.assertEqual(5, result["algebraic_roots"]["total"])
        self.assertEqual("1", self.evaluate("counter")["text"])
        self.assertEqual("False", self.evaluate(f"FreeQ[Out[{result['line']}],_Root]")["text"])
        self.assertEqual("1", self.evaluate("counter")["text"])

    def test_unrelated_results_and_fake_root_are_not_interpreted(self):
        for source in (
            "Solve[x^2==4,x]", "{}", "{{}}", '"Root[#^5-5 #+6&,1]"',
            "{{x->Global`Root[6+#^5-5 #&,1]}}", "{{x->y}}",
            "Root[6+#^5-5 #&,1]", "Solve[x^5-5 x+6==0,x];",
        ):
            with self.subTest(source=source):
                self.assertNotIn("algebraic_roots", self.evaluate(source))

    def test_limits_and_formatting_failure_preserve_exact_fallback(self):
        result = self.evaluate("Solve[x^5-5 x+6==0,x]")
        session = self.kernel.sessions[self.notebook]
        exact = session.evaluation.last_eval
        with patch("algebraic_roots.MAX_DEGREE", 4):
            self.assertIsNone(solution_preview(exact, session.evaluation))
        with patch("algebraic_roots.MAX_ROOTS", 4):
            self.assertIsNone(solution_preview(exact, session.evaluation))
        with patch("algebraic_roots.MAX_PREVIEW_SECONDS", -1):
            self.assertIsNone(solution_preview(exact, session.evaluation))
        with patch.object(session.evaluation, "format_output", side_effect=ValueError("bad boxes")):
            self.assertIsNone(solution_preview(exact, session.evaluation))
        # Direct AST comparison detects accidental mutation independently of
        # any subsequent user input evaluation.
        self.assertEqual(result["latex"], session.evaluation.format_output(exact, "latex"))

    def test_multiple_rules_and_mixed_exact_numeric_solutions(self):
        result = self.evaluate("{{x->Root[6+#^5-5 #&,1], y->2}, {x->1,y->I}}")
        self.assertEqual(2, result["algebraic_roots"]["total"])
        self.assertIn(r",\quad y \approx", result["algebraic_roots"]["rows"][0]["approximate_latex"])
        self.assertIn("i", result["algebraic_roots"]["rows"][1]["approximate_latex"])


if __name__ == "__main__":
    unittest.main()
