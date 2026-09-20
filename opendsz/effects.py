"""
OpenDSZ Dynamic RGB Lightbar Effects Engine
Provides 13 hardware-accelerated animations:
Breathing, Rainbow, Police, Neon Sunset, Battery, Fire, Cyberpunk 2077,
Aurora Borealis, RPM Shift Light (Forza), Hyperdrive, Matrix Rain, and Ocean Waves.
"""

import time
import math
import colorsys
import threading
from enum import Enum
from typing import Optional, Callable, Tuple

class LightEffect(str, Enum):
    STATIC = "Static Color"
    BREATHING = "Breathing"
    RAINBOW = "Rainbow Cycle"
    POLICE = "Police Flashers"
    NEON_SUNSET = "Neon Sunset (Synthwave)"
    BATTERY = "Battery Indicator"
    FIRE = "Fire & Flame"
    CYBERPUNK = "Cyberpunk 2077 Neon"
    AURORA = "Aurora Borealis"
    RPM_SHIFT = "RPM Shift Light (Ferrari & Forza)"
    SUPERNOVA = "Supernova (Cosmic Burst)"
    QUANTUM_FLUX = "Quantum Flux (Chroma Comet)"
    VAPORWAVE = "Vaporwave Dreams (80s Pastel)"
    HEARTBEAT = "Heartbeat Monitor (ECG Vital)"
    GOLDEN_AURA = "Super Saiyan (Golden Aura)"
    HYPERDRIVE = "Hyperdrive Warp"
    MATRIX = "Matrix Code Rain"
    OCEAN = "Ocean Waves"

