"""
File    : student2_logic_csp/logic_kb.py
Module  : Logic / Knowledge Base (First-Order Logic, Horn-style rules)
Owner   : Student 2

Purpose : Stores the campus knowledge base (facts + rules R1-R15), answers
          logic queries with forward chaining and backward chaining, and
          decides whether a request is allowed. Entry point for the
          integration layer: check_logic(request).

Rules   : imports only from shared/, never prints, never reads input.

Notation (kept deliberately simple)
          atom      = tuple  ("UsesLab", "DrKhan", "Lab1")   -> UsesLab(DrKhan, Lab1)
          constant  = starts with a capital letter           (Ali, AI, Lab1)
          variable  = a lowercase letter                     (x, g)
          (inside rules, a renamed copy of a variable looks like "x7";
           it is still a variable because it starts with a lowercase letter)
          rule      = dict {"id", "premises": [atoms], "conclusion": atom}
          Atoms are flat (no nested terms), so unification is just
          "match the predicate, then match the arguments one by one".

Closed world : anything that cannot be proven from the facts and rules is
          treated as FALSE, and the explanation names the premise that is
          missing.

Assumption   : Lab1 in this knowledge base is the AI_Lab node on the campus
          map (shared.campus_data.LAB1_NODE). R5-R15 and the extra facts are
          team-defined extensions (see CLAUDE.md).
"""

import sys
import os
import re

# Make "shared" importable when this file is run directly from its folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.campus_data import CATEGORIES, ROLES
from shared.templates import new_template, LOGIC_OUTPUT_TEMPLATE

MAX_DEPTH = 25   # safety limit for backward chaining (the rules are not recursive)

# ===========================================================================
# 1. The knowledge base: facts and rules
# ===========================================================================
# Diagram facts (from the handout / CLAUDE.md)
FACTS = [
    ("Teaches", "DrKhan", "AI"),
    ("Enrolled", "Ali", "AI"),
    ("Student", "Sara"),
    ("Student", "Ali"),
    ("Completed", "Ali", "ProgrammingFundamentals"),
    # Team-added demo facts (assumption)
    ("Faculty", "DrKhan"),
    ("Faculty", "DrAmna"),
    ("Staff", "Bilal"),
    ("Student", "Ahmed"),
    ("Enrolled", "Ahmed", "AI"),
    ("Completed", "Ahmed", "ProgrammingFundamentals"),
    ("FYPGroup", "G1"), ("FYPGroup", "G2"), ("FYPGroup", "G3"),
    ("FYPGroup", "G4"), ("FYPGroup", "G5"), ("FYPGroup", "G6"),
    ("MemberOf", "Ahmed", "G4"),
    ("MemberOf", "Ali", "G3"),
    ("Supervises", "DrKhan", "G4"),
    ("HasIDCard", "Ali"),
    ("HasIDCard", "Ahmed"),
]

RULES = [
    # --- R1-R4: exactly as in CLAUDE.md --------------------------------------
    {"id": "R1", "premises": [("Student", "x"), ("Completed", "x", "ProgrammingFundamentals")],
     "conclusion": ("Eligible", "x", "AI")},
    {"id": "R2", "premises": [("Teaches", "x", "AI")],
     "conclusion": ("Instructor", "x", "AI")},
    {"id": "R3", "premises": [("Enrolled", "x", "AI")],
     "conclusion": ("UsesLab", "x", "Lab1")},
    {"id": "R4", "premises": [("Instructor", "x", "AI")],
     "conclusion": ("UsesLab", "x", "Lab1")},
    # --- R5-R15: team-defined permission rules (assumption) ------------------
    {"id": "R5", "premises": [("Student", "x")], "conclusion": ("Person", "x")},
    {"id": "R6", "premises": [("Faculty", "x")], "conclusion": ("Person", "x")},
    {"id": "R7", "premises": [("Staff", "x")], "conclusion": ("Person", "x")},
    {"id": "R8", "premises": [("Eligible", "x", "AI"), ("UsesLab", "x", "Lab1")],
     "conclusion": ("CanRequest", "x", "AI_Lab_Support")},
    {"id": "R9", "premises": [("Instructor", "x", "AI")],
     "conclusion": ("CanRequest", "x", "AI_Lab_Support")},
    {"id": "R10", "premises": [("MemberOf", "x", "g"), ("FYPGroup", "g")],
     "conclusion": ("CanScheduleViva", "x", "g")},
    {"id": "R11", "premises": [("Supervises", "x", "g"), ("FYPGroup", "g")],
     "conclusion": ("CanScheduleViva", "x", "g")},
    {"id": "R12", "premises": [("Student", "x"), ("HasIDCard", "x")],
     "conclusion": ("CanRequest", "x", "Access_Request")},
    {"id": "R13", "premises": [("Faculty", "x")],
     "conclusion": ("CanRequest", "x", "Access_Request")},
    {"id": "R14", "premises": [("Person", "x")],
     "conclusion": ("CanRequest", "x", "Maintenance")},
    {"id": "R15", "premises": [("Person", "x")],
     "conclusion": ("CanRequest", "x", "Emergency_Help")},
]

