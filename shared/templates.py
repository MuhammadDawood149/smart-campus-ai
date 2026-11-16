"""
File    : shared/templates.py
Module  : Shared data (no AI logic)
Owner   : Joint (shared by all three students)

Purpose : Standard Python data structures from handout section 12.
          Every module builds its request/response dicts from these
          templates so all parts use identical field names.
"""

import copy

REQUEST_TEMPLATE = {
    "request_id": "", "name": "", "role": "", "request_type": "",
    "category": "", "current_location": "", "destination": "",
    "preferred_slot": None, "severity": 0, "time_sensitivity": 0,
    "crowd_level": 0, "group_id": "", "query": "",
    "eligibility_claim": False, "description_note": ""
}

ROUTER_OUTPUT_TEMPLATE = {
    "request_id": "", "selected_pipeline": [], "needs_ann": False,
    "needs_logic": False, "needs_csp": False, "needs_search": False
}

PRIORITY_OUTPUT_TEMPLATE = {"binary_priority": "", "final_priority": "", "confidence": 0.0}

LOGIC_OUTPUT_TEMPLATE = {"allowed": False, "entailed": False, "explanation": ""}

CSP_OUTPUT_TEMPLATE = {"decision": "", "assigned_room": "", "assigned_slot": None, "destination": "", "notes": ""}

SEARCH_OUTPUT_TEMPLATE = {"algorithm_used": "", "path": [], "cost": 0, "steps": 0}

FINAL_RESPONSE_TEMPLATE = {
    "request_id": "", "decision": "", "priority": {}, "eligibility": {},
    "assignment": {}, "route": {}, "message": ""
}


def new_template(t):
    """
    Function: new_template
    Purpose : Return an independent copy of a template so callers can fill it
              in without changing the shared original.
    Params  : t (dict) - one of the templates above
    Returns : dict - deep copy of t
    """
    return copy.deepcopy(t)
