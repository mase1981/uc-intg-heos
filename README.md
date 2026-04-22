# HEOS Integration for Unfolded Circle Remote Two/3

Control your Denon/Marantz HEOS devices directly from your Unfolded Circle Remote 2 or Remote 3 with comprehensive multi-room audio control.

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

---

## Support Development

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

---

## Features

### Account-Based Device Discovery
- **Single Sign-In** - Connect once with your HEOS account credentials
- **Auto-Discovery** - All HEOS devices on your account are automatically detected
- **Unified Control** - Every device gets its own set of entities

### Media Player
Each HEOS player gets a full-featured media player entity:
- Play, Pause, Stop, Next, Previous
- Volume control with mute toggle
- Repeat (Off / All / One) and Shuffle
- Now playing info: track, artist, album, artwork, progress and duration
- Source selection: favorites, input sources, music services

### Media Browser
Browse and play content directly from the Remote UI:
- **Favorites** - Your HEOS preset stations
- **Input Sources** - AUX, HDMI, Optical, Bluetooth, Coaxial
- **Music Services** - Spotify, TuneIn, Pandora, and all connected services
- Nested browsing into service catalogs with direct playback

### Remote Control
Each player gets a remote entity with custom UI pages:
- **Playback Page** - Transport controls, volume, mute
- **Modes Page** - Repeat, shuffle, input switching
- **Grouping Page** - Multi-room group management (when multiple players detected)
- Physical button mapping for volume, playback, and mute

### Sensor Entities
Per-player device information sensors:
- **Model** - Device model name (e.g., "Denon Home 250")
- **Network** - Connection type (wired/wifi)
- **IP Address** - Current device IP
- **Firmware** - Firmware version

### Select Entities
- **Input Source** - Quick input switching per player (AUX, HDMI, Optical, etc.)

### Device Compatibility
- **AVR Receivers** - Denon and Marantz receivers with HEOS
- **Soundbars** - HEOS Bar, Denon Home Sound Bar series
- **Speakers** - HEOS 1, HEOS 3, HEOS 5, HEOS 7
- **Home Series** - Denon Home 150, 250, 350
- **All-in-One** - Any Marantz/Denon device with HEOS built-in

AVR devices are automatically detected and use graceful shutdown (volume to 0 before stop).

## Installation

### Option 1: Remote Web Interface (Recommended)
1. Download the latest `uc-intg-heos-<version>-aarch64.tar.gz` from [Releases](https://github.com/mase1981/uc-intg-heos/releases)
2. Open your Remote's web interface (`http://your-remote-ip`)
3. Go to **Settings** > **Integrations** > **Add Integration**
4. Click **Upload** and select the downloaded file

### Option 2: Docker
```yaml
services:
  uc-intg-heos:
    image: ghcr.io/mase1981/uc-intg-heos:latest
    container_name: uc-intg-heos
    network_mode: host
    volumes:
      - </local/path>:/data
    environment:
      - UC_CONFIG_HOME=/data
      - UC_INTEGRATION_HTTP_PORT=9090
      - UC_INTEGRATION_INTERFACE=0.0.0.0
    restart: unless-stopped
```

## Configuration

### Prerequisites
1. Active HEOS account (free, created via HEOS app)
2. All HEOS devices configured in the HEOS app
3. IP address of any HEOS device on your network
4. HEOS account email and password

### Setup Steps
1. After installation, go to **Settings** > **Integrations**
2. Find HEOS and click **Configure**
3. Enter:
   - **HEOS Device IP** - Any HEOS device on your network
   - **HEOS Account Email** - Your HEOS account email
   - **HEOS Password** - Your HEOS account password
4. The integration connects, authenticates, and discovers all players
5. Entities are created automatically:
   - `media_player.heos_<ip>.<player_id>` - Media player per device
   - `remote.heos_<ip>.<player_id>` - Remote per device
   - `sensor.heos_<ip>.<player_id>.<type>` - Sensors per device
   - `select.heos_<ip>.<player_id>.input` - Input select per device

### Network Requirements
- HEOS devices on same network as Remote
- Port 1255 accessible (HEOS CLI, automatically used)
- Wired connection and static IP recommended for stability

## Credits

- **Developer** - Meir Miyara
- **HEOS Protocol** - Built using [pyheos](https://github.com/andrewsayre/pyheos) library
- **Unfolded Circle** - [ucapi-framework](https://github.com/unfoldedcircle/integration-python-library) and [ucapi](https://github.com/unfoldedcircle/integration-python-library)
- **Community** - Testing and feedback from UC community

## License

Mozilla Public License 2.0 (MPL-2.0) - see LICENSE file for details.

## Support & Community

- **GitHub Issues** - [Report bugs and request features](https://github.com/mase1981/uc-intg-heos/issues)
- **UC Community Forum** - [General discussion and support](https://unfolded.community/)

---

**Made with care for the Unfolded Circle Community**
