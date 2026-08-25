from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from .config import EvaluationConfig, PROJECT_ROOT


class MarketDataError(RuntimeError):
    """Retryable market data or infrastructure failure."""


class MarketDataProvider(Protocol):
    def load_trade_dates(self, start: str, end: str) -> list[pd.Timestamp]: ...

    def load_panel(self, start: str, end: str, refresh: bool = False) -> pd.DataFrame: ...


def _to_ymd(value: str | pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def _is_mainland_a_share(ts_code: str) -> bool:
    value = str(ts_code).upper()
    if "." not in value:
        return False
    code, exchange = value.split(".", 1)
    if exchange == "SH":
        return code.startswith(("600", "601", "603", "605", "688", "689"))
    if exchange == "SZ":
        return code.startswith(("000", "001", "002", "003", "300", "301"))
    return False


def _limit_ratio(code: str) -> float:
    return 0.20 if str(code)[:3] in {"300", "301", "688", "689"} else 0.10


def _attach_exact_next_session_return(
    prices: pd.DataFrame,
    trade_dates: list[pd.Timestamp],
) -> pd.DataFrame:
    """Attach the next market session, never the next available stock observation."""
    dates = sorted(pd.Timestamp(value).normalize() for value in trade_dates)
    next_session = {dates[index]: dates[index + 1] for index in range(len(dates) - 1)}
    result = prices.copy()
    result["exit_date"] = result["entry_date"].map(next_session)
    next_prices = result[["code", "entry_date", "open", "pre_close"]].rename(
        columns={
            "entry_date": "exit_date",
            "open": "next_open",
            "pre_close": "next_pre_close",
        }
    )
    result = result.merge(next_prices, on=["code", "exit_date"], how="left", validate="many_to_one")
    next_overnight = result["next_open"] / result["next_pre_close"].replace(0, np.nan)
    result["oto_return"] = (result["close"] / result["open"]) * next_overnight - 1.0
    return result


@dataclass
class MongoMarketDataProvider:
    config: EvaluationConfig

    def _database(self):
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise MarketDataError("pymongo is required for Mongo OTO evaluation") from exc

        uri = os.environ.get("MONGO_URI", "").strip()
        database_name = os.environ.get("MONGO_DB", "").strip()
        if not uri or not database_name:
            raise MarketDataError("MONGO_URI and MONGO_DB must be configured")
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=15000, connectTimeoutMS=15000)
            client.admin.command("ping")
            return client[database_name]
        except Exception as exc:
            raise MarketDataError(f"Mongo connection failed: {type(exc).__name__}") from exc

    def load_trade_dates(self, start: str, end: str) -> list[pd.Timestamp]:
        db = self._database()
        start_ymd, end_ymd = _to_ymd(start), _to_ymd(end)
        try:
            values = db["Index_DayLine"].distinct(
                "trade_date",
                {"ts_code": "000852.SH", "trade_date": {"$gte": start_ymd, "$lte": end_ymd}},
            )
        except Exception as exc:
            raise MarketDataError(f"Failed to load trade calendar: {type(exc).__name__}") from exc
        return sorted(pd.Timestamp(value) for value in values)

    def _cache_path(self, start: str, end: str) -> Path:
        raw = self.config.section("engine").get("market_cache_dir", "data/results/evaluation_cache")
        root = Path(raw)
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        return root / f"oto_panel_exact_session_v2_{_to_ymd(start)}_{_to_ymd(end)}.pkl"

    def load_panel(self, start: str, end: str, refresh: bool = False) -> pd.DataFrame:
        cache_path = self._cache_path(start, end)
        if cache_path.exists() and not refresh:
            panel = pd.read_pickle(cache_path)
            return self._validate_panel(panel)

        db = self._database()
        start_ymd, end_ymd = _to_ymd(start), _to_ymd(end)
        years = range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)
        price_frames: list[pd.DataFrame] = []
        st_frames: list[pd.DataFrame] = []
        try:
            collections = set(db.list_collection_names())
            for year in years:
                price_collection = f"Stock_DayLine_{year}"
                st_collection = f"stock_bak_daily_{year}"
                if price_collection not in collections:
                    raise MarketDataError(f"Mongo collection missing: {price_collection}")
                price_frames.append(
                    pd.DataFrame(
                        list(
                            db[price_collection].find(
                                {"trade_date": {"$gte": start_ymd, "$lte": end_ymd}},
                                {
                                    "_id": 0,
                                    "ts_code": 1,
                                    "trade_date": 1,
                                    "open": 1,
                                    "close": 1,
                                    "pre_close": 1,
                                },
                            )
                        )
                    )
                )
                if st_collection in collections:
                    st_frames.append(
                        pd.DataFrame(
                            list(
                                db[st_collection].find(
                                    {"trade_date": {"$gte": start_ymd, "$lte": end_ymd}},
                                    {"_id": 0, "ts_code": 1, "trade_date": 1, "name": 1},
                                )
                            )
                        )
                    )
        except MarketDataError:
            raise
        except Exception as exc:
            raise MarketDataError(f"Mongo market query failed: {type(exc).__name__}") from exc

        if not price_frames:
            raise MarketDataError("Mongo price panel is empty")
        prices = pd.concat(price_frames, ignore_index=True)
        prices = prices[prices["ts_code"].map(_is_mainland_a_share)].copy()
        if prices.empty:
            raise MarketDataError("No Shanghai/Shenzhen A-share rows in Mongo price panel")

        prices["code"] = prices["ts_code"].str[:6]
        prices["entry_date"] = pd.to_datetime(prices["trade_date"], format="%Y%m%d")
        prices = prices.sort_values(["code", "entry_date"]).reset_index(drop=True)
        prices["pre_close"] = pd.to_numeric(prices["pre_close"], errors="coerce").replace(0, np.nan)
        prices["open"] = pd.to_numeric(prices["open"], errors="coerce")
        prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
        try:
            calendar_values = db["Index_DayLine"].distinct(
                "trade_date",
                {"ts_code": "000852.SH", "trade_date": {"$gte": start_ymd, "$lte": end_ymd}},
            )
            trade_dates = sorted(pd.Timestamp(value) for value in calendar_values)
        except Exception as exc:
            raise MarketDataError(f"Failed to load exact-session calendar: {type(exc).__name__}") from exc
        if len(trade_dates) < 2:
            raise MarketDataError("Trade calendar has fewer than two sessions")
        prices = _attach_exact_next_session_return(prices, trade_dates)
        ratios = prices["code"].map(_limit_ratio)
        upper = (prices["pre_close"] * (1.0 + ratios)).round(2)
        lower = (prices["pre_close"] * (1.0 - ratios)).round(2)
        prices["open_limit"] = (prices["open"] >= upper - 0.001) | (prices["open"] <= lower + 0.001)

        prices["is_st"] = False
        if st_frames:
            st = pd.concat(st_frames, ignore_index=True)
            if not st.empty:
                st["code"] = st["ts_code"].astype(str).str[:6]
                st["entry_date"] = pd.to_datetime(st["trade_date"], format="%Y%m%d")
                st["is_st"] = st["name"].astype(str).str.contains("ST", na=False)
                st = st[["code", "entry_date", "is_st"]].drop_duplicates(["code", "entry_date"], keep="last")
                prices = prices.drop(columns=["is_st"]).merge(st, on=["code", "entry_date"], how="left")
                prices["is_st"] = prices["is_st"].astype("boolean").fillna(False).astype(bool)

        panel = prices[
            ["code", "entry_date", "exit_date", "oto_return", "open_limit", "is_st"]
        ].replace([np.inf, -np.inf], np.nan)
        panel = self._validate_panel(panel)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        panel.to_pickle(cache_path)
        return panel

    @staticmethod
    def _validate_panel(panel: pd.DataFrame) -> pd.DataFrame:
        required = {"code", "entry_date", "exit_date", "oto_return", "open_limit", "is_st"}
        missing = required.difference(panel.columns)
        if missing:
            raise MarketDataError(f"Market panel missing columns: {sorted(missing)}")
        result = panel.copy()
        result["entry_date"] = pd.to_datetime(result["entry_date"])
        result["exit_date"] = pd.to_datetime(result["exit_date"])
        result["code"] = result["code"].astype(str).str.zfill(6)
        return result.sort_values(["entry_date", "code"]).reset_index(drop=True)
