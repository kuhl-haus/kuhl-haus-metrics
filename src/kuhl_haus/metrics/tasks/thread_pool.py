import sys
import traceback
from logging import Logger
from threading import BoundedSemaphore, RLock, Thread
from time import sleep
from typing import Callable, Dict, Union


class ThreadPool:
    size: int

    def __init__(self, logger: Logger, size: int = 10):
        """
        TODO: Replace a bunch of this with ThreadPoolExecutor
        https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor

        :param logger:
        :param size:
        """
        self.idle_time_out = 360
        self.clean_up_sleep = 0.250
        self.size = size
        self.__logger = logger
        self.__mutex = RLock()
        self.__thread_pool = BoundedSemaphore(value=size)
        self.__threads: Dict[str, Thread] = {}
        self.__cleanup_thread = Thread(
            target=self.__cleanup_threads,
            kwargs={
                "idle_time_out": self.idle_time_out,
                "clean_up_sleep": self.clean_up_sleep,
                "threads": self.__threads,
                "thread_pool": self.__thread_pool,
                "mutex": self.__mutex,
            },
            daemon=True,
        )
        self.__cleanup_thread.start()

    @property
    def thread_count(self):
        with self.__mutex:
            return len(self.__threads)

    def start_task(
        self,
        task_name: str,
        target: Union[Callable[..., object], None],
        kwargs: dict,
        blocking: bool = False,
    ):
        with self.__mutex:
            if task_name in self.__threads:
                if self.__threads[task_name].is_alive():
                    return
                else:
                    del self.__threads[task_name]
        if self.__thread_pool.acquire(blocking=blocking):
            try:
                with self.__mutex:
                    self.__threads[task_name] = Thread(target=target, kwargs=kwargs, daemon=True)
                    self.__threads[task_name].start()
            except Exception as e:
                print(f"Unhandled exception raised:{repr(e)}")
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_exception(
                    exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout
                )
                self.__logger.error(
                    "Unhandled exception raised:%s", repr(e), exc_info=e, stack_info=True
                )
            finally:
                self.__notify_cleanup()

    def __notify_cleanup(self):
        if self.__cleanup_thread.is_alive():
            self.__logger.debug("Cleanup thread is alive... not starting a new thread.")
            return
        self.__logger.debug("Cleanup thread is not alive... starting a new thread.")
        self.__cleanup_thread = Thread(
            target=self.__cleanup_threads,
            kwargs={
                "idle_time_out": self.idle_time_out,
                "clean_up_sleep": self.clean_up_sleep,
                "threads": self.__threads,
                "thread_pool": self.__thread_pool,
                "mutex": self.__mutex,
            },
            daemon=True,
        )
        self.__cleanup_thread.start()

    @staticmethod
    def __cleanup_threads(idle_time_out, clean_up_sleep, threads, thread_pool, mutex):
        idle_timer = idle_time_out
        while idle_timer > 0:
            deleted_threads = []
            with mutex:
                thread_count = len(threads)
                for task_name, thread in threads.items():
                    if not thread.is_alive():
                        deleted_threads.append(task_name)
                        thread_pool.release()
                for task_name in deleted_threads:
                    del threads[task_name]
                    thread_count -= 1
                    idle_timer = idle_time_out
            if thread_count <= 0 and not deleted_threads:
                idle_timer -= 1
            else:
                sleep(clean_up_sleep)
