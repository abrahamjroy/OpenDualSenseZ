"""
OpenDSX DualSense HID Protocol Implementation
Supports USB (Report 0x02) and Bluetooth (Report 0x31 with IEEE 802.3 CRC-32)
"""

from enum import IntEnum
from typing import List, Optional, Any
import math
import struct

# Sony DualSense Vendor and Product IDs
DUALSENSE_VID = 0x054C
DUALSENSE_PID = 0x0CE6
DUALSENSE_EDGE_PID = 0x0DF2

class TriggerMode(IntEnum):
    OFF = 0x05            # Hardware disable trigger effect
    RIGID = 0x21          # Continuous resistance (Feedback mode)
    FEEDBACK = 0x21       # Continuous resistance across zones
    BOW = 0x22            # Bow tension effect
    GALLOP = 0x23         # Galloping vibration effect
    TRIGGER_STOP = 0x25   # Hard stop / resistance wall (Weapon mode)
    WEAPON = 0x25         # Hard stop / weapon effect
    PULSE = 0x26          # Automatic pulse / frequency vibration
    VIBRATION = 0x26      # Variable frequency and amplitude vibration
    MACHINE_GUN = 0x27    # Rapid machine gun cycle
    CHOPPY = 0x26         # Choppy vibration (alias for VIBRATION)

    @classmethod
    def _missing_(cls, value):
        legacy = {
            0: cls.OFF,
            1: cls.RIGID,
            2: cls.TRIGGER_STOP,
            3: cls.BOW,
            4: cls.FEEDBACK,
            6: cls.PULSE,
            7: cls.CHOPPY,
            0x00: cls.OFF,
            0x01: cls.RIGID,
            0x02: cls.TRIGGER_STOP,
            0x03: cls.BOW,
            0x04: cls.FEEDBACK,
            0x06: cls.PULSE,
        }
        if value in legacy:
            return legacy[value]
        return cls.OFF

