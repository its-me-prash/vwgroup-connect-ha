# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2078 — one unknown container asked five Audi owners to file the same report.

``charging.chargingBidirectionalSettings`` arrives on the brand API's
``selectivestatus`` read. Nothing reads it, so the Vehicle Data Scout raised its
repair on every poll — and #2078, #2081, #2088 and #2095 are four hand-filed
copies of one finding within two days, all on 5.3.0.

The report cannot move the mapping forward, however often it is filed. The
Scout does not recurse into an unknown container and samples a dict by its
SHAPE only, so every copy says ``{1 keys}`` and none says which key. The inner
key is not lost: the diagnostics download of the integration ENTRY carries the
raw ``selectivestatus`` section with field names intact (the download of a
single car drops that account-scoped section). That is the route the evidence
comes by, and the one the maintainer asked for on #2078.

So the REPAIR is skipped for this leaf and nothing else changes. The finding is
still detected, still in ``unexpected_findings`` (diagnostics and the observer
sensor); only the per-poll card that asks for one more identical report stops.

Deliberately NOT done, and pinned below as the reason:

* listing the container in ``EXPECTED_KEYS`` would make the Scout descend and
  report the inner key as part of the PATH — and paths are published unmasked,
  so an identifier-shaped key would go out verbatim;
* the meaning is not guessed. The name suggests bidirectional-charging
  settings; a name is not evidence.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._reporter_pipeline import (
    _is_scout_repair_skipped,
)
from custom_components.vag_connect.cariad._unexpected_keys import (
    UnexpectedField,
    detect_unexpected,
    mask_value,
)
from custom_components.vag_connect.diagnostics import _scrub_raw

_PATH = "charging.chargingBidirectionalSettings"


def _f(path: str, sample: str = "{1 keys}") -> UnexpectedField:
    return UnexpectedField(
        path=path, sample_masked=sample,
        endpoint="selectivestatus", first_seen_at="2026-11-11T13:47:31Z",
    )


def test_the_container_no_longer_raises_the_repair() -> None:
    """The reported nuisance: one card per poll for a report that cannot help."""
    assert _is_scout_repair_skipped(_f(_PATH))


def test_the_skip_is_keyed_to_this_leaf_only() -> None:
    """A different unknown container next to it must still surface."""
    assert not _is_scout_repair_skipped(_f("charging.chargingFooSettings"))
    assert not _is_scout_repair_skipped(_f("charging.chargingBidirectionalSettingsV2"))


def test_the_finding_is_still_detected() -> None:
    """Repair suppression is not data suppression.

    The Scout must go on recording the field — diagnostics and the observer
    sensor read ``unexpected_findings`` — whatever sits inside the container.
    """
    payload = {"charging": {"chargingBidirectionalSettings": {"value": {}}}}
    paths = [f.path for f in detect_unexpected("audi", "selectivestatus", payload)]
    assert paths.count(_PATH) == 1


def test_a_scout_sample_never_carries_the_inner_key() -> None:
    """Why re-filing cannot unlock the mapping: the sample is the shape, not the key."""
    assert mask_value({"value": {"mode": "off"}}) == "{1 keys}"
    assert mask_value({"anything_else": 1}) == "{1 keys}"


def test_the_diagnostics_download_does_carry_the_inner_key() -> None:
    """The evidence route this skip relies on: field names survive the scrub."""
    raw = {"charging": {"chargingBidirectionalSettings": {"value": {"mode": "off"}}}}
    scrubbed = _scrub_raw(raw)
    inner = scrubbed["charging"]["chargingBidirectionalSettings"]
    assert list(inner) == ["value"], "the inner key name must reach the download"

    # ... and an identifier-shaped key does not go out in the clear there.
    vin = "WAUZZZF40NA012345"
    masked = _scrub_raw({"charging": {"chargingBidirectionalSettings": {vin: 1}}})
    keys = list(masked["charging"]["chargingBidirectionalSettings"])
    assert vin not in keys
    assert keys == ["***012345"]
