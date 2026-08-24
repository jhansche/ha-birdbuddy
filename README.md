# Bird Buddy Home Assistant Integration

[![Build Status][build-status-shield]][build-status]
![Maintenance][maintenance-shield]
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

Custom integration for [Bird Buddy][birdbuddy].

This component makes use of the [pybirdbuddy] library for API calls, also
available on [PyPI][pypi].

## Requirements

- Home Assistant 2026.7.1 or newer (Python 3.14).
- A Bird Buddy account. You will need its `email` and `password`.

> **Note**
>
> If your Bird Buddy account was created using SSO (Google, Facebook,
> etc), those methods will not work currently. To work around that, you
> can sign up a new account using email and password, and then invite
> that new account as a member of your main/owner account. Be aware that
> certain information or functionality may not be available to member
> accounts (for example, "off-grid" settings and firmware version).
>
> Alternatively, you may reset the Bird Buddy unit and re-pair it with a
> new account that was created with a password. See
> [Bird Buddy support][reset-wifi] for more information.

## Installation

### With HACS

[![HACS Custom][hacs-badge]][hacs]

1. Open HACS Settings and add this repository
   (<https://github.com/jhansche/ha-birdbuddy/>) as a Custom Repository
   (use **Integration** as the category).
2. The `Bird Buddy` page should automatically load (or find it in the
   HACS Store)
3. Click `Install`
4. Continue to [Setup](#setup)

Alternatively, click on the button below to add the repository:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][hacs-repo-badge]][hacs-repo]

### Manual

Copy the `birdbuddy` directory from `custom_components` in this
repository, and place inside your Home Assistant Core installation's
`custom_components` directory.

## Setup

1. Install this integration.
2. Navigate to the Home Assistant Integrations page
   (Settings --> Devices & Services)
3. Click the `+ Add Integration` button in the bottom-right
4. Search for `Bird Buddy`

Alternatively, click on the button below to add the integration:

[![Open your Home Assistant instance and start setting up a new integration.][config-flow-badge]][config-flow]

## Devices

A device is created for each Bird Buddy feeder associated with the
account. See below for the entities available.

## Entities

| Entity           | Entity Type     | Notes                                                                                                                              |
| ---------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `Audio`          | `switch`        | Whether recorded visitor videos will include audio.                                                                                |
| `Battery`        | `sensor`        | Current Bird Buddy battery percentage                                                                                              |
| `Charging`       | `binary_sensor` | Whether the Bird Buddy is currently charging                                                                                       |
| `Off-Grid`       | `switch`        | Present and toggle Off-Grid status (owners only)                                                                                   |
| `Power Profile`  | `select`        | Choose between the Power Profile settings the feeder reports.                                                                      |
| `Recent Visitor` | `sensor`        | State represents the most recent visitor's bird species name, and the `entity_picture` points to the first image on that postcard. |
| `State`          | `sensor`        | Current state (ready, offline, etc)                                                                                                |
| `Signal`         | `sensor`        | Current wifi signal (RSSI)                                                                                                         |
| `Update`         | `update`        | Show and install Firmware updates (owners only)                                                                                    |

Some entities are disabled or hidden by default, if they represent an
advanced use case (for example, the "Signal" and "Recent Visitor"
entities). There are also some entities that are disabled by default
because the support is not yet enabled by the Bird Buddy API (for
example, the Temperature and Food Level sensors are not yet enabled by
Bird Buddy).

More entities may be added in the future.

## Media

Bird species and sightings that have _already been collected_ from
postcards can be viewed in the Home Assistant Media Browser. To collect a
postcard you will need to use the mobile app to open the postcards as
they arrive. Only opened postcards can be viewed in the Media Browser
(same as the Collections tab in the Bird Buddy app).

## Events

### `birdbuddy_new_postcard`

This event is fired when a new postcard is detected in the feed and Bird
Buddy has identified its species.

| Field         | Description                                                                                        |
| ------------- | -------------------------------------------------------------------------------------------------- |
| `postcard_id` | Id of the postcard. Pass this to the `birdbuddy.collect_postcard` service to collect the postcard. |
| `feeder_id`   | Id of the feeder that captured the postcard, or `null`. Can be used to filter/target automations.  |
| `species`     | List of recognized species (each an `{ "id", "name" }` object). Empty when nothing was recognized. |
| `media`       | The first image on the postcard (`{ "contentUrl", "thumbnailUrl", ... }`), or `null`.              |

`media.contentUrl` and `media.thumbnailUrl` are time-sensitive URLs that
can be used to download the postcard image. The event carries the media
object as Bird Buddy returns it, so these keys keep the API's spelling.
Every media item has a `thumbnailUrl`; `contentUrl` accompanies the ones
that carry full-size content.

This event can also be handled with the "A new postcard is ready" Device
Trigger, which automatically filters to the matching feeder:

```yaml
triggers:
  - trigger: device
    domain: birdbuddy
    type: new_postcard
    device_id: <ha device id>
```

## Services

### `birdbuddy.collect_postcard`

