"""
HEOS Remote entity.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any, Dict, List, Optional
import asyncio

import ucapi
from ucapi import Remote, StatusCodes
from ucapi.ui import UiPage

from pyheos import Heos, HeosPlayer, HeosError, RepeatType

_LOG = logging.getLogger(__name__)


class HeosRemote(Remote):
    
    def __init__(self, heos_player: HeosPlayer, device_name: str, api: ucapi.IntegrationAPI, 
                 capabilities: Dict[str, Any], heos: Heos, ui_pages: List[UiPage], 
                 simple_commands: List[str]):
        
        entity_id = f"heos_{device_name.lower().replace(' ', '_').replace('-', '_')}_remote"
        
        # Initialize attributes
        attributes = {
            "state": "available",
            "device_model": heos_player.model,
            "last_command": "",
            "last_result": "",
            "connection_status": "connected",
            "capabilities": capabilities
        }
        
        # Store references
        self._heos_player = heos_player
        self._api = api
        self._device_name = device_name
        self._player_id = heos_player.player_id
        self._heos = heos
        self._capabilities = capabilities
        self._capabilities_initialized = False  # Track if UI is built
        self._all_players = None  # Will be set after init
        
        # Command throttling
        self._last_command_time: Dict[str, float] = {}
        self._command_lock = asyncio.Lock()
        
        super().__init__(
            identifier=entity_id,
            name=f"{device_name} Remote",
            features=["send_cmd"],
            attributes=attributes,
            simple_commands=simple_commands,
            ui_pages=ui_pages,
            cmd_handler=self.handle_cmd
        )
        
        _LOG.info(f"Created HEOS Remote: {device_name} ({entity_id}) with {len(simple_commands)} commands")

    def set_all_players(self, all_players: Dict[int, HeosPlayer]):
        """Store reference to all players for UI building."""
        self._all_players = all_players

    async def initialize(self) -> None:
        """Initialize the remote entity."""
        await self.initialize_capabilities()
        _LOG.info(f"HEOS Remote initialized: {self._device_name}")
    
    async def initialize_capabilities(self):
        """
        Initialize/rebuild remote capabilities and UI pages.
        CRITICAL: This is called on initial setup AND after reboot.
        """
        if self._capabilities_initialized:
            _LOG.debug(f"Remote {self._device_name} capabilities already initialized")
            return
        
        _LOG.info(f"Initializing HEOS remote capabilities for {self._device_name}")
        
        try:
            # Check if we can rebuild (coordinator must exist for dynamic UI)
            from uc_intg_heos.driver import _coordinator, _build_dynamic_ui_pages, _build_simple_commands
            

            if _coordinator is None:
                _LOG.info(f"Initial setup for {self._device_name} - using pre-built UI")
                self._capabilities_initialized = True
                return
            
            if self._all_players:
                # Rebuild UI pages
                ui_pages = await _build_dynamic_ui_pages(
                    self._heos_player, 
                    self._capabilities, 
                    self._all_players
                )
                
                # Rebuild simple commands
                simple_commands = _build_simple_commands(
                    self._capabilities,
                    self._all_players
                )
                
                if hasattr(self, 'options') and self.options:
                    self.options["simple_commands"] = simple_commands
                    self.options["user_interface"] = {"pages": [page.__dict__ for page in ui_pages]}
                    _LOG.info(f"✓ Rebuilt UI with {len(ui_pages)} pages for {self._device_name}")
                
                self._capabilities_initialized = True
            else:
                _LOG.warning(f"Cannot rebuild UI for {self._device_name}: all_players not set")
                
        except Exception as e:
            _LOG.error(f"Failed to initialize remote capabilities for {self._device_name}: {e}", exc_info=True)
        
        await self.push_update()
    
    async def push_update(self) -> None:

        try:
            # CRITICAL FIX: Rebuild UI if not initialized (MusicCast pattern)
            if not self._capabilities_initialized:
                _LOG.info(f"⚠️ Remote {self._device_name} UI not initialized, rebuilding...")
                await self.initialize_capabilities()
            
            # Update attributes
            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
                
        except Exception as e:
            _LOG.error(f"Error in remote push_update for {self._device_name}: {e}")

    async def _execute_with_retry(self, command_func, command_name: str, max_retries: int = 3) -> bool:
        """Execute a command with retry logic for 'Processing previous command' errors."""
        retry_delays = [1.0, 2.0, 3.0]
        
        for attempt in range(max_retries):
            try:
                await command_func()
                return True
            except HeosError as e:
                error_msg = str(e)
                
                if "Processing previous command (13)" in error_msg:
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        _LOG.warning(f"Command {command_name} failed (processing previous command), retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        _LOG.error(f"Command {command_name} failed after {max_retries} attempts: {e}")
                        raise
                else:
                    _LOG.error(f"Command {command_name} failed: {e}")
                    raise
        
        return False

    async def handle_cmd(self, entity, cmd_id: str, params: Dict[str, Any] = None) -> StatusCodes:
        """Handle remote commands using detected capabilities with throttling."""
        _LOG.info(f"Remote command received: {cmd_id} for {self._device_name}")
        
        async with self._command_lock:
            try:
                command_map = {
                    "VOLUME_UP": "VOLUME_UP",
                    "VOLUME_DOWN": "VOLUME_DOWN",
                    "MUTE_TOGGLE": "MUTE_TOGGLE",
                    "PLAY": "PLAY",
                    "PAUSE": "PAUSE",
                    "STOP": "STOP",
                    "NEXT": "NEXT",
                    "PREVIOUS": "PREVIOUS",
                    "CURSOR_UP": "CURSOR_UP",
                    "CURSOR_DOWN": "CURSOR_DOWN",
                    "CURSOR_LEFT": "CURSOR_LEFT",
                    "CURSOR_RIGHT": "CURSOR_RIGHT",
                    "CURSOR_ENTER": "CURSOR_ENTER",
                    "BACK": "BACK",
                    "HOME": "HOME"
                }
                
                actual_command = command_map.get(cmd_id, cmd_id)
                self.attributes["last_command"] = actual_command
                
                # Basic playback controls
                if actual_command == "PLAY":
                    await self._heos.play(self._player_id)
                    self.attributes["last_result"] = "Playing"
                    
                elif actual_command == "PAUSE":
                    await self._heos.pause(self._player_id)
                    self.attributes["last_result"] = "Paused"
                    
                elif actual_command == "STOP":
                    await self._heos.stop(self._player_id)
                    self.attributes["last_result"] = "Stopped"
                    
                elif actual_command == "NEXT":
                    await self._heos.play_next(self._player_id)
                    self.attributes["last_result"] = "Next track"
                    
                elif actual_command == "PREVIOUS":
                    await self._heos.play_previous(self._player_id)
                    self.attributes["last_result"] = "Previous track"
                
                # Volume controls
                elif actual_command == "VOLUME_UP":
                    await self._heos.volume_up(self._player_id, step=5)
                    self.attributes["last_result"] = "Volume up"
                    
                elif actual_command == "VOLUME_DOWN":
                    await self._heos.volume_down(self._player_id, step=5)
                    self.attributes["last_result"] = "Volume down"
                    
                elif actual_command == "MUTE_TOGGLE":
                    await self._heos.toggle_mute(self._player_id)
                    self.attributes["last_result"] = "Mute toggled"
                
                # Repeat and shuffle
                elif actual_command == "REPEAT_TOGGLE":
                    current_repeat = self._heos_player.repeat
                    if current_repeat == RepeatType.OFF:
                        await self._heos.set_play_mode(self._player_id, repeat=RepeatType.ON_ALL)
                        self.attributes["last_result"] = "Repeat: All"
                    elif current_repeat == RepeatType.ON_ALL:
                        await self._heos.set_play_mode(self._player_id, repeat=RepeatType.ON_ONE)
                        self.attributes["last_result"] = "Repeat: One"
                    else:
                        await self._heos.set_play_mode(self._player_id, repeat=RepeatType.OFF)
                        self.attributes["last_result"] = "Repeat: Off"
                        
                elif actual_command == "SHUFFLE_TOGGLE":
                    current_shuffle = self._heos_player.shuffle
                    await self._heos.set_play_mode(self._player_id, shuffle=not current_shuffle)
                    self.attributes["last_result"] = f"Shuffle: {'On' if not current_shuffle else 'Off'}"
                
                # All-speakers grouping
                elif actual_command == "GROUP_ALL_SPEAKERS":
                    await self._handle_group_all_speakers()
                
                # Individual speaker grouping
                elif actual_command.startswith("GROUP_WITH_"):
                    await self._handle_grouping_commands(actual_command)
                    
                elif actual_command == "LEAVE_GROUP":
                    await self._handle_ungroup_command()
                
                # Input switching
                elif actual_command.startswith("INPUT_"):
                    await self._handle_input_commands(actual_command)
                    
                # Favorites
                elif actual_command.startswith("FAVORITE_"):
                    await self._handle_favorite_command(actual_command)
                    
                # Music services
                elif actual_command.startswith("SERVICE_"):
                    await self._handle_service_command(actual_command)
                    
                # Queue management
                elif actual_command == "CLEAR_QUEUE":
                    await self._heos.player_clear_queue(self._player_id)
                    self.attributes["last_result"] = "Queue cleared"
                    
                elif actual_command == "QUEUE_INFO":
                    self.attributes["last_result"] = "Queue info displayed"
                    
                else:
                    _LOG.warning(f"Unsupported remote command: {actual_command}")
                    self.attributes["last_result"] = f"Command {actual_command} not recognized"
                    return StatusCodes.NOT_IMPLEMENTED

                await self.push_update()
                return StatusCodes.OK
                
            except HeosError as e:
                error_msg = f"HEOS command failed: {e}"
                _LOG.error(f"HEOS command failed for '{cmd_id}': {e}")
                self.attributes["last_result"] = error_msg
                await self.push_update()
                return StatusCodes.SERVER_ERROR
                
            except Exception as e:
                error_msg = f"Command error: {str(e)}"
                _LOG.error(f"Error handling command '{cmd_id}': {e}", exc_info=True)
                self.attributes["last_result"] = error_msg
                await self.push_update()
                return StatusCodes.SERVER_ERROR

    async def _handle_group_all_speakers(self):
        """Handle creating a group with ALL available speakers."""
        try:
            all_players = self._heos.players
            
            if not all_players or len(all_players) <= 1:
                self.attributes["last_result"] = "No other speakers available"
                return
            
            player_ids = [self._player_id]
            speaker_names = [self._device_name]
            
            for player_id, player in all_players.items():
                if player_id != self._player_id:
                    player_ids.append(player_id)
                    speaker_names.append(player.name)
            
            _LOG.info(f"Creating all-speakers group with {len(player_ids)} devices: {speaker_names}")
            
            async def group_all_command():
                await self._heos.set_group(player_ids)
            
            success = await self._execute_with_retry(
                group_all_command,
                "GROUP_ALL_SPEAKERS"
            )
            
            if success:
                speakers_list = ", ".join(speaker_names)
                self.attributes["last_result"] = f"Grouped {len(player_ids)} speakers"
                _LOG.info(f"✓ Successfully created all-speakers group")
            else:
                self.attributes["last_result"] = f"Failed to group all speakers after retries"
                
        except Exception as e:
            _LOG.error(f"Error creating all-speakers group: {e}", exc_info=True)
            self.attributes["last_result"] = f"Failed to group all speakers"

    async def _handle_input_commands(self, command: str):
        """Handle input source commands."""
        input_name = command[len("INPUT_"):].lower()
        heos_input = f"inputs/{input_name}"
        
        try:
            await self._heos.play_input_source(self._player_id, heos_input)
            display_name = input_name.replace('_', ' ').title()
            self.attributes["last_result"] = f"Switched to {display_name}"
        except Exception as e:
            _LOG.error(f"Error playing input {input_name}: {e}")
            self.attributes["last_result"] = f"Failed to switch to {input_name}"

    async def _handle_grouping_commands_with_retry(self, command: str):
        """Handle group management commands with retry logic."""
        target_name = command[len("GROUP_WITH_"):]
        
        try:
            target_player_id = None
            for player_id, player in self._heos.players.items():
                if player.name.upper().replace(' ', '_').replace('-', '_') == target_name:
                    target_player_id = player_id
                    break
            
            if target_player_id:
                async def group_command():
                    await self._heos.set_group([self._player_id, target_player_id])
                
                success = await self._execute_with_retry(
                    group_command,
                    f"GROUP_WITH_{target_name}"
                )
                
                if success:
                    display_name = target_name.replace('_', ' ').title()
                    self.attributes["last_result"] = f"Grouped with {display_name}"
                else:
                    self.attributes["last_result"] = f"Failed to group after retries"
            else:
                self.attributes["last_result"] = f"Could not find device: {target_name}"
                
        except Exception as e:
            _LOG.error(f"Error grouping with {target_name}: {e}")
            self.attributes["last_result"] = f"Failed to group"

    async def _handle_ungroup_command_with_retry(self):
        """Handle ungrouping player with retry logic."""
        try:
            async def ungroup_command():
                await self._heos.set_group([self._player_id])
            
            success = await self._execute_with_retry(
                ungroup_command,
                "LEAVE_GROUP"
            )
            
            if success:
                self.attributes["last_result"] = "Left group"
            else:
                self.attributes["last_result"] = "Failed to leave group after retries"
                
        except Exception as e:
            _LOG.error(f"Error leaving group: {e}")
            self.attributes["last_result"] = "Failed to leave group"

    async def _handle_grouping_commands(self, command: str):
        await self._handle_grouping_commands_with_retry(command)

    async def _handle_ungroup_command(self):
        await self._handle_ungroup_command_with_retry()

    async def _handle_favorite_command(self, command: str):
        """Handle favorite playback commands."""
        try:
            favorite_num = int(command.split("_")[-1])
            await self._heos.play_preset_station(self._player_id, favorite_num)
            self.attributes["last_result"] = f"Playing favorite {favorite_num}"
        except Exception as e:
            _LOG.error(f"Error playing favorite: {e}")
            self.attributes["last_result"] = "Failed to play favorite"

    async def _handle_service_command(self, command: str):
        """Handle music service commands."""
        service_name = command[len("SERVICE_"):].replace('_', ' ')
        self.attributes["last_result"] = f"Switched to {service_name}"
        _LOG.info(f"Service command: {service_name}")

    async def shutdown(self):
        """Shutdown the remote entity."""
        _LOG.info(f"Shutting down HEOS Remote: {self._device_name}")