def encode_trigger(mode, params: List[int]):
    """
    Translates high-level or legacy trigger configurations into the exact
    11-byte [mode_opcode, param0..param9] hardware structure expected by DualSense MCU firmware.
    """
    p = list(params) if params else [0] * 10

    # Normalization of input mode (support string, int, enum, legacy DSX values)
    if isinstance(mode, str):
        m_str = mode.strip().upper()
        if "OFF" in m_str:
            return 0x05, [0] * 10
        elif "RIGID" in m_str or "FEEDBACK" in m_str or "RESIST" in m_str:
            mode = 0x21
        elif "STOP" in m_str or "WEAPON" in m_str:
            mode = 0x25
        elif "BOW" in m_str:
            mode = 0x22
        elif "GALLOP" in m_str:
            mode = 0x23
        elif "MACHINE" in m_str or "TRACTION" in m_str:
            mode = 0x27
        elif "PULSE" in m_str or "VIBRAT" in m_str or "ABS" in m_str:
            mode = 0x26
        else:
            return 0x05, [0] * 10
    else:
        try:
            mode = int(mode)
        except Exception:
            return 0x05, [0] * 10

    # Remap legacy DSX UDP mode codes (0=Off, 1=Rigid, 2=Stop, 6=Pulse)
    if mode == 0 or mode == 0x05:
        return 0x05, [0] * 10
    elif mode == 1:
        mode = 0x21
    elif mode == 2:
        mode = 0x25
    elif mode == 6:
        mode = 0x26

    # 1. FEEDBACK / RIGID RESISTANCE (0x21)
    if mode == 0x21:
        start_pos = max(0, min(9, p[0] if len(p) > 0 else 0))
        force_val = p[1] if len(p) > 1 else 200
        # Map 0..255 force to 1..8 DualSense strength
        strength_val = max(1, min(8, int(math.ceil(force_val / 32.0)))) if force_val > 8 else max(1, min(8, force_val))
        
        strength_zones = 0
        active_zones = 0
        for i in range(start_pos, 10):
            val = (strength_val - 1) & 0x07
            strength_zones |= (val << (3 * i))
            active_zones |= (1 << i)

        return 0x21, [
            active_zones & 0xFF,
            (active_zones >> 8) & 0xFF,
            strength_zones & 0xFF,
            (strength_zones >> 8) & 0xFF,
            (strength_zones >> 16) & 0xFF,
            (strength_zones >> 24) & 0xFF,
            0, 0, 0, 0
        ]

    # 2. WEAPON / TRIGGER STOP (0x25)
    elif mode == 0x25:
        start_pos = max(0, min(7, p[0] if len(p) > 0 else 2))
        end_pos = max(start_pos + 1, min(8, p[1] if len(p) > 1 else 8))
        force_val = p[2] if len(p) > 2 else 255
        strength_val = max(1, min(8, int(math.ceil(force_val / 32.0)))) if force_val > 8 else max(1, min(8, force_val))
        
        start_stop_zones = (1 << start_pos) | (1 << end_pos)
        return 0x25, [
            start_stop_zones & 0xFF,
            (start_stop_zones >> 8) & 0xFF,
            (strength_val - 1) & 0x07,
            0, 0, 0, 0, 0, 0, 0
        ]

    # 3. BOW TENSION (0x22)
    elif mode == 0x22:
        start_pos = max(0, min(7, p[0] if len(p) > 0 else 1))
        end_pos = max(start_pos + 1, min(8, p[1] if len(p) > 1 else 8))
        f_val = p[2] if len(p) > 2 else 6
        snap_val = p[3] if len(p) > 3 else 8
        s1 = max(1, min(8, int(math.ceil(f_val / 32.0)))) if f_val > 8 else max(1, min(8, f_val))
        s2 = max(1, min(8, int(math.ceil(snap_val / 32.0)))) if snap_val > 8 else max(1, min(8, snap_val))
        
        start_stop_zones = (1 << start_pos) | (1 << end_pos)
        force_pair = ((s1 - 1) & 0x07) | (((s2 - 1) & 0x07) << 3)
        return 0x22, [
            start_stop_zones & 0xFF,
            (start_stop_zones >> 8) & 0xFF,
            force_pair & 0xFF,
            0, 0, 0, 0, 0, 0, 0
        ]

    # 4. GALLOPING (0x23)
    elif mode == 0x23:
        if len(p) >= 5:
            start_pos = max(0, min(8, p[0]))
            end_pos = max(start_pos + 1, min(9, p[1]))
            first = max(0, min(6, p[2]))
            second = max(first + 1, min(7, p[3]))
            freq = max(1, min(255, p[4]))
        else:
            freq = max(1, min(255, p[0] if len(p) > 0 else 10))
            start_pos = max(0, min(7, p[2] if len(p) > 2 else 2))
            end_pos = 9
            first = 2
            second = 6

        start_stop_zones = (1 << start_pos) | (1 << end_pos)
        ratio = (second & 0x07) | ((first & 0x07) << 3)
        return 0x23, [
            start_stop_zones & 0xFF,
            (start_stop_zones >> 8) & 0xFF,
            ratio & 0xFF,
            freq & 0xFF,
            0, 0, 0, 0, 0, 0
        ]

    # 5. MACHINE GUN (0x27)
    elif mode == 0x27:
        if len(p) >= 6:
            start_pos = max(1, min(8, p[0]))
            end_pos = max(start_pos + 1, min(9, p[1]))
            sa = max(0, min(7, p[2]))
            sb = max(0, min(7, p[3]))
            freq = max(1, min(255, p[4]))
            period = max(1, min(255, p[5]))
        else:
            freq = max(1, min(255, p[0] if len(p) > 0 else 12))
            force_val = p[1] if len(p) > 1 else 220
            start_pos = max(1, min(7, p[2] if len(p) > 2 else 2))
            end_pos = 9
            sa = max(1, min(7, int(force_val / 36.0) if force_val > 7 else force_val))
            sb = max(0, sa - 2)
            period = 10

        start_stop_zones = (1 << start_pos) | (1 << end_pos)
        force_pair = (sa & 0x07) | ((sb & 0x07) << 3)
        return 0x27, [
            start_stop_zones & 0xFF,
            (start_stop_zones >> 8) & 0xFF,
            force_pair & 0xFF,
            freq & 0xFF,
            period & 0xFF,
            0, 0, 0, 0, 0
        ]

    # 6. VIBRATION / PULSE (0x26)
    elif mode == 0x26:
        # Check parameter signature: [freq, force, start_pos] vs [pos, amp, freq]
        if len(p) >= 3 and p[0] <= 9 and p[1] > 10:
            pos = max(0, min(9, p[0]))
            amp_val = p[1]
            freq_val = p[2]
        elif len(p) >= 3:
            freq_val = p[0]
            amp_val = p[1]
            pos = max(0, min(9, p[2]))
        else:
            freq_val = p[0] if len(p) > 0 else 12
            amp_val = p[1] if len(p) > 1 else 200
            pos = 2

        strength_val = max(1, min(8, int(math.ceil(amp_val / 32.0)))) if amp_val > 8 else max(1, min(8, amp_val))
        freq = max(1, min(255, freq_val))

        strength_zones = 0
        active_zones = 0
        for i in range(pos, 10):
            val = (strength_val - 1) & 0x07
            strength_zones |= (val << (3 * i))
            active_zones |= (1 << i)

        return 0x26, [
            active_zones & 0xFF,
            (active_zones >> 8) & 0xFF,
            strength_zones & 0xFF,
            (strength_zones >> 8) & 0xFF,
            (strength_zones >> 16) & 0xFF,
            (strength_zones >> 24) & 0xFF,
            0, 0,
            freq & 0xFF,
            0
        ]

    return 0x05, [0] * 10


