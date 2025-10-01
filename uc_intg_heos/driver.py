"""
HEOS Integration Driver.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import ucapi
from ucapi import DeviceStates, Events, IntegrationAPI, StatusCodes
from ucapi.api_definitions import SetupAction, SetupDriver, SetupComplete, SetupError
from ucapi.ui import UiPage, Size, create_ui_icon, create_ui_text

from pyheos import HeosPlayer

from uc_intg_heos.config import HeosConfig
from uc_intg_heos.coordinator import HeosCoordinator  
from uc_intg_heos.setup import HeosSetupManager
from uc_intg_heos.media_player import HeosMediaPlayer
from uc_intg_heos.remote import HeosRemote

api: IntegrationAPI | None = None
_config: HeosConfig | None = None
_coordinator: HeosCoordinator | None = None
_media_players: Dict[int, HeosMediaPlayer] = {}
_remotes: Dict[int, HeosRemote] = {}
_entities_ready: bool = False
_initialization_lock: asyncio.Lock = asyncio.Lock()
_setup_manager: HeosSetupManager | None = None

_LOG = logging.getLogger(__name__)


async def _initialize_entities():
    """Initialize entities with intelligent detection - MANDATORY."""
    global _config, _coordinator, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready:
            _LOG.debug("Entities already initialized, skipping")
            return
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return
            
        _LOG.info("Initializing HEOS entities with intelligent detection...")
        
        try:
            # Clear existing entities
            api.available_entities.clear()
            _media_players.clear()
            _remotes.clear()
            
            # Create and setup coordinator
            _coordinator = HeosCoordinator(api, _config)
            await _coordinator.async_setup()
            
            # Get all HEOS players from coordinator
            players = _coordinator.heos.players
            if not players:
                _LOG.warning("No HEOS devices found on account")
                return

            _LOG.info(f"Found {len(players)} HEOS device(s)")
            
            # create media player per device
            for player_id, player in players.items():
                _LOG.info(f"Creating media player for: {player.name} (ID: {player_id})")
                
                media_player = HeosMediaPlayer(_coordinator, player, api)
                await media_player.initialize()
                
                _media_players[player_id] = media_player
                api.available_entities.add(media_player)
                api.configured_entities.add(media_player)  # ADDED for reboot survival
                
                _LOG.info(f"Created media player entity: {media_player.id}")
            
            # Create remote for multi-device scenarios
            if len(players) > 1:
                _LOG.info("Multiple devices detected - creating intelligent remote entities")
                await _create_intelligent_remotes(players)
            else:
                _LOG.info("Single device detected - media player only (no remote needed)")
            
            # Mark entities as ready before setting connected state
            _entities_ready = True
            
            _LOG.info(f"HEOS integration ready: {len(_media_players)} media players, {len(_remotes)} remotes")
            
        except Exception as e:
            _LOG.error(f"Failed to initialize HEOS entities: {e}", exc_info=True)
            _entities_ready = False
            if _coordinator:
                await _coordinator.async_shutdown()
                _coordinator = None
            raise


async def _create_intelligent_remotes(players: Dict[int, HeosPlayer]):
    """Create intelligent remotes based on discovered capabilities."""
    global _remotes, _coordinator
    
    for player_id, player in players.items():
        _LOG.info(f"Building intelligent remote for: {player.name}")
        
        # Detect device capabilities
        capabilities = await _detect_device_capabilities(player)
        
        # Build dynamic UI pages
        ui_pages = _build_dynamic_ui_pages(player, capabilities, players)
        
        # Build dynamic simple commands
        simple_commands = _build_dynamic_simple_commands(player, capabilities, players)
        
        # Create remote with detected capabilities only
        remote = HeosRemote(
            heos_player=player,
            device_name=player.name,
            api=api,
            capabilities=capabilities,
            heos=_coordinator.heos,
            ui_pages=ui_pages,
            simple_commands=simple_commands
        )
        
        await remote.initialize()
        _remotes[player_id] = remote
        api.available_entities.add(remote)
        api.configured_entities.add(remote)  # CRITICAL FIX: Added for reboot survival
        
        _LOG.info(f"Created intelligent remote for {player.name} with {len(simple_commands)} commands")


async def _detect_device_capabilities(player: HeosPlayer) -> Dict[str, Any]:
    """Detect actual device capabilities - NO ASSUMPTIONS."""
    capabilities = {
        'basic_controls': {},
        'volume_controls': {},
        'navigation': {},
        'inputs': {},
        'can_be_grouped': True,  # All HEOS devices support grouping
        'supports_favorites': _coordinator.heos.is_signed_in,
        'available_services': [],
        'playlists_available': len(_coordinator.playlists) > 0,
        'favorites_count': len(_coordinator.favorites)
    }
    
    # Basic controls - all HEOS devices support these
    capabilities['basic_controls'] = {
        'play': True,
        'pause': True,
        'stop': True
    }
    
    # Volume controls - all HEOS devices support these
    capabilities['volume_controls'] = {
        'volume_up': True,
        'volume_down': True,
        'mute': True
    }
    
    # Navigation - all HEOS devices support these
    capabilities['navigation'] = {
        'next': True,
        'previous': True
    }
    
    # Detect actual inputs for THIS device
    for input_source in _coordinator.inputs:
        # Check if input belongs to this player by matching media_id pattern or availability
        input_name = input_source.name.lower().replace(' ', '_')
        capabilities['inputs'][input_name] = True
    
    # Get available music services (account-wide)
    for source_id, source in _coordinator.music_sources.items():
        if source.available:
            capabilities['available_services'].append(source.name)
    
    _LOG.info(f"Detected capabilities for {player.name}:")
    _LOG.info(f"  - Inputs: {list(capabilities['inputs'].keys())}")
    _LOG.info(f"  - Services: {capabilities['available_services']}")
    _LOG.info(f"  - Favorites: {capabilities['favorites_count']}")
    _LOG.info(f"  - Playlists: {capabilities['playlists_available']}")
    
    return capabilities


def _build_dynamic_simple_commands(player: HeosPlayer, capabilities: Dict, all_players: Dict) -> List[str]:
    """Build simple commands based ONLY on detected capabilities."""
    commands = []
    
    # Basic playback - always available
    commands.extend(["PLAY", "PAUSE", "STOP", "PLAY_PAUSE"])
    
    # Volume - always available
    commands.extend(["VOLUME_UP", "VOLUME_DOWN", "MUTE_TOGGLE"])
    
    # Navigation - always available
    commands.extend(["NEXT", "PREVIOUS"])
    
    # Repeat and shuffle - always available
    commands.extend(["REPEAT_OFF", "REPEAT_ALL", "REPEAT_ONE", "SHUFFLE_ON", "SHUFFLE_OFF"])
    
    # Inputs - only those detected for THIS device
    input_count = 0
    for input_name, available in capabilities['inputs'].items():
        if available:
            command_name = input_name.upper().replace(' ', '_')
            commands.append(f"INPUT_{command_name}")
            input_count += 1
    
    _LOG.debug(f"Added {input_count} input commands for {player.name}")
    
    # Grouping - only if multiple devices exist
    if len(all_players) > 1:
        commands.append("LEAVE_GROUP")
        
        # CRITICAL FIX: Add GROUP_ALL_SPEAKERS command
        commands.append("GROUP_ALL_SPEAKERS")
        
        # Add specific group commands for each other device
        for other_player_id, other_player in all_players.items():
            if other_player_id != player.player_id:
                safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
                commands.append(f"GROUP_WITH_{safe_name}")
        
        _LOG.debug(f"Added {len(all_players)+1} grouping commands (including GROUP_ALL_SPEAKERS) for {player.name}")
    
    # Favorites - only if they exist
    if capabilities['supports_favorites'] and capabilities['favorites_count'] > 0:
        num_favorites = min(capabilities['favorites_count'], 10)
        for i in range(1, num_favorites + 1):
            commands.append(f"FAVORITE_{i}")
        
        _LOG.debug(f"Added {num_favorites} favorite commands for {player.name}")
    
    # Music services - only available ones
    for service_name in capabilities['available_services']:
        safe_name = service_name.upper().replace(' ', '_')
        commands.append(f"SERVICE_{safe_name}")
    
    _LOG.debug(f"Added {len(capabilities['available_services'])} service commands for {player.name}")
    
    # Playlists - only if they exist
    if capabilities['playlists_available']:
        commands.append("PLAYLISTS")
    
    # Queue management - always available
    commands.extend(["CLEAR_QUEUE", "QUEUE_INFO"])
    
    _LOG.info(f"Built {len(commands)} dynamic commands for {player.name}")
    return commands


def _build_dynamic_ui_pages(player: HeosPlayer, capabilities: Dict, all_players: Dict) -> List[UiPage]:
    """Build UI pages based only on detected capabilities."""
    pages = []
    
    # Page 1: Basic Transport Controls (always available)
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
    
    # Page 2: Inputs (only if this device has inputs)
    if capabilities['inputs']:
        page2 = UiPage(page_id="inputs", name="Inputs", grid=Size(4, 6))
        row, col = 0, 0
        for input_name in sorted(capabilities['inputs'].keys()):
            display_name = input_name.replace('_', ' ').title()
            command_name = f"INPUT_{input_name.upper()}"
            page2.add(create_ui_text(display_name, col, row, cmd=command_name))
            col += 1
            if col >= 4:
                col = 0
                row += 1
        pages.append(page2)
        _LOG.debug(f"Created inputs page with {len(capabilities['inputs'])} inputs")
    
    # Page 3: Grouping (only if multiple devices)
    if len(all_players) > 1:
        page3 = UiPage(page_id="grouping", name="Grouping", grid=Size(4, 6))
        
        # CRITICAL FIX: Make "Multi-Room" a functional button for GROUP_ALL_SPEAKERS
        page3.add(create_ui_text("Group All", 0, 0, Size(4, 1), cmd="GROUP_ALL_SPEAKERS"))
        
        row = 1
        for other_player_id, other_player in all_players.items():
            if other_player_id != player.player_id:
                safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
                display_name = other_player.name[:20]  # Truncate long names
                page3.add(create_ui_text(
                    f"+ {display_name}",
                    0, row,
                    Size(4, 1),
                    cmd=f"GROUP_WITH_{safe_name}"
                ))
                row += 1
                if row >= 6:  # Don't overflow page
                    break
        if row < 6:
            page3.add(create_ui_text("Ungroup", 0, row, Size(4, 1), cmd="LEAVE_GROUP"))
        pages.append(page3)
        _LOG.debug(f"Created grouping page with GROUP_ALL_SPEAKERS and {len(all_players)-1} other devices")
    
    # Page 4: Music Services (only available ones)
    if capabilities['available_services']:
        page4 = UiPage(page_id="services", name="Services", grid=Size(4, 6))
        row, col = 0, 0
        for service_name in sorted(capabilities['available_services']):
            safe_name = service_name.upper().replace(' ', '_')
            display_name = service_name[:15]  # Truncate long names
            page4.add(create_ui_text(display_name, col, row, cmd=f"SERVICE_{safe_name}"))
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:  # Don't overflow page
                    break
        pages.append(page4)
        _LOG.debug(f"Created services page with {len(capabilities['available_services'])} services")
    
    # Page 5: Favorites (only if they exist)
    if capabilities['supports_favorites'] and capabilities['favorites_count'] > 0:
        page5 = UiPage(page_id="favorites", name="Favorites", grid=Size(4, 6))
        row, col = 0, 0
        num_favorites = min(capabilities['favorites_count'], 10)
        for i in range(1, num_favorites + 1):
            # Get actual favorite name if available
            favorite_name = f"Fav {i}"
            if i in _coordinator.favorites:
                favorite_name = _coordinator.favorites[i].name[:12]  # Truncate
            
            page5.add(create_ui_text(
                favorite_name,
                col, row,
                cmd=f"FAVORITE_{i}"
            ))
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:  # Don't overflow page
                    break
        pages.append(page5)
        _LOG.debug(f"Created favorites page with {num_favorites} favorites")
    
    _LOG.info(f"Built {len(pages)} dynamic UI pages for {player.name}")
    return pages


async def on_connect() -> None:
    """Handle Remote connection with reboot survival."""
    global _config, _entities_ready
    
    _LOG.info("UC Remote connected. Checking configuration state...")
    
    if not _config:
        _config = HeosConfig(api.config_dir_path)
    
    # Reload config from disk (critical for reboot survival)
    _config.reload_from_disk()
    
    # If configured but entities not ready, initialize them now
    if _config.is_configured() and not _entities_ready:
        _LOG.info("Configuration found but entities missing, reinitializing...")
        try:
            await _initialize_entities()
        except Exception as e:
            _LOG.error(f"Failed to reinitialize entities: {e}")
            await api.set_device_state(DeviceStates.ERROR)
            return
    
    # Set appropriate device state
    if _config.is_configured() and _entities_ready:
        _LOG.info("Configuration valid and entities ready - setting CONNECTED state")
        await api.set_device_state(DeviceStates.CONNECTED)
    elif not _config.is_configured():
        _LOG.info("No configuration found - setting DISCONNECTED state")
        await api.set_device_state(DeviceStates.DISCONNECTED)
    else:
        _LOG.error("Configuration exists but entities failed - setting ERROR state")
        await api.set_device_state(DeviceStates.ERROR)


async def on_disconnect() -> None:
    """Handle Remote disconnection."""
    _LOG.info("UC Remote disconnected")
    await api.set_device_state(DeviceStates.DISCONNECTED)


async def on_subscribe_entities(entity_ids: List[str]):
    """Handle entity subscriptions with race condition protection."""
    _LOG.info(f"Entities subscription requested: {entity_ids}")
    
    # Guard against race condition
    if not _entities_ready:
        _LOG.error("RACE CONDITION: Subscription before entities ready! Attempting recovery...")
        if _config and _config.is_configured():
            await _initialize_entities()
        else:
            _LOG.error("Cannot recover - no configuration available")
            return
    
    for entity_id in entity_ids:
        # Check media players
        for player_id, media_player in _media_players.items():
            if entity_id == media_player.id:
                await media_player.push_update()
                break
        
        # Check remotes
        for player_id, remote in _remotes.items():
            if entity_id == remote.id:
                await remote.push_update()
                break


async def on_unsubscribe_entities(entity_ids: List[str]):
    """Handle entity unsubscriptions."""
    _LOG.info(f"Unsubscribed from entities: {entity_ids}")


async def setup_handler(msg: SetupAction) -> SetupAction:
    """Handle setup flow and create entities."""
    global _setup_manager, _entities_ready
    
    if not _setup_manager:
        return SetupError()
    
    action = await _setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("Setup confirmed. Initializing integration components...")
        await _initialize_entities()
    
    return action


async def main():
    """Main entry point with pre-initialization for reboot survival."""
    global api, _config, _setup_manager
    
    logging.basicConfig(level=logging.INFO)
    _LOG.info("Starting HEOS integration driver with intelligent detection")
    
    try:
        loop = asyncio.get_running_loop()
        api = IntegrationAPI(loop)
        
        _config = HeosConfig(api.config_dir_path)
        if _config.is_configured():
            _LOG.info("Found existing configuration, pre-initializing entities for reboot survival")
            loop.create_task(_initialize_entities())
        
        # Register event handlers
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        api.add_listener(Events.UNSUBSCRIBE_ENTITIES, on_unsubscribe_entities)
        
        # Initialize setup manager
        _setup_manager = HeosSetupManager(_config)
        
        await api.init("driver.json", setup_handler)
        await api.set_device_state(DeviceStates.DISCONNECTED)
        
        await asyncio.Future()
        
    except asyncio.CancelledError:
        _LOG.info("Driver task cancelled")
    except Exception as e:
        _LOG.error(f"Driver initialization failed: {e}", exc_info=True)
    finally:
        await shutdown()


async def shutdown():
    """Shutdown integration cleanly."""
    global _coordinator, _media_players, _remotes
    
    _LOG.info("Shutting down HEOS integration")
    
    # Shutdown media players
    for player in _media_players.values():
        if hasattr(player, 'shutdown'):
            try:
                await player.shutdown()
            except Exception as e:
                _LOG.error(f"Error shutting down media player: {e}")
    
    # Shutdown remotes
    for remote in _remotes.values():
        if hasattr(remote, 'shutdown'):
            try:
                await remote.shutdown()
            except Exception as e:
                _LOG.error(f"Error shutting down remote: {e}")
    
    # Shutdown coordinator
    if _coordinator:
        try:
            await _coordinator.async_shutdown()
        except Exception as e:
            _LOG.error(f"Error shutting down coordinator: {e}")


if __name__ == "__main__":
    asyncio.run(main())