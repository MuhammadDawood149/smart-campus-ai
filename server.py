"""
File    : server.py
Module  : Web server for the UI in web/ (an extra interface, like cli.py)
Owner   : Joint (Students 1, 2 and 3)

Purpose : Serves the single-page UI in web/ and implements every endpoint that
          web/api.js calls, using the real modules:
              POST /api/request          main.process_request (whole pipeline)
              GET  /api/demo-scenarios   integration.demo_scenarios
              GET  /api/graph            shared.campus_data + Search heuristic k
              POST /api/search           Search policy (BFS / A* / UCS)
              POST /api/search/compare   all 9 search algorithms
              GET  /api/bookings         current CSP bookings
              POST /api/viva/solve       viva timetable CSP with its step log
              GET  /api/kb               facts and rules R1-R15
              POST /api/kb/query         backward chaining with a proof
              POST /api/kb/forward       forward chaining log
              POST /api/ann/predict      MLP + Perceptron for one feature vector
              GET  /api/ann/metrics      test accuracy, confusion matrices, loss
              GET  /api/history          the requests processed this session
              POST /api/reset            main.reset_system ({"keep_counter": true}
                                         = bookings only, before a demo scenario)
          The modules decide everything; this file only reshapes their outputs
          into the JSON the UI reads (field names match the mock in api.js).

Rules   : the only file (with cli.py) that does I/O. AI modules are not changed
          by it. Bad input gives HTTP 400 with {"error": "..."}.
Run     : python server.py            (opens the browser at http://127.0.0.1:5000)
          python server.py --port 8000 --no-browser
"""

import argparse
import os
from datetime import datetime
import sys
import threading
import webbrowser

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import main
from integration import preprocessing as pre
from integration.demo_scenarios import DEMO_SCENARIOS
from shared.campus_data import NODES, EDGES
from student1_search import search_module as search
from student2_logic_csp import csp_scheduler as csp
from student2_logic_csp import logic_kb as kb
from student3_ann import ann_module as ann
from student3_ann import train

WEB_DIR = os.path.join(ROOT, "web")
HANDOUT_RULES = ["R1", "R2", "R3", "R4"]      # R5-R15 are team-defined
MAX_DLS_LIMIT = 12

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
app.json.sort_keys = False                    # keep the handout field order
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0   # always serve the latest web/ files

LOCK = threading.Lock()      # one request at a time touches the shared session state
BOOKED_BY = {}               # (room, slot) -> request_id that made the booking
HISTORY = []                 # every request processed this session: {request, response, time}
CACHE = {"metrics": None}


class BadRequest(Exception):
    """Raised by the endpoints for invalid input; becomes HTTP 400."""


# ===========================================================================
# 1. Small helpers
# ===========================================================================
def body():
    """
    Function: body
    Purpose : The JSON body of the current request (an empty dict if none).
    Params  : none
    Returns : dict (raises BadRequest if the body is not a JSON object)
    """
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise BadRequest("request body must be a JSON object")
    return data


def location(value, field):
    """
    Function: location
    Purpose : Turn user text into an exact node name with Search's normaliser.
    Params  : value - raw text, field (str) - name used in the error message
    Returns : str node name (raises BadRequest if unknown)
    """
    node, error = search.normalize_location(value)
    if error:
        raise BadRequest("%s: %s" % (field, error))
    return node


def rule_body(rule):
    """
    Function: rule_body
    Purpose : A rule as text without its id: "Teaches(x, AI) => Instructor(x, AI)".
    Params  : rule (dict) - a rule from logic_kb.RULES
    Returns : str
    """
    return kb.rule_text(rule).split(": ", 1)[1]


def answer_texts(answers):
    """
    Function: answer_texts
    Purpose : Write variable bindings as text, one string per answer.
    Params  : answers (list of dicts {variable: constant})
    Returns : list of str, e.g. ["x = DrKhan", "x = Ali"]
    """
    return [", ".join("%s = %s" % (v, c) for v, c in a.items()) for a in answers if a]


