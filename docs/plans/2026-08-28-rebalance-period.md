# Rebalance Period Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a configurable rebalance period to the OTO single-factor evaluator, while still calculating portfolio returns for every trading day.

**Architecture:** Keep the existing daily OTO return target and `F(t-1) -> open(t) -> open(t+1)` alignment unchanged. Add a config value that controls when group memberships are refreshed; on non-rebalance days, carry forward the last selected holdings and mark daily returns from those holdings. Default to `1` so existing behavior and tests remain compatible.

**Tech Stack:** Python, pandas, YAML config, unittest/pytest.

---

## Product Semantics

### Current Behavior

The current `_group_returns()` in `quantaalpha/evaluation/engine.py`:

1. Iterates every `entry_date`.
2. Uses that day aligned factor values to form `G0 ... G9`.
3. Computes that day's OTO return for each group.
4. Charges turnover fee based on membership changes from the previous day.

That means the current rebalance period is effectively `1` trading day.

### New Behavior

Add:

```yaml
portfolio:
  rebalance_period_days: 1
```

Definition:

- `rebalance_period_days = 1`: current behavior, rebalance every trading day.
- `rebalance_period_days = N`: only refresh group memberships every N trading days.
- Daily returns are still calculated for every trading day.
- On rebalance days, use the already-aligned factor values for that `entry_date`, which means the signal is still `F(t-1)`.
- On non-rebalance days, reuse the previous rebalance day's holdings.
- Fees are charged only when memberships are refreshed on rebalance days.
- Benchmark should follow the same rebalance schedule if `costs.charge_benchmark=true`: charge benchmark turnover only on benchmark rebalance days, but calculate benchmark daily return every trading day.

### Alignment Rule

The existing signal/return alignment must not change:

```text
factor_date = previous_market_session(entry_date)
factor_date < entry_date < exit_date
F(t-1) -> open(t) -> open(t+1)
```

For `rebalance_period_days=N`, this means:

```text
rebalance day t:
  use F(t-1) to choose holdings at open(t)

hold day t+k:
  keep holdings selected at open(t)
  calculate daily OTO return from open(t+k) to open(t+k+1)
```

## Recommended Design

### Config Location

Add a new `portfolio` section to `/Users/wangjiayi/Downloads/QuantaAlpha/configs/evaluation.yaml`:

```yaml
portfolio:
  rebalance_period_days: 1
```

Reason:

- `metrics` should stay for measurement thresholds and grouping parameters.
- `costs` should stay for fees.
- Rebalance period describes portfolio construction, so `portfolio` is clearer.

### Backward Compatibility

Use a helper:

```python
def _rebalance_period_days(self) -> int:
    value = self.config.section("portfolio").get("rebalance_period_days", 1)
    days = int(value)
    if days < 1:
        raise ValueError("portfolio.rebalance_period_days must be >= 1")
    return days
```

No config change from older files should break evaluation because missing `portfolio` defaults to `1`.

### Core Algorithm

Change only `_group_returns()` first.

Inputs stay the same:

```python
def _group_returns(
    self,
    aligned: pd.DataFrame,
    direction: int,
    benchmark_panel: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
```

Internal state:

```python
rebalance_period = self._rebalance_period_days()
current_groups: dict[int, set[str]] = {index: set() for index in range(group_count)}
previous_groups: dict[int, set[str]] = {index: set() for index in range(group_count)}
days_since_rebalance = rebalance_period
```

Daily loop:

1. Iterate all `entry_date` in order.
2. Determine `is_rebalance_day`:

```python
is_rebalance_day = days_since_rebalance >= rebalance_period or not any(current_groups.values())
```

3. If rebalance day:
   - Use that day's `aligned` factor values.
   - Rank by `oriented_factor = factor_value * direction`.
   - Assign qcut groups.
   - Replace `current_groups`.
   - Compute fees versus `previous_groups`.
   - Set `days_since_rebalance = 1`.

