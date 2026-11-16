"""
File    : student2_logic_csp/csp_scheduler.py
Module  : CSP Scheduler (Constraint Satisfaction Problem)
Owner   : Student 2

Purpose : A small generic CSP solver (backtracking + MRV + degree tie-break + LCV
          + forward checking) and two problems built on it:
            1. the viva timetable (G1..G6, slots 1-4, from the CSP diagram)
            2. room/slot booking for service requests (team-defined, see CLAUDE.md)
          Entry point for the integration layer: schedule(request, priority).

Rules   : imports only from shared/, never prints, never reads input.

How a CSP is written here (kept deliberately simple)
          variables   = list of names                    ["G1", "G2", ...]
          domains     = dict  name -> list of values     {"G1": [1, 2, 3, 4], ...}
          constraints = list of (scope, test)            (("G1", "G2"), not_equal)
                        scope is a tuple of variable names, test(*values) -> True/False
          solution    = dict  name -> value, or None when no solution exists
          stats       = {"assignments": values tried, "backtracks": assignments undone}

Assumption : the booking CSP, the deadlines (Urgent 2, High 3, others 4) and the
          initial bookings are team-defined extensions (see CLAUDE.md).
"""

import sys
import os

# Make "shared" importable when this file is run directly from its folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.campus_data import CATEGORIES, TIME_SLOTS, PRIORITY_LEVELS
from shared.templates import new_template, CSP_OUTPUT_TEMPLATE

# ===========================================================================
# 1. Generic CSP solver
# ===========================================================================


def conflicts(var, value, assignment, domains, constraints):
    """
    Function: conflicts
    Purpose : Find which values of the other variables stop being possible if
              var = value. Only constraints that have exactly one unassigned
              variable left (besides var) can rule values out.
              Used for forward checking and to count the cost of a value (LCV).
    Params  : var (str), value, assignment (dict, var not in it),
              domains (dict var -> list), constraints (list of (scope, test))
    Returns : dict other_var -> set of values that would be removed
    """
    trial = dict(assignment)
    trial[var] = value
    lost = {}
    for scope, test in constraints:
        if var not in scope:
            continue
        open_vars = [v for v in scope if v not in trial]
        if len(open_vars) != 1:
            continue
        other = open_vars[0]
        for w in domains[other]:
            trial[other] = w
            if not test(*[trial[v] for v in scope]):
                lost.setdefault(other, set()).add(w)
        del trial[other]
    return lost


def forward_check(var, value, assignment, domains, constraints):
    """
    Function: forward_check
    Purpose : Remove from the unassigned variables every value that clashes
              with var = value. If some domain becomes empty this branch is dead.
    Params  : same as conflicts
    Returns : new domains dict (the input is not changed), or None if a domain
              became empty
    """
    new_domains = dict(domains)
    for other, removed in conflicts(var, value, assignment, domains, constraints).items():
        new_domains[other] = [w for w in domains[other] if w not in removed]
        if not new_domains[other]:
            return None
    return new_domains


def degree(var, assignment, constraints):
    """
    Function: degree
    Purpose : Degree heuristic: how many constraints link var to a variable
              that is still unassigned.
    Params  : var (str), assignment (dict), constraints (list of (scope, test))
    Returns : int
    """
    count = 0
    for scope, test in constraints:
        if var in scope and any(v != var and v not in assignment for v in scope):
            count += 1
    return count


def pick_variable(variables, assignment, domains, constraints, var_order):
    """
    Function: pick_variable
    Purpose : Choose the next variable. A fixed var_order wins if given; otherwise
              MRV (smallest domain first) and, on a tie, the highest degree.
              Remaining ties keep the order of the variables list.
    Params  : variables (list), assignment (dict), domains (dict),
              constraints (list), var_order (list or None)
    Returns : str - the variable to assign next
    """
    open_vars = [v for v in variables if v not in assignment]
    for v in (var_order or []):
        if v in open_vars:
            return v
    best, best_key = None, None
    for v in open_vars:
        key = (len(domains[v]), -degree(v, assignment, constraints))
        if best is None or key < best_key:
            best, best_key = v, key
    return best


