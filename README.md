# HEOS Integration for Unfolded Circle Remote Two/3

Control your Denon/Marantz HEOS devices directly from your Unfolded Circle Remote 2 or Remote 3 with comprehensive multi-room audio control.

![HEOS](https://img.shields.io/badge/HEOS-Multi--Room%20Audio-blue)
[![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-heos?style=flat-square)](https://github.com/mase1981/uc-intg-heos/releases)
![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)
[![GitHub issues](https://img.shields.io/github/issues/mase1981/uc-intg-heos?style=flat-square)](https://github.com/mase1981/uc-intg-heos/issues)
[![Community Forum](https://img.shields.io/badge/community-forum-blue?style=flat-square)](https://community.unfoldedcircle.com/)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-heos/total?style=flat-square)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg?style=flat-square)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA&style=flat-square)](https://github.com/sponsors/mase1981)


## Features

This integration provides comprehensive control of all HEOS devices on your account, with intelligent multi-device support and automatic capability detection.

---
## ❤️ Support Development ❤️

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

Your support helps maintain this integration. Thank you! ❤️
---

### 🎵 **Account-Based Device Discovery**

#### **Automatic Setup**
- **Single Sign-In** - Connect once with your HEOS account credentials
- **Auto-Discovery** - All configured HEOS devices automatically detected
- **Unified Control** - Control all devices from a single integration
- **Network Flexibility** - Connect to any HEOS device IP - discovers entire ecosystem


### 📺 **Media Player Functionality**

- **Basic Controls** - Play, Pause, Stop, Next, Previous, Volume Management, Repeat (off/all/one), Shuffle (on/off)
- **Now Playing** - Track, artist, album, station information
- **Artwork Display** - Album art and media images
- **Progress Tracking** - Real-time position and duration
- **Source Display** - Currently playing source/service
- **Favorites** - Quick access to preset HEOS favorite stations (if configured)
- **Music Services** - Pandora, SoundCloud, and all configured services (if configured)
- **Playlists** - HEOS playlists with smart playback (if configured)
- **Input Sources** - AUX, Optical, Bluetooth, HDMI inputs (device-dependent)
- **Auto-Play** - Intelligent automatic playback from music services (due to UCAPI limitation no playlists)

### 🎛️ **Remote Control (Multi-Device Only)**

- **Dynamic UI** - Remote pages built based on actual device features
- **Per-Device Controls** - Each device gets appropriate remote functionality
- **Create Groups** - Group multiple HEOS devices for synchronized playback
- **Ungroup** - Easily remove devices from groups
- **Dynamic Commands** - Group commands automatically generated per device
- **Playback** - Transport controls, volume, repeat, shuffle
- **Inputs** - Device-specific input switching (if available)
- **Grouping** - Multi-room audio control with other HEOS devices
- **Services** - Quick access to music services (Pandora, SoundCloud, etc.)
- **Favorites** - One-touch access to favorite stations

### **Device Compatibility**

#### **Supported HEOS Products**
- **AVR Receivers** - Denon, Marantz receivers with HEOS
- **Soundbars** - HEOS Bar, Denon Home Sound Bar series
- **Speakers** - HEOS 1, HEOS 3, HEOS 5, HEOS 7
- **Home Series** - Denon Home 150, 250, 350
- **All-in-One** - Marantz devices with HEOS built-in

### **Network Requirements**

- **HEOS Account** - Active HEOS account (free)
- **Network Access** - HEOS devices on same network as Remote
- **CLI Port** - Port 1255 (automatically configured)
- **Authentication** - HEOS account username/email and password

## Installation

### Option 1: Remote Web Interface (Recommended)
1. Navigate to the [**Releases**](https://github.com/mase1981/uc-intg-heos/releases) page
2. Download the latest `uc-intg-heos-<version>-aarch64.tar.gz` file
3. Open your remote's web interface (`http://your-remote-ip`)
4. Go to **Settings** → **Integrations** → **Add Integration**
5. Click **Upload** and select the downloaded `.tar.gz` file

### Option 2: Docker (Advanced Users)

The integration is available as a pre-built Docker image from GitHub Container Registry:

**Image**: `ghcr.io/mase1981/uc-intg-heos:latest`

**Docker Compose:**
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
      - PYTHONPATH=/app
    restart: unless-stopped
```

**Docker Run:**
```bash
docker run -d --name uc-heos --restart unless-stopped --network host -v heos-config:/app/config -e UC_CONFIG_HOME=/app/config -e UC_INTEGRATION_INTERFACE=0.0.0.0 -e UC_INTEGRATION_HTTP_PORT=9090 -e PYTHONPATH=/app ghcr.io/mase1981/uc-intg-heos:latest
```

## Configuration

### Step 1: Prepare Your HEOS Account

**IMPORTANT**: All HEOS devices must be fully configured in the HEOS app before setting up the integration.

#### Account Setup:
1. Ensure you have a HEOS account (free, created via HEOS app)
2. Note your username/email and password
3. All HEOS devices must be configured in the HEOS app first
4. Configure playlists, favorites, and music sources via HEOS app

#### Find Device IP:
1. Open HEOS app
2. Go to Settings → Device → (Select any HEOS device)
3. Note the IP address of any HEOS device
4. Integration will discover all other devices automatically

#### Network Setup:
- **Wired Connection** - Recommended for stability
- **Static IP** - Recommended via DHCP reservation
- **Firewall** - Allow CLI traffic (port 1255)
- **Network Isolation** - Must be on same subnet as Remote

### Step 2: Setup Integration

1. After installation, go to **Settings** → **Integrations**
2. The HEOS integration should appear in **Available Integrations**
3. Click **"Configure"** to begin setup:

#### **Configuration:**
- **HEOS Device IP** - IP address of any HEOS device (e.g., 192.168.1.100)
- **HEOS Username** - Your HEOS account email/username
- **HEOS Password** - Your HEOS account password
- Click **Complete Setup**

#### **Connection Test:**
- Integration connects to HEOS device
- Signs in to your HEOS account
- Discovers all HEOS devices on your account
- Creates appropriate entities automatically

4. Integration will create entities:
   - **Media Player** - `media_player.heos_[device_name]` (one per device)
   - **Remote** - `heos_[device_name]_remote` (multi-device only)

## Using the Integration

### Media Player Entities

Each HEOS device gets its own media player entity:

- **Playback Control** - Play, Pause, Stop, Next, Previous
- **Volume Control** - Volume slider, mute toggle
- **Repeat Modes** - Off, All, One
- **Shuffle** - On/Off
- **Media Info** - Track, artist, album, artwork
- **Source Selection** - Favorites, services, inputs
- **Progress** - Real-time position and duration

### Remote Entity (Multi-Device Only)

The remote entity provides comprehensive control:

- **Transport Controls** - Play/Pause, Next, Previous
- **Volume Controls** - Volume up/down, mute
- **Grouping** - Create and manage multi-room groups
- **Services** - Quick access to music services
- **Favorites** - One-touch access to stations
- **Inputs** - Device-specific input switching

## Credits

- **Developer** - Meir Miyara
- **HEOS Protocol** - Built using pyheos library and official HEOS CLI
- **Unfolded Circle** - Remote 2/3 integration framework (ucapi)
- **Community** - Testing and feedback from UC community
- **Home Assistant** - Architecture patterns from HA HEOS integration

## License

This project is licensed under the Mozilla Public License 2.0 (MPL-2.0) - see LICENSE file for details.

## Support & Community

- **GitHub Issues** - [Report bugs and request features](https://github.com/mase1981/uc-intg-heos/issues)
- **UC Community Forum** - [General discussion and support](https://unfolded.community/)
- **Developer** - [Meir Miyara](https://www.linkedin.com/in/meirmiyara)

---

**Made with ❤️ for the Unfolded Circle Community**

**Thank You** - Meir Miyara
