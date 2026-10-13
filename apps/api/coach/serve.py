"""Run API and durable worker together for a single-service beta deployment."""
import os
import signal
import subprocess
import sys
import time


def main():
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")

    # Validate production configuration; only development/test creates tables.
    # Initialize before children to avoid racing local SQLite schema creation.
    from .db import initialize
    initialize()

    children = []

    def stop(*_):
        raise SystemExit(0)

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        children.append(subprocess.Popen([
            sys.executable, "-m", "uvicorn", "coach.main:app",
            "--host", "0.0.0.0", "--port", str(port),
        ]))
        children.append(subprocess.Popen([sys.executable, "-m", "coach.worker"]))
        while all(child.poll() is None for child in children):
            time.sleep(.5)
        # An API with a dead worker must not look like a healthy service.
        raise SystemExit("API or worker exited unexpectedly")
    finally:
        # Finish cleanup even if the host sends another termination signal.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        for child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + 10
        for child in children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
