"""
File    : integration/final_response.py
Module  : Final Response Generator (integration layer)
Owner   : Joint (Students 1, 2 and 3)

Purpose : Combines the outputs of the modules that actually ran into one
          user-facing response, in the handout formats:
            Navigation        6.2  decision "completed", route
            Eligibility       6.3  decision "answered", eligibility {entailed, explanation}
            Booking           6.4  decision "accepted", eligibility {allowed},
                                   assignment {room, slot}, route if Search ran
            Urgent / Full     6.5  decision "accepted", priority, eligibility,
                                   assignment, route
            Rejection         3.4  decision "rejected", rejected_at (the stage),
                                   reason, plus the outputs gathered before the stop
          Only the fields a request uses appear in the response ("Not every
          request will fill every field", handout 6.1).

Rules   : never prints, never raises.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.templates import new_template, FINAL_RESPONSE_TEMPLATE, PRIORITY_OUTPUT_TEMPLATE

# Stages a request can be rejected at (handout Phase 3 section 3.2) and the
# message sentence for each.
REJECTION_MESSAGES = {
    "preprocessing": "the request details are invalid.",
    "ann": "its priority could not be predicted.",
    "logic": "you are not eligible for this service.",
    "csp": "no feasible conflict-free room and slot exists.",
    "search": "no valid route could be found.",
    "system": "an internal error occurred.",
}


def build(request_id, decision, message, **parts):
    """
    Function: build
    Purpose : Fill FINAL_RESPONSE_TEMPLATE and drop the empty parts, keeping the
              key order of the template (extra keys such as rejected_at go last
              before message).
    Params  : request_id (str), decision (str), message (str),
              parts - priority / eligibility / assignment / route dicts and extras
    Returns : dict
    """
    response = new_template(FINAL_RESPONSE_TEMPLATE)
    response["request_id"] = request_id
    response["decision"] = decision
    for key, value in parts.items():
        response[key] = value
    response.pop("message")
    response = {k: v for k, v in response.items()
                if k in ("request_id", "decision") or v not in ({}, None, "")}
    response["message"] = message
    return response


def route_part(search_output):
    """
    Function: route_part
    Purpose : The route block of a response: algorithm, path, cost, steps.
    Params  : search_output (dict or None) - result of run_search()
    Returns : dict, {} when Search did not run
    """
    if not search_output or not search_output.get("success"):
        return {}
    r = search_output["route"]
    return {"algorithm": r["algorithm"], "path": list(r["path"]),
            "cost": r["cost"], "steps": r["steps"]}


def priority_part(priority_output):
    """
    Function: priority_part
    Purpose : The priority block: binary_priority, final_priority, confidence.
    Params  : priority_output (dict or None) - result of predict_priority()
    Returns : dict, {} when the ANN did not run
    """
    if not priority_output or priority_output.get("error"):
        return {}
    return {key: priority_output[key] for key in PRIORITY_OUTPUT_TEMPLATE}


def assignment_part(csp_output):
    """
    Function: assignment_part
    Purpose : The assignment block: room and slot from the CSP.
    Params  : csp_output (dict) - result of schedule()
    Returns : dict {"room", "slot"}
    """
    return {"room": csp_output["assigned_room"], "slot": csp_output["assigned_slot"]}


def navigation_response(request_id, search_output):
    """
    Function: navigation_response
    Purpose : Handout 6.2 - route only.
    Params  : request_id (str), search_output (dict) - successful run_search() result
    Returns : dict
    """
    return build(request_id, "completed", "Best route generated successfully.",
                 route=route_part(search_output))


def eligibility_response(request_id, logic_output):
    """
    Function: eligibility_response
    Purpose : Handout 6.3 - the query answer (entailed or not) and its explanation.
    Params  : request_id (str), logic_output (dict) - check_logic() result
    Returns : dict
    """
    return build(request_id, "answered", "Eligibility query answered successfully.",
                 eligibility={"entailed": logic_output["entailed"],
                              "explanation": logic_output["explanation"]})


def booking_response(request_id, csp_output, search_output=None):
    """
    Function: booking_response
    Purpose : Handout 6.4 - allowed, room and slot, plus the route when Search ran.
    Params  : request_id (str), csp_output (dict) - accepted schedule() result,
              search_output (dict or None) - run_search() result if Search ran
    Returns : dict
    """
    return build(request_id, "accepted", "Booking assigned successfully.",
                 eligibility={"allowed": True}, assignment=assignment_part(csp_output),
                 route=route_part(search_output))


def service_response(request_id, priority_output, csp_output, search_output=None):
    """
    Function: service_response
    Purpose : Handout 6.5 / 11.8 - Urgent and Full service: priority, allowed,
              room and slot, route.
    Params  : request_id (str), priority_output (dict) - predict_priority() result,
              csp_output (dict) - accepted schedule() result,
              search_output (dict or None) - run_search() result if Search ran
    Returns : dict
    """
    message = ("Your request has been accepted. You are assigned %s in slot %d."
               % (csp_output["assigned_room"], csp_output["assigned_slot"]))
    route = route_part(search_output)
    if route:
        message += " Please follow the recommended route."
    return build(request_id, "accepted", message, priority=priority_part(priority_output),
                 eligibility={"allowed": True}, assignment=assignment_part(csp_output),
                 route=route)


def rejection_response(request_id, stage, reason, priority_output=None, logic_output=None):
    """
    Function: rejection_response
    Purpose : Handout 3.4 - a request stopped at some stage. Shows the stage, the
              specific reason, and the outputs gathered before the stop (the ANN
              priority; the Logic result once Logic has run).
    Params  : request_id (str),
              stage (str) - "preprocessing" / "ann" / "logic" / "csp" / "search"
              (or "system" for an unexpected internal error),
              reason (str) - why it was rejected,
              priority_output (dict or None), logic_output (dict or None)
    Returns : dict
    """
    eligibility = {}
    if logic_output is not None:
        eligibility = {"allowed": logic_output["allowed"]}
        if not logic_output["allowed"]:
            eligibility["explanation"] = logic_output["explanation"]
    message = "Your request has been rejected because " + REJECTION_MESSAGES.get(
        stage, "it could not be completed.")
    return build(request_id, "rejected", message, priority=priority_part(priority_output),
                 eligibility=eligibility, rejected_at=stage, reason=reason)
