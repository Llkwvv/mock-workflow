"""Tests for TaskExecutor back-pressure and cancellation."""

import asyncio

import pytest

from backend.app.executor import TaskExecutor


@pytest.fixture
def executor():
    return TaskExecutor(max_concurrent=2)


@pytest.mark.asyncio
async def test_submit_and_run(executor):
    done = asyncio.Event()

    async def work():
        done.set()

    await executor.submit("t1", work())
    # Wait for the executor wrapper to pick up the task
    await asyncio.wait_for(done.wait(), timeout=2.0)
    assert done.is_set()


@pytest.mark.asyncio
async def test_concurrency_limit(executor):
    """Ensure that with max_concurrent=2, at most 2 tasks are active at once."""
    delay = 0.1
    results = []

    async def work(tag: str):
        results.append((tag, "start"))
        await asyncio.sleep(delay)
        results.append((tag, "end"))

    await executor.submit("t1", work("t1"))
    await executor.submit("t2", work("t2"))
    await executor.submit("t3", work("t3"))

    # After a short delay t1 and t2 should be inside sleep, t3 queued
    await asyncio.sleep(0.05)
    active_tags = [tag for tag, state in results if state == "start"]
    assert len(active_tags) <= 2

    # Wait for all to finish
    await asyncio.sleep(delay * 2 + 0.05)
    assert len([s for _, s in results if s == "end"]) == 3


@pytest.mark.asyncio
async def test_cancel_before_start(executor):
    async def work():
        await asyncio.sleep(10)  # long sleep so cancel hits it

    await executor.submit("t1", work())
    await asyncio.sleep(0.02)  # let wrapper enter sleep
    cancelled = await executor.cancel("t1")
    assert cancelled is True
    # After cancel returns, bookkeeping is cleaned up; just verify token existed
    assert executor.is_cancelled("t1") is False  # already cleaned


@pytest.mark.asyncio
async def test_cancel_token_is_set(executor):
    token = executor.get_cancel_token("t1")
    assert not token.is_set()
    await executor.cancel("t1")
    assert token.is_set()


@pytest.mark.asyncio
async def test_stats(executor):
    async def work():
        await asyncio.sleep(0.2)

    await executor.submit("t1", work())
    await asyncio.sleep(0.02)
    stats = executor.stats()
    assert stats["max_concurrent"] == 2
    assert stats["active"] == 1
