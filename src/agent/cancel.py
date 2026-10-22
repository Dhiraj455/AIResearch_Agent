"""Cooperative cancellation for research runs (checked between graph steps and inside parallel workers)."""

import threading

_cancelled: set[str] = set()
_lock = threading.Lock()


class RunCancelled(Exception):
    pass


def request_cancel(run_id: str) -> None:
    with _lock:
        _cancelled.add(run_id)


def is_cancelled(run_id: str) -> bool:
    with _lock:
        return run_id in _cancelled


def clear(run_id: str) -> None:
    with _lock:
        _cancelled.discard(run_id)


def raise_if_cancelled(run_id: str) -> None:
    if is_cancelled(run_id):
        raise RunCancelled(run_id)