# Which KB predicate proves each claimed role (used by the authorization step)
ROLE_PREDICATE = {"student": "Student", "instructor": "Faculty", "staff": "Staff"}

# Request types handled by check_logic
ELIGIBILITY_TYPE = "Eligibility_Check"
SERVICE_TYPES = ["Booking_or_Scheduling", "Urgent_Service_Request", "Full_Service_Request"]
VIVA_CATEGORY = "Viva_Scheduling"   # needs group_id; proven with CanScheduleViva(name, group_id)

# Plain-English phrase for each predicate ("{0}" is always the subject)
PHRASES = {
    "Teaches": "{0} teaches {1}",
    "Enrolled": "{0} is enrolled in {1}",
    "Student": "{0} is a student",
    "Faculty": "{0} is a faculty member",
    "Staff": "{0} is a staff member",
    "Completed": "{0} completed {1}",
    "Eligible": "{0} is eligible for {1}",
    "Instructor": "{0} is an instructor of {1}",
    "UsesLab": "{0} can use {1}",
    "Person": "{0} is a person on campus",
    "CanRequest": "{0} can request {1}",
    "CanScheduleViva": "{0} can schedule a viva for {1}",
    "FYPGroup": "{0} is an FYP group",
    "MemberOf": "{0} is a member of {1}",
    "Supervises": "{0} supervises {1}",
    "HasIDCard": "{0} has an ID card",
}

CONSTANT_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
VARIABLE_PATTERN = re.compile(r"^[a-z]$")


def predicate_arities(facts, rules):
    """
    Function: predicate_arities
    Purpose : Collect every predicate name used in the facts and rules with its
              number of arguments (used to reject unknown predicates in queries).
    Params  : facts (list of atoms), rules (list of rule dicts)
    Returns : dict {predicate name: number of arguments}
    """
    arities = {}
    atoms = list(facts)
    for rule in rules:
        atoms.extend(rule["premises"])
        atoms.append(rule["conclusion"])
    for atom in atoms:
        arities[atom[0]] = len(atom) - 1
    return arities


PREDICATES = predicate_arities(FACTS, RULES)


# ===========================================================================
# 2. Atoms, text, parsing
# ===========================================================================
def atom_text(atom):
    """
    Function: atom_text
    Purpose : Write an atom the way the handout does.
    Params  : atom (tuple) - e.g. ("UsesLab", "DrKhan", "Lab1")
    Returns : str - "UsesLab(DrKhan, Lab1)"
    """
    return "%s(%s)" % (atom[0], ", ".join(atom[1:]))


def rule_text(rule):
    """
    Function: rule_text
    Purpose : Write a rule in readable form, with its id.
    Params  : rule (dict) - {"id", "premises", "conclusion"}
    Returns : str - "R2: Teaches(x, AI) => Instructor(x, AI)"
    """
    left = " & ".join(atom_text(p) for p in rule["premises"])
    return "%s: %s => %s" % (rule["id"], left, atom_text(rule["conclusion"]))


