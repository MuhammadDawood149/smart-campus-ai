# Smart Campus AI Decision Support and Automation System

AL2002 AI Lab project, Fall 2026, section BSE-5A1.

A campus help desk that takes one structured request and decides what to do with it.
After preprocessing checks and normalises the input, a router sends the request only to
the AI modules it needs. An **ANN** predicts the priority, a **Logic / knowledge base**
module checks eligibility and permission, a **CSP scheduler** assigns a room and time
slot, and a **Search** module finds the best route on the campus map. The final response
uses the handout's standard format. The main interface is a structured CLI form. A web
UI is included as an extra interface, and it calls the same Python modules.

## Team

| Student | Roll number | Name | Part | Folder |
|---|---|---|---|---|
| Student 1 | 24F-3054 | Muhammad Dawood | Search & Navigation | `student1_search/` |
| Student 2 | 24F-3070 | Ibrahim Asif | Logic / KB + CSP Scheduler | `student2_logic_csp/` |
| Student 3 | 24F-3001 | Haroon Afzal | ANN (Perceptron + MLP) | `student3_ann/` |

The integration layer (`integration/`, `main.py`, `cli.py`, `server.py`, `web/`) is joint work.

## Requirements and setup

Python 3 with two libraries: `numpy` and `flask` (only `server.py` uses Flask).

```bash
python -m venv venv
venv\Scripts\activate            # Windows
source venv/bin/activate         # Linux / macOS
pip install -r requirements.txt
```

## How to run

| What | Command |
|---|---|
| Web UI (opens http://127.0.0.1:5000) | `python server.py` (options: `--port 8000`, `--no-browser`) |
| Structured CLI form (main interface) | `python cli.py` |
| CLI demo scenarios (9 scenarios, then exit) | `python cli.py --demo` |
| Student 1 demo: Search & Navigation | `python student1_search/search_cli.py` |
| Student 2 demo: Logic / KB + CSP | `python student2_logic_csp/logic_csp_cli.py` |
| Student 3 demo: ANN | `python student3_ann/ann_cli.py` |
| All tests (175 tests in 5 files) | `python run_all_tests.py` |
| Web UI end-to-end test (optional, ~6 min) | `python tests_ui/test_ui.py` (`--shots` also saves the report screenshots) |

The UI test is separate from `run_all_tests.py` because it needs a browser. It needs:
`pip install playwright` and `python -m playwright install`. Playwright is not in
`requirements.txt` because the project itself does not use it. If Playwright's browsers
are not installed, the test uses the installed Microsoft Edge (or pass `--channel chrome`).

## Folder structure

```
shared/              data formats + verified diagram data (no AI logic)
student1_search/     Search & Navigation           (Student 1)
student2_logic_csp/  Logic / KB + CSP Scheduler    (Student 2)
student3_ann/        Perceptron + MLP              (Student 3)
integration/         preprocessing, router, final response, demo scenarios (joint)
tests_ui/            end-to-end test of the web UI (Playwright, optional)
main.py              process_request(request) -> final response dict
cli.py               structured CLI form
server.py            Flask server for the web UI (no AI logic)
web/                 single-page web UI (index.html, app.js, api.js, styles.css)
run_all_tests.py     runs every test file
docs/                handout, screenshots, report
```

Student folders import only from `shared/`, never from each other. Only `integration/` and
`main.py` connect the modules. The AI modules never print or read input: each one takes a
dict and returns a dict.

## Request types and the modules they use

| Request type | Modules (in order) |
|---|---|
| `Navigation_Only` | Search |
| `Eligibility_Check` | Logic / KB |
| `Booking_or_Scheduling` | Logic / KB → CSP → Search (Search only if a current location is given) |
| `Urgent_Service_Request` | ANN → Logic / KB → CSP → Search (Search only if a current location is given) |
| `Full_Service_Request` | ANN → Logic / KB → CSP → Search |

Every request passes through preprocessing first and ends with the final response. When a
stage rejects the request, the response names that stage in `rejected_at`
(`preprocessing`, `logic` or `csp`) and gives the reason.

## Handout example (Full_Service_Request, Phase 3 section 11)

Input: Ali, student, Full_Service_Request, AI_Lab_Support, current location Hostel,
preferred slot 2, severity 8, time sensitivity 9, crowd level 5, eligible.

Expected result (from `python cli.py --demo`, scenario 6):

```json
{
  "request_id": "REQ106",
  "decision": "accepted",
  "priority": {"binary_priority": "urgent", "final_priority": "high", "confidence": 0.59},
  "eligibility": {"allowed": true},
  "assignment": {"room": "AI_Lab", "slot": 3},
  "route": {"algorithm": "A*", "path": ["Hostel", "Cafeteria", "Science_Block", "AI_Lab"],
            "cost": 6, "steps": 3},
  "message": "Your request has been accepted. You are assigned AI_Lab in slot 3. Please follow the recommended route."
}
```

Slot 2 of AI_Lab is already booked at the start, so the CSP assigns the next free slot (3).
The route distance (6) is passed to the ANN as feature x6.

## Team-defined assumptions

The handout leaves some details open. The team's choices are documented in `CLAUDE.md`:

- Rules R5–R15 and the extra facts (Faculty, Staff, MemberOf, Supervises, HasIDCard, ...)
  are team-defined, so every request category has a rule that can prove permission. R1–R4
  and the diagram facts come from the handout.
- `Lab1` in the knowledge base is the `AI_Lab` node on the map.
- The heuristic is `h(n) = k · euclid(n, goal)` with `k = 1/3`. Raw Euclidean distance
  overestimates on 12 of the 19 edges, so it is not admissible.
- The room/slot booking CSP, its priority deadlines (Urgent ≤ 2, High ≤ 3, otherwise ≤ 4)
  and the initial bookings (AI_Lab 2, Exam_Hall 1, Admin_Block 1) are team-defined.
- The ANN dataset (1500 samples, seed 42) and its labelling rule are team-defined.
- The CLI wording `Viva` / `Access` is normalised to `Viva_Scheduling` / `Access_Request`.

See `CLAUDE.md` for the full list and for the verified diagram data.
