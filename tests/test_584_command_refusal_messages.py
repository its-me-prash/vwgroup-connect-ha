# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 (@Joassens, 2017 VW Passat GTE, NL) — say what the gateway actually
refused, instead of a raw 403.

He instrumented all three SecToken legs and found that legs 1 and 2 succeed —
challenge received, S-PIN accepted — and the refusal lands on the action itself:

    403 {"errorCode":"mbbc.rolesandrights.unauthorized",
         "description":"Did not find permission for systemId 'XID_APP_VW' …"}

while the charge-target variant answered differently:

    400 {"errorCode":"gw.error.validation","description":"Invalid Request"}

Both used to reach the user as an unexplained traceback, which reads like "your
password or your subscription is wrong" — and all three of those had demonstrably
checked out: licence ACTIVATED to 2027-08, the operationList granting the
operation, and the S-PIN handshake completing.

He then captured the official app (4.6.4) on a rooted emulator: it authenticates
purely as a CARIAD/BFF client with no MBB scope and fails without device
attestation. So for a car like his the command most likely never travels this
plane at all, and there is nothing the owner can switch on. The honest
deliverable is therefore a clear message, not a workaround — his own conclusion,
and the reason these two strings exist.

The two are kept apart deliberately. A 400 here is the gateway validating the
body against this service's older schema BEFORE the permission check, so it says
"this model does not take that setting", not "you may not". His operationList
lists P_SETTINGS as granted, which is why the control stays visible.

REWRITTEN 2026-10-11, because the first version of this file did not test the
shipped code. It re-implemented the branch over a plain string in its own helper,
and its control test grepped the module source for the marker strings. Both
passed while the handler matched those markers against ``str(APIError)`` — whose
message is deliberately redacted to the status and a masked URL (#1355) and can
therefore never contain them. The branches were dead in v4.13.0, which is why a
second reporter still got a bare 403 after we announced the fix. The
classification now lives in one module-level function that the handler and these
tests both call, and the control test pins the SIGNATURE rather than the source
text: it proves that matching the string cannot work, which is what makes reading
the body the load-bearing detail.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import (
    body_has_marker,
    leg3_refusal_kind,
)
from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    VehicleCommandError,
)

#: A real action URL, so the redacted message has something to mask.
ACTION_URL = (
    "https://mal-3a.prd.eu.dp.vwg-connect.com"
    "/api/bs/rlu/v1/VW/NL/vehicles/WVWZZZ1JZ3W000001/actions"
)

# The bodies, from his log lines. The JSON is what ``APIError.body`` holds; the
# ``HTTP 403 `` prefix is how his log printed it, kept on one case to show the
# match does not depend on the body being bare JSON.
SYSTEMID_403 = (
    '{"errorCode":"mbbc.rolesandrights.unauthorized","description":'
    '"Did not find permission for systemId \'XID_APP_VW\', therefore denying '
    'access"}'
)
CHARGE_403 = (
    'HTTP 403 {"errorCode":"batterycharge.auth.forbidden","description":'
    '"Did not find permission for systemId \'XID_APP_VW\', therefore denying '
    'access"}'
)
VALIDATION_400 = (
    '{"errorCode":"gw.error.validation","description":"Invalid Request"}'
)
PIN_LOCKED_403 = '{"errorCode":"mbbc.rolesandrights.securityPinLocked"}'


def _err(body: str, status: int = 403) -> APIError:
    """The exception the leg-3 handler actually catches, built the way the
    producer builds it (``vw_eu._mbb_post_action`` raises
    ``APIError(resp.status, url, body=text)``)."""
    return APIError(status, ACTION_URL, body=body)


@pytest.mark.parametrize("body", [SYSTEMID_403, CHARGE_403])
def test_a_systemid_refusal_is_recognised(body: str) -> None:
    assert leg3_refusal_kind(_err(body)) == "client-identity"


def test_a_validation_failure_is_kept_separate() -> None:
    """Not folded into the permission case: it means something different, and
    telling a user they lack permission when the car called the request invalid
    would send them to VW support for nothing."""
    assert leg3_refusal_kind(_err(VALIDATION_400, status=400)) == "schema"


@pytest.mark.parametrize("body", [
    PIN_LOCKED_403,
    "Bad Gateway",
    '{"errorCode":"gw.error.notFound"}',
    "",
])
def test_an_unrelated_error_is_not_swallowed(body: str) -> None:
    """Anything we have not measured must keep propagating unchanged, or a new
    failure mode would be hidden behind a reassuring sentence."""
    assert leg3_refusal_kind(_err(body)) is None


def test_matching_the_exception_string_cannot_work() -> None:
    """The control, and the whole point of this rewrite.

    ``APIError`` masks its message on purpose so that re-raising it cannot leak
    the body or the VIN-bearing URL. So a classifier that reads ``str(err)`` is
    not merely fragile, it is unreachable code — and that is exactly what shipped.
    Pinning it here means the next person who reaches for ``str(exc)`` in a
    marker test gets a failing test instead of a silent regression.
    """
    err = _err(SYSTEMID_403)
    rendered = str(err).lower()
    for marker in ("xid_app_vw", "rolesandrights.unauthorized",
                   "auth.forbidden", "gw.error.validation",
                   "securitypinlocked"):
        assert marker not in rendered, marker
    # ... while the body carries the one it should.
    assert "rolesandrights.unauthorized" in err.body.lower()
    # And the shipped classifier reads the body, so it fires.
    assert leg3_refusal_kind(err) == "client-identity"


