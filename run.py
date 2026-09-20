#!/usr/bin/env python3
"""
OpenDSZ Entry Point
Run this script to launch OpenDSZ on Windows, macOS, or Linux.
"""

import sys
import tkinter as tk

# On Windows, set explicit AppUserModelID before initializing GUI elements so Windows taskbar
# groups OpenDSZ under its own identity and renders the custom application icon.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("opendsz.dualsense.manager.1.0")
    except Exception:
        pass

from opendsz.ui import OpenDSZApp

def main():
    try:
        root = tk.Tk()
        app = OpenDSZApp(root)
        root.mainloop()
    except Exception:
        import traceback
        import os
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
        with open(log_path, "w") as f:
            traceback.print_exc(file=f)

if __name__ == "__main__":
    main()

