# 调仓周期配置实现方案

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 给新版 OTO 单因子评估引擎增加“调仓周期”配置，默认每 3 个交易日调一次仓，但组合收益仍然每天计算。

**架构：** 保持现有 OTO 收益目标和 `F(t-1) -> open(t) -> open(t+1)` 时间对齐不变。新增一个组合层配置，用来控制什么时候重新按因子分组建仓；非调仓日沿用上一次调仓日的持仓，并继续用当天 OTO 收益做每日记账。默认值改为 `3`，表示新版默认行为是三日调仓；如果要复现旧版每日调仓，需要显式配置为 `1`。

**技术栈：** Python、pandas、YAML 配置、unittest/pytest。

---

## 一、产品语义

### 当前行为

当前 `quantaalpha/evaluation/engine.py` 里的 `_group_returns()` 逻辑是：

1. 每个 `entry_date` 都重新读取当天对齐后的因子值。
2. 每天都按因子值排序并分成 `G0 ... G9` 十组。
3. 每天都计算各组从 `open(t)` 到 `open(t+1)` 的 OTO 收益。
4. 每天都根据相邻两天组内股票变化计算换仓手续费。

也就是说，当前代码等价于：

```yaml
portfolio:
  rebalance_period_days: 1
```

### 新行为

新增配置：

```yaml
portfolio:
  rebalance_period_days: 3
```

定义：

- `rebalance_period_days = 3`：默认每 3 个交易日重新调仓一次。
- `rebalance_period_days = N`：每隔 N 个交易日重新按因子值分组。
- `rebalance_period_days = 1`：复现旧版行为，即每日调仓。
- 无论 N 是多少，组合收益仍然每天计算。
- 调仓日使用该开仓日已经对齐好的因子值，也就是 `F(t-1)`。
- 非调仓日不重新排序、不重新分组，直接沿用上一调仓日的持仓。
- 手续费只在调仓日收取，非调仓日手续费为 `0`。
- benchmark 如果开启 `costs.charge_benchmark=true`，也按同样调仓周期收取换仓成本，但 benchmark 每日收益仍然每天计算。

## 二、时间对齐规则

现有信号/收益对齐规则不变：

```text
factor_date = previous_market_session(entry_date)
factor_date < entry_date < exit_date
F(t-1) -> open(t) -> open(t+1)
```

当 `rebalance_period_days = 3` 时：

```text
调仓日 t:
  使用 F(t-1) 在 open(t) 形成持仓
  计算 open(t) -> open(t+1) 的当天 OTO 收益

持仓日 t+1:
  沿用 t 日形成的持仓
  计算 open(t+1) -> open(t+2) 的当天 OTO 收益

持仓日 t+2:
  继续沿用 t 日形成的持仓
  计算 open(t+2) -> open(t+3) 的当天 OTO 收益

下一调仓日 t+3:
  使用 F(t+2) 重新分组调仓
```

核心原则：

```text
因子只在调仓日决定新持仓；
收益每天都按当前持仓计算；
任何时候都不能使用当天开盘以后才知道的信息决定当天开盘持仓。
```

## 三、配置设计

建议在 `/Users/wangjiayi/Downloads/QuantaAlpha/configs/evaluation.yaml` 中新增：

```yaml
portfolio:
  rebalance_period_days: 3
```

建议位置：放在 `alignment` 之后、`lookahead_audit` 或 `metrics` 之前。

理由：

- `metrics` 主要是指标和门槛，例如 IC、ICIR、分组数量、Sharpe 阈值。
- `costs` 主要是手续费规则。
- `rebalance_period_days` 描述的是组合构建和持仓更新频率，放在 `portfolio` 更清楚。

## 四、默认值与兼容性

实现 helper：

```python
def _rebalance_period_days(self) -> int:
    value = self.config.section("portfolio").get("rebalance_period_days", 3)
    days = int(value)
    if days < 1:
        raise ValueError("portfolio.rebalance_period_days must be >= 1")
    return days
```

