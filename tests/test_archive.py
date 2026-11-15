"""Tests for the Bird Buddy visit archive."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from birdbuddy.exceptions import GraphqlError, UnexpectedResponseError
from birdbuddy.feed import Feed, FeedNode
from birdbuddy.media import Collection, Media
from birdbuddy.postcards import PostcardAnalysis
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.birdbuddy import _async_options_updated
from custom_components.birdbuddy.archive import (
    INDEX_FILE,
    UNKNOWN_VISITOR,
    PostcardArchive,
)
from custom_components.birdbuddy.const import (
    CONF_ARCHIVE_FOLDER,
    DOMAIN,
    SERVICE_ARCHIVE_HISTORY,
)
from custom_components.birdbuddy.coordinator import (
    GALLERY_SYNC_EVERY,
    BirdBuddyDataUpdateCoordinator,
)
from custom_components.birdbuddy.gallery import (
    MYSTERY_VISITOR,
    async_feed_media,
    async_gallery_pages,
    feed_item_media,
)

_FUTURE = "Expires=4102444800"  # 2100-01-01
_PAST = "Expires=946684800"  # 2000-01-01
_PHOTO = f"https://example.invalid/c.jpg?{_FUTURE}"
_VIDEO = f"https://example.invalid/v.mp4?{_FUTURE}"
_TAKEN = "2026-11-14T14:14:02.000Z"


def _image(media_id: str = "m1", url: str = _PHOTO, taken: str = _TAKEN) -> dict:
    return {
        "__typename": "MediaImage",
        "id": media_id,
        "createdAt": taken,
        "thumbnailUrl": url,
        "contentUrl": url,
    }


def _video(media_id: str = "v1") -> dict:
    return {
        "__typename": "MediaVideo",
        "id": media_id,
        "createdAt": _TAKEN,
        "thumbnailUrl": f"https://example.invalid/vt.jpg?{_FUTURE}",
        "contentUrl": _VIDEO,
    }


def _analysis(medias: list[dict], species: list[str] | None = None) -> PostcardAnalysis:
    return PostcardAnalysis(
        {
            "id": "pc1",
            "feeder": {"__typename": "Feeder", "id": "feeder1"},
            "medias": medias,
            "inferenceConfidenceLevel": "HIGH_CONFIDENCE",
            "sightingReportPreview": {
                "sightings": [
                    {
                        "__typename": "SightingRecognizedBird",
                        "species": {"id": f"s{i}", "name": name},
                    }
                    for i, name in enumerate(species or [])
                ]
            },
        }
    )


def _local_stem(taken: str = _TAKEN) -> tuple[str, str]:
    when = dt_util.as_local(dt_util.parse_datetime(taken))  # type: ignore[arg-type]
    return f"{when:%Y}/{when:%m}/{when:%d}", f"{when:%H-%M-%S}"


@pytest.fixture
def media_urls(aioclient_mock):
    """Serve a photo and a video."""
    aioclient_mock.get(_PHOTO, content=b"jpeg", headers={"Content-Type": "image/jpeg"})
    aioclient_mock.get(_VIDEO, content=b"mp4", headers={"Content-Type": "video/mp4"})
    return aioclient_mock


async def test_saves_a_postcards_photo_video_and_details(hass, tmp_path, media_urls):
    """A postcard's media lands in a dated folder, named after the species."""
    archive = PostcardArchive(hass, tmp_path)
    analysis = _analysis([_image(), _video()], ["American Robin"])

    written = await archive.async_save_postcard(analysis, "Birdhouse")

    day, time = _local_stem()
    assert written == [
        f"{day}/{time} American Robin.jpg",
        f"{day}/{time} American Robin.mp4",
    ]
    assert (tmp_path / written[0]).read_bytes() == b"jpeg"
    assert (tmp_path / written[1]).read_bytes() == b"mp4"
    details = json.loads((tmp_path / f"{day}/{time} American Robin.json").read_text())
    assert details["postcard_id"] == "pc1"
    assert details["species"] == ["American Robin"]
    assert details["feeder"] == "Birdhouse"
    assert details["confidence"] == "HIGH_CONFIDENCE"
    assert details["files"] == written
    index = json.loads((tmp_path / INDEX_FILE).read_text())
    assert index == {
        "m1": written[0],
        "v1": written[1],
        "postcard:pc1": f"{day}/{time} American Robin.json",
    }


