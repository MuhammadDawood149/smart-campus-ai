"""
File    : test_integration.py
Module  : Integration tests (preprocessing, router, final response, main)
Owner   : Joint (Students 1, 2 and 3)

Purpose : unittest checks for the whole system end to end:
            - every demo scenario: decision, room, slot, route, rejection stage
            - the handout full-service example matches Phase 3 section 11.8
            - a second identical booking gets a different slot (shared state)
            - reset_system() restores the initial bookings and request ids
            - preprocessing validation / normalisation, router pipelines,
              rejections at every stage, and that nothing ever raises
Run     : python -m unittest test_integration -v
"""

import json
import os
import tempfile
import unittest
from unittest import mock

import main
from integration.demo_scenarios import DEMO_SCENARIOS
from integration.preprocessing import preprocess
from integration.router import route
from student2_logic_csp.csp_scheduler import INITIAL_BOOKINGS

HANDOUT_PATH = ["Hostel", "Cafeteria", "Science_Block", "AI_Lab"]
HANDOUT_ROUTE = {"algorithm": "A*", "path": HANDOUT_PATH, "cost": 6, "steps": 3}
FULL_SERVICE = next(s["request"] for s in DEMO_SCENARIOS if s["id"] == "full_service")

# Expected result of each demo scenario run from the initial bookings:
# (decision, room, slot, route path or None, route cost or None, rejected_at or None)
EXPECTED = {
    "navigation": ("completed", None, None, HANDOUT_PATH, 6, None),
    "eligibility": ("answered", None, None, None, None, None),
    "booking": ("accepted", "AI_Lab", 3, HANDOUT_PATH, 6, None),
    "viva": ("accepted", "Exam_Hall", 2, None, None, None),
    "urgent": ("accepted", "Medical_Center", 1, ["Bus_Stop", "Medical_Center"], 2, None),
    "full_service": ("accepted", "AI_Lab", 3, HANDOUT_PATH, 6, None),
    "reject_logic_sara": ("rejected", None, None, None, None, "logic"),
    "reject_logic_viva": ("rejected", None, None, None, None, "logic"),
    "reject_location": ("rejected", None, None, None, None, "preprocessing"),
}


def booking(slot, name="Ali", location=None):
    """
    Function: booking
    Purpose : Build a raw AI_Lab_Support booking request.
    Params  : slot (int) - preferred slot, name (str), location (str or None)
    Returns : dict
    """
    raw = {"name": name, "role": "student", "request_type": "Booking_or_Scheduling",
           "category": "AI_Lab_Support", "preferred_slot": slot}
    if location:
        raw["current_location"] = location
    return raw


def full(**changes):
    """
    Function: full
    Purpose : The handout full-service request with some fields changed.
    Params  : changes - fields to override
    Returns : dict
    """
    raw = dict(FULL_SERVICE)
    raw.update(changes)
    return raw


class IntegrationTest(unittest.TestCase):
    """Common setup: logging off, fresh system before every test."""

    def setUp(self):
        """
        Function: setUp
        Purpose : Switch logging off and reset bookings and request ids.
        Params  : none
        Returns : None
        """
        main.LOG_ENABLED = False
        main.reset_system()

    def preprocess_error(self, raw):
        """
        Function: preprocess_error
        Purpose : Run preprocessing on its own and return the error text.
        Params  : raw (dict)
        Returns : str or None
        """
        return preprocess(raw, {"request_counter": 100})[1]


