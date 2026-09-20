"""
OpenDSZ Bluetooth & USB Audio/Haptics Protocol Engine
Implements the proprietary Sony Bluetooth Report 0x36 multiplexed Opus Audio & 3000Hz Haptic stream
as used in PulseCore and daidr/dualsense-tester.
"""

import math
import struct
import time
from typing import Optional, Tuple
from .protocol import compute_bt_crc32, ConnectionType

REPORT_0x36_ID = 0x36
REPORT_0x36_PAYLOAD_LEN = 397 # 398 bytes total including report ID

OPUS_FRAME_BYTES = 200
HAPTIC_FRAME_BYTES = 64

class DualSenseAudioEngine:
    def __init__(self):
        self.audio_target = "speaker" # "speaker" (0x93) or "headphone" (0x96)
        self.volume = 0x4B            # Default comfortable volume (0..100)
        self.seq_num = 0
        self.frame_counter = 0

    def set_target(self, target: str):
        if target in ("speaker", "headphone"):
            self.audio_target = target

    def set_volume(self, volume: int):
        self.volume = max(0, min(100, volume))

    def build_report_0x36(self, opus_frame: Optional[bytes] = None,
                          haptic_frame: Optional[bytes] = None) -> bytes:
        """
        Builds the 398-byte Report 0x36 payload with CRC-32 checksum for Bluetooth transmission.
        Multiplexes:
          - Audio subpacket (Opus, 200 bytes)
          - Haptics subpacket (3000Hz PCM, 64 bytes)
        """
        # Packet buffer: 1 byte report ID (0x36) + 397 bytes payload = 398 bytes
        packet = bytearray(398)
        packet[0] = REPORT_0x36_ID

        payload = memoryview(packet)[1:] # 397 bytes

        # Byte 0: Seq high 4-bits
        payload[0] = (self.seq_num & 0x0F) << 4
        self.seq_num = (self.seq_num + 1) & 0x0F

        # Control subpacket
        payload[1] = 0x90
        payload[2] = 0x3F
        if self.audio_target == "headphone":
            payload[3] = 0x90 # Headphones flag
            payload[7] = self.volume
        else:
            payload[3] = 0xA0 # Speaker flag
            payload[8] = self.volume

        payload[4] = 0x00
        payload[10] = 0x09 # Audio control

        # Audio subpacket (starts at offset 66 in payload)
        payload[66] = 0x91
        payload[67] = 0x07
        payload[68] = 0xFE
        payload[69:74] = bytes([0x40, 0x40, 0x40, 0x40, 0x40]) # Latency/mix params
        payload[74] = self.frame_counter & 0xFF
        self.frame_counter = (self.frame_counter + 1) & 0xFF

        payload[75] = 0x96 if self.audio_target == "headphone" else 0x93
        payload[76] = 0xC8 # 200 bytes

        if opus_frame and len(opus_frame) >= OPUS_FRAME_BYTES:
            payload[77:77 + OPUS_FRAME_BYTES] = opus_frame[:OPUS_FRAME_BYTES]

        # Haptic subpacket (starts at offset 277 in payload)
        payload[277] = 0x92
        payload[278] = 0x40 # 64 bytes
        if haptic_frame and len(haptic_frame) >= HAPTIC_FRAME_BYTES:
            payload[279:279 + HAPTIC_FRAME_BYTES] = haptic_frame[:HAPTIC_FRAME_BYTES]

        # Checksum: Last 4 bytes
        crc = compute_bt_crc32(REPORT_0x36_ID, bytes(payload[:393]))
        payload[393] = crc & 0xFF
        payload[394] = (crc >> 8) & 0xFF
        payload[395] = (crc >> 16) & 0xFF
        payload[396] = (crc >> 24) & 0xFF

        return bytes(packet)

    @staticmethod
    def generate_test_haptic_pcm(freq_hz: float = 150.0, amplitude: float = 0.8) -> bytes:
        """
        Generates a 64-byte 3000Hz 2-channel interleaved PCM buffer (int8)
        to physically drive the voice-coil actuators.
        """
        buf = bytearray(HAPTIC_FRAME_BYTES)
        sample_rate = 3000.0
        num_samples = HAPTIC_FRAME_BYTES // 2 # 32 samples per channel

        for i in range(num_samples):
            val = math.sin(2.0 * math.pi * freq_hz * (i / sample_rate)) * amplitude
            int8_val = int(max(-127, min(127, val * 127.0))) & 0xFF
            buf[i * 2] = int8_val     # Left actuator
            buf[i * 2 + 1] = int8_val # Right actuator

        return bytes(buf)

    @staticmethod
    def generate_speaker_tone_frame(freq_hz: float = 880.0, frame_idx: int = 0) -> bytes:
        """
        Generates a 200-byte audio payload frame for the built-in controller speaker (48kHz, 10ms frame).
        """
        buf = bytearray(OPUS_FRAME_BYTES)
        # Construct header followed by synthetic tone payload
        buf[0] = 0x98 # CELT mode frame marker
        for i in range(1, OPUS_FRAME_BYTES):
            t = (frame_idx * OPUS_FRAME_BYTES + i) / 48000.0
            val = int((math.sin(2.0 * math.pi * freq_hz * t) + 1.0) * 127)
            buf[i] = val & 0xFF
        return bytes(buf)