class ConnectionType(IntEnum):
    UNKNOWN = 0
    USB = 1
    BLUETOOTH = 2

# Pre-computed CRC32 lookup table for DualSense Bluetooth packets
def _generate_crc32_table():
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            if c & 1:
                c = 0xEDB88320 ^ (c >> 1)
            else:
                c = c >> 1
        table.append(c)
    return table

_CRC32_TABLE = _generate_crc32_table()

def compute_bt_crc32(report_id: int, payload: bytes) -> int:
    """Computes IEEE 802.3 CRC-32 with the 0xA2 Bluetooth HID header prepended."""
    crc = 0xFFFFFFFF
    for b in (0xA2, report_id):
        crc = (crc >> 8) ^ _CRC32_TABLE[(crc ^ b) & 0xFF]
    for b in payload:
        crc = (crc >> 8) ^ _CRC32_TABLE[(crc ^ b) & 0xFF]
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF


class DualSenseOutputReport:
    """
    Constructs the 47-byte output configuration payload
    and encapsulates it for USB (Report 0x02) or Bluetooth (Report 0x31).
    """
    def __init__(self):
        # Flags (Must be set to 0xFF to enable trigger motors, rumble, and haptics)
        self.valid_flag0 = 0xFF  # Enables rumble, triggers, and audio volumes
        self.valid_flag1 = 0xF7  # Enables LEDs, power save, and lightbar
        self.valid_flag2 = 0x02  # DS_OUTPUT_VALID_FLAG2_LIGHTBAR_SETUP_CONTROL_ENABLE (0x02)

        # Vibration (Classic rumble fallback)
        self.rumble_right = 0
        self.rumble_left = 0

        # Audio
        self.headphone_volume = 0
        self.speaker_volume = 0
        self.mic_volume = 0
        self.audio_control = 0
        self.mute_led = 0
        self.power_save = 0

        # Right Trigger (10 bytes params)
        self.right_trigger_mode = TriggerMode.OFF
        self.right_trigger_params: List[int] = [0] * 10

        # Left Trigger (10 bytes params)
        self.left_trigger_mode = TriggerMode.OFF
        self.left_trigger_params: List[int] = [0] * 10

        # Lightbar & Player LEDs
        self.lightbar_setup = 0x01  # DS_OUTPUT_LIGHTBAR_SETUP_LIGHT_ON (0x01)
        self.led_brightness = 0x00  # 0=High, 1=Med, 2=Low
        self.player_leds = 0x04     # Player 1 default (0x04)
        self.led_r = 0
        self.led_g = 0
        self.led_b = 0

        self.seq_num = 0

    def set_left_trigger(self, mode: Any, params: List[int]):
        m, p = encode_trigger(mode, params)
        self.left_trigger_mode = m
        self.left_trigger_params = p

    def set_right_trigger(self, mode: Any, params: List[int]):
        m, p = encode_trigger(mode, params)
        self.right_trigger_mode = m
        self.right_trigger_params = p

    def set_led_color(self, r: int, g: int, b: int):
        self.led_r = max(0, min(255, r))
        self.led_g = max(0, min(255, g))
        self.led_b = max(0, min(255, b))

    def build_raw_payload(self) -> bytearray:
        """Constructs the standard 47-byte DualSense control block."""
        data = bytearray(47)
        data[0] = self.valid_flag0
        data[1] = self.valid_flag1
        data[2] = self.rumble_right
        data[3] = self.rumble_left
        data[4] = self.headphone_volume
        data[5] = self.speaker_volume
        data[6] = self.mic_volume
        data[7] = self.audio_control
        data[8] = self.mute_led
        data[9] = self.power_save

        # Right trigger (bytes 10..20)
        data[10] = int(self.right_trigger_mode)
        for i in range(10):
            data[11 + i] = self.right_trigger_params[i]

        # Left trigger (bytes 21..31)
        data[21] = int(self.left_trigger_mode)
        for i in range(10):
            data[22 + i] = self.left_trigger_params[i]

        # Audio control 2 & flags
        data[37] = 0x00
        data[38] = self.valid_flag2
        data[41] = self.lightbar_setup
        data[42] = self.led_brightness
        data[43] = self.player_leds
        data[44] = self.led_r
        data[45] = self.led_g
        data[46] = self.led_b

        return data

    def build_packet(self, connection_type: ConnectionType) -> bytes:
        """Returns the complete HID report ready for hid_write."""
        raw = self.build_raw_payload()

        if connection_type == ConnectionType.USB:
            # Report ID 0x02, 63 bytes payload (total 64 with report ID)
            packet = bytearray(64)
            packet[0] = 0x02
            packet[1:1 + len(raw)] = raw
            return bytes(packet)

        elif connection_type == ConnectionType.BLUETOOTH:
            # Report ID 0x31, 77 bytes payload + 1 report ID = 78 bytes total
            packet = bytearray(78)
            packet[0] = 0x31
            packet[1] = (self.seq_num & 0x0F) << 4
            packet[2] = 0x10  # Mode switch tag
            packet[3:3 + len(raw)] = raw
            self.seq_num = (self.seq_num + 1) & 0x0F

            # Compute CRC32 on bytes 1..73 with 0xA2 + 0x31 prepended
            crc = compute_bt_crc32(0x31, bytes(packet[1:74]))
            packet[74] = crc & 0xFF
            packet[75] = (crc >> 8) & 0xFF
            packet[76] = (crc >> 16) & 0xFF
            packet[77] = (crc >> 24) & 0xFF
            return bytes(packet)

        return bytes()


