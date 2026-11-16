"""
File    : student2_logic_csp/logic_csp_cli.py
Module  : Logic / KB + CSP Scheduler demo
Owner   : Student 2

Purpose : Menu-driven demo of Student 2's parts: run a logic query, check a
          service permission, book a room/slot, show the current bookings,
          solve the viva timetable, reset the bookings. Invalid input is
          re-asked, never a crash.
Run     : python student2_logic_csp/logic_csp_cli.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logic_kb as kb
import csp_scheduler as cs
from shared.campus_data import CATEGORIES, ROLES, PRIORITY_LEVELS, TIME_SLOTS
from shared.templates import REQUEST_TEMPLATE, new_template


def read_line(prompt):
    """
    Function: read_line
    Purpose : input() that treats Ctrl+C / end of input as "leave the program".
    Params  : prompt (str)
    Returns : str, or None when input is closed
    """
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def ask_choice(prompt, options, allow_blank=False):
    """
    Function: ask_choice
    Purpose : Show a numbered list and ask until a valid number or name is given.
    Params  : prompt (str), options (list of str), allow_blank (bool) - blank = None
    Returns : the chosen option (str), or None if blank (when allowed) / input closed
    """
    for number, option in enumerate(options, 1):
        print("  %d. %s" % (number, option))
    while True:
        text = read_line("%s%s: " % (prompt, " (blank = none)" if allow_blank else ""))
        if text is None:
            return None
        text = text.strip()
        if not text and allow_blank:
            return None
        if text.isdigit() and 1 <= int(text) <= len(options):
            return options[int(text) - 1]
        for option in options:
            if text.lower() == option.lower():
                return option
        print("  Please pick one of the options above.")


def ask_slot(prompt):
    """
    Function: ask_slot
    Purpose : Ask for a time slot; blank means no preference.
    Params  : prompt (str)
    Returns : int slot, or None (blank / input closed)
    """
    while True:
        text = read_line("%s %s (blank = none): " % (prompt, TIME_SLOTS))
        if text is None or not text.strip():
            return None
        if text.strip().isdigit() and int(text.strip()) in TIME_SLOTS:
            return int(text.strip())
        print("  Slot must be one of %s." % TIME_SLOTS)


def logic_query():
    """
    Function: logic_query
    Purpose : Ask for a logic query and print the Logic/KB answer.
    Params  : none
    Returns : None
    """
    print("Query examples: UsesLab(Ali, Lab1)   Eligible(x, AI)   Instructor(DrKhan, AI)")
    text = read_line("Query (blank = back): ")
    if text is None or not text.strip():
        return
    result = kb.check_logic({"request_type": "Eligibility_Check", "query": text.strip()})
    print("  Entailed    : %s" % result["entailed"])
    print("  Explanation : %s" % result["explanation"])
    for line in result["proof"]:
        print("    - " + line)


def check_permission():
    """
    Function: check_permission
    Purpose : Ask who wants which service and print the Logic/KB permission check.
    Params  : none
    Returns : None
    """
    name = read_line("Name, one word starting with a capital, e.g. Ali (blank = back): ")
    if name is None or not name.strip():
        return
    role = ask_choice("Role", ROLES)
    category = ask_choice("Category", CATEGORIES) if role else None
    if category is None:
        return
    request = {"name": name.strip(), "role": role, "category": category,
               "request_type": "Booking_or_Scheduling"}
    if category == cs.VIVA_CATEGORY:
        group = read_line("Group (e.g. G3): ")
        if group is None:
            return
        request["group_id"] = group.strip()
    result = kb.check_logic(request)
    print("  Allowed     : %s" % result["allowed"])
    print("  Explanation : %s" % result["explanation"])


def book_slot():
    """
    Function: book_slot
    Purpose : Ask for a service request and book it with the CSP scheduler.
    Params  : none
    Returns : None
    """
    print("Category:")
    category = ask_choice("Choose", CATEGORIES)
    if category is None:
        return
    request = new_template(REQUEST_TEMPLATE)
    request["category"] = category
    if category == cs.VIVA_CATEGORY:
        group = read_line("Group (G1-G6): ")
        if group is None:
            return
        request["group_id"] = group.strip()
    request["preferred_slot"] = ask_slot("Preferred slot")
    print("Priority:")
    priority = ask_choice("Choose", PRIORITY_LEVELS, allow_blank=True)
    result = cs.schedule(request, priority)
    print("  Decision : %s" % result["decision"])
    if result["decision"] == "accepted":
        print("  Room     : %s" % result["assigned_room"])
        print("  Slot     : %s" % result["assigned_slot"])
    print("  Notes    : %s" % result["notes"])
    print("  Search   : %d assignments tried, %d backtracks"
          % (result["stats"]["assignments"], result["stats"]["backtracks"]))


def show_bookings():
    """
    Function: show_bookings
    Purpose : Print every current booking, one line each.
    Params  : none
    Returns : None
    """
    print("Current bookings (%d):" % len(cs.get_bookings()))
    for room, slot in cs.get_bookings():
        groups = [g for g, booked in sorted(cs.STATE["viva"].items()) if booked == (room, slot)]
        print("  Slot %d  %-17s%s" % (slot, room, "  (viva %s)" % groups[0] if groups else ""))


def viva_timetable():
    """
    Function: viva_timetable
    Purpose : Solve the viva timetable (optionally with one preferred slot) and
              print it with the search statistics. Does not book anything.
    Params  : none
    Returns : None
    """
    group = read_line("Group with a preferred slot, e.g. G4 (blank = none): ")
    if group is None:
        return
    group = group.strip().upper()
    preferred = None
    if group in cs.VIVA_GROUPS:
        slot = ask_slot("Preferred slot for %s" % group)
        preferred = {group: slot} if slot else None
    elif group:
        print("  '%s' is not one of %s; solving without a preference." % (group, ", ".join(cs.VIVA_GROUPS)))
    timetable, stats = cs.run_viva(preferred)
    if timetable is None:
        print("  No valid timetable exists.")
        return
    print("  Viva timetable (G4 before G3, no clashes):")
    for slot in TIME_SLOTS:
        print("    Slot %d: %s" % (slot, ", ".join(g for g in cs.VIVA_GROUPS if timetable[g] == slot) or "-"))
    print("  Search: %d assignments tried, %d backtracks" % (stats["assignments"], stats["backtracks"]))


def main():
    """
    Function: main
    Purpose : Show the menu in a loop until the user exits.
    Params  : none
    Returns : None
    """
    while True:
        print("\n=== Logic and CSP ===")
        print("1. Run a logic query\n2. Check a service permission\n3. Book a slot")
        print("4. Show current bookings\n5. Solve the viva timetable\n6. Reset bookings\n7. Exit")
        choice = read_line("Choose 1-7: ")
        if choice is None or choice.strip() == "7":
            print("Goodbye.")
            return
        choice = choice.strip()
        if choice == "1":
            logic_query()
        elif choice == "2":
            check_permission()
        elif choice == "3":
            book_slot()
        elif choice == "4":
            show_bookings()
        elif choice == "5":
            viva_timetable()
        elif choice == "6":
            cs.reset()
            print("Bookings reset to the initial ones.")
        else:
            print("Please enter a number from 1 to 7.")


if __name__ == "__main__":
    main()
