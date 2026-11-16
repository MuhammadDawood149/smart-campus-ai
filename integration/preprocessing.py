"""
File    : integration/preprocessing.py
Module  : Request Preprocessing (integration layer)
Owner   : Joint (Students 1, 2 and 3)

Purpose : The first handling layer after input collection (handout Phase 1
          section 4 and Phase 3 section 8). preprocess(raw, state) turns the raw
          CLI / GUI fields into one standard request object:
            1. assign a request_id (REQ101, REQ102, ...)
            2. validate the base fields and the fields the request type needs
               (handout Phase 1 section 2.2)
            3. normalise names, categories, roles, request types, locations
            4. prepare module inputs: the ANN feature vector (Distance comes
               from the Search module)
          Rejection reasons are specific, e.g. "preferred_slot must be 1-4, got 7".

Rules   : integration may import from every module. Never prints, never raises.

Assumptions (team-defined)
          - Distance (ANN x6) = route cost from current_location to the first
            room of the request's category (csp_scheduler.CATEGORY_ROOMS), found
            by the Search module's default policy (A* on the weighted graph).
          - Eligibility (ANN x7) = the user's own eligibility_claim (1 / 0).
          - A name not in the KB is kept (capitalised) so Logic can reject it with
            a reason; Logic, not preprocessing, decides who is allowed.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.campus_data import (CATEGORIES, ROLES, TIME_SLOTS, SCALE_MIN, SCALE_MAX,
                                ROLE_ENCODING, CATEGORY_ENCODING)
from shared.templates import new_template, REQUEST_TEMPLATE
from student1_search.search_module import normalize_location, run_search
from student2_logic_csp.logic_kb import FACTS, ROLE_PREDICATE, parse_atom
from student2_logic_csp.csp_scheduler import CATEGORY_ROOMS

# ===========================================================================
# 1. Names and tables
# ===========================================================================
REQUEST_TYPES = ["Navigation_Only", "Eligibility_Check", "Booking_or_Scheduling",
                 "Urgent_Service_Request", "Full_Service_Request"]

# Fields each request type needs on top of name / role / request_type
# (handout Phase 1 section 2.2). group_id is added when the category is
# Viva_Scheduling ("group_id (if group-based)").
REQUIRED_FIELDS = {
    "Navigation_Only": ["current_location", "destination"],
    "Eligibility_Check": ["query"],
    "Booking_or_Scheduling": ["category", "preferred_slot"],
    "Urgent_Service_Request": ["category", "current_location", "severity",
                               "time_sensitivity", "crowd_level"],
    "Full_Service_Request": ["category", "current_location", "preferred_slot",
                             "severity", "time_sensitivity", "crowd_level"],
}
OPTIONAL_FIELDS = {
    "Navigation_Only": [],
    "Eligibility_Check": [],
    "Booking_or_Scheduling": ["current_location", "description_note"],
    "Urgent_Service_Request": ["preferred_slot", "eligibility_claim", "description_note"],
    "Full_Service_Request": ["eligibility_claim", "description_note"],
}
ANN_TYPES = ["Urgent_Service_Request", "Full_Service_Request"]
SCALE_FIELDS = ["severity", "time_sensitivity", "crowd_level"]
VIVA_CATEGORY = "Viva_Scheduling"

# CLI wording -> encoding names (handout CLI prompt says Viva / Access)
CATEGORY_ALIASES = {"viva": "Viva_Scheduling", "access": "Access_Request",
                    "emergency": "Emergency_Help", "lab_support": "AI_Lab_Support"}

NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")     # one word, starts with a letter
YES_WORDS = ["y", "yes", "true", "1"]
NO_WORDS = ["n", "no", "false", "0"]

DEFAULT_STATE = {"request_counter": 100}    # used when the caller passes no state


def text_key(text):
    """
    Function: text_key
    Purpose : Comparison key for free text: lower case, spaces and hyphens
              turned into underscores ("Booking or scheduling" -> "booking_or_scheduling").
    Params  : text (str)
    Returns : str
    """
    return "_".join(text.strip().lower().replace("-", " ").replace("_", " ").split())


def kb_people():
    """
    Function: kb_people
    Purpose : Every person the knowledge base knows (subject of a Student /
              Faculty / Staff fact), keyed by a lowercase key without spaces,
              dots or underscores, so "dr khan" and "Dr.Khan" both find DrKhan.
    Params  : none
    Returns : dict {lookup key: KB spelling}
    """
    role_predicates = list(ROLE_PREDICATE.values())
    people = {}
    for fact in FACTS:
        if fact[0] in role_predicates:
            people[name_key(fact[1])] = fact[1]
    return people


def name_key(text):
    """
    Function: name_key
    Purpose : Lookup key for a person name: lower case, without spaces, dots,
              hyphens or underscores.
    Params  : text (str)
    Returns : str
    """
    return "".join(ch for ch in text.lower() if ch not in " ._-")


KB_PEOPLE = kb_people()


# ===========================================================================
# 2. Field checks: each returns (normalised value, error or None).
#    cli.py uses the same checks to re-ask a question after bad input.
# ===========================================================================
def is_blank(value):
    """
    Function: is_blank
    Purpose : True when a field was not given (None or empty / spaces only text).
    Params  : value - any field value
    Returns : bool
    """
    return value is None or (isinstance(value, str) and not value.strip())


def check_name(value):
    """
    Function: check_name
    Purpose : Normalise a person name to its KB spelling (case-insensitive:
              ali -> Ali, drkhan -> DrKhan). An unknown name is kept but its
              first letter is capitalised, so Logic rejects it with a reason.
    Params  : value - raw name
    Returns : (name or None, error or None)
    """
    if is_blank(value) or not isinstance(value, str):
        return None, "name is required"
    text = value.strip()
    if name_key(text) in KB_PEOPLE:
        return KB_PEOPLE[name_key(text)], None
    if not NAME_PATTERN.match(text):
        return None, ("name must be one word of letters/digits starting with a letter, got %r"
                      % text)
    return text[0].upper() + text[1:], None


def check_role(value):
    """
    Function: check_role
    Purpose : Normalise the role to student / instructor / staff.
    Params  : value - raw role
    Returns : (role or None, error or None)
    """
    if is_blank(value) or not isinstance(value, str):
        return None, "role is required (student/instructor/staff)"
    role = value.strip().lower()
    if role not in ROLES:
        return None, "role must be one of %s, got %r" % ("/".join(ROLES), value.strip())
    return role, None


def check_request_type(value):
    """
    Function: check_request_type
    Purpose : Normalise the request type to its canonical name. Accepts any
              case, spaces instead of underscores, or the CLI menu number 1-5.
    Params  : value - raw request type (str or int)
    Returns : (request_type or None, error or None)
    """
    if is_blank(value):
        return None, "request_type is required"
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None, "request_type must be text, got %r" % (value,)
    text = value.strip()
    if text.isdigit() and 1 <= int(text) <= len(REQUEST_TYPES):
        return REQUEST_TYPES[int(text) - 1], None
    table = {text_key(t): t for t in REQUEST_TYPES}
    if text_key(text) in table:
        return table[text_key(text)], None
    return None, "request_type must be one of %s, got %r" % (", ".join(REQUEST_TYPES), text)


def check_category(value):
    """
    Function: check_category
    Purpose : Normalise the category to the encoding name (Viva -> Viva_Scheduling,
              Access -> Access_Request, Emergency -> Emergency_Help; any case).
    Params  : value - raw category
    Returns : (category or None, error or None)
    """
    if is_blank(value) or not isinstance(value, str):
        return None, "category is required"
    table = {text_key(c): c for c in CATEGORIES}
    table.update(CATEGORY_ALIASES)
    key = text_key(value)
    if key in table:
        return table[key], None
    return None, "category must be one of %s, got %r" % (", ".join(CATEGORIES), value.strip())


def check_location(value, field):
    """
    Function: check_location
    Purpose : Normalise a location to an exact campus node with Search's
              normalize_location ("ai lab" -> AI_Lab, "hostel" -> Hostel).
    Params  : value - raw location, field (str) - field name used in the message
    Returns : (node or None, error or None)
    """
    if is_blank(value):
        return None, "%s is required" % field
    if not isinstance(value, str):
        return None, "%s must be text, got %r" % (field, value)
    node, error = normalize_location(value)
    if error:
        return None, "%s: %s" % (field, error)
    return node, None


def read_int(value):
    """
    Function: read_int
    Purpose : Read a whole number from an int or digit text ("7", " 7 ").
              bool and float values are not accepted.
    Params  : value - raw value
    Returns : int or None
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.match(r"^-?\d+$", value.strip()):
        return int(value.strip())
    return None