async def test_a_saved_visit_is_not_saved_twice(hass, tmp_path, media_urls):
    """Media already in the index is skipped, even by a new archive object."""
    analysis = _analysis([_image()], ["American Robin"])
    assert await PostcardArchive(hass, tmp_path).async_save_postcard(analysis)

    again = await PostcardArchive(hass, tmp_path).async_save_postcard(analysis)

    assert again == []
    day, _ = _local_stem()
    assert len(list((tmp_path / day).iterdir())) == 2  # one photo, one details file


async def test_two_photos_of_one_visit_get_numbered(hass, tmp_path, aioclient_mock):
    """A second photo with the same time and species gets " 2"."""
    other = f"https://example.invalid/d.jpg?{_FUTURE}"
    aioclient_mock.get(_PHOTO, content=b"a", headers={"Content-Type": "image/jpeg"})
    aioclient_mock.get(other, content=b"b", headers={"Content-Type": "image/jpeg"})
    archive = PostcardArchive(hass, tmp_path)

    written = await archive.async_save_postcard(
        _analysis([_image("m1"), _image("m2", other)], ["Blue Jay"])
    )

    day, time = _local_stem()
    assert written == [f"{day}/{time} Blue Jay.jpg", f"{day}/{time} Blue Jay 2.jpg"]


async def test_an_unrecognized_visitor_and_unsafe_names(hass, tmp_path, media_urls):
    """No species gives "Unknown visitor"; unsafe characters are replaced."""
    archive = PostcardArchive(hass, tmp_path)
    unknown = await archive.async_save_postcard(_analysis([_image("m1")]))
    assert unknown[0].endswith(f" {UNKNOWN_VISITOR}.jpg")

    archive2 = PostcardArchive(hass, tmp_path / "other")
    odd = await archive2.async_save_postcard(_analysis([_image("m2")], ["Jay/Crow?"]))
    assert odd[0].endswith(" Jay-Crow.jpg")


async def test_an_expired_link_is_skipped(hass, tmp_path, aioclient_mock):
    """An expired signed URL isn't fetched, and nothing is written."""
    expired = f"https://example.invalid/old.jpg?{_PAST}"
    archive = PostcardArchive(hass, tmp_path)

    written = await archive.async_save_postcard(
        _analysis([_image("m1", expired)], ["American Robin"])
    )

    assert written == []
    assert aioclient_mock.call_count == 0
    assert not (tmp_path / INDEX_FILE).exists()


async def test_a_failed_download_is_skipped(hass, tmp_path, aioclient_mock):
    """A failing download writes nothing and doesn't raise."""
    aioclient_mock.get(_PHOTO, status=403)
    archive = PostcardArchive(hass, tmp_path)

    assert await archive.async_save_postcard(_analysis([_image()], ["Robin"])) == []


async def test_saves_a_collection_by_day(hass, tmp_path, aioclient_mock):
    """Collection media is filed under the day each item was taken."""
    later = f"https://example.invalid/e.jpg?{_FUTURE}"
    aioclient_mock.get(_PHOTO, content=b"a", headers={"Content-Type": "image/jpeg"})
    aioclient_mock.get(later, content=b"b", headers={"Content-Type": "image/jpeg"})
    collection = Collection({"id": "c1", "species": {"id": "s1", "name": "Blue Jay"}})
    medias = [Media(_image("m2", later, "2026-11-10T18:00:00.000Z")), Media(_image())]

    written = await PostcardArchive(hass, tmp_path).async_save_collection(
        collection, medias
    )

    first_day, first_time = _local_stem("2026-11-10T18:00:00.000Z")
    day, time = _local_stem()
    assert written == [
        f"{first_day}/{first_time} Blue Jay.jpg",
        f"{day}/{time} Blue Jay.jpg",
    ]


def _coordinator(hass, folder: Path | None) -> BirdBuddyDataUpdateCoordinator:
    client = MagicMock()
    client.feeders = {"feeder1": MagicMock()}
    client.feeders["feeder1"].name = "Birdhouse"
    options = {CONF_ARCHIVE_FOLDER: str(folder)} if folder else {}
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options, title="Bird Buddy")
    entry.add_to_hass(hass)
    return BirdBuddyDataUpdateCoordinator(hass, client, entry)


