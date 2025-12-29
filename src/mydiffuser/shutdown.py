"""Shared shutdown coordination for generators and servers.

This module provides shutdown signaling without depending on server or worker modules,
avoiding circular imports.
"""

import threading

# Shutdown flag - checked during long operations
_shutdown_event = threading.Event()


def request_shutdown() -> None:
    """Signal that shutdown has been requested."""
    _shutdown_event.set()


def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested."""
    return _shutdown_event.is_set()


def check_shutdown() -> None:
    """Raise an exception if shutdown was requested.

    Call this at safe points during long operations to allow
    graceful interruption.
    """
    if _shutdown_event.is_set():
        raise ShutdownRequested("Shutdown requested")


def reset_shutdown() -> None:
    """Reset the shutdown flag (for testing)."""
    _shutdown_event.clear()


class ShutdownRequested(Exception):
    """Raised when a shutdown is requested during a long operation."""

    pass
