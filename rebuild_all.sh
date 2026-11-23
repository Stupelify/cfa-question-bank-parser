#!/usr/bin/env python3
"""One-command rebuild: extract → merge manual → build HTML."""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
PY = sys.executable


def run(script: str):
    print(f"\n>>> {script}")
    subprocess.run([PY, str(BASE / script)], check=True)


def main():
    run("extract_questions.py")
    manual = BASE / "manual_questions.json"
    if manual.exists():
        run("merge_manual.py")
    else:
        run("build_html.py")
    run("report_missing.py")
    print("\nDone. Open index.html in your browser.")


if __name__ == "__main__":
    main()
