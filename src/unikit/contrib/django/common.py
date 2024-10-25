#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc

from django.db import models


class AbstractModelMeta(abc.ABCMeta, type(models.Model)):  # type: ignore[misc]
    """
    Metaclass for abstract models that allows to inherit from both abstract models and models.Model.

    Usage:

    class MyAbstractModel(SomeOtherModel, models.Model, metaclass=AbstractModelMeta):
        ...

        @abc.abstractmethod
        def do_something(self):
            pass
    """

    pass
