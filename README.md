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

<!-- TODO: add to HACS -->

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

| Entity    | Entity Type | Notes                                 |
|-----------|-------------|---------------------------------------|
| `Battery` | `Sensor`    | Current Bird Buddy battery percentage |

More entities may be added in the future.
