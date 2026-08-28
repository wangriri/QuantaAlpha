from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .artifacts import ArtifactWriter
from .config import EvaluationConfig, load_evaluation_config
from .market_data import MarketDataError, MarketDataProvider, MongoMarketDataProvider
from .models import SingleFactorEvaluationResult


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _instrument_to_code(value: Any) -> str | None:
    text = str(value).strip().upper()
    if "." in text:
        left, right = text.split(".", 1)
        if right in {"SH", "SZ"} and left.isdigit():
            return left.zfill(6)
    if text.startswith(("SH", "SZ")) and text[2:].isdigit():
        return text[2:].zfill(6)
    if text.isdigit():
        return text.zfill(6)
    return None


def _daily_correlations(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date, group in frame.groupby("entry_date", sort=True):
        clean = group[["factor_value", "oto_return"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(clean) < 3 or clean["factor_value"].nunique() < 2 or clean["oto_return"].nunique() < 2:
            continue
        rows.append(
            {
                "date": pd.Timestamp(date),
                "ic": clean["factor_value"].corr(clean["oto_return"], method="pearson"),
                "rank_ic": clean["factor_value"].corr(clean["oto_return"], method="spearman"),
                "stock_count": len(clean),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["ic", "rank_ic", "stock_count"]).rename_axis("date")
    return pd.DataFrame(rows).set_index("date").sort_index()


@dataclass
class PeriodEvaluation:
    metrics: dict[str, Any]
    daily_ic: pd.DataFrame
    group_returns: pd.DataFrame
    excess_returns: pd.DataFrame
    aligned: pd.DataFrame


class SingleFactorEvaluator:
    """Evaluate one factor against the company's OTO execution target."""

    def __init__(
        self,
        config: EvaluationConfig | None = None,
        market_data: MarketDataProvider | None = None,
    ):
        self.config = config or load_evaluation_config()
        self.market_data = market_data or MongoMarketDataProvider(self.config)

    def evaluate(
        self,
        factor_values: pd.Series | pd.DataFrame,
        *,
        factor_id: str,
        factor_name: str,
        lookahead_audit: dict[str, Any] | None = None,
        run_id: str | None = None,
        refresh_market_cache: bool = False,
    ) -> SingleFactorEvaluationResult:
        engine_name = str(self.config.section("engine").get("name", "oto_single_factor_v1"))
        result = SingleFactorEvaluationResult(
            factor_id=factor_id,
            factor_name=factor_name,
            status="running",
            evaluation_engine=engine_name,
            config_hash=self.config.config_hash,
            config_snapshot=self.config.snapshot(),
            lookahead_audit=lookahead_audit or {"status": "not_run"},
            oos_status="sealed",
        )
        if result.lookahead_audit.get("status") in {"failed", "lookahead_rejected"}:
            result.status = "lookahead_rejected"
            result.lifecycle = {"status": "lookahead_rejected", "active": False}
            return result

        try:
            factor = self._normalize_factor(factor_values, factor_name)
            train_start, train_end = self.config.training_period
            valid_start, valid_end = self.config.validation_period
            calendar_start = (pd.Timestamp(train_start) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
            trade_dates = self.market_data.load_trade_dates(calendar_start, valid_end)
            panel = self.market_data.load_panel(train_start, valid_end, refresh=refresh_market_cache)
            panel = self._eligible_panel(panel)

            training_panel = self._period_panel(panel, train_start, train_end)
            training_aligned = self._align(factor, panel, trade_dates, train_start, train_end)
            raw_daily_ic = _daily_correlations(training_aligned)
            raw_ic = _finite(raw_daily_ic["ic"].mean()) if not raw_daily_ic.empty else None
            direction = -1 if raw_ic is not None and raw_ic < 0 else 1
            result.direction_multiplier = direction

            training = self._evaluate_period(training_aligned, direction, training_panel)
            decay = self._compute_ic_decay(factor, panel, trade_dates, train_start, train_end, direction)
            half_life = self._half_life(decay)
            training.metrics["ic_half_life"] = half_life
            training.metrics["ic_decay_max_lag"] = int(self.config.section("metrics").get("half_life_max_lag", 20))

            gates = self._gate_results(training.metrics)
            passed = all(item["passed"] for item in gates.values())
            result.status = "passed" if passed else "failed"
            result.gate_results = gates
            result.training = training.metrics
            result.alignment = self._alignment_summary(
                training.aligned,
                sorted(training_panel["entry_date"].dropna().unique()),
                train_start,
                train_end,
            )
            result.subperiods = self._subperiod_metrics(training.aligned, training_panel, direction)
            result.lifecycle = {
                "status": "candidate" if passed else "evaluation_failed",
                "active": bool(passed),
                "reason": "training_gates_passed" if passed else "training_gates_failed",
            }

            coverage = training.metrics.get("coverage", {})
            coverage_cfg = self.config.section("coverage")
            if coverage.get("day_ratio", 0.0) < float(coverage_cfg.get("warning_day_ratio", 0.9)):
                result.warnings.append("Factor covers fewer trading days than the configured warning ratio")
            if coverage.get("median_stock_count", 0) < int(coverage_cfg.get("warning_min_stocks", 1000)):
                result.warnings.append("Factor has a low median daily stock count")

            if passed or not self.config.section("validation").get("run_for_training_pass_only", True):
                validation_panel = self._period_panel(panel, valid_start, valid_end)
                validation_aligned = self._align(factor, panel, trade_dates, valid_start, valid_end)
                validation = self._evaluate_period(validation_aligned, direction, validation_panel)
                result.validation = validation.metrics
                result.validation["degradation_from_training"] = self._validation_degradation(
                    training.metrics,
                    validation.metrics,
                )
            else:
                validation = None
                result.validation = {"status": "skipped_training_failed", "hard_gate": False}

            writer = ArtifactWriter(self.config, factor_id, run_id or uuid.uuid4().hex[:12])
            result.artifacts = self._write_artifacts(writer, result, training, decay, validation)
            writer.write_json("summary.json", result.to_dict())
            result.artifacts["summary"] = str(writer.directory / "summary.json")
            return result
        except MarketDataError as exc:
            result.status = "data_error"
            result.lifecycle = {"status": "not_evaluated", "active": False, "reason": "retryable_data_error"}
            result.error = {"type": type(exc).__name__, "message": str(exc), "retryable": True}
            return result
        except Exception as exc:
            result.status = "failed"
            result.lifecycle = {"status": "evaluation_error", "active": False}
            result.error = {"type": type(exc).__name__, "message": str(exc), "retryable": False}
            return result

    @staticmethod
    def _normalize_factor(values: pd.Series | pd.DataFrame, factor_name: str) -> pd.DataFrame:
        if isinstance(values, pd.DataFrame):
            if factor_name in values.columns:
                series = values[factor_name]
            elif values.shape[1] == 1:
                series = values.iloc[:, 0]
            else:
                raise ValueError(f"Factor frame has multiple columns and no {factor_name!r} column")
        else:
            series = values
        if not isinstance(series.index, pd.MultiIndex) or series.index.nlevels != 2:
            raise ValueError("Factor values must use a two-level (datetime, instrument) MultiIndex")

        names = list(series.index.names)
        if "datetime" not in names or "instrument" not in names:
            inferred: list[str] = []
            for level in range(2):
                vals = series.index.get_level_values(level)
                inferred.append("datetime" if pd.api.types.is_datetime64_any_dtype(vals) else "instrument")
            series.index = series.index.set_names(inferred)
        frame = series.rename("factor_value").reset_index()
        frame["factor_date"] = pd.to_datetime(frame["datetime"], errors="coerce")
        frame["code"] = frame["instrument"].map(_instrument_to_code)
        frame["factor_value"] = pd.to_numeric(frame["factor_value"], errors="coerce")
        frame = frame[["factor_date", "code", "factor_value"]].replace([np.inf, -np.inf], np.nan).dropna()
        return frame.drop_duplicates(["factor_date", "code"], keep="last").sort_values(["factor_date", "code"])

    def _eligible_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        eligible = panel.copy()
        universe = self.config.section("universe")
        if universe.get("exclude_st", True):
            eligible = eligible[~eligible["is_st"].fillna(False)]
        if universe.get("exclude_open_limit", True):
            eligible = eligible[~eligible["open_limit"].fillna(False)]
        return eligible.dropna(subset=["entry_date", "exit_date", "oto_return"])

    @staticmethod
    def _period_panel(panel: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        return panel[
            (panel["entry_date"] >= start_ts)
            & (panel["entry_date"] <= end_ts)
            & (panel["exit_date"] >= start_ts)
            & (panel["exit_date"] <= end_ts)
        ].copy()

    @staticmethod
    def _calendar_previous_map(trade_dates: list[pd.Timestamp]) -> dict[pd.Timestamp, pd.Timestamp]:
        dates = sorted(pd.Timestamp(value).normalize() for value in trade_dates)
        return {dates[index]: dates[index - 1] for index in range(1, len(dates))}

    def _align(
        self,
        factor: pd.DataFrame,
        panel: pd.DataFrame,
        trade_dates: list[pd.Timestamp],
        start: str,
        end: str,
    ) -> pd.DataFrame:
        period_panel = self._period_panel(panel, start, end)
        previous = self._calendar_previous_map(trade_dates)
        period_panel["factor_date"] = period_panel["entry_date"].map(previous)
        period_panel = period_panel.dropna(subset=["factor_date"])
        aligned = period_panel.merge(factor, on=["factor_date", "code"], how="inner")
        aligned = aligned.replace([np.inf, -np.inf], np.nan).dropna(subset=["factor_value", "oto_return"])
        if not aligned.empty and not (aligned["factor_date"] < aligned["entry_date"]).all():
            raise ValueError("Look-ahead alignment detected: factor_date must precede entry_date")
        if not aligned.empty and not (aligned["entry_date"] < aligned["exit_date"]).all():
            raise ValueError("Invalid OTO alignment: entry_date must precede exit_date")
        return aligned.sort_values(["entry_date", "code"]).reset_index(drop=True)

    def _evaluate_period(
        self,
        aligned: pd.DataFrame,
        direction: int,
        benchmark_panel: pd.DataFrame | None = None,
    ) -> PeriodEvaluation:
        if aligned.empty:
            return PeriodEvaluation(
                metrics={
                    "status": "no_data",
                    "coverage": {},
                    "portfolio": {
                        "rebalance_period_days": self._rebalance_period_days(),
                        "rebalance_days": 0,
                        "return_days": 0,
                    },
                },
                daily_ic=pd.DataFrame(),
                group_returns=pd.DataFrame(),
                excess_returns=pd.DataFrame(),
                aligned=aligned,
            )
        daily_ic = _daily_correlations(aligned)
        raw_ic = _finite(daily_ic["ic"].mean())
        raw_ic_std = _finite(daily_ic["ic"].std(ddof=1))
        raw_rank_ic = _finite(daily_ic["rank_ic"].mean())
        rank_std = _finite(daily_ic["rank_ic"].std(ddof=1))
        icir = abs(raw_ic) / raw_ic_std if raw_ic is not None and raw_ic_std and raw_ic_std > 0 else None
        rank_icir = abs(raw_rank_ic) / rank_std if raw_rank_ic is not None and rank_std and rank_std > 0 else None

        grouped, excess = self._group_returns(aligned, direction, benchmark_panel)
        spread = None
        if not grouped.empty and {"G0", "G9"}.issubset(grouped.columns):
            spread = _finite((grouped["G9"] - grouped["G0"]).sum())
        sharpe = None
        if not excess.empty and excess["excess_return"].std(ddof=1) > 0:
            annualization = float(self.config.section("metrics").get("annualization", 252))
            sharpe = _finite(math.sqrt(annualization) * excess["excess_return"].mean() / excess["excess_return"].std(ddof=1))

        expected_days = int(benchmark_panel["entry_date"].nunique()) if benchmark_panel is not None else int(aligned["entry_date"].nunique())
        valid_days = int(aligned["entry_date"].nunique())
        counts = aligned.groupby("entry_date").size()
        portfolio = {
            "rebalance_period_days": self._rebalance_period_days(),
            "rebalance_days": int(grouped["is_rebalance_day"].sum()) if "is_rebalance_day" in grouped else 0,
            "return_days": int(len(grouped)),
        }
        metrics = {
            "status": "completed",
            "ic": raw_ic,
            "ic_abs": abs(raw_ic) if raw_ic is not None else None,
            "ic_std": raw_ic_std,
            "icir": _finite(icir),
            "icir_annualized_reference": _finite(icir * math.sqrt(252)) if icir is not None else None,
            "rank_ic": raw_rank_ic,
            "rank_icir": _finite(rank_icir),
            "rank_icir_annualized_reference": _finite(rank_icir * math.sqrt(252)) if rank_icir is not None else None,
            "directional_ic": _finite(raw_ic * direction) if raw_ic is not None else None,
            "long_short_spread": spread,
            "excess_sharpe": sharpe,
            "head_group_return_gross": _finite(grouped["G9"].sum()) if "G9" in grouped else None,
            "tail_group_return_gross": _finite(grouped["G0"].sum()) if "G0" in grouped else None,
            "portfolio": portfolio,
            "coverage": {
                "valid_days": valid_days,
                "expected_days": expected_days,
                "day_ratio": valid_days / expected_days if expected_days else 0.0,
                "median_stock_count": _finite(counts.median()),
                "min_stock_count": _finite(counts.min()),
                "max_stock_count": _finite(counts.max()),
            },
        }
        return PeriodEvaluation(metrics, daily_ic, grouped, excess, aligned)

    @staticmethod
    def _validation_degradation(training: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        comparable = {
            "directional_ic": (training.get("directional_ic"), validation.get("directional_ic")),
            "icir": (training.get("icir"), validation.get("icir")),
            "long_short_spread": (training.get("long_short_spread"), validation.get("long_short_spread")),
            "excess_sharpe": (training.get("excess_sharpe"), validation.get("excess_sharpe")),
        }
        for name, (training_value, validation_value) in comparable.items():
            train = _finite(training_value)
            valid = _finite(validation_value)
            retention = valid / train if train is not None and valid is not None and train != 0 else None
            output[name] = {
                "training": train,
                "validation": valid,
                "retention_ratio": _finite(retention),
                "degradation_ratio": _finite(1.0 - retention) if retention is not None else None,
            }
        return output

    def _fee_rate(self, date: pd.Timestamp) -> float:
        for item in self.config.section("costs").get("schedule", []):
            if pd.Timestamp(date) <= pd.Timestamp(item["end_date"]):
                return float(item["rate"])
        return 0.0

    def _rebalance_period_days(self) -> int:
        value = self.config.section("portfolio").get("rebalance_period_days", 3)
        days = int(value)
        if days < 1:
            raise ValueError("portfolio.rebalance_period_days must be >= 1")
        return days

    def _group_returns(
        self,
        aligned: pd.DataFrame,
        direction: int,
        benchmark_panel: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        metrics_cfg = self.config.section("metrics")
        group_count = int(metrics_cfg.get("group_count", 10))
        noise_std = float(metrics_cfg.get("qcut_noise_std", 1e-8))
        seed = metrics_cfg.get("qcut_random_seed")
        rng = np.random.default_rng(seed) if seed is not None else None
        rebalance_period = self._rebalance_period_days()
        current_groups: dict[int, set[str]] = {index: set() for index in range(group_count)}
        previous_groups: dict[int, set[str]] = {index: set() for index in range(group_count)}
        previous_benchmark: set[str] = set()
        current_benchmark: set[str] = set()
        days_since_rebalance = rebalance_period
        group_rows: list[dict[str, Any]] = []
        excess_rows: list[dict[str, Any]] = []
        benchmark_by_date = {
            pd.Timestamp(date): group[["code", "oto_return"]].dropna()
            for date, group in (benchmark_panel.groupby("entry_date") if benchmark_panel is not None else [])
        }
        aligned_by_date = {
            pd.Timestamp(date): group
            for date, group in aligned.groupby("entry_date", sort=True)
        }
        all_dates = sorted(benchmark_by_date.keys() if benchmark_by_date else aligned_by_date.keys())

        for date in all_dates:
            selection_day = aligned_by_date.get(pd.Timestamp(date), pd.DataFrame())
            return_day = benchmark_by_date.get(pd.Timestamp(date))
            if return_day is None:
                return_day = selection_day[["code", "oto_return"]].dropna()
            rate = self._fee_rate(pd.Timestamp(date))
            should_rebalance = days_since_rebalance >= rebalance_period or not any(current_groups.values())
            is_rebalance_day = False
            rebalance_skipped = False
            row: dict[str, Any] = {
                "date": pd.Timestamp(date),
                "is_rebalance_day": False,
                "rebalance_skipped": False,
                "rebalance_period_days": rebalance_period,
            }

            if should_rebalance:
                day = selection_day[["code", "factor_value"]].dropna().copy()
                if len(day) >= group_count:
                    day["oriented_factor"] = day["factor_value"] * direction
                    noise = (
                        rng.normal(0.0, noise_std, len(day))
                        if rng is not None
                        else np.random.normal(0.0, noise_std, len(day))
                    )
                    try:
                        day["group"] = pd.qcut(day["oriented_factor"] + noise, group_count, labels=False)
                        next_groups = {
                            group_index: set(day[day["group"] == group_index]["code"].astype(str))
                            for group_index in range(group_count)
                        }
                        current_groups = next_groups
                        is_rebalance_day = True
                        days_since_rebalance = 1
                    except ValueError:
                        rebalance_skipped = True
                else:
                    rebalance_skipped = True

            if not any(current_groups.values()):
                continue
            if not is_rebalance_day:
                days_since_rebalance += 1

            row["is_rebalance_day"] = is_rebalance_day
            row["rebalance_skipped"] = rebalance_skipped
            top_net = None
            returns = return_day.set_index("code")["oto_return"]
            for group_index in range(group_count):
                current = current_groups[group_index]
                previous = previous_groups[group_index]
                fee = 0.0
                if is_rebalance_day:
                    denominator = max(len(current), len(previous))
                    fee = len(current - previous) * 2.0 * rate / denominator if denominator else 0.0
                    previous_groups[group_index] = set(current)
                member_returns = returns.reindex(sorted(current)).dropna()
                gross = _finite(member_returns.mean()) if not member_returns.empty else None
                row[f"G{group_index}"] = gross
                row[f"G{group_index}_fee"] = fee
                if group_index == group_count - 1 and gross is not None:
                    top_net = gross - fee
            group_rows.append(row)

            benchmark_day = return_day
            if is_rebalance_day or not current_benchmark:
                current_benchmark = set(benchmark_day["code"].astype(str))
            benchmark_members = current_benchmark
            benchmark_fee = 0.0
            if is_rebalance_day:
                denominator = max(len(benchmark_members), len(previous_benchmark))
                benchmark_fee = (
                    len(benchmark_members - previous_benchmark) * 2.0 * rate / denominator if denominator else 0.0
                )
                previous_benchmark = set(benchmark_members)
            if not self.config.section("costs").get("charge_benchmark", True):
                benchmark_fee = 0.0
            benchmark_returns = benchmark_day.set_index("code")["oto_return"].reindex(sorted(benchmark_members)).dropna()
            benchmark_gross = _finite(benchmark_returns.mean()) if not benchmark_returns.empty else None
            if top_net is not None and benchmark_gross is not None:
                benchmark_net = benchmark_gross - benchmark_fee
                excess_rows.append(
                    {
                        "date": pd.Timestamp(date),
                        "head_net_return": top_net,
                        "benchmark_net_return": benchmark_net,
                        "excess_return": top_net - benchmark_net,
                        "benchmark_fee": benchmark_fee,
                        "is_rebalance_day": is_rebalance_day,
                        "rebalance_period_days": rebalance_period,
                    }
                )

        groups = pd.DataFrame(group_rows).set_index("date").sort_index() if group_rows else pd.DataFrame()
        excess = pd.DataFrame(excess_rows).set_index("date").sort_index() if excess_rows else pd.DataFrame()
        return groups, excess

    def _compute_ic_decay(
        self,
        factor: pd.DataFrame,
        panel: pd.DataFrame,
        trade_dates: list[pd.Timestamp],
        start: str,
        end: str,
        direction: int,
    ) -> pd.DataFrame:
        base = self._align(factor, panel, trade_dates, start, end)[["factor_date", "entry_date", "code", "factor_value"]]
        if base.empty:
            return pd.DataFrame(columns=["ic", "rank_ic", "days"])
        period_dates = [d for d in sorted(pd.Timestamp(x).normalize() for x in trade_dates) if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
        date_position = {date: index for index, date in enumerate(period_dates)}
        target_returns = panel[
            (panel["entry_date"] >= pd.Timestamp(start))
            & (panel["exit_date"] <= pd.Timestamp(end))
        ][["entry_date", "code", "oto_return"]].rename(columns={"entry_date": "target_date"})
        rows: list[dict[str, Any]] = []
        max_lag = int(self.config.section("metrics").get("half_life_max_lag", 20))
        for lag in range(1, max_lag + 1):
            mapping = {
                date: period_dates[position + lag - 1]
                for date, position in date_position.items()
                if position + lag - 1 < len(period_dates)
            }
            candidate = base.rename(columns={"entry_date": "signal_entry_date"}).copy()
            candidate["target_date"] = candidate["signal_entry_date"].map(mapping)
            candidate = candidate.dropna(subset=["target_date"]).merge(target_returns, on=["target_date", "code"], how="inner")
            candidate["factor_value"] = candidate["factor_value"] * direction
            candidate = candidate.rename(columns={"target_date": "entry_date"})
            daily = _daily_correlations(candidate[["entry_date", "factor_value", "oto_return"]])
            rows.append(
                {
                    "lag": lag,
                    "ic": _finite(daily["ic"].mean()) if not daily.empty else None,
                    "rank_ic": _finite(daily["rank_ic"].mean()) if not daily.empty else None,
                    "days": len(daily),
                }
            )
        return pd.DataFrame(rows).set_index("lag")

    def _half_life(self, decay: pd.DataFrame) -> int | str | None:
        if decay.empty or _finite(decay.iloc[0]["ic"]) is None:
            return None
        threshold = float(decay.iloc[0]["ic"]) * 0.5
        consecutive = int(self.config.section("metrics").get("half_life_consecutive", 3))
        values = decay["ic"].tolist()
        for index in range(0, len(values) - consecutive + 1):
            window = values[index : index + consecutive]
            if all(_finite(value) is not None and float(value) <= threshold for value in window):
                return index + 1
        return f">{len(values)}"

    def _gate_results(self, metrics: dict[str, Any]) -> dict[str, Any]:
        cfg = self.config.section("metrics")
        checks = {
            "ic": (metrics.get("ic_abs"), float(cfg.get("ic_threshold", 0.03))),
            "icir": (metrics.get("icir"), float(cfg.get("icir_threshold", 0.5))),
            "long_short_spread": (metrics.get("long_short_spread"), float(cfg.get("spread_threshold", 0.3))),
            "excess_sharpe": (metrics.get("excess_sharpe"), float(cfg.get("excess_sharpe_threshold", 1.0))),
        }
        return {
            name: {"value": _finite(value), "threshold": threshold, "operator": ">=", "passed": value is not None and float(value) >= threshold}
            for name, (value, threshold) in checks.items()
        }

    def _subperiod_metrics(
        self,
        aligned: pd.DataFrame,
        benchmark_panel: pd.DataFrame,
        direction: int,
    ) -> dict[str, Any]:
        periods = {
            "2023": ("2023-01-01", "2023-12-31"),
            "2024": ("2024-01-01", "2024-12-31"),
            "2025H1": ("2025-01-01", "2025-06-30"),
        }
        output: dict[str, Any] = {}
        for name, (start, end) in periods.items():
            subset = aligned[(aligned["entry_date"] >= start) & (aligned["exit_date"] <= end)]
            benchmark_subset = benchmark_panel[
                (benchmark_panel["entry_date"] >= start) & (benchmark_panel["exit_date"] <= end)
            ]
            output[name] = self._evaluate_period(subset, direction, benchmark_subset).metrics
        return output

    @staticmethod
    def _alignment_summary(
        aligned: pd.DataFrame,
        trade_dates: list[pd.Timestamp],
        start: str,
        end: str,
    ) -> dict[str, Any]:
        expected = [date for date in trade_dates if pd.Timestamp(start) <= date <= pd.Timestamp(end)]
        samples = aligned[["factor_date", "entry_date", "exit_date"]].drop_duplicates().head(20)
        return {
            "factor_lag_trading_days": 1,
            "label": "oto_open_to_open",
            "factor_before_entry": bool(aligned.empty or (aligned["factor_date"] < aligned["entry_date"]).all()),
            "entry_before_exit": bool(aligned.empty or (aligned["entry_date"] < aligned["exit_date"]).all()),
            "expected_trade_days": len(expected),
            "aligned_trade_days": int(aligned["entry_date"].nunique()),
            "samples": samples.astype(str).to_dict("records"),
        }

    def _write_artifacts(
        self,
        writer: ArtifactWriter,
        result: SingleFactorEvaluationResult,
        training: PeriodEvaluation,
        decay: pd.DataFrame,
        validation: PeriodEvaluation | None,
    ) -> dict[str, str]:
        artifacts = {
            "training_daily_ic": writer.write_frame("training_daily_ic.csv", training.daily_ic),
            "ic_decay": writer.write_frame("ic_decay.csv", decay),
            "training_group_returns": writer.write_frame("training_group_returns.csv", training.group_returns),
            "training_group_cumulative": writer.write_frame(
                "training_group_cumulative.csv", training.group_returns.filter(regex=r"^G\d+$").cumsum()
            ),
            "training_excess_returns": writer.write_frame("training_excess_returns.csv", training.excess_returns),
            "alignment_audit": writer.write_frame(
                "alignment_audit.csv",
                training.aligned[["factor_date", "entry_date", "exit_date", "code"]].drop_duplicates().head(1000),
            ),
        }
        if validation is not None:
            artifacts.update(
                {
                    "validation_daily_ic": writer.write_frame("validation_daily_ic.csv", validation.daily_ic),
                    "validation_group_returns": writer.write_frame("validation_group_returns.csv", validation.group_returns),
                    "validation_excess_returns": writer.write_frame("validation_excess_returns.csv", validation.excess_returns),
                }
            )
        return artifacts
