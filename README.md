# HEOS Integration for Unfolded Circle Remote 2/3

Control your **Denon / Marantz HEOS** multi-room audio system directly from your Unfolded Circle Remote 2 or Remote 3. Play/pause, volume, mute, favorites and source selection, media browsing, multi-room grouping, and per-player info sensors - for **every HEOS player on your account**, controlled locally over your network.

![HEOS](https://img.shields.io/badge/HEOS-Multi--Room%20Audio-blue)
[![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-heos?style=flat-square)](https://github.com/mase1981/uc-intg-heos/releases)
![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)
[![GitHub issues](https://img.shields.io/github/issues/mase1981/uc-intg-heos?style=flat-square)](https://github.com/mase1981/uc-intg-heos/issues)
[![Community Forum](https://img.shields.io/badge/community-forum-blue?style=flat-square)](https://unfolded.community/)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-heos/total?style=flat-square)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg?style=flat-square)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA&style=flat-square)](https://github.com/sponsors/mase1981)

## Supported Devices

Any Denon or Marantz device with **HEOS built-in**, discovered automatically from your HEOS account, including: **AVR receivers** (Denon AVR-X / Marantz SR / NR series), **soundbars** (HEOS Bar, Denon Home Sound Bar), **speakers** (HEOS 1 / 3 / 5 / 7), and the **Denon Home 150 / 250 / 350** series. AVR models are detected automatically and use a graceful shutdown (volume to 0 before stop).

## Features

- **🔊 Media player** - per player: play / pause / stop, next / previous, volume + mute, repeat (off / all / one), shuffle, now-playing (track, artist, album, artwork, progress), and source selection.
- **📚 Media browser** - browse and play favorites, input sources, and connected music services (Spotify, TuneIn, Pandora, etc.) with nested catalog navigation directly from the Remote UI.
- **🎛️ Remote entity** - the full button surface as simple commands for Activities (transport, volume, mute, repeat / shuffle, inputs, grouping) with physical button mapping and ready-made button pages.
- **🔗 Multi-room grouping** - group and ungroup players from the remote's grouping page (shown when more than one player is present).
- **🎚️ Input select** - quick input switching per player (AUX, HDMI, Optical, Coaxial, Bluetooth).
- **ℹ️ Info sensors** - model, network type, IP address, and firmware per player.
- **🎚️ Configurable volume step** - choose the volume up/down step size (1-25) during setup.
- **♻️ Self-healing** - detects connection loss (network blips, device reboots, Remote standby) and reconnects automatically, keeping entity state in sync without re-running setup.
- **Multi-device** - every HEOS player on your account gets its own set of entities.

---
## ❤️ Support Development ❤️

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

Your support helps maintain this integration. Thank you! ❤️
---

## How It Works

HEOS exposes a local control protocol (the HEOS CLI on port 1255). The integration connects to one HEOS device on your network and uses your HEOS account to enumerate the whole system:

- **One connection, all players** - connect to any single HEOS device and every player on the account is discovered.
- **Account for favorites & services** - your HEOS account is used to load favorites and music services; playback and control run locally over your network.
- **State follows the system** - player state, now-playing, volume, and grouping are kept live via HEOS events plus periodic polling.
- **Resilient** - if the connection drops, the integration marks entities unavailable, reconnects automatically, and restores state - no re-setup required.

## Requirements

- One or more Denon / Marantz HEOS devices on the same network as your Remote.
- A (free) HEOS account, with your devices already set up in the HEOS app.
- The IP address of any one HEOS device on your network.
- Unfolded Circle Remote 2 / 3 with firmware supporting custom integrations.

## Installation

### Option 1: Remote Web Interface (Recommended)

1. Download the latest `uc-intg-heos-<version>-aarch64.tar.gz` from the [**Releases**](https://github.com/mase1981/uc-intg-heos/releases) page.
2. Open your Remote's web interface (`http://your-remote-ip`).
3. Go to **Settings -> Integrations -> Add Integration -> Install Custom** and upload the `.tar.gz`.

### Option 2: Docker (Advanced Users)

**Image**: `ghcr.io/mase1981/uc-intg-heos:latest`

**Docker Compose:**
```yaml
services:
  uc-intg-heos:
    image: ghcr.io/mase1981/uc-intg-heos:latest
    container_name: uc-intg-heos
    network_mode: host
    volumes:
      - ./config:/config
    environment:
      - UC_CONFIG_HOME=/config
      - UC_INTEGRATION_HTTP_PORT=9090
      - UC_INTEGRATION_INTERFACE=0.0.0.0
      - PYTHONPATH=/app
    restart: unless-stopped
```

**Docker Run:**
```bash
docker run -d --name uc-intg-heos --restart unless-stopped --network host -v $(pwd)/config:/config -e UC_CONFIG_HOME=/config -e UC_INTEGRATION_INTERFACE=0.0.0.0 -e UC_INTEGRATION_HTTP_PORT=9090 -e PYTHONPATH=/app ghcr.io/mase1981/uc-intg-heos:latest
```

## Configuration

HEOS uses **account-based** setup. Make sure your devices are already configured in the HEOS app, then start setup and enter:

- **HEOS Device IP** - any HEOS device on your network.
- **HEOS Account Email** / **Password** - your HEOS account credentials.
- **Volume Step** - the volume up/down step size (1-25, default 5).

The integration connects, authenticates, and discovers **all** players on your account automatically.

For each player the integration creates:

| Entity | Purpose |
|--------|---------|
| **Media player** (`media_player.heos_<ip>.<player_id>`) | Transport, volume, mute, repeat / shuffle, now-playing, source selection, and media browsing. |
| **Remote** (`remote.heos_<ip>.<player_id>`) | Full command surface with button pages (transport, volume, inputs, grouping) for Activities. |
| **Select** (`select.heos_<ip>.<player_id>.input`) | Input source switching. |
| **Sensors** (`sensor.heos_<ip>.<player_id>.<type>`) | Model, network, IP address, and firmware. |

### Network Requirements

- HEOS devices on the same network / subnet as the Remote.
- Port 1255 (HEOS CLI) reachable - used automatically.
- Wired connection and static IP recommended for stability.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Cannot connect during setup | Verify the IP belongs to a HEOS device on the same subnet and that port 1255 is reachable; confirm your account email/password. |
| Players show as unavailable | The integration reconnects automatically after a network/device blip; if it does not recover, confirm the device is online and re-run setup. |
| Authentication failed | Re-check your HEOS account email and password (the same ones you use in the HEOS app). |
| Favorites or music services missing | Favorites and services come from your HEOS account - add them in the HEOS app first. |
| Grouping page missing | The grouping page only appears when more than one HEOS player is detected. |

## Credits

- **Developer**: Meir Miyara
- **HEOS protocol**: built on the [pyheos](https://github.com/andrewsayre/pyheos) library.
- **Unfolded Circle**: Remote 2/3 integration framework ([ucapi](https://github.com/unfoldedcircle/integration-python-library) / [ucapi-framework](https://github.com/JackJPowell/ucapi-framework)).

## License

Mozilla Public License 2.0 (MPL-2.0) - see the LICENSE file.

## Support & Community

- **GitHub Issues**: [Report bugs and request features](https://github.com/mase1981/uc-intg-heos/issues)
- **UC Community Forum**: [General discussion and support](https://unfolded.community/)
- **Developer**: [Meir Miyara](https://www.linkedin.com/in/meirmiyara)

---

**Made with ❤️ for the Unfolded Circle Community**

**Thank You**: Meir Miyara
