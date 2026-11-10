# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A browser sign-in that is added to a car, never substituted for one (#1712).

The native token exchange is refused with HTTP 400 and ``invalid assertion
headers``. That is the vendor checking the request came from its own app, and a
third-party client cannot produce that proof. This module does not get around
that check — it uses a door that does not have one.

The group identity host also serves a plain authorization-code flow with PKCE
under the audience ``https://api.cariad.com``. It is completed in a browser,
and a browser has no app for the vendor to attest, which is why the wall does
not stand in front of it.

**Measured on 2026-11-09, with the counter-probe that makes it a measurement**
(first response from ``/authorize``, redirects not followed):

==========================================  ================================
request                                     answer
==========================================  ================================
brand's own client id + its own callback    ``302`` to ``/u/login``
brand's own client id + a foreign callback  ``unauthorized_client`` —
                                              *Callback URL mismatch*
a client id this tenant does not hold       ``invalid_request`` —
  (Škoda)                                     *Unknown client*
an invented id of the same shape (control)  ``invalid_request`` —
                                              *Unknown client*
==========================================  ================================

Three distinguishable answers, so "reached the login page" is a result rather
than an impression. Škoda is absent from :data:`AUTH0_BRANDS` because its
client is not in this tenant at all, and offering it would spend a user's time
on a login that cannot complete.

**Reaching the login page is not the same as signing in.** The code exchange
is unverified from here: it needs a real sign-in, which is the owner's to
perform. Nothing in this module claims otherwise.

Why every function here is additive
-----------------------------------
A second source for fields a car already reports is the exact shape of two
open defects — a stale reading sitting beside a current one, and a resolver
picking between them. So this channel:

* never writes over a credential the entry already holds, and never clears the
  session used for remote commands. A competing implementation cleared it on
  this route and its own tester measured lock and unlock failing immediately
  afterwards;
* reports *unavailable* when it dies, leaving the entry's other channels alone
  rather than raising one failure for the whole account;
* labels every value with its origin, so two candidates are resolved by the
  existing rules instead of by luck.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, quote, urlencode, urlparse