class TestDemoScenarios(IntegrationTest):

    def test_every_demo_scenario(self):
        """Each scenario, from the initial bookings, gives its expected result."""
        self.assertEqual(sorted(EXPECTED), sorted(s["id"] for s in DEMO_SCENARIOS))
        for scenario in DEMO_SCENARIOS:
            with self.subTest(scenario["id"]):
                main.reset_system()
                r = main.process_request(scenario["request"])
                decision, room, slot, path, cost, stage = EXPECTED[scenario["id"]]
                self.assertEqual(r["decision"], decision)
                self.assertEqual(r.get("rejected_at"), stage)
                if room is None:
                    self.assertNotIn("assignment", r)
                else:
                    self.assertEqual(r["assignment"], {"room": room, "slot": slot})
                if path is None:
                    self.assertNotIn("route", r)
                else:
                    self.assertEqual((r["route"]["path"], r["route"]["cost"]), (path, cost))
                    self.assertEqual(r["route"]["algorithm"], "A*")

    def test_navigation_matches_handout_6_2(self):
        r = main.process_request(DEMO_SCENARIOS[0]["request"])
        self.assertEqual(r, {"request_id": "REQ101", "decision": "completed",
                             "route": HANDOUT_ROUTE,
                             "message": "Best route generated successfully."})

    def test_eligibility_matches_handout_6_3(self):
        r = main.process_request(DEMO_SCENARIOS[1]["request"])
        self.assertEqual(r["decision"], "answered")
        self.assertEqual(r["eligibility"], {
            "entailed": True,
            "explanation": "DrKhan teaches AI, therefore DrKhan is an instructor of AI "
                           "and can use Lab1."})
        self.assertEqual(r["message"], "Eligibility query answered successfully.")

    def test_query_that_is_not_entailed_is_still_answered(self):
        r = main.process_request({"name": "Sara", "role": "student",
                                  "request_type": "Eligibility_Check",
                                  "query": "Eligible(Sara, AI)"})
        self.assertEqual(r["decision"], "answered")
        self.assertFalse(r["eligibility"]["entailed"])
        self.assertIn("Completed(Sara, ProgrammingFundamentals)", r["eligibility"]["explanation"])

    def test_booking_matches_handout_6_4(self):
        r = main.process_request(booking(2))
        self.assertEqual(r, {"request_id": "REQ101", "decision": "accepted",
                             "eligibility": {"allowed": True},
                             "assignment": {"room": "AI_Lab", "slot": 3},
                             "message": "Booking assigned successfully."})

    def test_logic_rejection_matches_handout_3_4(self):
        sara = next(s["request"] for s in DEMO_SCENARIOS if s["id"] == "reject_logic_sara")
        r = main.process_request(sara)
        self.assertEqual(list(r), ["request_id", "decision", "eligibility",
                                   "rejected_at", "reason", "message"])
        self.assertFalse(r["eligibility"]["allowed"])
        self.assertIn("Completed(Sara, ProgrammingFundamentals)", r["eligibility"]["explanation"])
        self.assertIn("CanRequest(Sara, AI_Lab_Support) cannot be proven", r["reason"])
        self.assertEqual(r["message"], "Your request has been rejected because you are "
                                       "not eligible for this service.")
        self.assertEqual(main.get_bookings()["bookings"], sorted(INITIAL_BOOKINGS,
                                                                 key=lambda b: (b[1], b[0])))


class TestHandoutFullService(IntegrationTest):

    def test_matches_handout_11_8(self):
        """Phase 3 section 11.8: high / urgent, AI_Lab slot 3, route cost 6."""
        r = main.process_request(FULL_SERVICE)
        self.assertEqual(list(r), ["request_id", "decision", "priority", "eligibility",
                                   "assignment", "route", "message"])
        self.assertEqual(r["decision"], "accepted")
        self.assertEqual(r["priority"]["binary_priority"], "urgent")
        self.assertEqual(r["priority"]["final_priority"], "high")
        self.assertTrue(0.0 <= r["priority"]["confidence"] <= 1.0)
        self.assertEqual(r["eligibility"], {"allowed": True})
        self.assertEqual(r["assignment"], {"room": "AI_Lab", "slot": 3})
        self.assertEqual(r["route"], HANDOUT_ROUTE)
        self.assertEqual(r["message"], "Your request has been accepted. You are assigned "
                                       "AI_Lab in slot 3. Please follow the recommended route.")

    def test_feature_vector(self):
        """Distance = route cost Hostel -> AI_Lab (6); eligibility claim -> 1."""
        request, error = preprocess(FULL_SERVICE, {"request_counter": 100})
        self.assertIsNone(error)
        self.assertEqual(request["ann_features"], [0, 0, 8, 9, 5, 6, 1])

    def test_router_output_matches_handout_7_2(self):
        request, _ = preprocess(FULL_SERVICE, {"request_counter": 204})
        self.assertEqual(route(request), {
            "request_id": "REQ205", "selected_pipeline": ["ANN", "Logic_KB", "CSP", "Search"],
            "needs_ann": True, "needs_logic": True, "needs_csp": True, "needs_search": True})


