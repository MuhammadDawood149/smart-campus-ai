"""
File    : student3_ann/ann_module.py
Module  : ANN Priority Prediction - entry point
Owner   : Student 3

Purpose : predict_priority(features) is the function the rest of the system
          calls. It takes the raw (unscaled) feature vector in FEATURE_ORDER
              [Role, RequestType, Severity, TimeSensitivity, CrowdLevel,
               Distance, Eligibility]          e.g. [0, 0, 8, 9, 5, 4, 1]
          and returns PRIORITY_OUTPUT_TEMPLATE filled in like the handout:
              binary_priority  "urgent" / "not_urgent"        (Perceptron)
              final_priority   "low" / "normal" / "high" / "urgent"  (MLP)
              confidence       highest MLP softmax probability, 2 decimals
          The MLP result is the one used for scheduling; the Perceptron is
          the baseline shown for comparison (handout Phase 2, section 3.2).
          Never prints and never raises: bad input returns the empty template
          plus an "error" field explaining what is wrong.
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dataset as ds
import mlp
import perceptron as pc
import train
from shared.campus_data import FEATURE_ORDER
from shared.templates import PRIORITY_OUTPUT_TEMPLATE, new_template

# Allowed raw range for each feature (inclusive), in FEATURE_ORDER, and
# whether the value is a code that must be a whole number.
FEATURE_RULES = [
    ("Role", 0, 2, True),
    ("RequestType", 0, 4, True),
    ("Severity", 1, 10, False),
    ("TimeSensitivity", 1, 10, False),
    ("CrowdLevel", 1, 10, False),
    ("Distance", 0, None, False),     # no upper limit; above 15 is capped at 15
    ("Eligibility", 0, 1, True),
]
assert [rule[0] for rule in FEATURE_RULES] == FEATURE_ORDER

# Models are loaded (or trained) once, on first use, then kept here.
_CACHE = {"models": None, "source": ""}


def load_models(retrain=False):
    """
    Function: load_models
    Purpose : Get the trained models (from weights.json, or train and save
              them) and keep them for later predictions.
    Params  : retrain (bool) - True forces fresh training
    Returns : (models, source) - see train.get_models
    """
    if retrain or _CACHE["models"] is None:
        _CACHE["models"], _CACHE["source"] = train.get_models(retrain=retrain)
    return _CACHE["models"], _CACHE["source"]


def models_loaded():
    """
    Function: models_loaded
    Purpose : Tell whether the models are already in memory.
    Params  : None
    Returns : bool
    """
    return _CACHE["models"] is not None


def validate_features(features):
    """
    Function: validate_features
    Purpose : Check the raw feature vector: a list/tuple of exactly 7 finite
              numbers, each inside its allowed range (True/False count as
              1/0 for Eligibility). Distance above 15 is capped at 15, the
              largest distance in the training data.
    Params  : features - anything the caller passed
    Returns : (values, "") with a list of 7 floats, or (None, error message)
    """
    if isinstance(features, np.ndarray):
        features = features.tolist()
    if not isinstance(features, (list, tuple)):
        return None, "features must be a list of 7 numbers in FEATURE_ORDER, got %s" % type(features).__name__
    if len(features) != len(FEATURE_ORDER):
        return None, "expected 7 features (%s), got %d" % (", ".join(FEATURE_ORDER), len(features))
    values = []
    for raw, (name, low, high, whole) in zip(features, FEATURE_RULES):
        if isinstance(raw, (bool, np.bool_)):
            raw = int(raw)
        if not isinstance(raw, (int, float, np.integer, np.floating)):
            return None, "%s must be a number, got %r" % (name, raw)
        value = float(raw)
        if not math.isfinite(value):
            return None, "%s must be a finite number, got %r" % (name, raw)
        if whole and value != int(value):
            return None, "%s must be a whole number (a code), got %r" % (name, raw)
        if value < low or (high is not None and value > high):
            limit = "%s to %s" % (low, high) if high is not None else "at least %s" % low
            return None, "%s must be %s, got %r" % (name, limit, raw)
        values.append(value)
    values[5] = min(values[5], ds.FEATURE_MAX[5])   # cap Distance at 15
    return values, ""


def error_result(message):
    """
    Function: error_result
    Purpose : The empty priority template plus an error message.
    Params  : message (str)
    Returns : dict
    """
    result = new_template(PRIORITY_OUTPUT_TEMPLATE)
    result["error"] = message
    return result


def explain_prediction(features):
    """
    Function: explain_prediction
    Purpose : Same as predict_priority, plus the details used in the demo /
              viva: scaled inputs, the Perceptron's weighted sum and the MLP
              probability of every class.
    Params  : features (list of 7 raw numbers in FEATURE_ORDER)
    Returns : dict - template fields + "scaled_features", "perceptron_sum",
              "probabilities" {class: p}; or the error result
    """
    values, error = validate_features(features)
    if error:
        return error_result(error)
    try:
        models, _ = load_models()
        x = ds.scale_features(values)
        z = float(pc.weighted_sum(models["perceptron"], x))
        probs = mlp.predict_proba(models["mlp"], x)[0]
    except Exception as exc:    # never let a model problem crash the caller
        return error_result("ANN model unavailable: %s" % exc)

    best = int(np.argmax(probs))
    result = new_template(PRIORITY_OUTPUT_TEMPLATE)
    result["binary_priority"] = ds.BINARY_NAMES[int(pc.step(z))]
    result["final_priority"] = ds.CLASS_NAMES[best]
    result["confidence"] = round(float(probs[best]), 2)
    result["scaled_features"] = [round(float(v), 4) for v in x]
    result["perceptron_sum"] = round(z, 4)
    result["probabilities"] = {name: round(float(p), 4) for name, p in zip(ds.CLASS_NAMES, probs)}
    return result


def hidden_activations(features):
    """
    Function: hidden_activations
    Purpose : The sigmoid outputs of both MLP hidden layers for one request,
              so the web UI can light up the 7 -> 4 -> 3 -> 4 network.
              Read-only: uses the same forward pass as predict_priority.
    Params  : features (list of 7 raw numbers in FEATURE_ORDER)
    Returns : dict {"hidden1": 4 floats, "hidden2": 3 floats}; or the error result
    """
    values, error = validate_features(features)
    if error:
        return error_result(error)
    try:
        models, _ = load_models()
        cache = mlp.forward(models["mlp"], np.atleast_2d(ds.scale_features(values)))
    except Exception as exc:    # never let a model problem crash the caller
        return error_result("ANN model unavailable: %s" % exc)
    return {"hidden1": [round(float(v), 4) for v in cache["A1"][0]],
            "hidden2": [round(float(v), 4) for v in cache["A2"][0]]}


def predict_priority(features):
    """
    Function: predict_priority
    Purpose : Entry point - predict the priority of one request.
    Params  : features (list of 7 raw numbers in FEATURE_ORDER),
              e.g. [0, 0, 8, 9, 5, 4, 1]
    Returns : dict PRIORITY_OUTPUT_TEMPLATE, e.g. {"binary_priority": "urgent",
              "final_priority": "high", "confidence": 0.76}; on bad input the
              empty template plus an "error" field
    """
    details = explain_prediction(features)
    if "error" in details:
        return details
    return {key: details[key] for key in PRIORITY_OUTPUT_TEMPLATE}
