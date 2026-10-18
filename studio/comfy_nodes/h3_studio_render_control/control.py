"""Cooperative sampling gate. No tensor mutation, interruption or process suspension."""
import threading
import time


class SamplingGate:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.condition = threading.Condition()
        self.requested = False
        self.waiting = False
        self.expires = 0.0

    def _expire(self):
        if self.requested and self.clock() >= self.expires:
            self.requested = False
            self.condition.notify_all()

    def request(self, paused, lease=30.0):
        with self.condition:
            self.requested = bool(paused)
            self.expires = self.clock() + lease if paused else 0.0
            self.condition.notify_all()
            return self._state()

    def _state(self):
        self._expire()
        return {'requested': self.requested, 'paused': self.waiting and self.requested}

    def state(self):
        with self.condition:
            return self._state()

    def checkpoint(self, interrupt, synchronize=lambda: None):
        with self.condition:
            self._expire()
            requested = self.requested
        if not requested:
            return
        # Flush already submitted device work before acknowledging the pause.
        synchronize()
        try:
            while True:
                interrupt()  # Stop remains effective while paused.
                with self.condition:
                    self._expire()
                    if not self.requested:
                        return
                    self.waiting = True
                    self.condition.wait(timeout=0.2)
        finally:
            with self.condition:
                self.waiting = False


GATES = {}
REGISTRY_LOCK = threading.Lock()


def gate_for(token):
    with REGISTRY_LOCK:
        return GATES.setdefault(token, SamplingGate())
