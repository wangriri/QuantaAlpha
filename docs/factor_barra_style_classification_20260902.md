# 因子库 Barra 风格分类

本文按截图中的 Barra 风格大类，对 `all_factors_library_exp_20260821_153508` 中 21 个因子做人工归类。

需要注意：当前因子库主要基于日频价量字段构造，包括 `$open`、`$close`、`$high`、`$low`、`$volume`、`$amount`、`$return`。因此大部分因子只能落在“动量”“流动性”“残差波动”相关类别；“成长”“盈利预期”“账面市值比”“杠杆”“市值”“非线性市值”等基本面或市值类大类，在当前这批因子中基本没有直接对应项。

## 分类口径

| Barra 风格大类 | 当前口径说明 | 当前因子库覆盖情况 |
|---|---|---|
| Beta | 对市场组合收益的敏感度，通常需要个股收益相对指数/市场收益回归 | 暂无直接因子 |
| 残差波动 | 个股收益波动、特异波动、波动状态调节项 | 少量因子作为主类或辅类 |
| 成长 | 收入、利润、资产等基本面成长 | 暂无直接因子 |
| 动量 | 过去收益趋势、反转、隔夜/日内收益结构、价格位置趋势 | 当前主力类别 |
| 非线性市值 | 市值的非线性变换，如 Size 的立方项残差 | 暂无直接因子 |
| 杠杆 | 财务杠杆、负债率等 | 暂无直接因子 |
| 流动性 | 成交量、成交额、量比、量价配合、流动性调节项 | 当前主力类别 |
| 市值 | 总市值/流通市值等规模暴露 | 暂无直接因子 |
| 盈利预期 | 盈利收益率、分析师预期盈利等 | 暂无直接因子 |
| 账面市值比 | 账面价值/市值、价值因子 | 暂无直接因子 |

## 因子逐项分类

| 序号 | 因子 ID | 因子名称 | 主类 | 辅类 | 分类理由 |
|---:|---|---|---|---|---|
| 1 | `df02445ad05db071` | `Reversal_Volume_Interaction_Rank_5D_20D` | 动量 | 流动性 | 以 5 日收益反转为核心，并用 5 日/20 日量比调节。 |
| 2 | `7ef9d13d6d24f999` | `Conditional_Extreme_Reversal_Volume_5D` | 动量 | 流动性 | 只在短期放量且收益为负时输出反转信号，属于反转动量的流动性条件化版本。 |
| 3 | `95c7a207894923e8` | `ZScore_Reversal_Volume_Interaction_5D_20D` | 动量 | 流动性 | 对反转强度和量比做时序标准化后交互，核心仍是反转信号。 |
| 4 | `5985b341c52c44d7` | `VolumePrice_Concordance_10D` | 流动性 | 动量 | 衡量收益方向与成交量变化方向的一致性，核心是量价配合状态。 |
| 5 | `d2384d0db48c1922` | `VolumePrice_Corr_10D` | 流动性 | 动量 | 计算收益与成交量变化的滚动相关，属于量价同步/背离状态。 |
| 6 | `bc79a87d1993bfb3` | `VolumePrice_Asymmetry_10D` | 流动性 | 动量 | 统计上涨放量与下跌放量天数差，主暴露是量价不对称。 |
| 7 | `38da793f6ba8733a` | `Intraday_Position_Trend_Interaction_10D` | 动量 | 价格位置 | 结合收盘价在日内高低区间的位置与 10 日趋势方向。 |
| 8 | `9b6534efa8484ba1` | `Overnight_Intraday_Return_Differential_10D` | 动量 | 隔夜/日内结构 | 比较隔夜收益和日内收益的 10 日均值排名差，属于收益成分动量/反转结构。 |
| 9 | `f7233eadb536931a` | `Trend_Adjusted_Price_Position_20D` | 动量 | 价格位置 | 用 20 日价格位置乘以短期收益方向，属于趋势状态调整后的价格位置因子。 |
| 10 | `bce321c2a9884646` | `Liquidity_Adjusted_Momentum_20D_5D` | 流动性 | 动量 | 以 20 日平均成交额排名调节 5 日超额收益。 |
| 11 | `9896bde1b0c46764` | `Liquidity_Excess_Return_Coverage_5D` | 流动性 | 动量 | 用中心化流动性排名乘以 5 日收益标准分。 |
| 12 | `9a590eb1ee51435d` | `Liquidity_Momentum_Volatility_Regime_20D_5D` | 流动性 | 动量、残差波动 | 同时包含成交额排名、5 日收益和 20 日收益波动率。 |
| 13 | `a1d342f500466b36` | `Liquidity_Weighted_Volume_Reversal_Factor` | 流动性 | 动量 | 以成交额排名加权放量反转信号。 |
| 14 | `befdae294e0b2b58` | `Volatility_Modulated_Volume_Reversal_Factor` | 残差波动 | 动量、流动性 | 用 20 日收益波动率调节放量反转，波动暴露较明确。 |
| 15 | `0611579c82e4ecbb` | `Liquidity_Volatility_Cross_Reversal_Factor` | 流动性 | 残差波动、动量 | 成交额排名、波动率排名和放量反转共同交互。 |
| 16 | `66e1a1c8dca44d7f` | `VolumePrice_Reversal_Interaction_10D` | 动量 | 流动性、价格位置 | 综合短期跌势、缩量状态和日内收盘位置，核心是超跌反转。 |
| 17 | `62d432d02f1155ca` | `VolumeWeakness_Continuation_10D` | 动量 | 流动性、价格位置 | 刻画放量下跌、收盘低位、高开低走的下跌延续状态。 |
| 18 | `aec33f675c4df56f` | `OvernightIntraday_Diff_Reversal_10D` | 动量 | 隔夜/日内结构 | 将短期下跌与隔夜/日内收益差结合，核心是反转信号。 |
| 19 | `3d57226fb0347783` | `Reversal_Volume_Linear_Interaction` | 动量 | 流动性 | 直接用反转排名乘以量比排名。 |
| 20 | `86a3a4cc7f80c447` | `Reversal_Volume_InvertedU_Weight` | 动量 | 流动性 | 反转强度乘以量比偏离 1 的倒 U 型权重。 |
| 21 | `f1c98ca31e3ceedb` | `Reversal_Volume_Moderate_Zone` | 动量 | 流动性 | 只在量比适中区间输出反转排名。 |