def order_values(var, assignment, domains, constraints, value_first):
    """
    Function: order_values
    Purpose : Value order for var: the values in value_first (if still possible)
              come first in the given order, the rest follow in LCV order
              (least constraining value = removes the fewest values from the
              neighbours; ties keep the domain order).
    Params  : var (str), assignment (dict), domains (dict), constraints (list),
              value_first (dict var -> list of values)
    Returns : list of values
    """
    first = [v for v in value_first.get(var, []) if v in domains[var]]
    scored = []
    for index, value in enumerate(domains[var]):
        if value in first:
            continue
        removed = conflicts(var, value, assignment, domains, constraints)
        cost = sum(len(values) for values in removed.values())
        scored.append((cost, index, value))
    scored.sort()
    return first + [value for cost, index, value in scored]


def solve_csp(variables, domains, constraints, value_first=None, var_order=None):
    """
    Function: solve_csp
    Purpose : Find one solution by backtracking search with MRV (+ degree
              tie-break), LCV value ordering and forward checking. One-variable
              constraints are applied to the domains before the search starts.
    Params  : variables (list of str), domains (dict var -> list of values),
              constraints (list of (scope tuple, test function)),
              value_first (dict var -> values to try first, optional),
              var_order (fixed variable order replacing MRV, optional)
    Returns : (solution, stats) - solution is a dict var -> value or None;
              stats = {"assignments": int, "backtracks": int}
    """
    stats = {"assignments": 0, "backtracks": 0}
    value_first = value_first or {}
    start = {v: list(domains[v]) for v in variables}
    for scope, test in constraints:
        if len(scope) == 1:
            start[scope[0]] = [x for x in start[scope[0]] if test(x)]
    if any(not d for d in start.values()):
        return None, stats
    assignment = {}

    def search(current):
        """
        Function: search
        Purpose : Recursive backtracking step: pick a variable, try its values
                  in order, forward check, recurse; undo on failure.
        Params  : current (dict) - the domains still possible at this point
        Returns : solution dict, or None if this branch has no solution
        """
        if len(assignment) == len(variables):
            return dict(assignment)
        var = pick_variable(variables, assignment, current, constraints, var_order)
        for value in order_values(var, assignment, current, constraints, value_first):
            stats["assignments"] += 1
            reduced = forward_check(var, value, assignment, current, constraints)
            if reduced is not None:
                assignment[var] = value
                result = search(reduced)
                if result is not None:
                    return result
                del assignment[var]
            stats["backtracks"] += 1
        return None

    return search(start), stats


# ===========================================================================
# 2. Viva timetable CSP (from the CSP diagram)
# ===========================================================================
VIVA_GROUPS = ["G1", "G2", "G3", "G4", "G5", "G6"]
# G1-G3 examiner clash, G2-G5 supervisor clash; the others are from the diagram.
VIVA_NOT_EQUAL = [("G1", "G2"), ("G1", "G4"), ("G1", "G3"), ("G2", "G4"),
                  ("G2", "G5"), ("G3", "G5"), ("G3", "G6"), ("G5", "G6")]
VIVA_PRECEDENCE = [("G4", "G3")]          # G4 must be strictly earlier than G3


def not_equal(a, b):
    """
    Function: not_equal
    Purpose : Constraint test: two groups must not share a slot.
    Params  : a, b - the two slots
    Returns : bool
    """
    return a != b


def before(a, b):
    """
    Function: before
    Purpose : Constraint test: the first slot must be strictly earlier.
    Params  : a, b - the two slots
    Returns : bool
    """
    return a < b


def viva_problem(slots=TIME_SLOTS, allowed=None):
    """
    Function: viva_problem
    Purpose : Build the viva timetable CSP.
    Params  : slots (list of int) - the slot domain of every group
              allowed (dict group -> list of slots, optional) - limits a group's domain
    Returns : (variables, domains, constraints) ready for solve_csp
    """
    domains = {g: list(slots) for g in VIVA_GROUPS}
    for group, ok in (allowed or {}).items():
        domains[group] = [s for s in domains[group] if s in ok]
    constraints = [(pair, not_equal) for pair in VIVA_NOT_EQUAL]
    constraints += [(pair, before) for pair in VIVA_PRECEDENCE]
    return list(VIVA_GROUPS), domains, constraints


def slot_order(preferred, slots=TIME_SLOTS):
    """
    Function: slot_order
    Purpose : Value order for slots: the preferred slot, then later slots in
              ascending order, then earlier slots in descending order.
              No preference = plain ascending order.
    Params  : preferred (int or None), slots (list of int)
    Returns : list of int
    """
    if preferred is None:
        return sorted(slots)
    return ([s for s in slots if s == preferred]
            + sorted(s for s in slots if s > preferred)
            + sorted((s for s in slots if s < preferred), reverse=True))


