"""Graph builtins batch 2 (backend/graphs2.py), checked on real evaluator output.

Contracts follow Wolfram 15.0.1; every expected value here was confirmed
against the local Wolfram kernel (oracle/inputs-graphs2.txt in the RE
workspace).  Edge-list results are checked structurally because the app's
text form prints UndirectedEdge as <-> while Wolfram's InputForm does not.
"""

from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kernel import Kernel


_KERNEL = None


def _get_kernel():
    # Mathics 10 re-runs its builtin import on every Kernel() and that path is
    # flaky (intermittent IncompleteSyntaxError), so share one kernel for the
    # whole module; each test still gets a fresh session via its notebook id.
    global _KERNEL
    if _KERNEL is None:
        last = None
        for _ in range(5):
            try:
                _KERNEL = Kernel()
                break
            except Exception as exc:  # noqa: BLE001 - flaky re-init, retry
                last = exc
        else:
            raise last
    return _KERNEL


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = _get_kernel()

    def setUp(self):
        self.notebook = self.id()

    def evaluate(self, source):
        response = self.kernel.dispatch({"id": source, "op": "evaluate", "source": source, "notebook_id": self.notebook})
        self.assertTrue(response["ok"], response)
        return response["result"]

    def text(self, source):
        return self.evaluate(source)["text"]


