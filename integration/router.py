"""
File    : integration/router.py
Module  : Request Router (integration layer)
Owner   : Joint (Students 1, 2 and 3)

Purpose : Reads request_type from the preprocessed request and decides which
          modules run and in what order (handout Phase 1 section 7 and Phase 3
          section 7.1):
            Navigation_Only         -> [Search]
            Eligibility_Check       -> [Logic_KB]
            Booking_or_Scheduling   -> [Logic_KB, CSP, optional Search]
            Urgent_Service_Request  -> [ANN, Logic_KB, CSP, optional Search]
            Full_Service_Request    -> [ANN, Logic_KB, CSP, Search]
          "Optional Search" runs only when the user gave a current_location
          (route guidance needed). The router does not solve anything itself.

Rules   : never prints, never raises.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.templates import new_template, ROUTER_OUTPUT_TEMPLATE

# request_type -> (fixed pipeline, does it end with an optional Search?)
PIPELINES = {
    "Navigation_Only": (["Search"], False),
    "Eligibility_Check": (["Logic_KB"], False),
    "Booking_or_Scheduling": (["Logic_KB", "CSP"], True),
    "Urgent_Service_Request": (["ANN", "Logic_KB", "CSP"], True),
    "Full_Service_Request": (["ANN", "Logic_KB", "CSP", "Search"], False),
}


def route(request):
    """
    Function: route
    Purpose : Choose the module pipeline for a preprocessed request.
    Params  : request (dict) - output of preprocess() (needs request_id,
              request_type and current_location)
    Returns : dict ROUTER_OUTPUT_TEMPLATE: request_id, selected_pipeline (list of
              "ANN" / "Logic_KB" / "CSP" / "Search" in run order), needs_ann,
              needs_logic, needs_csp, needs_search. An unknown request_type gives
              an empty pipeline (ELSE: reject request).
    """
    result = new_template(ROUTER_OUTPUT_TEMPLATE)
    if not isinstance(request, dict):
        return result
    result["request_id"] = request.get("request_id", "")
    pipeline, optional_search = PIPELINES.get(request.get("request_type"), ([], False))
    pipeline = list(pipeline)
    if optional_search and request.get("current_location"):
        pipeline.append("Search")
    result["selected_pipeline"] = pipeline
    result["needs_ann"] = "ANN" in pipeline
    result["needs_logic"] = "Logic_KB" in pipeline
    result["needs_csp"] = "CSP" in pipeline
    result["needs_search"] = "Search" in pipeline
    return result
