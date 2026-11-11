# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1712 — a browser login that does not replace the one a car already has.

The native token exchange is refused with HTTP 400 and ``invalid assertion
headers``: the vendor checks that the request comes from the real app, and a
third-party client cannot produce that proof. That wall is real and this file
does not pretend otherwise.

**What changes is where the key is issued.** A browser-based authorization-code
flow with PKCE is served by the group identity host under a different audience,
and a browser has no app for the vendor to attest. Measured on 2026-11-09, with
a counter-probe that makes the result mean something:

===================  =========================================================
client id            first response from ``/authorize``
===================  =========================================================
each brand below     ``302`` to ``/u/login`` — the universal login page
right client, wrong  ``unauthorized_client`` — *Callback URL mismatch*
  callback
a client the tenant  ``invalid_request`` — *Unknown client*
  does not know
a made-up id of the  ``invalid_request`` — *Unknown client*  (control)
  same shape
===================  =========================================================

So "reaches the login page" separates from "wrong callback" and from "no such
client", which is what makes it a measurement rather than an observation. Škoda
answers *Unknown client* and is therefore deliberately absent here.

**The contract this file pins is the one that matters more than the login.**
A second source for fields a car already reports is exactly the shape of two
open defects (a stale value sitting beside a current one, and a resolver
choosing between them). So the channel is additive and labelled:

* it never replaces a credential an entry already holds, and never clears the
  session used for remote commands — the thing a competing implementation
  dropped, which cost its users lock and unlock;
* it is opt-in per entry, so an entry that works today is untouched;
* when it dies it goes *unavailable*, and the entry keeps every other channel
  rather than raising one failure for the whole account;
* every value it delivers carries its origin, so nothing is resolved by
  guessing.

These tests are written before the code and are expected to fail.
"""
from __future__ import annotations

import base64
import hashlib
import re
from urllib.parse import parse_qs, urlparse

import pytest

# The four brands measured open, each with the client id and the callback it
# registers. Both values already existed in the integration for the native
# flow; nothing here is a new secret.
#
# The keys are the integration's own brand keys as ``ClientFactory`` spells
# them, not a second naming scheme invented here. ``volkswagen_commercial``
# shares this client id and this callback with ``volkswagen``, so the same
# probe covers it; it is left out until someone asks for it.
BRANDS_OPEN = {
    "volkswagen": (
        "a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com",
        "weconnect://authenticated",
    ),
    "audi": (
        "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
        "myaudi:///",
    ),
    "cupra": (
        "3c756d46-f1ba-4d78-9f9a-cff0d5292d51@apps_vw-dilab_com",
        "cupra://oauth-callback",
    ),
    "seat": (
        "99a5b77d-bd88-4d53-b4e5-a539c60694a3@apps_vw-dilab_com",
        "seat://oauth-callback",
    ),
}

AUDIENCE = "https://api.cariad.com"
AUTHORIZE_HOST = "group.identity.vwgroup.io"


# ---------------------------------------------------------------------------
# PKCE. The verifier never leaves the config flow; only its digest does.

def test_pkce_pair_is_a_correct_s256_pair() -> None:
    """The challenge must be the base64url SHA-256 of the verifier, unpadded.

    Getting this wrong is not a visible bug at the authorize step — the login
    page still appears. It fails later, at the code exchange, with a message
    that does not mention PKCE.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    verifier, challenge = _auth0.new_pkce_pair()

    assert re.fullmatch(r"[A-Za-z0-9_-]{43,128}", verifier), verifier
    assert "=" not in challenge, "base64url for PKCE is unpadded"
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    assert challenge == expected


def test_two_pkce_pairs_differ() -> None:
    """A reused verifier would let one intercepted code be replayed."""
    from custom_components.vag_connect.cariad.auth import _auth0

    first, _ = _auth0.new_pkce_pair()
    second, _ = _auth0.new_pkce_pair()
    assert first != second


# ---------------------------------------------------------------------------
# The authorize URL, per brand.