def check_slot(value):
    """
    Function: check_slot
    Purpose : preferred_slot must be one of the time slots {1, 2, 3, 4}.
    Params  : value - raw slot
    Returns : (slot or None, error or None)
    """
    if is_blank(value):
        return None, "preferred_slot is required"
    slot = read_int(value)
    if slot not in TIME_SLOTS:
        return None, "preferred_slot must be %d-%d, got %s" % (
            min(TIME_SLOTS), max(TIME_SLOTS), shown(value))
    return slot, None


def check_scale(value, field):
    """
    Function: check_scale
    Purpose : severity / time_sensitivity / crowd_level must be integers 1-10.
    Params  : value - raw number, field (str) - field name used in the message
    Returns : (int or None, error or None)
    """
    if is_blank(value):
        return None, "%s is required" % field
    number = read_int(value)
    if number is None or not SCALE_MIN <= number <= SCALE_MAX:
        return None, "%s must be an integer %d-%d, got %s" % (field, SCALE_MIN, SCALE_MAX,
                                                              shown(value))
    return number, None


def check_yes_no(value, field):
    """
    Function: check_yes_no
    Purpose : Read a yes/no answer (True/False, y/n, yes/no, 1/0).
    Params  : value - raw answer, field (str) - field name used in the message
    Returns : (bool or None, error or None)
    """
    if isinstance(value, bool):
        return value, None
    if isinstance(value, int) and value in (0, 1):
        return bool(value), None
    if isinstance(value, str) and value.strip().lower() in YES_WORDS:
        return True, None
    if isinstance(value, str) and value.strip().lower() in NO_WORDS:
        return False, None
    return None, "%s must be yes or no, got %s" % (field, shown(value))


