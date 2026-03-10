## Win Probability Model Notes

This doc captures practical notes about the V1 logistic regression model
used for the win probability function \(w(x)\), including convergence
warnings, quality expectations, and how future changes may impact
downstream steps in the LLM pipeline.

### Current training setup

- **Script**: `scripts/train_win_prob_model.py`
- **Input**: `data/training.csv` exported by `scripts/export_training_data.py`
- **Model**: `sklearn.linear_model.LogisticRegression` with:
  - `max_iter = 1000`
  - `class_weight = "balanced"`
  - solver = default (`lbfgs`)
- **Features**:
  - Order defined in `app/services/win_prob_features.py::FEATURE_ORDER`
  - Rank encoded via `encode_rank()` (ordinal tier index)
- **Output**:
  - Joblib file `data/win_prob_model.joblib` (default)
  - Passed to the API/worker via `WIN_PROB_MODEL_PATH` / `win_prob_model_path`

### Convergence warning \("lbfgs failed to converge"\)

When running the training script on the current dataset, scikit-learn
emits:

> ConvergenceWarning: lbfgs failed to converge after 1000 iteration(s)
> (status=1): STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT

**What this means:**

- The optimizer hit the `max_iter` cap (1000) before fully converging.
- A model was still fit and saved; this is a **soft warning**, not a hard
  error.
- Coefficients are likely close to optimal but not perfectly optimized.

**Why this is acceptable for now:**

- V1 is a baseline used to:
  - Wire up step 3 \(Score\) and step 4 \(Compute \(\Delta W\)\).
  - Drive early aggregation and LLM prompt design.
- For this phase, we mostly care about **relative ordering** of states and
  actions, not perfect calibration.

### Implications for future changes

1. **Model quality and calibration**
   - Predictions are usable but may be **slightly under-optimized**.
   - Before doing serious evaluation \(accuracy, ECE, reliability
     diagrams\), we should:
     - increase `max_iter`, and/or
     - standardize features, and/or
     - consider alternate solvers.

2. **ΔW magnitudes and rankings**
   - Current `delta_w` values will be based on this partially converged
     model.
   - Coarse insights \(e.g., clearly strong vs clearly weak items\) are
     likely robust.
   - Fine-grained ordering between very similar items or decisions may
     change if we later retrain with better convergence.

3. **Versioning considerations**
   - Future retrains with different hyperparameters \(e.g. scaled inputs,
     higher `max_iter`, new solver\) will produce **different
     coefficients** from the same CSV.
   - Any code that aggregates or exposes `delta_w` should treat the model as
     **versioned state**, even if we do not persist an explicit
     `model_version` yet.
   - If we start relying on stable historical values, we should:
     - either store a `model_version` alongside scores, or
     - plan to re-score existing actions when changing the model.

4. **Downstream pipeline impact**
   - **Aggregation / Compare** \(steps 5–6\):
     - They only depend on the numerical `delta_w` values, not on the
       training internals.
     - It is safe to build and test aggregation and comparison logic on the
       current model and later re-score if we upgrade the model.
   - **LLM prompt construction** \(step 7\):
     - The prompt consumes `delta_w` and rankings, not the model itself.
     - If we later retrain, only the numbers change; prompt structure and
       semantics remain the same.

### Recommended future improvements

When we are ready to harden the baseline model:

- **Increase `max_iter`**:
  - Example: 2000–5000 iterations to allow `lbfgs` to fully converge.
- **Feature scaling**:
  - Standardize numeric features \(mean 0, std 1\) before fitting.
  - This usually improves convergence speed and numerical stability.
- **Solver choices**:
  - Keep `lbfgs` if it converges cleanly after scaling and higher
    `max_iter`.
  - Alternatively, consider `saga` if we want more flexibility or on very
    large datasets.
- **Evaluation pass**:
  - Once convergence is clean, run an explicit evaluation pass
    \(accuracy, ECE, reliability diagrams\) to validate that V1 hits the
    expected quality bar before investing in a DNN \(V2\).

