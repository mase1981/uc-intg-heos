"""
HEOS Integration Driver - Direct Connection Pattern.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional

import ucapi
from ucapi import DeviceStates, Events, IntegrationAPI, StatusCodes
from ucapi.api_definitions import SetupAction, SetupComplete, SetupError

from pyheos import Heos, HeosOptions, Credentials, HeosError

from uc_intg_heos.config import HeosConfig
from uc_intg_heos.setup import HeosSetupManager
from uc_intg_heos.media_player import HeosMediaPlayer
from uc_intg_heos.remote import HeosRemote

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOG = logging.getLogger(__name__)

api: Optional[IntegrationAPI] = None
config: Optional[HeosConfig] = None
heos: Optional[Heos] = None
media_players: Dict[int, HeosMediaPlayer] = {}
remotes: Dict[int, HeosRemote] = {}

entities_ready = False
initialization_lock = asyncio.Lock()

setup_manager: Optional[HeosSetupManager] = None
reconnect_task: Optional[asyncio.Task] = None

# Connection retry settings
MAX_STARTUP_RETRIES = 15  # Try for ~60 seconds during startup
STARTUP_RETRY_DELAY = 4   # Start with 4 second delay
RECONNECT_CHECK_INTERVAL = 30  # Check connection every 30 seconds
RECONNECT_RETRY_DELAY = 10     # Wait 10 seconds between reconnection attempts


async def _initialize_integration(is_reconnection: bool = False):
    """
    Initialize integration entities - direct pattern like Naim/MusicCast.

    Args:
        is_reconnection: If True, reuse existing entities (avoid re-registration)
    """
    global config, api, heos, media_players, remotes, entities_ready

    async with initialization_lock:
        if entities_ready and not is_reconnection:
            _LOG.debug("Entities already initialized")
            return True

        if not config or not config.is_configured():
            _LOG.info("No configuration found")
            return False

        _LOG.info("Initializing HEOS integration (direct pattern)..." if not is_reconnection else "Reconnecting to HEOS...")
        await api.set_device_state(DeviceStates.CONNECTING)

        # Retry logic with exponential backoff
        retry_count = 0
        retry_delay = STARTUP_RETRY_DELAY
        max_retries = MAX_STARTUP_RETRIES if not is_reconnection else 3

        while retry_count < max_retries:
            try:
                # Clear entities only on initial connection
                if not is_reconnection:
                    api.available_entities.clear()
                    media_players.clear()
                    remotes.clear()

                # Disconnect old connection if reconnecting
                if is_reconnection and heos:
                    try:
                        await heos.disconnect()
                    except:
                        pass
                    heos = None

                # Get configuration
                account_config = config.get_heos_account()
                if not account_config:
                    raise HeosError("No HEOS account configuration found")

                # Create Heos connection directly (FAST - no coordinator bottleneck)
                credentials = Credentials(account_config.username, account_config.password)
                heos_options = HeosOptions(
                    host=account_config.host,
                    all_progress_events=False,
                    auto_reconnect=True,
                    auto_failover=True,
                    credentials=credentials
                )

                heos = Heos(heos_options)

                # Connect (this is fast - ~500ms)
                _LOG.info(f"Connecting to HEOS at {account_config.host}...")
                await heos.connect()

                # Get players immediately
                await heos.get_players()

                players = heos.players
                if not players:
                    _LOG.warning("No HEOS devices found")
                    await api.set_device_state(DeviceStates.ERROR)
                    return False

                _LOG.info(f"Connected - found {len(players)} HEOS device(s)")

                # Create entities only on initial connection
                if not is_reconnection:
                    # Create entities immediately (also fast)
                    for player_id, player in players.items():
                        media_player = HeosMediaPlayer(heos, player, api)
                        await media_player.initialize()

                        media_players[player_id] = media_player
                        api.available_entities.add(media_player)

                        _LOG.debug(f"Created media player: {media_player.id}")

                    # Create remotes if multiple devices
                    if len(players) > 1:
                        for player_id, player in players.items():
                            remote = HeosRemote(
                                heos=heos,
                                heos_player=player,
                                device_name=player.name,
                                api=api,
                                all_players=players
                            )

                            await remote.initialize()

                            remotes[player_id] = remote
                            api.available_entities.add(remote)

                            _LOG.debug(f"Created remote: {remote.id}")
                else:
                    # Reconnection: update existing entities with new heos instance
                    _LOG.info("Reconnection: updating entities with new connection")
                    for player_id, player in players.items():
                        if player_id in media_players:
                            media_players[player_id]._heos = heos
                            media_players[player_id]._player = player
                            await media_players[player_id].update_attributes()

                        if player_id in remotes:
                            remotes[player_id]._heos = heos
                            remotes[player_id]._heos_player = player
                            remotes[player_id]._all_players = players
                            await remotes[player_id].update_attributes()

                entities_ready = True
                await api.set_device_state(DeviceStates.CONNECTED)
                _LOG.info(f"Integration {'reconnected' if is_reconnection else 'initialized'}: {len(media_players)} players, {len(remotes)} remotes")
                return True

            except (HeosError, ConnectionError, asyncio.TimeoutError, OSError) as e:
                retry_count += 1
                if retry_count >= max_retries:
                    _LOG.error(f"Connection failed after {retry_count} attempts: {e}")
                    entities_ready = False
                    await api.set_device_state(DeviceStates.ERROR)
                    if heos:
                        try:
                            await heos.disconnect()
                        except:
                            pass
                        heos = None
                    return False

                _LOG.warning(f"Connection attempt {retry_count}/{max_retries} failed: {e}. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)

                # Exponential backoff, max 30 seconds
                retry_delay = min(retry_delay * 1.5, 30)

            except Exception as e:
                _LOG.error(f"Unexpected error during {'reconnection' if is_reconnection else 'initialization'}: {e}", exc_info=True)
                entities_ready = False
                await api.set_device_state(DeviceStates.ERROR)
                if heos:
                    try:
                        await heos.disconnect()
                    except:
                        pass
                    heos = None
                return False

        return False


async def connection_monitor():
    """
    Background task to monitor connection health and attempt reconnection if needed.
    Runs continuously to survive remote reboots or network issues.
    """
    global heos, api

    _LOG.info("Connection monitor started")

    while True:
        try:
            await asyncio.sleep(RECONNECT_CHECK_INTERVAL)

            # Check if we're in ERROR state or heos connection is dead
            if api.device_state == DeviceStates.ERROR or not heos or not heos.connected:
                _LOG.warning("Connection lost. Attempting reconnection...")
                success = await _initialize_integration(is_reconnection=True)

                if not success:
                    _LOG.error(f"Reconnection failed. Will retry in {RECONNECT_RETRY_DELAY} seconds")
                    await asyncio.sleep(RECONNECT_RETRY_DELAY)
                else:
                    _LOG.info("Reconnection successful!")

            # Verify connection is actually working
            elif api.device_state == DeviceStates.CONNECTED and heos and heos.connected:
                try:
                    # Quick connection test - check if we can get players
                    if not heos.players:
                        _LOG.warning("Connection test failed - no players available. Marking as disconnected.")
                        await api.set_device_state(DeviceStates.ERROR)
                except Exception as e:
                    _LOG.warning(f"Connection test failed: {e}. Marking as disconnected.")
                    await api.set_device_state(DeviceStates.ERROR)

        except asyncio.CancelledError:
            _LOG.info("Connection monitor task cancelled")
            break
        except Exception as e:
            _LOG.error(f"Error in connection monitor: {e}", exc_info=True)
            await asyncio.sleep(RECONNECT_RETRY_DELAY)


async def setup_handler(msg: ucapi.SetupDriver) -> ucapi.SetupAction:
    """Handle setup flow."""
    global setup_manager
    
    if not setup_manager:
        return SetupError()
    
    action = await setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("Setup complete - initializing entities")
        await _initialize_integration()
    
    return action


async def on_subscribe_entities(entity_ids: List[str]):
    """Handle entity subscription with race condition protection."""
    global media_players, remotes, entities_ready, config
    
    _LOG.info(f"Subscription requested for {len(entity_ids)} entities")
    
    if not entities_ready:
        _LOG.warning("Subscription before entities ready - attempting recovery")
        
        if config and config.is_configured():
            await _initialize_integration()
            
            if not entities_ready:
                _LOG.error("Recovery failed - entities still not ready")
                return
        else:
            _LOG.error("Cannot recover - no configuration available")
            return
    
    subscribed_count = 0
    for entity_id in entity_ids:
        for player_id, media_player in media_players.items():
            if media_player.id == entity_id:
                api.configured_entities.add(media_player)
                await media_player.update_attributes()
                subscribed_count += 1
                break
        
        for player_id, remote in remotes.items():
            if remote.id == entity_id:
                api.configured_entities.add(remote)
                await remote.update_attributes()
                subscribed_count += 1
                break
    
    _LOG.info(f"Subscribed to {subscribed_count}/{len(entity_ids)} entities")


async def on_unsubscribe_entities(entity_ids: List[str]):
    """Handle entity unsubscription."""
    _LOG.info(f"Unsubscribed from {len(entity_ids)} entities")


async def on_connect():
    """Handle Remote connection with reboot survival."""
    global entities_ready, config
    
    _LOG.info("Remote connected")
    
    if config:
        config.load()
    
    if config and config.is_configured():
        if not entities_ready:
            _LOG.info("Initializing entities")
            await _initialize_integration()
        else:
            await api.set_device_state(DeviceStates.CONNECTED)
    else:
        await api.set_device_state(DeviceStates.DISCONNECTED)


async def on_disconnect():
    """Handle Remote disconnection."""
    _LOG.info("Remote disconnected")


async def main():
    """Main entry point."""
    global api, config, setup_manager, reconnect_task

    _LOG.info("Starting HEOS Integration v1.1.3")

    try:
        loop = asyncio.get_running_loop()
        api = IntegrationAPI(loop)

        driver_path = os.path.join(os.path.dirname(__file__), "..", "driver.json")

        # Register listeners before init
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        api.add_listener(Events.UNSUBSCRIBE_ENTITIES, on_unsubscribe_entities)
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)

        # Create temporary config
        config = HeosConfig()
        setup_manager = HeosSetupManager(config)

        # Initialize API
        await api.init(os.path.abspath(driver_path), setup_handler)

        # Update config path
        from pathlib import Path
        config._config_dir = Path(api.config_dir_path)
        config._config_file = config._config_dir / "heos_config.json"

        try:
            config._config_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        config.load()

        # Start connection monitor task
        reconnect_task = asyncio.create_task(connection_monitor())

        # Pre-initialize if configured
        if config.is_configured():
            _LOG.info("Pre-initializing entities with retry logic")
            asyncio.create_task(_initialize_integration(is_reconnection=False))
        else:
            await api.set_device_state(DeviceStates.DISCONNECTED)

        await asyncio.Future()

    except Exception as e:
        _LOG.error(f"Fatal error: {e}", exc_info=True)
    finally:
        # Cleanup tasks
        if reconnect_task and not reconnect_task.done():
            reconnect_task.cancel()
            try:
                await reconnect_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    asyncio.run(main())