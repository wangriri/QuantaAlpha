from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import PROJECT_ROOT, EvaluationConfig


class ArtifactWriter:
    def __init__(self, config: EvaluationConfig, factor_id: str, run_id: str):
        output_dir = Path(config.section("engine").get("output_dir", "data/results/factor_evaluations"))
        if not output_dir.is_absolute():
            output_dir = PROJECT_ROOT / output_dir
        self.directory = output_dir / factor_id / run_id
        self.directory.mkdir(parents=True, exist_ok=True)

    def write_frame(self, name: str, frame: pd.DataFrame | pd.Series) -> str:
        path = self.directory / name
        frame.to_csv(path)
        return str(path)

    def write_json(self, name: str, data: dict[str, Any]) -> str:
        path = self.directory / name
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
        temp.replace(path)
        return str(path)

