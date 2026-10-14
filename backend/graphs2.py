"""Second batch of graph builtins, backed by networkx.

Contracts follow Wolfram 15.0.1 (reference.wolfram.com/language), checked by a
differential battery against the activated local kernel
(oracle/inputs-graphs2.txt in the RE workspace).

Graph representation is the one from backend/graphs.py: ``Graph`` stays an
inert head; each builtin parses it into ``_Graph`` and returns ``None``
(unevaluated) for malformed input.  networkx algorithms run on integer vertex
indices and results are mapped back to the original Mathics vertex
expressions, which may be arbitrary expressions.

Intentional deviations:
  * IncidenceMatrix / KirchhoffMatrix return dense nested Lists
    (Wolfram: SparseArray), matching graphs.py's AdjacencyMatrix choice.
  * ChromaticPolynomial / TuttePolynomial are evaluated by subset enumeration,
    so graphs with more than 18 edges are left unevaluated.
  * FindVertexCover / FindIndependentVertexSet use exact clique search on the
    complement graph; large graphs are left unevaluated.
  * FindMinimumCut supports only the one-argument undirected form (the s-t
    form stays unevaluated in Wolfram 15 too).
  * PageRankCentrality iterates to machine precision; Wolfram's looser
    iteration can differ beyond the 9th decimal on asymmetric graphs.
"""

from __future__ import annotations

import networkx as nx
import sympy

from mathics.core.atoms import Integer, MachineReal
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression

from graphs import (
    _bfs_dist,
    _int,
    _key,
    _parse_edge,
    _parse_graph,
    _wl_list,
    SymbolDirectedEdge,
    SymbolFalse,
    SymbolGraph,
    SymbolTrue,
    SymbolUndirectedEdge,
)

# Subset-enumeration cap for the graph polynomials (2^E spanning subgraphs).
_POLY_MAX_EDGES = 18
# Exact-search cap for clique/cover/independent-set and isomorphism helpers.
_EXACT_MAX_VERTICES = 64


# ---------------------------------------------------------------------------
# networkx conversion and graph-expression construction
# ---------------------------------------------------------------------------

def _to_nx(gr, directed=None):
    """networkx graph on integer vertex indices.  Undirected edges inside a
    directed graph become antiparallel pairs; parallel edges collapse."""
    if directed is None:
        directed = gr.directed
    G = nx.DiGraph() if directed else nx.Graph()
    G.add_nodes_from(range(len(gr.vertices)))
    for i, j, d in gr.edges:
        if directed and not d:
            G.add_edge(i, j)
            G.add_edge(j, i)
        else:
            G.add_edge(i, j)
    return G


def _edge_expr(a, b, d):
    return Expression(SymbolDirectedEdge if d else SymbolUndirectedEdge, a, b)


def _graph_expr(vertices, edges, with_vertex_list=False):
    """edges: (a_expr, b_expr, directed) triples."""
    edge_exprs = [_edge_expr(a, b, d) for a, b, d in edges]
    if with_vertex_list:
        return Expression(SymbolGraph, _wl_list(list(vertices)), _wl_list(edge_exprs))
    return Expression(SymbolGraph, _wl_list(edge_exprs))


def _induced(gr, keep):
    """Induced subgraph on the index set `keep`; vertices keep gr's order."""
    order = [i for i in range(len(gr.vertices)) if i in keep]
    edges = [(gr.vertices[i], gr.vertices[j], d)
             for i, j, d in gr.edges if i in keep and j in keep]
    return _graph_expr([gr.vertices[i] for i in order], edges, with_vertex_list=True)


def _edge_key(gr, e):
    """Hashable identity of an edge for set operations."""
    i, j, d = e
    ki, kj = _key(gr.vertices[i]), _key(gr.vertices[j])
    if not d and kj < ki:
        ki, kj = kj, ki
    return (d, ki, kj)


def _merge_graphs(graphs, mode):
    """mode in {'union', 'intersection'}: returns (vertices, edges)."""
    vertices, seen_v = [], set()

    def add_vertex(v):
        k = _key(v)
        if k not in seen_v:
            seen_v.add(k)
            vertices.append(v)

    if mode == "union":
        for gr in graphs:
            for v in gr.vertices:
                add_vertex(v)
    else:
        first, rest = graphs[0], graphs[1:]
        # Wolfram's GraphIntersection keeps the union of the vertex lists
        for gr in graphs:
            for v in gr.vertices:
                add_vertex(v)
    if mode == "union":
        edges, seen_e = [], set()
        for gr in graphs:
            for e in gr.edges:
                k = _edge_key(gr, e)
                if k not in seen_e:
                    seen_e.add(k)
                    edges.append((gr.vertices[e[0]], gr.vertices[e[1]], e[2]))
    else:
        first = graphs[0]
        rest_keys = [set(_edge_key(gr, e) for e in gr.edges) for gr in graphs[1:]]
        edges, seen_e = [], set()
        for e in first.edges:
            k = _edge_key(first, e)
            if k not in seen_e and all(k in s for s in rest_keys):
                seen_e.add(k)
                edges.append((first.vertices[e[0]], first.vertices[e[1]], e[2]))
    return vertices, edges


def _max_clique_indices(G):
    """Largest clique of a simple nx graph; smallest-index ties first."""
    best = None
    for clique in nx.find_cliques(G):
        c = sorted(clique)
        if best is None or len(c) > len(best) or (len(c) == len(best) and c < best):
            best = c
    return best or []


# ---------------------------------------------------------------------------
# Structural operations
# ---------------------------------------------------------------------------