@pytest.mark.parametrize("brand", sorted(BRANDS_OPEN))
def test_authorize_url_carries_this_brands_own_client_and_callback(
    brand: str,
) -> None:
    """Each brand signs in as itself.

    The measurement above is the reason this is parametrised rather than
    written once for Audi: a brand's client id is known to the tenant only
    together with the callback that brand registers. Mixing them produced
    *Callback URL mismatch* on three of the four.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    client_id, redirect_uri = BRANDS_OPEN[brand]
    _verifier, challenge = _auth0.new_pkce_pair()
    url = _auth0.authorization_url(
        brand=brand, code_challenge=challenge, state="st-1", nonce="no-1")

    parts = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}

    assert parts.netloc == AUTHORIZE_HOST
    assert parts.path == "/authorize"
    assert q["client_id"] == client_id
    assert q["redirect_uri"] == redirect_uri
    assert q["audience"] == AUDIENCE
    assert q["response_type"] == "code"
    assert q["code_challenge"] == challenge
    assert q["code_challenge_method"] == "S256"
    assert q["state"] == "st-1"
    assert q["nonce"] == "no-1"
    assert "offline_access" in q["scope"], "no refresh token without it"


def test_the_verifier_is_never_in_the_url() -> None:
    """Only the digest travels. The verifier in the URL defeats PKCE entirely."""
    from custom_components.vag_connect.cariad.auth import _auth0

    verifier, challenge = _auth0.new_pkce_pair()
    url = _auth0.authorization_url(
        brand="audi", code_challenge=challenge, state="s", nonce="n")
    assert verifier not in url


def test_a_brand_the_tenant_does_not_know_is_refused_locally() -> None:
    """Škoda answers *Unknown client*; we must not send it at all.

    Letting it through would spend a user's time on a login that cannot
    succeed, and would read to them as our failure rather than as an absent
    route.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    with pytest.raises(_auth0.Auth0NotAvailable):
        _auth0.authorization_url(
            brand="skoda", code_challenge="c", state="s", nonce="n")


def test_every_open_brand_is_declared_and_skoda_is_not() -> None:
    """The brand set is a list, not a guess, and it names what it excludes."""
    from custom_components.vag_connect.cariad.auth import _auth0

    assert set(_auth0.AUTH0_BRANDS) == set(BRANDS_OPEN)
    assert "skoda" not in _auth0.AUTH0_BRANDS
    assert "porsche" not in _auth0.AUTH0_BRANDS


# ---------------------------------------------------------------------------
# Reachable is not the same as proven, and the gate must say which it is.

def test_only_the_proven_brand_is_offered_by_default() -> None:
    """Audi is the one brand where a sign-in has been seen to complete.

    Five independent owners reported it working on a competing
    implementation, one of them on a fresh setup. For the other three there is
    no such report, and a string dump of their current app builds found no
    login provider for this route at all — the ``auth0`` strings in two of them
    are a JWT decoding library. Offering a login that cannot finish costs
    somebody an evening and reads as our defect.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    assert _auth0.is_offered("audi") is True
    for brand in ("volkswagen", "cupra", "seat"):
        assert _auth0.is_offered(brand) is False, brand


def test_an_unproven_brand_can_be_switched_on_deliberately() -> None:
    """The reachable-but-unproven brands are a switch away, not a rebuild away —
    except a DENIED one. CUPRA and SEAT can be switched on; Volkswagen cannot,
    because its exchange never completes (AUTH0_DENIED)."""
    from custom_components.vag_connect.cariad.auth import _auth0

    for brand in ("cupra", "seat"):
        assert _auth0.is_offered(brand, include_unproven=True) is True, brand


def test_a_denied_brand_is_never_offered_even_with_the_switch() -> None:
    """#1712 — Volkswagen reaches /authorize but the exchange returns 401
    access_denied and localhost answers *Callback URL mismatch* (live-measured).
    It is kept in AUTH0_BRANDS (the module documents the route) but can never be
    offered, not even with include_unproven — a switch that turns on a
    guaranteed failure would be a defect."""
    from custom_components.vag_connect.cariad.auth import _auth0

    assert "volkswagen" in _auth0.AUTH0_DENIED
    assert _auth0.is_offered("volkswagen") is False
    assert _auth0.is_offered("volkswagen", include_unproven=True) is False


def test_no_switch_can_enable_a_brand_the_tenant_does_not_hold() -> None:
    """Škoda answers *Unknown client*. That is a measurement, not a default.

    A flag that could turn it on would be a flag that guarantees a failure, so
    the absence is enforced below the switch rather than beside it.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    assert _auth0.is_offered("skoda", include_unproven=True) is False
    assert _auth0.is_offered("porsche", include_unproven=True) is False


# ---------------------------------------------------------------------------
# The additive contract. This is the part the worst case is built from.

