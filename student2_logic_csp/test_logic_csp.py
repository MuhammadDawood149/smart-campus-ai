"""
File    : student2_logic_csp/test_logic_csp.py
Module  : CSP Scheduler tests
Owner   : Student 2

Purpose : unittest checks for csp_scheduler.py: the generic solver, the viva
          timetable (brute-force counts 120 / 6 / 0), and schedule() (handout
          example, double booking, urgent deadline, viva precedence, bad input).
Run     : python -m unittest student2_logic_csp.test_logic_csp -v
          (or: python student2_logic_csp/test_logic_csp.py)
"""

import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import csp_scheduler as cs

# The diagram constraints written out again here (from CLAUDE.md), so the tests
# do not depend on the constants inside csp_scheduler.py.
NOT_EQUAL = [("G1", "G2"), ("G1", "G4"), ("G1", "G3"), ("G2", "G4"),
             ("G2", "G5"), ("G3", "G5"), ("G3", "G6"), ("G5", "G6")]
GROUPS = ["G1", "G2", "G3", "G4", "G5", "G6"]
HANDOUT_NOTE = ("Preferred slot 2 was unavailable. Slot 3 is the next feasible "
                "conflict-free assignment.")


def is_valid_timetable(t):
    """
    Function: is_valid_timetable
    Purpose : Check a timetable against all 8 not-equal constraints and G4 < G3.
    Params  : t (dict group -> slot)
    Returns : bool
    """
    return (all(t[a] != t[b] for a, b in NOT_EQUAL) and t["G4"] < t["G3"])


def count_solutions(slots):
    """
    Function: count_solutions
    Purpose : Brute force: try every assignment of slots 1..slots to G1..G6.
    Params  : slots (int) - number of slots
    Returns : int - how many assignments satisfy every constraint
    """
    return sum(is_valid_timetable(dict(zip(GROUPS, values)))
               for values in itertools.product(range(1, slots + 1), repeat=6))


def request(category="AI_Lab_Support", slot=None, group="", name="Ali"):
    """
    Function: request
    Purpose : Build a minimal request dict for schedule().
    Params  : category (str), slot (int or None), group (str), name (str)
    Returns : dict
    """
    return {"name": name, "category": category, "preferred_slot": slot, "group_id": group}


class TestSolver(unittest.TestCase):
    """The generic CSP solver."""

    def test_brute_force_counts(self):
        self.assertEqual(count_solutions(4), 120)
        self.assertEqual(count_solutions(3), 6)
        self.assertEqual(count_solutions(2), 0)

    def test_solver_output_satisfies_every_constraint(self):
        solution, stats = cs.solve_csp(*cs.viva_problem())
        self.assertEqual(sorted(solution), GROUPS)
        self.assertTrue(is_valid_timetable(solution), solution)
        self.assertTrue(all(s in [1, 2, 3, 4] for s in solution.values()))
        self.assertGreaterEqual(stats["assignments"], 6)

    def test_three_slots_solvable_two_slots_not(self):
        solution, stats = cs.solve_csp(*cs.viva_problem(slots=[1, 2, 3]))
        self.assertTrue(is_valid_timetable(solution), solution)
        solution, stats = cs.solve_csp(*cs.viva_problem(slots=[1, 2]))
        self.assertIsNone(solution)

    def test_stats_count_tries_and_backtracks(self):
        # Two variables that must differ, but only one value exists: no solution.
        solution, stats = cs.solve_csp(["A", "B"], {"A": [1], "B": [1]},
                                       [(("A", "B"), cs.not_equal)])
        self.assertIsNone(solution)
        self.assertEqual(stats, {"assignments": 1, "backtracks": 1})

    def test_unary_constraint_and_empty_domain(self):
        def big(x):
            """
            Function: big
            Purpose : Test constraint: the value is above 5.
            Params  : x (int)
            Returns : bool
            """
            return x > 5
        solution, stats = cs.solve_csp(["A"], {"A": [1, 2, 3]}, [(("A",), big)])
        self.assertIsNone(solution)
        self.assertEqual(stats["assignments"], 0)

    def test_preferred_is_tried_first_not_forced(self):
        free = cs.solve_viva()
        self.assertTrue(is_valid_timetable(free))
        # G4 = 2 is possible, so it is used...
        t = cs.solve_viva({"G4": 2})
        self.assertEqual(t["G4"], 2)
        self.assertTrue(is_valid_timetable(t))
        # ...but G4 = 4 is impossible (G4 < G3), so the preference is skipped.
        t = cs.solve_viva({"G4": 4})
        self.assertNotEqual(t["G4"], 4)
        self.assertTrue(is_valid_timetable(t))

    def test_every_feasible_preference_is_honoured(self):
        feasible = set()                 # (group, slot) pairs that some valid timetable uses
        for values in itertools.product(range(1, 5), repeat=6):
            t = dict(zip(GROUPS, values))
            if is_valid_timetable(t):
                feasible.update(t.items())
        for group in GROUPS:
            for slot in range(1, 5):
                t = cs.solve_viva({group: slot})
                self.assertTrue(is_valid_timetable(t), (group, slot))
                if (group, slot) in feasible:
                    self.assertEqual(t[group], slot, (group, slot))
                else:
                    self.assertNotEqual(t[group], slot, (group, slot))

    def test_slot_order(self):
        self.assertEqual(cs.slot_order(2), [2, 3, 4, 1])
        self.assertEqual(cs.slot_order(4), [4, 3, 2, 1])
        self.assertEqual(cs.slot_order(None), [1, 2, 3, 4])


