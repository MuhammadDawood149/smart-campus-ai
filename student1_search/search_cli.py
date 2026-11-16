"""
File    : student1_search/search_cli.py
Module  : Search & Navigation demo
Owner   : Student 1

Purpose : Menu-driven demo of the search module: find a route, change the
          graph mode (BFS / A* / UCS), compare all 9 algorithms, show the
          map and heuristic table. Invalid input is re-asked, never a crash.
Run     : python student1_search/search_cli.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import search_module as sm
from shared.campus_data import NODES
from shared.templates import REQUEST_TEMPLATE, new_template

# mode name -> (graph_type, heuristic_available)
MODES = {"BFS": ("unweighted", True), "A*": ("weighted", True), "UCS": ("weighted", False)}


def read_line(prompt):
    """
    Function: read_line
    Purpose : input() that treats Ctrl+C / end of input as "leave the program".
    Params  : prompt (str)
    Returns : str, or None when input is closed
    """
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def ask_location(prompt):
    """
    Function: ask_location
    Purpose : Ask for a location until it is valid. A blank answer cancels.
    Params  : prompt (str)
    Returns : node name (str), or None if cancelled / input closed
    """
    while True:
        text = read_line(prompt + " (blank = back): ")
        if text is None or not text.strip():
            return None
        node, error = sm.normalize_location(text)
        if node:
            return node
        print("  " + error)


def ask_int(prompt, default):
    """
    Function: ask_int
    Purpose : Ask for a non-negative whole number; blank uses the default.
    Params  : prompt (str), default (int)
    Returns : int, or None if input closed
    """
    while True:
        text = read_line("%s [%d]: " % (prompt, default))
        if text is None:
            return None
        if not text.strip():
            return default
        if text.strip().isdigit():
            return int(text.strip())
        print("  Please enter a whole number.")


def find_route(mode):
    """
    Function: find_route
    Purpose : Ask for source and destination and print the route found with
              the current mode.
    Params  : mode (str) - "BFS", "A*" or "UCS"
    Returns : None
    """
    source = ask_location("From")
    if source is None:
        return
    destination = ask_location("To")
    if destination is None:
        return
    request = new_template(REQUEST_TEMPLATE)
    request["current_location"] = source
    request["destination"] = destination
    graph_type, heuristic_available = MODES[mode]
    out = sm.run_search(request, None, graph_type, heuristic_available)
    if not out["success"]:
        print("  Error: " + out["error"])
        return
    r = out["route"]
    print("  Algorithm      : %s" % r["algorithm"])
    print("  Path           : %s" % " -> ".join(r["path"]))
    print("  Cost           : %s%s" % (r["cost"], " (edges)" if mode == "BFS" else ""))
    print("  Steps          : %d" % r["steps"])
    print("  Nodes expanded : %d" % r["nodes_expanded"])


def change_mode(mode):
    """
    Function: change_mode
    Purpose : Let the user pick BFS, A* or UCS.
    Params  : mode (str) - current mode
    Returns : str - the new mode (unchanged if cancelled)
    """
    while True:
        text = read_line("Mode BFS / A* / UCS (now %s, blank = keep): " % mode)
        if text is None or not text.strip():
            return mode
        choice = text.strip().upper()
        if choice in MODES:
            print("  Mode set to %s." % choice)
            return choice
        print("  Please type BFS, A* or UCS.")


def print_comparison(source, destination, dls_limit):
    """
    Function: print_comparison
    Purpose : Run all 9 algorithms (weighted graph) and print a table.
    Params  : source, destination (str), dls_limit (int)
    Returns : None
    """
    results = sm.compare_algorithms(source, destination, dls_limit)
    print("\nComparison: %s -> %s   (weighted graph, DLS limit %d)" % (source, destination, dls_limit))
    head = "%-18s %-5s %5s %5s %9s %8s  %s" % ("Algorithm", "Found", "Cost", "Steps", "Expanded", "ms", "Path")
    print(head)
    print("-" * len(head) + "-" * 30)
    for r in results:
        found = "yes" if r["found"] else ("cut" if r.get("cutoff") else "no")
        path = " -> ".join(r["path"]) if r["found"] else "-"
        print("%-18s %-5s %5s %5s %9d %8.3f  %s" % (
            r["algorithm_used"], found, r["cost"] if r["found"] else "-",
            r["steps"] if r["found"] else "-", r["nodes_expanded"], r["time_ms"], path))


def compare_menu():
    """
    Function: compare_menu
    Purpose : Ask for the inputs of the comparison table and print it.
    Params  : none
    Returns : None
    """
    source = ask_location("From")
    if source is None:
        return
    destination = ask_location("To")
    if destination is None:
        return
    limit = ask_int("DLS depth limit", sm.DEFAULT_DLS_LIMIT)
    if limit is None:
        return
    print_comparison(source, destination, limit)


def show_map():
    """
    Function: show_map
    Purpose : Print every node with its coordinates and weighted neighbours,
              then the heuristic table for a chosen goal.
    Params  : none
    Returns : None
    """
    print("\nCampus map (13 nodes, 19 edges)")
    for node, (x, y) in NODES.items():
        links = ", ".join("%s(%s)" % (nb, c) for nb, c in sorted(sm.WEIGHTED_GRAPH[node].items()))
        print("  %-17s (%2d,%d)  %s" % (node, x, y, links))
    goal = ask_location("\nGoal for the heuristic table")
    if goal is None:
        return
    print("\nk = %.4f   h(n) = k * euclid(n, %s)" % (sm.K, goal))
    print("%-17s %8s %8s %10s  %s" % ("Node", "euclid", "h(n)", "true cost", "h <= true"))
    for node in NODES:
        true_cost = sm.run_algorithm("UCS", node, goal)["cost"]
        e, h = sm.euclid(node, goal), sm.heuristic(node, goal)
        print("%-17s %8.3f %8.3f %10s  %s" % (node, e, h, true_cost,
                                             "ok" if h <= true_cost + 1e-9 else "NO"))


def main():
    """
    Function: main
    Purpose : Show the menu in a loop until the user exits.
    Params  : none
    Returns : None
    """
    mode = "A*"
    while True:
        print("\n=== Campus Search (mode: %s) ===" % mode)
        print("1. Find route\n2. Change graph mode (BFS / A* / UCS)")
        print("3. Compare all 9 algorithms\n4. Show map + heuristic table\n5. Exit")
        choice = read_line("Choose 1-5: ")
        if choice is None or choice.strip() == "5":
            print("Goodbye.")
            return
        choice = choice.strip()
        if choice == "1":
            find_route(mode)
        elif choice == "2":
            mode = change_mode(mode)
        elif choice == "3":
            compare_menu()
        elif choice == "4":
            show_map()
        else:
            print("Please enter a number from 1 to 5.")


if __name__ == "__main__":
    main()
