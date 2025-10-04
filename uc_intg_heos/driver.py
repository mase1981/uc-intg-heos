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


async def _initialize_entities_fast():
    """FAST initialization - creates entities BEFORE loading account data."""
    global _config, _coordinator, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready:
            _LOG.debug("Entities already initialized, skipping")
            return
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return
            
        _LOG.info("FAST initialization: Creating entities immediately...")
        
        try:
            # Clear existing entities
            api.available_entities.clear()
            _media_players.clear()
            _remotes.clear()
            
            # Create coordinator (but don't load account data yet)
            _coordinator = HeosCoordinator(api, _config)
            
            #  Connect and get players ONLY (no account data loading)
            account_config = _config.get_heos_account()
            from pyheos import Credentials, Heos, HeosOptions
            
            credentials = Credentials(account_config.username, account_config.password)
            heos_options = HeosOptions(
                host=account_config.host,
                all_progress_events=False,
                auto_reconnect=True,
                auto_failover=True,
                credentials=credentials
            )
            
            _coordinator.heos = Heos(heos_options)
            _coordinator.heos.add_on_user_credentials_invalid(_coordinator._async_on_auth_failure)
            _coordinator.heos.add_on_disconnected(_coordinator._async_on_disconnected)
            _coordinator.heos.add_on_connected(_coordinator._async_on_reconnected)
            _coordinator.heos.add_on_controller_event(_coordinator._async_on_controller_event)
            
            _LOG.info("Connecting to HEOS (fast path - players only)")
            await _coordinator.heos.connect()
            _coordinator._is_connected = True
            
            # Get players ONLY (no favorites, sources, etc.)
            await _coordinator.heos.get_players()
            players = _coordinator.heos.players
            
            if not players:
                _LOG.warning("No HEOS devices found")
                return

            _LOG.info(f"Found {len(players)} players - creating entities NOW")
            
            # Create media players IMMEDIATELY (they'll update when data loads)
            for player_id, player in players.items():
                media_player = HeosMediaPlayer(_coordinator, player, api)
                # Don't call initialize() yet - just create the entity
                
                _media_players[player_id] = media_player
                api.available_entities.add(media_player)
                api.configured_entities.add(media_player)
                
                _LOG.info(f"Created media player: {media_player.id}")
            
            # Create remotes IMMEDIATELY
            if len(players) > 1:
                for player_id, player in players.items():
                    remote = HeosRemote(
                        heos_player=player,
                        device_name=player.name,
                        api=api,
                        all_players=players
                    )
                    remote.set_heos(_coordinator.heos)
                    
                    _remotes[player_id] = remote
                    api.available_entities.add(remote)
                    api.configured_entities.add(remote)
                    
                    _LOG.info(f"Created remote: {remote.id}")
            
            # Mark entities as ready IMMEDIATELY
            _entities_ready = True
            
            _LOG.info(f"✓ Entities ready FAST: {len(_media_players)} players, {len(_remotes)} remotes")
            
            # NOW start background task to load account data
            asyncio.create_task(_load_account_data_background())
            
        except Exception as e:
            _LOG.error(f"FAST initialization failed: {e}", exc_info=True)
            _entities_ready = False
            if _coordinator and _coordinator.heos:
                try:
                    await _coordinator.heos.disconnect()
                except:
                    pass
                _coordinator = None
            raise


async def _load_account_data_background():
    """Background task to load account data AFTER entities are created."""
    global _coordinator, _media_players
    
    try:
        _LOG.info("Loading account data in background...")
        
        # Load all account data (favorites, sources, playlists, inputs)
        await _coordinator._load_account_data_synchronously()
        _coordinator._account_data_loaded = True
        
        # Initialize all media players (now that data is available)
        for player_id, media_player in _media_players.items():
            await media_player.initialize()
            await media_player.push_update()
        
        # Initialize all remotes
        for player_id, remote in _remotes.items():
            await remote.initialize()
            await remote.push_update()
        
        _LOG.info("✓ Account data loaded and entities updated")
        
    except Exception as e:
        _LOG.error(f"Background data loading failed: {e}", exc_info=True)


