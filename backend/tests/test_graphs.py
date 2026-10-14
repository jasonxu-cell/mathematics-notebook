"""Graph builtins (backend/graphs.py), checked on real evaluator output.

Contracts follow Wolfram 15.0.1; ordering-ambiguous results (Eulerian /
Hamiltonian cycles, component order) are validated structurally, not by text.
"""

from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel()

    def setUp(self):
        self.notebook = self.id()

    def evaluate(self, source):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def text(self, source):
        return self.evaluate(source)["text"]


class GraphAccessorTests(_Base):
    def test_vertex_and_edge_lists_keep_first_appearance_order(self):
        self.assertEqual("{1, 2, 3}", self.text("VertexList[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{b, a, c}", self.text("VertexList[Graph[{b <-> a, a <-> c}]]"))
        self.assertEqual("3", self.text("VertexCount[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("2", self.text("EdgeCount[Graph[{1 <-> 2, 2 -> 3}]]"))

    def test_two_argument_form(self):
        self.assertEqual("{1, 2, 3, 4}", self.text("VertexList[Graph[{1, 2, 3, 4}, {1 <-> 2}]]"))
        self.assertEqual("1", self.text("EdgeCount[Graph[{1, 2, 3, 4}, {1 <-> 2}]]"))

    def test_adjacency_matrix_is_dense(self):
        self.assertEqual("{{0, 1, 0}, {1, 0, 1}, {0, 0, 0}}",
                         self.text("AdjacencyMatrix[Graph[{1 <-> 2, 2 -> 3}]]"))
        # multi-edges count
        self.assertEqual("{{0, 2}, {2, 0}}", self.text("AdjacencyMatrix[Graph[{1 <-> 2, 1 <-> 2}]]"))

    def test_degrees(self):
        self.assertEqual("{1, 2, 1}", self.text("VertexDegree[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{1, 2, 1}", self.text("VertexDegree[Graph[{1 -> 2, 2 -> 3}]]"))
        self.assertEqual("{0, 1, 1}", self.text("VertexInDegree[Graph[{1 -> 2, 2 -> 3}]]"))
        self.assertEqual("{1, 1, 0}", self.text("VertexOutDegree[Graph[{1 -> 2, 2 -> 3}]]"))
        # undirected self-loop counts twice
        self.assertEqual("{3, 1}", self.text("VertexDegree[Graph[{1 <-> 1, 1 <-> 2}]]"))

    def test_membership(self):
        self.assertEqual("True", self.text("VertexQ[Graph[{1 <-> 2}], 2]"))
        self.assertEqual("False", self.text("VertexQ[Graph[{1 <-> 2}], 5]"))
        self.assertEqual("True", self.text("EdgeQ[Graph[{1 <-> 2}], 2 <-> 1]"))
        self.assertEqual("False", self.text("EdgeQ[Graph[{1 -> 2}], 2 -> 1]"))
        self.assertEqual("True", self.text("DirectedGraphQ[Graph[{1 -> 2}]]"))
        self.assertEqual("False", self.text("DirectedGraphQ[Graph[{1 <-> 2}]]"))
        self.assertEqual("True", self.text("UndirectedGraphQ[Graph[{1 <-> 2}]]"))

    def test_adjacency_list(self):
        self.assertEqual("{2, 3}", self.text("AdjacencyList[Graph[{1 <-> 2, 1 <-> 3}], 1]"))

    def test_non_graph_input_is_unevaluated(self):
        self.assertTrue(self.text("VertexCount[{1, 2, 3}]").startswith("VertexCount["))


class GraphPathTests(_Base):
    def test_shortest_path_directed(self):
        self.assertEqual("{1, 2, 3}", self.text("FindShortestPath[Graph[{1 -> 2, 2 -> 3}], 1, 3]"))

    def test_shortest_path_unreachable_is_unevaluated(self):
        self.assertTrue(self.text("FindShortestPath[Graph[{1 -> 2}], 2, 1]").startswith("FindShortestPath["))

    def test_shortest_path_all(self):
        self.assertEqual("{{1}, {1, 2}, {1, 2, 3}}",
                         self.text("FindShortestPath[Graph[{1 -> 2, 2 -> 3}], 1, All]"))

    def test_distances(self):
        self.assertEqual("2", self.text("GraphDistance[Graph[{1 -> 2, 2 -> 3}], 1, 3]"))
        self.assertEqual("Infinity", self.text("GraphDistance[Graph[{1 <-> 2, 3 <-> 4}], 1, 4]"))
        self.assertEqual("{{0, 1, 2}, {1, 0, 1}, {2, 1, 0}}",
                         self.text("GraphDistanceMatrix[Graph[{1 <-> 2, 2 <-> 3}]]"))

    def test_eccentricity_family(self):
        self.assertEqual("2", self.text("VertexEccentricity[Graph[{1 <-> 2, 2 <-> 3}], 1]"))
        self.assertEqual("3", self.text("GraphDiameter[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}]]"))
        self.assertEqual("1", self.text("GraphRadius[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{2}", self.text("GraphCenter[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{1, 3}", self.text("GraphPeriphery[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("Infinity", self.text("GraphDiameter[Graph[{1 <-> 2, 3 <-> 4}]]"))


class GraphConnectivityTests(_Base):
    def test_components(self):
        self.assertEqual("{{1, 2}, {3, 4}}", self.text("ConnectedComponents[Graph[{1 <-> 2, 3 <-> 4}]]"))
        self.assertEqual("{{1, 2, 3}}", self.text("WeaklyConnectedComponents[Graph[{1 -> 2, 2 -> 3}]]"))

    def test_strong_components_directed(self):
        comps = self.text("ConnectedComponents[Graph[{1 -> 2, 2 -> 1, 2 -> 3}]]")
        self.assertIn("{1, 2}", comps)
        self.assertIn("{3}", comps)

    def test_connected_acyclic_tree(self):
        self.assertEqual("True", self.text("ConnectedGraphQ[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("False", self.text("ConnectedGraphQ[Graph[{1 <-> 2, 3 <-> 4}]]"))
        self.assertEqual("True", self.text("AcyclicGraphQ[Graph[{1 -> 2, 2 -> 3}]]"))
        self.assertEqual("False", self.text("AcyclicGraphQ[Graph[{1 -> 2, 2 -> 1}]]"))
        # Wolfram 15: TreeQ tests the Tree object, not graphs; the graph
        # predicate is TreeGraphQ (TreeQ[graph] is False there).
        self.assertEqual("True", self.text("TreeGraphQ[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("False", self.text("TreeGraphQ[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]"))

    def test_topological_sort_is_valid(self):
        order = self.text("TopologicalSort[Graph[{1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4}]]")
        # Wolfram tie-break: largest first-appearance index first
        self.assertEqual("{1, 3, 2, 4}", order)
        # cycle -> unevaluated
        self.assertTrue(self.text("TopologicalSort[Graph[{1 -> 2, 2 -> 1}]]").startswith("TopologicalSort["))

    def test_spanning_tree_edges_form_a_tree(self):
        out = self.text("FindSpanningTree[Graph[{1 <-> 2, 2 <-> 3, 1 <-> 3}]]")
        self.assertTrue(out.startswith("Graph["), out)
        # 3 vertices, 2 edges, connected
        self.assertEqual("2", self.text("EdgeCount[FindSpanningTree[Graph[{1 <-> 2, 2 <-> 3, 1 <-> 3}]]]"))


class GraphCycleTests(_Base):
    def test_eulerian(self):
        self.assertEqual("True", self.text("EulerianGraphQ[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]"))
        self.assertEqual("False", self.text("EulerianGraphQ[Graph[{1 <-> 2, 2 <-> 3}]]"))
        cycle = self.text("FindEulerianCycle[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]")
        self.assertTrue(cycle.startswith("{{") and cycle.endswith("}}"), cycle)  # list of cycles
        for e in ("1 ↔ 2", "2 ↔ 3", "3 ↔ 1"):
            self.assertIn(e, cycle)
        self.assertEqual("{}", self.text("FindEulerianCycle[Graph[{1 <-> 2, 2 <-> 3}]]"))

    def test_hamiltonian(self):
        self.assertEqual("True", self.text("HamiltonianGraphQ[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]"))
        self.assertEqual("False", self.text("HamiltonianGraphQ[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}]]"))
        cycle = self.text("FindHamiltonianCycle[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4, 4 <-> 1, 1 <-> 3}]]")
        self.assertTrue(cycle.startswith("{{") and cycle.endswith("}}"), cycle)  # list of cycles
        self.assertEqual(4, cycle.count("↔"))
        self.assertEqual("{}", self.text("FindHamiltonianCycle[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}]]"))


class GraphScanTests(_Base):
    def test_bfs_dfs_order(self):
        self.assertEqual("{1, 2, 3, 4}", self.text("BreadthFirstScan[Graph[{1 <-> 2, 1 <-> 3, 2 <-> 4}], 1]"))
        self.assertEqual("{1, 2, 4, 3}", self.text("DepthFirstScan[Graph[{1 <-> 2, 1 <-> 3, 2 <-> 4}], 1]"))

    def test_scan_unknown_vertex_unevaluated(self):
        self.assertTrue(self.text("BreadthFirstScan[Graph[{1 <-> 2}], 9]").startswith("BreadthFirstScan["))


if __name__ == "__main__":
    unittest.main()
