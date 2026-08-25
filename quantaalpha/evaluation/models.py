from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SingleFactorEvaluationResult:
    factor_id: str
    factor_name: str
    status: str
    evaluation_engine: str
    config_hash: str
    direction_multiplier: int = 1
    lookahead_audit: dict[str, Any] = field(default_factory=dict)
    alignment: dict[str, Any] = field(default_factory=dict)
    training: dict[str, Any] = field(default_factory=dict)
    subperiods: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    gate_results: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    lifecycle: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None
    oos_status: str = "sealed"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