class TestSchedule(unittest.TestCase):
    """schedule(): the entry point."""

    FIELDS = ["decision", "assigned_room", "assigned_slot", "destination",
              "notes", "stats", "timetable"]

    def setUp(self):
        cs.reset()

    def test_initial_bookings(self):
        self.assertEqual(sorted(cs.get_bookings()),
                         sorted([("AI_Lab", 2), ("Exam_Hall", 1), ("Admin_Block", 1)]))

    def test_handout_example(self):
        r = cs.schedule(request("AI_Lab_Support", 2), "high")
        for field in self.FIELDS:
            self.assertIn(field, r)
        self.assertEqual(r["decision"], "accepted")
        self.assertEqual((r["assigned_room"], r["assigned_slot"]), ("AI_Lab", 3))
        self.assertEqual(r["destination"], "AI_Lab")
        self.assertEqual(r["notes"], HANDOUT_NOTE)

    def test_handout_example_any_priority_case(self):
        for spelling in ["high", "High", "HIGH", " hIgH "]:
            cs.reset()
            r = cs.schedule(request("AI_Lab_Support", 2), spelling)
            self.assertEqual((r["decision"], r["assigned_room"], r["assigned_slot"]),
                             ("accepted", "AI_Lab", 3), spelling)
            self.assertEqual(r["notes"], HANDOUT_NOTE, spelling)

    def test_unknown_priority_strings_are_rejected(self):
        for bad in ["hi", "highest", "", "Critical", 3, ["high"]]:
            r = cs.schedule(request("AI_Lab_Support", 2), bad)
            self.assertEqual(r["decision"], "rejected", bad)
            self.assertIn("Priority", r["notes"])
        self.assertEqual(len(cs.get_bookings()), 3)

    def test_free_preferred_slot_is_used(self):
        r = cs.schedule(request("AI_Lab_Support", 4), "low")
        self.assertEqual((r["assigned_room"], r["assigned_slot"]), ("AI_Lab", 4))
        self.assertIn("available", r["notes"])

    def test_no_preferred_slot_takes_earliest(self):
        r = cs.schedule(request("Maintenance"), None)
        self.assertEqual((r["assigned_room"], r["assigned_slot"]), ("Student_Services", 1))

    def test_each_category_gets_its_room(self):
        expected = {"AI_Lab_Support": "AI_Lab", "Access_Request": "Admin_Block",
                    "Maintenance": "Student_Services", "Emergency_Help": "Medical_Center"}
        for category, room in expected.items():
            r = cs.schedule(request(category, 4))
            self.assertEqual((r["decision"], r["assigned_room"]), ("accepted", room), category)

    def test_preferred_slot_with_earlier_fallback(self):
        # preferred 4 is free but after the deadline, so the order continues 3, 2, 1
        r = cs.schedule(request("Maintenance", 4), "high")       # deadline 3
        self.assertEqual(r["assigned_slot"], 3)
        self.assertIn("Preferred slot 4 was unavailable", r["notes"])

    def test_booking_same_slot_twice_moves_to_next(self):
        first = cs.schedule(request("Maintenance", 2), "normal")
        second = cs.schedule(request("Maintenance", 2), "normal")
        self.assertEqual(first["assigned_slot"], 2)
        self.assertEqual(second["assigned_slot"], 3)
        self.assertEqual(second["notes"], HANDOUT_NOTE)
        third = cs.schedule(request("Maintenance", 2), "normal")
        self.assertEqual(third["assigned_slot"], 4)
        self.assertEqual(cs.get_bookings().count(("Student_Services", 3)), 1)

    def test_urgent_rejected_when_only_late_slots_are_free(self):
        cs.schedule(request("AI_Lab_Support", 1), "normal")       # AI_Lab slot 1
        # AI_Lab slot 2 is an initial booking, so only slots 3 and 4 are free
        before = cs.get_bookings()
        r = cs.schedule(request("AI_Lab_Support", 2), "urgent")
        self.assertEqual(r["decision"], "rejected")
        self.assertIsNone(r["assigned_slot"])
        self.assertEqual((r["assigned_room"], r["destination"]), ("", ""))
        self.assertIn("slot 2", r["notes"])
        self.assertIn("urgent", r["notes"].lower())
        self.assertIn("after the deadline", r["notes"])
        self.assertEqual(cs.get_bookings(), before)               # nothing was committed

    def test_rejected_request_does_not_change_bookings(self):
        before = cs.get_bookings()
        for bad in [request("Nonsense", 2), request("AI_Lab_Support", 9)]:
            self.assertEqual(cs.schedule(bad)["decision"], "rejected")
        self.assertEqual(cs.get_bookings(), before)

    def test_reset_restores_initial_bookings(self):
        cs.schedule(request("Maintenance", 1))
        self.assertEqual(len(cs.get_bookings()), 4)
        cs.reset()
        self.assertEqual(len(cs.get_bookings()), 3)

    def test_separate_state_does_not_touch_shared_one(self):
        mine = cs.new_state()
        cs.schedule(request("Maintenance", 1), None, mine)
        self.assertEqual(len(cs.get_bookings()), 3)
        self.assertEqual(len(cs.get_bookings(mine)), 4)

    def test_priority_is_case_insensitive_and_checked(self):
        self.assertEqual(cs.schedule(request("Maintenance", 4), "URGENT")["assigned_slot"], 2)
        r = cs.schedule(request("Maintenance", 4), "Critical")
        self.assertEqual(r["decision"], "rejected")
        self.assertIn("Critical", r["notes"])