def test_a_dead_auth0_channel_does_not_take_the_entry_with_it() -> None:
    """WORST CASE, written before the code.

    A car runs on the portal channel. Its owner adds the browser login. Three
    days later the refresh dies silently.

    What the installation must show: every entity that worked before still
    works, the browser channel reports itself unavailable rather than raising,
    and no repair card is opened for the whole entry. A competing
    implementation cleared the command session when it took this route; its
    own tester measured lock and unlock failing straight afterwards.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    before = {
        "channels": {"eu_data_act": "ok"},
        "tokens": {"mbb": "mbb-token", "idk": "idk-token"},
        "field_sources": {"battery_soc": "eu_data_act"},
    }
    after = _auth0.apply_channel_failure(before, brand="audi")

    assert after["channels"]["eu_data_act"] == "ok", "the old channel survives"
    assert after["channels"]["auth0"] == "unavailable"
    assert after["tokens"]["mbb"] == "mbb-token", (
        "the command session must not be cleared — this is the regression "
        "that cost a competing implementation lock and unlock"
    )
    assert after["tokens"]["idk"] == "idk-token"
    assert after.get("reauth_required") is not True, (
        "one dead optional channel is not a reason to send the whole entry "
        "to a reauth prompt"
    )


def test_adding_the_channel_never_overwrites_an_existing_credential() -> None:
    """Opt-in means additive. An entry that works today must not change."""
    from custom_components.vag_connect.cariad.auth import _auth0

    entry = {"tokens": {"mbb": "keep-me", "idk": "keep-me-too"}}
    out = _auth0.attach_session(
        entry, brand="audi",
        result={"access_token": "a", "refresh_token": "r"})

    assert out["tokens"]["mbb"] == "keep-me"
    assert out["tokens"]["idk"] == "keep-me-too"
    assert out["tokens"]["auth0_refresh"] == "r"


def test_a_stored_auth0_token_is_recognisable_as_one() -> None:
    """Two refresh tokens in one store must not be confusable.

    They are redeemed at different hosts under different audiences; sending one
    to the other's endpoint produces an error that names neither.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    assert _auth0.is_auth0_refresh_token(
        _auth0.mark_refresh_token("abc"))
    assert not _auth0.is_auth0_refresh_token("abc")


def test_every_field_from_this_channel_carries_its_origin() -> None:
    """A second source for the same field is how a stale value wins.

    Two open reports are exactly this shape. A value that arrives without a
    source cannot be resolved against another candidate, so the channel labels
    everything it delivers.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    labelled = _auth0.label_fields({"battery_soc": 66, "odometer_km": 4885})
    assert labelled["field_sources"]["battery_soc"] == "auth0"
    assert labelled["field_sources"]["odometer_km"] == "auth0"


# ---------------------------------------------------------------------------
# Failure separation. Two different walls must not share one message.

@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"error": "invalid_grant"}, "expired"),
        ({"error": "unauthorized_client",
          "error_description": "Callback URL mismatch. x is not in the list "
                               "of allowed callback URLs"}, "callback"),
        ({"error": "invalid_request",
          "error_description": "Unknown client: x"}, "unknown_client"),
        ({"error": "invalid_request",
          "error_description": "invalid assertion headers"}, "attestation"),
    ],
)
def test_each_refusal_is_classified_as_itself(
    payload: dict[str, str], expected: str,
) -> None:
    """A competing implementation treats *invalid_grant* and *invalid assertion
    headers* as one re-auth trigger. They are different situations: one is a
    session that ran out, the other is a door that was never open. A user told
    to sign in again cannot act on the second.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    assert _auth0.classify_refusal(payload) == expected


def test_a_token_response_without_an_access_token_is_a_failure() -> None:
    """A 200 with no token is the shape that reads as success and is not."""
    from custom_components.vag_connect.cariad.auth import _auth0

    with pytest.raises(_auth0.Auth0ExchangeFailed):
        _auth0.read_token_response({"token_type": "Bearer", "expires_in": 3600})


# ---------------------------------------------------------------------------
# The two switchable routes, and the pasted-redirect handling. Every assertion
# here is a contract the design cross-check (two model families, 2026-11-09)
# demanded: route<->callback sealed, state bound, the pasted code never echoed.

def test_direct_route_exists_for_every_open_brand() -> None:
    from custom_components.vag_connect.cariad.auth import _auth0

    for brand in BRANDS_OPEN:
        routes = _auth0.routes_for(brand)
        assert routes, brand
        assert any(r.authorize_url.startswith("https://group.identity")
                   for r in routes), brand


