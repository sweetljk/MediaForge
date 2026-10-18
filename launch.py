"""Frozen entry point, with a readable crash log even without a console."""
import os
from pathlib import Path
import sys
import traceback

if __name__ == "__main__":
    try:
        from mediaforge.app import main
        raise SystemExit(main())
    except Exception:
        directory = Path(os.environ.get("MEDIAFORGE_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MediaForge"))
        directory.mkdir(parents=True, exist_ok=True)
        log = directory / "startup-error.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        if sys.stderr:
            traceback.print_exc()
        if os.name == "nt" and "--smoke-test" not in sys.argv and "--worker" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"MediaForge 无法启动。详细错误已保存到：\n{log}", "MediaForge", 16)
        raise SystemExit(1)