async def test_new_postcards_are_archived_without_listeners(hass, tmp_path, media_urls):
    """With an archive folder, postcards are identified and saved anyway."""
    coordinator = _coordinator(hass, tmp_path)
    analysis = _analysis([_image()], ["American Robin"])
    coordinator.client.identify_postcard = AsyncMock(return_value=analysis)

    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc1"})
    await coordinator._process_feed([postcard])

    coordinator.client.identify_postcard.assert_awaited_once_with(postcard)
    day, time = _local_stem()
    details = json.loads((tmp_path / f"{day}/{time} American Robin.json").read_text())
    assert details["feeder"] == "Birdhouse"


async def test_without_an_archive_folder_nothing_is_saved(hass):
    """No folder and no listeners still skips the identify call."""
    coordinator = _coordinator(hass, None)
    coordinator.client.identify_postcard = AsyncMock()

    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc1"})
    await coordinator._process_feed([postcard])

    assert coordinator.archive is None
    coordinator.client.identify_postcard.assert_not_awaited()


async def test_a_failed_save_keeps_the_poll_going(hass, tmp_path):
    """A disk error is logged; the coordinator carries on."""
    coordinator = _coordinator(hass, tmp_path)
    analysis = _analysis([_image()], ["American Robin"])
    with patch.object(
        coordinator.archive, "async_save_postcard", side_effect=OSError("disk full")
    ):
        assert await coordinator.async_archive_postcard(analysis) == []


async def test_archive_history_saves_collections_and_the_feed(hass, tmp_path):
    """The backfill walks every collection and every postcard in the feed."""
    coordinator = _coordinator(hass, tmp_path)
    collection = Collection({"id": "c1", "species": {"id": "s1", "name": "Blue Jay"}})
    client = coordinator.client
    client.refresh_collections = AsyncMock(return_value={"c1": collection})
    client.collection = AsyncMock(return_value={"m2": Media(_image("m2"))})
    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc1"})
    client.new_postcards = AsyncMock(return_value=[postcard])
    client.identify_postcard = AsyncMock(return_value=_analysis([_image()], ["Robin"]))
    archive = coordinator.archive
    assert archive is not None

    sync = AsyncMock(return_value=4)
    with (
        patch.object(coordinator, "async_sync_gallery", sync),
        patch(
            "custom_components.birdbuddy.coordinator.async_feed_media",
            AsyncMock(return_value=[(["Cardinal"], Media(_image("m3")))]),
        ),
        patch.object(archive, "async_save_items", AsyncMock(return_value=["d"])),
        patch.object(
            archive, "async_save_collection", AsyncMock(return_value=["a", "b"])
        ),
        patch.object(archive, "async_save_postcard", AsyncMock(return_value=["c"])),
    ):
        counts = await coordinator.async_archive_history()

    assert counts == {"gallery": 4, "collections": 2, "feed": 1, "postcards": 1}
    client.collection.assert_awaited_once_with("c1")
    sync.assert_awaited_once_with(full=True)


async def test_archive_history_needs_a_folder(hass):
    """The backfill explains what to set when there is no archive."""
    coordinator = _coordinator(hass, None)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_archive_history()


async def test_the_service_runs_the_backfill(hass, tmp_path):
    """birdbuddy.archive_history returns the counts per account."""
    from custom_components.birdbuddy import _setup_services  # noqa: PLC0415

    _setup_services(hass)
    coordinator = _coordinator(hass, tmp_path)
    hass.data.setdefault(DOMAIN, {})[coordinator.config_entry.entry_id] = coordinator
    with patch.object(
        coordinator,
        "async_archive_history",
        AsyncMock(return_value={"collections": 3, "postcards": 0}),
    ):
        response = await hass.services.async_call(
            DOMAIN, SERVICE_ARCHIVE_HISTORY, {}, blocking=True, return_response=True
        )
    assert response == {"Bird Buddy": {"collections": 3, "postcards": 0}}


async def test_the_service_without_a_folder_raises(hass):
    """With no archive folder anywhere, the service raises."""
    from custom_components.birdbuddy import _setup_services  # noqa: PLC0415

    _setup_services(hass)
    hass.data.setdefault(DOMAIN, {})["x"] = _coordinator(hass, None)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, SERVICE_ARCHIVE_HISTORY, {}, blocking=True, return_response=True
        )


