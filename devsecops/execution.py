"""Per-job execution deadline propagated into outbound network operations."""
import time
from contextlib import contextmanager
from contextvars import ContextVar

_deadline = ContextVar('job_deadline', default=None)
_checkpoint = ContextVar('job_checkpoint', default=None)


@contextmanager
def execution_budget(seconds):
    token = _deadline.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


@contextmanager
def cancellation_checks(checkpoint):
    token = _checkpoint.set(checkpoint)
    try:
        yield
    finally:
        _checkpoint.reset(token)


def request_deadline(timeout):
    deadline = time.monotonic() + timeout
    outer = _deadline.get()
    return min(deadline, outer) if outer is not None else deadline


def check_execution():
    checkpoint = _checkpoint.get()
    if checkpoint:
        checkpoint()
    deadline = _deadline.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise ValueError('Analysis exceeded its overall time budget. Saved evidence is retained.')