class TestViva(unittest.TestCase):
    """Viva_Scheduling through schedule()."""

    def setUp(self):
        cs.reset()

    def test_g4_is_earlier_than_g3(self):
        g4 = cs.schedule(request("Viva_Scheduling", group="G4"))
        g3 = cs.schedule(request("Viva_Scheduling", group="G3"))
        self.assertEqual((g4["decision"], g3["decision"]), ("accepted", "accepted"))
        self.assertLess(g4["assigned_slot"], g3["assigned_slot"])
        self.assertLess(g4["timetable"]["G4"], g4["timetable"]["G3"])
        self.assertTrue(is_valid_timetable(g4["timetable"]))
        self.assertEqual(g4["assigned_slot"], g4["timetable"]["G4"])

    def test_g3_requested_first_is_still_after_g4(self):
        g3 = cs.schedule(request("Viva_Scheduling", 1, group="G3"))   # slot 1 is impossible
        g4 = cs.schedule(request("Viva_Scheduling", group="G4"))
        self.assertGreater(g3["assigned_slot"], 1)
        self.assertLess(g4["assigned_slot"], g3["assigned_slot"])

    def test_room_is_first_free_in_that_slot(self):
        r = cs.schedule(request("Viva_Scheduling", 1, group="G1"))
        self.assertEqual(r["assigned_slot"], 1)
        self.assertEqual(r["assigned_room"], "Seminar_Room")      # Exam_Hall is booked at 1
        self.assertEqual(r["destination"], "Seminar_Room")
        r = cs.schedule(request("Viva_Scheduling", 2, group="G2"))
        self.assertEqual((r["assigned_room"], r["assigned_slot"]), ("Exam_Hall", 2))

    def test_groups_get_distinct_slots_when_they_clash(self):
        a = cs.schedule(request("Viva_Scheduling", 2, group="G1"))
        b = cs.schedule(request("Viva_Scheduling", 2, group="G2"))   # G1-G2 must differ
        self.assertNotEqual(a["assigned_slot"], b["assigned_slot"])
        self.assertIn("unavailable", b["notes"])

    def test_same_group_again_replaces_its_booking(self):
        cs.schedule(request("Viva_Scheduling", 2, group="G1"))
        count = len(cs.get_bookings())
        again = cs.schedule(request("Viva_Scheduling", 3, group="G1"))
        self.assertEqual(again["assigned_slot"], 3)
        self.assertEqual(len(cs.get_bookings()), count)
        self.assertNotIn(("Exam_Hall", 2), cs.get_bookings())

    def test_reschedule_is_mentioned_in_notes(self):
        first = cs.schedule(request("Viva_Scheduling", 1, group="G4"))
        self.assertEqual(first["assigned_slot"], 1)
        self.assertNotIn("rescheduled", first["notes"])          # a first booking is not a move
        again = cs.schedule(request("Viva_Scheduling", 2, group="G4"))
        self.assertEqual(again["assigned_slot"], 2)
        self.assertIn("G4 was rescheduled from slot 1 to slot 2.", again["notes"])
        same = cs.schedule(request("Viva_Scheduling", 2, group="G4"))
        self.assertEqual(same["assigned_slot"], 2)
        self.assertIn("G4 already had slot 2", same["notes"])
        self.assertNotIn("rescheduled", same["notes"])
        # a rejected re-request keeps the booking and says nothing about moving
        r = cs.schedule(request("Viva_Scheduling", 4, group="G4"), "bogus")
        self.assertEqual(r["decision"], "rejected")
        self.assertEqual(cs.STATE["viva"]["G4"][1], 2)

    def test_group_is_case_insensitive_and_required(self):
        self.assertEqual(cs.schedule(request("Viva_Scheduling", group="g4"))["decision"], "accepted")
        for bad in ["", "G9", "Group4", None]:
            r = cs.schedule(request("Viva_Scheduling", group=bad))
            self.assertEqual(r["decision"], "rejected", bad)
            self.assertIn("group_id", r["notes"])

    def test_urgent_viva_respects_deadline(self):
        r = cs.schedule(request("Viva_Scheduling", group="G4"), "urgent")
        self.assertEqual(r["decision"], "accepted")
        self.assertLessEqual(r["assigned_slot"], 2)
        # G3 needs a slot after G4, so with G4 at 1 an urgent G3 gets slot 2
        r = cs.schedule(request("Viva_Scheduling", group="G3"), "urgent")
        self.assertEqual(r["decision"], "accepted")
        self.assertLessEqual(r["assigned_slot"], 2)

    def test_viva_rejected_when_no_room_before_deadline(self):
        for slot in (1, 2):                      # fill Seminar_Room at 1 and 2, Exam_Hall at 2
            cs.STATE["bookings"].update([("Seminar_Room", slot), ("Exam_Hall", slot)])
        before = cs.get_bookings()
        r = cs.schedule(request("Viva_Scheduling", group="G4"), "urgent")
        self.assertEqual(r["decision"], "rejected")
        self.assertIn("slot 2", r["notes"])
        self.assertEqual(cs.get_bookings(), before)


