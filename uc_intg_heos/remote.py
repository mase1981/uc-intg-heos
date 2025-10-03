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

from pyheos import Heos, HeosPlayer, HeosError, RepeatType

_LOG = logging.getLogger(__name__)


class HeosRemote(Remote):
    """HEOS Remote entity with dynamic capability discovery."""
    
    def __init__(self, heos_player: HeosPlayer, device_name: str):
        """Initialize remote entity with MINIMAL setup (WiiM pattern)."""
        entity_id = f"heos_{device_name.lower().replace(' ', '_').replace('-', '_')}_remote"
        
        # Start with basic features and minimal UI
        features = ["send_cmd"]
        attributes = {"state": "available"}
        
        # Build minimal base commands
        simple_commands = self._build_base_commands()
        
        # Build minimal main page (as DICTIONARY)
        ui_pages = [self._create_main_page()]
        
        super().__init__(
            identifier=entity_id,
            name=f"{device_name} Remote",
            features=features,
            attributes=attributes,
            simple_commands=simple_commands,
            ui_pages=ui_pages,
            cmd_handler=self.handle_cmd
        )
        
        # Store references
        self._heos_player = heos_player
        self._device_name = device_name
        self._player_id = heos_player.player_id
        
        # Will be set externally
        self._api = None
        self._heos = None
        self._coordinator = None
        self._capabilities = {}
        self._all_players = {}
        
        # Initialization flag
        self._capabilities_initialized = False
        
        # Command throttling
        self._last_command_time: Dict[str, float] = {}
        self._command_lock = asyncio.Lock()
        
        _LOG.info(f"Created HEOS Remote: {device_name} ({entity_id})")

    def set_coordinator(self, coordinator, heos: Heos, all_players: Dict):
        """Set coordinator and HEOS instance (called externally)."""
        self._coordinator = coordinator
        self._heos = heos
        self._all_players = all_players

    def _build_base_commands(self) -> List[str]:
        """Build base command list (always available)."""
        return [
            "PLAY", "PAUSE", "STOP", "PLAY_PAUSE",
            "VOLUME_UP", "VOLUME_DOWN", "MUTE_TOGGLE",
            "NEXT", "PREVIOUS",
            "REPEAT_OFF", "REPEAT_ALL", "REPEAT_ONE",
            "SHUFFLE_ON", "SHUFFLE_OFF"
        ]

    def _create_main_page(self) -> Dict[str, Any]:
        """Create main transport control page as DICTIONARY."""
        return {
            'page_id': 'transport',
            'name': 'Playback',
            'grid': {'width': 4, 'height': 6},
            'items': [
                {'type': 'icon', 'location': {'x': 0, 'y': 0}, 'icon': 'uc:play',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'PLAY'}}},
                {'type': 'icon', 'location': {'x': 1, 'y': 0}, 'icon': 'uc:pause',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'PAUSE'}}},
                {'type': 'icon', 'location': {'x': 2, 'y': 0}, 'icon': 'uc:stop',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'STOP'}}},
                {'type': 'icon', 'location': {'x': 3, 'y': 0}, 'icon': 'uc:skip-forward',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'NEXT'}}},
                {'type': 'icon', 'location': {'x': 0, 'y': 1}, 'icon': 'uc:skip-backward',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'PREVIOUS'}}},
                {'type': 'icon', 'location': {'x': 1, 'y': 1}, 'icon': 'uc:volume-up',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'VOLUME_UP'}}},
                {'type': 'icon', 'location': {'x': 2, 'y': 1}, 'icon': 'uc:volume-down',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'VOLUME_DOWN'}}},
                {'type': 'icon', 'location': {'x': 3, 'y': 1}, 'icon': 'uc:mute',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'MUTE_TOGGLE'}}},
                {'type': 'icon', 'location': {'x': 0, 'y': 2}, 'icon': 'uc:repeat',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'REPEAT_ALL'}}},
                {'type': 'icon', 'location': {'x': 1, 'y': 2}, 'icon': 'uc:shuffle',
                 'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'SHUFFLE_ON'}}},
            ]
        }

    async def initialize(self):
        """Basic initialization."""
        await self.push_update()
        _LOG.info(f"HEOS Remote initialized: {self._device_name}")

    async def initialize_capabilities(self):
        """Initialize full capabilities after coordinator is ready (WiiM pattern)."""
        if self._capabilities_initialized or not self._coordinator:
            return
        
        _LOG.info(f"Initializing capabilities for {self._device_name}...")
        
        try:
            # Build capabilities from coordinator
            self._capabilities = await self._detect_device_capabilities()
            
            # Build extended commands
            extended_commands = self._build_extended_commands()
            
            # Build all UI pages (as DICTIONARIES)
            all_pages = self._create_dynamic_pages()
            
            # Update entity options (WiiM pattern)
            self.options = {
                'simple_commands': extended_commands,
                'user_interface': {'pages': all_pages}
            }
            
            self.attributes["state"] = "available"
            self.attributes["capabilities"] = self._capabilities
            
            # Force update
            await self.push_update()
            
            self._capabilities_initialized = True
            _LOG.info(f"✓ Remote capabilities initialized for {self._device_name}: "
                     f"{len(extended_commands)} commands, {len(all_pages)} pages")
            
        except Exception as e:
            _LOG.error(f"Error initializing capabilities: {e}", exc_info=True)

    async def _detect_device_capabilities(self) -> Dict[str, Any]:
        """Detect device capabilities from coordinator."""
        capabilities = {
            'basic_controls': {'play': True, 'pause': True, 'stop': True},
            'volume_controls': {'volume_up': True, 'volume_down': True, 'mute': True},
            'navigation': {'next': True, 'previous': True},
            'inputs': {},
            'can_be_grouped': True,
            'supports_favorites': False,
            'available_services': [],
            'playlists_available': False,
            'favorites_count': 0
        }
        
        if not self._coordinator:
            return capabilities
        
        try:
            if self._coordinator.heos and self._coordinator.heos.is_signed_in:
                capabilities['supports_favorites'] = True
            
            if self._coordinator.favorites:
                capabilities['favorites_count'] = len(self._coordinator.favorites)
            
            if self._coordinator.playlists:
                capabilities['playlists_available'] = len(self._coordinator.playlists) > 0
            
            if self._coordinator.inputs:
                for input_source in self._coordinator.inputs:
                    try:
                        input_name = input_source.name.lower().replace(' ', '_').replace('-', '_')
                        capabilities['inputs'][input_name] = True
                    except (AttributeError, TypeError):
                        pass
            
            if self._coordinator.music_sources:
                for source_id, source in self._coordinator.music_sources.items():
                    try:
                        if source.available:
                            capabilities['available_services'].append(source.name)
                    except (AttributeError, TypeError):
                        pass
        
        except Exception as e:
            _LOG.warning(f"Error detecting capabilities: {e}")
        
        return capabilities

    def _build_extended_commands(self) -> List[str]:
        """Build full command list based on capabilities."""
        commands = self._build_base_commands()
        
        # Add inputs
        for input_name in self._capabilities['inputs'].keys():
            command_name = input_name.upper().replace(' ', '_')
            commands.append(f"INPUT_{command_name}")
        
        # Add grouping (if multiple devices)
        if len(self._all_players) > 1:
            commands.append("LEAVE_GROUP")
            commands.append("GROUP_ALL_SPEAKERS")
            
            for other_player_id, other_player in self._all_players.items():
                if other_player_id != self._player_id:
                    safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
                    commands.append(f"GROUP_WITH_{safe_name}")
        
        # Add favorites
        if self._capabilities['supports_favorites'] and self._capabilities['favorites_count'] > 0:
            num_favorites = min(self._capabilities['favorites_count'], 10)
            for i in range(1, num_favorites + 1):
                commands.append(f"FAVORITE_{i}")
        
        # Add services
        for service_name in self._capabilities['available_services']:
            safe_name = service_name.upper().replace(' ', '_')
            commands.append(f"SERVICE_{safe_name}")
        
        # Add playlists
        if self._capabilities['playlists_available']:
            commands.append("PLAYLISTS")
        
        # Queue management
        commands.extend(["CLEAR_QUEUE", "QUEUE_INFO"])
        
        return commands

    def _create_dynamic_pages(self) -> List[Dict[str, Any]]:
        """Create all UI pages as DICTIONARIES."""
        pages = [self._create_main_page()]
        
        # Add input page if inputs exist
        if self._capabilities['inputs']:
            if input_page := self._create_inputs_page():
                pages.append(input_page)
        
        # Add grouping page if multiple devices
        if len(self._all_players) > 1:
            if grouping_page := self._create_grouping_page():
                pages.append(grouping_page)
        
        # Add services page
        if self._capabilities['available_services']:
            if services_page := self._create_services_page():
                pages.append(services_page)
        
        # Add favorites page
        if self._capabilities['supports_favorites'] and self._capabilities['favorites_count'] > 0:
            if favorites_page := self._create_favorites_page():
                pages.append(favorites_page)
        
        return pages

    def _create_inputs_page(self) -> Optional[Dict[str, Any]]:
        """Create inputs page as DICTIONARY."""
        page = {
            'page_id': 'inputs',
            'name': 'Inputs',
            'grid': {'width': 4, 'height': 6},
            'items': []
        }
        
        row, col = 0, 0
        for input_name in sorted(self._capabilities['inputs'].keys()):
            display_name = input_name.replace('_', ' ').title()
            command_name = f"INPUT_{input_name.upper()}"
            
            page['items'].append({
                'type': 'text',
                'location': {'x': col, 'y': row},
                'text': display_name,
                'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': command_name}}
            })
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        
        return page if page['items'] else None

    def _create_grouping_page(self) -> Optional[Dict[str, Any]]:
        """Create grouping page as DICTIONARY."""
        page = {
            'page_id': 'grouping',
            'name': 'Grouping',
            'grid': {'width': 4, 'height': 6},
            'items': [
                {
                    'type': 'text',
                    'location': {'x': 0, 'y': 0},
                    'size': {'width': 4, 'height': 1},
                    'text': 'Group All',
                    'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'GROUP_ALL_SPEAKERS'}}
                }
            ]
        }
        
        row = 1
        for other_player_id, other_player in self._all_players.items():
            if other_player_id != self._player_id:
                safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
                display_name = other_player.name[:20]
                
                page['items'].append({
                    'type': 'text',
                    'location': {'x': 0, 'y': row},
                    'size': {'width': 4, 'height': 1},
                    'text': f"+ {display_name}",
                    'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': f"GROUP_WITH_{safe_name}"}}
                })
                
                row += 1
                if row >= 6:
                    break
        
        if row < 6:
            page['items'].append({
                'type': 'text',
                'location': {'x': 0, 'y': row},
                'size': {'width': 4, 'height': 1},
                'text': 'Ungroup',
                'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': 'LEAVE_GROUP'}}
            })
        
        return page

    def _create_services_page(self) -> Optional[Dict[str, Any]]:
        """Create services page as DICTIONARY."""
        page = {
            'page_id': 'services',
            'name': 'Services',
            'grid': {'width': 4, 'height': 6},
            'items': []
        }
        
        row, col = 0, 0
        for service_name in sorted(self._capabilities['available_services']):
            safe_name = service_name.upper().replace(' ', '_')
            display_name = service_name[:15]
            
            page['items'].append({
                'type': 'text',
                'location': {'x': col, 'y': row},
                'text': display_name,
                'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': f"SERVICE_{safe_name}"}}
            })
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        
        return page if page['items'] else None

    def _create_favorites_page(self) -> Optional[Dict[str, Any]]:
        """Create favorites page as DICTIONARY."""
        page = {
            'page_id': 'favorites',
            'name': 'Favorites',
            'grid': {'width': 4, 'height': 6},
            'items': []
        }
        
        row, col = 0, 0
        num_favorites = min(self._capabilities['favorites_count'], 10)
        
        for i in range(1, num_favorites + 1):
            favorite_name = f"Favorite {i}"
            
            # Get actual name from coordinator
            try:
                if self._coordinator and i in self._coordinator.favorites:
                    favorite_name = self._coordinator.favorites[i].name[:12]
            except Exception:
                pass
            
            page['items'].append({
                'type': 'text',
                'location': {'x': col, 'y': row},
                'text': favorite_name,
                'command': {'cmd_id': 'remote.send_cmd', 'params': {'command': f"FAVORITE_{i}"}}
            })
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        
        return page if page['items'] else None

    async def push_update(self):
        """Push update to UC Remote."""
        if self._api and self._api.configured_entities.contains(self.id):
            self._api.configured_entities.update_attributes(self.id, self.attributes)

    async def handle_cmd(self, entity, cmd_id: str, params: Dict[str, Any] = None) -> StatusCodes:
        """Handle remote commands with throttling."""
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
                
                # Basic playback commands
                if actual_command == "PLAY":
                    await self._heos.player_set_play_state(self._player_id, "play")
                    
                elif actual_command == "PAUSE":
                    await self._heos.player_set_play_state(self._player_id, "pause")
                    
                elif actual_command == "STOP":
                    await self._heos.player_set_play_state(self._player_id, "stop")
                    
                elif actual_command == "PLAY_PAUSE":
                    current_state = self._heos_player.state
                    new_state = "pause" if str(current_state) == "PlayState.PLAY" else "play"
                    await self._heos.player_set_play_state(self._player_id, new_state)
                    
                # Volume commands
                elif actual_command == "VOLUME_UP":
                    await self._heos.player_volume_up(self._player_id, step=5)
                    
                elif actual_command == "VOLUME_DOWN":
                    await self._heos.player_volume_down(self._player_id, step=5)
                    
                elif actual_command == "MUTE_TOGGLE":
                    await self._heos.player_toggle_mute(self._player_id)
                    
                # Navigation commands
                elif actual_command == "NEXT":
                    await self._heos.player_play_next(self._player_id)
                    
                elif actual_command == "PREVIOUS":
                    await self._heos.player_play_previous(self._player_id)
                    
                # Repeat commands
                elif actual_command == "REPEAT_OFF":
                    await self._heos.player_set_play_mode(self._player_id, RepeatType.OFF, self._heos_player.shuffle)
                    
                elif actual_command == "REPEAT_ALL":
                    await self._heos.player_set_play_mode(self._player_id, RepeatType.ON_ALL, self._heos_player.shuffle)
                    
                elif actual_command == "REPEAT_ONE":
                    await self._heos.player_set_play_mode(self._player_id, RepeatType.ON_ONE, self._heos_player.shuffle)
                    
                # Shuffle commands
                elif actual_command == "SHUFFLE_ON":
                    await self._heos.player_set_play_mode(self._player_id, self._heos_player.repeat, True)
                    
                elif actual_command == "SHUFFLE_OFF":
                    await self._heos.player_set_play_mode(self._player_id, self._heos_player.repeat, False)
                    
                # Input source commands
                elif actual_command.startswith("INPUT_"):
                    await self._handle_input_commands(actual_command)
                    
                # Group all speakers
                elif actual_command == "GROUP_ALL_SPEAKERS":
                    await self._handle_group_all_speakers()
                    
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
                    
                else:
                    _LOG.warning(f"Unsupported remote command: {actual_command}")
                    return StatusCodes.NOT_IMPLEMENTED

                return StatusCodes.OK
                
            except HeosError as e:
                _LOG.error(f"HEOS command failed for '{cmd_id}': {e}")
                return StatusCodes.SERVER_ERROR
                
            except Exception as e:
                _LOG.error(f"Error handling command '{cmd_id}': {e}", exc_info=True)
                return StatusCodes.SERVER_ERROR

    async def _handle_input_commands(self, command: str):
        """Handle input source commands."""
        input_name = command[len("INPUT_"):].lower()
        heos_input = f"inputs/{input_name}"
        
        try:
            await self._heos.play_input_source(self._player_id, heos_input)
            _LOG.info(f"Switched to {input_name}")
        except Exception as e:
            _LOG.error(f"Error playing input {input_name}: {e}")

    async def _handle_group_all_speakers(self):
        """Handle creating a group with ALL available speakers."""
        try:
            all_players = self._heos.players
            
            if not all_players or len(all_players) <= 1:
                _LOG.warning("Cannot create all-speakers group: only one device available")
                return
            
            player_ids = [self._player_id]
            for player_id in all_players.keys():
                if player_id != self._player_id:
                    player_ids.append(player_id)
            
            await self._heos.set_group(player_ids)
            _LOG.info(f"Created all-speakers group with {len(player_ids)} devices")
                
        except Exception as e:
            _LOG.error(f"Error creating all-speakers group: {e}")

    async def _handle_grouping_commands_with_retry(self, command: str):
        """Handle group management commands."""
        target_name = command[len("GROUP_WITH_"):]
        
        try:
            target_player_id = None
            for player_id, player in self._heos.players.items():
                if player.name.upper().replace(' ', '_').replace('-', '_') == target_name:
                    target_player_id = player_id
                    break
            
            if target_player_id:
                await self._heos.set_group([self._player_id, target_player_id])
                _LOG.info(f"Grouped with {target_name}")
            else:
                _LOG.warning(f"Could not find device: {target_name}")
                
        except Exception as e:
            _LOG.error(f"Error grouping with {target_name}: {e}")

    async def _handle_ungroup_command_with_retry(self):
        """Handle ungrouping player."""
        try:
            await self._heos.set_group([self._player_id])
            _LOG.info("Left group")
        except Exception as e:
            _LOG.error(f"Error leaving group: {e}")

    async def _handle_favorite_command(self, command: str):
        """Handle favorite playback commands."""
        try:
            favorite_num = int(command.split("_")[-1])
            await self._heos.play_preset_station(self._player_id, favorite_num)
            _LOG.info(f"Playing favorite {favorite_num}")
        except Exception as e:
            _LOG.error(f"Error playing favorite: {e}")

    async def _handle_service_command(self, command: str):
        """Handle music service commands."""
        service_name = command[len("SERVICE_"):].replace('_', ' ')
        _LOG.info(f"Service command: {service_name} - use media player for actual playback")

    async def shutdown(self):
        """Shutdown the remote entity."""
        _LOG.info(f"Shutting down HEOS Remote: {self._device_name}")