def run_viva(preferred=None, allowed=None):
    """
    Function: run_viva
    Purpose : Solve the viva timetable and also return the search statistics.
              A group with a preferred slot is assigned first, so its preference is
              tried before other groups can take that slot (otherwise MRV might
              give the slot away). Everything else is still MRV / LCV.
    Params  : preferred (dict group -> slot, optional) - that slot is tried first
              for that group (a value order, not a constraint)
              allowed (dict group -> list of slots, optional) - limits a domain
    Returns : (timetable, stats) - timetable is {group: slot} or None
    """
    variables, domains, constraints = viva_problem(allowed=allowed)
    preferred = preferred or {}
    value_first = {g: slot_order(s) for g, s in preferred.items()}
    return solve_csp(variables, domains, constraints, value_first, list(preferred))


def solve_viva(preferred=None):
    """
    Function: solve_viva
    Purpose : Return one valid viva timetable.
    Params  : preferred (dict group -> slot, optional) e.g. {"G4": 2}
    Returns : dict {group: slot} for G1..G6, or None if no timetable exists
    """
    return run_viva(preferred)[0]


# ===========================================================================
# 3. Room/slot booking CSP for service requests
# ===========================================================================
CATEGORY_ROOMS = {
    "AI_Lab_Support": ["AI_Lab"],
    "Viva_Scheduling": ["Exam_Hall", "Seminar_Room"],
    "Access_Request": ["Admin_Block"],
    "Maintenance": ["Student_Services"],
    "Emergency_Help": ["Medical_Center"],
}
ALL_ROOMS = [room for rooms in CATEGORY_ROOMS.values() for room in rooms]
VIVA_CATEGORY = "Viva_Scheduling"

# Latest allowed slot per ANN priority; no priority (None) = the last slot.
PRIORITY_DEADLINE = {"Urgent": 2, "High": 3, "Normal": 4, "Low": 4}
DEFAULT_DEADLINE = max(TIME_SLOTS)

INITIAL_BOOKINGS = [("AI_Lab", 2), ("Exam_Hall", 1), ("Admin_Block", 1)]


def new_state():
    """
    Function: new_state
    Purpose : Build a fresh booking state with the initial bookings.
    Params  : none
    Returns : dict {"bookings": set of (room, slot), "viva": {group: (room, slot)}}
    """
    return {"bookings": set(INITIAL_BOOKINGS), "viva": {}}


STATE = new_state()      # the bookings every schedule() call shares


def reset(state=None):
    """
    Function: reset
    Purpose : Put the bookings back to the initial ones (in place).
    Params  : state (dict, optional) - defaults to the shared STATE
    Returns : None
    """
    state = STATE if state is None else state
    state.clear()
    state.update(new_state())


def get_bookings(state=None):
    """
    Function: get_bookings
    Purpose : List the current bookings.
    Params  : state (dict, optional) - defaults to the shared STATE
    Returns : list of (room, slot), sorted by slot then room
    """
    state = STATE if state is None else state
    return [(room, slot) for slot, room in sorted((s, r) for r, s in state["bookings"])]


def booking_problem(category, deadline, bookings):
    """
    Function: booking_problem
    Purpose : Build the booking CSP: variables slot and room, with the three
              constraints (room serves the category, (room, slot) not booked,
              slot <= deadline).
    Params  : category (str), deadline (int), bookings (set of (room, slot))
    Returns : (variables, domains, constraints) ready for solve_csp
    """
    def serves_category(room):
        """
        Function: serves_category
        Purpose : Constraint test: the room is one of the category's rooms.
        Params  : room (str)
        Returns : bool
        """
        return room in CATEGORY_ROOMS[category]

    def not_booked(room, slot):
        """
        Function: not_booked
        Purpose : Constraint test: this (room, slot) is not already taken.
        Params  : room (str), slot (int)
        Returns : bool
        """
        return (room, slot) not in bookings

    def meets_deadline(slot):
        """
        Function: meets_deadline
        Purpose : Constraint test: the slot is not later than the deadline.
        Params  : slot (int)
        Returns : bool
        """
        return slot <= deadline

    variables = ["slot", "room"]
    domains = {"slot": list(TIME_SLOTS), "room": list(ALL_ROOMS)}
    constraints = [(("room",), serves_category), (("slot",), meets_deadline),
                   (("room", "slot"), not_booked)]
    return variables, domains, constraints


