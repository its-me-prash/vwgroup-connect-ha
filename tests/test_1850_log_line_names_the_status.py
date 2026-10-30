# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1850 (@indigomejor) — "no data-request yet" was printed at a user whose
data request was active the whole time.

He paired the line with its timestamps, which is what made it diagnosable: at
12:03 the portal said *no data-request yet — enable the continuous data
request*, then four `dataset listing unavailable (HTTP 404)` lines followed, and
the request recovered on its own at 12:42. It had never gone away.

#1932/#1933 had already split this message once, for a portal that could not be
**reached** — that case now says plainly it is a VW-side outage and not to touch
the request. What neither covered is a portal that **answers** with an error
status on the metadata read: `identifier` stays empty, no transport error is
recorded, and the original sentence came out.

Two things are pinned here. The branch that names the status, and the reset that
makes naming it honest: `_last_soft_status` is only written in the soft+transient
branch of `_get_json`, so a 200 leaves whatever an earlier poll put there. Before
this change the flag was reset *after* the metadata read, so reporting it would
have attributed an old poll's 404 to a successful one.

Also here, from the same read: `_unzip_json` used to return `{}` for a JSON root
that is not an object, which a log cannot tell apart from an empty delivery.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile

import pytest

from custom_components.vag_connect.cariad.auth import _eu_data_act as eda


# --- the reset that makes the status trustworthy ----------------------------

def test_the_soft_status_is_reset_before_the_metadata_read() -> None:
    """Source-level, because the ordering is the whole point: the reset has to
    sit before the metadata request, not after it."""
    import inspect

    src = inspect.getsource(eda)
    reset = src.index("self._last_soft_status = None")
    meta_read = src.index('f"{_PORTAL_BASE}{meta_path.format(vin=vin)}"')
    assert reset < meta_read, (
        "_last_soft_status is no longer cleared before the metadata read, so "
        "the status named in the no-data-request message can belong to an "
        "earlier poll"
    )


def test_the_status_is_only_recorded_for_a_soft_transient_read() -> None:
    """The reason the reset is load-bearing rather than tidy: a 200 never
    updates the flag, so without the reset it holds an older poll's status."""
    import inspect
    import re

    src = inspect.getsource(eda)
    writes = [
        m.start() for m in re.finditer(r"self\._last_soft_status = resp\.status", src)
    ]
    assert len(writes) == 1, (
        f"the soft status is now written in {len(writes)} places; the reset "
        "before the metadata read was reasoned about assuming exactly one"
    )
    guard = src[max(0, writes[0] - 400) : writes[0]]
    assert "soft and resp.status in _TRANSIENT_STATUSES" in guard, (
        "the soft status is no longer written only in the soft+transient "
        "branch, so a successful read may now update it too"
    )


# --- the two wordings ------------------------------------------------------

def _joined(text: str) -> str:
    """Source with adjacent string literals joined.

    The first version of these tests searched the raw source for a sentence
    that the formatter had wrapped across two literals, so the phrase was
    "missing" while being perfectly present. Join the pieces first.
    """
    import re

    return re.sub(r'"\s*\n\s*"', "", text)


def _no_request_message() -> str:
    """The one message this branch logs, literals joined.

    Composition is checked here; the live behaviour of the surrounding branch
    is covered by test_1932_an_unreachable_portal_is_not_a_missing_request,
    which drives a real poll. That file's decisions are deliberate and this one
    must not quietly reverse them — an earlier version of this test did, by
    replacing the advice for a 404.
    """
    import inspect

    src = inspect.getsource(eda)
    start = src.index('self._note_no_data("no_request")')
    # Sliced to the next ``return d`` rather than to a character count: a fixed
    # window silently stopped reaching the end of the call when the comment
    # above it grew, and the helper then raised instead of reporting.
    body = src[src.index("_LOGGER.info(", start):]
    end = body.index("return d")
    return _joined(body[:end])


def test_the_message_keeps_the_advice_and_adds_the_status_and_the_caveat() -> None:
    """All three at once, because each exists for a different reader.

    The advice is for someone who really has no request (#1932 pins it). The
    status is so a log says what the portal actually answered. The caveat is
    @indigomejor's case: his request was live while this line was printed.
    """
    msg = _no_request_message()
    assert "enable the continuous data request" in msg, (
        "#1932: a 404 is the portal saying 'no such request', and that is the "
        "one case where the user has something to do — the advice must stay"
    )
    assert "HTTP {self._last_soft_status}" in msg, "the status is not named"
    assert "leave it alone" in msg, (
        "the caveat is gone; without it the line still reads as proof that the "
        "request is missing, which is what #1850 reported"
    )


def test_the_status_suffix_is_empty_when_nothing_was_recorded() -> None:
    """A message that said 'HTTP None' would be worse than saying nothing."""
    msg = _no_request_message()
    assert "if self._last_soft_status is not None" in msg, (
        "the status is no longer conditional, so a poll that recorded none "
        "would print a placeholder"
    )
    assert 'else ""' in msg


# --- the JSON root -------------------------------------------------------

def _zip_with(payload: object) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dataset.json", json.dumps(payload))
    return buf.getvalue()


def test_a_dict_root_still_parses() -> None:
    raw = _zip_with({"vin": "X", "Data": [{"dataFieldName": "soc", "value": 80}]})
    assert eda._unzip_json(raw, "dataset.zip").get("vin") == "X"


def test_a_list_root_is_still_treated_as_empty_but_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Behaviour deliberately unchanged — the shape has never been seen, and
    handling an unseen payload is how untested branches are born. What changes
    is that it is no longer silent."""
    raw = _zip_with([{"dataFieldName": "soc", "value": 80}, {"x": 1}])
    with caplog.at_level(logging.WARNING):
        assert eda._unzip_json(raw, "dataset.zip") == {}
    assert "root" in caplog.text
    assert "list" in caplog.text, "the actual root type is not named"
    assert "2 top-level item" in caplog.text, "the item count is not named"


def test_the_root_warning_leaks_neither_the_file_name_nor_a_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """It is a portal file: the name can carry a VIN and the values are the
    car's data. Shape only."""
    raw = _zip_with([{"dataFieldName": "soc", "value": 80}])
    with caplog.at_level(logging.WARNING):
        eda._unzip_json(raw, "WVWZZZAUZFW000000-export.zip")
    assert "WVWZZZAUZFW000000" not in caplog.text
    assert "80" not in caplog.text


def test_an_empty_zip_stays_quiet() -> None:
    """A no-content delivery is normal and must not start warning."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "nothing here")
    assert eda._unzip_json(buf.getvalue(), "dataset.zip") == {}


def test_the_one_time_export_is_not_called_a_continuous_request() -> None:
    """The one-time historical export reaches this same branch through a
    different metadata path, and "continuous data request" is the wrong control
    to send that user to — there is nothing continuous to enable."""
    import inspect

    msg = _no_request_message()
    assert "if _one_time" in msg, (
        "the message no longer distinguishes the one-time export"
    )
    assert "request the historical data export" in msg
    assert "historical data export" in msg
    # and the flag really is the request type, which is set outside the call
    assert '_one_time = request_type == "all"' in inspect.getsource(eda)
