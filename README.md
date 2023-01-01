# Bird Buddy Home Assistant Integration

Custom integration for [Bird Buddy](https://mybirdbuddy.com/).

**Prior To Installation**

You will need your Bird Buddy `email` and `password`.

Note: if your BirdBuddy account was created using SSO (Google, Facebook, etc), those methods will
not work currently. To work around that, you can sign up a new account using email and password,
and then invite that new account as a member of your main/owner account. Be aware that certain
information or functionality may not be available to member accounts (for example, "off-grid"
settings and firmware version).

## Installation

### With HACS

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

1. Open HACS Settings and add this repository (https://github.com/jhansche/ha-birdbuddy/)
   as a Custom Repository (use **Integration** as the category).
2. The `Bird Buddy` page should automatically load (or find it in the HACS Store)
3. Click `Install`
4. Continue to [Setup](README.md#Setup)

Alternatively, click on the button below to add the repository:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?category=Integration&repository=ha-birdbuddy&owner=jhansche)

### Manual

Copy the `birdbuddy` directory from `custom_components` in this repository,
and place inside your Home Assistant Core installation's `custom_components` directory.

## Setup

1. Install this integration.
2. Navigate to the Home Assistant Integrations page (Settings --> Devices & Services)
3. Click the `+ Add Integration` button in the bottom-right
4. Search for `Bird Buddy`

Alternatively, click on the button below to add the integration:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=birdbuddy)

# Devices

A device is created for each Bird Buddy feeder associated with the account. See below for the entities available.

# Entities

| Entity     | Entity Type     | Notes                                            |
| ---------- | --------------- | ------------------------------------------------ |
| `Battery`  | `sensor`        | Current Bird Buddy battery percentage            |
| `Charging` | `binary_sensor` | Whether the Bird Buddy is currently charging     |
| `Off-Grid` | `switch`        | Present and toggle Off-Grid status (owners only) |
| `State`    | `sensor`        | Current state (ready, offline, etc)              |
| `Signal`   | `sensor`        | Current wifi signal (RSSI)                       |
| `Update`   | `update`        | Show and install Firmware updates                |

More entities may be added in the future.

# Media

Bird species and sightings that have _already been collected_ from postcards can be viewed in the
Home Assistant Media Browser. To collect a postcard you will need to use the mobile app to open the
postcards as they arrive. Only opened postcards can be viewed in the Media Browser (same as the
Collections tab in the Bird Buddy app).

# Events

### `birdbuddy_new_postcard_sighting`

This event is fired when a new postcard is detected in the feed.

| Field      | Description                                                                                                          |
| ---------- | -------------------------------------------------------------------------------------------------------------------- |
| `postcard` | The `FeedNode` data for the `FeedItemNewPostcard` type.                                                              |
| `sighting` | The `PostcardSighting` data, containing information about the sighting, potential species info, and images captured. |

Some interesting fields from `sighting` include:

- `sighting.medias[].contentUrl`, `.thumbnailUrl` - time-sensitive URLs that can be used to download the associated sighting image(s)
- `sighting.sightingReport.sightings[]` - list of sightings grouped together in the postcard
  - The data here depends on the type of sighting (i.e., `SightingRecognizedBird`, `SightingCantDecideWhichBird`, etc)
  - Possible fields include `.suggestions` if the bird is not recognized, or `.species` for confidently recognized birds
- `sighting.feeder.id` - not generally useful as is, but can be used to filter automations to those matching the specified Feeder.
  This filter is applied automatically with the Device Trigger.

This event data can also be passed through as-is to the [`birdbuddy.collect_postcard`](#birdbuddycollect_postcard) service.

This event can also be added in an automation using the "A new postcard is ready" Device Trigger:

```yaml
trigger:
  - platform: device
    domain: birdbuddy
    type: new_postcard
    device_id: <ha device id>
    feeder_id: <bird buddy feeder id>
```

# Services

### `birdbuddy.collect_postcard`

"Finishes" a postcard sighting by adding the media to the associated species collections, thus making them available in the [Media Browser](#media).

| Service attribute data  | Optional | Description                                                                                |
| ----------------------- | -------- | ------------------------------------------------------------------------------------------ |
| `postcard`              | No       | Postcard data from `birdbuddy_new_postcard_sighting` event                                 |
| `sighting`              | No       | Sighting data from `birdbuddy_new_postcard_sighting` event                                 |
| `strategy`              | Yes      | Strategy for resolving the sighting. One of `"recognized"`, `"best_guess"`, or `"mystery"` |
| `best_guess_confidence` | Yes      | Minimum confidence to support `"best_guess"` strategy                                      |

Postcard sighting strategies:

- `recognized` (Default): collect the postcard only if Bird Buddy's AI identified a bird species. Note: the identified species may be incorrect.
- `best_guess`: In the "can't decide which bird" sightings, a list of possible species is usually included. This strategy will select the
highest-confidence species automatically (assuming that confidence is at least `best_guess_confidence`, defaults to 10%).
<!-- * `mystery`: If the bird is not recognized and no species meets the confidence threshold, collect the sighting as a "Mystery Visitor".
  NOTE: Mystery Visitor is not yet implemented. -->

#### Automation example

```yaml
trigger:
  - platform: event
    event_type: birdbuddy_new_postcard_sighting
  # or device trigger:
  - platform: device
    domain: birdbuddy
    type: new_postcard
    # $ids...
action:
  - service: birdbuddy.collect_postcard
    data_template:
      strategy: best_guess
      # pass-through these 2 event fields as they are
      postcard: "{{ trigger.event.data.postcard }}"
      sighting: "{{ trigger.event.data.sighting }}"
```
