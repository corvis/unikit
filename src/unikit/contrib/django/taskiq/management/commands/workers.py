#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from typing import Any

from taskiq.cli.worker.args import WorkerArgs
from taskiq.cli.worker.run import start_listen

from unikit.contrib.django.taskiq.management.base import BaseTaskiqCommand


class Command(BaseTaskiqCommand):
    """Start Taskiq worker process."""

    help = "Starts Taskiq worker process"

    def handle(self, *args: Any, **options: Any) -> None:
        """Start Taskiq worker process."""
        taskiq_app = self.taskiq_app
        if len(args) > 0 and not args[0].startswith("-"):
            broker_name = args[0]
            args = args[1:]
        else:
            broker_name = taskiq_app.default_broker_name

        broker_path_for_taskiq = self.__to_taskiq_class_path(taskiq_app.broker_paths[broker_name])
        args = tuple([broker_path_for_taskiq] + list(args))
        worker_args = WorkerArgs.from_cli(args)
        worker_args.tasks_pattern = taskiq_app.task_discovery_pattern

        if not worker_args.modules:
            worker_args.fs_discover = True

        start_listen(worker_args)

    @staticmethod
    def __to_taskiq_class_path(path: str) -> str:
        return ":".join((path.rsplit(".", 1)))
