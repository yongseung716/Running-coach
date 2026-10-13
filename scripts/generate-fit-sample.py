"""Create a deterministic synthetic FIT fixture with explicit running dynamics."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'apps/api/tests'))
from fit_fixture import make_fit

target = root / 'samples/running-dynamics.fit'
target.write_bytes(make_fit())
print(f'Created synthetic fixture: {target}')
