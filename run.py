#!/usr/bin/env python3
"""
OpenDSZ Entry Point
Run this script to launch OpenDSZ on Windows, macOS, or Linux.
Supports GUI mode (default) and Headless Daemon mode (--daemon / --headless).
"""

import sys
import os
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="OpenDSZ - DualSense Controller Manager")
    parser.add_argument("--daemon", "--headless", action="store_true", dest="daemon",
                        help="Run OpenDSZ in headless background daemon mode with local REST API")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="API host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5305,
                        help="API port for local plugin/web integration (default: 5305)")
    return parser.parse_known_args()

def main():
    args, _ = parse_args()

    if args.daemon:
        from opendsz.daemon import OpenDSZDaemon
        daemon = OpenDSZDaemon(host=args.host, port=args.port)
        daemon.run_forever()
        return

    # On Windows, set explicit AppUserModelID before initializing GUI elements so Windows taskbar
    # groups OpenDSZ under its own identity and renders the custom application icon.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("opendsz.dualsense.manager.1.0")
        except Exception:
            pass

    import tkinter as tk
    from opendsz.ui import OpenDSZApp

    try:
        root = tk.Tk()
        app = OpenDSZApp(root)
        root.mainloop()
    except Exception:
        import traceback
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
        with open(log_path, "w") as f:
            traceback.print_exc(file=f)

if __name__ == "__main__":
    main()