注意：

- 旧配置文件如果没有 `portfolio` 字段，会默认走 `3`。
- 因此新版默认评估结果会从“每日调仓”变成“三日调仓”。
- 如果需要和历史旧版结果严格对照，应在配置里显式写：

```yaml
portfolio:
  rebalance_period_days: 1
```

## 五、核心算法方案

主要改动位置：

```text
/Users/wangjiayi/Downloads/QuantaAlpha/quantaalpha/evaluation/engine.py
```

优先只改 `_group_returns()`，函数签名保持不变：

```python
def _group_returns(
    self,
    aligned: pd.DataFrame,
    direction: int,
    benchmark_panel: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
```

### 内部状态

新增状态：

```python
rebalance_period = self._rebalance_period_days()
current_groups: dict[int, set[str]] = {index: set() for index in range(group_count)}
previous_groups: dict[int, set[str]] = {index: set() for index in range(group_count)}
days_since_rebalance = rebalance_period
```

含义：

- `current_groups`：当前实际持仓。
- `previous_groups`：上一调仓日的持仓，用于计算换仓成本。
- `days_since_rebalance`：距离上一次调仓经过的交易日数量。

### 每日循环逻辑

按 `entry_date` 升序遍历每个交易日。

判断是否调仓：

```python
is_rebalance_day = days_since_rebalance >= rebalance_period or not any(current_groups.values())
```

如果是调仓日：

1. 使用当天 `aligned` 中的因子值。
2. 计算方向调整后的因子：

```python
day["oriented_factor"] = day["factor_value"] * direction
```

3. 用 `pd.qcut` 分成 `G0 ... G9`。
4. 更新 `current_groups`。
5. 与 `previous_groups` 比较，计算手续费。
6. 更新 `previous_groups = current_groups`。
7. 设置 `days_since_rebalance = 1`。

如果不是调仓日：

1. 不读取当天因子值来换仓。
2. 不重新分组。
3. 沿用 `current_groups`。
4. 所有组的手续费设为 `0.0`。
5. `days_since_rebalance += 1`。

无论是否调仓，每天都要：

1. 取当天每只股票的 OTO 收益。
2. 用当前持仓集合去匹配当天可交易且有收益的股票。
3. 计算每组平均收益。
4. 写入当天 `group_returns`。
5. 计算当天头组相对 benchmark 的超额收益。

## 六、每日收益数据来源

需要区分两个日度数据：

### 1. 调仓用数据

调仓日使用：

```text
selection_day = aligned[aligned["entry_date"] == date]
```

它包含：

- `factor_date`
- `entry_date`
- `exit_date`
- `code`
- `factor_value`
- `oto_return`

调仓时用 `factor_value` 分组。

### 2. 每日收益用数据

每日收益优先使用：

```text
return_day = benchmark_panel[benchmark_panel["entry_date"] == date]
```

原因：

- 非调仓日不需要当天因子值。
- 但非调仓日仍需要当天持仓股票的 OTO 收益。
- 如果只从 `aligned` 取收益，会不必要地依赖当天是否有因子值，容易漏掉持仓收益。

如果没有传入 `benchmark_panel`，再 fallback 到当天 `aligned`。

## 七、手续费规则

保留当前手续费公式：

```python
fee = len(current - previous) * 2.0 * rate / denominator
```

其中：

```python
denominator = max(len(current), len(previous))
```

调整为：

- 调仓日：正常计算手续费。
- 非调仓日：手续费为 `0.0`。

benchmark 费用：

- `costs.charge_benchmark=true`：benchmark 只在调仓日收换仓成本。
- `costs.charge_benchmark=false`：benchmark 手续费始终为 `0.0`。

## 八、指标口径

现有核心指标保留，但含义需要说明清楚。

### IC / ICIR

IC / ICIR 仍然基于每日对齐数据计算：

```text
Corr(F(t-1), R_OTO(t,t+1))
```

