"""Run blocking calls (network) off the UI thread and deliver results back on it."""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_live: set["_Task"] = set()


class _Task(QObject):
    finished = Signal(object, object)  # result, error

    def __init__(self, on_done, on_error):
        super().__init__()
        self.on_done = on_done
        self.on_error = on_error
        # Connected to our own slot: the task object lives on the UI thread, so the
        # emit from the pool thread is queued and the callbacks run on the UI thread.
        self.finished.connect(self._deliver)

    @Slot(object, object)
    def _deliver(self, result, error):
        _live.discard(self)
        try:
            if error is not None:
                if self.on_error:
                    self.on_error(error)
                else:
                    traceback.print_exception(error)
            elif self.on_done:
                self.on_done(result)
        finally:
            self.deleteLater()


class _Runner(QRunnable):
    def __init__(self, task: _Task, fn, args, kwargs):
        super().__init__()
        self.task, self.fn, self.args, self.kwargs = task, fn, args, kwargs

    def run(self):
        try:
            res = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self.task.finished.emit(None, exc)
        else:
            self.task.finished.emit(res, None)


def run_async(fn: Callable[..., Any], *args,
              on_done: Callable[[Any], None] | None = None,
              on_error: Callable[[Exception], None] | None = None, **kwargs) -> None:
    task = _Task(on_done, on_error)
    _live.add(task)
    QThreadPool.globalInstance().start(_Runner(task, fn, args, kwargs))
