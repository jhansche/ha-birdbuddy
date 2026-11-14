"""Keep every Bird Buddy visit on disk: photos, videos and species.

Bird Buddy's media links are signed and expire after a day, and uncollected
postcards leave the feed within days, so nothing survives unless it is
downloaded while the link still works. The archive saves each visit into
date folders that Home Assistant's Media panel can browse::

    <folder>/2026/11/14/08-14-02 American Robin.jpg
    <folder>/2026/11/14/08-14-02 American Robin 2.mp4
    <folder>/2026/11/14/08-14-02 American Robin.json

The JSON file beside a postcard's media holds the species, the confidence,
the feeder and its files (paths from the archive folder). ``.index.json``
in the archive folder maps each saved media id, and each postcard's details
file, to its file, so a visit that turns up again (a later poll, a backfill
from the collections) is not saved twice.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError
from birdbuddy.media import Collection, Media, is_media_expired
from birdbuddy.postcards import PostcardAnalysis
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.util.dt as dt_util

from .const import LOGGER

INDEX_FILE = ".index.json"
# hass.data key: one archive per folder, shared by every account that uses it.
DATA_ARCHIVES = "birdbuddy_archives"
# Index key prefix for a postcard's details file, beside the media ids.
DETAILS_PREFIX = "postcard:"
UNKNOWN_VISITOR = "Unknown visitor"

_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}
# Characters that aren't safe in file names on common file systems.
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def normalize_folder(folder: str | None) -> str:
    """Spell a folder one way, so equal folders compare equal.

    Args:
        folder: The folder as entered, or None.

    Returns:
        The normalized path (no trailing slash, no ``..`` or ``//``), or ""
        when no folder is set.
    """
    folder = (folder or "").strip()
    return os.path.normpath(folder) if folder else ""


def get_archive(hass: HomeAssistant, folder: str) -> PostcardArchive:
    """Return the archive for a folder, shared by every account using it.

    Each archive has one lock and one cached index, so two accounts with the
    same folder can't overwrite each other's index entries.

    Args:
        hass: The Home Assistant instance.
        folder: The archive folder.

    Returns:
        The folder's archive.
    """
    key = normalize_folder(folder)
    archives: dict[str, PostcardArchive] = hass.data.setdefault(DATA_ARCHIVES, {})
    if key not in archives:
        archives[key] = PostcardArchive(hass, key)
    return archives[key]


def _safe_name(text: str) -> str:
    """Make text safe to use in a file name.

    Args:
        text: The text, usually a species name.

    Returns:
        The text with unsafe characters replaced and spaces tidied.
    """
    cleaned = _UNSAFE.sub("-", text).strip(" .-")
    return re.sub(r"\s+", " ", cleaned) or UNKNOWN_VISITOR


def _species_label(names: list[str]) -> str:
    """Name a visit after its species.

    Args:
        names: The recognized species names; empty when none was recognized.

    Returns:
        The names joined with " & ", or ``UNKNOWN_VISITOR``.
    """
    unique = list(dict.fromkeys(n for n in names if n))
    return _safe_name(" & ".join(unique)) if unique else UNKNOWN_VISITOR


def _extension(media: Media, url: str, content_type: str | None) -> str:
    """Pick the file extension for downloaded media.

    Args:
        media: The media that was downloaded.
        url: The URL it came from.
        content_type: The response's Content-Type, if any.

    Returns:
        The extension, including the dot.
    """
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base in _CONTENT_TYPES:
            return _CONTENT_TYPES[base]
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in _CONTENT_TYPES.values() or suffix == ".jpeg":
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".mp4" if media.is_video else ".jpg"


def _media_url(media: Media) -> str | None:
    """Pick the full-size URL for a media item.

    Args:
        media: The media item.

    Returns:
        The content URL (the video itself, for a video), else the thumbnail.
    """
    return media.content_url or media.thumbnail_url or None


class PostcardArchive:
    """Saves Bird Buddy visits into dated folders."""

    def __init__(self, hass: HomeAssistant, folder: str | Path) -> None:
        """Initialize the archive.

        Args:
            hass: The Home Assistant instance.
            folder: The folder that holds the archive.
        """
        self._hass = hass
        self.folder = Path(folder)
        self._lock = asyncio.Lock()
        self._index: dict[str, str] | None = None
        # True while the cached index has entries not yet written to disk.
        self._dirty = False

    async def _async_index(self) -> dict[str, str]:
        """Load the media-id index once.

        Returns:
            The index, mapping media id to its file relative to the folder.
        """
        index = self._index
        if index is None:
            index = await self._hass.async_add_executor_job(self._read_index)
            self._index = index
        return index

    def _read_index(self) -> dict[str, str]:
        """Read the index from disk (executor).

        A read error is raised, not treated as an empty index, so the index
        isn't cached empty and later overwritten. An index that isn't valid
        JSON is set aside as ``.index.json.bad-<time>`` and a new one begun.

        Returns:
            The saved index, or an empty one if there is none yet.

        Raises:
            OSError: If the index exists but can't be read.
        """
        path = self.folder / INDEX_FILE
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        try:
            data = json.loads(text)
        except ValueError as err:
            data = None
            problem = str(err)
        else:
            problem = "not a JSON object"
        if not isinstance(data, dict):
            bad = path.with_name(f"{INDEX_FILE}.bad-{dt_util.utcnow():%Y%m%d%H%M%S}")
            LOGGER.warning(
                "The archive index %s is damaged (%s); keeping it as %s",
                path,
                problem,
                bad,
            )
            path.replace(bad)
            return {}
        return {str(k): str(v) for k, v in data.items()}

    async def _async_flush(self) -> None:
        """Write the index if it has unsaved entries.

        Raises:
            OSError: If the write fails; the entries stay unsaved and the
                next save tries again.
        """
        if self._dirty and self._index is not None:
            await self._hass.async_add_executor_job(
                self._write_index, dict(self._index)
            )
            self._dirty = False

    def _write_index(self, index: dict[str, str]) -> None:
        """Write the index to disk atomically (executor).

        Args:
            index: The index to save.
        """
        path = self.folder / INDEX_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
        temp.replace(path)

    def _day_folder(self, when: datetime) -> Path:
        """Return the folder for a day.

        Args:
            when: A local time on that day.

        Returns:
            ``<folder>/YYYY/MM/DD``.
        """
        return self.folder / f"{when:%Y}" / f"{when:%m}" / f"{when:%d}"

    @staticmethod
    def _free_path(folder: Path, stem: str, suffix: str) -> Path:
        """Find a file name in a folder that isn't taken yet (executor).

        Args:
            folder: The folder.
            stem: The wanted name without extension.
            suffix: The extension, including the dot.

        Returns:
            ``stem + suffix``, or ``stem + " 2" + suffix`` and so on.
        """
        path = folder / f"{stem}{suffix}"
        n = 2
        while path.exists():
            path = folder / f"{stem} {n}{suffix}"
            n += 1
        return path

    def _write_file(self, folder: Path, stem: str, suffix: str, content: bytes) -> Path:
        """Write one file under a free name (executor).

        Args:
            folder: The folder.
            stem: The wanted name without extension.
            suffix: The extension, including the dot.
            content: The bytes to write.

        Returns:
            The path written.
        """
        folder.mkdir(parents=True, exist_ok=True)
        path = self._free_path(folder, stem, suffix)
        temp = path.with_name(path.name + ".part")
        temp.write_bytes(content)
        temp.replace(path)
        return path

    @staticmethod
    def _replace_file(path: Path, content: bytes) -> None:
        """Overwrite a file atomically (executor).

        Args:
            path: The file.
            content: Its new bytes.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".part")
        temp.write_bytes(content)
        temp.replace(path)

    async def _async_download(self, media: Media) -> tuple[bytes, str] | None:
        """Download a media item.

        Args:
            media: The media to download.

        Returns:
            The bytes and the file extension, or None if it can't be fetched.
        """
        url = _media_url(media)
        if not url or is_media_expired(url):
            LOGGER.debug("No usable URL for Bird Buddy media %s", media.id)
            return None
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                content = await resp.read()
                content_type = resp.headers.get("Content-Type")
        except (ClientError, TimeoutError) as err:
            LOGGER.warning("Could not download Bird Buddy media %s: %s", media.id, err)
            return None
        if not content:
            return None
        return content, _extension(media, url, content_type)

    async def _async_save_media(
        self, medias: list[Media], label: str, when: datetime
    ) -> list[str]:
        """Save the media not saved before, named after the visit.

        Args:
            medias: The media of one visit.
            label: The species label for the file names.
            when: The visit's local time.

        Returns:
            The newly written files, relative to the archive folder.
        """
        index = await self._async_index()
        folder = self._day_folder(when)
        stem = f"{when:%H-%M-%S} {label}"
        written: list[str] = []
        for media in medias:
            if media.id in index:
                continue
            downloaded = await self._async_download(media)
            if downloaded is None:
                continue
            content, suffix = downloaded
            path = await self._hass.async_add_executor_job(
                self._write_file, folder, stem, suffix, content
            )
            rel = path.relative_to(self.folder).as_posix()
            index[media.id] = rel
            self._dirty = True
            written.append(rel)
        await self._async_flush()
        return written

    async def async_save_postcard(
        self, analysis: PostcardAnalysis, feeder_name: str | None = None
    ) -> list[str]:
        """Save a postcard's photos and videos, with a JSON file of its details.

        Args:
            analysis: The identified postcard.
            feeder_name: The feeder's name, for the details file.

        Returns:
            The newly written media files, relative to the archive folder.
        """
        medias = analysis.medias
        if not medias:
            return []
        species = [name for s in analysis.species if (name := s.get("name"))]
        label = _species_label(species)
        when = dt_util.as_local(min(m.created_at for m in medias))
        async with self._lock:
            # Retry any index entries an earlier failed write left unsaved.
            await self._async_flush()
            written = await self._async_save_media(medias, label, when)
            index = await self._async_index()
            details_key = f"{DETAILS_PREFIX}{analysis.id}"
            # Paths from the archive folder: collection items are filed by the
            # day each was taken, which may not be the postcard's day.
            files = [index[m.id] for m in medias if m.id in index]
            # Tracked on its own, so a retry writes it when it's missing, and
            # rewrites it in place when the retry saved more of the media.
            if files and (details_key not in index or written):
                details: dict[str, Any] = {
                    "postcard_id": analysis.id,
                    "time": when.isoformat(),
                    "feeder": feeder_name,
                    "species": species,
                    "confidence": analysis.confidence,
                    "files": files,
                }
                content = json.dumps(details, indent=1, ensure_ascii=False).encode()
                if existing := index.get(details_key):
                    await self._hass.async_add_executor_job(
                        self._replace_file, self.folder / existing, content
                    )
                else:
                    path = await self._hass.async_add_executor_job(
                        self._write_file,
                        self._day_folder(when),
                        f"{when:%H-%M-%S} {label}",
                        ".json",
                        content,
                    )
                    index[details_key] = path.relative_to(self.folder).as_posix()
                    self._dirty = True
                    await self._async_flush()
        return written

    async def async_is_complete(self, analysis: PostcardAnalysis) -> bool:
        """Report whether a postcard's media and details file are all saved.

        Args:
            analysis: The identified postcard.

        Returns:
            True when every media item and the details file are in the index.
        """
        index = await self._async_index()
        if self._dirty:
            # Saved files whose index entries aren't on disk yet.
            return False
        if not analysis.medias:
            return True
        return f"{DETAILS_PREFIX}{analysis.id}" in index and all(
            m.id in index for m in analysis.medias
        )

    async def async_save_collection(
        self, collection: Collection, medias: list[Media]
    ) -> list[str]:
        """Save a species collection's photos and videos.

        Each item is filed under the day it was taken, named after the
        collection's species.

        Args:
            collection: The species collection.
            medias: Its media.

        Returns:
            The newly written media files, relative to the archive folder.
        """
        label = _species_label([collection.bird_name or ""])
        written: list[str] = []
        async with self._lock:
            await self._async_flush()
            for media in sorted(medias, key=lambda m: m.created_at):
                when = dt_util.as_local(media.created_at)
                written += await self._async_save_media([media], label, when)
        return written
