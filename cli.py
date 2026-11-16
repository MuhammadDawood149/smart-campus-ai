"""
File    : cli.py
Module  : Structured CLI request form (main user interface)
Owner   : Joint (Students 1, 2 and 3)

Purpose : The structured CLI form from handout Phase 1 section 1.2. Asks for
          Name, Role and Request Type (menu 1-5), then only the fields that
          request type needs (handout section 2.2), re-asking after invalid
          input. Sends the request to main.process_request() and pretty-prints
          the final response (a readable summary plus the JSON).

          Main menu: 1 new request, 2 run demo scenarios, 3 show current
          bookings, 4 reset system, 5 exit.
          "python cli.py --demo" runs the demo scenarios and exits.

Rules   : the only place (with gui.py later) that calls print() / input().
          Field checks are the same ones preprocessing uses, so what the form
          accepts is exactly what the system accepts.
"""

import json
import sys
import textwrap

import main
from integration import preprocessing as pre
from integration.demo_scenarios import DEMO_SCENARIOS

WIDTH = 78
CATEGORY_PROMPT = "Enter Category (AI_Lab_Support / Viva / Access / Maintenance / Emergency): "


class InputClosed(Exception):
    """Raised when standard input ends (Ctrl+Z / Ctrl+D or a finished pipe)."""


# ===========================================================================
# 1. Asking questions
# ===========================================================================
def read_line(prompt):
    """
    Function: read_line
    Purpose : Read one line from the user.
    Params  : prompt (str)
    Returns : str (without surrounding spaces); raises InputClosed at end of input
    """
    try:
        return input(prompt).strip()
    except EOFError:
        raise InputClosed()


def ask(prompt, check, optional=False):
    """
    Function: ask
    Purpose : Ask until the answer passes the check; print the reason otherwise.
    Params  : prompt (str), check (function text -> (value, error)),
              optional (bool) - an empty answer is allowed and gives None
    Returns : the checked, normalised value (or None for a skipped optional field)
    """
    while True:
        text = read_line(prompt)
        if optional and not text:
            return None
        value, error = check(text)
        if error is None:
            return value
        sentence = error if error.endswith((".", "?")) else error + "."
        print("  Invalid input: %s Please try again." % sentence)


def ask_request_type():
    """
    Function: ask_request_type
    Purpose : Show the request type menu (1-5) and read the choice.
    Params  : none
    Returns : str - canonical request type
    """
    print("Enter Request Type:")
    for number, name in enumerate(pre.REQUEST_TYPES, start=1):
        print("  %d. %s" % (number, name))
    return ask("Enter choice: ", pre.check_request_type)


def ask_category(raw):
    """
    Function: ask_category
    Purpose : Ask the category, and the group id when it is Viva_Scheduling.
    Params  : raw (dict) - the request being filled in (changed in place)
    Returns : None
    """
    raw["category"] = ask(CATEGORY_PROMPT, pre.check_category)
    if raw["category"] == pre.VIVA_CATEGORY:
        raw["group_id"] = ask("Enter Group ID (e.g. G4): ", pre.check_group)


def ask_location(field, label, optional=False):
    """
    Function: ask_location
    Purpose : Ask for a campus location.
    Params  : field (str) - request field name, label (str) - prompt text,
              optional (bool)
    Returns : str node name, or None when an optional answer was skipped
    """
    return ask(label, lambda text: pre.check_location(text, field), optional)


def ask_scale(field, label):
    """
    Function: ask_scale
    Purpose : Ask for a 1-10 value (severity, time sensitivity, crowd level).
    Params  : field (str) - request field name, label (str) - shown name
    Returns : int
    """
    return ask("Enter %s (1-10): " % label, lambda text: pre.check_scale(text, field))


def ask_scales(raw):
    """
    Function: ask_scales
    Purpose : Ask severity, time sensitivity and crowd level.
    Params  : raw (dict) - changed in place
    Returns : None
    """
    raw["severity"] = ask_scale("severity", "Severity")
    raw["time_sensitivity"] = ask_scale("time_sensitivity", "Time Sensitivity")
    raw["crowd_level"] = ask_scale("crowd_level", "Crowd Level")


def ask_eligibility_and_note(raw):
    """
    Function: ask_eligibility_and_note
    Purpose : Urgent / Full only: the eligibility claim (ANN feature x7) and the
              optional description note.
    Params  : raw (dict) - changed in place
    Returns : None
    """
    raw["eligibility_claim"] = ask("Do you meet the eligibility requirements? (y/n): ",
                                   lambda text: pre.check_yes_no(text, "answer"))
    raw["description_note"] = read_line("Enter Description Note (optional): ")