def is_variable(term):
    """
    Function: is_variable
    Purpose : A term is a variable if it starts with a lowercase letter;
              constants start with a capital letter.
    Params  : term (str)
    Returns : bool
    """
    return term[:1].islower()


def parse_atom(text):
    """
    Function: parse_atom
    Purpose : Turn a query string such as "UsesLab(DrKhan, Lab1)" or
              "UsesLab(x, Lab1)" into an atom tuple, rejecting malformed text
              with a clear message. The predicate must exist in the KB and be
              used with the right number of arguments.
    Params  : text (str) - the query text
    Returns : (atom, None) on success, or (None, error message) on failure
    """
    if not isinstance(text, str) or not text.strip():
        return None, "Query is empty. Expected something like UsesLab(DrKhan, Lab1)."
    text = text.strip()
    if "(" not in text:
        return None, "Malformed query '%s': missing '('. Expected Predicate(arg1, arg2)." % text
    if not text.endswith(")"):
        return None, "Malformed query '%s': missing closing parenthesis ')'." % text
    if text.count("(") != 1 or text.count(")") != 1:
        return None, "Malformed query '%s': unbalanced or extra parentheses." % text
    open_at = text.index("(")
    predicate = text[:open_at].strip()
    if not CONSTANT_PATTERN.match(predicate):
        return None, ("Malformed query '%s': predicate name '%s' must start with a capital "
                      "letter (e.g. UsesLab)." % (text, predicate))
    inside = text[open_at + 1:-1]
    if not inside.strip():
        return None, "Malformed query '%s': no arguments between the parentheses." % text
    terms = []
    for raw in inside.split(","):
        term = raw.strip()
        if not term:
            return None, "Malformed query '%s': empty argument (check the commas)." % text
        if not (CONSTANT_PATTERN.match(term) or VARIABLE_PATTERN.match(term)):
            return None, ("Malformed query '%s': argument '%s' must be a constant starting with "
                          "a capital letter (Ali, Lab1) or a single lowercase letter variable "
                          "(x)." % (text, term))
        terms.append(term)
    if predicate not in PREDICATES:
        return None, ("Unknown predicate '%s'. Known predicates: %s."
                      % (predicate, ", ".join(sorted(PREDICATES))))
    if len(terms) != PREDICATES[predicate]:
        return None, ("Predicate %s takes %d argument(s) but %d were given."
                      % (predicate, PREDICATES[predicate], len(terms)))
    return (predicate,) + tuple(terms), None


# ===========================================================================
# 3. Unification (flat atoms)
# ===========================================================================
def walk(term, subst):
    """
    Function: walk
    Purpose : Follow a variable through the substitution until it reaches a
              constant or an unbound variable.
    Params  : term (str), subst (dict {variable: term})
    Returns : str - the term's current value
    """
    while is_variable(term) and term in subst:
        term = subst[term]
    return term


def substitute(atom, subst):
    """
    Function: substitute
    Purpose : Replace every variable in an atom by its value in the substitution.
    Params  : atom (tuple), subst (dict)
    Returns : tuple - new atom
    """
    return (atom[0],) + tuple(walk(t, subst) for t in atom[1:])


def unify(a, b, subst):
    """
    Function: unify
    Purpose : Try to make two flat atoms equal. Predicates must match; then
              each pair of arguments must be equal or one of them a variable
              that can be bound. The input substitution is not changed.
    Params  : a (tuple), b (tuple), subst (dict) - bindings found so far
    Returns : dict - extended substitution, or None if they cannot unify
    """
    if a[0] != b[0] or len(a) != len(b):
        return None
    result = dict(subst)
    for t1, t2 in zip(a[1:], b[1:]):
        t1 = walk(t1, result)
        t2 = walk(t2, result)
        if t1 == t2:
            continue
        if is_variable(t1):
            result[t1] = t2
        elif is_variable(t2):
            result[t2] = t1
        else:
            return None            # two different constants
    return result


