"""Shared request counter for a multi-threaded web server."""
import threading
import time


class RequestCounter:
    def __init__(self):
        self.count = 0
        self.error_count = 0
        self._history = []

    def increment(self):
        self.count += 1                       # read-modify-write, not atomic

    def increment_error(self):
        self.error_count += 1                 # same race

    def record(self, path: str, status: int, duration_ms: float):
        self._history.append({               # list.append is GIL-safe in CPython,
            "path": path,                    # but the read below is not
            "status": status,
            "duration_ms": duration_ms,
            "total_at_time": self.count,     # stale read — count may have changed
        })

    def error_rate(self) -> float:
        return self.error_count / self.count  # ZeroDivisionError if count == 0

    def recent(self, n: int = 10) -> list:
        return self._history[-n:]             # slice while another thread appends


def simulate(n_threads: int = 20):
    counter = RequestCounter()

    def worker():
        for _ in range(100):
            counter.increment()
            time.sleep(0)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter.count
