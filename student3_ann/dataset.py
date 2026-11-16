"""
File    : student3_ann/dataset.py
Module  : ANN Priority Prediction - synthetic dataset
Owner   : Student 3

Purpose : The handout gives no training data, so the team defines a labelling
          rule (assumption, see CLAUDE.md "ANN design") and generates 1500
          labelled requests with numpy (fixed seed 42, fully reproducible).

          Raw features, in the fixed FEATURE_ORDER x1..x7:
            x1 Role             0-2   (student / instructor / staff)
            x2 RequestType      0-4   (AI_Lab_Support .. Emergency_Help)
            x3 Severity         1-10
            x4 TimeSensitivity  1-10
            x5 CrowdLevel       1-10
            x6 Distance         0-15  (route cost from Search)
            x7 Eligibility      0/1

          Labelling rule:
            score = 0.4*severity + 0.4*time + 0.1*crowd + 0.1*min(distance, 10)
                    + 2 if type == Emergency_Help
                    - 1 if eligibility == 0
            score += Gaussian noise (std 0.3), so the classes overlap a little
            like real data instead of being a perfect formula.
            class : score < 4 low(0), < 6 normal(1), < 8 high(2), else urgent(3)
            binary: 1 (urgent) if class is high or urgent, else 0 (not_urgent)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.campus_data import CATEGORY_ENCODING, ROLE_ENCODING, FEATURE_ORDER

SEED = 42
N_SAMPLES = 1500
NOISE_STD = 0.3
TEST_FRACTION = 0.2

# Largest raw value of each feature; dividing by it puts every input in 0..1
# so no feature dominates the weighted sum just because its numbers are big.
FEATURE_MAX = np.array([2, 4, 10, 10, 10, 15, 1], dtype=float)

EMERGENCY_CODE = CATEGORY_ENCODING["Emergency_Help"]   # 4

# Class boundaries on the score: < 4 low, < 6 normal, < 8 high, else urgent
CLASS_THRESHOLDS = [4.0, 6.0, 8.0]
CLASS_NAMES = ["low", "normal", "high", "urgent"]       # labels 0..3
BINARY_NAMES = ["not_urgent", "urgent"]                 # labels 0, 1

# Sanity check: the dataset columns follow the shared feature order.
assert len(FEATURE_ORDER) == len(FEATURE_MAX) == 7
assert max(ROLE_ENCODING.values()) == FEATURE_MAX[0]
assert max(CATEGORY_ENCODING.values()) == FEATURE_MAX[1]


def priority_score(X):
    """
    Function: priority_score
    Purpose : Apply the team's labelling formula (without noise) to raw rows.
    Params  : X (numpy array, shape (n, 7)) - raw, unscaled features
    Returns : numpy array, shape (n,) - the score of each row
    """
    severity, time_s, crowd, distance, eligible = X[:, 2], X[:, 3], X[:, 4], X[:, 5], X[:, 6]
    score = 0.4 * severity + 0.4 * time_s + 0.1 * crowd + 0.1 * np.minimum(distance, 10)
    score = score + np.where(X[:, 1] == EMERGENCY_CODE, 2.0, 0.0)
    score = score + np.where(eligible == 0, -1.0, 0.0)
    return score


def score_to_class(score):
    """
    Function: score_to_class
    Purpose : Turn scores into class labels 0..3 using CLASS_THRESHOLDS.
    Params  : score (numpy array or float)
    Returns : numpy int array - 0 low, 1 normal, 2 high, 3 urgent
    """
    # np.digitize counts how many thresholds each score has passed.
    return np.digitize(score, CLASS_THRESHOLDS).astype(int)


def class_to_binary(y_class):
    """
    Function: class_to_binary
    Purpose : Collapse the 4 classes to the Perceptron's 2 classes.
    Params  : y_class (numpy int array) - labels 0..3
    Returns : numpy int array - 1 if high or urgent, else 0
    """
    return (np.asarray(y_class) >= 2).astype(int)


def scale_features(X):
    """
    Function: scale_features
    Purpose : Divide each raw feature by FEATURE_MAX so inputs are in 0..1.
    Params  : X (numpy array, shape (n, 7) or (7,)) - raw features
    Returns : numpy float array of the same shape
    """
    return np.asarray(X, dtype=float) / FEATURE_MAX


def generate_dataset(seed=SEED, n=N_SAMPLES):
    """
    Function: generate_dataset
    Purpose : Draw n random raw requests and label them with the noisy score.
    Params  : seed (int) - random seed (default 42), n (int) - number of rows
    Returns : (X_raw, y_class, y_binary) - raw features (n, 7) and labels (n,)
    """
    rng = np.random.default_rng(seed)
    X = np.column_stack([
        rng.integers(0, 3, n),      # x1 Role 0-2
        rng.integers(0, 5, n),      # x2 RequestType 0-4
        rng.integers(1, 11, n),     # x3 Severity 1-10
        rng.integers(1, 11, n),     # x4 TimeSensitivity 1-10
        rng.integers(1, 11, n),     # x5 CrowdLevel 1-10
        rng.integers(0, 16, n),     # x6 Distance 0-15
        rng.integers(0, 2, n),      # x7 Eligibility 0/1
    ]).astype(float)
    noisy_score = priority_score(X) + rng.normal(0.0, NOISE_STD, n)
    y_class = score_to_class(noisy_score)
    return X, y_class, class_to_binary(y_class)


def train_test_split(X, y_class, y_binary, seed=SEED, test_fraction=TEST_FRACTION):
    """
    Function: train_test_split
    Purpose : Shuffle the rows with a fixed seed and cut them 80% / 20%.
    Params  : X, y_class, y_binary (numpy arrays with the same row count),
              seed (int), test_fraction (float)
    Returns : dict with X_train, X_test (scaled), X_train_raw, X_test_raw,
              yc_train, yc_test (4-class) and yb_train, yb_test (binary)
    """
    order = np.random.default_rng(seed).permutation(len(X))
    n_test = int(round(len(X) * test_fraction))
    test_idx, train_idx = order[:n_test], order[n_test:]
    return {
        "X_train_raw": X[train_idx], "X_test_raw": X[test_idx],
        "X_train": scale_features(X[train_idx]), "X_test": scale_features(X[test_idx]),
        "yc_train": y_class[train_idx], "yc_test": y_class[test_idx],
        "yb_train": y_binary[train_idx], "yb_test": y_binary[test_idx],
    }


def load_data(seed=SEED):
    """
    Function: load_data
    Purpose : One call that generates the dataset and splits it.
    Params  : seed (int) - used for both generation and the split
    Returns : dict - see train_test_split
    """
    X, y_class, y_binary = generate_dataset(seed)
    return train_test_split(X, y_class, y_binary, seed)