# ===========================================================================
# 4. schedule(): the entry point used by the integration layer
# ===========================================================================
def make_result(decision, room="", slot=None, notes="", stats=None, timetable=None):
    """
    Function: make_result
    Purpose : Build the output dict: the CSP_OUTPUT_TEMPLATE fields plus stats
              and timetable.
    Params  : decision (str) "accepted" / "rejected", room (str), slot (int or None),
              notes (str), stats (dict or None), timetable (dict or None)
    Returns : dict with decision, assigned_room, assigned_slot, destination (= room),
              notes, stats {"assignments", "backtracks"}, timetable {group: slot}
    """
    result = new_template(CSP_OUTPUT_TEMPLATE)
    result["decision"] = decision
    result["assigned_room"] = room
    result["assigned_slot"] = slot
    result["destination"] = room
    result["notes"] = notes
    result["stats"] = stats if stats is not None else {"assignments": 0, "backtracks": 0}
    result["timetable"] = timetable if timetable is not None else {}
    return result


def reject(notes, stats=None):
    """
    Function: reject
    Purpose : Build a rejected result.
    Params  : notes (str) - the reason, stats (dict or None)
    Returns : dict (see make_result)
    """
    return make_result("rejected", notes=notes, stats=stats)


def list_text(numbers):
    """
    Function: list_text
    Purpose : Write numbers as "1, 2, 3".
    Params  : numbers (iterable of int)
    Returns : str
    """
    return ", ".join(str(n) for n in sorted(numbers))


def preference_note(preferred, slot):
    """
    Function: preference_note
    Purpose : Say what happened to the preferred slot.
    Params  : preferred (int or None), slot (int) - the slot that was assigned
    Returns : str, "" when there was no preferred slot
    """
    if preferred is None:
        return ""
    if preferred == slot:
        return "Preferred slot %d was available and conflict-free." % preferred
    return ("Preferred slot %d was unavailable. Slot %d is the next feasible "
            "conflict-free assignment." % (preferred, slot))


def no_slot_reason(category, deadline, label, bookings):
    """
    Function: no_slot_reason
    Purpose : Explain why no slot at or before the deadline is free.
    Params  : category (str), deadline (int), label (str or None) - priority name,
              bookings (set of (room, slot))
    Returns : str
    """
    rooms = CATEGORY_ROOMS[category]
    why = "%s priority" % label if label else "no priority given"
    text = ("No conflict-free slot for %s at or before slot %d (%s). "
            % (category, deadline, why))
    for room in rooms:
        taken = [s for s in TIME_SLOTS if s <= deadline and (room, s) in bookings]
        text += "%s is already booked at slot(s) %s. " % (room, list_text(taken))
    later = [s for s in TIME_SLOTS if s > deadline
             and any((r, s) not in bookings for r in rooms)]
    if later:
        text += "Free slot(s) %s come after the deadline." % list_text(later)
    return text.strip()


def schedule_room(category, preferred, deadline, label, state):
    """
    Function: schedule_room
    Purpose : Book a room and slot for a non-viva category with the booking CSP.
              Commits the booking only when a solution is found.
    Params  : category (str), preferred (int or None), deadline (int),
              label (str or None) - priority name, state (dict)
    Returns : dict (see make_result)
    """
    variables, domains, constraints = booking_problem(category, deadline, state["bookings"])
    solution, stats = solve_csp(variables, domains, constraints,
                                value_first={"slot": slot_order(preferred)},
                                var_order=["slot", "room"])
    if solution is None:
        return reject(no_slot_reason(category, deadline, label, state["bookings"]), stats)
    room, slot = solution["room"], solution["slot"]
    state["bookings"].add((room, slot))
    notes = preference_note(preferred, slot)
    if not notes:
        notes = ("No preferred slot given. Slot %d is the earliest feasible "
                 "conflict-free assignment." % slot)
    return make_result("accepted", room, slot, notes, stats)


