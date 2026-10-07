# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1737/#1752 — the Porsche report link must ask for a capture the reporter
can actually produce.

One paragraph used to go to every caller, and it was wrong for most of them.
It sent people to the three-dots debug toggle, which needs a configured entry
that a failed initial setup never leaves behind (#1337, 2026-09-22: "i cannot
enable debug on the integration, because i never had [set up] the
integration"). And for a WALL it asked for debug logging plus "reproduce once"
although the decisive line — screen plus page markers — is already in the
default log at WARNING, so the extra login attempt bought nothing on an
account where repeated failures cause lockouts (#1633 shows a reporter
supplying that line with no debug logging at all).

The report also never named our own version, while the Scout and error
reporters both do (#1736/#1738).
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from custom_components.vag_connect.config_flow import VagConnectConfigFlow

_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
_LANGS = ("cs", "da", "de", "en", "es", "fi", "fr", "it", "nb", "nl", "pl", "sv")
_URL = VagConnectConfigFlow._porsche_report_url


def _body(step: str, reason: str, screen: str = "", version: str = "") -> str:
    url = _URL(step, reason, screen, version=version)
    return parse_qs(urlsplit(url).query)["body"][0]


# ── the route has to exist where the reporter is standing ───────────────────


def test_a_failed_setup_is_never_sent_to_the_three_dots_menu() -> None:
    body = _body("email_password", "porsche_portal_step", "my.porsche.com/")

    # naming the toggle to say it is NOT there is fine and saves a hunt;
    # issuing it as an instruction is the bug
    assert "Enable debug logging" not in body
    assert "nothing to hang off" in body
    assert "no entry yet" in body
    # ...and it still offers a way to get the deeper lines
    assert "configuration.yaml" in body
    assert "custom_components.vag_connect.cariad.auth.porsche: debug" in body


def test_a_reauth_report_is_asked_for_diagnostics_it_actually_has() -> None:
    body = _body("reauth", "porsche_captcha")

    assert "Download diagnostics" in body
    assert "no entry yet" not in body
    # the three-dots route is legitimate here — an entry exists
    assert "three-dots menu -> Enable debug logging" in body
    assert "configuration.yaml" not in body


def test_the_entry_bearing_steps_are_exactly_the_two_that_need_one() -> None:
    assert VagConnectConfigFlow._PORSCHE_STEPS_WITH_ENTRY == frozenset(
        {"reauth", "reconfigure"}
    )
    # initial setup and the form's own fallback label must NOT claim an entry
    for step in ("email_password", "porsche_captcha"):
        assert step not in VagConnectConfigFlow._PORSCHE_STEPS_WITH_ENTRY


# ── a wall asks for the line that is already written ───────────────────────


def test_a_wall_points_at_the_warning_line_and_never_asks_for_a_retry() -> None:
    for reason in ("porsche_login_wall", "porsche_portal_step"):
        body = _body("email_password", reason, "my.porsche.com/")

        assert "markers=" in body, reason
        assert "home-assistant.log" in body, reason
        assert "no further login attempt" in body, reason
        assert "do NOT retry" in body, reason
        # the old instruction must be gone: it cost an extra attempt
        assert "reproduce once" not in body, reason


def test_both_wall_reasons_are_recognised_as_walls() -> None:
    assert VagConnectConfigFlow._PORSCHE_WALL_REASONS == frozenset(
        {"porsche_login_wall", "porsche_portal_step"}
    )


# ── a captcha asks the question that decides it ────────────────────────────


def test_a_captcha_report_asks_whether_the_image_rendered() -> None:
    body = _body("reauth", "porsche_captcha")

    assert "did the captcha image actually appear" in body
    assert "empty or broken" in body
    assert "do NOT retry" in body
    # that question is pointless for a wall, where no image is involved
    assert "did the captcha image actually appear" not in _body(
        "email_password", "porsche_portal_step", "my.porsche.com/"
    )


# ── the version line ───────────────────────────────────────────────────────


def test_the_report_names_our_version_when_it_is_known() -> None:
    body = _body("reauth", "porsche_captcha", version="4.11.1")
    assert "- Integration: vag_connect 4.11.1" in body


def test_an_unknown_version_renders_no_line_at_all() -> None:
    body = _body("reauth", "porsche_captcha")
    assert "Integration:" not in body
    # and the rest of the header is untouched
    assert "- Step: reauth" in body
    assert "- Error: porsche_captcha" in body
    assert "- Auth0 screen: unknown" in body


def test_the_version_does_not_loosen_the_pii_guard() -> None:
    """G7 (#1337) again, with the new field in place."""
    url = _URL(
        "email_password", "porsche_login_wall", "identity.porsche.com/x",
        version="4.11.1",
    )
    for leak in (
        "secret-user@example.com", "hunter2-secret", "state-abc", "verifier-xyz",
        "code=", "access_token", "Bearer ",
    ):
        assert leak not in url


# ── the new abort text, in every language ──────────────────────────────────


def test_the_credentials_abort_exists_in_every_language() -> None:
    for name in ("strings.json", *(f"translations/{lang}.json" for lang in _LANGS)):
        data = json.loads((_ROOT / name).read_text(encoding="utf-8"))
        text = data["config"]["abort"].get("porsche_captcha_credentials")
        assert text, f"{name} is missing porsche_captcha_credentials"
        assert "{report_url}" in text, f"{name} drops the report link"
        assert "Porsche" in text, f"{name} does not name the service"


def test_the_credentials_abort_does_not_blame_the_captcha() -> None:
    """The whole point: the English text must not repeat the old diagnosis."""
    data = json.loads((_ROOT / "translations" / "en.json").read_text(encoding="utf-8"))
    abort = data["config"]["abort"]

    credentials = abort["porsche_captcha_credentials"]
    assert "password" in credentials
    assert "refused the sign-in" in credentials

    # the old text stays where it belongs — for a captcha that really failed
    assert "could not be verified" in abort["porsche_captcha_failed"]
    assert "could not be verified" not in credentials
