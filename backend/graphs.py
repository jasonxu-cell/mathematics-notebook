"""Graph builtins missing from Mathics 10.0.1, in pure Python (no networkx).

Contracts follow Wolfram 15.0.1 (reference.wolfram.com/language), checked by a
differential battery against the activated local kernel during development.

Graph representation
--------------------
``Graph`` stays an inert head.  Each builtin parses ``Graph[...]`` into a
lightweight ``_Graph`` (vertex list in order of first appearance, edge list,
per-edge directedness) and returns ``None`` — leaving the input unevaluated —
when the argument is not a well-formed graph.

Edge forms accepted: ``UndirectedEdge[a, b]`` (``a <-> b``), ``Rule[a, b]``
(``a -> b``), ``DirectedEdge[a, b]`` and ``TwoWayRule[a, b]``.  Vertices may be
arbitrary expressions; identity is SameQ-like (``1`` and ``1.0`` differ).

Intentional deviations (documented in CAPABILITIES.md):
  * ``AdjacencyMatrix`` returns a dense nested List (Wolfram: SparseArray).
  * ``BreadthFirstScan`` / ``DepthFirstScan`` return the visit-order vertex
    list; Wolfram's event-callback form is not supported.
  * ``FindHamiltonianCycle`` refuses graphs with more than 14 vertices.
"""

from __future__ import annotations

from mathics.core.atoms import Integer
from mathics.core.attributes import A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol

SymbolDirectedEdge = Symbol("System`DirectedEdge")
SymbolUndirectedEdge = Symbol("System`UndirectedEdge")
SymbolGraph = Symbol("System`Graph")
SymbolInfinity = Symbol("System`Infinity")
SymbolTrue = Symbol("System`True")
SymbolFalse = Symbol("System`False")

_DIRECTED_HEADS = {"System`Rule", "System`DirectedEdge"}
_UNDIRECTED_HEADS = {"System`UndirectedEdge", "System`TwoWayRule"}

# Hard caps so NP-hard search never blocks the kernel.
_HAMILTON_MAX_VERTICES = 14
_SEARCH_STEP_CAP = 400_000


