"""
File    : student1_search/search_module.py
Module  : Search & Navigation
Owner   : Student 1

Purpose : Finds routes on the campus graph.
          Operational algorithms : BFS, UCS, A*   (chosen by select_algorithm)
          Comparison algorithms  : DFS, DLS, IDS, Bidirectional BFS,
                                   Greedy Best-First, RBFS
          Entry point for the integration layer: run_search(request, csp_output).

Rules   : imports only from shared/, never prints, never reads input.

Result dict returned by EVERY algorithm:
          algorithm_used, path, cost, steps, nodes_expanded, time_ms, found,
          expanded_order
          (steps = number of edges in the path; nodes_expanded = nodes taken
          off the frontier and examined, including the goal node;
          expanded_order = those nodes in the order they were expanded, used
          by the web UI to animate the search.)
          DLS adds one extra key, "cutoff" (True if the depth limit stopped it).
"""

import sys
import os
import math
import time
import heapq
import difflib
from collections import deque

# Make "shared" importable when this file is run directly from its folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.campus_data import NODES, EDGES
from shared.templates import new_template, SEARCH_OUTPUT_TEMPLATE

INF = float("inf")
DEFAULT_DLS_LIMIT = 5

ALGORITHM_ORDER = ["BFS", "UCS", "A*", "DFS", "DLS", "IDS",
                   "Bidirectional BFS", "Greedy Best-First", "RBFS"]


# ===========================================================================
# 1. Graph and heuristic
# ===========================================================================
def build_graph(weighted=True):
    """
    Function: build_graph
    Purpose : Build an adjacency dict from the shared campus data.
              Weighted view uses the real edge costs; unweighted view gives
              every edge cost 1 (same 19 connections).
    Params  : weighted (bool) - True for real costs, False for cost 1
    Returns : dict {node: {neighbour: cost}}
    """
    graph = {node: {} for node in NODES}
    for a, b, cost in EDGES:
        c = cost if weighted else 1
        graph[a][b] = c
        graph[b][a] = c
    return graph


WEIGHTED_GRAPH = build_graph(True)
UNWEIGHTED_GRAPH = build_graph(False)


def euclid(a, b):
    """
    Function: euclid
    Purpose : Straight-line distance between two nodes using the diagram
              coordinates.
    Params  : a, b (str) - node names
    Returns : float
    """
    (x1, y1), (x2, y2) = NODES[a], NODES[b]
    return math.hypot(x1 - x2, y1 - y2)


def compute_k():
    """
    Function: compute_k
    Purpose : Compute the heuristic scale factor k = min(edge_cost / euclid)
              over all edges. On this map that is 1/3 (Admin_Block ->
              Student_Services: cost 1, straight-line 3).
    Params  : none
    Returns : float
    """
    return min(cost / euclid(a, b) for a, b, cost in EDGES)


# Why not raw Euclidean distance?  On this diagram the edge costs are NOT
# proportional to the drawn distances. 12 of the 19 edges are cheaper than
# their straight-line length (e.g. Admin_Block-Exam_Hall costs 2 but is 5
# units apart). A heuristic that is larger than the true cost is not
# admissible, so A* could return a wrong (non-optimal) route.
# Scaling by k, the smallest cost/distance ratio of any edge, makes
# k * euclid(a, b) <= cost(a, b) for every edge. Then h never overestimates
# (admissible) and h(a) <= cost(a, b) + h(b) (consistent), so A* is optimal.
K = compute_k()


def heuristic(node, goal):
    """
    Function: heuristic
    Purpose : Admissible and consistent estimate h(n) = k * euclid(n, goal).
    Params  : node (str), goal (str)
    Returns : float
    """
    return K * euclid(node, goal)


# ===========================================================================
# 2. Small helpers shared by the algorithms
# ===========================================================================
def neighbours(graph, node):
    """
    Function: neighbours
    Purpose : Neighbours of a node in alphabetical order (keeps results
              deterministic).
    Params  : graph (dict), node (str)
    Returns : list of str
    """
    return sorted(graph[node])


def path_cost(graph, path):
    """
    Function: path_cost
    Purpose : Total edge cost along a path in the given graph view.
    Params  : graph (dict), path (list of str)
    Returns : int or float
    """
    return sum(graph[path[i]][path[i + 1]] for i in range(len(path) - 1))


