"""One monotonic deadline per tool, shared across its worker, locks and HTTP calls."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from threading import Event
import time

import anyio
from mcp.server.mcpserver.exceptions import ToolError

WORK_SECONDS = 45.0
RESPONSE_SECONDS = 50.0  # Leave 10 seconds for transport against the 60-second baseline.


class Exhausted(ToolError):
    code = "time_budget_exceeded"

    def __init__(self):
        super().__init__("本次调用已达到时间预算，已停止继续请求；可从返回的续读位置继续，凭证已保留。")


@dataclass
class _Budget:
    deadline: float
    stopped: Event = field(default_factory=Event)


_current = ContextVar("linuxdo_request_budget", default=None)


@contextmanager
def operation():
    """Nested preflight/formatting calls inherit the original deadline."""
    existing = _current.get()
    if existing is not None:
        yield existing
        return
    current = _Budget(time.monotonic() + WORK_SECONDS)
    token = _current.set(current)
    try:
        yield current
    finally:
        current.stopped.set()
        _current.reset(token)


def remaining(cap=30.0):
    current = _current.get()
    if current is None:
        return cap
    left = current.deadline - time.monotonic()
    if current.stopped.is_set() or left <= 0.01:
        raise Exhausted()
    return min(cap, left)


def sleep(seconds):
    # Do not spend the remaining budget sleeping when no request can follow it.
    if seconds >= remaining(float("inf")):
        raise Exhausted()
    time.sleep(seconds)
    remaining()


def tool(fn):
    """Start before worker-pool queuing; cancellation prevents subsequent HTTP calls."""
    @wraps(fn)
    async def bounded(*args, **kwargs):
        with operation():
            def invoke():
                remaining()
                return fn(*args, **kwargs)
            try:
                with anyio.fail_after(RESPONSE_SECONDS):
                    return await anyio.to_thread.run_sync(invoke, abandon_on_cancel=True)
            except TimeoutError:
                raise Exhausted() from None
    return bounded
