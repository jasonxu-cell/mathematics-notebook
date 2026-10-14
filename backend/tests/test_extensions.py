"""Actual Mathics evaluations for mesh output and held numeric controls."""

import json
from pathlib import Path
import sys
import unittest


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel()

    def setUp(self):
        self.notebook = self.id()

    def request(self, source, controls=None):
        request = {"id": 1, "op": "evaluate", "source": source, "notebook_id": self.notebook}
        if controls is not None:
            request["controls"] = controls
        return self.kernel.dispatch(request)

    def evaluate(self, source, controls=None):
        response = self.request(source, controls)
        self.assertTrue(response["ok"], response)
        return response["result"]

    def assert_geometry_valid(self, geometry):
        self.assertEqual("data", geometry["coordinateSpace"])
        json.dumps(geometry, allow_nan=False)
        for face in geometry["faces"]:
            self.assertGreaterEqual(len(face), 3)
            self.assertTrue(all(0 <= index < len(geometry["vertices"]) for index in face))
        for kind in ("faces", "lines", "points"):
            self.assertEqual(len(geometry[kind]), len(geometry["colors"][kind]))
        self.assertEqual(3, len(geometry["bounds"]))

    def test_graphics3d_coordinates_and_colors(self):
        result = self.evaluate("Graphics3D[{Red,Polygon[{{0,0,0},{2,0,0},{0,3,4}}],Blue,Line[{{0,0,0},{1,2,3}}],Green,Point[{2,3,4}]}]")
        geometry = result["graphics3d"]
        self.assert_geometry_valid(geometry)
        self.assertEqual([[0,0,0],[2,0,0],[0,3,4]], geometry["vertices"])
        self.assertEqual([[0,1,2]], geometry["faces"])
        self.assertEqual([[[0,0,0],[1,2,3]]], geometry["lines"])
        self.assertEqual([[2,3,4]], geometry["points"])
        self.assertEqual([[1,0,0]], geometry["colors"]["faces"])
        self.assertEqual([[0,0,1]], geometry["colors"]["lines"])
        self.assertEqual([[0,1,0]], geometry["colors"]["points"])

    def test_sphere_cuboid_tessellation(self):
        geometry = self.evaluate("Graphics3D[{Red,Sphere[{0,0,0},2],Blue,Cuboid[{3,3,3},{4,4,4}]}]")["graphics3d"]
        self.assert_geometry_valid(geometry)
        self.assertEqual(294, len(geometry["faces"]))
        self.assertEqual([[-2,4],[-2,4],[-2,4]], geometry["bounds"])
        sphere_vertices = {index for face in geometry["faces"][:288] for index in face}
        for index in sphere_vertices:
            self.assertAlmostEqual(4, sum(value * value for value in geometry["vertices"][index]), places=10)

    def test_cylinder_and_cone_tessellation(self):
        geometry = self.evaluate("Graphics3D[{Cylinder[{{0,0,0},{0,0,2}},1],Cone[{{3,0,0},{3,0,2}},1]}]")["graphics3d"]
        self.assert_geometry_valid(geometry)
        self.assertEqual(51, len(geometry["faces"]))

    def test_plot3d_uses_actual_unscaled_surface(self):
        geometry = self.evaluate("Plot3D[x y,{x,-1,1},{y,-1,1},PlotPoints->3,MaxRecursion->0]")["graphics3d"]
        self.assert_geometry_valid(geometry)
        self.assertGreater(len(geometry["faces"]), 0)
        self.assertGreater(len(geometry["lines"]), 0)
        for x, y, z in geometry["vertices"]:
            self.assertAlmostEqual(x*y, z, places=10)
        self.assertEqual([[-1,1],[-1,1],[-1,1]], geometry["bounds"])

    def test_initial_value_update_and_global_isolation(self):
        self.evaluate("a = 99")
        source = "Manipulate[a^2,{a,0,5}]"
        initial = self.evaluate(source)
        self.assertEqual("0", initial["text"])
        self.assertEqual(0, initial["interactive"]["controls"][0]["value"])
        changed = self.evaluate(source, {"a":3})
        self.assertEqual("9", changed["text"])
        self.assertEqual(3, changed["interactive"]["controls"][0]["value"])
        self.assertEqual("99", self.evaluate("a")["text"])

    def test_multiple_labeled_stepped_controls(self):
        source = 'Manipulate[a+b,{{a,2,"First"},0,4,1},{{b,1,"Second"},0,3,1}]'
        initial = self.evaluate(source)
        self.assertEqual("3", initial["text"])
        controls = initial["interactive"]["controls"]
        self.assertEqual(["First","Second"], [control["label"] for control in controls])
        changed = self.evaluate(source, {"a":4,"b":2})
        self.assertEqual("6", changed["text"])
        self.assertEqual("a + b", self.evaluate("a+b")["text"])

    def test_numeric_constants_in_ranges(self):
        result = self.evaluate("Manipulate[N[a],{{a,Pi},0,2 Pi}]", {"a":2})
        self.assertEqual("2.", result["text"])
        self.assertAlmostEqual(6.283185307179586, result["interactive"]["controls"][0]["max"])

    def test_manipulate_svg_changes_without_parameter_leak(self):
        source = "Manipulate[Plot[a x,{x,0,1},PlotRange->{0,3}],{a,0,3}]"
        first = self.evaluate(source, {"a":1})
        second = self.evaluate(source, {"a":2})
        self.assertIn("<svg", first["svg"])
        self.assertNotEqual(first["svg"], second["svg"])
        self.assertEqual("a", self.evaluate("a")["text"])

    def test_manipulate_held_graphics_coordinates(self):
        source = "Manipulate[Graphics3D[Point[{a,0,0}]],{a,0,5}]"
        first = self.evaluate(source, {"a":2})
        second = self.evaluate(source, {"a":4})
        self.assertEqual([[2,0,0]], first["graphics3d"]["points"])
        self.assertEqual([[4,0,0]], second["graphics3d"]["points"])
        self.assertIn("interactive", second)
        self.assertEqual("a", self.evaluate("a")["text"])

    def test_graphics_coordinate_effects_execute_once(self):
        self.evaluate("counter=0")
        result = self.evaluate("Manipulate[Graphics3D[Point[{counter++,a,0}]],{a,0,5}]", {"a":2})
        self.assertEqual([[0,2,0]], result["graphics3d"]["points"])
        self.assertEqual("1", self.evaluate("counter")["text"])

    def test_abort_restores_controls(self):
        self.evaluate("a=99")
        result = self.evaluate("Manipulate[Abort[],{a,0,5}]", {"a":2})
        self.assertEqual("$Aborted", result["text"])
        self.assertEqual("99", self.evaluate("a")["text"])

    def test_manipulate_plot3d_changes_real_samples(self):
        source = "Manipulate[Plot3D[a x y,{x,-1,1},{y,-1,1},PlotPoints->3,MaxRecursion->0],{a,1,3}]"
        first = self.evaluate(source, {"a":1})["graphics3d"]
        second = self.evaluate(source, {"a":3})["graphics3d"]
        self.assertNotEqual(first["vertices"], second["vertices"])
        for x, y, z in second["vertices"]:
            self.assertAlmostEqual(3*x*y, z, places=10)

    def test_effects_execute_once_per_request_and_history(self):
        self.evaluate("counter=0")
        source = 'Manipulate[(counter++;Print["once"];a^2),{a,0,5}]'
        result = self.evaluate(source, {"a":3})
        self.assertEqual("9", result["text"])
        self.assertEqual(["once"], result["prints"])
        self.assertEqual(2, result["line"])
        self.assertEqual("10", self.evaluate("%+1")["text"])
        self.assertEqual("1", self.evaluate("counter")["text"])
        # Inspect the stored input AST without asking the evaluator to execute
        # the original input again, as In[n] normally does.
        definitions = self.kernel.sessions[self.notebook].definitions
        stored = definitions.get_definition("System`In").downvalues
        self.assertTrue(any(rule.replace.get_head_name().endswith("`Manipulate") for rule in stored))

    def test_semicolon_suppresses_interactive_output(self):
        self.evaluate("counter=0")
        result = self.evaluate("Manipulate[(counter++;a^2),{a,0,5}];", {"a":3})
        self.assertEqual("", result["text"])
        self.assertTrue(result["suppressed"])
        self.assertNotIn("interactive", result)
        self.assertNotIn("graphics3d", result)
        self.assertEqual(2, result["line"])
        self.assertEqual("9", self.evaluate("Out[2]")["text"])
        self.assertEqual("1", self.evaluate("counter")["text"])

    def test_invalid_controls_and_options_never_execute_body(self):
        self.evaluate("counter=0")
        cases = [
            ("Manipulate[counter++,{a,1,1}]", None),
            ("Manipulate[counter++,{a,0,5},AppearanceElements->None]", None),
            ("Manipulate[counter++,{{a,0},0,5,1}]", {"a":1.5}),
            ("Manipulate[counter++,{a,0,5}]", {"a":6}),
            ("Manipulate[counter++,{a,0,5}]", {"a":True}),
            ("Manipulate[counter++,{a,0,5}]", {"a":"2"}),
            ("Manipulate[counter++,{a,0,5}]", {"a":float("inf")}),
            ("Manipulate[counter++,{a,0,5}]", {"missing":1}),
            ("Manipulate[counter++,{a,0,b}]", None),
            ("Manipulate[counter++,{a,(counter++),5}]", None),
            ("Manipulate[Manipulate[counter++,{b,0,5}],{a,0,5}]", None),
            ("1+Manipulate[counter++,{a,0,5}]", None),
            ("a^2", {"a":2}),
        ]
        for source, controls in cases:
            with self.subTest(source=source, controls=controls):
                response = self.request(source, controls)
                self.assertFalse(response["ok"], response)
                self.assertIn(response["error"]["code"], {"invalid_controls","invalid_control","unsupported_control","unsupported_manipulate"})
        self.assertEqual("0", self.evaluate("counter")["text"])

    def test_protected_control_is_rejected(self):
        self.evaluate("a=8;Protect[a]")
        response = self.request("Manipulate[a^2,{a,0,5}]", {"a":2})
        self.assertFalse(response["ok"], response)
        self.assertEqual("invalid_control", response["error"]["code"])
        self.assertEqual("8", self.evaluate("a")["text"])

    def test_unsupported_graphics_restore_parameter(self):
        self.evaluate("a=9")
        response = self.request("Manipulate[Graphics3D[Arrow[{{0,0,0},{a,1,1}}]],{a,0,5}]", {"a":2})
        self.assertFalse(response["ok"], response)
        self.assertEqual("unsupported_graphics3d", response["error"]["code"])
        self.assertEqual("9", self.evaluate("a")["text"])


if __name__ == "__main__":
    unittest.main()
