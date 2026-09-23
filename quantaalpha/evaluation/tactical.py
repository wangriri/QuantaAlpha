from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_TACTICAL_CONFIG: dict[str, Any] = {
    "enabled": True,
    "min_training_months": 6,
    "min_validation_months": 3,
    "min_trading_days_per_month": 10,
    "strong_best_month_quantile": 0.85,
    "burst_month_quantile": 0.80,
    "high_volatility_quantile": 0.75,
    "severe_loss_quantile": 0.15,
    "severe_drawdown_quantile": 0.15,
    "min_positive_month_ratio": 0.30,
    "min_burst_month_count": 1,
    "high_return_correlation_threshold": 0.98,
    "duplicate_return_correlation_threshold": 0.9999,
    "min_return_correlation_overlap": 20,
    "return_correlation_group_size": 5,
    "return_correlation_group_avg_threshold": 0.70,
    "max_return_correlation_groups": 50,
}

TACTICAL_LABELS = ("战术进攻型", "高风险爆发型", "稳健候选型", "暂无战术价值", "数据不足")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return _finite(value)
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if value is not None and not isinstance(value, (str, bytes)) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _clip01(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _quantile(values: list[float | None], q: float) -> float | None:
    clean = [float(value) for value in values if _finite(value) is not None]
    if not clean:
        return None
    return _finite(np.quantile(clean, q))


def _percentile_rank(values: list[float | None], value: float | None) -> float | None:
    finite_values = np.array([float(item) for item in values if _finite(item) is not None], dtype=float)
    if value is None or not len(finite_values):
        return None
    return _finite((np.sum(finite_values <= float(value)) - 0.5) / len(finite_values))


def compute_monthly_drawdown(monthly_returns: pd.Series) -> float | None:
    if monthly_returns.empty:
        return None
    cumulative = monthly_returns.fillna(0.0).cumsum()
    baseline = pd.Series([0.0], index=[cumulative.index[0] - 1])
    path = pd.concat([baseline, cumulative])
    drawdown = path - path.cummax()
    return _finite(drawdown.min())


@dataclass
class TacticalFactorAnalyzer:
    config: dict[str, Any] | None = None

    @property
    def settings(self) -> dict[str, Any]:
        merged = dict(DEFAULT_TACTICAL_CONFIG)
        if isinstance(self.config, dict):
            merged.update({key: value for key, value in self.config.items() if key in DEFAULT_TACTICAL_CONFIG})
        return merged

    def monthly_returns(self, excess_returns: pd.DataFrame) -> pd.DataFrame:
        if excess_returns is None or excess_returns.empty or "excess_return" not in excess_returns.columns:
            return pd.DataFrame(columns=["month", "monthly_excess", "trading_days", "cumulative_excess"])

        frame = self._returns_frame(excess_returns)
        if frame.empty:
            return pd.DataFrame(columns=["month", "monthly_excess", "trading_days", "cumulative_excess"])

        frame["month"] = frame["date"].dt.to_period("M")
        grouped = frame.groupby("month")["excess_return"].agg(monthly_excess="sum", trading_days="count")
        min_days = int(self.settings.get("min_trading_days_per_month", 10))
        grouped = grouped[grouped["trading_days"] >= min_days].sort_index()
        if grouped.empty:
            return pd.DataFrame(columns=["month", "monthly_excess", "trading_days", "cumulative_excess"])

        grouped["cumulative_excess"] = grouped["monthly_excess"].cumsum()
        grouped = grouped.reset_index()
        grouped["month"] = grouped["month"].astype(str)
        return grouped

    def daily_excess_series(self, excess_returns: pd.DataFrame | None) -> pd.Series:
        if not isinstance(excess_returns, pd.DataFrame):
            return pd.Series(dtype=float)
        frame = self._returns_frame(excess_returns)
        if frame.empty:
            return pd.Series(dtype=float)
        series = frame.groupby("date")["excess_return"].sum().sort_index()
        return pd.to_numeric(series, errors="coerce").dropna()

    @staticmethod
    def _returns_frame(excess_returns: pd.DataFrame) -> pd.DataFrame:
        if excess_returns is None or excess_returns.empty or "excess_return" not in excess_returns.columns:
            return pd.DataFrame(columns=["date", "excess_return"])

        frame = excess_returns.copy()
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        elif frame.index.name == "date" or isinstance(frame.index, pd.DatetimeIndex):
            frame["date"] = pd.to_datetime(frame.index, errors="coerce")
        else:
            first_column = str(frame.columns[0]) if len(frame.columns) else ""
            if first_column.lower().startswith("unnamed") or first_column in {"index", ""}:
                frame["date"] = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
            else:
                frame["date"] = pd.to_datetime(frame.index, errors="coerce")

        frame["excess_return"] = pd.to_numeric(frame["excess_return"], errors="coerce")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["date", "excess_return"])
        frame["date"] = frame["date"].dt.normalize()
        return frame[["date", "excess_return"]]

    def period_metrics(self, monthly: pd.DataFrame) -> dict[str, Any]:
        if monthly.empty:
            return {
                "valid_months": 0,
                "mean_monthly_excess": None,
                "monthly_excess_std": None,
                "best_month_excess": None,
                "worst_month_excess": None,
                "max_monthly_drawdown": None,
                "positive_month_ratio": 0.0,
                "burst_month_count": 0,
                "recent_3m_excess": None,
                "annualized_excess_return": None,
                "daily_excess_count": 0,
            }
        returns = pd.to_numeric(monthly["monthly_excess"], errors="coerce").dropna()
        valid_months = int(len(returns))
        return {
            "valid_months": valid_months,
            "mean_monthly_excess": _finite(returns.mean()),
            "monthly_excess_std": _finite(returns.std(ddof=1)) if valid_months > 1 else 0.0,
            "best_month_excess": _finite(returns.max()),
            "worst_month_excess": _finite(returns.min()),
            "max_monthly_drawdown": compute_monthly_drawdown(returns),
            "positive_month_ratio": _finite((returns > 0).mean()) or 0.0,
            "burst_month_count": 0,
            "recent_3m_excess": _finite(returns.tail(3).sum()) if valid_months else None,
            "annualized_excess_return": None,
            "daily_excess_count": 0,
        }

    def analyze_factors(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        prepared: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for record in records:
            factor_id = str(record.get("factorId") or record.get("factor_id") or "")
            training_excess = record.get("training_excess")
            if not isinstance(training_excess, pd.DataFrame):
                skipped.append({"factorId": factor_id, "reason": record.get("skipReason") or "缺少训练期超额收益产物"})
                continue

            item = {
                "factorId": factor_id,
                "factorName": record.get("factorName") or record.get("factor_name") or factor_id,
                "factorExpression": record.get("factorExpression") or record.get("factor_expression") or "",
                "factorDescription": record.get("factorDescription") or record.get("factor_description") or "",
                "evaluationStatus": record.get("evaluationStatus") or record.get("evaluation_status") or "not_evaluated",
                "_training_daily": self.daily_excess_series(training_excess),
                "_validation_daily": self.daily_excess_series(record.get("validation_excess")),
                "training": self._prepare_period(training_excess),
                "validation": self._prepare_period(record.get("validation_excess"))
                if isinstance(record.get("validation_excess"), pd.DataFrame)
                else None,
            }
            prepared.append(item)

        thresholds = {
            "training": self._period_thresholds([item["training"] for item in prepared], "training"),
            "validation": self._period_thresholds([item["validation"] for item in prepared if item["validation"]], "validation"),
        }

        for item in prepared:
            item["training"] = self._finalize_period(item["training"], thresholds["training"], "training")
            if item["validation"] is not None:
                item["validation"] = self._finalize_period(item["validation"], thresholds["validation"], "validation")

        correlations = {
            "training": self._return_correlations(prepared, "training"),
            "validation": self._return_correlations(
                [item for item in prepared if item.get("validation") is not None],
                "validation",
            ),
        }
        for period_name in ["training", "validation"]:
            per_factor = correlations[period_name]["byFactor"]
            for item in prepared:
                period = item.get(period_name)
                if period is not None:
                    period["returnCorrelation"] = per_factor.get(item["factorId"], self._empty_return_correlation())
        for item in prepared:
            item.pop("_training_daily", None)
            item.pop("_validation_daily", None)

        label_counts = {label: 0 for label in TACTICAL_LABELS}
        for item in prepared:
            label = item["training"]["label"]
            label_counts[label] = label_counts.get(label, 0) + 1

        factors = sorted(prepared, key=self._sort_key)
        return _clean(
            {
                "summary": {
                    "total": len(records),
                    "analyzed": len(prepared),
                    "skipped": len(skipped),
                    "labels": label_counts,
                    "thresholds": {
                        "training": self._public_thresholds(thresholds["training"]),
                        "validation": self._public_thresholds(thresholds["validation"]),
                    },
                    "returnCorrelation": {
                        "training": correlations["training"]["summary"],
                        "validation": correlations["validation"]["summary"],
                    },
                    "skippedFactors": skipped[:100],
                },
                "factors": factors,
            }
        )

    def test_factor_group(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        from quantaalpha.evaluation.config import load_evaluation_config

        if len(records) < 2:
            raise ValueError("至少需要两个因子才能进行组合测试")

        evaluation_config = load_evaluation_config()
        train_start, _train_end = map(pd.Timestamp, evaluation_config.training_period)
        _valid_start, valid_end = map(pd.Timestamp, evaluation_config.validation_period)
        value_frames: dict[str, pd.DataFrame] = {}
        factors: list[dict[str, Any]] = []
        for record in records:
            factor_id = str(record.get("factorId") or record.get("factor_id") or "")
            factor_name = record.get("factorName") or record.get("factor_name") or factor_id
            factor_values = record.get("factor_values")
            if not isinstance(factor_values, (pd.Series, pd.DataFrame)):
                raise ValueError(f"因子 {factor_name} 缺少 result.h5 因子值")
            frame = self._normalize_factor_values(factor_values, str(factor_name))
            frame = frame[(frame["factor_date"] >= train_start) & (frame["factor_date"] <= valid_end)].copy()
            if frame.empty:
                raise ValueError(f"因子 {factor_name} 的因子值为空")
            value_frames[factor_id] = frame
            factors.append({
                "factorId": factor_id,
                "factorName": factor_name,
                "factorExpression": record.get("factorExpression") or record.get("factor_expression") or "",
                "directionMultiplier": int(record.get("directionMultiplier") or record.get("direction_multiplier") or 1),
                "training_excess": record.get("training_excess"),
                "validation_excess": record.get("validation_excess"),
            })

        value_correlation = self._factor_value_group_correlation(factors, value_frames)
        composite_values = self._equal_weight_score(factors, value_frames)
        strategy = self._evaluate_score_strategy(composite_values, factors)
        return _clean({
            "factorIds": [factor["factorId"] for factor in factors],
            "factorNames": [factor["factorName"] for factor in factors],
            "factorValueCorrelation": value_correlation,
            "strategy": strategy,
        })

    def _return_correlations(self, items: list[dict[str, Any]], period_name: str) -> dict[str, Any]:
        cfg = self.settings
        high_threshold = float(cfg.get("high_return_correlation_threshold", 0.98))
        duplicate_threshold = float(cfg.get("duplicate_return_correlation_threshold", 0.9999))
        min_overlap = int(cfg.get("min_return_correlation_overlap", 20))
        series_key = f"_{period_name}_daily"
        by_factor = {item["factorId"]: self._empty_return_correlation() for item in items}
        high_pairs: list[dict[str, Any]] = []
        matrix: dict[tuple[str, str], dict[str, Any]] = {}
        max_correlation: float | None = None

        for left_index, left in enumerate(items):
            left_series = left.get(series_key)
            if not isinstance(left_series, pd.Series) or left_series.empty:
                continue
            for right in items[left_index + 1:]:
                right_series = right.get(series_key)
                if not isinstance(right_series, pd.Series) or right_series.empty:
                    continue
                aligned = pd.concat([left_series, right_series], axis=1, join="inner").dropna()
                aligned.columns = ["left", "right"]
                overlap = int(len(aligned))
                if overlap < min_overlap:
                    continue
                if float(aligned["left"].std(ddof=0)) == 0.0 or float(aligned["right"].std(ddof=0)) == 0.0:
                    continue
                correlation = _finite(aligned["left"].corr(aligned["right"]))
                if correlation is None:
                    continue
                max_abs_diff = _finite((aligned["left"] - aligned["right"]).abs().max())
                max_correlation = correlation if max_correlation is None else max(max_correlation, correlation)
                matrix[self._pair_key(left["factorId"], right["factorId"])] = {
                    "correlation": correlation,
                    "overlapDays": overlap,
                    "maxAbsDiff": max_abs_diff,
                }
                if correlation < high_threshold:
                    continue

                duplicate_like = correlation >= duplicate_threshold or (max_abs_diff is not None and max_abs_diff <= 1e-12)
                pair = {
                    "period": period_name,
                    "factorId": left["factorId"],
                    "factorName": left.get("factorName") or left["factorId"],
                    "peerFactorId": right["factorId"],
                    "peerFactorName": right.get("factorName") or right["factorId"],
                    "correlation": correlation,
                    "overlapDays": overlap,
                    "maxAbsDiff": max_abs_diff,
                    "duplicateLike": duplicate_like,
                }
                high_pairs.append(pair)
                self._append_peer(by_factor[left["factorId"]], pair)
                self._append_peer(by_factor[right["factorId"]], self._reverse_pair(pair))

        for correlation in by_factor.values():
            peers = sorted(correlation["peers"], key=lambda peer: (not peer.get("duplicateLike"), -float(peer.get("correlation") or 0.0)))[:8]
            correlation["peers"] = peers
            correlation["highCorrelationCount"] = len(peers)
            correlation["duplicateLikeCount"] = sum(1 for peer in peers if peer.get("duplicateLike"))
            correlation["maxCorrelation"] = peers[0]["correlation"] if peers else None
            correlation["maxPeerFactorId"] = peers[0]["factorId"] if peers else None
            correlation["maxPeerFactorName"] = peers[0]["factorName"] if peers else None

        high_pair_count = len(high_pairs)
        duplicate_pair_count = sum(1 for pair in high_pairs if pair.get("duplicateLike"))
        high_pairs = sorted(high_pairs, key=lambda pair: (not pair.get("duplicateLike"), -float(pair.get("correlation") or 0.0)))[:100]
        group_candidates = self._positive_annualized_group_candidates(items, period_name)
        groups = self._return_correlation_groups(group_candidates, matrix, period_name)
        return {
            "summary": {
                "threshold": high_threshold,
                "duplicateThreshold": duplicate_threshold,
                "minOverlapDays": min_overlap,
                "highPairCount": high_pair_count,
                "duplicateLikePairCount": duplicate_pair_count,
                "maxCorrelation": max_correlation,
                "pairs": high_pairs[:20],
                "groups": groups,
                "groupSize": int(cfg.get("return_correlation_group_size", 5)),
                "groupAvgThreshold": float(cfg.get("return_correlation_group_avg_threshold", 0.70)),
                "groupPositiveAnnualizedFilter": True,
                "groupEligibleFactorCount": len(group_candidates),
                "groupExcludedNonPositiveAnnualizedCount": max(0, len(items) - len(group_candidates)),
            },
            "byFactor": by_factor,
        }

    def _factor_value_group_correlation(
        self,
        factors: list[dict[str, Any]],
        value_frames: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        pairs: list[dict[str, Any]] = []
        for left, right in itertools.combinations(factors, 2):
            pearson, spearman, days, median_stocks = self._factor_value_pair_correlation(
                value_frames[left["factorId"]],
                value_frames[right["factorId"]],
            )
            pairs.append({
                "factorId": left["factorId"],
                "factorName": left["factorName"],
                "peerFactorId": right["factorId"],
                "peerFactorName": right["factorName"],
                "pearson": pearson,
                "spearman": spearman,
                "overlapDays": days,
                "medianStocks": median_stocks,
            })
        pearsons = [pair["pearson"] for pair in pairs if pair["pearson"] is not None]
        spearmans = [pair["spearman"] for pair in pairs if pair["spearman"] is not None]
        return {
            "groupSize": len(factors),
            "pairCount": len(pairs),
            "averagePearson": _finite(np.mean(pearsons)) if pearsons else None,
            "averageSpearman": _finite(np.mean(spearmans)) if spearmans else None,
            "minPearson": _finite(np.min(pearsons)) if pearsons else None,
            "minSpearman": _finite(np.min(spearmans)) if spearmans else None,
            "pairs": sorted(pairs, key=lambda pair: float(pair.get("pearson") or -2.0)),
        }

    @staticmethod
    def _factor_value_pair_correlation(left: pd.DataFrame, right: pd.DataFrame) -> tuple[float | None, float | None, int, float | None]:
        merged = left.merge(right, on=["factor_date", "code"], suffixes=("_left", "_right"))
        pearson_values: list[float] = []
        spearman_values: list[float] = []
        stock_counts: list[int] = []
        for _date, group in merged.groupby("factor_date", sort=True):
            clean = group[["factor_value_left", "factor_value_right"]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(clean) < 3 or clean["factor_value_left"].nunique() < 2 or clean["factor_value_right"].nunique() < 2:
                continue
            pearson = clean["factor_value_left"].corr(clean["factor_value_right"], method="pearson")
            spearman = clean["factor_value_left"].corr(clean["factor_value_right"], method="spearman")
            if pd.notna(pearson):
                pearson_values.append(float(pearson))
            if pd.notna(spearman):
                spearman_values.append(float(spearman))
            stock_counts.append(int(len(clean)))
        return (
            _finite(np.mean(pearson_values)) if pearson_values else None,
            _finite(np.mean(spearman_values)) if spearman_values else None,
            max(len(pearson_values), len(spearman_values)),
            _finite(np.median(stock_counts)) if stock_counts else None,
        )

    @staticmethod
    def _normalize_factor_values(values: pd.Series | pd.DataFrame, factor_name: str) -> pd.DataFrame:
        from quantaalpha.evaluation.engine import SingleFactorEvaluator

        return SingleFactorEvaluator._normalize_factor(values, factor_name)

    def _equal_weight_score(
        self,
        factors: list[dict[str, Any]],
        value_frames: dict[str, pd.DataFrame],
    ) -> pd.Series:
        merged: pd.DataFrame | None = None
        value_columns: list[str] = []
        for index, factor in enumerate(factors):
            column = f"value_{index}"
            frame = value_frames[factor["factorId"]].rename(columns={"factor_value": column}).copy()
            frame[column] = pd.to_numeric(frame[column], errors="coerce") * int(factor.get("directionMultiplier") or 1)
            frame = frame[["factor_date", "code", column]].dropna()
            value_columns.append(column)
            merged = frame if merged is None else merged.merge(frame, on=["factor_date", "code"], how="inner")
        if merged is None or merged.empty:
            raise ValueError("组合因子没有可对齐的共同因子值")

        for column in value_columns:
            grouped = merged.groupby("factor_date")[column]
            mean = grouped.transform("mean")
            std = grouped.transform("std").replace(0.0, np.nan)
            merged[column] = (merged[column] - mean) / std
        merged = merged.dropna(subset=value_columns)
        if merged.empty:
            raise ValueError("组合因子标准化后没有有效样本")
        merged["score"] = merged[value_columns].mean(axis=1)
        series = merged.set_index(["factor_date", "code"])["score"].sort_index()
        series.index = series.index.set_names(["datetime", "instrument"])
        return series.rename("equal_weight_score")

    def _evaluate_score_strategy(
        self,
        composite_values: pd.Series,
        factors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from quantaalpha.evaluation.config import load_evaluation_config
        from quantaalpha.evaluation.engine import SingleFactorEvaluator

        config = load_evaluation_config()
        evaluator = SingleFactorEvaluator(config)
        factor = evaluator._normalize_factor(composite_values, "equal_weight_score")
        train_start, train_end = config.training_period
        valid_start, valid_end = config.validation_period
        cached_panel = self._load_cached_market_panel(config, train_start, valid_end)
        if cached_panel is not None:
            panel = evaluator._eligible_panel(cached_panel)
            trade_dates = sorted(
                pd.Timestamp(value).normalize()
                for value in pd.concat([panel["entry_date"], panel["exit_date"]]).dropna().unique()
            )
        else:
            calendar_start = (pd.Timestamp(train_start) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
            trade_dates = evaluator.market_data.load_trade_dates(calendar_start, valid_end)
            panel = evaluator._eligible_panel(evaluator.market_data.load_panel(train_start, valid_end))

        training_panel = evaluator._period_panel(panel, train_start, train_end)
        training_aligned = evaluator._align(factor, panel, trade_dates, train_start, train_end)
        training = evaluator._evaluate_period(training_aligned, 1, training_panel)
        if not training_aligned.empty and not (training_aligned["factor_date"] < training_aligned["entry_date"]).all():
            raise ValueError("Look-ahead alignment detected in tactical group strategy")

        validation_panel = evaluator._period_panel(panel, valid_start, valid_end)
        validation_aligned = evaluator._align(factor, panel, trade_dates, valid_start, valid_end)
        validation = evaluator._evaluate_period(validation_aligned, 1, validation_panel)

        training_components = self._component_periods(factors, "training")
        validation_components = self._component_periods(factors, "validation")
        return {
            "method": {
                "name": "五因子等权评分模型",
                "formula": "score = mean(zscore(direction_i * factor_i))",
                "direction": "使用各因子 evaluation_v2.direction_multiplier 做方向统一；组合自身 direction 固定为 +1",
                "selection": "沿用 OTO 单因子评估：按当日组合评分做横截面 qcut，取最高组相对基准的超额收益",
            },
            "alignment": {
                "factorLagTradingDays": 1,
                "factorBeforeEntry": bool(training_aligned.empty or (training_aligned["factor_date"] < training_aligned["entry_date"]).all()),
                "entryBeforeExit": bool(training_aligned.empty or (training_aligned["entry_date"] < training_aligned["exit_date"]).all()),
                "trainingPeriod": [train_start, train_end],
                "validationPeriod": [valid_start, valid_end],
                "oosStatus": "sealed",
            },
            "training": self._strategy_period_result(training, training_components),
            "validation": self._strategy_period_result(validation, validation_components),
        }

    @staticmethod
    def _load_cached_market_panel(config: Any, start: str, end: str) -> pd.DataFrame | None:
        from quantaalpha.evaluation.market_data import MongoMarketDataProvider

        provider = MongoMarketDataProvider(config)
        cache_path = provider._cache_path(start, end)
        if not cache_path.exists():
            return None
        return provider._validate_panel(pd.read_pickle(cache_path))

    def _component_periods(self, factors: list[dict[str, Any]], period_name: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        key = f"{period_name}_excess"
        for factor in factors:
            frame = factor.get(key)
            if not isinstance(frame, pd.DataFrame):
                output.append({
                    "factorId": factor["factorId"],
                    "factorName": factor["factorName"],
                    "metrics": self._period_return_metrics(pd.DataFrame()),
                    "monthly": [],
                })
                continue
            monthly = self.monthly_returns(frame)
            output.append({
                "factorId": factor["factorId"],
                "factorName": factor["factorName"],
                "metrics": self._period_return_metrics(monthly),
                "monthly": monthly.to_dict("records") if not monthly.empty else [],
            })
        return output

    def _strategy_period_result(self, period: Any, components: list[dict[str, Any]]) -> dict[str, Any]:
        monthly = self.monthly_returns(period.excess_returns)
        component_metrics = [item["metrics"] for item in components if item.get("metrics", {}).get("valid_months")]
        component_avg = self._average_return_metrics(component_metrics)
        combination_metrics = self._period_return_metrics(monthly, daily_excess=period.excess_returns)
        return {
            "metrics": combination_metrics,
            "evaluationMetrics": period.metrics,
            "monthly": monthly.to_dict("records") if not monthly.empty else [],
            "components": components,
            "comparison": self._compare_metrics(combination_metrics, component_avg),
        }

    @staticmethod
    def _period_return_metrics(monthly: pd.DataFrame, daily_excess: pd.DataFrame | None = None) -> dict[str, Any]:
        if monthly.empty:
            return {
                "valid_months": 0,
                "total_excess": None,
                "mean_monthly_excess": None,
                "monthly_excess_std": None,
                "best_month_excess": None,
                "worst_month_excess": None,
                "max_monthly_drawdown": None,
                "excess_sharpe": None,
            }
        returns = pd.to_numeric(monthly["monthly_excess"], errors="coerce").dropna()
        sharpe = None
        if daily_excess is not None and not daily_excess.empty and "excess_return" in daily_excess:
            daily = pd.to_numeric(daily_excess["excess_return"], errors="coerce").dropna()
            if len(daily) > 1 and daily.std(ddof=1) > 0:
                sharpe = math.sqrt(252) * daily.mean() / daily.std(ddof=1)
        return {
            "valid_months": int(len(returns)),
            "total_excess": _finite(returns.sum()),
            "mean_monthly_excess": _finite(returns.mean()),
            "monthly_excess_std": _finite(returns.std(ddof=1)) if len(returns) > 1 else 0.0,
            "best_month_excess": _finite(returns.max()),
            "worst_month_excess": _finite(returns.min()),
            "max_monthly_drawdown": compute_monthly_drawdown(returns),
            "excess_sharpe": _finite(sharpe),
        }

    @staticmethod
    def _average_return_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
        keys = [
            "total_excess",
            "mean_monthly_excess",
            "monthly_excess_std",
            "best_month_excess",
            "worst_month_excess",
            "max_monthly_drawdown",
            "excess_sharpe",
        ]
        output: dict[str, Any] = {"valid_months": _finite(np.mean([item.get("valid_months") for item in metrics])) if metrics else 0}
        for key in keys:
            values = [item.get(key) for item in metrics if item.get(key) is not None]
            output[key] = _finite(np.mean(values)) if values else None
        return output

    @staticmethod
    def _compare_metrics(combination: dict[str, Any], component_average: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {"componentAverage": component_average, "deltas": {}, "summary": []}
        labels = {
            "total_excess": "累计超额",
            "mean_monthly_excess": "平均月度超额",
            "monthly_excess_std": "月度波动",
            "worst_month_excess": "最差单月",
            "max_monthly_drawdown": "最大月度回撤",
            "excess_sharpe": "超额 Sharpe",
        }
        for key, label in labels.items():
            combo = combination.get(key)
            base = component_average.get(key)
            delta = combo - base if combo is not None and base is not None else None
            output["deltas"][key] = _finite(delta)
            if delta is None:
                continue
            if key in {"monthly_excess_std"}:
                direction = "下降" if delta < 0 else "上升"
            elif key in {"max_monthly_drawdown"}:
                direction = "改善" if delta > 0 else "恶化"
            else:
                direction = "提升" if delta > 0 else "回退"
            output["summary"].append(f"{label}{direction} {abs(delta) * 100:.2f}pct")
        return output

    def _return_correlation_groups(
        self,
        items: list[dict[str, Any]],
        matrix: dict[tuple[str, str], dict[str, Any]],
        period_name: str,
    ) -> list[dict[str, Any]]:
        cfg = self.settings
        group_size = int(cfg.get("return_correlation_group_size", 5))
        avg_threshold = float(cfg.get("return_correlation_group_avg_threshold", 0.70))
        max_groups = int(cfg.get("max_return_correlation_groups", 50))
        if group_size < 2 or len(items) < group_size or not matrix or max_groups <= 0:
            return []

        ids = [item["factorId"] for item in items]
        names = {item["factorId"]: item.get("factorName") or item["factorId"] for item in items}
        total_pairs = group_size * (group_size - 1) // 2
        min_sum = avg_threshold * total_pairs
        groups: list[dict[str, Any]] = []

        for combo in itertools.combinations(ids, group_size):
            pair_rows: list[dict[str, Any]] = []
            corr_sum = 0.0
            min_corr: float | None = None
            min_overlap: int | None = None
            complete = True
            for left, right in itertools.combinations(combo, 2):
                pair = matrix.get(self._pair_key(left, right))
                if pair is None:
                    complete = False
                    break
                corr = float(pair["correlation"])
                corr_sum += corr
                min_corr = corr if min_corr is None else min(min_corr, corr)
                overlap = int(pair["overlapDays"])
                min_overlap = overlap if min_overlap is None else min(min_overlap, overlap)
                pair_rows.append({
                    "factorId": left,
                    "peerFactorId": right,
                    "factorName": names[left],
                    "peerFactorName": names[right],
                    "correlation": corr,
                    "overlapDays": overlap,
                })
            if not complete:
                continue
            avg_corr = corr_sum / total_pairs
            if avg_corr < avg_threshold:
                continue
            groups.append({
                "period": period_name,
                "factorIds": list(combo),
                "factorNames": [names[factor_id] for factor_id in combo],
                "averageCorrelation": _finite(avg_corr),
                "minPairCorrelation": _finite(min_corr),
                "minOverlapDays": min_overlap,
                "pairCount": total_pairs,
                "pairs": sorted(pair_rows, key=lambda row: float(row["correlation"])),
            })

        return sorted(groups, key=lambda group: -float(group.get("averageCorrelation") or 0.0))[:max_groups]

    @staticmethod
    def _positive_annualized_group_candidates(items: list[dict[str, Any]], period_name: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in items:
            period = item.get(period_name) or {}
            metrics = period.get("metrics") or {}
            annualized = _finite(metrics.get("annualized_excess_return"))
            if annualized is not None and annualized > 0:
                candidates.append(item)
        return candidates

    @staticmethod
    def _empty_return_correlation() -> dict[str, Any]:
        return {
            "maxCorrelation": None,
            "maxPeerFactorId": None,
            "maxPeerFactorName": None,
            "highCorrelationCount": 0,
            "duplicateLikeCount": 0,
            "peers": [],
        }

    @staticmethod
    def _append_peer(target: dict[str, Any], pair: dict[str, Any]) -> None:
        target["peers"].append({
            "factorId": pair["peerFactorId"],
            "factorName": pair["peerFactorName"],
            "correlation": pair["correlation"],
            "overlapDays": pair["overlapDays"],
            "maxAbsDiff": pair["maxAbsDiff"],
            "duplicateLike": pair["duplicateLike"],
        })

    @staticmethod
    def _reverse_pair(pair: dict[str, Any]) -> dict[str, Any]:
        reversed_pair = dict(pair)
        reversed_pair["factorId"] = pair["peerFactorId"]
        reversed_pair["factorName"] = pair["peerFactorName"]
        reversed_pair["peerFactorId"] = pair["factorId"]
        reversed_pair["peerFactorName"] = pair["factorName"]
        return reversed_pair

    @staticmethod
    def _pair_key(left: str, right: str) -> tuple[str, str]:
        return tuple(sorted((left, right)))

    def _prepare_period(self, excess_returns: pd.DataFrame | None) -> dict[str, Any]:
        monthly = self.monthly_returns(excess_returns) if isinstance(excess_returns, pd.DataFrame) else pd.DataFrame()
        metrics = self.period_metrics(monthly)
        daily = self.daily_excess_series(excess_returns)
        if not daily.empty:
            metrics["annualized_excess_return"] = _finite(daily.mean() * 252.0)
            metrics["daily_excess_count"] = int(len(daily))
        return {"monthly": monthly, "metrics": metrics}

    def _period_thresholds(self, periods: list[dict[str, Any]], period_name: str) -> dict[str, Any]:
        cfg = self.settings
        min_months = int(cfg.get("min_training_months", 6) if period_name == "training" else cfg.get("min_validation_months", 3))
        metrics = [
            period["metrics"]
            for period in periods
            if period and period.get("metrics") and int((period["metrics"] or {}).get("valid_months") or 0) >= min_months
        ]
        monthly_values: list[float | None] = []
        for period in periods:
            monthly = period.get("monthly") if isinstance(period, dict) else None
            if (
                isinstance(monthly, pd.DataFrame)
                and not monthly.empty
                and int((period.get("metrics") or {}).get("valid_months") or 0) >= min_months
            ):
                monthly_values.extend([_finite(value) for value in monthly["monthly_excess"].tolist()])

        return {
            "strong_best_month": _quantile(
                [metric.get("best_month_excess") for metric in metrics],
                float(cfg.get("strong_best_month_quantile", 0.85)),
            ),
            "burst_month": _quantile(monthly_values, float(cfg.get("burst_month_quantile", 0.80))),
            "high_volatility": _quantile(
                [metric.get("monthly_excess_std") for metric in metrics],
                float(cfg.get("high_volatility_quantile", 0.75)),
            ),
            "severe_loss": _quantile(
                [metric.get("worst_month_excess") for metric in metrics],
                float(cfg.get("severe_loss_quantile", 0.15)),
            ),
            "severe_drawdown": _quantile(
                [metric.get("max_monthly_drawdown") for metric in metrics],
                float(cfg.get("severe_drawdown_quantile", 0.15)),
            ),
            "best_month_values": [metric.get("best_month_excess") for metric in metrics],
            "volatility_values": [metric.get("monthly_excess_std") for metric in metrics],
            "worst_month_values": [metric.get("worst_month_excess") for metric in metrics],
            "drawdown_values": [metric.get("max_monthly_drawdown") for metric in metrics],
        }

    def _finalize_period(self, period: dict[str, Any], thresholds: dict[str, Any], period_name: str) -> dict[str, Any]:
        monthly = period["monthly"].copy()
        metrics = dict(period["metrics"])
        burst_threshold = thresholds.get("burst_month")
        if not monthly.empty and burst_threshold is not None:
            monthly["is_burst"] = monthly["monthly_excess"] >= float(burst_threshold)
        else:
            monthly["is_burst"] = False
        burst_count = int(monthly["is_burst"].sum()) if not monthly.empty else 0
        metrics["burst_month_count"] = burst_count
        metrics["burst_month_ratio"] = burst_count / metrics["valid_months"] if metrics.get("valid_months") else 0.0
        metrics["best_month_percentile"] = _percentile_rank(
            thresholds.get("best_month_values", []),
            metrics.get("best_month_excess"),
        )
        metrics["volatility_percentile"] = _percentile_rank(
            thresholds.get("volatility_values", []),
            metrics.get("monthly_excess_std"),
        )
        metrics["worst_month_percentile"] = _percentile_rank(
            thresholds.get("worst_month_values", []),
            metrics.get("worst_month_excess"),
        )
        metrics["drawdown_percentile"] = _percentile_rank(
            thresholds.get("drawdown_values", []),
            metrics.get("max_monthly_drawdown"),
        )
        classification = self._classify(metrics, thresholds, period_name)
        monthly_records = monthly.to_dict("records") if not monthly.empty else []
        burst_records = monthly[monthly["is_burst"]].to_dict("records") if not monthly.empty else []
        return {
            "label": classification["label"],
            "score": classification["score"],
            "metrics": metrics,
            "monthly": monthly_records,
            "burstMonths": burst_records,
            "reasons": classification["reasons"],
            "thresholds": {key: thresholds.get(key) for key in ["strong_best_month", "burst_month", "high_volatility", "severe_loss", "severe_drawdown"]},
        }

    def _classify(self, metrics: dict[str, Any], thresholds: dict[str, Any], period_name: str) -> dict[str, Any]:
        cfg = self.settings
        min_months = int(cfg.get("min_training_months", 6) if period_name == "training" else cfg.get("min_validation_months", 3))
        valid_months = int(metrics.get("valid_months") or 0)
        if valid_months < min_months:
            return {"label": "数据不足", "score": 0.0, "reasons": [f"有效月份 {valid_months} 少于要求 {min_months}"]}

        best = metrics.get("best_month_excess")
        volatility = metrics.get("monthly_excess_std")
        worst = metrics.get("worst_month_excess")
        drawdown = metrics.get("max_monthly_drawdown")
        strong_best = best is not None and thresholds.get("strong_best_month") is not None and best >= thresholds["strong_best_month"]
        high_vol = volatility is not None and thresholds.get("high_volatility") is not None and volatility >= thresholds["high_volatility"]
        severe_loss = worst is not None and thresholds.get("severe_loss") is not None and worst <= thresholds["severe_loss"]
        severe_drawdown = drawdown is not None and thresholds.get("severe_drawdown") is not None and drawdown <= thresholds["severe_drawdown"]
        positive_ok = float(metrics.get("positive_month_ratio") or 0.0) >= float(cfg.get("min_positive_month_ratio", 0.3))
        burst_ok = int(metrics.get("burst_month_count") or 0) >= int(cfg.get("min_burst_month_count", 1))

        reasons: list[str] = []
        if strong_best:
            reasons.append("最佳单月位于同库高分位")
        if high_vol:
            reasons.append("月度波动位于同库高分位")
        if burst_ok:
            reasons.append("存在达到同库爆发阈值的月份")
        if positive_ok:
            reasons.append("正收益月份比例达标")
        if severe_loss:
            reasons.append("最差单月落入同库危险分位")
        if severe_drawdown:
            reasons.append("月度累计回撤落入同库危险分位")

        score = self._score(metrics, severe_loss=severe_loss, severe_drawdown=severe_drawdown)
        if strong_best and (severe_loss or severe_drawdown):
            return {"label": "高风险爆发型", "score": score, "reasons": reasons}
        if strong_best and high_vol and burst_ok and positive_ok:
            reasons.append("下行风险未触发危险分位")
            return {"label": "战术进攻型", "score": score, "reasons": reasons}
        if (
            (metrics.get("mean_monthly_excess") or 0.0) > 0
            and float(metrics.get("positive_month_ratio") or 0.0) >= 0.5
            and not high_vol
            and not severe_loss
            and not severe_drawdown
        ):
            reasons.append("月度收益为正且波动不高")
            return {"label": "稳健候选型", "score": score, "reasons": reasons}
        if not reasons:
            reasons.append("未达到爆发、稳定或风险识别条件")
        return {"label": "暂无战术价值", "score": score, "reasons": reasons}

    @staticmethod
    def _public_thresholds(thresholds: dict[str, Any]) -> dict[str, Any]:
        return {
            key: thresholds.get(key)
            for key in ["strong_best_month", "burst_month", "high_volatility", "severe_loss", "severe_drawdown"]
        }

    @staticmethod
    def _score(metrics: dict[str, Any], *, severe_loss: bool, severe_drawdown: bool) -> float:
        best_score = _clip01(metrics.get("best_month_percentile"))
        volatility_score = _clip01(metrics.get("volatility_percentile"))
        burst_score = _clip01((metrics.get("burst_month_count") or 0) / 3.0)
        downside_score = 0.0 if severe_loss or severe_drawdown else min(
            _clip01(metrics.get("worst_month_percentile")),
            _clip01(metrics.get("drawdown_percentile")),
        )
        return round(0.35 * best_score + 0.25 * volatility_score + 0.20 * burst_score + 0.20 * downside_score, 4)

    @staticmethod
    def _sort_key(item: dict[str, Any]) -> tuple[int, float, float]:
        order = {"战术进攻型": 0, "高风险爆发型": 1, "稳健候选型": 2, "暂无战术价值": 3, "数据不足": 4}
        training = item.get("training") or {}
        metrics = training.get("metrics") or {}
        return (
            order.get(training.get("label"), 99),
            -float(training.get("score") or 0.0),
            -float(metrics.get("best_month_excess") or 0.0),
        )
