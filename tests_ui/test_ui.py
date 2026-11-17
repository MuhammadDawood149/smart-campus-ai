"""
File    : tests_ui/test_ui.py
Module  : End-to-end test of the web UI (extra interface)
Owner   : Joint (Students 1, 2 and 3)

Purpose : Starts server.py on a free port, opens the web UI in a headless
          browser (1366x768) and checks every page against the REAL backend.
          The expected values are computed first by calling the Python modules
          directly (cli.py --demo results, compare_algorithms(), check_logic(),
          predict_priority(), train.evaluate(), ...). Browser console errors and
          failed network requests (4xx/5xx) are captured on every page and count
          as failures. At the end the server is stopped to check the
          "server not reachable" message.
Output  : a results table on the screen and docs/report/ui_test_results.json
          (used by docs/report/build_report.py). With --shots it also saves the
          report screenshots in docs/screenshots/.
Needs   : pip install playwright
          python -m playwright install      (or use --channel msedge / chrome)
          Not part of run_all_tests.py (it needs a browser and takes ~6 minutes).
Run     : python tests_ui/test_ui.py [--shots] [--channel msedge] [--only console,map]
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from playwright.sync_api import sync_playwright        # noqa: E402

import main                                            # noqa: E402
from integration.demo_scenarios import DEMO_SCENARIOS  # noqa: E402
from shared.campus_data import EDGES, NODES            # noqa: E402
from student1_search import search_module as sm        # noqa: E402
from student2_logic_csp import logic_kb as kb          # noqa: E402
from student2_logic_csp import test_logic_csp          # noqa: E402
from student3_ann import ann_module as ann             # noqa: E402
from student3_ann import train                         # noqa: E402

RESULTS_PATH = os.path.join(ROOT, "docs", "report", "ui_test_results.json")
SHOT_DIR = os.path.join(ROOT, "docs", "screenshots")
VIEWPORT = {"width": 1366, "height": 768}
DLS_LIMIT = 3                                  # the UI's default DLS limit
COMPARE_PAIRS = [("Hostel", "AI_Lab"), ("Main_Gate", "Seminar_Room"), ("Bus_Stop", "Library")]
DECISION_LABEL = {"accepted": "Accepted", "completed": "Completed", "answered": "Answered", "rejected": "Rejected"}
STAGE_MODULE = {"ann": "ANN", "logic": "Logic_KB", "eligible": "Logic_KB", "csp": "CSP", "search": "Search"}

RESULTS = []                                   # [{"area", "check", "pass", "notes"}]
OPTIONS = {"shots": False}


# ===========================================================================
# 1. Expected values, computed by calling the modules directly
# ===========================================================================
def pretty(text):
    """
    Function: pretty
    Purpose : The UI shows names with spaces instead of underscores.
    Params  : text (str)
    Returns : str
    """
    return str(text).replace("_", " ")


def expected():
    """
    Function: expected
    Purpose : Every value the UI should show, from the Python modules.
    Params  : none
    Returns : dict
    """
    want = {"demos": []}
    main.reset_system()
    for scenario in DEMO_SCENARIOS:                    # exactly like cli.py --demo
        main.reset_system(clear_counter=False)
        res = main.process_request(scenario["request"], with_trace=True)
        want["demos"].append({
            "title": scenario["title"], "decision": res["decision"], "rejected_at": res.get("rejected_at"),
            "room": (res.get("assignment") or {}).get("room"), "slot": (res.get("assignment") or {}).get("slot"),
            "path": (res.get("route") or {}).get("path"), "cost": (res.get("route") or {}).get("cost"),
            "priority": res.get("priority"), "pipeline": res["trace"]["pipeline"]})
    main.reset_system()
    want["initial_bookings"] = sorted("%s:%d" % b for b in main.get_bookings()["bookings"])
    slots = []
    for _ in range(4):                                 # AI_Lab slot 2, four times
        res = main.process_request({"name": "Ali", "role": "student", "request_type": "Booking_or_Scheduling",
                                    "category": "AI_Lab_Support", "preferred_slot": 2})
        slots.append(res["assignment"]["slot"] if res.get("assignment") else "rejected@%s" % res.get("rejected_at"))
    want["repeat_slots"] = slots
    main.reset_system()
    want["compare"] = {pair: sm.compare_algorithms(pair[0], pair[1], DLS_LIMIT) for pair in COMPARE_PAIRS}
    want["policy"] = {}
    for mode, (graph_type, has_h) in {"weighted-h": ("weighted", True), "unweighted": ("unweighted", False),
                                      "weighted": ("weighted", False)}.items():
        name = sm.select_algorithm(graph_type, has_h)
        want["policy"][mode] = sm.run_algorithm(name, "Hostel", "AI_Lab", weighted=(name != "BFS"))
    want["forward"] = [kb.atom_text(e["derived"]) for e in kb.forward_chain()["log"]]
    want["ann"] = ann.predict_priority([0, 0, 8, 9, 5, 4, 1])
    models, _ = ann.load_models()
    want["metrics"] = train.evaluate(models)
    return want


def logic_answer(query):
    """
    Function: logic_answer
    Purpose : What check_logic() says about one query.
    Params  : query (str)
    Returns : dict - check_logic result
    """
    return kb.check_logic({"request_type": "Eligibility_Check", "query": query})


# ===========================================================================
# 2. Results, server, error capture
# ===========================================================================
def rec(area, check, ok, notes=""):
    """
    Function: rec
    Purpose : Record one check and print it.
    Params  : area (str), check (str), ok (bool), notes (any)
    Returns : None
    """
    notes = str(notes)[:400]
    RESULTS.append({"area": area, "check": check, "pass": bool(ok), "notes": notes})
    print("%s | %s | %s | %s" % ("PASS" if ok else "FAIL", area, check, notes[:160]))


def free_port():
    """
    Function: free_port
    Purpose : A TCP port nobody is using.
    Params  : none
    Returns : int
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Server:
    """server.py running in its own process."""

    def __init__(self, port):
        """
        Function: __init__
        Purpose : Remember the port; the server is started with start().
        Params  : port (int)
        Returns : None
        """
        self.port = port
        self.base = "http://127.0.0.1:%d" % port
        self.proc = None

    def start(self):
        """
        Function: start
        Purpose : Start server.py and wait until it answers.
        Params  : none
        Returns : None (raises RuntimeError if it does not start in 90 s)
        """
        self.proc = subprocess.Popen([sys.executable, "server.py", "--port", str(self.port), "--no-browser"],
                                     cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(180):
            try:
                self.get("/graph")
                return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("server.py did not start")

    def stop(self):
        """
        Function: stop
        Purpose : Stop the server (used for the "server not reachable" check).
        Params  : none
        Returns : None
        """
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=30)

    def get(self, path):
        """
        Function: get
        Purpose : GET an API endpoint.
        Params  : path (str) - e.g. "/bookings"
        Returns : decoded JSON
        """
        with urllib.request.urlopen(self.base + "/api" + path, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def bookings(self):
        """
        Function: bookings
        Purpose : Current bookings as sorted "room:slot" strings.
        Params  : none
        Returns : list of str
        """
        return sorted("%s:%d" % (b["room"], b["slot"]) for b in self.get("/bookings"))


class Watcher:
    """Collects browser console errors, page errors and failed requests."""

    def __init__(self):
        """
        Function: __init__
        Purpose : Start with no errors.
        Params  : none
        Returns : None
        """
        self.errors = []

    def attach(self, page, label):
        """
        Function: attach
        Purpose : Listen to one page.
        Params  : page (Page), label (str) - shown in the error text
        Returns : None
        """
        def on_console(msg):
            """
            Function: on_console
            Purpose : Keep console messages of type "error".
            Params  : msg (ConsoleMessage)
            Returns : None
            """
            if msg.type == "error":
                self.errors.append("[%s] console: %s" % (label, msg.text))

        def on_page_error(err):
            """
            Function: on_page_error
            Purpose : Keep uncaught JavaScript exceptions.
            Params  : err (Error)
            Returns : None
            """
            self.errors.append("[%s] pageerror: %s" % (label, err))

        def on_response(resp):
            """
            Function: on_response
            Purpose : Keep HTTP 4xx / 5xx responses.
            Params  : resp (Response)
            Returns : None
            """
            if resp.status >= 400:
                self.errors.append("[%s] HTTP %d %s" % (label, resp.status, resp.url))

        def on_failed(req):
            """
            Function: on_failed
            Purpose : Keep requests that got no response at all.
            Params  : req (Request)
            Returns : None
            """
            self.errors.append("[%s] failed: %s %s" % (label, req.url, req.failure))

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("response", on_response)
        page.on("requestfailed", on_failed)

    def take(self):
        """
        Function: take
        Purpose : Return the errors collected so far and start again.
        Params  : none
        Returns : list of str
        """
        errors, self.errors = self.errors, []
        return errors

    def check(self, area, what):
        """
        Function: check
        Purpose : Record a check that no error happened since the last one.
        Params  : area (str), what (str)
        Returns : None
        """
        errors = self.take()
        rec(area, "no JS errors / failed requests (%s)" % what, not errors, " || ".join(errors))


def shot(page, name, full=True):
    """
    Function: shot
    Purpose : Save a report screenshot (only with --shots). "full" uses a
              viewport as tall as the page, so the fixed sidebar fills the image.
    Params  : page (Page), name (str) - file name, full (bool)
    Returns : None
    """
    if not OPTIONS["shots"]:
        return
    page.wait_for_timeout(400)
    path = os.path.join(SHOT_DIR, name)
    if not full:
        page.screenshot(path=path)
        return
    height = page.evaluate("() => document.documentElement.scrollHeight")
    scroll = page.evaluate("() => window.scrollY")
    page.set_viewport_size({"width": VIEWPORT["width"], "height": max(VIEWPORT["height"], height)})
    page.wait_for_timeout(700)
    page.screenshot(path=path)
    page.set_viewport_size(VIEWPORT)
    page.evaluate("(y) => window.scrollTo(0, y)", scroll)


# ===========================================================================
# 3. Page helpers
# ===========================================================================
def go(page, section):
    """
    Function: go
    Purpose : Open a page of the UI with the sidebar.
    Params  : page (Page), section (str) - console / map / csp / kb / ann / history
    Returns : None
    """
    page.click('.nav-item[data-section="%s"]' % section)
    page.wait_for_timeout(300)


def wait_pipeline(page, request_id):
    """
    Function: wait_pipeline
    Purpose : Wait until the pipeline tracker has finished animating a request.
    Params  : page (Page), request_id (str)
    Returns : None
    """
    page.wait_for_function("(id) => document.querySelector('#pipe-meta b')?.textContent === id",
                           arg=request_id, timeout=15000)
    page.wait_for_function("""() => { const f = document.querySelector('.pnode[data-key="final"]');
        return f.classList.contains('done') || f.classList.contains('rejected') || document.querySelector('.pnode.rejected'); }""",
                           timeout=30000)
    page.wait_for_timeout(150)


def run_demo(page, index):
    """
    Function: run_demo
    Purpose : Pick a demo scenario (the UI runs it at once) and wait for the result.
    Params  : page (Page), index (int) - 0-based
    Returns : dict - the response the backend sent
    """
    with page.expect_response("**/api/request", timeout=20000) as info:
        page.select_option("#demo-select", str(index))
    res = info.value.json()
    wait_pipeline(page, res["request_id"])
    return res


def submit(page):
    """
    Function: submit
    Purpose : Click "Run through pipeline" and wait for the result.
    Params  : page (Page)
    Returns : (request body the UI sent, response)
    """
    with page.expect_request("**/api/request", timeout=15000) as req_info:
        with page.expect_response("**/api/request", timeout=15000) as res_info:
            page.click("#submit-btn")
    res = res_info.value.json()
    wait_pipeline(page, res["request_id"])
    return req_info.value.post_data_json, res


def set_type(page, request_type):
    """
    Function: set_type
    Purpose : Choose a request type card.
    Params  : page (Page), request_type (str)
    Returns : None
    """
    page.click('#type-grid label:has(input[value="%s"])' % request_type)
    page.wait_for_timeout(450)


def fill(page, actions):
    """
    Function: fill
    Purpose : Fill the request form: Clear first, then each action in order.
              ("type", t) request type, ("name", v), ("role", v),
              ("select", css, v), ("fill", css, v), ("slot", n), ("js", code)
    Params  : page (Page), actions (list of tuples)
    Returns : None
    """
    page.click("#clear-btn")
    for action in actions:
        kind = action[0]
        if kind == "type":
            set_type(page, action[1])
        elif kind == "name":
            page.fill("#f-name", action[1])
        elif kind == "role":
            page.select_option("#f-role", action[1])
        elif kind == "select":
            page.select_option(action[1], action[2])
            page.wait_for_timeout(200)
        elif kind == "fill":
            page.fill(action[1], action[2])
        elif kind == "slot":
            page.click('input[name="preferred_slot"][value="%s"]' % action[1], force=True)
        elif kind == "js":
            page.evaluate(action[1])


def visible_fields(page):
    """
    Function: visible_fields
    Purpose : Names of the request-type fields the form shows right now.
    Params  : page (Page)
    Returns : sorted list of str (name and role excluded)
    """
    return page.evaluate("""() => { const names = new Set();
        document.querySelectorAll('#req-form .dyn').forEach((d) => {
          if (d.hidden || d.inert) return;
          d.querySelectorAll('input,select,textarea').forEach((i) => { if (i.name) names.add(i.name); }); });
        return [...names].sort(); }""")


READ_CONSOLE_JS = """() => {
  const t = (s) => document.querySelector(s)?.textContent.trim() ?? null;
  const cards = [...document.querySelectorAll('#result .rcard')];
  const card = (title) => cards.find((c) => c.querySelector('h4')?.textContent === title);
  const asg = card('Assignment'); const route = card('Route'); const pri = card('Priority');
  return {
    title: t('#result .banner-title'), msg: t('#result .banner-msg'), stage: t('#result .banner-stage'),
    kicker: t('#result .banner-kicker'),
    room: asg?.querySelector('.big-val')?.textContent ?? null, asgKv: asg?.querySelector('.kv')?.textContent ?? null,
    path: route?.querySelector('.sub-val.mono')?.textContent ?? null,
    pri: pri ? [...pri.querySelectorAll('.pchip')].map((x) => x.textContent) : [],
    pnodes: [...document.querySelectorAll('.pnode')].map((n) => ({ key: n.dataset.key, cls: n.className })),
    callout: document.querySelector('#pipe-callout').hidden ? null : t('#pipe-callout'),
    resultLen: document.querySelector('#result').innerHTML.length,
  };
}"""


def read_console(page):
    """
    Function: read_console
    Purpose : What the result panel and the pipeline tracker show.
    Params  : page (Page)
    Returns : dict
    """
    return page.evaluate(READ_CONSOLE_JS)


def pipeline_problems(ui, pipeline, rejected_at):
    """
    Function: pipeline_problems
    Purpose : Check the tracker: modules the router did not select are
              "skipped"; the others are "done" up to the rejecting stage, which
              is "rejected"; later ones are "unreached"; a rejection has a callout.
    Params  : ui (dict) - read_console(), pipeline (list), rejected_at (str or None)
    Returns : list of str - empty when everything is right
    """
    problems = []
    stop_key = "eligible" if rejected_at == "logic" else rejected_at
    stopped = False
    for node in ui["pnodes"]:
        classes = node["cls"].split()
        module = STAGE_MODULE.get(node["key"])
        if module and module not in pipeline:
            if "skipped" not in classes:
                problems.append("%s should be skipped" % node["key"])
            continue
        if "skipped" in classes:
            problems.append("%s wrongly skipped" % node["key"])
        if stopped:
            if "unreached" not in classes:
                problems.append("%s should be unreached" % node["key"])
        elif node["key"] == stop_key:
            if "rejected" not in classes:
                problems.append("%s should be rejected" % node["key"])
            stopped = True
        elif "done" not in classes:
            problems.append("%s not done" % node["key"])
    if rejected_at and not stopped:
        problems.append("no stop at %s" % rejected_at)
    if rejected_at and not ui["callout"]:
        problems.append("no rejection callout")
    return problems


def booking_grid(page):
    """
    Function: booking_grid
    Purpose : Booked cells of the CSP grid as sorted "room:slot" strings.
    Params  : page (Page)
    Returns : list of str
    """
    return sorted(page.eval_on_selector_all("#booking-grid .cell.booked",
                                            "cs => cs.map((c) => c.dataset.room + ':' + c.dataset.slot)"))


def timeline(page):
    """
    Function: timeline
    Purpose : The History page as [request id, decision], newest first.
    Params  : page (Page)
    Returns : list of [str, str]
    """
    return page.eval_on_selector_all("#timeline .t-item", """items => items.map((x) =>
        [x.querySelector('.t-id').textContent, x.querySelector('.dec-chip').textContent])""")


# ===========================================================================
# 4. Request console
# ===========================================================================
FORM_FIELDS = {          # what cli.py asks for each request type (besides name and role)
    "Navigation_Only": ["current_location", "destination"],
    "Eligibility_Check": ["query"],
    "Booking_or_Scheduling": ["category", "current_location", "preferred_slot"],
    "Urgent_Service_Request": ["category", "crowd_level", "current_location", "description_note", "eligibility",
                               "preferred_slot", "severity", "time_sensitivity"],
    "Full_Service_Request": ["category", "crowd_level", "current_location", "description_note", "eligibility",
                             "preferred_slot", "severity", "time_sensitivity"],
}
MANUAL = {
    "Navigation_Only": [("name", "Ali"), ("select", "#f-loc", "Main_Gate"), ("select", "#f-dest", "Seminar_Room")],
    "Eligibility_Check": [("name", "DrKhan"), ("role", "instructor"), ("fill", "#f-query", "CanRequest(Ali, AI_Lab_Support)")],
    "Booking_or_Scheduling": [("name", "Ali"), ("select", "#f-cat", "Maintenance"), ("slot", 3), ("select", "#f-loc", "Library")],
    "Urgent_Service_Request": [("name", "Bilal"), ("role", "staff"), ("select", "#f-cat", "Emergency_Help"),
                               ("select", "#f-loc", "Hostel"), ("fill", "#f-sev", "10"), ("fill", "#f-time", "7"),
                               ("fill", "#f-crowd", "3"), ("fill", "#f-note", "Water leak near the hostel")],
    "Full_Service_Request": [("name", "Ali"), ("select", "#f-cat", "AI_Lab_Support"), ("select", "#f-loc", "Library"),
                             ("slot", 4), ("fill", "#f-sev", "5"), ("fill", "#f-note", "Projector broken")],
}
INVALID = [   # (label, form actions, expected decision, expected rejected_at, normalised field check)
    ("empty name", [("type", "Navigation_Only"), ("select", "#f-loc", "Hostel"), ("select", "#f-dest", "AI_Lab")],
     "rejected", "preprocessing", None),
    ("unknown location (option injected; the dropdown cannot produce it)",
     [("type", "Navigation_Only"), ("name", "Ali"), ("select", "#f-loc", "Hostel"),
      ("js", "() => { const s = document.querySelector('#f-dest'); s.append(new Option('Sports Complex', 'Sports_Complex')); s.value = 'Sports_Complex'; }")],
     "rejected", "preprocessing", None),
    ("slot outside 1-4 (radio value forced to 7)",
     [("type", "Booking_or_Scheduling"), ("name", "Ali"), ("select", "#f-cat", "AI_Lab_Support"),
      ("js", "() => { const r = document.querySelector('input[name=\"preferred_slot\"][value=\"4\"]'); r.value = '7'; r.checked = true; }")],
     "rejected", "preprocessing", None),
    ("severity 0 (slider limits removed)",
     [("type", "Urgent_Service_Request"), ("name", "Bilal"), ("role", "staff"), ("select", "#f-cat", "Emergency_Help"),
      ("select", "#f-loc", "Bus_Stop"), ("js", "() => { const r = document.querySelector('#f-sev'); r.min = '-5'; r.max = '20'; r.value = '0'; }")],
     "rejected", "preprocessing", None),
    ("severity 11 (slider limits removed)",
     [("type", "Urgent_Service_Request"), ("name", "Bilal"), ("role", "staff"), ("select", "#f-cat", "Emergency_Help"),
      ("select", "#f-loc", "Bus_Stop"), ("js", "() => { const r = document.querySelector('#f-sev'); r.min = '-5'; r.max = '20'; r.value = '11'; }")],
     "rejected", "preprocessing", None),
    ('malformed FOL query "UsesLab(DrKhan"', [("type", "Eligibility_Check"), ("name", "DrKhan"), ("fill", "#f-query", "UsesLab(DrKhan")],
     "rejected", "preprocessing", None),
    ("viva without group_id (select emptied)",
     [("type", "Booking_or_Scheduling"), ("name", "Ahmed"), ("select", "#f-cat", "Viva_Scheduling"),
      ("js", "() => { document.querySelector('#f-group').value = ''; }")],
     "rejected", "preprocessing", None),
    ('lowercase "ali" (normalised -> accepted)',
     [("type", "Full_Service_Request"), ("name", "ali"), ("select", "#f-cat", "AI_Lab_Support"), ("select", "#f-loc", "Hostel")],
     "accepted", None, ("name", "Ali")),
    ('lowercase "g4" (normalised -> accepted)',
     [("type", "Booking_or_Scheduling"), ("name", "Ahmed"), ("select", "#f-cat", "Viva_Scheduling"),
      ("js", "() => { const s = document.querySelector('#f-group'); s.append(new Option('g4', 'g4')); s.value = 'g4'; }")],
     "accepted", None, ("group_id", "G4")),
]
RESTORE_FORM_JS = """() => {
  const r = document.querySelector('#f-sev'); r.min = '1'; r.max = '10';
  const seven = document.querySelector('input[name="preferred_slot"][value="7"]'); if (seven) seven.value = '4';
  document.querySelectorAll('#f-group option, #f-dest option').forEach((o) => {
    if (o.value === 'g4' || o.value === 'Sports_Complex') o.remove(); });
}"""


def console_tests(page, server, want, watch):
    """
    Function: console_tests
    Purpose : Demo scenarios (twice), the form for every request type, Clear,
              invalid input, the repeated booking and the bookings grid.
    Params  : page (Page), server (Server), want (dict), watch (Watcher)
    Returns : None
    """
    area = "Console"
    go(page, "console")
    options = page.eval_on_selector_all("#demo-select option", "o => o.slice(1).map((x) => x.textContent)")
    rec(area, "demo list has 9 scenarios", len(options) == 9, len(options))
    for run in (1, 2):
        for i, w in enumerate(want["demos"]):
            res = run_demo(page, i)
            ui = read_console(page)
            p = []
            if res["decision"] != w["decision"] or res.get("rejected_at") != w["rejected_at"]:
                p.append("decision %s/%s" % (res["decision"], res.get("rejected_at")))
            asg = res.get("assignment") or {}
            if asg.get("room") != w["room"] or asg.get("slot") != w["slot"]:
                p.append("assignment %s" % asg)
            route = res.get("route") or {}
            if route.get("path") != w["path"] or route.get("cost") != w["cost"]:
                p.append("route %s" % route)
            handout = {k: (res.get("priority") or {}).get(k) for k in ("binary_priority", "final_priority", "confidence")}
            if w["priority"] and handout != w["priority"]:      # the UI-only extras (probabilities) are ignored
                p.append("priority %s" % handout)
            if ui["title"] != DECISION_LABEL[w["decision"]]:
                p.append("banner %s" % ui["title"])
            if w["room"] and ui["room"] != pretty(w["room"]):
                p.append("room card %s" % ui["room"])
            if w["slot"] and "Slot %d ·" % w["slot"] not in (ui["asgKv"] or ""):
                p.append("slot card %s" % ui["asgKv"])
            if w["path"] and ui["path"] != " → ".join(pretty(x) for x in w["path"]):
                p.append("route card %s" % ui["path"])
            if w["rejected_at"] and pretty(w["rejected_at"]) not in (ui["stage"] or ""):
                p.append("stage chip %s" % ui["stage"])
            if w["priority"] and ui["pri"] != [w["priority"]["final_priority"], pretty(w["priority"]["binary_priority"])]:
                p.append("priority chips %s" % ui["pri"])
            p += pipeline_problems(ui, w["pipeline"], w["rejected_at"])
            summary = "%s %s%s%s%s" % (res["request_id"], res["decision"],
                                       " at " + res["rejected_at"] if res.get("rejected_at") else "",
                                       " %s s%s" % (asg.get("room"), asg.get("slot")) if asg else "",
                                       " cost %s" % route.get("cost") if route else "")
            rec(area, "demo %d run %d: %s" % (i + 1, run, w["title"][:60]), not p, "; ".join(p) or summary)
            if i == 5:
                pr = res.get("priority") or {}
                ok = (pr.get("final_priority"), pr.get("binary_priority"), asg.get("room"), asg.get("slot"),
                      route.get("path"), route.get("cost")) == ("high", "urgent", "AI_Lab", 3,
                                                               ["Hostel", "Cafeteria", "Science_Block", "AI_Lab"], 6)
                rec(area, "handout full-service example (run %d): high/urgent, AI_Lab s3, cost 6" % run, ok,
                    "confidence %s" % pr.get("confidence"))
    watch.check(area, "demo scenarios")

    # ---- Clear resets every field to its default
    fill(page, [("type", "Full_Service_Request"), ("name", "Bilal"), ("role", "staff"), ("select", "#f-cat", "Maintenance"),
                ("select", "#f-loc", "Library"), ("slot", 4), ("fill", "#f-sev", "2"), ("fill", "#f-note", "x"),
                ("js", "() => { document.querySelector('#f-elig').checked = false; }")])
    page.click("#clear-btn")
    page.wait_for_timeout(400)
    state = page.evaluate("""() => { const f = document.querySelector('#req-form');
        return [f.name.value, f.role.value, document.querySelector('input[name="request_type"]:checked').value,
                f.current_location.value, f.category.value, document.querySelector('input[name="preferred_slot"]:checked').value,
                f.severity.value, f.time_sensitivity.value, f.crowd_level.value, f.eligibility.checked, f.description_note.value]; }""")
    defaults = ["", "student", "Navigation_Only", "", "AI_Lab_Support", "2", "8", "9", "5", True, ""]
    rec(area, "Clear resets every field (incl. role) to its default", state == defaults, state)

    # ---- the form for every request type
    page.click("#reset-btn")
    page.wait_for_timeout(600)
    for request_type, actions in MANUAL.items():
        fill(page, [("type", request_type)])
        shown = visible_fields(page)
        rec(area, "form fields for %s = cli.py" % request_type, shown == FORM_FIELDS[request_type], ", ".join(shown))
        fill(page, [("type", request_type)] + actions)
        body, res = submit(page)
        missing = [f for f in shown if f not in body and f != "description_note"]
        if any(a[0] == "fill" and a[1] == "#f-note" for a in actions) and "description_note" not in body:
            missing.append("description_note")
        extra = [k for k in body if k not in ["name", "role", "request_type"] + shown]
        ui = read_console(page)
        rec(area, "manual %s reaches the backend with every field" % request_type,
            not missing and not extra and body["request_type"] == request_type,
            "%s -> %s %s%s%s" % (json.dumps(body), res["request_id"], res["decision"],
                                 " MISSING %s" % missing if missing else "", " EXTRA %s" % extra if extra else ""))
        rec(area, "manual %s result rendered" % request_type, ui["title"] and ui["resultLen"] > 500,
            "%s: %s" % (ui["title"], ui["msg"]))
    fill(page, [("type", "Booking_or_Scheduling"), ("select", "#f-cat", "Viva_Scheduling")])
    page.wait_for_timeout(400)
    rec(area, "group_id field appears only for Viva_Scheduling", "group_id" in visible_fields(page), "")
    watch.check(area, "manual form")

    # ---- invalid input
    for label, actions, decision, stage, normalised in INVALID:
        fill(page, actions)
        body, res = submit(page)
        ui = read_console(page)
        ok = res["decision"] == decision and res.get("rejected_at") == stage and ui["resultLen"] > 500
        if normalised:
            ok = ok and res["trace"]["request"].get(normalised[0]) == normalised[1]
        if stage:
            ok = ok and bool(ui["callout"])
        shown = " | ".join(x for x in (ui["title"], ui["stage"], ui["callout"]) if x)
        rec("Invalid input", label, ok, "sent %s -> UI: %s" % (json.dumps(body), shown))
        page.evaluate(RESTORE_FORM_JS)
    watch.check("Invalid input", "invalid-input submissions")

    # ---- AI_Lab slot 2, four times
    page.click("#reset-btn")
    page.wait_for_timeout(700)
    slots = []
    for _ in range(4):
        fill(page, [("type", "Booking_or_Scheduling"), ("name", "Ali"), ("select", "#f-cat", "AI_Lab_Support"), ("slot", 2)])
        _, res = submit(page)
        slots.append(res["assignment"]["slot"] if res.get("assignment") else "rejected@%s" % res.get("rejected_at"))
    ui = read_console(page)
    rec(area, "AI_Lab slot 2 booked 4x = CSP rules (%s)" % " -> ".join(map(str, want["repeat_slots"])),
        slots == want["repeat_slots"], " -> ".join(map(str, slots)))
    rec(area, "4th booking: rejection shown with the reason", ui["title"] == "Rejected" and ui["callout"], ui["callout"])
    go(page, "csp")
    page.wait_for_timeout(800)
    grid = booking_grid(page)
    rec("CSP", "booking grid = backend bookings after requests", grid == server.bookings(), " ".join(grid))
    who = page.eval_on_selector_all("#booking-grid .cell.booked .who", "w => w.map((x) => x.textContent)")
    rec("CSP", "grid shows which request made each booking", sum(1 for x in who if x.startswith("REQ")) == 3, " ".join(who))
    with page.expect_response("**/api/request") as info:
        page.select_option("#tb-cat", "Maintenance")
        page.select_option("#tb-slot", "2")
        page.click('#try-booking button[type="submit"]')
    res = info.value.json()
    page.wait_for_function("() => document.querySelector('.cell.just-booked')", timeout=15000)
    rec("CSP", "quick booking (DrKhan, Maintenance s2) animates and grid = backend",
        booking_grid(page) == server.bookings() and res["decision"] == "accepted", "%s %s" % (res["request_id"], res.get("assignment")))
    page.click("#reset-btn")
    page.wait_for_timeout(900)
    grid = booking_grid(page)
    rec("CSP", "Reset restores the initial bookings (grid and backend)",
        grid == want["initial_bookings"] and server.bookings() == want["initial_bookings"], " ".join(grid))
    rec("Top bar", "Reset clears the history (UI counter and GET /api/history)",
        page.text_content("#hist-count") == "0" and server.get("/history") == [], page.text_content("#hist-count"))
    watch.check("CSP", "bookings")


# ===========================================================================
# 5. Campus map & search
# ===========================================================================
MAP_JS = """() => {
  const at = {};
  const nodes = [...document.querySelectorAll('#campus-map .nodes .node')];
  nodes.forEach((n) => { const m = n.getAttribute('transform').match(/translate\\(([\\d.]+),([\\d.]+)\\)/); at[(+m[1]) + ',' + (+m[2])] = n.dataset.name; });
  const edges = [...document.querySelectorAll('#campus-map .edges .edge')].map((e) => {
    const l = e.querySelector('line');
    const a = at[(+l.getAttribute('x1')) + ',' + (+l.getAttribute('y1'))]; const b = at[(+l.getAttribute('x2')) + ',' + (+l.getAttribute('y2'))];
    return [[a, b].sort().join('|'), +e.querySelector('.edge-cost').textContent]; });
  return { nodes: nodes.length, dots: document.querySelectorAll('#campus-map .node-dot').length,
           lines: document.querySelectorAll('#campus-map .edges line').length, edges };
}"""
SEARCH_STATE_JS = """() => ({ algo: document.querySelector('#policy-algo').textContent,
  cost: document.querySelector('#st-cost').textContent, steps: document.querySelector('#st-steps').textContent,
  exp: document.querySelector('#st-exp').textContent, path: document.querySelector('#st-path').textContent,
  strip: document.querySelectorAll('#exp-strip li').length, segs: document.querySelectorAll('#campus-map .path-seg').length })"""


def map_tests(page, want, watch):
    """
    Function: map_tests
    Purpose : The map's nodes / edges / costs, the search policy, the
              9-algorithm comparison and the replay of one row.
    Params  : page (Page), want (dict), watch (Watcher)
    Returns : None
    """
    area = "Map & search"
    go(page, "map")
    g = page.evaluate(MAP_JS)
    rec(area, "map has 13 nodes", g["nodes"] == 13 and g["dots"] == 13, "%d nodes" % g["nodes"])
    rec(area, "map has 19 edges", len(g["edges"]) == 19 and g["lines"] == 19, "%d lines" % g["lines"])
    drawn = sorted("%s=%d" % (k, c) for k, c in g["edges"])
    data = sorted("%s=%d" % ("|".join(sorted((a, b))), c) for a, b, c in EDGES)
    rec(area, "no Science_Block-Library edge", not any(k == "Library|Science_Block" for k, _ in g["edges"]), "")
    rec(area, "edges and costs = verified diagram data (total 44)", drawn == data and sum(c for _, c in g["edges"]) == 44,
        "total %d" % sum(c for _, c in g["edges"]))
    page.select_option("#m-src", "Hostel")
    page.select_option("#m-dst", "AI_Lab")
    for mode in ("weighted-h", "unweighted", "weighted"):
        w = want["policy"][mode]
        page.click('input[name="graph-mode"][value="%s"]' % mode, force=True)
        page.wait_for_timeout(200)
        before = page.text_content("#policy-algo")
        page.click("#m-run")
        page.wait_for_function("() => document.querySelector('#st-path').textContent.length > 0", timeout=30000)
        s = page.evaluate(SEARCH_STATE_JS)
        ok = (s["algo"] == before == w["algorithm_used"] and s["cost"] == str(w["cost"]) and s["steps"] == str(w["steps"])
              and s["path"] == " → ".join(pretty(x) for x in w["path"]) and s["strip"] == w["nodes_expanded"]
              and s["exp"] == str(w["nodes_expanded"]) and s["segs"] == len(w["path"]) - 1)
        rec(area, "%s Hostel -> AI_Lab = %s, cost %s, %s steps" % (mode, w["algorithm_used"], w["cost"], w["steps"]), ok,
            "UI: %s cost %s steps %s expanded %s, %s" % (s["algo"], s["cost"], s["steps"], s["exp"], s["path"]))
        if mode == "weighted-h":
            shot(page, "03_map_astar_route_hostel_ai_lab.png")
    page.click('input[name="graph-mode"][value="weighted-h"]', force=True)
    page.click('#campus-map .node[data-name="Main_Gate"] .node-dot')
    page.click('#campus-map .node[data-name="Seminar_Room"] .node-dot')
    picked = [page.input_value("#m-src"), page.input_value("#m-dst")]
    rec(area, "clicking map nodes sets source, then destination", picked == ["Main_Gate", "Seminar_Room"], " -> ".join(picked))
    for src, dst in COMPARE_PAIRS:
        page.select_option("#m-src", src)
        page.select_option("#m-dst", dst)
        page.fill("#dls-limit", str(DLS_LIMIT))
        page.click("#cmp-run")
        page.wait_for_function("() => document.querySelectorAll('#cmp-body tbody tr').length === 9", timeout=15000)
        page.wait_for_timeout(300)
        rows = page.eval_on_selector_all("#cmp-body tbody tr", "trs => trs.map((tr) => [...tr.children].map((td) => td.textContent.trim()))")
        p = []
        for row, w in zip(rows, want["compare"][(src, dst)]):
            name = "DLS (limit %d)" % DLS_LIMIT if w["algorithm_used"] == "DLS" else w["algorithm_used"]
            cells = [row[0].replace("optimal", "").strip(), row[1], row[2], row[3], row[4], row[5]]
            wanted = [name, "yes" if w["found"] else "no",
                      " → ".join(pretty(x) for x in w["path"]) if w["found"] else "–",
                      str(w["cost"]) if w["found"] else "–", str(w["steps"]) if w["found"] else "–", str(w["nodes_expanded"])]
            if cells != wanted:
                p.append("%s: %s != %s" % (name, cells, wanted))
        rec(area, "compare 9 algorithms %s -> %s = compare_algorithms()" % (src, dst), not p and len(rows) == 9,
            "; ".join(p) or " ".join("%s:%s/%d" % (w["algorithm_used"], w["cost"] if w["found"] else "x", w["nodes_expanded"])
                                     for w in want["compare"][(src, dst)]))
    w = want["compare"][COMPARE_PAIRS[-1]][3]                     # the DFS row of the last pair
    page.click("#cmp-body tbody tr:nth-child(4)")
    page.wait_for_timeout(400)
    mid = page.eval_on_selector_all("#exp-strip li", "l => l.length")
    playing = page.eval_on_selector("#cmp-body tbody tr:nth-child(4)", "tr => tr.classList.contains('is-playing')")
    page.wait_for_function("() => document.querySelector('#st-path').textContent.length > 0", timeout=30000)
    s = page.evaluate(SEARCH_STATE_JS)
    rec(area, "clicking a compare row replays its expansion (%s)" % w["algorithm_used"],
        playing and s["algo"] == w["algorithm_used"] and s["strip"] == w["nodes_expanded"] and mid < w["nodes_expanded"],
        "%d chips mid-animation, %d at the end, cost %s" % (mid, s["strip"], s["cost"]))
    watch.check(area, "map & search")
    if OPTIONS["shots"]:
        page.select_option("#m-src", "Hostel")
        page.select_option("#m-dst", "AI_Lab")
        page.click("#cmp-run")
        page.wait_for_function("() => document.querySelectorAll('#cmp-body tbody tr').length === 9")
        page.wait_for_timeout(1500)
        page.locator(".compare-card").screenshot(path=os.path.join(SHOT_DIR, "04_map_compare_9_algorithms.png"))


# ===========================================================================
# 6. Viva CSP, knowledge base, ANN
# ===========================================================================
def viva_tests(page, watch):
    """
    Function: viva_tests
    Purpose : Solve the viva timetable in the UI and check it in Python.
    Params  : page (Page), watch (Watcher)
    Returns : None
    """
    area = "CSP viva"
    go(page, "csp")
    with page.expect_response("**/api/viva/solve") as info:
        page.click("#viva-solve")
    res = info.value.json()
    page.wait_for_function("() => /Solved/.test(document.querySelector('#viva-log')?.lastElementChild?.textContent || '')",
                           timeout=120000)
    ui = page.evaluate("""() => ({ tried: document.querySelector('#viva-tried').textContent,
        bt: document.querySelector('#viva-bt').textContent,
        rows: [...document.querySelectorAll('#viva-table tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent.trim())),
        assigned: document.querySelectorAll('#viva-graph .v-node.assigned').length,
        log: document.querySelectorAll('#viva-log li').length })""")
    table = {}
    for row in ui["rows"]:
        for group in row[2].split(", "):
            if group and group != "–":
                table[group] = int(row[0].replace("Slot ", ""))
    rec(area, "timetable shown = /api/viva/solve", table == res["timetable"], json.dumps(table, sort_keys=True))
    rec(area, "timetable satisfies every constraint (checked in Python)",
        len(table) == 6 and test_logic_csp.is_valid_timetable(table), "G4=%s < G3=%s" % (table.get("G4"), table.get("G3")))
    rec(area, "stats shown (assignments tried / backtracks)",
        ui["tried"] == str(res["stats"]["assignments_tried"]) and ui["bt"] == str(res["stats"]["backtracks"]),
        "tried %s, backtracks %s" % (ui["tried"], ui["bt"]))
    rec(area, "animation played (6 groups assigned, log written)", ui["assigned"] == 6 and ui["log"] >= 7,
        "%d log lines for %d steps" % (ui["log"], len(res["steps"])))
    shot(page, "06_csp_viva_timetable_solved.png")
    watch.check(area, "viva")


def kb_tests(page, want, watch):
    """
    Function: kb_tests
    Purpose : Every example query against check_logic(), a malformed query
              and forward chaining.
    Params  : page (Page), want (dict), watch (Watcher)
    Returns : None
    """
    area = "Knowledge base"
    go(page, "kb")
    counts = page.evaluate("() => [document.querySelectorAll('#fact-list li').length, document.querySelectorAll('#rule-list li').length]")
    rec(area, "facts and rules R1-R15 listed", counts[1] == 15 and counts[0] == len(kb.FACTS), "%d facts, %d rules" % tuple(counts))
    chips = page.eval_on_selector_all("#sec-kb [data-query-chips] .chip", "c => c.map((x) => x.textContent)")
    for i, query in enumerate(chips):
        w = logic_answer(query)
        with page.expect_response("**/api/kb/query") as info:
            page.click("#sec-kb [data-query-chips] .chip:nth-child(%d)" % (i + 1))
        res = info.value.json()
        page.wait_for_function("() => !document.querySelector('#kb-verdict').hidden", timeout=20000)
        ui = page.evaluate("""() => ({ verdict: document.querySelector('#kb-verdict strong').textContent,
            answers: [...document.querySelectorAll('#kb-verdict .answers span')].map((x) => x.textContent),
            cards: [...document.querySelectorAll('#kb-proof .pcard')].map((c) => c.querySelector('.pk').textContent + ': ' + c.querySelector('.pt').textContent) })""")
        answers = [", ".join("%s = %s" % kv for kv in a.items()) for a in w["answers"]]
        p = []
        if res["entailed"] != w["entailed"] or ui["verdict"].startswith("Entailed") != w["entailed"]:
            p.append("entailed differs")
        if res["explanation"] != w["explanation"]:
            p.append("explanation differs")
        if ui["answers"] != answers:
            p.append("answers %s" % ui["answers"])
        for m in w["missing"]:
            if not any(c.startswith("Missing premise") and m in c for c in ui["cards"]):
                p.append("missing premise %s not shown" % m)
        if w["entailed"] and not any(c.startswith("Derived") for c in ui["cards"]):
            p.append("no derived step")
        rec(area, "query %s = check_logic()" % query, not p,
            "; ".join(p) or "%s %s | proof: %s" % (ui["verdict"], ui["answers"] or "", " > ".join(ui["cards"])))
        if query == "UsesLab(DrKhan, Lab1)":
            shot(page, "07_kb_proof_UsesLab_DrKhan.png")
        if query == "Eligible(Sara, AI)":
            shot(page, "08_kb_not_entailed_missing_premise.png")
    page.fill("#kb-query", "UsesLab(DrKhan")
    page.press("#kb-query", "Enter")
    page.wait_for_timeout(1200)
    verdict = page.evaluate("() => document.querySelector('#kb-verdict').hidden ? '' : document.querySelector('#kb-verdict').textContent")
    rec(area, "malformed query on the KB page gives a clear message", "Malformed query" in verdict, verdict)
    page.click("#kb-forward")
    page.wait_for_function("() => /Fixed point/.test(document.querySelector('#forward-log')?.lastElementChild?.textContent || '')", timeout=60000)
    derived = page.eval_on_selector_all("#forward-log li .fact", "l => l.map((x) => x.textContent)")
    in_list = page.eval_on_selector_all("#fact-list li.derived", "l => l.length")
    rec(area, "forward chaining shows the derived facts = forward_chain()", derived == want["forward"] and in_list == len(derived),
        "%d derived" % len(derived))
    shot(page, "09_kb_forward_chaining.png")
    watch.check(area, "knowledge base")


def ann_tests(page, want, watch):
    """
    Function: ann_tests
    Purpose : The handout ANN example against predict_priority(), and the
              metrics against train.evaluate().
    Params  : page (Page), want (dict), watch (Watcher)
    Returns : None
    """
    area = "ANN"
    go(page, "ann")
    page.evaluate("""(f) => { document.querySelector('#a-role').value = f[0]; document.querySelector('#a-type').value = f[1];
        [['#a-sev', 2], ['#a-time', 3], ['#a-crowd', 4], ['#a-dist', 5]].forEach(([id, i]) => {
          const r = document.querySelector(id); r.value = f[i]; r.dispatchEvent(new Event('input', { bubbles: true })); });
        document.querySelector('#a-elig').checked = !!f[6]; }""", [0, 0, 8, 9, 5, 4, 1])
    with page.expect_response("**/api/ann/predict") as info:
        page.click('#ann-form button[type="submit"]')
    sent = info.value.request.post_data_json
    res = info.value.json()
    page.wait_for_function("() => document.querySelector('#ann-verdict').children.length === 2", timeout=20000)
    page.wait_for_timeout(1500)
    ui = page.evaluate("""() => ({ verdict: document.querySelector('#ann-verdict').textContent,
        perceptron: document.querySelector('#perceptron').textContent, lit: document.querySelectorAll('#ann-net .a-neuron.lit').length })""")
    w = want["ann"]
    ok = (sent["features"] == [0, 0, 8, 9, 5, 4, 1] and all(res[k] == w[k] for k in ("final_priority", "binary_priority", "confidence"))
          and "%s (%.2f)" % (w["final_priority"], w["confidence"]) in ui["verdict"] and "urgent" in ui["verdict"])
    rec(area, "[0,0,8,9,5,4,1] -> high / urgent, same confidence as predict_priority()", ok,
        "UI: %s | Python: %s" % (ui["verdict"], w))
    rec(area, "network animation lit all 18 neurons; perceptron output shown", ui["lit"] == 18 and "Urgent" in ui["perceptron"],
        "%d lit" % ui["lit"])
    m = page.evaluate("""() => ({ acc: document.querySelector('#acc-bars').textContent,
        mlp: [...document.querySelectorAll('#cm-mlp .cm-c')].map((x) => +x.textContent),
        perc: [...document.querySelectorAll('#cm-perc .cm-c')].map((x) => +x.textContent),
        loss: (document.querySelector('#loss-curve polyline')?.getAttribute('points') || '').split(' ').length })""")
    ev = want["metrics"]
    acc = [100 * ev["mlp_accuracy"], 100 * ev["noise_ceiling"], 100 * ev["perceptron_accuracy"]]
    rec(area, "metrics: MLP %.2f%%, ceiling %.2f%%, Perceptron %.2f%%" % tuple(acc),
        all("%.2f%%" % v in m["acc"] for v in acc), m["acc"][:120])
    rec(area, "confusion matrices render and = train.evaluate()",
        m["mlp"] == [v for row in ev["mlp_confusion"] for v in row] and m["perc"] == [v for row in ev["perceptron_confusion"] for v in row],
        "%d + %d cells" % (len(m["mlp"]), len(m["perc"])))
    rec(area, "loss curve renders", m["loss"] > 5, "%d points" % m["loss"])
    if OPTIONS["shots"]:
        page.evaluate("() => window.scrollTo(0, 0)")
        shot(page, "10_ann_prediction_handout_example.png", full=False)
        page.locator("#cm-mlp").scroll_into_view_if_needed()
        page.wait_for_timeout(1800)
        shot(page, "11_ann_full_page_prediction_and_metrics.png")
    watch.check(area, "ANN")


# ===========================================================================
# 7. Reduced motion, history, theme, reload, server stopped
# ===========================================================================
def reduced_motion_tests(browser, server, watch):
    """
    Function: reduced_motion_tests
    Purpose : The main features with prefers-reduced-motion: reduce.
    Params  : browser (Browser), server (Server), watch (Watcher)
    Returns : None
    """
    area = "Reduced motion"
    ctx = browser.new_context(viewport=VIEWPORT, reduced_motion="reduce")
    page = ctx.new_page()
    watch.attach(page, "reduced")
    page.goto(server.base + "/")
    page.wait_for_function("() => document.querySelectorAll('#demo-select option').length === 10")
    matches = page.evaluate("() => matchMedia('(prefers-reduced-motion: reduce)').matches")
    res = run_demo(page, 5)
    rec(area, "handout full-service demo works", matches and res["assignment"]["slot"] == 3 and res["route"]["cost"] == 6,
        "media query matches: %s" % matches)
    go(page, "map")
    page.click("#m-run")
    page.wait_for_function("() => document.querySelector('#st-path').textContent.length > 0", timeout=20000)
    rec(area, "map search works", page.text_content("#st-cost") == "6", page.text_content("#st-path"))
    page.click("#cmp-run")
    page.wait_for_function("() => document.querySelectorAll('#cmp-body tbody tr').length === 9")
    page.click("#cmp-body tbody tr:nth-child(4)")
    page.wait_for_timeout(1500)
    rec(area, "compare + row replay works", page.text_content("#policy-algo") == "DFS", page.text_content("#st-path"))
    go(page, "csp")
    page.click("#viva-solve")
    page.wait_for_function("() => /Solved/.test(document.querySelector('#viva-log')?.lastElementChild?.textContent || '')", timeout=30000)
    rec(area, "viva solver works", page.eval_on_selector_all("#viva-graph .v-node.assigned", "l => l.length") == 6, "")
    go(page, "kb")
    page.click("#sec-kb [data-query-chips] .chip:nth-child(3)")
    page.wait_for_function("() => !document.querySelector('#kb-verdict').hidden")
    rec(area, "KB query works", "x = Ali" in page.text_content("#kb-verdict"), "")
    page.click("#kb-forward")
    page.wait_for_function("() => /Fixed point/.test(document.querySelector('#forward-log').textContent)", timeout=20000)
    rec(area, "forward chaining works", True, "")
    go(page, "ann")
    page.click('#ann-form button[type="submit"]')
    page.wait_for_function("() => document.querySelector('#ann-verdict').children.length === 2")
    rec(area, "ANN prediction works", True, page.text_content("#ann-verdict"))
    page.click("#theme-toggle")
    rec(area, "theme toggle works", page.evaluate("() => document.documentElement.dataset.theme") == "light", "")
    watch.check(area, "reduced motion")
    ctx.close()


CONTRAST_JS = """() => {
  const lum = (c) => { let m = c.match(/[\\d.]+/g).map(Number); if (c.startsWith('color(')) m = m.map((v) => v * 255);
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(m[0]) + 0.7152 * f(m[1]) + 0.0722 * f(m[2]); };
  const bgOf = (el) => { while (el) { const b = getComputedStyle(el).backgroundColor; const a = b.match(/[\\d.]+/g);
    if (a && (a.length < 4 || +a[a.length - 1] > 0.5)) return b; el = el.parentElement; } return 'rgb(255, 255, 255)'; };
  const low = [];
  document.querySelectorAll('body *').forEach((el) => {
    if (!el.offsetParent) return;
    const text = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    if (text.length < 2) return;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || +cs.opacity < 0.3) return;
    const a = lum(cs.color); const b = lum(bgOf(el));
    const r = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    if (r < 3) low.push(text.slice(0, 24) + ' (' + r.toFixed(2) + ')'); });
  return low;
}"""


def history_tests(page, server, watch):
    """
    Function: history_tests
    Purpose : History (also after a reload), counters, the theme in both
              modes, and the message when the server is stopped (run last).
    Params  : page (Page), server (Server), watch (Watcher)
    Returns : None
    """
    area = "History & top bar"
    page.click("#reset-btn")
    page.wait_for_timeout(700)
    go(page, "console")
    made = []
    for i in (0, 1, 5, 6, 8):
        res = run_demo(page, i)
        made.append([res["request_id"], res["decision"]])
    go(page, "history")
    items = timeline(page)
    server_items = [[e["response"]["request_id"], e["response"]["decision"]] for e in reversed(server.get("/history"))]
    rec(area, "History lists every request with its ID and decision (newest first) = GET /api/history",
        items == made[::-1] == server_items, ", ".join(" ".join(x) for x in items))
    counts = [page.text_content("#hist-count"), page.text_content("#nav-count")]
    rec(area, "request counters (top bar + sidebar) match", counts == [str(len(made))] * 2, " / ".join(counts))
    page.click("#timeline li:nth-child(3) .t-item")
    wait_pipeline(page, made[2][0])
    ui = read_console(page)
    rec(area, "reopening a History item shows its result", (ui["kicker"] or "").startswith(made[2][0]) and ui["title"] == "Accepted",
        ui["kicker"])
    page.click("#history-counter")
    page.wait_for_timeout(300)
    rec(area, "clicking the request counter opens History", page.evaluate("() => !document.querySelector('#sec-history').hidden"), "")
    for theme in ("dark", "light"):
        if page.evaluate("() => document.documentElement.dataset.theme") != theme:
            page.click("#theme-toggle")
        page.wait_for_timeout(1200)
        low = []
        for section in ("console", "map", "csp", "kb", "ann", "history"):
            go(page, section)
            page.wait_for_timeout(700)
            low += ["%s: %s" % (section, x) for x in page.evaluate(CONTRAST_JS)]
        rec(area, "%s theme: toggle works, all text contrast >= 3:1" % theme,
            page.evaluate("() => document.documentElement.dataset.theme") == theme and not low, ", ".join(low[:8]) or "all text >= 3:1")
        if theme == "light" and OPTIONS["shots"]:
            go(page, "console")
            run_demo(page, 5)
            page.evaluate("() => window.scrollTo(0, 0)")
            shot(page, "13_console_light_theme.png")
    page.click("#theme-toggle")
    rec(area, "theme choice remembered", page.evaluate("() => localStorage.getItem('sc-theme')") == "dark", "")
    watch.check(area, "history / theme")

    area = "General"
    before = timeline(page)
    page.reload()
    page.wait_for_function("() => document.querySelectorAll('#demo-select option').length === 10 && document.querySelectorAll('#campus-map .node').length === 13")
    page.wait_for_timeout(800)
    after = timeline(page)
    rec(area, "reload mid-session: page loads, History kept (loaded from the server)",
        after == before and page.text_content("#hist-count") == str(len(before)), "%d items before, %d after" % (len(before), len(after)))
    res = run_demo(page, 0)
    rec(area, "after reload the next request continues the ids", int(res["request_id"][3:]) == int(before[0][0][3:]) + 1,
        "%s after %s" % (res["request_id"], before[0][0]))
    watch.check(area, "reload")
    server.stop()
    fill(page, [("type", "Navigation_Only"), ("name", "Ali"), ("select", "#f-loc", "Hostel"), ("select", "#f-dest", "Library")])
    page.click("#submit-btn")
    page.wait_for_timeout(2500)
    toast = page.evaluate("() => document.querySelector('#toast').hidden ? '' : document.querySelector('#toast').textContent")
    busy = page.evaluate("() => document.querySelector('#submit-btn').classList.contains('is-busy')")
    kept = page.evaluate("() => document.querySelector('#result').innerHTML.length") > 500
    crashes = [e for e in watch.take() if "pageerror" in e]
    rec(area, 'server stopped: friendly "server not reachable" message, no crash',
        "not reachable" in toast and not crashes and kept and not busy, "toast: %s" % toast)


def screenshot_pass(page):
    """
    Function: screenshot_pass
    Purpose : A clean session for the report screenshots (dark theme).
    Params  : page (Page)
    Returns : None
    """
    page.evaluate("() => localStorage.setItem('sc-theme', 'dark')")
    page.reload()
    page.wait_for_function("() => document.querySelectorAll('#demo-select option').length === 10")
    page.click("#reset-btn")
    page.wait_for_timeout(800)
    go(page, "console")
    names = {5: "01_console_handout_full_service_example.png", 7: "02_console_rejection_at_logic.png",
             8: "02b_console_rejection_at_preprocessing.png"}
    for i in range(9):
        run_demo(page, i)
        if i in names:
            page.evaluate("() => window.scrollTo(0, 0)")
            shot(page, names[i])
    go(page, "csp")
    page.select_option("#tb-cat", "AI_Lab_Support")
    page.select_option("#tb-slot", "2")
    page.click('#try-booking button[type="submit"]')
    page.wait_for_function("() => document.querySelector('.cell.just-booked')", timeout=15000)
    page.wait_for_timeout(800)
    page.evaluate("() => window.scrollTo(0, 0)")
    shot(page, "05_csp_booking_grid.png")
    go(page, "history")
    shot(page, "12_history.png")


# ===========================================================================
# 8. Main
# ===========================================================================
def launch(playwright, channel):
    """
    Function: launch
    Purpose : Start a headless browser: the given channel, else Playwright's
              Chromium, else the installed Microsoft Edge.
    Params  : playwright, channel (str or None) - "msedge", "chrome", ...
    Returns : (Browser, str name)
    """
    if channel:
        return playwright.chromium.launch(channel=channel, headless=True), channel
    try:
        return playwright.chromium.launch(headless=True), "chromium"
    except Exception:                          # browsers not installed: use Edge
        return playwright.chromium.launch(channel="msedge", headless=True), "msedge"


def run(argv=None):
    """
    Function: run
    Purpose : Run every check, print the summary and save the results.
    Params  : argv (list or None)
    Returns : int - 0 when every check passed, else 1
    """
    parser = argparse.ArgumentParser(description="End-to-end test of the web UI")
    parser.add_argument("--shots", action="store_true", help="save the report screenshots in docs/screenshots/")
    parser.add_argument("--channel", help="browser channel, e.g. msedge or chrome")
    parser.add_argument("--only", default="", help="comma list: console,map,viva,kb,ann,reduced,history")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # "→" in route texts on a Windows console
    OPTIONS["shots"] = args.shots
    only = [x for x in args.only.split(",") if x]
    if args.shots:
        os.makedirs(SHOT_DIR, exist_ok=True)
    print("Computing the expected values with the Python modules ...")
    want = expected()
    server = Server(free_port())
    server.start()
    watch = Watcher()
    started = time.time()
    name = ""
    try:
        with sync_playwright() as p:
            browser, name = launch(p, args.channel)
            page = browser.new_context(viewport=VIEWPORT).new_page()
            watch.attach(page, "main")
            page.goto(server.base + "/")
            page.wait_for_function("() => document.querySelectorAll('#demo-select option').length === 10 && document.querySelectorAll('#campus-map .node').length === 13",
                                   timeout=30000)
            rec("Setup", "UI loads in live mode (USE_MOCK = false)", page.text_content("#api-mode-text") == "Live API",
                page.text_content("#api-mode-text"))
            page.click("#reset-btn")
            page.wait_for_timeout(500)
            watch.check("Setup", "first load")
            phases = [("console", lambda: console_tests(page, server, want, watch)), ("map", lambda: map_tests(page, want, watch)),
                      ("viva", lambda: viva_tests(page, watch)), ("kb", lambda: kb_tests(page, want, watch)),
                      ("ann", lambda: ann_tests(page, want, watch)), ("reduced", lambda: reduced_motion_tests(browser, server, watch)),
                      ("shots", lambda: screenshot_pass(page) if args.shots else None),
                      ("history", lambda: history_tests(page, server, watch))]
            for key, phase in phases:
                if only and key not in only and key != "shots":
                    continue
                try:
                    phase()
                except Exception as exc:       # a broken step must not hide the other results
                    rec(key, "phase stopped with an error", False, str(exc).split("\n")[0])
                    watch.take()
            browser.close()
    finally:
        server.stop()
    passed = sum(1 for r in RESULTS if r["pass"])
    print("\n%d/%d checks passed in %d s" % (passed, len(RESULTS), time.time() - started))
    if not only:
        os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
        with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
            json.dump({"date": datetime.now().isoformat(timespec="seconds"), "browser": name,
                       "viewport": "%dx%d" % (VIEWPORT["width"], VIEWPORT["height"]),
                       "passed": passed, "total": len(RESULTS), "results": RESULTS}, fh, indent=1)
        print("Results saved to %s" % os.path.relpath(RESULTS_PATH, ROOT))
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(run())