def rename_rule(rule, number):
    """
    Function: rename_rule
    Purpose : Give a rule fresh variable names (x -> x7) so its variables can
              never clash with the variables of the query or of another rule use.
    Params  : rule (dict), number (int) - unique suffix
    Returns : dict - renamed copy (same id)
    """
    def rename(atom):
        """
        Function: rename
        Purpose : Add the suffix to every variable of one atom.
        Params  : atom (tuple)
        Returns : tuple
        """
        return (atom[0],) + tuple(t + str(number) if is_variable(t) else t for t in atom[1:])

    return {"id": rule["id"],
            "premises": [rename(p) for p in rule["premises"]],
            "conclusion": rename(rule["conclusion"])}


# ===========================================================================
# 4. Forward chaining: derive every fact that follows from the rules
# ===========================================================================
def match_premises(premises, facts, subst):
    """
    Function: match_premises
    Purpose : Find every way to satisfy a list of premises using known facts
              (a join over the premises, left to right).
    Params  : premises (list of atoms), facts (list of atoms), subst (dict)
    Returns : generator of substitutions (dicts)
    """
    if not premises:
        yield subst
        return
    for fact in facts:
        extended = unify(premises[0], fact, subst)
        if extended is not None:
            yield from match_premises(premises[1:], facts, extended)


def forward_chain(facts=None, rules=None):
    """
    Function: forward_chain
    Purpose : Repeatedly fire every rule whose premises are all known until no
              new fact appears. Records which rule produced which fact.
    Params  : facts (list of atoms, default FACTS), rules (list, default RULES)
    Returns : dict {"facts": all facts (given first, derived after),
                    "derived": only the newly derived facts, in order,
                    "log": list of {"round", "rule", "premises", "derived"}}
    """
    facts = FACTS if facts is None else facts
    rules = RULES if rules is None else rules
    known = list(facts)
    known_set = set(known)
    derived, log = [], []
    round_no = 0
    changed = True
    while changed:
        changed = False
        round_no += 1
        for rule in rules:
            for subst in list(match_premises(rule["premises"], known, {})):
                new_fact = substitute(rule["conclusion"], subst)
                if any(is_variable(t) for t in new_fact[1:]) or new_fact in known_set:
                    continue
                known.append(new_fact)
                known_set.add(new_fact)
                derived.append(new_fact)
                log.append({"round": round_no, "rule": rule["id"],
                            "premises": [substitute(p, subst) for p in rule["premises"]],
                            "derived": new_fact})
                changed = True
    return {"facts": known, "derived": derived, "log": log}


def format_log(log):
    """
    Function: format_log
    Purpose : Turn the forward-chaining log into readable lines.
    Params  : log (list of dicts from forward_chain)
    Returns : list of str, e.g. "Round 1: R2 fired on Teaches(DrKhan, AI) => Instructor(DrKhan, AI)"
    """
    lines = []
    for entry in log:
        used = " & ".join(atom_text(p) for p in entry["premises"])
        lines.append("Round %d: %s fired on %s => %s"
                     % (entry["round"], entry["rule"], used, atom_text(entry["derived"])))
    return lines


def forward_answers(query, facts=None, rules=None):
    """
    Function: forward_answers
    Purpose : Answer a query by forward chaining: derive everything, then list
              the facts that match the query.
    Params  : query (atom, may contain variables), facts, rules (defaults: the KB)
    Returns : list of dicts {variable: constant}, one per answer ({} for a ground query
              that is true); empty list if nothing matches
    """
    everything = forward_chain(facts, rules)["facts"]
    answers = []
    for fact in everything:
        subst = unify(query, fact, {})
        if subst is not None:
            answers.append({v: walk(v, subst) for v in query_variables(query)})
    return answers


# ===========================================================================
# 5. Backward chaining: prove a query and return the proof chain
# ===========================================================================
def query_variables(query):
    """
    Function: query_variables
    Purpose : List the distinct variables of a query, in order of appearance.
    Params  : query (atom)
    Returns : list of str
    """
    seen = []
    for term in query[1:]:
        if is_variable(term) and term not in seen:
            seen.append(term)
    return seen


