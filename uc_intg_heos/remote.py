"""
HEOS Remote entity - Simplified for reboot survival

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any, Dict, List
import asyncio

import ucapi
from ucapi import Remote, StatusCodes
from ucapi.ui import UiPage, Size, create_ui_icon, create_ui_text

from pyheos import Heos, HeosPlayer, HeosError, RepeatType

_LOG = logging.getLogger(__name__)


class HeosRemote(Remote):
    """Simplified HEOS Remote with static capabilities for reboot survival."""
    
    def __init__(self, heos_player: HeosPlayer, device_name: str, api: ucapi.IntegrationAPI, all_players: Dict[int, HeosPlayer]):
        
        # CRITICAL FIX: Strip ALL invalid characters from entity ID
        safe_name = device_name.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('.', '')
        entity_id = f"heos_{safe_name}_remote"
        
        # Store references FIRST before building UI
        self._heos_player = heos_player
        self._api = api
        self._device_name = device_name
        self._player_id = heos_player.player_id
        self._all_players = all_players
        self._heos = None
        
        # Command throttling
        self._last_command_time: Dict[str, float] = {}
        self._command_lock = asyncio.Lock()
        
        # Static attributes
        attributes = {
            "state": "available",
            "device_model": heos_player.model,
            "last_command": "",
            "last_result": ""
        }
        
        # NOW build UI pages and commands (after _player_id is set)
        ui_pages = self._build_static_ui_pages(device_name, all_players)
        simple_commands = self._build_static_commands(all_players)
        
        super().__init__(
            identifier=entity_id,
            name=f"{device_name} Remote",
            features=["send_cmd"],
            attributes=attributes,
            simple_commands=simple_commands,
            ui_pages=ui_pages,
            cmd_handler=self.handle_cmd
        )
        
        _LOG.info(f"Created static HEOS Remote: {device_name} ({entity_id}) with {len(simple_commands)} commands")

    def set_heos(self, heos: Heos):
        """Set HEOS connection reference."""
        self._heos = heos

    def _build_static_commands(self, all_players: Dict[int, HeosPlayer]) -> List[str]:
        """Build static command list - no dynamic detection."""
        commands = []
        
        # Basic playback
        commands.extend(["PLAY", "PAUSE", "STOP", "PLAY_PAUSE"])
        
        # Volume
        commands.extend(["VOLUME_UP", "VOLUME_DOWN", "MUTE_TOGGLE"])
        
        # Navigation
        commands.extend(["NEXT", "PREVIOUS"])
        
        # Repeat and shuffle
        commands.extend(["REPEAT_OFF", "REPEAT_ALL", "REPEAT_ONE", "SHUFFLE_ON", "SHUFFLE_OFF"])
        
        # Grouping - only if multiple devices
        if len(all_players) > 1:
            commands.append("LEAVE_GROUP")
            commands.append("GROUP_ALL_SPEAKERS")
            
            # Add specific group commands for each other device
            for other_player_id, other_player in all_players.items():
                if other_player_id != self._player_id:
                    safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('.', '')
                    commands.append(f"GROUP_WITH_{safe_name}")
        
        _LOG.info(f"Built {len(commands)} static commands for {self._device_name}")
        return commands

    def _build_static_ui_pages(self, device_name: str, all_players: Dict[int, HeosPlayer]) -> List[UiPage]:
        """Build static UI pages - no dynamic content."""
        pages = []
        
        # Page 1: Basic Transport Controls
        page1 = UiPage(
            page_id="transport",
            name="Playback",
            grid=Size(4, 6)
        )
        page1.add(create_ui_icon("uc:play", 0, 0, cmd="PLAY"))
        page1.add(create_ui_icon("uc:pause", 1, 0, cmd="PAUSE"))
        page1.add(create_ui_icon("uc:stop", 2, 0, cmd="STOP"))
        page1.add(create_ui_icon("uc:skip-forward", 3, 0, cmd="NEXT"))
        page1.add(create_ui_icon("uc:skip-backward", 0, 1, cmd="PREVIOUS"))
        page1.add(create_ui_icon("uc:volume-up", 1, 1, cmd="VOLUME_UP"))
        page1.add(create_ui_icon("uc:volume-down", 2, 1, cmd="VOLUME_DOWN"))
        page1.add(create_ui_icon("uc:mute", 3, 1, cmd="MUTE_TOGGLE"))
        page1.add(create_ui_icon("uc:repeat", 0, 2, cmd="REPEAT_ALL"))
        page1.add(create_ui_icon("uc:shuffle", 1, 2, cmd="SHUFFLE_ON"))
        pages.append(page1)
        
        # Page 2: Grouping (only if multiple devices)
        if len(all_players) > 1:
            page2 = UiPage(page_id="grouping", name="Multi-Room", grid=Size(4, 6))
            
            # Group All button
            page2.add(create_ui_text("Group All", 0, 0, Size(4, 1), cmd="GROUP_ALL_SPEAKERS"))
            
            # Individual device grouping buttons
            row = 1
            for other_player_id, other_player in all_players.items():
                if other_player_id != self._player_id and row < 5:
                    safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('.', '')
                    display_name = other_player.name[:20]
                    page2.add(create_ui_text(
                        f"+ {display_name}",
                        0, row,
                        Size(4, 1),
                        cmd=f"GROUP_WITH_{safe_name}"
                    ))
                    row += 1
            
            # Ungroup button
            if row < 6:
                page2.add(create_ui_text("Ungroup", 0, row, Size(4, 1), cmd="LEAVE_GROUP"))
            
            pages.append(page2)
        
        _LOG.info(f"Built {len(pages)} static UI pages for {device_name}")
        return pages

    async def initialize(self) -> None:
        """Initialize the remote entity."""
        await self.push_update()
        _LOG.info(f"Static HEOS Remote initialized: {self._device_name}")
    
    async def push_update(self) -> None:
        """Update remote entity state."""
        try:
            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
        except Exception as e:
            _LOG.error(f"Error updating {self._device_name}: {e}")

    async def update_attributes(self) -> None:
        """Update remote entity state."""
        try:
            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
        except Exception as e:
            _LOG.error(f"Error updating {self._device_name}: {e}")

    async def _execute_with_retry(self, command_func, command_name: str, max_retries: int = 3) -> bool:
        """Execute a command with retry logic."""
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
                        _LOG.warning(f"Command {command_name} failed (processing previous), retrying in {delay}s")
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
        """Handle remote commands - static implementation."""
        async with self._command_lock:
            try:
                actual_command = params.get("command", cmd_id) if params else cmd_id
                _LOG.info(f"Executing HEOS Remote command: {actual_command} for {self._device_name}")
                
                # Throttle commands
                import time
                current_time = time.time()
                last_time = self._last_command_time.get(actual_command, 0)
                time_diff = current_time - last_time
                
                if time_diff < 0.5:
                    wait_time = 0.5 - time_diff
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
                    
                # Group All Speakers
                elif actual_command == "GROUP_ALL_SPEAKERS":
                    await self._handle_group_all_speakers()
                    
                # Group with specific device
                elif actual_command.startswith("GROUP_WITH_"):
                    await self._handle_grouping_commands_with_retry(actual_command)
                    
                elif actual_command == "LEAVE_GROUP":
                    await self._handle_ungroup_command_with_retry()
                    
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
            all_players = self._all_players
            
            if not all_players or len(all_players) <= 1:
                self.attributes["last_result"] = "No other speakers available"
                return
            
            player_ids = [self._player_id]
            speaker_names = [self._device_name]
            
            for player_id, player in all_players.items():
                if player_id != self._player_id:
                    player_ids.append(player_id)
                    speaker_names.append(player.name)
            
            _LOG.info(f"Creating all-speakers group with {len(player_ids)} devices")
            
            async def group_all_command():
                await self._heos.set_group(player_ids)
            
            success = await self._execute_with_retry(group_all_command, "GROUP_ALL_SPEAKERS")
            
            if success:
                self.attributes["last_result"] = f"Grouped {len(player_ids)} speakers"
            else:
                self.attributes["last_result"] = "Failed to group all speakers"
                
        except Exception as e:
            _LOG.error(f"Error creating all-speakers group: {e}")
            self.attributes["last_result"] = "Failed to group all speakers"

    async def _handle_grouping_commands_with_retry(self, command: str):
        """Handle group management commands with retry logic."""
        target_name = command[len("GROUP_WITH_"):]
        
        try:
            target_player_id = None
            for player_id, player in self._all_players.items():
                safe_name = player.name.upper().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('.', '')
                if safe_name == target_name:
                    target_player_id = player_id
                    break
            
            if target_player_id:
                async def group_command():
                    await self._heos.set_group([self._player_id, target_player_id])
                
                success = await self._execute_with_retry(group_command, f"GROUP_WITH_{target_name}")
                
                if success:
                    self.attributes["last_result"] = f"Grouped with {target_name.replace('_', ' ').title()}"
                else:
                    self.attributes["last_result"] = "Failed to group"
            else:
                self.attributes["last_result"] = f"Device not found: {target_name}"
                
        except Exception as e:
            _LOG.error(f"Error grouping with {target_name}: {e}")
            self.attributes["last_result"] = "Failed to group"

    async def _handle_ungroup_command_with_retry(self):
        """Handle ungrouping player with retry logic."""
        try:
            async def ungroup_command():
                await self._heos.set_group([self._player_id])
            
            success = await self._execute_with_retry(ungroup_command, "LEAVE_GROUP")
            
            if success:
                self.attributes["last_result"] = "Left group"
            else:
                self.attributes["last_result"] = "Failed to leave group"
                
        except Exception as e:
            _LOG.error(f"Error leaving group: {e}")
            self.attributes["last_result"] = "Failed to leave group"

    async def shutdown(self):
        """Shutdown the remote entity."""
        _LOG.info(f"Shutting down HEOS Remote: {self._device_name}")