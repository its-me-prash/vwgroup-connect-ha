"""#923 (@kalwados) — an auth repair card has to say which account it is about.

He runs two cars, saw a card with a Repair button on 5.1.3, and could not tell
which of his entries it belonged to. The inventory explains it: of the repair
cards this integration raises, only ``stale_data``, ``historical_timeout`` and
``supplementary_reauth`` name the vehicle, and only the first two are keyed per
vehicle at all. Everything the auth path raises is per entry, and the one field
that could identify the entry — ``{username}``, which four of the texts print
inside parentheses — was supplied as an empty string.

That is why it was not caught: the frontend only checks that the placeholder
KEY exists, so an empty value renders "Your Volkswagen account ()" and errors
nowhere. The tests below drive the real function and read what it hands to the
issue registry, rather than asserting on the source text.

The address is masked (#709) because these cards get screenshotted into public
issues; a verbatim account id in a card is a leak waiting for a screenshot.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.const import CONF_USERNAME

_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
_STRINGS = json.loads((_ROOT / "strings.json").read_text(encoding="utf-8"))

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# Every reason the auth path maps, plus one it does not: an unmapped reason
# falls through to the generic ``auth_failed`` copy, which also prints {brand}.
_REASONS = (
    "two_factor_required",
    "email_two_factor_required",
    "device_login_expired",
    "eu_signin_attestation",
    "device_login_grant_retired",
    "terms_and_consitions_typo_is_not_a_reason",  # unmapped -> auth_failed
    "terms_and_conditions",
    "marketing_consent",
    "too_many_requests",
    "invalid_credentials",
)

_ADDRESS = "prash@example.de"


def _card_text(card: dict) -> str:
    """Only what the card itself renders.

    NOT the whole JSON entry: a card's ``fix_flow`` steps carry their own
    placeholders, fed by ``description_placeholders`` on the flow instead of by
    the issue. Reading the entry wholesale is what first made this file claim
    that ``supplementary_reauth`` prints {username} on its card, which it does
    not — its flow step does.
    """
    return f"{card.get('title', '')}\n{card.get('description', '')}"


def _cards_printing(placeholder: str) -> set[str]:
    needle = "{" + placeholder + "}"
    return {
        key
        for key, card in _STRINGS["issues"].items()
        if needle in _card_text(card)
    }


def _raise(reason: str, *, entry: object | None, brand: str | None = "volkswagen"):
    """Run the real function, return the kwargs it passed to the registry."""
    from custom_components.vag_connect import repairs

    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = entry
    with patch(
        "custom_components.vag_connect.repairs.ir.async_create_issue"
    ) as created:
        repairs.raise_issue_auth_required(
            hass, entry_id="01ABC", reason=reason, brand=brand
        )
        assert created.call_count == 1, "one card per call, or the id collides"
        return created.call_args.kwargs


def _entry(username: str | None = _ADDRESS, title: str = "Volkswagen (Golf)"):
    return SimpleNamespace(
        data={CONF_USERNAME: username} if username is not None else {},
        title=title,
    )


class TestTheAccountSlotIsFilled:
    """The defect itself: the slot existed and said nothing."""

    @pytest.mark.parametrize("reason", _REASONS)
    def test_never_empty(self, reason: str) -> None:
        got = _raise(reason, entry=_entry())["translation_placeholders"]
        assert got["username"], (
            f"{reason}: the account slot is empty again, so the card reads "
            "'account ()' and a two-entry owner cannot tell which one it is"
        )

    @pytest.mark.parametrize("reason", _REASONS)
    def test_the_address_is_masked_not_verbatim(self, reason: str) -> None:
        got = _raise(reason, entry=_entry())["translation_placeholders"]
        assert _ADDRESS not in got["username"]
        assert "example" not in got["username"], "the domain must not survive"
        # what mask_email(#709) yields: first letter, masked domain, real TLD
        assert got["username"] == "p***@***.de"

    def test_two_accounts_stay_distinguishable(self) -> None:
        """The whole point: his two entries must not render identically."""
        one = _raise(
            "invalid_credentials", entry=_entry("prash@example.de")
        )["translation_placeholders"]["username"]
        two = _raise(
            "invalid_credentials", entry=_entry("kalle@example.com")
        )["translation_placeholders"]["username"]
        assert one != two


class TestTheFallbacks:
    """A passwordless entry and a vanished entry must not reintroduce ()."""

    def test_passwordless_entry_falls_back_to_the_title(self) -> None:
        """#1813 device-login entries carry no username at all."""
        got = _raise("device_login_expired", entry=_entry(username=None))
        assert got["translation_placeholders"]["username"] == "Volkswagen (Golf)"

    def test_empty_username_falls_back_to_the_title(self) -> None:
        got = _raise("device_login_expired", entry=_entry(username=""))
        assert got["translation_placeholders"]["username"] == "Volkswagen (Golf)"

    def test_vanished_entry_does_not_crash_or_blank(self) -> None:
        """async_get_entry returns None for an entry being removed."""
        got = _raise("invalid_credentials", entry=None)
        assert got["translation_placeholders"]["username"] == "this entry"

    def test_titleless_entry_does_not_blank(self) -> None:
        got = _raise(
            "invalid_credentials", entry=_entry(username=None, title="")
        )
        assert got["translation_placeholders"]["username"] == "this entry"


class TestEveryPlaceholderInTheCopyIsSupplied:
    """The invariant, derived from the copy rather than from the call site.

    Reading the call site is how the empty value survived review: it supplies
    both keys, and that looks complete. So go the other way — take the text
    that will actually be rendered and demand a non-empty value for every
    placeholder in it.
    """

    @pytest.mark.parametrize("reason", _REASONS)
    def test_text_placeholders_are_all_supplied_and_non_empty(
        self, reason: str
    ) -> None:
        kwargs = _raise(reason, entry=_entry())
        key = kwargs["translation_key"]
        card = _STRINGS["issues"][key]
        wanted = set(_PLACEHOLDER.findall(_card_text(card)))
        supplied = kwargs["translation_placeholders"]
        missing = wanted - set(supplied)
        assert not missing, f"{key}: {sorted(missing)} would render MISSING_VALUE"
        blank = sorted(k for k in wanted if not str(supplied[k]).strip())
        assert not blank, f"{key}: {blank} supplied but empty"

    def test_positive_control_the_copy_really_uses_the_slot(self) -> None:
        """Guards the test above: if no text used {username}, it proves nothing."""
        users = sorted(_cards_printing("username"))
        assert len(users) >= 4, f"expected the known users of the slot, got {users}"

    def test_no_auth_card_with_the_slot_is_left_undriven(self) -> None:
        """A new auth card using {username} must be added to _REASONS."""
        driven = {
            _raise(r, entry=_entry())["translation_key"] for r in _REASONS
        }
        assert _cards_printing("username") <= driven, (
            f"{sorted(_cards_printing('username') - driven)} print the account "
            "but are never driven here — either they are raised elsewhere "
            "(then say so) or they are an untested path"
        )
