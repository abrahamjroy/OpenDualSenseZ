"""
OpenDSZ Cross-Platform System Tray Integration
Supports minimize-to-tray, restore on click, battery/status tooltip, and clean shutdown.
"""

import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw

try:
    import pystray
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

def create_default_icon_image() -> Image.Image:
    """Generates a clean 64x64 DualSense controller silhouette icon for the system tray."""
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Controller body (dark rounded rectangle)
    draw.rounded_rectangle([6, 14, 58, 52], radius=12, fill="#2563eb", outline="#60a5fa", width=2)
    # Handles
    draw.polygon([(10, 36), (6, 56), (18, 54)], fill="#1d4ed8")
    draw.polygon([(54, 36), (58, 56), (46, 54)], fill="#1d4ed8")
    # Touchpad area
    draw.rounded_rectangle([20, 18, 44, 32], radius=4, fill="#18181b", outline="#93c5fd", width=1)
    # Analog sticks
    draw.ellipse([18, 36, 26, 44], fill="#1e293b", outline="#cbd5e1", width=1)
    draw.ellipse([38, 36, 46, 44], fill="#1e293b", outline="#cbd5e1", width=1)

    return img

class SystemTrayManager:
    def __init__(self, on_restore: Callable[[], None], on_quit: Callable[[], None]):
        self.on_restore = on_restore
        self.on_quit = on_quit
        self.icon: Optional['pystray.Icon'] = None
        self._thread: Optional[threading.Thread] = None
        self.status_text = "OpenDSZ - Controller Manager"

    def start(self):
        if not HAS_PYSTRAY or self.icon:
            return

        import os
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo_48.png")
        if os.path.exists(logo_path):
            try:
                image = Image.open(logo_path)
            except Exception:
                image = create_default_icon_image()
        else:
            image = create_default_icon_image()

        menu = pystray.Menu(
            pystray.MenuItem("Open OpenDSZ", self._on_restore_action, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit OpenDSZ", self._on_quit_action)
        )

        self.icon = pystray.Icon("OpenDSZ", image, self.status_text, menu=menu)
        self._thread = threading.Thread(target=self.icon.run, daemon=True, name="SystemTray-Thread")
        self._thread.start()

    def update_status(self, text: str):
        self.status_text = f"OpenDSZ: {text}"
        if self.icon:
            self.icon.title = self.status_text

    def _on_restore_action(self, icon=None, item=None):
        if self.on_restore:
            self.on_restore()

    def _on_quit_action(self, icon=None, item=None):
        self.stop()
        if self.on_quit:
            self.on_quit()

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