from ..exceptions import AuthenticationError, TokenRefreshRetryError
from ..models import (
    BRAND_AUDI,
    BRAND_CUPRA,
    BRAND_SEAT,
    BRAND_VW_EU,
    BrandConfig,
    TokenSet,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

#: Shared across every brand: one tenant, one pair of endpoints.
AUTHORIZATION_ENDPOINT: Final = "https://group.identity.vwgroup.io/authorize"
TOKEN_ENDPOINT: Final = "https://group.identity.vwgroup.io/oauth/token"

#: The audience is what makes these tokens usable against CARIAD rather than
#: against the legacy identity API. Without it the exchange yields a token the
#: vehicle endpoints refuse.
AUDIENCE: Final = "https://api.cariad.com"

#: ``offline_access`` is what produces a refresh token. Dropping it turns this
#: into a sign-in the user has to repeat every hour. ``email`` is requested on
#: top so the id_token carries the account's e-mail: the config flow uses it to
#: attach a browser sign-in to an existing email+password entry for the same
#: account (falling back to the ``sub`` claim). The tenant returns the claim.
SCOPE: Final = "openid profile email offline_access"

#: Marks a refresh token as belonging to this flow. Two refresh tokens can sit
#: in one store, they are redeemed at different hosts under different
#: audiences, and sending one to the other's endpoint fails with a message that
#: names neither.
REFRESH_TOKEN_PREFIX: Final = "auth0:"

#: Where this channel's readings are attributed. Must be a value the merge path
#: already understands as a source name.
CHANNEL: Final = "auth0"

# The ``TokenSet.strategy`` tag for a session minted by this flow is the literal
# ``"auth0"`` — one generic value across every brand (the brand is already known
# per entry). It is stamped as a literal in ``Auth0Grant._to_tokens`` below, not
# through a constant, because the strategy-label pairing test
# (``test_strategy_labels_are_paired``) only counts a label as *produced* when a
# ``TokenSet(strategy="…")`` carries a string constant. base.py routes a refresh
# on it to the Auth0 endpoint (never the attestation-walled IDK endpoint) and its
# passwordless guard knows the entry holds no password; audi.py skips render
# images for it; the config flow routes a reauth by it.

#: Refresh rejections that are permanent — the refresh token is dead, or the
#: client is no longer allowed to use it — so only a new interactive sign-in
#: can help. Anything else (5xx, rate limit, odd body, network) is transient,
#: and retrying forever on a permanent one would hide a dead account behind a
#: quiet retry on every poll.
_HARD_REFRESH_ERRORS: Final[frozenset[str]] = frozenset(
    {"invalid_grant", "unauthorized_client", "invalid_client"}
)

#: Sent on the token calls. The myAudi app's UA; the token endpoint does not
#: key on it, so one value serves every brand's route.
_USER_AGENT: Final = (
    "Android/5.8.1 (Build 800344777.root project 'myaudi_android'"
    ".ext.buildTime) Android/13"
)
_REQUEST_TIMEOUT_S: Final = 30

#: The brands measured open, keyed the way ``ClientFactory`` spells them. The
#: client id and callback are read from the brand config rather than repeated
#: here: one source, and the test that asserts the literal values then
#: cross-checks the measurement against the configuration.
#:
#: ``volkswagen_commercial`` shares ``BRAND_VW_EU``'s client and callback, so
#: the same probe covers it. It is left out until someone asks for it.
AUTH0_BRANDS: Final[Mapping[str, BrandConfig]] = {
    "volkswagen": BRAND_VW_EU,
    "audi": BRAND_AUDI,
    "cupra": BRAND_CUPRA,
    "seat": BRAND_SEAT,
}

#: Where a sign-in has actually been **completed**, as opposed to merely
#: reaching the login page. The distinction is the whole reason this constant
#: exists, and it is not pedantry:
#:
#: * reaching ``/u/login`` proves the client id and the callback are registered
#:   in this tenant. Measured for all four brands above.
#: * completing the exchange proves the tenant also issues a token for the
#:   CARIAD audience to that client. Evidenced for **Audi only**, by five
#:   independent owners reporting a working sign-in on a competing
#:   implementation, one of them on a fresh setup rather than a re-auth.
#:
#: The app binaries argue for caution rather than against it. A string dump of
#: the current We Connect, MyCupra and MySEAT builds (2026-11-09, with a
#: counter-probe that hit ~24k-29k times, so the zeroes mean something) found
#: **no** login provider for this route: the ``auth0`` strings in MyCupra and
#: MySEAT are the ``com.auth0.android.jwt`` decoding library, and We Connect
#: has none at all. Only the myAudi build ever carried the provider.
#:
#: So three of the four brands stay off until one real sign-in completes. A
#: brand that offers a login which cannot finish spends somebody's evening and
#: reads to them as our defect.
AUTH0_PROVEN: Final[frozenset[str]] = frozenset({"audi"})

#: Where the browser token is verified to reach the **command plane**, not just
#: the read plane. This is a different axis from :data:`AUTH0_PROVEN` (which is
#: about a sign-in completing at all) and deliberately a separate set, because a
#: token that reads a car is not automatically a token that can command it.
#:
#: Measured live on 2026-11-10 with a real myAudi sign-in over this exact route
#: (three vehicles on one account): ``GET .../pendingrequests`` answered **204**
#: on every car — i.e. the Auth0 token is accepted on the CARIAD command
#: namespace (``emea.bff.cariad.digital/vehicle/v1/vehicles/{vin}/...``), not
#: 401/403. The S6 C8 also read ``selectivestatus`` 207 and ``capabilities``
#: 200 on the same token. Commands route through ``_post_command`` on that same
#: session (no MBB connector needed), so lock/climate/charge entities have a
#: real path for Audi. The write itself was not force-tested on the car (the
#: owner declined actuating it), so a server-side command refusal, if any, is
#: surfaced honestly by ``classify_command_failure`` rather than hidden.
#:
#: Only Audi is listed: the other reachable brands either never complete the
#: exchange (Volkswagen, see :data:`AUTH0_DENIED`) or have an attestation-walled
#: command backend (SEAT/CUPRA, forced read-only in the coordinator by brand).
AUTH0_TWOWAY: Final[frozenset[str]] = frozenset({"audi"})

#: Reachable in this tenant but **never offered**: the sign-in page loads, yet
#: the exchange cannot complete, so offering it would spend an owner's evening on
#: a route that reads as our defect. Measured live on 2026-11-09/10: the
#: Volkswagen client reaches ``/authorize`` but the ``localhost`` callback is
#: answered *Callback URL mismatch* (302 to ``/v2/login/ui/error``) and the code
#: exchange returns ``401 access_denied`` — the We Connect build carries no
#: Auth0 login provider at all (string dump, ~24k-hit counter-probe). Kept in
#: :data:`AUTH0_BRANDS` (the module still documents the route) but gated out of
#: :func:`is_offered` even with ``include_unproven`` — a switch that could turn
#: on a guaranteed failure would be a defect, not a feature.
AUTH0_DENIED: Final[frozenset[str]] = frozenset({"volkswagen"})


@dataclass(frozen=True)
class Route:
    """One way to reach the same browser sign-in, bound as a whole.

    The pieces travel together because a cross-check of the design (two
    independent model families, 2026-11-09) and RFC 6749 §4.1.3 agree on the
    same point: the ``redirect_uri`` used at the token exchange must be byte-for
    byte the one used at ``/authorize``. So the route is a sealed tuple, never
    assembled from a user's choice or from a pasted URL — a mismatch must be
    impossible rather than merely discouraged.

    ``catchable`` records whether a desktop browser actually lands on the
    callback so the user can copy it. A custom app scheme (``weconnect://``,
    ``myaudi:///``) does **not** show in the address bar — the 302 to it leaves
    the browser on the previous page, and on a phone the native app intercepts
    it. Only an ``http://localhost`` style callback is copyable without
    DevTools. This is the single most load-bearing fact for the step's UX and it
    was the cross-check's sharpest finding.
    """

    key: str  # "direct" | "bff"
    authorize_url: str
    token_url: str
    client_id: str
    redirect_uri: str
    catchable: bool


class Auth0NotAvailable(RuntimeError):
    """This brand has no browser sign-in on this tenant.

    Raised before anything is sent. Škoda's client id answers *Unknown client*,
    so starting the flow would produce a failure that reads as ours.
    """


class Auth0RedirectInvalid(RuntimeError):
    """The pasted redirect did not carry a code bound to this login attempt.

    Its message never contains the pasted text — the whole point is to keep the
    authorization code out of logs and tracebacks.
    """


class Auth0ExchangeFailed(RuntimeError):
    """The code exchange did not yield a usable token."""


class Auth0Denied(Auth0RedirectInvalid):
    """The owner cancelled or refused the sign-in on the provider's page.

    A subtype of :class:`Auth0RedirectInvalid` — a denial is still an invalid
    redirect, so a caller that catches the base class keeps working — but the
    config flow catches this first, to say *you cancelled* rather than *that is
    the wrong address*.
    """


def is_offered(brand: str, *, include_unproven: bool = False) -> bool:
    """Whether to put this sign-in in front of an owner of this brand.

    Three gates, and the order matters. A brand whose client this tenant does
    not hold can **never** be offered, not even with ``include_unproven``: that
    is a measured absence, not a cautious default, and a switch that could
    override it would be a switch that produces a guaranteed failure. A brand on
    the denied list (reachable but with an exchange that cannot complete, see
    :data:`AUTH0_DENIED`) is also never offered, for the same reason. A brand
    that is reachable, not denied, but unproven is offered only when the caller
    says it accepts an unfinished route.
    """
    b = brand.lower()
    if b not in AUTH0_BRANDS:
        return False
    if b in AUTH0_DENIED:
        return False
    if b in AUTH0_PROVEN:
        return True
    return include_unproven


# ---------------------------------------------------------------------------
# The two routes, per brand. Populated only where there is evidence.
#
# DIRECT is the host a competing implementation drives and the one measured to
# reach ``/u/login`` for all four brands. BFF is the path the vendor's own app
# uses — confirmed from the current We Connect build for Volkswagen only
# (``emea.bff.cariad.digital/auth/v1/auth0/authorize`` with the
# ``weconnect://authenticated-auth0`` callback). It is left absent for the
# other brands rather than guessed: an invented BFF host would fail in a way
# that reads as our defect.

_DIRECT_AUTHORIZE: Final = "https://group.identity.vwgroup.io/authorize"
_DIRECT_TOKEN: Final = "https://group.identity.vwgroup.io/oauth/token"

#: The one catchable callback that is actually registered: a competing
#: implementation proved ``localhost:8080`` works for Audi's client. The probe
#: showed the other three brands answer *Callback URL mismatch* for localhost,
#: so only Audi gets the copy-from-address-bar UX; the rest need the Location
#: header.
_AUDI_LOCALHOST: Final = "http://localhost:8080/myaudi-callback"


def routes_for(brand: str) -> tuple[Route, ...]:
    """Return the sealed routes available for a brand, direct first.

    Empty for a brand this tenant does not hold. The caller offers these; it
    never builds a route itself.
    """
    cfg = AUTH0_BRANDS.get(brand.lower())
    if cfg is None:
        return ()

    # One client id for authorize, exchange AND refresh. Audi's market config
    # may rotate it (:func:`resolve_client_id`); the route carries the resolved
    # value, so the exchange and the later refresh use the same client — never
    # the static brand-config literal for one and the rotated one for the other.
    client_id = resolve_client_id(brand)
    out: list[Route] = []

    # DIRECT. Audi has a catchable localhost callback; the others only their
    # app scheme, which a desktop browser will not surrender without DevTools.
    if brand.lower() == "audi":
        out.append(Route("direct", _DIRECT_AUTHORIZE, _DIRECT_TOKEN,
                         client_id, _AUDI_LOCALHOST, catchable=True))
    out.append(Route("direct-app", _DIRECT_AUTHORIZE, _DIRECT_TOKEN,
                     client_id, cfg.redirect_uri, catchable=False))

    # BFF: Volkswagen only, from the app binary.
    if brand.lower() == "volkswagen":
        out.append(Route(
            "bff",
            "https://emea.bff.cariad.digital/auth/v1/auth0/authorize",
            "https://emea.bff.cariad.digital/auth/v1/auth0/token",
            client_id,
            "weconnect://authenticated-auth0",
            catchable=False,
        ))
    return tuple(out)


def new_state() -> str:
    """An opaque value binding a pasted redirect to this login attempt.

    Without it, a code pasted back cannot be tied to the attempt that produced
    it (RFC 6749 §10.12). Held in a private flow attribute next to the verifier,
    and checked on paste.
    """
    return secrets.token_urlsafe(24)


def parse_redirect(pasted: str, *, expected_redirect_uri: str,
                   expected_state: str) -> str:
    """Pull the authorization code out of a pasted redirect, or refuse.

    Accepts either the full redirect URL or a bare ``code`` (some callbacks are
    app schemes a browser will not show, so a tester may read only the code from
    DevTools). A full redirect is bound to this attempt by its ``state``; a bare
    code carries none and is bound instead by the PKCE verifier the exchange
    repeats — an unrelated string pasted as a bare code produces a token
    exchange that fails, not a sign-in to the wrong account.

    This function is the reason the pasted value is treated as a secret: it is
    parsed here and nowhere logged. Every refusal raises
    :class:`Auth0RedirectInvalid` with a message that does **not** echo the
    input, so an authorization code cannot reach a log line or a traceback.
    """
    text = (pasted or "").strip()
    if not text:
        raise Auth0RedirectInvalid("no redirect was pasted")

    # A bare code: no scheme, no query. Then state cannot be checked from the
    # URL, so it must be supplied to match — a bare code is accepted only when
    # the caller already knows the state is right (single-attempt flow).
    if "://" not in text and "?" not in text and "#" not in text:
        if any(ch.isspace() for ch in text):
            raise Auth0RedirectInvalid("the pasted value is not a bare code")
        return text

    # Tolerate a paste without a scheme ("localhost:8080/myaudi-callback?…")
    # when the route's callback is an http(s) one.
    if text.startswith("localhost") and expected_redirect_uri.startswith("http"):
        text = "http://" + text

    try:
        parsed = urlparse(text)
        # Touch the authority fields inside the guard: a bad port or an
        # unbalanced IPv6 raises ``ValueError`` here, and its message can carry
        # the pasted text — e.g. a code dropped into the port position
        # (``localhost:<code>``). That must never reach a traceback.
        parsed_host, parsed_port, parsed_path = (
            parsed.hostname, parsed.port, parsed.path)
    except ValueError:
        raise Auth0RedirectInvalid(
            "the pasted redirect is not a valid callback address"
        ) from None
    # Bind to the route's own callback. A redirect for a different scheme is a
    # redirect from a different attempt or a different route. For a catchable
    # http(s) callback the host, port and path must match exactly too — a
    # ``localhost:9999`` or ``/other`` paste is not this route's callback.
    if expected_redirect_uri:
        exp = urlparse(expected_redirect_uri)
        if parsed.scheme != exp.scheme:
            raise Auth0RedirectInvalid(
                "the pasted redirect does not match the route's callback scheme"
            )
        if exp.scheme in ("http", "https") and (
            parsed_host != exp.hostname
            or parsed_port != exp.port
            or parsed_path.rstrip("/") != exp.path.rstrip("/")
        ):
            raise Auth0RedirectInvalid(
                "the pasted redirect is not this route's callback address"
            )

    # The code and state live in the query or, for some providers, the fragment.
    # Read the fragment first so the query — the code flow's own location —
    # wins when a redirect carries both.
    params: dict[str, list[str]] = {}
    if parsed.fragment:
        params.update(parse_qs(parsed.fragment))
    params.update(parse_qs(parsed.query))

    if "error" in params:
        raise Auth0Denied(
            "the redirect carried an error rather than a code"
        )
    got_state = (params.get("state") or [""])[0]
    if not secrets.compare_digest(got_state, expected_state):
        raise Auth0RedirectInvalid(
            "the redirect's state does not match this login attempt"
        )
    code = (params.get("code") or [""])[0]
    if not code:
        raise Auth0RedirectInvalid("the redirect carried no authorization code")
    return code


def new_pkce_pair() -> tuple[str, str]:
    """Return a fresh ``(verifier, challenge)`` pair.

    The verifier stays in the config flow; only the challenge travels. A wrong
    pair is invisible at the authorize step — the login page still appears —
    and fails later at the exchange with a message that does not mention PKCE,
    which is why the pairing is pinned by a test rather than trusted.
    """
    verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(32))
        .decode("ascii")
        .rstrip("=")
    )
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def authorization_url(
    *, brand: str, code_challenge: str, state: str, nonce: str,
) -> str:
    """Build the URL the owner opens in a browser.

    Raises :class:`Auth0NotAvailable` for a brand this tenant does not hold.

    The client id and the callback travel together on purpose: the measurement
    showed a brand's client is accepted only with the callback that brand
    registers, and mixing them answers *Callback URL mismatch*.
    """
    cfg = AUTH0_BRANDS.get(brand.lower())
    if cfg is None:
        raise Auth0NotAvailable(
            f"{brand} has no browser sign-in on this tenant; its client id is "
            f"not held there, so the login could not complete"
        )
    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "audience": AUDIENCE,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "nonce": nonce,
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params, quote_via=quote)}"


