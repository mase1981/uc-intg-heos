# HEOS Integration for Unfolded Circle Remote Two/3

Control your Denon/Marantz HEOS devices directly from your Unfolded Circle Remote 2 or Remote 3 with comprehensive multi-room audio control.

![HEOS](https://img.shields.io/badge/HEOS-Multi--Room%20Audio-blue)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-heos)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-heos/total)
![License](https://img.shields.io/badge/license-MPL--2.0-blue)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA)](https://github.com/sponsors/mase1981/button)

## Features

This integration provides comprehensive control of all HEOS devices on your account, with intelligent multi-device support and automatic capability detection.

### 🎵 **Account-Based Device Discovery**

#### **Automatic Setup**
- **Single Sign-In**: Connect once with your HEOS account credentials
- **Auto-Discovery**: All configured HEOS devices automatically detected
- **Unified Control**: Control all devices from a single integration
- **Network Flexibility**: Connect to any HEOS device IP - discovers entire ecosystem


### 📺 **Media Player Functionality**

- **Basic Controls**: Play, Pause, Stop, Next, Previous, Volume Management, Repeat (off/all/one), Shuffle (on/off)
- **Now Playing**: Track, artist, album, station information
- **Artwork Display**: Album art and media images
- **Progress Tracking**: Real-time position and duration
- **Source Display**: Currently playing source/service
- **Favorites**: Quick access to preset HEOS favorite stations (if configured)
- **Music Services**: Pandora, SoundCloud, and all configured services (if configured)
- **Playlists**: HEOS playlists with smart playback (if configured)
- **Input Sources**: AUX, Optical, Bluetooth, HDMI inputs (device-dependent)
- **Auto-Play**: Intelligent automatic playback from music services (due to UCAPI limitation no playlists)

### 🎛️ **Remote Control (Multi-Device Only)**

- **Dynamic UI**: Remote pages built based on actual device features
- **Per-Device Controls**: Each device gets appropriate remote functionality
- **Create Groups**: Group multiple HEOS devices for synchronized playback
- **Ungroup**: Easily remove devices from groups
- **Dynamic Commands**: Group commands automatically generated per device
- **Playback**: Transport controls, volume, repeat, shuffle
- **Inputs**: Device-specific input switching (if available)
- **Grouping**: Multi-room audio control with other HEOS devices
- **Services**: Quick access to music services (Pandora, SoundCloud, etc.)
- **Favorites**: One-touch access to favorite stations

## Device Compatibility

### **Supported HEOS Products**
- **AVR Receivers**: Denon, Marantz receivers with HEOS
- **Soundbars**: HEOS Bar, Denon Home Sound Bar series
- **Speakers**: HEOS 1, HEOS 3, HEOS 5, HEOS 7
- **Home Series**: Denon Home 150, 250, 350
- **All-in-One**: Marantz devices with HEOS built-in

### **Network Requirements**
- **HEOS Account**: Active HEOS account (free)
- **Network Access**: HEOS devices on same network as Remote
- **CLI Port**: Port 1255 (automatically configured)
- **Authentication**: HEOS account username/email and password

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
      - ./data:/data
    environment:
      - UC_CONFIG_HOME=/data
      - UC_INTEGRATION_HTTP_PORT=9090
      - UC_DISABLE_MDNS_PUBLISH=false
    restart: unless-stopped
```

**Docker Run:**
```bash
docker run -d --name=uc-intg-heos --network host -v </local/path>:/config --restart unless-stopped ghcr.io/mase1981/uc-intg-heos:latest
```

## Configuration

### Step 1: Prepare Your HEOS Account

1. **HEOS Account:**
   - Ensure you have a HEOS account (free, created via HEOS app)
   - Note your username/email and password
   - All HEOS devices must be fully configured in the HEOS app first
   - All HEOS playlists, favorites, Music Sources, etc - all must be configured via app before setting up integration

2. **Find Device IP:**
   - Open HEOS app
   - Go to Settings → Device → (Select any HEOS device)
   - Note the IP address of any HEOS device
   - Integration will discover all other devices automatically

### Step 2: Setup Integration

1. After installation, go to **Settings** → **Integrations**
2. The HEOS integration should appear in **Available Integrations**
3. Click **"Configure"** and enter the following:

   **Account Configuration:**
   - **HEOS Device IP**: IP address of any HEOS device (e.g., `192.168.1.100`)
   - **HEOS Username**: Your HEOS account email/username
   - **HEOS Password**: Your HEOS account password

4. Click **"Complete Setup"** - the integration will:
   - Connect to the HEOS device
   - Sign in to your HEOS account
   - Discover all HEOS devices on your account
   - Create appropriate entities automatically



## Troubleshooting

### Common Issues

**Connection Failed:**
- Verify HEOS device IP is correct and accessible
- Check device is on same network as Remote
- Ensure HEOS device is powered on
- Try IP of different HEOS device if available

**Authentication Error:**
- Verify HEOS account credentials are correct
- Check username/email is exact match
- Ensure password is correct (case-sensitive)
- Try signing in via HEOS app first

**No Devices Discovered:**
- Ensure devices are configured in HEOS app first
- Verify HEOS account credentials
- Check all devices are on same HEOS account
- Restart HEOS devices if needed

**Grouping Not Working:**
- Feature requires multiple HEOS devices
- Ensure all devices are on same network
- Check devices are discovered (visible as entities)
- Try ungrouping and regrouping

**Sources Not Showing:**
- Favorites require active HEOS account login
- Music services must be configured in HEOS app
- Input sources vary by device model
- Check device capabilities in HEOS app

### Debug Information

Enable detailed logging for troubleshooting:

**Docker Environment:**
```bash
# Add to docker-compose.yml environment section
- LOG_LEVEL=DEBUG

# View logs
docker logs uc-intg-heos
```

**Integration Logs:**
- **Remote Interface**: Settings → Integrations → HEOS → View Logs
- **Common Errors**: Authentication, discovery, grouping issues

**Network Verification:**
```bash
# Test HEOS device connectivity
ping <device-ip>

# Test HEOS CLI port
telnet <device-ip> 1255
nc -v <device-ip> 1255
```

**HEOS App Verification:**
- Verify all devices visible in HEOS app
- Ensure account login active
- Check favorites and services configured
- Test grouping functionality in app

## For Developers

### Local Development

1. **Clone and setup:**
   ```bash
   git clone https://github.com/mase1981/uc-intg-heos.git
   cd uc-intg-heos
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configuration:**
   ```bash
   # Development configuration
   # Run integration and configure via Remote interface
   python -m uc_intg_heos.driver
   # Integration runs on localhost:9090
   ```

3. **VS Code debugging:**
   - Open project in VS Code
   - Use F5 to start debugging session
   - Configure integration with your HEOS account

### Project Structure

```
uc-intg-heos/
├── uc_intg_heos/              # Main package
│   ├── __init__.py            # Package info
│   ├── client.py              # HEOS CLI client (legacy reference)
│   ├── config.py              # Configuration management
│   ├── coordinator.py         # HEOS connection coordinator
│   ├── driver.py              # Main integration driver
│   ├── media_player.py        # Media player entity
│   ├── remote.py              # Remote control entity
│   └── setup.py               # Setup flow handler
├── .github/workflows/         # GitHub Actions CI/CD
│   └── build.yml              # Automated build pipeline
├── docker-compose.yml         # Docker deployment
├── Dockerfile                 # Container build instructions
├── docker-entry.sh            # Container entry point
├── driver.json                # Integration metadata
├── requirements.txt           # Dependencies
├── pyproject.toml             # Python project config
└── README.md                  # This file
```

### Development Features

#### HEOS Protocol Implementation
Complete HEOS CLI protocol integration:
- **pyheos Library**: Official Python library for HEOS communication
- **Account Authentication**: Credentials-based authentication
- **Device Discovery**: Automatic discovery of all account devices
- **Real-time Events**: Live state updates and event handling

#### Entity Architecture
Production-ready intelligent entities:
- **Dynamic Creation**: Entities created based on device count
- **Reboot Survival**: State persists across Remote reboots
- **Race Condition Protection**: Bulletproof initialization
- **Capability Detection**: No hardcoded assumptions

#### Multi-Room Support
Comprehensive grouping functionality:
- **Dynamic Grouping**: Create/modify groups on-the-fly
- **Group Commands**: Volume, mute, playback for groups
- **Leader/Member**: Proper group hierarchy management
- **Event Handling**: Real-time group state updates

### Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run integration
python -m uc_intg_heos.driver

# Configure with your HEOS account
# Test all media player controls
# Test multi-room grouping (if multiple devices)
```

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and test with HEOS devices
4. Test with both single and multi-device scenarios
5. Verify reboot survival functionality
6. Commit changes: `git commit -m 'Add amazing feature'`
7. Push to branch: `git push origin feature/amazing-feature`
8. Open a Pull Request


## Credits

- **Developer**: Meir Miyara
- **HEOS Protocol**: Built using pyheos library and official HEOS CLI
- **Unfolded Circle**: Remote 2/3 integration framework (ucapi)
- **Community**: Testing and feedback from UC community
- **Home Assistant**: Architecture patterns from HA HEOS integration

## Support & Community

- **GitHub Issues**: [Report bugs and request features](https://github.com/mase1981/uc-intg-heos/issues)
- **UC Community Forum**: [General discussion and support](https://unfolded.community/)
- **Developer**: [Meir Miyara](https://www.linkedin.com/in/meirmiyara)

## Known Limitations

- **Grouping**: Multi-device grouping tested with simulator only (real hardware validation pending)
- **Input Detection**: Input sources detected but may vary by device model
- **Music Services**: Requires services configured in HEOS app first
- **Network**: All devices must be on same network as Remote

---

**Made with ❤️ for the Unfolded Circle Community**

**Thank You**: Meir Miyara