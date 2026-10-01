import asyncio
from collections.abc import Callable, Coroutine, Hashable
from typing import Any


class SingleFlight[R]:
    """Coalesces concurrent calls with the same key into one execution (in-process only).

    The first caller starts the work as a task; concurrent callers with the same key await
    that task and share its result *or* exception. The task is shielded, so a cancelled
    caller (e.g. a disconnected client) does not cancel the work for the others. Entries
    are removed as soon as the task finishes, so nothing is retained between calls.
    """

    def __init__(self) -> None:
        self._in_flight: dict[Hashable, asyncio.Task[R]] = {}

    async def run(self, key: Hashable, work: Callable[[], Coroutine[Any, Any, R]]) -> R:
        task = self._in_flight.get(key)
        if task is None or task.get_loop() is not asyncio.get_running_loop():
            task = asyncio.create_task(work())
            self._in_flight[key] = task
            task.add_done_callback(lambda done: self._finish(key, done))
        return await asyncio.shield(task)

    def __len__(self) -> int:
        return len(self._in_flight)

    def _finish(self, key: Hashable, task: asyncio.Task[R]) -> None:
        if self._in_flight.get(key) is task:
            del self._in_flight[key]
        if not task.cancelled():
            task.exception()  # mark as retrieved even if every caller was cancelled
