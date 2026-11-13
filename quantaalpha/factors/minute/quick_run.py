"""Prepare a bounded, read-only minute mining acceptance run."""

from pathlib import Path

import pandas as pd
import yaml

from .mongo_reader import is_sh_sz_a_share


def prepare_quick_run(debug_hdf: Path, evaluation_yaml: Path, output_dir: Path) -> tuple[Path, Path, int]:
    """Write only a small daily input and evaluation config; minute bars stay in MongoDB."""
    daily = pd.read_hdf(debug_hdf, key="data")
    if not isinstance(daily.index, pd.MultiIndex) or not {"datetime", "instrument"}.issubset(daily.index.names):
        raise ValueError("Debug daily data must have datetime and instrument index levels")
    dates = pd.DatetimeIndex(daily.index.get_level_values("datetime").unique()).sort_values()
    if len(dates) < 20:
        raise ValueError("Minute quick run needs at least 20 trading dates")
    chosen = dates[-20:]
    date_index = daily.index.get_level_values("datetime")
    stock_index = daily.index.get_level_values("instrument")
    selected = daily.loc[date_index.isin(chosen) & stock_index.map(is_sh_sz_a_share)]
    if selected.empty:
        raise ValueError("Minute quick run has no SH/SZ A-share daily input")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir / "source"
    source_dir.mkdir(exist_ok=True)
    selected.to_hdf(source_dir / "daily_pv.h5", key="data", mode="w")

    config = yaml.safe_load(evaluation_yaml.read_text(encoding="utf-8"))
    config["periods"]["training"] = [chosen[0].strftime("%Y-%m-%d"), chosen[9].strftime("%Y-%m-%d")]
    config["periods"]["validation"] = [chosen[10].strftime("%Y-%m-%d"), chosen[-1].strftime("%Y-%m-%d")]
    config["engine"]["output_dir"] = str(output_dir / "evaluations")
    config["engine"]["market_cache_dir"] = str(output_dir / "market_cache")
    config_path = output_dir / "evaluation.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return source_dir / "daily_pv.h5", config_path, len(selected)
