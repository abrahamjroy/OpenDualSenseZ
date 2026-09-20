"""
OpenDSX Game Profile & Template Manager
Handles loading, saving, active window auto-switching, and community template sharing.
"""

import os
import json
import urllib.request
from typing import Dict, List, Optional, Any
from .protocol import TriggerMode

DEFAULT_PROFILES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "profiles"))

DEFAULT_FORZA_PROFILE = {
    "name": "Forza Horizon 5 (Steam)",
    "description": "Dynamic ABS brake vibration, tire traction loss kickback, and gear shift clunk",
    "steam_app_id": 1551360,
    "process_names": ["forzahorizon6.exe", "ForzaHorizon6.exe", "ForzaHorizon5.exe", "ForzaHorizon4.exe"],
    "telemetry": {
        "enabled": True,
        "protocol": "ForzaDataOut",
        "port": 5300,
        "abs_sensitivity": 1.05,
        "traction_sensitivity": 1.10
    },
    "triggers": {
        "left": {
            "mode": int(TriggerMode.RIGID),
            "params": [5, 180, 0, 0, 0, 0, 0, 0, 0, 0]
        },
        "right": {
            "mode": int(TriggerMode.RIGID),
            "params": [5, 80, 0, 0, 0, 0, 0, 0, 0, 0]
        }
    },
    "touchpad": {
        "enabled": False,
        "sensitivity": 1.2
    },
    "led": {
        "r": 255,
        "g": 60,
        "b": 0,
        "effect": "RPM Shift Light (Forza)"
    }
}

DEFAULT_CYBERPUNK_PROFILE = {
    "name": "Cyberpunk 2077 (Steam)",
    "description": "DSX mod integration with automatic weapon feedback and vehicle triggers",
    "steam_app_id": 1091500,
    "process_names": ["Cyberpunk2077.exe"],
    "telemetry": {
        "enabled": True,
        "protocol": "DSX_UDP",
        "port": 6969
    },
    "triggers": {
        "left": {
            "mode": int(TriggerMode.TRIGGER_STOP),
            "params": [10, 100, 200, 0, 0, 0, 0, 0, 0, 0]
        },
        "right": {
            "mode": int(TriggerMode.RIGID),
            "params": [0, 120, 0, 0, 0, 0, 0, 0, 0, 0]
        }
    },
    "touchpad": {
        "enabled": False,
        "sensitivity": 1.0
    },
    "led": {
        "r": 0,
        "g": 255,
        "b": 230
    }
}

DEFAULT_DESKTOP_PROFILE = {
    "name": "Desktop Navigation",
    "description": "Touchpad as smooth desktop mouse with tap-to-click and gesture scroll",
    "steam_app_id": 0,
    "process_names": [],
    "telemetry": {
        "enabled": False,
        "protocol": "None",
        "port": 0
    },
    "triggers": {
        "left": {
            "mode": int(TriggerMode.OFF),
            "params": [0] * 10
        },
        "right": {
            "mode": int(TriggerMode.OFF),
            "params": [0] * 10
        }
    },
    "touchpad": {
        "enabled": True,
        "sensitivity": 0.2,
        "scroll_lines": 3,
        "air_mouse": False,
        "haptics": True,
        "shortcuts": True
    },
    "led": {
        "r": 0,
        "g": 120,
        "b": 255
    }
}


class ProfileManager:
    def __init__(self, profiles_dir: str = DEFAULT_PROFILES_DIR):
        self.profiles_dir = profiles_dir
        os.makedirs(self.profiles_dir, exist_ok=True)
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.active_profile_name: str = "Desktop Navigation"
        self._ensure_defaults()
        self.load_all()

    def _ensure_defaults(self):
        defaults = {
            "forza_horizon_5.json": DEFAULT_FORZA_PROFILE,
            "cyberpunk_2077.json": DEFAULT_CYBERPUNK_PROFILE,
            "desktop_mouse.json": DEFAULT_DESKTOP_PROFILE,
        }
        for fname, data in defaults.items():
            fpath = os.path.join(self.profiles_dir, fname)
            if not os.path.exists(fpath):
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

    def load_all(self):
        self.profiles.clear()
        for fname in os.listdir(self.profiles_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.profiles_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        name = data.get("name", os.path.splitext(fname)[0])
                        self.profiles[name] = data
                except Exception:
                    pass

        if self.active_profile_name not in self.profiles and self.profiles:
            self.active_profile_name = next(iter(self.profiles))

    def save_profile(self, name: str, data: Dict[str, Any]):
        filename = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name.lower()) + ".json"
        fpath = os.path.join(self.profiles_dir, filename)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.profiles[name] = data

    def get_active_profile(self) -> Dict[str, Any]:
        return self.profiles.get(self.active_profile_name, DEFAULT_DESKTOP_PROFILE)

    def download_community_profile(self, url: str) -> Optional[str]:
        """Downloads a community profile JSON template from a public URL or GitHub raw."""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'OpenDSZ-App/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                content = response.read().decode('utf-8')
                data = json.loads(content)
                name = data.get("name", "Community Profile")
                self.save_profile(name, data)
                return name
        except Exception:
            return None