def test_only_audi_has_a_catchable_callback() -> None:
    """The copy-from-address-bar UX works only where a localhost callback is
    registered. The probe showed that is Audi alone; the rest answer *Callback
    URL mismatch* for localhost and reach the login only via an app scheme a
    desktop browser will not surrender.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    audi_catchable = [r for r in _auth0.routes_for("audi") if r.catchable]
    assert audi_catchable
    assert all(r.redirect_uri.startswith("http://localhost")
               for r in audi_catchable)

    for brand in ("volkswagen", "cupra", "seat"):
        assert not any(r.catchable for r in _auth0.routes_for(brand)), brand


def test_bff_route_is_volkswagen_only_and_matches_the_app() -> None:
    """BFF is populated only where the app binary confirmed it. Guessing a BFF
    host for another brand would fail as our defect.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    vw_bff = [r for r in _auth0.routes_for("volkswagen") if r.key == "bff"]
    assert len(vw_bff) == 1
    assert vw_bff[0].authorize_url == (
        "https://emea.bff.cariad.digital/auth/v1/auth0/authorize")
    assert vw_bff[0].redirect_uri == "weconnect://authenticated-auth0"

    for brand in ("audi", "cupra", "seat"):
        assert not any(r.key == "bff" for r in _auth0.routes_for(brand)), brand


def test_a_route_is_a_sealed_tuple_not_a_user_choice() -> None:
    """redirect_uri at the token exchange must equal the one at authorize
    (RFC 6749 4.1.3). Binding them in one frozen object makes a mismatch
    impossible rather than discouraged.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    route = _auth0.routes_for("volkswagen")[0]
    import dataclasses
    assert dataclasses.is_dataclass(route)
    with pytest.raises(dataclasses.FrozenInstanceError):
        route.redirect_uri = "weconnect://something-else"  # type: ignore[misc]


def test_a_pasted_redirect_with_the_wrong_state_is_refused() -> None:
    """The state ties a pasted code to the attempt that started it. A mismatch
    is a code from a different login (or a forged one) and must not be
    exchanged.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    with pytest.raises(_auth0.Auth0RedirectInvalid):
        _auth0.parse_redirect(
            "weconnect://authenticated-auth0?code=abc&state=WRONG",
            expected_redirect_uri="weconnect://authenticated-auth0",
            expected_state="RIGHT",
        )


def test_a_matching_redirect_yields_the_code() -> None:
    from custom_components.vag_connect.cariad.auth import _auth0

    code = _auth0.parse_redirect(
        "http://localhost:8080/myaudi-callback?code=the-code&state=S",
        expected_redirect_uri="http://localhost:8080/myaudi-callback",
        expected_state="S",
    )
    assert code == "the-code"