def check_group(value):
    """
    Function: check_group
    Purpose : group_id is required for Viva_Scheduling and is upper-cased (g3 -> G3).
              A well-formed but unknown group (G9) is left for Logic to reject.
    Params  : value - raw group id
    Returns : (group_id or None, error or None)
    """
    if is_blank(value) or not isinstance(value, str):
        return None, "group_id is required for %s (e.g. G4)" % VIVA_CATEGORY
    group = value.strip().upper()
    if not NAME_PATTERN.match(group):
        return None, "group_id must be one word like G4, got %r" % value.strip()
    return group, None


def check_query(value):
    """
    Function: check_query
    Purpose : The Eligibility_Check query must be a well-formed logic atom such
              as UsesLab(DrKhan, Lab1) (checked with the Logic module's parser).
    Params  : value - raw query text
    Returns : (query or None, error or None)
    """
    if is_blank(value) or not isinstance(value, str):
        return None, "query is required (e.g. UsesLab(DrKhan, Lab1))"
    atom, error = parse_atom(value)
    if error:
        return None, "query is invalid: " + error
    return "%s(%s)" % (atom[0], ", ".join(atom[1:])), None


def shown(value):
    """
    Function: shown
    Purpose : Show a bad value in a message: text without quotes, others with repr.
    Params  : value - any value
    Returns : str
    """
    return value.strip() if isinstance(value, str) else repr(value)


# ===========================================================================
# 3. Module inputs
# ===========================================================================
def route_distance(source, category):
    """
    Function: route_distance
    Purpose : ANN Distance feature: route cost from the user's location to the
              first room of the category, found by the Search module.
    Params  : source (str) - node, category (str) - canonical category
    Returns : (cost or None, error or None)
    """
    room = CATEGORY_ROOMS[category][0]
    result = run_search({"current_location": source, "destination": room})
    if not result["success"]:
        return None, "could not compute Distance to %s: %s" % (room, result["error"])
    return result["route"]["cost"], None


