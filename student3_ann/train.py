"""
File    : student3_ann/train.py
Module  : ANN Priority Prediction - training, evaluation, saved weights
Owner   : Student 3

Purpose : Trains the Perceptron (binary) and the MLP (4 classes) on the
          dataset from dataset.py, evaluates both on the 20% test set
          (accuracy + confusion matrices) and compares them like for like
          (MLP classes collapsed to urgent / not_urgent).
          The MLP accuracy is reported next to the noise ceiling: the
          accuracy of the noise-free labelling formula itself on the noisy
          test labels. No model can be expected to beat it by much, because
          the labels were made with random noise the features cannot show.
          Trained weights are saved to student3_ann/weights.json and loaded
          from there next time instead of retraining. The file also stores
          the training settings; if they no longer match the code, the file
          is ignored and the models are retrained. To keep the file small,
          the MLP loss is stored only every LOSS_EVERY (100) epochs.
          Never prints when imported and never raises on a bad weights file;
          running this file directly prints a short summary.
Run     : python student3_ann/train.py
"""

import json
import os
import sys

import numpy as np

# This folder on the path, so the sibling files import the same way whether
# train.py is run from here or imported from the project root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dataset as ds
import mlp
import perceptron as pc

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights.json")

# The MLP loss is recorded every epoch during training, but only epoch 1 and
# every 100th epoch are kept in the models dict and in weights.json.
LOSS_EVERY = 100

# Every setting that changes the trained weights (or the file format). Saved
# next to the weights so a file made with other settings is never used.
CONFIG = {
    "seed": ds.SEED,
    "n_samples": ds.N_SAMPLES,
    "noise_std": ds.NOISE_STD,
    "test_fraction": ds.TEST_FRACTION,
    "feature_max": ds.FEATURE_MAX.tolist(),
    "perceptron": {"learning_rate": pc.LEARNING_RATE, "epochs": pc.EPOCHS},
    "mlp": {"layers": mlp.LAYER_SIZES, "learning_rate": mlp.LEARNING_RATE, "epochs": mlp.EPOCHS},
    "loss_every": LOSS_EVERY,
}

MLP_KEYS = ["W1", "b1", "W2", "b2", "W3", "b3"]


def sample_losses(losses, every=LOSS_EVERY):
    """
    Function: sample_losses
    Purpose : Keep the loss of epoch 1 and of every `every`-th epoch (and the
              last epoch, if it is not already included).
    Params  : losses (list of float) - one loss per epoch, epoch 1 first
              every (int) - keep one value per this many epochs
    Returns : list of [epoch, loss] pairs, e.g. [[1, 1.41], [100, 1.09], ...]
    """
    if not losses:
        return []
    epochs = sorted({1, len(losses)} | set(range(every, len(losses) + 1, every)))
    return [[e, float(losses[e - 1])] for e in epochs]


def train_models(seed=ds.SEED):
    """
    Function: train_models
    Purpose : Generate the data and train both models from scratch.
    Params  : seed (int) - seed for the data, the split and the MLP weights
    Returns : dict {"perceptron", "mlp", "perceptron_errors",
              "mlp_loss_history", "config"} - the models are dicts of numpy
              arrays; mlp_loss_history is a list of [epoch, loss] pairs
    """
    data = ds.load_data(seed)
    p_model, p_errors = pc.train_perceptron(data["X_train"], data["yb_train"])
    m_model, m_losses = mlp.train_mlp(data["X_train"], data["yc_train"], seed=seed)
    config = dict(CONFIG, seed=seed)
    return {"perceptron": p_model, "mlp": m_model, "perceptron_errors": p_errors,
            "mlp_loss_history": sample_losses(m_losses), "config": config}


def accuracy(y_true, y_pred):
    """
    Function: accuracy
    Purpose : Fraction of predictions that match the true labels.
    Params  : y_true, y_pred (numpy int arrays of equal length)
    Returns : float in 0..1
    """
    return float(np.mean(np.asarray(y_true) == np.asarray(y_pred)))


def noise_ceiling(data):
    """
    Function: noise_ceiling
    Purpose : Accuracy of the noise-free labelling formula on the noisy test
              labels. Scores that sit on or near a class boundary (4, 6, 8)
              get flipped by the noise, so even the exact formula misses
              them; this is the realistic best a model can do.
    Params  : data (dict from dataset.load_data)
    Returns : float in 0..1
    """
    clean_labels = ds.score_to_class(ds.priority_score(data["X_test_raw"]))
    return accuracy(data["yc_test"], clean_labels)


def confusion_matrix(y_true, y_pred, n_classes):
    """
    Function: confusion_matrix
    Purpose : Count how often each true class was predicted as each class.
              Row = true class, column = predicted class; the diagonal holds
              the correct predictions.
    Params  : y_true, y_pred (numpy int arrays), n_classes (int)
    Returns : list of lists (n_classes x n_classes) of ints
    """
    matrix = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        matrix[int(t), int(p)] += 1
    return matrix.tolist()


