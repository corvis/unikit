#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
import argparse
import dataclasses
from typing import Any

from taskiq.acks import AcknowledgeType
from taskiq.cli.worker.args import WorkerArgs
from taskiq.cli.worker.run import start_listen

from unikit.contrib.django.taskiq.management.base import BaseTaskiqCommand


class Command(BaseTaskiqCommand):
    """Start Taskiq worker process."""

    help = "Starts Taskiq worker process"

    def create_parser(self, prog_name: str, subcommand: str, **kwargs: Any) -> argparse.ArgumentParser:
        """Create argument parser for the command."""
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.add_argument(
            "broker",
            help=(
                "Where to search for broker or broker factory function. "
                "This string must be specified in "
                "'module.module:variable' format."
            ),
        )
        parser.add_argument(
            "--tasks-pattern",
            "-tp",
            default=["**/tasks.py"],
            action="append",
            help="Glob patterns of files in which taskiq will try to find the tasks.",
        )
        parser.add_argument(
            "modules",
            help="List of modules where to look for tasks.",
            nargs="*",
        )
        parser.add_argument(
            "--fs-discover",
            "-fsd",
            action="store_true",
            help=(
                "If this option is on, "
                "taskiq will try to find tasks modules "
                "in current directory recursively. Name of file to search for "
                "can be configured using `--tasks-pattern` option."
            ),
        )
        parser.add_argument(
            "--workers",
            "-w",
            type=int,
            default=2,
            help="Number of worker child processes",
        )
        parser.add_argument(
            "--no-parse",
            action="store_true",
            help=("If this parameter is on, taskiq doesn't parse incoming parameters  with pydantic."),
        )
        parser.add_argument(
            "--no-propagate-errors",
            action="store_true",
            dest="no_propagate_errors",
            help=(
                "If this parameter is on,"
                " all errors that happen in tasks "
                " won't be propagated to generator dependencies."
            ),
        )
        parser.add_argument(
            "--max-threadpool-threads",
            type=int,
            default=None,
            help="Maximum number of threads for executing sync functions.",
        )
        parser.add_argument(
            "--shutdown-timeout",
            type=float,
            default=5,
            help="Maximum amount of time for graceful broker's shutdown is seconds.",
        )
        parser.add_argument(
            "--reload",
            "-r",
            action="store_true",
            help="Reload workers if file is changed. `reload` extra is required for this option.",
        )
        parser.add_argument(
            "--do-not-use-gitignore",
            action="store_true",
            dest="no_gitignore",
            help="Do not use gitignore to check for updated files.",
        )
        parser.add_argument(
            "--max-async-tasks",
            type=int,
            dest="max_async_tasks",
            default=100,
            help="Maximum simultaneous async tasks per worker process. ",
        )
        parser.add_argument(
            "--max-prefetch",
            type=int,
            dest="max_prefetch",
            default=0,
            help="Maximum prefetched tasks per worker process. ",
        )
        parser.add_argument(
            "--no-configure-logging",
            action="store_false",
            dest="configure_logging",
            default=True,
            help="Use this parameter if your application configures custom logging.",
        )
        parser.add_argument(
            "--max-fails",
            type=int,
            dest="max_fails",
            default=-1,
            help="Maximum number of child process exits.",
        )
        parser.add_argument(
            "--ack-type",
            type=lambda value: AcknowledgeType(value.lower()),
            default=AcknowledgeType.WHEN_SAVED,
            choices=list(AcknowledgeType),
            help="When to acknowledge message.",
        )
        parser.add_argument(
            "--max-tasks-per-child",
            type=int,
            default=None,
            help="Maximum number of tasks to execute per child process.",
        )
        parser.add_argument(
            "--wait-tasks-timeout",
            type=float,
            default=None,
            help="Maximum time to wait for all current tasks to finish before exiting.",
        )
        parser.add_argument(
            "--hardkill-count",
            type=int,
            default=3,
            help="Number of termination signals to the main process before performing a hardkill.",
        )
        parser.add_argument(
            "--use-process-pool",
            action="store_true",
            dest="use_process_pool",
            help="Use process pool instead of thread pool for sync tasks.",
        )
        parser.add_argument(
            "--max-process-pool-processes",
            type=int,
            dest="max_process_pool_processes",
            default=None,
            help="Maximum number of processes in process pool.",
        )
        return parser

    def handle(self, *args: Any, **options: Any) -> None:
        """Start Taskiq worker process."""
        taskiq_app = self.taskiq_app
        taskiq_app.init_brokers_on_ready = False
        broker_name = options.get("broker", taskiq_app.default_broker_name)

        broker_path_for_taskiq = self._to_taskiq_class_path(taskiq_app.broker_paths[broker_name])
        worker_args_dict: dict[str, Any] = {
            param.name: options.get(param.name) for param in dataclasses.fields(WorkerArgs) if param.name in options
        }
        worker_args_dict["broker"] = broker_path_for_taskiq
        worker_args = WorkerArgs(**worker_args_dict)
        worker_args.tasks_pattern = taskiq_app.task_discovery_pattern

        if not worker_args.modules:
            worker_args.fs_discover = True

        start_listen(worker_args)