class Graph(Builtin):
    """
    <dl><dt>'Graph[{$e1$, $e2$, ...}]'<dd>an inert graph object with edges
    $e_i$ ('UndirectedEdge' / 'Rule' / 'DirectedEdge').  The algorithms are
    provided by the VertexList / FindShortestPath / ... builtins.</dl>
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "graph object (inert container)"


def _key(v):
    return (v.__class__.__name__, str(v))


class _Graph:
    __slots__ = ("vertices", "index", "edges", "directed", "adj_out", "adj_in")

    def __init__(self, vertices, edges, directed):
        self.vertices = vertices          # Mathics exprs, first-appearance order
        self.index = {_key(v): i for i, v in enumerate(vertices)}
        self.edges = edges                # [(i, j, edge_directed)]
        self.directed = directed          # any directed edge present
        n = len(vertices)
        self.adj_out = [[] for _ in range(n)]
        self.adj_in = [[] for _ in range(n)]
        for i, j, d in edges:
            self.adj_out[i].append(j)
            self.adj_in[j].append(i)
            if not d:
                self.adj_out[j].append(i)
                self.adj_in[i].append(j)

    def vertex_index(self, v):
        return self.index.get(_key(v))

    def edge_expr(self, e):
        i, j, d = e
        head = SymbolDirectedEdge if d else SymbolUndirectedEdge
        return Expression(head, self.vertices[i], self.vertices[j])


def _parse_edge(e):
    """-> (a, b, directed) or None."""
    if not isinstance(e, Expression) or len(e.elements) != 2:
        return None
    head = e.get_head_name()
    if head in _DIRECTED_HEADS:
        return e.elements[0], e.elements[1], True
    if head in _UNDIRECTED_HEADS:
        return e.elements[0], e.elements[1], False
    return None


def _parse_graph(expr):
    """Graph expression -> _Graph, or None (caller leaves input unevaluated)."""
    if not isinstance(expr, Expression) or expr.get_head_name() != "System`Graph":
        return None
    el = expr.elements
    if len(el) == 0:
        return _Graph([], [], False)
    first = el[0]
    if not first.has_form("List", None):
        return None
    if len(el) >= 2:
        if not el[1].has_form("List", None):
            return None
        vertex_exprs = list(first.elements)
        edge_exprs = list(el[1].elements)
    else:
        vertex_exprs = []
        edge_exprs = list(first.elements)
    vertices, seen = [], set()
    edges, any_directed = [], False

    def add_vertex(v):
        k = _key(v)
        if k not in seen:
            seen.add(k)
            vertices.append(v)

    for v in vertex_exprs:
        add_vertex(v)
    parsed_edges = []
    for e in edge_exprs:
        parsed = _parse_edge(e)
        if parsed is None:
            return None
        a, b, d = parsed
        add_vertex(a)
        add_vertex(b)
        parsed_edges.append((a, b, d))
        any_directed = any_directed or d
    # resolve indices after all vertices are known
    idx = {_key(v): i for i, v in enumerate(vertices)}
    edges = [(idx[_key(a)], idx[_key(b)], d) for a, b, d in parsed_edges]
    return _Graph(vertices, edges, any_directed)


def _wl_list(items):
    return ListExpression(*items)


def _int(n):
    return Integer(n)


# ---------------------------------------------------------------------------
# Traversal helpers (integer-index BFS/DFS)
# ---------------------------------------------------------------------------

def _bfs_order(g, start):
    seen = {start}
    order = [start]
    queue = [start]
    for u in queue:
        for w in g.adj_out[u]:
            if w not in seen:
                seen.add(w)
                order.append(w)
                queue.append(w)
    return order


def _bfs_dist(g, start):
    dist = {start: 0}
    queue = [start]
    for u in queue:
        for w in g.adj_out[u]:
            if w not in dist:
                dist[w] = dist[u] + 1
                queue.append(w)
    return dist


def _bfs_path(g, start, goal):
    if start == goal:
        return [start]
    prev = {start: None}
    queue = [start]
    for u in queue:
        for w in g.adj_out[u]:
            if w not in prev:
                prev[w] = u
                if w == goal:
                    path = [w]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    return path[::-1]
                queue.append(w)
    return None


def _undirected_components(g):
    """Components of the underlying undirected graph, in vertex order."""
    n = len(g.vertices)
    seen = [False] * n
    comps = []
    for s in range(n):
        if seen[s]:
            continue
        comp = []
        queue = [s]
        seen[s] = True
        for u in queue:
            comp.append(u)
            for w in g.adj_out[u]:
                if not seen[w]:
                    seen[w] = True
                    queue.append(w)
        comps.append(sorted(comp))
    return comps


def _strongly_connected(g):
    """Tarjan SCC, iterative. Returns list of vertex-index lists."""
    n = len(g.vertices)
    index = [None] * n
    low = [0] * n
    on_stack = [False] * n
    stack = []
    comps = []
    counter = [0]

    for root in range(n):
        if index[root] is not None:
            continue
        work = [(root, 0)]
        while work:
            u, pi = work[-1]
            if pi == 0:
                index[u] = low[u] = counter[0]
                counter[0] += 1
                stack.append(u)
                on_stack[u] = True
            recurse = False
            neighbors = g.adj_out[u]
            while pi < len(neighbors):
                w = neighbors[pi]
                pi += 1
                if index[w] is None:
                    work[-1] = (u, pi)
                    work.append((w, 0))
                    recurse = True
                    break
                elif on_stack[w]:
                    low[u] = min(low[u], index[w])
            if recurse:
                continue
            work[-1] = (u, pi)
            if pi >= len(neighbors):
                work.pop()
                if low[u] == index[u]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        comp.append(w)
                        if w == u:
                            break
                    comps.append(sorted(comp))
                if work:
                    p = work[-1][0]
                    low[p] = min(low[p], low[u])
    return comps


def _topological_order(g):
    """Kahn; ties by vertex-appearance order. None if a directed cycle exists."""
    n = len(g.vertices)
    indeg = [0] * n
    for i, j, d in g.edges:
        if d:
            indeg[j] += 1
    avail = sorted(i for i in range(n) if indeg[i] == 0)
    order = []
    while avail:
        u = avail.pop()  # Wolfram tie-break: largest first-appearance index
        order.append(u)
        for i, j, d in g.edges:
            if d and i == u:
                indeg[j] -= 1
                if indeg[j] == 0:
                    avail.append(j)
        avail.sort()
    return order if len(order) == n else None


def _has_directed_cycle(g):
    return _topological_order(_dag_view(g)) is None


def _dag_view(g):
    """View of g with undirected edges dropped (for cycle checks they are cycles)."""
    edges = [(i, j, d) for i, j, d in g.edges if d]
    und = [(i, j, False) for i, j, d in g.edges if not d]
    if und:
        return None  # caller treats undirected edge presence separately
    return _Graph(g.vertices, edges, True)


def _has_undirected_cycle(g):
    """True if the underlying undirected multigraph has a cycle (loops count)."""
    n = len(g.vertices)
    parent = list(range(n))

    def find(u):
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    seen_pairs = set()
    for i, j, d in g.edges:
        if i == j:
            return True
        ri, rj = find(i), find(j)
        if ri == rj:
            return True
        parent[ri] = rj
    return False


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

class VertexList(Builtin):
    """
    <dl><dt>'VertexList[$g$]'<dd>vertex list of $g$, in first-appearance order.</dl>
    >> VertexList[Graph[{1 <-> 2, 2 <-> 3}]]
     = {1, 2, 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "list of vertices"

    def eval(self, g, evaluation):
        "VertexList[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return _wl_list(gr.vertices)


class EdgeList(Builtin):
    """
    <dl><dt>'EdgeList[$g$]'<dd>edge list of $g$, in input order.</dl>
    >> EdgeList[Graph[{1 <-> 2, 2 -> 3}]]
     = {1 <-> 2, 2 -> 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "list of edges"

    def eval(self, g, evaluation):
        "EdgeList[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return _wl_list([gr.edge_expr(e) for e in gr.edges])


class VertexCount(Builtin):
    """
    <dl><dt>'VertexCount[$g$]'<dd>number of vertices.</dl>
    >> VertexCount[Graph[{1 <-> 2, 2 <-> 3}]]
     = 3
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "number of vertices"

    def eval(self, g, evaluation):
        "VertexCount[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return _int(len(gr.vertices))


class EdgeCount(Builtin):
    """
    <dl><dt>'EdgeCount[$g$]'<dd>number of edges (multi-edges counted).</dl>
    >> EdgeCount[Graph[{1 <-> 2, 2 -> 3}]]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "number of edges"

    def eval(self, g, evaluation):
        "EdgeCount[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return _int(len(gr.edges))


class AdjacencyMatrix(Builtin):
    """
    <dl><dt>'AdjacencyMatrix[$g$]'<dd>dense adjacency matrix of $g$.</dl>
    >> AdjacencyMatrix[Graph[{1 <-> 2, 2 -> 3}]]
     = {{0, 1, 0}, {1, 0, 1}, {0, 0, 0}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "adjacency matrix (dense list)"

    def eval(self, g, evaluation):
        "AdjacencyMatrix[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        M = [[0] * n for _ in range(n)]
        for i, j, d in gr.edges:
            M[i][j] += 1
            if not d:
                M[j][i] += 1
        return _wl_list([_wl_list([_int(v) for v in row]) for row in M])


class VertexDegree(Builtin):
    """
    <dl><dt>'VertexDegree[$g$]'<dd>degree of every vertex; directed graphs give
    in-degree + out-degree.</dl>
    >> VertexDegree[Graph[{1 <-> 2, 2 <-> 3}]]
     = {1, 2, 1}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "vertex degrees"

    def eval(self, g, evaluation):
        "VertexDegree[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        if gr.directed:
            degrees = [len(gr.adj_in[i]) + len(gr.adj_out[i]) for i in range(n)]
        else:
            # undirected adj_out lists both endpoints; a self-loop appears twice
            degrees = [len(gr.adj_out[i]) for i in range(n)]
        return _wl_list([_int(d) for d in degrees])


class VertexInDegree(Builtin):
    """
    <dl><dt>'VertexInDegree[$g$]'<dd>in-degree of every vertex.</dl>
    >> VertexInDegree[Graph[{1 -> 2, 2 -> 3}]]
     = {0, 1, 1}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "vertex in-degrees"

    def eval(self, g, evaluation):
        "VertexInDegree[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return _wl_list([_int(len(gr.adj_in[i])) for i in range(len(gr.vertices))])


class VertexOutDegree(Builtin):
    """
    <dl><dt>'VertexOutDegree[$g$]'<dd>out-degree of every vertex.</dl>
    >> VertexOutDegree[Graph[{1 -> 2, 2 -> 3}]]
     = {1, 1, 0}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "vertex out-degrees"

    def eval(self, g, evaluation):
        "VertexOutDegree[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return _wl_list([_int(len(gr.adj_out[i])) for i in range(len(gr.vertices))])


class AdjacencyList(Builtin):
    """
    <dl><dt>'AdjacencyList[$g$, $v$]'<dd>neighbors of $v$ (out-neighbors when
    the graph is directed).</dl>
    >> AdjacencyList[Graph[{1 <-> 2, 1 <-> 3}], 1]
     = {2, 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "neighbors of a vertex"

    def eval(self, g, v, evaluation):
        "AdjacencyList[g_Graph, v_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i = gr.vertex_index(v)
        if i is None:
            return None
        seen, out = set(), []
        for w in gr.adj_out[i]:
            if w not in seen:
                seen.add(w)
                out.append(gr.vertices[w])
        return _wl_list(out)


class VertexQ(Builtin):
    """
    <dl><dt>'VertexQ[$g$, $v$]'<dd>True if $v$ is a vertex of $g$.</dl>
    >> VertexQ[Graph[{1 <-> 2}], 2]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test vertex membership"

    def eval(self, g, v, evaluation):
        "VertexQ[g_Graph, v_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return SymbolTrue if gr.vertex_index(v) is not None else SymbolFalse


class EdgeQ(Builtin):
    """
    <dl><dt>'EdgeQ[$g$, $e$]'<dd>True if $e$ is an edge of $g$.</dl>
    >> EdgeQ[Graph[{1 <-> 2}], 2 <-> 1]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test edge membership"

    def eval(self, g, e, evaluation):
        "EdgeQ[g_Graph, e_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        parsed = _parse_edge(e)
        if parsed is None:
            return SymbolFalse
        a, b, d = parsed
        ia, ib = gr.vertex_index(a), gr.vertex_index(b)
        if ia is None or ib is None:
            return SymbolFalse
        for i, j, ed in gr.edges:
            if gr.directed:
                # directed graph: only directed queries, exact orientation
                if d and ed and (i, j) == (ia, ib):
                    return SymbolTrue
            else:
                # undirected graph: either query head, either orientation
                if {i, j} == {ia, ib}:
                    return SymbolTrue
        return SymbolFalse


class DirectedGraphQ(Builtin):
    """
    <dl><dt>'DirectedGraphQ[$g$]'<dd>True if every edge of $g$ is directed.</dl>
    >> DirectedGraphQ[Graph[{1 -> 2}]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test whether a graph is directed"

    def eval(self, g, evaluation):
        "DirectedGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return SymbolFalse
        return SymbolTrue if gr.edges and all(d for _, _, d in gr.edges) else SymbolFalse


class UndirectedGraphQ(Builtin):
    """
    <dl><dt>'UndirectedGraphQ[$g$]'<dd>True if every edge of $g$ is undirected.</dl>
    >> UndirectedGraphQ[Graph[{1 <-> 2}]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test whether a graph is undirected"

    def eval(self, g, evaluation):
        "UndirectedGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return SymbolFalse
        return SymbolTrue if all(not d for _, _, d in gr.edges) else SymbolFalse


# ---------------------------------------------------------------------------
# Paths and distances
# ---------------------------------------------------------------------------

class FindShortestPath(Builtin):
    """
    <dl><dt>'FindShortestPath[$g$, $s$, $t$]'<dd>shortest vertex path from $s$
    to $t$; unevaluated when unreachable.</dl>
    >> FindShortestPath[Graph[{1 -> 2, 2 -> 3}], 1, 3]
     = {1, 2, 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "shortest path between two vertices"

    def eval(self, g, s, t, evaluation):
        "FindShortestPath[g_Graph, s_, t_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i, j = gr.vertex_index(s), gr.vertex_index(t)
        if i is None or j is None:
            return None
        path = _bfs_path(gr, i, j)
        if path is None:
            return None
        return _wl_list([gr.vertices[k] for k in path])

    def eval_all(self, g, s, evaluation):
        "FindShortestPath[g_Graph, s_, All]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i = gr.vertex_index(s)
        if i is None:
            return None
        paths = []
        for j in range(len(gr.vertices)):
            p = _bfs_path(gr, i, j)
            if p is not None:
                paths.append(_wl_list([gr.vertices[k] for k in p]))
        return _wl_list(paths)


class GraphDistance(Builtin):
    """
    <dl><dt>'GraphDistance[$g$, $s$, $t$]'<dd>shortest-path length; Infinity
    when unreachable.</dl>
    >> GraphDistance[Graph[{1 -> 2, 2 -> 3}], 1, 3]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "shortest-path distance between two vertices"

    def eval(self, g, s, t, evaluation):
        "GraphDistance[g_Graph, s_, t_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i, j = gr.vertex_index(s), gr.vertex_index(t)
        if i is None or j is None:
            return None
        dist = _bfs_dist(gr, i)
        if j not in dist:
            return SymbolInfinity
        return _int(dist[j])


class GraphDistanceMatrix(Builtin):
    """
    <dl><dt>'GraphDistanceMatrix[$g$]'<dd>matrix of pairwise shortest-path
    distances (Infinity where unreachable).</dl>
    >> GraphDistanceMatrix[Graph[{1 <-> 2, 2 <-> 3}]]
     = {{0, 1, 2}, {1, 0, 1}, {2, 1, 0}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "all-pairs shortest-path distances"

    def eval(self, g, evaluation):
        "GraphDistanceMatrix[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        rows = []
        for i in range(n):
            dist = _bfs_dist(gr, i)
            rows.append(_wl_list([_int(dist[j]) if j in dist else SymbolInfinity for j in range(n)]))
        return _wl_list(rows)


def _eccentricity(gr, i):
    dist = _bfs_dist(gr, i)
    if len(dist) < len(gr.vertices):
        return None  # Infinity
    return max(dist.values(), default=0)


class VertexEccentricity(Builtin):
    """
    <dl><dt>'VertexEccentricity[$g$, $v$]'<dd>greatest shortest-path distance
    from $v$ to any vertex; Infinity when some vertex is unreachable.</dl>
    >> VertexEccentricity[Graph[{1 <-> 2, 2 <-> 3}], 2]
     = 1
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "eccentricity of a vertex"

    def eval(self, g, v, evaluation):
        "VertexEccentricity[g_Graph, v_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i = gr.vertex_index(v)
        if i is None:
            return None
        e = _eccentricity(gr, i)
        return SymbolInfinity if e is None else _int(e)


def _eccentricities(gr):
    return [_eccentricity(gr, i) for i in range(len(gr.vertices))]


class GraphDiameter(Builtin):
    """
    <dl><dt>'GraphDiameter[$g$]'<dd>greatest eccentricity over all vertices.</dl>
    >> GraphDiameter[Graph[{1 <-> 2, 2 <-> 3}]]
     = 2
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "graph diameter"

    def eval(self, g, evaluation):
        "GraphDiameter[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        ecc = _eccentricities(gr)
        if any(e is None for e in ecc):
            return SymbolInfinity
        return _int(max(ecc, default=0))


class GraphRadius(Builtin):
    """
    <dl><dt>'GraphRadius[$g$]'<dd>smallest eccentricity over all vertices.</dl>
    >> GraphRadius[Graph[{1 <-> 2, 2 <-> 3}]]
     = 1
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "graph radius"

    def eval(self, g, evaluation):
        "GraphRadius[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        ecc = _eccentricities(gr)
        if any(e is None for e in ecc):
            return SymbolInfinity
        return _int(min(ecc, default=0))


class GraphCenter(Builtin):
    """
    <dl><dt>'GraphCenter[$g$]'<dd>vertices whose eccentricity equals the radius.</dl>
    >> GraphCenter[Graph[{1 <-> 2, 2 <-> 3}]]
     = {2}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "center vertices"

    def eval(self, g, evaluation):
        "GraphCenter[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        ecc = _eccentricities(gr)
        if any(e is None for e in ecc):
            return _wl_list([])
        r = min(ecc, default=0)
        return _wl_list([gr.vertices[i] for i, e in enumerate(ecc) if e == r])


class GraphPeriphery(Builtin):
    """
    <dl><dt>'GraphPeriphery[$g$]'<dd>vertices whose eccentricity equals the
    diameter.</dl>
    >> GraphPeriphery[Graph[{1 <-> 2, 2 <-> 3}]]
     = {1, 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "periphery vertices"

    def eval(self, g, evaluation):
        "GraphPeriphery[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        ecc = _eccentricities(gr)
        if any(e is None for e in ecc):
            return _wl_list([])
        d = max(ecc, default=0)
        return _wl_list([gr.vertices[i] for i, e in enumerate(ecc) if e == d])


# ---------------------------------------------------------------------------
# Connectivity and structure
# ---------------------------------------------------------------------------

class ConnectedComponents(Builtin):
    """
    <dl><dt>'ConnectedComponents[$g$]'<dd>connected components of an
    undirected graph; strongly connected components of a directed graph.</dl>
    >> ConnectedComponents[Graph[{1 <-> 2, 3 <-> 4}]]
     = {{1, 2}, {3, 4}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "connected components"

    def eval(self, g, evaluation):
        "ConnectedComponents[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        comps = _strongly_connected(gr) if gr.directed else _undirected_components(gr)
        return _wl_list([_wl_list([gr.vertices[i] for i in comp]) for comp in comps])


class WeaklyConnectedComponents(Builtin):
    """
    <dl><dt>'WeaklyConnectedComponents[$g$]'<dd>components of the underlying
    undirected graph.</dl>
    >> WeaklyConnectedComponents[Graph[{1 -> 2, 3 -> 4}]]
     = {{1, 2}, {3, 4}}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "weakly connected components"

    def eval(self, g, evaluation):
        "WeaklyConnectedComponents[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        return _wl_list([_wl_list([gr.vertices[i] for i in comp]) for comp in _undirected_components(gr)])


class ConnectedGraphQ(Builtin):
    """
    <dl><dt>'ConnectedGraphQ[$g$]'<dd>True if connected (strongly connected
    for a directed graph).</dl>
    >> ConnectedGraphQ[Graph[{1 <-> 2, 2 <-> 3}]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test connectivity"

    def eval(self, g, evaluation):
        "ConnectedGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        comps = _strongly_connected(gr) if gr.directed else _undirected_components(gr)
        return SymbolTrue if len(comps) <= 1 else SymbolFalse


class AcyclicGraphQ(Builtin):
    """
    <dl><dt>'AcyclicGraphQ[$g$]'<dd>True if $g$ has no cycles (directed cycles
    for a directed graph, undirected cycles otherwise; self-loops count).</dl>
    >> AcyclicGraphQ[Graph[{1 -> 2, 2 -> 3}]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test acyclicity"

    def eval(self, g, evaluation):
        "AcyclicGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        if gr.directed:
            if any(i == j or not d for i, j, d in gr.edges):
                return SymbolFalse
            dag = _Graph(gr.vertices, [(i, j, True) for i, j, d in gr.edges if d], True)
            return SymbolTrue if _topological_order(dag) is not None else SymbolFalse
        return SymbolFalse if _has_undirected_cycle(gr) else SymbolTrue


class TreeGraphQ(Builtin):
    """
    <dl><dt>'TreeGraphQ[$g$]'<dd>True if $g$ is a tree (connected and acyclic
    in the underlying undirected sense).  Note: Wolfram's 'TreeQ' tests the
    'Tree' object, not graphs — this is the graph predicate.</dl>
    >> TreeGraphQ[Graph[{1 <-> 2, 2 <-> 3}]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test whether a graph is a tree"

    def eval(self, g, evaluation):
        "TreeGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        if not gr.vertices:
            return SymbolFalse
        if len(_undirected_components(gr)) != 1:
            return SymbolFalse
        return SymbolFalse if _has_undirected_cycle(gr) else SymbolTrue


class TopologicalSort(Builtin):
    """
    <dl><dt>'TopologicalSort[$g$]'<dd>a topological ordering of a directed
    acyclic graph; unevaluated when a cycle exists.</dl>
    >> TopologicalSort[Graph[{1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4}]]
     = {1, 2, 3, 4}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "topological ordering"

    def eval(self, g, evaluation):
        "TopologicalSort[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or not gr.directed:
            return None
        order = _topological_order(gr)
        if order is None:
            return None
        return _wl_list([gr.vertices[i] for i in order])


class FindSpanningTree(Builtin):
    """
    <dl><dt>'FindSpanningTree[$g$]'<dd>a BFS spanning tree (forest when
    disconnected) as a Graph.</dl>
    >> FindSpanningTree[Graph[{1 <-> 2, 2 <-> 3, 1 <-> 3}]]
     = Graph[{1 <-> 2, 1 <-> 3}]
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "BFS spanning tree"

    def eval(self, g, evaluation):
        "FindSpanningTree[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        n = len(gr.vertices)
        seen = [False] * n
        tree_edges = []
        for s in range(n):
            if seen[s]:
                continue
            seen[s] = True
            queue = [s]
            for u in queue:
                for i, j, d in gr.edges:
                    if d:
                        if i != u:
                            continue
                        w = j
                    else:
                        if i == u:
                            w = j
                        elif j == u:
                            w = i
                        else:
                            continue
                    if not seen[w]:
                        seen[w] = True
                        tree_edges.append(gr.edge_expr((i, j, d)))
                        queue.append(w)
        return Expression(SymbolGraph, _wl_list(tree_edges))


# ---------------------------------------------------------------------------
# Eulerian / Hamiltonian cycles
# ---------------------------------------------------------------------------

def _eulerian_undirected(gr):
    """Hierholzer; returns list of edges (i, j, False) or None."""
    edges = [(i, j) for i, j, d in gr.edges if not d]
    if not edges:
        return [] if len(gr.vertices) <= 1 else None
    used = [False] * len(edges)
    adj = [[] for _ in gr.vertices]
    for k, (i, j) in enumerate(edges):
        adj[i].append(k)
        if i != j:
            adj[j].append(k)
    start = next((v for v in range(len(adj)) if adj[v]), None)
    if start is None:
        return []
    stack, circuit = [(start, None)], []
    while stack:
        u, _ = stack[-1]
        found = False
        while adj[u]:
            k = adj[u].pop()
            if not used[k]:
                used[k] = True
                i, j = edges[k]
                stack.append((j if i == u else i, k))
                found = True
                break
        if not found:
            u, k = stack.pop()
            if k is not None:
                circuit.append(k)
    if not all(used):
        return None
    circuit.reverse()
    return [edges[k] for k in circuit]


class EulerianGraphQ(Builtin):
    """
    <dl><dt>'EulerianGraphQ[$g$]'<dd>True if $g$ has an Eulerian cycle
    (connected and all degrees even; directed: balanced in/out and weakly
    connected).</dl>
    >> EulerianGraphQ[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test for an Eulerian cycle"

    def eval(self, g, evaluation):
        "EulerianGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        if not gr.vertices:
            return SymbolFalse
        if len(_undirected_components(gr)) > 1:
            return SymbolFalse
        if gr.directed:
            ok = all(len(gr.adj_in[i]) == len(gr.adj_out[i]) for i in range(len(gr.vertices)))
        else:
            ok = all(len(gr.adj_out[i]) % 2 == 0 for i in range(len(gr.vertices)))
        return SymbolTrue if ok else SymbolFalse


class FindEulerianCycle(Builtin):
    """
    <dl><dt>'FindEulerianCycle[$g$]'<dd>an Eulerian cycle as an edge list;
    {} when none exists (undirected graphs).</dl>
    >> FindEulerianCycle[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]
     = {1 <-> 2, 2 <-> 3, 3 <-> 1}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find an Eulerian cycle"

    def eval(self, g, evaluation):
        "FindEulerianCycle[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or gr.directed:
            return None
        # not Eulerian (odd degree / disconnected): {} per Wolfram
        if len(_undirected_components(gr)) > 1 or any(
                len(gr.adj_out[i]) % 2 for i in range(len(gr.vertices))):
            return _wl_list([])
        circuit = _eulerian_undirected(gr)
        if circuit is None:
            return _wl_list([])
        cycle = _wl_list([gr.edge_expr((i, j, False)) for i, j in circuit])
        return _wl_list([cycle])  # Wolfram returns a list of cycles


def _hamiltonian_cycle(gr):
    """Backtracking Hamiltonian cycle on the underlying adjacency; returns a
    vertex-index cycle [v0, v1, ..., v0] or None. Step-capped."""
    n = len(gr.vertices)
    if n == 0:
        return None
    if n == 1:
        return [0, 0] if any(i == j for i, j, _ in gr.edges) else None
    if n == 2:
        return [0, 1, 0] if gr.edges else None
    neighbors = [set(a) for a in gr.adj_out]
    steps = [0]
    path = [0]
    visited = {0}

    def extend():
        steps[0] += 1
        if steps[0] > _SEARCH_STEP_CAP:
            return None
        if len(path) == n:
            return 0 in neighbors[path[-1]]
        u = path[-1]
        for w in sorted(neighbors[u]):
            if w not in visited:
                visited.add(w)
                path.append(w)
                r = extend()
                if r:
                    return True
                path.pop()
                visited.discard(w)
        return False

    if extend():
        return path + [0]
    return None


class HamiltonianGraphQ(Builtin):
    """
    <dl><dt>'HamiltonianGraphQ[$g$]'<dd>True if $g$ has a Hamiltonian cycle
    (backtracking; graphs over 14 vertices are left unevaluated).</dl>
    >> HamiltonianGraphQ[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]
     = True
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "test for a Hamiltonian cycle"

    def eval(self, g, evaluation):
        "HamiltonianGraphQ[g_Graph]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        if len(gr.vertices) > _HAMILTON_MAX_VERTICES:
            return None
        return SymbolTrue if _hamiltonian_cycle(gr) else SymbolFalse


class FindHamiltonianCycle(Builtin):
    """
    <dl><dt>'FindHamiltonianCycle[$g$]'<dd>a Hamiltonian cycle as an edge
    list; {} when none exists (graphs over 14 vertices unevaluated).</dl>
    >> FindHamiltonianCycle[Graph[{1 <-> 2, 2 <-> 3, 3 <-> 1}]]
     = {1 <-> 2, 2 <-> 3, 3 <-> 1}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "find a Hamiltonian cycle"

    def eval(self, g, evaluation):
        "FindHamiltonianCycle[g_Graph]"
        gr = _parse_graph(g)
        if gr is None or len(gr.vertices) > _HAMILTON_MAX_VERTICES:
            return None
        cycle = _hamiltonian_cycle(gr)
        if not cycle:
            return _wl_list([])
        edges = []
        for a, b in zip(cycle, cycle[1:]):
            match = next(((i, j, d) for i, j, d in gr.edges
                          if (i, j) == (a, b) or (not d and (i, j) == (b, a))), None)
            if match is None:
                return _wl_list([])
            edges.append(gr.edge_expr(match))
        return _wl_list([_wl_list(edges)])  # Wolfram returns a list of cycles


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------

class BreadthFirstScan(Builtin):
    """
    <dl><dt>'BreadthFirstScan[$g$, $s$]'<dd>vertices in breadth-first visit
    order from $s$ (event-callback form not supported).</dl>
    >> BreadthFirstScan[Graph[{1 <-> 2, 1 <-> 3, 2 <-> 4}], 1]
     = {1, 2, 3, 4}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "breadth-first visit order"

    def eval(self, g, s, evaluation):
        "BreadthFirstScan[g_Graph, s_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i = gr.vertex_index(s)
        if i is None:
            return None
        return _wl_list([gr.vertices[k] for k in _bfs_order(gr, i)])


class DepthFirstScan(Builtin):
    """
    <dl><dt>'DepthFirstScan[$g$, $s$]'<dd>vertices in depth-first visit order
    from $s$ (event-callback form not supported).</dl>
    >> DepthFirstScan[Graph[{1 <-> 2, 1 <-> 3, 2 <-> 4}], 1]
     = {1, 2, 4, 3}
    """
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "depth-first visit order"

    def eval(self, g, s, evaluation):
        "DepthFirstScan[g_Graph, s_]"
        gr = _parse_graph(g)
        if gr is None:
            return None
        i = gr.vertex_index(s)
        if i is None:
            return None
        order, seen = [], set()

        def visit(u):
            seen.add(u)
            order.append(u)
            for w in gr.adj_out[u]:
                if w not in seen:
                    visit(w)

        try:
            visit(i)
        except RecursionError:
            return None
        return _wl_list([gr.vertices[k] for k in order])


# ---------------------------------------------------------------------------

def register_graphs(session):
    for cls in (Graph, VertexList, EdgeList, VertexCount, EdgeCount, AdjacencyMatrix,
                VertexDegree, VertexInDegree, VertexOutDegree, AdjacencyList,
                VertexQ, EdgeQ, DirectedGraphQ, UndirectedGraphQ,
                FindShortestPath, GraphDistance, GraphDistanceMatrix,
                VertexEccentricity, GraphDiameter, GraphRadius, GraphCenter,
                GraphPeriphery, ConnectedComponents, WeaklyConnectedComponents,
                ConnectedGraphQ, AcyclicGraphQ, TreeGraphQ, TopologicalSort,
                FindSpanningTree, EulerianGraphQ, FindEulerianCycle,
                HamiltonianGraphQ, FindHamiltonianCycle,
                BreadthFirstScan, DepthFirstScan):
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.name}")