4. If non-rebalance day:
   - Keep `current_groups`.
   - Set all group fees to `0.0`.
   - Increment `days_since_rebalance += 1`.

5. For every day, compute each group return from that day's OTO returns:
   - Prefer `benchmark_panel` as daily return source because it contains the full eligible daily universe.
   - Use `current_groups[group_index] ∩ daily_return_codes`.
   - If no held member has a valid daily return, set group return to `None`.

6. Append daily row regardless of rebalance/hold day:

```python
row = {
    "date": date,
    "is_rebalance_day": is_rebalance_day,
    "rebalance_period_days": rebalance_period,
    ...
}
```

7. Excess return remains daily:

```python
excess_return = head_net_return - benchmark_net_return
```

### Important Return Source Choice

Use two daily frames:

- `selection_day`: from `aligned`, only needed on rebalance days because it contains factor values.
- `return_day`: from `benchmark_panel` when available, otherwise from `aligned`, because held stocks on non-rebalance days may not need that day's factor value but still need that day's return.

This avoids accidentally dropping daily PnL just because the factor was not refreshed.

### Fees

Current fee formula:

```python
fee = len(current - previous) * 2.0 * rate / denominator
```

Keep this formula.

Change when it applies:

- On rebalance days: calculate normally.
- On non-rebalance days: `fee = 0.0`.

Benchmark:

- If `costs.charge_benchmark=true`, charge benchmark fee only on rebalance days.
- If `costs.charge_benchmark=false`, benchmark fee remains `0.0`.

### Metrics

Existing metrics can stay:

- IC / ICIR: still daily signal-vs-next-OTO IC based on aligned data. This measures factor information, not portfolio holding PnL.
- group return cumulative: now reflects N-day rebalance portfolio.
- long_short_spread: sum of daily `G9 - G0`, using held portfolios.
- excess_sharpe: daily excess return Sharpe, using held portfolios.

Add to returned metrics:

```python
"portfolio": {
    "rebalance_period_days": rebalance_period,
    "rebalance_days": int(grouped["is_rebalance_day"].sum()),
    "return_days": int(len(grouped)),
}
```

This makes the UI and summary self-explanatory.

## Task Plan

### Task 1: Add Config Default

**Files:**

- Modify: `/Users/wangjiayi/Downloads/QuantaAlpha/configs/evaluation.yaml`

**Step 1: Add config**

Add:

```yaml
portfolio:
  rebalance_period_days: 1
```

Place it after `alignment` or before `metrics`.

**Step 2: Verify config loads**

Run:

```bash
/Users/wangjiayi/Downloads/QuantaAlpha/.venv/bin/python - <<'PY'
from quantaalpha.evaluation.config import load_evaluation_config
cfg = load_evaluation_config()
print(cfg.section("portfolio").get("rebalance_period_days"))
PY
```

Expected:

```text
1
```

### Task 2: Add Rebalance Helper

**Files:**

- Modify: `/Users/wangjiayi/Downloads/QuantaAlpha/quantaalpha/evaluation/engine.py`
- Test: `/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`

**Step 1: Write tests**

Add tests for:

- Missing `portfolio` defaults to `1`.
- `rebalance_period_days=0` raises an error.

**Step 2: Implement helper**

Add to `SingleFactorEvaluator`:

```python
def _rebalance_period_days(self) -> int:
    value = self.config.section("portfolio").get("rebalance_period_days", 1)
    days = int(value)
    if days < 1:
        raise ValueError("portfolio.rebalance_period_days must be >= 1")
    return days
```

### Task 3: Refactor `_group_returns()` for Holding Portfolios

**Files:**

- Modify: `/Users/wangjiayi/Downloads/QuantaAlpha/quantaalpha/evaluation/engine.py`
- Test: `/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`

**Step 1: Write failing test**

Create a fixture where factor ranks change every day and set:

```python
raw["portfolio"] = {"rebalance_period_days": 3}
```

