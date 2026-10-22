"""Per-run event listeners, so the UI sees each event the moment a node emits it (not when the node ends)."""

import threading
from typing import Callable, Dict

_listeners: Dict[str, Callable[[dict], None]] = {}
_lock = threading.Lock()


def subscribe(run_id: str, fn: Callable[[dict], None]) -> None:
    with _lock:
        _listeners[run_id] = fn


def unsubscribe(run_id: str) -> None:
    with _lock:
        _listeners.pop(run_id, None)


def publish(run_id: str, event: dict) -> None:
    with _lock:
        fn = _listeners.get(run_id)
    if fn:
        fn(event)
