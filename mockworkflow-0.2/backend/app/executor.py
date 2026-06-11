"""Task executor with concurrency back-pressure and cancellation tokens.

Replaces the raw ``BackgroundTasks`` usage so that mass uploads do not
instantly spawn unlimited concurrent generators / LLM calls.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any, Callable


class TaskExecutor:
    """Bounded async executor with queueing and per-task cancellation."""

    def __init__(self, max_concurrent: int = 4):
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._active: dict[str, asyncio.Task] = {}
        self._cancel_tokens: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    # -- public API --

    def get_cancel_token(self, task_id: str) -> asyncio.Event:
        """Return (or create) the cancellation Event for a task_id."""
        token = self._cancel_tokens.get(task_id)
        if token is None:
            token = asyncio.Event()
            self._cancel_tokens[task_id] = token
        return token

    def is_cancelled(self, task_id: str) -> bool:
        token = self._cancel_tokens.get(task_id)
        return token is not None and token.is_set()

    async def submit(
        self,
        task_id: str,
        coro: Coroutine[Any, Any, Any],
    ) -> None:
        """Queue a coroutine for execution under the semaphore."""
        async with self._lock:
            if task_id in self._active:
                return  # already running or queued

        # Pre-register cancel token so callers can cancel before it starts
        self.get_cancel_token(task_id)
        await self._queue.put(task_id)

        # Spawn a wrapper that acquires the semaphore then runs the coro
        wrapper = asyncio.create_task(self._run_wrapper(task_id, coro))
        async with self._lock:
            self._active[task_id] = wrapper

    async def cancel(self, task_id: str) -> bool:
        """Signal cancellation and cancel the running asyncio.Task if present."""
        token = self._cancel_tokens.get(task_id)
        if token:
            token.set()

        async with self._lock:
            running = self._active.get(task_id)

        if running and not running.done():
            running.cancel()
            try:
                await running
            except asyncio.CancelledError:
                pass
            finally:
                async with self._lock:
                    self._active.pop(task_id, None)
                    self._cancel_tokens.pop(task_id, None)
            return True

        # Already done or never started – clean up bookkeeping
        async with self._lock:
            self._active.pop(task_id, None)
            self._cancel_tokens.pop(task_id, None)
        return token is not None

    def stats(self) -> dict[str, int]:
        """Return queue size and active task count."""
        return {
            "queue_size": self._queue.qsize(),
            "active": len(self._active),
            "max_concurrent": self._max_concurrent,
        }

    # -- internals --

    async def _run_wrapper(
        self,
        task_id: str,
        coro: Coroutine[Any, Any, Any],
    ) -> None:
        try:
            async with self._semaphore:
                if self.is_cancelled(task_id):
                    return
                await coro
        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                self._active.pop(task_id, None)
                self._cancel_tokens.pop(task_id, None)
