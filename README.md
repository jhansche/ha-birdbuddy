# Bird Buddy Home Assistant Integration

Custom integration for [Bird Buddy](https://mybirdbuddy.com/).

This component makes use of the [pybirdbuddy](https://github.com/jhansche/pybirdbuddy) library
for API calls, also available on [PyPI](https://pypi.org/project/pybirdbuddy/).

**Prior To Installation**

You will need your Bird Buddy `email` and `password`.

> **Note**
>
> If your BirdBuddy account was created using SSO (Google, Facebook, etc), those methods will
> not work currently. To work around that, you can sign up a new account using email and password,
> and then invite that new account as a member of your main/owner account. Be aware that certain
> information or functionality may not be available to member accounts (for example, "off-grid"
> settings and firmware version).
>
> Alternatively, you may reset the Bird Buddy unit and re-pair it with a new account that was created
> with a password. See [Bird Buddy support](https://support.mybirdbuddy.com/hc/en-us/articles/9764938883089-Connecting-Bird-Buddy-to-a-different-Wi-Fi-network)
> for more information.

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

| Entity           | Entity Type     | Notes                                                                                                                                           |
|------------------|-----------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `Battery`        | `sensor`        | Current Bird Buddy battery percentage                                                                                                           |
| `Charging`       | `binary_sensor` | Whether the Bird Buddy is currently charging                                                                                                    |
| `Off-Grid`       | `switch`        | Present and toggle Off-Grid status (owners only)                                                                                                |
| `Recent Visitor` | `sensor`        | State represents the most recent visitor's bird species name, and the `entity_picture` points to the cover media of that recent postcard visit. |
| `State`          | `sensor`        | Current state (ready, offline, etc)                                                                                                             |
| `Signal`         | `sensor`        | Current wifi signal (RSSI)                                                                                                                      |
| `Update`         | `update`        | Show and install Firmware updates (owners only)                                                                                                 |

Some entities are disabled or hidden by default, if they represent an advanced use case (for example,
the "Signal" and "Recent Visitor" entities). There are also some entities that are disabled by
default because the support is not yet enabled by the Bird Buddy API (for example, the Temperature
and Food Level sensors are not yet enabled by Bird Buddy; and the "Frequency" setting does not appear
to be have any effect currently).

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
This is the same effect as opening and saving the postcard in the Bird Buddy app.

> **Note**
> 
> This service _is not_ intended to be invoked manually, but should be used in conjunction with the
> [`birdbuddy_new_postcard_sighting`](#birdbuddy_new_postcard_sighting) event, device trigger, or [Blueprint](#blueprint).
>
> Attempting to call the service manually will likely fail, because the service requires the `postcard` and `sighting` data that would be included
> in the event.

| Service attribute data  | Optional | Description                                                                                |
| ----------------------- | -------- | ------------------------------------------------------------------------------------------ |
| `postcard`              | No       | Postcard data from `birdbuddy_new_postcard_sighting` event                                 |
| `sighting`              | No       | Sighting data from `birdbuddy_new_postcard_sighting` event                                 |
| `strategy`              | Yes      | Strategy for resolving the sighting (see strategies below, default: `recognized`)          |
| `best_guess_confidence` | Yes      | Minimum confidence to support `"best_guess"` strategy (default: 10%)                       |
| `share_media`           | Yes      | Whether the saved media will also be shared with the community (default: false)            |

Postcard sighting strategies:

- `recognized` (Default): collect the postcard only if Bird Buddy's AI identified a bird species. Note: the identified species may be incorrect.
  Also note that any sighting not recognized by the Bird Buddy API will be *discarded*.
- `best_guess`: In the "can't decide which bird" sightings, a list of possible species is usually included. This strategy will behave like
  `recognized`, but if the species is not recognized it will select the highest-confidence species automatically (assuming that confidence is
  at least `best_guess_confidence`, defaults to 10%). If none of the suggestions meet the `best_guess_confidence` strategy, the sighting will be
  *discarded*.
- `mystery`: Same behavior as `best_guess`, but if the bird is not recognized and no species meets the confidence threshold, collect the sighting
  as a "Mystery Visitor".

#### Automation example

```yaml
trigger:
  - platform: event
    event_type: birdbuddy_new_postcard_sighting
  # OR a device trigger:
  - platform: device
    domain: birdbuddy
    type: new_postcard
    # $ids...
action:
  - service: birdbuddy.collect_postcard
    data:
      strategy: best_guess
      # pass-through these 2 event fields as they are
      postcard: "{{ trigger.event.data.postcard }}"
      sighting: "{{ trigger.event.data.sighting }}"
```

#### Blueprint

To simplify the combination of the trigger and the action of collecting the postcard, you can import a predefined
[Blueprint](https://www.home-assistant.io/docs/automation/using_blueprints/).

To add the Blueprint, use the button below:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjhansche%2Fha-birdbuddy%2Fblob%2Fmain%2Fcustom_components%2Fbirdbuddy%2Fblueprints%2Fcollect_postcard.yaml)

or go to **Settings** > **Automations & Scenes** > **Blueprints**, click the **Import Blueprint** button, and enter this URL:

```
https://github.com/jhansche/ha-birdbuddy/blob/main/custom_components/birdbuddy/blueprints/collect_postcard.yaml
```

After the Blueprint has been imported, you still need to
[create an automation from that Blueprint](https://www.home-assistant.io/docs/automation/using_blueprints/#blueprint-automations). Also note that
if we update the Blueprint here, your imported Blueprint will not automatically receive the update, and you may need to re-import it to get the update.
