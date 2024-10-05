#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
__all__ = ("raise_or_default", "OnErrorDef")

from typing import TypeVar, Union, cast

TDefault = TypeVar("TDefault")
OnErrorDef = Union[type[Exception], TDefault, None]


def raise_or_default(on_error: OnErrorDef[TDefault], error_msg: str) -> TDefault | None:
    """Raise an exception or return a default value."""
    if isinstance(on_error, type) and issubclass(on_error, Exception):
        raise on_error(error_msg)
    return cast(TDefault, on_error)
