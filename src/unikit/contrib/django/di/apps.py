#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from unikit.contrib.django.di._injection import _DjangoInjectionApp


class DjangoDiAppConfig(_DjangoInjectionApp):
    """Django DI app enables DI django lifecycle (views, template processors, etc)."""

    name = "unikit.contrib.django.di"
    label = "django_di"
    default = True
