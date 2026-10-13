"""Repository entry point for the same API/worker supervisor used in beta."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ['PYTHONPATH'] = str(root / 'apps/api')
sys.path.insert(0, str(root / 'apps/api'))
os.chdir(root / 'apps/api')

from coach.serve import main

if __name__ == '__main__':
    main()
