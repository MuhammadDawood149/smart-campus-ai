"""
File    : student3_ann/perceptron.py
Module  : ANN Priority Prediction - Perceptron (binary baseline)
Owner   : Student 3

Purpose : Single-layer Perceptron: 7 inputs + bias -> step activation ->
          urgent (1) / not_urgent (0). Trained with the perceptron learning
          rule (learning rate 0.1, 50 epochs). Used as the baseline that the
          MLP is compared against.

How it works:
  1. Weighted sum   z = w1*x1 + w2*x2 + ... + w7*x7 + b
     Each weight says how much its feature pushes towards "urgent"
     (positive weight) or "not urgent" (negative weight); the bias b shifts
     the threshold.
  2. Activation     y_hat = step(z) = 1 if z >= 0 else 0
     The step function turns the sum into a hard yes/no decision.
  3. Decision boundary
     The points where z = 0 form a flat hyperplane w.x + b = 0 in the 7-D
     input space. Everything on one side is "urgent", everything on the other
     side is "not urgent". A Perceptron can only draw ONE straight boundary,
     which is why it is a baseline: it cannot model the bent shape that the
     MLP's hidden layers can.
  4. Learning rule  (for each training sample)
     error = y - y_hat               (0 if correct, +1 or -1 if wrong)
     w = w + lr * error * x
     b = b + lr * error
     A correct prediction changes nothing; a wrong one moves the boundary
     towards classifying that sample correctly.
"""

import numpy as np

LEARNING_RATE = 0.1
EPOCHS = 50
N_INPUTS = 7


def init_perceptron(n_inputs=N_INPUTS):
    """
    Function: init_perceptron
    Purpose : Create a Perceptron with all weights and the bias at zero
              (zero start = no randomness, so training is reproducible).
    Params  : n_inputs (int) - number of input features (7)
    Returns : dict {"w": numpy array (n_inputs,), "b": float}
    """
    return {"w": np.zeros(n_inputs), "b": 0.0}


def weighted_sum(model, X):
    """
    Function: weighted_sum
    Purpose : Compute z = w.x + b for one sample or a batch of samples.
    Params  : model (dict), X (numpy array, shape (7,) or (n, 7)) - scaled
    Returns : float or numpy array (n,) - the weighted sums
    """
    return np.dot(X, model["w"]) + model["b"]


def step(z):
    """
    Function: step
    Purpose : Step activation - 1 if z >= 0 else 0.
    Params  : z (float or numpy array)
    Returns : numpy int array (or int) of 0/1
    """
    return (np.asarray(z) >= 0).astype(int)


def predict(model, X):
    """
    Function: predict
    Purpose : Classify samples as urgent (1) or not urgent (0).
    Params  : model (dict), X (numpy array, shape (7,) or (n, 7)) - scaled
    Returns : numpy int array of 0/1 (or a 0-d array for one sample)
    """
    return step(weighted_sum(model, X))


def train_perceptron(X, y, lr=LEARNING_RATE, epochs=EPOCHS):
    """
    Function: train_perceptron
    Purpose : Train with the perceptron learning rule, one sample at a time,
              visiting the training rows in the same order every epoch.
    Params  : X (numpy array (n, 7)) - scaled training features,
              y (numpy array (n,)) - 0/1 labels, lr (float), epochs (int)
    Returns : (model, errors_per_epoch) - trained dict and a list with the
              number of misclassified training samples in each epoch
    """
    model = init_perceptron(X.shape[1])
    errors_per_epoch = []
    for _ in range(epochs):
        mistakes = 0
        for x_i, y_i in zip(X, y):
            y_hat = int(step(weighted_sum(model, x_i)))    # 1. sum, 2. activation
            error = int(y_i) - y_hat                        # 0, +1 or -1
            if error != 0:                                  # 4. learning rule
                model["w"] = model["w"] + lr * error * x_i
                model["b"] = model["b"] + lr * error
                mistakes += 1
        errors_per_epoch.append(mistakes)
    return model, errors_per_epoch
