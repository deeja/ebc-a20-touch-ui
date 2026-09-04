#!/usr/bin/env python3
import os
import sys

from ui.app import App

if __name__ == "__main__":
    # --kiosk is a convenience for a double-clicked packaged build (Windows
    # .exe / macOS .app) where setting an env var first isn't practical -
    # equivalent to running with EBC_KIOSK=1 set already.
    if "--kiosk" in sys.argv:
        os.environ.setdefault("EBC_KIOSK", "1")
    app = App()
    app.mainloop()