async def test_options_flow_sets_and_checks_the_folder(hass, tmp_path):
    """The options form takes an allowed absolute folder; blank turns it off."""
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    entry = MockConfigEntry(domain=DOMAIN, data={}, version=2)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ARCHIVE_FOLDER: "media/birds"}
    )
    assert result["errors"] == {CONF_ARCHIVE_FOLDER: "not_absolute"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ARCHIVE_FOLDER: "/etc/birds"}
    )
    assert result["errors"] == {CONF_ARCHIVE_FOLDER: "not_allowed"}

    folder = str(tmp_path / "birds")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ARCHIVE_FOLDER: f" {folder} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_ARCHIVE_FOLDER: folder}

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ARCHIVE_FOLDER: ""}
    )
    assert entry.options == {CONF_ARCHIVE_FOLDER: ""}


async def test_only_a_folder_change_reloads(hass, tmp_path):
    """A token rotation updates the entry too, but must not reload it."""
    coordinator = _coordinator(hass, tmp_path)
    entry = coordinator.config_entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        await _async_options_updated(hass, entry)
        reload.assert_not_awaited()

        hass.config_entries.async_update_entry(
            entry, options={CONF_ARCHIVE_FOLDER: str(tmp_path / "new")}
        )
        await _async_options_updated(hass, entry)
        reload.assert_awaited_once_with(entry.entry_id)


def test_the_archive_folder_is_a_path(hass, tmp_path):
    """The archive keeps its folder as a Path."""
    assert PostcardArchive(hass, str(tmp_path)).folder == tmp_path


async def test_a_trailing_slash_does_not_cause_reloads(hass, tmp_path):
    """The same folder spelled with a trailing slash isn't a change."""
    coordinator = _coordinator(hass, None)
    entry = coordinator.config_entry
    hass.config_entries.async_update_entry(
        entry, options={CONF_ARCHIVE_FOLDER: f"{tmp_path}/"}
    )
    coordinator = BirdBuddyDataUpdateCoordinator(hass, coordinator.client, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        await _async_options_updated(hass, entry)
    reload.assert_not_awaited()


async def test_accounts_sharing_a_folder_share_one_archive(hass, tmp_path):
    """Two accounts with the same folder use one archive, so one index."""
    first = _coordinator(hass, tmp_path)
    second = _coordinator(hass, Path(f"{tmp_path}/./"))
    assert first.archive is second.archive


async def test_options_flow_normalizes_the_folder(hass, tmp_path):
    """A trailing slash is dropped before the folder is saved."""
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    entry = MockConfigEntry(domain=DOMAIN, data={}, version=2)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ARCHIVE_FOLDER: f"{tmp_path}/birds/"}
    )
    assert entry.options == {CONF_ARCHIVE_FOLDER: f"{tmp_path}/birds"}


async def test_a_missing_details_file_is_written_on_retry(hass, tmp_path, media_urls):
    """If the details file failed, a retry writes it though the media is saved."""
    archive = PostcardArchive(hass, tmp_path)
    analysis = _analysis([_image()], ["American Robin"])
    real_write = archive._write_file

    def fail_json(folder, stem, suffix, content):
        if suffix == ".json":
            msg = "disk full"
            raise OSError(msg)
        return real_write(folder, stem, suffix, content)

    with (
        patch.object(archive, "_write_file", side_effect=fail_json),
        pytest.raises(OSError, match="disk full"),
    ):
        await archive.async_save_postcard(analysis)

    assert await archive.async_save_postcard(analysis) == []
    day, time = _local_stem()
    details = json.loads((tmp_path / f"{day}/{time} American Robin.json").read_text())
    assert details["files"] == [f"{day}/{time} American Robin.jpg"]