def prove(goal, subst, facts, rules, counter, depth=0):
    """
    Function: prove
    Purpose : Prove one goal. First try to match a known fact; then try every
              rule whose conclusion unifies with the goal and prove its premises.
    Params  : goal (atom), subst (dict), facts (list), rules (list),
              counter (list with one int, used to rename rule variables),
              depth (int) - recursion depth guard
    Returns : generator of (substitution, proof node) pairs. A proof node is
              {"atom": atom, "rule": rule dict or None for a fact, "children": [nodes]}
    """
    if depth > MAX_DEPTH:
        return
    for fact in facts:
        extended = unify(goal, fact, subst)
        if extended is not None:
            yield extended, {"atom": fact, "rule": None, "children": []}
    for rule in rules:
        counter[0] += 1
        fresh = rename_rule(rule, counter[0])
        extended = unify(goal, fresh["conclusion"], subst)
        if extended is None:
            continue
        for final, children in prove_all(fresh["premises"], extended, facts, rules,
                                         counter, depth + 1):
            yield final, {"atom": fresh["conclusion"], "rule": rule, "children": children}


def prove_all(goals, subst, facts, rules, counter, depth):
    """
    Function: prove_all
    Purpose : Prove a list of goals one after another, passing the variable
              bindings found so far to the next goal.
    Params  : goals (list of atoms), subst (dict), facts, rules, counter, depth
    Returns : generator of (substitution, list of proof nodes)
    """
    if not goals:
        yield subst, []
        return
    for after_first, node in prove(goals[0], subst, facts, rules, counter, depth):
        for after_all, rest in prove_all(goals[1:], after_first, facts, rules, counter, depth):
            yield after_all, [node] + rest


def resolve_tree(node, subst):
    """
    Function: resolve_tree
    Purpose : Apply the final substitution to every atom of a proof tree so it
              shows real names instead of variables.
    Params  : node (proof node), subst (dict)
    Returns : proof node (new tree)
    """
    return {"atom": substitute(node["atom"], subst), "rule": node["rule"],
            "children": [resolve_tree(c, subst) for c in node["children"]]}


def proof_lines(tree):
    """
    Function: proof_lines
    Purpose : List the facts and rules used by a proof, in the order they are
              needed (facts first, then the rule that uses them), like handout 10.4.
    Params  : tree (proof node)
    Returns : list of str, e.g. ["Teaches(DrKhan, AI)", "R2: Teaches(x, AI) => ...", "R4: ..."]
    """
    lines = []
    for child in tree["children"]:
        for line in proof_lines(child):
            if line not in lines:
                lines.append(line)
    own = atom_text(tree["atom"]) if tree["rule"] is None else rule_text(tree["rule"])
    if own not in lines:
        lines.append(own)
    return lines


def backward_chain(query, facts=None, rules=None, find_all=True):
    """
    Function: backward_chain
    Purpose : Prove a query from the facts and rules. A query with variables
              returns every answer; a ground query stops at the first proof.
              No proof at all means the query is false (closed world).
    Params  : query (atom), facts / rules (defaults: the KB),
              find_all (bool) - False stops after the first answer
    Returns : list of answers, each {"bindings": {variable: constant},
              "tree": proof tree, "proof": list of str}; [] if unprovable
    """
    facts = FACTS if facts is None else facts
    rules = RULES if rules is None else rules
    variables = query_variables(query)
    counter = [0]
    answers, seen = [], []
    for subst, node in prove(query, {}, facts, rules, counter):
        bindings = {v: walk(v, subst) for v in variables}
        if bindings in seen:
            continue
        seen.append(bindings)
        tree = resolve_tree(node, subst)
        answers.append({"bindings": bindings, "tree": tree, "proof": proof_lines(tree)})
        if not variables or not find_all:
            break
    return answers


# ===========================================================================
# 6. Explanations (plain English) and missing premises
# ===========================================================================
def phrase_parts(atom):
    """
    Function: phrase_parts
    Purpose : Split the English phrase of an atom into subject and rest, so
              several phrases about the same subject can be joined smoothly.
    Params  : atom (tuple)
    Returns : (subject, rest) - subject is "" if the predicate has no phrase
    """
    template = PHRASES.get(atom[0])
    if template is None:
        return "", atom_text(atom)
    full = template.format(*atom[1:])
    return atom[1], full[len(atom[1]) + 1:]


