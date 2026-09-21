"""
OpenDSZ Headless Daemon & Local REST API Service
Allows OpenDSZ to run as a background service on Linux / SteamOS / Windows
without requiring a GUI or X11/Wayland display server.
Exposes an ultra-fast, zero-dependency JSON HTTP API on localhost:5305.
"""

import os
import sys
import json
import time
import signal
import threading
from typing import Dict, Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from .protocol import TriggerMode, ConnectionType
from .controller import DualSenseController
from .telemetry_forza import ForzaTelemetryEngine
from .dsx_server import DSXUdpServer
from .profiles import ProfileManager
from .effects import LightbarEffectsEngine, LightEffect


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class OpenDSZDaemon:
    def __init__(self, host: str = "127.0.0.1", port: int = 5305):
        self.host = host
        self.port = port
        self._running = False

        # Core subsystems
        self.controller = DualSenseController()
        self.profile_mgr = ProfileManager()
        self.forza_telemetry = ForzaTelemetryEngine()
        self.dsx_server = DSXUdpServer()
        self.effects = LightbarEffectsEngine()

        self.active_profile_name: Optional[str] = None
        self._active_effect_name: str = "Ferrari F1 Shift Indicator"

        # Wire callbacks
        self.controller.on_connection_change = self._on_connection_changed
        self.forza_telemetry.on_trigger_update = self._on_forza_trigger_update
        self.forza_telemetry.on_rpm_update = self.effects.set_rpm_ratio
        self.dsx_server.on_trigger_update = self._on_dsx_trigger_update
        self.dsx_server.on_rgb_update = self._on_dsx_rgb_update
        self.effects.on_color_update = self._on_effect_color_update

        # Set default effect
        self.set_effect("RPM Shift Light (Ferrari & Forza)")

        self._server: Optional[ThreadedHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def _on_connection_changed(self, connected: bool, conn_type: ConnectionType):
        state = "Connected" if connected else "Disconnected"
        print(f"[OpenDSZ Daemon] Controller {state} ({conn_type.name})", flush=True)

    def _on_forza_trigger_update(self, left_mode: int, left_params: list, right_mode: int, right_params: list):
        if self.controller.is_connected:
            self.controller.update_trigger_left(TriggerMode(left_mode), left_params)
            self.controller.update_trigger_right(TriggerMode(right_mode), right_params)

    def _on_dsx_trigger_update(self, trigger_type: str, mode: TriggerMode, params: list):
        if self.controller.is_connected:
            if trigger_type == "left":
                self.controller.update_trigger_left(mode, params)
            elif trigger_type == "right":
                self.controller.update_trigger_right(mode, params)

    def _on_dsx_rgb_update(self, r: int, g: int, b: int):
        if self.controller.is_connected:
            self.controller.update_led(r, g, b)

    def _on_effect_color_update(self, r: int, g: int, b: int):
        if self.controller.is_connected:
            self.controller.update_led(r, g, b)

    def get_status(self) -> Dict[str, Any]:
        diag = self.controller.get_diagnostics_report()
        return {
            "status": "online",
            "connected": self.controller.is_connected,
            "connection_type": diag.get("connection_type", "Disconnected"),
            "battery": diag.get("battery_level", 0),
            "is_charging": diag.get("is_charging", False),
            "latency_ms": diag.get("latency_ms", 0.0),
            "polling_rate_hz": diag.get("polling_rate_hz", 0.0),
            "active_profile": self.active_profile_name or "default",
            "effect": self._active_effect_name,
            "telemetry": {
                "forza_active": self.forza_telemetry.running,
                "forza_port": self.forza_telemetry.port,
                "dsx_active": self.dsx_server.running
            }
        }

    def list_profiles(self) -> list:
        return list(self.profile_mgr.profiles.keys())

    def apply_profile(self, profile_name: str) -> bool:
        prof = self.profile_mgr.profiles.get(profile_name)
        if not prof:
            for k, v in self.profile_mgr.profiles.items():
                if k.lower() == profile_name.lower() or profile_name.lower() in k.lower():
                    prof = v
                    profile_name = k
                    break
        if not prof:
            return False

        self.active_profile_name = profile_name
        self.profile_mgr.active_profile_name = profile_name

        # Triggers
        triggers = prof.get("triggers", {})
        lt = triggers.get("left", {})
        rt = triggers.get("right", {})
        if lt:
            mode = TriggerMode(lt.get("mode", int(TriggerMode.OFF)))
            self.controller.update_trigger_left(mode, lt.get("params", []))
        if rt:
            mode = TriggerMode(rt.get("mode", int(TriggerMode.OFF)))
            self.controller.update_trigger_right(mode, rt.get("params", []))

        # LED
        led = prof.get("led", {})
        effect = led.get("effect")
        if effect:
            self.set_effect(effect)
        else:
            r = led.get("r", 0)
            g = led.get("g", 120)
            b = led.get("b", 255)
            self.set_effect("Static", r=r, g=g, b=b)

        # Telemetry
        tel = prof.get("telemetry", {})
        if tel.get("enabled"):
            port = tel.get("port", 5300)
            self.forza_telemetry.set_port(port)
            self.forza_telemetry.start()
        else:
            self.forza_telemetry.stop()

        return True

    def set_effect(self, effect_name: str, r: int = 0, g: int = 120, b: int = 255) -> bool:
        self.effects.set_base_color(r, g, b)

        target_effect = LightEffect.STATIC
        for eff in LightEffect:
            if eff.value.lower() == effect_name.lower() or effect_name.lower() in eff.value.lower() or eff.name.lower() == effect_name.lower():
                target_effect = eff
                break

        self._active_effect_name = target_effect.value
        self.effects.set_effect(target_effect)
        return True

    def set_triggers(self, left: Optional[dict] = None, right: Optional[dict] = None) -> bool:
        if left:
            mode = TriggerMode[left.get("mode", "OFF")] if isinstance(left.get("mode"), str) else TriggerMode(left.get("mode", 0))
            params = left.get("params", [left.get("start", 0), left.get("force", 0), left.get("freq", 0)])
            self.controller.update_trigger_left(mode, params)
        if right:
            mode = TriggerMode[right.get("mode", "OFF")] if isinstance(right.get("mode"), str) else TriggerMode(right.get("mode", 0))
            params = right.get("params", [right.get("start", 0), right.get("force", 0), right.get("freq", 0)])
            self.controller.update_trigger_right(mode, params)
        return True

    def _connection_watcher(self):
        while self._running:
            if not self.controller.is_connected:
                try:
                    self.controller.connect()
                except Exception:
                    pass
            time.sleep(2.0)

    def start(self):
        if self._running:
            return
        self._running = True

        print(f"[OpenDSZ Daemon] Starting OpenDSZ Headless Daemon...", flush=True)

        # 1. Start controller background connection watcher
        self._watcher_thread = threading.Thread(target=self._connection_watcher, daemon=True)
        self._watcher_thread.start()
        # Immediate initial connect attempt
        try:
            self.controller.connect()
        except Exception:
            pass

        # 2. Start effects engine
        self.effects.start()

        # 3. Start default telemetry listener
        self.forza_telemetry.start()
        self.dsx_server.start()

        # 4. Apply default profile
        profiles = self.list_profiles()
        if "forza_horizon_5" in profiles:
            self.apply_profile("forza_horizon_5")
        elif profiles:
            self.apply_profile(profiles[0])

        # 5. Start HTTP REST Server
        daemon_ref = self

        class DaemonRequestHandler(BaseHTTPRequestHandler):
            def _send_json(self, status_code: int, data: Any):
                payload = json.dumps(data).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.end_headers()
                self.wfile.write(payload)

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.end_headers()

            def do_GET(self):
                if self.path == "/api/status":
                    self._send_json(200, daemon_ref.get_status())
                elif self.path == "/api/profiles":
                    self._send_json(200, {
                        "profiles": daemon_ref.list_profiles(),
                        "active": daemon_ref.active_profile_name
                    })
                elif self.path == "/api/effects":
                    self._send_json(200, {
                        "effects": [eff.value for eff in LightEffect],
                        "active": daemon_ref._active_effect_name
                    })
                else:
                    self._send_json(404, {"error": "Endpoint not found"})

            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", 0))
                body = {}
                if content_length > 0:
                    raw_body = self.rfile.read(content_length).decode("utf-8")
                    try:
                        body = json.loads(raw_body)
                    except Exception:
                        self._send_json(400, {"error": "Invalid JSON payload"})
                        return

                if self.path == "/api/profile":
                    name = body.get("name")
                    if not name or not daemon_ref.apply_profile(name):
                        self._send_json(400, {"error": f"Failed to apply profile '{name}'"})
                    else:
                        self._send_json(200, {"success": True, "active_profile": name})

                elif self.path == "/api/effects":
                    eff = body.get("effect", daemon_ref._active_effect_name)
                    r = body.get("r", 0)
                    g = body.get("g", 120)
                    b = body.get("b", 255)
                    daemon_ref.set_effect(eff, r, g, b)
                    self._send_json(200, {"success": True, "effect": eff})

                elif self.path == "/api/triggers":
                    daemon_ref.set_triggers(body.get("left"), body.get("right"))
                    self._send_json(200, {"success": True})

                elif self.path == "/api/telemetry":
                    enabled = body.get("enabled", True)
                    port = body.get("port", 5300)
                    if enabled:
                        daemon_ref.forza_telemetry.set_port(port)
                        daemon_ref.forza_telemetry.start()
                    else:
                        daemon_ref.forza_telemetry.stop()
                    self._send_json(200, {"success": True, "telemetry_enabled": enabled, "port": port})

                else:
                    self._send_json(404, {"error": "Endpoint not found"})

            def log_message(self, format, *args):
                # Suppress verbose HTTP access logs to stdout in daemon mode
                pass

        self._server = ThreadedHTTPServer((self.host, self.port), DaemonRequestHandler)
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()

        print(f"[OpenDSZ Daemon] REST API listening on http://{self.host}:{self.port}/api/status", flush=True)

    def stop(self):
        if not self._running:
            return
        self._running = False
        print("[OpenDSZ Daemon] Shutting down daemon...", flush=True)

        if self._server:
            self._server.shutdown()
            self._server.server_close()

        self.forza_telemetry.stop()
        self.dsx_server.stop()
        self.effects.stop()
        self.controller.disconnect()
        print("[OpenDSZ Daemon] Stopped cleanly.", flush=True)

    def run_forever(self):
        self.start()
        stop_event = threading.Event()

        def _handle_signal(signum, frame):
            print(f"\n[OpenDSZ Daemon] Signal {signum} received, stopping...", flush=True)
            stop_event.set()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        try:
            while not stop_event.is_set():
                time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self.stop()