class GraphStructureTests(_Base):
    def test_subgraph_induced_keeps_requested_order(self):
        self.assertEqual("{3, 2}", self.text("VertexList[Subgraph[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], {3, 2}]]"))
        self.assertEqual("1", self.text("EdgeCount[Subgraph[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], {1, 2}]]"))
        self.assertEqual("1", self.text("EdgeCount[Subgraph[Graph[{1 -> 2, 2 -> 3, 1 -> 3}], {1, 3}]]"))

    def test_neighborhood_graph_center_first(self):
        self.assertEqual("{2, 1, 3}", self.text("VertexList[NeighborhoodGraph[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}], 2]]"))
        self.assertEqual("{2, 1, 3, 4}", self.text("VertexList[NeighborhoodGraph[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}], 2, 2]]"))
        # directed: out-neighbors only
        self.assertEqual("1", self.text("EdgeCount[NeighborhoodGraph[Graph[{1 -> 2, 2 -> 3}], 1]]"))

    def test_union_intersection_difference(self):
        self.assertEqual("2", self.text("EdgeCount[GraphUnion[Graph[{1 <-> 2}], Graph[{1 <-> 2, 2 <-> 3}]]]"))
        self.assertEqual("{1, 2, 3, 4}", self.text("VertexList[GraphUnion[Graph[{1, 2, 3}, {1 <-> 2}], Graph[{3, 4}, {3 <-> 4}]]]"))
        self.assertEqual("2", self.text("EdgeCount[GraphUnion[Graph[{1 -> 2}], Graph[{2 -> 3}]]]"))
        self.assertEqual("1", self.text("EdgeCount[GraphIntersection[Graph[{1 <-> 2, 2 <-> 3}], Graph[{2 <-> 3}]]]"))
        # Wolfram keeps the union of the vertex lists
        self.assertEqual("{1, 2, 3}", self.text("VertexList[GraphIntersection[Graph[{1, 2, 3}, {1 <-> 2, 2 <-> 3}], Graph[{2, 3}, {2 <-> 3}]]]"))
        self.assertEqual("1", self.text("EdgeCount[GraphDifference[Graph[{1 <-> 2, 2 <-> 3}], Graph[{2 <-> 3}]]]"))
        self.assertEqual("{1, 2, 3}", self.text("VertexList[GraphDifference[Graph[{1, 2, 3}, {1 <-> 2, 2 <-> 3}], Graph[{2 <-> 3}]]]"))
        self.assertEqual("2", self.text("EdgeCount[GraphDifference[CompleteGraph[4], CycleGraph[4]]]"))

    def test_complement(self):
        self.assertEqual("{{0, 0, 1}, {0, 0, 0}, {1, 0, 0}}",
                         self.text("Normal[AdjacencyMatrix[GraphComplement[Graph[{1 <-> 2, 2 <-> 3}]]]]"))
        self.assertEqual("{1, 2, 3}", self.text("VertexList[GraphComplement[Graph[{1, 2, 3}, {1 <-> 2}]]]"))
        self.assertEqual("4", self.text("EdgeCount[GraphComplement[Graph[{1 -> 2, 2 -> 3}]]]"))
        self.assertEqual("0", self.text("EdgeCount[GraphComplement[CompleteGraph[4]]]"))

    def test_directed_undirected_conversion(self):
        self.assertEqual("4", self.text("EdgeCount[DirectedGraph[Graph[{1 <-> 2, 2 <-> 3}]]]"))
        self.assertEqual("True", self.text("DirectedGraphQ[DirectedGraph[Graph[{1 <-> 2}]]]"))
        self.assertEqual("2", self.text("EdgeCount[UndirectedGraph[Graph[{1 -> 2, 2 -> 1, 2 -> 3}]]]"))
        self.assertEqual("True", self.text("UndirectedGraphQ[UndirectedGraph[Graph[{1 -> 2}]]]"))

    def test_adjacency_graph(self):
        self.assertEqual("{1, 2}", self.text("VertexList[AdjacencyGraph[{{0, 1}, {1, 0}}]]"))
        self.assertEqual("{{0, 2}, {2, 0}}", self.text("Normal[AdjacencyMatrix[AdjacencyGraph[{{0, 2}, {2, 0}}]]]"))
        self.assertEqual("False", self.text("DirectedGraphQ[AdjacencyGraph[{{0, 1}, {1, 0}}]]"))
        self.assertEqual("True", self.text("DirectedGraphQ[AdjacencyGraph[{{0, 1}, {0, 0}}]]"))

    def test_incidence_matrix(self):
        self.assertEqual("{{-1, 0}, {1, -1}, {0, 1}}", self.text("Normal[IncidenceMatrix[Graph[{1 -> 2, 2 -> 3}]]]"))
        self.assertEqual("{{1, 0}, {1, 1}, {0, 1}}", self.text("Normal[IncidenceMatrix[Graph[{1 <-> 2, 2 <-> 3}]]]"))
        self.assertEqual("{{2}}", self.text("Normal[IncidenceMatrix[Graph[{1 <-> 1}]]]"))
        self.assertEqual("{{-2}}", self.text("Normal[IncidenceMatrix[Graph[{1 -> 1}]]]"))
        self.assertEqual("{{-1, -1}, {1, 1}}", self.text("Normal[IncidenceMatrix[Graph[{1 -> 2, 1 -> 2}]]]"))

    def test_kirchhoff_matrix(self):
        self.assertEqual("{{1, -1, 0}, {-1, 2, -1}, {0, -1, 1}}",
                         self.text("Normal[KirchhoffMatrix[Graph[{1 <-> 2, 2 <-> 3}]]]"))
        # directed: diagonal is in-degree + out-degree, adjacency keeps direction
        self.assertEqual("{{1, -1, 0}, {0, 2, -1}, {0, 0, 1}}",
                         self.text("Normal[KirchhoffMatrix[Graph[{1 -> 2, 2 -> 3}]]]"))
        self.assertEqual("{{1, -1}, {-1, 1}}", self.text("Normal[KirchhoffMatrix[Graph[{1 <-> 1, 1 <-> 2}]]]"))

    def test_line_graph(self):
        self.assertEqual("{1, 2}", self.text("VertexList[LineGraph[Graph[{1 <-> 2, 1 <-> 3}]]]"))
        self.assertEqual("{{0, 1}, {1, 0}}", self.text("Normal[AdjacencyMatrix[LineGraph[Graph[{1 <-> 2, 2 <-> 3}]]]]"))
        self.assertEqual("{{0, 1}, {0, 0}}", self.text("Normal[AdjacencyMatrix[LineGraph[Graph[{1 -> 2, 2 -> 3}]]]]"))
        self.assertEqual("3", self.text("EdgeCount[LineGraph[StarGraph[4]]]"))

    def test_edge_add_delete(self):
        self.assertEqual("2", self.text("EdgeCount[EdgeAdd[Graph[{1 <-> 2}], 1 <-> 2]]"))
        self.assertEqual("{1, 2, 3, 4}", self.text("VertexList[EdgeAdd[Graph[{1 <-> 2}], 3 -> 4]]"))
        self.assertEqual("1", self.text("EdgeCount[EdgeDelete[Graph[{1 <-> 2, 2 <-> 3}], 2 <-> 3]]"))
        # only one instance is removed from a multi-edge (Wolfram)
        self.assertEqual("1", self.text("EdgeCount[EdgeDelete[Graph[{1 <-> 2, 1 <-> 2}], 1 <-> 2]]"))
        self.assertEqual("{1, 2, 3}", self.text("VertexList[EdgeDelete[Graph[{1, 2, 3}, {1 <-> 2}], 1 <-> 2]]"))

    def test_vertex_add_delete(self):
        self.assertEqual("{{0, 1, 0}, {1, 0, 0}, {0, 0, 0}}",
                         self.text("Normal[AdjacencyMatrix[VertexAdd[Graph[{1 <-> 2}], 5]]]"))
        self.assertEqual("{a, b, c}", self.text("VertexList[VertexAdd[Graph[{a <-> b}], c]]"))
        self.assertEqual("0", self.text("EdgeCount[VertexDelete[Graph[{1 <-> 2, 2 <-> 3}], 2]]"))
        self.assertEqual("0", self.text("EdgeCount[VertexDelete[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], {1, 2}]]"))
        self.assertEqual("{a, c}", self.text("VertexList[VertexDelete[Graph[{a <-> b, b <-> c}], b]]"))

    def test_edge_contract(self):
        self.assertEqual("{1, 3}", self.text("VertexList[EdgeContract[Graph[{1 <-> 2, 2 <-> 3}], 1 <-> 2]]"))
        self.assertEqual("1", self.text("EdgeCount[EdgeContract[Graph[{1 <-> 2, 2 <-> 3}], 1 <-> 2]]"))
        # parallel edges merge after contraction
        self.assertEqual("{{0, 1}, {1, 0}}",
                         self.text("Normal[AdjacencyMatrix[EdgeContract[Graph[{1 <-> 2, 1 <-> 3, 2 <-> 3}], 1 <-> 2]]]"))

    def test_graph_power(self):
        self.assertEqual("5", self.text("EdgeCount[GraphPower[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}], 2]]"))
        self.assertEqual("10", self.text("EdgeCount[GraphPower[CycleGraph[5], 2]]"))
        self.assertEqual("{{0, 1, 1}, {0, 0, 1}, {0, 0, 0}}",
                         self.text("Normal[AdjacencyMatrix[GraphPower[Graph[{1 -> 2, 2 -> 3}], 2]]]"))

    def test_transitive_closure(self):
        self.assertEqual("3", self.text("EdgeCount[TransitiveClosureGraph[Graph[{1 -> 2, 2 -> 3}]]]"))
        self.assertEqual("{{0, 1, 1}, {0, 0, 1}, {0, 0, 0}}",
                         self.text("Normal[AdjacencyMatrix[TransitiveClosureGraph[Graph[{1 -> 2, 2 -> 3}]]]]"))
        self.assertEqual("2", self.text("EdgeCount[TransitiveClosureGraph[Graph[{1 <-> 2, 3 <-> 4}]]]"))


