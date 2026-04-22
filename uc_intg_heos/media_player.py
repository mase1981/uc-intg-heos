"""
HEOS Media Player entity.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any

from ucapi import media_player, StatusCodes
from ucapi.media_player import (
    Attributes,
    BrowseMediaItem,
    BrowseOptions,
    BrowseResults,
    Commands,
    DeviceClasses,
    Features,
    MediaClass,
    MediaContentType,
    RepeatMode,
    States,
)
from ucapi.api_definitions import Pagination

from pyheos import HeosError, HeosPlayer
from pyheos.types import PlayState, RepeatType

from ucapi_framework import MediaPlayerEntity

from uc_intg_heos.config import HeosDeviceConfig
from uc_intg_heos.device import HeosDevice

_LOG = logging.getLogger(__name__)

PLAY_STATE_MAP = {
    None: States.STANDBY,
    PlayState.UNKNOWN: States.STANDBY,
    PlayState.PLAY: States.PLAYING,
    PlayState.STOP: States.STANDBY,
    PlayState.PAUSE: States.PAUSED,
}

HEOS_REPEAT_MAP = {
    RepeatType.OFF: RepeatMode.OFF,
    RepeatType.ON_ALL: RepeatMode.ALL,
    RepeatType.ON_ONE: RepeatMode.ONE,
}
UC_REPEAT_MAP = {v: k for k, v in HEOS_REPEAT_MAP.items()}

FEATURES = [
    Features.ON_OFF,
    Features.PLAY_PAUSE,
    Features.STOP,
    Features.NEXT,
    Features.PREVIOUS,
    Features.VOLUME,
    Features.VOLUME_UP_DOWN,
    Features.MUTE_TOGGLE,
    Features.MUTE,
    Features.UNMUTE,
    Features.REPEAT,
    Features.SHUFFLE,
    Features.SELECT_SOURCE,
    Features.MEDIA_DURATION,
    Features.MEDIA_POSITION,
    Features.MEDIA_TITLE,
    Features.MEDIA_ARTIST,
    Features.MEDIA_ALBUM,
    Features.MEDIA_IMAGE_URL,
    Features.MEDIA_TYPE,
    Features.BROWSE_MEDIA,
    Features.PLAY_MEDIA,
]


class HeosMediaPlayer(MediaPlayerEntity):
    """Media player entity for a single HEOS player."""

    def __init__(
        self, device_config: HeosDeviceConfig, device: HeosDevice, player: HeosPlayer
    ) -> None:
        self._device = device
        self._player = player
        self._player_id = player.player_id

        model_lower = player.model.lower()
        self._is_avr = device.is_avr(player)
        dev_class = DeviceClasses.RECEIVER if self._is_avr else DeviceClasses.SPEAKER

        entity_id = f"media_player.{device_config.identifier}.{player.player_id}"

        super().__init__(
            entity_id,
            player.name,
            FEATURES,
            {
                Attributes.STATE: States.UNKNOWN,
                Attributes.VOLUME: 0,
                Attributes.MUTED: False,
                Attributes.MEDIA_DURATION: 0,
                Attributes.MEDIA_POSITION: 0,
                Attributes.MEDIA_TITLE: "",
                Attributes.MEDIA_ARTIST: "",
                Attributes.MEDIA_ALBUM: "",
                Attributes.MEDIA_IMAGE_URL: "",
                Attributes.SOURCE: "",
                Attributes.SOURCE_LIST: [],
                Attributes.REPEAT: RepeatMode.OFF,
                Attributes.SHUFFLE: False,
            },
            device_class=dev_class,
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == "UNAVAILABLE":
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return

        player = self._device.get_player(self._player_id)
        if not player:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return

        self._player = player
        attrs: dict[str, Any] = {}
        attrs[Attributes.STATE] = PLAY_STATE_MAP.get(player.state, States.STANDBY)
        attrs[Attributes.VOLUME] = player.volume
        attrs[Attributes.MUTED] = player.is_muted
        attrs[Attributes.REPEAT] = HEOS_REPEAT_MAP.get(player.repeat, RepeatMode.OFF)
        attrs[Attributes.SHUFFLE] = player.shuffle
        attrs[Attributes.SOURCE_LIST] = self._device.get_source_list(self._player_id)

        now = player.now_playing_media
        if now:
            attrs[Attributes.MEDIA_TITLE] = now.song or now.station or ""
            attrs[Attributes.MEDIA_ARTIST] = now.artist or ""
            attrs[Attributes.MEDIA_ALBUM] = now.album or ""
            attrs[Attributes.MEDIA_IMAGE_URL] = now.image_url or ""
            attrs[Attributes.MEDIA_DURATION] = now.duration or 0
            attrs[Attributes.MEDIA_POSITION] = now.current_position or 0

            if now.source_id is not None:
                src = self._device.music_sources.get(now.source_id)
                if src:
                    attrs[Attributes.SOURCE] = src.name
            for inp in self._device.input_sources:
                if inp.media_id == (now.media_id or ""):
                    attrs[Attributes.SOURCE] = inp.name
                    break
        else:
            attrs[Attributes.MEDIA_TITLE] = ""
            attrs[Attributes.MEDIA_ARTIST] = ""
            attrs[Attributes.MEDIA_ALBUM] = ""
            attrs[Attributes.MEDIA_IMAGE_URL] = ""
            attrs[Attributes.MEDIA_DURATION] = 0
            attrs[Attributes.MEDIA_POSITION] = 0

        self.update(attrs)

    async def browse(self, options: BrowseOptions) -> BrowseResults | StatusCodes:
        media_id = options.media_id

        try:
            if not media_id or media_id == "root":
                raw_items = await self._device.browse_root()
            elif media_id == "favorites":
                raw_items = await self._device.browse_favorites()
            elif media_id == "inputs":
                raw_items = await self._device.browse_inputs()
            elif media_id.startswith("source_"):
                source_id = int(media_id.split("_", 1)[1])
                raw_items = await self._device.browse_music_source(source_id)
            elif media_id.startswith("media_"):
                parts = media_id.split("_", 3)
                if len(parts) >= 3:
                    source_id = int(parts[1])
                    container_id = parts[2] if len(parts) > 2 else ""
                    raw_items = await self._device.browse_container(source_id, container_id)
                else:
                    raw_items = []
            else:
                raw_items = []

            browse_items = []
            for item in raw_items:
                browse_items.append(
                    BrowseMediaItem(
                        media_id=item["media_id"],
                        title=item["title"],
                        subtitle=item.get("artist"),
                        artist=item.get("artist"),
                        album=item.get("album"),
                        media_class=item.get("media_class"),
                        media_type=None,
                        can_browse=item.get("can_browse", False),
                        can_play=item.get("can_play", False),
                        can_search=None,
                        thumbnail=item.get("thumbnail"),
                        duration=None,
                        items=None,
                    )
                )

            root_item = BrowseMediaItem(
                media_id=media_id or "root",
                title="HEOS" if not media_id or media_id == "root" else media_id,
                subtitle=None,
                artist=None,
                album=None,
                media_class=MediaClass.DIRECTORY,
                media_type=None,
                can_browse=True,
                can_play=False,
                can_search=None,
                thumbnail=None,
                duration=None,
                items=browse_items,
            )

            return BrowseResults(
                media=root_item,
                pagination=Pagination(page=1, limit=len(browse_items), count=len(browse_items)),
            )
        except Exception as err:
            _LOG.error("Browse error for %s: %s", media_id, err)
            return StatusCodes.SERVER_ERROR

    async def _handle_command(
        self, entity: media_player.MediaPlayer, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        params = params or {}
        player = self._device.get_player(self._player_id)
        if not player:
            return StatusCodes.SERVICE_UNAVAILABLE

        try:
            match cmd_id:
                case Commands.ON:
                    await player.play()

                case Commands.OFF:
                    if self._is_avr:
                        try:
                            await player.set_volume(0)
                            await asyncio.sleep(0.3)
                            await player.stop()
                        except Exception:
                            await player.stop()
                    else:
                        await player.stop()

                case Commands.PLAY_PAUSE:
                    if player.state == PlayState.PLAY:
                        await player.pause()
                    else:
                        await player.play()

                case Commands.STOP:
                    await player.stop()

                case Commands.NEXT:
                    await player.play_next()

                case Commands.PREVIOUS:
                    await player.play_previous()

                case Commands.VOLUME:
                    vol = int(params.get("volume", 0))
                    await player.set_volume(vol)

                case Commands.VOLUME_UP:
                    await player.volume_up(params.get("step", 5))

                case Commands.VOLUME_DOWN:
                    await player.volume_down(params.get("step", 5))

                case Commands.MUTE_TOGGLE:
                    await player.toggle_mute()

                case Commands.MUTE:
                    await player.mute()

                case Commands.UNMUTE:
                    await player.unmute()

                case Commands.REPEAT:
                    mode = params.get("repeat", "OFF")
                    heos_repeat = UC_REPEAT_MAP.get(RepeatMode(mode), RepeatType.OFF)
                    await player.set_play_mode(heos_repeat, player.shuffle)

                case Commands.SHUFFLE:
                    shuffle = params.get("shuffle", False)
                    await player.set_play_mode(player.repeat, shuffle)

                case Commands.SELECT_SOURCE:
                    source = params.get("source", "")
                    if not source:
                        return StatusCodes.BAD_REQUEST
                    found = await self._device.play_source_by_name(self._player_id, source)
                    if not found:
                        _LOG.warning("Source not found: %s", source)
                        return StatusCodes.BAD_REQUEST

                case Commands.PLAY_MEDIA:
                    media_id = params.get("media_id", "")
                    if not media_id:
                        return StatusCodes.BAD_REQUEST
                    played = await self._device.play_media_by_id(self._player_id, media_id)
                    if not played:
                        return StatusCodes.BAD_REQUEST

                case _:
                    return StatusCodes.NOT_IMPLEMENTED

            return StatusCodes.OK

        except HeosError as err:
            _LOG.error("[%s] HEOS command error %s: %s", entity.id, cmd_id, err)
            return StatusCodes.SERVER_ERROR
        except Exception as err:
            _LOG.error("[%s] Command error %s: %s", entity.id, cmd_id, err)
            return StatusCodes.SERVER_ERROR


def create_media_players(
    device_config: HeosDeviceConfig, device: HeosDevice
) -> list[HeosMediaPlayer]:
    entities = []
    for player in device.players.values():
        entities.append(HeosMediaPlayer(device_config, device, player))
    return entities