def test_the_locked_s_pin_is_detected_from_the_body_too() -> None:
    """The same defect hit the S-PIN-locked branch at two other sites, where it
    cost the user the one message that tells them what to do about it."""
    assert body_has_marker(_err(PIN_LOCKED_403), "securitypinlocked") is True
    assert body_has_marker(_err(VALIDATION_400), "securitypinlocked") is False
    # A body-less failure must not be read as a locked S-PIN.
    assert body_has_marker(_err(""), "securitypinlocked") is False


def test_no_marker_test_in_this_module_reads_the_exception_string() -> None:
    """Belt and braces against the regression returning by copy-paste.

    The producer of these errors redacts its message, so every marker test in
    the VW EU client has to read ``body``. This greps for the idiom that cannot
    work, rather than for the strings that should be present — a presence check
    was what let the dead branches ship.
    """
    import inspect

    from custom_components.vag_connect.cariad.api import vw_eu

    src = inspect.getsource(vw_eu)
    assert "str(_e).lower()" not in src
    assert "str(exc).lower()" not in src


def test_the_messages_name_what_is_not_wrong() -> None:
    """The point of the wording. A bare 403 reads as "wrong password or expired
    subscription", and both were verified fine — so the message has to rule them
    out explicitly or the user goes to VW support with the wrong question."""
    import inspect

    from custom_components.vag_connect.cariad.api import vw_eu

    src = inspect.getsource(vw_eu)
    assert "not your password, your S-PIN or your subscription" in src
    assert "Reads are unaffected." in src


def test_vehicle_command_error_is_an_api_error_subclass_or_not() -> None:
    """Pin the relationship rather than assume it: callers catch one or the
    other, and if VehicleCommandError were an APIError subclass the leg-3
    handler would re-enter its own except block on a retry."""
    assert not issubclass(VehicleCommandError, APIError)


# ── The lock path, which the first fix did not reach ─────────────────────────
#
# v4.13.0 put the classification inline in `_command_mbb_op`, which serves
# climate, charge and the timers. The reporter whose command was refused was
# locking, and `_command_rlu_mbb` had no handler on its leg-3 action at all, so
# he would have received the byte-identical bare 403 a third time, in a release
# whose changelog credited him by name. The classification now lives in one
# function both paths call.


@pytest.mark.parametrize("body,expected", [
    # His own code, which nothing in the classifier was matching. The wake
    # handler in the same module has matched it since v4.7.x for this exact
    # grant gap, so the code alone is enough and we never have to ask a
    # reporter for a description our logging deliberately does not print.
    ('{"error":{"errorCode":"security.9007"}}', "client-identity"),
    (SYSTEMID_403, "client-identity"),
    (VALIDATION_400, "schema"),
])
def test_the_classifier_covers_the_lock_refusals(body: str, expected: str) -> None:
    assert leg3_refusal_kind(_err(body)) == expected


def test_the_shared_raiser_names_the_command_it_was_given() -> None:
    """Both paths pass their own verb, so the message says "lock" for a lock."""
    from custom_components.vag_connect.cariad.api.vw_eu import (
        raise_if_leg3_refusal,
    )

    with pytest.raises(VehicleCommandError) as caught:
        raise_if_leg3_refusal(_err('{"error":{"errorCode":"security.9007"}}'), "lock")
    assert "lock" in str(caught.value)
    assert "not your password, your S-PIN or your subscription" in str(caught.value)


def test_an_unmeasured_body_is_not_swallowed_by_the_raiser() -> None:
    """Returning without raising is the contract: the caller re-raises.

    Hiding a failure mode we have never seen behind a reassuring sentence would
    turn a new fault into a silent one.
    """
    from custom_components.vag_connect.cariad.api.vw_eu import (
        raise_if_leg3_refusal,
    )

    assert raise_if_leg3_refusal(_err('{"errorCode":"gw.error.notFound"}'), "lock") is None


def test_the_lock_path_actually_calls_the_raiser() -> None:
    """The structural guard, and the one the first fix needed.

    A test of the classifier alone passed while the lock path never called it.
    So this pins the wiring: the leg-3 action in `_command_rlu_mbb` must sit
    inside a try whose handler calls the shared raiser. Checking for the absence
    of an unguarded call is the kind of check that catches this; asserting the
    classifier exists is not.
    """
    import inspect
    import re

    from custom_components.vag_connect.cariad.api import vw_eu

    src = inspect.getsource(vw_eu.VWEUClient._command_rlu_mbb)
    assert "raise_if_leg3_refusal" in src, "the lock path does not classify at all"
    # The action call and the handler must be in the same try block, which means
    # the call is indented under a try and an except follows it.
    assert re.search(r"try:\s*\n\s+action_resp = await self\._mbb_post_rlu\(", src), (
        "the leg-3 action call is not inside a try block"
    )
    # And the climate path must still use the same function rather than its own copy.
    op_src = inspect.getsource(vw_eu.VWEUClient._command_mbb_op)
    assert "raise_if_leg3_refusal" in op_src
    assert "client-identity" not in op_src, (
        "the climate path still carries its own copy of the classification"
    )
