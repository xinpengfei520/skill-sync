#!/usr/bin/env python3
"""skill-sync entry point. Adds the repo root to sys.path and runs the CLI, so
it works from a plain `git clone` without any install step."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skillsync.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
