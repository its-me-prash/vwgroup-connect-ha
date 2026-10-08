# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Re-arming from the stored key map must not throw away the typed key.

``arm_supplementary_official`` REPLACES the official channel from whatever it is
handed, and its own docstring calls ``api_key`` "the single manual-fallback key
(applied to any VIN without its own)". Setup has always passed both the typed
key and the per-VIN map; ``_arm_official_from_map`` passed only the map.

So a user who typed a key for one car and then auto-enrolled another lost the
typed one on the next re-arm — and with it that car's read failover and, since
the command fallback landed, its commands. Nothing logged it, because arming
"succeeded".

The second half of this file pins the repair text that announces auto-enrolment,
which claimed the official channel "stays on standby and only reads when your
main connection can't". That stopped being true in v4.6.1 — whose CHANGELOG
heading is "Škoda official API now reads live every cycle, not just on failover"
— so the text was describing the version before it, in thirteen files.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.vag_connect.const import CONF_SKODA_OFFICIAL_API_KEY

_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
_LANGS = ("cs", "da", "de", "en", "es", "fi", "fr", "it", "nb", "nl", "pl", "sv")
_MAP = {"TMBJJ7NE0J0000001": {"key": "msk_auto_enrolled"}}


def _coord(entry_data: dict):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    c._cariad_client = client
    c.entry = MagicMock()
    c.entry.data = entry_data
    return c, client


# ── the typed key survives ──────────────────────────────────────────────────


def test_a_typed_key_is_handed_over_alongside_the_map() -> None:
    coord, client = _coord({CONF_SKODA_OFFICIAL_API_KEY: "msk_typed_by_hand"})

    coord._arm_official_from_map(_MAP)

    client.arm_supplementary_official.assert_called_once()
    kwargs = client.arm_supplementary_official.call_args.kwargs
    assert kwargs["api_key"] == "msk_typed_by_hand"
    assert kwargs["keys_by_vin"] == {"TMBJJ7NE0J0000001": "msk_auto_enrolled"}


def test_no_typed_key_arms_with_an_empty_one_not_a_missing_one() -> None:
    """The parameter is always passed, so the call shape cannot drift back."""
    coord, client = _coord({})

    coord._arm_official_from_map(_MAP)

    kwargs = client.arm_supplementary_official.call_args.kwargs
    assert kwargs["api_key"] == ""
    assert kwargs["keys_by_vin"] == {"TMBJJ7NE0J0000001": "msk_auto_enrolled"}


def test_the_key_is_read_from_entry_data_not_options() -> None:
    """Standing trap in this repository: the options flow writes through to data,
    so ``entry.options`` is always empty and reading it would silently yield ''."""
    coord, client = _coord({CONF_SKODA_OFFICIAL_API_KEY: "msk_in_data"})
    coord.entry.options = {CONF_SKODA_OFFICIAL_API_KEY: "msk_in_options"}

    coord._arm_official_from_map(_MAP)

    assert client.arm_supplementary_official.call_args.kwargs["api_key"] == "msk_in_data"


def test_an_empty_map_still_arms_nothing() -> None:
    """Unchanged behaviour: this method arms FROM the map, so with no per-VIN key
    there is nothing for it to do — setup handles the typed-key-only case."""
    coord, client = _coord({CONF_SKODA_OFFICIAL_API_KEY: "msk_typed_by_hand"})

    coord._arm_official_from_map({})

    client.arm_supplementary_official.assert_not_called()


def test_a_client_without_the_setter_is_tolerated() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._cariad_client = object()  # no arm_supplementary_official at all
    coord.entry = MagicMock()
    coord.entry.data = {}

    coord._arm_official_from_map(_MAP)  # must not raise


# ── the repair text tells the truth again ───────────────────────────────────


def _description(name: str) -> str:
    data = json.loads((_PKG / name).read_text(encoding="utf-8"))
    return data["issues"]["skoda_official_enrolled"]["description"]


def test_no_language_still_claims_the_channel_waits_on_standby() -> None:
    stale = ("standby", "Standby", "veille", "vänteläge", "vente", "Bereitschaft")
    offenders = [
        name for name in ("strings.json", *(f"translations/{x}.json" for x in _LANGS))
        if any(word in _description(name) for word in stale)
    ]
    assert not offenders, f"still promise standby: {offenders}"


def test_the_english_text_says_it_reads_on_every_update() -> None:
    text = _description("translations/en.json")
    assert "every regular update" in text
    # and still explains the rate limit, which was the true half of the old text
    assert "requests an hour" in text
    # and still says it covers a failure, which is also true
    assert "fails" in text


def test_every_language_has_a_description_of_its_own() -> None:
    """Guard against a half-finished translation pass leaving English behind."""
    english = _description("translations/en.json")
    for lang in _LANGS:
        if lang == "en":
            continue
        text = _description(f"translations/{lang}.json")
        assert text, lang
        assert text != english, f"{lang}.json still carries the English text"
