"""Reup Voice Studio: an independent, local-first VieNeu application."""

import os
from pathlib import Path

VERSION = "0.5.1"

# Let pydub discover the bundled tools before its first import, without changing MPT.
_root = Path(__file__).resolve().parents[1]
for _folder in (_root / "tools", _root.parent / "release" / "MPT" / "tools"):
    if (_folder / "ffmpeg.exe").is_file():
        os.environ["PATH"] = str(_folder) + os.pathsep + os.environ.get("PATH", "")
        break