class Subgraph(Builtin):
    """
    <dl><dt>'Subgraph[$g$, {$v1$, $v2$, ...}]'<dd>subgraph of $g$ induced by
    the given vertices.</dl>
    >> EdgeList[Subgraph[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], {1, 2}]]
     = {1 <-> 2}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "induced subgraph on a vertex subset"

    def eval(self, g, spec, evaluation):
        "Subgraph[g_Graph, spec_List]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        order = []
        keep = set()
        for v in spec.elements:
            i = gr.vertex_index(v)
            if i is None:
                return None
            if i not in keep:
                keep.add(i)
                order.append(i)  # Wolfram keeps the requested vertex order
        edges = [(gr.vertices[i], gr.vertices[j], d)
                 for i, j, d in gr.edges if i in keep and j in keep]
        return _graph_expr([gr.vertices[i] for i in order], edges, with_vertex_list=True)


class NeighborhoodGraph(Builtin):
    """
    <dl><dt>'NeighborhoodGraph[$g$, $v$]'<dd>subgraph induced by $v$ and its
    neighbors.<dt>'NeighborhoodGraph[$g$, $v$, $k$]'<dd>vertices within
    distance $k$ of $v$.</dl>
    >> VertexList[NeighborhoodGraph[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}], 2]]
     = {2, 1, 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "neighborhood subgraph around a vertex"

    def _eval(self, g, v, k, evaluation):
        gr = _parse_graph(g)
        if gr is None:
            return None
        i = gr.vertex_index(v)
        if i is None or k < 0:
            return None
        dist = _bfs_dist(gr, i)
        keep = {u for u, d in dist.items() if d <= k}
        # Wolfram orders the center vertex first, the rest in graph order
        order = [i] + [u for u in range(len(gr.vertices)) if u != i and u in keep]
        edges = [(gr.vertices[a], gr.vertices[b], d)
                 for a, b, d in gr.edges if a in keep and b in keep]
        return _graph_expr([gr.vertices[u] for u in order], edges, with_vertex_list=True)

    def eval(self, g, v, evaluation):
        "NeighborhoodGraph[g_Graph, v_]"
        return self._eval(g, v, 1, evaluation)

    def eval_k(self, g, v, k, evaluation):
        "NeighborhoodGraph[g_Graph, v_, k_Integer]"
        return self._eval(g, v, k.value, evaluation)


class GraphUnion(Builtin):
    """
    <dl><dt>'GraphUnion[$g1$, $g2$]'<dd>graph with the vertices and edges of
    both graphs (shared edges merged).</dl>
    >> EdgeCount[GraphUnion[Graph[{1 <-> 2}], Graph[{1 <-> 2, 2 <-> 3}]]]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "union of graphs"

    def _eval(self, graphs, evaluation):
        parsed = [_parse_graph(g) for g in graphs]
        if any(gr is None for gr in parsed):
            return None
        vertices, edges = _merge_graphs(parsed, "union")
        return _graph_expr(vertices, edges, with_vertex_list=True)

    def eval(self, g1, g2, evaluation):
        "GraphUnion[g1_Graph, g2_Graph]"
        return self._eval([g1, g2], evaluation)


class GraphIntersection(Builtin):
    """
    <dl><dt>'GraphIntersection[$g1$, $g2$]'<dd>graph with the vertices and
    edges common to both graphs.</dl>
    >> EdgeList[GraphIntersection[Graph[{1 <-> 2, 2 <-> 3}], Graph[{2 <-> 3}]]]
     = {2 <-> 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "intersection of graphs"

    def _eval(self, graphs, evaluation):
        parsed = [_parse_graph(g) for g in graphs]
        if any(gr is None for gr in parsed):
            return None
        vertices, edges = _merge_graphs(parsed, "intersection")
        return _graph_expr(vertices, edges, with_vertex_list=True)

    def eval(self, g1, g2, evaluation):
        "GraphIntersection[g1_Graph, g2_Graph]"
        return self._eval([g1, g2], evaluation)


class GraphDifference(Builtin):
    """
    <dl><dt>'GraphDifference[$g1$, $g2$]'<dd>graph with the vertices of $g1$
    and the edges of $g1$ not present in $g2$.</dl>
    >> EdgeList[GraphDifference[Graph[{1 <-> 2, 2 <-> 3}], Graph[{2 <-> 3}]]]
     = {1 <-> 2}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "difference of graphs"

    def eval(self, g1, g2, evaluation):
        "GraphDifference[g1_Graph, g2_Graph]"
        gr1, gr2 = _parse_graph(g1), _parse_graph(g2)
        if gr1 is None or gr2 is None:
            return None
        drop = {_edge_key(gr2, e) for e in gr2.edges}
        edges = [(gr1.vertices[i], gr1.vertices[j], d)
                 for i, j, d in gr1.edges if _edge_key(gr1, (i, j, d)) not in drop]
        return _graph_expr(gr1.vertices, edges, with_vertex_list=True)


class GraphComplement(Builtin):
    """
    <dl><dt>'GraphComplement[$g$]'<dd>simple complement of $g$: same vertices,
    exactly the missing edges between distinct vertices.</dl>
    >> EdgeList[GraphComplement[Graph[{1 <-> 2, 2 <-> 3}]]]
     = {1 <-> 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "complement graph"

    def eval(self, g, evaluation):
        "GraphComplement[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        present = set()
        for i, j, d in gr.edges:
            if d or i <= j:
                present.add((i, j, d))
            else:
                present.add((j, i, d))
        edges = []
        if gr.directed:
            for i in range(n):
                for j in range(n):
                    if i != j and (i, j, True) not in present:
                        edges.append((gr.vertices[i], gr.vertices[j], True))
        else:
            for i in range(n):
                for j in range(i + 1, n):
                    if (i, j, False) not in present:
                        edges.append((gr.vertices[i], gr.vertices[j], False))
        return _graph_expr(gr.vertices, edges, with_vertex_list=True)


class DirectedGraph(Builtin):
    """
    <dl><dt>'DirectedGraph[$g$]'<dd>directed version of $g$: every undirected
    edge becomes a pair of antiparallel directed edges.</dl>
    >> EdgeCount[DirectedGraph[Graph[{1 <-> 2, 2 <-> 3}]]]
     = 4
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "convert to a directed graph"

    def eval(self, g, evaluation):
        "DirectedGraph[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        edges = []
        for i, j, d in gr.edges:
            a, b = gr.vertices[i], gr.vertices[j]
            if d:
                edges.append((a, b, True))
            else:
                edges.append((a, b, True))
                edges.append((b, a, True))
        return _graph_expr(gr.vertices, edges, with_vertex_list=True)


class UndirectedGraph(Builtin):
    """
    <dl><dt>'UndirectedGraph[$g$]'<dd>undirected version of $g$: directed
    edges become undirected (antiparallel pairs merge).</dl>
    >> EdgeCount[UndirectedGraph[Graph[{1 -> 2, 2 -> 1, 2 -> 3}]]]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "convert to an undirected graph"

    def eval(self, g, evaluation):
        "UndirectedGraph[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        edges, seen = [], set()
        for i, j, d in gr.edges:
            ki, kj = _key(gr.vertices[i]), _key(gr.vertices[j])
            if i != j and kj < ki:
                ki, kj = kj, ki
            if (ki, kj) in seen:
                continue
            seen.add((ki, kj))
            edges.append((gr.vertices[i], gr.vertices[j], False))
        return _graph_expr(gr.vertices, edges, with_vertex_list=True)


class AdjacencyGraph(Builtin):
    """
    <dl><dt>'AdjacencyGraph[$m$]'<dd>graph with the given (dense) adjacency
    matrix; symmetric matrices give undirected graphs.</dl>
    >> VertexCount[AdjacencyGraph[{{0, 1}, {1, 0}}]]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "graph from an adjacency matrix"

    def eval(self, m, evaluation):
        "AdjacencyGraph[m_List]"
        if not m.elements or not all(row.has_form("List", None) for row in m.elements):
            return None
        rows = []
        for row in m.elements:
            entries = []
            if len(row.elements) != len(m.elements):
                return None
            for e in row.elements:
                if not isinstance(e, Integer) or e.value < 0:
                    return None
                entries.append(e.value)
            rows.append(entries)
        n = len(rows)
        vertices = [_int(i + 1) for i in range(n)]
        symmetric = all(rows[i][j] == rows[j][i] for i in range(n) for j in range(n))
        edges = []
        if symmetric:
            for i in range(n):
                for _ in range(rows[i][i] // 2):
                    edges.append((vertices[i], vertices[i], False))
                for j in range(i + 1, n):
                    for _ in range(rows[i][j]):
                        edges.append((vertices[i], vertices[j], False))
        else:
            for i in range(n):
                for j in range(n):
                    for _ in range(rows[i][j]):
                        edges.append((vertices[i], vertices[j], True))
        return _graph_expr(vertices, edges, with_vertex_list=True)


class IncidenceMatrix(Builtin):
    """
    <dl><dt>'IncidenceMatrix[$g$]'<dd>dense vertex-edge incidence matrix.
    Directed graphs use -1 at the tail and 1 at the head.</dl>
    >> IncidenceMatrix[Graph[{1 -> 2, 2 -> 3}]]
     = {{-1, 0}, {1, -1}, {0, 1}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "vertex-edge incidence matrix (dense list)"

    def eval(self, g, evaluation):
        "IncidenceMatrix[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n, m = len(gr.vertices), len(gr.edges)
        M = [[0] * m for _ in range(n)]
        for col, (i, j, d) in enumerate(gr.edges):
            if d:
                if i == j:
                    M[i][col] = -2  # Wolfram's convention for a directed loop
                else:
                    M[i][col] -= 1
                    M[j][col] += 1
            else:
                M[i][col] += 1
                M[j][col] += 1
        return _wl_list([_wl_list([_int(v) for v in row]) for row in M])


class KirchhoffMatrix(Builtin):
    """
    <dl><dt>'KirchhoffMatrix[$g$]'<dd>dense Kirchhoff (Laplacian) matrix:
    degrees on the diagonal, minus the adjacency matrix.  Directed graphs use
    in-degree + out-degree on the diagonal and keep the adjacency direction
    (the matrix is then asymmetric).</dl>
    >> KirchhoffMatrix[Graph[{1 <-> 2, 2 <-> 3}]]
     = {{1, -1, 0}, {-1, 2, -1}, {0, -1, 1}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Kirchhoff (Laplacian) matrix (dense list)"

    def eval(self, g, evaluation):
        "KirchhoffMatrix[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        M = [[0] * n for _ in range(n)]
        if gr.directed:
            # Wolfram: diagonal = in-degree + out-degree, off-diagonal
            # M[[i, j]] = -(number of edges i -> j); the matrix is asymmetric.
            for i, j, d in gr.edges:
                if d:
                    M[i][j] -= 1
                else:
                    M[i][j] -= 1
                    M[j][i] -= 1
            for i in range(n):
                M[i][i] = len(gr.adj_in[i]) + len(gr.adj_out[i])
        else:
            for i, j, d in gr.edges:
                M[i][j] -= 1
                M[j][i] -= 1
                M[i][i] += 1
                M[j][j] += 1
        return _wl_list([_wl_list([_int(v) for v in row]) for row in M])


class LineGraph(Builtin):
    """
    <dl><dt>'LineGraph[$g$]'<dd>line graph of $g$: one vertex per edge of $g$
    (labeled 1..EdgeCount[$g$], in edge order), adjacent when the edges share
    an endpoint — for a directed graph, when the head of one meets the tail of
    the other.</dl>
    >> VertexList[LineGraph[Graph[{1 <-> 2, 1 <-> 3}]]]
     = {1, 2}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "line graph"

    def eval(self, g, evaluation):
        "LineGraph[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        m = len(gr.edges)
        edge_vertices = [_int(k + 1) for k in range(m)]
        edges = []
        if gr.directed:
            for a in range(m):
                for b in range(m):
                    if a != b and gr.edges[a][1] == gr.edges[b][0]:
                        edges.append((edge_vertices[a], edge_vertices[b], True))
        else:
            for a in range(m):
                for b in range(a + 1, m):
                    i, j, _ = gr.edges[a]
                    k, l, _ = gr.edges[b]
                    if len({i, j} & {k, l}) > 0:
                        edges.append((edge_vertices[a], edge_vertices[b], False))
        return _graph_expr(edge_vertices, edges, with_vertex_list=True)


class EdgeAdd(Builtin):
    """
    <dl><dt>'EdgeAdd[$g$, $e$]'<dd>$g$ with the edge $e$ added (parallel edges
    are kept).</dl>
    >> EdgeCount[EdgeAdd[Graph[{1 <-> 2}], 1 <-> 2]]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "add an edge"

    def eval(self, g, e, evaluation):
        "EdgeAdd[g_Graph, e_]"
        gr = _parse_graph(g)
        parsed = _parse_edge(e) if gr is not None else None
        if parsed is None:
            return None
        a, b, d = parsed
        vertices = list(gr.vertices)
        seen = {_key(v) for v in vertices}
        for v in (a, b):
            if _key(v) not in seen:
                seen.add(_key(v))
                vertices.append(v)
        edges = [(gr.vertices[i], gr.vertices[j], dd) for i, j, dd in gr.edges]
        edges.append((a, b, d))
        return _graph_expr(vertices, edges, with_vertex_list=True)


class EdgeDelete(Builtin):
    """
    <dl><dt>'EdgeDelete[$g$, $e$]'<dd>$g$ with the first edge matching $e$
    removed; vertices are kept.</dl>
    >> EdgeList[EdgeDelete[Graph[{1 <-> 2, 2 <-> 3}], 2 <-> 3]]
     = {1 <-> 2}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "delete an edge"

    def eval(self, g, e, evaluation):
        "EdgeDelete[g_Graph, e_]"
        gr = _parse_graph(g)
        parsed = _parse_edge(e) if gr is not None else None
        if parsed is None:
            return None
        a, b, d = parsed
        ka, kb = _key(a), _key(b)
        if not d and kb < ka:
            ka, kb = kb, ka
        edges = []
        removed = False
        for i, j, dd in gr.edges:
            ki, kj = _key(gr.vertices[i]), _key(gr.vertices[j])
            if not dd and kj < ki:
                ki, kj = kj, ki
            if gr.directed:
                match = d and dd and (ki, kj) == (ka, kb)
            else:
                match = (ki, kj) == (ka, kb)
            if match and not removed:
                removed = True  # Wolfram removes a single instance
                continue
            edges.append((gr.vertices[i], gr.vertices[j], dd))
        return _graph_expr(gr.vertices, edges, with_vertex_list=True)


class VertexAdd(Builtin):
    """
    <dl><dt>'VertexAdd[$g$, $v$]'<dd>$g$ with the isolated vertex $v$ added.</dl>
    >> VertexCount[VertexAdd[Graph[{1 <-> 2}], 5]]
     = 3
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "add a vertex"

    def eval(self, g, v, evaluation):
        "VertexAdd[g_Graph, v_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        vertices = list(gr.vertices)
        if gr.vertex_index(v) is None:
            vertices.append(v)
        edges = [(gr.vertices[i], gr.vertices[j], d) for i, j, d in gr.edges]
        return _graph_expr(vertices, edges, with_vertex_list=True)


class VertexDelete(Builtin):
    """
    <dl><dt>'VertexDelete[$g$, $v$]'<dd>$g$ with $v$ and its incident edges
    removed.</dl>
    >> EdgeList[VertexDelete[Graph[{1 <-> 2, 2 <-> 3}], 2]]
     = {}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "delete vertices"

    def eval(self, g, v, evaluation):
        "VertexDelete[g_Graph, v_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i = gr.vertex_index(v)
        if i is None:
            return _graph_expr(gr.vertices,
                               [(gr.vertices[a], gr.vertices[b], d) for a, b, d in gr.edges],
                               with_vertex_list=True)
        return _induced(gr, set(range(len(gr.vertices))) - {i})

    def eval_list(self, g, vs, evaluation):
        "VertexDelete[g_Graph, vs_List]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        drop = set()
        for v in vs.elements:
            i = gr.vertex_index(v)
            if i is not None:
                drop.add(i)
        return _induced(gr, set(range(len(gr.vertices))) - drop)


class EdgeContract(Builtin):
    """
    <dl><dt>'EdgeContract[$g$, $e$]'<dd>$g$ with the edge $e$ contracted: its
    endpoints merge into the first endpoint and parallel edges merge (the
    result is simple).</dl>
    >> VertexList[EdgeContract[Graph[{1 <-> 2, 2 <-> 3}], 1 <-> 2]]
     = {1, 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "contract an edge"

    def eval(self, g, e, evaluation):
        "EdgeContract[g_Graph, e_]"
        gr = _parse_graph(g)
        parsed = _parse_edge(e) if gr is not None else None
        if parsed is None:
            return None
        a, b, d = parsed
        ia, ib = gr.vertex_index(a), gr.vertex_index(b)
        if ia is None or ib is None:
            return None
        keep_target = gr.vertices[ia]
        vertices = [v for k, v in enumerate(gr.vertices) if k != ib]
        edges, seen = [], set()
        for i, j, dd in gr.edges:
            if {i, j} == {ia, ib} and dd == d:
                continue  # the contracted edge itself
            vi = keep_target if i == ib else gr.vertices[i]
            vj = keep_target if j == ib else gr.vertices[j]
            ki, kj = _key(vi), _key(vj)
            if not dd and kj < ki:
                ki, kj = kj, ki
            if (dd, ki, kj) in seen:
                continue  # parallel edges merge (Wolfram keeps it simple)
            seen.add((dd, ki, kj))
            edges.append((vi, vj, dd))
        return _graph_expr(vertices, edges, with_vertex_list=True)


class GraphPower(Builtin):
    """
    <dl><dt>'GraphPower[$g$, $k$]'<dd>$k$-th power of $g$: edges join distinct
    vertices at distance at most $k$.</dl>
    >> EdgeCount[GraphPower[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}], 2]]
     = 5
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "graph power"

    def eval(self, g, k, evaluation):
        "GraphPower[g_Graph, k_Integer]"
        gr = _parse_graph(g)
        if gr is None or k.value < 1:
            return None
        n = len(gr.vertices)
        edges = []
        for i in range(n):
            dist = _bfs_dist(gr, i)
            for j, d in dist.items():
                if i == j or d > k.value:
                    continue
                if gr.directed:
                    edges.append((gr.vertices[i], gr.vertices[j], True))
                elif i < j:
                    edges.append((gr.vertices[i], gr.vertices[j], False))
        return _graph_expr(gr.vertices, edges, with_vertex_list=True)


class TransitiveClosureGraph(Builtin):
    """
    <dl><dt>'TransitiveClosureGraph[$g$]'<dd>supergraph of $g$ with an edge
    for every reachable pair of distinct vertices.</dl>
    >> EdgeCount[TransitiveClosureGraph[Graph[{1 -> 2, 2 -> 3}]]]
     = 3
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "transitive closure"

    def eval(self, g, evaluation):
        "TransitiveClosureGraph[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        # dedupe to simple edges, then emit in canonical sorted order (Wolfram)
        seen = set()
        simple = []
        for i, j, d in gr.edges:
            key = (i, j) if (d or i <= j) else (j, i)
            if key not in seen:
                seen.add(key)
                simple.append((i, j, d))
        for i in range(n):
            dist = _bfs_dist(gr, i)
            for j in dist:
                if i == j:
                    continue
                key = (i, j) if gr.directed else (min(i, j), max(i, j))
                if key not in seen:
                    seen.add(key)
                    simple.append((i, j, gr.directed))
        simple.sort(key=lambda e: (e[0], e[1]) if e[2] else (min(e[0], e[1]), max(e[0], e[1])))
        edges = [(gr.vertices[i], gr.vertices[j], d) for i, j, d in simple]
        return _graph_expr(gr.vertices, edges, with_vertex_list=True)


# ---------------------------------------------------------------------------
# Predicates and invariants
# ---------------------------------------------------------------------------

class IsomorphicGraphQ(Builtin):
    """
    <dl><dt>'IsomorphicGraphQ[$g1$, $g2$]'<dd>True if $g1$ and $g2$ are
    isomorphic (directedness must agree).</dl>
    >> IsomorphicGraphQ[Graph[{1 <-> 2, 2 <-> 3}], PathGraph[3]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test graph isomorphism"

    def eval(self, g1, g2, evaluation):
        "IsomorphicGraphQ[g1_Graph, g2_Graph]"
        gr1, gr2 = _parse_graph(g1), _parse_graph(g2)
        if gr1 is None or gr2 is None:
            return SymbolFalse
        G1, G2 = _to_nx(gr1), _to_nx(gr2)
        if G1.is_directed() != G2.is_directed():
            return SymbolFalse
        return SymbolTrue if nx.is_isomorphic(G1, G2) else SymbolFalse


class BipartiteGraphQ(Builtin):
    """
    <dl><dt>'BipartiteGraphQ[$g$]'<dd>True if $g$ is bipartite.</dl>
    >> BipartiteGraphQ[CycleGraph[4]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test whether a graph is bipartite"

    def eval(self, g, evaluation):
        "BipartiteGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        if any(i == j for i, j, _ in gr.edges):
            return SymbolFalse
        return SymbolTrue if nx.is_bipartite(_to_nx(gr, directed=False)) else SymbolFalse


class PlanarGraphQ(Builtin):
    """
    <dl><dt>'PlanarGraphQ[$g$]'<dd>True if $g$ is planar.</dl>
    >> PlanarGraphQ[CompleteGraph[5]]
     = False
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test whether a graph is planar"

    def eval(self, g, evaluation):
        "PlanarGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        ok, _ = nx.check_planarity(_to_nx(gr, directed=False))
        return SymbolTrue if ok else SymbolFalse


class VertexConnectivity(Builtin):
    """
    <dl><dt>'VertexConnectivity[$g$]'<dd>smallest number of vertices whose
    removal disconnects $g$ (n-1 for the complete graph on n vertices).</dl>
    >> VertexConnectivity[CompleteGraph[4]]
     = 3
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "vertex connectivity"

    def eval(self, g, evaluation):
        "VertexConnectivity[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        if n <= 1:
            return _int(0)
        try:
            return _int(nx.node_connectivity(_to_nx(gr)))
        except nx.NetworkXError:
            return None


class EdgeConnectivity(Builtin):
    """
    <dl><dt>'EdgeConnectivity[$g$]'<dd>smallest number of edges whose removal
    disconnects $g$.</dl>
    >> EdgeConnectivity[Graph[{1 <-> 2, 2 <-> 3}]]
     = 1
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "edge connectivity"

    def eval(self, g, evaluation):
        "EdgeConnectivity[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        if n <= 1:
            return _int(0)
        # multigraph-aware: parallel edges raise the connectivity (Wolfram)
        G = nx.MultiDiGraph() if gr.directed else nx.MultiGraph()
        G.add_nodes_from(range(n))
        for i, j, d in gr.edges:
            if gr.directed and not d:
                G.add_edge(i, j)
                G.add_edge(j, i)
            else:
                G.add_edge(i, j)
        try:
            return _int(nx.edge_connectivity(G))
        except nx.NetworkXError:
            return None


def _spanning_subgraph_polynomial(gr, sx, sy=None):
    """Chromatic polynomial (sy None) or Tutte polynomial of gr by spanning-
    subgraph enumeration, as a sympy expression."""
    n = len(gr.vertices)
    edges = [(i, j) for i, j, _ in gr.edges]
    m = len(edges)
    # components of the full graph (for the chromatic/Tutte exponents)
    parent = list(range(n))

    def find(u):
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    for i, j in edges:
        parent[find(i)] = find(j)
    c_full = len({find(i) for i in range(n)}) if n else 0

    one = sympy.Integer(1)
    total = sympy.Integer(0)
    for mask in range(1 << m):
        p = list(range(n))
        bits = 0

        def find2(u):
            while p[u] != u:
                p[u] = p[p[u]]
                u = p[u]
            return u

        mm = mask
        k = 0
        while mm:
            if mm & 1:
                i, j = edges[k]
                p[find2(i)] = find2(j)
                bits += 1
            mm >>= 1
            k += 1
        c = len({find2(i) for i in range(n)}) if n else 0
        if sy is None:
            total += ((-one) ** bits) * sx ** c
        else:
            total += (sx - 1) ** (c - c_full) * (sy - 1) ** (bits - n + c)
    return total


class ChromaticPolynomial(Builtin):
    """
    <dl><dt>'ChromaticPolynomial[$g$, $x$]'<dd>chromatic polynomial of $g$,
    expanded (Wolfram's form).  Graphs with more than 18 edges are left
    unevaluated.</dl>
    >> ChromaticPolynomial[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], x]
     = 2 x - 3 x^2 + x^3
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "chromatic polynomial"

    def eval(self, g, x, evaluation):
        "ChromaticPolynomial[g_Graph, x_Symbol]"
        gr = _parse_graph(g)
        if gr is None or len(gr.edges) > _POLY_MAX_EDGES:
            return None
        sx = x.to_sympy()
        if not isinstance(sx, sympy.Symbol):
            return None
        poly = _spanning_subgraph_polynomial(gr, sx)
        return from_sympy(sympy.expand(poly))

    def eval_numeric(self, g, x, evaluation):
        "ChromaticPolynomial[g_Graph, x_]"
        gr = _parse_graph(g)
        if gr is None or len(gr.edges) > _POLY_MAX_EDGES:
            return None
        sx = x.to_sympy()
        if sx is None or sx.free_symbols:
            return None
        poly = _spanning_subgraph_polynomial(gr, sympy.Symbol("lambda_"))
        return from_sympy(poly.subs(sympy.Symbol("lambda_"), sx))


class TuttePolynomial(Builtin):
    """
    <dl><dt>'TuttePolynomial[$g$, {$x$, $y$}]'<dd>Tutte polynomial of $g$.
    Graphs with more than 18 edges are left unevaluated.</dl>
    >> TuttePolynomial[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}], {x, y}]
     = x + x^2 + y
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "Tutte polynomial"

    def eval(self, g, vars, evaluation):
        "TuttePolynomial[g_Graph, vars_List]"
        gr = _parse_graph(g)
        if gr is None or len(vars.elements) != 2 or len(gr.edges) > _POLY_MAX_EDGES:
            return None
        sx, sy = (v.to_sympy() for v in vars.elements)
        if sx is None or sy is None:
            return None
        dx, dy = sympy.Symbol("tu_"), sympy.Symbol("tv_")
        poly = _spanning_subgraph_polynomial(gr, dx, dy).subs({dx: sx, dy: sy})
        return from_sympy(sympy.expand(poly))


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

class FindClique(Builtin):
    """
    <dl><dt>'FindClique[$g$]'<dd>a largest clique, as a list of cliques
    (Wolfram wraps the result in an extra list).</dl>
    >> FindClique[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]
     = {{1, 2, 3}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find a largest clique"

    def eval(self, g, evaluation):
        "FindClique[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or len(gr.vertices) > _EXACT_MAX_VERTICES:
            return None
        clique = _max_clique_indices(_to_nx(gr, directed=False))
        return _wl_list([_wl_list([gr.vertices[i] for i in clique])])


class FindVertexCover(Builtin):
    """
    <dl><dt>'FindVertexCover[$g$]'<dd>a minimum vertex cover (exact search on
    the complement graph).</dl>
    >> FindVertexCover[Graph[{1 <-> 2, 2 <-> 3}]]
     = {2}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find a minimum vertex cover"

    def eval(self, g, evaluation):
        "FindVertexCover[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or len(gr.vertices) > _EXACT_MAX_VERTICES:
            return None
        G = _to_nx(gr, directed=False)
        comp = nx.complement(G)
        best_size, best = None, None
        for clique in nx.find_cliques(comp):
            cover = tuple(sorted(set(range(len(gr.vertices))) - set(clique)))
            if best is None or len(cover) < best_size or (len(cover) == best_size and cover < best):
                best_size, best = len(cover), cover
        return _wl_list([gr.vertices[i] for i in (best or ())])


class FindIndependentVertexSet(Builtin):
    """
    <dl><dt>'FindIndependentVertexSet[$g$]'<dd>a maximum independent vertex
    set (exact search on the complement graph), wrapped in a list like
    Wolfram 15.</dl>
    >> FindIndependentVertexSet[Graph[{1 <-> 2, 2 <-> 3}]]
     = {{1, 3}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find a maximum independent vertex set"

    def eval(self, g, evaluation):
        "FindIndependentVertexSet[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or len(gr.vertices) > _EXACT_MAX_VERTICES:
            return None
        G = _to_nx(gr, directed=False)
        clique = _max_clique_indices(nx.complement(G))
        return _wl_list([_wl_list([gr.vertices[i] for i in clique])])


class FindIndependentEdgeSet(Builtin):
    """
    <dl><dt>'FindIndependentEdgeSet[$g$]'<dd>a maximum matching, as an edge
    list.</dl>
    >> FindIndependentEdgeSet[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 4}]]
     = {1 <-> 2, 3 <-> 4}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find a maximum matching"

    def eval(self, g, evaluation):
        "FindIndependentEdgeSet[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        matching = nx.max_weight_matching(_to_nx(gr, directed=False), weight=None)
        edges = []
        for i, j, d in gr.edges:
            pair = (i, j) if i <= j else (j, i)
            if any(pair == ((a, b) if a <= b else (b, a)) for a, b in matching):
                edges.append(gr.edge_expr((i, j, d)))
                matching = [m for m in matching
                            if ((m[0], m[1]) if m[0] <= m[1] else (m[1], m[0])) != pair]
        return _wl_list(edges)


