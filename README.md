# OpenDSZ: Free & Open-Source DualSense Controller Manager

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-emerald.svg)](README.md)
[![Release](https://img.shields.io/badge/Release-v1.0.0-indigo.svg)](https://github.com/abrahamjroy/OpenDualSenseZ/releases)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

OpenDSZ is a fast, lightweight, and completely open-source alternative to DualSenseX. It provides full adaptive trigger manipulation, UDP telemetry synthesis, touchpad & 6-axis air mouse navigation, Ferrari's F1 inspired dynamic shift lights for Forza games, and Steam game templates with zero paywalls, zero telemetry, and zero bloated browser runtimes.

Developed and maintained by **[Abraham Jeevan Roy](https://github.com/abrahamjroy)** and the OpenDSZ Contributors.

---

## 1. Standalone Zero-Install Applications (Cross-Platform Releases)

End users do **not** need to install Python, Git, or dependencies. OpenDSZ is distributed as pre-compiled, standalone binaries for **Windows**, **macOS**, and **Linux**:

| Platform | Format | Release Asset | How to Run |
| :--- | :--- | :--- | :--- |
| **Windows (Direct)** | **Standalone Single Executable** | **`OpenDSZ-DualSense.exe`** | **Download and run directly** (Zero extraction, zero install) |
| **Windows (Portable)** | Portable Directory Package | `OpenDSZ-Windows-x64.zip` | Extract zip and run `OpenDSZ-DualSense.exe` |
| **Linux (Direct)** | Standalone Executable Binary | `OpenDSZ-Linux-x86_64` | `chmod +x OpenDSZ-Linux-x86_64 && ./OpenDSZ-Linux-x86_64` |
| **Linux (Tarball)** | Standalone Tarball Package | `OpenDSZ-Linux-x86_64.tar.gz` | Extract tarball and execute `./OpenDSZ` |
| **macOS** | Universal App Bundle | `OpenDSZ-macOS-universal.zip` | Unzip and open `OpenDSZ.app` (Apple Silicon & Intel) |

### Automated GitHub CI/CD Pipeline
Every git tag (e.g. `v1.0.0`) automatically triggers [`.github/workflows/release.yml`](.github/workflows/release.yml) to cross-compile standalone binaries on Windows, Ubuntu, and macOS runners and publish them directly to GitHub Releases.

---

## 2. Core Capabilities

1. **Adaptive Triggers (USB & Bluetooth)**:
   - Full support for `Rigid` (hydraulic resistance), `Trigger Stop` (firearm hair-triggers & weapon stops), `Pulse` (ABS shudder), `Machine Gun`, `Bow`, and `Gallop` modes.
   - Built-in Bluetooth IEEE 802.3 CRC-32 checksum generation for Report `0x31`.
2. **Forza Horizon Real-Time Telemetry & Ferrari F1 Tachometer**:
   - Reads the 324-byte UDP Data Out stream from Steam versions of **Forza Horizon 4, 5, and 6** on Port `5300`.
   - **Ferrari F1 Shift Lights**: Rosso Corsa Red during normal acceleration $\rightarrow$ Electric Blue in shift window $\rightarrow$ Giallo Modena Gold burst confirmation on gear shifts.
   - **Brake Trigger (LT)**: Progressive hydraulic resistance with rapid pulsing (ABS simulation) when front tires lock or slip.
   - **Throttle Trigger (RT)**: Traction loss vibration kick when drive wheels spin, plus physical resistance thumps during gear changes.
3. **Desktop Navigation: Touchpad Mouse & 6-Axis Air Mouse (Gyro)**:
   - **Touchpad Mouse**: High-precision 12-bit cursor tracking, tap-to-click, physical pad zones (Left, Right, Middle click), MacBook-style tactile Force Touch haptic clicks, and configurable scroll lines (1 to 15 lines).
   - **Air Mouse (Gyro)**: Leverage 6-axis IMU gyro motion with EMA smoothing and deadzone filtering for effortless pointer aiming. Automatically arms L2/R2 into firearm hair-triggers (`0x25` Trigger Stop) with tactile recoil kick.
4. **DualSenseX Drop-in Compatibility (UDP 6969)**:
   - Emulates the DSX v2/v3 UDP socket server. All existing community mods (Cyberpunk 2077, GTA V, Witcher 3, BeamNG.drive) work out of the box.
5. **Dynamic RGB Lighting Engine (18 Presets)**:
   - Intuitive 360° Hue and Brightness sliders with live swatch preview.
   - 18 high-performance hardware-accelerated animations running at 30 FPS:
     - *Static Color, Breathing, Rainbow Cycle, Police Flashers, Neon Sunset, Battery Indicator, Fire & Flame, Cyberpunk 2077, Aurora Borealis, Ferrari F1 RPM Shift Light, Supernova, Quantum Flux, Vaporwave Dreams, Heartbeat Monitor, Super Saiyan Golden Aura, Hyperdrive Warp, Matrix Code Rain, and Ocean Waves*.
6. **PulseCore-Inspired System & Wireless Capabilities**:
   - **Automatic Headset Audio Switching**: Reads Byte 53 to detect 3.5mm jack insertion/removal and switches between speaker and headphones automatically.
   - **Hardware Mic Mute & Amber LED**: Full bidirectional synchronization with the controller's physical mute button and indicator LED.
   - **Battery-Saving Idle Auto-Sleep**: Configurable timer (5, 10, 15, 30 min) powers down trigger motors and RGB LEDs on inactivity; wakes instantly on button press or touchpad contact.
   - **Real-time Diagnostics & Jitter Alerts**: Live polling rate (Hz) and latency (ms) readouts with automatic 2.4GHz interference warnings (>20ms).
   - **Diagnostic Bundle Export**: Generates a complete troubleshooting report (controller VID/PID, connection type, battery, latency, telemetry state) ready to paste into GitHub issues or Discord.
   - **Master Rumble Gain**: Global haptic and vibration intensity scaling (0% - 100%).
7. **Utilitarian, High-Speed UI & Multi-Resolution Windows Branding**:
   - Built for speed (< 25MB RAM, sub-50ms launch, dark midnight theme).
   - Authentic two-tone white and black controller branding with embedded 7-size multi-resolution Windows ICO (16x16 to 256x256) and explicit AppUserModelID.

---

## 3. Steam Game Setup

### Forza Horizon 4 / 5 / 6 (Steam Version)
1. Open Forza Horizon and go to **Settings > HUD and Gameplay**.
2. Scroll to the bottom and configure:
   - **Data Out**: `ON`
   - **Data Out IP Address**: `127.0.0.1`
   - **Data Out IP Port**: `5300`
3. Launch OpenDSZ and ensure **"Forza Horizon Telemetry"** is checked. Triggers and lighting will dynamically respond to RPM, tire slip, and braking forces in real time.

### Cyberpunk 2077 & Other DSX-Modded Games
1. Install any standard DualSenseX mod for your Steam game (e.g. Cyberpunk DualSense Mod from Nexus Mods).
2. Keep OpenDSZ running with **"DualSenseX UDP Server (UDP 6969)"** enabled.
3. The game mod will automatically transmit trigger instructions to OpenDSZ.

---

## 4. Linux Setup (udev rules)

To allow OpenDSZ to communicate with your DualSense controller over USB and Bluetooth without root (`sudo`) privileges on Linux:

```bash
sudo cp scripts/99-dualsense.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

## 5. Building from Source (Developers)

```bash
# Clone the repository
git clone https://github.com/abrahamjroy/OpenDualSenseZ.git
cd OpenDualSenseZ

# Install dependencies
pip install -r requirements.txt pyinstaller

# Run locally
python run.py

# Build standalone executable
# Windows:
python build.py

# Linux:
bash scripts/build_linux.sh

# macOS:
bash scripts/build_macos.sh
```
---

## 6. Attribution, Credits & Upstream Research

OpenDSZ is built upon pioneering reverse-engineering and open-source contributions from the gaming and hardware community:

- **Original Author & Maintainer**: **Abraham Jeevan Roy** ([@abrahamjroy](https://github.com/abrahamjroy))
- **daidr ([daidr/dualsense-tester](https://github.com/daidr/dualsense-tester))**: Invaluable documentation of Bluetooth Output Report `0x36`, Opus CELT frame layouts, and 3000Hz haptic PCM stream multiplexing.
- **nowrep ([nowrep/dualsensectl](https://github.com/nowrep/dualsensectl))**: Linux HID protocol reverse-engineering, output report structures, and IEEE 802.3 CRC-32 seed calculations for Bluetooth Report `0x31`.
- **Sony Interactive Entertainment**: Official Linux kernel driver `hid-playstation` (`drivers/hid/hid-playstation.c`) for baseline report definitions and validity flags.
- **ligun0510 ([ligun0510/PulseCore](https://github.com/ligun0510/PulseCore))**: Architecture inspiration for real-time link diagnostics, audio route state tracking, and rumble attenuation scaling.

---

## 7. How to Attribute / Cite OpenDSZ

If you use OpenDSZ in your software, game mods, research, or articles, please provide attribution using the following formats:

### BibTeX
```bibtex
@software{Roy_OpenDualSenseZ_2026,
  author       = {Roy, Abraham Jeevan},
  title        = {{OpenDSZ: Free & Open-Source DualSense Controller Manager}},
  year         = {2026},
  publisher    = {GitHub},
  journal      = {GitHub repository},
  howpublished = {\url{https://github.com/abrahamjroy/OpenDualSenseZ}},
  version      = {1.0.0}
}
```

### Markdown / Text
```text
OpenDSZ by Abraham Jeevan Roy (https://github.com/abrahamjroy/OpenDualSenseZ) - Licensed under Apache-2.0.
```

---

## 8. License & Legal Disclaimers

### License
OpenDSZ is licensed under the **Apache License, Version 2.0**. See the [LICENSE](LICENSE) file for the full license text and the [NOTICE](NOTICE) file for mandatory attribution notices.

Under Section 4(d) of the Apache 2.0 License, any redistribution or derivative work must retain and display the attribution notices contained in the `NOTICE` file in documentation or user interfaces.

### Trademark Disclaimer
- "PlayStation", "DualSense", "DualSense Edge", and "PS5" are registered trademarks or trademarks of **Sony Interactive Entertainment Inc.**
- "Forza", "Forza Horizon", and "Windows" are trademarks of the **Microsoft Corporation**.
- "Steam" is a registered trademark of **Valve Corporation**.
- "macOS" is a trademark of **Apple Inc.**

OpenDSZ is an independent open-source project and is neither affiliated with, authorized by, sponsored by, nor endorsed by Sony Interactive Entertainment, Microsoft, Valve, or Apple. All product and company names are trademarks or registered trademarks of their respective holders. Use of them does not imply any affiliation with or endorsement by them.
