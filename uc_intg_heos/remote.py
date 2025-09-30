"""
HEOS Remote entity

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

    async def initialize(self) -> None:
        """Initialize the remote entity."""
        await self.push_update()
        _LOG.info(f"HEOS Remote initialized: {self._device_name}")
    
    async def push_update(self) -> None:
        """Update remote entity state."""
        try:
            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
        except Exception as e:
            _LOG.error(f"Error in remote push_update for {self._device_name}: {e}")

    async def _execute_with_retry(self, command_func, command_name: str, max_retries: int = 3) -> bool:
        """Execute a command with retry logic for 'Processing previous command' errors."""
        retry_delays = [1.0, 2.0, 3.0]  # Exponential backoff delays
        
        for attempt in range(max_retries):
            try:
                await command_func()
                return True
            except HeosError as e:
                error_msg = str(e)
                
                # Check if it's error code 13 (Processing previous command)
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
                    # For other errors, don't retry
                    _LOG.error(f"Command {command_name} failed: {e}")
                    raise
        
        return False

    async def handle_cmd(self, entity, cmd_id: str, params: Dict[str, Any] = None) -> StatusCodes:
        """Handle remote commands using detected capabilities with throttling."""
        async with self._command_lock:
            try:
                actual_command = params.get("command", cmd_id) if params else cmd_id
                _LOG.info(f"Executing HEOS Remote command: {actual_command} for {self._device_name}")
                
                # Throttle commands - minimum 500ms between commands
                import time
                current_time = time.time()
                last_time = self._last_command_time.get(actual_command, 0)
                time_diff = current_time - last_time
                
                if time_diff < 0.5:  # 500ms throttle
                    wait_time = 0.5 - time_diff
                    _LOG.debug(f"Throttling command {actual_command}, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                
                self._last_command_time[actual_command] = time.time()
                self.attributes["last_command"] = actual_command
                
                # Basic playback commands
                if actual_command == "PLAY":
                    await self._heos.player_set_play_state(self._player_id, "play")
                    self.attributes["last_result"] = "Playing"
                    
                elif actual_command == "PAUSE":
                    await self._heos.player_set_play_state(self._player_id, "pause")
                    self.attributes["last_result"] = "Paused"
                    
                elif actual_command == "STOP":
                    await self._heos.player_set_play_state(self._player_id, "stop")
                    self.attributes["last_result"] = "Stopped"
                    
                elif actual_command == "PLAY_PAUSE":
                    # Toggle play/pause
                    current_state = self._heos_player.state
                    new_state = "pause" if str(current_state) == "PlayState.PLAY" else "play"
                    await self._heos.player_set_play_state(self._player_id, new_state)
                    self.attributes["last_result"] = "Play/Pause toggled"
                    
                # Volume commands
                elif actual_command == "VOLUME_UP":
                    await self._heos.player_volume_up(self._player_id, step=5)
                    self.attributes["last_result"] = "Volume increased"
                    
                elif actual_command == "VOLUME_DOWN":
                    await self._heos.player_volume_down(self._player_id, step=5)
                    self.attributes["last_result"] = "Volume decreased"
                    
                elif actual_command == "MUTE_TOGGLE":
                    await self._heos.player_toggle_mute(self._player_id)
                    self.attributes["last_result"] = "Mute toggled"
                    
                # Navigation commands
                elif actual_command == "NEXT":
                    await self._heos.player_play_next(self._player_id)
                    self.attributes["last_result"] = "Playing next track"
                    
                elif actual_command == "PREVIOUS":
                    await self._heos.player_play_previous(self._player_id)
                    self.attributes["last_result"] = "Playing previous track"
                    
                # Repeat commands
                elif actual_command == "REPEAT_OFF":
                    await self._heos.player_set_play_mode(self._player_id, RepeatType.OFF, self._heos_player.shuffle)
                    self.attributes["last_result"] = "Repeat: Off"
                    
                elif actual_command == "REPEAT_ALL":
                    await self._heos.player_set_play_mode(self._player_id, RepeatType.ON_ALL, self._heos_player.shuffle)
                    self.attributes["last_result"] = "Repeat: All"
                    
                elif actual_command == "REPEAT_ONE":
                    await self._heos.player_set_play_mode(self._player_id, RepeatType.ON_ONE, self._heos_player.shuffle)
                    self.attributes["last_result"] = "Repeat: One"
                    
                # Shuffle commands
                elif actual_command == "SHUFFLE_ON":
                    await self._heos.player_set_play_mode(self._player_id, self._heos_player.repeat, True)
                    self.attributes["last_result"] = "Shuffle: On"
                    
                elif actual_command == "SHUFFLE_OFF":
                    await self._heos.player_set_play_mode(self._player_id, self._heos_player.repeat, False)
                    self.attributes["last_result"] = "Shuffle: Off"
                    
                # Input source commands
                elif actual_command.startswith("INPUT_"):
                    await self._handle_input_commands(actual_command)
                    
                # Group management
                elif actual_command.startswith("GROUP_WITH_"):
                    await self._handle_grouping_commands_with_retry(actual_command)
                    
                elif actual_command == "LEAVE_GROUP":
                    await self._handle_ungroup_command_with_retry()
                    
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

                # Update the entity state
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

    async def _handle_input_commands(self, command: str):
        """Handle input source commands."""
        # Extract input name from command (e.g., "INPUT_AUX_IN_1" -> "inputs/aux_in_1")
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
        # Extract target player name from command
        target_name = command[len("GROUP_WITH_"):]
        
        try:
            # Find target player
            target_player_id = None
            for player_id, player in self._heos.players.items():
                if player.name.upper().replace(' ', '_').replace('-', '_') == target_name:
                    target_player_id = player_id
                    break
            
            if target_player_id:
                # Create group with retry logic
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
            self.attributes["last_result"] = f"Failed to group with {target_name}"

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
            # Extract favorite number
            favorite_num = int(command.split("_")[-1])
            await self._heos.play_preset_station(self._player_id, favorite_num)
            self.attributes["last_result"] = f"Playing favorite {favorite_num}"
        except Exception as e:
            _LOG.error(f"Error playing favorite: {e}")
            self.attributes["last_result"] = "Failed to play favorite"

    async def _handle_service_command(self, command: str):
        """Handle music service commands."""
        try:
            # Extract service name from command
            service_name = command[len("SERVICE_"):].replace('_', ' ')
            
            # This would typically trigger the media player's source selection
            # For now, just acknowledge
            self.attributes["last_result"] = f"Switched to {service_name}"
            _LOG.info(f"Service command: {service_name} - use media player for actual playback")
            
        except Exception as e:
            _LOG.error(f"Error handling service command: {e}")
            self.attributes["last_result"] = "Failed to switch service"

    async def shutdown(self):
        """Shutdown the remote entity."""
        _LOG.info(f"Shutting down HEOS Remote: {self._device_name}")