它衡量的是因子日频预测信息，不随调仓周期改变。

### 分组收益

分组收益变成“按调仓周期持有”的组合收益：

```text
R_{g,t}^{net} = mean_{i in H_{g,t}}(R_{i,t}^{OTO}) - Fee_{g,t}
```

其中：

```text
H_{g,t} =
  调仓日：由 Rank(F_{t-1}) 选出的第 g 组股票
  非调仓日：H_{g,t-1}
```

```text
Fee_{g,t} =
  调仓日：换仓手续费
  非调仓日：0
```

### 多空收益

```text
Spread_t = R_{G9,t}^{net} - R_{G0,t}^{net}
```

```text
long_short_spread = sum_t Spread_t
```

### 超额收益与超额 Sharpe

```text
Excess_t = R_{G9,t}^{net} - R_{benchmark,t}^{net}
```

```text
ExcessSharpe = sqrt(252) * mean(Excess_t) / std(Excess_t)
```

即使 3 日调仓，`Excess_t` 仍然是每日序列。

## 九、结果中增加组合信息

建议在 `_evaluate_period()` 的 `metrics` 中增加：

```python
"portfolio": {
    "rebalance_period_days": rebalance_period,
    "rebalance_days": int(grouped["is_rebalance_day"].sum()),
    "return_days": int(len(grouped)),
}
```

同时 `training_group_returns.csv` / `validation_group_returns.csv` 增加列：

```text
is_rebalance_day
rebalance_period_days
G0_fee ... G9_fee
```

这样同事看到产物就能判断：

- 哪些天调仓了。
- 当前设置是几日调仓。
- 非调仓日是否正确没有收手续费。
- 每日收益是否连续计算。

## 十、实现任务拆分

### 任务 1：新增默认配置

**文件：**

- 修改：`/Users/wangjiayi/Downloads/QuantaAlpha/configs/evaluation.yaml`

**步骤 1：增加配置**

添加：

```yaml
portfolio:
  rebalance_period_days: 3
```

**步骤 2：验证配置读取**

运行：

```bash
/Users/wangjiayi/Downloads/QuantaAlpha/.venv/bin/python - <<'PY'
from quantaalpha.evaluation.config import load_evaluation_config
cfg = load_evaluation_config()
print(cfg.section("portfolio").get("rebalance_period_days"))
PY
```

预期输出：

```text
3
```

### 任务 2：新增调仓周期读取 helper

**文件：**

- 修改：`/Users/wangjiayi/Downloads/QuantaAlpha/quantaalpha/evaluation/engine.py`
- 测试：`/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`

**步骤 1：先写测试**

新增测试：

- 缺少 `portfolio` 时默认返回 `3`。
- `rebalance_period_days=1` 时允许每日调仓。
- `rebalance_period_days=0` 时报错。

**步骤 2：实现 helper**

在 `SingleFactorEvaluator` 中新增：

```python
def _rebalance_period_days(self) -> int:
    value = self.config.section("portfolio").get("rebalance_period_days", 3)
    days = int(value)
    if days < 1:
        raise ValueError("portfolio.rebalance_period_days must be >= 1")
    return days
```

### 任务 3：重构 `_group_returns()` 为“调仓日建仓 + 每日记账”

**文件：**

- 修改：`/Users/wangjiayi/Downloads/QuantaAlpha/quantaalpha/evaluation/engine.py`
- 测试：`/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`

**步骤 1：先写失败测试**

构造一个因子排序每天变化的 fixture，并设置：

```python
raw["portfolio"] = {"rebalance_period_days": 3}
```

测试应验证：

- 第一天是调仓日。
- 第 2、3 天不是调仓日。
- 第 4 天再次调仓。
- 非调仓日不重新分组。
- 非调仓日仍然有每日收益。
- 非调仓日 `G*_fee` 全部为 `0.0`。

**步骤 2：实现最小逻辑**

在 `_group_returns()` 中：

