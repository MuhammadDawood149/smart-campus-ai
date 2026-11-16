"""
File    : run_all_tests.py
Module  : Test runner for the whole project
Owner   : Joint (Students 1, 2 and 3)

Purpose : Runs every test file of every student (student*/test_*.py) and the
          integration tests (test_integration.py), each in its own Python
          process so the parts stay independent, and prints a one-line
          summary per part. The full output of a failing part is shown below
          the summary. Exit code 0 only when every part passes.
Run     : python run_all_tests.py
"""

import glob
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

PART_NAMES = {"student1_search": "Student 1 - Search",
              "student2_logic_csp": "Student 2 - Logic/CSP",
              "student3_ann": "Student 3 - ANN",
              ".": "Integration"}


def find_test_files():
    """
    Function: find_test_files
    Purpose : List every student test file, then the integration tests.
    Params  : none
    Returns : list of paths relative to the project root
    """
    files = sorted(glob.glob(os.path.join("student*", "test_*.py"), root_dir=ROOT))
    return files + ["test_integration.py"]


def run_file(path):
    """
    Function: run_file
    Purpose : Run one test file in a fresh Python process and read the unittest
              summary ("Ran N tests", then "OK" or "FAILED (...)").
    Params  : path (str) - test file relative to the project root
    Returns : dict {"passed": bool, "tests": int, "status": str, "seconds": float,
                    "output": str}
    """
    start = time.perf_counter()
    done = subprocess.run([sys.executable, path], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    seconds = time.perf_counter() - start
    output = done.stdout + done.stderr
    ran = re.search(r"^Ran (\d+) tests?", output, re.MULTILINE)
    status = re.findall(r"^(OK.*|FAILED.*)$", output, re.MULTILINE)
    return {"passed": done.returncode == 0 and bool(ran),
            "tests": int(ran.group(1)) if ran else 0,
            "status": status[-1] if status else "ERROR (exit code %d)" % done.returncode,
            "seconds": seconds, "output": output}


def main():
    """
    Function: main
    Purpose : Run all parts, print one summary line each and a total.
    Params  : none
    Returns : int - process exit code (0 = all passed)
    """
    results = []
    for path in find_test_files():
        part = PART_NAMES.get(os.path.dirname(path) or ".", os.path.dirname(path))
        result = run_file(path)
        results.append((part, path, result))
        print("%-22s %-40s %4d tests  %-6s %5.1fs  %s" % (
            part, path.replace(os.sep, "/"), result["tests"],
            "PASS" if result["passed"] else "FAIL", result["seconds"], result["status"]))

    failed = [(part, path, r) for part, path, r in results if not r["passed"]]
    total = sum(r["tests"] for _, _, r in results)
    print("-" * 78)
    print("TOTAL: %d tests in %d files, %s" % (
        total, len(results), "all passed" if not failed else "%d file(s) FAILED" % len(failed)))
    for part, path, result in failed:
        print("\n===== Output of %s (%s) =====" % (path, part))
        print(result["output"])
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
