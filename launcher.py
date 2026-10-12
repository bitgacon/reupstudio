"""Windowed entry point: keep startup failures visible without a console."""
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# pythonw has no console streams. Uvicorn's formatter needs isatty(), and
# startup diagnostics must survive even before Qt creates a window.
from reup.storage import DATA
DATA.mkdir(parents=True, exist_ok=True)
for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, (DATA / "desktop.log").open("a", encoding="utf-8", buffering=1))

if __name__ == "__main__":
    try:
        from run import main
        result = main()
        if result:
            raise RuntimeError("Ứng dụng không hoàn tất khởi động; xem desktop.log.")
    except (Exception, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code in (None, 0):
            raise
        from reup.storage import DATA
        DATA.mkdir(parents=True, exist_ok=True)
        path = DATA / "startup-error.log"
        path.write_text(traceback.format_exc(), encoding="utf-8")
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, "Không mở được Reup Voice Studio.\n" + str(exc) + "\nChi tiết:\n" + str(path), "Reup Voice Studio", 0x10)
        raise SystemExit(1)
