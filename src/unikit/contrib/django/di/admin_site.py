#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
from collections.abc import Iterable
from typing import Any

from django.contrib.admin import AdminSite, ModelAdmin
from django.contrib.admin.exceptions import AlreadyRegistered
from django.core.exceptions import ImproperlyConfigured
from django.db.models.base import ModelBase

from unikit.di import root_container


class DiSupportedAdminSite(AdminSite):  # type: ignore[misc]
    """Custom Django admin site that supports dependency injection."""

    def __init__(self, name: str = "admin") -> None:
        super().__init__(name)
        self._di_container = root_container

    def register(self, model_or_iterable: ModelBase | Iterable, admin_class: ModelAdmin = None, **options: Any) -> None:
        """Register a model with the given admin class."""
        # The reason for this override is to instantiate model admin with call with injection
        admin_class = admin_class or ModelAdmin
        if isinstance(model_or_iterable, ModelBase):
            model_or_iterable = [model_or_iterable]
        for model in model_or_iterable:
            if model._meta.abstract:
                raise ImproperlyConfigured(
                    f"The model {model.__name__} is abstract, so it cannot be registered with admin."
                )

            if self.is_registered(model):
                registered_admin = str(self.get_model_admin(model))
                msg = f"The model {model.__name__} is already registered "
                if registered_admin.endswith(".ModelAdmin"):
                    # Most likely registered without a ModelAdmin subclass.
                    msg += "in app {!r}.".format(registered_admin.removesuffix(".ModelAdmin"))
                else:
                    msg += f"with {registered_admin!r}."
                raise AlreadyRegistered(msg)

            if not model._meta.swapped:
                if options:
                    options["__module__"] = __name__
                    admin_class = type(f"{model.__name__}Admin", (admin_class,), options)

                # Instantiate the admin class to save in the registry
                self._registry[model] = self._di_container.create_object(
                    admin_class, additional_kwargs=dict(model=model, admin_site=self)
                )
