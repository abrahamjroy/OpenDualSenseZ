"""
OpenDSZ Modern & Lightweight Desktop Interface
Engineered for maximum readability, clean visual hierarchy, low latency,
and minimal memory footprint (<30MB RAM).
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import colorsys
from PIL import Image, ImageTk

from .protocol import TriggerMode, ConnectionType
from .controller import DualSenseController
from .mouse import TouchpadMouse
from .telemetry_forza import ForzaTelemetryEngine
from .dsx_server import DSXUdpServer
from .profiles import ProfileManager
from .effects import LightbarEffectsEngine, LightEffect
from .tray import SystemTrayManager
from .audio import DualSenseAudioEngine

# Typography Definition
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_SUBTITLE = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_BODY = ("Segoe UI", 10, "normal")
FONT_BODY_BOLD = ("Segoe UI", 10, "bold")
FONT_CAPTION = ("Segoe UI", 9, "normal")
FONT_BADGE = ("Segoe UI", 9, "bold")

# Color Palette (Deep Midnight Obsidian)
CLR_BG = "#0b0f19"         # Base window background
CLR_SURFACE = "#151e33"    # Elevated card surfaces
CLR_SURFACE_ALT = "#1a253f"# Secondary card background
CLR_BORDER = "#253456"     # Card border / outline
CLR_ACCENT = "#38bdf8"     # Electric cyan accent
CLR_ACCENT_HOVER = "#0284c7"
CLR_TEXT = "#f8fafc"       # High-contrast primary text
CLR_TEXT_MUTED = "#94a3b8" # Secondary muted text
CLR_GREEN = "#10b981"      # Connected / Normal
CLR_AMBER = "#f59e0b"      # Warning / Charging
CLR_RED = "#ef4444"        # Error / Disconnected

LT_MODE_OPTIONS = [
    ("Off (Standard)", TriggerMode.OFF),
    ("Brake Hydraulic Resistance", TriggerMode.RIGID),
    ("ABS Pulse (Brake Lockup Shudder)", TriggerMode.PULSE),
    ("Trigger Stop (Hair Trigger / Cut)", TriggerMode.TRIGGER_STOP),
    ("Machine Gun (Rapid Vibration)", TriggerMode.MACHINE_GUN),
    ("Gallop (Dual Pulse Shudder)", TriggerMode.GALLOP),
    ("Bow (Progressive Elastic Tension)", TriggerMode.BOW),
]

RT_MODE_OPTIONS = [
    ("Off (Standard)", TriggerMode.OFF),
    ("Throttle Resistance (Pedal Stiffness)", TriggerMode.RIGID),
    ("Traction Loss (Wheelspin Impulse Pulse)", TriggerMode.MACHINE_GUN),
    ("Traction Loss (Gallop Dual-Pulse Shudder)", TriggerMode.GALLOP),
    ("Pulse (Rapid Vibration)", TriggerMode.PULSE),
    ("Trigger Stop (Hair Trigger / Cut)", TriggerMode.TRIGGER_STOP),
    ("Bow (Progressive Elastic Tension)", TriggerMode.BOW),
]

ALL_MODE_OPTIONS = LT_MODE_OPTIONS + RT_MODE_OPTIONS
MODE_OPTIONS = RT_MODE_OPTIONS  # For backwards-compatibility

EFFECT_OPTIONS = [eff.value for eff in LightEffect]


class OpenDSZApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OpenDSZ - DualSense Controller Manager")
        self.root.geometry("640x720")
        self.root.minsize(580, 680)

        # Asset Paths (Supports dev tree, PyInstaller onedir, and standalone bundle)
        if getattr(sys, "frozen", False):
            base_candidates = [
                getattr(sys, "_MEIPASS", ""),
                os.path.dirname(sys.executable),
                os.path.join(getattr(sys, "_MEIPASS", ""), "opendsz"),
                os.path.join(os.path.dirname(sys.executable), "opendsz"),
            ]
            self.assets_dir = os.path.join(os.path.dirname(__file__), "assets")
            for base in base_candidates:
                if base:
                    cand = os.path.join(base, "assets")
                    if os.path.exists(cand):
                        self.assets_dir = cand
                        break
        else:
            self.assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        self._setup_window_icon()

        # Core Backend Subsystems
        self.controller = DualSenseController()
        self.mouse = TouchpadMouse()
        self.forza_telemetry = ForzaTelemetryEngine()
        self.dsx_server = DSXUdpServer()
        self.profile_mgr = ProfileManager()
        self.effects = LightbarEffectsEngine()
        self.audio = DualSenseAudioEngine()

        # Callbacks
        self.controller.on_connection_change = self._on_connection_changed
        self.controller.on_input_update = self._on_input_update
        self.controller.on_mute_toggle = self._on_controller_mute_toggled
        self.controller.on_sleep_change = self._on_controller_sleep_changed
        self.forza_telemetry.on_trigger_update = self._on_forza_trigger_update
        self.forza_telemetry.on_rpm_update = self.effects.set_rpm_ratio
        self.forza_telemetry.on_telemetry_stats = self._on_forza_telemetry_stats
        self.forza_telemetry.on_gear_shift = self._on_forza_gear_shift
        self.dsx_server.on_trigger_update = self._on_dsx_trigger_update
        self.dsx_server.on_rgb_update = self._on_dsx_rgb_update
        self.effects.on_color_update = self._on_effect_color_update
        self.mouse.on_haptic_feedback = self._on_mouse_haptic_feedback

        # System Tray Integration
        self.tray = SystemTrayManager(
            on_restore=self._restore_from_tray,
            on_quit=self._quit_app
        )

        # UI State Variables
        self.conn_dot_var = tk.StringVar(value="○")
        self.conn_text_var = tk.StringVar(value="Disconnected")
        self.battery_text_var = tk.StringVar(value="--%")
        self.is_charging_var = tk.BooleanVar(value=False)
        self.polling_text_var = tk.StringVar(value="-- Hz")
        self.mic_status_var = tk.StringVar(value="🎙️ Mic: ON")
        self.is_mic_muted_var = tk.BooleanVar(value=False)
        self.jitter_status_var = tk.StringVar(value="Optimal")
        self.idle_sleep_var = tk.StringVar(value="10 minutes")

        self.touch_mouse_var = tk.BooleanVar(value=False)
        self.mouse_sens_var = tk.DoubleVar(value=0.2)
        self.scroll_lines_var = tk.IntVar(value=3)
        self.air_mouse_var = tk.BooleanVar(value=False)
        self.gyro_sens_var = tk.DoubleVar(value=0.8)
        self.gyro_deadzone_var = tk.IntVar(value=100)
        self.invert_pitch_var = tk.BooleanVar(value=False)
        self.touch_haptics_var = tk.BooleanVar(value=True)
        self.mouse_buttons_var = tk.BooleanVar(value=True)
        self.forza_tel_var = tk.BooleanVar(value=True)
        self.forza_port_var = tk.IntVar(value=5300)
        self.forza_status_var = tk.StringVar(value="📡 Telemetry: Waiting for packets on UDP 5300...")
        self.dsx_udp_var = tk.BooleanVar(value=True)
        self.minimize_to_tray_var = tk.BooleanVar(value=True)

        # Triggers & Rumble
        self.lt_mode_var = tk.StringVar(value="Brake Hydraulic Resistance")
        self.lt_start_var = tk.IntVar(value=5)
        self.lt_force_var = tk.IntVar(value=180)
        self.lt_freq_var = tk.IntVar(value=10)

        self.rt_mode_var = tk.StringVar(value="Throttle Resistance (Pedal Stiffness)")
        self.rt_start_var = tk.IntVar(value=5)
        self.rt_force_var = tk.IntVar(value=80)
        self.rt_freq_var = tk.IntVar(value=10)
        self.master_rumble_var = tk.IntVar(value=100)

        # Lightbar Hue-based Color Controls
        self.light_effect_var = tk.StringVar(value=LightEffect.STATIC.value)
        self.light_speed_var = tk.DoubleVar(value=1.0)
        self.hue_var = tk.DoubleVar(value=210.0)        # 0.0 to 360.0 (PlayStation Cyan/Blue)
        self.brightness_var = tk.DoubleVar(value=100.0) # 0.0 to 100.0%
        self.rgb_r_var = tk.IntVar(value=0)
        self.rgb_g_var = tk.IntVar(value=120)
        self.rgb_b_var = tk.IntVar(value=255)
        self._updating_color_ui = False

        # Audio & Headset Detection
        self.audio_route_var = tk.StringVar(value="Speaker (Controller)")
        self.audio_vol_var = tk.IntVar(value=75)
        self.auto_switch_audio_var = tk.BooleanVar(value=True)
        self.headphone_status_var = tk.StringVar(value="Unplugged (Speaker)")
        self._last_headphone_state = False

        # Window Lifecycle Hooks
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.root.bind("<Unmap>", self._on_window_unmap)

        # Build Interface
        self._apply_theme()
        self._build_ui()

        # Auto-detect if any game process is running to auto-select its profile
        detected_profile = None
        if sys.platform == "win32":
            try:
                import subprocess
                out = subprocess.check_output("tasklist /FO CSV", shell=True, text=True).lower()
                for p_name, p_data in self.profile_mgr.profiles.items():
                    for proc in p_data.get("process_names", []):
                        if proc.lower() in out:
                            detected_profile = p_name
                            break
                    if detected_profile:
                        break
            except Exception:
                pass

        if detected_profile:
            self.profile_mgr.active_profile_name = detected_profile
            self.prof_combo.set(detected_profile)

        self.effects.start()
        self._apply_active_profile()
        self._toggle_forza_telemetry()
        self._toggle_dsx_server()
        self.reconnect_controller()
        self.root.deiconify()
        self.root.lift()

    def _setup_window_icon(self):
        """Applies high-resolution application branding to window titlebar and OS taskbar."""
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("opendsz.dualsense.manager.1.0")
            except Exception:
                pass

        icon_path = os.path.join(self.assets_dir, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        logo_path = os.path.join(self.assets_dir, "logo_48.png")
        if os.path.exists(logo_path):
            try:
                self._window_icon_img = ImageTk.PhotoImage(Image.open(logo_path))
                self.root.iconphoto(True, self._window_icon_img)
            except Exception:
                pass

    def _apply_theme(self):
        style = ttk.Style()
        style.theme_use("clam")

        self.root.configure(bg=CLR_BG)

        # General
        style.configure(".", background=CLR_BG, foreground=CLR_TEXT, font=FONT_BODY)
        style.configure("TFrame", background=CLR_BG)
        style.configure("TLabel", background=CLR_BG, foreground=CLR_TEXT, font=FONT_BODY)
        style.configure("Muted.TLabel", background=CLR_BG, foreground=CLR_TEXT_MUTED, font=FONT_CAPTION)

        # Card Frames
        style.configure("Card.TFrame", background=CLR_SURFACE, relief="flat")
        style.configure("Card.TLabel", background=CLR_SURFACE, foreground=CLR_TEXT, font=FONT_BODY)
        style.configure("CardTitle.TLabel", background=CLR_SURFACE, foreground=CLR_TEXT, font=FONT_SECTION)
        style.configure("CardMuted.TLabel", background=CLR_SURFACE, foreground=CLR_TEXT_MUTED, font=FONT_CAPTION)

        # Badges
        style.configure("BadgeGreen.TLabel", background="#064e3b", foreground="#34d399", font=FONT_BADGE, padding=(6, 2))
        style.configure("BadgeRed.TLabel", background="#450a0a", foreground="#f87171", font=FONT_BADGE, padding=(6, 2))
        style.configure("BadgeAmber.TLabel", background="#451a03", foreground="#fbbf24", font=FONT_BADGE, padding=(6, 2))

        # Checkbuttons
        style.configure("TCheckbutton", background=CLR_SURFACE, foreground=CLR_TEXT, font=FONT_BODY)

        # Buttons
        style.configure("TButton", font=FONT_BODY_BOLD, background=CLR_SURFACE_ALT, foreground=CLR_TEXT, borderwidth=0, padding=(10, 6))
        style.map("TButton", background=[("active", CLR_ACCENT_HOVER), ("hover", CLR_BORDER)])

        style.configure("Primary.TButton", font=FONT_BODY_BOLD, background=CLR_ACCENT, foreground="#090d16", borderwidth=0, padding=(10, 6))
        style.map("Primary.TButton", background=[("active", CLR_ACCENT_HOVER)])

        # Modern Tabs (Notebook)
        style.configure("TNotebook", background=CLR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=CLR_SURFACE_ALT, foreground=CLR_TEXT_MUTED, font=FONT_SUBTITLE, padding=(14, 8), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", CLR_SURFACE), ("active", CLR_BORDER)],
                  foreground=[("selected", CLR_ACCENT), ("active", CLR_TEXT)])

        # Combobox
        style.configure("TCombobox", fieldbackground=CLR_SURFACE_ALT, background=CLR_BORDER, foreground=CLR_TEXT, font=FONT_BODY)

    def _build_ui(self):
        # Header Top Bar
        header = tk.Frame(self.root, bg=CLR_SURFACE, height=64, padx=16, pady=10)
        header.pack(fill=tk.X, side=tk.TOP)

        # Logo and Title Left Group
        left_group = tk.Frame(header, bg=CLR_SURFACE)
        left_group.pack(side=tk.LEFT, fill=tk.Y)

        logo_path = os.path.join(self.assets_dir, "logo_48.png")
        if os.path.exists(logo_path):
            try:
                self.logo_img = ImageTk.PhotoImage(Image.open(logo_path).resize((36, 36)))
                logo_lbl = tk.Label(left_group, image=self.logo_img, bg=CLR_SURFACE)
                logo_lbl.pack(side=tk.LEFT, padx=(0, 10))
            except Exception:
                pass

        title_box = tk.Frame(left_group, bg=CLR_SURFACE)
        title_box.pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(title_box, text="OpenDSZ", font=FONT_TITLE, fg=CLR_TEXT, bg=CLR_SURFACE).pack(anchor="w")
        tk.Label(title_box, text="DualSense Controller Manager", font=FONT_CAPTION, fg=CLR_TEXT_MUTED, bg=CLR_SURFACE).pack(anchor="w")

        # Right Status Group (Diagnostics, Mute, Connection, Battery, Refresh)
        right_group = tk.Frame(header, bg=CLR_SURFACE)
        right_group.pack(side=tk.RIGHT, fill=tk.Y)

        # Polling Diagnostics Pill
        self.polling_pill = tk.Frame(right_group, bg="#1e293b", padx=8, pady=4)
        self.polling_pill.pack(side=tk.LEFT, padx=3)
        self.polling_lbl = tk.Label(self.polling_pill, textvariable=self.polling_text_var, font=FONT_BADGE, fg=CLR_ACCENT, bg="#1e293b")
        self.polling_lbl.pack(side=tk.LEFT)

        # Mic Mute Toggle Pill
        self.mic_pill = tk.Frame(right_group, bg="#1e293b", padx=8, pady=4, cursor="hand2")
        self.mic_pill.pack(side=tk.LEFT, padx=3)
        self.mic_lbl = tk.Label(self.mic_pill, textvariable=self.mic_status_var, font=FONT_BADGE, fg=CLR_TEXT, bg="#1e293b", cursor="hand2")
        self.mic_lbl.pack(side=tk.LEFT)
        self.mic_pill.bind("<Button-1>", lambda e: self._toggle_mic_mute_ui())
        self.mic_lbl.bind("<Button-1>", lambda e: self._toggle_mic_mute_ui())

        # Connection Pill
        self.conn_pill = tk.Frame(right_group, bg="#1e293b", padx=8, pady=4)
        self.conn_pill.pack(side=tk.LEFT, padx=3)
        self.dot_lbl = tk.Label(self.conn_pill, textvariable=self.conn_dot_var, font=FONT_BADGE, fg=CLR_RED, bg="#1e293b")
        self.dot_lbl.pack(side=tk.LEFT, padx=(0, 4))
        self.conn_lbl = tk.Label(self.conn_pill, textvariable=self.conn_text_var, font=FONT_BADGE, fg=CLR_TEXT_MUTED, bg="#1e293b")
        self.conn_lbl.pack(side=tk.LEFT)

        # Battery Pill
        self.batt_pill = tk.Frame(right_group, bg="#1e293b", padx=8, pady=4)
        self.batt_pill.pack(side=tk.LEFT, padx=3)
        self.batt_icon = tk.Label(self.batt_pill, text="🔋", font=FONT_CAPTION, bg="#1e293b")
        self.batt_icon.pack(side=tk.LEFT, padx=(0, 4))
        self.batt_lbl = tk.Label(self.batt_pill, textvariable=self.battery_text_var, font=FONT_BADGE, fg=CLR_TEXT, bg="#1e293b")
        self.batt_lbl.pack(side=tk.LEFT)

        # Refresh Device Button
        ttk.Button(right_group, text="⟳ Refresh", command=self.reconnect_controller).pack(side=tk.LEFT, padx=(4, 0))

        # Main Tabbed Content Area
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        # Tab 1: Triggers & Games
        tab_triggers = ttk.Frame(notebook)
        notebook.add(tab_triggers, text=" ⚡ Triggers & Profiles ")
        self._build_tab_triggers(tab_triggers)

        # Tab 2: Lightbar Effects
        tab_lights = ttk.Frame(notebook)
        notebook.add(tab_lights, text=" 🌈 RGB Lightbar ")
        self._build_tab_lights(tab_lights)

        # Tab 3: Audio & Haptics
        tab_audio = ttk.Frame(notebook)
        notebook.add(tab_audio, text=" 🔊 Audio & Haptics ")
        self._build_tab_audio(tab_audio)

        # Tab 4: Touchpad & System
        tab_mouse = ttk.Frame(notebook)
        notebook.add(tab_mouse, text=" 🖱️ Touchpad & System ")
        self._build_tab_mouse(tab_mouse)

    def _build_tab_triggers(self, parent):
        # 1. Profile Selector Card
        prof_card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        prof_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(prof_card, text="Game Profile / Steam Preset", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        p_row = ttk.Frame(prof_card, style="Card.TFrame")
        p_row.pack(fill=tk.X)

        self.prof_combo = ttk.Combobox(p_row, state="readonly", values=list(self.profile_mgr.profiles.keys()), width=26)
        self.prof_combo.set(self.profile_mgr.active_profile_name)
        self.prof_combo.pack(side=tk.LEFT, padx=(0, 6))
        self.prof_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        ttk.Button(p_row, text="💾 Save", command=self._save_current_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(p_row, text="➕ New", command=self._create_new_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(p_row, text="🌐 Community DL", command=self._download_profile_dialog).pack(side=tk.LEFT, padx=2)

        # 2. Dual Trigger Control Cards (Left & Right Side by Side)
        dual_frame = ttk.Frame(parent)
        dual_frame.pack(fill=tk.X, pady=(0, 10))

        # Left Trigger Card (L2 / Brake)
        lt_card = ttk.Frame(dual_frame, style="Card.TFrame", padding=12)
        lt_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        ttk.Label(lt_card, text="Left Trigger (L2 / Brake)", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(lt_card, text="Progressive hydraulic resistance & ABS", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 8))

        ttk.Label(lt_card, text="Trigger Mode:", style="Card.TLabel").pack(anchor="w")
        self.lt_combo = ttk.Combobox(lt_card, state="readonly", values=[l for l, _ in LT_MODE_OPTIONS], textvariable=self.lt_mode_var)
        self.lt_combo.pack(fill=tk.X, pady=(2, 8))
        self.lt_combo.bind("<<ComboboxSelected>>", self._apply_trigger_presets)

        ttk.Label(lt_card, text="Resistance Force:", style="Card.TLabel").pack(anchor="w")
        ttk.Scale(lt_card, from_=0, to=255, variable=self.lt_force_var, command=lambda e: self._send_manual_triggers()).pack(fill=tk.X, pady=2)

        ttk.Label(lt_card, text="Vibration Frequency (Hz):", style="Card.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Scale(lt_card, from_=0, to=15, variable=self.lt_freq_var, command=lambda e: self._send_manual_triggers()).pack(fill=tk.X, pady=2)

        # Right Trigger Card (R2 / Throttle)
        rt_card = ttk.Frame(dual_frame, style="Card.TFrame", padding=12)
        rt_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        ttk.Label(rt_card, text="Right Trigger (R2 / Throttle)", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(rt_card, text="Throttle resistance & traction loss kick", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 8))

        ttk.Label(rt_card, text="Trigger Mode:", style="Card.TLabel").pack(anchor="w")
        self.rt_combo = ttk.Combobox(rt_card, state="readonly", values=[l for l, _ in RT_MODE_OPTIONS], textvariable=self.rt_mode_var)
        self.rt_combo.pack(fill=tk.X, pady=(2, 8))
        self.rt_combo.bind("<<ComboboxSelected>>", self._apply_trigger_presets)

        ttk.Label(rt_card, text="Resistance Force:", style="Card.TLabel").pack(anchor="w")
        ttk.Scale(rt_card, from_=0, to=255, variable=self.rt_force_var, command=lambda e: self._send_manual_triggers()).pack(fill=tk.X, pady=2)

        ttk.Label(rt_card, text="Vibration Frequency (Hz):", style="Card.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Scale(rt_card, from_=0, to=15, variable=self.rt_freq_var, command=lambda e: self._send_manual_triggers()).pack(fill=tk.X, pady=2)

        # 3. Game Integrations Quick Toggles Card
        intel_card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        intel_card.pack(fill=tk.X)

        ttk.Label(intel_card, text="Active Telemetry & Game Engines", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        # Forza Horizon Telemetry Controls
        forza_frame = ttk.Frame(intel_card, style="Card.TFrame")
        forza_frame.pack(fill=tk.X, pady=2)

        ttk.Checkbutton(forza_frame, text="Forza Horizon Telemetry - Real-time ABS Shudder & Wheelspin",
                        variable=self.forza_tel_var, command=self._toggle_forza_telemetry).pack(side=tk.LEFT)

        ttk.Label(forza_frame, text="Port:", style="CardMuted.TLabel").pack(side=tk.LEFT, padx=(12, 4))
        self.forza_port_spin = ttk.Spinbox(forza_frame, from_=1024, to=65535, textvariable=self.forza_port_var, width=6,
                                           command=self._on_forza_port_change)
        self.forza_port_spin.pack(side=tk.LEFT)
        self.forza_port_spin.bind("<FocusOut>", lambda e: self._on_forza_port_change())
        self.forza_port_spin.bind("<Return>", lambda e: self._on_forza_port_change())

        # Live Telemetry Status Badge Frame
        self.forza_status_box = tk.Frame(intel_card, bg="#0d1b2a", padx=8, pady=5)
        self.forza_status_box.pack(fill=tk.X, pady=(4, 6))
        self.forza_status_lbl = tk.Label(self.forza_status_box, textvariable=self.forza_status_var,
                                         font=FONT_CAPTION, fg="#38bdf8", bg="#0d1b2a", anchor="w")
        self.forza_status_lbl.pack(fill=tk.X)
        # Quick Trigger Test Buttons
        test_frame = ttk.Frame(intel_card, style="Card.TFrame")
        test_frame.pack(fill=tk.X, pady=(2, 4))
        ttk.Button(test_frame, text="⚡ ABS Shudder (L2)", command=self._test_abs_haptics).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(test_frame, text="⚡ Traction Loss (R2)", command=self._test_traction_haptics).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(test_frame, text="⚡ Stiff Brake", command=self._test_heavy_brake).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(test_frame, text="⚡ Gear Shift Clunk & Flash", command=self._test_gear_shift_haptics).pack(side=tk.LEFT)

        ttk.Checkbutton(intel_card, text="DualSenseX UDP Server (UDP 6969) - Drop-in Mod Server (Cyberpunk, GTA V)",
                        variable=self.dsx_udp_var, command=self._toggle_dsx_server).pack(anchor="w", pady=3)

        # Master Rumble Gain (PulseCore inspired)
        rumble_frame = ttk.Frame(intel_card, style="Card.TFrame")
        rumble_frame.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(rumble_frame, text="Master Rumble Intensity:", width=22, style="Card.TLabel").pack(side=tk.LEFT)
        self.rumble_scale = ttk.Scale(rumble_frame, from_=0, to=100, variable=self.master_rumble_var, command=self._on_rumble_gain_change)
        self.rumble_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.rumble_lbl = ttk.Label(rumble_frame, text="100%", width=6, style="Card.TLabel")
        self.rumble_lbl.pack(side=tk.LEFT, padx=(6, 0))

    def _build_tab_lights(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card, text="Dynamic Lightbar Animations", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text="Pre-programmed hardware-accelerated animations running at 30 FPS", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 10))

        # Effect Preset Row
        row1 = ttk.Frame(card, style="Card.TFrame")
        row1.pack(fill=tk.X, pady=4)
        ttk.Label(row1, text="Preset Animation:", width=18, style="Card.TLabel").pack(side=tk.LEFT)
        self.eff_combo = ttk.Combobox(row1, state="readonly", values=EFFECT_OPTIONS, textvariable=self.light_effect_var, width=24)
        self.eff_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.eff_combo.bind("<<ComboboxSelected>>", self._on_effect_selected)

        # Animation Speed
        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill=tk.X, pady=4)
        ttk.Label(row2, text="Animation Speed:", width=18, style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Scale(row2, from_=0.2, to=3.0, variable=self.light_speed_var, command=self._update_effect_speed).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Separator(card, orient="horizontal").pack(fill=tk.X, pady=12)

        # Hue-Based Color Selector with Top Preview Card
        ttk.Label(card, text="Static Color & Brightness", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(card, text="Intuitive 360° Hue and Brightness control with live hardware synchronization", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 8))

        # 1. Color Preview Swatch Bar (Directly Above Controls)
        self.swatch_box = tk.Label(
            card,
            text="#0078FF  •  RGB(0, 120, 255)  •  Hue: 210°  •  100%",
            font=FONT_SUBTITLE,
            fg="#ffffff",
            bg="#0078ff",
            height=2,
            relief="ridge",
            bd=2
        )
        self.swatch_box.pack(fill=tk.X, pady=(0, 10))

        # 2. Hue Slider (0° to 360°)
        hue_row = ttk.Frame(card, style="Card.TFrame")
        hue_row.pack(fill=tk.X, pady=4)
        self.hue_lbl = ttk.Label(hue_row, text="Color Hue (210°):", width=18, style="Card.TLabel")
        self.hue_lbl.pack(side=tk.LEFT)
        self.hue_scale = ttk.Scale(hue_row, from_=0.0, to=360.0, variable=self.hue_var, command=self._on_hue_slider_change)
        self.hue_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 3. Brightness Slider (0% to 100%)
        bright_row = ttk.Frame(card, style="Card.TFrame")
        bright_row.pack(fill=tk.X, pady=4)
        self.bright_lbl = ttk.Label(bright_row, text="Brightness (100%):", width=18, style="Card.TLabel")
        self.bright_lbl.pack(side=tk.LEFT)
        self.bright_scale = ttk.Scale(bright_row, from_=0.0, to=100.0, variable=self.brightness_var, command=self._on_brightness_slider_change)
        self.bright_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 4. Quick Color Presets Palette
        ttk.Label(card, text="Quick Color Presets:", style="CardTitle.TLabel").pack(anchor="w", pady=(12, 6))
        palette_grid = ttk.Frame(card, style="Card.TFrame")
        palette_grid.pack(fill=tk.X, pady=2)

        presets = [
            ("🔵 PS Blue", 210.0, 100.0, False),
            ("🔷 Cyan", 180.0, 100.0, False),
            ("🟣 Purple", 280.0, 100.0, False),
            ("🔴 Red", 0.0, 100.0, False),
            ("🟢 Green", 120.0, 100.0, False),
            ("🟡 Amber", 38.0, 100.0, False),
            ("⚪ White", 0.0, 100.0, True),
            ("⚫ Off", 0.0, 0.0, False),
        ]
        for text, h, b, is_w in presets:
            btn = ttk.Button(palette_grid, text=text, command=lambda hue=h, br=b, white=is_w: self._set_color_preset(hue, br, white))
            btn.pack(side=tk.LEFT, padx=3, pady=2)

    def _build_tab_audio(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card, text="Wireless Audio & Voice-Coil Haptics", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text="Sony Report 0x36 multiplexed Opus Audio & 3000Hz Haptic PCM stream", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 12))

        # Routing Selection
        row1 = ttk.Frame(card, style="Card.TFrame")
        row1.pack(fill=tk.X, pady=6)
        ttk.Label(row1, text="Audio Route:", width=16, style="Card.TLabel").pack(side=tk.LEFT)
        self.route_combo = ttk.Combobox(row1, state="readonly", values=["Speaker (Controller)", "Headphone (3.5mm Jack)"], textvariable=self.audio_route_var, width=22)
        self.route_combo.pack(side=tk.LEFT)
        self.route_combo.bind("<<ComboboxSelected>>", self._on_audio_route_changed)

        # Volume
        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill=tk.X, pady=6)
        ttk.Label(row2, text="Playback Volume:", width=16, style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Scale(row2, from_=0, to=100, variable=self.audio_vol_var, command=self._on_volume_changed).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # PulseCore Auto-Switch & Jack Detection
        ttk.Checkbutton(card, text="Auto-switch between Speaker and Headset when 3.5mm jack is plugged in",
                        variable=self.auto_switch_audio_var).pack(anchor="w", pady=(8, 2))

        jack_row = ttk.Frame(card, style="Card.TFrame")
        jack_row.pack(fill=tk.X, pady=2)
        ttk.Label(jack_row, text="3.5mm Headset Jack:", width=18, style="Card.TLabel").pack(side=tk.LEFT)
        self.jack_status_lbl = ttk.Label(jack_row, textvariable=self.headphone_status_var, font=FONT_BODY_BOLD, foreground=CLR_ACCENT)
        self.jack_status_lbl.pack(side=tk.LEFT)

        ttk.Separator(card, orient="horizontal").pack(fill=tk.X, pady=12)

        # Hardware Test Actions
        ttk.Label(card, text="Hardware Speaker & Haptic Diagnostics", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(card, text="Directly tests the built-in micro speaker and voice-coil haptic actuators.", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 8))

        btn_row = ttk.Frame(card, style="Card.TFrame")
        btn_row.pack(fill=tk.X, pady=4)
        ttk.Button(btn_row, text="🔊 Test Built-in Speaker (Chime)", style="Primary.TButton", command=self._test_speaker_audio).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="⚡ Test Voice-Coil Haptics (150Hz)", command=self._test_voice_coil_haptics).pack(side=tk.LEFT)

        # Speaker Setup Guide Card
        guide_card = tk.Frame(card, bg=CLR_SURFACE_ALT, padx=12, pady=10, relief="flat")
        guide_card.pack(fill=tk.X, pady=(12, 0))

        tk.Label(guide_card, text="How to use the Built-in Speaker on PC", font=FONT_SUBTITLE, fg=CLR_ACCENT, bg=CLR_SURFACE_ALT).pack(anchor="w")
        spk_tips = [
            "• Built-in Speaker Hardware: Located below the PS button. Unplugging 3.5mm headphones routes audio to it.",
            "• USB Connection: Windows creates a 'Wireless Controller' sound device. In Windows Settings > Volume Mixer,",
            "  you can route Discord voice chat or game sound directly to 'Wireless Controller' to play from the controller!",
            "• Bluetooth Connection: OpenDSZ uses Sony Report 0x36 (Opus audio) to stream sound directly to the speaker.",
        ]
        for tip in spk_tips:
            tk.Label(guide_card, text=tip, font=FONT_CAPTION, fg=CLR_TEXT, bg=CLR_SURFACE_ALT).pack(anchor="w", pady=1)

    def _build_tab_mouse(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card, text="Touchpad Cursor & Power Options", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text="12-bit absolute tracking converted to OS mouse events with ballistic smoothing", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 10))

        ttk.Checkbutton(card, text="Enable Touchpad as Mouse Cursor", variable=self.touch_mouse_var, command=self._toggle_mouse).pack(anchor="w", pady=3)

        sens_row = ttk.Frame(card, style="Card.TFrame")
        sens_row.pack(fill=tk.X, pady=4)
        ttk.Label(sens_row, text="Cursor Sensitivity:", width=18, style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Scale(sens_row, from_=0.2, to=3.0, variable=self.mouse_sens_var, command=self._update_mouse_sens).pack(side=tk.LEFT, fill=tk.X, expand=True)

        scroll_row = ttk.Frame(card, style="Card.TFrame")
        scroll_row.pack(fill=tk.X, pady=4)
        ttk.Label(scroll_row, text="Scroll Distance (Lines):", width=18, style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Spinbox(scroll_row, from_=1, to=15, textvariable=self.scroll_lines_var, width=5, command=self._update_scroll_lines).pack(side=tk.LEFT)
        ttk.Label(scroll_row, text="  lines per scroll step / gesture", style="CardMuted.TLabel").pack(side=tk.LEFT)

        # MacBook Force Touch Haptics & Controller Shortcuts toggles
        ttk.Checkbutton(card, text="MacBook Force Touch Haptics (Tactile mechanical clicks, double-tick right-click & scroll detents)",
                        variable=self.touch_haptics_var, command=self._toggle_touch_haptics).pack(anchor="w", pady=2)
        ttk.Checkbutton(card, text="Controller Mouse Shortcuts (L1=Left Click, R1=Right Click, R3=Middle Click, D-Pad=Scroll)",
                        variable=self.mouse_buttons_var, command=self._toggle_mouse_buttons).pack(anchor="w", pady=2)

        test_row = ttk.Frame(card, style="Card.TFrame")
        test_row.pack(fill=tk.X, pady=(2, 4))
        ttk.Button(test_row, text="⚡ Feel Force Touch Click (Down/Up)", command=self._test_macbook_haptic_click).pack(side=tk.LEFT)

        ttk.Separator(card, orient="horizontal").pack(fill=tk.X, pady=8)

        # Air Mouse Mode (Gyro Motion Steering & Gun-like Adaptive Triggers)
        air_card = tk.Frame(card, bg=CLR_SURFACE_ALT, padx=12, pady=10, relief="flat")
        air_card.pack(fill=tk.X, pady=(2, 6))

        tk.Label(air_card, text="🎮 Air Mouse (Motion Gyro Steering & Hair-Trigger Gun Clicks)", font=FONT_SUBTITLE, fg=CLR_ACCENT, bg=CLR_SURFACE_ALT).pack(anchor="w")
        tk.Label(air_card, text="Steer PC cursor through the air with DualSense 6-axis IMU gyro. Triggers act as firearm hair-triggers!", font=FONT_CAPTION, fg=CLR_TEXT_MUTED, bg=CLR_SURFACE_ALT).pack(anchor="w", pady=(0, 6))

        ttk.Checkbutton(air_card, text="Enable Air Mouse Mode (Gyro Motion Steering + Gun Triggers)",
                        variable=self.air_mouse_var, command=self._toggle_air_mouse).pack(anchor="w", pady=2)

        g_sens_row = tk.Frame(air_card, bg=CLR_SURFACE_ALT)
        g_sens_row.pack(fill=tk.X, pady=2)
        tk.Label(g_sens_row, text="Gyro Sensitivity:", width=18, anchor="w", font=FONT_CAPTION, fg=CLR_TEXT, bg=CLR_SURFACE_ALT).pack(side=tk.LEFT)
        ttk.Scale(g_sens_row, from_=0.2, to=3.0, variable=self.gyro_sens_var, command=self._update_gyro_sens).pack(side=tk.LEFT, fill=tk.X, expand=True)

        g_opt_row = tk.Frame(air_card, bg=CLR_SURFACE_ALT)
        g_opt_row.pack(fill=tk.X, pady=2)
        tk.Label(g_opt_row, text="Anti-Drift Deadzone:", width=18, anchor="w", font=FONT_CAPTION, fg=CLR_TEXT, bg=CLR_SURFACE_ALT).pack(side=tk.LEFT)
        ttk.Scale(g_opt_row, from_=30, to=300, variable=self.gyro_deadzone_var, command=self._update_gyro_deadzone).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Checkbutton(g_opt_row, text="Invert Pitch (Y-Axis)", variable=self.invert_pitch_var, command=self._update_invert_pitch).pack(side=tk.RIGHT, padx=(10, 0))

        gun_tips = [
            "• R2 Trigger: Firearm Sear Break -> Left Click (with tactile mechanical wall & gunshot recoil kick)",
            "• L2 Trigger: Aim Sear Break -> Right Click (with tactile mechanical wall & gunshot recoil kick)",
            "• Adaptive Triggers automatically lock into rigid Weapon Stop mode (0x25) on Air Mouse activation",
        ]
        for tip in gun_tips:
            tk.Label(air_card, text=tip, font=FONT_CAPTION, fg=CLR_TEXT, bg=CLR_SURFACE_ALT).pack(anchor="w", pady=1)

        ttk.Separator(card, orient="horizontal").pack(fill=tk.X, pady=10)

        # Idle Auto-Sleep (PulseCore feature)
        ttk.Label(card, text="Power Management & Idle Auto-Sleep", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Label(card, text="Powers down trigger resistance and RGB LEDs on inactivity to save battery", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 6))

        sleep_row = ttk.Frame(card, style="Card.TFrame")
        sleep_row.pack(fill=tk.X, pady=2)
        ttk.Label(sleep_row, text="Idle Auto-Sleep:", width=18, style="Card.TLabel").pack(side=tk.LEFT)
        self.sleep_combo = ttk.Combobox(sleep_row, state="readonly", values=["Disabled", "5 minutes", "10 minutes", "15 minutes", "30 minutes"], textvariable=self.idle_sleep_var, width=16)
        self.sleep_combo.pack(side=tk.LEFT)
        self.sleep_combo.bind("<<ComboboxSelected>>", self._on_idle_sleep_selected)

        ttk.Separator(card, orient="horizontal").pack(fill=tk.X, pady=10)

        ttk.Label(card, text="System Tray & Diagnostics", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Checkbutton(card, text="Minimize to System Tray on window minimize", variable=self.minimize_to_tray_var).pack(anchor="w", pady=2)

        # Connection Diagnostics & Link Health Card
        diag_card = tk.Frame(card, bg=CLR_SURFACE_ALT, padx=12, pady=8, relief="flat")
        diag_card.pack(fill=tk.X, pady=(8, 0))

        tk.Label(diag_card, text="Hardware Diagnostics & Link Health", font=FONT_SUBTITLE, fg=CLR_ACCENT, bg=CLR_SURFACE_ALT).pack(anchor="w")
        self.diag_details_lbl = tk.Label(diag_card, text="Polling Rate: -- Hz | Latency: -- ms | Status: Optimal", font=FONT_CAPTION, fg=CLR_TEXT, bg=CLR_SURFACE_ALT)
        self.diag_details_lbl.pack(anchor="w", pady=(2, 6))

        ttk.Button(diag_card, text="📋 Export Diagnostics Report", command=self._export_diagnostics_report).pack(anchor="w")

        # Gesture Guide Box
        guide_box = tk.Frame(card, bg=CLR_SURFACE_ALT, padx=12, pady=10, relief="flat")
        guide_box.pack(fill=tk.X, pady=(12, 0))

        tk.Label(guide_box, text="Touchpad & Desktop Navigation Guide", font=FONT_SUBTITLE, fg=CLR_ACCENT, bg=CLR_SURFACE_ALT).pack(anchor="w")
        gestures = [
            "• Cursor Tracking: Single-finger glide with ballistic velocity curve",
            "• Left Click: 1-Finger Tap or Physical Pad Click (Left/Center zone) or L1 or R2 (Air Mouse)",
            "• Right Click: 2-Finger Tap or Physical Pad Click (Right zone) or R1 or L2 (Air Mouse)",
            "• Middle Click: Physical Pad Click (Top-Center zone) or R3 (Right Stick Press)",
            "• Vertical Scroll: 2-Finger Drag (with haptic detents) or D-Pad Up/Down",
            "• Air Mouse: Move controller freely in 3D space to guide cursor using 6-axis gyro",
            "• Gun Triggers: Squeeze L2/R2 past mechanical stop for tactile break & gunshot recoil kick",
            "• Force Touch Haptics: Dual-stage tactile impulse on down-press and mechanical tick on release",
        ]
        for g in gestures:
            tk.Label(guide_box, text=g, font=FONT_CAPTION, fg=CLR_TEXT, bg=CLR_SURFACE_ALT).pack(anchor="w", pady=1)

    # --- System Tray & Window State Handlers ---
    def _on_window_unmap(self, event=None):
        """Window minimize [-] button hides the window to the system tray."""
        if getattr(self, "_quitting", False):
            return
        if event and event.widget != self.root:
            return
        if self.minimize_to_tray_var.get():
            try:
                if self.root.state() == "iconic":
                    self.root.withdraw()
                    self.tray.start()
                    self._update_tray_tooltip()
                else:
                    self.root.after(20, self._check_minimize_to_tray)
            except Exception:
                pass

    def _check_minimize_to_tray(self):
        if getattr(self, "_quitting", False):
            return
        try:
            if self.minimize_to_tray_var.get() and self.root.state() == "iconic":
                self.root.withdraw()
                self.tray.start()
                self._update_tray_tooltip()
        except Exception:
            pass

    def _on_window_close(self):
        """Cross close button [X] exits the application completely."""
        self._quit_app()

    def _restore_from_tray(self):
        self.root.after(0, self._show_window)

    def _show_window(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _update_tray_tooltip(self):
        self.tray.update_status(f"{self.conn_text_var.get()} | {self.battery_text_var.get()}")

    def _quit_app(self):
        self._quitting = True
        self.effects.stop()
        self.forza_telemetry.stop()
        self.dsx_server.stop()
        self.controller.disconnect()
        self.tray.stop()
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        import os
        os._exit(0)

    # --- Device & Input Callbacks ---
    def reconnect_controller(self):
        if self.controller.is_connected:
            self.controller.disconnect()
        connected = self.controller.connect()
        if not connected:
            self.conn_dot_var.set("○")
            self.conn_text_var.set("Disconnected")
            self.dot_lbl.configure(fg=CLR_RED)
            self.conn_lbl.configure(fg=CLR_TEXT_MUTED)
            self.battery_text_var.set("--%")
        self._update_tray_tooltip()

    def _on_connection_changed(self, connected: bool, desc: str):
        if connected:
            self.conn_dot_var.set("●")
            self.conn_text_var.set(desc)
            self.dot_lbl.configure(fg=CLR_GREEN)
            self.conn_lbl.configure(fg=CLR_GREEN)
            self._send_manual_triggers()
        else:
            self.conn_dot_var.set("○")
            self.conn_text_var.set("Disconnected")
            self.dot_lbl.configure(fg=CLR_RED)
            self.conn_lbl.configure(fg=CLR_TEXT_MUTED)
            self.battery_text_var.set("--%")
        self._update_tray_tooltip()

    def _on_input_update(self, state):
        charge_tag = " ⚡" if state.is_charging else ""
        self.battery_text_var.set(f"{state.battery_level}%{charge_tag}")
        self.effects.set_battery_state(state.battery_level, state.is_charging)

        # PulseCore Link diagnostics
        rate = self.controller.polling_rate_hz
        lat = self.controller.input_latency_ms
        self.polling_text_var.set(f"{rate:.0f} Hz ({lat:.1f} ms)")

        if hasattr(self, 'diag_details_lbl'):
            is_bt = (self.controller.connection_type == ConnectionType.BLUETOOTH)
            status = "⚠️ High Jitter" if (is_bt and lat > 20.0) else "Optimal"
            self.diag_details_lbl.configure(text=f"Polling Rate: {rate:.0f} Hz | Latency: {lat:.1f} ms | Link: {status}")
            if status == "⚠️ High Jitter":
                self.polling_pill.configure(bg="#451a03")
            else:
                self.polling_pill.configure(bg="#1e293b")

        # PulseCore Auto Headphone Switch
        if hasattr(state, 'headphones_connected'):
            if state.headphones_connected != self._last_headphone_state:
                self._last_headphone_state = state.headphones_connected
                status_str = "Connected (3.5mm)" if state.headphones_connected else "Unplugged (Speaker)"
                self.headphone_status_var.set(status_str)
                if self.auto_switch_audio_var.get():
                    if state.headphones_connected:
                        self.audio_route_var.set("Headphone (3.5mm Jack)")
                        self.audio.set_target("headphone")
                    else:
                        self.audio_route_var.set("Speaker (Controller)")
                        self.audio.set_target("speaker")

        # Air Mouse (Gyro) and Touchpad Processing
        if self.air_mouse_var.get():
            self.mouse.process_gyro(state.gyro_x, state.gyro_y, state.gyro_z, state.l2, state.r2)

        if self.touch_mouse_var.get():
            btn_shortcuts = self.mouse_buttons_var.get()
            self.mouse.process_touch(
                state.touch1_active, state.touch1_x, state.touch1_y,
                state.touch2_active, state.touch2_x, state.touch2_y,
                state.touchpad_click,
                l1=state.l1 if btn_shortcuts else False,
                r1=state.r1 if btn_shortcuts else False,
                r3=state.r3 if btn_shortcuts else False,
                dpad=state.dpad if btn_shortcuts else 8
            )

    # --- Lightbar Effects & Hue Color Engine ---
    def _on_effect_selected(self, event=None):
        name = self.light_effect_var.get()
        for eff in LightEffect:
            if eff.value == name:
                self.effects.set_effect(eff)
                break

    def _update_effect_speed(self, val):
        self.effects.speed = float(val)

    def _on_hue_slider_change(self, val=None):
        self._apply_hsv_color(is_white=False)

    def _on_brightness_slider_change(self, val=None):
        self._apply_hsv_color(is_white=False)

    def _set_color_preset(self, hue: float, brightness: float, is_white: bool = False):
        self.hue_var.set(hue)
        self.brightness_var.set(brightness)
        self._apply_hsv_color(is_white=is_white)

    def _apply_hsv_color(self, is_white: bool = False):
        if self._updating_color_ui:
            return
        self._updating_color_ui = True
        try:
            hue = self.hue_var.get()
            brightness = self.brightness_var.get()
            sat = 0.0 if is_white else 1.0

            h = (hue % 360.0) / 360.0
            v = max(0.0, min(1.0, brightness / 100.0))
            r_f, g_f, b_f = colorsys.hsv_to_rgb(h, sat, v)
            r, g, b = int(round(r_f * 255)), int(round(g_f * 255)), int(round(b_f * 255))

            self.rgb_r_var.set(r)
            self.rgb_g_var.set(g)
            self.rgb_b_var.set(b)

            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            text_color = "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 140 else "#ffffff"

            if hasattr(self, 'swatch_box'):
                lbl_h = "White" if is_white else f"Hue: {hue:.0f}°"
                self.swatch_box.configure(
                    bg=hex_color,
                    fg=text_color,
                    text=f"{hex_color.upper()}  •  RGB({r}, {g}, {b})  •  {lbl_h}  •  {brightness:.0f}%"
                )
            if hasattr(self, 'hue_lbl'):
                self.hue_lbl.configure(text=f"Color Hue ({hue:.0f}°):")
            if hasattr(self, 'bright_lbl'):
                self.bright_lbl.configure(text=f"Brightness ({brightness:.0f}%):")

            self.effects.set_base_color(r, g, b)
            if self.light_effect_var.get() == LightEffect.STATIC.value and self.controller.is_connected:
                self.controller.update_led(r, g, b)
        finally:
            self._updating_color_ui = False

    def _sync_hsv_from_rgb(self):
        if self._updating_color_ui:
            return
        self._updating_color_ui = True
        try:
            r, g, b = self.rgb_r_var.get(), self.rgb_g_var.get(), self.rgb_b_var.get()
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            self.hue_var.set(round(h * 360.0, 1))
            self.brightness_var.set(round(v * 100.0, 1))

            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            text_color = "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 140 else "#ffffff"
            if hasattr(self, 'swatch_box'):
                self.swatch_box.configure(
                    bg=hex_color,
                    fg=text_color,
                    text=f"{hex_color.upper()}  •  RGB({r}, {g}, {b})  •  Hue: {h * 360.0:.0f}°  •  {v * 100.0:.0f}%"
                )
            if hasattr(self, 'hue_lbl'):
                self.hue_lbl.configure(text=f"Color Hue ({h * 360.0:.0f}°):")
            if hasattr(self, 'bright_lbl'):
                self.bright_lbl.configure(text=f"Brightness ({v * 100.0:.0f}%):")
            self.effects.set_base_color(r, g, b)
        finally:
            self._updating_color_ui = False

    def _on_rgb_slider_change(self, val=None):
        self._sync_hsv_from_rgb()

    def _on_effect_color_update(self, r: int, g: int, b: int):
        if self.controller.is_connected:
            self.controller.update_led(r, g, b)

    # --- PulseCore Master Rumble, Idle Auto-Sleep, and Mic Mute ---
    def _on_rumble_gain_change(self, val):
        gain = float(val) / 100.0
        self.controller.master_rumble_gain = gain
        if hasattr(self, 'rumble_lbl'):
            self.rumble_lbl.configure(text=f"{int(float(val))}%")

    def _on_idle_sleep_selected(self, event=None):
        choice = self.idle_sleep_var.get()
        timeouts = {
            "Disabled": 0,
            "5 minutes": 300,
            "10 minutes": 600,
            "15 minutes": 900,
            "30 minutes": 1800
        }
        seconds = timeouts.get(choice, 600)
        self.controller.idle_timeout_seconds = seconds

    def _on_controller_mute_toggled(self, is_muted: bool):
        self.is_mic_muted_var.set(is_muted)
        if is_muted:
            self.mic_status_var.set("🔇 Mic: MUTED")
            self.mic_pill.configure(bg="#450a0a")
        else:
            self.mic_status_var.set("🎙️ Mic: ON")
            self.mic_pill.configure(bg="#1e293b")

    def _toggle_mic_mute_ui(self):
        if not self.controller.is_connected:
            return
        new_state = not self.controller.is_mic_muted
        self.controller.is_mic_muted = new_state
        self.controller.update_mute_led(1 if new_state else 0)
        self._on_controller_mute_toggled(new_state)

    def _on_controller_sleep_changed(self, is_sleeping: bool):
        if is_sleeping:
            self.conn_text_var.set("💤 Sleep (Idle)")
            self.dot_lbl.configure(fg=CLR_AMBER)
            self.conn_lbl.configure(fg=CLR_AMBER)
        else:
            conn_name = "Bluetooth" if self.controller.connection_type == ConnectionType.BLUETOOTH else "USB"
            self.conn_text_var.set(conn_name)
            self.dot_lbl.configure(fg=CLR_GREEN)
            self.conn_lbl.configure(fg=CLR_GREEN)
            self._apply_active_profile()

    def _export_diagnostics_report(self):
        diag = self.controller.get_diagnostics_report()
        report_lines = [
            "==================================================",
            " OpenDSZ Controller Diagnostic Bundle (PulseCore Mode)",
            "==================================================",
            f"Generated At: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Platform: {sys.platform} ({os.name})",
            f"Python Version: {sys.version.split()[0]}",
            "",
            "[Controller Hardware]",
            f"Connected: {diag['connected']}",
            f"Device: {diag['device_name']}",
            f"Connection Type: {diag['connection_type']}",
            f"Battery: {diag['battery_level']}% (Charging: {diag['is_charging']})",
            f"3.5mm Headset Jack: {'Connected' if diag['headphones_connected'] else 'Unplugged'}",
            f"Hardware Mic Mute: {'MUTED' if diag['is_mic_muted'] else 'Active'}",
            "",
            "[Link & Diagnostics]",
            f"Polling Rate: {diag['polling_rate_hz']} Hz",
            f"Packet Latency: {diag['latency_ms']} ms",
            f"Jitter Warning: {diag['jitter_warning']}",
            f"Idle Power Saving: {'Sleeping' if diag['is_sleeping'] else 'Active'}",
            f"Idle Timeout: {diag['idle_timeout_seconds']}s",
            f"Master Rumble Gain: {int(diag['master_rumble_gain'] * 100)}%",
            "",
            "[Software Engine Status]",
            f"Active Profile: {self.profile_mgr.active_profile_name}",
            f"Left Trigger Mode: {self.lt_mode_var.get()}",
            f"Right Trigger Mode: {self.rt_mode_var.get()}",
            f"Lightbar Effect: {self.light_effect_var.get()}",
            f"Lightbar Base RGB: ({self.rgb_r_var.get()}, {self.rgb_g_var.get()}, {self.rgb_b_var.get()})",
            f"Touchpad Mouse: {'Enabled' if self.touch_mouse_var.get() else 'Disabled'}",
            f"Forza UDP 5300 Telemetry: {'Listening' if self.forza_tel_var.get() else 'Disabled'}",
            f"DSX UDP 6969 Server: {'Listening' if self.dsx_udp_var.get() else 'Disabled'}",
            "=================================================="
        ]
        report_text = "\n".join(report_lines)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(report_text)
            messagebox.showinfo("Diagnostics Exported", "Full diagnostic bundle copied to clipboard!\nYou can paste it directly into GitHub issues or Discord.")
        except Exception:
            messagebox.showinfo("Diagnostics Export", report_text[:500] + "\n...")

    # --- Audio & Voice-Coil Haptics (Report 0x36) ---
    def _on_audio_route_changed(self, event=None):
        target = "headphone" if "Headphone" in self.audio_route_var.get() else "speaker"
        self.audio.set_target(target)

    def _on_volume_changed(self, val):
        vol = int(float(val))
        self.audio.set_volume(vol)
        if self.controller.is_connected:
            with self.controller._lock:
                self.controller.output_state.speaker_volume = vol
                self.controller.output_state.headphone_volume = vol

    def _test_speaker_audio(self):
        """Streams an ascending electronic chime directly through the built-in controller speaker."""
        if not self.controller.is_connected:
            messagebox.showwarning("Not Connected", "Please connect your DualSense controller first.")
            return

        def stream_chime():
            notes = [523.25, 659.25, 784.00, 1046.50] # C5, E5, G5, C6
            for freq in notes:
                for f_idx in range(10): # 100ms per note
                    audio_frame = self.audio.generate_speaker_tone_frame(freq_hz=freq, frame_idx=f_idx)
                    packet = self.audio.build_report_0x36(opus_frame=audio_frame)
                    self.controller.send_raw_report(packet)
                    time.sleep(0.01)

        threading.Thread(target=stream_chime, daemon=True).start()

    def _test_voice_coil_haptics(self):
        """Streams 150Hz PCM haptic packets over Bluetooth Report 0x36."""
        if not self.controller.is_connected:
            messagebox.showwarning("Not Connected", "Please connect your DualSense controller first.")
            return

        def stream_buzz():
            haptic_pcm = self.audio.generate_test_haptic_pcm(freq_hz=150.0, amplitude=1.0)
            for _ in range(25):
                packet = self.audio.build_report_0x36(haptic_frame=haptic_pcm)
                self.controller.send_raw_report(packet)
                time.sleep(0.01)

        threading.Thread(target=stream_buzz, daemon=True).start()

    def _test_abs_haptics(self):
        """Triggers 1.5 seconds of simulated ABS hydraulic vibration on L2."""
        if not self.controller.is_connected:
            messagebox.showwarning("Not Connected", "Please connect your DualSense controller first.")
            return

        def run_abs():
            self.controller.update_trigger_left(TriggerMode.PULSE, [14, 255, 2])
            self.controller.update_rumble(180, 0)
            time.sleep(1.5)
            self._send_manual_triggers()
            self.controller.update_rumble(0, 0)

        threading.Thread(target=run_abs, daemon=True).start()

    def _test_traction_haptics(self):
        """Triggers 1.5 seconds of simulated wheelspin chatter & impulse vibration on R2."""
        if not self.controller.is_connected:
            messagebox.showwarning("Not Connected", "Please connect your DualSense controller first.")
            return

        def run_spin():
            self.controller.update_trigger_right(TriggerMode.MACHINE_GUN, [13, 255, 2])
            self.controller.update_rumble(0, 210)
            time.sleep(1.5)
            self._send_manual_triggers()
            self.controller.update_rumble(0, 0)

        threading.Thread(target=run_spin, daemon=True).start()

    def _test_heavy_brake(self):
        """Applies 2 seconds of firm hydraulic brake pedal resistance on L2."""
        if not self.controller.is_connected:
            messagebox.showwarning("Not Connected", "Please connect your DualSense controller first.")
            return

        def run_stiff():
            self.controller.update_trigger_left(TriggerMode.RIGID, [2, 255])
            time.sleep(2.0)
            self._send_manual_triggers()

        threading.Thread(target=run_stiff, daemon=True).start()

    def _test_gear_shift_haptics(self):
        """Simulates a heavy transmission gear shift mechanical thump, trigger recoil, and shift confirmation flash."""
        if not self.controller.is_connected:
            messagebox.showwarning("Not Connected", "Please connect your DualSense controller first.")
            return

        def run_shift():
            self.effects.trigger_shift_flash()
            start = time.perf_counter()
            while True:
                elapsed = time.perf_counter() - start
                if elapsed >= 0.25:
                    break
                decay = max(0.0, (1.0 - elapsed / 0.25) ** 1.4)
                rumble_l = int(255 * decay)
                rumble_r = int(240 * decay)
                self.controller.update_rumble(rumble_l, rumble_r)
                self.controller.update_trigger_right(TriggerMode.VIBRATION, [30, int(255 * decay), 0])
                time.sleep(0.01)

            self.controller.update_rumble(0, 0)
            self._send_manual_triggers()

        threading.Thread(target=run_shift, daemon=True).start()

    def _on_forza_gear_shift(self, gear: int):
        self.effects.trigger_shift_flash()

    # --- Toggles & Profiles ---
    def _toggle_mouse(self):
        self.mouse.enabled = self.touch_mouse_var.get()

    def _toggle_air_mouse(self):
        is_air = self.air_mouse_var.get()
        self.mouse.air_mouse_enabled = is_air
        if is_air:
            # Configure DualSense adaptive triggers into firearm weapon stop mode (0x25)
            self.controller.update_trigger_left(TriggerMode.TRIGGER_STOP, [2, 7, 255])
            self.controller.update_trigger_right(TriggerMode.TRIGGER_STOP, [2, 7, 255])
            if self.controller.is_connected:
                def _confirm_pulse():
                    self.controller.trigger_haptic_pulse(left=180, right=220, duration_ms=30)
                    time.sleep(0.06)
                    self.controller.trigger_haptic_pulse(left=200, right=255, duration_ms=35)
                threading.Thread(target=_confirm_pulse, daemon=True).start()
        else:
            self.mouse.reset()
            self._send_manual_triggers()

    def _update_scroll_lines(self, *args):
        self.mouse.set_scroll_lines(self.scroll_lines_var.get())

    def _update_gyro_sens(self, val):
        self.mouse.set_gyro_sensitivity(float(val))

    def _update_gyro_deadzone(self, val):
        self.mouse.set_gyro_deadzone(int(float(val)))

    def _update_invert_pitch(self):
        self.mouse.invert_pitch = self.invert_pitch_var.get()

    def _toggle_touch_haptics(self):
        self.mouse.haptics_enabled = self.touch_haptics_var.get()

    def _toggle_mouse_buttons(self):
        self.mouse.controller_shortcuts_enabled = self.mouse_buttons_var.get()

    def _update_mouse_sens(self, val):
        self.mouse.sensitivity = float(val)

    def _on_mouse_haptic_feedback(self, feedback_type: str):
        if not self.touch_haptics_var.get() or not self.controller.is_connected:
            return

        if feedback_type == "down_left":
            # Solid MacBook Force Touch mechanical click-down
            self.controller.trigger_haptic_pulse(left=160, right=230, duration_ms=32)
        elif feedback_type == "up":
            # Subtle crisp mechanical switch release
            self.controller.trigger_haptic_pulse(left=40, right=90, duration_ms=18)
        elif feedback_type == "tap":
            # Feather-light tap-to-click tick
            self.controller.trigger_haptic_pulse(left=70, right=140, duration_ms=22)
        elif feedback_type == "down_right":
            # Distinctive double micro-tick confirming right click
            def _double_tick():
                self.controller.trigger_haptic_pulse(left=90, right=190, duration_ms=16)
                time.sleep(0.025)
                self.controller.trigger_haptic_pulse(left=110, right=220, duration_ms=20)
            threading.Thread(target=_double_tick, daemon=True).start()
        elif feedback_type == "down_middle":
            # Deep center wheel-click thud
            self.controller.trigger_haptic_pulse(left=220, right=130, duration_ms=38)
        elif feedback_type == "scroll":
            # Faint ratcheting detent tick
            self.controller.trigger_haptic_pulse(left=0, right=85, duration_ms=12)
        elif feedback_type == "gun_recoil_right":
            # Sharp gunshot recoil kick on R2 break (dominant right motor pulse)
            self.controller.trigger_haptic_pulse(left=160, right=255, duration_ms=40)
        elif feedback_type == "gun_recoil_left":
            # Sharp gunshot recoil kick on L2 break (dominant left motor pulse)
            self.controller.trigger_haptic_pulse(left=255, right=160, duration_ms=40)
        elif feedback_type == "gun_reset":
            # Crisp mechanical reset tick on trigger release
            self.controller.trigger_haptic_pulse(left=35, right=65, duration_ms=15)

    def _test_macbook_haptic_click(self):
        """Simulates a full MacBook Force Touch click-down followed by click-up release."""
        if not self.controller.is_connected:
            messagebox.showwarning("Not Connected", "Please connect your DualSense controller first.")
            return

        def _test():
            self._on_mouse_haptic_feedback("down_left")
            time.sleep(0.12)
            self._on_mouse_haptic_feedback("up")

        threading.Thread(target=_test, daemon=True).start()

    def _on_forza_port_change(self):
        try:
            p = int(self.forza_port_var.get())
            if 1 <= p <= 65535:
                self.forza_telemetry.set_port(p)
                if self.forza_tel_var.get():
                    self.forza_status_var.set(f"📡 Telemetry: Listening on port {p} (In Forza: Data Out=ON, Port={p})")
        except ValueError:
            pass

    def _toggle_forza_telemetry(self):
        if self.forza_tel_var.get():
            self._on_forza_port_change()
            self.forza_telemetry.start()
            self.forza_status_var.set(f"📡 Telemetry: Waiting for Forza packets on port {self.forza_port_var.get()}...")
            if hasattr(self, 'forza_status_lbl'):
                self.forza_status_lbl.configure(fg="#38bdf8")
        else:
            self.forza_telemetry.stop()
            self.forza_status_var.set("📡 Telemetry: Disabled")
            if hasattr(self, 'forza_status_lbl'):
                self.forza_status_lbl.configure(fg="#94a3b8")
            self._send_manual_triggers()
            if self.controller.is_connected:
                self.controller.update_rumble(0, 0)

    def _on_forza_telemetry_stats(self, stats: dict):
        def update():
            if not self.forza_tel_var.get():
                return
            hz = stats.get("packet_hz", 0.0)
            spd = stats.get("speed_mph", 0.0)
            rpm = stats.get("rpm", 0)
            gear = stats.get("gear", 0)
            thr = int(stats.get("throttle", 0) / 2.55)
            brk = int(stats.get("brake", 0) / 2.55)
            event = stats.get("event", "Waiting")
            is_racing = stats.get("is_race_on", False)

            if not hasattr(self, 'forza_status_lbl'):
                return

            if hz > 0:
                gear_str = "R" if gear == 0 else (f"G{gear}" if gear > 0 else "N")
                self.forza_status_var.set(
                    f"📡 Telemetry: 🟢 {hz:.0f} Hz | {spd:.0f} mph | {gear_str} {rpm:,} RPM | Thr: {thr}% | Brk: {brk}% | {event}"
                )
                if "Gear Shift" in event:
                    self.forza_status_lbl.configure(fg="#38bdf8") # Electric cyan
                elif "Traction Loss" in event or "Chirp" in event:
                    self.forza_status_lbl.configure(fg="#f59e0b") # Amber / orange
                elif "ABS" in event:
                    self.forza_status_lbl.configure(fg="#ef4444") # Red
                else:
                    self.forza_status_lbl.configure(fg="#4ade80") # Soft green

                # Auto-activate dynamic RPM Shift Light (live tachometer) when Forza connects
                if not getattr(self, "_forza_telemetry_active", False):
                    self._forza_telemetry_active = True
                    self._saved_user_light_effect = self.light_effect_var.get()
                    self.light_effect_var.set(LightEffect.RPM_SHIFT.value)
                    self.effects.set_effect(LightEffect.RPM_SHIFT)
            else:
                self.forza_status_var.set(
                    f"📡 Telemetry: ⏳ Waiting for Forza on port {self.forza_port_var.get()} (In Forza: Data Out=ON, IP=127.0.0.1)"
                )
                self.forza_status_lbl.configure(fg="#38bdf8")

                if getattr(self, "_forza_telemetry_active", False):
                    self._forza_telemetry_active = False
                    if hasattr(self, "_saved_user_light_effect") and self._saved_user_light_effect:
                        self.light_effect_var.set(self._saved_user_light_effect)
                        self._on_effect_selected()

        try:
            self.root.after_idle(update)
        except Exception:
            pass

    def _toggle_dsx_server(self):
        if self.dsx_udp_var.get():
            self.dsx_server.start()
        else:
            self.dsx_server.stop()

    def _on_forza_trigger_update(self, l_mode, l_params, r_mode, r_params, rumble_left=0, rumble_right=0):
        if self.controller.is_connected and self.forza_tel_var.get():
            self.controller.update_trigger_left(l_mode, l_params)
            self.controller.update_trigger_right(r_mode, r_params)
            self.controller.update_rumble(rumble_left, rumble_right)

    def _on_dsx_trigger_update(self, side: str, mode, params):
        if self.controller.is_connected and self.dsx_udp_var.get():
            if side == "left":
                self.controller.update_trigger_left(mode, params)
            else:
                self.controller.update_trigger_right(mode, params)

    def _on_dsx_rgb_update(self, r: int, g: int, b: int):
        self.rgb_r_var.set(r)
        self.rgb_g_var.set(g)
        self.rgb_b_var.set(b)
        self._on_rgb_slider_change()

    def _get_mode_from_name(self, name: str) -> TriggerMode:
        for label, mode in ALL_MODE_OPTIONS:
            if label == name:
                return mode
        # Fallback keyword matching
        name_lower = name.lower()
        if "traction" in name_lower or "machine" in name_lower:
            return TriggerMode.MACHINE_GUN
        if "gallop" in name_lower:
            return TriggerMode.GALLOP
        if "rigid" in name_lower or "resistance" in name_lower:
            return TriggerMode.RIGID
        if "stop" in name_lower or "cut" in name_lower:
            return TriggerMode.TRIGGER_STOP
        if "pulse" in name_lower or "abs" in name_lower:
            return TriggerMode.PULSE
        if "bow" in name_lower:
            return TriggerMode.BOW
        return TriggerMode.OFF

    def _apply_trigger_presets(self, event=None):
        self._send_manual_triggers()

    def _send_manual_triggers(self):
        if not self.controller.is_connected:
            return

        l_mode = self._get_mode_from_name(self.lt_mode_var.get())
        r_mode = self._get_mode_from_name(self.rt_mode_var.get())

        l_force = self.lt_force_var.get()
        l_start = self.lt_start_var.get()
        l_freq = self.lt_freq_var.get()

        r_force = self.rt_force_var.get()
        r_start = self.rt_start_var.get()
        r_freq = self.rt_freq_var.get()

        if l_mode == TriggerMode.RIGID:
            l_params = [l_start, l_force]
        elif l_mode == TriggerMode.TRIGGER_STOP:
            l_params = [l_start, 100, l_force]
        elif l_mode in (TriggerMode.PULSE, TriggerMode.MACHINE_GUN, TriggerMode.GALLOP):
            l_params = [l_freq, l_force, l_start]
        elif l_mode == TriggerMode.BOW:
            l_params = [l_start, 120, l_force, 80]
        else:
            l_params = [0] * 10

        if r_mode == TriggerMode.RIGID:
            r_params = [r_start, r_force]
        elif r_mode == TriggerMode.TRIGGER_STOP:
            r_params = [r_start, 100, r_force]
        elif r_mode in (TriggerMode.PULSE, TriggerMode.MACHINE_GUN, TriggerMode.GALLOP):
            r_params = [r_freq, r_force, r_start]
        elif r_mode == TriggerMode.BOW:
            r_params = [r_start, 120, r_force, 80]
        else:
            r_params = [0] * 10

        self.controller.update_trigger_left(l_mode, l_params)
        self.controller.update_trigger_right(r_mode, r_params)

    def _on_profile_selected(self, event=None):
        name = self.prof_combo.get()
        self.profile_mgr.active_profile_name = name
        self._apply_active_profile()

    def _apply_active_profile(self):
        prof = self.profile_mgr.get_active_profile()
        t_left = prof.get("triggers", {}).get("left", {})
        t_right = prof.get("triggers", {}).get("right", {})
        l_mode = TriggerMode(t_left.get("mode", 0))
        r_mode = TriggerMode(t_right.get("mode", 0))

        for label, mode in LT_MODE_OPTIONS:
            if mode == l_mode:
                self.lt_mode_var.set(label)
                break
        for label, mode in RT_MODE_OPTIONS:
            if mode == r_mode:
                self.rt_mode_var.set(label)
                break

        touch_cfg = prof.get("touchpad", {})
        self.touch_mouse_var.set(touch_cfg.get("enabled", False))
        self.mouse.enabled = self.touch_mouse_var.get()
        self.mouse_sens_var.set(touch_cfg.get("sensitivity", 0.2))
        self.mouse.sensitivity = self.mouse_sens_var.get()
        self.scroll_lines_var.set(touch_cfg.get("scroll_lines", 3))
        self.mouse.set_scroll_lines(self.scroll_lines_var.get())
        self.air_mouse_var.set(touch_cfg.get("air_mouse", False))
        self.mouse.air_mouse_enabled = self.air_mouse_var.get()
        self.touch_haptics_var.set(touch_cfg.get("haptics", True))
        self.mouse.haptics_enabled = self.touch_haptics_var.get()
        self.mouse_buttons_var.set(touch_cfg.get("shortcuts", True))
        self.mouse.controller_shortcuts_enabled = self.mouse_buttons_var.get()

        tel_cfg = prof.get("telemetry", {})
        if tel_cfg.get("protocol") == "ForzaDataOut" or tel_cfg.get("enabled", False):
            self.forza_tel_var.set(True)
            self._toggle_forza_telemetry()

        rumble_cfg = prof.get("rumble", {})
        gain = rumble_cfg.get("master_gain", 1.0)
        self.master_rumble_var.set(int(gain * 100))
        self.controller.master_rumble_gain = gain
        if hasattr(self, 'rumble_lbl'):
            self.rumble_lbl.configure(text=f"{int(gain * 100)}%")

        led_cfg = prof.get("led", {})
        self.rgb_r_var.set(led_cfg.get("r", 0))
        self.rgb_g_var.set(led_cfg.get("g", 120))
        self.rgb_b_var.set(led_cfg.get("b", 255))
        self._sync_hsv_from_rgb()
        eff_name = led_cfg.get("effect", None)
        if eff_name:
            matched = False
            for opt in EFFECT_OPTIONS:
                if eff_name == opt or (eff_name.startswith("RPM Shift") and opt.startswith("RPM Shift")):
                    self.light_effect_var.set(opt)
                    self._on_effect_selected()
                    matched = True
                    break
            if not matched and eff_name in EFFECT_OPTIONS:
                self.light_effect_var.set(eff_name)
                self._on_effect_selected()
        self._send_manual_triggers()

    def _save_current_profile(self):
        name = self.prof_combo.get()
        l_mode = self._get_mode_from_name(self.lt_mode_var.get())
        r_mode = self._get_mode_from_name(self.rt_mode_var.get())

        data = {
            "name": name,
            "telemetry": {
                "enabled": self.forza_tel_var.get(),
                "protocol": "ForzaDataOut" if self.forza_tel_var.get() else "None",
                "port": 5300
            },
            "triggers": {
                "left": {"mode": int(l_mode), "params": [self.lt_start_var.get(), self.lt_force_var.get()]},
                "right": {"mode": int(r_mode), "params": [self.rt_start_var.get(), self.rt_force_var.get()]}
            },
            "rumble": {
                "master_gain": self.controller.master_rumble_gain
            },
            "touchpad": {
                "enabled": self.touch_mouse_var.get(),
                "sensitivity": self.mouse_sens_var.get(),
                "scroll_lines": self.scroll_lines_var.get(),
                "air_mouse": self.air_mouse_var.get(),
                "haptics": self.touch_haptics_var.get(),
                "shortcuts": self.mouse_buttons_var.get()
            },
            "led": {
                "r": self.rgb_r_var.get(),
                "g": self.rgb_g_var.get(),
                "b": self.rgb_b_var.get(),
                "effect": self.light_effect_var.get()
            }
        }
        self.profile_mgr.save_profile(name, data)
        messagebox.showinfo("Profile Saved", f"Profile '{name}' has been saved successfully.")

    def _create_new_profile(self):
        new_name = simpledialog.askstring("New Profile", "Enter Profile Name:")
        if new_name:
            self.profile_mgr.save_profile(new_name, {"name": new_name})
            self.prof_combo["values"] = list(self.profile_mgr.profiles.keys())
            self.prof_combo.set(new_name)
            self._on_profile_selected()

    def _download_profile_dialog(self):
        url = simpledialog.askstring("Community Profile Download", "Enter URL to Profile JSON template (e.g. GitHub raw URL):")
        if url:
            res = self.profile_mgr.download_community_profile(url)
            if res:
                self.prof_combo["values"] = list(self.profile_mgr.profiles.keys())
                self.prof_combo.set(res)
                self._on_profile_selected()
                messagebox.showinfo("Success", f"Imported community profile: {res}")
            else:
                messagebox.showerror("Download Error", "Could not download or parse profile template.")