def test_a_bare_code_is_accepted_for_uncatchable_callbacks() -> None:
    """When the callback is an app scheme the browser will not show, a tester
    reads the code from DevTools. A bare code with no URL around it is allowed.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    assert _auth0.parse_redirect(
        "0xDEADBEEFcode", expected_redirect_uri="weconnect://x",
        expected_state="ignored-for-bare-code") == "0xDEADBEEFcode"


def test_no_refusal_message_ever_echoes_the_pasted_code() -> None:
    """The whole reason this parsing lives in one function: the authorization
    code must never reach a log or a traceback. Every refusal path is checked.
    """
    from custom_components.vag_connect.cariad.auth import _auth0

    secret = "SUPER-SECRET-AUTHCODE-7f3a"
    bad_inputs = [
        f"weconnect://x?code={secret}&state=WRONG",       # wrong state
        f"https://wrong-scheme/cb?code={secret}&state=S",  # scheme mismatch
        f"weconnect://x?error=access_denied&detail={secret}",  # error payload
    ]
    for bad in bad_inputs:
        try:
            _auth0.parse_redirect(
                bad, expected_redirect_uri="weconnect://x", expected_state="S")
        except _auth0.Auth0RedirectInvalid as err:
            assert secret not in str(err), f"code leaked in: {err}"
        else:
            raise AssertionError(f"should have refused: {bad}")


def test_an_error_redirect_is_refused_not_mistaken_for_a_code() -> None:
    from custom_components.vag_connect.cariad.auth import _auth0

    with pytest.raises(_auth0.Auth0RedirectInvalid):
        _auth0.parse_redirect(
            "http://localhost:8080/myaudi-callback?error=access_denied&state=S",
            expected_redirect_uri="http://localhost:8080/myaudi-callback",
            expected_state="S",
        )


def test_state_values_differ_between_attempts() -> None:
    from custom_components.vag_connect.cariad.auth import _auth0

    assert _auth0.new_state() != _auth0.new_state()


# ---------------------------------------------------------------------------
# Route-aware builders: the authorize URL and the token body must be built from
# the SAME route, so the redirect_uri matches at both steps (RFC 6749 4.1.3).

def test_route_aware_authorize_url_uses_the_routes_own_callback() -> None:
    from urllib.parse import parse_qs, urlparse

    from custom_components.vag_connect.cariad.auth import _auth0

    # Audi's catchable route carries the localhost callback, not myaudi:///.
    catchable = [r for r in _auth0.routes_for("audi") if r.catchable][0]
    url = _auth0.authorization_url_for(
        catchable, code_challenge="c", state="s", nonce="n")
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["redirect_uri"] == "http://localhost:8080/myaudi-callback"
    assert q["client_id"] == catchable.client_id
    assert urlparse(url).netloc + urlparse(url).path == (
        "group.identity.vwgroup.io/authorize")


def test_the_token_body_repeats_the_same_callback_as_authorize() -> None:
    from custom_components.vag_connect.cariad.auth import _auth0

    for route in _auth0.routes_for("audi"):
        body = _auth0.token_body_for(route, code="x", code_verifier="v")
        assert body["redirect_uri"] == route.redirect_uri, route.key
        assert body["client_id"] == route.client_id
        assert body["grant_type"] == "authorization_code"


def test_the_bff_route_builds_against_the_bff_host() -> None:
    from urllib.parse import urlparse

    from custom_components.vag_connect.cariad.auth import _auth0

    bff = [r for r in _auth0.routes_for("volkswagen") if r.key == "bff"][0]
    url = _auth0.authorization_url_for(bff, code_challenge="c", state="s", nonce="n")
    assert urlparse(url).netloc == "emea.bff.cariad.digital"
    body = _auth0.token_body_for(bff, code="x", code_verifier="v")
    assert body["redirect_uri"] == "weconnect://authenticated-auth0"


# ---------------------------------------------------------------------------
# Hardening added after an adversarial cross-review (two model families).


def test_a_code_in_the_port_position_is_refused_without_leaking() -> None:
    """A tester who pastes the code where the port goes (``localhost:<code>``)
    makes urllib raise a ValueError whose message carries the code. It must
    become a clean refusal, and the code must not reach the message."""
    from custom_components.vag_connect.cariad.auth import _auth0

    secret = "SECRETCODE7f3a"
    try:
        # A URL-form paste with the code dropped into the port position: .port
        # raises ValueError('Port could not be cast … SECRETCODE7f3a').
        _auth0.parse_redirect(
            f"http://localhost:{secret}/myaudi-callback?code=x&state=S",
            expected_redirect_uri="http://localhost:8080/myaudi-callback",
            expected_state="S")
    except _auth0.Auth0RedirectInvalid as err:
        assert secret not in str(err), f"code leaked: {err}"
    else:
        raise AssertionError("should have refused a code-in-port paste")


def test_a_bare_code_with_control_whitespace_is_refused() -> None:
    """Only a space was rejected before; a tab or newline in a bare code must be
    refused too, not sent to the exchange."""
    from custom_components.vag_connect.cariad.auth import _auth0

    for bad in ("ab\tcd", "ab\ncd"):
        with pytest.raises(_auth0.Auth0RedirectInvalid):
            _auth0.parse_redirect(
                bad, expected_redirect_uri="weconnect://x",
                expected_state="ignored")


def test_a_routes_client_id_is_the_resolved_one() -> None:
    """authorize/exchange (route.client_id) and refresh (resolve_client_id) must
    use the SAME client, or a rotated market-config client breaks the refresh."""
    from custom_components.vag_connect.cariad.auth import _auth0

    for brand in _auth0.AUTH0_BRANDS:
        resolved = _auth0.resolve_client_id(brand)
        for route in _auth0.routes_for(brand):
            assert route.client_id == resolved, (brand, route.key)


def test_id_token_claims_tolerate_a_non_string() -> None:
    """The docstring promises it never raises; None or an int must give {}."""
    from custom_components.vag_connect.cariad.auth import _auth0

    assert _auth0.id_token_claims(None) == {}  # type: ignore[arg-type]
    assert _auth0.id_token_claims(123) == {}  # type: ignore[arg-type]
