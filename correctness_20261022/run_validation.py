"""Compatibility entry; all tests are maintained in root run_tests.py."""
from pathlib import Path
import subprocess, sys
if __name__ == "__main__":
    root=Path(__file__).resolve().parents[1]
    sys.exit(subprocess.call([sys.executable,"-B",str(root/"run_tests.py"),*sys.argv[1:]],cwd=root))
