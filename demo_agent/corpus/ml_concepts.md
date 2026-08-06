# Machine Learning Concepts

## Gradient Descent

Gradient descent minimizes a loss function L(θ) by iteratively updating parameters θ
in the direction opposite to the gradient:

    θ ← θ − η · ∇L(θ)

where η (eta) is the learning rate.

**Variants:**
- **Batch gradient descent**: uses the full dataset per update. Stable but slow for large data.
- **Stochastic gradient descent (SGD)**: one sample per update. Noisy but fast, escapes local minima.
- **Mini-batch SGD**: subset of n samples (typically 32–512). Best practical trade-off.

**Adaptive optimizers** (Adam, RMSProp, AdaGrad) scale η per parameter using gradient history,
converging faster than vanilla SGD on most deep learning tasks.

Adam update rule:
    m ← β₁·m + (1−β₁)·g          (first moment, momentum)
    v ← β₂·v + (1−β₂)·g²         (second moment, RMS)
    θ ← θ − η·m̂ / (√v̂ + ε)      (bias-corrected update)

Typical defaults: β₁=0.9, β₂=0.999, ε=1e-8.

## Backpropagation

Backprop computes ∂L/∂θ for every parameter using the chain rule:

    ∂L/∂θ = ∂L/∂a · ∂a/∂z · ∂z/∂θ

where a is the activation and z is the pre-activation (weighted sum).

Steps:
1. Forward pass: compute predictions and cache intermediate activations.
2. Compute loss (cross-entropy, MSE, etc.).
3. Backward pass: propagate gradients from output to input layer by layer.
4. Update parameters with an optimizer.

Vanishing gradient: gradients shrink exponentially through sigmoid/tanh layers.
Mitigations: ReLU activations, residual connections (ResNet), batch normalization.

## Overfitting

A model overfits when it memorizes training data instead of learning general patterns,
leading to high training accuracy but poor test/validation accuracy.

Signs: large gap between training loss and validation loss.

**Regularization techniques:**

| Technique | Mechanism |
|-----------|-----------|
| L2 (weight decay) | Adds λ·‖θ‖² to loss; penalizes large weights |
| L1 (Lasso) | Adds λ·‖θ‖₁; drives some weights to exactly zero (sparsity) |
| Dropout | Randomly zeros activations with probability p during training |
| Early stopping | Halt training when validation loss stops improving |
| Data augmentation | Artificially expand training set (flips, crops, noise) |
| Batch normalization | Normalizes layer inputs; mild regularization effect |

## Bias-Variance Trade-off

Total error = Bias² + Variance + Irreducible noise

- High bias (underfitting): model too simple, misses patterns.
- High variance (overfitting): model too complex, sensitive to training noise.
- Goal: find the sweet spot via cross-validation, regularization, and model selection.

## Cross-Validation

k-fold CV: split data into k folds, train on k-1, validate on 1, rotate k times.
Reports mean ± std of validation metric across folds — more reliable than a single split.