# ===========================================================================
# 2. Logic proofs as steps for the UI
# ===========================================================================
def proof_steps(tree, steps):
    """
    Function: proof_steps
    Purpose : Flatten a backward-chaining proof tree into the order it is read:
              facts first, then the rule that uses them, then what it concludes.
    Params  : tree (resolved proof node from logic_kb.backward_chain),
              steps (list) - filled in place
    Returns : list of {"type": "fact" / "rule" / "conclusion", "text", "rule"}
    """
    if tree["rule"] is None:
        step = {"type": "fact", "text": kb.atom_text(tree["atom"])}
        if step not in steps:
            steps.append(step)
        return steps
    for child in tree["children"]:
        proof_steps(child, steps)
    steps.append({"type": "rule", "rule": tree["rule"]["id"], "text": rule_body(tree["rule"])})
    steps.append({"type": "conclusion", "text": kb.atom_text(tree["atom"])})
    return steps


def failure_steps(goal):
    """
    Function: failure_steps
    Purpose : Steps that show why a goal is not entailed: the missing premise,
              then each rule (innermost first) that could not fire because of it.
    Params  : goal (atom)
    Returns : list of {"type": "missing" / "blocked", "text", "rule"}
    """
    rules = {r["id"]: r for r in kb.RULES}
    steps = []
    for path, atom in kb.find_missing(goal, kb.FACTS, kb.RULES, [0]):
        steps.append({"type": "missing", "text": kb.atom_text(atom)})
        for rule_id in reversed(path):
            step = {"type": "blocked", "rule": rule_id, "text": rule_body(rules[rule_id])}
            if step not in steps:
                steps.append(step)
    return steps


def kb_query(text):
    """
    Function: kb_query
    Purpose : Answer one FOL query with the Logic module (the same path as an
              Eligibility_Check) and add proof steps for the UI.
    Params  : text (str) - e.g. "UsesLab(DrKhan, Lab1)" or "UsesLab(x, Lab1)"
    Returns : dict {query, entailed, explanation, proof, missing, answers}
    """
    result = kb.check_logic({"request_type": "Eligibility_Check", "query": text})
    out = {"query": result["query"] or text, "entailed": result["entailed"],
           "explanation": result["explanation"], "proof": [],
           "missing": result["missing"], "answers": answer_texts(result["answers"])}
    if result["error"]:
        return out
    goal, _ = kb.parse_atom(text)
    if result["entailed"]:
        out["proof"] = proof_steps(kb.backward_chain(goal, find_all=False)[0]["tree"], [])
    else:
        out["proof"] = failure_steps(goal)
    return out


# ===========================================================================
# 3. The full pipeline: shape the final response for the UI
# ===========================================================================
def form_to_request(data):
    """
    Function: form_to_request
    Purpose : The UI form calls the claim checkbox "eligibility"; the request
              template calls it "eligibility_claim".
    Params  : data (dict) - JSON body from the UI
    Returns : dict - raw request for main.process_request
    """
    raw = dict(data)
    if "eligibility" in raw and "eligibility_claim" not in raw:
        raw["eligibility_claim"] = raw.pop("eligibility")
    return raw


def deadline_for(final_priority):
    """
    Function: deadline_for
    Purpose : Latest allowed slot for an ANN priority (same table the CSP uses).
    Params  : final_priority (str or None) - e.g. "high"
    Returns : int
    """
    if not final_priority:
        return csp.DEFAULT_DEADLINE
    return csp.PRIORITY_DEADLINE.get(final_priority.capitalize(), csp.DEFAULT_DEADLINE)


def ui_response(response):
    """
    Function: ui_response
    Purpose : Add the details the UI shows to the handout response, taken from
              the trace: ANN probabilities and features, the logic query / proof /
              missing premises, the CSP preference / deadline / notes and the
              nodes Search expanded. Handout fields are never changed, only added to.
              The raw module outputs are then dropped from the trace.
    Params  : response (dict) - main.process_request(..., with_trace=True) result
    Returns : dict - the same response, extended
    """
    trace = response["trace"]
    modules = trace.pop("modules")
    req = trace["request"]
    priority = response.get("priority")
    if priority and "ann" in modules:
        details = ann.explain_prediction(req["ann_features"])
        priority["probabilities"] = details.get("probabilities", {})
        priority["features"] = req["ann_features"]

    logic = modules.get("logic")
    eligibility = response.get("eligibility")
    if logic and eligibility is not None:
        eligibility.setdefault("allowed", logic["allowed"])
        eligibility.setdefault("explanation", logic["explanation"])
        eligibility["query"] = logic["query"]
        eligibility["proof"] = logic["proof"]
        eligibility["missing"] = logic["missing"]
        eligibility["answers"] = answer_texts(logic["answers"])

    assignment = response.get("assignment")
    if assignment and "csp" in modules:
        label = priority["final_priority"] if priority else None
        assignment["preferred_slot"] = req["preferred_slot"]
        assignment["priority"] = label
        assignment["deadline"] = deadline_for(label)
        assignment["notes"] = modules["csp"]["notes"]

    route_info = response.get("route")
    if route_info and "search" in modules:
        route_info["nodes_expanded"] = modules["search"]["route"]["nodes_expanded"]
    return response


