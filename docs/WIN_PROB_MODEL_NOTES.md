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

### ARQ job id strategy for scoring (score_actions_job)

`score_actions_job` is enqueued with a custom `_job_id` to avoid duplicate
work. That idempotency behaviour is powerful but has some sharp edges.

#### Current pattern (one-shot, idempotent)

- Helper script: `scripts/score_actions_for_match.py`
- Job id: `_job_id = f"score-actions:{match_id}"`
- Result key: `arq:result:score-actions:{match_id}`

ARQ semantics:

- If a job with a given `_job_id` has **ever completed** (success *or*
  failure), subsequent `enqueue_job` calls with the same `_job_id`:
  - **do not enqueue a new job**, and
  - immediately return the existing result.
- Practically: a past failure like “function 'score_actions_job' not found”
  will block all future runs with that same `_job_id` unless the result
  keys are cleaned up.

This is desirable when we want “at most once per match per model version”,
but surprising when trying to re-run after fixing code or changing the
model.

#### Future-friendly pattern: bake a version into `_job_id`

To support re-running scoring after model or code changes without manual
Redis cleanup:

- Introduce a **scoring version string**, e.g. `SCORE_VERSION = "v1"`.
- Build job ids as:

  - `_job_id = f"score-actions:{SCORE_VERSION}:{match_id}"`
  - Result keys become `arq:result:score-actions:v1:{match_id}`

When we change scoring semantics (new model, feature set, or logic):

- Bump `SCORE_VERSION` \(e.g. `"v2"`\).
- Existing `v1` results remain in Redis; new jobs use `v2`:
  - `score-actions:v1:NA1_...` and `score-actions:v2:NA1_...` are distinct.
- Aggregation/analysis code can decide whether to:
  - treat old and new versions separately, or
  - re-score only a subset with the new version.

This yields:

- Idempotency **within** a given scoring version.
- Safe re-running after upgrades by bumping the version, not by deleting
  keys.

#### Manual cleanup procedure (when a stale result is blocking re-runs)

If we accidentally enqueue with a bad `_job_id` before the worker is
ready, ARQ may store a failure like:

> JobExecutionFailed … function 'score_actions_job' not found

under `arq:result:score-actions:{match_id}`. To recover for that one
match:

1. Connect to the same Redis instance / DB the worker uses
   (`REDIS_URL`, typically `redis://localhost:6379/0`).
2. Inspect the result key:

   ```bash
   redis-cli GET arq:result:score-actions:NA1_...
   ```

3. If it contains a stale failure you no longer care about, delete both
   the result and any associated job key:

   ```bash
   redis-cli DEL arq:result:score-actions:NA1_...
   redis-cli DEL arq:job:score-actions:NA1_...   # only if it exists
   ```

4. Ensure the worker is running with the correct code (`make worker-dev`),
   then re-enqueue:

   ```bash
   make score-actions MATCH_ID=NA1_...
   ```

Going forward, using a versioned `_job_id` reduces the need for manual
cleanup; we only delete keys when we explicitly want to force a retry for
the same version string.