def schedule_viva(request, preferred, deadline, label, state):
    """
    Function: schedule_viva
    Purpose : Viva_Scheduling: solve the G1..G6 timetable, then give the request's
              group its slot and the first free room (Exam_Hall, then Seminar_Room).
              The group's domain is limited to slots that meet the deadline and have
              a free room; groups that already booked keep their slot. Booking the
              same group again replaces its earlier booking. Commits only if accepted.
    Params  : request (dict) - needs group_id, preferred (int or None),
              deadline (int), label (str or None), state (dict)
    Returns : dict (see make_result)
    """
    group_text = request.get("group_id")
    group = group_text.strip().upper() if isinstance(group_text, str) else ""
    if group not in VIVA_GROUPS:
        return reject("group_id '%s' is invalid: %s needs one of %s."
                      % (group_text, VIVA_CATEGORY, ", ".join(VIVA_GROUPS)))
    bookings = set(state["bookings"])
    earlier = state["viva"].get(group)                # (room, slot) or None
    bookings.discard(earlier)                         # a repeat request replaces the old one
    rooms = CATEGORY_ROOMS[VIVA_CATEGORY]
    usable = [s for s in TIME_SLOTS if s <= deadline
              and any((r, s) not in bookings for r in rooms)]
    if not usable:
        return reject(no_slot_reason(VIVA_CATEGORY, deadline, label, bookings))
    allowed = {g: [slot] for g, (room, slot) in state["viva"].items() if g != group}
    allowed[group] = usable
    timetable, stats = run_viva({group: preferred} if preferred else None, allowed)
    if timetable is None:
        fixed = ", ".join("%s=%d" % (g, slots[0]) for g, slots in sorted(allowed.items())
                          if g != group)
        return reject("No valid viva timetable exists for %s at or before slot %d: the slots "
                      "already booked by other groups (%s) leave no consistent timetable."
                      % (group, deadline, fixed or "none"), stats)
    slot = timetable[group]
    room = [r for r in rooms if (r, slot) not in bookings][0]
    bookings.add((room, slot))
    state["bookings"] = bookings
    state["viva"][group] = (room, slot)
    shown = ", ".join("%s=%d" % (g, timetable[g]) for g in VIVA_GROUPS)
    if earlier is None:
        moved = ""
    elif earlier[1] == slot:
        moved = "%s already had slot %d; its earlier booking was replaced." % (group, slot)
    else:
        moved = "%s was rescheduled from slot %d to slot %d." % (group, earlier[1], slot)
    notes = " ".join(part for part in [
        preference_note(preferred, slot), moved,
        "Viva timetable solved for G1-G6 (no clashes, G4 before G3): %s." % shown,
        "%s gets slot %d in %s." % (group, slot, room)] if part)
    return make_result("accepted", room, slot, notes, stats, timetable)


def read_preferred_slot(value):
    """
    Function: read_preferred_slot
    Purpose : Check the preferred slot: None, or a whole number (an int or digit
              text) that is one of the time slots.
    Params  : value - request["preferred_slot"]
    Returns : (slot or None, error text or None)
    """
    if value is None or value == "":
        return None, None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, int) and not isinstance(value, bool) and value in TIME_SLOTS:
        return value, None
    return None, ("preferred_slot %r is out of range: expected one of %s."
                  % (value, list_text(TIME_SLOTS)))


def schedule(request, priority=None, state=None):
    """
    Function: schedule
    Purpose : CSP entry point. Validates the request, then books a conflict-free
              room and slot (or solves the viva timetable for Viva_Scheduling).
              Never prints and never raises; problems come back as a rejection.
    Params  : request (dict) - standard request dict (category, preferred_slot,
              group_id for Viva_Scheduling)
              priority (str or None) - the ANN final_priority: Low / Normal / High / Urgent
              state (dict, optional) - bookings to use, defaults to the shared STATE
    Returns : dict with decision ("accepted" / "rejected"), assigned_room, assigned_slot,
              destination (= room), notes (CSP_OUTPUT_TEMPLATE fields) plus stats and timetable
    """
    state = STATE if state is None else state
    try:
        if not isinstance(request, dict):
            return reject("Request must be a dict.")
        category_text = request.get("category")
        category = {c.lower(): c for c in CATEGORIES}.get(
            category_text.strip().lower() if isinstance(category_text, str) else "")
        if category is None:
            return reject("Category '%s' is invalid: expected one of %s."
                          % (category_text, ", ".join(CATEGORIES)))
        label = None
        if priority is not None:
            label = {p.lower(): p for p in PRIORITY_LEVELS}.get(
                priority.strip().lower() if isinstance(priority, str) else "")
            if label is None:
                return reject("Priority '%s' is invalid: expected one of %s."
                              % (priority, ", ".join(PRIORITY_LEVELS)))
        deadline = PRIORITY_DEADLINE.get(label, DEFAULT_DEADLINE)
        preferred, error = read_preferred_slot(request.get("preferred_slot"))
        if error:
            return reject(error)
        if category == VIVA_CATEGORY:
            return schedule_viva(request, preferred, deadline, label, state)
        return schedule_room(category, preferred, deadline, label, state)
    except Exception as exc:          # never let an error escape to the caller
        return reject("Scheduling failed: %s" % exc)
