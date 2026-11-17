"""
File    : docs/report/build_report.py
Module  : Project report builder (not part of the AI system)
Owner   : Joint (Students 1, 2 and 3)

Purpose : Builds docs/report/24F-3054_24F-3070_24F-3001_Report.docx and, when
          Microsoft Word (or LibreOffice) is installed, the matching .pdf.
          Every number in the report is computed here by running the project
          code (search results, CSP counts, ANN accuracy, test counts); nothing
          is typed in by hand. Steps:
            1. run the modules and collect the facts
            2. run the CLIs and run_all_tests.py, save their output, and render
               the output as dark-terminal images (headless Microsoft Edge)
            3. write the Word document (python-docx)
            4. convert it to PDF with Word (this also fills in the table of
               contents) or with LibreOffice
Needs   : python-docx, installed in the venv only to build the report. It is
          not in requirements.txt because the project itself does not use it.
Run     : python docs/report/build_report.py
"""

import glob
import html
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date

REPORT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(REPORT_DIR))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from docx import Document                                      # noqa: E402
from docx.enum.section import WD_ORIENT                        # noqa: E402,F401
from docx.enum.table import WD_TABLE_ALIGNMENT                 # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK        # noqa: E402
from docx.image.image import Image as DocxImage                # noqa: E402
from docx.oxml import OxmlElement                              # noqa: E402
from docx.oxml.ns import qn                                    # noqa: E402
from docx.shared import Cm, Pt, RGBColor                       # noqa: E402

import main                                                    # noqa: E402
from integration.demo_scenarios import DEMO_SCENARIOS          # noqa: E402
from integration import preprocessing as pre                   # noqa: E402
from integration import router                                 # noqa: E402
from shared.campus_data import NODES, EDGES, FEATURE_ORDER, ROLE_ENCODING, CATEGORY_ENCODING  # noqa: E402
from shared import templates                                   # noqa: E402
from student1_search import search_module as sm                # noqa: E402
from student2_logic_csp import logic_kb as kb                  # noqa: E402
from student2_logic_csp import csp_scheduler as csp            # noqa: E402
from student2_logic_csp import test_logic_csp                  # noqa: E402
from student3_ann import ann_module as ann                     # noqa: E402
from student3_ann import dataset as ds                         # noqa: E402
from student3_ann import mlp, perceptron, train                # noqa: E402

NAME = "24F-3054_24F-3070_24F-3001_Report"
DOCX_PATH = os.path.join(REPORT_DIR, NAME + ".docx")
PDF_PATH = os.path.join(REPORT_DIR, NAME + ".pdf")
IMG_DIR = os.path.join(REPORT_DIR, "images")
OUT_DIR = os.path.join(REPORT_DIR, "cli_output")
SHOT_DIR = os.path.join(ROOT, "docs", "screenshots")
UI_RESULTS = os.path.join(REPORT_DIR, "ui_test_results.json")
PY = sys.executable
EDGE_PATHS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

TITLE = "Smart Campus AI Decision Support and Automation System"
SECTION = "BSE-5A1"
STUDENTS = [("Student 1", "24F-3054", "Muhammad Dawood", "Search & Navigation", "student1_search/"),
            ("Student 2", "24F-3070", "Ibrahim Asif", "Logic / KB + CSP Scheduler", "student2_logic_csp/"),
            ("Student 3", "24F-3001", "Haroon Afzal", "ANN (Perceptron + MLP)", "student3_ann/")]
HANDOUT_FACTS = ["Teaches(DrKhan, AI)", "Enrolled(Ali, AI)", "Student(Sara)", "Student(Ali)",
                 "Completed(Ali, ProgrammingFundamentals)"]
HANDOUT_RULES = ["R1", "R2", "R3", "R4"]
UI_CHANGES = [
    "web/api.js: with the server stopped, the UI showed the browser's \"Failed to fetch\". It now says \"Server not "
    "reachable. Start it with python server.py, then try again.\"",
    "web/index.html: the optional Description note is now shown for Urgent_Service_Request too, as cli.py asks for it.",
    "server.py + web/app.js: History is kept on the server (GET /api/history, cleared by a full Reset) and loaded "
    "when the page opens, so a reload keeps it.",
    "web/app.js: Clear now resets every field, including the role, to its default.",
]


# ===========================================================================
# 1. Facts from running the code
# ===========================================================================
def demo_responses():
    """
    Function: demo_responses
    Purpose : Run every demo scenario the way "cli.py --demo" does (bookings
              reset before each one, request ids keep counting).
    Params  : none
    Returns : list of (scenario, response with trace)
    """
    main.reset_system()
    out = []
    for scenario in DEMO_SCENARIOS:
        main.reset_system(clear_counter=False)
        out.append((scenario, main.process_request(scenario["request"], with_trace=True)))
    main.reset_system()
    return out


def raw_euclid_wrong_pairs():
    """
    Function: raw_euclid_wrong_pairs
    Purpose : Run the module's own A* with k = 1 (raw Euclidean heuristic) on
              every ordered pair and list the ones whose cost is higher than
              the optimal UCS cost.
    Params  : none
    Returns : list of (source, goal, A* cost with raw h, optimal cost)
    """
    k = sm.K
    wrong = []
    try:
        for a, b in itertools.permutations(NODES, 2):
            sm.K = k
            best = sm.run_algorithm("UCS", a, b)["cost"]
            sm.K = 1.0
            got = sm.run_algorithm("A*", a, b)["cost"]
            if got != best:
                wrong.append((a, b, got, best))
    finally:
        sm.K = k
    return wrong


def collect_facts():
    """
    Function: collect_facts
    Purpose : Every number and example used in the report, from the code.
    Params  : none
    Returns : dict
    """
    f = {}
    # ---- Search
    degree = {n: 0 for n in NODES}
    for a, b, _ in EDGES:
        degree[a] += 1
        degree[b] += 1
    f["degree"] = degree
    f["over_edges"] = [(a, b, c, sm.euclid(a, b)) for a, b, c in EDGES if sm.euclid(a, b) > c + 1e-9]
    f["wrong_pairs"] = raw_euclid_wrong_pairs()
    f["k"] = sm.K
    f["k_edge"] = min(EDGES, key=lambda e: e[2] / sm.euclid(e[0], e[1]))
    f["compare"] = sm.compare_algorithms("Hostel", "AI_Lab", sm.DEFAULT_DLS_LIMIT)
    f["policy"] = {}
    for label, (gtype, has_h) in [("unweighted", ("unweighted", False)),
                                  ("weighted + heuristic", ("weighted", True)),
                                  ("weighted, no heuristic", ("weighted", False))]:
        name = sm.select_algorithm(gtype, has_h)
        f["policy"][label] = sm.run_algorithm(name, "Hostel", "AI_Lab", weighted=(name != "BFS"))
    # ---- Logic
    f["forward"] = kb.forward_chain()
    queries = ["UsesLab(DrKhan, Lab1)", "UsesLab(x, Lab1)", "Eligible(Ali, AI)", "Eligible(Sara, AI)",
               "Instructor(DrKhan, AI)", "CanScheduleViva(Ahmed, G4)", "CanScheduleViva(Ali, G4)"]
    f["queries"] = [(q, kb.check_logic({"request_type": "Eligibility_Check", "query": q})) for q in queries]
    perm = [("Ali", "student", "AI_Lab_Support", ""), ("Sara", "student", "AI_Lab_Support", ""),
            ("Ali", "staff", "Maintenance", ""), ("DrKhan", "instructor", "AI_Lab_Support", ""),
            ("Ahmed", "student", "Viva_Scheduling", "G4"), ("Ali", "student", "Viva_Scheduling", "G4"),
            ("DrKhan", "instructor", "Viva_Scheduling", "G4"), ("Sara", "student", "Access_Request", ""),
            ("Bilal", "staff", "Emergency_Help", "")]
    f["permissions"] = [(p, kb.check_logic({"request_type": "Booking_or_Scheduling", "name": p[0], "role": p[1],
                                            "category": p[2], "group_id": p[3]})) for p in perm]
    # ---- CSP
    solution, stats = csp.solve_csp(*csp.viva_problem())
    f["viva"] = (solution, stats)
    f["viva_pref"] = csp.solve_viva(preferred={"G4": 2})
    f["brute"] = {n: test_logic_csp.count_solutions(n) for n in (4, 3, 2)}
    state = csp.new_state()
    f["handout_csp"] = csp.schedule({"name": "Ali", "category": "AI_Lab_Support", "preferred_slot": 2}, "high", state)
    deadline_rows = []
    for prio in ["urgent", "high", "normal", None]:
        st = csp.new_state()
        r = csp.schedule({"name": "Ali", "category": "AI_Lab_Support", "preferred_slot": 4}, prio, st)
        deadline_rows.append((prio, r))
    f["deadlines"] = deadline_rows
    st = csp.new_state()
    f["repeat"] = [csp.schedule({"name": "Ali", "category": "AI_Lab_Support", "preferred_slot": 2}, None, st)
                   for _ in range(4)]
    # ---- ANN
    X, y_class, y_binary = ds.generate_dataset()
    f["class_counts"] = [int((y_class == c).sum()) for c in range(4)]
    f["binary_counts"] = [int((y_binary == c).sum()) for c in range(2)]
    models, source = ann.load_models()
    f["models"] = models
    f["models_source"] = source
    f["eval"] = train.evaluate(models)
    f["predictions"] = [(v, ann.predict_priority(v), ann.explain_prediction(v))
                        for v in ([0, 0, 8, 9, 5, 4, 1], [0, 0, 8, 9, 5, 6, 1], [2, 4, 9, 9, 6, 2, 1], [0, 3, 2, 2, 3, 1, 1])]
    # ---- Integration
    f["demos"] = demo_responses()
    main.reset_system()
    rej = None
    for _ in range(4):
        rej = main.process_request({"name": "Ali", "role": "student", "request_type": "Booking_or_Scheduling",
                                    "category": "AI_Lab_Support", "preferred_slot": 2}, with_trace=True)
    f["csp_rejection"] = rej
    main.reset_system()
    f["router"] = {t: router.route({"request_id": "REQ", "request_type": t, "current_location": "Hostel"})
                   for t in pre.REQUEST_TYPES}
    return f


