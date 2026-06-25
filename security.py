"""security.py – Deterministic pre-processing layer.

All three functions run before data reaches any LLM agent.
They raise ValueError on any violation so the UI can catch and display the
error without exposing a raw Python traceback.
"""
from __future__ import annotations

import re
from typing import Any

# Tags we want to strip before sending text to an LLM
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_EXCESS_WS_RE = re.compile(r"[ \t]{2,}")

MAX_CAMP_NODES = 30


def is_allowed_file(filename: str) -> bool:
    """Return True only if *filename* ends with '.json' (case-insensitive)."""
    return filename.strip().lower().endswith(".json")


def sanitize_json_text(raw_text: str) -> str:
    """Strip HTML/script tags and collapse excessive whitespace from *raw_text*.

    Returns the cleaned string. Does not raise – callers decide what to do with
    the sanitized output.
    """
    cleaned = _TAG_RE.sub("", raw_text)
    cleaned = _EXCESS_WS_RE.sub(" ", cleaned)
    return cleaned.strip()


def validate_node_count(data_dict: dict[str, Any]) -> None:
    """Validate warehouse and camp counts inside *data_dict*.

    Raises:
        ValueError: if there are fewer than 1 warehouse or the camp count is
                    outside the range [1, MAX_CAMP_NODES].
    """
    warehouses = data_dict.get("warehouses", [])
    camps = data_dict.get("camp_blocks", [])

    if len(warehouses) < 1:
        raise ValueError(
            "Security Error: Scenario must contain at least 1 warehouse."
        )

    if len(camps) < 1:
        raise ValueError(
            "Security Error: Scenario must contain at least 1 camp distribution point."
        )

    if len(camps) > MAX_CAMP_NODES:
        raise ValueError(
            f"Security Error: Node count exceeds maximum threshold of {MAX_CAMP_NODES}. "
            f"Found {len(camps)} camp blocks."
        )