class GraphPredicateTests(_Base):
    def test_isomorphic(self):
        self.assertEqual("True", self.text("IsomorphicGraphQ[Graph[{1 <-> 2, 2 <-> 3}], Graph[{5 <-> 6, 6 <-> 7}]]"))
        self.assertEqual("True", self.text("IsomorphicGraphQ[CycleGraph[3], CompleteGraph[3]]"))
        self.assertEqual("True", self.text("IsomorphicGraphQ[HypercubeGraph[2], CycleGraph[4]]"))
        self.assertEqual("False", self.text("IsomorphicGraphQ[Graph[{1 -> 2}], Graph[{1 <-> 2}]]"))
        self.assertEqual("True", self.text("IsomorphicGraphQ[Graph[{1 <-> 2, 2 <-> 3}], Graph[{1 <-> 2, 1 <-> 3}]]"))

    def test_bipartite_planar(self):
        self.assertEqual("True", self.text("BipartiteGraphQ[CycleGraph[4]]"))
        self.assertEqual("False", self.text("BipartiteGraphQ[CycleGraph[3]]"))
        self.assertEqual("False", self.text("BipartiteGraphQ[Graph[{1 <-> 1}]]"))
        self.assertEqual("True", self.text("BipartiteGraphQ[CompleteGraph[{2, 3}]]"))
        self.assertEqual("False", self.text("PlanarGraphQ[CompleteGraph[5]]"))
        self.assertEqual("True", self.text("PlanarGraphQ[CompleteGraph[4]]"))
        self.assertEqual("False", self.text("PlanarGraphQ[CompleteGraph[{3, 3}]]"))
        self.assertEqual("True", self.text("PlanarGraphQ[CompleteGraph[{2, 3}]]"))

    def test_connectivity(self):
        self.assertEqual("3", self.text("VertexConnectivity[CompleteGraph[4]]"))
        self.assertEqual("1", self.text("VertexConnectivity[Graph[{1 <-> 2, 2 <-> 3, 1 <-> 3, 3 <-> 4}]]"))
        self.assertEqual("0", self.text("VertexConnectivity[Graph[{1 <-> 2, 3 <-> 4}]]"))
        self.assertEqual("2", self.text("VertexConnectivity[CycleGraph[4]]"))
        self.assertEqual("3", self.text("EdgeConnectivity[CompleteGraph[4]]"))
        self.assertEqual("1", self.text("EdgeConnectivity[Graph[{1 <-> 2, 2 <-> 3}]]"))
        # parallel edges count (Wolfram)
        self.assertEqual("2", self.text("EdgeConnectivity[Graph[{1 <-> 2, 1 <-> 2}]]"))
        self.assertEqual("0", self.text("EdgeConnectivity[Graph[{1 <-> 2, 3 <-> 4}]]"))

    def test_chromatic_polynomial(self):
        self.assertEqual("2 x - 3 x ^ 2 + x ^ 3",
                         self.text("ChromaticPolynomial[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], x]"))
        self.assertEqual("-3 x + 6 x ^ 2 - 4 x ^ 3 + x ^ 4",
                         self.text("ChromaticPolynomial[CycleGraph[4], x]"))
        self.assertEqual("x ^ 2 - 2 x ^ 3 + x ^ 4",
                         self.text("ChromaticPolynomial[Graph[{1 <-> 2, 3 <-> 4}], x]"))
        self.assertEqual("24", self.text("ChromaticPolynomial[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], 4]"))
        self.assertEqual("0", self.text("ChromaticPolynomial[Graph[{1 <-> 1, 1 <-> 2}], x]"))

    def test_tutte_polynomial(self):
        self.assertEqual("x + x ^ 2 + y", self.text("TuttePolynomial[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], {x, y}]"))
        self.assertEqual("x ^ 2", self.text("TuttePolynomial[Graph[{1 <-> 2, 2 <-> 3}], {x, y}]"))
        self.assertEqual("x + x ^ 2 + x ^ 3 + y",
                         self.text("TuttePolynomial[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4, 1 <-> 4}], {x, y}]"))
        self.assertEqual("17", self.text("TuttePolynomial[CycleGraph[4], {2, 3}]"))
        self.assertEqual("x y", self.text("TuttePolynomial[Graph[{1 <-> 1, 1 <-> 2}], {x, y}]"))


