#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import dataclasses
import unittest

from unikit.utils import dict_utils


@dataclasses.dataclass(kw_only=True)
class MyClass:
    a: int
    b: int


class TestDictUtils(unittest.TestCase):

    def test_get_object_dataclass(self):
        given = dict(a=1, b=2, c="3", d=dict(a=10, b=11))

        result = dict_utils.get_object(given, MyClass)
        self.assertEqual(result, MyClass(a=1, b=2))
        result = dict_utils.get_object(given, MyClass, "d")
        self.assertEqual(result, MyClass(a=10, b=11))

    def test_set_objects_dataclass(self):
        my_dict = {}
        my_class = MyClass(a=1, b=2)
        dict_utils.set_objects(my_dict, my_class)
        self.assertEqual(my_dict, dict(a=1, b=2))
        my_class2 = MyClass(a=10, b=11)
        dict_utils.set_objects(my_dict, my_class2, key="d")
        self.assertEqual(my_dict, dict(a=1, b=2, d=dict(a=10, b=11)))
