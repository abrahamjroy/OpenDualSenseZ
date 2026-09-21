from __future__ import annotations

import asyncio
import json
import os
import sys
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Optional

try:
    import decky
except ImportError:
    class DummyDecky:
        DECKY_HOME = "/home/deck/homebrew"
        DECKY_SETTINGS_DIR = "/home/deck/homebrew/settings"
        DECKY_LOG_DIR = "/home/deck/homebrew/logs/opendsz"
        class logger:
            @staticmethod
            def info(msg): print(f"[INFO] {msg}")
            @staticmethod
            def error(msg): print(f"[ERROR] {msg}")
            @staticmethod
            def warning(msg): print(f"[WARN] {msg}")
    decky = DummyDecky()

PLUGIN_DIR = Path(__file__).resolve().parent
OPENDSZ_API_URL = "http://127.0.0.1:5305/api"


class Plugin:
    def __init__(self):
        self._daemon_process: Optional[subprocess.Popen] = None

    def _http_get(self, endpoint: str) -> dict:
        try:
            req = urllib.request.Request(f"{OPENDSZ_API_URL}/{endpoint}", headers={"User-Agent": "OpenDSZ-Decky/1.0"})
            with urllib.request.urlopen(req, timeout=2) as res:
                return json.loads(res.read().decode())
        except Exception as e:
            return {"error": str(e), "connected": False, "status": "offline"}

    def _http_post(self, endpoint: str, payload: dict) -> dict:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{OPENDSZ_API_URL}/{endpoint}",
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": "OpenDSZ-Decky/1.0"}
            )
            with urllib.request.urlopen(req, timeout=2) as res:
                return json.loads(res.read().decode())
        except Exception as e:
            return {"error": str(e), "success": False}

    async def get_status(self) -> dict:
        return await asyncio.to_thread(self._http_get, "status")

    async def get_profiles(self) -> dict:
        return await asyncio.to_thread(self._http_get, "profiles")

    async def get_effects(self) -> dict:
        return await asyncio.to_thread(self._http_get, "effects")

    async def set_profile(self, name: str) -> dict:
        return await asyncio.to_thread(self._http_post, "profile", {"name": name})

    async def set_effect(self, effect: str) -> dict:
        return await asyncio.to_thread(self._http_post, "effects", {"effect": effect})

    async def set_telemetry(self, enabled: bool, port: int = 5300) -> dict:
        return await asyncio.to_thread(self._http_post, "telemetry", {"enabled": enabled, "port": port})

    async def reconnect(self) -> dict:
        # Reconnect by querying status / retriggering profile
        return await self.get_status()

    async def _ensure_daemon_running(self):
        status = await self.get_status()
        if status.get("status") != "online":
            decky.logger.info("OpenDSZ daemon is not running on 5305, launching background service...")
            # Look for OpenDSZ executable or run.py
            cmd = None
            candidates = [
                PLUGIN_DIR / "bin" / "OpenDSZ-Linux-x86_64",
                PLUGIN_DIR.parent / "dist" / "OpenDSZ-Linux-x86_64",
                Path("/usr/local/bin/OpenDSZ-Linux-x86_64"),
                PLUGIN_DIR.parent / "run.py",
            ]
            for c in candidates:
                if c.exists():
                    if c.suffix == ".py":
                        cmd = [sys.executable, str(c), "--daemon"]
                    else:
                        cmd = [str(c), "--daemon"]
                    break

            if cmd:
                try:
                    self._daemon_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    decky.logger.info(f"Launched daemon process: {' '.join(cmd)}")
                except Exception as ex:
                    decky.logger.error(f"Failed to launch OpenDSZ daemon: {ex}")
            else:
                decky.logger.warning("No local OpenDSZ binary found to auto-launch. Please run OpenDSZ daemon manually.")

    async def _main(self):
        decky.logger.info("OpenDSZ Decky Plugin v1.0.0 initializing")
        await self._ensure_daemon_running()

    async def _unload(self):
        decky.logger.info("OpenDSZ Decky Plugin unloading")
        if self._daemon_process:
            try:
                self._daemon_process.terminate()
            except Exception:
                pass
