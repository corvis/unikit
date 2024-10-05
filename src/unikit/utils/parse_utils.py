#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
__all__ = (
    "parse_bool",
    "parse_int",
    "parse_float",
    "parse_path",
    "no_trailing_slash",
    "parse_list_of_strings",
)

from pathlib import Path
from typing import overload

from .default import OnErrorDef, raise_or_default


def parse_bool(val: str | bool | int, on_error: OnErrorDef[bool] = False) -> bool:
    """
    Convert input value to the boolean if possible.

    Supported input types are `str`, `int`, `bool`.
    Non-supported input type is considered as error.
    """
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("y", "yes", "true", "1")
    if isinstance(val, int):
        return val != 0
    return raise_or_default(on_error, f"Unable to parse value `{val}`")


@overload
def parse_int(val: str | int | None, on_error: type[Exception]) -> int: ...


@overload
def parse_int(val: str | int | None, on_error: int | None = None) -> int | None: ...


def parse_int(val: str | int | None, on_error: OnErrorDef[int | None] = None) -> int | None:
    """
    Convert given input value into integer if possible. Supported inputs are: str representing integer, integer.

    Non-supported input type is considered as error.
    :param val: input value
    :param on_error: default value or exception to be raised
    :return: int value
    """
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return raise_or_default(on_error, f"Unable parse value `{val}`")


@overload
def parse_float(val: str | float | int | None, on_error: type[Exception]) -> float: ...


@overload
def parse_float(val: str | float | int | None, on_error: int | None = None) -> float | None: ...


def parse_float(val: str | float | int | None, on_error: OnErrorDef[int | None] = None) -> float | None:
    """
    Convert given input value into float if possible.

    Supported inputs are: str representing float, integer, float.
    Non-supported input type is considered as error.
    :param val: input value
    :param on_error: default value or exception to be raised
    :return: float value
    """
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return raise_or_default(on_error, f"Unable parse value `{val}`")


def parse_path(val: str | Path | None, on_error: OnErrorDef[Path | None] = None) -> Path | None:
    """
    Convert given input value into Path if possible. Supported inputs are: str representing Path, Path.

    Non-supported input type is considered as error.
    :param val: input value
    :param on_error: default value or exception to be raised
    :return: Path value
    """
    if val is not None:
        try:
            return Path(val)
        except ValueError:
            pass
    return raise_or_default(on_error, f"Unable parse path from `{val}`")


def no_trailing_slash(val: str, on_error: OnErrorDef[str] = ValueError) -> str:
    """
    Remove all trailing slashes from the given string. Might be useful to normalize URLs.

    Non-string input is considered as error.
    """
    if isinstance(val, str):
        while val.endswith("/"):
            val = val[:-1]
        return val
    return raise_or_default(on_error, f"no_trailing_slash expects string but {type(val)} given")


@overload
def parse_list_of_strings(val: None, separator: str = ...) -> None: ...


@overload
def parse_list_of_strings(val: list[str] | str, separator: str = ...) -> list[str]: ...


def parse_list_of_strings(val: list[str] | str | None, separator: str = ",") -> list[str] | None:
    """
    Split comma-separated string and return it as list of values.

    :param val: input value
    :param separator: separator
    :return: list of values
    """
    if isinstance(val, str):
        return [v.strip() for v in val.split(separator)]
    return val
