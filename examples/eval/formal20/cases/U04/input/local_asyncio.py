"""Test-only asyncio loop for disk/thread work inside a no-network sandbox."""
import asyncio
import selectors
from threading import Condition


class ThreadSelector(selectors.BaseSelector):
    def __init__(self):
        self._signal = Condition()
        self._ready = False

    def register(self, fileobj, events, data=None):
        raise RuntimeError("This offline fixture does not allow network I/O")

    def unregister(self, fileobj):
        raise KeyError(fileobj)

    def get_map(self):
        return {}

    def wake(self):
        with self._signal:
            self._ready = True
            self._signal.notify()

    def select(self, timeout=None):
        with self._signal:
            self._signal.wait_for(lambda: self._ready, timeout)
            self._ready = False
        return []


class LocalEventLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        super().__init__(ThreadSelector())

    def _make_self_pipe(self):
        pass

    def _close_self_pipe(self):
        pass

    def _write_to_self(self):
        self._selector.wake()
