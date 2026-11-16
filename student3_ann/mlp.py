"""
File    : student3_ann/mlp.py
Module  : ANN Priority Prediction - Multi-Layer Perceptron (final model)
Owner   : Student 3

Purpose : MLP with the architecture from the handout diagram:
              input 7 -> hidden1 4 (sigmoid) -> hidden2 3 (sigmoid)
                      -> output 4 (softmax: low, normal, high, urgent)
          Every layer has a bias. Trained with cross-entropy loss and
          backpropagation, using full-batch gradient descent (all training
          rows in every update) and a fixed seed, so the same seed always
          gives the same weights. Loss is recorded once per epoch.
          Confidence = the highest softmax probability.

Shapes (n = number of samples):
  X  (n, 7)   W1 (7, 4)  b1 (4,)   ->  A1 (n, 4)
              W2 (4, 3)  b2 (3,)   ->  A2 (n, 3)
              W3 (3, 4)  b3 (4,)   ->  P  (n, 4)   rows sum to 1
"""

import numpy as np

LAYER_SIZES = [7, 4, 3, 4]
LEARNING_RATE = 0.5
EPOCHS = 20000
SEED = 42


def init_mlp(seed=SEED, sizes=LAYER_SIZES):
    """
    Function: init_mlp
    Purpose : Create the weights with small random values from a seeded
              generator (Xavier scale 1/sqrt(inputs)) and biases at zero.
              Random start breaks symmetry: if all weights were equal, all
              hidden neurons would learn the same thing.
    Params  : seed (int), sizes (list of int) - [7, 4, 3, 4]
    Returns : dict {"W1", "b1", "W2", "b2", "W3", "b3"} of numpy arrays
    """
    rng = np.random.default_rng(seed)
    model = {}
    for layer in range(1, len(sizes)):
        n_in, n_out = sizes[layer - 1], sizes[layer]
        model["W%d" % layer] = rng.normal(0.0, 1.0 / np.sqrt(n_in), (n_in, n_out))
        model["b%d" % layer] = np.zeros(n_out)
    return model


def sigmoid(z):
    """
    Function: sigmoid
    Purpose : Hidden-layer activation 1 / (1 + e^-z), squashes z into (0, 1).
              z is clipped so e^-z can never overflow.
    Params  : z (numpy array)
    Returns : numpy array of the same shape
    """
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def softmax(z):
    """
    Function: softmax
    Purpose : Output activation: turns each row of scores into probabilities
              that are positive and sum to 1. The row maximum is subtracted
              first (does not change the result, avoids overflow in exp).
    Params  : z (numpy array (n, k))
    Returns : numpy array (n, k)
    """
    e = np.exp(z - np.max(z, axis=1, keepdims=True))
    return e / np.sum(e, axis=1, keepdims=True)


def one_hot(y, n_classes=4):
    """
    Function: one_hot
    Purpose : Turn labels like [2, 0] into rows [[0,0,1,0], [1,0,0,0]].
    Params  : y (numpy int array (n,)), n_classes (int)
    Returns : numpy array (n, n_classes)
    """
    return np.eye(n_classes)[np.asarray(y, dtype=int)]


def forward(model, X):
    """
    Function: forward
    Purpose : Forward pass - each layer computes Z = A_prev . W + b, then its
              activation. Intermediate values are kept for backpropagation.
    Params  : model (dict), X (numpy array (n, 7)) - scaled features
    Returns : dict cache {"X", "A1", "A2", "P"}; P = softmax probabilities
    """
    Z1 = X.dot(model["W1"]) + model["b1"]       # hidden layer 1 weighted sums
    A1 = sigmoid(Z1)
    Z2 = A1.dot(model["W2"]) + model["b2"]      # hidden layer 2 weighted sums
    A2 = sigmoid(Z2)
    Z3 = A2.dot(model["W3"]) + model["b3"]      # output scores (logits)
    P = softmax(Z3)
    return {"X": X, "A1": A1, "A2": A2, "P": P}


