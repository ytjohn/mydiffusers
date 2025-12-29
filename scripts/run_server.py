#!/usr/bin/env python
"""Entry point for running the mydiffuser server.

Auto-detects ROCm vs CUDA and configures appropriately.
No environment variables needed for basic operation.

Optional overrides:
  MYDIFFUSER_VIDEO=1          Enable video generation
  MYDIFFUSER_LAZY=0           Disable lazy loading (load all at startup)
  MYDIFFUSER_VIDEO_MODEL=14B  Use 14B model instead of 5B
  MYDIFFUSER_DTYPE=fp16       Use fp16 instead of bf16
  MYDIFFUSER_VAE_DEVICE=cuda  Force VAE on GPU (NVIDIA only)
  MYDIFFUSER_FLASH_SDP=1      Enable flash attention (experimental on ROCm)
"""

import atexit
import os
import socket
import sys
from pathlib import Path

# ============================================================================
# Pre-torch environment setup (must be before any torch imports)
# ============================================================================

# Silence tokenizers fork warning from huggingface
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ROCm-specific workarounds (harmless on CUDA, just ignored)
# These help with MIOpen conv3d kernel selection on AMD GPUs
os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")
os.environ.setdefault("MIOPEN_DEBUG_CONV_IMPLICIT_GEMM", "0")
os.environ.setdefault("MIOPEN_DEBUG_DISABLE_FIND_DB", "1")

# SDP backend: ROCm needs math-only by default; CUDA can use all
# Only set if not already configured and flash SDP not explicitly enabled
if os.environ.get("MYDIFFUSER_FLASH_SDP", "0") != "1":
    os.environ.setdefault("PYTORCH_SDP_BACKEND", "math")

# Add src to path for development (when not installed as package)
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# PID file location
PID_FILE = Path(__file__).parent.parent / "outputs" / "mydiffuser.pid"
PORT = 7999


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it (different user)
        return True


def is_port_in_use(port: int) -> bool:
    """Check if a port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


def check_existing_instance() -> None:
    """Check for existing server instance and abort if found."""
    # Check PID file
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if is_process_running(old_pid):
                print(f"ERROR: Server already running (PID {old_pid})")
                print(f"  Kill it with: kill {old_pid}")
                print(f"  Or force: kill -9 {old_pid}")
                print(f"  PID file: {PID_FILE}")
                sys.exit(1)
            else:
                # Stale PID file, remove it
                print(f"Removing stale PID file (old PID {old_pid} not running)")
                PID_FILE.unlink()
        except (ValueError, OSError) as e:
            print(f"Warning: Could not read PID file: {e}")
            PID_FILE.unlink(missing_ok=True)

    # Check port even if no PID file (something else might be using it)
    if is_port_in_use(PORT):
        print(f"ERROR: Port {PORT} is already in use")
        print(f"  Find what's using it: lsof -i :{PORT}")
        print(f"  Or: ss -tlnp | grep {PORT}")
        sys.exit(1)


def write_pid_file() -> None:
    """Write current PID to file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    print(f"PID file written: {PID_FILE}")


def cleanup_pid_file() -> None:
    """Remove PID file on exit."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
            print(f"PID file removed: {PID_FILE}")
    except OSError:
        pass


def main():
    # Pre-flight checks
    check_existing_instance()

    # Set up cleanup (atexit handles normal exit and exceptions)
    write_pid_file()
    atexit.register(cleanup_pid_file)

    # Now import and run (imports trigger model loading)
    import uvicorn

    from mydiffuser.server.app import create_app

    app = create_app()

    print(f"Starting server on port {PORT}...")
    print("Press Ctrl+C to stop")

    # Let uvicorn handle signals - it will propagate to our lifespan handler
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