class GraphOptimizationTests(_Base):
    def test_find_clique(self):
        self.assertEqual("{{1, 2, 3}}", self.text("FindClique[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]"))
        self.assertEqual("{{1, 3}}", self.text("FindClique[CompleteGraph[{2, 3}]]"))
        self.assertEqual("{{1, 2}}", self.text("FindClique[Graph[{1 <-> 2, 3 <-> 4}]]"))
        self.assertEqual("2", self.text("Length[First[FindClique[CycleGraph[5]]]]"))

    def test_find_vertex_cover(self):
        self.assertEqual("{2}", self.text("FindVertexCover[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{1, 3}", self.text("FindVertexCover[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]"))
        self.assertEqual("{1}", self.text("FindVertexCover[StarGraph[4]]"))
        self.assertEqual("3", self.text("Length[FindVertexCover[CycleGraph[5]]]"))

    def test_find_independent_vertex_set(self):
        self.assertEqual("{{1, 3}}", self.text("FindIndependentVertexSet[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{{3, 4, 5}}", self.text("FindIndependentVertexSet[CompleteGraph[{2, 3}]]"))
        self.assertEqual("3", self.text("Length[First[FindIndependentVertexSet[CycleGraph[6]]]]"))

    def test_find_independent_edge_set(self):
        matching = self.text("FindIndependentEdgeSet[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}]]")
        self.assertEqual(2, matching.count("↔"), matching)
        self.assertEqual("{True, True}",
                         self.text("Map[EdgeQ[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}], #] &, "
                                   "FindIndependentEdgeSet[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}]]]"))
        self.assertEqual("2", self.text("Length[FindIndependentEdgeSet[CycleGraph[5]]]"))
        self.assertEqual("2", self.text("Length[FindIndependentEdgeSet[CompleteGraph[4]]]"))

    def test_maximum_flow(self):
        self.assertEqual("2", self.text("FindMaximumFlow[Graph[{1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4}], 1, 4]"))
        self.assertEqual("2", self.text("FindMaximumFlow[Graph[{1 <-> 2, 1 <-> 3, 2 <-> 4, 3 <-> 4}], 1, 4]"))
        # Wolfram treats the graph as simple: parallel edges add no capacity
        self.assertEqual("1", self.text("FindMaximumFlow[Graph[{1 -> 2, 1 -> 2, 2 -> 3}], 1, 3]"))
        self.assertEqual("2", self.text("FindMaximumFlow[Graph[{1 -> 2, 2 -> 3, 1 -> 3}], 1, 3]"))

    def test_minimum_cut(self):
        self.assertEqual("{1, {{4}, {1, 2, 3}}}",
                         self.text("FindMinimumCut[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]"))
        self.assertEqual("{1, {{3}, {1, 2}}}", self.text("FindMinimumCut[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{3, {{4}, {1, 2, 3}}}", self.text("FindMinimumCut[CompleteGraph[4]]"))
        # the s-t form and directed graphs stay unevaluated in Wolfram 15
        self.assertTrue(self.text("FindMinimumCut[Graph[{1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4}], 1, 4]").startswith("FindMinimumCut["))

    def test_find_path(self):
        # Wolfram's choice is depth-first, not shortest
        self.assertEqual("{{1, 2, 3}}", self.text("FindPath[Graph[{1 <-> 2, 2 <-> 3, 1 <-> 3}], 1, 3]"))
        self.assertEqual("{}", self.text("FindPath[Graph[{1 <-> 2, 3 <-> 4}], 1, 4]"))
        self.assertEqual("{{1, 3, 4}}", self.text("FindPath[Graph[{1 <-> 3, 1 <-> 2, 2 <-> 4, 3 <-> 4}], 1, 4]"))
        self.assertEqual("{}", self.text("FindPath[Graph[{1 -> 2, 2 -> 3}], 3, 1]"))

    def test_find_cycle(self):
        self.assertEqual("3", self.text("Length[First[FindCycle[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]]]"))
        self.assertEqual("{}", self.text("FindCycle[Graph[{1 <-> 2, 3 <-> 4}]]"))
        self.assertEqual("{}", self.text("FindCycle[Graph[{1 -> 2, 2 -> 3}]]"))
        self.assertEqual("2", self.text("Length[First[FindCycle[Graph[{1 -> 2, 2 -> 1}]]]]"))


class GraphCentralityTests(_Base):
    def test_degree(self):
        self.assertEqual("{1, 2, 1}", self.text("DegreeCentrality[Graph[{1 <-> 2, 2 <-> 3}]]"))
        self.assertEqual("{1, 2, 1}", self.text("DegreeCentrality[Graph[{1 -> 2, 2 -> 3}]]"))
        self.assertEqual("{3, 1, 1, 1}", self.text("DegreeCentrality[StarGraph[4]]"))

    def test_betweenness(self):
        self.assertEqual("{0., 2., 2., 0.}", self.text("BetweennessCentrality[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}]]"))
        self.assertEqual("{0., 2., 2., 0.}", self.text("BetweennessCentrality[Graph[{1 -> 2, 2 -> 3, 3 -> 4}]]"))
        self.assertEqual("{3., 0., 0., 0.}", self.text("BetweennessCentrality[StarGraph[4]]"))

    def test_closeness(self):
        self.assertEqual("{666667, 1000000, 666667}",
                         self.text("Round[1000000 ClosenessCentrality[Graph[{1 <-> 2, 2 <-> 3}]]]"))
        self.assertEqual("{666667, 1000000, 0}",
                         self.text("Round[1000000 ClosenessCentrality[Graph[{1 -> 2, 2 -> 3}]]]"))
        # disconnected: reachable count over distance sum (Wolfram)
        self.assertEqual("{1000000, 1000000, 1000000, 1000000}",
                         self.text("Round[1000000 ClosenessCentrality[Graph[{1 <-> 2, 3 <-> 4}]]]"))

    def test_eigenvector(self):
        # normalized so the components sum to 1 (Wolfram)
        self.assertEqual("{292893, 414214, 292893}",
                         self.text("Round[1000000 EigenvectorCentrality[Graph[{1 <-> 2, 2 <-> 3}]]]"))
        self.assertEqual("{269594, 269594, 315449, 145362}",
                         self.text("Round[1000000 EigenvectorCentrality[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]]"))

    def test_pagerank(self):
        self.assertEqual("{333333, 333333, 333333}",
                         self.text("Round[1000000 PageRankCentrality[Graph[{1 -> 2, 2 -> 3, 3 -> 1}]]]"))
        self.assertEqual("{500000, 500000}", self.text("Round[1000000 PageRankCentrality[Graph[{1 -> 2, 2 -> 1}]]]"))
        self.assertEqual("1", self.text("Round[Total[PageRankCentrality[Graph[{1 -> 2, 2 -> 3}]]]]"))


class NamedGraphTests(_Base):
    def test_complete(self):
        self.assertEqual("10", self.text("EdgeCount[CompleteGraph[5]]"))
        self.assertEqual("{{0, 0, 1, 1, 1}, {0, 0, 1, 1, 1}, {1, 1, 0, 0, 0}, {1, 1, 0, 0, 0}, {1, 1, 0, 0, 0}}",
                         self.text("Normal[AdjacencyMatrix[CompleteGraph[{2, 3}]]]"))
        self.assertEqual("12", self.text("EdgeCount[CompleteGraph[{2, 2, 2}]]"))

    def test_cycle_path(self):
        self.assertEqual("{1, 2, 3, 4}", self.text("VertexList[CycleGraph[4]]"))
        self.assertEqual("4", self.text("EdgeCount[CycleGraph[4]]"))
        self.assertEqual("{a, b, c}", self.text("VertexList[PathGraph[{a, b, c}]]"))
        self.assertEqual("3", self.text("EdgeCount[PathGraph[{1, 2, 3, 4}]]"))
        # Wolfram has no integer form: PathGraph[3] is not a graph there
        self.assertEqual("PathGraph[3]", self.text("PathGraph[3]"))

    def test_star_wheel(self):
        self.assertEqual("{{0, 1, 1, 1}, {1, 0, 0, 0}, {1, 0, 0, 0}, {1, 0, 0, 0}}",
                         self.text("Normal[AdjacencyMatrix[StarGraph[4]]]"))
        self.assertEqual("{{0, 1, 1, 1}, {1, 0, 1, 1}, {1, 1, 0, 1}, {1, 1, 1, 0}}",
                         self.text("Normal[AdjacencyMatrix[WheelGraph[4]]]"))
        self.assertEqual("8", self.text("EdgeCount[WheelGraph[5]]"))

    def test_grid_hypercube(self):
        # GridGraph labels run fastest along the first dimension
        self.assertEqual("{{0, 1, 1, 0, 0, 0}, {1, 0, 0, 1, 0, 0}, {1, 0, 0, 1, 1, 0}, "
                         "{0, 1, 1, 0, 0, 1}, {0, 0, 1, 0, 0, 1}, {0, 0, 0, 1, 1, 0}}",
                         self.text("Normal[AdjacencyMatrix[GridGraph[{2, 3}]]]"))
        self.assertEqual("12", self.text("EdgeCount[GridGraph[{3, 3}]]"))
        self.assertEqual("{{0, 1, 1, 0}, {1, 0, 0, 1}, {1, 0, 0, 1}, {0, 1, 1, 0}}",
                         self.text("Normal[AdjacencyMatrix[HypercubeGraph[2]]]"))
        self.assertEqual("12", self.text("EdgeCount[HypercubeGraph[3]]"))


if __name__ == "__main__":
    unittest.main()
