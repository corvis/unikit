#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import dataclasses
from typing import Any, Mapping, TypeVar, cast

from pydantic import BaseModel

from unikit.utils.default import OnErrorDef, raise_or_default

TDict = TypeVar("TDict", bound=Mapping)
_T = TypeVar("_T")


def deepmerge(to_dict: TDict, from_dict: TDict, merge_lists: bool = False) -> TDict:
    """
    Merge two dictionaries recursively and return created dict. Dict `from_dict` will be merged into dict `to_dict`.

    This is a PURE function (doesn't have side effects), so it will not modify the original dictionaries.
    If a key is present in both dictionaries, the value from `new` will be used.

    :param to_dict: original object which will be used as a base
    :param from_dict: new object which will be merged into original
    :param merge_lists: whether to merge lists or replace them
    """

    def merge(_old: TDict, _new: TDict) -> TDict:
        # pylint: disable=no-else-return
        if isinstance(_new, dict):
            if not isinstance(_old, dict):
                return cast(TDict, _new)
            res = _old.copy()
            for k, v in _new.items():
                res[k] = merge(_old[k], v) if k in _old else v
            return cast(TDict, res)
        elif isinstance(_new, list):
            if merge_lists:
                if not isinstance(_old, list):
                    return _new
                return _old + _new
            else:
                return _new
        return _new

    return merge(to_dict, from_dict)


def set_objects(_dict: dict, *objects: Any, key: str | None = None) -> None:
    """
    Convert all given objects to dictionaries and set them to the target dictionary.

    If key is provided - all objects will be set under this key in the target dictionary.

    :param _dict: target dictionary
    :param objects: objects to be serialized and set to the target dictionary
    :param key: optional key to set objects into
    """
    result_dict: dict[str, Any] = {}
    for obj in objects:
        if dataclasses.is_dataclass(obj):
            obj_dict = dataclasses.asdict(obj)  # type: ignore[call-overload]
        elif hasattr(obj, "to_dict"):
            obj_dict = obj.to_dict()
        elif isinstance(obj, dict):
            obj_dict = obj
        elif isinstance(obj, BaseModel):
            obj_dict = obj.model_dump(by_alias=True)
        else:
            raise ValueError("Object must be either dict, dataclass or has .to_dict() method")
        result_dict.update(obj_dict)
    if key is None:
        _dict.update(result_dict)
    else:
        _dict[key] = result_dict


def get_object(
    _dict: TDict, target_cls: type[_T], key: str | None = None, on_missing: OnErrorDef[Any] = None
) -> _T | None:
    """
    Get the object from the dictionary and convert it to the target class.

    :param _dict: target dictionary
    :param target_cls: target class
    :param key: optional key, if set the data will be extracted from this specific key, otherwise from the dict itself.
    :param on_missing: what to do if the key is missing. Could be either error or default value.
    :return: instance of target class populated from the dict
    """
    target_object = _dict.get(key) if key else _dict
    if target_object is None:
        return raise_or_default(
            on_missing, f"Key `{key}` not found in the dictionary" if key else "Dictionary is empty"
        )
    if dataclasses.is_dataclass(target_cls):
        fields = set([f.name for f in dataclasses.fields(target_cls)])
        data: dict[str, Any] = {}
        for k, v in target_object.items():
            if k in fields:
                data[k] = v
        obj = target_cls(**data)
    elif issubclass(target_cls, BaseModel):
        obj = target_cls.model_load(target_object)  # type: ignore
    elif hasattr(target_cls, "from_dict"):
        obj = target_cls.from_dict(target_object)  # type: ignore
    else:
        raise ValueError("Object must be either dict, dataclass or has .from_dict() method")
    return cast(_T, obj)
