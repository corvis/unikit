#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import injector

from unikit.contrib.taskiq.di import BaseTaskiqDiModule
from unikit.worker import WorkerServiceRegistry


class _TaskiqModule(BaseTaskiqDiModule):

    def configure(self, binder: injector.Binder) -> None:
        super().configure(binder)

        self.register_singleton(WorkerServiceRegistry)
