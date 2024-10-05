#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
import datetime
import time


class ExecutionTimer(metaclass=abc.ABCMeta):
    """
    Class for measuring execution time of a block of code.

    Example:
        timer = ExecutionTimer()
        try:
            for x in range(5):
                sleep(random())
        finally:
            timer.stop()
        print("Execution finished in " + timer.format_elapsed())
    """

    def __init__(self, start: bool = True) -> None:
        if start:
            self.start()

    @abc.abstractmethod
    def start(self) -> None:
        """Start the timer."""
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop the timer."""
        pass

    @abc.abstractmethod
    def format_elapsed(self) -> str:
        """Format elapsed time as a string."""
        pass

    @abc.abstractmethod
    def format_elapsed_sec(self) -> str:
        """Format elapsed time in fractional seconds as a string."""
        pass

    @abc.abstractmethod
    def get_eta(self, processed: int, total: int) -> datetime.timedelta | None:
        """Return estimated time of arrival (ETA) for a given number of processed items and total number of items."""
        pass

    @property
    @abc.abstractmethod
    def elapsed(self) -> datetime.timedelta | None:
        """
        Return elapsed time as a timedelta object.

        If timer has not been started returns None.
        :return: timedelta or none
        """
        pass

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """Return True if timer is running, False otherwise."""
        pass

    @property
    @abc.abstractmethod
    def elapsed_sec(self) -> float | None:
        """
        Return elapsed time in fractional seconds.

        If timer has not been started returns None.
        :return: timedelta or none
        """
        pass

    @property
    @abc.abstractmethod
    def is_finished(self) -> bool:
        """Return True if timer has been stopped, False otherwise."""
        pass


class PerfExecutionTimer(ExecutionTimer):
    """
    Implementation of the ExecutionTimer which relies on `time.perf_timer`.

    This method provides accurate and _monotonic_ clock so could be used for very precise short-time measurements.
    """

    def __init__(self, start: bool = True) -> None:
        self.__start_time: float | None = None
        self.__end_time: float | None = None
        super().__init__(start)

    def start(self) -> None:
        """Start the timer."""
        self.__start_time = time.perf_counter()
        self.__end_time = None

    def stop(self) -> None:
        """Stop the timer."""
        self.__end_time = time.perf_counter()

    @property
    def elapsed(self) -> datetime.timedelta | None:
        """
        Return elapsed time as a timedelta object.

        If timer has not been started returns None.
        :return: timedelta or none
        """
        secs = self.elapsed_sec
        if secs is None:
            return None
        return datetime.timedelta(seconds=secs)

    @property
    def is_running(self) -> bool:
        """Return True if timer is running, False otherwise."""
        return self.__start_time is not None and self.__end_time is None

    @property
    def elapsed_sec(self) -> float | None:
        """
        Return elapsed time in fractional seconds.

        If timer has not been started returns None.
        :return: timedelta or none
        """
        if self.is_finished:
            return self.__end_time - self.__start_time  # type: ignore
        if self.is_running:
            return time.perf_counter() - self.__start_time  # type: ignore
        else:
            return None

    @property
    def is_finished(self) -> bool:
        """Return True if timer has been stopped, False otherwise."""
        return self.__start_time is not None and self.__end_time is not None

    def format_elapsed(self) -> str:
        """Format elapsed time as a string."""
        val = self.elapsed
        return str(val) if val is not None else "n/a"

    def format_elapsed_sec(self) -> str:
        """Format elapsed time in fractional seconds as a string."""
        val = self.elapsed_sec
        if val is None:
            return "n/a"
        else:
            return f"{round(val, 2)}s"

    def get_eta(self, processed: int, total: int) -> datetime.timedelta | None:
        """Return estimated time of arrival (ETA) for a given number of processed items and total number of items."""
        assert processed > 0, "Could be used only after some progress is done"
        if self.elapsed_sec is None:
            return None
        return datetime.timedelta(seconds=(total - processed) * self.elapsed_sec / processed)
