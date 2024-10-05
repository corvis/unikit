#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from collections.abc import Collection, Iterable
from typing import Sequence

from .types import T


def filter_none(collection: Sequence[T]) -> list[T]:
    """Return the copy of given list without None elements."""
    return list(filter(None, collection))


def filter_unique(collection: Collection[T]) -> list[T]:
    """Return a copy of passed `collection` without duplicates preserving order."""
    return list(dict.fromkeys(collection))


def ensure_list(list_or_obj: T | Iterable[T]) -> list[T]:
    """Wrap given object into list and returns as result unless given object is not list already."""
    if not isinstance(list_or_obj, (list, tuple)):
        return [list_or_obj]  # type: ignore
    if isinstance(list_or_obj, tuple):
        return list(list_or_obj)
    return list_or_obj
