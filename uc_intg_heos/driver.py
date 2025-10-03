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


async def _initialize_entities():
    global _config, _coordinator, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready:
            _LOG.debug("Entities already initialized, skipping")
            return
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return
            
        _LOG.info("Initializing HEOS entities...")
        
        try:
            api.available_entities.clear()
            _media_players.clear()
            _remotes.clear()
            
            _coordinator = HeosCoordinator(api, _config)
            await _coordinator.async_setup()
            
            players = _coordinator.heos.players
            if not players:
                _LOG.warning("No HEOS devices found on account")
                return

            _LOG.info(f"Found {len(players)} HEOS device(s)")
            
            for player_id, player in players.items():
                _LOG.info(f"Creating media player for: {player.name} (ID: {player_id})")
                
                media_player = HeosMediaPlayer(_coordinator, player, api)
                await media_player.initialize()
                
                _media_players[player_id] = media_player
                api.available_entities.add(media_player)
                api.configured_entities.add(media_player)
                
                _LOG.info(f"Created media player entity: {media_player.id}")
            
            if len(players) > 1:
                _LOG.info("Multiple devices - creating remotes")
                await _create_remotes(players)
            else:
                _LOG.info("Single device - media player only")
            
            _entities_ready = True
            
            _LOG.info(f"All entities ready: {len(_media_players)} media players, {len(_remotes)} remotes")
            
        except Exception as e:
            _LOG.error(f"Failed to initialize HEOS entities: {e}", exc_info=True)
            _entities_ready = False
            if _coordinator:
                await _coordinator.async_shutdown()
                _coordinator = None
            raise


async def _create_remotes(players: Dict[int, HeosPlayer]):
    global _remotes, _coordinator, api
    
    for player_id, player in players.items():
        _LOG.info(f"Creating remote for: {player.name}")
        
        try:
            remote = HeosRemote(
                heos_player=player,
                device_name=player.name
            )
            
            remote._api = api
            remote.set_coordinator(_coordinator, _coordinator.heos, players)
            
            await remote.initialize()
            await remote.initialize_capabilities()
            
            _remotes[player_id] = remote
            api.available_entities.add(remote)
            api.configured_entities.add(remote)
            
            _LOG.info(f"Created remote for {player.name} with full capabilities")
            
        except Exception as e:
            _LOG.error(f"Failed to create remote for {player.name}: {e}", exc_info=True)


async def on_connect() -> None:
    global _config, _entities_ready
    
    _LOG.info("UC Remote connected")
    
    if not _config:
        _config = HeosConfig(api.config_dir_path)
    
    if _entities_ready:
        await api.set_device_state(DeviceStates.CONNECTED)
    else:
        _LOG.warning("Entities not ready on connect")
        await api.set_device_state(DeviceStates.ERROR)


async def on_disconnect() -> None:
    _LOG.info("UC Remote disconnected")
    await api.set_device_state(DeviceStates.DISCONNECTED)


async def on_subscribe_entities(entity_ids: List[str]):
    _LOG.info(f"Entities subscription requested: {entity_ids}")
    
    if not _entities_ready:
        _LOG.error("Subscription before entities ready!")
        return
    
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
    _LOG.info(f"Unsubscribed from entities: {entity_ids}")


async def setup_handler(msg: SetupAction) -> SetupAction:
    global _setup_manager
    
    if not _setup_manager:
        return SetupError()
    
    action = await _setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("Setup confirmed. Initializing integration components...")
        await _initialize_entities()
    
    return action


async def main():
    global api, _config, _setup_manager
    
    logging.basicConfig(level=logging.INFO)
    _LOG.info("Starting HEOS integration driver")
    
    try:
        loop = asyncio.get_running_loop()
        api = IntegrationAPI(loop)
        
        _config = HeosConfig(api.config_dir_path)
        
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        api.add_listener(Events.UNSUBSCRIBE_ENTITIES, on_unsubscribe_entities)
        
        _setup_manager = HeosSetupManager(_config)
        
        await api.init("driver.json", setup_handler)
        
        if _config.is_configured():
            _LOG.info("Configuration exists, initializing entities synchronously")
            await _initialize_entities()
            await api.set_device_state(DeviceStates.CONNECTED)
        else:
            await api.set_device_state(DeviceStates.DISCONNECTED)
        
        await asyncio.Future()
        
    except asyncio.CancelledError:
        _LOG.info("Driver task cancelled")
    except Exception as e:
        _LOG.error(f"Driver initialization failed: {e}", exc_info=True)
    finally:
        await shutdown()


async def shutdown():
    global _coordinator, _media_players, _remotes
    
    _LOG.info("Shutting down HEOS integration")
    
    for player in _media_players.values():
        if hasattr(player, 'shutdown'):
            try:
                await player.shutdown()
            except Exception as e:
                _LOG.error(f"Error shutting down media player: {e}")
    
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