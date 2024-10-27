#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import asyncio
from typing import Any

from taskiq import TaskiqScheduler
from taskiq.cli.scheduler.args import SchedulerArgs
from taskiq.cli.scheduler.run import run_scheduler

from unikit.contrib.django.taskiq.management.base import BaseTaskiqCommand


class Command(BaseTaskiqCommand):
    """Start Taskiq worker process."""

    help = "Starts Taskiq scheduler process"

    def handle(self, *args: Any, **options: Any) -> None:
        """Start Taskiq worker process."""
        broker_name = self._get_broker_name(args)
        args = tuple(["<PLACEHOLDER>"] + list(args))

        scheduler_args = SchedulerArgs.from_cli(args)
        scheduler_args.tasks_pattern = self.taskiq_app.task_discovery_pattern

        from taskiq.schedule_sources import LabelScheduleSource

        broker = self.taskiq_app.brokers.get(broker_name)
        if broker is None:
            raise ValueError(f"Broker {broker_name} is not found.")

        scheduler = TaskiqScheduler(
            broker=broker,
            sources=[LabelScheduleSource(broker)],
        )
        scheduler_args.scheduler = scheduler

        if not scheduler_args.modules:
            scheduler_args.fs_discover = True

        asyncio.run(run_scheduler(scheduler_args))
