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
    """Initialize entities - create ALL entities immediately using cached data."""
    global _config, _coordinator, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready:
            _LOG.debug("Entities already initialized, skipping")
            return
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return
            
        _LOG.info("Initializing HEOS entities with cache-based approach...")
        
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
            
            # Create media players immediately
            for player_id, player in players.items():
                _LOG.info(f"Creating media player for: {player.name} (ID: {player_id})")
                
                media_player = HeosMediaPlayer(_coordinator, player, api)
                await media_player.initialize()
                
                _media_players[player_id] = media_player
                api.available_entities.add(media_player)
                api.configured_entities.add(media_player)
                
                _LOG.info(f"Created media player entity: {media_player.id}")
            
            # CRITICAL: Create remotes IMMEDIATELY using cached data
            if len(players) > 1:
                _LOG.info("Multiple devices - creating remotes IMMEDIATELY with cached data")
                await _create_remotes_with_cached_data(players)
            else:
                _LOG.info("Single device - media player only (no remote needed)")
            
            # Mark entities as ready BEFORE any background tasks
            _entities_ready = True
            
            _LOG.info(f"✓ All entities created and ready: {len(_media_players)} media players, {len(_remotes)} remotes")
            
            # Background task: Refresh remote UI with live data (doesn't block subscription)
            if len(_remotes) > 0:
                asyncio.create_task(_refresh_remote_ui_from_live_data())
            
        except Exception as e:
            _LOG.error(f"Failed to initialize HEOS entities: {e}", exc_info=True)
            _entities_ready = False
            if _coordinator:
                await _coordinator.async_shutdown()
                _coordinator = None
            raise


async def _create_remotes_with_cached_data(players: Dict[int, HeosPlayer]):
    """Create remotes IMMEDIATELY using cached data (no network delays)."""
    global _remotes, _coordinator, api
    
    # Get cached data (instant - no network calls)
    cached_favorites_count = _coordinator.get_cached_favorites_count()
    cached_favorite_names = _coordinator.get_cached_favorite_names()
    cached_inputs = _coordinator.get_cached_inputs()
    cached_services = _coordinator.get_cached_services()
    cached_playlists_available = _coordinator.get_cached_playlists_available()
    
    _LOG.info(f"Using cached data: {cached_favorites_count} favorites, "
             f"{len(cached_inputs)} inputs, {len(cached_services)} services")
    
    for player_id, player in players.items():
        _LOG.info(f"Creating remote for: {player.name} (using cached data)")
        
        try:
            # Build capabilities from cache (instant)
            capabilities = {
                'basic_controls': {'play': True, 'pause': True, 'stop': True},
                'volume_controls': {'volume_up': True, 'volume_down': True, 'mute': True},
                'navigation': {'next': True, 'previous': True},
                'inputs': {inp.lower().replace(' ', '_').replace('-', '_'): True for inp in cached_inputs},
                'can_be_grouped': True,
                'supports_favorites': cached_favorites_count > 0,
                'available_services': cached_services,
                'playlists_available': cached_playlists_available,
                'favorites_count': cached_favorites_count
            }
            
            # Build UI pages from cached data (instant)
            ui_pages = _build_ui_pages_from_cache(player, capabilities, players, cached_favorites_count, cached_favorite_names)
            
            # Build commands from cached data (instant)
            simple_commands = _build_commands_from_cache(player, capabilities, players)
            
            # Create remote immediately
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
            api.configured_entities.add(remote)
            
            _LOG.info(f"✓ Created remote for {player.name} with {len(simple_commands)} commands (cached data)")
            
        except Exception as e:
            _LOG.error(f"Failed to create remote for {player.name}: {e}", exc_info=True)


def _build_ui_pages_from_cache(player, capabilities, players, favorites_count, favorite_names):
    """Build UI pages using cached data - no coordinator network access needed."""
    pages = []
    
    # Page 1: Basic Transport Controls (always available)
    page1 = UiPage(page_id="transport", name="Playback", grid=Size(4, 6))
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
    
    # Page 2: Inputs (from cache)
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
                if row >= 6:
                    break
        pages.append(page2)
    
    # Page 3: Grouping
    if len(players) > 1:
        page3 = UiPage(page_id="grouping", name="Grouping", grid=Size(4, 6))
        page3.add(create_ui_text("Group All", 0, 0, Size(4, 1), cmd="GROUP_ALL_SPEAKERS"))
        
        row = 1
        for other_player_id, other_player in players.items():
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
    
    # Page 4: Music Services (from cache)
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
    
    # Page 5: Favorites (using cached names if available, otherwise generic)
    if favorites_count > 0:
        page5 = UiPage(page_id="favorites", name="Favorites", grid=Size(4, 6))
        row, col = 0, 0
        num_favorites = min(favorites_count, 10)
        
        for i in range(1, num_favorites + 1):
            # Use cached name if available, otherwise generic
            favorite_name = favorite_names.get(i, f"Favorite {i}")
            if len(favorite_name) > 12:
                favorite_name = favorite_name[:12]
            
            page5.add(create_ui_text(favorite_name, col, row, cmd=f"FAVORITE_{i}"))
            col += 1
            if col >= 4:
                col = 0
                row += 1
                if row >= 6:
                    break
        
        pages.append(page5)
    
    return pages


