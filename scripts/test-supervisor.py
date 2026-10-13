"""Linux process smoke test: host PORT, graceful stop and worker failure."""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def children_of(parent):
    children = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / 'status').read_text()
            if f'PPid:\t{parent}\n' in status:
                children[int(entry.name)] = (entry / 'cmdline').read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            pass
    return children


def wait_for(check, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.1)
    raise AssertionError('Timed out waiting for supervisor smoke test')


def run_case(worker_failure):
    with tempfile.TemporaryDirectory(prefix='coach-supervisor-') as directory:
        # Give the host a port other than the local development default.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update(MODE='test', PORT=str(port), PYTHONPATH=str(root / 'apps/api'),
                   DATA_DIR=directory, DATABASE_URL=f'sqlite:///{directory}/coach.db')
        log = Path(directory) / 'process.log'
        with log.open('w+') as output:
            process = subprocess.Popen([sys.executable, '-m', 'coach.serve'],
                                       cwd=directory, env=env, stdout=output, stderr=output)
            child_pids = []
            try:
                def ready():
                    if process.poll() is not None:
                        raise AssertionError('Supervisor exited before startup')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                            return response.status == 200
                    except OSError:
                        return False
                wait_for(ready)
                wait_for(lambda: len(children_of(process.pid)) == 2)
                children = children_of(process.pid)
                child_pids = list(children)
                assert len(children) == 2, 'Expected independent API and worker processes'
                worker = next(pid for pid, command in children.items() if b'coach.worker' in command)
                if worker_failure:
                    os.kill(worker, signal.SIGKILL)
                else:
                    process.terminate()
                code = process.wait(timeout=15)
                assert (code != 0) if worker_failure else (code == 0), f'Unexpected exit code: {code}'
                assert all(not Path(f'/proc/{pid}').exists() for pid in child_pids), 'Child process leaked'
            except Exception:
                output.flush()
                print(log.read_text(), file=sys.stderr)
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                for pid in child_pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == '__main__':
    if not Path('/proc/self/status').exists():
        raise SystemExit('This process smoke test requires Linux /proc')
    run_case(worker_failure=False)
    run_case(worker_failure=True)
    print(json.dumps({'host_port': 'passed', 'api_and_worker': 'passed',
                      'sigterm_cleanup': 'passed', 'worker_failure_cleanup': 'passed'}))
