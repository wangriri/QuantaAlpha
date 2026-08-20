"""Prompt pack schema keys.

Prompt pack files are intentionally small manifests that point existing runtime
stages to concrete prompt YAML files. This keeps A/B testing lightweight while
avoiding a large refactor of prompt rendering code.
"""

from __future__ import annotations

from typing import TypedDict


class PromptPack(TypedDict, total=False):
    name: str
    version: str
    output_language: str
    strict_json: bool
    planning_prompt_file: str
    factor_prompt_file: str
    description: str
