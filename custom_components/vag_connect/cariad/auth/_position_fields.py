# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""EU Data Act portal — vehicle-position field map (issue #923).

**What the dictionary documents, and what cars actually send, are two different
statements. Both are true; neither answers the other.** An earlier version of
this docstring collapsed them and said the continuous feed carries no
coordinates full stop, which is wrong about real cars and was already
contradicted inside this package.

**The dictionary (measured 2026-11-03, both copies).** ``eu_data_dictionary.json``
beside this file — 7990 entries, 6618 distinct field names, ``_meta`` version
V6.0, a curated V5.0 Continuous base merged with the full V6.0 Continuous +
Historical dictionary — documents the vehicle position in its own cluster,
``Vehicle Location (Historical Export)``, with exactly ten entries: the eight
``HISTORICAL_POSITION_FIELDS`` plus the two ``HISTORY_PATH_POSITION_FIELDS``
below, confirmed one-for-one. The **continuous** side documents none: its
``Vehicle Location Tracking`` cluster holds exactly three members — ``mileage``,
``outside_temperature`` and a GPS ``trueness`` quality flag — and every one of
the 110 coordinate-named entries in the whole file sits in a Historical-Export
cluster. Independently reproduced on a competing reader's 1141-entry copy of the
same catalogue: same three-member cluster, same absence.

**Real cars (issue #1378).** MEB portal cars — Škoda Elroq and others — ship the
position in the **continuous** feed anyway, under a leaf named ``persLocation``
whose value is a bracketed decimal pair as a *string* (``"[<lat>, <lon>]"``, six
decimals), and which appears in **neither** copy of the dictionary: an
undocumented field. That path is live and is read by
``_parse_pers_location`` in ``_eu_data_act.py``; it validates the pair, rejects
the ``0,0`` null-island and a charging/destination coordinate, and stamps the pin
with its own capture time. **If you are looking for where portal position comes
from today, that is the answer — not this module.**

So the honest split: the dictionary is authoritative about what VW *documents*
and says the continuous feed has no position; it is silent about undocumented
leaves, and one of those is how the position actually arrives on MEB cars.

This module remains the *field map* for the Historical export only, and nothing
reads it yet. The parser is intentionally NOT built: we have no response sample
of the **historical** envelope (how that export wraps these values), so building
it blind would risk a wrong read. It waits on a schema-only sample on #923, and
that wait is specific: the continuous envelope *was* sampled there in August —
a flat JSON array of ``key`` / ``dataFieldName`` / ``value`` rows — but no
historical package has ever arrived to be sampled, for the reason below.

**Why the kickoff stays manual — reason corrected 2026-11-03.** An earlier
wording here hung the opt-in on an open question: whether an in-flight
historical request suspends the continuous feed. That question was settled on
#923 in August and the answer is **no**. A reporter measured the feed running
unchanged straight through a pending one-time request, then ran a control night
with nothing pending and reproduced the same ~22:00–05:00 half-rate cadence,
which identifies the overnight halving as the portal's own diurnal rhythm
rather than anything our polling provokes. Citing a settled question as the
blocker made the restriction look removable once it was answered. It is not,
because the real constraint was found in the same measurements: a one-time
request can **vanish** 24–36 h after submission — no package, no mail, no
error, no failure state, the panel simply resets — while the recurring request
for the same VIN keeps running normally. Nothing distinguishes "still
processing" from "silently dropped", so an automatic kickoff can fire into a
void and wait forever. Anything built on this path therefore needs its own
client-side deadline and an explicit "no response — resubmit" state. Hence:
opt-in manual "refresh parked location", never an automatic kickoff — for that
reason, not the retracted one.

Two neighbouring findings from those same measurements, recorded so they are
not re-litigated. First, the portal's own format description ("a zip file that
includes subfolders for each data cluster, containing machine-readable data
including meta information") does **not** match what it delivers for the
continuous package — one flat JSON, no subfolders, no meta file — and it is the
*same* sentence for the historical request, so it cannot be used to predict
that envelope either. Second, the "every 15 minutes" badge drifts (~16.6 min
across 30 buffered files), which is why staleness keys off each reading's own
``car_captured_time`` and never an assumed cadence.
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
# "latitude"/"longitude", precisely because these exist.
#
# Counted 2026-11-03 over all 110 coordinate-named entries in the dictionary, so
# the list is grounded rather than guessed:
#   48  alert positions — GEOFEN / SPEEDA / VALETA ``occurrencePosition``
#   24  navigation — destination-memory / active-guidance
#   16  charging / wallbox telemetry — wallbox, flexpole, ocpi, csm, msp_, fleet
#    8  RPT / RBC
#   14  other
#
# The alert family was the largest and was NOT covered until that count: a
# geofence, speed- or valet-alert ``occurrencePosition`` IS the car, which makes
# it the most tempting of all to a name-matching reader — and still wrong, because
# it is where an event fired, not where the car is parked now.
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
    # alert positions: the car's location when an alert fired, not its position
    "geofencingalerts",
    "speedalertalerts",
    "valetalertalerts",
    "occurrenceposition",
)


def is_position_false_friend(data_point_name: str) -> bool:
    """True if a coordinate-looking field is a charging/destination coordinate,
    not the vehicle's own position. Used to keep the position parser honest."""
    low = (data_point_name or "").lower()
    return any(m in low for m in POSITION_FALSE_FRIEND_NAME_MARKERS)
