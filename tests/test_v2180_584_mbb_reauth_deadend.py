# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 — once MBB was armed, there was no way back to the approval flow.

Two halves of one dead end, reported by @Mattheisen87 with a Passat GTE:

* The Reconfigure form never passed the stored channel flag into the schema, so
  the "enable MBB commands" box rendered unticked for everyone — including
  people whose channel was on. The form said off; the code said on.
* Ticking it anyway did nothing, because arming was gated on the channel NOT
  already being set. The single moment you need to re-approve — armed, but the
  tokens are dead — was the exact case the guard excluded.

Together: the box looks off, ticking it does nothing, and the only escape is
delete + re-add, which renames all ~70 entities and takes the user's dashboards
and automations with it.

The two halves hid each other. With the box always unticked, nobody noticed the
guard; with the guard silently skipping, nobody questioned the box.

Paired with the refresh fix (test_v2180_mbb_refresh_field.py): that one stops
the tokens from dying, this one lets you recover the ones already dead.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.config_flow import _credentials_schema
from custom_components.vag_connect.const import CONF_MBB_COMMAND_CHANNEL


def _schema_default(schema, field: str):
    """Return the default voluptuous would render for ``field``."""
    for marker in schema.schema:
        if str(marker) == field:
            default = marker.default
            return default() if callable(default) else default
    raise AssertionError(f"{field} not in schema")


class TestCheckboxReflectsStoredState:
    def test_armed_channel_renders_the_box_ticked(self) -> None:
        # The bug: this argument was never passed, so it defaulted to False and
        # the box lied to every MBB user about the state of their own entry.
        schema = _credentials_schema(enable_mbb_commands=True)
        assert _schema_default(schema, "enable_mbb_commands") is True

    def test_unarmed_channel_renders_the_box_unticked(self) -> None:
        schema = _credentials_schema(enable_mbb_commands=False)
        assert _schema_default(schema, "enable_mbb_commands") is False

    def test_reconfigure_reads_the_key_it_is_actually_stored_under(self) -> None:
        # The schema field is "enable_mbb_commands"; the stored key is
        # CONF_MBB_COMMAND_CHANNEL. They are different strings, which is how a
        # missing argument stayed invisible for so long. Guard the mismatch.
        assert CONF_MBB_COMMAND_CHANNEL != "enable_mbb_commands"

        import inspect

        from custom_components.vag_connect import config_flow

        src = inspect.getsource(config_flow.VagConnectConfigFlow.async_step_reconfigure)
        assert "enable_mbb_commands=bool(current.get(CONF_MBB_COMMAND_CHANNEL" in src, (
            "reconfigure must seed the box from the stored channel flag"
        )


class TestReApprovalIsReachable:
    """The arming gate must not exclude the case that needs it most."""

    @staticmethod
    def _gate(user_input: dict, brand: str, entry_data: dict) -> bool:
        """Mirror of the condition in async_step_reconfigure."""
        import inspect

        from custom_components.vag_connect import config_flow

        src = inspect.getsource(config_flow.VagConnectConfigFlow.async_step_reconfigure)
        # The old guard. If this string is back, the dead end is back.
        assert "and not entry.data.get(CONF_MBB_COMMAND_CHANNEL)" not in src, (
            "re-approval is gated off again for already-armed entries (#584)"
        )
        return bool(user_input.get("enable_mbb_commands")) and brand in (
            "volkswagen",
            "audi",
        )

    def test_already_armed_entry_can_re_approve(self) -> None:
        # Mattheisen87's exact state: armed, tokens dead since 13 Jul, no route
        # back. This must now offer the QR flow.
        assert self._gate(
            {"enable_mbb_commands": True},
            "volkswagen",
            {CONF_MBB_COMMAND_CHANNEL: True},
        )

    def test_first_time_arming_still_works(self) -> None:
        assert self._gate({"enable_mbb_commands": True}, "audi", {})

    def test_unticked_box_does_not_drag_you_through_qr(self) -> None:
        assert not self._gate({"enable_mbb_commands": False}, "volkswagen", {})

    @pytest.mark.parametrize("brand", ["skoda", "cupra", "seat", "porsche"])
    def test_non_mbb_brands_are_untouched(self, brand: str) -> None:
        # MBB is a VW/Audi-only legacy Car-Net path; widening the gate must not
        # start offering it to brands that have no such backend.
        assert not self._gate({"enable_mbb_commands": True}, brand, {})


def test_reauth_is_not_forced_on_the_whole_entry() -> None:
    """MBB dying must not mark a working entry as broken.

    Mattheisen87 also suggested raising ConfigEntryAuthFailed on a dead MBB
    token so HA prompts for reauth. Tempting, but MBB is a *command* channel
    sitting beside a perfectly healthy read path — raising it would flag the
    whole entry as auth-broken and nag users whose data is arriving fine.
    Recovery belongs in Reconfigure, which is where we put it.
    """
    import inspect

    from custom_components.vag_connect.cariad.auth import _mbboauth

    src = inspect.getsource(_mbboauth)
    assert "ConfigEntryAuthFailed" not in src