def run_request(raw, form):
    """
    Function: run_request
    Purpose : Run one request through main.process_request, remember which
              request made each new booking (shown in the bookings grid) and
              add it to the session history (shown on the History page).
    Params  : raw (dict) - raw request fields, form (dict) - the body as the UI sent it
    Returns : dict - final response for the UI
    """
    state = main.SESSION["csp"]
    before = set(state["bookings"])
    response = main.process_request(raw, with_trace=True)
    after = set(state["bookings"])
    for pair in before - after:
        BOOKED_BY.pop(pair, None)
    for pair in after - before:
        BOOKED_BY[pair] = response["request_id"]
    response = ui_response(response)
    HISTORY.append({"request": form, "response": response,
                    "time": datetime.now().isoformat(timespec="seconds")})
    return response


def demo_for_form(raw):
    """
    Function: demo_for_form
    Purpose : The UI form uses drop-downs, so known categories, locations and
              groups are given their canonical names (an unknown location such
              as Sports_Complex is kept, so preprocessing still rejects it).
              Free-text fields (name) stay as typed and are normalised later.
    Params  : raw (dict) - a demo request from integration.demo_scenarios
    Returns : dict
    """
    out = form_to_request(raw)
    out.pop("eligibility_claim", None)
    if "eligibility_claim" in raw:
        out["eligibility"] = bool(raw["eligibility_claim"])
    if "category" in out:
        out["category"] = pre.check_category(out["category"])[0] or out["category"]
    for field in ("current_location", "destination"):
        if field in out:
            out[field] = pre.check_location(out[field], field)[0] or out[field]
    if "group_id" in out:
        out["group_id"] = pre.check_group(out["group_id"])[0] or out["group_id"]
    return out


# ===========================================================================
# 4. Endpoints
# ===========================================================================
@app.route("/")
def index():
    """
    Function: index
    Purpose : Serve the UI.
    Params  : none
    Returns : web/index.html
    """
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/favicon.ico")
def favicon():
    """
    Function: favicon
    Purpose : The UI has no icon; answer "no content" instead of a 404.
    Params  : none
    Returns : empty 204 response
    """
    return "", 204


@app.post("/api/request")
def api_request():
    """
    Function: api_request
    Purpose : Run a request from the console form through the whole system.
    Params  : JSON body - raw request fields
    Returns : JSON final response (handout format + trace + UI details)
    """
    form = body()
    with LOCK:
        return jsonify(run_request(form_to_request(form), form))


@app.get("/api/demo-scenarios")
def api_demo_scenarios():
    """
    Function: api_demo_scenarios
    Purpose : The demo scenarios, ready to fill the console form.
    Params  : none
    Returns : JSON list of {"name", "request"}
    """
    return jsonify([{"name": d["title"], "request": demo_for_form(d["request"])}
                    for d in DEMO_SCENARIOS])


@app.get("/api/graph")
def api_graph():
    """
    Function: api_graph
    Purpose : The campus graph and the heuristic scale factor k.
    Params  : none
    Returns : JSON {"nodes": [{name, x, y}], "edges": [{a, b, cost}], "heuristic_k"}
    """
    return jsonify({"nodes": [{"name": n, "x": x, "y": y} for n, (x, y) in NODES.items()],
                    "edges": [{"a": a, "b": b, "cost": c} for a, b, c in EDGES],
                    "heuristic_k": round(search.K, 6)})