def cross_entropy(P, Y):
    """
    Function: cross_entropy
    Purpose : Mean cross-entropy loss  L = -(1/n) * sum( Y * log(P) ).
              Only the probability given to the true class counts: the closer
              it is to 1, the closer the loss is to 0.
    Params  : P (numpy array (n, 4)) - predicted probabilities,
              Y (numpy array (n, 4)) - one-hot true labels
    Returns : float - the average loss
    """
    return float(-np.mean(np.sum(Y * np.log(np.clip(P, 1e-12, 1.0)), axis=1)))


def backward(model, cache, Y):
    """
    Function: backward
    Purpose : Backpropagation - apply the chain rule from the loss back to
              every weight, one layer at a time.
    Params  : model (dict), cache (dict from forward), Y (one-hot (n, 4))
    Returns : dict of gradients {"W1", "b1", "W2", "b2", "W3", "b3"}
    """
    n = Y.shape[0]
    X, A1, A2, P = cache["X"], cache["A1"], cache["A2"], cache["P"]

    # Step 1 - output layer error.
    # For softmax + cross-entropy the derivative of the loss with respect to
    # the logits simplifies to (P - Y): predicted minus true probability.
    # Divide by n because the loss is an average over the batch.
    dZ3 = (P - Y) / n

    # Step 2 - output layer gradients.
    # Z3 = A2.W3 + b3, so dL/dW3 = A2^T . dZ3 and dL/db3 = sum of dZ3 rows.
    dW3 = A2.T.dot(dZ3)
    db3 = dZ3.sum(axis=0)

    # Step 3 - send the error back into hidden layer 2.
    # dL/dA2 = dZ3 . W3^T, then multiply by the sigmoid derivative
    # sigmoid'(Z2) = A2 * (1 - A2).
    dA2 = dZ3.dot(model["W3"].T)
    dZ2 = dA2 * A2 * (1.0 - A2)

    # Step 4 - hidden layer 2 gradients (same pattern as step 2).
    dW2 = A1.T.dot(dZ2)
    db2 = dZ2.sum(axis=0)

    # Step 5 - send the error back into hidden layer 1 (same pattern as step 3).
    dA1 = dZ2.dot(model["W2"].T)
    dZ1 = dA1 * A1 * (1.0 - A1)

    # Step 6 - hidden layer 1 gradients; its input is X itself.
    dW1 = X.T.dot(dZ1)
    db1 = dZ1.sum(axis=0)

    return {"W1": dW1, "b1": db1, "W2": dW2, "b2": db2, "W3": dW3, "b3": db3}


def update(model, grads, lr):
    """
    Function: update
    Purpose : Gradient descent step: move every parameter a little against
              its gradient, w = w - lr * dL/dw.
    Params  : model (dict), grads (dict from backward), lr (float)
    Returns : dict - the new model (the old one is not changed)
    """
    return {name: model[name] - lr * grads[name] for name in model}


def train_mlp(X, y, lr=LEARNING_RATE, epochs=EPOCHS, seed=SEED):
    """
    Function: train_mlp
    Purpose : Full-batch gradient descent: every epoch does one forward pass
              over all training rows, records the loss, backpropagates and
              updates the weights once.
    Params  : X (numpy array (n, 7)) - scaled training features,
              y (numpy int array (n,)) - labels 0..3,
              lr (float), epochs (int), seed (int) - for init_mlp
    Returns : (model, losses) - trained dict and a list of per-epoch losses
    """
    model = init_mlp(seed)
    Y = one_hot(y, LAYER_SIZES[-1])
    losses = []
    for _ in range(epochs):
        cache = forward(model, X)
        losses.append(cross_entropy(cache["P"], Y))
        model = update(model, backward(model, cache, Y), lr)
    return model, losses


def predict_proba(model, X):
    """
    Function: predict_proba
    Purpose : Softmax probabilities for each class.
    Params  : model (dict), X (numpy array (n, 7)) - scaled features
    Returns : numpy array (n, 4) - columns low, normal, high, urgent
    """
    return forward(model, np.atleast_2d(X))["P"]


def predict(model, X):
    """
    Function: predict
    Purpose : The predicted class = the column with the highest probability.
    Params  : model (dict), X (numpy array (n, 7)) - scaled features
    Returns : numpy int array (n,) - labels 0..3
    """
    return np.argmax(predict_proba(model, X), axis=1)
