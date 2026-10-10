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
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    VehicleCommandError,
)

# The two bodies, verbatim from his log lines.
SYSTEMID_403 = (
    'HTTP 403 {"errorCode":"mbbc.rolesandrights.unauthorized","description":'
    '"Did not find permission for systemId \'XID_APP_VW\', therefore denying '
    'access"}'
)
CHARGE_403 = (
    'HTTP 403 {"errorCode":"batterycharge.auth.forbidden","description":'
    '"Did not find permission for systemId \'XID_APP_VW\', therefore denying '
    'access"}'
)
VALIDATION_400 = (
    'HTTP 400 {"errorCode":"gw.error.validation","description":"Invalid Request"}'
)


def _classify(body: str) -> str:
    """Run the module's own branch logic over one error body.

    Mirrors the leg-3 handler rather than importing it: the handler needs a live
    client, three legs of HTTP and an S-PIN to reach. What is asserted here is
    the thing that was missing — that these bodies are recognised and separated
    — and `test_the_handler_still_contains_these_branches` pins it to the real
    source so this file cannot drift into testing only itself.
    """
    low = body.lower()
    if ("xid_app_vw" in low or "rolesandrights.unauthorized" in low
            or "auth.forbidden" in low):
        return "client-identity"
    if "gw.error.validation" in low:
        return "schema"
    return "unhandled"


@pytest.mark.parametrize("body", [SYSTEMID_403, CHARGE_403])
def test_a_systemid_refusal_is_recognised(body: str) -> None:
    assert _classify(body) == "client-identity"


def test_a_validation_failure_is_kept_separate() -> None:
    """Not folded into the permission case: it means something different, and
    telling a user they lack permission when the car called the request invalid
    would send them to VW support for nothing."""
    assert _classify(VALIDATION_400) == "schema"


def test_an_unrelated_error_is_not_swallowed() -> None:
    """Anything we have not measured must keep propagating unchanged, or a new
    failure mode would be hidden behind a reassuring sentence."""
    for body in (
        'HTTP 403 {"errorCode":"mbbc.rolesandrights.securityPinLocked"}',
        'HTTP 502 Bad Gateway',
        'HTTP 404 {"errorCode":"gw.error.notFound"}',
        "",
    ):
        assert _classify(body) == "unhandled", body


def test_the_handler_still_contains_these_branches() -> None:
    """Control. If the leg-3 handler is refactored away, the parametrised tests
    above would keep passing against a copy of logic that no longer runs."""
    import inspect

    from custom_components.vag_connect.cariad.api import vw_eu

    src = inspect.getsource(vw_eu)
    # the recognition strings
    for needle in ("xid_app_vw", "rolesandrights.unauthorized",
                   "auth.forbidden", "gw.error.validation"):
        assert needle in src, needle
    # and that they raise a command error rather than leaking the raw APIError
    assert "the car's gateway accepted your S-PIN" in src
    assert "rejected the request as invalid rather than" in src


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
