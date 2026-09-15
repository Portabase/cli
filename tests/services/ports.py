import pytest

from services import ports
from services.ports import FixedPortAllocator, PortAllocator


def port_allocator_returns_distinct_free_ports():
    allocator = PortAllocator()
    given = [allocator.free() for _ in range(5)]
    assert len(set(given)) == 5
    assert all(1024 <= port <= 65535 for port in given)


def port_allocator_gives_up_when_the_os_repeats_a_port(monkeypatch):
    class _Socket:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def bind(self, address):
            pass

        def getsockname(self):
            return ("0.0.0.0", 45678)

    monkeypatch.setattr(ports.socket, "socket", _Socket)
    allocator = PortAllocator()
    assert allocator.free() == 45678
    with pytest.raises(RuntimeError, match="Could not allocate a free port"):
        allocator.free()


def fixed_port_allocator_counts_up():
    allocator = FixedPortAllocator()
    assert [allocator.free() for _ in range(3)] == [40000, 40001, 40002]
    assert FixedPortAllocator(start=5000).free() == 5000
