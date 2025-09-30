"""
HEOS Integration Coordinator 
:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from pyheos import (
    Credentials,
    Heos,
    HeosError,
    HeosOptions,
    HeosPlayer,
    MediaItem,
    PlayerUpdateResult,
    const,
)

from uc_intg_heos.config import HeosConfig

_LOG = logging.getLogger(__name__)


class HeosCoordinator:
    """HEOS Integration Coordinator - manages connection and state."""

    def __init__(self, api, config: HeosConfig):
        """Initialize the coordinator."""
        self._api = api
        self._config = config
        self.heos: Optional[Heos] = None
        
        # State tracking
        self._source_list: List[str] = []
        self._favorites: Dict[int, MediaItem] = {}
        self._inputs: List[MediaItem] = []
        self._music_sources: Dict[int, Any] = {}
        self._playlists: List[MediaItem] = []
        self._is_connected = False
        
        # Source intelligence tracking
        self._last_played_content: Dict[str, Dict[str, Any]] = {}
        self._source_usage_count: Dict[str, int] = {}
        self._preferred_containers: Dict[str, str] = {}
        
        # Callbacks for entity updates
        self._entity_callbacks: List[Callable] = []
        
        # Update debouncing
        self._update_sources_task: Optional[asyncio.Task] = None

    @property
    def host(self) -> str:
        """Get the current host address."""
        return self.heos.current_host if self.heos else self._config.get_host()

    @property
    def inputs(self) -> List[MediaItem]:
        """Get input sources across all devices."""
        return self._inputs

    @property
    def favorites(self) -> Dict[int, MediaItem]:
        """Get favorite stations."""
        return self._favorites

    @property
    def music_sources(self) -> Dict[int, Any]:
        """Get available music sources."""
        return self._music_sources

    @property
    def playlists(self) -> List[MediaItem]:
        """Get available playlists."""
        return self._playlists

    @property
    def is_connected(self) -> bool:
        """Check if connected to HEOS system."""
        return self._is_connected and self.heos is not None

    async def async_setup(self) -> None:
        """Set up the coordinator and connect to HEOS."""
        account_config = self._config.get_heos_account()
        if not account_config:
            raise HeosError("No HEOS account configuration found")

        # Create credentials
        credentials = Credentials(account_config.username, account_config.password)
        
        heos_options = HeosOptions(
            host=account_config.host,
            all_progress_events=False,
            auto_reconnect=True,
            auto_failover=True,
            credentials=credentials
        )
        
        # Create HEOS instance
        self.heos = Heos(heos_options)
        
        # Add event callbacks before connecting
        self.heos.add_on_user_credentials_invalid(self._async_on_auth_failure)
        self.heos.add_on_disconnected(self._async_on_disconnected)
        self.heos.add_on_connected(self._async_on_reconnected)
        self.heos.add_on_controller_event(self._async_on_controller_event)
        
        try:
            # Connect to HEOS system
            _LOG.info(f"Connecting to HEOS system at {account_config.host}")
            await self.heos.connect()
            self._is_connected = True
            
            # Load players
            _LOG.info("Loading HEOS players")
            await self.heos.get_players()
            
            # Check authentication status
            if not self.heos.is_signed_in:
                _LOG.warning("HEOS System is not logged in - some features may be unavailable")
            else:
                _LOG.info(f"Successfully authenticated as: {self.heos.signed_in_username}")
            
            # Load initial data with error handling
            await self._async_update_groups()
            await self._async_update_sources()
            
            _LOG.info(f"HEOS coordinator setup complete - {len(self.heos.players)} players found")
            
        except HeosError as error:
            _LOG.error(f"Failed to connect to HEOS system: {error}")
            self._is_connected = False
            raise

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and disconnect from HEOS."""
        _LOG.info("Shutting down HEOS coordinator")
        
        # Cancel any pending tasks
        if self._update_sources_task and not self._update_sources_task.done():
            self._update_sources_task.cancel()
            try:
                await self._update_sources_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from HEOS
        if self.heos:
            try:
                self.heos.dispatcher.disconnect_all()
                await self.heos.disconnect()
            except Exception as e:
                _LOG.error(f"Error disconnecting from HEOS: {e}")
        
        self._is_connected = False
        self.heos = None

    def add_entity_callback(self, callback: Callable) -> None:
        """Add callback for entity updates."""
        self._entity_callbacks.append(callback)

    def remove_entity_callback(self, callback: Callable) -> None:
        """Remove entity callback."""
        if callback in self._entity_callbacks:
            self._entity_callbacks.remove(callback)

    def notify_entities(self) -> None:
        """Notify all entities of state changes."""
        for callback in self._entity_callbacks:
            try:
                callback()
            except Exception as e:
                _LOG.error(f"Error in entity callback: {e}")

    def remember_content(self, source_name: str, content_info: Dict[str, Any]) -> None:
        """Remember last played content for a source."""
        self._last_played_content[source_name] = {
            'content': content_info,
            'timestamp': datetime.now().isoformat(),
            'success': True
        }
        
        # Track usage
        self._source_usage_count[source_name] = self._source_usage_count.get(source_name, 0) + 1
        
        _LOG.info(f"Remembered content for {source_name}: {content_info.get('name', 'unknown')}")
    
    def get_last_played_content(self, source_name: str) -> Optional[Dict[str, Any]]:
        """Get last successfully played content for a source."""
        return self._last_played_content.get(source_name)
    
    def remember_container(self, source_name: str, container_id: str) -> None:
        """Remember preferred container for a source."""
        self._preferred_containers[source_name] = container_id
        _LOG.debug(f"Remembered container for {source_name}: {container_id}")
    
    def get_preferred_container(self, source_name: str) -> Optional[str]:
        """Get preferred container for a source."""
        return self._preferred_containers.get(source_name)
    
    def get_most_used_sources(self, limit: int = 5) -> List[str]:
        """Get most frequently used sources."""
        sorted_sources = sorted(
            self._source_usage_count.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [source for source, _ in sorted_sources[:limit]]

    async def _async_on_auth_failure(self) -> None:
        """Handle authentication failure."""
        _LOG.error("HEOS authentication failed - credentials are invalid")

    async def _async_on_disconnected(self) -> None:
        """Handle disconnection from HEOS."""
        _LOG.warning(f"Connection to HEOS host {self.host} lost")
        self._is_connected = False
        self.notify_entities()

    async def _async_on_reconnected(self) -> None:
        """Handle reconnection to HEOS."""
        _LOG.info(f"Reconnected to HEOS host {self.host}")
        self._is_connected = True
        
        # Update host if it changed (failover)
        if self.host != self._config.get_host():
            _LOG.info(f"HEOS host changed to {self.host}")
            self._config.update_host(self.host)
        
        # Refresh sources and notify entities - with error handling
        try:
            await self._async_update_sources()
        except Exception as e:
            _LOG.error(f"Error updating sources after reconnection: {e}")
        
        self.notify_entities()

    async def _async_on_controller_event(self, event: str, data: PlayerUpdateResult = None) -> None:
        """Handle controller events like players/groups/sources changed."""
        _LOG.debug(f"HEOS controller event: {event}")
        
        if event == const.EVENT_PLAYERS_CHANGED:
            if data:
                self._handle_player_update_result(data)
        elif event in (const.EVENT_SOURCES_CHANGED, const.EVENT_USER_CHANGED):
            await self._debounced_update_sources()
        
        self.notify_entities()

    def _handle_player_update_result(self, update_result: PlayerUpdateResult) -> None:
        """Handle player updates (new players added, etc.)."""
        if update_result.added_player_ids:
            _LOG.info(f"New HEOS players detected: {update_result.added_player_ids}")

        if update_result.updated_player_ids:
            _LOG.debug(f"HEOS player IDs updated: {update_result.updated_player_ids}")

    async def _debounced_update_sources(self) -> None:
        """Debounced source update to avoid rapid successive calls."""
        if self._update_sources_task and not self._update_sources_task.done():
            self._update_sources_task.cancel()
        
        self._update_sources_task = asyncio.create_task(self._delayed_update_sources())

    async def _delayed_update_sources(self) -> None:
        """Delayed source update."""
        try:
            await asyncio.sleep(2.0)
            await self._async_update_sources()
        except asyncio.CancelledError:
            pass

    async def _async_update_groups(self) -> None:
        """Update group information with error handling."""
        if not self.heos:
            return
            
        try:
            await self.heos.get_groups(refresh=True)
            _LOG.debug("Updated HEOS groups")
        except HeosError as error:
            _LOG.error(f"Unable to retrieve HEOS groups: {error}")
        except Exception as e:
            _LOG.error(f"Unexpected error retrieving HEOS groups: {e}")

    async def _async_update_sources(self) -> None:
        """Build comprehensive source list with defensive error handling."""
        if not self.heos:
            return
            
        self._source_list.clear()
        
        # Get HEOS music sources - with error handling
        try:
            music_sources = await self.heos.get_music_sources()
            self._music_sources = music_sources
            _LOG.info(f"Found {len(music_sources)} total music sources")
            
            available_services = []
            for source_id, source in music_sources.items():
                if source.available:
                    available_services.append(source.name)
                    self._source_list.append(source.name)
                    _LOG.info(f"  - Available music service: {source.name} (ID: {source_id})")
                else:
                    _LOG.debug(f"  - Unavailable music service: {source.name} (ID: {source_id})")
            
            _LOG.info(f"Available music services: {available_services}")
            
        except HeosError as error:
            _LOG.error(f"Unable to retrieve HEOS music sources: {error}")
        except Exception as e:
            _LOG.error(f"Unexpected error retrieving music sources: {e}")
        
        # Get favorites - with error handling
        if self.heos.is_signed_in:
            try:
                self._favorites = await self.heos.get_favorites()
                for favorite in self._favorites.values():
                    self._source_list.append(favorite.name)
                _LOG.info(f"Loaded {len(self._favorites)} HEOS favorites: {[f.name for f in self._favorites.values()]}")
            except HeosError as error:
                _LOG.error(f"Unable to retrieve HEOS favorites: {error}")
                self._favorites = {}  # Clear favorites on error
            except KeyError as e:
                _LOG.error(f"Favorites data missing required field: {e}")
                self._favorites = {}
            except Exception as e:
                _LOG.error(f"Unexpected error retrieving favorites: {e}")
                self._favorites = {}
        else:
            _LOG.warning("Not signed in - favorites unavailable")
        
        # Get input sources - with error handling
        try:
            self._inputs = await self.heos.get_input_sources()
            input_names = [source.name for source in self._inputs]
            self._source_list.extend(input_names)
            _LOG.info(f"Loaded {len(self._inputs)} input sources: {input_names}")
        except HeosError as error:
            _LOG.error(f"Unable to retrieve input sources: {error}")
            self._inputs = []
        except Exception as e:
            _LOG.error(f"Unexpected error retrieving input sources: {e}")
            self._inputs = []
        
        # Get playlists - with error handling
        try:
            self._playlists = await self.heos.get_playlists()
            playlist_names = [playlist.name for playlist in self._playlists]
            self._source_list.extend(playlist_names)
            _LOG.info(f"Loaded {len(self._playlists)} playlists: {playlist_names}")
        except HeosError as error:
            _LOG.error(f"Unable to retrieve playlists: {error}")
            self._playlists = []
        except Exception as e:
            _LOG.error(f"Unexpected error retrieving playlists: {e}")
            self._playlists = []
        
        _LOG.info(f"Total source list ({len(self._source_list)}): {self._source_list}")

    def get_source_list(self) -> List[str]:
        """Return the list of sources for players."""
        return list(self._source_list)

    def get_favorite_index(self, name: str) -> Optional[int]:
        """Get the index of a favorite by name."""
        for index, favorite in self._favorites.items():
            if favorite.name == name:
                return index
        return None

    def get_current_source(self, now_playing_media) -> Optional[str]:
        """Determine current source from now playing media."""
        if not now_playing_media:
            return None
            
        # Try matching input source
        if now_playing_media.source_id == const.MUSIC_SOURCE_AUX_INPUT:
            for input_source in self._inputs:
                if input_source.name == now_playing_media.station:
                    return input_source.name
            for input_source in self._inputs:
                if input_source.media_id == now_playing_media.media_id:
                    return input_source.name
        
        # Try matching favorite station
        if hasattr(now_playing_media, 'type') and now_playing_media.type == 'station':
            for favorite in self._favorites.values():
                if (favorite.name == now_playing_media.station or 
                    favorite.media_id == getattr(now_playing_media, 'album_id', None)):
                    return favorite.name
        
        return None

    def find_input_source(self, name: str) -> Optional[MediaItem]:
        """Find input source by name."""
        for input_source in self._inputs:
            if input_source.name == name:
                return input_source
        return None

    def find_playlist(self, name: str) -> Optional[MediaItem]:
        """Find playlist by name."""
        for playlist in self._playlists:
            if playlist.name == name:
                return playlist
        return None

    def find_music_source(self, name: str) -> Optional[tuple[int, Any]]:
        """Find music source by name, return (source_id, source)."""
        for source_id, source in self._music_sources.items():
            if source.name == name and source.available:
                return source_id, source
        return None

    # Correct pyheos API methods for browsing
    async def browse_music_source(self, source_id: int):
        """Browse a music source using correct pyheos API."""
        try:
            _LOG.debug(f"Browsing source {source_id}")
            result = await self.heos.browse(source_id)
            _LOG.debug(f"Browse result type: {type(result)}")
            
            # Handle BrowseResult object properly
            if hasattr(result, 'items'):
                items = result.items
                _LOG.debug(f"Found items attribute with {len(items)} items")
                return items
            elif hasattr(result, 'media_items'):
                items = result.media_items
                _LOG.debug(f"Found media_items attribute with {len(items)} items")
                return items
            elif hasattr(result, 'data'):
                items = result.data
                _LOG.debug(f"Found data attribute with {len(items)} items")
                return items
            elif isinstance(result, list):
                _LOG.debug(f"Result is already a list with {len(result)} items")
                return result
            else:
                # Try to iterate over the result object
                try:
                    items = list(result)
                    _LOG.debug(f"Converted result to list with {len(items)} items")
                    return items
                except TypeError:
                    _LOG.warning(f"Unable to extract items from BrowseResult: {dir(result)}")
                    return []
                
        except Exception as e:
            _LOG.error(f"Error browsing source {source_id}: {e}")
            return []

    async def browse_container(self, source_id: int, container_id: str):
        """Browse a container using correct pyheos API."""
        try:
            _LOG.debug(f"Browsing container {container_id} in source {source_id}")
            result = await self.heos.browse(source_id, container_id)
            _LOG.debug(f"Browse container result type: {type(result)}")
            
            # Handle BrowseResult object properly
            if hasattr(result, 'items'):
                items = result.items
                _LOG.debug(f"Found items attribute with {len(items)} items")
                return items
            elif hasattr(result, 'media_items'):
                items = result.media_items
                _LOG.debug(f"Found media_items attribute with {len(items)} items")
                return items
            elif hasattr(result, 'data'):
                items = result.data
                _LOG.debug(f"Found data attribute with {len(items)} items")
                return items
            elif isinstance(result, list):
                _LOG.debug(f"Result is already a list with {len(result)} items")
                return result
            else:
                # Try to iterate over the result object
                try:
                    items = list(result)
                    _LOG.debug(f"Converted result to list with {len(items)} items")
                    return items
                except TypeError:
                    _LOG.warning(f"Unable to extract items from BrowseResult: {dir(result)}")
                    return []
                
        except Exception as e:
            _LOG.error(f"Error browsing container {container_id} in source {source_id}: {e}")
            return []