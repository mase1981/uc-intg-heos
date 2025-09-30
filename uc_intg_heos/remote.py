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
        retry_delays = [1.0, 2.0, 3.0]
        
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
        _LOG.info(f"Remote command received: {cmd_id} for {self._device_name}")
        
        async with self._command_lock:
            try:
                # Map remote command to actual command
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

    async def _handle_group_all_speakers(self):
        """
        CRITICAL FIX: Handle creating a group with ALL available speakers.
        
        This gathers all player IDs from the HEOS system and creates a single
        multi-room group with this device as the leader.
        """
        try:
            # Get all players from HEOS
            all_players = self._heos.players
            
            if not all_players or len(all_players) <= 1:
                self.attributes["last_result"] = "No other speakers available"
                _LOG.warning("Cannot create all-speakers group: only one device available")
                return
            
            # Build list of all player IDs with current player as leader (first)
            player_ids = [self._player_id]
            speaker_names = [self._device_name]
            
            for player_id, player in all_players.items():
                if player_id != self._player_id:
                    player_ids.append(player_id)
                    speaker_names.append(player.name)
            
            _LOG.info(f"Creating all-speakers group with {len(player_ids)} devices: {speaker_names}")
            
            # Create group with retry logic
            async def group_all_command():
                await self._heos.set_group(player_ids)
            
            success = await self._execute_with_retry(
                group_all_command,
                "GROUP_ALL_SPEAKERS"
            )
            
            if success:
                speakers_list = ", ".join(speaker_names)
                self.attributes["last_result"] = f"Grouped {len(player_ids)} speakers: {speakers_list[:50]}"
                _LOG.info(f"✓ Successfully created all-speakers group with {len(player_ids)} devices")
            else:
                self.attributes["last_result"] = f"Failed to group all speakers after retries"
                _LOG.error("Failed to create all-speakers group after retries")
                
        except Exception as e:
            _LOG.error(f"Error creating all-speakers group: {e}", exc_info=True)
            self.attributes["last_result"] = f"Failed to group all speakers: {str(e)}"

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
            favorite_num = int(command.split("_")[-1])
            
            # Get favorite from coordinator
            from uc_intg_heos.driver import _coordinator
            
            if _coordinator and favorite_num in _coordinator.favorites:
                favorite = _coordinator.favorites[favorite_num]
                await self._heos.play_preset_station(self._player_id, favorite_num)
                self.attributes["last_result"] = f"Playing: {favorite.name}"
            else:
                self.attributes["last_result"] = f"Favorite {favorite_num} not found"
                
        except Exception as e:
            _LOG.error(f"Error playing favorite: {e}")
            self.attributes["last_result"] = f"Failed to play favorite"

    async def _handle_service_command(self, command: str):
        """Handle music service commands."""
        service_name = command[len("SERVICE_"):].replace('_', ' ')
        
        try:
            # Get coordinator for service access
            from uc_intg_heos.driver import _coordinator
            
            if _coordinator:
                # Find matching service
                for source_id, source in _coordinator.music_sources.items():
                    if source.name.upper().replace(' ', '_') == command[len("SERVICE_"):]:
                        await self._heos.browse_source(source_id)
                        self.attributes["last_result"] = f"Browsing: {source.name}"
                        return
            
            self.attributes["last_result"] = f"Service {service_name} not available"
            
        except Exception as e:
            _LOG.error(f"Error accessing service: {e}")
            self.attributes["last_result"] = f"Failed to access {service_name}"

    async def shutdown(self):
        """Shutdown the remote entity."""
        _LOG.info(f"Shutting down HEOS Remote: {self._device_name}")