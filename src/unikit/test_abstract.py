#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from inspect import isabstract
import unittest

from unikit.abstract import Abstract, AbstractMeta


class AbstractModuleTestCase(unittest.TestCase):
    def test_inheritance(self) -> None:
        class MyAbstractClass(Abstract, metaclass=AbstractMeta):
            pass

        class AnotherAbstractClass(MyAbstractClass, Abstract):
            pass

        class A(MyAbstractClass):
            pass

        class B(AnotherAbstractClass):
            pass

        self.assertTrue(isabstract(MyAbstractClass))
        self.assertTrue(isabstract(AnotherAbstractClass))
        self.assertFalse(isabstract(A))
        self.assertFalse(isabstract(B))
