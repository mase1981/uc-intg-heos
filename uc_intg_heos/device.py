"""
HEOS device implementing PollingDevice pattern.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from pyheos import Heos, HeosError, HeosOptions, HeosPlayer
from pyheos.media import MediaItem, MediaMusicSource
from pyheos.types import PlayState, RepeatType, AddCriteriaType

from ucapi_framework import DeviceEvents, PollingDevice

from uc_intg_heos.config import HeosDeviceConfig
from uc_intg_heos.const import AVR_KEYWORDS, POLL_INTERVAL

_LOG = logging.getLogger(__name__)


class HeosDevice(PollingDevice):
    """HEOS system device managing pyheos client and all discovered players."""

    def __init__(self, device_config: HeosDeviceConfig, **kwargs: Any) -> None:
        super().__init__(device_config, poll_interval=POLL_INTERVAL, **kwargs)
        self._device_config = device_config
        self._heos: Heos | None = None
        self._state: str = "UNAVAILABLE"
        self._players: dict[int, HeosPlayer] = {}
        self._favorites: dict[int, MediaItem] = {}
        self._music_sources: dict[int, MediaMusicSource] = {}
        self._input_sources: list[MediaItem] = []
        self._source_lists: dict[int, list[str]] = {}
        self._event_unsubs: list = []

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str:
        return self._device_config.host

    @property
    def log_id(self) -> str:
        return f"{self.name} ({self.address})"

    @property
    def state(self) -> str:
        return self._state

    @property
    def heos(self) -> Heos | None:
        return self._heos

    @property
    def players(self) -> dict[int, HeosPlayer]:
        return self._players

    @property
    def favorites(self) -> dict[int, MediaItem]:
        return self._favorites

    @property
    def music_sources(self) -> dict[int, MediaMusicSource]:
        return self._music_sources

    @property
    def input_sources(self) -> list[MediaItem]:
        return self._input_sources

    def get_player(self, player_id: int) -> HeosPlayer | None:
        return self._players.get(player_id)

    def get_source_list(self, player_id: int) -> list[str]:
        return self._source_lists.get(player_id, [])

    def is_avr(self, player: HeosPlayer) -> bool:
        model_lower = player.model.lower()
        return any(kw in model_lower for kw in AVR_KEYWORDS)

    async def establish_connection(self) -> Heos:
        options = HeosOptions(
            host=self._device_config.host,
            events=True,
            all_progress_events=True,
            auto_reconnect=True,
            auto_reconnect_delay=5.0,
            heart_beat=True,
            heart_beat_interval=30.0,
        )
        self._heos = Heos(options)
        await self._heos.connect()

        if self._device_config.username and self._device_config.password:
            try:
                await self._heos.sign_in(
                    self._device_config.username, self._device_config.password
                )
                _LOG.info("[%s] Signed in to HEOS account", self.log_id)
            except HeosError as err:
                _LOG.warning("[%s] HEOS sign-in failed: %s", self.log_id, err)

        self._players = await self._heos.get_players()
        _LOG.info(
            "[%s] Discovered %d player(s): %s",
            self.log_id,
            len(self._players),
            ", ".join(p.name for p in self._players.values()),
        )

        self._register_event_callbacks()

        try:
            await self._load_account_data()
        except Exception as err:
            _LOG.warning("[%s] Initial account data load failed: %s", self.log_id, err)

        self._state = "ON"
        self.push_update()
        return self._heos

    async def poll_device(self) -> None:
        if not self._heos:
            return
        try:
            await self._refresh_players()
            self.push_update()
        except HeosError as err:
            _LOG.debug("[%s] Poll error: %s", self.log_id, err)
            if self._state != "UNAVAILABLE":
                self._state = "UNAVAILABLE"
                self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)
        except Exception as err:
            _LOG.debug("[%s] Unexpected poll error: %s", self.log_id, err)

    async def disconnect(self) -> None:
        for unsub in self._event_unsubs:
            unsub()
        self._event_unsubs.clear()

        if self._heos:
            try:
                await self._heos.disconnect()
            except Exception:
                pass
            self._heos = None

        self._players.clear()
        self._state = "UNAVAILABLE"
        await super().disconnect()

    def _register_event_callbacks(self) -> None:
        for player in self._players.values():
            unsub = player.add_on_player_event(self._on_player_event)
            self._event_unsubs.append(unsub)

        unsub = self._heos.add_on_controller_event(self._on_controller_event)
        self._event_unsubs.append(unsub)

    async def _on_player_event(self, player_id: int, event: str) -> None:
        _LOG.debug("[%s] Player event: player=%d event=%s", self.log_id, player_id, event)
        self.push_update()

    async def _on_controller_event(self, event: str, data: Any = None) -> None:
        _LOG.debug("[%s] Controller event: %s", self.log_id, event)
        if event in ("players_changed", "groups_changed"):
            try:
                self._players = await self._heos.get_players()
                await self._load_account_data()
            except HeosError as err:
                _LOG.warning("[%s] Failed to refresh after controller event: %s", self.log_id, err)
        self.push_update()

    async def _refresh_players(self) -> None:
        for player in self._players.values():
            try:
                await player.refresh()
            except HeosError as err:
                _LOG.debug("[%s] Failed to refresh player %s: %s", self.log_id, player.name, err)

    async def _load_account_data(self) -> None:
        try:
            self._favorites = await self._heos.get_favorites()
            _LOG.debug("[%s] Loaded %d favorites", self.log_id, len(self._favorites))
        except HeosError as err:
            _LOG.debug("[%s] Failed to load favorites: %s", self.log_id, err)

        try:
            self._music_sources = await self._heos.get_music_sources()
            _LOG.debug("[%s] Loaded %d music sources", self.log_id, len(self._music_sources))
        except HeosError as err:
            _LOG.debug("[%s] Failed to load music sources: %s", self.log_id, err)

        try:
            self._input_sources = await self._heos.get_input_sources()
            _LOG.debug("[%s] Loaded %d input sources", self.log_id, len(self._input_sources))
        except HeosError as err:
            _LOG.debug("[%s] Failed to load input sources: %s", self.log_id, err)

        self._build_source_lists()

    def _build_source_lists(self) -> None:
        base_sources: list[str] = []
        for fav in self._favorites.values():
            base_sources.append(fav.name)
        for inp in self._input_sources:
            base_sources.append(inp.name)
        for src in self._music_sources.values():
            if src.available:
                base_sources.append(src.name)

        for player_id in self._players:
            self._source_lists[player_id] = list(base_sources)

    async def play_source_by_name(self, player_id: int, source_name: str) -> bool:
        for fav_idx, fav in self._favorites.items():
            if fav.name == source_name:
                player = self._players.get(player_id)
                if player:
                    await player.play_preset_station(fav_idx)
                    return True

        for inp in self._input_sources:
            if inp.name == source_name:
                player = self._players.get(player_id)
                if player:
                    await player.play_input_source(inp.media_id)
                    return True

        for src_id, src in self._music_sources.items():
            if src.name == source_name and src.available:
                try:
                    result = await src.browse()
                    if result and result.items:
                        first = result.items[0]
                        if first.playable:
                            await first.play_media(player_id, AddCriteriaType.REPLACE_AND_PLAY)
                            return True
                        elif first.browsable:
                            sub_result = await first.browse(None, None)
                            if sub_result and sub_result.items:
                                for item in sub_result.items:
                                    if item.playable:
                                        await item.play_media(
                                            player_id, AddCriteriaType.REPLACE_AND_PLAY
                                        )
                                        return True
                except HeosError as err:
                    _LOG.error("[%s] Error browsing source %s: %s", self.log_id, source_name, err)

        return False

    async def browse_root(self) -> list[dict]:
        items = []
        if self._favorites:
            items.append({
                "media_id": "favorites",
                "title": "Favorites",
                "can_browse": True,
                "can_play": False,
                "media_class": "playlist",
            })
        if self._input_sources:
            items.append({
                "media_id": "inputs",
                "title": "Input Sources",
                "can_browse": True,
                "can_play": False,
                "media_class": "directory",
            })
        for src_id, src in self._music_sources.items():
            if src.available:
                items.append({
                    "media_id": f"source_{src_id}",
                    "title": src.name,
                    "thumbnail": src.image_url or None,
                    "can_browse": True,
                    "can_play": False,
                    "media_class": "directory",
                })
        return items

    async def browse_favorites(self) -> list[dict]:
        items = []
        for idx, fav in self._favorites.items():
            items.append({
                "media_id": f"favorite_{idx}",
                "title": fav.name,
                "thumbnail": fav.image_url or None,
                "can_browse": False,
                "can_play": True,
                "media_class": "radio",
            })
        return items

    async def browse_inputs(self) -> list[dict]:
        items = []
        for inp in self._input_sources:
            items.append({
                "media_id": f"input_{inp.media_id}",
                "title": inp.name,
                "thumbnail": inp.image_url or None,
                "can_browse": False,
                "can_play": True,
                "media_class": "channel",
            })
        return items

    async def browse_music_source(self, source_id: int) -> list[dict]:
        items = []
        src = self._music_sources.get(source_id)
        if not src:
            return items
        try:
            result = await src.browse()
            if result and result.items:
                for item in result.items:
                    media_id_str = f"media_{source_id}_{item.container_id or ''}_{item.media_id or ''}"
                    items.append({
                        "media_id": media_id_str,
                        "title": item.name,
                        "artist": item.artist or None,
                        "album": item.album or None,
                        "thumbnail": item.image_url or None,
                        "can_browse": item.browsable,
                        "can_play": item.playable,
                        "media_class": "music" if item.playable else "directory",
                    })
        except HeosError as err:
            _LOG.error("[%s] Failed to browse source %d: %s", self.log_id, source_id, err)
        return items

    async def browse_container(self, source_id: int, container_id: str) -> list[dict]:
        items = []
        src = self._music_sources.get(source_id)
        if not src:
            return items
        try:
            result = await src.browse()
            if result and result.items:
                for parent_item in result.items:
                    if parent_item.container_id == container_id:
                        sub_result = await parent_item.browse(None, None)
                        if sub_result and sub_result.items:
                            for item in sub_result.items:
                                media_id_str = (
                                    f"media_{source_id}_{item.container_id or ''}_{item.media_id or ''}"
                                )
                                items.append({
                                    "media_id": media_id_str,
                                    "title": item.name,
                                    "artist": item.artist or None,
                                    "album": item.album or None,
                                    "thumbnail": item.image_url or None,
                                    "can_browse": item.browsable,
                                    "can_play": item.playable,
                                    "media_class": "music" if item.playable else "directory",
                                })
                        break
        except HeosError as err:
            _LOG.error(
                "[%s] Failed to browse container %s in source %d: %s",
                self.log_id, container_id, source_id, err,
            )
        return items

    async def play_media_by_id(self, player_id: int, media_id: str) -> bool:
        player = self._players.get(player_id)
        if not player:
            return False

        if media_id.startswith("favorite_"):
            idx = int(media_id.split("_", 1)[1])
            await player.play_preset_station(idx)
            return True

        if media_id.startswith("input_"):
            input_name = media_id.split("_", 1)[1]
            await player.play_input_source(input_name)
            return True

        if media_id.startswith("media_"):
            parts = media_id.split("_", 3)
            if len(parts) >= 4:
                source_id = int(parts[1])
                container_id = parts[2] if parts[2] else None
                item_media_id = parts[3] if parts[3] else None
                await player.add_to_queue(
                    source_id,
                    container_id or "",
                    item_media_id,
                    AddCriteriaType.REPLACE_AND_PLAY,
                )
                return True

        return False