Collects a postcard into your Collections, adding its media to the
associated species and making them available in the
[Media Browser](#media). This is the same effect as opening and saving
the postcard in the Bird Buddy app.

> **Note**
>
> This service is meant to be used with the
> [`birdbuddy_new_postcard`](#birdbuddy_new_postcard) event, Device
> Trigger, or [Blueprint](#blueprint), which supply the `postcard_id`.

| Service data  | Optional | Description                                                                                 |
| ------------- | -------- | ------------------------------------------------------------------------------------------- |
| `postcard_id` | No       | Id of the postcard to collect, from the `birdbuddy_new_postcard` event.                     |
| `feeder_id`   | Yes      | Feeder id, used to pick the account when more than one Bird Buddy account is configured.    |
| `share`       | Yes      | Whether the collected media is also shared with the Bird Buddy community (default: false).  |

Bird Buddy now identifies species server-side, so the integration no
longer chooses a species client-side (and there is no longer a `strategy`
or `best_guess_confidence` option): the postcard is collected exactly as
the Bird Buddy app would collect it.

#### Automation example

```yaml
triggers:
  - trigger: event
    event_type: birdbuddy_new_postcard
  # OR a device trigger:
  - trigger: device
    domain: birdbuddy
    type: new_postcard
    # $ids...
actions:
  - action: birdbuddy.collect_postcard
    data:
      postcard_id: "{{ trigger.event.data.postcard_id }}"
      feeder_id: "{{ trigger.event.data.feeder_id }}"
      share: false
```

#### Blueprint

To simplify the combination of the trigger and the action of collecting
the postcard, you can import a predefined [Blueprint][using-blueprints].

To add the Blueprint, use the button below:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.][blueprint-import-badge]][blueprint-import]

or go to **Settings** > **Automations & Scenes** > **Blueprints**, click
the **Import Blueprint** button, and enter this URL:

```text
https://github.com/jhansche/ha-birdbuddy/blob/main/custom_components/birdbuddy/blueprints/collect_postcard.yaml
```

After the Blueprint has been imported, you still need to
[create an automation from that Blueprint][blueprint-automations].
Also note that if we update the Blueprint here, your imported Blueprint
will not automatically receive the update, and you may need to re-import
it to get the update.

## Breaking changes

Adopting [pybirdbuddy] v0.1.0 moves the integration to Bird Buddy's
server-side `postcardCollect` flow. Entities keep their IDs and history,
and automations built on the "A new postcard is ready" Device Trigger carry
over untouched, since the trigger resolves the event internally. Automations
that reference the event or the service directly need updating:

- `birdbuddy_new_postcard_sighting` — renamed to
  [`birdbuddy_new_postcard`](#birdbuddy_new_postcard). The payload carries
  `postcard_id`, `feeder_id`, `species`, and `media` in place of the
  `postcard` and `sighting` report objects.
- `birdbuddy.collect_postcard` — takes `postcard_id`, plus optional
  `feeder_id` and `share`, in place of the `postcard` and `sighting`
  objects. Bird Buddy identifies species server-side, so the schema now
  rejects `strategy` and `best_guess_confidence`; `share_media` becomes
  `share`.
- The bundled [Blueprint](#blueprint) — re-import it and re-create any
  automation built from it, since it now uses the renamed event and the new
  service inputs.

Re-importing the Blueprint covers everything if you use it without
customizing the payload.

Home Assistant raises a Repairs notice while an automation or script still
triggers on `birdbuddy_new_postcard_sighting`. Editing that trigger clears
the notice on a following update poll.

## Development

```bash
make deps    # create venv (Python 3.14.4) + install dev/test tooling
make check   # ruff + ruff format --check + markdownlint + pyright + pytest
make format  # auto-fix ruff issues
```

The pinned `pytest-homeassistant-custom-component` selects the exact Home
Assistant version tested against (see `requirements-dev.txt`).

## License

Released under the [MIT No Attribution License](LICENSE).

[birdbuddy]: https://mybirdbuddy.com/
[blueprint-automations]: https://www.home-assistant.io/docs/automation/using_blueprints/#blueprint-automations
[blueprint-import]: https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjhansche%2Fha-birdbuddy%2Fblob%2Fmain%2Fcustom_components%2Fbirdbuddy%2Fblueprints%2Fcollect_postcard.yaml
[blueprint-import-badge]: https://my.home-assistant.io/badges/blueprint_import.svg
[build-status]: https://github.com/jhansche/ha-birdbuddy/actions/workflows/pythonpackage.yaml?query=branch%3Amain
[build-status-shield]: https://img.shields.io/github/actions/workflow/status/jhansche/ha-birdbuddy/pythonpackage.yaml?branch=main&style=for-the-badge
[config-flow]: https://my.home-assistant.io/redirect/config_flow_start/?domain=birdbuddy
[config-flow-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[hacs]: https://github.com/hacs/integration
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-repo]: https://my.home-assistant.io/redirect/hacs_repository/?category=Integration&repository=ha-birdbuddy&owner=jhansche
[hacs-repo-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[license-shield]: https://img.shields.io/github/license/jhansche/ha-birdbuddy.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026?style=for-the-badge
[pybirdbuddy]: https://github.com/jhansche/pybirdbuddy
[pypi]: https://pypi.org/project/pybirdbuddy/
[releases]: https://github.com/jhansche/ha-birdbuddy/releases
[releases-shield]: https://img.shields.io/github/v/release/jhansche/ha-birdbuddy.svg?style=for-the-badge
[reset-wifi]: https://support.mybirdbuddy.com/hc/en-us/articles/9764938883089-Connecting-Bird-Buddy-to-a-different-Wi-Fi-network
[using-blueprints]: https://www.home-assistant.io/docs/automation/using_blueprints/
