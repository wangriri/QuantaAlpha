# 战术进攻型因子看板实施说明

## 目标

新增一个独立的前端“战术因子”看板，用来从已有单因子 OTO 评估产物中识别短期爆发明显、月度波动较高、适合研究观察的因子。

该功能保持独立：

- 不提供 CLI。
- 不触发新的 OTO 评估。
- 不读取 2026 封存数据。
- 不写回 `all_factors_library*.json`。
- 不改变 `evaluation_v2`、`gate_results` 或 `lifecycle`。
- 不把战术标签反馈给因子挖掘或进化流程。

## 数据来源

看板只读取已有评估产物：

- `evaluation_v2.artifacts.training_excess_returns`
- `evaluation_v2.artifacts.validation_excess_returns`

后端只允许读取 `data/results/factor_evaluations/` 下的 CSV，避免任意路径读取。

## 配置

战术阈值单独保存在：

```text
configs/tactical_analysis.yaml
```

默认配置：

```yaml
enabled: true
min_training_months: 6
min_validation_months: 3
min_trading_days_per_month: 10
strong_best_month_quantile: 0.85
burst_month_quantile: 0.80
high_volatility_quantile: 0.75
severe_loss_quantile: 0.15
severe_drawdown_quantile: 0.15
min_positive_month_ratio: 0.30
min_burst_month_count: 1
```

前端可以编辑并保存这些阈值。保存只会修改 `configs/tactical_analysis.yaml`，不会修改 `configs/evaluation.yaml`。

## 分类口径

每个因子按训练期和验证期分别计算：

- 有效月份数
- 平均月度超额
- 月度超额波动
- 最佳单月超额
- 最差单月超额
- 月度累计超额最大回撤
- 正收益月份比例
- 爆发月份数
- 最近 3 个月累计超额

标签：

- `战术进攻型`：最佳单月、月度波动、爆发月份和正收益月份比例都达标，且没有触发严重亏损/回撤分位。
- `高风险爆发型`：最佳单月很强，但最差月或月度回撤落入危险分位。
- `稳健候选型`：月度收益为正、正收益月份比例较高，且波动不高。
- `暂无战术价值`：不满足以上条件。
- `数据不足`：有效月份少于配置要求。

## 前端入口

导航新增：

```text
战术因子
```

页面包含：

- 因子库选择。
- 手动“开始战术分析”按钮。
- 战术阈值编辑面板。
- 总览统计。
- 战术因子表格。
- 因子详情弹窗，展示月度超额、累计月度超额、爆发月份、分类理由和训练/验证对比。

## 后端接口

```text
GET /api/v1/tactical/config
PUT /api/v1/tactical/config
POST /api/v1/tactical/analyze
```

`POST /api/v1/tactical/analyze` 请求：

```json
{
  "library": "all_factors_library.json"
}
```

响应包含：

- `summary`：总数、已分析、跳过数量、各标签计数、训练/验证分位阈值。
- `factors`：每个因子的训练期和验证期战术分析结果。

## 验证

已覆盖：

- 月度聚合过滤交易日不足月份。
- 同库相对分位阈值。
- 五类战术标签。
- 缺失训练期超额产物时跳过。
- artifact 路径必须位于评估产物目录。
- 独立 YAML 配置读取。