1. 从配置读取 `rebalance_period`。
2. 为每日收益建立 `returns_by_date`。
3. 调仓日用 `aligned` 中当天因子分组。
4. 非调仓日沿用 `current_groups`。
5. 每天都用 `return_day` 计算持仓收益。
6. 在结果行中写入：

```python
row["is_rebalance_day"] = is_rebalance_day
row["rebalance_period_days"] = rebalance_period
```

### 任务 4：保留每日调仓兼容测试

**文件：**

- 测试：`/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`

**步骤 1：显式设置旧行为**

当前已有测试 `test_fee_formula_matches_oto_membership_turnover` 可以明确设置：

```python
raw["portfolio"] = {"rebalance_period_days": 1}
```

这样该测试继续验证旧版每日调仓手续费逻辑。

**步骤 2：跑测试**

运行：

```bash
/Users/wangjiayi/Downloads/QuantaAlpha/.venv/bin/python -m pytest /Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py -q
```

预期：

```text
passed
```

### 任务 5：更新指标和产物说明

**文件：**

- 修改：`/Users/wangjiayi/Downloads/QuantaAlpha/quantaalpha/evaluation/engine.py`
- 修改：`/Users/wangjiayi/Downloads/QuantaAlpha/docs/新版回测与因子筛选流程说明.md`
- 视情况修改：`/Users/wangjiayi/Downloads/QuantaAlpha/docs/ADR-OTO单因子评估.md`

**步骤 1：指标中加入 portfolio**

在 `_evaluate_period()` 返回的 `metrics` 中加入：

```python
"portfolio": {
    "rebalance_period_days": self._rebalance_period_days(),
    "rebalance_days": int(grouped["is_rebalance_day"].sum()) if "is_rebalance_day" in grouped else 0,
    "return_days": int(len(grouped)),
}
```

**步骤 2：文档说明默认 3 日调仓**

写清楚：

```text
默认调仓周期为 3 个交易日。
每日收益仍然计算。
若需要旧版每日调仓结果，将 rebalance_period_days 设为 1。
```

### 任务 6：整体测试

**文件：**

- 测试：`/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py`
- 测试：`/Users/wangjiayi/Downloads/QuantaAlpha/tests/test_evaluation_services.py`

**步骤 1：跑单因子评估测试**

```bash
/Users/wangjiayi/Downloads/QuantaAlpha/.venv/bin/python -m pytest /Users/wangjiayi/Downloads/QuantaAlpha/tests/test_single_factor_evaluation.py -q
```

预期：

```text
passed
```

**步骤 2：跑服务层测试**

```bash
/Users/wangjiayi/Downloads/QuantaAlpha/.venv/bin/python -m pytest /Users/wangjiayi/Downloads/QuantaAlpha/tests/test_evaluation_services.py -q
```

预期：

```text
passed
```

## 十一、边界情况

- 第一个有效交易日必须强制调仓。
- 如果调仓日股票数量不足以分成 10 组，则跳过该日，继续等待下一个可调仓日。
- 如果非调仓日某只持仓股票没有有效 OTO 收益，则该股票从当天组内平均收益中剔除。
- 如果某组当天所有持仓股票都没有有效收益，则该组当天收益记为 `None`。
- 如果训练期/验证期边界截断了持仓区间，不跨边界补收益，继续遵守现有 `_period_panel()` 的区间约束。
- `rebalance_period_days` 按交易日计数，不按自然日计数。

## 十二、验收标准

- 默认配置为 `rebalance_period_days=3`。
- `rebalance_period_days=3` 时，第 1、4、7... 个有效交易日调仓，其余交易日持仓不变。
- 每个有效交易日都有组合收益和超额收益记录。
- 非调仓日所有组的手续费为 `0.0`。
- `rebalance_period_days=1` 可以复现旧版每日调仓行为。
- `alignment_audit.csv` 仍然证明 `factor_date < entry_date < exit_date`。
- 训练期、验证期、分年份/分半年度子区间都使用同一套调仓周期逻辑。