def make_result(name, path, graph, expanded, start_time, found=True):
    """
    Function: make_result
    Purpose : Build the standard result dict returned by every algorithm.
    Params  : name (str) - algorithm name
              path (list) - node list (ignored if not found)
              graph (dict) - graph view used to compute the cost
              expanded (list) - the expanded nodes, in expansion order
              start_time (float) - time.perf_counter() value at the start
              found (bool)
    Returns : dict
    """
    result = new_template(SEARCH_OUTPUT_TEMPLATE)
    result["algorithm_used"] = name
    if found:
        result["path"] = list(path)
        result["cost"] = path_cost(graph, path)
        result["steps"] = len(path) - 1
    result["nodes_expanded"] = len(expanded)
    result["time_ms"] = (time.perf_counter() - start_time) * 1000
    result["found"] = found
    result["expanded_order"] = list(expanded)
    return result


def trace(parent, node):
    """
    Function: trace
    Purpose : Follow parent links from node back to the root of its search.
    Params  : parent (dict) - child -> parent (root maps to None)
              node (str)
    Returns : list of str, [node, ..., root]
    """
    out = []
    while node is not None:
        out.append(node)
        node = parent[node]
    return out


# ===========================================================================
# 3. Operational algorithms: BFS, UCS, A*
# ===========================================================================
def bfs(graph, source, goal):
    """
    Function: bfs
    Purpose : Breadth-First Search - fewest edges (right choice for the
              unweighted view).
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    parent = {source: None}
    queue = deque([source])
    expanded = []
    while queue:
        node = queue.popleft()
        expanded.append(node)
        if node == goal:
            return make_result("BFS", trace(parent, node)[::-1], graph, expanded, start)
        for nb in neighbours(graph, node):
            if nb not in parent:
                parent[nb] = node
                queue.append(nb)
    return make_result("BFS", [], graph, expanded, start, found=False)


def ucs(graph, source, goal):
    """
    Function: ucs
    Purpose : Uniform-Cost Search - cheapest route by g(n) only (weighted
              graph without a heuristic).
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    best_g = {source: 0}
    counter = 0                      # tie-breaker so the heap never compares paths
    heap = [(0, counter, source, [source])]
    expanded = []
    while heap:
        g, _, node, path = heapq.heappop(heap)
        if g > best_g[node]:
            continue                 # stale entry, a cheaper one was already used
        expanded.append(node)
        if node == goal:
            return make_result("UCS", path, graph, expanded, start)
        for nb in neighbours(graph, node):
            g2 = g + graph[node][nb]
            if g2 < best_g.get(nb, INF):
                best_g[nb] = g2
                counter += 1
                heapq.heappush(heap, (g2, counter, nb, path + [nb]))
    return make_result("UCS", [], graph, expanded, start, found=False)


def a_star(graph, source, goal):
    """
    Function: a_star
    Purpose : A* Search - orders the frontier by f(n) = g(n) + h(n) using the
              scaled Euclidean heuristic (admissible, so the route is optimal).
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    best_g = {source: 0}
    counter = 0
    heap = [(heuristic(source, goal), counter, 0, source, [source])]
    expanded = []
    while heap:
        _, _, g, node, path = heapq.heappop(heap)
        if g > best_g[node]:
            continue
        expanded.append(node)
        if node == goal:
            return make_result("A*", path, graph, expanded, start)
        for nb in neighbours(graph, node):
            g2 = g + graph[node][nb]
            if g2 < best_g.get(nb, INF):
                best_g[nb] = g2
                counter += 1
                heapq.heappush(heap, (g2 + heuristic(nb, goal), counter, g2, nb, path + [nb]))
    return make_result("A*", [], graph, expanded, start, found=False)


# ===========================================================================
# 4. Comparison algorithms
# ===========================================================================
def dfs(graph, source, goal):
    """
    Function: dfs
    Purpose : Depth-First Search - goes deep first; finds a path but not
              necessarily the shortest or cheapest one.
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    visited = set()
    stack = [(source, [source])]
    expanded = []
    while stack:
        node, path = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        expanded.append(node)
        if node == goal:
            return make_result("DFS", path, graph, expanded, start)
        for nb in reversed(neighbours(graph, node)):   # reversed -> alphabetical first
            if nb not in visited:
                stack.append((nb, path + [nb]))
    return make_result("DFS", [], graph, expanded, start, found=False)