@app.post("/api/search")
def api_search():
    """
    Function: api_search
    Purpose : Run the search policy: unweighted -> BFS, weighted + heuristic -> A*,
              weighted without heuristic -> UCS.
    Params  : JSON body {source, destination, graph_type, heuristic_available}
    Returns : JSON search result incl. expanded_order
    """
    data = body()
    source = location(data.get("source"), "source")
    destination = location(data.get("destination"), "destination")
    try:
        name = search.select_algorithm(data.get("graph_type", "weighted"),
                                       bool(data.get("heuristic_available", True)))
    except ValueError as exc:
        raise BadRequest(str(exc))
    return jsonify(search.run_algorithm(name, source, destination, weighted=(name != "BFS")))


@app.post("/api/search/compare")
def api_compare():
    """
    Function: api_compare
    Purpose : Run all 9 algorithms on the weighted graph for comparison.
    Params  : JSON body {source, destination, dls_limit}
    Returns : JSON list of 9 search results
    """
    data = body()
    source = location(data.get("source"), "source")
    destination = location(data.get("destination"), "destination")
    limit = pre.read_int(data.get("dls_limit", search.DEFAULT_DLS_LIMIT))
    if limit is None or not 0 <= limit <= MAX_DLS_LIMIT:
        raise BadRequest("dls_limit must be a whole number 0-%d" % MAX_DLS_LIMIT)
    return jsonify(search.compare_algorithms(source, destination, limit))


@app.get("/api/bookings")
def api_bookings():
    """
    Function: api_bookings
    Purpose : The current room/slot bookings and which request made each one
              (initial bookings have no request id).
    Params  : none
    Returns : JSON list of {"room", "slot", "request_id"}
    """
    with LOCK:
        return jsonify([{"room": room, "slot": slot, "request_id": BOOKED_BY.get((room, slot))}
                        for room, slot in main.get_bookings()["bookings"]])


@app.post("/api/viva/solve")
def api_viva_solve():
    """
    Function: api_viva_solve
    Purpose : Solve the G1..G6 viva timetable (no preferences) and return every
              assign / backtrack step so the UI can replay the search.
    Params  : none
    Returns : JSON {"timetable", "steps": [{group, slot, action}],
                    "stats": {assignments_tried, backtracks}}
    """
    log = []
    variables, domains, constraints = csp.viva_problem()
    timetable, stats = csp.solve_csp(variables, domains, constraints, log=log)
    return jsonify({"timetable": timetable or {},
                    "steps": [{"group": s["variable"], "slot": s["value"], "action": s["action"]}
                              for s in log],
                    "stats": {"assignments_tried": stats["assignments"],
                              "backtracks": stats["backtracks"]}})


@app.get("/api/kb")
def api_kb():
    """
    Function: api_kb
    Purpose : The knowledge base: facts and rules (handout R1-R4, team R5-R15).
    Params  : none
    Returns : JSON {"facts": [str], "rules": [{id, text, source}]}
    """
    return jsonify({"facts": [kb.atom_text(f) for f in kb.FACTS],
                    "rules": [{"id": r["id"], "text": rule_body(r),
                               "source": "handout" if r["id"] in HANDOUT_RULES else "team"}
                              for r in kb.RULES]})


@app.post("/api/kb/query")
def api_kb_query():
    """
    Function: api_kb_query
    Purpose : Answer a FOL query by backward chaining.
    Params  : JSON body {"query": str}
    Returns : JSON {query, entailed, explanation, proof, missing, answers}
    """
    return jsonify(kb_query(body().get("query")))


@app.post("/api/kb/forward")
def api_kb_forward():
    """
    Function: api_kb_forward
    Purpose : Forward chaining to a fixed point.
    Params  : none
    Returns : JSON {"log": ["R2 fired -> Instructor(DrKhan, AI)", ...], "rounds"}
    """
    result = kb.forward_chain()
    return jsonify({"log": ["%s fired -> %s" % (e["rule"], kb.atom_text(e["derived"]))
                            for e in result["log"]],
                    "rounds": kb.format_log(result["log"])})