class FindMaximumFlow(Builtin):
    """
    <dl><dt>'FindMaximumFlow[$g$, $s$, $t$]'<dd>maximum flow value from $s$
    to $t$ with unit edge capacities.  Wolfram treats the graph as simple:
    parallel edges do not add capacity; undirected edges work both ways.</dl>
    >> FindMaximumFlow[Graph[{1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4}], 1, 4]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "maximum flow value"

    def eval(self, g, s, t, evaluation):
        "FindMaximumFlow[g_Graph, s_, t_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i, j = gr.vertex_index(s), gr.vertex_index(t)
        if i is None or j is None or i == j:
            return None
        G = _to_nx(gr, directed=True)  # simple view; capacity 1 per arc
        for a, b in G.edges:
            G.edges[a, b]["capacity"] = 1
        try:
            return _int(nx.maximum_flow_value(G, i, j))
        except nx.NetworkXError:
            return None


class FindMinimumCut(Builtin):
    """
    <dl><dt>'FindMinimumCut[$g$]'<dd>minimum edge cut of an undirected graph
    as '{$value$, {{$side1$}, {$side2$}}}'.  The $s$-$t$ form and directed
    graphs stay unevaluated, as in Wolfram 15.</dl>
    >> FindMinimumCut[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]
     = {1, {{4}, {1, 2, 3}}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "minimum edge cut"

    def eval(self, g, evaluation):
        "FindMinimumCut[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or gr.directed or len(gr.vertices) <= 1:
            return None
        G = _to_nx(gr, directed=False)
        try:
            value, (left, right) = nx.stoer_wagner(G)
        except nx.NetworkXError:
            return None
        left, right = sorted(left), sorted(right)
        # Wolfram lists the side not containing the first vertex first
        if 0 in left:
            left, right = right, left
        parts = _wl_list([_wl_list([gr.vertices[i] for i in left]),
                          _wl_list([gr.vertices[i] for i in right])])
        return _wl_list([_int(int(value)), parts])


class FindPath(Builtin):
    """
    <dl><dt>'FindPath[$g$, $s$, $t$]'<dd>a path from $s$ to $t$ (depth-first,
    neighbors in vertex order, matching Wolfram's choice), wrapped in a list;
    {} when none exists.</dl>
    >> FindPath[Graph[{1 <-> 2, 2 <-> 3, 1 <-> 3}], 1, 3]
     = {{1, 2, 3}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find a path between two vertices"

    def eval(self, g, s, t, evaluation):
        "FindPath[g_Graph, s_, t_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i, j = gr.vertex_index(s), gr.vertex_index(t)
        if i is None or j is None:
            return None
        # iterative DFS, neighbors in vertex order
        path = [i]
        visited = {i}
        stack = [iter(sorted(set(gr.adj_out[i])))]
        while stack:
            advanced = False
            for w in stack[-1]:
                if w in visited:
                    continue
                visited.add(w)
                path.append(w)
                if w == j:
                    return _wl_list([_wl_list([gr.vertices[k] for k in path])])
                stack.append(iter(sorted(set(gr.adj_out[w]))))
                advanced = True
                break
            if not advanced:
                stack.pop()
                path.pop()
        return _wl_list([])


class FindCycle(Builtin):
    """
    <dl><dt>'FindCycle[$g$]'<dd>a cycle of $g$ as an edge list, wrapped in a
    list; {} when $g$ is acyclic.</dl>
    >> FindCycle[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1, 3 <-> 4}]]
     = {{1 <-> 2, 2 <-> 3, 3 <-> 1}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find a cycle"

    def eval(self, g, evaluation):
        "FindCycle[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        G = _to_nx(gr)
        try:
            cycle = nx.find_cycle(G)
        except nx.NetworkXNoCycle:
            return _wl_list([])
        edges = []
        for a, b in cycle:
            match = next(((i, j, d) for i, j, d in gr.edges
                          if (i, j) == (a, b) or (not d and (i, j) == (b, a))), None)
            if match is None:
                return None
            edges.append(gr.edge_expr(match))
        return _wl_list([_wl_list(edges)])


# ---------------------------------------------------------------------------
# Centrality
# ---------------------------------------------------------------------------

class DegreeCentrality(Builtin):
    """
    <dl><dt>'DegreeCentrality[$g$]'<dd>vertex degrees (in-degree + out-degree
    for directed graphs).</dl>
    >> DegreeCentrality[Graph[{1 <-> 2, 2 <-> 3}]]
     = {1, 2, 1}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "degree centrality"

    def eval(self, g, evaluation):
        "DegreeCentrality[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        if gr.directed:
            degrees = [len(gr.adj_in[i]) + len(gr.adj_out[i]) for i in range(n)]
        else:
            degrees = [len(gr.adj_out[i]) for i in range(n)]
        return _wl_list([_int(d) for d in degrees])


class BetweennessCentrality(Builtin):
    """
    <dl><dt>'BetweennessCentrality[$g$]'<dd>betweenness centrality of every
    vertex (unnormalized pair counts).</dl>
    >> BetweennessCentrality[Graph[{1 <-> 2, 2 <-> 3}]]
     = {0., 1., 0.}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "betweenness centrality"

    def eval(self, g, evaluation):
        "BetweennessCentrality[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        cb = nx.betweenness_centrality(_to_nx(gr), normalized=False)
        return _wl_list([MachineReal(cb.get(i, 0.0)) for i in range(len(gr.vertices))])


class ClosenessCentrality(Builtin):
    """
    <dl><dt>'ClosenessCentrality[$g$]'<dd>closeness centrality: the number of
    reachable vertices over the sum of distances to them (Wolfram's
    convention).</dl>
    >> ClosenessCentrality[Graph[{1 <-> 2, 2 <-> 3}]]
     = {0.666667, 1., 0.666667}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "closeness centrality"

    def eval(self, g, evaluation):
        "ClosenessCentrality[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        out = []
        for i in range(n):
            dist = _bfs_dist(gr, i)
            total = sum(d for u, d in dist.items() if u != i)
            reached = len(dist) - 1
            # Wolfram: reachable count over distance sum (not Wasserman-Faust)
            out.append(MachineReal(0.0) if total == 0 or reached == 0
                       else MachineReal(reached / total))
        return _wl_list(out)


class EigenvectorCentrality(Builtin):
    """
    <dl><dt>'EigenvectorCentrality[$g$]'<dd>dominant eigenvector of the
    adjacency matrix, normalized so the components sum to 1 (Wolfram's
    convention).</dl>
    >> EigenvectorCentrality[CompleteGraph[3]]
     = {0.333333, 0.333333, 0.333333}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "eigenvector centrality"

    def eval(self, g, evaluation):
        "EigenvectorCentrality[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or not gr.vertices:
            return None
        try:
            ce = nx.eigenvector_centrality(_to_nx(gr), max_iter=4000, tol=1e-13)
        except (nx.NetworkXError, nx.PowerIterationFailedConvergence):
            return None
        total = sum(ce.get(i, 0.0) for i in range(len(gr.vertices)))
        if total == 0:
            return None
        return _wl_list([MachineReal(ce.get(i, 0.0) / total) for i in range(len(gr.vertices))])


class PageRankCentrality(Builtin):
    """
    <dl><dt>'PageRankCentrality[$g$]'<dd>PageRank with damping factor 0.85.</dl>
    >> Round[Total[PageRankCentrality[Graph[{1 -> 2, 2 -> 3}]]]]
     = 1
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "PageRank centrality"

    def eval(self, g, evaluation):
        "PageRankCentrality[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or not gr.vertices:
            return None
        pr = nx.pagerank(_to_nx(gr, directed=True), alpha=0.85, tol=1e-12)
        return _wl_list([MachineReal(pr.get(i, 0.0)) for i in range(len(gr.vertices))])


# ---------------------------------------------------------------------------
# Named graph families
# ---------------------------------------------------------------------------

class CompleteGraph(Builtin):
    """
    <dl><dt>'CompleteGraph[$n$]'<dd>complete graph on the vertices 1..$n$.
    <dt>'CompleteGraph[{$n1$, $n2$, ...}]'<dd>complete multipartite graph.</dl>
    >> EdgeCount[CompleteGraph[4]]
     = 6
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "complete (multipartite) graph"

    def eval(self, n, evaluation):
        "CompleteGraph[n_Integer]"
        if n.value < 1:
            return None
        vertices = [_int(i + 1) for i in range(n.value)]
        edges = [(vertices[i], vertices[j], False)
                 for i in range(n.value) for j in range(i + 1, n.value)]
        return _graph_expr(vertices, edges, with_vertex_list=True)

    def eval_parts(self, parts, evaluation):
        "CompleteGraph[parts_List]"
        sizes = []
        for p in parts.elements:
            if not isinstance(p, Integer) or p.value < 1:
                return None
            sizes.append(p.value)
        vertices = [_int(i + 1) for i in range(sum(sizes))]
        edges = []
        blocks, start = [], 0
        for s in sizes:
            blocks.append(range(start, start + s))
            start += s
        for bi in range(len(blocks)):
            for bj in range(bi + 1, len(blocks)):
                for i in blocks[bi]:
                    for j in blocks[bj]:
                        edges.append((vertices[i], vertices[j], False))
        return _graph_expr(vertices, edges, with_vertex_list=True)


class CycleGraph(Builtin):
    """
    <dl><dt>'CycleGraph[$n$]'<dd>cycle on the vertices 1..$n$.</dl>
    >> EdgeCount[CycleGraph[5]]
     = 5
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "cycle graph"

    def eval(self, n, evaluation):
        "CycleGraph[n_Integer]"
        if n.value < 1:
            return None
        vertices = [_int(i + 1) for i in range(n.value)]
        if n.value == 1:
            edges = [(vertices[0], vertices[0], False)]
        else:
            edges = [(vertices[i], vertices[(i + 1) % n.value], False)
                     for i in range(n.value)]
        return _graph_expr(vertices, edges, with_vertex_list=True)


class PathGraph(Builtin):
    """
    <dl><dt>'PathGraph[{$v1$, $v2$, ...}]'<dd>path through the given vertices.
    (Wolfram has no integer-argument form: 'PathGraph[3]' is not a graph
    there.)</dl>
    >> EdgeCount[PathGraph[{1, 2, 3, 4}]]
     = 3
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "path graph"

    def eval_list(self, vs, evaluation):
        "PathGraph[vs_List]"
        vertices = list(vs.elements)
        edges = [(vertices[i], vertices[i + 1], False) for i in range(len(vertices) - 1)]
        return _graph_expr(vertices, edges, with_vertex_list=True)


class StarGraph(Builtin):
    """
    <dl><dt>'StarGraph[$n$]'<dd>star on $n$ vertices: vertex 1 is the center.</dl>
    >> VertexDegree[StarGraph[4]]
     = {3, 1, 1, 1}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "star graph"

    def eval(self, n, evaluation):
        "StarGraph[n_Integer]"
        if n.value < 1:
            return None
        vertices = [_int(i + 1) for i in range(n.value)]
        edges = [(vertices[0], vertices[i], False) for i in range(1, n.value)]
        return _graph_expr(vertices, edges, with_vertex_list=True)


class WheelGraph(Builtin):
    """
    <dl><dt>'WheelGraph[$n$]'<dd>wheel on $n$ vertices: hub 1 joined to the
    cycle 2..$n$.</dl>
    >> VertexCount[WheelGraph[5]]
     = 5
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "wheel graph"

    def eval(self, n, evaluation):
        "WheelGraph[n_Integer]"
        if n.value < 4:
            return None
        vertices = [_int(i + 1) for i in range(n.value)]
        rim = list(range(1, n.value))
        edges = [(vertices[rim[i]], vertices[rim[(i + 1) % len(rim)]], False)
                 for i in range(len(rim))]
        edges += [(vertices[0], vertices[i], False) for i in rim]
        return _graph_expr(vertices, edges, with_vertex_list=True)


class GridGraph(Builtin):
    """
    <dl><dt>'GridGraph[{$m$, $n$}]'<dd>$m$ x $n$ grid graph; the vertex labels
    1..$m n$ run fastest along the first dimension (Wolfram's labeling).</dl>
    >> VertexCount[GridGraph[{2, 3}]]
     = 6
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "grid graph"

    def eval(self, dims, evaluation):
        "GridGraph[dims_List]"
        sizes = []
        for p in dims.elements:
            if not isinstance(p, Integer) or p.value < 1:
                return None
            sizes.append(p.value)
        import itertools

        def flat(idx):
            # first coordinate runs fastest (Wolfram's GridGraph labeling)
            v = 0
            for s, c in zip(reversed(sizes), reversed(idx)):
                v = v * s + c
            return v

        count = 1
        for s in sizes:
            count *= s
        vertices = [_int(i + 1) for i in range(count)]
        edges = []
        for idx in itertools.product(*[range(s) for s in sizes]):
            for axis in range(len(sizes)):
                if idx[axis] + 1 < sizes[axis]:
                    other = list(idx)
                    other[axis] += 1
                    edges.append((vertices[flat(idx)], vertices[flat(other)], False))
        return _graph_expr(vertices, edges, with_vertex_list=True)


class HypercubeGraph(Builtin):
    """
    <dl><dt>'HypercubeGraph[$d$]'<dd>$d$-dimensional hypercube on 2^$d$
    vertices; vertices i, j are adjacent when (i-1) and (j-1) differ in one
    bit.</dl>
    >> EdgeCount[HypercubeGraph[3]]
     = 12
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "hypercube graph"

    def eval(self, d, evaluation):
        "HypercubeGraph[d_Integer]"
        if d.value < 0:
            return None
        count = 1 << d.value
        vertices = [_int(i + 1) for i in range(count)]
        edges = []
        for i in range(count):
            for bit in range(d.value):
                j = i ^ (1 << bit)
                if i < j:
                    edges.append((vertices[i], vertices[j], False))
        return _graph_expr(vertices, edges, with_vertex_list=True)


# ---------------------------------------------------------------------------

def register_graphs2(session):
    for cls in (Subgraph, NeighborhoodGraph, GraphUnion, GraphIntersection,
                GraphDifference, GraphComplement, DirectedGraph, UndirectedGraph,
                AdjacencyGraph, IncidenceMatrix, KirchhoffMatrix, LineGraph,
                EdgeAdd, EdgeDelete, VertexAdd, VertexDelete, EdgeContract,
                GraphPower, TransitiveClosureGraph,
                IsomorphicGraphQ, BipartiteGraphQ, PlanarGraphQ,
                VertexConnectivity, EdgeConnectivity,
                ChromaticPolynomial, TuttePolynomial,
                FindClique, FindVertexCover, FindIndependentVertexSet,
                FindIndependentEdgeSet, FindMaximumFlow, FindMinimumCut,
                FindPath, FindCycle,
                DegreeCentrality, BetweennessCentrality, ClosenessCentrality,
                EigenvectorCentrality, PageRankCentrality,
                CompleteGraph, CycleGraph, PathGraph, StarGraph, WheelGraph,
                GridGraph, HypercubeGraph):
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
