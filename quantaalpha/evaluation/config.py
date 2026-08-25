from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "evaluation.yaml"


@dataclass(frozen=True)
class EvaluationConfig:
    raw: dict[str, Any]
    path: Path

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    @property
    def config_hash(self) -> str:
        canonical = json.dumps(self.raw, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def training_period(self) -> tuple[str, str]:
        start, end = self.section("periods")["training"]
        return str(start), str(end)

    @property
    def validation_period(self) -> tuple[str, str]:
        start, end = self.section("periods")["validation"]
        return str(start), str(end)

    def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.raw, default=str))


def load_evaluation_config(path: str | Path | None = None) -> EvaluationConfig:
    config_path = Path(path or DEFAULT_CONFIG_PATH).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Evaluation config must be a mapping: {config_path}")
    return EvaluationConfig(raw=raw, path=config_path)