# ===========================================================================
# 2. CLI output, captured and rendered as terminal images
# ===========================================================================
BOOT = r"""
import builtins, json, runpy, sys
answers = iter(json.loads(sys.argv[1]))
def fake_input(prompt=""):
    try:
        answer = next(answers)
    except StopIteration:
        raise EOFError
    sys.stdout.write(prompt + answer + "\n")
    return answer
builtins.input = fake_input
path = sys.argv[2]
sys.argv = [path] + json.loads(sys.argv[3])
runpy.run_path(path, run_name="__main__")
"""


def run_cli(script, answers=(), args=()):
    """
    Function: run_cli
    Purpose : Run a CLI with scripted answers; each answer is echoed after its
              prompt so the captured text reads like a real terminal session.
    Params  : script (str) - path relative to the project root,
              answers (list of str), args (list of str) - command-line arguments
    Returns : str - everything the program printed
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=ROOT)
    proc = subprocess.run([PY, "-c", BOOT, json.dumps(list(answers)), script, json.dumps(list(args))],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)
    return proc.stdout + proc.stderr


def demo_block(text, number):
    """
    Function: demo_block
    Purpose : Cut one scenario out of the "cli.py --demo" output.
    Params  : text (str), number (int) - scenario number (1-9)
    Returns : str
    """
    parts = re.split(r"(?m)^=+\nDemo (\d+): ", text)
    for i in range(1, len(parts) - 1, 2):
        if int(parts[i]) == number:
            return "Demo %d: %s" % (number, parts[i + 1].rstrip("= \n"))
    return ""


def find_edge():
    """
    Function: find_edge
    Purpose : Path of Microsoft Edge (used headless to render images).
    Params  : none
    Returns : str or None
    """
    for path in EDGE_PATHS:
        if os.path.exists(path):
            return path
    return shutil.which("msedge")


def render_html(html_text, out_png, width, height):
    """
    Function: render_html
    Purpose : Screenshot an HTML page with headless Edge.
    Params  : html_text (str), out_png (str), width / height (int) - CSS pixels
    Returns : bool - True when the image was written
    """
    edge = find_edge()
    if not edge:
        return False
    page = out_png[:-4] + ".html"
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    if os.path.exists(out_png):
        os.remove(out_png)
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    "--window-size=%d,%d" % (width, height), "--screenshot=" + out_png,
                    "file:///" + page.replace("\\", "/")], capture_output=True, timeout=120)
    os.remove(page)
    return os.path.exists(out_png)


def terminal_image(text, command, out_png, width=980):
    """
    Function: terminal_image
    Purpose : Render terminal output as a dark terminal window image.
    Params  : text (str) - program output, command (str) - shown on the prompt line,
              out_png (str), width (int)
    Returns : bool
    """
    lines = text.rstrip("\n").split("\n")
    body = "(venv) PS AI-Project&gt; <b>%s</b>\n%s" % (html.escape(command), html.escape("\n".join(lines)))
    page = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#0c0f14}
.win{margin:0;border:1px solid #2b3240}
.bar{height:30px;background:#1b2130;display:flex;align-items:center;gap:7px;padding:0 12px;
     font:13px Segoe UI,Arial;color:#9aa4b8}
.bar i{width:11px;height:11px;border-radius:50%%;display:inline-block}
pre{margin:0;padding:12px 16px 16px;font:13px/18px Consolas,'Cascadia Mono',monospace;color:#d6dbe5;white-space:pre-wrap}
b{color:#7ee787;font-weight:normal}
</style></head><body><div class="win"><div class="bar"><i style="background:#ff5f57"></i>
<i style="background:#febc2e"></i><i style="background:#28c840"></i><span style="margin-left:8px">Terminal</span>
</div><pre>%s</pre></div></body></html>""" % body
    wrapped = sum(max(1, -(-len(line) // 118)) for line in lines) + 1
    return render_html(page, out_png, width, 30 + 30 + wrapped * 18 + 4)


def loss_curve_image(history, out_png):
    """
    Function: loss_curve_image
    Purpose : Draw the MLP training loss (cross-entropy per epoch) as an SVG
              line chart and render it to PNG.
    Params  : history (list of (epoch, loss)), out_png (str)
    Returns : bool
    """
    W, H, L, R, T, B = 760, 330, 60, 20, 20, 50
    epochs = [e for e, _ in history]
    losses = [v for _, v in history]
    top = max(losses) * 1.05
    x = lambda e: L + (e - epochs[0]) / (epochs[-1] - epochs[0]) * (W - L - R)
    y = lambda v: T + (1 - v / top) * (H - T - B)
    grid = "".join('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="#e3e6ec"/>'
                   '<text x="%d" y="%.1f" text-anchor="end" font-size="12" fill="#555">%.2f</text>'
                   % (L, W - R, y(top * i / 4), y(top * i / 4), L - 8, y(top * i / 4) + 4, top * i / 4) for i in range(5))
    ticks = "".join('<text x="%.1f" y="%d" text-anchor="middle" font-size="12" fill="#555">%d</text>'
                    % (x(e), H - B + 18, e) for e in range(0, epochs[-1] + 1, 4000))
    pts = " ".join("%.1f,%.1f" % (x(e), y(v)) for e, v in history)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="Segoe UI,Arial">%s%s'
           '<polyline points="%s" fill="none" stroke="#c2410c" stroke-width="2.2"/>'
           '<text x="%d" y="%d" text-anchor="middle" font-size="13" fill="#333">epoch</text>'
           '<text x="16" y="%d" font-size="13" fill="#333" transform="rotate(-90 16 %d)" text-anchor="middle">cross-entropy loss</text>'
           '<text x="%d" y="%.1f" text-anchor="end" font-size="12" fill="#c2410c">final %.4f</text></svg>'
           % (W, H, grid, ticks, pts, (L + W - R) // 2, H - 10, H // 2, H // 2, W - R, y(losses[-1]) - 8, losses[-1]))
    return render_html('<!doctype html><html><body style="margin:0;background:#fff">%s</body></html>' % svg,
                       out_png, W, H)


def capture_cli():
    """
    Function: capture_cli
    Purpose : Run run_all_tests.py, cli.py (demo + one form session) and every
              student CLI; save the text and render the terminal images.
    Params  : none
    Returns : dict {"tests": text, "images": {key: png path}}
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)
    runs = {
        "run_all_tests": ("python run_all_tests.py", "run_all_tests.py", [], []),
        "cli_demo": ("python cli.py --demo", "cli.py", [], ["--demo"]),
        "cli_form": ("python cli.py", "cli.py",
                     ["1", "Ali", "student", "5", "AI_Lab_Support", "Hostel", "2", "8", "9", "5", "y",
                      "Need urgent help before practical evaluation.", "4", "5"], []),
        "search_cli": ("python student1_search/search_cli.py", "student1_search/search_cli.py",
                       ["1", "Hostel", "AI_Lab", "3", "Hostel", "AI_Lab", "", "5"], []),
        "logic_csp_cli": ("python student2_logic_csp/logic_csp_cli.py", "student2_logic_csp/logic_csp_cli.py",
                          ["1", "Eligible(Sara, AI)", "1", "UsesLab(x, Lab1)", "5", "", "7"], []),
        "ann_cli": ("python student3_ann/ann_cli.py", "student3_ann/ann_cli.py", ["4", "2", "5"], []),
    }
    text = {}
    for key, (cmd, script, answers, args) in runs.items():
        if key == "run_all_tests":
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            proc = subprocess.run([PY, script], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
            text[key] = proc.stdout + proc.stderr
        else:
            text[key] = run_cli(script, answers, args)
        with open(os.path.join(OUT_DIR, key + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("$ %s\n%s" % (cmd, text[key]))
    main.reset_system()                         # the demo / form runs wrote to the session log only
    images = {}
    shots = {
        "cli_full_service": ("python cli.py --demo   (scenario 6 of 9)", demo_block(text["cli_demo"], 6)),
        "cli_rejection": ("python cli.py --demo   (scenario 7 of 9)", demo_block(text["cli_demo"], 7)),
        "cli_form": ("python cli.py", text["cli_form"]),
        "cli_search_compare": ("python student1_search/search_cli.py", text["search_cli"]),
        "cli_logic_csp": ("python student2_logic_csp/logic_csp_cli.py", text["logic_csp_cli"]),
        "cli_ann": ("python student3_ann/ann_cli.py", text["ann_cli"]),
        "cli_run_all_tests": ("python run_all_tests.py", text["run_all_tests"]),
    }
    for key, (cmd, out) in shots.items():
        png = os.path.join(IMG_DIR, key + ".png")
        width = 1180 if key in ("cli_search_compare", "cli_run_all_tests") else 980
        if terminal_image(out, cmd, png, width):
            images[key] = png
    return {"text": text, "images": images}


def parse_tests(text):
    """
    Function: parse_tests
    Purpose : Read the per-file summary lines of run_all_tests.py.
    Params  : text (str) - its output
    Returns : (list of (part, file, tests, result, seconds), total line)
    """
    rows = re.findall(r"(?m)^(Student \d - [\w/]+|Integration)\s+(\S+\.py)\s+(\d+) tests\s+(PASS|FAIL)\s+([\d.]+s)", text)
    total = re.search(r"(?m)^TOTAL:.*$", text)
    return rows, (total.group(0) if total else "")


def test_names(path):
    """
    Function: test_names
    Purpose : The test method names of one test file, grouped by class.
    Params  : path (str)
    Returns : list of (class name, [test names])
    """
    out, current = [], None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"class (\w+)\(unittest\.TestCase\)", line)
            if m:
                current = (m.group(1), [])
                out.append(current)
            m = re.match(r"\s+def (test_\w+)", line)
            if m and current:
                current[1].append(m.group(1)[5:].replace("_", " "))
    return out


# ===========================================================================
# 3. Word document helpers
# ===========================================================================
class Report:
    """The document plus running figure / table numbers."""

    def __init__(self):
        """
        Function: __init__
        Purpose : New A4 document with the report styles.
        Params  : none
        Returns : None
        """
        self.doc = Document()
        self.fig = 0
        self.tab = 0
        sec = self.doc.sections[0]
        sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
        for side in ("left_margin", "right_margin"):
            setattr(sec, side, Cm(2.2))
        sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(2.0)
        styles = self.doc.styles
        normal = styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.12
        for level, size in ((1, 16), (2, 13), (3, 11.5)):
            st = styles["Heading %d" % level]
            st.font.name = "Calibri"
            st.font.size = Pt(size)
            st.font.color.rgb = RGBColor(0x1F, 0x3A, 0x68)
            st.paragraph_format.space_before = Pt(14 if level == 1 else 10)
            st.paragraph_format.space_after = Pt(6)
            st.paragraph_format.keep_with_next = True
        for name, size in (("Code", 8.5), ("CodeSmall", 7)):
            st = styles.add_style(name, 1)
            st.base_style = normal
            st.font.name = "Consolas"
            st.font.size = Pt(size)
            st.paragraph_format.space_after = Pt(0)
            st.paragraph_format.space_before = Pt(0)
            st.paragraph_format.line_spacing = 1.0
            st.element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
        cap = styles["Caption"]
        cap.font.size = Pt(9.5)
        cap.font.italic = True
        cap.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        cap.paragraph_format.space_after = Pt(10)
        self.footer_page_numbers()

    def footer_page_numbers(self):
        """
        Function: footer_page_numbers
        Purpose : "Page N" centred in the footer.
        Params  : none
        Returns : None
        """
        p = self.doc.sections[0].footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run("Page ")
        self.field(p, "PAGE")

    @staticmethod
    def field(paragraph, code, placeholder="1"):
        """
        Function: field
        Purpose : Insert a Word field (PAGE, TOC, ...) into a paragraph.
        Params  : paragraph, code (str) - field code, placeholder (str) - text until updated
        Returns : None
        """
        run = paragraph.add_run()
        for kind, text in (("begin", None), (None, code), ("separate", None), (None, None), ("end", None)):
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            elif text:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = " %s " % code
            else:
                el = OxmlElement("w:t")
                el.text = placeholder
            run._r.append(el)

    def h(self, text, level=1):
        """
        Function: h
        Purpose : Add a heading.
        Params  : text (str), level (int)
        Returns : None
        """
        self.doc.add_heading(text, level)

    def p(self, text="", bold_lead=None, style=None, align=None):
        """
        Function: p
        Purpose : Add a paragraph; **bold** parts and `code` parts are formatted.
        Params  : text (str), bold_lead (str or None) - bold text before it,
                  style (str or None), align (alignment or None)
        Returns : the paragraph
        """
        para = self.doc.add_paragraph(style=style)
        if align is not None:
            para.alignment = align
        if bold_lead:
            para.add_run(bold_lead).bold = True
        for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
            if part.startswith("**") and part.endswith("**"):
                para.add_run(part[2:-2]).bold = True
            elif part.startswith("`") and part.endswith("`"):
                run = para.add_run(part[1:-1])
                run.font.name = "Consolas"
                run.font.size = Pt(9.5)
            elif part:
                para.add_run(part)
        return para

    def bullets(self, items):
        """
        Function: bullets
        Purpose : Bulleted list (items may use **bold** and `code`).
        Params  : items (list of str)
        Returns : None
        """
        for item in items:
            para = self.p(item, style="List Bullet")
            para.paragraph_format.space_after = Pt(2)

    def code(self, text, small=False, shade=True):
        """
        Function: code
        Purpose : Monospace block, one paragraph per line, light grey background.
        Params  : text (str), small (bool) - 7 pt instead of 8.5 pt, shade (bool)
        Returns : None
        """
        lines = text.replace("\r", "").replace("\t", "    ").rstrip("\n").split("\n")
        for i, line in enumerate(lines):
            para = self.doc.add_paragraph(style="CodeSmall" if small else "Code")
            para.add_run(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", line) or " ")
            if shade:
                ppr = para._p.get_or_add_pPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "F3F5F8")
                ppr.append(shd)
            if i == len(lines) - 1:
                para.paragraph_format.space_after = Pt(8)

    def caption(self, text):
        """
        Function: caption
        Purpose : Add a caption paragraph.
        Params  : text (str)
        Returns : None
        """
        para = self.doc.add_paragraph(text, style="Caption")
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def figure(self, path, text, max_w=16.4, max_h=21.5):
        """
        Function: figure
        Purpose : Picture scaled to fit the page, with a numbered caption below.
        Params  : path (str), text (str) - caption, max_w / max_h (float) - cm
        Returns : None (skipped with a note if the image is missing)
        """
        if not path or not os.path.exists(path):
            self.p("[Image missing: %s]" % text)
            return
        img = DocxImage.from_file(path)
        ratio = img.px_height / img.px_width
        width = min(max_w, max_h / ratio)
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.keep_with_next = True
        para.add_run().add_picture(path, width=Cm(width))
        self.fig += 1
        self.caption("Figure %d: %s" % (self.fig, text))

    def table(self, headers, rows, title, widths=None, size=9):
        """
        Function: table
        Purpose : Bordered table with a shaded header row (repeated on every
                  page) and a numbered caption above it.
        Params  : headers (list of str), rows (list of lists), title (str),
                  widths (list of float cm or None), size (float) - font pt
        Returns : None
        """
        self.tab += 1
        cap = self.doc.add_paragraph("Table %d: %s" % (self.tab, title), style="Caption")
        cap.paragraph_format.keep_with_next = True
        cap.paragraph_format.space_after = Pt(3)
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, text in enumerate(headers):
            cell = t.rows[0].cells[i]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(text))
            run.bold = True
            run.font.size = Pt(size)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "DCE4F0")
            cell._tc.get_or_add_tcPr().append(shd)
        trpr = t.rows[0]._tr.get_or_add_trPr()
        hdr = OxmlElement("w:tblHeader")
        hdr.set(qn("w:val"), "true")
        trpr.append(hdr)
        for row in rows:
            cells = t.add_row().cells
            for i, value in enumerate(row):
                cells[i].text = ""
                para = cells[i].paragraphs[0]
                text = str(value)
                if text.startswith("`") and text.endswith("`"):
                    run = para.add_run(text[1:-1])
                    run.font.name = "Consolas"
                    run.font.size = Pt(size - 0.5)
                else:
                    run = para.add_run(text)
                    run.font.size = Pt(size)
                    if text in ("PASS", "FAIL"):
                        run.bold = True
                        run.font.color.rgb = RGBColor(0x1A, 0x7F, 0x37) if text == "PASS" else RGBColor(0xB4, 0x23, 0x18)
        keep_together = len(rows) <= 15            # small tables never split across pages
        for n, row in enumerate(t.rows):
            cant = OxmlElement("w:cantSplit")
            row._tr.get_or_add_trPr().append(cant)
            for cell in row.cells:
                for para in cell.paragraphs:
                    para.paragraph_format.space_after = Pt(1)
                    para.paragraph_format.line_spacing = 1.0
                    if keep_together and n < len(t.rows) - 1:
                        para.paragraph_format.keep_with_next = True
        if widths:
            # fixed layout, otherwise Word autofits and ignores the widths
            t.autofit = False
            layout = OxmlElement("w:tblLayout")
            layout.set(qn("w:type"), "fixed")
            t._tbl.tblPr.append(layout)
            for i, w in enumerate(widths):
                t.columns[i].width = Cm(w)
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def page_break(self):
        """
        Function: page_break
        Purpose : Start a new page.
        Params  : none
        Returns : None
        """
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def jdump(obj):
    """
    Function: jdump
    Purpose : Pretty JSON for code blocks.
    Params  : obj
    Returns : str
    """
    text = json.dumps(obj, indent=2, default=str)
    # lists of plain values on one line: [0, 0, 8, 9, 5, 6, 1]
    return re.sub(r"\[\n\s*((?:[^\[\]{}\n]+,\n\s*)*[^\[\]{}\n]+)\n\s*\]",
                  lambda m: "[" + " ".join(x.strip() for x in m.group(1).split("\n")) + "]", text)


def shot(name):
    """
    Function: shot
    Purpose : Path of a UI screenshot in docs/screenshots/.
    Params  : name (str) - file name
    Returns : str
    """
    return os.path.join(SHOT_DIR, name)


# ===========================================================================
# 4. The report, section by section
# ===========================================================================
def title_page(r):
    """
    Function: title_page
    Purpose : Title page.
    Params  : r (Report)
    Returns : None
    """
    for _ in range(5):
        r.doc.add_paragraph()
    para = r.p("", align=WD_ALIGN_PARAGRAPH.CENTER)
    run = para.add_run(TITLE)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(24), RGBColor(0x1F, 0x3A, 0x68)
    para = r.p("", align=WD_ALIGN_PARAGRAPH.CENTER)
    run = para.add_run("Project Report")
    run.font.size = Pt(16)
    r.doc.add_paragraph()
    for line in ("AL2002 Artificial Intelligence Lab", "Fall 2026", "Section: %s" % SECTION):
        para = r.p("", align=WD_ALIGN_PARAGRAPH.CENTER)
        para.add_run(line).font.size = Pt(13)
    for _ in range(2):
        r.doc.add_paragraph()
    t = r.doc.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, text in enumerate(("Roll number", "Name", "Part")):
        t.rows[0].cells[i].text = ""
        t.rows[0].cells[i].paragraphs[0].add_run(text).bold = True
    for label, roll, name, part, _ in STUDENTS:
        cells = t.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = roll, name, "%s: %s" % (label, part)
    for row in t.rows:
        for i, w in enumerate((3.2, 6.0, 6.8)):
            row.cells[i].width = Cm(w)
    for _ in range(3):
        r.doc.add_paragraph()
    r.p("Date: %s" % date.today().strftime("%d %B %Y"), align=WD_ALIGN_PARAGRAPH.CENTER)
    r.page_break()
    r.h("Table of Contents", 1)
    r.field(r.doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u',
            "Right-click here and choose Update Field to build the table of contents.")
    r.page_break()


def sec_intro(r, f):
    """
    Function: sec_intro
    Purpose : 1. Introduction.
    Params  : r (Report), f (dict) - facts
    Returns : None
    """
    r.h("1. Introduction")
    r.p("A university campus gets many small requests every day: students ask for help in the AI lab, "
        "groups need a viva slot, staff report broken equipment and someone may need emergency help. "
        "Each request needs several decisions. How urgent is it? Is the person allowed to ask for this "
        "service? Which room and time slot are free? What is the best way to walk there? This project "
        "builds one system that makes all four decisions with four classic AI techniques and explains "
        "every decision.")
    r.h("1.1 Goals", 2)
    r.bullets([
        "Accept one structured request and send it only to the AI modules it needs.",
        "**ANN**: predict the priority of a request (Perceptron baseline and a 7-4-3-4 MLP).",
        "**Logic / knowledge base**: decide eligibility and permission with first-order rules, using forward "
        "and backward chaining, and explain why a query is or is not entailed.",
        "**CSP**: assign a conflict-free room and slot (and solve the viva timetable) with backtracking, "
        "MRV, the degree heuristic, LCV and forward checking.",
        "**Search**: find the best campus route (BFS, A* or UCS by policy) and compare 9 algorithms.",
        "Return one final response in the handout format, or reject the request at the stage that failed, "
        "with the reason.",
        "Keep each student's module independent, simple to explain in the viva and fully tested.",
    ])
    r.h("1.2 Interfaces", 2)
    r.p("The main interface is the **structured CLI form** required by the handout (`python cli.py`). It asks "
        "for the name, role and request type, and then only for the fields that request type needs. Invalid "
        "input is asked again. The CLI also has a demo mode (`python cli.py --demo`) that runs 9 scenarios, "
        "one for each request type plus the handout examples and rejections.")
    r.p("A **web UI** is included as an extra interface (`python server.py`). It is a single page served by a "
        "small Flask server. It calls the same Python modules and adds visualisations: a pipeline tracker, the "
        "campus map with search animations, the booking grid, the viva constraint graph, proof chains from the "
        "knowledge base and the neural network. The server contains no AI logic.")


def sec_architecture(r, f):
    """
    Function: sec_architecture
    Purpose : 2. System architecture.
    Params  : r (Report), f (dict)
    Returns : None
    """
    r.h("2. System architecture")
    r.h("2.1 The pipeline", 2)
    r.p("Every request follows the same path. Stages the router does not select are skipped:")
    r.code("raw request -> preprocessing -> router -> ANN -> Logic / KB -> CSP -> Search -> final response")
    r.bullets([
        "**Preprocessing** (`integration/preprocessing.py`) checks every field, normalises names, categories, "
        "groups and locations, gives the request an id (REQ101, REQ102, ...) and builds the ANN feature vector.",
        "**Router** (`integration/router.py`) chooses the pipeline from the request type.",
        "**ANN** (Student 3) predicts the priority. Its `final_priority` sets the CSP deadline.",
        "**Logic / KB** (Student 2) checks role authorization and permission. If permission fails, the "
        "request stops here.",
        "**CSP** (Student 2) assigns a room and a slot. Its room becomes the Search destination.",
        "**Search** (Student 1) finds the route from the current location to that room.",
        "**Final response** (`integration/final_response.py`) builds the handout's response dictionary.",
    ])
    r.h("2.2 Request types and their pipelines", 2)
    rows = []
    for t in pre.REQUEST_TYPES:
        out = f["router"][t]
        rows.append([t, " -> ".join(out["selected_pipeline"]),
                     ", ".join(pre.REQUIRED_FIELDS.get(t, [])) or "-",
                     ", ".join(pre.OPTIONAL_FIELDS.get(t, [])) or "-"])
    r.table(["Request type", "Pipeline (from router.route)", "Required fields", "Optional fields"], rows,
            "The five request types (pipelines produced by the router with a current location given)",
            [3.6, 4.4, 4.6, 3.8], 8.5)
    r.p("For `Booking_or_Scheduling` and `Urgent_Service_Request` the final Search step runs only when a "
        "current location is given. Without it the pipeline ends after the CSP.")
    r.h("2.3 Folder structure", 2)
    r.code("shared/              data formats + verified diagram data (no AI logic)\n"
           "student1_search/     Search & Navigation           (Student 1, 24F-3054)\n"
           "student2_logic_csp/  Logic / KB + CSP Scheduler    (Student 2, 24F-3070)\n"
           "student3_ann/        Perceptron + MLP              (Student 3, 24F-3001)\n"
           "integration/         preprocessing, router, final response, demo scenarios (joint)\n"
           "main.py              process_request(request) -> final response dict\n"
           "cli.py               structured CLI form (main interface)\n"
           "server.py            Flask server for the web UI (no AI logic)\n"
           "web/                 single-page web UI\n"
           "run_all_tests.py     runs every test file")
    r.h("2.4 Rules that keep the parts independent", 2)
    r.bullets([
        "Student folders import **only from `shared/`**, never from each other. Each part runs, is tested and "
        "can be explained on its own, and each has its own `*_cli.py` demo and `test_*.py` file.",
        "Only `integration/` and `main.py` connect the modules. For example, integration gets the route "
        "distance from Search and passes it to the ANN as feature x6.",
        "AI modules never call `print()` or `input()`. Each one takes a dict and returns a dict, so new "
        "interfaces (CLI, web) need no change to any module.",
        "Every function starts with a comment block (Function, Purpose, Params, Returns), and every file "
        "starts with a header naming the file, the module and the owning student.",
    ])


def sec_search(r, f, cli):
    """
    Function: sec_search
    Purpose : 3. Student 1 - Search & Navigation.
    Params  : r (Report), f (dict), cli (dict)
    Returns : None
    """
    r.h("3. Student 1 - Search & Navigation (Muhammad Dawood, 24F-3054)")
    r.h("3.1 Campus graph", 2)
    total = sum(c for _, _, c in EDGES)
    r.p("The campus map from the handout diagram is stored in `shared/campus_data.py`: %d nodes with (x, y) "
        "coordinates and %d undirected edges with costs (degree sum %d, total cost %d). The unweighted and the "
        "weighted diagram have the same %d connections. There is no Science_Block-Library edge."
        % (len(NODES), len(EDGES), sum(f["degree"].values()), total, len(EDGES)))
    r.table(["Node", "x", "y", "Degree"], [[n, x, y, f["degree"][n]] for n, (x, y) in NODES.items()],
            "Campus nodes", [5, 2, 2, 2.5])
    r.table(["#", "Edge", "Cost", "Euclidean length", "Raw Euclid overestimates?"],
            [[i + 1, "%s - %s" % (a, b), c, "%.2f" % sm.euclid(a, b), "yes" if sm.euclid(a, b) > c + 1e-9 else "no"]
             for i, (a, b, c) in enumerate(EDGES)],
            "Campus edges (%d edges, total cost %d)" % (len(EDGES), total), [1, 6.2, 1.5, 3.2, 4])
    r.h("3.2 The nine algorithms", 2)
    props = {
        "BFS": ("Yes", "Fewest steps (unweighted)", "Policy: unweighted graph"),
        "UCS": ("Yes", "Yes (lowest cost)", "Policy: weighted, no heuristic"),
        "A*": ("Yes", "Yes (admissible, consistent h)", "Policy: weighted + heuristic (default)"),
        "DFS": ("Yes on this finite graph (no repeated nodes)", "No", "Comparison"),
        "DLS": ("No (fails if the goal is deeper than the limit)", "No", "Comparison"),
        "IDS": ("Yes", "Fewest steps", "Comparison"),
        "Bidirectional BFS": ("Yes", "Fewest steps", "Comparison"),
        "Greedy Best-First": ("Yes on this finite graph", "No (uses h only)", "Comparison"),
        "RBFS": ("Yes", "Yes (admissible h)", "Comparison (A* with linear memory)"),
    }
    r.table(["Algorithm", "Complete", "Optimal", "Role in the system"],
            [[n] + list(props[n]) for n in sm.ALGORITHM_ORDER], "Properties of the implemented algorithms",
            [3.3, 4.6, 4.2, 4.3])
    r.p("All nine are in `student1_search/search_module.py`, written in pure Python. Every result has the "
        "same fields: `algorithm_used`, `found`, `path`, `cost`, `steps`, `nodes_expanded`, `expanded_order` "
        "and `time_ms`.")
    r.h("3.3 Search policy", 2)
    rows = [[label, res["algorithm_used"], " -> ".join(res["path"]), res["cost"], res["steps"], res["nodes_expanded"]]
            for label, res in f["policy"].items()]
    r.table(["Graph mode", "Algorithm", "Hostel -> AI_Lab path", "Cost", "Steps", "Expanded"], rows,
            "Search policy (select_algorithm) on Hostel -> AI_Lab", [3.4, 1.8, 6.4, 1.2, 1.3, 1.9], 8.5)
    r.p("On the unweighted graph BFS returns the route with the fewest steps (3). Its weighted cost would be 7. "
        "On the weighted graph A* and UCS both find the cheapest route (cost 6). A* expands fewer nodes "
        "because the heuristic guides it towards the goal.")
    r.h("3.4 The scaled heuristic", 2)
    a, b, c = f["k_edge"]
    wrong = f["wrong_pairs"]
    unordered = {tuple(sorted((x, y))) for x, y, _, _ in wrong}
    r.p("The obvious heuristic is the straight-line (Euclidean) distance to the goal. On this map it is **not "
        "admissible**: edge costs are not proportional to the drawn distances, and %d of the %d edges cost less "
        "than their straight-line length (for example Admin_Block-Exam_Hall costs 2 but is 5.00 units long). "
        "When the code runs its own A* with raw Euclidean distance (k = 1), it returns a non-optimal route for "
        "%d ordered source-goal queries, which is %d different pairs of places. Bus_Stop-Library is wrong in "
        "both directions." % (len(f["over_edges"]), len(EDGES), len(wrong), len(unordered)))
    r.p("The fix is to scale the distance: **h(n) = k · euclid(n, goal)** with k = min over all edges of "
        "cost / euclid = %.4f (= 1/3, from the edge %s-%s: cost %d, length %.0f). Then k · euclid(a, b) <= "
        "cost(a, b) on every edge. By the triangle inequality, h never overestimates the true remaining cost "
        "(admissible), and h(a) <= cost(a, b) + h(b) holds on every edge (consistent). A* with this h is "
        "optimal, and the tests check both properties for every pair." % (f["k"], a, b, c, sm.euclid(a, b)))
    r.table(["Source", "Goal", "A* cost with raw Euclid", "Optimal cost"],
            [[x, y, got, best] for x, y, got, best in wrong],
            "Queries where A* with raw Euclidean distance is not optimal", [4.4, 4.4, 4, 3])
    r.h("3.5 Comparison: Hostel -> AI_Lab", 2)
    rows = [[res["algorithm_used"] + (" (limit %d)" % sm.DEFAULT_DLS_LIMIT if res["algorithm_used"] == "DLS" else ""),
             "yes" if res["found"] else "no", " -> ".join(res["path"]) if res["found"] else "-",
             res["cost"] if res["found"] else "-", res["steps"] if res["found"] else "-", res["nodes_expanded"]]
            for res in f["compare"]]
    r.table(["Algorithm", "Found", "Path", "Cost", "Steps", "Expanded"], rows,
            "compare_algorithms('Hostel', 'AI_Lab') on the weighted graph", [3.4, 1.3, 7.2, 1.2, 1.3, 1.9], 8.5)
    best = min(res["cost"] for res in f["compare"] if res["found"])
    opt = [res["algorithm_used"] for res in f["compare"] if res["found"] and res["cost"] == best]
    r.p("The cheapest cost is %d. It is found by %s. BFS, DFS, DLS, IDS and bidirectional BFS ignore the "
        "edge costs, so they return the 3-step route through Library (cost 7). A* finds the optimal route "
        "with the fewest expansions of the optimal algorithms. Greedy best-first happens to be optimal here "
        "but is not optimal in general." % (best, ", ".join(opt)))
    r.figure(cli["images"].get("cli_search_compare"),
             "Student 1 CLI (student1_search/search_cli.py): route Hostel -> AI_Lab and the 9-algorithm comparison")
    r.figure(shot("03_map_astar_route_hostel_ai_lab.png"),
             "Web UI, Campus map: A* Hostel -> AI_Lab (cost 6, 3 steps, 6 nodes expanded)")
    r.figure(shot("04_map_compare_9_algorithms.png"), "Web UI: comparison table and charts for Hostel -> AI_Lab (DLS limit 3 here; table 7 uses the default 5)")
    sec_tests(r, f, "student1_search/test_search.py")


def sec_tests(r, f, path):
    """
    Function: sec_tests
    Purpose : Short "Tests" subsection: test classes and how many tests each has.
    Params  : r (Report), f (dict), path (str) - test file
    Returns : None
    """
    groups = test_names(os.path.join(ROOT, path))
    total = sum(len(t) for _, t in groups)
    r.h("Tests (%s)" % os.path.basename(path), 3)
    r.p("`%s` has %d tests in %d groups. All of them pass (see section 8):" % (path, total, len(groups)))
    r.bullets(["**%s** (%d): %s" % (cls, len(t), "; ".join(t)) for cls, t in groups])


def sec_logic_csp(r, f, cli):
    """
    Function: sec_logic_csp
    Purpose : 4. Student 2 - Logic / KB and CSP.
    Params  : r (Report), f (dict), cli (dict)
    Returns : None
    """
    r.h("4. Student 2 - Logic / KB and CSP Scheduler (Ibrahim Asif, 24F-3070)")
    r.h("4.1 Knowledge base", 2)
    r.p("Atoms are tuples such as `(\"UsesLab\", \"DrKhan\", \"Lab1\")`. Variables are single lowercase "
        "letters (x, g) and constants start with a capital letter. The facts and rules are in "
        "`student2_logic_csp/logic_kb.py`. The handout gives 5 facts and the rules R1-R4. The team added "
        "facts and the rules R5-R15 so that every request category has a rule that can prove permission. "
        "These additions are kept separate and marked as team-defined.")
    facts = [kb.atom_text(x) for x in kb.FACTS]
    r.table(["Fact", "Source"], [[x, "handout" if x in HANDOUT_FACTS else "team-defined"] for x in facts],
            "Facts in the knowledge base (%d)" % len(facts), [9, 4], 8.5)
    r.table(["Rule", "Definition", "Source"],
            [[x["id"], kb.rule_text(x).split(": ", 1)[1], "handout" if x["id"] in HANDOUT_RULES else "team-defined"]
             for x in kb.RULES], "Rules R1-R15", [1.3, 11.5, 2.6], 8.5)
    r.p("Lab1 in the rules is treated as the AI_Lab node on the campus map (assumption).")
    r.h("4.2 Forward chaining", 2)
    log = f["forward"]["log"]
    r.p("Forward chaining applies every rule to the known facts and adds each new conclusion, round by round, "
        "until no rule adds anything new (a fixed point). From the %d facts it derives **%d new facts**. The "
        "handout's derived facts are all there: Instructor(DrKhan, AI), UsesLab(DrKhan, Lab1), "
        "UsesLab(Ali, Lab1) and Eligible(Ali, AI). Sara is not eligible because Completed(Sara, "
        "ProgrammingFundamentals) is not a fact." % (len(kb.FACTS), len(log)))
    r.table(["#", "Rule fired", "Derived fact"], [[i + 1, e["rule"], kb.atom_text(e["derived"])] for i, e in enumerate(log)],
            "Forward chaining log (kb.forward_chain())", [1, 2.2, 9], 8.5)
    r.h("4.3 Backward chaining and explanations", 2)
    r.p("Backward chaining starts from the query and works backwards. It finds a fact that matches the goal, "
        "or a rule whose conclusion unifies with the goal, and then proves that rule's premises. Variables in "
        "the query collect every answer. The proof tree is turned into a readable explanation. When a query "
        "fails, the module searches for the **missing premise**: the deepest atom that is neither a fact nor "
        "derivable. Under the closed-world assumption, an atom that cannot be proven is false.")
    rows = []
    for q, res in f["queries"]:
        rows.append([q, "yes" if res["entailed"] else "no", res["explanation"]])
    r.table(["Query", "Entailed", "Explanation (check_logic)"], rows, "Example queries answered by backward chaining",
            [4.2, 1.6, 10.6], 8.5)
    r.figure(shot("07_kb_proof_UsesLab_DrKhan.png"), "Web UI, Knowledge base: proof chain for UsesLab(DrKhan, Lab1)")
    r.figure(shot("08_kb_not_entailed_missing_premise.png"),
             "Web UI: Eligible(Sara, AI) is not entailed; the missing premise and the blocked rule are shown")
    r.figure(shot("09_kb_forward_chaining.png"), "Web UI: forward chaining to a fixed point")
    r.h("4.4 Authorization and permission", 2)
    r.p("Service requests (Booking, Urgent and Full service) are checked in two steps. **Step 1, role "
        "authorization**: the stated role must be provable (student -> Student(name), instructor -> "
        "Faculty(name), staff -> Staff(name)). **Step 2, permission**: prove CanRequest(name, category). For "
        "Viva_Scheduling a group id is required, and step 2 proves CanScheduleViva(name, group) instead, so "
        "a member or supervisor of G4 cannot schedule G3's viva. If either step fails, the request is "
        "rejected at the logic stage and the reason names the step and the missing premise.")
    rows = []
    for (name, role, cat, group), res in f["permissions"]:
        rows.append(["%s (%s), %s%s" % (name, role, cat, " " + group if group else ""), "yes" if res["allowed"] else "no",
                     res["explanation"]])
    r.table(["Request", "Allowed", "Explanation"], rows, "Authorization + permission examples (check_logic)",
            [4.6, 1.5, 10.3], 8)
    r.figure(cli["images"].get("cli_logic_csp"),
             "Student 2 CLI (student2_logic_csp/logic_csp_cli.py): two logic queries and the viva timetable")

    r.h("4.5 CSP: viva timetable", 2)
    r.p("Variables: the groups %s. Domain: slots %s. Constraints from the handout diagram:"
        % (", ".join(csp.VIVA_GROUPS), ", ".join(str(s) for s in csp.TIME_SLOTS)))
    r.bullets(["**Not equal** (shared examiner or supervisor): " + ", ".join("%s != %s" % p for p in csp.VIVA_NOT_EQUAL),
               "**Precedence**: " + ", ".join("%s < %s (strictly earlier)" % p for p in csp.VIVA_PRECEDENCE)])
    r.p("The solver `solve_csp(variables, domains, constraints, value_first, var_order)` in "
        "`student2_logic_csp/csp_scheduler.py` is a generic backtracking search with:")
    r.bullets([
        "**MRV (minimum remaining values)**: pick the unassigned variable with the fewest legal values left.",
        "**Degree heuristic**: break MRV ties by choosing the variable involved in the most constraints with "
        "unassigned variables.",
        "**LCV (least constraining value)**: try first the value that removes the fewest values from the "
        "neighbours' domains (stable order).",
        "**Forward checking**: after each assignment, remove inconsistent values from the neighbours' domains. "
        "If a domain becomes empty, backtrack at once.",
    ])
    sol, stats = f["viva"]
    r.p("Result: **%s**, with %d assignments tried and %d backtracks. G4 (slot %d) is before G3 (slot %d)."
        % (", ".join("%s=%d" % (g, sol[g]) for g in csp.VIVA_GROUPS), stats["assignments"], stats["backtracks"],
           sol["G4"], sol["G3"]))
    r.p("**Brute-force check** (every possible assignment, counted by the test file): %d valid timetables with "
        "4 slots, %d with 3 slots and %d with 2 slots. A preference such as G4 in slot 2 is a value ordering, "
        "not a constraint: `solve_viva(preferred={'G4': 2})` gives %s."
        % (f["brute"][4], f["brute"][3], f["brute"][2],
           ", ".join("%s=%d" % (g, f["viva_pref"][g]) for g in csp.VIVA_GROUPS)))
    r.figure(shot("06_csp_viva_timetable_solved.png"),
             "Web UI, Scheduling: the viva constraint graph after the solver finished (assign / backtrack replay)")
    r.h("4.6 CSP: room and slot booking", 2)
    r.p("The handout gives only the viva CSP. The booking CSP below is team-defined. Variables: `slot` and "
        "`room`. Constraints:")
    r.bullets(["the room serves the category: " + "; ".join("%s -> %s" % (k, ", ".join(v)) for k, v in csp.CATEGORY_ROOMS.items()),
               "(room, slot) is not already booked; the initial bookings are " +
               ", ".join("%s slot %d" % b for b in csp.INITIAL_BOOKINGS),
               "slot <= deadline from the ANN priority: " +
               ", ".join("%s %d" % (k, v) for k, v in csp.PRIORITY_DEADLINE.items()) +
               " (no priority: %d)" % csp.DEFAULT_DEADLINE])
    r.p("Slot values are tried in this order: the preferred slot, then later slots ascending, then earlier "
        "slots descending. The slot is chosen before the room, so the preference wins over the room order. "
        "The bookings are shared state, so a second request sees the first. A booking is committed only when "
        "the whole request is accepted.")
    hc = f["handout_csp"]
    r.p("**Handout example**: AI_Lab_Support, preferred slot 2, priority high (deadline 3). Slot 2 of AI_Lab is "
        "already booked, so the CSP assigns **%s slot %s**: \"%s\"" % (hc["assigned_room"], hc["assigned_slot"], hc["notes"]))
    rows = [[(p or "none").capitalize() if p else "none", csp.PRIORITY_DEADLINE.get((p or "").capitalize(), csp.DEFAULT_DEADLINE),
             res["decision"], "%s %s" % (res["assigned_room"], res["assigned_slot"] or "") if res["decision"] == "accepted" else "-",
             res["notes"]] for p, res in f["deadlines"]]
    r.table(["Priority", "Deadline", "Decision", "Assigned", "Notes"], rows,
            "AI_Lab_Support with preferred slot 4, from the initial bookings, for each priority", [1.8, 1.6, 1.8, 2.2, 9], 8)
    rows = [[i + 1, res["decision"], res["assigned_slot"] or "-", res["notes"]] for i, res in enumerate(f["repeat"])]
    r.table(["Request", "Decision", "Slot", "Notes"], rows,
            "Four requests in a row for AI_Lab slot 2 (no priority): 3 -> 4 -> 1 -> rejected", [1.6, 2, 1.2, 11.6], 8)
    r.figure(shot("05_csp_booking_grid.png"),
             "Web UI, Scheduling: booking grid after a request for AI_Lab slot 2 was moved to slot 3")
    sec_tests(r, f, "student2_logic_csp/test_logic.py")
    sec_tests(r, f, "student2_logic_csp/test_logic_csp.py")


def sec_ann(r, f, cli):
    """
    Function: sec_ann
    Purpose : 5. Student 3 - ANN.
    Params  : r (Report), f (dict), cli (dict)
    Returns : None
    """
    ev, models = f["eval"], f["models"]
    r.h("5. Student 3 - ANN Priority Prediction (Haroon Afzal, 24F-3001)")
    r.h("5.1 Features and encodings", 2)
    ranges = ["0-2", "0-4", "1-10", "1-10", "1-10", "0-15", "0 / 1"]
    notes = [", ".join("%s %d" % kv for kv in ROLE_ENCODING.items()),
             ", ".join("%s %d" % kv for kv in CATEGORY_ENCODING.items()),
             "user input", "user input", "user input", "route cost from Search (capped at 10 in the score)",
             "user's eligibility claim"]
    r.table(["Input", "Feature", "Range", "Encoding / source"],
            [["x%d" % (i + 1), FEATURE_ORDER[i], ranges[i], notes[i]] for i in range(7)],
            "ANN input features (fixed order)", [1.3, 3.4, 1.6, 10.1], 8.5)
    r.p("Before training and prediction, the features are scaled to 0-1 by dividing by FEATURE_MAX = %s."
        % [int(v) for v in ds.FEATURE_MAX])
    r.h("5.2 Dataset and labelling rule (team-defined)", 2)
    r.p("The handout gives no training data, so `student3_ann/dataset.py` generates %d samples with numpy "
        "(fixed seed %d). Each sample gets a priority score:" % (ds.N_SAMPLES, ds.SEED))
    r.code("score = 0.4*severity + 0.4*time + 0.1*crowd + 0.1*min(distance, 10)\n"
           "        + 2  if type == Emergency_Help\n"
           "        - 1  if eligibility == 0\n"
           "score += Gaussian noise (std %.1f)\n"
           "class  = low if score < 4, normal if < 6, high if < 8, else urgent   (labels 0..3)\n"
           "binary = urgent (1) if class is high or urgent, else not_urgent (0)" % ds.NOISE_STD)
    cc, bc = f["class_counts"], f["binary_counts"]
    r.p("Class counts: low %d, normal %d, high %d, urgent %d. Binary: not_urgent %d, urgent %d. Split: %d "
        "training and %d test samples (%d%% test, seed %d). The noise makes the labels imperfect on purpose. "
        "The best accuracy any model can reach is the **noise ceiling**: the accuracy of the noise-free formula "
        "on the noisy test labels."
        % (cc[0], cc[1], cc[2], cc[3], bc[0], bc[1], ev["n_train"], ev["n_test"], int(ds.TEST_FRACTION * 100), ds.SEED))
    r.h("5.3 Perceptron (binary baseline)", 2)
    w = models["perceptron"]
    r.p("7 inputs plus a bias, the weighted sum z = w·x + b, and a step activation (output 1 = urgent if z >= 0). "
        "It is trained with the perceptron learning rule w <- w + lr·(y - ŷ)·x, with learning rate %s for %d "
        "epochs. The decision boundary is the hyperplane w·x + b = 0, so the perceptron can only separate "
        "classes linearly."
        % (perceptron.LEARNING_RATE, perceptron.EPOCHS))
    r.table(["Weight"] + ["w%d (%s)" % (i + 1, FEATURE_ORDER[i]) for i in range(7)] + ["bias"],
            [["value"] + ["%.3f" % v for v in w["w"]] + ["%.3f" % float(w["b"])]],
            "Trained perceptron weights (student3_ann/weights.json)", None, 7.5)
    r.h("5.4 MLP 7-4-3-4", 2)
    r.p("The network is exactly the diagram: 7 inputs -> 4 sigmoid units -> 3 sigmoid units -> 4 softmax outputs "
        "(low, normal, high, urgent), with a bias on each layer. Training uses cross-entropy loss and "
        "backpropagation, written out step by step in numpy: output error P - Y, then the gradient through each "
        "sigmoid layer, then the weight gradients. It runs full-batch gradient descent with learning rate %s for "
        "%d epochs (seed %d). The confidence is the highest softmax probability."
        % (mlp.LEARNING_RATE, mlp.EPOCHS, mlp.SEED))
    r.h("5.5 Results", 2)
    cmp_ = ev["comparison"]
    r.table(["Model", "Task", "Test accuracy"],
            [["MLP 7-4-3-4", "4 classes", "%.2f%%" % (100 * ev["mlp_accuracy"])],
             ["Noise ceiling", "4 classes", "%.2f%%" % (100 * ev["noise_ceiling"])],
             ["Perceptron", "binary", "%.2f%%" % (100 * ev["perceptron_accuracy"])],
             ["MLP collapsed to binary", "binary", "%.2f%%" % (100 * cmp_["mlp_binary_accuracy"])],
             ["Perceptron vs MLP agreement", "binary", "%.2f%%" % (100 * cmp_["agreement"])]],
            "Test-set accuracy (train.evaluate on %d test samples)" % ev["n_test"], [5, 3, 3.5])
    r.p("The MLP reaches %.2f%% against a noise ceiling of %.2f%%, which is %.1f%% of the best possible "
        "accuracy. To compare like with like, the MLP's 4 classes are collapsed to binary (high/urgent -> "
        "urgent). The collapsed MLP scores %.2f%%, the perceptron %.2f%%. The MLP is better because the "
        "classes are not linearly separable in the scaled feature space, and its hidden layers can model the "
        "thresholds of the score."
        % (100 * ev["mlp_accuracy"], 100 * ev["noise_ceiling"], 100 * ev["mlp_accuracy"] / ev["noise_ceiling"],
           100 * cmp_["mlp_binary_accuracy"], 100 * ev["perceptron_accuracy"]))
    labels = ds.CLASS_NAMES
    r.table(["actual \\ predicted"] + labels, [[labels[i]] + list(row) for i, row in enumerate(ev["mlp_confusion"])],
            "MLP confusion matrix (rows: actual class, columns: predicted)", [3.5, 2.2, 2.2, 2.2, 2.2])
    r.table(["actual \\ predicted"] + ds.BINARY_NAMES,
            [[ds.BINARY_NAMES[i]] + list(row) for i, row in enumerate(ev["perceptron_confusion"])],
            "Perceptron confusion matrix", [3.5, 3, 3])
    loss_png = os.path.join(IMG_DIR, "ann_loss_curve.png")
    if loss_curve_image(models["mlp_loss_history"], loss_png):
        r.figure(loss_png, "MLP training loss (cross-entropy, recorded every %d epochs)" % train.LOSS_EVERY, max_w=14)
    r.h("5.6 Predictions", 2)
    rows = []
    for v, res, det in f["predictions"]:
        probs = det.get("probabilities", {})
        rows.append([str(v), res["final_priority"], res["binary_priority"], res["confidence"],
                     ", ".join("%s %.2f" % (k, probs[k]) for k in labels)])
    r.table(["Features (raw)", "MLP final", "Perceptron", "Confidence", "Probabilities"], rows,
            "predict_priority() examples", [3.6, 1.8, 2.1, 1.8, 7], 8.5)
    r.p("The first row is the handout's ANN example [0, 0, 8, 9, 5, 4, 1] (score 7.7): **high**, with a binary "
        "result of **urgent**. In the full pipeline, distance x6 is the real route cost from Hostel to "
        "AI_Lab, which is 6 rather than the 4 used in the handout. With 6 the result is still high / urgent, "
        "with confidence %.2f (second row)." % f["predictions"][1][1]["confidence"])
    r.figure(cli["images"].get("cli_ann"),
             "Student 3 CLI (student3_ann/ann_cli.py): handout example and the evaluation report")
    r.figure(shot("10_ann_prediction_handout_example.png"), "Web UI, ANN priority: forward pass for [0, 0, 8, 9, 5, 4, 1]")
    r.figure(shot("11_ann_full_page_prediction_and_metrics.png"),
             "Web UI, ANN priority: perceptron, accuracy bars, confusion matrices and loss curve")
    sec_tests(r, f, "student3_ann/test_ann.py")


def sec_integration(r, f, cli):
    """
    Function: sec_integration
    Purpose : 6. Integration.
    Params  : r (Report), f (dict), cli (dict)
    Returns : None
    """
    r.h("6. Integration")
    r.h("6.1 Preprocessing and normalisation", 2)
    r.p("The Logic module is strict about names: a lowercase term would be read as a variable and could match "
        "anyone. Preprocessing therefore normalises every field before any module runs, and rejects invalid "
        "input at the `preprocessing` stage with the reason.")
    rows = []
    for scenario, res in f["demos"]:
        raw, norm = scenario["request"], res["trace"]["request"]
        for field in ("name", "category", "group_id", "current_location", "destination"):
            if field in raw and str(raw[field]) != str(norm.get(field)) and norm.get(field):
                rows.append([field, "`%s`" % raw[field], "`%s`" % norm[field]])
    r.table(["Field", "Typed", "Normalised"], rows, "Normalisation seen in the demo scenarios", [4, 5, 5])
    r.bullets([
        "Person names are capitalised exactly as in the knowledge base (ali -> Ali, drkhan -> DrKhan).",
        "group_id is upper-cased (g4 -> G4). A well-formed but unknown group such as G9 is not a "
        "preprocessing error: Logic rejects it at the permission step.",
        "Category, role and request type get their canonical names. The CLI words Viva and Access map to "
        "Viva_Scheduling and Access_Request.",
        "Locations go through Search's `normalize_location` (\"ai lab\" -> AI_Lab). Unknown places are rejected "
        "with the list of valid ones.",
        "Slots must be 1-4 and severity / time / crowd 1-10. A malformed FOL query is rejected with the reason.",
        "For ANN request types, preprocessing builds the feature vector. x6 is the route cost from the current "
        "location to the category's room (`route_distance`).",
    ])
    r.h("6.2 Router and response formats", 2)
    r.p("`router.route(request)` fills the ROUTER_OUTPUT_TEMPLATE: the selected pipeline and the flags "
        "needs_ann, needs_logic, needs_csp and needs_search. Every module output follows its template in "
        "`shared/templates.py`, and the final response follows FINAL_RESPONSE_TEMPLATE:")
    r.code(jdump({"FINAL_RESPONSE_TEMPLATE": templates.FINAL_RESPONSE_TEMPLATE,
                  "PRIORITY_OUTPUT_TEMPLATE": templates.PRIORITY_OUTPUT_TEMPLATE,
                  "LOGIC_OUTPUT_TEMPLATE": templates.LOGIC_OUTPUT_TEMPLATE,
                  "CSP_OUTPUT_TEMPLATE": templates.CSP_OUTPUT_TEMPLATE,
                  "SEARCH_OUTPUT_TEMPLATE": templates.SEARCH_OUTPUT_TEMPLATE}))
    r.p("Only the parts a request type produces are included. A navigation response has only a route, and an "
        "eligibility check has only eligibility. The decision is `completed` (navigation), `answered` "
        "(eligibility), `accepted` or `rejected`.")
    r.h("6.3 Rejection at each stage", 2)
    rows = []
    picks = [res for s, res in f["demos"] if res["decision"] == "rejected"] + [f["csp_rejection"]]
    for res in picks:
        stage = res.get("rejected_at")
        reason = next((st["notes"] or st["summary"] for st in res["trace"]["stages"] if st["status"] == "rejected"), "")
        req = res["trace"]["request"]
        what = "%s, %s%s" % (req.get("name") or "?", req.get("request_type"),
                             (", " + req["category"]) if req.get("category") else "")
        rows.append([what, stage, res["message"], reason])
    r.table(["Request", "rejected_at", "Message", "Reason (trace)"], rows,
            "Rejections at preprocessing, logic and CSP", [3.6, 2, 4.6, 6.2], 8)
    r.figure(cli["images"].get("cli_rejection"), "CLI demo scenario 7: Sara is rejected at the logic stage")
    r.figure(shot("02_console_rejection_at_logic.png"),
             "Web UI: a rejection at the eligibility check stops the pipeline and shows the reason")
    r.h("6.4 The handout full-service example, end to end", 2)
    scenario, res = f["demos"][5]
    trace = res["trace"]
    r.p("Input (handout Phase 3 section 11):")
    r.code(jdump(scenario["request"]))
    r.p("After preprocessing (normalised request with id and ANN features):")
    r.code(jdump({k: v for k, v in trace["request"].items() if v not in ("", None)}))
    r.p("Router: **%s**." % " -> ".join(trace["pipeline"]))
    mods = trace["modules"]
    for key, title in (("ann", "ANN output (Student 3)"), ("logic", "Logic output (Student 2)"),
                       ("csp", "CSP output (Student 2)"), ("search", "Search output (Student 1)")):
        out = dict(mods[key])
        out.pop("timetable", None)
        if key == "logic":
            out = {k: out[k] for k in ("allowed", "entailed", "query", "explanation", "proof")}
        r.p(title + ":")
        r.code(jdump(out))
    r.p("Final response (exactly what `main.process_request` returns):")
    final = {k: v for k, v in res.items() if k != "trace"}
    r.code(jdump(final))
    r.p("The result is **%s**: priority %s / %s (confidence %.2f), %s slot %d, route %s with cost %d. The "
        "preferred slot 2 is already booked, so the CSP moves the booking to slot 3, the next free slot within "
        "the deadline for priority high (slot 3)."
        % (res["decision"], res["priority"]["final_priority"], res["priority"]["binary_priority"],
           res["priority"]["confidence"], res["assignment"]["room"], res["assignment"]["slot"],
           " -> ".join(res["route"]["path"]), res["route"]["cost"]))
    r.figure(cli["images"].get("cli_full_service"), "CLI demo scenario 6: the handout full-service example")
    r.figure(shot("01_console_handout_full_service_example.png"),
             "Web UI, Request console: the same example with the pipeline tracker")


def sec_ui(r, f, cli):
    """
    Function: sec_ui
    Purpose : 7. User interface.
    Params  : r (Report), f (dict), cli (dict)
    Returns : None
    """
    r.h("7. User interface")
    r.h("7.1 Structured CLI form", 2)
    r.p("`cli.py` is the main interface. The main menu offers: 1 new request, 2 run demo scenarios, 3 show "
        "current bookings, 4 reset, 5 exit. A new request asks for Name, Role and Request Type, and then only "
        "for the fields that type needs (see Table 1). Every answer is checked with the same functions "
        "preprocessing uses, and an invalid answer is asked again. Each response is printed as a short summary "
        "followed by the handout JSON.")
    r.figure(cli["images"].get("cli_form"), "The structured CLI form: a Full_Service_Request typed in by hand")
    r.h("7.2 Web UI", 2)
    r.p("`python server.py` starts a Flask server at http://127.0.0.1:5000 and opens the browser. `web/` is a "
        "single page (index.html, app.js, styles.css). `web/api.js` is the only file that talks to the "
        "backend. The server has no AI logic: each endpoint calls an existing module and only reshapes its "
        "output into JSON. Handout response fields are never changed, only added to, and bad input returns "
        "HTTP 400 with an error message.")
    with open(os.path.join(ROOT, "server.py"), encoding="utf-8") as fh:
        doc = fh.read()
    eps = re.findall(r"^\s+(GET|POST)\s+(/api/\S+)\s+(.+)$", doc, re.M)
    r.table(["Method", "Endpoint", "Calls"], [[m, "`%s`" % p, d.split(" (")[0].strip()] for m, p, d in eps],
            "Web API endpoints (server.py)", [1.6, 4.6, 10], 8.5)
    r.table(["Page", "What it shows"], [
        ["Request console", "The request form, which shows only the fields the request type needs, and 9 demo "
         "scenarios. A pipeline tracker lights up only the modules the router selected; skipped modules are "
         "grey and a rejection stops at its stage with the reason. Result cards show priority, eligibility, "
         "assignment, route and the raw JSON."],
        ["Campus map & search", "The 13-node map with edge costs and live h(n) values. It runs BFS / A* / UCS by "
         "graph mode, animates the node expansion, and compares all 9 algorithms (clicking a row replays its "
         "search)."],
        ["Scheduling / CSP", "The live booking grid (room x slot, with the request that booked each cell), a "
         "quick booking form, and the viva constraint graph with a step-by-step replay of the solver."],
        ["Knowledge base", "Facts and rules R1-R15 (handout / team-defined), queries with proof chains or the "
         "missing premise, and forward chaining to a fixed point."],
        ["ANN priority", "The 7-4-3-4 network animated for any feature vector, the perceptron, accuracy against "
         "the noise ceiling, confusion matrices and the loss curve."],
        ["History", "Every request of the session with id, decision and modules. Clicking one reopens its "
         "result. The list is kept on the server (GET /api/history), so a page reload keeps it, and Reset "
         "clears it."],
    ], "Pages of the web UI", [3.4, 13])
    r.figure(shot("12_history.png"), "Web UI, History: every request of the session with its decision")
    r.figure(shot("13_console_light_theme.png"), "Web UI in the light theme (the theme toggle is in the top bar)")


def sec_testing(r, f, cli):
    """
    Function: sec_testing
    Purpose : 8. Testing.
    Params  : r (Report), f (dict), cli (dict)
    Returns : None
    """
    r.h("8. Testing")
    r.h("8.1 Unit and integration tests", 2)
    rows, total = parse_tests(cli["text"]["run_all_tests"])
    r.p("`python run_all_tests.py` runs every test file in its own Python process and prints one line per file:")
    r.table(["Part", "Test file", "Tests", "Result", "Time"], [list(x) for x in rows],
            "run_all_tests.py summary", [3.8, 6, 1.6, 1.8, 1.8])
    r.p(total + ".")
    r.figure(cli["images"].get("cli_run_all_tests"), "Output of python run_all_tests.py")
    sec_tests(r, f, "test_integration.py")
    r.h("8.2 Web UI end-to-end test", 2)
    if not os.path.exists(UI_RESULTS):
        r.p("[UI test results file missing: %s]" % UI_RESULTS)
        return
    with open(UI_RESULTS, encoding="utf-8") as fh:
        ui = json.load(fh)
    res = ui["results"]
    passed = sum(1 for x in res if x["pass"])
    r.p("`tests_ui/test_ui.py` tests the web UI end to end against the real backend (USE_MOCK = false). It starts "
        "server.py and drives a headless browser (%s, %s) with Playwright. Every expected value is computed first by "
        "calling the Python modules directly: the cli.py --demo results, compare_algorithms(), check_logic(), "
        "predict_priority() and train.evaluate(). Browser console errors and failed network requests (any 4xx/5xx) "
        "are captured on every page and count as failures. The test is not part of run_all_tests.py because it "
        "needs a browser (`pip install playwright`, `python -m playwright install`). Last run %s: **%d of %d "
        "checks passed**." % (ui.get("browser", "msedge"), ui.get("viewport", "1366x768"),
                              ui.get("date", "")[:10], passed, len(res)))
    rows = [[x["area"], x["check"], "PASS" if x["pass"] else "FAIL", x["notes"][:150]] for x in res]
    r.table(["Area", "Check", "Result", "Notes"], rows, "Web UI end-to-end checks (%d)" % len(res), [2.3, 5.6, 1.4, 7.3], 7.5)
    failed = [x for x in res if not x["pass"]]
    if failed:
        r.p("Checks that did not pass:")
        r.bullets(["%s / %s: %s" % (x["area"], x["check"], x["notes"]) for x in failed])
    r.p("Found and changed during UI testing:")
    r.bullets(UI_CHANGES)


def sec_assumptions(r, f):
    """
    Function: sec_assumptions
    Purpose : 9. Assumptions and handout inconsistencies.
    Params  : r (Report), f (dict)
    Returns : None
    """
    r.h("9. Assumptions and resolved handout inconsistencies")
    r.table(["Topic", "Handout", "What we did"], [
        ["Category names", "The CLI prompt says Viva / Access; the ANN encoding says Viva_Scheduling / Access_Request.",
         "User input is normalised to the encoding names. Emergency_Help is a valid category."],
        ["Lab1", "The rules use Lab1; the map has an AI_Lab node.", "Lab1 is treated as the AI_Lab node."],
        ["Permission rules", "Only R1-R4 and 5 facts are given, which cannot decide every request category.",
         "Team-defined facts and rules R5-R15 (Person, CanRequest, CanScheduleViva), kept separate from R1-R4."],
        ["Heuristic", "Use a heuristic for A*.",
         "Raw Euclidean distance overestimates on %d of %d edges, so h(n) = k * euclid with k = 1/3 (admissible "
         "and consistent)." % (len(f["over_edges"]), len(EDGES))],
        ["Distance 6 vs 4", "The ANN example uses distance 4 for the Hostel -> AI_Lab request.",
         "The pipeline uses the real route cost (6). Both give high / urgent (confidence %.2f with 6, %.2f with 4)."
         % (f["predictions"][1][1]["confidence"], f["predictions"][0][1]["confidence"])],
        ["Booking CSP", "Only the viva CSP is specified.",
         "Room/slot CSP with category rooms, initial bookings %s and deadlines Urgent 2 / High 3 / other 4."
         % ", ".join("%s %d" % b for b in csp.INITIAL_BOOKINGS)],
        ["ANN data", "No training data is given.",
         "%d generated samples (seed %d) with a documented labelling rule and Gaussian noise." % (ds.N_SAMPLES, ds.SEED)],
        ["Report format", "Word in one place, PDF in another.", "A Word report and the same report exported as PDF."],
    ], "Assumptions (full list in CLAUDE.md)", [2.8, 6, 7.6], 8.5)


def sec_run(r, f, cli):
    """
    Function: sec_run
    Purpose : 10. How to run and modules completed.
    Params  : r (Report), f (dict), cli (dict)
    Returns : None
    """
    r.h("10. How to run")
    r.code("python -m venv venv\n"
           "venv\\Scripts\\activate                 (Windows; Linux/macOS: source venv/bin/activate)\n"
           "pip install -r requirements.txt      (numpy, flask)\n\n"
           "python server.py                     web UI at http://127.0.0.1:5000  (--port N, --no-browser)\n"
           "python cli.py                        structured CLI form\n"
           "python cli.py --demo                 the 9 demo scenarios\n"
           "python student1_search/search_cli.py         Student 1 demo\n"
           "python student2_logic_csp/logic_csp_cli.py   Student 2 demo\n"
           "python student3_ann/ann_cli.py               Student 3 demo\n"
           "python run_all_tests.py              all tests\n\n"
           "pip install playwright               optional, only for the web UI test\n"
           "python -m playwright install\n"
           "python tests_ui/test_ui.py           web UI end-to-end test (--shots: report screenshots)")
    rows, _ = parse_tests(cli["text"]["run_all_tests"])
    counts = {}
    for part, file, n, result, _ in rows:
        counts[file] = (int(n), result)
    def st(*files):
        n = sum(counts.get(x, (0, ""))[0] for x in files)
        ok = all(counts.get(x, (0, "FAIL"))[1] == "PASS" for x in files)
        return "Complete, %d tests pass" % n if ok else "Tests failing"
    r.h("Modules completed", 2)
    r.table(["Module", "Owner", "Status"], [
        ["Search & Navigation (9 algorithms, policy, scaled heuristic)", "Muhammad Dawood (24F-3054)", st("student1_search/test_search.py")],
        ["Logic / KB (forward + backward chaining, explanations)", "Ibrahim Asif (24F-3070)", st("student2_logic_csp/test_logic.py")],
        ["CSP Scheduler (viva + booking)", "Ibrahim Asif (24F-3070)", st("student2_logic_csp/test_logic_csp.py")],
        ["ANN (Perceptron + MLP 7-4-3-4)", "Haroon Afzal (24F-3001)", st("student3_ann/test_ann.py")],
        ["Integration (preprocessing, router, final response)", "Joint", st("test_integration.py")],
        ["Structured CLI form + demo mode", "Joint", "Complete"],
        ["Web UI (server.py + web/)", "Joint", "Complete, end-to-end tested (section 8.2)"],
    ], "Modules and their status", [8, 3.8, 4.6])


def appendix(r):
    """
    Function: appendix
    Purpose : Appendix: the complete source code, grouped by owner.
    Params  : r (Report)
    Returns : None
    """
    r.page_break()
    r.h("Appendix: Source code")
    groups = [
        ("A.1 Shared data", ["shared/*.py"]),
        ("A.2 Student 1 - Search & Navigation", ["student1_search/*.py"]),
        ("A.3 Student 2 - Logic / KB + CSP", ["student2_logic_csp/*.py"]),
        ("A.4 Student 3 - ANN", ["student3_ann/*.py"]),
        ("A.5 Integration", ["integration/*.py", "main.py", "cli.py", "run_all_tests.py", "test_integration.py"]),
        ("A.6 Web UI", ["server.py", "web/index.html", "web/app.js", "web/api.js", "web/styles.css",
                        "tests_ui/test_ui.py"]),
    ]
    for title, patterns in groups:
        r.h(title, 2)
        files = []
        for pat in patterns:
            files.extend(sorted(glob.glob(os.path.join(ROOT, pat))))
        for path in files:
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            r.h("%s (%d lines)" % (rel, text.count("\n") + 1), 3)
            r.code(text, small=True, shade=False)


# ===========================================================================
# 5. PDF conversion
# ===========================================================================
WORD_PS = r"""
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open('%(docx)s')
  foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
  $doc.Fields.Update() | Out-Null
  foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
  $doc.Save()
  $doc.SaveAs2('%(pdf)s', 17)
  $doc.Close(0)
} finally { $word.Quit() }
"""


def to_pdf():
    """
    Function: to_pdf
    Purpose : Convert the docx to PDF with Word (also fills in the table of
              contents and page numbers), else with LibreOffice.
    Params  : none
    Returns : str - what happened
    """
    if os.name == "nt":
        script = WORD_PS % {"docx": DOCX_PATH, "pdf": PDF_PATH}
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=900)
        if proc.returncode == 0 and os.path.exists(PDF_PATH):
            return "PDF written with Microsoft Word (table of contents updated)"
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if office:
        subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", REPORT_DIR, DOCX_PATH],
                       capture_output=True, timeout=900)
        if os.path.exists(PDF_PATH):
            return "PDF written with LibreOffice (update the table of contents in Word before submitting)"
    return "No Word or LibreOffice found: open the .docx in Word, update the table of contents and export it as PDF"


def build():
    """
    Function: build
    Purpose : Build the whole report.
    Params  : none
    Returns : None
    """
    print("Running the modules ...")
    f = collect_facts()
    print("Running the CLIs and the tests ...")
    cli = capture_cli()
    print("Writing the document ...")
    r = Report()
    title_page(r)
    sec_intro(r, f)
    sec_architecture(r, f)
    sec_search(r, f, cli)
    sec_logic_csp(r, f, cli)
    sec_ann(r, f, cli)
    sec_integration(r, f, cli)
    sec_ui(r, f, cli)
    sec_testing(r, f, cli)
    sec_assumptions(r, f)
    sec_run(r, f, cli)
    appendix(r)
    if os.path.exists(PDF_PATH):
        os.remove(PDF_PATH)
    r.doc.save(DOCX_PATH)
    print("Saved %s (%d figures, %d tables)" % (DOCX_PATH, r.fig, r.tab))
    print(to_pdf())


if __name__ == "__main__":
    build()