def evaluate(models, seed=None):
    """
    Function: evaluate
    Purpose : Test-set accuracy and confusion matrices for both models, the
              noise ceiling, plus the Perceptron-vs-MLP comparison on the
              same binary task.
    Params  : models (dict from train_models / load_weights),
              seed (int or None) - data seed; None = the one the models used
    Returns : dict report (see keys below)
    """
    seed = models["config"]["seed"] if seed is None else seed
    data = ds.load_data(seed)
    X_test, yc_test, yb_test = data["X_test"], data["yc_test"], data["yb_test"]

    mlp_pred = mlp.predict(models["mlp"], X_test)
    perc_pred = pc.predict(models["perceptron"], X_test)
    # Like-for-like comparison: low/normal -> not_urgent, high/urgent -> urgent
    mlp_binary = ds.class_to_binary(mlp_pred)

    perc_acc = accuracy(yb_test, perc_pred)
    mlp_bin_acc = accuracy(yb_test, mlp_binary)
    if abs(perc_acc - mlp_bin_acc) < 1e-12:
        better = "tie"
    else:
        better = "MLP" if mlp_bin_acc > perc_acc else "Perceptron"

    history = models.get("mlp_loss_history") or [[0, float("nan")]]
    return {
        "n_train": int(len(data["X_train"])),
        "n_test": int(len(X_test)),
        "mlp_accuracy": accuracy(yc_test, mlp_pred),
        "noise_ceiling": noise_ceiling(data),
        "mlp_confusion": confusion_matrix(yc_test, mlp_pred, 4),
        "perceptron_accuracy": perc_acc,
        "perceptron_confusion": confusion_matrix(yb_test, perc_pred, 2),
        "comparison": {
            "perceptron_binary_accuracy": perc_acc,
            "mlp_binary_accuracy": mlp_bin_acc,
            "mlp_binary_confusion": confusion_matrix(yb_test, mlp_binary, 2),
            "agreement": accuracy(perc_pred, mlp_binary),
            "better": better,
        },
        "mlp_first_loss": float(history[0][1]),
        "mlp_final_loss": float(history[-1][1]),
        "mlp_epochs": int(history[-1][0]),
    }


def save_weights(models, path=WEIGHTS_PATH):
    """
    Function: save_weights
    Purpose : Write both models (numpy arrays as lists), the training history
              (loss every LOSS_EVERY epochs) and the config to a JSON file.
    Params  : models (dict), path (str)
    Returns : (ok, message) - (True, "") or (False, reason)
    """
    payload = {
        "config": models["config"],
        "perceptron": {"w": models["perceptron"]["w"].tolist(), "b": float(models["perceptron"]["b"])},
        "mlp": {key: models["mlp"][key].tolist() for key in MLP_KEYS},
        "perceptron_errors": [int(e) for e in models["perceptron_errors"]],
        "mlp_loss_history": [[int(e), float(v)] for e, v in models["mlp_loss_history"]],
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return True, ""
    except (OSError, TypeError, ValueError) as exc:
        return False, "could not save weights: %s" % exc


def load_weights(path=WEIGHTS_PATH, expected_config=None):
    """
    Function: load_weights
    Purpose : Read a weights file back into numpy arrays. Checks the config
              and every array shape, so a stale or broken file is ignored.
    Params  : path (str), expected_config (dict or None) - default CONFIG
    Returns : models dict like train_models, or None if missing / invalid
    """
    expected_config = CONFIG if expected_config is None else expected_config
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("config") != expected_config:
            return None
        sizes = mlp.LAYER_SIZES
        m_model = {key: np.array(payload["mlp"][key], dtype=float) for key in MLP_KEYS}
        for layer in range(1, len(sizes)):
            if m_model["W%d" % layer].shape != (sizes[layer - 1], sizes[layer]):
                return None
            if m_model["b%d" % layer].shape != (sizes[layer],):
                return None
        p_model = {"w": np.array(payload["perceptron"]["w"], dtype=float),
                   "b": float(payload["perceptron"]["b"])}
        if p_model["w"].shape != (pc.N_INPUTS,):
            return None
        all_values = [p_model["w"], np.array([p_model["b"]])] + list(m_model.values())
        if not all(np.all(np.isfinite(v)) for v in all_values):
            return None
        history = [[int(e), float(v)] for e, v in payload["mlp_loss_history"]]
        return {"perceptron": p_model, "mlp": m_model,
                "perceptron_errors": [int(e) for e in payload["perceptron_errors"]],
                "mlp_loss_history": history,
                "config": payload["config"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def get_models(path=WEIGHTS_PATH, retrain=False):
    """
    Function: get_models
    Purpose : Load saved weights if a valid file exists; otherwise (or when
              retrain is True) train both models and save them.
    Params  : path (str), retrain (bool) - True forces fresh training
    Returns : (models, source) - source is "loaded", "trained" or
              "trained (not saved: <reason>)"
    """
    if not retrain:
        models = load_weights(path)
        if models is not None:
            return models, "loaded"
    models = train_models()
    ok, message = save_weights(models, path)
    return models, "trained" if ok else "trained (not saved: %s)" % message


def main():
    """
    Function: main
    Purpose : Script entry: load or train the models and print the headline
              numbers. Only runs when this file is executed directly, so the
              module itself stays print-free when imported.
    Params  : None
    Returns : None
    """
    models, source = get_models()
    report = evaluate(models)
    print("Models %s (%s)" % (source, WEIGHTS_PATH))
    print("MLP %.2f%% vs ceiling %.2f%%" % (100 * report["mlp_accuracy"], 100 * report["noise_ceiling"]))
    print("Perceptron (binary) %.2f%%, MLP collapsed to binary %.2f%%"
          % (100 * report["perceptron_accuracy"], 100 * report["comparison"]["mlp_binary_accuracy"]))


if __name__ == "__main__":
    main()