def join_phrases(atoms):
    """
    Function: join_phrases
    Purpose : Join the English phrases of several atoms with "and", dropping a
              repeated subject: "Ali is a student and completed X".
    Params  : atoms (list of atoms)
    Returns : str
    """
    parts, previous = [], None
    for atom in atoms:
        subject, rest = phrase_parts(atom)
        if subject and subject == previous:
            parts.append(rest)
        else:
            parts.append((subject + " " + rest) if subject else rest)
        previous = subject
    return " and ".join(parts)


def explain_tree(node):
    """
    Function: explain_tree
    Purpose : Describe a proof in plain English: premises, "therefore", conclusion.
              A chain of single-premise rules is merged into one sentence.
    Params  : node (resolved proof tree)
    Returns : str - e.g. "DrKhan teaches AI, therefore DrKhan is an instructor of AI
              and can use Lab1" (no final period)
    """
    if node["rule"] is None:
        return join_phrases([node["atom"]])
    chain = [node]
    current = node
    while len(current["children"]) == 1 and current["children"][0]["rule"] is not None:
        current = current["children"][0]
        chain.append(current)
    conclusions = [n["atom"] for n in reversed(chain)]
    kids = current["children"]
    if all(k["rule"] is None for k in kids):
        return join_phrases([k["atom"] for k in kids]) + ", therefore " + join_phrases(conclusions)
    return "; ".join(explain_tree(k) for k in kids) + "; so " + join_phrases(conclusions)


def explain_answer(tree):
    """
    Function: explain_answer
    Purpose : One sentence (with final period) explaining a proof.
    Params  : tree (resolved proof tree)
    Returns : str
    """
    text = explain_tree(tree)
    if tree["rule"] is None:
        text += " (a known fact)"
    return text + "."


def find_missing(goal, facts, rules, counter, path=(), depth=0):
    """
    Function: find_missing
    Purpose : For a goal that cannot be proven, find the premises that are
              missing. For each rule that could conclude the goal, take its first
              premise that cannot be proven and go deeper into it until a base
              fact is missing.
    Params  : goal (atom), facts, rules, counter (list with one int),
              path (tuple of rule ids followed so far), depth (int)
    Returns : list of (tuple of rule ids, missing atom), without duplicates
    """
    if depth > MAX_DEPTH:
        return []
    found = []
    matched = False
    for rule in rules:
        counter[0] += 1
        fresh = rename_rule(rule, counter[0])
        subst = unify(goal, fresh["conclusion"], {})
        if subst is None:
            continue
        matched = True
        for premise in fresh["premises"]:
            first = next(prove(premise, subst, facts, rules, counter), None)
            if first is None:
                found.extend(find_missing(substitute(premise, subst), facts, rules, counter,
                                          path + (rule["id"],), depth + 1))
                break
            subst = first[0]
    if not matched:
        found.append((path, goal))
    unique = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique


def missing_report(goal, facts=None, rules=None):
    """
    Function: missing_report
    Purpose : Explain in words why a goal is false under the closed-world
              assumption and which premises are missing.
    Params  : goal (atom), facts / rules (defaults: the KB)
    Returns : (explanation str, list of missing-atom strings)
    """
    facts = FACTS if facts is None else facts
    rules = RULES if rules is None else rules
    items = find_missing(goal, facts, rules, [0])
    text = ("%s cannot be proven, so under the closed-world assumption it is false."
            % atom_text(goal))
    missing = []
    for path, atom in items:
        shown = atom_text(atom)
        if shown not in missing:
            missing.append(shown)
        if path:
            text += (" Via %s: missing %s (not a known fact and no rule derives it)."
                     % (" -> ".join(path), shown))
        else:
            text += " There is no fact %s and no rule that concludes it." % shown
    return text, missing