def dls_core(graph, source, goal, limit):
    """
    Function: dls_core
    Purpose : Recursive depth-limited search used by DLS and IDS.
              Avoids cycles by never revisiting a node on the current path.
    Params  : graph (dict), source (str), goal (str), limit (int) - max edges
    Returns : tuple (path or None, cutoff (bool), expanded (list of nodes, in order))
    """
    expanded = []

    def recurse(node, path, depth_left):
        """
        Function: recurse
        Purpose : Explore one node; stop when depth_left reaches 0.
        Params  : node (str), path (list), depth_left (int)
        Returns : tuple (path or None, cutoff (bool))
        """
        expanded.append(node)
        if node == goal:
            return path, False
        if depth_left == 0:
            return None, True
        cutoff = False
        for nb in neighbours(graph, node):
            if nb in path:
                continue
            found, cut = recurse(nb, path + [nb], depth_left - 1)
            if found is not None:
                return found, False
            cutoff = cutoff or cut
        return None, cutoff

    path, cutoff = recurse(source, [source], limit)
    return path, cutoff, expanded


def dls(graph, source, goal, limit=DEFAULT_DLS_LIMIT):
    """
    Function: dls
    Purpose : Depth-Limited Search - DFS that stops at a depth limit.
              If it fails because of the limit, "cutoff" is True.
    Params  : graph (dict), source (str), goal (str), limit (int)
    Returns : result dict (with the extra key "cutoff")
    """
    start = time.perf_counter()
    path, cutoff, expanded = dls_core(graph, source, goal, limit)
    if path is None:
        result = make_result("DLS", [], graph, expanded, start, found=False)
    else:
        result = make_result("DLS", path, graph, expanded, start)
    result["cutoff"] = cutoff and path is None
    return result


def ids(graph, source, goal):
    """
    Function: ids
    Purpose : Iterative Deepening Search - runs DLS with limit 0, 1, 2, ...
              Finds the path with the fewest edges.
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    expanded = []
    for limit in range(len(graph)):
        path, cutoff, order = dls_core(graph, source, goal, limit)
        expanded.extend(order)
        if path is not None:
            return make_result("IDS", path, graph, expanded, start)
        if not cutoff:
            break                      # whole graph explored, no route
    return make_result("IDS", [], graph, expanded, start, found=False)


def expand_layer(graph, frontier, parent, depth, other_depth):
    """
    Function: expand_layer
    Purpose : Expand one full BFS layer for one side of Bidirectional BFS and
              note every place where it touches the other side's search.
    Params  : graph (dict)
              frontier (list) - nodes of the current layer
              parent (dict), depth (dict) - this side's search data
              other_depth (dict) - the other side's visited nodes and depths
    Returns : tuple (next_frontier, best_meeting) where best_meeting is
              (total_edges, node_on_this_side, node_on_other_side) or None
    """
    next_frontier = []
    best = None
    for node in frontier:
        for nb in neighbours(graph, node):
            if nb in other_depth:
                total = depth[node] + 1 + other_depth[nb]
                if best is None or total < best[0]:
                    best = (total, node, nb)
            if nb not in parent:
                parent[nb] = node
                depth[nb] = depth[node] + 1
                next_frontier.append(nb)
    return next_frontier, best


def bidirectional_bfs(graph, source, goal):
    """
    Function: bidirectional_bfs
    Purpose : Run BFS from the source and from the goal at the same time
              (smaller frontier first) until the two searches meet.
              Whole layers are expanded and the best meeting point is taken,
              so the fewest-edges path is still found.
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    if source == goal:
        return make_result("Bidirectional BFS", [source], graph, [source], start)
    parent_s, depth_s, front_s = {source: None}, {source: 0}, [source]
    parent_g, depth_g, front_g = {goal: None}, {goal: 0}, [goal]
    expanded = []
    while front_s and front_g:
        if len(front_s) <= len(front_g):
            expanded.extend(front_s)
            front_s, best = expand_layer(graph, front_s, parent_s, depth_s, depth_g)
            if best:
                _, node, other = best                 # node on source side
                path = trace(parent_s, node)[::-1] + trace(parent_g, other)
                return make_result("Bidirectional BFS", path, graph, expanded, start)
        else:
            expanded.extend(front_g)
            front_g, best = expand_layer(graph, front_g, parent_g, depth_g, depth_s)
            if best:
                _, node, other = best                 # node on goal side
                path = trace(parent_s, other)[::-1] + trace(parent_g, node)
                return make_result("Bidirectional BFS", path, graph, expanded, start)
    return make_result("Bidirectional BFS", [], graph, expanded, start, found=False)


