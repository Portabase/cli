from __future__ import annotations

import socket


class PortAllocator:
    def __init__(self) -> None:
        self._given: set[int] = set()

    def free(self) -> int:
        for _ in range(50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("", 0))
                port = sock.getsockname()[1]
            if port not in self._given:
                self._given.add(port)
                return port
        raise RuntimeError("Could not allocate a free port")


class FixedPortAllocator(PortAllocator):
    def __init__(self, start: int = 40000) -> None:
        super().__init__()
        self._next = start

    def free(self) -> int:
        port = self._next
        self._next += 1
        return port
