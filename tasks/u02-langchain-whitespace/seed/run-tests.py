from pathlib import Path
import subprocess
import sys

workspace = Path(__file__).resolve().parent
python = workspace.parent / "runtime" / "Scripts" / "python.exe"
raise SystemExit(subprocess.call(
    [str(python), "-B", "-I", "-m", "unittest", "discover", "-s", "tests", "-v"],
    cwd=workspace,
))