class TestSharedState(IntegrationTest):

    def test_second_identical_booking_gets_a_different_slot(self):
        first = main.process_request(booking(2))
        second = main.process_request(booking(2))
        self.assertEqual(first["assignment"], {"room": "AI_Lab", "slot": 3})
        self.assertEqual(second["assignment"], {"room": "AI_Lab", "slot": 4})
        self.assertEqual((first["request_id"], second["request_id"]), ("REQ101", "REQ102"))

    def test_reset_system_restores_initial_bookings(self):
        initial = main.get_bookings()
        main.process_request(booking(2))
        main.process_request(DEMO_SCENARIOS[3]["request"])           # viva G4
        self.assertNotEqual(main.get_bookings(), initial)
        main.reset_system()
        self.assertEqual(main.get_bookings(), initial)
        self.assertEqual(sorted(initial["bookings"]), sorted(INITIAL_BOOKINGS))
        self.assertEqual(initial["viva"], {})
        self.assertEqual(main.process_request(booking(2))["request_id"], "REQ101")

    def test_reset_keeping_the_counter(self):
        main.process_request(booking(2))
        main.reset_system(clear_counter=False)
        r = main.process_request(booking(2))
        self.assertEqual((r["request_id"], r["assignment"]["slot"]), ("REQ102", 3))

    def test_csp_rejection_when_every_slot_is_taken(self):
        for slot in (1, 3, 4):                         # slot 2 is booked initially
            self.assertEqual(main.process_request(booking(slot))["assignment"]["slot"], slot)
        before = main.get_bookings()
        r = main.process_request(booking(1))
        self.assertEqual((r["decision"], r["rejected_at"]), ("rejected", "csp"))
        self.assertEqual(r["eligibility"], {"allowed": True})
        self.assertIn("AI_Lab is already booked at slot(s) 1, 2, 3, 4", r["reason"])
        self.assertEqual(main.get_bookings(), before)

    def test_urgent_priority_tightens_the_deadline(self):
        """An urgent AI_Lab request must be served by slot 2; slot 1 is free."""
        r = main.process_request(full(severity=10, time_sensitivity=10, crowd_level=10,
                                      preferred_slot=4))
        self.assertEqual(r["priority"]["final_priority"], "urgent")
        self.assertEqual(r["assignment"], {"room": "AI_Lab", "slot": 1})

    def test_search_failure_undoes_the_booking(self):
        before = main.get_bookings()
        failed = {"success": False, "route": {}, "error": "No route found."}
        with mock.patch.object(main, "run_search", return_value=failed):
            r = main.process_request(FULL_SERVICE)
        self.assertEqual((r["decision"], r["rejected_at"], r["reason"]),
                         ("rejected", "search", "No route found."))
        self.assertIn("priority", r)
        self.assertEqual(main.get_bookings(), before)


class TestPreprocessing(IntegrationTest):

    def test_specific_rejection_reasons(self):
        cases = [
            (full(preferred_slot=7), "preferred_slot must be 1-4, got 7"),
            (full(preferred_slot="two"), "preferred_slot must be 1-4, got two"),
            (full(severity=11), "severity must be an integer 1-10, got 11"),
            (full(crowd_level="high"), "crowd_level must be an integer 1-10, got high"),
            (full(time_sensitivity=7.5), "time_sensitivity must be an integer 1-10, got 7.5"),
            (full(severity=None), "severity is required"),
            (full(request_type="Teleport"), "request_type must be one of"),
            (full(role="dean"), "role must be one of student/instructor/staff, got 'dean'"),
            (full(name=""), "name is required"),
            (full(name="Ali Khan"), "name must be one word"),
            (full(category="Parking_Permit"), "category must be one of"),
            (full(current_location="Moon"), "current_location: Unknown location 'Moon'"),
            (full(eligibility_claim="maybe"), "eligibility_claim must be yes or no, got maybe"),
            (full(category="Viva"), "group_id is required for Viva_Scheduling"),
            (booking(None), "preferred_slot is required"),
            ({"name": "Ali", "role": "student", "request_type": "Eligibility_Check",
              "query": "UsesLab(Ali Lab1"}, "query is invalid"),
            ({"name": "Ali", "role": "student", "request_type": "Navigation_Only",
              "current_location": "Hostel"}, "destination is required"),
        ]
        for raw, expected in cases:
            with self.subTest(expected):
                self.assertIn(expected, self.preprocess_error(raw) or "")

    def test_rejected_request_still_gets_an_id(self):
        r = main.process_request(full(preferred_slot=7))
        self.assertEqual(r, {"request_id": "REQ101", "decision": "rejected",
                             "rejected_at": "preprocessing",
                             "reason": "preferred_slot must be 1-4, got 7",
                             "message": "Your request has been rejected because the "
                                        "request details are invalid."})
        self.assertEqual(main.process_request(booking(2))["request_id"], "REQ102")

    def test_normalisation(self):
        raw = {"name": "dr khan", "role": " Instructor ", "request_type": "booking or scheduling",
               "category": "viva", "group_id": "g4", "preferred_slot": "3",
               "current_location": "main gate"}
        request, error = preprocess(raw, {"request_counter": 100})
        self.assertIsNone(error)
        self.assertEqual({k: request[k] for k in ("request_id", "name", "role", "request_type",
                                                  "category", "group_id", "preferred_slot",
                                                  "current_location")},
                         {"request_id": "REQ101", "name": "DrKhan", "role": "instructor",
                          "request_type": "Booking_or_Scheduling",
                          "category": "Viva_Scheduling", "group_id": "G4",
                          "preferred_slot": 3, "current_location": "Main_Gate"})

    def test_category_aliases_and_menu_numbers(self):
        for text, expected in (("Viva", "Viva_Scheduling"), ("access", "Access_Request"),
                               ("EMERGENCY", "Emergency_Help"), ("maintenance", "Maintenance"),
                               ("ai lab support", "AI_Lab_Support")):
            request, error = preprocess(full(category=text, group_id="G3"),
                                        {"request_counter": 1})
            self.assertEqual((request["category"], error), (expected, None), text)
        request, _ = preprocess(full(request_type="5"), {"request_counter": 1})
        self.assertEqual(request["request_type"], "Full_Service_Request")

    def test_unused_fields_keep_template_defaults(self):
        raw = dict(DEMO_SCENARIOS[0]["request"], severity=99, preferred_slot=9)
        request, error = preprocess(raw, {"request_counter": 1})
        self.assertIsNone(error)
        self.assertEqual((request["severity"], request["preferred_slot"]), (0, None))

    def test_unknown_name_is_rejected_by_logic_not_preprocessing(self):
        r = main.process_request(booking(2, name="zara"))
        self.assertEqual(r["rejected_at"], "logic")
        self.assertIn("Student(Zara)", r["reason"])
        self.assertIn("Zara is not a known person on campus", r["eligibility"]["explanation"])

    def test_unknown_group_is_rejected_by_logic(self):
        r = main.process_request({"name": "Ahmed", "role": "student",
                                  "request_type": "Booking_or_Scheduling",
                                  "category": "Viva", "group_id": "g9", "preferred_slot": 2})
        self.assertEqual(r["rejected_at"], "logic")
        self.assertIn("G9 is not a known FYP group", r["eligibility"]["explanation"])

    def test_wrong_role_is_rejected_at_authorization(self):
        r = main.process_request(dict(booking(2), role="instructor"))
        self.assertEqual(r["rejected_at"], "logic")
        self.assertEqual(r["reason"], "Role authorization failed: Faculty(Ali) cannot be proven.")

    def test_garbage_never_raises(self):
        for bad in (None, 42, "text", [], {}, {"name": "Ali"}, {"request_type": None}):
            with self.subTest(bad):
                r = main.process_request(bad)
                self.assertEqual((r["decision"], r["rejected_at"]), ("rejected", "preprocessing"))


