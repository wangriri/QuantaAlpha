"""Prompt context assembly placeholders.

The first prompt-pack version intentionally does not add data_context or
factor_library_context. Keep this module as the future extension point so those
contexts are added only after the runtime can provide them truthfully.
"""

from __future__ import annotations


def build_prompt_context() -> dict:
    """Return currently supported prompt context.

    No extra context is exposed in the light version. Future work can add
    data_context, factor_library_context, and environment_context here.
    """

    return {}