async def test_a_retry_that_saves_more_media_updates_the_details(
    hass, tmp_path, aioclient_mock
):
    """The details file lists media that only a retry managed to save."""
    other = f"https://example.invalid/d.jpg?{_FUTURE}"
    aioclient_mock.get(_PHOTO, content=b"a", headers={"Content-Type": "image/jpeg"})
    aioclient_mock.get(other, status=503)
    archive = PostcardArchive(hass, tmp_path)
    analysis = _analysis([_image("m1"), _image("m2", other)], ["Blue Jay"])
    await archive.async_save_postcard(analysis)

    aioclient_mock.clear_requests()
    aioclient_mock.get(other, content=b"b", headers={"Content-Type": "image/jpeg"})
    written = await archive.async_save_postcard(analysis)

    day, time = _local_stem()
    assert written == [f"{day}/{time} Blue Jay 2.jpg"]
    details = json.loads((tmp_path / f"{day}/{time} Blue Jay.json").read_text())
    assert details["files"] == [
        f"{day}/{time} Blue Jay.jpg",
        f"{day}/{time} Blue Jay 2.jpg",
    ]
    assert not list((tmp_path / day).glob("*Blue Jay 2.json"))


async def test_a_failed_download_is_retried_on_later_polls(
    hass, tmp_path, aioclient_mock, hass_storage
):
    """An incomplete save is retried, without firing the event again."""
    aioclient_mock.get(_PHOTO, status=503)
    coordinator = _coordinator(hass, tmp_path)
    analysis = _analysis([_image()], ["American Robin"])
    coordinator.client.identify_postcard = AsyncMock(return_value=analysis)
    events = []
    hass.bus.async_listen("birdbuddy_new_postcard", events.append)

    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc1"})
    await coordinator._process_feed([postcard])
    await hass.async_block_till_done()
    assert len(events) == 1
    key = f"{DOMAIN}.{coordinator.config_entry.entry_id}.archive_retry"
    assert list(hass_storage[key]["data"]["pending"]) == ["pc1"]

    aioclient_mock.clear_requests()
    aioclient_mock.get(_PHOTO, content=b"a", headers={"Content-Type": "image/jpeg"})
    await coordinator._async_retry_archive()
    await hass.async_block_till_done()

    coordinator.client.identify_postcard.assert_awaited_with("pc1")
    assert hass_storage[key]["data"]["pending"] == {}
    assert len(events) == 1
    day, time = _local_stem()
    assert (tmp_path / f"{day}/{time} American Robin.jpg").read_bytes() == b"a"


async def test_an_old_retry_is_given_up(hass, tmp_path, hass_storage):
    """A postcard still failing after a week is dropped from the list."""
    coordinator = _coordinator(hass, tmp_path)
    key = f"{DOMAIN}.{coordinator.config_entry.entry_id}.archive_retry"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {"pending": {"old": "2020-01-01T00:00:00+00:00"}},
    }
    coordinator.client.identify_postcard = AsyncMock()

    await coordinator._async_retry_archive()

    coordinator.client.identify_postcard.assert_not_awaited()
    assert hass_storage[key]["data"]["pending"] == {}


async def test_a_postcard_that_fails_to_identify_is_retried(
    hass, tmp_path, hass_storage
):
    """A rejected identify call puts the postcard on the retry list."""
    coordinator = _coordinator(hass, tmp_path)
    coordinator.client.identify_postcard = AsyncMock(side_effect=GraphqlError({}))

    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "pc9"})
    await coordinator._process_feed([postcard])

    key = f"{DOMAIN}.{coordinator.config_entry.entry_id}.archive_retry"
    assert list(hass_storage[key]["data"]["pending"]) == ["pc9"]


async def test_a_failed_index_write_is_retried(hass, tmp_path, aioclient_mock):
    """Unsaved index entries are written on the next save, not lost."""
    other = f"https://example.invalid/d.jpg?{_FUTURE}"
    aioclient_mock.get(_PHOTO, content=b"a", headers={"Content-Type": "image/jpeg"})
    aioclient_mock.get(other, content=b"b", headers={"Content-Type": "image/jpeg"})
    archive = PostcardArchive(hass, tmp_path)
    first = _analysis([_image("m1")], ["Robin"])

    msg = "disk full"
    with (
        patch.object(archive, "_write_index", side_effect=OSError(msg)),
        pytest.raises(OSError, match=msg),
    ):
        await archive.async_save_postcard(first)
    assert not await archive.async_is_complete(first)
    assert not (tmp_path / INDEX_FILE).exists()

    collection = Collection({"id": "c1", "species": {"id": "s1", "name": "Jay"}})
    await archive.async_save_collection(collection, [Media(_image("m2", other))])

    index = json.loads((tmp_path / INDEX_FILE).read_text())
    assert {"m1", "m2"} <= set(index)