def token_request_body(
    *, brand: str, code: str, code_verifier: str,
) -> dict[str, str]:
    """The form body for the code exchange.

    Separated from the transport so the shape can be asserted without a
    network call, and so the verifier appears in exactly one place.
    """
    cfg = AUTH0_BRANDS.get(brand.lower())
    if cfg is None:
        raise Auth0NotAvailable(f"{brand} has no browser sign-in")
    return {
        "client_id": cfg.client_id,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": cfg.redirect_uri,
    }


# ---------------------------------------------------------------------------
# Route-aware builders. ``authorization_url`` / ``token_request_body`` above key
# on the brand's default (app-scheme) callback. A :class:`Route` may carry a
# DIFFERENT callback — Audi's catchable ``http://localhost:8080`` is the reason
# these exist — and RFC 6749 §4.1.3 requires the token exchange to repeat the
# exact ``redirect_uri`` used at authorize. So when a route was chosen, both
# steps must be built from that route, not from the brand default, or the two
# disagree and the exchange is refused.


def authorization_url_for(
    route: Route, *, code_challenge: str, state: str, nonce: str,
    ui_locales: str = "",
) -> str:
    """Build the authorize URL for a specific chosen route.

    ``ui_locales`` (e.g. ``de-DE``) asks the provider to render its login page
    in the owner's language; omitted, the provider picks its own default.
    """
    params = {
        "client_id": route.client_id,
        "redirect_uri": route.redirect_uri,
        "audience": AUDIENCE,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "nonce": nonce,
    }
    if ui_locales:
        params["ui_locales"] = ui_locales
    # ``quote_via=quote`` so the scope's spaces travel as %20, as the app sends
    # them, not as "+".
    return f"{route.authorize_url}?{urlencode(params, quote_via=quote)}"


