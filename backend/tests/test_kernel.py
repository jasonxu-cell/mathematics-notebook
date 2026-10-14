"""Integration tests against the pinned Mathics engine, without mocks."""

import json
from pathlib import Path
import subprocess
import sys
import unittest


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


class KernelEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel()

    def evaluate(self, source, notebook="test"):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def test_factor(self):
        result = self.evaluate("Factor[x^2 - 1]")
        self.assertIn("(-1 + x)", result["text"])
        self.assertIn("(1 + x)", result["text"])

    def test_solve(self):
        result = self.evaluate("Solve[x^2 == 4, x]")
        self.assertRegex(result["text"], r"x\s+[⇾→]\s+-2")
        self.assertRegex(result["text"], r"x\s+[⇾→]\s+2")

    def test_derivative(self):
        result = self.evaluate("D[x^3, x]")
        self.assertEqual("3x^2", result["text"].replace(" ", ""))
        self.assertIn("latex", result)

    def test_integral(self):
        result = self.evaluate("Integrate[2 x, x]")
        self.assertEqual("x^2", result["text"].replace(" ", ""))

    def test_persistent_variables_and_notebook_isolation(self):
        self.evaluate("remembered = 17", "persistent")
        result = self.evaluate("remembered + 4", "persistent")
        self.assertEqual("21", result["text"])
        self.assertEqual(2, result["line"])
        other = self.evaluate("remembered", "isolated")
        self.assertEqual("remembered", other["text"])

    def test_in_out_history(self):
        self.evaluate("5 + 6", "history")
        result = self.evaluate("% + 1", "history")
        self.assertEqual("12", result["text"])
        self.assertEqual(2, result["line"])

    def test_print_and_semicolon(self):
        result = self.evaluate('Print["hello"]; 2 + 2;', "print")
        self.assertEqual(["hello"], result["prints"])
        self.assertTrue(result["suppressed"])
        self.assertEqual("", result["text"])
        self.assertNotIn("latex", result)

    def test_reset(self):
        self.evaluate("remembered = 8", "reset")
        response = self.kernel.dispatch({"id": 9, "op": "reset", "notebook_id": "reset"})
        self.assertTrue(response["ok"], response)
        result = self.evaluate("remembered", "reset")
        self.assertEqual("remembered", result["text"])
        self.assertEqual(1, result["line"])

    def test_invalid_syntax_is_an_error(self):
        response = self.kernel.dispatch({"id": 10, "op": "evaluate", "source": "Factor[", "notebook_id": "syntax"})
        self.assertFalse(response["ok"], response)
        self.assertEqual("syntax_error", response["error"]["code"])
        self.assertTrue(response["error"]["message"])

    def test_evaluation_messages_are_preserved(self):
        result = self.evaluate("1 / 0")
        self.assertTrue(result["messages"])
        self.assertIn("Infinite expression", result["messages"][0]["text"])

    def test_plot_produces_svg(self):
        result = self.evaluate("Plot[Sin[x], {x, 0, 2 Pi}]")
        self.assertIn("svg", result, result)
        self.assertIn("<svg", result["svg"])
        self.assertIn("</svg>", result["svg"])
        self.assertNotIn("Display conversion failed", str(result["messages"]))

    def test_bad_request_is_rejected(self):
        response = self.kernel.dispatch({"id": 12, "op": "evaluate", "source": 25})
        self.assertFalse(response["ok"])
        self.assertEqual("invalid_source", response["error"]["code"])


class ProtocolTests(unittest.TestCase):
    def test_stdout_contains_only_json_lines(self):
        requests = [
            {"id": 1, "op": "evaluate", "source": 'Print["protocol"]; 9 + 1', "notebook_id": "protocol"},
            {"id": 2, "op": "health"},
        ]
        process = subprocess.run(
            [sys.executable, str(BACKEND / "kernel.py")],
            input="\n".join(json.dumps(request) for request in requests) + "\n",
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(0, process.returncode, process.stderr)
        messages = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(3, len(messages))
        self.assertEqual("ready", messages[0]["event"])
        self.assertEqual("10.0.1", messages[0]["version"])
        self.assertEqual("10", messages[1]["result"]["text"])
        self.assertEqual(["protocol"], messages[1]["result"]["prints"])
        self.assertTrue(messages[2]["ok"])


if __name__ == "__main__":
    unittest.main()
