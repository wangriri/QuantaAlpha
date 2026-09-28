from __future__ import annotations

import re
from collections.abc import Iterable


def replace_data_column_tokens(expr: str, columns: Iterable[object], frame_name: str = "df") -> str:
    """Replace parsed data-column tokens with DataFrame column references.

    The expression parser strips the leading "$" from data variables, so "$pe_ttm"
    becomes "pe_ttm". A plain str.replace can corrupt prefixed names, e.g. replacing
    "pe" inside "pe_ttm". This helper matches complete identifier tokens only.
    """

    token_to_column: dict[str, str] = {}
    for column in columns:
        column_name = str(column)
        if column_name.startswith("$") and len(column_name) > 1:
            token_to_column[column_name[1:]] = column_name
    if not token_to_column:
        return expr

    token_pattern = "|".join(re.escape(token) for token in sorted(token_to_column, key=len, reverse=True))
    pattern = re.compile(rf"(?<![\w$'])({token_pattern})(?![\w'])")

    def repl(match: re.Match[str]) -> str:
        column_name = token_to_column[match.group(1)]
        return f"{frame_name}[{column_name!r}]"

    return pattern.sub(repl, expr)