def token_body_for(
    route: Route, *, code: str, code_verifier: str,
) -> dict[str, str]:
    """Build the code-exchange body for a specific chosen route.

    Uses the route's own ``redirect_uri`` so it matches the authorize step
    byte-for-byte.
    """
    return {
        "client_id": route.client_id,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": route.redirect_uri,
    }


def read_token_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a token payload before anything is stored.

    A 200 carrying ``token_type`` and ``expires_in`` but no ``access_token``
    reads as success to a caller that only checks the status code. That shape
    is the one worth refusing loudly.
    """
    if not payload.get("access_token"):
        raise Auth0ExchangeFailed(
            "the token response carried no access_token; "
            f"keys present: {sorted(payload)}"
        )
    return dict(payload)


def classify_refusal(payload: Mapping[str, Any]) -> str:
    """Name which wall was hit: ``expired``, ``callback``, ``unknown_client``,
    ``attestation`` — or ``unknown``.

    A competing implementation treats ``invalid_grant`` and ``invalid assertion
    headers`` as one re-auth trigger. They are not one situation: the first is
    a session that ran out and signing in again fixes it, the second is a door
    that was never open and signing in again cannot. Telling someone to retry
    an impossible step is worse than telling them nothing.

    The description is read before the bare code, because ``invalid_request``
    carries two distinct meanings here.
    """
    code = str(payload.get("error") or "").strip().lower()
    desc = str(payload.get("error_description") or "").lower()

    if "invalid assertion headers" in desc:
        return "attestation"
    if "unknown client" in desc:
        return "unknown_client"
    if "callback url mismatch" in desc:
        return "callback"
    if code == "invalid_grant":
        return "expired"
    if code == "unauthorized_client":
        return "callback"
    return "unknown"


def mark_refresh_token(token: str) -> str:
    """Tag a refresh token as this flow's."""
    if token.startswith(REFRESH_TOKEN_PREFIX):
        return token
    return f"{REFRESH_TOKEN_PREFIX}{token}"