class TestRouter(IntegrationTest):

    def pipeline(self, raw):
        """
        Function: pipeline
        Purpose : Preprocess a raw request and return the router's pipeline.
        Params  : raw (dict)
        Returns : list of str
        """
        request, error = preprocess(raw, {"request_counter": 1})
        self.assertIsNone(error)
        return route(request)["selected_pipeline"]

    def test_pipelines(self):
        by_id = {s["id"]: s["request"] for s in DEMO_SCENARIOS}
        self.assertEqual(self.pipeline(by_id["navigation"]), ["Search"])
        self.assertEqual(self.pipeline(by_id["eligibility"]), ["Logic_KB"])
        self.assertEqual(self.pipeline(booking(2)), ["Logic_KB", "CSP"])
        self.assertEqual(self.pipeline(booking(2, location="Hostel")),
                         ["Logic_KB", "CSP", "Search"])
        self.assertEqual(self.pipeline(by_id["urgent"]), ["ANN", "Logic_KB", "CSP", "Search"])
        self.assertEqual(self.pipeline(FULL_SERVICE), ["ANN", "Logic_KB", "CSP", "Search"])

    def test_route_only_output_matches_handout_7_3(self):
        request, _ = preprocess(DEMO_SCENARIOS[0]["request"], {"request_counter": 200})
        self.assertEqual(route(request), {
            "request_id": "REQ201", "selected_pipeline": ["Search"], "needs_ann": False,
            "needs_logic": False, "needs_csp": False, "needs_search": True})

    def test_unknown_type_gives_empty_pipeline(self):
        self.assertEqual(route({"request_id": "REQ1", "request_type": "X"})["selected_pipeline"],
                         [])


class TestLogging(IntegrationTest):

    def test_each_response_is_one_json_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "logs", "responses.jsonl")
            with mock.patch.object(main, "LOG_FILE", path):
                main.LOG_ENABLED = True
                first = main.process_request(DEMO_SCENARIOS[0]["request"])
                second = main.process_request(full(preferred_slot=7))
                main.LOG_ENABLED = False
            with open(path, encoding="utf-8") as handle:
                lines = [json.loads(line) for line in handle]
        self.assertEqual(lines, [first, second])


if __name__ == "__main__":
    unittest.main(verbosity=2)
