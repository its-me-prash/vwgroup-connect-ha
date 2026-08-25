# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""EU Data Act portal — vehicle-position field map (issue #923).

Grounding (2026-08-24, @naked-head): the portal publishes **two** dictionaries.
The **Continuous** feed (what our auto-kickoff creates) carries *no* coordinates —
only a GPS ``trueness`` quality flag. The vehicle's actual position lives only in
the one-time **Historical export**, in a contiguous ``0x01010200 01``-``08`` block,
plus a JSON ``history.[*].lat`` / ``.lon`` pair. Verified against the official
V6.0 PDFs (2026-07-24) and cross-checked against our own diagnostics archive (no
captured historical export yet — the continuous feed confirms coordinates are
absent there).

This module is the *field map* only. The parser that reads a real historical
export is intentionally NOT built yet: we have no response sample, so the exact
envelope shape (how the export wraps these values) is unknown. Building it blind
would risk a wrong read — it waits on a schema-only sample on #923. Wiring must be
an opt-in manual "refresh parked location", never an automatic kickoff, until it's
settled whether an in-flight historical request suspends the continuous feed.
"""
from __future__ import annotations

from typing import Final

# The vehicle-position block from the Historical dictionary. UUID -> our role.
# Coordinates first, then the quality/staleness fields that let us label a fix
# honestly as a daily "last parked location" rather than dress it up as live GPS.
HISTORICAL_POSITION_FIELDS: Final[dict[str, str]] = {
    "784c4692-9041-3cf7-9446-09efedd1d708": "latitude",   # 0x0101020002, degrees
    "787807ad-3246-3f82-82d3-78baa334c574": "longitude",  # 0x0101020003, degrees
    "eb432cf5-cee5-38b7-8927-7c42f2170c0c": "altitude",   # 0x0101020001, m
    "50cbd333-1311-30b3-a570-5bde68a4480a": "precision",  # 0x0101020004, m
    "74453e67-da21-39aa-b3e3-885cd9d3219c": "trueness",   # 0x0101020005
    "09a5f0e7-4023-3c57-8225-eac108ed02b7": "heading",    # 0x0101020006, degrees
    "d5836d0d-1940-3da5-813b-20919db55785": "moving",     # 0x0101020007, boolean
    "932274c4-92cd-31ed-afd2-403d7ae7c809": "outdated",   # 0x0101020008, boolean
}

# The JSON-path variant carried under a ``history[]`` array of past positions.
HISTORY_PATH_POSITION_FIELDS: Final[dict[str, str]] = {
    "dc9f9fc6-1ac4-35fd-bdb9-a737316745b9": "latitude",   # history.[*].lat
    "0b2da7cb-60ed-3f91-b783-ff3ece36a753": "longitude",  # history.[*].lon
}

# FALSE FRIENDS — coordinates that are NOT the vehicle's position and must never be
# read as it. The Historical dictionary is full of them: public-charging / wallbox /
# fleet charging-record coordinates (where a charge happened) and navigation
# ``destination-memory`` / ``active-guidance`` coordinates (saved destinations, not
# the car). A position parser must key on the UUIDs above, not on a name match for
# "latitude"/"longitude", precisely because these exist:
POSITION_FALSE_FRIEND_NAME_MARKERS: Final[tuple[str, ...]] = (
    "charging_record",
    "charging_records",
    "wallbox",
    "flexpole",
    "ocpi",
    "fleet_public_charging",
    "destination-memory",
    "active-guidance",
    "locationtokens",
    "geolocations",
    "avoidedchargingstations",
)


def is_position_false_friend(data_point_name: str) -> bool:
    """True if a coordinate-looking field is a charging/destination coordinate,
    not the vehicle's own position. Used to keep the position parser honest."""
    low = (data_point_name or "").lower()
    return any(m in low for m in POSITION_FALSE_FRIEND_NAME_MARKERS)