def is_auth0_refresh_token(token: str) -> bool:
    """Whether a stored refresh token belongs to this flow."""
    return token.startswith(REFRESH_TOKEN_PREFIX)


def attach_session(
    entry: Mapping[str, Any], *, brand: str, result: Mapping[str, Any],
) -> dict[str, Any]:
    """Add this channel's tokens to an entry, leaving its own untouched.

    ``brand`` is accepted and validated so a caller cannot attach a session for
    a brand that has no browser sign-in; the stored shape does not depend on
    it.
    """
    if brand.lower() not in AUTH0_BRANDS:
        raise Auth0NotAvailable(f"{brand} has no browser sign-in")

    out: dict[str, Any] = {k: v for k, v in entry.items() if k != "tokens"}
    tokens = dict(entry.get("tokens") or {})
    if result.get("access_token"):
        tokens["auth0_access"] = result["access_token"]
    if result.get("refresh_token"):
        tokens["auth0_refresh"] = result["refresh_token"]
    out["tokens"] = tokens
    return out


def apply_channel_failure(
    state: Mapping[str, Any], *, brand: str,  # noqa: ARG001
) -> dict[str, Any]:
    """Mark this channel unavailable without disturbing the rest of the entry.

    This is the behaviour the whole design exists for. One optional channel
    going quiet is not a reason to send an account to a re-auth prompt, and it
    is certainly not a reason to drop the session that performs remote
    commands — which is what a competing implementation did on this route.
    """
    out: dict[str, Any] = {
        k: v for k, v in state.items() if k not in ("channels", "tokens")
    }
    channels = dict(state.get("channels") or {})
    channels[CHANNEL] = "unavailable"
    out["channels"] = channels
    # Copied through unchanged, deliberately: the command session and the
    # native session are not this channel's to invalidate.
    out["tokens"] = dict(state.get("tokens") or {})
    if "field_sources" in state:
        out["field_sources"] = dict(state["field_sources"])
    return out


