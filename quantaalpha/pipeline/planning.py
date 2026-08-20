from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from quantaalpha.log import logger
from quantaalpha.llm.client import APIBackend
from quantaalpha.prompting import get_prompt_pack_metadata


def _load_prompts(prompt_file: Path) -> dict[str, str]:
    if not prompt_file.exists():
        return {}
    try:
        return yaml.safe_load(prompt_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning(f"Failed to load planning prompts: {exc}")
        return {}


def _extract_json(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    fence = re.search(r"```json\s*(.*?)```", t, re.DOTALL | re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start : end + 1]
    return t


def _parse_directions(message: str, n: int) -> list[str] | None:
    frag = _extract_json(message)
    try:
        data = json.loads(frag)
    except Exception:
        return None
    arr = data.get("directions") if isinstance(data, dict) else None
    if not isinstance(arr, list):
        return None
    vals = [str(x).strip() for x in arr if isinstance(x, str) and x.strip()]
    return vals if len(vals) >= n else None


def _fallback_directions(initial_direction: str, n: int) -> list[str]:
    base = initial_direction.strip() if initial_direction else "market microstructure"
    patterns = [
        f"{base} + short-term momentum signal with volume confirmation",
        f"{base} + volatility regime switch using rolling variance",
        f"{base} + liquidity/turnover adjustment for noise reduction",
        f"{base} + cross-sectional rank with sector-neutralization",
        f"{base} + intraday reversal vs overnight drift decomposition",
        f"{base} + fundamental proxy alignment (price-to-book, earnings momentum)",
        f"{base} + calendar effects and seasonality-aware normalization",
        f"{base} + risk-adjusted return features (downside volatility focus)",
    ]
    out = []
    for i in range(n):
        out.append(patterns[i % len(patterns)])
    return out


def generate_parallel_directions(
    initial_direction: str,
    n: int,
    prompt_file: Path,
    max_attempts: int = 5,
    use_llm: bool = True,
    allow_fallback: bool = True,
) -> list[str]:
    directions, _trace = generate_parallel_directions_with_trace(
        initial_direction=initial_direction,
        n=n,
        prompt_file=prompt_file,
        max_attempts=max_attempts,
        use_llm=use_llm,
        allow_fallback=allow_fallback,
    )
    return directions


def generate_parallel_directions_with_trace(
    initial_direction: str,
    n: int,
    prompt_file: Path,
    max_attempts: int = 5,
    use_llm: bool = True,
    allow_fallback: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    n = max(1, int(n))
    prompts = _load_prompts(prompt_file)
    sys_tpl = prompts.get("system", "")
    user_tpl = prompts.get("user", "")
    output_format = prompts.get("output_format", "")

    system_prompt = sys_tpl.format(initial_direction=initial_direction, n=n)
    user_prompt = user_tpl.format(initial_direction=initial_direction, n=n)
    if output_format:
        if "{n}" in output_format:
            output_format = output_format.replace("{n}", str(n))
        user_prompt = f"{user_prompt}\n\n{output_format}"

    trace: dict[str, Any] = {
        "raw": {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "variables": {
                "initial_direction": initial_direction,
                "n": n,
                "prompt_file": str(prompt_file),
                "prompt_pack": get_prompt_pack_metadata(),
            },
            "responses": [],
        },
        "parser": {"attempt_count": 0, "warnings": []},
        "fallback_used": False,
        "directions": [],
    }

    if not use_llm:
        directions = _fallback_directions(initial_direction, n) if allow_fallback else []
        trace["fallback_used"] = bool(directions)
        trace["directions"] = directions
        return directions, trace

    for attempt in range(1, max_attempts + 1):
        trace["parser"]["attempt_count"] = attempt
        try:
            resp = APIBackend().build_messages_and_create_chat_completion(
                user_prompt=user_prompt, system_prompt=system_prompt, json_mode=False
            )
            trace["raw"]["responses"].append({"attempt": attempt, "response_text": resp})
            directions = _parse_directions(resp, n)
            if directions:
                trace["directions"] = directions[:n]
                return directions[:n], trace
            system_prompt += "\n\nStrictly output valid JSON. No extra text."
            trace["parser"]["warnings"].append(f"Planning parse failed at attempt {attempt}")
            logger.warning(f"Planning parse failed (attempt {attempt}), retrying...")
        except Exception as exc:
            trace["raw"]["responses"].append({"attempt": attempt, "error": str(exc)})
            trace["parser"]["warnings"].append(f"Planning LLM call failed at attempt {attempt}: {exc}")
            logger.warning(f"Planning LLM call failed (attempt {attempt}): {exc}")

    directions = _fallback_directions(initial_direction, n) if allow_fallback else []
    trace["fallback_used"] = bool(directions)
    trace["directions"] = directions
    return directions, trace


def load_run_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning(f"Failed to load run config: {exc}")
        return {}