class DualSenseInputReport:
    """Parses incoming USB (0x01) or Bluetooth (0x31) DualSense HID input reports."""
    def __init__(self):
        # Sticks (0..255, 128 is center)
        self.lx = 128
        self.ly = 128
        self.rx = 128
        self.ry = 128

        # Triggers (0..255)
        self.l2 = 0
        self.r2 = 0

        # Buttons
        self.dpad = 8  # 8 is neutral
        self.square = False
        self.cross = False
        self.circle = False
        self.triangle = False
        self.l1 = False
        self.r1 = False
        self.l2_btn = False
        self.r2_btn = False
        self.create = False
        self.options = False
        self.l3 = False
        self.r3 = False
        self.ps = False
        self.touchpad_click = False
        self.mute = False

        # Touchpad Coordinates
        self.touch1_active = False
        self.touch1_id = 0
        self.touch1_x = 0
        self.touch1_y = 0

        self.touch2_active = False
        self.touch2_id = 0
        self.touch2_x = 0
        self.touch2_y = 0

        # Battery
        self.battery_level = 0
        self.is_charging = False

        # IMU / Motion Sensors (Gyroscope & Accelerometer)
        self.gyro_x = 0  # Pitch rate (signed 16-bit)
        self.gyro_y = 0  # Yaw rate (signed 16-bit)
        self.gyro_z = 0  # Roll rate (signed 16-bit)
        self.accel_x = 0 # Lateral acceleration X (signed 16-bit)
        self.accel_y = 0 # Vertical acceleration Y (signed 16-bit)
        self.accel_z = 0 # Forward acceleration Z (signed 16-bit)
        self.sensor_timestamp = 0

        # Audio Status (Byte 53)
        self.headphones_connected = False
        self.mic_muted_hw = False

    def parse(self, data: bytes, is_bluetooth: bool = False):
        if not data:
            return

        offset = 0
        if data[0] in (0x01, 0x31):
            offset = 1 if not is_bluetooth else 2

        if len(data) < offset + 10:
            return

        # Sticks
        self.lx = data[offset + 0]
        self.ly = data[offset + 1]
        self.rx = data[offset + 2]
        self.ry = data[offset + 3]
        self.l2 = data[offset + 4]
        self.r2 = data[offset + 5]

        # Buttons
        b1 = data[offset + 7]
        self.dpad = b1 & 0x0F
        self.square = bool(b1 & (1 << 4))
        self.cross = bool(b1 & (1 << 5))
        self.circle = bool(b1 & (1 << 6))
        self.triangle = bool(b1 & (1 << 7))

        b2 = data[offset + 8]
        self.l1 = bool(b2 & (1 << 0))
        self.r1 = bool(b2 & (1 << 1))
        self.l2_btn = bool(b2 & (1 << 2))
        self.r2_btn = bool(b2 & (1 << 3))
        self.create = bool(b2 & (1 << 4))
        self.options = bool(b2 & (1 << 5))
        self.l3 = bool(b2 & (1 << 6))
        self.r3 = bool(b2 & (1 << 7))

        b3 = data[offset + 9]
        self.ps = bool(b3 & (1 << 0))
        self.touchpad_click = bool(b3 & (1 << 1))
        self.mute = bool(b3 & (1 << 2))

        # IMU Motion Sensors (Gyroscope at offset + 15, Accelerometer at offset + 21)
        if len(data) >= offset + 27:
            self.gyro_x, self.gyro_y, self.gyro_z = struct.unpack_from('<3h', data, offset + 15)
            self.accel_x, self.accel_y, self.accel_z = struct.unpack_from('<3h', data, offset + 21)
        if len(data) >= offset + 31:
            self.sensor_timestamp = struct.unpack_from('<I', data, offset + 27)[0]

        # Touchpad (Offset ~32 on USB, ~33 on BT)
        touch_offset = offset + 32
        if len(data) >= touch_offset + 8:
            t0 = data[touch_offset]
            t1 = data[touch_offset + 1]
            t2 = data[touch_offset + 2]
            t3 = data[touch_offset + 3]

            self.touch1_active = (t0 & 0x80) == 0
            self.touch1_id = t0 & 0x7F
            self.touch1_x = ((t2 & 0x0F) << 8) | t1
            self.touch1_y = (t3 << 4) | ((t2 & 0xF0) >> 4)

            t4 = data[touch_offset + 4]
            t5 = data[touch_offset + 5]
            t6 = data[touch_offset + 6]
            t7 = data[touch_offset + 7]

            self.touch2_active = (t4 & 0x80) == 0
            self.touch2_id = t4 & 0x7F
            self.touch2_x = ((t6 & 0x0F) << 8) | t5
            self.touch2_y = (t7 << 4) | ((t6 & 0xF0) >> 4)

        # Battery (Offset ~52)
        batt_offset = offset + 52
        if len(data) > batt_offset:
            b_info = data[batt_offset]
            self.battery_level = min(100, (b_info & 0x0F) * 10)
            self.is_charging = bool((b_info & 0xF0) == 0x10)

        # Audio Status (Offset ~53: bit 0 = headphone jack, bit 1 = mic status)
        audio_offset = offset + 53
        if len(data) > audio_offset:
            a_info = data[audio_offset]
            self.headphones_connected = bool(a_info & 0x01)
            self.mic_muted_hw = bool(a_info & 0x02)
