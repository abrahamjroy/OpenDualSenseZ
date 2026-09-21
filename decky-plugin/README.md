# OpenDSZ Decky Loader Plugin (SteamOS Game Mode)

**OpenDSZ for Decky Loader** integrates DualSense controller management directly into the Steam Deck Quick Access Menu (`...` button) in SteamOS Game Mode.

---

## Highlights & Features

- **SteamOS Game Mode Integration**: Adjust controller settings directly from the Decky Quick Access Menu without exiting games.
- **Controller Diagnostics**: Live connection type (Bluetooth vs USB), battery percentage, charging state, and polling rate (Hz).
- **One-Click Profile Switching**: Switch between Forza Horizon 5, Rocket League, Cyberpunk 2077, and Desktop navigation.
- **Ferrari F1 Dynamic Rev Lights**: Synchronized with game RPM telemetry (Red $\rightarrow$ Blue at shift point $\rightarrow$ Flashing Yellow/Gold at redline).
- **Adaptive Trigger Haptics**: ABS brake shudder and throttle resistance mapped in real-time from UDP telemetry.
- **Decoupled Daemon Architecture**: Communicates with the lightweight, zero-dependency OpenDSZ daemon on localhost port `5305`.

---

## Directory Structure

```text
decky-plugin/
├── plugin.json         # Decky Loader manifest
├── package.json        # Frontend npm dependencies & build scripts
├── tsconfig.json       # TypeScript configuration
├── rollup.config.js    # Rollup bundler config
├── src/
│   └── index.tsx       # React UI for the Steam Quick Access Menu
├── main.py             # Python backend bridge to OpenDSZ daemon
└── README.md           # Documentation & installation guide
```

---

## Building the Plugin

To compile the React frontend bundle for Decky Loader:

```bash
cd decky-plugin
pnpm install
pnpm run build
```

This generates `dist/index.js` bundled and ready for Decky Loader.

---

## Installation on Steam Deck

### Method 1: Local Development / Testing

1. Enable Developer Mode in SteamOS Settings $\rightarrow$ System $\rightarrow$ Developer Mode.
2. In the Decky Loader settings tab, enable **Developer settings**.
3. Copy the `decky-plugin` directory into your Deck's homebrew plugins folder:
   ```bash
   scp -r decky-plugin deck@<steam-deck-ip>:~/homebrew/plugins/OpenDSZ
   ```
4. Restart the Decky plugin loader or restart the Steam Deck:
   ```bash
   sudo systemctl restart plugin_loader
   ```
5. Press the Quick Access Menu (`...`) button on your Steam Deck—**OpenDSZ** will appear in the Decky plugin list!

---

## Preparing for Decky Store Submission

When submitting to the official [Decky Store](https://github.com/SteamDeckHomebrew/decky-plugin-database):
1. Tag a release on GitHub containing the built zip artifact (`OpenDSZ-Decky-v1.0.0.zip`).
2. Verify all icons and descriptions match `plugin.json`.
3. Submit a Pull Request to `SteamDeckHomebrew/decky-plugin-database` following their QA testing checklist.