Expected:

- First day has `is_rebalance_day=True`.
- Next two days have `is_rebalance_day=False`.
- Group members are not rebuilt on hold days.
- Group returns are still present on every day.
- Fees are zero on hold days.

**Step 2: Implement minimal logic**

Inside `_group_returns()`:

- Build `returns_by_date` from `benchmark_panel` if provided.
- Rebalance only every N days.
- On hold days, compute returns using carried `current_groups`.
- Append `is_rebalance_day` and `rebalance_period_days`.

**Step 3: Preserve N=1 behavior**

Existing test `test_fee_formula_matches_oto_membership_turnover` should still pass without changing assertions.

### Task 4: Add Metrics and Artifacts Visibility

**Files:**

- Modify: `/Users/wangjiayi/Downloads/QuantaAlpha/quantaalpha/evaluation/engine.py`
- Test: `/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`

**Step 1: Add metrics**

In `_evaluate_period()`, after `grouped` is computed:

```python
portfolio_metrics = {
    "rebalance_period_days": self._rebalance_period_days(),
    "rebalance_days": int(grouped["is_rebalance_day"].sum()) if "is_rebalance_day" in grouped else 0,
    "return_days": int(len(grouped)),
}
```

Add it under:

```python
"portfolio": portfolio_metrics
```

**Step 2: Confirm artifact columns**

`training_group_returns.csv` and `validation_group_returns.csv` should include:

- `is_rebalance_day`
- `rebalance_period_days`
- `G0_fee ... G9_fee`

No new artifact file is required.

### Task 5: Update Documentation

**Files:**

- Modify: `/Users/wangjiayi/Downloads/QuantaAlpha/docs/新版回测与因子筛选流程说明.md`
- Modify if present/relevant: `/Users/wangjiayi/Downloads/QuantaAlpha/docs/ADR-OTO单因子评估.md`

**Step 1: Document config**

Add:

```yaml
portfolio:
  rebalance_period_days: 1
```

**Step 2: Document formula**

For rebalance day:

```text
H_{g,t} = Top/Bottom group selected by Rank(F_{t-1})
```

For hold day:

```text
H_{g,t} = H_{g,t-1}
```

Daily group return:

```text
R_{g,t}^{net} = mean_{i in H_{g,t}}(R_{i,t}^{OTO}) - Fee_{g,t}
```

Where:

```text
Fee_{g,t} = turnover_fee if t is rebalance day, else 0
```

### Task 6: Run Tests

**Files:**

- Test: `/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`
- Optional: `/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_evaluation_services.py`

**Step 1: Run focused tests**

```bash
/Users/wangjiayi/Downloads/QuantaAlpha/.venv/bin/python -m pytest /Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py -q
```

Expected:

```text
passed
```

**Step 2: Run service tests**

```bash
/Users/wangjiayi/Downloads/QuantaAlpha/.venv/bin/python -m pytest /Users/wangjiayi/Downloads/QuantaAlpha/tests/test_evaluation_services.py -q
```

Expected:

```text
passed
```

## Edge Cases

- If the first day cannot form all groups, skip until the first valid rebalance day.
- If a held stock has no valid OTO return on a hold day, exclude it from that day's average and record available members implicitly through the daily group return.
- If all held stocks in a group lack returns, set that group return to `None` for the day.
- If the period boundary cuts a holding interval, do not carry returns across the boundary; existing `_period_panel()` rule should remain.
- `rebalance_period_days` counts trading days, not calendar days.

## Acceptance Criteria

- `rebalance_period_days=1` reproduces current daily rebalance behavior.
- `rebalance_period_days=N` refreshes holdings only every N trading days.
- Group and excess returns still have one row per valid trading day.
- Hold days have zero group turnover fees.
- Alignment audit still proves `factor_date < entry_date < exit_date`.
- Training/validation/subperiod metrics all use the same rebalance-period logic.