def label_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Attach this channel's name to every reading it delivered.

    Without an origin a value cannot be weighed against a second candidate for
    the same field, and the resolver falls back to a rule that was written for
    one source. Two open reports are that failure.
    """
    return {
        "fields": dict(fields),
        "field_sources": {key: CHANNEL for key in fields},
    }


# ---------------------------------------------------------------------------
# Reading the id_token, resolving a brand's live client id, and the async token
# client. These are the integration-facing half: the pure builders above shape
# the request, this half carries it and mints a TokenSet.


def id_token_claims(id_token: str) -> dict[str, Any]:
    """Decode the public payload of a JWT. Never raises; no signature check.

    Used only to read the account's ``email`` (or ``sub``) so a browser sign-in
    can attach to an existing entry for the same account. A malformed or empty
    token yields ``{}`` — a missing claim must not turn a successful sign-in
    into a failure.
    """
    if not isinstance(id_token, str):
        return {}
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def resolve_client_id(brand: str) -> str:
    """The client id to drive a brand's sign-in with.

    The brand config is the single source. Audi additionally lets the market
    config rotate it (``idkClientIDAndroidLive``); most markets do not carry
    the key, so the brand-config literal is what runs in practice. Raises
    :class:`Auth0NotAvailable` for a brand this tenant does not hold, so a
    caller cannot resolve a client for a login that cannot complete.
    """
    cfg = AUTH0_BRANDS.get(brand.lower())
    if cfg is None:
        raise Auth0NotAvailable(f"{brand} has no browser sign-in on this tenant")
    if brand.lower() == "audi":
        try:
            from ._audi_market_config import (  # noqa: PLC0415
                cached_audi_market_config,
            )

            override = cached_audi_market_config().get("idkClientIDAndroidLive")
        except Exception:  # noqa: BLE001 — the cache is best-effort
            override = None
        if isinstance(override, str) and "@apps_vw-dilab_com" in override:
            return override
    return cfg.client_id


def _oauth_error(payload: Any) -> tuple[str, str]:
    """``(error, error_description)`` from a token error payload, else ``("", "")``."""
    if not isinstance(payload, Mapping):
        return "", ""
    return (
        str(payload.get("error") or ""),
        str(payload.get("error_description") or ""),
    )


class Auth0Grant:
    """Token client for a brand's public Auth0 client.

    Bound to a brand, because a refresh carries no route and must still reach
    the right endpoint and client. The code exchange is bound to a
    :class:`Route` instead: the ``redirect_uri`` it repeats has to be the one
    the ``/authorize`` step used (RFC 6749 §4.1.3), and that lives on the route.
    """

    def __init__(
        self,
        session: ClientSession,
        *,
        brand: str,
        client_id: str | None = None,
    ) -> None:
        self._session = session
        self._brand = brand.lower()
        self._client_id = client_id or resolve_client_id(brand)

    @property
    def client_id(self) -> str:
        return self._client_id

    async def _post_token(
        self, url: str, data: Mapping[str, str], context: str,
    ) -> tuple[int, Any]:
        from aiohttp import ClientTimeout  # noqa: PLC0415

        # Encode by hand so the scope's spaces travel as %20 (what the app
        # sends) rather than aiohttp's form default "+".
        body = urlencode(dict(data), quote_via=quote)
        headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _USER_AGENT,
        }
        try:
            async with self._session.post(
                url,
                data=body,
                headers=headers,
                allow_redirects=False,
                timeout=ClientTimeout(total=_REQUEST_TIMEOUT_S),
            ) as resp:
                status = resp.status
                payload = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001 — network / decode
            raise TokenRefreshRetryError(
                f"{context}: request failed ({type(exc).__name__})"
            ) from exc
        return status, payload

    @staticmethod
    def _to_tokens(
        payload: Mapping[str, Any],
        *,
        fallback_refresh: str = "",
        fallback_id: str = "",
    ) -> TokenSet:
        try:
            expires_in = int(payload.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        return TokenSet(
            access_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or "") or fallback_refresh,
            id_token=str(payload.get("id_token") or "") or fallback_id,
            expires_at=time.time() + expires_in - 60,
            strategy="auth0",  # literal — see the strategy-tag note above
        )

    async def exchange_code(
        self, route: Route, code: str, code_verifier: str,
    ) -> TokenSet:
        """Trade an authorization code for a token set on ``route``.

        A refused code raises :class:`AuthenticationError` — a code is single
        use, so the config flow starts a fresh attempt rather than retrying. A
        network failure is a :class:`TokenRefreshRetryError`.
        """
        status, payload = await self._post_token(
            route.token_url,
            token_body_for(route, code=code, code_verifier=code_verifier),
            "Auth0 code exchange",
        )
        if (
            status != 200
            or not isinstance(payload, Mapping)
            or not payload.get("access_token")
        ):
            err, desc = _oauth_error(payload)
            _LOGGER.warning(
                "Auth0 code exchange rejected: HTTP %d %s "
                "(%d-byte description withheld)",
                status, err or "(no error code)", len(desc),
            )
            raise AuthenticationError(
                f"Auth0 code exchange rejected: HTTP {status} {err}".rstrip()
            )
        tokens = self._to_tokens(payload)
        if not tokens.refresh_token:
            raise AuthenticationError("Auth0 did not issue a refresh token")
        if not tokens.id_token:
            raise AuthenticationError("Auth0 did not issue an id_token")
        _LOGGER.info(
            "Auth0 sign-in succeeded for %s (expires_in=%ss)",
            self._brand, payload.get("expires_in"),
        )
        return tokens

    async def refresh(self, refresh_token: str, *, id_token: str = "") -> TokenSet:
        """Refresh at the brand's Auth0 token endpoint.

        ``invalid_grant`` means the refresh token is dead →
        :class:`AuthenticationError` so the caller starts a reauth. Everything
        else (5xx, network, odd body) → :class:`TokenRefreshRetryError` so the
        next poll simply tries again. An unrotated refresh token is kept, and
        so is the previous ``id_token`` when the response carries none
        (``TokenSet.is_valid`` needs one); the strategy tag is preserved.
        """
        status, payload = await self._post_token(
            TOKEN_ENDPOINT,
            {
                "client_id": self._client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "audience": AUDIENCE,
                "scope": SCOPE,
            },
            "Auth0 refresh",
        )
        if (
            status != 200
            or not isinstance(payload, Mapping)
            or not payload.get("access_token")
        ):
            err, desc = _oauth_error(payload)
            if err.lower() in _HARD_REFRESH_ERRORS:
                _LOGGER.warning(
                    "Auth0 refresh token rejected (%s) — a new browser sign-in "
                    "is needed", err,
                )
                raise AuthenticationError(
                    f"Auth0 refresh rejected: HTTP {status} {err}"
                )
            raise TokenRefreshRetryError(
                f"Auth0 refresh: transient rejection HTTP {status} "
                f"{err or '(no error code)'} ({len(desc)}-byte description "
                f"withheld)"
            )
        return self._to_tokens(
            payload, fallback_refresh=refresh_token, fallback_id=id_token
        )