class LightbarEffectsEngine:
    def __init__(self):
        self.current_effect = LightEffect.STATIC
        self.base_color: Tuple[int, int, int] = (0, 120, 255) # Default Cyan-Blue
        self.speed = 1.0 # Multiplier
        self.battery_level = 100
        self.is_charging = False
        self.rpm_ratio = 0.0 # 0.0 to 1.0 from Forza telemetry
        self.shift_flash_time = 0.0

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Callback invoked with (r, g, b)
        self.on_color_update: Optional[Callable[[int, int, int], None]] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Lightbar-Effects")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def set_effect(self, effect: LightEffect):
        with self._lock:
            self.current_effect = effect

    def set_base_color(self, r: int, g: int, b: int):
        with self._lock:
            self.base_color = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))

    def set_battery_state(self, level: int, charging: bool):
        with self._lock:
            self.battery_level = level
            self.is_charging = charging

    def set_rpm_ratio(self, ratio: float):
        with self._lock:
            self.rpm_ratio = max(0.0, min(1.0, ratio))

    def trigger_shift_flash(self):
        """Triggers a 160ms brilliant electric white tachometer shift confirmation flash."""
        with self._lock:
            self.shift_flash_time = time.perf_counter()

    def _loop(self):
        interval = 1.0 / 30.0 # 30 FPS smooth rendering
        start_time = time.perf_counter()

        while self._running:
            t = (time.perf_counter() - start_time) * self.speed
            with self._lock:
                eff = self.current_effect
                base_r, base_g, base_b = self.base_color
                batt = self.battery_level
                charging = self.is_charging
                rpm = self.rpm_ratio
                shift_flash = self.shift_flash_time

            r, g, b = 0, 0, 0
            shift_age = time.perf_counter() - shift_flash

            # Universal Gear Shift Confirmation Flash: Ferrari Giallo Modena Gold Burst
            if shift_age < 0.22:
                flash_prog = max(0.0, 1.0 - (shift_age / 0.22))
                r = 255
                g = int(215 * (0.65 + 0.35 * flash_prog))
                b = int(15 * (1.0 - flash_prog))

            # 1. Static
            elif eff == LightEffect.STATIC:
                r, g, b = base_r, base_g, base_b

            # 2. Breathing
            elif eff == LightEffect.BREATHING:
                factor = 0.55 + 0.45 * math.sin(t * 2.5)
                r = int(base_r * factor)
                g = int(base_g * factor)
                b = int(base_b * factor)

            # 3. Rainbow Cycle
            elif eff == LightEffect.RAINBOW:
                hue = (t * 0.2) % 1.0
                rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                r, g, b = int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)

            # 4. Police Flashers
            elif eff == LightEffect.POLICE:
                phase = int(t * 8) % 4
                if phase in (0, 1):
                    r, g, b = (255, 0, 0) if (int(t * 16) % 2 == 0) else (30, 0, 0)
                else:
                    r, g, b = (0, 40, 255) if (int(t * 16) % 2 == 0) else (0, 5, 30)

            # 5. Neon Sunset (Synthwave)
            elif eff == LightEffect.NEON_SUNSET:
                cycle = (math.sin(t * 1.5) + 1.0) / 2.0
                if cycle < 0.5:
                    sub_t = cycle * 2.0
                    r = int(255 * (1 - sub_t) + 140 * sub_t)
                    g = 0
                    b = int(128 * (1 - sub_t) + 255 * sub_t)
                else:
                    sub_t = (cycle - 0.5) * 2.0
                    r = int(140 * (1 - sub_t) + 255 * sub_t)
                    g = int(0 * (1 - sub_t) + 90 * sub_t)
                    b = int(255 * (1 - sub_t) + 0 * sub_t)

            # 6. Battery Indicator
            elif eff == LightEffect.BATTERY:
                if charging:
                    factor = 0.4 + 0.6 * ((math.sin(t * 3.0) + 1.0) / 2.0)
                    r, g, b = 0, int(255 * factor), int(80 * factor)
                else:
                    if batt > 50:
                        r, g, b = 0, 230, 60
                    elif batt > 20:
                        r, g, b = 255, 180, 0
                    else:
                        pulse = 0.5 + 0.5 * math.sin(t * 6.0)
                        r, g, b = int(255 * pulse), 0, 0

            # 7. Fire & Flame
            elif eff == LightEffect.FIRE:
                flicker = 0.65 + math.sin(t * 7.0) * 0.2 + math.cos(t * 13.0) * 0.15
                r = int(min(255, 255 * flicker))
                g = int(min(255, 100 * (flicker ** 1.8)))
                b = int(min(255, 15 * (flicker ** 3)))

            # 8. Cyberpunk 2077 Neon
            elif eff == LightEffect.CYBERPUNK:
                # Cyan base (#00f0ff) with rhythmic electric yellow/pink glitches
                glitch_phase = (math.sin(t * 4.0) + math.cos(t * 9.0))
                if glitch_phase > 1.4:
                    # Cyberpunk electric yellow
                    r, g, b = 254, 232, 1
                elif glitch_phase < -1.4:
                    # Hot magenta pink
                    r, g, b = 255, 0, 110
                else:
                    # Signature neon cyan
                    pulse = 0.8 + 0.2 * math.sin(t * 3.0)
                    r, g, b = 0, int(240 * pulse), int(255 * pulse)

            # 9. Aurora Borealis
            elif eff == LightEffect.AURORA:
                # Ethereal waves: Emerald Green (#00ff87) -> Cyan (#60efff) -> Violet (#7000ff)
                w1 = (math.sin(t * 1.2) + 1.0) / 2.0
                w2 = (math.cos(t * 1.8) + 1.0) / 2.0
                r = int(112 * w2)
                g = int(255 * w1)
                b = int(255 * (1.0 - w1 * 0.5) + 200 * w2 * 0.5)

            # 10. RPM Shift Light (Ferrari F1 & Forza Telemetry)
            # Normal Zone: Ferrari Rosso Corsa Red | Shift Zone: Ferrari F1 Electric Blue | Shift Event: Giallo Modena Gold
            elif eff == LightEffect.RPM_SHIFT:
                if rpm < 0.85:
                    # Normal Acceleration / Powerband Zone: Ferrari Rosso Red
                    # Deep crimson at idle (0.0), intensifying to blazing pure Ferrari Red
                    prog = max(0.0, min(1.0, rpm / 0.85))
                    r = int(140 + 115 * prog)
                    g = 0
                    b = 0
                elif rpm < 0.96:
                    # Shift Window: Ferrari F1 Steering Wheel Electric Blue
                    r = 0
                    g = 90
                    b = 255
                else:
                    # Approaching Rev Limiter / Redline: Rapid 18Hz High-Speed Ferrari Blue Strobe
                    strobe = int(time.perf_counter() * 18) % 2
                    r, g, b = (120, 210, 255) if strobe else (0, 70, 255)

            # 11. Supernova (Cosmic Burst)
            elif eff == LightEffect.SUPERNOVA:
                # Deep cosmic violet swelling into intense magenta with periodic stellar white explosion
                burst = (max(0.0, math.sin(t * 2.2)) ** 7)
                r = int(min(255, 160 + 95 * burst + 40 * math.sin(t * 1.5)))
                g = int(min(255, 20 + 235 * burst))
                b = int(min(255, 80 + 175 * burst))

            # 12. Quantum Flux (Chroma Comet)
            elif eff == LightEffect.QUANTUM_FLUX:
                # High-speed particle stream oscillating between electric cyan and neon violet with trailing comet sparks
                beam = (math.sin(t * 3.5) + 1.0) / 2.0
                comet = (max(0.0, math.sin(t * 7.5 + math.pi / 4)) ** 8)
                r = int(min(255, (160 * (1 - beam) + 0 * beam) + 255 * comet))
                g = int(min(255, (10 * (1 - beam) + 240 * beam) + 255 * comet))
                b = 255

            # 13. Vaporwave Dreams (80s Pastel)
            elif eff == LightEffect.VAPORWAVE:
                # Tri-color nostalgic pastel crossfade: Mint (#2dd4bf) -> Peach (#fb7185) -> Lilac (#c084fc)
                phase = (t * 0.75) % 3.0
                if phase < 1.0:
                    p = phase
                    r = int(45 * (1 - p) + 251 * p)
                    g = int(212 * (1 - p) + 113 * p)
                    b = int(191 * (1 - p) + 133 * p)
                elif phase < 2.0:
                    p = phase - 1.0
                    r = int(251 * (1 - p) + 192 * p)
                    g = int(113 * (1 - p) + 132 * p)
                    b = int(133 * (1 - p) + 252 * p)
                else:
                    p = phase - 2.0
                    r = int(192 * (1 - p) + 45 * p)
                    g = int(132 * (1 - p) + 212 * p)
                    b = int(252 * (1 - p) + 191 * p)

            # 14. Heartbeat Monitor (ECG Vital)
            elif eff == LightEffect.HEARTBEAT:
                # Cardiac ECG cycle: rhythmic 66 BPM double-systolic "thump-thump" pulse with diastolic resting fade
                cycle_t = (t * 1.1) % 1.0
                if cycle_t < 0.12:  # First beat (systole)
                    p = math.sin((cycle_t / 0.12) * math.pi)
                    r, g, b = int(120 + 135 * p), int(10 * p), 0
                elif 0.18 < cycle_t < 0.32:  # Second beat (diastole)
                    p = math.sin(((cycle_t - 0.18) / 0.14) * math.pi)
                    r, g, b = int(100 + 155 * p), int(20 * p), 0
                else:  # Calm resting vessel glow
                    p = 0.5 + 0.5 * math.sin(cycle_t * math.pi * 2)
                    r, g, b = int(35 + 25 * p), 0, 0

            # 15. Super Saiyan (Golden Aura)
            elif eff == LightEffect.GOLDEN_AURA:
                # Blazing golden energy aura with crackling lightning micro-flickering
                flicker = 0.75 + 0.15 * math.sin(t * 12.0) + 0.10 * math.cos(t * 21.0)
                spark = 1.0 if (int(t * 16) % 6 == 0) else 0.0
                r = int(min(255, 255 * flicker + 60 * spark))
                g = int(min(255, 185 * (flicker ** 1.3) + 70 * spark))
                b = int(min(255, 15 * flicker + 30 * spark))

            # 16. Hyperdrive Warp
            elif eff == LightEffect.HYPERDRIVE:
                # Cosmic deep blue with sharp photon flashes
                pulse = (math.sin(t * 6.0) ** 6) # Sharp burst
                r = int(255 * pulse)
                g = int(220 * pulse + 40)
                b = int(255 * (0.4 + 0.6 * pulse))

            # 17. Matrix Code Rain
            elif eff == LightEffect.MATRIX:
                # Phosphor green digital stream with periodic bright drop pulses
                drop = (math.sin(t * 8.0) + 1.0) / 2.0
                r = int(20 * drop)
                g = int(180 + 75 * drop)
                b = int(40 * drop)

            # 18. Ocean Waves
            elif eff == LightEffect.OCEAN:
                # Aquatic tide: Deep navy -> Aquamarine -> Seafoam cyan
                wave = (math.sin(t * 1.6) + 1.0) / 2.0
                r = int(0 * (1 - wave) + 40 * wave)
                g = int(100 * (1 - wave) + 230 * wave)
                b = int(255 * (1 - wave) + 210 * wave)

            if self.on_color_update:
                self.on_color_update(r, g, b)

            time.sleep(interval)
