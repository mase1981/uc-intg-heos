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
from ucapi.ui import UiPage, Size, create_ui_icon, create_ui_text

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
        
        # Build minimal main page
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

    def _create_main_page(self) -> UiPage:
        """Create main transport control page (always available)."""
        page = UiPage(page_id="transport", name="Playback", grid=Size(4, 6))
        page.add(create_ui_icon("uc:play", 0, 0, cmd="PLAY"))
        page.add(create_ui_icon("uc:pause", 1, 0, cmd="PAUSE"))
        page.add(create_ui_icon("uc:stop", 2, 0, cmd="STOP"))
        page.add(create_ui_icon("uc:skip-forward", 3, 0, cmd="NEXT"))
        page.add(create_ui_icon("uc:skip-backward", 0, 1, cmd="PREVIOUS"))
        page.add(create_ui_icon("uc:volume-up", 1, 1, cmd="VOLUME_UP"))
        page.add(create_ui_icon("uc:volume-down", 2, 1, cmd="VOLUME_DOWN"))
        page.add(create_ui_icon("uc:mute", 3, 1, cmd="MUTE_TOGGLE"))
        page.add(create_ui_icon("uc:repeat", 0, 2, cmd="REPEAT_ALL"))
        page.add(create_ui_icon("uc:shuffle", 1, 2, cmd="SHUFFLE_ON"))
        return page

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
            
            # Build all UI pages
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
        """Create all UI pages based on capabilities."""
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

    def _create_inputs_page(self) -> Optional[UiPage]:
        """Create inputs page."""
        page = UiPage(page_id="inputs", name="Inputs", grid=Size(4, 6))
        row, col = 0, 0
        
        for input_name in sorted(self._capabilities['inputs'].keys()):
            display_name = input_name.replace('_', ' ').title()
            command_name = f"INPUT_{input_name.upper()}"
            page.add(create_ui_text(display_name, col, row, cmd=command_name))
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        
        return page

    def _create_grouping_page(self) -> Optional[UiPage]:
        """Create grouping page."""
        page = UiPage(page_id="grouping", name="Grouping", grid=Size(4, 6))
        page.add(create_ui_text("Group All", 0, 0, Size(4, 1), cmd="GROUP_ALL_SPEAKERS"))
        
        row = 1
        for other_player_id, other_player in self._all_players.items():
            if other_player_id != self._player_id:
                safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
                display_name = other_player.name[:20]
                page.add(create_ui_text(
                    f"+ {display_name}",
                    0, row,
                    Size(4, 1),
                    cmd=f"GROUP_WITH_{safe_name}"
                ))
                row += 1
                if row >= 6:
                    break
        
        if row < 6:
            page.add(create_ui_text("Ungroup", 0, row, Size(4, 1), cmd="LEAVE_GROUP"))
        
        return page

    def _create_services_page(self) -> Optional[UiPage]:
        """Create services page."""
        page = UiPage(page_id="services", name="Services", grid=Size(4, 6))
        row, col = 0, 0
        
        for service_name in sorted(self._capabilities['available_services']):
            safe_name = service_name.upper().replace(' ', '_')
            display_name = service_name[:15]
            page.add(create_ui_text(display_name, col, row, cmd=f"SERVICE_{safe_name}"))
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        
        return page

    def _create_favorites_page(self) -> Optional[UiPage]:
        """Create favorites page."""
        page = UiPage(page_id="favorites", name="Favorites", grid=Size(4, 6))
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
            
            page.add(create_ui_text(favorite_name, col, row, cmd=f"FAVORITE_{i}"))
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        
        return page

    async def push_update(self):
        """Push update to UC Remote."""
        if self._api and self._api.configured_entities.contains(self.id):
            self._api.configured_entities.update_attributes(self.id, self.attributes)

    async def handle_cmd(self, entity, cmd_id: str, params: Dict[str, Any] = None) -> StatusCodes:
        """Handle remote commands (same as before)."""
        # ... keep existing command handling code ...
        pass

    async def shutdown(self):
        """Shutdown the remote entity."""
        _LOG.info(f"Shutting down HEOS Remote: {self._device_name}")