## 按大类汇总

| 主类 | 因子数量 | 因子 |
|---|---:|---|
| 动量 | 12 | `Reversal_Volume_Interaction_Rank_5D_20D`, `Conditional_Extreme_Reversal_Volume_5D`, `ZScore_Reversal_Volume_Interaction_5D_20D`, `Intraday_Position_Trend_Interaction_10D`, `Overnight_Intraday_Return_Differential_10D`, `Trend_Adjusted_Price_Position_20D`, `VolumePrice_Reversal_Interaction_10D`, `VolumeWeakness_Continuation_10D`, `OvernightIntraday_Diff_Reversal_10D`, `Reversal_Volume_Linear_Interaction`, `Reversal_Volume_InvertedU_Weight`, `Reversal_Volume_Moderate_Zone` |
| 流动性 | 8 | `VolumePrice_Concordance_10D`, `VolumePrice_Corr_10D`, `VolumePrice_Asymmetry_10D`, `Liquidity_Adjusted_Momentum_20D_5D`, `Liquidity_Excess_Return_Coverage_5D`, `Liquidity_Momentum_Volatility_Regime_20D_5D`, `Liquidity_Weighted_Volume_Reversal_Factor`, `Liquidity_Volatility_Cross_Reversal_Factor` |
| 残差波动 | 1 | `Volatility_Modulated_Volume_Reversal_Factor` |
| Beta | 0 | 暂无 |
| 成长 | 0 | 暂无 |
| 非线性市值 | 0 | 暂无 |
| 杠杆 | 0 | 暂无 |
| 市值 | 0 | 暂无 |
| 盈利预期 | 0 | 暂无 |
| 账面市值比 | 0 | 暂无 |

## 结论

这批因子不是标准 Barra 十大风格因子的全覆盖，而是一组以价量数据为基础的交易型因子。主线集中在：

1. 短期反转/趋势状态，也就是“动量”类。
2. 成交量、成交额、量价配合，也就是“流动性”类。
3. 少量波动率调节项，可归入“残差波动”或作为辅类。

若后续需要覆盖“成长、盈利预期、账面市值比、杠杆、市值、非线性市值”，需要引入财务报表、估值、市值、指数收益或风险模型残差等额外原始数据维度。
