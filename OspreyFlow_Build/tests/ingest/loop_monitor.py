"""A loop monitor: what the keep-alive tests never had (ADR-127 Amendment 29).

The keep-alive of an open graph transaction is an asyncio task, so it runs only when the event loop
gets a turn. A test that idles with real sleeps always gives it one, and so proved nothing about a
run that holds the loop in a long synchronous stretch. `LoopMonitor` is a task that asks the loop
for a turn every `interval` seconds and records how late each came: the longest of those is the
longest the loop was held, which is the longest the keep-alive could have been kept from running.

So that a failure says where, not only for how long, a watchdog thread looks at the loop's thread
every half second, and while the loop is more than a second overdue it counts the innermost frames
it finds (`where`); the garbage collector's own pauses are timed too (`gc_longest`), since a
collection over a heap of millions of objects stops the loop wherever it happens to fall.
Not a test module.
"""

from __future__ import annotations

import asyncio
import gc
import sys
import threading
import time
import traceback
from collections import Counter
from types import TracebackType
from typing import Any


class LoopMonitor:
    def __init__(self, interval: float = 0.1) -> None:
        self.interval = interval
        self.longest = 0.0
        self.gc_longest = 0.0
        self.where: Counter[str] = Counter()
        self._last = 0.0
        self._gc_started = 0.0
        self._task: asyncio.Task[None] | None = None
        self._stop = threading.Event()
        self._loop_thread = threading.get_ident()

    def report(self) -> str:
        """The longest stall, the longest garbage collection, and where the loop was found while
        it was overdue (each innermost-frames signature with how many looks found it there)."""
        lines = [
            f"longest stall {self.longest:.2f} s, "
            f"longest garbage collection {self.gc_longest:.2f} s"
        ]
        lines += [f"{count:4d} looks at: {where}" for where, count in self.where.most_common(8)]
        return "\n".join(lines)

    def _watch(self) -> None:
        while not self._stop.wait(0.5):
            if time.monotonic() - self._last - self.interval <= 1.0:
                continue
            frame = sys._current_frames().get(self._loop_thread)
            if frame is not None:
                tail = traceback.extract_stack(frame)[-3:]
                self.where[" < ".join(f"{f.name}:{f.lineno}" for f in reversed(tail))] += 1

    def _gc(self, phase: str, info: dict[str, Any]) -> None:
        if phase == "start":
            self._gc_started = time.monotonic()
        else:
            self.gc_longest = max(self.gc_longest, time.monotonic() - self._gc_started)

    async def _sample(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            now = time.monotonic()
            self.longest = max(self.longest, now - self._last - self.interval)
            self._last = now

    async def __aenter__(self) -> LoopMonitor:
        self._last = time.monotonic()
        gc.callbacks.append(self._gc)
        self._task = asyncio.create_task(self._sample())
        threading.Thread(target=self._watch, daemon=True).start()
        await asyncio.sleep(0)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # A stall that ran to the very end of the block is one the sampler has not yet seen.
        self.longest = max(self.longest, time.monotonic() - self._last - self.interval)
        self._stop.set()
        gc.callbacks.remove(self._gc)
        assert self._task is not None
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
