"""
HEOS Integration Driver.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Dict, List

from ucapi import (
    IntegrationAPI,
    StatusCodes,
    MediaPlayer,
)
from ucapi.api import filter_log_msg_data
from ucapi.media_player import Attributes as MediaAttr

from pyheos import (
    Credentials,
    Heos,
    HeosError,
    HeosOptions,
    HeosPlayer,
    const as heos_const
)

from uc_intg_heos.media_player import HeosMediaPlayer
from uc_intg_heos.remote import HeosRemote
from uc_intg_heos.config import HeosConfig
from uc_intg_heos.coordinator import HeosCoordinator
from uc_intg_heos.setup import HeosSetupManager

from ucapi import (
    DeviceStates,
    EntityTypes,
    Events,
    Remote,
    SetupAction,
    SetupComplete,
    SetupError,
)

from ucapi.ui import (
    Buttons,
    DeviceButtonMapping,
    Size,
    UiPage,
    create_btn_mapping,
)

_LOG = logging.getLogger(__name__)

# Global integration components
api: IntegrationAPI | None = None
_config: HeosConfig | None = None
_coordinator: HeosCoordinator | None = None
_media_players: Dict[int, HeosMediaPlayer] = {}
_remotes: Dict[int, HeosRemote] = {}
_entities_ready: bool = False
_initialization_lock: asyncio.Lock = asyncio.Lock()
_setup_manager: HeosSetupManager | None = None


def create_ui_text(text: str, x: int, y: int, size: Size = None, cmd: str = None) -> dict:
    """Helper to create UI text element."""
    element = {
        "type": "text",
        "text": text,
        "x": x,
        "y": y
    }
    if size:
        element["size"] = {"width": size.width, "height": size.height}
    if cmd:
        element["command"] = cmd
    return element


async def _initialize_entities():

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
            
            # Create media player per device
            for player_id, player in players.items():
                _LOG.info(f"Creating media player for: {player.name} (ID: {player_id})")
                
                media_player = HeosMediaPlayer(_coordinator, player, api)
                await media_player.initialize()
                
                _media_players[player_id] = media_player
                api.available_entities.add(media_player)
                
                _LOG.info(f"Created media player entity: {media_player.id}")
            
            # Create remote for multi-device scenarios
            if len(players) > 1:
                _LOG.info("Multiple devices detected - creating intelligent remote entities")
                await _create_intelligent_remotes(players)
            else:
                _LOG.info("Single device detected - media player only (no remote needed)")
            
            # CRITICAL FIX: Set entities_ready ONLY after all entities are in api.available_entities
            _entities_ready = True
            
            _LOG.info(f"✓ HEOS entities ready: {len(_media_players)} media players, {len(_remotes)} remotes")
            _LOG.info(f"✓ Entities in api.available_entities: {len(api.available_entities.get_all())}")
            
        except Exception as e:
            _LOG.error(f"Failed to initialize HEOS entities: {e}", exc_info=True)
            _entities_ready = False
            if _coordinator:
                await _coordinator.async_shutdown()
                _coordinator = None
            raise


async def _create_intelligent_remotes(players: Dict[int, HeosPlayer]):
    """
    Create intelligent remotes with multi-room support - ENHANCED FOR ALL-SPEAKERS GROUP.
    """
    global _remotes, api
    
    _LOG.info("Building intelligent remote controls for multi-device scenario")
    
    for player_id, player in players.items():
        _LOG.info(f"Analyzing capabilities for {player.name}")
        
        # Detect device capabilities
        capabilities = await _detect_device_capabilities(player, player_id)
        
        # Build UI pages
        ui_pages = await _build_dynamic_ui_pages(player, capabilities, players)
        
        # Build simple commands
        simple_commands = _build_simple_commands(capabilities, players)
        
        # Create remote entity
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
        # CRITICAL: Add to available_entities immediately
        api.available_entities.add(remote)
        
        _LOG.info(f"Created intelligent remote: {remote.id}")


async def _detect_device_capabilities(player: HeosPlayer, player_id: int) -> Dict[str, any]:
    """Detect what this device can actually do."""
    capabilities = {
        'supports_inputs': False,
        'available_inputs': [],
        'supports_favorites': False,
        'favorites_count': 0,
        'supports_playlists': False,
        'playlists_count': 0,
        'supports_services': False,
        'available_services': [],
        'supports_grouping': True,
        'supports_repeat': True,
        'supports_shuffle': True,
    }
    
    try:
        # Check inputs
        if _coordinator and _coordinator.inputs:
            for input_item in _coordinator.inputs:
                if hasattr(input_item, 'playable') and input_item.playable:
                    capabilities['supports_inputs'] = True
                    capabilities['available_inputs'].append(input_item.name)
        
        # Check favorites
        if _coordinator and _coordinator.favorites:
            capabilities['supports_favorites'] = True
            capabilities['favorites_count'] = len(_coordinator.favorites)
        
        # Check playlists
        if _coordinator and _coordinator.playlists:
            capabilities['supports_playlists'] = True
            capabilities['playlists_count'] = len(_coordinator.playlists)
        
        # Check music services
        if _coordinator and _coordinator.music_sources:
            for source_id, source in _coordinator.music_sources.items():
                if hasattr(source, 'available') and source.available:
                    capabilities['supports_services'] = True
                    capabilities['available_services'].append(source.name)
        
        _LOG.info(f"Device capabilities for {player.name}: "
                 f"Inputs={capabilities['supports_inputs']}, "
                 f"Favorites={capabilities['favorites_count']}, "
                 f"Services={len(capabilities['available_services'])}")
        
    except Exception as e:
        _LOG.error(f"Error detecting capabilities for {player.name}: {e}")
    
    return capabilities


def _build_simple_commands(capabilities: Dict[str, any], all_players: Dict[int, HeosPlayer]) -> List[str]:
    """
    Build simple command list - ENHANCED WITH ALL-SPEAKERS GROUP.
    """
    commands = [
        "VOLUME_UP",
        "VOLUME_DOWN", 
        "MUTE_TOGGLE",
        "CURSOR_UP",
        "CURSOR_DOWN",
        "CURSOR_LEFT",
        "CURSOR_RIGHT",
        "CURSOR_ENTER",
        "BACK",
        "HOME"
    ]
    
    # Add grouping commands
    if len(all_players) > 1:
        # Add individual speaker grouping
        for other_player_id, other_player in all_players.items():
            safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
            commands.append(f"GROUP_WITH_{safe_name}")
        
        # CRITICAL FIX: Add "all speakers" group command
        commands.append("GROUP_ALL_SPEAKERS")
        commands.append("LEAVE_GROUP")
    
    # Add input commands
    if capabilities['supports_inputs']:
        for input_name in capabilities['available_inputs']:
            safe_name = input_name.upper().replace(' ', '_').replace('/', '_')
            commands.append(f"INPUT_{safe_name}")
    
    # Add service commands
    if capabilities['available_services']:
        for service_name in capabilities['available_services']:
            safe_name = service_name.upper().replace(' ', '_')
            commands.append(f"SERVICE_{safe_name}")
    
    # Add favorite commands
    if capabilities['supports_favorites']:
        for i in range(1, min(capabilities['favorites_count'] + 1, 11)):
            commands.append(f"FAVORITE_{i}")
    
    return commands


async def _build_dynamic_ui_pages(player: HeosPlayer, capabilities: Dict[str, any], 
                                   all_players: Dict[int, HeosPlayer]) -> List[UiPage]:
    """
    Build dynamic UI pages - ENHANCED WITH ALL-SPEAKERS GROUP BUTTON.
    """
    pages = []
    
    # Page 1: Playback Controls
    page1 = UiPage(page_id="playback", name="Playback", grid=Size(4, 6))
    page1.add(create_ui_text("Play", 0, 0, cmd="PLAY"))
    page1.add(create_ui_text("Pause", 1, 0, cmd="PAUSE"))
    page1.add(create_ui_text("Stop", 2, 0, cmd="STOP"))
    page1.add(create_ui_text("Next", 3, 0, cmd="NEXT"))
    page1.add(create_ui_text("Previous", 0, 1, cmd="PREVIOUS"))
    page1.add(create_ui_text("Vol +", 1, 1, cmd="VOLUME_UP"))
    page1.add(create_ui_text("Vol -", 2, 1, cmd="VOLUME_DOWN"))
    page1.add(create_ui_text("Mute", 3, 1, cmd="MUTE_TOGGLE"))
    
    if capabilities['supports_repeat']:
        page1.add(create_ui_text("Repeat", 0, 2, cmd="REPEAT_TOGGLE"))
    if capabilities['supports_shuffle']:
        page1.add(create_ui_text("Shuffle", 1, 2, cmd="SHUFFLE_TOGGLE"))
    
    pages.append(page1)
    
    # Page 2: Inputs (only if device has inputs)
    if capabilities['supports_inputs'] and capabilities['available_inputs']:
        page2 = UiPage(page_id="inputs", name="Inputs", grid=Size(4, 6))
        row, col = 0, 0
        for input_name in capabilities['available_inputs']:
            safe_name = input_name.upper().replace(' ', '_').replace('/', '_')
            display_name = input_name[:15]
            page2.add(create_ui_text(display_name, col, row, cmd=f"INPUT_{safe_name}"))
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        pages.append(page2)
        _LOG.debug(f"Created inputs page with {len(capabilities['available_inputs'])} inputs")
    
    if len(all_players) > 1:
        page3 = UiPage(page_id="grouping", name="Grouping", grid=Size(4, 6))
        
        page3.add(create_ui_text(
            "🔊 Group All",
            0, 0,
            Size(4, 1),
            cmd="GROUP_ALL_SPEAKERS"  # Now has a command!
        ))
        
        row = 1
        for other_player_id, other_player in all_players.items():
            if other_player_id != player.player_id:
                safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
                display_name = other_player.name[:20]
                page3.add(create_ui_text(
                    f"+ {display_name}",
                    0, row,
                    Size(4, 1),
                    cmd=f"GROUP_WITH_{safe_name}"
                ))
                row += 1
                if row >= 6:
                    break
        
        if row < 6:
            page3.add(create_ui_text("Ungroup", 0, row, Size(4, 1), cmd="LEAVE_GROUP"))
        
        pages.append(page3)
        _LOG.debug(f"Created grouping page with ALL speakers button + {len(all_players)-1} individual options")
    
    # Page 4: Music Services (only available ones)
    if capabilities['available_services']:
        page4 = UiPage(page_id="services", name="Services", grid=Size(4, 6))
        row, col = 0, 0
        for service_name in sorted(capabilities['available_services']):
            safe_name = service_name.upper().replace(' ', '_')
            display_name = service_name[:15]
            page4.add(create_ui_text(display_name, col, row, cmd=f"SERVICE_{safe_name}"))
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        pages.append(page4)
        _LOG.debug(f"Created services page with {len(capabilities['available_services'])} services")
    
    # Page 5: Favorites (only if they exist)
    if capabilities['supports_favorites'] and capabilities['favorites_count'] > 0:
        page5 = UiPage(page_id="favorites", name="Favorites", grid=Size(4, 6))
        row, col = 0, 0
        num_favorites = min(capabilities['favorites_count'], 10)
        for i in range(1, num_favorites + 1):
            favorite_name = f"Fav {i}"
            if i in _coordinator.favorites:
                favorite_name = _coordinator.favorites[i].name[:12]
            
            page5.add(create_ui_text(
                favorite_name,
                col, row,
                cmd=f"FAVORITE_{i}"
            ))
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        pages.append(page5)
        _LOG.debug(f"Created favorites page with {num_favorites} favorites")
    
    _LOG.info(f"Built {len(pages)} dynamic UI pages for {player.name}")
    return pages


async def on_connect() -> None:
    """Handle Remote connection with reboot survival - ENHANCED."""
    global _config, _entities_ready
    
    _LOG.info("UC Remote connected. Checking configuration state...")
    
    if not _config:
        _config = HeosConfig(api.config_dir_path)
    
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
        _LOG.info("✓ Configuration valid and entities ready - setting CONNECTED state")
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
    """
    Handle entity subscriptions with race condition protection - ENHANCED LOGGING.
    """
    _LOG.info(f"📋 Entities subscription requested: {entity_ids}")
    
    # Guard against race condition
    if not _entities_ready:
        _LOG.error("⚠️ RACE CONDITION: Subscription before entities ready! Attempting recovery...")
        if _config and _config.is_configured():
            await _initialize_entities()
        else:
            _LOG.error("Cannot recover - no configuration available")
            return
    
    _LOG.info(f"✓ Entities ready flag: {_entities_ready}")
    _LOG.info(f"✓ Media players: {list(_media_players.keys())}")
    _LOG.info(f"✓ Remotes: {list(_remotes.keys())}")
    
    # Process subscriptions
    for entity_id in entity_ids:
        found = False
        
        # Check media players
        for player_id, media_player in _media_players.items():
            if entity_id == media_player.id:
                _LOG.info(f"✓ Subscribing to media player: {entity_id}")
                await media_player.push_update()
                found = True
                break
        
        # Check remotes
        if not found:
            for player_id, remote in _remotes.items():
                if entity_id == remote.id:
                    _LOG.info(f"✓ Subscribing to remote: {entity_id}")
                    await remote.push_update()
                    found = True
                    break
        
        if not found:
            _LOG.warning(f"⚠️ Entity not found: {entity_id}")


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
    """
    Main entry point with pre-initialization for reboot survival - CRITICAL FIX.
    """
    global api, _config, _setup_manager
    
    logging.basicConfig(level=logging.INFO)
    _LOG.info("Starting HEOS integration driver with intelligent detection")
    
    try:
        loop = asyncio.get_running_loop()
        api = IntegrationAPI(loop)
        
        _config = HeosConfig(api.config_dir_path)
        
        # CRITICAL FIX: Pre-initialize entities synchronously if configured
        if _config.is_configured():
            _LOG.info("🔄 Found existing configuration, pre-initializing entities for reboot survival")
            # Use await instead of create_task to ensure completion before CONNECT
            try:
                await _initialize_entities()
                _LOG.info("✓ Pre-initialization complete - entities ready for subscription")
            except Exception as e:
                _LOG.error(f"⚠️ Pre-initialization failed: {e}")
        
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