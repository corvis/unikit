#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
R = TypeVar("R")

Number = int | float
TAnyDate = TypeVar("TAnyDate", bound=datetime.date)

_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsDunderLT(Protocol[_T_contra]):
    """A type that supports the `<` operator."""

    def __lt__(self, __other: _T_contra) -> bool: ...


class SupportsDunderGT(Protocol[_T_contra]):
    """A type that supports the `>` operator."""

    def __gt__(self, __other: _T_contra) -> bool: ...


class SupportsDunderLE(Protocol[_T_contra]):
    """A type that supports the `<=` operator."""

    def __le__(self, __other: _T_contra) -> bool: ...


class SupportsDunderGE(Protocol[_T_contra]):
    """A type that supports the `>=` operator."""

    def __ge__(self, __other: _T_contra) -> bool: ...


class SupportsAllComparisons(
    SupportsDunderLT[Any], SupportsDunderGT[Any], SupportsDunderLE[Any], SupportsDunderGE[Any], Protocol
):
    """A type that supports all comparison operators."""

    ...


TSupportsAllComparisons = TypeVar("TSupportsAllComparisons", bound=SupportsAllComparisons)


def none_raises(optional: T | None, message: str = "Unexpected `None`") -> T:
    """Convert an optional to its value."""
    if optional is None:
        raise AssertionError(message)
    return optional