# ===========================================================================
# 7. check_logic: the entry point used by the integration layer
# ===========================================================================
def make_result(allowed, entailed, explanation, query="", proof=None, answers=None,
                missing=None, rejected_at=None, error=None):
    """
    Function: make_result
    Purpose : Build the output dict: the LOGIC_OUTPUT_TEMPLATE fields (allowed,
              entailed, explanation) plus the extra fields described below.
    Params  : allowed (bool), entailed (bool), explanation (str), query (str),
              proof (list of str), answers (list of binding dicts),
              missing (list of str), rejected_at (str or None), error (str or None)
    Returns : dict with keys allowed, entailed, explanation, query, proof, answers,
              missing, rejected_at ("input" / "authorization" / "permission" / None),
              error (message for malformed or invalid input, else None)
    """
    result = new_template(LOGIC_OUTPUT_TEMPLATE)
    result["allowed"] = bool(allowed)
    result["entailed"] = bool(entailed)
    result["explanation"] = explanation
    result["query"] = query
    result["proof"] = proof if proof is not None else []
    result["answers"] = answers if answers is not None else []
    result["missing"] = missing if missing is not None else []
    result["rejected_at"] = rejected_at
    result["error"] = error
    return result


def merge_proofs(*proofs):
    """
    Function: merge_proofs
    Purpose : Join several proof lists into one, keeping order and removing repeats.
    Params  : proofs (lists of str)
    Returns : list of str
    """
    merged = []
    for proof in proofs:
        for line in proof:
            if line not in merged:
                merged.append(line)
    return merged


def eligibility_check(request):
    """
    Function: eligibility_check
    Purpose : Answer the logic query in request["query"] (e.g. "UsesLab(DrKhan, Lab1)").
              A query with variables returns every answer.
    Params  : request (dict) - needs "query"
    Returns : result dict (see make_result). allowed = entailed. A malformed query gives
              error set and rejected_at "input".
    """
    text = request.get("query")
    query, error = parse_atom(text)
    if error:
        shown = text if isinstance(text, str) else ""
        return make_result(False, False, error, shown, rejected_at="input", error=error)
    shown = atom_text(query)
    answers = backward_chain(query)
    if not answers:
        explanation, missing = missing_report(query)
        return make_result(False, False, explanation,
                           shown, missing=missing)
    proof = merge_proofs(*[a["proof"] for a in answers])
    if not query_variables(query):
        return make_result(True, True, explain_answer(answers[0]["tree"]), shown, proof)
    pieces = []
    for a in answers:
        binding = ", ".join("%s = %s" % (v, c) for v, c in a["bindings"].items())
        pieces.append("%s (%s)" % (binding, explain_answer(a["tree"]).rstrip(".")))
    explanation = "%s has %d answer(s): %s." % (shown, len(answers), "; ".join(pieces))
    return make_result(True, True, explanation, shown, proof,
                       answers=[a["bindings"] for a in answers])


