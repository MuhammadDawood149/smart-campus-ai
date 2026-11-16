"""
File    : student3_ann/ann_cli.py
Module  : ANN Priority Prediction demo
Owner   : Student 3

Purpose : Menu-driven demo of Student 3's part: train / retrain both models,
          show test accuracy, confusion matrices and the Perceptron-vs-MLP
          comparison, enter a feature vector by hand and predict it, and run
          the handout example [0, 0, 8, 9, 5, 4, 1]. Invalid input is
          re-asked, never a crash.
Run     : python student3_ann/ann_cli.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ann_module as am
import dataset as ds
import mlp
import train
from shared.campus_data import ROLE_ENCODING, CATEGORY_ENCODING

HANDOUT_EXAMPLE = [0, 0, 8, 9, 5, 4, 1]

# Extra help shown when asking for each feature, in FEATURE_ORDER
FEATURE_HINTS = [
    ", ".join("%d=%s" % (code, name) for name, code in ROLE_ENCODING.items()),
    ", ".join("%d=%s" % (code, name) for name, code in CATEGORY_ENCODING.items()),
    "1-10", "1-10", "1-10",
    "route cost, 0 or more",
    "1=eligible, 0=not eligible",
]


def read_line(prompt):
    """
    Function: read_line
    Purpose : input() that treats Ctrl+C / end of input as "leave the program".
    Params  : prompt (str)
    Returns : str, or None when input is closed
    """
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def ask_feature(index):
    """
    Function: ask_feature
    Purpose : Ask for one feature until a number inside its range is given.
    Params  : index (int) - position in FEATURE_ORDER (0..6)
    Returns : int or float, or None if input is closed
    """
    name, low, high, whole = am.FEATURE_RULES[index]
    while True:
        text = read_line("  x%d %s (%s): " % (index + 1, name, FEATURE_HINTS[index]))
        if text is None:
            return None
        try:
            value = float(text.strip())
        except ValueError:
            print("  Please enter a number.")
            continue
        if whole and value != int(value):
            print("  Please enter a whole number.")
        elif value < low or (high is not None and value > high):
            print("  Out of range (%s)." % FEATURE_HINTS[index])
        else:
            return int(value) if value == int(value) else value


def show_prediction(features):
    """
    Function: show_prediction
    Purpose : Predict one feature vector and print the result and details.
    Params  : features (list of 7 raw numbers)
    Returns : None
    """
    result = am.explain_prediction(features)
    print("\nInput x = %s" % features)
    if "error" in result:
        print("Error: %s" % result["error"])
        return
    print("Scaled  = %s" % result["scaled_features"])
    print("Perceptron weighted sum z = %.4f -> step(z) = %s"
          % (result["perceptron_sum"], result["binary_priority"]))
    print("MLP softmax probabilities:")
    for name, p in result["probabilities"].items():
        print("  %-7s %.4f %s" % (name, p, "#" * int(round(p * 40))))
    print("\nOutput:")
    print("  binary_priority : %s   (Perceptron baseline)" % result["binary_priority"])
    print("  final_priority  : %s   (MLP, used for scheduling)" % result["final_priority"])
    print("  confidence      : %.2f" % result["confidence"])


def print_matrix(matrix, labels):
    """
    Function: print_matrix
    Purpose : Print a confusion matrix with row (true) / column (predicted) labels.
    Params  : matrix (list of lists of int), labels (list of str)
    Returns : None
    """
    width = max(8, max(len(label) for label in labels) + 2)
    print("  %-12s" % "true \\ pred" + "".join(label.rjust(width) for label in labels))
    for label, row in zip(labels, matrix):
        print("  %-12s" % label + "".join(str(v).rjust(width) for v in row))


def get_models(retrain=False):
    """
    Function: get_models
    Purpose : Load or train the models, telling the user what happened.
    Params  : retrain (bool) - True forces fresh training
    Returns : models dict, or None if loading and training both failed
    """
    if retrain or (not am.models_loaded() and train.load_weights() is None):
        print("Training both models (MLP: %d epochs, about 5-10 seconds)..." % mlp.EPOCHS)
    start = time.time()
    try:
        models, source = am.load_models(retrain=retrain)
    except Exception as exc:
        print("Could not load or train the models: %s" % exc)
        return None
    if source != "loaded" or retrain:
        print("Models %s in %.1f s (weights file: %s)." % (source, time.time() - start, train.WEIGHTS_PATH))
    return models


def show_evaluation():
    """
    Function: show_evaluation
    Purpose : Print test accuracy, both confusion matrices, the comparison and
              the training history.
    Params  : None
    Returns : None
    """
    models = get_models()
    if models is None:
        return
    report = train.evaluate(models)
    cmp_ = report["comparison"]
    print("\nDataset: %d training / %d test samples (seed %d)"
          % (report["n_train"], report["n_test"], models["config"]["seed"]))

    print("\n--- MLP 7-4-3-4 (4 classes) ---")
    print("Test accuracy: MLP %.2f%% vs ceiling %.2f%%"
          % (100 * report["mlp_accuracy"], 100 * report["noise_ceiling"]))
    print("(ceiling = the noise-free labelling formula scored on the noisy test labels)")
    print_matrix(report["mlp_confusion"], ds.CLASS_NAMES)

    print("\n--- Perceptron (binary) ---")
    print("Test accuracy: %.2f%%" % (100 * report["perceptron_accuracy"]))
    print_matrix(report["perceptron_confusion"], ds.BINARY_NAMES)

    print("\n--- Comparison on the same binary task (MLP high/urgent -> urgent) ---")
    print("  Perceptron : %.2f%%" % (100 * cmp_["perceptron_binary_accuracy"]))
    print("  MLP        : %.2f%%" % (100 * cmp_["mlp_binary_accuracy"]))
    print("  MLP binary confusion matrix:")
    print_matrix(cmp_["mlp_binary_confusion"], ds.BINARY_NAMES)
    print("  The two models agree on %.2f%% of test samples. Better: %s"
          % (100 * cmp_["agreement"], cmp_["better"]))

    history = models["mlp_loss_history"]      # [epoch, loss] every 100 epochs
    if history:
        last = history[-1][0]
        marks = {1, last // 20, last // 4, last // 2, last}
        print("\nMLP cross-entropy loss: " + ", ".join(
            "epoch %d: %.4f" % (e, loss) for e, loss in history if e in marks))
    errors = models["perceptron_errors"]
    if errors:
        marks = sorted({1, 10, 25, len(errors)} & set(range(1, len(errors) + 1)))
        print("Perceptron training mistakes: " + ", ".join("epoch %d: %d" % (e, errors[e - 1]) for e in marks))
        print("(The data is not perfectly linearly separable, so the Perceptron never reaches 0.)")


def enter_vector():
    """
    Function: enter_vector
    Purpose : Ask for the 7 features one by one, then predict.
    Params  : None
    Returns : None
    """
    print("Enter the raw feature values (FEATURE_ORDER x1..x7):")
    features = []
    for index in range(len(am.FEATURE_RULES)):
        value = ask_feature(index)
        if value is None:
            return
        features.append(value)
    if get_models() is not None:
        show_prediction(features)


def run_example():
    """
    Function: run_example
    Purpose : Run the handout example (student, AI_Lab_Support, severity 8,
              time 9, crowd 5, distance 4, eligible). Handout expects
              binary "urgent", final "high".
    Params  : None
    Returns : None
    """
    print("Handout example: student, AI_Lab_Support, severity 8, time 9, crowd 5, distance 4, eligible")
    if get_models() is not None:
        show_prediction(HANDOUT_EXAMPLE)


def main():
    """
    Function: main
    Purpose : Show the menu until the user chooses Exit.
    Params  : None
    Returns : None
    """
    while True:
        print("\n=== ANN Priority Prediction ===")
        print("1. Train / retrain the models\n2. Show accuracy, confusion matrices and comparison")
        print("3. Enter a feature vector and predict\n4. Run the handout example\n5. Exit")
        choice = read_line("Choose 1-5: ")
        if choice is None or choice.strip() == "5":
            print("Goodbye.")
            return
        choice = choice.strip()
        if choice == "1":
            get_models(retrain=True)
        elif choice == "2":
            show_evaluation()
        elif choice == "3":
            enter_vector()
        elif choice == "4":
            run_example()
        else:
            print("Please enter a number from 1 to 5.")


if __name__ == "__main__":
    main()
