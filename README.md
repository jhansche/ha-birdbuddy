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

1. Open HACS Settings and add this repository (https://github.com/jhansche/ha-birdbuddy/)
   as a Custom Repository (use **Integration** as the category).
2. The `Bird Buddy` page should automatically load (or find it in the HACS Store)
3. Click `Install`
4. Continue to [Setup](README.md#Setup)

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

| Entity     | Entity Type     | Notes                                        |
|------------|-----------------|----------------------------------------------|
| `Battery`  | `sensor`        | Current Bird Buddy battery percentage        |
| `Charging` | `binary_sensor` | Whether the Bird Buddy is currently charging |
| `State`    | `sensor`        | Current state (ready, offline, etc)          |
| `Signal`   | `sensor`        | Current wifi signal (RSSI)                   |

More entities may be added in the future.

# Media

Bird species and sightings that have _already been collected_ from postcards can be viewed in the
Home Assistant Media Browser. To collect a postcard you will need to use the mobile app to open the
postcards as they arrive. Only opened postcards can be viewed in the Media Browser (same as the
Collections tab in the Bird Buddy app).

<!-- # Services -->
<!-- # Events -->
