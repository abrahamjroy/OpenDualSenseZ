"""
OpenDSZ Forza Horizon Telemetry Parser & Advanced Traction Loss Synthesizer
Compatible with Steam versions of Forza Horizon 4, 5, and 6, and Forza Motorsport (UDP Data Out).
Accurately replicates Xbox impulse trigger haptics and stepper motor pushback
during wheelspin, tire slip, ABS braking, gear shifts, and kerb strikes.
"""

import math
import socket
import struct
import threading
import time
from typing import Optional, Callable, Dict, Any
from .protocol import TriggerMode

FORZA_UDP_PORT = 5300

class ForzaTelemetryEngine:
    def __init__(self, port: int = FORZA_UDP_PORT):
        self.port = port
        self.running = False
        self.socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

        # Callbacks
        # on_trigger_update(left_mode, left_params, right_mode, right_params, rumble_left, rumble_right)
        self.on_trigger_update: Optional[Callable[[TriggerMode, list, TriggerMode, list, int, int], None]] = None
        self.on_rpm_update: Optional[Callable[[float], None]] = None
        self.on_telemetry_stats: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_gear_shift: Optional[Callable[[int], None]] = None

        # Tuning Parameters
        self.abs_sensitivity = 1.05        # Front slip threshold for ABS pulsation
        self.traction_sensitivity = 1.05   # Drive wheel slip threshold for traction loss vibration
        self.brake_resistance_base = 170   # Hydraulic brake baseline stiffness
        self.throttle_resistance_base = 75 # Throttle baseline stiffness

        self.last_gear = 0
        self.last_shift_time = 0.0

        # Diagnostics & Activity Tracking
        self.packet_count = 0
        self.packets_in_window = 0
        self.current_hz = 0.0
        self.last_stat_time = time.perf_counter()
        self.last_packet_time = 0.0
        self.last_state = {
            "speed_mph": 0.0,
            "rpm": 0,
            "max_rpm": 0,
            "gear": 0,
            "throttle": 0,
            "brake": 0,
            "slip_drive": 0.0,
            "slip_front": 0.0,
            "is_race_on": False,
            "packet_hz": 0.0,
            "event": "Waiting"
        }

    def set_port(self, port: int):
        if port == self.port or port <= 0 or port > 65535:
            return
        self.port = port
        if self.running:
            self.stop()
            self.start()

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="Forza-Telemetry")
        self._thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, 'sockets') and self.sockets:
            for s in self.sockets:
                try:
                    s.close()
                except Exception:
                    pass
            self.sockets.clear()
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _listen_loop(self):
        import select
        self.sockets = []
        target_ports = [self.port]
        for cp in (5300, 5607, 5301, 7777):
            if cp not in target_ports:
                target_ports.append(cp)

        for p in target_ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Prevent WinError 10054 on ICMP port unreachable
                if hasattr(socket, "SIO_UDP_CONNRESET"):
                    try:
                        s.ioctl(socket.SIO_UDP_CONNRESET, False)
                    except Exception:
                        pass
                # Bind to 0.0.0.0 so all interfaces (127.0.0.1, local LAN IP, broadcast) are accepted
                s.bind(("0.0.0.0", p))
                s.setblocking(False)
                self.sockets.append(s)
                if p == self.port:
                    self.socket = s
            except Exception:
                pass

        if not self.sockets:
            self.running = False
            return

        self.last_stat_time = time.perf_counter()
        self.packets_in_window = 0

        while self.running:
            try:
                readable, _, _ = select.select(self.sockets, [], [], 0.5)
                if not readable:
                    now = time.perf_counter()
                    if (now - self.last_packet_time) > 2.0 and self.last_packet_time > 0:
                        self.current_hz = 0.0
                        self.last_state["packet_hz"] = 0.0
                        self.last_state["event"] = "Waiting"
                        if self.on_telemetry_stats:
                            self.on_telemetry_stats(dict(self.last_state))
                    continue

                for s in readable:
                    try:
                        data, _ = s.recvfrom(1024)
                        if len(data) >= 232:
                            self._parse_and_synthesize(data)
                            self.packet_count += 1
                            self.packets_in_window += 1
                    except (BlockingIOError, socket.error):
                        pass
            except (ConnectionResetError, OSError):
                continue
            except Exception:
                break

            now = time.perf_counter()
            dt = now - self.last_stat_time
            if dt >= 0.5:
                self.current_hz = self.packets_in_window / dt
                self.packets_in_window = 0
                self.last_stat_time = now
                self.last_state["packet_hz"] = round(self.current_hz, 1)
                if self.on_telemetry_stats:
                    self.on_telemetry_stats(dict(self.last_state))

    def _parse_and_synthesize(self, data: bytes):
        """
        Parses Forza Data Out packet (Little-Endian):
          Supported wire formats:
            - 324 bytes: Forza Horizon 4 / 5 / 6 Dash (CarDash with 12-byte Sled gap)
            - 311 bytes: Forza Motorsport 7 / FM 2023 Dash
            - 232 bytes: Sled base telemetry

          Sled Offsets (0..231 in all formats):
            Byte 0: is_race_on (s32)
            Byte 8: engine_max_rpm (f32)
            Byte 12: engine_idle_rpm (f32)
            Byte 16: current_engine_rpm (f32)
            Byte 20..31: accel_x, accel_y, accel_z (3 x f32)
            Byte 32..43: vel_x, vel_y, vel_z (3 x f32)
            Byte 84: tire_slip_ratio_fl (f32)
            Byte 88: tire_slip_ratio_fr (f32)
            Byte 92: tire_slip_ratio_rl (f32)
            Byte 96: tire_slip_ratio_rr (f32)
            Byte 116..131: wheel_on_rumble_strip (4 x s32: fl, fr, rl, rr)
            Byte 148..163: surface_rumble (4 x f32: fl, fr, rl, rr)
            Byte 224: drivetrain_type (s32: 0=FWD, 1=RWD, 2=AWD)

          Dash Offsets:
            324-byte Horizon (12-byte gap at 232..243):
              Byte 256: speed (f32, m/s)
              Byte 315: throttle (u8, 0..255)
              Byte 316: brake (u8, 0..255)
              Byte 317: clutch (u8, 0..255)
              Byte 318: handbrake (u8, 0..255)
              Byte 319: gear (u8, 0..10)
              Byte 320: steer (s8, -128..127)
            311-byte FM7:
              Byte 244: speed (f32, m/s)
              Byte 303: throttle (u8, 0..255)
              Byte 304: brake (u8, 0..255)
              Byte 305: clutch (u8, 0..255)
              Byte 306: handbrake (u8, 0..255)
              Byte 307: gear (u8, 0..10)
              Byte 308: steer (s8, -128..127)
        """
        try:
            now = time.perf_counter()
            self.last_packet_time = now

            # Sled header unpacking
            is_race_on = struct.unpack_from('<i', data, 0)[0]
            engine_max_rpm = struct.unpack_from('<f', data, 8)[0]
            current_rpm = struct.unpack_from('<f', data, 16)[0]
            accel_z = struct.unpack_from('<f', data, 28)[0]
            vel_x, vel_y, vel_z = struct.unpack_from('<3f', data, 32)

            # Tire slip ratios (Front Left starts at offset 84)
            slip_fl, slip_fr, slip_rl, slip_rr = struct.unpack_from('<4f', data, 84)

            # Rumble strips & surface rumble
            rumble_fl, rumble_fr, rumble_rl, rumble_rr = struct.unpack_from('<4i', data, 116)
            surface_fl, surface_fr, surface_rl, surface_rr = struct.unpack_from('<4f', data, 148)

            drivetrain_type = struct.unpack_from('<i', data, 224)[0] if len(data) >= 228 else 1

            # Dash extraction based on wire format length
            if len(data) >= 324:
                speed_ms = struct.unpack_from('<f', data, 256)[0]
                throttle = data[315]
                brake = data[316]
                gear = data[319]
            elif len(data) >= 311:
                speed_ms = struct.unpack_from('<f', data, 244)[0]
                throttle = data[303]
                brake = data[304]
                gear = data[307]
            else: # Sled (232 bytes)
                speed_ms = math.sqrt(vel_x*vel_x + vel_y*vel_y + vel_z*vel_z)
                throttle = min(255, int(max(0.0, accel_z) * 35.0))
                brake = min(255, int(max(0.0, -accel_z) * 35.0))
                gear = 1 if speed_ms > 0.5 else 0

            speed_mph = max(0.0, speed_ms * 2.23694)

            # RPM Ratio (0.0 to 1.0) for tachometer shift light
            if engine_max_rpm > 100.0:
                rpm_ratio = max(0.0, min(1.0, current_rpm / engine_max_rpm))
                if self.on_rpm_update:
                    self.on_rpm_update(rpm_ratio)

            # If not racing (paused, menus, loading), reset triggers to idle
            if is_race_on == 0:
                if self.on_trigger_update:
                    self.on_trigger_update(TriggerMode.OFF, [0]*10, TriggerMode.OFF, [0]*10, 0, 0)
                self.last_state.update({
                    "speed_mph": round(speed_mph, 1),
                    "rpm": int(current_rpm),
                    "max_rpm": int(engine_max_rpm),
                    "gear": gear,
                    "throttle": throttle,
                    "brake": brake,
                    "slip_drive": 0.0,
                    "slip_front": 0.0,
                    "is_race_on": False,
                    "event": "Paused / In Menus"
                })
                return

            rumble_left = 0
            rumble_right = 0
            active_event = "Cruising"

            # ============================================================
            # 1. LEFT TRIGGER: Hydraulic Braking & ABS Kickback
            # ============================================================
            max_front_slip = max(abs(slip_fl), abs(slip_fr))
            if brake > 15:
                if max_front_slip > self.abs_sensitivity:
                    # ABS Engagement: Rapid vibration simulating hydraulic shudder
                    abs_severity = min(1.0, (max_front_slip - self.abs_sensitivity) * 3.0)
                    freq = int(10 + abs_severity * 5) # 10Hz to 15Hz
                    force = min(255, int(brake * 1.15))
                    start_pos = 8
                    left_mode = TriggerMode.PULSE
                    left_params = [freq, force, start_pos]
                    rumble_left = int(abs_severity * 190)
                    active_event = f"ABS Lockup ({max_front_slip:.2f}x)"
                else:
                    # Progressive hydraulic pedal resistance curve
                    progressive_force = min(255, self.brake_resistance_base + int((brake / 255.0) * 80))
                    left_mode = TriggerMode.RIGID
                    left_params = [4, progressive_force]
                    active_event = f"Braking ({int(brake/2.55)}%)"
            else:
                left_mode = TriggerMode.OFF
                left_params = [0] * 10

            # ============================================================
            # 2. RIGHT TRIGGER: Traction Loss Simulation (Xbox Impulse Style)
            # ============================================================
            # Determine drive wheel slip based on drivetrain:
            # 0 = FWD (front wheels slip), 1 = RWD (rear wheels slip), 2 = AWD (all wheels slip)
            if drivetrain_type == 0:
                drive_slip = max(abs(slip_fl), abs(slip_fr))
            elif drivetrain_type == 1:
                drive_slip = max(abs(slip_rl), abs(slip_rr))
            else:
                drive_slip = max(abs(slip_fl), abs(slip_fr), abs(slip_rl), abs(slip_rr))

            # Detect gear shifts (250ms mechanical transmission clunk & trigger kick)
            if self.packet_count <= 5:
                self.last_gear = gear
            elif gear != self.last_gear:
                self.last_gear = gear
                self.last_shift_time = now
                if self.on_gear_shift:
                    try:
                        self.on_gear_shift(gear)
                    except Exception:
                        pass

            shift_elapsed = now - self.last_shift_time
            if shift_elapsed < 0.25:
                # Heavy dual-motor mechanical clunk with exponential decay
                decay = max(0.0, (1.0 - shift_elapsed / 0.25) ** 1.4)
                rumble_left = max(rumble_left, int(255 * decay))
                rumble_right = max(rumble_right, int(240 * decay))
                # Recoil kick against finger on throttle (30Hz sharp pulses decaying with shift impact)
                right_mode = TriggerMode.VIBRATION
                right_params = [30, int(255 * decay), 0]
                active_event = f"Gear Shift -> G{gear}" if gear > 0 else "Gear Shift -> R"

            elif throttle > 15 and drive_slip > self.traction_sensitivity:
                # Traction Loss Detected!
                slip_excess = drive_slip - self.traction_sensitivity
                slip_ratio_clamped = min(1.0, slip_excess * 3.5) # Scale to 0.0 - 1.0

                if slip_ratio_clamped > 0.35:
                    # Severe wheelspin (burnout, launch, corner exit oversteer)
                    # Machine-gun rapid mechanical chatter pushing back against trigger
                    freq = min(15, int(11 + slip_ratio_clamped * 4)) # 11Hz - 15Hz
                    force = min(255, int(throttle * 1.10))
                    right_mode = TriggerMode.MACHINE_GUN
                    right_params = [freq, force, 4]
                    active_event = f"Traction Loss! ({drive_slip:.2f}x)"
                else:
                    # Mild slip / initial loss of traction (tires chirping)
                    freq = min(12, int(7 + slip_ratio_clamped * 10)) # 7Hz - 11Hz
                    force = min(220, int(throttle * 0.95))
                    right_mode = TriggerMode.GALLOP
                    right_params = [freq, force, 5]
                    active_event = f"Tire Chirp ({drive_slip:.2f}x)"

                # Dual feedback: synchronize right motor rumble for complete impulse feel
                rumble_right = max(rumble_right, int(slip_ratio_clamped * 220))

            elif throttle > 10:
                # Normal acceleration: progressive throttle cable tension
                throttle_force = min(200, self.throttle_resistance_base + int((throttle / 255.0) * 45))
                right_mode = TriggerMode.RIGID
                right_params = [4, throttle_force]
                if active_event == "Cruising":
                    active_event = f"Accelerating ({int(throttle/2.55)}%)"
            else:
                right_mode = TriggerMode.OFF
                right_params = [0] * 10

            # ============================================================
            # 3. KERBS & ROAD SURFACE HAPTIC SYNTHESIS
            # ============================================================
            # Kerb / Rumble Strips
            if rumble_fl > 0 or rumble_rl > 0:
                rumble_left = max(rumble_left, 160)
            if rumble_fr > 0 or rumble_rr > 0:
                rumble_right = max(rumble_right, 160)

            # Surface roughness (gravel, cobblestones, dirt)
            surf_left = max(surface_fl, surface_rl)
            surf_right = max(surface_fr, surface_rr)
            if surf_left > 0.05:
                rumble_left = max(rumble_left, min(200, int(surf_left * 220)))
            if surf_right > 0.05:
                rumble_right = max(rumble_right, min(200, int(surf_right * 220)))

            # Update cached state
            self.last_state.update({
                "speed_mph": round(speed_mph, 1),
                "rpm": int(current_rpm),
                "max_rpm": int(engine_max_rpm),
                "gear": gear,
                "throttle": throttle,
                "brake": brake,
                "slip_drive": round(drive_slip, 2),
                "slip_front": round(max_front_slip, 2),
                "is_race_on": True,
                "event": active_event
            })

            if self.on_trigger_update:
                self.on_trigger_update(left_mode, left_params, right_mode, right_params, rumble_left, rumble_right)

        except Exception:
            pass
