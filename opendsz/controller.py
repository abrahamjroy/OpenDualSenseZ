"""
OpenDSX DualSense Device Manager and I/O Loop
Handles USB / Bluetooth detection, input polling, and asynchronous output report writing.
"""

import time
import threading
from typing import Optional, Callable
import hid

from .protocol import (
    DUALSENSE_VID,
    DUALSENSE_PID,
    DUALSENSE_EDGE_PID,
    ConnectionType,
    TriggerMode,
    DualSenseOutputReport,
    DualSenseInputReport,
)

class DualSenseController:
    def __init__(self):
        self.device = None
        self.connection_type = ConnectionType.UNKNOWN
        self.is_connected = False
        self.device_info = {}

        self.input_state = DualSenseInputReport()
        self.output_state = DualSenseOutputReport()

        self._running = False
        self._read_thread: Optional[threading.Thread] = None
        self._write_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Callbacks
        self.on_input_update: Optional[Callable[[DualSenseInputReport], None]] = None
        self.on_connection_change: Optional[Callable[[bool, str], None]] = None
        self.on_mute_toggle: Optional[Callable[[bool], None]] = None
        self.on_sleep_change: Optional[Callable[[bool], None]] = None

        # Diagnostics & Activity (PulseCore inspired)
        self.polling_rate_hz: float = 0.0
        self.input_latency_ms: float = 0.0
        self.last_activity_time: float = time.time()
        self.idle_timeout_seconds: int = 600  # Default 10 min auto-sleep (0 = off)
        self.is_sleeping: bool = False
        self.is_mic_muted: bool = False
        self.last_mute_btn_state: bool = False
        self.master_rumble_gain: float = 1.0
        self._pkt_count = 0
        self._last_rate_time = time.time()

    def connect(self) -> bool:
        """Discovers and connects to the first available DualSense or DualSense Edge controller."""
        devices = hid.enumerate(DUALSENSE_VID)
        target = None

        for d in devices:
            if d['product_id'] in (DUALSENSE_PID, DUALSENSE_EDGE_PID):
                # On Windows/Linux/Mac, the primary gamepad interface is selected
                target = d
                break

        if not target:
            return False

        try:
            self.device = hid.device()
            self.device.open_path(target['path'])
            self.device.set_nonblocking(False)

            # Determine USB vs Bluetooth by interface or report descriptor size
            # DualSense USB usually has usage page 1, usage 5, and shorter packet descriptor
            # Alternatively, test reading report length or path hints
            path_str = target.get('path', b'').decode('utf-8', errors='ignore').lower()
            if 'hid#{00001124' in path_str or 'bth' in path_str or 'bluetooth' in path_str:
                self.connection_type = ConnectionType.BLUETOOTH
            else:
                self.connection_type = ConnectionType.USB

            self.device_info = target
            self.is_connected = True

            # If Bluetooth, send feature report 0x05 to enable full extended reports
            if self.connection_type == ConnectionType.BLUETOOTH:
                try:
                    # 0x05 feature report initialization
                    init_data = bytes([0x05] + [0x00] * 40)
                    self.device.send_feature_report(init_data)
                except Exception:
                    pass

            self._start_threads()

            if self.on_connection_change:
                conn_name = "Bluetooth" if self.connection_type == ConnectionType.BLUETOOTH else "USB"
                self.on_connection_change(True, conn_name)

            return True

        except Exception as e:
            self.disconnect()
            return False

    def disconnect(self):
        self._running = False
        cur_thread = threading.current_thread()
        if self._read_thread and self._read_thread.is_alive() and cur_thread != self._read_thread:
            self._read_thread.join(timeout=0.5)
        if self._write_thread and self._write_thread.is_alive() and cur_thread != self._write_thread:
            self._write_thread.join(timeout=0.5)

        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

        self.is_connected = False
        self.connection_type = ConnectionType.UNKNOWN
        if self.on_connection_change:
            self.on_connection_change(False, "Disconnected")

    def _start_threads(self):
        self._running = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True, name="DualSense-Reader")
        self._write_thread = threading.Thread(target=self._write_loop, daemon=True, name="DualSense-Writer")
        self._read_thread.start()
        self._write_thread.start()

    def _read_loop(self):
        is_bt = (self.connection_type == ConnectionType.BLUETOOTH)
        read_size = 78 if is_bt else 64

        while self._running and self.device:
            try:
                data = self.device.read(read_size, timeout_ms=50)
                if not data:
                    continue

                raw_bytes = bytes(data)
                self.input_state.parse(raw_bytes, is_bluetooth=is_bt)

                now = time.time()
                self._pkt_count += 1
                delta = now - self._last_rate_time
                if delta >= 1.0:
                    self.polling_rate_hz = self._pkt_count / delta
                    self.input_latency_ms = (1000.0 / self.polling_rate_hz) if self.polling_rate_hz > 0 else 0.0
                    self._pkt_count = 0
                    self._last_rate_time = now

                # Activity detection
                active = any([
                    self.input_state.cross, self.input_state.circle, self.input_state.square, self.input_state.triangle,
                    self.input_state.l1, self.input_state.r1, self.input_state.l2 > 20, self.input_state.r2 > 20,
                    abs(self.input_state.lx - 128) > 15, abs(self.input_state.ly - 128) > 15,
                    abs(self.input_state.rx - 128) > 15, abs(self.input_state.ry - 128) > 15,
                    self.input_state.touch1_active, self.input_state.dpad != 8,
                ])
                if active:
                    self.last_activity_time = now
                    if self.is_sleeping:
                        self.is_sleeping = False
                        with self._lock:
                            self.output_state.power_save = 0x00
                        if self.on_sleep_change:
                            self.on_sleep_change(False)
                elif self.idle_timeout_seconds > 0 and not self.is_sleeping:
                    if (now - self.last_activity_time) > self.idle_timeout_seconds:
                        self.is_sleeping = True
                        with self._lock:
                            # Dim LEDs and triggers to conserve power
                            self.output_state.set_left_trigger(TriggerMode.OFF, [0] * 10)
                            self.output_state.set_right_trigger(TriggerMode.OFF, [0] * 10)
                            self.output_state.set_led_color(0, 0, 0)
                            self.output_state.rumble_left = 0
                            self.output_state.rumble_right = 0
                            self.output_state.power_save = 0x01
                        if self.on_sleep_change:
                            self.on_sleep_change(True)

                # Hardware Mute Button toggle & LED synchronization
                if self.input_state.mute and not self.last_mute_btn_state:
                    self.is_mic_muted = not self.is_mic_muted
                    self.update_mute_led(1 if self.is_mic_muted else 0)
                    if self.on_mute_toggle:
                        self.on_mute_toggle(self.is_mic_muted)
                self.last_mute_btn_state = self.input_state.mute

                if self.on_input_update:
                    self.on_input_update(self.input_state)

            except Exception:
                if self._running:
                    self.disconnect()
                break

    def _write_loop(self):
        # 40Hz for Bluetooth (prevents Windows BT HID buffer drops and controller watchdog resets)
        # 60Hz for USB (ultra-low latency)
        while self._running and self.device:
            interval = 1.0 / 40.0 if self.connection_type == ConnectionType.BLUETOOTH else 1.0 / 60.0
            start_time = time.perf_counter()

            with self._lock:
                packet = self.output_state.build_packet(self.connection_type)

            if packet:
                try:
                    self.device.write(packet)
                except Exception:
                    if self._running:
                        self.disconnect()
                    break

            elapsed = time.perf_counter() - start_time
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def update_trigger_left(self, mode, params):
        with self._lock:
            self.output_state.set_left_trigger(mode, params)

    def update_trigger_right(self, mode, params):
        with self._lock:
            self.output_state.set_right_trigger(mode, params)

    def update_led(self, r: int, g: int, b: int):
        with self._lock:
            self.output_state.set_led_color(r, g, b)

    def update_rumble(self, left: int, right: int):
        with self._lock:
            scaled_l = int(max(0, min(255, left)) * self.master_rumble_gain)
            scaled_r = int(max(0, min(255, right)) * self.master_rumble_gain)
            self.output_state.rumble_left = max(0, min(255, scaled_l))
            self.output_state.rumble_right = max(0, min(255, scaled_r))

    def trigger_haptic_pulse(self, left: int, right: int, duration_ms: int = 30):
        """Fires a precise non-blocking tactile micro-impulse for MacBook-style Force Touch feedback."""
        if not self.is_connected:
            return

        def _pulse():
            self.update_rumble(left, right)
            time.sleep(duration_ms / 1000.0)
            self.update_rumble(0, 0)

        threading.Thread(target=_pulse, daemon=True, name="Haptic-Touch-Pulse").start()

    def update_mute_led(self, state: int):
        """Sets the amber microphone mute LED (0=Off, 1=Solid, 2=Breathing)."""
        with self._lock:
            self.output_state.mute_led = state & 0x03

    def get_diagnostics_report(self) -> dict:
        """Returns full device diagnostics bundle inspired by PulseCore."""
        return {
            "connected": self.is_connected,
            "device_name": self.device_info.get("product_string", "DualSense Wireless Controller"),
            "connection_type": "Bluetooth" if self.connection_type == ConnectionType.BLUETOOTH else ("USB" if self.connection_type == ConnectionType.USB else "Disconnected"),
            "polling_rate_hz": round(self.polling_rate_hz, 1),
            "latency_ms": round(self.input_latency_ms, 2),
            "jitter_warning": bool(self.connection_type == ConnectionType.BLUETOOTH and self.input_latency_ms > 20.0),
            "battery_level": self.input_state.battery_level,
            "is_charging": self.input_state.is_charging,
            "headphones_connected": getattr(self.input_state, "headphones_connected", False),
            "is_mic_muted": self.is_mic_muted,
            "is_sleeping": self.is_sleeping,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "master_rumble_gain": self.master_rumble_gain,
        }

    def send_raw_report(self, data: bytes) -> bool:
        """Sends an immediate custom raw HID report (e.g. 0x36 Bluetooth audio/haptic stream)."""
        if not self.device or not self.is_connected:
            return False
        try:
            self.device.write(data)
            return True
        except Exception:
            return False