def fill_form():
    """
    Function: fill_form
    Purpose : The structured request form: base fields, then only the fields
              the chosen request type needs (handout 2.2).
    Params  : none
    Returns : dict - raw request for main.process_request
    """
    raw = {"name": ask("Enter Name: ", pre.check_name),
           "role": ask("Enter Role (student/instructor/staff): ", pre.check_role)}
    raw["request_type"] = kind = ask_request_type()

    if kind == "Navigation_Only":
        raw["current_location"] = ask_location("current_location", "Enter Current Location: ")
        raw["destination"] = ask_location("destination", "Enter Destination: ")
    elif kind == "Eligibility_Check":
        raw["query"] = ask("Enter Query (e.g. UsesLab(DrKhan, Lab1)): ", pre.check_query)
    elif kind == "Booking_or_Scheduling":
        ask_category(raw)
        raw["preferred_slot"] = ask("Enter Preferred Slot (1-4): ", pre.check_slot)
        raw["current_location"] = ask_location(
            "current_location", "Enter Current Location for route guidance (optional): ",
            optional=True)
    elif kind == "Urgent_Service_Request":
        ask_category(raw)
        raw["current_location"] = ask_location("current_location", "Enter Current Location: ")
        ask_scales(raw)
        raw["preferred_slot"] = ask("Enter Preferred Slot (1-4, optional): ", pre.check_slot,
                                    optional=True)
        ask_eligibility_and_note(raw)
    else:   # Full_Service_Request
        ask_category(raw)
        raw["current_location"] = ask_location("current_location", "Enter Current Location: ")
        raw["preferred_slot"] = ask("Enter Preferred Slot (1-4): ", pre.check_slot)
        ask_scales(raw)
        ask_eligibility_and_note(raw)
    return raw


# ===========================================================================
# 2. Showing results
# ===========================================================================
def show_field(label, text):
    """
    Function: show_field
    Purpose : Print "Label    : text", wrapping long text under the value column.
    Params  : label (str), text (str)
    Returns : None
    """
    lead = "  %-11s: " % label
    print(textwrap.fill(str(text), width=WIDTH, initial_indent=lead,
                        subsequent_indent=" " * len(lead)))


def print_response(response):
    """
    Function: print_response
    Purpose : Pretty-print a final response: readable summary, then the JSON.
    Params  : response (dict) - from main.process_request
    Returns : None
    """
    print("-" * WIDTH)
    print("  RESPONSE %s" % response["request_id"])
    show_field("Decision", response["decision"].upper())
    if "rejected_at" in response:
        show_field("Rejected at", response["rejected_at"])
        show_field("Reason", response["reason"])
    priority = response.get("priority")
    if priority:
        show_field("Priority", "%s (MLP, confidence %.2f); Perceptron baseline: %s"
                   % (priority["final_priority"], priority["confidence"],
                      priority["binary_priority"]))
    eligibility = response.get("eligibility", {})
    if "entailed" in eligibility:
        show_field("Entailed", "yes" if eligibility["entailed"] else "no")
    if "allowed" in eligibility:
        show_field("Allowed", "yes" if eligibility["allowed"] else "no")
    if "explanation" in eligibility:
        show_field("Explanation", eligibility["explanation"])
    if response.get("assignment"):
        show_field("Assigned", "%s, slot %d" % (response["assignment"]["room"],
                                                response["assignment"]["slot"]))
    route = response.get("route")
    if route:
        show_field("Route", "%s  (%s, cost %d, %d step%s)" % (
            " -> ".join(route["path"]), route["algorithm"], route["cost"], route["steps"],
            "" if route["steps"] == 1 else "s"))
    show_field("Message", response["message"])
    print("  JSON:")
    print(textwrap.indent(json.dumps(response, indent=2), "    "))
    print("-" * WIDTH)


def show_bookings():
    """
    Function: show_bookings
    Purpose : Print the current room/slot bookings and booked vivas.
    Params  : none
    Returns : None
    """
    state = main.get_bookings()
    print("Current bookings (room, slot):")
    for room, slot in state["bookings"]:
        print("  slot %d  %s" % (slot, room))
    if state["viva"]:
        print("Viva bookings:")
        for group, (room, slot) in state["viva"].items():
            print("  %s  %s, slot %d" % (group, room, slot))


# ===========================================================================
# 3. Menu actions
# ===========================================================================
def new_request():
    """
    Function: new_request
    Purpose : Fill the form, process the request, show the response.
    Params  : none
    Returns : None
    """
    raw = fill_form()
    print_response(main.process_request(raw))


def run_demo():
    """
    Function: run_demo
    Purpose : Run every demo scenario. Each starts from the initial bookings so
              it matches the handout regardless of order; request ids keep counting.
    Params  : none
    Returns : None
    """
    print("Running %d demo scenarios (bookings are reset before each one)." % len(DEMO_SCENARIOS))
    for number, scenario in enumerate(DEMO_SCENARIOS, start=1):
        main.reset_system(clear_counter=False)
        print()
        print("=" * WIDTH)
        print("Demo %d: %s" % (number, scenario["title"]))
        print("  Raw input: %s" % json.dumps(scenario["request"]))
        print_response(main.process_request(scenario["request"]))
    main.reset_system(clear_counter=False)
    print("Demo finished; bookings are back to the initial ones.")


def reset():
    """
    Function: reset
    Purpose : Reset bookings and the request counter.
    Params  : none
    Returns : None
    """
    main.reset_system()
    print("System reset: bookings restored to the initial ones, ids restart at REQ101.")


def main_menu():
    """
    Function: main_menu
    Purpose : Show the main menu until the user exits (or input ends).
    Params  : none
    Returns : None
    """
    actions = {"1": new_request, "2": run_demo, "3": show_bookings, "4": reset}
    print("Smart Campus AI Decision Support and Automation System")
    while True:
        print()
        print("Main menu: 1. New request  2. Run demo scenarios  3. Show current bookings"
              "  4. Reset system  5. Exit")
        try:
            choice = read_line("Enter choice: ")
            if choice == "5":
                break
            if choice in actions:
                actions[choice]()
            else:
                print("  Invalid choice %r. Please enter 1-5." % choice)
        except InputClosed:
            print()
            break
    print("Goodbye.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if "--demo" in sys.argv[1:]:
        run_demo()
    else:
        main_menu()