def ann_features(request):
    """
    Function: ann_features
    Purpose : Build the raw ANN feature vector in FEATURE_ORDER:
              [Role, RequestType, Severity, TimeSensitivity, CrowdLevel,
               Distance, Eligibility], e.g. [0, 0, 8, 9, 5, 6, 1].
    Params  : request (dict) - validated, normalised request
    Returns : (list of 7 numbers or None, error or None)
    """
    distance, error = route_distance(request["current_location"], request["category"])
    if error:
        return None, error
    return [ROLE_ENCODING[request["role"]], CATEGORY_ENCODING[request["category"]],
            request["severity"], request["time_sensitivity"], request["crowd_level"],
            distance, 1 if request["eligibility_claim"] else 0], None


# ===========================================================================
# 4. preprocess(): the entry point
# ===========================================================================
def next_request_id(state):
    """
    Function: next_request_id
    Purpose : Give the next request id: REQ101, REQ102, ...
    Params  : state (dict) - holds "request_counter" (the last number used)
    Returns : str
    """
    state["request_counter"] = state.get("request_counter", 100) + 1
    return "REQ%d" % state["request_counter"]


def check_field(field, value):
    """
    Function: check_field
    Purpose : Validate and normalise one conditional field by its name.
    Params  : field (str) - a REQUEST_TEMPLATE field name, value - raw value
    Returns : (normalised value or None, error or None)
    """
    if field == "category":
        return check_category(value)
    if field in ("current_location", "destination"):
        return check_location(value, field)
    if field == "preferred_slot":
        return check_slot(value)
    if field in SCALE_FIELDS:
        return check_scale(value, field)
    if field == "query":
        return check_query(value)
    if field == "eligibility_claim":
        return check_yes_no(value, field)
    if field == "group_id":
        return check_group(value)
    return (value.strip() if isinstance(value, str) else ""), None     # description_note


def preprocess(raw, state=None):
    """
    Function: preprocess
    Purpose : Validate and normalise a raw request and prepare module inputs.
              The request_id is assigned first, so a rejected request still has one.
              Only the fields the request type uses are copied; the others keep
              their REQUEST_TEMPLATE defaults.
    Params  : raw (dict) - raw fields from the CLI / GUI / a test
              state (dict, optional) - holds "request_counter"; defaults to DEFAULT_STATE
    Returns : (request, error). request = REQUEST_TEMPLATE filled in, plus
              "ann_features" (list, or None when the ANN is not needed).
              error = None, or the specific reason the request is rejected.
    """
    state = DEFAULT_STATE if state is None else state
    request = new_template(REQUEST_TEMPLATE)
    request["request_id"] = next_request_id(state)
    request["ann_features"] = None
    try:
        if not isinstance(raw, dict):
            return request, "request must be a dict of fields, got %s" % type(raw).__name__

        # --- base fields: name, role, request_type ---
        for field, check in (("name", check_name), ("role", check_role),
                             ("request_type", check_request_type)):
            value, error = check(raw.get(field))
            if error:
                return request, error
            request[field] = value
        request_type = request["request_type"]

        # --- conditional fields (handout 2.2) ---
        fields = REQUIRED_FIELDS[request_type] + OPTIONAL_FIELDS[request_type]
        for field in fields:
            value = raw.get(field)
            if field not in REQUIRED_FIELDS[request_type] and is_blank(value):
                continue                      # optional and not given: keep the default
            value, error = check_field(field, value)
            if error:
                return request, error
            request[field] = value
            if field == "category" and value == VIVA_CATEGORY:
                group, error = check_group(raw.get("group_id"))
                if error:
                    return request, error
                request["group_id"] = group

        # --- module inputs ---
        if request_type in ANN_TYPES:
            request["ann_features"], error = ann_features(request)
            if error:
                return request, error
        return request, None
    except Exception as exc:          # never let an error escape to the caller
        return request, "preprocessing failed: %s" % exc
