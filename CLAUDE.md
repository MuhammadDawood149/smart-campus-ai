# Smart Campus AI Decision Support and Automation System

AL2002 AI Lab project, Fall 2026. Group: 24F-3054, 24F-3070, 24F-3001.
One person builds the code, but it is split into three student-owned parts that each run and are explained on their own in the viva, plus a shared integration layer.

## Goals
- Simple and easy to explain in a viva, but complete: every handout requirement must work end to end.
- Main interface = structured CLI form (handout requirement). A CustomTkinter GUI is added later as an extra.
- Python 3, venv in `venv/`. Allowed libraries: `numpy`, `customtkinter` only (see requirements.txt). Search, Logic and CSP use pure Python.

## Folder rules (do not break)
```
shared/              data formats + verified diagram data only, no AI logic
student1_search/     Search & Navigation (Student 1)
student2_logic_csp/  Logic/KB + CSP Scheduler (Student 2)
student3_ann/        Perceptron + MLP (Student 3)
integration/         preprocessing, router, final_response (joint)
main.py              process_request(request) -> final response dict
cli.py               structured CLI form (later: gui.py)
```
1. Student folders import ONLY from `shared/`, never from each other.
2. Only `integration/` and `main.py` connect modules (e.g. integration gets Distance from Search and passes it to the ANN).
3. AI modules never call `print()` or `input()`. They take a dict and return a dict. Only `cli.py` / `gui.py` do input/output, so the GUI can be added without changing any module.
4. Each student folder has its own `*_cli.py` demo and a `test_*.py` file.
5. Every function (including methods and inner helpers) starts with a comment block / docstring: Function, Purpose, Params, Returns. Each file starts with a header naming the file, module and owning student.
6. Use the exact names from the handout everywhere. Prefer plain functions and dicts; classes only where they clearly help. No clever tricks.

## Verified diagram data (checked pixel by pixel - do NOT change)

### Campus graph: 13 nodes, 19 undirected edges, degree sum 38, total cost 44
The unweighted and weighted diagrams have the SAME 19 connections. There is NO Science_Block-Library edge.
Coordinates: Main_Gate(0,4) Parking(2,4) Admin_Block(3,5) Student_Services(6,5) Exam_Hall(8,5) Seminar_Room(10,4) Library(6,2) AI_Lab(9,2) Bus_Stop(0,1) Medical_Center(1,1) Cafeteria(4,1) Science_Block(7,1) Hostel(2,0)
Edges (cost): Main_Gate-Bus_Stop 1, Main_Gate-Parking 2, Main_Gate-Admin_Block 4, Main_Gate-Hostel 5, Parking-Bus_Stop 2, Parking-Science_Block 3, Admin_Block-Student_Services 1, Admin_Block-Exam_Hall 2, Student_Services-Library 2, Exam_Hall-Seminar_Room 1, Exam_Hall-Science_Block 3, Seminar_Room-Science_Block 2, Library-Cafeteria 2, Library-AI_Lab 3, AI_Lab-Science_Block 1, Bus_Stop-Medical_Center 2, Medical_Center-Hostel 3, Hostel-Cafeteria 2, Cafeteria-Science_Block 3
Degrees: Science_Block 5, Main_Gate 4, Library/Parking/Admin_Block/Exam_Hall/Bus_Stop/Cafeteria/Hostel 3, Student_Services/Seminar_Room/AI_Lab/Medical_Center 2.

Search policy: unweighted -> BFS; weighted + heuristic -> A* (default); weighted, no heuristic -> UCS.
Comparison/demo mode also: DFS, DLS, IDS, Bidirectional BFS, Greedy Best-First, RBFS.
Heuristic: raw Euclidean distance OVERESTIMATES on 12 of 19 edges and gives wrong A* routes for 13 pairs.
Use h(n) = k * euclid(n, goal) with k = min(edge_cost / euclid) over all edges = 1/3 (admissible + consistent). Explain this in comments.
Acceptance check: A* Hostel -> AI_Lab = Hostel, Cafeteria, Science_Block, AI_Lab, cost 6, steps 3.

