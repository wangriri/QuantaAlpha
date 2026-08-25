# ADR: OTO 单因子评估替代 Qlib 评估链

## 状态

已采纳，评估引擎标识为 `oto_single_factor_v1`。

## 决策

因子生成、表达式解析和 `result.h5` 保持不变。因子质量评估不再训练 LightGBM，也不合并多个因子；每个因子独立进入 OTO 评估，并写入因子库的 `evaluation_v2`。旧 `backtest_results` 只作为 `qlib_legacy` 保留。

## 时间与收益口径

信号和交易严格按市场交易日历对齐：

```text
factor_date = previous_market_session(entry_date)
factor_date < entry_date < exit_date
F(t-1) -> open(t) -> open(t+1)
```

收益沿用公司 OTO 公式：

```text
OTO(t,t+1) = close(t) / open(t) * open(t+1) / pre_close(t+1) - 1
```

`exit_date` 必须是下一市场交易日，不能使用个股的下一条可用记录。股票在下一市场交易日缺行情时，该样本被剔除，不能跨到复牌日。春节等长假同样按交易日历连接。

训练期为 2023-01-01 至 2025-06-30，验证期为 2025-07-01 至 2025-12-31。收益的 entry 和 exit 必须同时位于所属区间。2026 的状态固定为 `sealed`，评估引擎、API 和 AI 反馈均不得读取或计算 2026 数据。

## 防未来审计

评估前执行两层检查：

1. 静态拒绝负周期 `DELAY`、`DELTA`、`TS_PCTCHANGE`、`shift`、`diff` 和 `pct_change`，以及非标准外部数据读取。
2. 在训练历史的 25%、50%、75% 截点截断 `daily_pv.h5`，重新执行 `factor.py`。截点当日结果必须与完整数据运行结果一致。

规则失败记为 `lookahead_rejected`，不能进入回测。Mongo 不可用或行情缺失记为可重试 `data_error`，不能当作因子质量失败。

## 指标与方向

每日 Pearson IC 为 `Corr(F(t-1), OTO(t,t+1))`。训练期原始 IC 为负时记录 `direction_multiplier=-1`，训练分组和验证期都使用该固定方向，验证期不得重新选择方向。

训练通过要求以下四项同时通过：

| 指标 | 口径 | 门槛 |
| --- | --- | ---: |
| IC | 训练期 `abs(mean(daily Pearson IC))` | 0.03 |
| ICIR | `abs(mean(IC))/std(IC)`，非年化 | 0.5 |
| 多空收益差 | 零费率 `sum(G9-G0)` | 0.30 |
| 超额 Sharpe | 扣费 G9 减扣费全市场等权基线 | 1.0 |

`G0` 是方向标准化后的低因子值组，`G9` 是高因子值组。分组使用 `qcut` 和未固定种子的微噪声。手续费为 2023 年及以前 `0.0007`、2024 年起 `0.00035`，头组和等权基线均按成员变化收费。

IC 半衰期、RankIC、RankICIR、年化 ICIR 参考、覆盖率、有效天数和股票数只报告。训练未通过时不运行 2025H2 验证；训练通过时保存验证指标及相对训练的保留率和退化率，但验证不作为硬淘汰门槛。

## 生命周期与去重

训练未通过的因子保留公式、因子值、指标和反馈，但 `active=false`。进化排序依次为训练通过、训练超额 Sharpe、绝对 IC、收益差。

每个批次按 `planning_direction` 计算训练期逐日横截面 Pearson 和 Spearman 相关。任一绝对相关达到 0.7 即进入疑似重复报告。系统只推荐保留超额 Sharpe 最高者；人工确认后其余因子标记为 `duplicate_rejected`，记录和缓存不删除。

## 接口与产物

正式任务入口为 `/api/v1/evaluations/start`。旧 `/api/v1/backtest/start` 只作为单因子评估兼容入口，`combined` 返回错误。

每个因子保存摘要 JSON、每日 IC、IC 衰减、十分组日收益和累计收益、头组与基线超额收益、时间对齐审计 CSV。运行时保存 `configs/evaluation.yaml` 的完整快照和哈希，Mongo 连接信息只从环境变量读取，禁止写入日志和产物。
