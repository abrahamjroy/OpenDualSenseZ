"""
OpenDSX Touchpad-to-Mouse Driver
Provides cross-platform cursor movement, click injection, and gesture scrolling
for Windows, macOS, and Linux.
"""

import sys
import time
import math
import ctypes
from typing import Optional, Callable

# Platform-specific mouse injection
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

if IS_WINDOWS:
    # Win32 INPUT structure definitions
    PUL = ctypes.POINTER(ctypes.c_ulong)
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class INPUT_I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", INPUT_I)]

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800

    def _win_send_mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0):
        extra = ctypes.c_ulong(0)
        ii_ = INPUT_I()
        ii_.mi = MOUSEINPUT(dx, dy, data, flags, 0, ctypes.pointer(extra))
        cmd = INPUT(ctypes.c_ulong(0), ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))


class TouchpadMouse:
    def __init__(self):
        self.enabled = False
        self.sensitivity = 0.2  # Starts at lowest setting by default
        self.acceleration = 1.4
        self.scroll_sensitivity = 0.5
        self.scroll_lines = 3   # Windows standard scroll lines per step
        self.haptics_enabled = True
        self.controller_shortcuts_enabled = True

        # Air Mouse & Gyro Motion Tracking
        self.air_mouse_enabled = False
        self.gyro_sensitivity = 0.8
        self.gyro_deadzone = 100
        self.invert_pitch = False
        self.trigger_break_threshold = 150   # Trigger pull value (0-255) for crisp firearm sear break
        self.trigger_release_threshold = 60  # Trigger release reset value
        self.r2_clicked = False              # R2: Primary Gun Break (Left Click)
        self.l2_clicked = False              # L2: Aim/Secondary Gun Break (Right Click)
        self._last_gyro_dx = 0.0
        self._last_gyro_dy = 0.0

        # Callbacks
        # on_haptic_feedback(feedback_type: str) -> "tap", "down_left", "down_right", "down_middle", "up", "scroll", "gun_recoil_right", "gun_recoil_left", "gun_reset"
        self.on_haptic_feedback: Optional[Callable[[str], None]] = None

        # Tracking state
        self.last_x: Optional[int] = None
        self.last_y: Optional[int] = None
        self.last_touch_time: float = 0
        self.touch_start_time: float = 0
        self.is_touching = False
        self.touch_travel_dist = 0.0

        # Two-finger tap / scroll state
        self.two_finger_active = False
        self.two_finger_start_time = 0.0
        self.two_finger_travel_dist = 0.0
        self.last_two_x: Optional[int] = None
        self.last_two_y: Optional[int] = None
        self.scroll_accum = 0.0

        # Physical button click tracking
        self.last_pad_click = False
        self.active_pad_click_type: Optional[str] = None

        # Controller shortcuts edge tracking
        self.last_l1 = False
        self.last_r1 = False
        self.last_r3 = False

    def reset(self):
        self.last_x = None
        self.last_y = None
        self.is_touching = False
        self.touch_travel_dist = 0.0
        self.two_finger_active = False
        self.two_finger_travel_dist = 0.0
        self.last_two_x = None
        self.last_two_y = None

        # Release any held trigger clicks on reset
        if self.r2_clicked:
            self._inject_click("left", False)
            self.r2_clicked = False
        if self.l2_clicked:
            self._inject_click("right", False)
            self.l2_clicked = False
        self._last_gyro_dx = 0.0
        self._last_gyro_dy = 0.0

    def set_scroll_lines(self, lines: int):
        self.scroll_lines = max(1, min(20, int(lines)))

    def set_gyro_sensitivity(self, sens: float):
        self.gyro_sensitivity = max(0.1, min(5.0, float(sens)))

    def set_gyro_deadzone(self, deadzone: int):
        self.gyro_deadzone = max(0, min(500, int(deadzone)))

    def _haptic(self, feedback_type: str):
        if self.haptics_enabled and self.on_haptic_feedback:
            try:
                self.on_haptic_feedback(feedback_type)
            except Exception:
                pass

    def process_touch(self, touch1_active: bool, x1: int, y1: int,
                      touch2_active: bool, x2: int, y2: int,
                      pad_clicked: bool,
                      l1: bool = False, r1: bool = False,
                      r3: bool = False, dpad: int = 8):
        if not self.enabled:
            return

        now = time.perf_counter()

        # -------------------------------------------------------------
        # 1. Controller Hardware Button Shortcuts (L1=Left, R1=Right, R3=Middle)
        # -------------------------------------------------------------
        if self.controller_shortcuts_enabled:
            if l1 and not self.last_l1:
                self._inject_click("left", True)
                self._haptic("down_left")
            elif not l1 and self.last_l1:
                self._inject_click("left", False)
                self._haptic("up")
            self.last_l1 = l1

            if r1 and not self.last_r1:
                self._inject_click("right", True)
                self._haptic("down_right")
            elif not r1 and self.last_r1:
                self._inject_click("right", False)
                self._haptic("up")
            self.last_r1 = r1

            if r3 and not self.last_r3:
                self._inject_click("middle", True)
                self._haptic("down_middle")
            elif not r3 and self.last_r3:
                self._inject_click("middle", False)
                self._haptic("up")
            self.last_r3 = r3

            scroll_unit = int(40 * self.scroll_lines)
            if dpad == 0:  # D-Pad Up -> Scroll Up
                self._inject_scroll(scroll_unit)
                self._haptic("scroll")
            elif dpad == 4:  # D-Pad Down -> Scroll Down
                self._inject_scroll(-scroll_unit)
                self._haptic("scroll")

        # -------------------------------------------------------------
        # 2. Physical Touchpad Button Press (MacBook Force Touch Click)
        # -------------------------------------------------------------
        if pad_clicked and not self.last_pad_click:
            # Determine click type based on finger count and horizontal/vertical zone
            if touch1_active and touch2_active:
                click_type = "right"
                haptic_type = "down_right"
            elif touch1_active:
                # Top center zone (Middle click): 700 <= x <= 1220 and y < 380
                if 700 <= x1 <= 1220 and y1 < 380:
                    click_type = "middle"
                    haptic_type = "down_middle"
                # Right zone (Right click): x >= 1200
                elif x1 >= 1200:
                    click_type = "right"
                    haptic_type = "down_right"
                else:
                    click_type = "left"
                    haptic_type = "down_left"
            else:
                click_type = "left"
                haptic_type = "down_left"

            self.active_pad_click_type = click_type
            self._inject_click(click_type, True)
            self._haptic(haptic_type)

        elif not pad_clicked and self.last_pad_click:
            if self.active_pad_click_type:
                self._inject_click(self.active_pad_click_type, False)
                self.active_pad_click_type = None
            self._haptic("up")
        self.last_pad_click = pad_clicked

        # -------------------------------------------------------------
        # 3. Two-Finger Gestures (Vertical Scroll & Two-Finger Tap Right Click)
        # -------------------------------------------------------------
        if touch1_active and touch2_active:
            avg_x = (x1 + x2) // 2
            avg_y = (y1 + y2) // 2
            if not self.two_finger_active:
                self.two_finger_active = True
                self.two_finger_start_time = now
                self.two_finger_travel_dist = 0.0
                self.last_two_y = avg_y
                self.last_two_x = avg_x
            else:
                dy = avg_y - self.last_two_y
                if abs(dy) > 2:
                    self.two_finger_travel_dist += abs(dy)
                    scroll_delta = int(-dy * self.scroll_sensitivity * (self.scroll_lines / 3.0) * 5)
                    self._inject_scroll(scroll_delta)
                    self.scroll_accum += abs(scroll_delta)
                    if self.scroll_accum >= 90:
                        self.scroll_accum = 0.0
                        self._haptic("scroll")
                self.last_two_y = avg_y
                self.last_two_x = avg_x
            return

        elif self.two_finger_active:
            # Two fingers lifted: check if it was a quick tap (< 280ms) without scroll movement
            duration = now - self.two_finger_start_time
            if duration < 0.28 and self.two_finger_travel_dist < 18.0:
                # Two-Finger Tap -> Right Click!
                self._inject_click("right", True)
                time.sleep(0.01)
                self._inject_click("right", False)
                self._haptic("down_right")
            self.two_finger_active = False
            self.last_x = None
            self.last_y = None

        # -------------------------------------------------------------
        # 4. Single-Finger Cursor Tracking & Tap-to-Click
        # -------------------------------------------------------------
        if touch1_active:
            if not self.is_touching:
                # Touch down event
                self.is_touching = True
                self.touch_start_time = now
                self.touch_travel_dist = 0.0
                self.last_x = x1
                self.last_y = y1
                return

            if self.last_x is not None and self.last_y is not None:
                dx = x1 - self.last_x
                dy = y1 - self.last_y

                dist = math.hypot(dx, dy)
                self.touch_travel_dist += dist

                if dist > 1.0:
                    # Apply ballistic acceleration curve
                    speed_factor = (dist ** (self.acceleration - 1.0)) if dist > 0 else 1.0
                    move_x = int(dx * self.sensitivity * speed_factor)
                    move_y = int(dy * self.sensitivity * speed_factor)

                    if move_x != 0 or move_y != 0:
                        self._inject_move(move_x, move_y)

            self.last_x = x1
            self.last_y = y1
            self.last_touch_time = now

        else:
            if self.is_touching:
                # Touch released - check if it was a quick tap (tap-to-click)
                duration = now - self.touch_start_time
                if duration < 0.25 and self.touch_travel_dist < 15.0:
                    # Tap to left click
                    self._inject_click("left", True)
                    time.sleep(0.01)
                    self._inject_click("left", False)
                    self._haptic("tap")

                self.reset()

    def process_gyro(self, gyro_x: int, gyro_y: int, gyro_z: int, l2: int, r2: int):
        """
        Processes 6-axis gyroscope motion for Air Mouse cursor navigation,
        and manages firearm hair-trigger breaks for L2 (Right Click) and R2 (Left Click).
        """
        if not self.air_mouse_enabled:
            return

        # -------------------------------------------------------------
        # 1. Firearm Trigger Break & Recoil Kick Handling
        # -------------------------------------------------------------
        # R2: Gun Primary Trigger -> Left Click
        if r2 >= self.trigger_break_threshold and not self.r2_clicked:
            self.r2_clicked = True
            self._inject_click("left", True)
            self._haptic("gun_recoil_right")
        elif r2 <= self.trigger_release_threshold and self.r2_clicked:
            self.r2_clicked = False
            self._inject_click("left", False)
            self._haptic("gun_reset")

        # L2: Gun Aim / Secondary Trigger -> Right Click
        if l2 >= self.trigger_break_threshold and not self.l2_clicked:
            self.l2_clicked = True
            self._inject_click("right", True)
            self._haptic("gun_recoil_left")
        elif l2 <= self.trigger_release_threshold and self.l2_clicked:
            self.l2_clicked = False
            self._inject_click("right", False)
            self._haptic("gun_reset")

        # -------------------------------------------------------------
        # 2. Gyroscope Motion Cursor Steering
        # -------------------------------------------------------------
        # DualSense natural hand orientation:
        # Yaw (turning left/right horizontally) is gyro_z. Right turn -> +gyro_z -> move cursor right (+dx).
        # Pitch (tilting up/down) is gyro_x. Tilting nose down -> +gyro_x -> move cursor down (+dy).
        raw_yaw = float(gyro_z)
        raw_pitch = float(gyro_x if not self.invert_pitch else -gyro_x)

        # Apply deadzone filtering to eliminate sensor noise and resting drift
        if abs(raw_yaw) < self.gyro_deadzone:
            eff_yaw = 0.0
        else:
            eff_yaw = math.copysign(abs(raw_yaw) - self.gyro_deadzone, raw_yaw)

        if abs(raw_pitch) < self.gyro_deadzone:
            eff_pitch = 0.0
        else:
            eff_pitch = math.copysign(abs(raw_pitch) - self.gyro_deadzone, raw_pitch)

        # Convert to mouse velocity (typical gyro values are up to ±2000 dps ~ ±32000 counts)
        scale = 0.005 * self.gyro_sensitivity
        target_dx = eff_yaw * scale
        target_dy = eff_pitch * scale

        # Exponential Moving Average (EMA) low-pass filter (alpha=0.6) for jitter-free tracking
        alpha = 0.6
        smooth_dx = alpha * target_dx + (1.0 - alpha) * self._last_gyro_dx
        smooth_dy = alpha * target_dy + (1.0 - alpha) * self._last_gyro_dy
        self._last_gyro_dx = smooth_dx
        self._last_gyro_dy = smooth_dy

        move_x = int(round(smooth_dx))
        move_y = int(round(smooth_dy))

        if move_x != 0 or move_y != 0:
            self._inject_move(move_x, move_y)

    def _inject_move(self, dx: int, dy: int):
        if IS_WINDOWS:
            _win_send_mouse(MOUSEEVENTF_MOVE, dx, dy)
        elif IS_MAC:
            # macOS CoreGraphics injection via ctypes
            try:
                import Quartz
                loc = Quartz.NSEvent.mouseLocation()
                new_x = loc.x + dx
                new_y = Quartz.CGDisplayPixelsHigh(0) - loc.y + dy
                ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (new_x, new_y), 0)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            except Exception:
                pass

    def _inject_click(self, button, down: bool):
        # Support both boolean (left=True/False) and string ("left", "right", "middle")
        if isinstance(button, bool):
            btn = "left" if button else "right"
        else:
            btn = str(button).lower()

        if IS_WINDOWS:
            if btn == "left":
                flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
            elif btn == "right":
                flag = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
            elif btn == "middle":
                flag = MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP
            else:
                flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
            _win_send_mouse(flag)
        elif IS_MAC:
            try:
                import Quartz
                loc = Quartz.NSEvent.mouseLocation()
                pt = (loc.x, Quartz.CGDisplayPixelsHigh(0) - loc.y)
                if btn == "left":
                    ev_type = Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp
                    cg_btn = Quartz.kCGMouseButtonLeft
                elif btn == "right":
                    ev_type = Quartz.kCGEventRightMouseDown if down else Quartz.kCGEventRightMouseUp
                    cg_btn = Quartz.kCGMouseButtonRight
                elif btn == "middle":
                    ev_type = Quartz.kCGEventOtherMouseDown if down else Quartz.kCGEventOtherMouseUp
                    cg_btn = Quartz.kCGMouseButtonCenter
                else:
                    ev_type = Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp
                    cg_btn = Quartz.kCGMouseButtonLeft
                ev = Quartz.CGEventCreateMouseEvent(None, ev_type, pt, cg_btn)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            except Exception:
                pass

    def _inject_scroll(self, delta: int):
        if IS_WINDOWS:
            _win_send_mouse(MOUSEEVENTF_WHEEL, data=delta)
        elif IS_MAC:
            try:
                import Quartz
                ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, delta)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            except Exception:
                pass