### CSP (viva scheduling): variables G1..G6, domain slots {1,2,3,4}
Not-equal: G1-G2, G1-G4, G1-G3 (examiner clash), G2-G4, G2-G5 (supervisor clash), G3-G5, G3-G6, G5-G6.
Precedence: G4 < G3 (strictly earlier).
Solver: backtracking + MRV (+ degree heuristic tie-break) + LCV + forward checking.
Acceptance check (brute force): 120 valid timetables with 4 slots, 6 with 3 slots, 0 with 2 slots. NOT 96.

### FOL knowledge base
Facts: Teaches(DrKhan, AI), Enrolled(Ali, AI), Student(Sara), Student(Ali), Completed(Ali, ProgrammingFundamentals)
R1: Student(x) & Completed(x, ProgrammingFundamentals) => Eligible(x, AI)
R2: Teaches(x, AI) => Instructor(x, AI)
R3: Enrolled(x, AI) => UsesLab(x, Lab1)
R4: Instructor(x, AI) => UsesLab(x, Lab1)
Derived: Instructor(DrKhan, AI), UsesLab(DrKhan, Lab1), UsesLab(Ali, Lab1), Eligible(Ali, AI). Sara is NOT eligible.
Lab1 is treated as the AI_Lab node on the map (assumption - document it).
Inference: forward chaining + backward chaining with a readable explanation of why a query is / is not entailed.

### Team-defined extensions (assumption)
Not in the handout diagram; added by the team so every request category has a provable permission rule. Implemented in `student2_logic_csp/logic_kb.py`. Keep clearly separate from R1-R4 and the diagram facts in the report/viva.
Extra facts: Faculty(DrKhan), Faculty(DrAmna), Staff(Bilal), Student(Ahmed), Enrolled(Ahmed, AI), Completed(Ahmed, ProgrammingFundamentals), FYPGroup(G1)...FYPGroup(G6), MemberOf(Ahmed, G4), MemberOf(Ali, G3), Supervises(DrKhan, G4), HasIDCard(Ali), HasIDCard(Ahmed)
R5: Student(x) => Person(x)
R6: Faculty(x) => Person(x)
R7: Staff(x) => Person(x)
R8: Eligible(x, AI) & UsesLab(x, Lab1) => CanRequest(x, AI_Lab_Support)
R9: Instructor(x, AI) => CanRequest(x, AI_Lab_Support)
R10: MemberOf(x, g) & FYPGroup(g) => CanScheduleViva(x, g)
R11: Supervises(x, g) & FYPGroup(g) => CanScheduleViva(x, g)
R12: Student(x) & HasIDCard(x) => CanRequest(x, Access_Request)
R13: Faculty(x) => CanRequest(x, Access_Request)
R14: Person(x) => CanRequest(x, Maintenance)
R15: Person(x) => CanRequest(x, Emergency_Help)
Notation: atoms are tuples like ("UsesLab", "DrKhan", "Lab1"); variables are lowercase single letters (x, g); constants start with a capital.
Logic entry point `check_logic(request)`: Eligibility_Check parses `query`; Booking / Urgent / Full service do (1) role authorization (student -> Student(name), instructor -> Faculty(name), staff -> Staff(name)), then (2) prove CanRequest(name, category). Viva_Scheduling is group-specific: `group_id` is required (missing/invalid -> rejected_at "input") and step 2 proves CanScheduleViva(name, group_id) instead (R10/R11), so a member or supervisor of G4 cannot schedule G3's viva. Closed world: unprovable = false, with the missing premise named.

