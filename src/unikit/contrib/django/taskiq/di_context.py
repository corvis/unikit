#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import injector

from unikit.di import DiModule
from unikit.worker import WorkerServiceRegistry


class _TaskiqModule(DiModule):

    def configure(self, binder: injector.Binder) -> None:
        super().configure(binder)

        self.register_singleton(WorkerServiceRegistry)
