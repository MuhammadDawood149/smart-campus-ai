"""
File    : student3_ann/test_ann.py
Module  : ANN Priority Prediction tests
Owner   : Student 3

Purpose : unittest checks for the dataset, Perceptron, MLP, training /
          evaluation, saved weights and the predict_priority entry point:
          handout example, accuracy targets, reproducibility, save/load,
          bad input and an Emergency_Help example.
Run     : python -m unittest student3_ann.test_ann -v
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ann_module as am
import dataset as ds
import mlp
import perceptron as pc
import train
from shared.templates import PRIORITY_OUTPUT_TEMPLATE

HANDOUT_EXAMPLE = [0, 0, 8, 9, 5, 4, 1]
# Emergency_Help (4), severity 9, time 9: score = 3.6 + 3.6 + 0.5 + 0.3 + 2 = 10
EMERGENCY_EXAMPLE = [0, 4, 9, 9, 5, 3, 1]


def same_models(a, b):
    """
    Function: same_models
    Purpose : True if two model dicts hold exactly the same weights.
    Params  : a, b (dicts from train_models / load_weights)
    Returns : bool
    """
    if not np.array_equal(a["perceptron"]["w"], b["perceptron"]["w"]):
        return False
    if a["perceptron"]["b"] != b["perceptron"]["b"]:
        return False
    return all(np.array_equal(a["mlp"][k], b["mlp"][k]) for k in train.MLP_KEYS)


class TestDataset(unittest.TestCase):
    """The synthetic dataset follows the team-defined rule."""

    def test_shape_and_ranges(self):
        """1500 rows, 7 features, every feature inside its stated range."""
        X, y_class, y_binary = ds.generate_dataset()
        self.assertEqual(X.shape, (1500, 7))
        lows, highs = [0, 0, 1, 1, 1, 0, 0], [2, 4, 10, 10, 10, 15, 1]
        for col in range(7):
            self.assertGreaterEqual(X[:, col].min(), lows[col])
            self.assertLessEqual(X[:, col].max(), highs[col])
        self.assertEqual(set(y_class.tolist()), {0, 1, 2, 3})
        self.assertTrue(np.array_equal(y_binary, (y_class >= 2).astype(int)))

    def test_split_and_scaling(self):
        """80/20 split; scaled features are all in 0..1."""
        data = ds.load_data()
        self.assertEqual(len(data["X_train"]), 1200)
        self.assertEqual(len(data["X_test"]), 300)
        for key in ("X_train", "X_test"):
            self.assertGreaterEqual(data[key].min(), 0.0)
            self.assertLessEqual(data[key].max(), 1.0)

    def test_labelling_rule(self):
        """Score formula and class thresholds on hand-worked rows."""
        rows = np.array([HANDOUT_EXAMPLE, EMERGENCY_EXAMPLE, [0, 0, 1, 1, 1, 0, 0],
                         [0, 0, 5, 5, 5, 15, 1]], dtype=float)
        np.testing.assert_allclose(ds.priority_score(rows), [7.7, 10.0, -0.1, 5.5])
        self.assertEqual(ds.score_to_class(ds.priority_score(rows)).tolist(), [2, 3, 0, 1])
        self.assertEqual(ds.score_to_class(np.array([3.99, 4.0, 6.0, 8.0])).tolist(), [0, 1, 2, 3])


class TestModels(unittest.TestCase):
    """Training, accuracy targets, reproducibility and saved weights."""

    @classmethod
    def setUpClass(cls):
        """Train once from scratch (never from an existing weights file)."""
        cls.models = train.train_models()
        cls.report = train.evaluate(cls.models)

    def test_architecture(self):
        """MLP weights match 7 -> 4 -> 3 -> 4 with a bias on each layer."""
        shapes = {k: self.models["mlp"][k].shape for k in train.MLP_KEYS}
        self.assertEqual(shapes, {"W1": (7, 4), "b1": (4,), "W2": (4, 3), "b2": (3,),
                                  "W3": (3, 4), "b3": (4,)})
        self.assertEqual(self.models["perceptron"]["w"].shape, (7,))
        self.assertEqual(len(self.models["perceptron_errors"]), pc.EPOCHS)

    def test_loss_recorded_per_epoch(self):
        """train_mlp records one loss per epoch; only epoch 1 and every 100th are kept."""
        data = ds.load_data()
        _, losses = mlp.train_mlp(data["X_train"], data["yc_train"], epochs=250)
        self.assertEqual(len(losses), 250)
        history = train.sample_losses(losses)
        self.assertEqual([e for e, _ in history], [1, 100, 200, 250])
        self.assertEqual(history[1][1], losses[99])
        epochs = [e for e, _ in self.models["mlp_loss_history"]]
        self.assertEqual(epochs, [1] + list(range(100, mlp.EPOCHS + 1, 100)))

    def test_loss_decreases(self):
        """Cross-entropy loss falls clearly during training."""
        history = self.models["mlp_loss_history"]
        self.assertLess(history[-1][1], history[0][1] / 3)

    def test_mlp_accuracy(self):
        """MLP 4-class test accuracy is within 3 points of the noise ceiling."""
        data = ds.load_data()
        clean = ds.score_to_class(ds.priority_score(data["X_test_raw"]))
        ceiling = float(np.mean(clean == data["yc_test"]))
        self.assertAlmostEqual(self.report["noise_ceiling"], ceiling)
        self.assertGreaterEqual(self.report["mlp_accuracy"], ceiling - 0.03)

    def test_perceptron_accuracy(self):
        """Perceptron binary test accuracy is at least 80%."""
        self.assertGreaterEqual(self.report["perceptron_accuracy"], 0.80)

    def test_confusion_matrices(self):
        """4x4 and 2x2 matrices; each sums to the test size; diagonal = accuracy."""
        n = self.report["n_test"]
        cases = [(self.report["mlp_confusion"], 4, self.report["mlp_accuracy"]),
                 (self.report["perceptron_confusion"], 2, self.report["perceptron_accuracy"]),
                 (self.report["comparison"]["mlp_binary_confusion"], 2,
                  self.report["comparison"]["mlp_binary_accuracy"])]
        for matrix, size, acc in cases:
            m = np.array(matrix)
            self.assertEqual(m.shape, (size, size))
            self.assertEqual(m.sum(), n)
            self.assertAlmostEqual(np.trace(m) / n, acc)

    def test_comparison(self):
        """Comparison uses the same binary labels for both models."""
        comp = self.report["comparison"]
        self.assertEqual(comp["perceptron_binary_accuracy"], self.report["perceptron_accuracy"])
        self.assertIn(comp["better"], ("MLP", "Perceptron", "tie"))
        self.assertGreaterEqual(comp["agreement"], 0.0)
        self.assertLessEqual(comp["agreement"], 1.0)

    def test_same_seed_same_results(self):
        """Training again with the same seed gives identical weights and losses."""
        again = train.train_models()
        self.assertTrue(same_models(self.models, again))
        self.assertEqual(self.models["mlp_loss_history"], again["mlp_loss_history"])
        self.assertEqual(self.models["perceptron_errors"], again["perceptron_errors"])
        self.assertEqual(train.evaluate(again), self.report)
        X1, _, _ = ds.generate_dataset(seed=42)
        X2, _, _ = ds.generate_dataset(seed=7)
        self.assertFalse(np.array_equal(X1, X2))

    def test_save_and_load(self):
        """Saved weights load back identically and give the same predictions."""
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "weights.json")
            ok, message = train.save_weights(self.models, path)
            self.assertTrue(ok, message)
            loaded = train.load_weights(path)
            self.assertIsNotNone(loaded)
            X_test = ds.load_data()["X_test"]
            self.assertTrue(np.array_equal(mlp.predict(self.models["mlp"], X_test),
                                           mlp.predict(loaded["mlp"], X_test)))
            self.assertTrue(np.array_equal(pc.predict(self.models["perceptron"], X_test),
                                           pc.predict(loaded["perceptron"], X_test)))
            np.testing.assert_allclose(mlp.predict_proba(self.models["mlp"], X_test),
                                       mlp.predict_proba(loaded["mlp"], X_test))
            self.assertEqual(loaded["mlp_loss_history"], self.models["mlp_loss_history"])
            self.assertEqual(train.evaluate(loaded), self.report)
            # get_models must load the file instead of retraining
            models, source = train.get_models(path)
            self.assertEqual(source, "loaded")
            self.assertTrue(same_models(models, self.models))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_bad_weights_file_ignored(self):
        """A broken file or one trained with other settings is not used."""
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "weights.json")
            self.assertIsNone(train.load_weights(path))           # missing
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ not json")
            self.assertIsNone(train.load_weights(path))           # broken
            train.save_weights(self.models, path)
            other = dict(train.CONFIG, seed=1)
            self.assertIsNone(train.load_weights(path, expected_config=other))  # stale
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestPredictPriority(unittest.TestCase):
    """The entry point used by the rest of the system."""

    def test_handout_example(self):
        """[0, 0, 8, 9, 5, 4, 1] -> final "high", binary "urgent"."""
        result = am.predict_priority(HANDOUT_EXAMPLE)
        self.assertEqual(set(result), set(PRIORITY_OUTPUT_TEMPLATE))
        self.assertEqual(result["final_priority"], "high")
        self.assertEqual(result["binary_priority"], "urgent")
        self.assertIsInstance(result["confidence"], float)
        self.assertGreater(result["confidence"], 0.25)
        self.assertLessEqual(result["confidence"], 1.0)
        self.assertEqual(result["confidence"], round(result["confidence"], 2))

    def test_emergency_example(self):
        """Emergency_Help with high severity -> "urgent"."""
        result = am.predict_priority(EMERGENCY_EXAMPLE)
        self.assertEqual(result["final_priority"], "urgent")
        self.assertEqual(result["binary_priority"], "urgent")

    def test_low_example(self):
        """A mild, non-eligible maintenance request -> low / not_urgent."""
        result = am.predict_priority([2, 3, 1, 2, 1, 0, 0])
        self.assertEqual(result["final_priority"], "low")
        self.assertEqual(result["binary_priority"], "not_urgent")

    def test_accepted_input_forms(self):
        """Tuple, numpy array, floats and True/False all give the same answer."""
        expected = am.predict_priority(HANDOUT_EXAMPLE)
        for form in (tuple(HANDOUT_EXAMPLE), np.array(HANDOUT_EXAMPLE),
                     [0, 0, 8.0, 9.0, 5.0, 4.0, True]):
            self.assertEqual(am.predict_priority(form), expected)
        # Distance above 15 is capped, not rejected
        self.assertNotIn("error", am.predict_priority([0, 0, 8, 9, 5, 40, 1]))

    def test_bad_input(self):
        """Bad input returns a clean error field; nothing is raised or printed."""
        bad_inputs = [
            None, "0,0,8,9,5,4,1", 42, {"role": 0}, [], [0, 0, 8, 9, 5, 4],
            [0, 0, 8, 9, 5, 4, 1, 1], [0, 0, 8, 9, 5, "x", 1], [0, 0, 8, 9, 5, None, 1],
            [0, 0, 8, 9, 5, 4, float("nan")], [0, 0, 8, 9, 5, float("inf"), 1],
            [3, 0, 8, 9, 5, 4, 1], [0, 5, 8, 9, 5, 4, 1], [0, 0, 0, 9, 5, 4, 1],
            [0, 0, 8, 11, 5, 4, 1], [0, 0, 8, 9, 5, -1, 1], [0, 0, 8, 9, 5, 4, 2],
            [0.5, 0, 8, 9, 5, 4, 1], [[0], 0, 8, 9, 5, 4, 1],
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            for features in bad_inputs:
                result = am.predict_priority(features)
                self.assertIn("error", result, features)
                self.assertTrue(result["error"], features)
                self.assertEqual(result["binary_priority"], "", features)
                self.assertEqual(result["final_priority"], "", features)
                self.assertEqual(result["confidence"], 0.0, features)
            am.predict_priority(HANDOUT_EXAMPLE)
        self.assertEqual(out.getvalue(), "")

    def test_explain_prediction(self):
        """Details agree with predict_priority; probabilities sum to 1."""
        details = am.explain_prediction(HANDOUT_EXAMPLE)
        short = am.predict_priority(HANDOUT_EXAMPLE)
        for key in PRIORITY_OUTPUT_TEMPLATE:
            self.assertEqual(details[key], short[key])
        self.assertAlmostEqual(sum(details["probabilities"].values()), 1.0, places=3)
        self.assertEqual(max(details["probabilities"], key=details["probabilities"].get),
                         details["final_priority"])
        self.assertEqual(details["binary_priority"] == "urgent", details["perceptron_sum"] >= 0)


if __name__ == "__main__":
    unittest.main()