#### CSP scheduler design (Student 2, `student2_logic_csp/csp_scheduler.py`; assumption)
The handout diagram only gives the viva timetable CSP. The room/slot booking CSP, deadlines and initial bookings below are team-defined. Imports only from `shared/`, never prints, never raises.
1. Generic solver `solve_csp(variables, domains, constraints, value_first=None, var_order=None)` -> `(solution or None, stats)`. A constraint is `(scope, test)`: a tuple of variable names and a function of their values. Backtracking search with MRV (degree heuristic breaks ties), LCV value ordering (stable: fewest values removed from neighbours first) and forward checking. `stats = {"assignments": tried, "backtracks": undone}`. `value_first` = values tried before the LCV order (this is how preferences work); `var_order` = variables to assign first, in that order, before MRV takes over (used by the booking CSP: slot before room; and by the viva CSP: the group with a preferred slot goes first, otherwise MRV could give its slot to another group before the preference is tried).
2. Viva CSP: G1..G6, domain {1,2,3,4}, the 8 not-equal constraints and G4 < G3 (see above). `solve_viva(preferred=None)` returns one timetable `{group: slot}`; `preferred={"G4": 2}` tries slot 2 first for G4, then later slots ascending, then earlier slots descending. It is a value order, not a constraint, so an impossible preference is simply skipped.
3. Booking CSP: variables `slot`, `room`. Constraints: room serves the category (`CATEGORY_ROOMS`: AI_Lab_Support [AI_Lab]; Viva_Scheduling [Exam_Hall, Seminar_Room]; Access_Request [Admin_Block]; Maintenance [Student_Services]; Emergency_Help [Medical_Center]); (room, slot) not already booked; slot <= deadline (priority Urgent 2, High 3, Normal/Low/None 4). Slot value order: preferred slot, then later slots ascending, then earlier slots descending (no preference = ascending). Variables are searched slot first so the slot preference wins over the room order.
4. State: a dict `STATE = {"bookings": {(room, slot)}, "viva": {group: (room, slot)}}`, so a second request sees the first. Initial bookings (AI_Lab, 2), (Exam_Hall, 1), (Admin_Block, 1). `reset()` restores it. A booking is committed only when the request is accepted.
5. Entry point `schedule(request, priority=None)`; `priority` is the ANN `final_priority` string (case-insensitive; an unknown string is rejected). Returns the CSP_OUTPUT_TEMPLATE fields (decision "accepted"/"rejected", assigned_room, assigned_slot, destination = room, notes) plus `stats` and `timetable`. Invalid category or a preferred_slot outside 1-4 is a clean rejection with the reason in notes.
6. Viva_Scheduling in `schedule`: `group_id` (G1..G6) is required. The whole G1..G6 timetable is solved with this group's domain limited to slots that meet the deadline and have a free room; groups that already booked keep their slot (so G4 < G3 holds across requests); room = first free of Exam_Hall / Seminar_Room in the group's slot. Booking the same group again replaces its earlier viva booking.

#### ANN design (Student 3, `student3_ann/`; assumption)
The handout gives no training data, so the dataset and its labelling rule below are team-defined. numpy only, no sklearn. Imports only from `shared/`, never prints, never raises.
1. DATASET (`dataset.py`): 1500 samples generated with numpy, fixed seed 42. Features in FEATURE_ORDER: role 0-2, request type 0-4, severity/time/crowd 1-10, distance 0-15, eligibility 0/1.
   `score = 0.4*severity + 0.4*time + 0.1*crowd + 0.1*min(distance, 10) + (2 if type == Emergency_Help) + (-1 if eligibility == 0)`.
   Small Gaussian noise (std 0.3) is added to the score before labelling. Class: score < 4 low, < 6 normal, < 8 high, else urgent (labels 0..3). Binary: 1 (urgent) if class is high or urgent, else 0. 80/20 train/test split, seed 42. Features are scaled by dividing by `FEATURE_MAX = [2, 4, 10, 10, 10, 15, 1]`.
