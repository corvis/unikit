#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
__all__ = (
    "apply_pipeline",
    "normalize_spaces",
    "dedup_spaces",
    "strip_spaces",
    "strip_newlines",
)

import re
from typing import Callable, Sequence

_RE_WHITESPACES = re.compile(r"[\s\n]", re.IGNORECASE)
_RE_MULTIPLE_WHITESPACES = re.compile(r"\s+", re.IGNORECASE)


def normalize_spaces(input_: str) -> str:
    """Replace all whitespace characters with a single space."""
    return _RE_WHITESPACES.sub(" ", input_)


def dedup_spaces(input_: str) -> str:
    """Replace multiple spaces with a single space."""
    return _RE_MULTIPLE_WHITESPACES.sub(" ", input_)


def strip_spaces(input_: str) -> str:
    """Strip leading and trailing spaces from a string."""
    return input_.strip()


def strip_newlines(input_: str) -> str:
    """Strip newline characters from the beginning and end of the string."""
    return input_.strip("\n")


def apply_pipeline(target: str, pipeline: Sequence[Callable[[str], str]]) -> str:
    """Apply a sequence of functions to a string."""
    res = target
    for p in pipeline:
        res = p(res)
    return res