async def on_connect() -> None:
    """Handle Remote connection with reboot survival."""
    global _config, _entities_ready
    
    _LOG.info("UC Remote connected. Checking configuration state...")
    
    if not _config:
        _config = HeosConfig(api.config_dir_path)
    
    # Reload config from disk
    _config.reload_from_disk()
    
    # If configured but entities not ready, initialize them now (FAST)
    if _config.is_configured() and not _entities_ready:
        _LOG.info("Configuration found but entities missing, fast initialization...")
        try:
            await _initialize_entities_fast()
        except Exception as e:
            _LOG.error(f"Failed to initialize entities: {e}")
            await api.set_device_state(DeviceStates.ERROR)
            return
    
    # Set appropriate device state
    if _config.is_configured() and _entities_ready:
        _LOG.info("Entities ready - setting CONNECTED")
        await api.set_device_state(DeviceStates.CONNECTED)
    elif not _config.is_configured():
        await api.set_device_state(DeviceStates.DISCONNECTED)
    else:
        await api.set_device_state(DeviceStates.ERROR)


async def on_disconnect() -> None:
    """Handle Remote disconnection."""
    _LOG.info("UC Remote disconnected")
    await api.set_device_state(DeviceStates.DISCONNECTED)


async def on_subscribe_entities(entity_ids: List[str]):
    """Handle entity subscriptions with race condition protection."""
    _LOG.info(f"Subscription request for {len(entity_ids)} entities")
    
    # Guard against race condition
    if not _entities_ready:
        _LOG.error("RACE CONDITION: Subscription before entities ready! Fast recovery...")
        if _config and _config.is_configured():
            await _initialize_entities_fast()
        else:
            _LOG.error("Cannot recover - no configuration")
            return
    
    # Push updates for subscribed entities
    for entity_id in entity_ids:
        for player_id, media_player in _media_players.items():
            if entity_id == media_player.id:
                await media_player.push_update()
                break
        
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
        _LOG.info("Setup complete - initializing entities (fast)...")
        await _initialize_entities_fast()
    
    return action


async def main():
    """Main entry point with pre-initialization for reboot survival."""
    global api, _config, _setup_manager
    
    logging.basicConfig(level=logging.INFO)
    _LOG.info("Starting HEOS integration with FAST entity creation")
    
    try:
        loop = asyncio.get_running_loop()
        api = IntegrationAPI(loop)
        
        _config = HeosConfig(api.config_dir_path)
        
        #  Pre-initialize if configured (FAST mode)
        if _config.is_configured():
            _LOG.info("Configuration exists - pre-initializing entities (FAST)")
            loop.create_task(_initialize_entities_fast())
        
        # Register event handlers
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        api.add_listener(Events.UNSUBSCRIBE_ENTITIES, on_unsubscribe_entities)
        
        _setup_manager = HeosSetupManager(_config)
        
        await api.init("driver.json", setup_handler)
        await api.set_device_state(DeviceStates.DISCONNECTED)
        
        await asyncio.Future()
        
    except asyncio.CancelledError:
        _LOG.info("Driver cancelled")
    except Exception as e:
        _LOG.error(f"Driver failed: {e}", exc_info=True)
    finally:
        await shutdown()


async def shutdown():
    """Shutdown cleanly."""
    global _coordinator, _media_players, _remotes
    
    _LOG.info("Shutting down HEOS integration")
    
    for player in _media_players.values():
        if hasattr(player, 'shutdown'):
            try:
                await player.shutdown()
            except Exception as e:
                _LOG.error(f"Error shutting down player: {e}")
    
    for remote in _remotes.values():
        if hasattr(remote, 'shutdown'):
            try:
                await remote.shutdown()
            except Exception as e:
                _LOG.error(f"Error shutting down remote: {e}")
    
    if _coordinator:
        try:
            await _coordinator.async_shutdown()
        except Exception as e:
            _LOG.error(f"Error shutting down coordinator: {e}")


if __name__ == "__main__":
    asyncio.run(main())