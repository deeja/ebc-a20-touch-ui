#!/usr/bin/env python3
"""Writes ui/build_info.py with the given version and the current UTC
build time - called by deploy/build-package.sh and directly from CI
(.github/workflows/release.yml) before packaging each release artifact,
so the app's About dialog can show what it was actually built from.

    python3 deploy/write_build_info.py <version>
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

version = sys.argv[1] if len(sys.argv) > 1 else "dev"
build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

path = Path(__file__).resolve().parent.parent / "ui" / "build_info.py"
path.write_text(
    '"""Version/build metadata for the About dialog - overwritten by\n'
    'deploy/write_build_info.py before packaging a release; these are the\n'
    'plain source-checkout defaults."""\n'
    f"VERSION = {version!r}\n"
    f"BUILD_DATE = {build_date!r}\n"
)
print(f"Wrote {path}: VERSION={version!r} BUILD_DATE={build_date!r}")
