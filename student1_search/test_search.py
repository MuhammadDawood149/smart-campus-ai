"""
File    : student1_search/test_search.py
Module  : Search & Navigation tests
Owner   : Student 1

Purpose : unittest checks for search_module.py over all 156 ordered pairs of
          the 13 campus nodes, plus policy, heuristic and run_search checks.
Run     : python -m unittest discover -s student1_search -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import search_module as sm
from shared.campus_data import NODES, EDGES

PAIRS = [(a, b) for a in NODES for b in NODES if a != b]
EPS = 1e-9
RESULT_KEYS = {"algorithm_used", "path", "cost", "steps", "nodes_expanded", "time_ms", "found"}


def is_valid_path(path, source, goal):
    """
    Function: is_valid_path
    Purpose : Check a path starts/ends correctly and uses only real edges.
    Params  : path (list), source (str), goal (str)
    Returns : bool
    """
    if not path or path[0] != source or path[-1] != goal:
        return False
    return all(path[i + 1] in sm.WEIGHTED_GRAPH[path[i]] for i in range(len(path) - 1))


class TestSetup(unittest.TestCase):
    """Sanity checks on the graph and the number of pairs."""

    def test_pair_count(self):
        """There are 13 * 12 = 156 ordered pairs."""
        self.assertEqual(len(PAIRS), 156)

    def test_graph_views(self):
        """Both views have the same 19 connections; unweighted costs are all 1."""
        self.assertEqual(sum(len(v) for v in sm.WEIGHTED_GRAPH.values()), 38)
        for node in NODES:
            self.assertEqual(set(sm.WEIGHTED_GRAPH[node]), set(sm.UNWEIGHTED_GRAPH[node]))
            self.assertTrue(all(c == 1 for c in sm.UNWEIGHTED_GRAPH[node].values()))

    def test_result_keys(self):
        """Every algorithm returns the same keys."""
        for name in sm.ALGORITHM_ORDER:
            result = sm.run_algorithm(name, "Hostel", "AI_Lab")
            self.assertTrue(RESULT_KEYS.issubset(result), name)
            self.assertTrue(result["found"], name)


class TestOptimalAlgorithms(unittest.TestCase):
    """Acceptance check and equality checks across all pairs."""

    def test_astar_acceptance(self):
        """A* Hostel -> AI_Lab."""
        r = sm.run_algorithm("A*", "Hostel", "AI_Lab")
        self.assertEqual(r["path"], ["Hostel", "Cafeteria", "Science_Block", "AI_Lab"])
        self.assertEqual(r["cost"], 6)
        self.assertEqual(r["steps"], 3)

    def test_ucs_astar_rbfs_same_cost(self):
        """UCS, A* and RBFS find equally cheap routes for every pair."""
        for a, b in PAIRS:
            costs = [sm.run_algorithm(n, a, b)["cost"] for n in ("UCS", "A*", "RBFS")]
            self.assertEqual(len(set(costs)), 1, "%s -> %s: %s" % (a, b, costs))

    def test_bfs_ids_bidirectional_same_hops(self):
        """BFS, IDS and Bidirectional BFS find the same number of edges."""
        for a, b in PAIRS:
            steps = [sm.run_algorithm(n, a, b)["steps"]
                     for n in ("BFS", "IDS", "Bidirectional BFS")]
            self.assertEqual(len(set(steps)), 1, "%s -> %s: %s" % (a, b, steps))

    def test_all_paths_valid(self):
        """Every algorithm returns a real path for every pair (DLS limit 12)."""
        for name in sm.ALGORITHM_ORDER:
            for a, b in PAIRS:
                r = sm.run_algorithm(name, a, b, True, 12)
                self.assertTrue(r["found"], "%s %s->%s" % (name, a, b))
                self.assertTrue(is_valid_path(r["path"], a, b), "%s %s->%s" % (name, a, b))
                self.assertEqual(r["steps"], len(r["path"]) - 1)

    def test_dfs_greedy_valid(self):
        """DFS and Greedy paths use real edges with the right start and end."""
        for name in ("DFS", "Greedy Best-First"):
            for a, b in PAIRS:
                r = sm.run_algorithm(name, a, b)
                self.assertTrue(is_valid_path(r["path"], a, b), "%s %s->%s" % (name, a, b))

    def test_same_node(self):
        """Source equal to destination gives a one-node path of cost 0."""
        for name in sm.ALGORITHM_ORDER:
            r = sm.run_algorithm(name, "Library", "Library")
            self.assertEqual((r["path"], r["cost"], r["steps"]), (["Library"], 0, 0), name)


class TestHeuristic(unittest.TestCase):
    """The scaled Euclidean heuristic."""

    def test_k_is_one_third(self):
        """k computed from the edges is 1/3."""
        self.assertAlmostEqual(sm.K, 1 / 3, places=9)

    def test_raw_euclid_overestimates_12_edges(self):
        """Raw Euclidean distance is larger than the edge cost on 12 of 19 edges."""
        bad = sum(1 for a, b, c in EDGES if sm.euclid(a, b) > c + EPS)
        self.assertEqual(bad, 12)

    def test_admissible(self):
        """h(n) never exceeds the true cheapest cost to the goal."""
        for a, b in PAIRS:
            true_cost = sm.run_algorithm("UCS", a, b)["cost"]
            self.assertLessEqual(sm.heuristic(a, b), true_cost + EPS, "%s -> %s" % (a, b))

    def test_consistent(self):
        """h(a) <= cost(a, c) + h(c) on every edge in both directions, for every goal."""
        for goal in NODES:
            for a, b, cost in EDGES:
                self.assertLessEqual(sm.heuristic(a, goal), cost + sm.heuristic(b, goal) + EPS)
                self.assertLessEqual(sm.heuristic(b, goal), cost + sm.heuristic(a, goal) + EPS)


class TestDLS(unittest.TestCase):
    """Depth-limited search."""

    def test_cutoff(self):
        """Limit 1 on Hostel -> AI_Lab fails and reports a cutoff."""
        r = sm.run_algorithm("DLS", "Hostel", "AI_Lab", True, 1)
        self.assertFalse(r["found"])
        self.assertTrue(r["cutoff"])

    def test_large_limit_finds(self):
        """A generous limit finds a route and reports no cutoff."""
        r = sm.run_algorithm("DLS", "Hostel", "AI_Lab", True, 12)
        self.assertTrue(r["found"])
        self.assertFalse(r["cutoff"])


class TestPolicy(unittest.TestCase):
    """select_algorithm follows the search policy."""

    def test_policy(self):
        """unweighted -> BFS, weighted+h -> A*, weighted no h -> UCS."""
        self.assertEqual(sm.select_algorithm("unweighted", True), "BFS")
        self.assertEqual(sm.select_algorithm("unweighted", False), "BFS")
        self.assertEqual(sm.select_algorithm("weighted", True), "A*")
        self.assertEqual(sm.select_algorithm("weighted", False), "UCS")

    def test_bad_graph_type(self):
        """An unknown graph type is rejected."""
        with self.assertRaises(ValueError):
            sm.select_algorithm("bumpy", True)


class TestRunSearch(unittest.TestCase):
    """run_search entry point: normal use and clean failures."""

    def test_success_default_astar(self):
        """Default request uses A*."""
        out = sm.run_search({"current_location": "Hostel", "destination": "AI_Lab"})
        self.assertTrue(out["success"])
        self.assertIsNone(out["error"])
        self.assertEqual(out["route"]["algorithm"], "A*")
        self.assertEqual(out["route"]["cost"], 6)
        self.assertEqual(set(out["route"]), {"algorithm", "path", "cost", "steps", "nodes_expanded"})

    def test_modes(self):
        """graph_type / heuristic_available keyword parameters switch the algorithm."""
        base = {"current_location": "Hostel", "destination": "AI_Lab"}
        self.assertEqual(sm.run_search(base, graph_type="unweighted")["route"]["algorithm"], "BFS")
        self.assertEqual(sm.run_search(base, heuristic_available=False)["route"]["algorithm"], "UCS")

    def test_csp_destination_wins(self):
        """csp_output destination overrides the request destination."""
        out = sm.run_search({"current_location": "Hostel", "destination": "Library"},
                            {"destination": "AI_Lab"})
        self.assertEqual(out["route"]["path"][-1], "AI_Lab")

    def test_empty_csp_destination_falls_back(self):
        """An empty csp destination falls back to the request destination."""
        out = sm.run_search({"current_location": "Hostel", "destination": "Library"},
                            {"destination": ""})
        self.assertEqual(out["route"]["path"][-1], "Library")

    def test_aliases_and_case(self):
        """Names are case-insensitive and aliases work."""
        out = sm.run_search({"current_location": "main gate", "destination": "LAB1"})
        self.assertTrue(out["success"])
        self.assertEqual(out["route"]["path"][0], "Main_Gate")
        self.assertEqual(out["route"]["path"][-1], "AI_Lab")

    def test_invalid_source(self):
        """Unknown source fails cleanly with a suggestion for a typo."""
        out = sm.run_search({"current_location": "Libary", "destination": "AI_Lab"})
        self.assertFalse(out["success"])
        self.assertIn("Did you mean Library?", out["error"])

    def test_invalid_destination(self):
        """Unknown destination fails cleanly."""
        out = sm.run_search({"current_location": "Hostel", "destination": "Moon_Base"})
        self.assertFalse(out["success"])
        self.assertIsNotNone(out["error"])

    def test_missing_destination(self):
        """Missing or blank destination fails cleanly."""
        for dest in ("", None):
            out = sm.run_search({"current_location": "Hostel", "destination": dest})
            self.assertFalse(out["success"])
            self.assertIn("Destination", out["error"])
        out = sm.run_search({"current_location": "Hostel"})
        self.assertFalse(out["success"])

    def test_missing_source(self):
        """Missing source fails cleanly."""
        out = sm.run_search({"destination": "AI_Lab"})
        self.assertFalse(out["success"])

    def test_garbage_never_raises(self):
        """Odd inputs return a failure dict instead of raising."""
        for bad in (None, 5, "text", [], {"current_location": 7, "destination": 8}):
            out = sm.run_search(bad)
            self.assertFalse(out["success"])
            self.assertIsInstance(out["error"], str)
        out = sm.run_search({"current_location": "Hostel", "destination": "AI_Lab"}, graph_type="x")
        self.assertFalse(out["success"])
        self.assertIsInstance(out["error"], str)


class TestNormalize(unittest.TestCase):
    """normalize_location."""

    def test_forms(self):
        """Case, spaces and underscores are all accepted."""
        for text in ("ai lab", "AI_LAB", " Ai_Lab ", "lab1", "ai-lab"):
            self.assertEqual(sm.normalize_location(text), ("AI_Lab", None), text)
        self.assertEqual(sm.normalize_location("science block")[0], "Science_Block")

    def test_suggestion(self):
        """A typo gets a Did-you-mean message."""
        node, err = sm.normalize_location("Cafetria")
        self.assertIsNone(node)
        self.assertIn("Did you mean Cafeteria?", err)


if __name__ == "__main__":
    unittest.main()