def _build_commands_from_cache(player, capabilities, players):
    """Build simple commands based on cached capabilities."""
    commands = []
    
    # Basic playback
    commands.extend(["PLAY", "PAUSE", "STOP", "PLAY_PAUSE"])
    
    # Volume
    commands.extend(["VOLUME_UP", "VOLUME_DOWN", "MUTE_TOGGLE"])
    
    # Navigation
    commands.extend(["NEXT", "PREVIOUS"])
    
    # Repeat and shuffle
    commands.extend(["REPEAT_OFF", "REPEAT_ALL", "REPEAT_ONE", "SHUFFLE_ON", "SHUFFLE_OFF"])
    
    # Inputs
    for input_name in capabilities['inputs'].keys():
        command_name = input_name.upper().replace(' ', '_')
        commands.append(f"INPUT_{command_name}")
    
    # Grouping
    if len(players) > 1:
        commands.append("LEAVE_GROUP")
        commands.append("GROUP_ALL_SPEAKERS")
        
        for other_player_id, other_player in players.items():
            if other_player_id != player.player_id:
                safe_name = other_player.name.upper().replace(' ', '_').replace('-', '_')
                commands.append(f"GROUP_WITH_{safe_name}")
    
    # Favorites
    if capabilities['supports_favorites'] and capabilities['favorites_count'] > 0:
        num_favorites = min(capabilities['favorites_count'], 10)
        for i in range(1, num_favorites + 1):
            commands.append(f"FAVORITE_{i}")
    
    # Music services
    for service_name in capabilities['available_services']:
        safe_name = service_name.upper().replace(' ', '_')
        commands.append(f"SERVICE_{safe_name}")
    
    # Playlists
    if capabilities['playlists_available']:
        commands.append("PLAYLISTS")
    
    # Queue management
    commands.extend(["CLEAR_QUEUE", "QUEUE_INFO"])
    
    return commands


async def _refresh_remote_ui_from_live_data():
    """Background task: Update remote UI with actual favorite names (doesn't block boot)."""
    global _remotes, _coordinator
    
    try:
        # Let coordinator data fully load
        await asyncio.sleep(3)
        
        _LOG.info("Refreshing remote UI with live coordinator data...")
        
        # Check if we have live favorite data
        if not _coordinator or not _coordinator.favorites:
            _LOG.info("No live favorite data available yet, skipping refresh")
            return
        
        # Update favorite names in remote UI
        for remote in _remotes.values():
            updated = False
            for page in remote.ui_pages:
                if page.page_id == "favorites":
                    for item in page.items:
                        if hasattr(item, 'cmd') and item.cmd and item.cmd.startswith("FAVORITE_"):
                            try:
                                fav_num = int(item.cmd.split("_")[1])
                                if fav_num in _coordinator.favorites:
                                    actual_name = _coordinator.favorites[fav_num].name
                                    if len(actual_name) > 12:
                                        actual_name = actual_name[:12]
                                    
                                    # Update the UI item text
                                    if hasattr(item, 'text'):
                                        old_name = item.text
                                        item.text = actual_name
                                        if old_name != actual_name:
                                            _LOG.debug(f"Updated favorite {fav_num}: '{old_name}' -> '{actual_name}'")
                                            updated = True
                            except (ValueError, IndexError) as e:
                                _LOG.warning(f"Error parsing favorite command: {e}")
            
            # Push update to Remote if anything changed
            if updated:
                await remote.push_update()
        
        _LOG.info("✓ Remote UI refreshed with live favorite names")
        
    except Exception as e:
        _LOG.error(f"Error refreshing remote UI: {e}", exc_info=True)


async def on_connect() -> None:
    """Handle Remote connection with reboot survival."""
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
    global _setup_manager
    
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
    _LOG.info("Starting HEOS integration driver with cache-based approach")
    
    try:
        loop = asyncio.get_running_loop()
        api = IntegrationAPI(loop)
        
        _config = HeosConfig(api.config_dir_path)
        
        # Pre-initialize if already configured (reboot survival)
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