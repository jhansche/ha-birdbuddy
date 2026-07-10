"""Keep every recorded Home Assistant version pointing at the same release.

Four places in this repo name an HA version, and each one is written by hand:

  - requirements-dev.txt pins phacc, which installs one exact HA release. The
    phacc release number (0.13.345) reveals nothing about which release that
    is, so a comment beside the pin records the pairing.
  - hacs.json declares the minimum HA version users may install on. The only
    release this repo verifies is the one phacc installs, so that is the
    highest floor it can honestly claim, and the two move together.
  - README.md states the same floor for people reading the docs.
  - homeassistant.const holds the version phacc actually installed, which is
    the ground truth the other three describe.

Comments, manifests, and docs rot silently. A phacc bump that leaves any of
the others behind would have the repo claiming to test against, or require, a
release it stopped installing, and nothing else in the toolchain notices. So
this test reads the hand-written values back and compares them against the
installed version, failing a partial bump here instead of misleading whoever
reads those files next.
"""

import json
from pathlib import Path
import re

from homeassistant.const import MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION

# Parse these files as source text, since the comment under test lives only in
# requirements-dev.txt and never reaches the installed package metadata.
REPO_ROOT = Path(__file__).parent.parent
REQUIREMENTS = REPO_ROOT / "requirements-dev.txt"
HACS_MANIFEST = REPO_ROOT / "hacs.json"
README = REPO_ROOT / "README.md"

# The human-maintained record, which looks like:
#   # phacc 0.13.345 tests against Home Assistant 2026.7.1
MAPPING = re.compile(
    r"^# phacc (?P<phacc>\S+) tests against Home Assistant (?P<ha>\S+)$",
    re.MULTILINE,
)

# The pin a human or dependabot would edit, which looks like:
#   pytest-homeassistant-custom-component == 0.13.345
PIN = re.compile(
    r"^pytest-homeassistant-custom-component\s*==\s*(?P<phacc>\S+)$",
    re.MULTILINE,
)

# The floor quoted to users, which looks like:
#   - Home Assistant 2026.7.1 or newer (Python 3.14).
README_FLOOR = re.compile(
    r"^- Home Assistant (?P<ha>\S+) or newer",
    re.MULTILINE,
)


def test_recorded_ha_versions_match_the_installed_release():
    """Fail while the comment, hacs.json, and installed HA disagree."""
    installed = f"{MAJOR_VERSION}.{MINOR_VERSION}.{PATCH_VERSION}"
    text = REQUIREMENTS.read_text()

    mapping = MAPPING.search(text)
    assert mapping, "requirements-dev.txt lost its phacc/HA mapping comment"
    pin = PIN.search(text)
    assert pin, "requirements-dev.txt lost its phacc pin"

    # Catches a pin that moved while the comment above it stayed put.
    assert mapping["phacc"] == pin["phacc"], (
        f"mapping names phacc {mapping['phacc']}, pin says {pin['phacc']}"
    )

    # Catches a comment naming an HA version phacc does not install -- whether
    # the comment was skipped entirely or updated to the wrong number.
    assert mapping["ha"] == installed, (
        f"mapping names HA {mapping['ha']}, phacc installed {installed}"
    )

    # Catches a phacc bump that leaves the advertised minimum behind, which
    # would claim support for a release this repo stopped exercising.
    declared = json.loads(HACS_MANIFEST.read_text())["homeassistant"]
    assert declared == installed, (
        f"hacs.json requires HA {declared}, phacc installed {installed}"
    )

    # Catches the docs quoting a floor that disagrees with the manifest.
    readme = README_FLOOR.search(README.read_text())
    assert readme, "README.md lost its Home Assistant requirement line"
    assert readme["ha"] == installed, (
        f"README requires HA {readme['ha']}, phacc installed {installed}"
    )