@app.post("/api/ann/predict")
def api_ann_predict():
    """
    Function: api_ann_predict
    Purpose : Predict the priority of one raw feature vector with both models,
              plus the values the UI animates (hidden activations, perceptron sum).
    Params  : JSON body {"features": 7 raw numbers in FEATURE_ORDER}
    Returns : JSON {binary_priority, final_priority, confidence, probabilities,
                    scaled_features, activations, perceptron}
    """
    features = body().get("features")
    details = ann.explain_prediction(features)
    if "error" in details:
        raise BadRequest(details["error"])
    models, _ = ann.load_models()
    weights = models["perceptron"]
    z = details["perceptron_sum"]
    details["activations"] = ann.hidden_activations(features)
    details["perceptron"] = {"weights": [round(float(w), 2) for w in weights["w"]],
                             "bias": round(float(weights["b"]), 3),
                             "sum": z, "output": 1 if z >= 0 else 0}
    return jsonify(details)


@app.get("/api/ann/metrics")
def api_ann_metrics():
    """
    Function: api_ann_metrics
    Purpose : Test-set results of both models (computed once, then cached).
    Params  : none
    Returns : JSON {mlp_accuracy, noise_ceiling, perceptron_accuracy,
                    mlp_binary_accuracy (all in %), mlp_confusion,
                    perceptron_confusion, loss_curve, loss_epochs}
    """
    with LOCK:
        if CACHE["metrics"] is None:
            models, _ = ann.load_models()
            report = train.evaluate(models)
            history = models["mlp_loss_history"]
            CACHE["metrics"] = {
                "mlp_accuracy": round(100 * report["mlp_accuracy"], 2),
                "noise_ceiling": round(100 * report["noise_ceiling"], 2),
                "perceptron_accuracy": round(100 * report["perceptron_accuracy"], 2),
                "mlp_binary_accuracy": round(100 * report["comparison"]["mlp_binary_accuracy"], 2),
                "mlp_confusion": report["mlp_confusion"],
                "perceptron_confusion": report["perceptron_confusion"],
                "loss_curve": [round(loss, 4) for _, loss in history],
                "loss_epochs": [epoch for epoch, _ in history],
                "n_train": report["n_train"], "n_test": report["n_test"],
            }
        return jsonify(CACHE["metrics"])


@app.get("/api/history")
def api_history():
    """
    Function: api_history
    Purpose : The requests processed this session (oldest first), so the
              History page survives a page reload.
    Params  : none
    Returns : JSON list of {"request": UI form body, "response": final response, "time"}
    """
    with LOCK:
        return jsonify(HISTORY)


@app.post("/api/reset")
def api_reset():
    """
    Function: api_reset
    Purpose : Back to the initial bookings; request ids restart at REQ101 and
              the history is cleared, unless keep_counter is true (bookings only,
              used before each demo scenario, exactly like cli.py's demo mode).
    Params  : JSON body {"keep_counter": bool} (optional, default false)
    Returns : JSON {"ok": true}
    """
    keep_counter = body().get("keep_counter") is True
    with LOCK:
        main.reset_system(clear_counter=not keep_counter)
        BOOKED_BY.clear()
        if not keep_counter:
            HISTORY.clear()
    return jsonify({"ok": True})


@app.errorhandler(BadRequest)
def bad_request(exc):
    """
    Function: bad_request
    Purpose : Invalid input -> HTTP 400 with the reason.
    Params  : exc (BadRequest)
    Returns : (JSON, 400)
    """
    return jsonify({"error": str(exc)}), 400


@app.errorhandler(Exception)
def server_error(exc):
    """
    Function: server_error
    Purpose : Any other error -> JSON instead of an HTML page (HTTP errors such
              as 404 keep their own status code).
    Params  : exc (Exception)
    Returns : (JSON, status code)
    """
    if isinstance(exc, HTTPException):
        return jsonify({"error": exc.description}), exc.code
    return jsonify({"error": "internal error: %s" % exc}), 500


# ===========================================================================
# 5. Start
# ===========================================================================
def run(argv=None):
    """
    Function: run
    Purpose : Load the ANN models, start the server and open the browser.
    Params  : argv (list or None) - command-line arguments (--port, --no-browser)
    Returns : None
    """
    parser = argparse.ArgumentParser(description="Smart Campus AI web UI")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = parser.parse_args(argv)
    _, source = ann.load_models()          # first prediction is then instant
    url = "http://127.0.0.1:%d/" % args.port
    print("ANN models %s. Smart Campus AI running at %s (Ctrl+C to stop)" % (source, url))
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    run()
