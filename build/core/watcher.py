"""Watches context/ for changes and rescans the file registry after a short
debounce window, so a file mid-write doesn't get read half-finished."""

import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import config
from build.core import file_registry

_observer: Observer | None = None
_debounce_timer: threading.Timer | None = None
_debounce_lock = threading.Lock()


def _debounced_rescan():
    global _debounce_timer
    with _debounce_lock:
        if _debounce_timer is not None:
            _debounce_timer.cancel()
        _debounce_timer = threading.Timer(config.WATCH_DEBOUNCE_SECONDS, _safe_scan)
        _debounce_timer.daemon = True
        _debounce_timer.start()


def _safe_scan():
    try:
        file_registry.scan()
    except OSError:
        # A file may still be mid-write; keep the last-known-good registry
        # and pick it up on the next event.
        pass


class _ContextChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory:
            return
        _debounced_rescan()


def start():
    global _observer
    if _observer is not None:
        return
    config.CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    _observer = Observer()
    _observer.schedule(_ContextChangeHandler(), str(config.CONTEXT_DIR), recursive=False)
    _observer.daemon = True
    _observer.start()


def stop():
    global _observer
    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=2)
        _observer = None