def service_check(request):
    """
    Function: service_check
    Purpose : Booking / Urgent / Full service check in two steps.
              Step 1 role authorization: the claimed role must be provable
              (student -> Student(name), instructor -> Faculty(name), staff -> Staff(name)).
              Step 2 permission: CanRequest(name, category) must be provable; for
              Viva_Scheduling the group is required and CanScheduleViva(name, group_id)
              must be provable instead.
              Stops with the reason at whichever step fails.
    Params  : request (dict) - needs name, role, category (and group_id for Viva_Scheduling)
    Returns : result dict (see make_result); rejected_at is "input", "authorization",
              "permission" or None when allowed
    """
    name = request.get("name")
    name = name.strip() if isinstance(name, str) else ""
    role = request.get("role")
    role = role.strip().lower() if isinstance(role, str) else ""
    category_text = request.get("category")
    category = {c.lower(): c for c in CATEGORIES}.get(
        category_text.strip().lower() if isinstance(category_text, str) else "")

    # --- input validation (an unchecked lowercase name would act like a variable!) ---
    problem = None
    if not CONSTANT_PATTERN.match(name):
        problem = "Name '%s' is invalid: it must be one word starting with a capital letter." % name
    elif role not in ROLES:
        problem = "Role '%s' is invalid: expected one of %s." % (role, ", ".join(ROLES))
    elif category is None:
        problem = "Category '%s' is invalid: expected one of %s." % (category_text, ", ".join(CATEGORIES))
    if problem:
        return make_result(False, False, problem, rejected_at="input", error=problem)

    # Viva scheduling is group-specific: the permission is CanScheduleViva(name, group_id).
    group = None
    if category == VIVA_CATEGORY:
        group_text = request.get("group_id")
        group = group_text.strip() if isinstance(group_text, str) else ""
        if not group:
            problem = "group_id is required for %s (e.g. G3)." % VIVA_CATEGORY
        elif not CONSTANT_PATTERN.match(group):
            problem = ("group_id '%s' is invalid: it must start with a capital letter (e.g. G3)."
                       % group)
        if problem:
            return make_result(False, False, problem, rejected_at="input", error=problem)
        goal = ("CanScheduleViva", name, group)
    else:
        goal = ("CanRequest", name, category)
    shown = atom_text(goal)

    # --- step 1: role authorization ---
    role_atom = (ROLE_PREDICATE[role], name)
    role_proof = backward_chain(role_atom, find_all=False)
    if not role_proof:
        actual = [r for r in ROLES if backward_chain((ROLE_PREDICATE[r], name), find_all=False)]
        if actual:
            reason = "%s is registered as %s, not as %s." % (name, " / ".join(actual), role)
        else:
            reason = "%s is not a known person on campus." % name
        text = ("Role authorization failed: %s cannot be proven (closed world: unprovable = false). %s"
                % (atom_text(role_atom), reason))
        return make_result(False, False, text, shown, missing=[atom_text(role_atom)],
                           rejected_at="authorization")
    role_sentence = "Step 1 (role authorization) passed: %s." % join_phrases([role_atom])

    # --- step 2: permission ---
    permission = backward_chain(goal, find_all=False)
    if not permission:
        reason, missing = missing_report(goal)
        if group is not None:
            if backward_chain(("FYPGroup", group), find_all=False):
                reason = ("%s is neither a member nor the supervisor of %s. %s" % (name, group, reason))
            else:
                reason = "%s is not a known FYP group. %s" % (group, reason)
        text = "%s Step 2 (permission) failed: %s" % (role_sentence, reason)
        return make_result(False, False, text, shown, role_proof[0]["proof"],
                           missing=missing, rejected_at="permission")
    text = "%s Step 2 (permission) passed: %s" % (role_sentence, explain_answer(permission[0]["tree"]))
    return make_result(True, True, text, shown,
                       merge_proofs(role_proof[0]["proof"], permission[0]["proof"]))


def check_logic(request):
    """
    Function: check_logic
    Purpose : Logic / KB entry point. Eligibility_Check answers the logic query;
              Booking_or_Scheduling / Urgent_Service_Request / Full_Service_Request run
              role authorization and then the CanRequest permission proof.
              Never prints and never raises; problems come back in the result.
    Params  : request (dict) - standard request dict (see shared/templates.py)
    Returns : dict with allowed, entailed, explanation (LOGIC_OUTPUT_TEMPLATE fields)
              plus query, proof (facts and rules used), answers, missing,
              rejected_at and error (see make_result)
    """
    try:
        if not isinstance(request, dict):
            message = "Request must be a dict."
            return make_result(False, False, message, rejected_at="input", error=message)
        raw_type = request.get("request_type")
        canonical = {t.lower(): t for t in [ELIGIBILITY_TYPE] + SERVICE_TYPES}
        request_type = canonical.get(raw_type.strip().lower()) if isinstance(raw_type, str) else None
        if request_type == ELIGIBILITY_TYPE:
            return eligibility_check(request)
        if request_type in SERVICE_TYPES:
            return service_check(request)
        message = ("Logic/KB does not handle request_type '%s'. Expected %s."
                   % (raw_type, ", ".join([ELIGIBILITY_TYPE] + SERVICE_TYPES)))
        return make_result(False, False, message, rejected_at="input", error=message)
    except Exception as exc:          # never let an error escape to the caller
        message = "Logic check failed: %s" % exc
        return make_result(False, False, message, rejected_at="input", error=message)
