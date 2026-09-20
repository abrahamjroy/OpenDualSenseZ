"""
OpenDSX DSX-Compatible UDP IPC Server
Listens on UDP Port 6969 and parses standard DualSenseX instructions
(both Key-Value string format and JSON format) from games and mods.
"""

import socket
import json
import threading
import re
from typing import Optional, Callable
from .protocol import TriggerMode

DSX_DEFAULT_PORT = 6969

TRIGGER_NAME_MAP = {
    "off": TriggerMode.OFF,
    "normal": TriggerMode.OFF,
    "rigid": TriggerMode.RIGID,
    "resistance": TriggerMode.RIGID,
    "trigger": TriggerMode.TRIGGER_STOP,
    "hardstop": TriggerMode.TRIGGER_STOP,
    "bow": TriggerMode.BOW,
    "feedback": TriggerMode.FEEDBACK,
    "pulse": TriggerMode.PULSE,
    "automaticgun": TriggerMode.PULSE,
    "machinegun": TriggerMode.MACHINE_GUN,
    "machine": TriggerMode.MACHINE_GUN,
    "gallop": TriggerMode.GALLOP,
    "choppy": TriggerMode.CHOPPY,
}

DSX_NUMERIC_MODE_MAP = {
    0: TriggerMode.OFF,
    1: TriggerMode.RIGID,
    2: TriggerMode.TRIGGER_STOP,
    3: TriggerMode.BOW,
    4: TriggerMode.FEEDBACK,
    6: TriggerMode.PULSE,
    7: TriggerMode.CHOPPY,
    21: TriggerMode.RIGID,
    22: TriggerMode.BOW,
    23: TriggerMode.GALLOP,
    25: TriggerMode.TRIGGER_STOP,
    26: TriggerMode.PULSE,
    27: TriggerMode.MACHINE_GUN,
}

class DSXUdpServer:
    def __init__(self, port: int = DSX_DEFAULT_PORT):
        self.port = port
        self.running = False
        self.socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_trigger_update: Optional[Callable[[str, TriggerMode, list], None]] = None
        self.on_rgb_update: Optional[Callable[[int, int, int], None]] = None
        self.on_rumble_update: Optional[Callable[[int, int], None]] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._server_loop, daemon=True, name="DSX-UDP-Server")
        self._thread.start()

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _server_loop(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(("127.0.0.1", self.port))
            self.socket.settimeout(0.5)
        except Exception:
            self.running = False
            return

        while self.running:
            try:
                data, _ = self.socket.recvfrom(2048)
                if data:
                    self._dispatch_packet(data)
            except socket.timeout:
                continue
            except Exception:
                break

    def _dispatch_packet(self, data: bytes):
        # Try JSON format first
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if text.startswith("{") and text.endswith("}"):
                self._handle_json(text)
                return
            else:
                self._handle_key_value(text)
        except Exception:
            pass

    def _handle_json(self, text: str):
        payload = json.loads(text)
        instructions = payload.get("instructions", [])
        for inst in instructions:
            itype = inst.get("type")
            params = inst.get("parameters", [])
            # Type 1: Trigger update
            # Typically [TriggerIndex (0=Left, 1=Right), TriggerMode, Param1, Param2, ...]
            if itype == 1 and len(params) >= 2:
                side = "left" if params[0] == 0 else "right"
                mode_raw = params[1]
                mode = DSX_NUMERIC_MODE_MAP.get(mode_raw, TriggerMode.OFF)
                trigger_params = params[2:]
                if self.on_trigger_update:
                    self.on_trigger_update(side, mode, trigger_params)

            # Type 2: RGB update [R, G, B]
            elif itype == 2 and len(params) >= 3:
                if self.on_rgb_update:
                    self.on_rgb_update(params[0], params[1], params[2])

            # Type 3: Rumble update [Left, Right]
            elif itype == 3 and len(params) >= 2:
                if self.on_rumble_update:
                    self.on_rumble_update(params[0], params[1])

    def _handle_key_value(self, text: str):
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().lower()
                v = v.strip()

                if k in ("lefttrigger", "lt"):
                    self._parse_trigger_string("left", v)
                elif k in ("righttrigger", "rt"):
                    self._parse_trigger_string("right", v)
                elif k in ("rgb", "lightbar"):
                    parts = [int(p.strip()) for p in v.split(",") if p.strip().isdigit()]
                    if len(parts) >= 3 and self.on_rgb_update:
                        self.on_rgb_update(parts[0], parts[1], parts[2])
                elif k in ("rumble", "vibrate"):
                    parts = [int(p.strip()) for p in v.split(",") if p.strip().isdigit()]
                    if len(parts) >= 2 and self.on_rumble_update:
                        self.on_rumble_update(parts[0], parts[1])

    def _parse_trigger_string(self, side: str, val_str: str):
        # Parses forms like: "Rigid(start, force)" or "Resistance" or "Pulse(10, 200, 20)"
        m = re.match(r"([a-zA-Z_]+)(?:\((.*)\))?", val_str)
        if not m:
            return

        mode_name = m.group(1).lower()
        args_str = m.group(2) or ""
        mode = TRIGGER_NAME_MAP.get(mode_name, TriggerMode.OFF)

        params = []
        if args_str:
            for item in re.split(r"[,;]+", args_str):
                item = item.strip()
                if item.isdigit():
                    params.append(int(item))

        # Default fallback values for simple string commands like "LeftTrigger=Rigid"
        if not params:
            if mode == TriggerMode.RIGID:
                params = [10, 200]
            elif mode == TriggerMode.TRIGGER_STOP:
                params = [20, 150, 255]
            elif mode in (TriggerMode.PULSE, TriggerMode.MACHINE_GUN):
                params = [10, 220, 15]

        if self.on_trigger_update:
            self.on_trigger_update(side, mode, params)