2. PERCEPTRON (`perceptron.py`): 7 weights + bias, step activation, perceptron learning rule, learning rate 0.1, 50 epochs. Comments explain weighted sum, activation and decision boundary.
3. MLP (`mlp.py`): 7 -> 4 -> 3 -> 4 exactly as the diagram, sigmoid hidden layers, softmax output, cross-entropy loss, backpropagation written out step by step, full-batch gradient descent, fixed seed. Loss recorded per epoch. Confidence = highest softmax probability.
4. TRAINING + EVALUATION (`train.py`): trains both, reports test accuracy, confusion matrices (4x4 MLP, 2x2 Perceptron) and a Perceptron-vs-MLP comparison (MLP classes collapsed to binary to compare like for like). MLP accuracy is shown next to the noise ceiling (accuracy of the noise-free labelling formula on the noisy test labels), e.g. "MLP 85.67% vs ceiling 87.33%". Weights saved to `student3_ann/weights.json` (MLP loss stored only every 100 epochs to keep the file small); loaded if present instead of retraining.
5. Entry point `predict_priority(features)` (`ann_module.py`): features = raw (unscaled) list of 7 numbers in FEATURE_ORDER. Returns PRIORITY_OUTPUT_TEMPLATE with lowercase values like the handout: binary_priority "urgent"/"not_urgent" (Perceptron), final_priority "low"/"normal"/"high"/"urgent" (MLP), confidence rounded to 2 decimals. Wrong length / non-numeric input returns a clean `error` field instead of raising.
6. Acceptance: handout example `[0, 0, 8, 9, 5, 4, 1]` (score 7.7) -> final "high", binary "urgent"; MLP test accuracy >= noise ceiling - 3 points; Perceptron binary test accuracy >= 80%.

### ANN
Feature order (fixed): x1 Role, x2 RequestType, x3 Severity, x4 TimeSensitivity, x5 CrowdLevel, x6 Distance, x7 Eligibility.
Perceptron: 7 inputs + bias -> step activation -> Urgent {0,1} (binary baseline).
MLP: 7 -> 4 -> 3 -> 4 (Low, Normal, High, Urgent), biases on each layer, implemented with numpy (no sklearn for the model).
Encodings: role student 0 / instructor 1 / staff 2; category AI_Lab_Support 0, Viva_Scheduling 1, Access_Request 2, Maintenance 3, Emergency_Help 4.

## Known handout inconsistencies (resolved choices)
- CLI prompt says Viva/Access; encoding says Viva_Scheduling/Access_Request. Normalise user input to the encoding names. Emergency_Help is a valid category.
- Report: handout says Word in one place and PDF in another -> make a Word report and also export a PDF.
- Submission: 24F-3054_24F-3070_24F-3001_Project.zip without the venv folder.

## Preprocessing must normalise (before any module runs)
Logic is deliberately strict about names and groups: a lowercase term would be read as a variable and could match anyone, so Logic rejects it at `rejected_at = "input"` instead of guessing. `integration/` preprocessing therefore normalises these fields first:
- Person names: capitalised exactly as in the KB (ali -> Ali, drkhan -> DrKhan); one word, starts with a capital.
- `group_id`: uppercase (g3 -> G3). An unknown but well-formed group (G9) is NOT a preprocessing error: Logic rejects it at "permission" because that is KB knowledge.
- `category`, `role`, `request_type`: canonical names (AI_Lab_Support, Viva_Scheduling, Access_Request, Maintenance, Emergency_Help; student / instructor / staff; Eligibility_Check, Booking_or_Scheduling, Urgent_Service_Request, Full_Service_Request). Map the CLI wording (Viva/Access) to the encoding names. Logic also tolerates case differences here, but do not rely on it.
- Locations (`current_location`, `destination`): via Search's `normalize_location`.

## Working style
- Build one part at a time; after each part, run its tests and the acceptance checks above.
- Never invent nodes, edges, rules or constraints; if something is not in this file or the handout, ask.


## Source documents
The handout PDFs are in docs/. Templates are in Student_Project_Handout.pdf section 12 ("Standard Python Data Structures"); worked examples are in its Phase 3 sections 9-11.