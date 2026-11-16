"""
File    : integration/demo_scenarios.py
Module  : Demo scenarios (integration layer)
Owner   : Joint (Students 1, 2 and 3)

Purpose : The raw requests shown by "Run demo scenarios" in cli.py and checked
          end to end by test_integration.py: one per request type, the handout
          full-service example (Phase 3 section 11), and rejections at Logic and
          at preprocessing. Some fields are typed the way a user would type them
          (lowercase, "Viva", "g4") to show preprocessing normalising them.
          Each scenario is meant to run from the initial bookings
          (main.reset_system before it), so its result does not depend on order.

Rules   : data only, no logic.
"""

DEMO_SCENARIOS = [
    {"id": "navigation",
     "title": "Navigation_Only: Hostel -> AI_Lab (handout Phase 3 section 9)",
     "request": {"name": "Ali", "role": "student", "request_type": "Navigation_Only",
                 "current_location": "hostel", "destination": "ai lab"}},
    {"id": "eligibility",
     "title": "Eligibility_Check: UsesLab(DrKhan, Lab1) (handout Phase 3 section 10)",
     "request": {"name": "DrKhan", "role": "instructor", "request_type": "Eligibility_Check",
                 "query": "UsesLab(DrKhan, Lab1)"}},
    {"id": "booking",
     "title": "Booking_or_Scheduling: Ali, AI_Lab_Support, preferred slot 2, from Hostel",
     "request": {"name": "ali", "role": "student", "request_type": "Booking_or_Scheduling",
                 "category": "AI_Lab_Support", "preferred_slot": 2,
                 "current_location": "Hostel"}},
    {"id": "viva",
     "title": "Booking_or_Scheduling: Ahmed schedules the viva for group G4, slot 2",
     "request": {"name": "Ahmed", "role": "student", "request_type": "Booking_or_Scheduling",
                 "category": "Viva", "group_id": "g4", "preferred_slot": 2}},
    {"id": "urgent",
     "title": "Urgent_Service_Request: Bilal (staff), Emergency_Help from Bus_Stop",
     "request": {"name": "Bilal", "role": "staff", "request_type": "Urgent_Service_Request",
                 "category": "Emergency", "current_location": "Bus Stop", "severity": 9,
                 "time_sensitivity": 9, "crowd_level": 6, "eligibility_claim": True,
                 "description_note": "Student fainted near the bus stop."}},
    {"id": "full_service",
     "title": "Full_Service_Request: the handout example (Phase 3 section 11)",
     "request": {"name": "Ali", "role": "student", "request_type": "Full_Service_Request",
                 "category": "AI_Lab_Support", "current_location": "Hostel",
                 "preferred_slot": 2, "severity": 8, "time_sensitivity": 9,
                 "crowd_level": 5, "eligibility_claim": True,
                 "description_note": "Need urgent help before practical evaluation."}},
    {"id": "reject_logic_sara",
     "title": "Rejected at Logic: Sara asks for AI_Lab_Support (no ProgrammingFundamentals)",
     "request": {"name": "sara", "role": "student", "request_type": "Booking_or_Scheduling",
                 "category": "AI_Lab_Support", "preferred_slot": 1}},
    {"id": "reject_logic_viva",
     "title": "Rejected at Logic: Ali tries to schedule G4's viva (Ali is in G3)",
     "request": {"name": "Ali", "role": "student", "request_type": "Booking_or_Scheduling",
                 "category": "Viva_Scheduling", "group_id": "G4", "preferred_slot": 3}},
    {"id": "reject_location",
     "title": "Rejected at preprocessing: unknown location Sports_Complex",
     "request": {"name": "Ali", "role": "student", "request_type": "Navigation_Only",
                 "current_location": "Hostel", "destination": "Sports_Complex"}},
]
