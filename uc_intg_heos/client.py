"""
HEOS CLI client for communication with Denon/Marantz HEOS devices.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Callable
from urllib.parse import quote_plus, unquote_plus

_LOG = logging.getLogger(__name__)

class HeosCommandException(Exception):
    """Exception raised for HEOS command errors."""
    
    def __init__(self, message: str, error_code: int = None):
        super().__init__(message)
        self.error_code = error_code


class HeosResponse:
    """HEOS command response wrapper."""
    
    def __init__(self, raw_response: str):
        """Initialize response from raw JSON string."""
        self.raw = raw_response
        self.data = json.loads(raw_response)
        
        # Parse HEOS response structure
        self.heos = self.data.get('heos', {})
        self.command = self.heos.get('command', '')
        self.result = self.heos.get('result', '')
        self.message = self.heos.get('message', '')
        self.payload = self.data.get('payload', {})
        
        # Parse message attributes
        self.attributes = self._parse_message_attributes()
    
    def _parse_message_attributes(self) -> Dict[str, str]:
        """Parse message string into attribute dictionary."""
        attributes = {}
        if self.message:
            # Split on & and then on =
            pairs = self.message.split('&')
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    # URL decode values
                    attributes[key] = unquote_plus(value)
        return attributes
    
    @property
    def is_success(self) -> bool:
        """Check if command was successful."""
        return self.result == 'success'
    
    @property
    def error_code(self) -> Optional[int]:
        """Get error code if command failed."""
        if not self.is_success and 'eid' in self.attributes:
            try:
                return int(self.attributes['eid'])
            except ValueError:
                pass
        return None
    
    @property 
    def error_text(self) -> Optional[str]:
        """Get error text if command failed."""
        if not self.is_success:
            return self.attributes.get('text', 'Unknown error')
        return None


class HeosClient:
    """HEOS CLI client for device communication."""
    
    def __init__(self, ip_address: str, port: int = 1255, timeout: int = 10):
        """
        Initialize HEOS client.
        
        :param ip_address: HEOS device IP address
        :param port: HEOS CLI port (default 1255)
        :param timeout: Command timeout in seconds
        """
        self.ip_address = ip_address
        self.port = port
        self.timeout = timeout
        
        self._reader = None
        self._writer = None
        self._connected = False
        self._event_handlers: List[Callable] = []
        self._command_responses = {}
        self._listen_task = None
        
        # Device information
        self.device_info = {}
        self.player_id = None
        
    async def connect(self) -> bool:
        """
        Connect to HEOS device.
        
        :return: True if connection successful
        """
        try:
            _LOG.info(f"Connecting to HEOS device at {self.ip_address}:{self.port}")
            
            # Use standard asyncio connection - HEOS CLI is just TCP, not telnet
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip_address, self.port),
                timeout=self.timeout
            )
            
            self._connected = True
            
            # Start listening for responses and events
            self._listen_task = asyncio.create_task(self._listen_for_messages())
            
            # Get device information
            await self._initialize_device()
            
            _LOG.info(f"Successfully connected to HEOS device: {self.device_info.get('name', 'Unknown')}")
            return True
            
        except Exception as e:
            _LOG.error(f"Failed to connect to HEOS device {self.ip_address}: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from HEOS device."""
        _LOG.info("Disconnecting from HEOS device")
        
        self._connected = False
        
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        
        self._reader = None
        self._writer = None
    
    async def _initialize_device(self) -> None:
        """Initialize device information and settings."""
        try:
            # Get device information 
            response = await self.get_players()
            if response.is_success and response.payload:
                players = response.payload
                if players:
                    # Find this device in players list
                    for player in players:
                        if 'pid' in player:
                            self.player_id = player['pid']
                            self.device_info = player
                            break
            
            # Register for change events
            await self.register_for_change_events(True)
            
        except Exception as e:
            _LOG.error(f"Failed to initialize HEOS device: {e}")
    
    async def _listen_for_messages(self) -> None:
        """Listen for incoming messages from HEOS device."""
        try:
            while self._connected and self._reader:
                line = await self._reader.readline()
                if not line:
                    break
                
                message = line.decode('utf-8').strip()
                if message:
                    await self._handle_message(message)
                    
        except asyncio.CancelledError:
            _LOG.debug("Message listening cancelled")
        except Exception as e:
            _LOG.error(f"Error in message listener: {e}")
            self._connected = False
    
    async def _handle_message(self, message: str) -> None:
        """Handle incoming message from HEOS device."""
        try:
            response = HeosResponse(message)
            
            # Check if this is an event or command response
            if 'event/' in response.command:
                # This is an event - notify handlers
                await self._handle_event(response)
            else:
                # This is a command response - store for waiting command
                command_key = response.command
                if command_key in self._command_responses:
                    self._command_responses[command_key].set_result(response)
                
        except Exception as e:
            _LOG.error(f"Failed to handle message: {e}")
            _LOG.debug(f"Problematic message: {message}")
    
    async def _handle_event(self, response: HeosResponse) -> None:
        """Handle HEOS event notification."""
        _LOG.debug(f"Received HEOS event: {response.command}")
        
        # Notify registered event handlers
        for handler in self._event_handlers:
            try:
                await handler(response)
            except Exception as e:
                _LOG.error(f"Error in event handler: {e}")
    
    def add_event_handler(self, handler: Callable) -> None:
        """Add event handler for HEOS events."""
        self._event_handlers.append(handler)
    
    def remove_event_handler(self, handler: Callable) -> None:
        """Remove event handler."""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)
    
    async def _send_command(self, command: str) -> HeosResponse:
        """
        Send command to HEOS device and wait for response.
        
        :param command: HEOS command string
        :return: HEOS response
        """
        if not self._connected or not self._writer:
            raise HeosCommandException("Not connected to HEOS device")
        
        try:
            # Prepare command response future
            command_parts = command.split('?')[0]  # Remove parameters for key
            command_key = command_parts.replace('heos://', '')
            
            future = asyncio.Future()
            self._command_responses[command_key] = future
            
            # Send command
            command_line = f"{command}\r\n"
            self._writer.write(command_line.encode('utf-8'))
            await self._writer.drain()
            
            # Wait for response
            response = await asyncio.wait_for(future, timeout=self.timeout)
            
            # Clean up
            if command_key in self._command_responses:
                del self._command_responses[command_key]
            
            if not response.is_success:
                raise HeosCommandException(
                    f"Command failed: {response.error_text}",
                    response.error_code
                )
            
            return response
            
        except asyncio.TimeoutError:
            if command_key in self._command_responses:
                del self._command_responses[command_key]
            raise HeosCommandException(f"Command timeout: {command}")
        except Exception as e:
            if command_key in self._command_responses:
                del self._command_responses[command_key]
            raise HeosCommandException(f"Command error: {e}")
    
    @staticmethod
    def _encode_parameter(value: str) -> str:
        """Encode parameter value for HEOS command."""
        # HEOS requires URL encoding for special characters
        return quote_plus(str(value))
    
    # System Commands
    
    async def register_for_change_events(self, enable: bool = True) -> HeosResponse:
        """Register or unregister for change events."""
        command = f"heos://system/register_for_change_events?enable={'on' if enable else 'off'}"
        return await self._send_command(command)
    
    async def check_account(self) -> HeosResponse:
        """Check HEOS account status."""
        return await self._send_command("heos://system/check_account")
    
    async def sign_in(self, username: str, password: str) -> HeosResponse:
        """Sign in to HEOS account."""
        username_enc = self._encode_parameter(username)
        password_enc = self._encode_parameter(password)
        command = f"heos://system/sign_in?un={username_enc}&pw={password_enc}"
        return await self._send_command(command)
    
    async def sign_out(self) -> HeosResponse:
        """Sign out of HEOS account."""
        return await self._send_command("heos://system/sign_out")
    
    async def heart_beat(self) -> HeosResponse:
        """Send heartbeat to keep connection alive."""
        return await self._send_command("heos://system/heart_beat")
    
    # Player Commands
    
    async def get_players(self) -> HeosResponse:
        """Get list of HEOS players."""
        return await self._send_command("heos://player/get_players")
    
    async def get_player_info(self, player_id: str = None) -> HeosResponse:
        """Get player information."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/get_player_info?pid={pid}")
    
    async def get_play_state(self, player_id: str = None) -> HeosResponse:
        """Get player play state."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/get_play_state?pid={pid}")
    
    async def set_play_state(self, state: str, player_id: str = None) -> HeosResponse:
        """Set player play state (play, pause, stop)."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        if state not in ['play', 'pause', 'stop']:
            raise HeosCommandException(f"Invalid play state: {state}")
        return await self._send_command(f"heos://player/set_play_state?pid={pid}&state={state}")
    
    async def get_now_playing_media(self, player_id: str = None) -> HeosResponse:
        """Get now playing media information."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/get_now_playing_media?pid={pid}")
    
    async def get_volume(self, player_id: str = None) -> HeosResponse:
        """Get player volume."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/get_volume?pid={pid}")
    
    async def set_volume(self, level: int, player_id: str = None) -> HeosResponse:
        """Set player volume (0-100)."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        if not 0 <= level <= 100:
            raise HeosCommandException(f"Volume level must be 0-100, got {level}")
        return await self._send_command(f"heos://player/set_volume?pid={pid}&level={level}")
    
    async def volume_up(self, step: int = 5, player_id: str = None) -> HeosResponse:
        """Increase volume by step."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        if not 1 <= step <= 10:
            raise HeosCommandException(f"Volume step must be 1-10, got {step}")
        return await self._send_command(f"heos://player/volume_up?pid={pid}&step={step}")
    
    async def volume_down(self, step: int = 5, player_id: str = None) -> HeosResponse:
        """Decrease volume by step."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        if not 1 <= step <= 10:
            raise HeosCommandException(f"Volume step must be 1-10, got {step}")
        return await self._send_command(f"heos://player/volume_down?pid={pid}&step={step}")
    
    async def get_mute(self, player_id: str = None) -> HeosResponse:
        """Get player mute state."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/get_mute?pid={pid}")
    
    async def set_mute(self, state: bool, player_id: str = None) -> HeosResponse:
        """Set player mute state."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        mute_state = "on" if state else "off"
        return await self._send_command(f"heos://player/set_mute?pid={pid}&state={mute_state}")
    
    async def toggle_mute(self, player_id: str = None) -> HeosResponse:
        """Toggle player mute state."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/toggle_mute?pid={pid}")
    
    async def get_play_mode(self, player_id: str = None) -> HeosResponse:
        """Get player play mode (repeat and shuffle)."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/get_play_mode?pid={pid}")
    
    async def set_play_mode(self, repeat: str = "off", shuffle: bool = False, 
                           player_id: str = None) -> HeosResponse:
        """Set player play mode."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        if repeat not in ['off', 'on_all', 'on_one']:
            raise HeosCommandException(f"Invalid repeat mode: {repeat}")
        
        shuffle_state = "on" if shuffle else "off"
        return await self._send_command(
            f"heos://player/set_play_mode?pid={pid}&repeat={repeat}&shuffle={shuffle_state}"
        )
    
    async def play_next(self, player_id: str = None) -> HeosResponse:
        """Play next track."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/play_next?pid={pid}")
    
    async def play_previous(self, player_id: str = None) -> HeosResponse:
        """Play previous track."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://player/play_previous?pid={pid}")
    
    # Group Commands
    
    async def get_groups(self) -> HeosResponse:
        """Get list of HEOS groups."""
        return await self._send_command("heos://group/get_groups")
    
    async def get_group_info(self, group_id: str) -> HeosResponse:
        """Get group information."""
        return await self._send_command(f"heos://group/get_group_info?gid={group_id}")
    
    async def set_group(self, player_ids: List[str]) -> HeosResponse:
        """Create or modify group. First player is leader."""
        if not player_ids:
            raise HeosCommandException("At least one player ID required")
        
        pid_list = ",".join(player_ids)
        return await self._send_command(f"heos://group/set_group?pid={pid_list}")
    
    async def ungroup_player(self, player_id: str = None) -> HeosResponse:
        """Ungroup player (remove from any group)."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        return await self._send_command(f"heos://group/set_group?pid={pid}")
    
    async def get_group_volume(self, group_id: str) -> HeosResponse:
        """Get group volume."""
        return await self._send_command(f"heos://group/get_volume?gid={group_id}")
    
    async def set_group_volume(self, group_id: str, level: int) -> HeosResponse:
        """Set group volume (0-100)."""
        if not 0 <= level <= 100:
            raise HeosCommandException(f"Volume level must be 0-100, got {level}")
        return await self._send_command(f"heos://group/set_volume?gid={group_id}&level={level}")
    
    async def get_group_mute(self, group_id: str) -> HeosResponse:
        """Get group mute state."""
        return await self._send_command(f"heos://group/get_mute?gid={group_id}")
    
    async def set_group_mute(self, group_id: str, state: bool) -> HeosResponse:
        """Set group mute state."""
        mute_state = "on" if state else "off"
        return await self._send_command(f"heos://group/set_mute?gid={group_id}&state={mute_state}")
    
    # Browse Commands
    
    async def get_music_sources(self) -> HeosResponse:
        """Get available music sources."""
        return await self._send_command("heos://browse/get_music_sources")
    
    async def browse_source(self, source_id: str, container_id: str = None) -> HeosResponse:
        """Browse music source or container."""
        if container_id:
            return await self._send_command(f"heos://browse/browse?sid={source_id}&cid={container_id}")
        else:
            return await self._send_command(f"heos://browse/browse?sid={source_id}")
    
    async def play_stream(self, source_id: str, container_id: str = None, 
                         media_id: str = None, player_id: str = None) -> HeosResponse:
        """Play stream from source."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        
        params = [f"pid={pid}", f"sid={source_id}"]
        if container_id:
            params.append(f"cid={container_id}")
        if media_id:
            params.append(f"mid={media_id}")
        
        command = f"heos://browse/play_stream?{'&'.join(params)}"
        return await self._send_command(command)
    
    async def play_input(self, input_name: str, player_id: str = None) -> HeosResponse:
        """Play input source."""
        pid = player_id or self.player_id
        if not pid:
            raise HeosCommandException("No player ID available")
        
        return await self._send_command(f"heos://browse/play_input?pid={pid}&input={input_name}")
    
    # Connection status
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected
    
    @property
    def device_name(self) -> str:
        """Get device name."""
        return self.device_info.get('name', f'HEOS Device ({self.ip_address})')
    
    @property
    def device_model(self) -> str:
        """Get device model."""
        return self.device_info.get('model', 'Unknown')
    
    @property
    def device_version(self) -> str:
        """Get device firmware version."""
        return self.device_info.get('version', 'Unknown')