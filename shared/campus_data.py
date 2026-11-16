"""
File    : shared/campus_data.py
Module  : Shared data (no AI logic)
Owner   : Joint (shared by all three students)

Purpose : Holds the verified campus graph (13 nodes, 19 undirected weighted
          edges), node coordinates, request categories, user roles and the
          ANN encodings. Every other module imports its data from here.

Verified: 13 nodes, 19 edges, degree sum 38, total cost 44.
          There is NO Science_Block-Library edge.
"""

# ---------------------------------------------------------------------------
# Nodes with (x, y) coordinates on the campus diagram
# ---------------------------------------------------------------------------
NODES = {
    "Main_Gate": (0, 4),
    "Parking": (2, 4),
    "Admin_Block": (3, 5),
    "Student_Services": (6, 5),
    "Exam_Hall": (8, 5),
    "Seminar_Room": (10, 4),
    "Library": (6, 2),
    "AI_Lab": (9, 2),
    "Bus_Stop": (0, 1),
    "Medical_Center": (1, 1),
    "Cafeteria": (4, 1),
    "Science_Block": (7, 1),
    "Hostel": (2, 0),
}

# ---------------------------------------------------------------------------
# Undirected weighted edges: (node_a, node_b, cost)
# The unweighted and weighted diagrams share the same 19 connections.
# ---------------------------------------------------------------------------
EDGES = [
    ("Main_Gate", "Bus_Stop", 1),
    ("Main_Gate", "Parking", 2),
    ("Main_Gate", "Admin_Block", 4),
    ("Main_Gate", "Hostel", 5),
    ("Parking", "Bus_Stop", 2),
    ("Parking", "Science_Block", 3),
    ("Admin_Block", "Student_Services", 1),
    ("Admin_Block", "Exam_Hall", 2),
    ("Student_Services", "Library", 2),
    ("Exam_Hall", "Seminar_Room", 1),
    ("Exam_Hall", "Science_Block", 3),
    ("Seminar_Room", "Science_Block", 2),
    ("Library", "Cafeteria", 2),
    ("Library", "AI_Lab", 3),
    ("AI_Lab", "Science_Block", 1),
    ("Bus_Stop", "Medical_Center", 2),
    ("Medical_Center", "Hostel", 3),
    ("Hostel", "Cafeteria", 2),
    ("Cafeteria", "Science_Block", 3),
]

# Assumption: the Lab1 used in the logic knowledge base is the AI_Lab node.
LAB1_NODE = "AI_Lab"

# ---------------------------------------------------------------------------
# Request categories and user roles (names follow the ANN encoding)
# ---------------------------------------------------------------------------
CATEGORIES = [
    "AI_Lab_Support",
    "Viva_Scheduling",
    "Access_Request",
    "Maintenance",
    "Emergency_Help",
]

ROLES = ["student", "instructor", "staff"]

# ---------------------------------------------------------------------------
# ANN encodings
# ---------------------------------------------------------------------------
ROLE_ENCODING = {"student": 0, "instructor": 1, "staff": 2}

CATEGORY_ENCODING = {
    "AI_Lab_Support": 0,
    "Viva_Scheduling": 1,
    "Access_Request": 2,
    "Maintenance": 3,
    "Emergency_Help": 4,
}

# Input ranges (handout Phase 2, sections 1.3-1.4): Severity, TimeSensitivity
# and CrowdLevel are raw integers 1-10; no extra encoding is applied.
# Eligibility is boolean (True -> 1, False -> 0). Distance is the route cost
# from Search. preferred_slot must be one of TIME_SLOTS.
SCALE_MIN = 1
SCALE_MAX = 10
TIME_SLOTS = [1, 2, 3, 4]

# Fixed ANN input order: x1..x7
FEATURE_ORDER = [
    "Role",             # x1
    "RequestType",      # x2
    "Severity",         # x3
    "TimeSensitivity",  # x4
    "CrowdLevel",       # x5
    "Distance",         # x6
    "Eligibility",      # x7
]

# MLP output classes (index 0..3); the Perceptron outputs Urgent {0, 1}
PRIORITY_LEVELS = ["Low", "Normal", "High", "Urgent"]
