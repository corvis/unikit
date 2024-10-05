#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from typing import Mapping, TypeVar, cast

TDict = TypeVar("TDict", bound=Mapping)


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
