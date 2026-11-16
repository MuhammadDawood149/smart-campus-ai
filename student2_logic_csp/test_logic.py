"""
File    : student2_logic_csp/test_logic.py
Module  : Logic / KB tests
Owner   : Student 2

Purpose : unittest checks for logic_kb.py: the knowledge base, unification,
          forward chaining, backward chaining, and check_logic (eligibility
          queries, role authorization, permission rules, malformed input).
Run     : python -m unittest student2_logic_csp.test_logic -v
          (or: python student2_logic_csp/test_logic.py)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logic_kb as kb


def ask(query, name="Anyone", role="student"):
    """
    Function: ask
    Purpose : Run an Eligibility_Check query through check_logic.
    Params  : query (str), name (str), role (str)
    Returns : dict - the check_logic result
    """
    return kb.check_logic({"name": name, "role": role,
                           "request_type": "Eligibility_Check", "query": query})


def service(name, role, category, request_type="Booking_or_Scheduling", group_id=""):
    """
    Function: service
    Purpose : Run a service request (booking / urgent / full) through check_logic.
    Params  : name (str), role (str), category (str), request_type (str),
              group_id (str) - only needed for Viva_Scheduling
    Returns : dict - the check_logic result
    """
    return kb.check_logic({"name": name, "role": role, "request_type": request_type,
                           "category": category, "group_id": group_id})


def rule_line(rule_id):
    """
    Function: rule_line
    Purpose : Text of one rule as it appears in a proof.
    Params  : rule_id (str) - "R1".."R15"
    Returns : str
    """
    return kb.rule_text([r for r in kb.RULES if r["id"] == rule_id][0])


class TestKnowledgeBase(unittest.TestCase):
    """Sanity checks on the facts and rules."""

    def test_counts(self):
        self.assertEqual(len(kb.RULES), 15)
        self.assertEqual([r["id"] for r in kb.RULES], ["R%d" % i for i in range(1, 16)])
        self.assertEqual(len(kb.FACTS), len(set(kb.FACTS)))          # no duplicates
        self.assertEqual(len([f for f in kb.FACTS if f[0] == "FYPGroup"]), 6)

    def test_rules_are_safe(self):
        """Every variable of a conclusion also appears in a premise."""
        for rule in kb.RULES:
            premise_vars = {t for p in rule["premises"] for t in p[1:] if kb.is_variable(t)}
            conclusion_vars = {t for t in rule["conclusion"][1:] if kb.is_variable(t)}
            self.assertTrue(conclusion_vars <= premise_vars, rule["id"])

    def test_facts_are_ground(self):
        for fact in kb.FACTS:
            self.assertFalse(any(kb.is_variable(t) for t in fact[1:]), fact)


class TestUnification(unittest.TestCase):
    """Unification of flat atoms."""

    def test_constant_match(self):
        self.assertEqual(kb.unify(("Student", "Ali"), ("Student", "Ali"), {}), {})

    def test_constant_clash(self):
        self.assertIsNone(kb.unify(("Student", "Ali"), ("Student", "Sara"), {}))

    def test_predicate_or_arity_clash(self):
        self.assertIsNone(kb.unify(("Student", "Ali"), ("Faculty", "Ali"), {}))
        self.assertIsNone(kb.unify(("Student", "Ali"), ("Enrolled", "Ali", "AI"), {}))

    def test_variable_binding(self):
        s = kb.unify(("Teaches", "x", "AI"), ("Teaches", "DrKhan", "AI"), {})
        self.assertEqual(s, {"x": "DrKhan"})

    def test_existing_binding_is_respected(self):
        self.assertIsNone(kb.unify(("Student", "x"), ("Student", "Sara"), {"x": "Ali"}))
        self.assertEqual(kb.unify(("Student", "x"), ("Student", "Ali"), {"x": "Ali"}), {"x": "Ali"})

    def test_repeated_variable(self):
        self.assertIsNone(kb.unify(("P", "x", "x"), ("P", "A", "B"), {}))
        self.assertEqual(kb.unify(("P", "x", "x"), ("P", "A", "A"), {}), {"x": "A"})

    def test_input_substitution_not_changed(self):
        start = {}
        kb.unify(("Student", "x"), ("Student", "Ali"), start)
        self.assertEqual(start, {})


class TestForwardChaining(unittest.TestCase):
    """Forward chaining derives all consequences and logs the rules used."""

    def setUp(self):
        self.result = kb.forward_chain()

    def test_derives_instructor(self):
        self.assertIn(("Instructor", "DrKhan", "AI"), self.result["derived"])

    def test_derives_diagram_facts(self):
        """The four derived facts listed in CLAUDE.md."""
        for fact in [("Instructor", "DrKhan", "AI"), ("UsesLab", "DrKhan", "Lab1"),
                     ("UsesLab", "Ali", "Lab1"), ("Eligible", "Ali", "AI")]:
            self.assertIn(fact, self.result["facts"])

    def test_sara_not_eligible(self):
        self.assertNotIn(("Eligible", "Sara", "AI"), self.result["facts"])

    def test_log_records_rule_that_fired(self):
        entry = [e for e in self.result["log"] if e["derived"] == ("Instructor", "DrKhan", "AI")][0]
        self.assertEqual(entry["rule"], "R2")
        self.assertEqual(entry["premises"], [("Teaches", "DrKhan", "AI")])
        lines = kb.format_log(self.result["log"])
        self.assertIn("R2 fired on Teaches(DrKhan, AI) => Instructor(DrKhan, AI)",
                      " ".join(lines))

    def test_every_derived_fact_has_one_log_entry(self):
        self.assertEqual([e["derived"] for e in self.result["log"]], self.result["derived"])

    def test_no_duplicates_and_given_facts_kept(self):
        self.assertEqual(len(self.result["facts"]), len(set(self.result["facts"])))
        self.assertEqual(self.result["facts"][:len(kb.FACTS)], kb.FACTS)

    def test_does_not_change_the_kb(self):
        before = list(kb.FACTS)
        kb.forward_chain()
        self.assertEqual(kb.FACTS, before)

    def test_person_rules(self):
        for who in ["Sara", "Ali", "Ahmed", "DrKhan", "DrAmna", "Bilal"]:
            self.assertIn(("Person", who), self.result["facts"], who)


class TestBackwardChaining(unittest.TestCase):
    """Backward chaining: proofs, variables, closed world."""

    def test_ground_proof(self):
        answers = kb.backward_chain(("UsesLab", "DrKhan", "Lab1"))
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["proof"],
                         ["Teaches(DrKhan, AI)", rule_line("R2"), rule_line("R4")])

    def test_unprovable_is_empty(self):
        self.assertEqual(kb.backward_chain(("Eligible", "Sara", "AI")), [])
        self.assertEqual(kb.backward_chain(("Student", "Zed")), [])

    def test_variable_query_all_answers(self):
        answers = kb.backward_chain(("UsesLab", "x", "Lab1"))
        self.assertEqual({a["bindings"]["x"] for a in answers}, {"DrKhan", "Ali", "Ahmed"})
        self.assertEqual(len(answers), 3)            # no duplicates

    def test_two_variables(self):
        answers = kb.backward_chain(("MemberOf", "x", "g"))
        self.assertEqual({(a["bindings"]["x"], a["bindings"]["g"]) for a in answers},
                         {("Ahmed", "G4"), ("Ali", "G3")})

    def test_query_variable_clash_with_rule_variable(self):
        """Query uses x, rules also use x: renaming must keep them apart."""
        answers = kb.backward_chain(("Eligible", "x", "AI"))
        self.assertEqual({a["bindings"]["x"] for a in answers}, {"Ali", "Ahmed"})

    def test_forward_and_backward_agree(self):
        queries = [("UsesLab", "x", "Lab1"), ("Eligible", "x", "AI"), ("Person", "x"),
                   ("CanRequest", "x", "AI_Lab_Support"), ("CanScheduleViva", "x", "g"),
                   ("CanScheduleViva", "x", "G4"), ("CanScheduleViva", "Ali", "g"),
                   ("CanRequest", "x", "Access_Request"), ("CanRequest", "x", "Maintenance"),
                   ("CanRequest", "x", "Emergency_Help"), ("Instructor", "x", "AI"),
                   ("UsesLab", "Sara", "Lab1"), ("Eligible", "Ali", "AI")]
        for q in queries:
            backward = sorted(sorted(a["bindings"].items()) for a in kb.backward_chain(q))
            forward = sorted(sorted(b.items()) for b in kb.forward_answers(q))
            self.assertEqual(backward, forward, q)


class TestParsing(unittest.TestCase):
    """parse_atom accepts good queries and rejects bad ones with a message."""

    def test_good(self):
        self.assertEqual(kb.parse_atom("UsesLab(DrKhan, Lab1)"), (("UsesLab", "DrKhan", "Lab1"), None))
        self.assertEqual(kb.parse_atom("  UsesLab( x ,Lab1 )  ")[0], ("UsesLab", "x", "Lab1"))

    def test_bad(self):
        bad = ["", "   ", "UsesLab", "UsesLab(DrKhan", "UsesLab DrKhan)", "UsesLab()",
               "UsesLab(DrKhan,)", "UsesLab(,Lab1)", "UsesLab(DrKhan, Lab1))",
               "UsesLab((DrKhan, Lab1)", "usesLab(DrKhan, Lab1)", "UsesLab(drkhan, Lab1)",
               "UsesLab(xy, Lab1)", "UsesLab(Dr Khan, Lab1)", "Foo(Ali)", "UsesLab(Ali)",
               "Student(Ali, AI)", "Student(Ali) & Student(Sara)", None, 42, ["UsesLab(Ali, Lab1)"]]
        for text in bad:
            atom, error = kb.parse_atom(text)
            self.assertIsNone(atom, text)
            self.assertTrue(error, text)


class TestEligibilityCheck(unittest.TestCase):
    """check_logic with request_type Eligibility_Check."""

    def test_instructor_uses_lab(self):
        r = ask("UsesLab(DrKhan, Lab1)", "DrKhan", "instructor")
        self.assertTrue(r["allowed"])
        self.assertTrue(r["entailed"])
        self.assertEqual(r["query"], "UsesLab(DrKhan, Lab1)")
        # proof order: Teaches fact -> R2 -> R4 (handout 10.4)
        self.assertEqual(r["proof"], ["Teaches(DrKhan, AI)", rule_line("R2"), rule_line("R4")])
        self.assertEqual(r["explanation"],
                         "DrKhan teaches AI, therefore DrKhan is an instructor of AI and can use Lab1.")
        self.assertIsNone(r["error"])
        self.assertIsNone(r["rejected_at"])

    def test_student_uses_lab(self):
        r = ask("UsesLab(Ali, Lab1)", "Ali")
        self.assertTrue(r["allowed"] and r["entailed"])
        self.assertEqual(r["proof"], ["Enrolled(Ali, AI)", rule_line("R3")])

    def test_eligible_ali(self):
        r = ask("Eligible(Ali, AI)", "Ali")
        self.assertTrue(r["allowed"] and r["entailed"])
        self.assertEqual(r["proof"], ["Student(Ali)", "Completed(Ali, ProgrammingFundamentals)",
                                      rule_line("R1")])
        self.assertIn("Ali is a student and completed ProgrammingFundamentals", r["explanation"])

    def test_eligible_sara_false_names_missing_premise(self):
        r = ask("Eligible(Sara, AI)", "Sara")
        self.assertFalse(r["allowed"])
        self.assertFalse(r["entailed"])
        self.assertIn("Completed(Sara, ProgrammingFundamentals)", r["explanation"])
        self.assertEqual(r["missing"], ["Completed(Sara, ProgrammingFundamentals)"])
        self.assertIn("closed-world", r["explanation"])
        self.assertEqual(r["proof"], [])
        self.assertIsNone(r["error"])                 # a false answer is not an error

    def test_variable_query(self):
        r = ask("UsesLab(x, Lab1)")
        self.assertTrue(r["entailed"])
        self.assertEqual({a["x"] for a in r["answers"]}, {"DrKhan", "Ali", "Ahmed"})
        for who in ["DrKhan", "Ali", "Ahmed"]:
            self.assertIn("x = " + who, r["explanation"])
        self.assertNotIn("Sara", r["explanation"])
        self.assertIn("Teaches(DrKhan, AI)", r["proof"])
        self.assertIn("Enrolled(Ahmed, AI)", r["proof"])

    def test_variable_query_without_answers(self):
        r = ask("Teaches(x, Lab1)")
        self.assertFalse(r["entailed"])
        self.assertEqual(r["answers"], [])

    def test_known_fact_query(self):
        r = ask("Student(Ali)")
        self.assertTrue(r["entailed"])
        self.assertEqual(r["proof"], ["Student(Ali)"])
        self.assertIn("known fact", r["explanation"])

    def test_missing_premise_through_rule_chain(self):
        r = ask("UsesLab(Sara, Lab1)")
        self.assertFalse(r["entailed"])
        self.assertIn("Enrolled(Sara, AI)", r["missing"])
        self.assertIn("Teaches(Sara, AI)", r["missing"])

    def test_malformed_query_handled_cleanly(self):
        r = ask("UsesLab(DrKhan")
        self.assertFalse(r["allowed"])
        self.assertFalse(r["entailed"])
        self.assertEqual(r["rejected_at"], "input")
        self.assertIn("closing parenthesis", r["error"])
        self.assertEqual(r["explanation"], r["error"])

    def test_missing_query_field(self):
        r = kb.check_logic({"name": "Ali", "role": "student", "request_type": "Eligibility_Check"})
        self.assertFalse(r["allowed"])
        self.assertTrue(r["error"])

    def test_unknown_predicate(self):
        r = ask("UseLab(Ali, Lab1)")
        self.assertTrue(r["error"])
        self.assertIn("Unknown predicate", r["error"])


class TestServiceRequests(unittest.TestCase):
    """Booking / Urgent / Full service: role authorization, then permission."""

    def test_ali_allowed_ai_lab_support(self):
        r = service("Ali", "student", "AI_Lab_Support")
        self.assertTrue(r["allowed"] and r["entailed"])
        self.assertEqual(r["query"], "CanRequest(Ali, AI_Lab_Support)")
        self.assertIn("Student(Ali)", r["proof"])
        self.assertIn(rule_line("R8"), r["proof"])
        self.assertIsNone(r["rejected_at"])
        self.assertIn("Step 1", r["explanation"])
        self.assertIn("Step 2", r["explanation"])

    def test_sara_rejected_ai_lab_support(self):
        r = service("Sara", "student", "AI_Lab_Support")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["rejected_at"], "permission")          # role step passed
        self.assertIn("Completed(Sara, ProgrammingFundamentals)", r["explanation"])
        self.assertIn("Completed(Sara, ProgrammingFundamentals)", r["missing"])
        self.assertIn("Student(Sara)", r["proof"])                # authorization proof kept

    def test_sara_claiming_instructor_rejected_at_authorization(self):
        r = service("Sara", "instructor", "AI_Lab_Support")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["rejected_at"], "authorization")
        self.assertIn("Faculty(Sara)", r["explanation"])
        self.assertIn("registered as student", r["explanation"])

    def test_unknown_person_rejected(self):
        for role in ["student", "instructor", "staff"]:
            r = service("Zed", role, "Emergency_Help")
            self.assertFalse(r["allowed"], role)
            self.assertEqual(r["rejected_at"], "authorization")
            self.assertIn("not a known person", r["explanation"])

    def test_lowercase_name_is_rejected_not_treated_as_variable(self):
        """A lowercase name would unify with anyone if it slipped through."""
        r = service("ali", "student", "Maintenance")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["rejected_at"], "input")
        self.assertTrue(r["error"])

    def test_invalid_role_and_category(self):
        self.assertEqual(service("Ali", "janitor", "Maintenance")["rejected_at"], "input")
        self.assertEqual(service("Ali", "student", "Pizza")["rejected_at"], "input")
        self.assertEqual(service("", "student", "Maintenance")["rejected_at"], "input")

    def test_instructor_permissions(self):
        self.assertTrue(service("DrKhan", "instructor", "AI_Lab_Support")["allowed"])      # R9
        self.assertFalse(service("DrAmna", "instructor", "AI_Lab_Support")["allowed"])
        self.assertTrue(service("DrAmna", "instructor", "Access_Request")["allowed"])      # R13

    def test_student_permissions(self):
        self.assertTrue(service("Ali", "student", "Access_Request")["allowed"])            # R12
        r = service("Sara", "student", "Access_Request")                                  # no ID card
        self.assertFalse(r["allowed"])
        self.assertIn("HasIDCard(Sara)", r["missing"])

    def test_staff_permissions(self):
        self.assertTrue(service("Bilal", "staff", "Maintenance")["allowed"])
        self.assertTrue(service("Bilal", "staff", "Emergency_Help")["allowed"])
        self.assertFalse(service("Bilal", "staff", "AI_Lab_Support")["allowed"])
        self.assertFalse(service("Bilal", "staff", "Viva_Scheduling", group_id="G4")["allowed"])
        self.assertFalse(service("Bilal", "staff", "Access_Request")["allowed"])

    def test_everyone_may_request_maintenance_and_emergency(self):
        people = [("Sara", "student"), ("Ali", "student"), ("Ahmed", "student"),
                  ("DrKhan", "instructor"), ("DrAmna", "instructor"), ("Bilal", "staff")]
        for who, role in people:
            for category in ["Maintenance", "Emergency_Help"]:
                self.assertTrue(service(who, role, category)["allowed"], (who, category))

    def test_all_service_request_types_work(self):
        for rt in kb.SERVICE_TYPES:
            self.assertTrue(service("Ali", "student", "AI_Lab_Support", rt)["allowed"], rt)
            self.assertFalse(service("Sara", "student", "AI_Lab_Support", rt)["allowed"], rt)

    def test_input_is_normalised(self):
        r = kb.check_logic({"name": " Ali ", "role": "Student", "request_type": "booking_or_scheduling",
                            "category": "ai_lab_support"})
        self.assertTrue(r["allowed"])
        self.assertEqual(r["query"], "CanRequest(Ali, AI_Lab_Support)")


class TestVivaGroupPermission(unittest.TestCase):
    """Viva_Scheduling is group-specific: CanScheduleViva(name, group_id) (R10 / R11)."""

    def test_ali_allowed_for_his_own_group(self):
        r = service("Ali", "student", "Viva_Scheduling", group_id="G3")
        self.assertTrue(r["allowed"] and r["entailed"])
        self.assertEqual(r["query"], "CanScheduleViva(Ali, G3)")
        self.assertEqual(r["proof"], ["Student(Ali)", "MemberOf(Ali, G3)", "FYPGroup(G3)",
                                      rule_line("R10")])
        self.assertIsNone(r["rejected_at"])

    def test_ali_rejected_for_another_group(self):
        r = service("Ali", "student", "Viva_Scheduling", group_id="G4")
        self.assertFalse(r["allowed"])
        self.assertFalse(r["entailed"])
        self.assertEqual(r["rejected_at"], "permission")          # role check passed
        self.assertIn("Ali is neither a member nor the supervisor of G4", r["explanation"])
        self.assertIn("MemberOf(Ali, G4)", r["missing"])
        self.assertIn("Supervises(Ali, G4)", r["missing"])

    def test_ahmed_allowed_for_g4(self):
        r = service("Ahmed", "student", "Viva_Scheduling", group_id="G4")
        self.assertTrue(r["allowed"])
        self.assertIn(rule_line("R10"), r["proof"])

    def test_supervisor_allowed_for_g4(self):
        r = service("DrKhan", "instructor", "Viva_Scheduling", group_id="G4")
        self.assertTrue(r["allowed"])
        self.assertEqual(r["query"], "CanScheduleViva(DrKhan, G4)")
        self.assertIn("Supervises(DrKhan, G4)", r["proof"])
        self.assertIn(rule_line("R11"), r["proof"])

    def test_supervisor_rejected_for_other_group(self):
        self.assertFalse(service("DrKhan", "instructor", "Viva_Scheduling", group_id="G3")["allowed"])
        self.assertFalse(service("DrAmna", "instructor", "Viva_Scheduling", group_id="G4")["allowed"])

    def test_group_id_required(self):
        for missing in ["", None, "   ", 4]:
            r = service("Ali", "student", "Viva_Scheduling", group_id=missing)
            self.assertFalse(r["allowed"], missing)
            self.assertEqual(r["rejected_at"], "input", missing)
            self.assertIn("group_id", r["error"])
        r = kb.check_logic({"name": "Ali", "role": "student",
                            "request_type": "Booking_or_Scheduling", "category": "Viva_Scheduling"})
        self.assertEqual(r["rejected_at"], "input")            # key absent entirely

    def test_bad_or_unknown_group(self):
        r = service("Ali", "student", "Viva_Scheduling", group_id="g3")   # lowercase = variable-like
        self.assertEqual(r["rejected_at"], "input")
        r = service("Ali", "student", "Viva_Scheduling", group_id="G9")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["rejected_at"], "permission")
        self.assertIn("G9 is not a known FYP group", r["explanation"])

    def test_role_still_checked_first(self):
        r = service("Sara", "instructor", "Viva_Scheduling", group_id="G4")
        self.assertEqual(r["rejected_at"], "authorization")

    def test_no_member_or_supervisor_means_no_viva(self):
        r = service("Sara", "student", "Viva_Scheduling", group_id="G3")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["rejected_at"], "permission")

    def test_group_id_ignored_for_other_categories(self):
        self.assertTrue(service("Ali", "student", "Maintenance", group_id="G4")["allowed"])
        self.assertTrue(service("Ali", "student", "Maintenance")["allowed"])

    def test_viva_is_no_longer_a_plain_can_request(self):
        self.assertEqual(kb.backward_chain(("CanRequest", "Ali", "Viva_Scheduling")), [])
        got = {(a["bindings"]["x"], a["bindings"]["g"])
               for a in kb.backward_chain(("CanScheduleViva", "x", "g"))}
        self.assertEqual(got, {("Ali", "G3"), ("Ahmed", "G4"), ("DrKhan", "G4")})


class TestNeverRaises(unittest.TestCase):
    """check_logic always returns a dict with the template fields."""

    FIELDS = ["allowed", "entailed", "explanation", "query", "proof"]

    def test_odd_inputs(self):
        for bad in [None, 42, "text", [], {}, {"request_type": None}, {"request_type": 5},
                    {"request_type": "Navigation_Only"}, {"request_type": "Nonsense"},
                    {"request_type": "Booking_or_Scheduling"},
                    {"request_type": "Booking_or_Scheduling", "name": 5, "role": 5, "category": 5},
                    {"request_type": "Eligibility_Check", "query": 7}]:
            r = kb.check_logic(bad)
            self.assertIsInstance(r, dict, bad)
            for field in self.FIELDS:
                self.assertIn(field, r, (bad, field))
            self.assertFalse(r["allowed"], bad)
            self.assertTrue(r["explanation"], bad)

    def test_template_fields_on_success(self):
        r = ask("UsesLab(Ali, Lab1)")
        for field in self.FIELDS:
            self.assertIn(field, r)
        self.assertIsInstance(r["proof"], list)

    def test_result_is_independent_of_the_template(self):
        r = ask("UsesLab(Ali, Lab1)")
        r["proof"].append("junk")
        self.assertEqual(ask("UsesLab(Ali, Lab1)")["proof"], ["Enrolled(Ali, AI)", rule_line("R3")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
