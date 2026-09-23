from __future__ import annotations

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
                    "skippedFactors": skipped[:100],
                },
                "factors": factors,
            }
        )

    def _prepare_period(self, excess_returns: pd.DataFrame | None) -> dict[str, Any]:
        monthly = self.monthly_returns(excess_returns) if isinstance(excess_returns, pd.DataFrame) else pd.DataFrame()
        return {"monthly": monthly, "metrics": self.period_metrics(monthly)}

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
