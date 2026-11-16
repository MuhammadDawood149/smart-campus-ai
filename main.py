"""
File    : main.py
Module  : System entry point (integration layer)
Owner   : Joint (Students 1, 2 and 3)

Purpose : process_request(raw_request) runs one request through the whole system
          (handout Phase 3 sections 1-5):
              Preprocessing -> Router -> selected modules -> Final Response
          The modules run in the router's order; the first stage that fails
          stops the request and gives a rejection that names that stage.
          One shared SESSION state (request counter + CSP bookings) is kept for
          the whole run, so a second request sees the first one's booking.
          reset_system() clears it.

Rules   : never prints and never reads input (cli.py / gui.py do that). Each
          final response can be appended as one JSON line to logs/responses.jsonl.
"""

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from integration.preprocessing import preprocess
from integration.router import route
from integration import final_response as fr
from student1_search.search_module import run_search
from student2_logic_csp.logic_kb import check_logic
from student2_logic_csp import csp_scheduler
from student3_ann.ann_module import predict_priority

FIRST_REQUEST_NUMBER = 100                 # the first id given is REQ101
LOG_FILE = os.path.join(ROOT, "logs", "responses.jsonl")
LOG_ENABLED = True                         # tests switch this off

# The one shared state for the whole session.
SESSION = {"request_counter": FIRST_REQUEST_NUMBER, "csp": csp_scheduler.new_state()}


def reset_system(clear_counter=True):
    """
    Function: reset_system
    Purpose : Put the system back to its starting state: the CSP bookings go
              back to the initial ones and (by default) request ids restart at REQ101.
    Params  : clear_counter (bool) - False keeps the request counter running
              (used by the demo, which resets bookings before each scenario)
    Returns : None
    """
    if clear_counter:
        SESSION["request_counter"] = FIRST_REQUEST_NUMBER
    csp_scheduler.reset(SESSION["csp"])


def get_bookings():
    """
    Function: get_bookings
    Purpose : The current CSP bookings, for "show current bookings".
    Params  : none
    Returns : dict {"bookings": list of (room, slot) sorted by slot,
                    "viva": {group: (room, slot)}}
    """
    return {"bookings": csp_scheduler.get_bookings(SESSION["csp"]),
            "viva": dict(sorted(SESSION["csp"]["viva"].items()))}


def log_response(response):
    """
    Function: log_response
    Purpose : Append one final response as a JSON line to logs/responses.jsonl.
              A logging problem never stops the request.
    Params  : response (dict)
    Returns : None
    """
    if not LOG_ENABLED:
        return
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(response) + "\n")
    except OSError:
        pass


def logic_reason(logic):
    """
    Function: logic_reason
    Purpose : Short rejection reason from a Logic result: which goal could not be
              proven and which premises are missing (the full explanation goes in
              the response's eligibility block).
    Params  : logic (dict) - check_logic() result with allowed False
    Returns : str
    """
    if logic.get("error") or not logic.get("missing"):
        return logic["explanation"]
    if logic.get("rejected_at") == "authorization":
        return "Role authorization failed: %s cannot be proven." % logic["missing"][0]
    return "%s cannot be proven; missing premise(s): %s." % (
        logic["query"], ", ".join(logic["missing"]))


def run_pipeline(request, router_output):
    """
    Function: run_pipeline
    Purpose : Run the selected modules in order and build the final response.
              ANN -> Logic_KB -> (Allowed?) -> CSP -> Search. The CSP booking is
              undone if a later stage (Search) fails, so a rejected request never
              keeps a booking.
    Params  : request (dict) - preprocessed request, router_output (dict)
    Returns : dict - final response
    """
    rid = request["request_id"]
    pipeline = router_output["selected_pipeline"]
    request_type = request["request_type"]
    priority = logic = csp = search = None

    if "ANN" in pipeline:
        priority = predict_priority(request["ann_features"])
        if priority.get("error"):
            return fr.rejection_response(rid, "ann", priority["error"])

    if "Logic_KB" in pipeline:
        logic = check_logic(request)
        if request_type == "Eligibility_Check":
            if logic.get("error"):
                return fr.rejection_response(rid, "logic", logic["explanation"])
            return fr.eligibility_response(rid, logic)
        if not logic["allowed"]:
            return fr.rejection_response(rid, "logic", logic_reason(logic), priority, logic)

    saved_bookings = copy.deepcopy(SESSION["csp"])
    if "CSP" in pipeline:
        csp = csp_scheduler.schedule(request, priority["final_priority"] if priority else None,
                                     SESSION["csp"])
        if csp["decision"] != "accepted":
            return fr.rejection_response(rid, "csp", csp["notes"], priority, logic)

    if "Search" in pipeline:
        search = run_search(request, csp)
        if not search["success"]:
            SESSION["csp"].clear()
            SESSION["csp"].update(saved_bookings)          # undo the booking
            return fr.rejection_response(rid, "search", search["error"], priority, logic)

    if request_type == "Navigation_Only":
        return fr.navigation_response(rid, search)
    if request_type == "Booking_or_Scheduling":
        return fr.booking_response(rid, csp, search)
    return fr.service_response(rid, priority, csp, search)


def process_request(raw_request):
    """
    Function: process_request
    Purpose : Handle one request end to end: preprocess, route, run the
              selected modules, build the final response. Never raises.
    Params  : raw_request (dict) - raw fields, e.g. {"name": "Ali", "role": "student",
              "request_type": "Navigation_Only", "current_location": "Hostel",
              "destination": "AI_Lab"}
    Returns : dict - final response in the handout 6.x / 3.4 format
    """
    request, error = preprocess(raw_request, SESSION)
    rid = request["request_id"]
    if error:
        response = fr.rejection_response(rid, "preprocessing", error)
    else:
        router_output = route(request)
        if not router_output["selected_pipeline"]:
            response = fr.rejection_response(rid, "preprocessing", "unsupported request_type %r"
                                             % request["request_type"])
        else:
            try:
                response = run_pipeline(request, router_output)
            except Exception as exc:       # never let an error escape to the caller
                response = fr.rejection_response(rid, "system", "internal error: %s" % exc)
    log_response(response)
    return response
