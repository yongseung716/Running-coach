"""Start API + durable worker, propagate signals, fail if either child exits."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env['PYTHONPATH'] = str(root / 'apps/api')
children = []


def shutdown(*_):
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()


signal.signal(signal.SIGINT, lambda *args: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
try:
    # Initialize schema before concurrent API/worker startup in development.
    subprocess.run([sys.executable, '-c', 'from coach.db import initialize; initialize()'], cwd=root/'apps/api', env=env, check=True)
    children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'coach.main:app', '--host', '0.0.0.0', '--port', '8000'], cwd=root/'apps/api', env=env))
    children.append(subprocess.Popen([sys.executable, '-m', 'coach.worker'], cwd=root/'apps/api', env=env))
    while all(child.poll() is None for child in children):
        time.sleep(.5)
    raise SystemExit('API or worker exited unexpectedly')
finally:
    shutdown()