async def test_an_unreadable_index_is_not_replaced(hass, tmp_path, media_urls):
    """A read error is raised and retried; the old index survives."""
    (tmp_path / INDEX_FILE).write_text(json.dumps({"old": "2026/01/01/x.jpg"}))
    archive = PostcardArchive(hass, tmp_path)
    analysis = _analysis([_image()], ["Robin"])

    msg = "busy"
    with (
        patch.object(archive, "_read_index", side_effect=OSError(msg)),
        pytest.raises(OSError, match=msg),
    ):
        await archive.async_save_postcard(analysis)

    await archive.async_save_postcard(analysis)
    index = json.loads((tmp_path / INDEX_FILE).read_text())
    assert {"old", "m1"} <= set(index)


async def test_a_damaged_index_is_set_aside(hass, tmp_path, media_urls):
    """An index that isn't JSON is kept under a new name, not overwritten."""
    (tmp_path / INDEX_FILE).write_text("{not json")
    archive = PostcardArchive(hass, tmp_path)

    await archive.async_save_postcard(_analysis([_image()], ["Robin"]))

    assert len(list(tmp_path.glob(f"{INDEX_FILE}.bad-*"))) == 1
    assert "m1" in json.loads((tmp_path / INDEX_FILE).read_text())


def _owned(media: dict, species: list[str] | None = None, mystery: bool = False):
    return {
        "node": {
            "id": f"cm-{media['id']}",
            "isMysteryVisitor": mystery,
            "species": [{"id": n, "name": n} for n in species or []],
            "media": media,
        }
    }


def _owned_page(edges: list[dict], cursor: str | None = None) -> dict:
    return {
        "me": {
            "mediasOwned": {
                "edges": edges,
                "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
            }
        }
    }


async def test_gallery_pages_follow_the_cursor():
    """Every gallery page is read, with species and mystery visitors named."""
    client = MagicMock()
    client._make_request = AsyncMock(
        side_effect=[
            _owned_page([_owned(_image("m1"), ["Blue Jay"])], "c1"),
            _owned_page([_owned(_image("m2"), mystery=True), {"node": {}}]),
        ]
    )

    pages = [page async for page in async_gallery_pages(client)]

    assert [[(n, m.id) for n, m in p] for p in pages] == [
        [(["Blue Jay"], "m1")],
        [([MYSTERY_VISITOR], "m2")],
    ]
    first, second = client._make_request.await_args_list
    assert "after" not in first.kwargs["variables"]
    assert second.kwargs["variables"]["after"] == "c1"


async def test_a_gallery_page_without_media_edges_raises():
    """A page that isn't shaped as expected is reported, not skipped."""
    client = MagicMock()
    client._make_request = AsyncMock(return_value={"me": {}})

    with pytest.raises(UnexpectedResponseError):
        [page async for page in async_gallery_pages(client)]


def test_media_from_feed_items():
    """Collected postcards, sightings and mystery visitors carry media."""
    collected = FeedNode(
        {
            "__typename": "FeedItemCollectedPostcard",
            "id": "f1",
            "species": [{"id": "s1", "name": "Northern Cardinal"}],
            "medias": [_image("m1"), _video("v1")],
        }
    )
    sighting = FeedNode(
        {
            "__typename": "FeedItemSpeciesSighting",
            "id": "f2",
            "collection": {"species": {"id": "s2", "name": "Blue Jay"}},
            "media": _image("m2"),
        }
    )
    mystery = FeedNode(
        {
            "__typename": "FeedItemMysteryVisitorNotRecognized",
            "id": "f3",
            "media": _image("m3"),
        }
    )
    postcard = FeedNode({"__typename": "FeedItemNewPostcard", "id": "f4"})

    assert [(n, m.id) for n, m in feed_item_media(collected)] == [
        (["Northern Cardinal"], "m1"),
        (["Northern Cardinal"], "v1"),
    ]
    assert [(n, m.id) for n, m in feed_item_media(sighting)] == [(["Blue Jay"], "m2")]
    assert [(n, m.id) for n, m in feed_item_media(mystery)] == [
        ([MYSTERY_VISITOR], "m3")
    ]
    assert feed_item_media(postcard) == []


