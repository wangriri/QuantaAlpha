"""Load and resolve prompt packs for A/B testing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from quantaalpha.log import logger


PROMPT_PACK_ENV = "QUANTAALPHA_PROMPT_PACK"
DEFAULT_PROMPT_PACK = "zh_quant_v1"
PACKS_DIR = Path(__file__).parent / "packs"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_pack(pack_name: str | None = None) -> dict[str, Any]:
    name = pack_name or os.getenv(PROMPT_PACK_ENV) or DEFAULT_PROMPT_PACK
    path = PACKS_DIR / f"{name}.yaml"
    if not path.exists():
        logger.warning(f"Prompt pack not found: {path}; falling back to {DEFAULT_PROMPT_PACK}")
        name = DEFAULT_PROMPT_PACK
        path = PACKS_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("name", name)
    return data


def get_active_prompt_pack() -> str:
    return os.getenv(PROMPT_PACK_ENV) or DEFAULT_PROMPT_PACK


def configure_prompting(prompting_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Apply prompting config to environment for child processes and lazy imports."""

    cfg = prompting_cfg or {}
    pack = str(os.getenv(PROMPT_PACK_ENV) or cfg.get("pack") or DEFAULT_PROMPT_PACK)
    os.environ[PROMPT_PACK_ENV] = pack
    metadata = _load_pack(pack)
    logger.info(
        f"Prompt pack: {metadata.get('name', pack)} "
        f"(version={metadata.get('version', 'unknown')}, language={metadata.get('output_language', '')})"
    )
    return metadata


def get_prompt_pack_metadata(pack_name: str | None = None) -> dict[str, Any]:
    pack = _load_pack(pack_name)
    return {
        "name": pack.get("name", pack_name or get_active_prompt_pack()),
        "version": pack.get("version", ""),
        "output_language": pack.get("output_language", ""),
        "strict_json": bool(pack.get("strict_json", False)),
        "description": pack.get("description", ""),
    }


def resolve_planning_prompt_path(default_file: str | Path, pack_name: str | None = None) -> Path:
    pack = _load_pack(pack_name)
    prompt_file = pack.get("planning_prompt_file") or str(default_file)
    path = Path(prompt_file)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / "quantaalpha" / "pipeline" / "prompts" / path


def resolve_factor_prompts_path(default_path: str | Path, pack_name: str | None = None) -> Path:
    pack = _load_pack(pack_name)
    prompt_file = pack.get("factor_prompt_file")
    if not prompt_file:
        return Path(default_path)
    path = Path(prompt_file)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / "quantaalpha" / "factors" / "prompts" / path
