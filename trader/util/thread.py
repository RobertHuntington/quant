"""The `thread` module.

Primitives and infrastructure for multithreading.

"""

import datetime
import os
import time
import traceback
from enum import Enum
from queue import Queue
from threading import Condition, Lock, Thread


class BeatError(Exception):
    pass


class Beat:
    """A helper utility for running timed loops.

    Use this to schedule a function that runs once a minute, regardless of how long it takes to
    actually run the function.

    Args:
        interval (int): Milliseconds between beats.

    """

    def __init__(self, interval):
        self.__interval = interval
        self.__last_beat = None

    def loop(self):
        """Runs the timed loop and sleeps as necessary."""
        # Run sleep if a last beat time exists.
        if self.__last_beat is not None:
            delta = datetime.datetime.now() - self.__last_beat
            duration_to_sleep = (self.__interval / 1000.0) - delta.total_seconds()
            if duration_to_sleep < 0:
                raise BeatError("loop body too slow for beat interval")
            time.sleep(duration_to_sleep)
            self.__last_beat = None

        # Set a new last beat time for the next iteration.
        self.__last_beat = datetime.datetime.now()
        return True

    def clear(self):
        """Clears the last beat time for this loop."""
        self.__last_beat = None


class MVar:
    """A partial implementation of a Haskell MVar.

    Many of the usual functions (e.g. `put` or `take`) are missing, but the general concept (of a
    shared memory location for threads) is the same.

    """

    def __init__(self):
        self.__lock = Lock()
        self.__condition = Condition(lock=self.__lock)
        self.__value = None

    def swap(self, new_value):
        """Puts a new value in the `MVar` and returns the old value, if any.

        Args:
            new_value: The new value.

        Returns:
            The old value.

        """
        self.__lock.acquire()
        old_value = self.__value
        self.__value = new_value
        self.__condition.notify_all()
        self.__lock.release()
        return old_value

    def read(self):
        """Reads the current value of the `MVar`. Blocks until a value is ready.

        Returns:
            The current value.

        """
        self.__lock.acquire()
        if self.__value is None:
            self.__condition.wait()
        read_value = self.__value
        self.__lock.release()
        return read_value


class ThreadManagerError(Exception):
    pass


class ThreadManagerState(Enum):
    INITIALIZED = 1
    RUNNING = 2
    FINISHED = 3


class ThreadManager:
    """A centralized runner for our Python threads.

    Prints useful debug info on failures.

    """

    def __init__(self):
        self.__termination_queue = Queue()
        self.__finite_thread_count = 0
        self.__thread_runners = []
        self.__state = ThreadManagerState.INITIALIZED

    def __propagate_error(self, name, fn, should_terminate):
        # Used to propagate unhandled errors to the main thread.
        try:
            fn()
            if should_terminate:
                reason = None
            else:
                reason = "Expected thread to run forever.\n"
            self.__termination_queue.put((name, reason))
        except Exception:
            self.__termination_queue.put((name, traceback.format_exc()))

    def __run_daemon(self, fn):
        thread = Thread(target=fn)
        # Force-kill on KeyboardInterrupts.
        thread.daemon = True
        thread.start()

    def attach(self, name, fn, should_terminate=False):
        """Attaches a function to this thread manager as a new thread to be created.

        Args:
            name (str): A name to identify the new thread.
            fn (Function): A function to run on the new thread.
            should_terminate (bool): Whether we expect this function to terminate (or run forever).

        """
        if self.__state == ThreadManagerState.FINISHED:
            raise ThreadManagerError("ThreadManager has finished")

        if should_terminate:
            self.__finite_thread_count += 1

        def runner():
            self.__propagate_error(name, fn, should_terminate)

        if self.__state == ThreadManagerState.INITIALIZED:
            self.__thread_runners.append(runner)
        else:
            self.__run_daemon(runner)

    def run(self):
        """Cannibalizes the current thread and runs any attached functions as children threads."""
        if self.__state != ThreadManagerState.INITIALIZED:
            if self.__state == ThreadManagerState.RUNNING:
                raise ThreadManagerError("ThreadManager is currently running")
            else:
                raise ThreadManagerError("ThreadManager has finished")
        else:
            self.__state == ThreadManagerState.RUNNING
        for runner in self.__thread_runners:
            self.__run_daemon(runner)
        completed_threads = 0
        while True:
            (name, exc) = self.__termination_queue.get()
            completed_threads += 1
            if exc is None:
                print("Thread <{}> terminated.".format(name))
                if completed_threads == self.__finite_thread_count:
                    self.__state == ThreadManagerState.FINISHED
                    break
            else:
                print("Thread <{}> terminated unexpectedly!".format(name))
                if exc is not None:
                    print(exc[:-1])
                os._exit(1)