async def test_feed_media_reads_every_feed_page():
    """The backfill walks the whole feed, not only the newest page."""
    sighting = {
        "__typename": "FeedItemSpeciesSighting",
        "id": "f2",
        "collection": {"species": {"id": "s2", "name": "Blue Jay"}},
        "media": _image("m2"),
    }
    client = MagicMock()
    client.feed = AsyncMock(
        side_effect=[
            Feed(
                {
                    "edges": [{"node": sighting}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                }
            ),
            Feed({"edges": [], "pageInfo": {"hasNextPage": False}}),
        ]
    )

    items = await async_feed_media(client)

    assert [(n, m.id) for n, m in items] == [(["Blue Jay"], "m2")]
    assert client.feed.await_args_list[1].kwargs["after"] == "c1"


async def test_saves_items_named_by_their_own_species(hass, tmp_path, aioclient_mock):
    """Gallery items are filed by day and named after their species."""
    other = f"https://example.invalid/f.jpg?{_FUTURE}"
    aioclient_mock.get(_PHOTO, content=b"a", headers={"Content-Type": "image/jpeg"})
    aioclient_mock.get(other, content=b"b", headers={"Content-Type": "image/jpeg"})
    archive = PostcardArchive(hass, tmp_path)

    written = await archive.async_save_items(
        [
            (["Blue Jay"], Media(_image("m1"))),
            ([], Media(_image("m2", other, "2026-03-01T15:00:00.000Z"))),
        ]
    )

    march_day, march_time = _local_stem("2026-03-01T15:00:00.000Z")
    day, time = _local_stem()
    assert written == [
        f"{march_day}/{march_time} {UNKNOWN_VISITOR}.jpg",
        f"{day}/{time} Blue Jay.jpg",
    ]
    assert await archive.async_known(["m1", "m2"])
    assert not await archive.async_known(["m1", "m9"])
    assert await archive.async_save_items([(["Blue Jay"], Media(_image("m1")))]) == []


async def test_opened_postcards_in_the_feed_are_archived(hass, tmp_path, media_urls):
    """A postcard opened in the app is saved from its feed item."""
    coordinator = _coordinator(hass, tmp_path)
    collected = FeedNode(
        {
            "__typename": "FeedItemCollectedPostcard",
            "id": "f1",
            "species": [{"id": "s1", "name": "Northern Cardinal"}],
            "medias": [_image()],
        }
    )

    await coordinator._process_feed([collected])

    day, time = _local_stem()
    assert (tmp_path / f"{day}/{time} Northern Cardinal.jpg").read_bytes() == b"jpeg"


async def test_a_quick_gallery_sync_stops_at_a_saved_page(hass, tmp_path):
    """A quick sync stops at the first fully saved page; a full one doesn't."""
    coordinator = _coordinator(hass, tmp_path)
    archive = coordinator.archive
    assert archive is not None
    pages = [[(["Blue Jay"], Media(_image("m1")))], [(["Robin"], Media(_image("m2")))]]

    async def gallery(_client):
        for page in pages:
            yield page

    with (
        patch("custom_components.birdbuddy.coordinator.async_gallery_pages", gallery),
        patch.object(archive, "async_known", AsyncMock(return_value=True)),
        patch.object(archive, "async_save_items", AsyncMock(return_value=[])) as save,
    ):
        assert await coordinator.async_sync_gallery() == 0
        assert save.await_count == 1
        await coordinator.async_sync_gallery(full=True)
        assert save.await_count == 3


async def test_a_failed_gallery_check_waits_for_the_next_due_time(hass, tmp_path):
    """A failing gallery check is logged and not retried every poll."""
    coordinator = _coordinator(hass, tmp_path)
    failing = AsyncMock(side_effect=GraphqlError({}))

    with patch.object(coordinator, "async_sync_gallery", failing):
        await coordinator._async_sync_gallery_if_due()
        await coordinator._async_sync_gallery_if_due()
    assert failing.await_count == 1

    coordinator._gallery_synced = dt_util.utcnow() - GALLERY_SYNC_EVERY
    with patch.object(coordinator, "async_sync_gallery", failing):
        await coordinator._async_sync_gallery_if_due()
    assert failing.await_count == 2