def greedy(graph, source, goal):
    """
    Function: greedy
    Purpose : Greedy Best-First Search - always expands the node with the
              smallest h(n); fast but not guaranteed optimal.
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    visited = set()
    counter = 0
    heap = [(heuristic(source, goal), counter, source, [source])]
    expanded = []
    while heap:
        _, _, node, path = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        expanded.append(node)
        if node == goal:
            return make_result("Greedy Best-First", path, graph, expanded, start)
        for nb in neighbours(graph, node):
            if nb not in visited:
                counter += 1
                heapq.heappush(heap, (heuristic(nb, goal), counter, nb, path + [nb]))
    return make_result("Greedy Best-First", [], graph, expanded, start, found=False)


def rbfs(graph, source, goal):
    """
    Function: rbfs
    Purpose : Recursive Best-First Search - A*-style search that uses only
              linear memory by remembering the best alternative f-value and
              backing up when the current branch gets worse than it.
    Params  : graph (dict), source (str), goal (str)
    Returns : result dict
    """
    start = time.perf_counter()
    expanded = []

    def recurse(node, path, g, f_node, f_limit):
        """
        Function: recurse
        Purpose : Search below one node while its f-value stays <= f_limit.
        Params  : node (str), path (list), g (cost so far),
                  f_node (stored f of this node), f_limit (best alternative f)
        Returns : tuple (path or None, new f-value for this node)
        """
        expanded.append(node)
        if node == goal:
            return path, f_node
        successors = []
        for nb in neighbours(graph, node):
            if nb in path:
                continue
            g2 = g + graph[node][nb]
            f2 = max(g2 + heuristic(nb, goal), f_node)   # f never decreases down a branch
            successors.append([f2, g2, nb])
        if not successors:
            return None, INF
        while True:
            successors.sort(key=lambda s: (s[0], s[2]))
            best = successors[0]
            if best[0] > f_limit or best[0] == INF:
                return None, best[0]
            alternative = successors[1][0] if len(successors) > 1 else INF
            found, best[0] = recurse(best[2], path + [best[2]], best[1],
                                     best[0], min(f_limit, alternative))
            if found is not None:
                return found, best[0]

    path, _ = recurse(source, [source], 0, heuristic(source, goal), INF)
    if path is None:
        return make_result("RBFS", [], graph, expanded, start, found=False)
    return make_result("RBFS", path, graph, expanded, start)


# ===========================================================================
# 5. Algorithm selection and comparison
# ===========================================================================
def select_algorithm(graph_type, heuristic_available):
    """
    Function: select_algorithm
    Purpose : Search policy: unweighted -> BFS; weighted + heuristic -> A*;
              weighted without heuristic -> UCS.
    Params  : graph_type (str) - "unweighted" or "weighted"
              heuristic_available (bool)
    Returns : str - "BFS", "A*" or "UCS" (raises ValueError for another graph_type)
    """
    if graph_type == "unweighted":
        return "BFS"
    if graph_type == "weighted":
        return "A*" if heuristic_available else "UCS"
    raise ValueError("graph_type must be 'unweighted' or 'weighted'")


def run_algorithm(name, source, destination, weighted=True, dls_limit=DEFAULT_DLS_LIMIT):
    """
    Function: run_algorithm
    Purpose : Run one algorithm by name on the chosen graph view. Unknown
              nodes give a not-found result instead of an error.
    Params  : name (str) - one of ALGORITHM_ORDER
              source, destination (str) - node names
              weighted (bool) - graph view
              dls_limit (int) - depth limit, used by DLS only
    Returns : result dict (raises ValueError for an unknown algorithm name)
    """
    if name not in ALGORITHM_ORDER:
        raise ValueError("Unknown algorithm: " + str(name))
    graph = WEIGHTED_GRAPH if weighted else UNWEIGHTED_GRAPH
    if source not in graph or destination not in graph:
        return make_result(name, [], graph, [], time.perf_counter(), found=False)
    if name == "DLS":
        return dls(graph, source, destination, dls_limit)
    functions = {"BFS": bfs, "UCS": ucs, "A*": a_star, "DFS": dfs, "IDS": ids,
                 "Bidirectional BFS": bidirectional_bfs,
                 "Greedy Best-First": greedy, "RBFS": rbfs}
    return functions[name](graph, source, destination)


def compare_algorithms(source, destination, dls_limit=DEFAULT_DLS_LIMIT):
    """
    Function: compare_algorithms
    Purpose : Demo mode - run all 9 algorithms on the weighted graph so their
              costs are comparable (BFS/IDS/Bidirectional report the real
              cost of their fewest-edges path).
    Params  : source, destination (str) - node names
              dls_limit (int) - depth limit for DLS
    Returns : list of 9 result dicts in ALGORITHM_ORDER
    """
    return [run_algorithm(n, source, destination, True, dls_limit) for n in ALGORITHM_ORDER]


# ===========================================================================
# 6. Location names
# ===========================================================================
ALIASES = {
    "ai_lab": "AI_Lab", "ailab": "AI_Lab", "lab1": "AI_Lab", "lab_1": "AI_Lab",
    "lab": "AI_Lab", "gate": "Main_Gate", "main": "Main_Gate",
    "admin": "Admin_Block", "services": "Student_Services",
    "exam": "Exam_Hall", "seminar": "Seminar_Room", "medical": "Medical_Center",
    "medical_centre": "Medical_Center", "bus": "Bus_Stop",
    "science": "Science_Block", "canteen": "Cafeteria",
}


def location_key(text):
    """
    Function: location_key
    Purpose : Reduce text to a comparison key: lower case, spaces/hyphens
              turned into underscores.
    Params  : text (str)
    Returns : str
    """
    return "_".join(text.strip().lower().replace("-", " ").replace("_", " ").split())


def normalize_location(text):
    """
    Function: normalize_location
    Purpose : Turn user text into an exact node name. Case-insensitive,
              accepts spaces or underscores, a few aliases ("ai lab", "lab1"),
              and suggests a name for typos ("Did you mean ...?").
    Params  : text (str)
    Returns : tuple (node or None, error message or None)
    """
    if not isinstance(text, str) or not text.strip():
        return None, "Location is missing."
    key = location_key(text)
    table = {location_key(n): n for n in NODES}
    table.update(ALIASES)
    if key in table:
        return table[key], None
    close = difflib.get_close_matches(key, list(table), n=1, cutoff=0.6)
    if close:
        return None, "Unknown location '%s'. Did you mean %s?" % (text.strip(), table[close[0]])
    return None, "Unknown location '%s'. Valid locations: %s" % (text.strip(), ", ".join(NODES))


# ===========================================================================
# 7. Entry point for integration
# ===========================================================================
def failure(message):
    """
    Function: failure
    Purpose : Build the standard failed run_search response.
    Params  : message (str)
    Returns : dict
    """
    return {"success": False, "route": {}, "error": message}


def run_search(request, csp_output=None, graph_type="weighted", heuristic_available=True):
    """
    Function: run_search
    Purpose : Find the route for a request. Source = request["current_location"];
              destination = csp_output["destination"] if given, otherwise
              request["destination"]. graph_type and heuristic_available
              feed select_algorithm. Never raises, never prints.
    Params  : request (dict) - request dict (see shared/templates.py)
              csp_output (dict or None) - CSP result that may hold "destination"
              graph_type (str) - "weighted" (default) or "unweighted"
              heuristic_available (bool) - default True
    Returns : dict {"success": bool,
                    "route": {algorithm, path, cost, steps, nodes_expanded},
                    "error": str or None}
    """
    try:
        if not isinstance(request, dict):
            return failure("Request must be a dict.")
        dest_text = request.get("destination")
        if isinstance(csp_output, dict) and csp_output.get("destination"):
            dest_text = csp_output["destination"]
        source, error = normalize_location(request.get("current_location"))
        if error:
            return failure("Current location: " + error)
        if not dest_text:
            return failure("Destination is missing.")
        destination, error = normalize_location(dest_text)
        if error:
            return failure("Destination: " + error)
        name = select_algorithm(graph_type, heuristic_available)
        result = run_algorithm(name, source, destination, weighted=(name != "BFS"))
        if not result["found"]:
            return failure("No route found from %s to %s." % (source, destination))
        route = {k: result[k] for k in ("path", "cost", "steps", "nodes_expanded")}
        route["algorithm"] = result["algorithm_used"]
        return {"success": True, "route": route, "error": None}
    except Exception as exc:          # never let an error escape to the caller
        return failure("Search failed: %s" % exc)