class TestBadInput(unittest.TestCase):
    """Invalid requests are rejected cleanly: no exception, no print."""

    def setUp(self):
        cs.reset()

    def test_invalid_category(self):
        for category in ["Nonsense", "", None, 5, "Viva", "Access"]:
            r = cs.schedule(request(category, 2))
            self.assertEqual(r["decision"], "rejected", category)
            self.assertIn("Category", r["notes"])

    def test_slot_out_of_range(self):
        for slot in [0, 5, -1, 99, 2.5, "x", True, [1]]:
            r = cs.schedule(request("AI_Lab_Support", slot))
            self.assertEqual(r["decision"], "rejected", slot)
            self.assertIn("preferred_slot", r["notes"])
            self.assertIsNone(r["assigned_slot"])

    def test_slot_as_digit_text_is_accepted(self):
        self.assertEqual(cs.schedule(request("Maintenance", "3"))["assigned_slot"], 3)

    def test_odd_requests_never_raise(self):
        for bad in [None, 42, "text", [], {}, {"category": None}, {"category": 5}]:
            r = cs.schedule(bad)
            self.assertEqual(r["decision"], "rejected", bad)
            for field in TestSchedule.FIELDS:
                self.assertIn(field, r)

    def test_category_is_case_insensitive(self):
        r = cs.schedule(request("ai_lab_support", 4))
        self.assertEqual((r["decision"], r["assigned_room"]), ("accepted", "AI_Lab"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
