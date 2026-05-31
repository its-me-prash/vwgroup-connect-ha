# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.6.0 — OAuth 2.0 Device Authorization Grant (RFC 8628).

This module implements the standard headless-device OAuth flow:

  1. Client POSTs to the IDP's ``device_authorization_endpoint`` with
     ``client_id`` and ``scope`` → receives ``device_code``,
     ``user_code``, ``verification_uri``, ``verification_uri_complete``,
     ``expires_in`` and ``interval``.
  2. The end user is shown the verification URI plus the short
     ``user_code``. They open the URI in a browser, sign in with their
     Brand ID credentials, and approve the device.
  3. The client polls the IDP's ``token_endpoint`` with
     ``grant_type=urn:ietf:params:oauth:grant-type:device_code`` until
     either the user approves (200 + tokens) or the grant fails / times
     out (4xx with an RFC 8628 error code).

## Why this is the preferred strategy

- The flow is a standard OIDC/OAuth2 grant. No Play Integrity, no
  client_assertion, no app-attestation. The 2026-05-27 WAF migration
  does not affect ``identity.vwgroup.io/oidc/v1/*`` endpoints — those
  are the IDP itself, not the BFF.
- The IDP returns a real ``refresh_token``, so we avoid the ~2 h
  re-login penalty of the hybrid_full strategy.
- The user never types their credentials into Home Assistant; the
  browser session at identity.vwgroup.io handles them directly.
  Smaller blast radius if HA storage leaks.
- Mirrors the implementation Audi's own app uses internally — verified
  by inspection of ``technology.cariad.cat.idk.deviceflow.DeviceFlowRequest``
  in the myAudi 5.5.0 APK. That class implements the exact same RFC
  8628 surface (``device_code`` / ``user_code`` / ``verification_uri``
  / ``verification_uri_complete`` / ``expires_in`` / ``interval``) and
  handles the same four error codes (``authorization_pending``,
  ``slow_down``, ``expired_token``, ``access_denied``). We do not copy
  any code; we re-implement the standard from scratch using only the
  RFC and the public OIDC discovery doc at
  ``https://identity.vwgroup.io/.well-known/openid-configuration``.

## Brand coverage

- ✅ Audi (client_id ``09b6cbec-…`` + ``f4d0934f-…`` both whitelisted)
- ✅ Skoda (client_id ``7f045eee-…``)
- ✅ SEAT (client_id ``99a5b77d-…``)
- ✅ CUPRA (client_id ``3c756d46-…``)
- ❌ Volkswagen EU (client_id ``a24fba63-…`` returns ``unauthorized_client``
  — VW has not enabled device-grant on the consumer VW EU client.
  Falls back to hybrid_full + classic chain instead.)

## Two operating modes

The module supports two distinct call patterns to fit different UX
shapes inside Home Assistant:

1. **Coordinated** — ``request_device_code()`` to start the flow,
   surface ``user_code`` + ``verification_uri_complete`` to the user
   via ``persistent_notification`` (or config_flow show_form), then
   call ``poll_for_tokens(device_code, interval, expires_in)`` from a
   background task. The polling loop completes when the user approves
   or the grant expires.

2. **One-shot** — ``run()`` returns a ``TokenSet`` after the full
   request → notify → poll sequence, blocking until either success or
   timeout. Best for config_flow setup where the user already knows
   they are about to be redirected to a browser.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from aiohttp import ClientSession

from ..exceptions import AuthenticationError
from ..models import TokenSet

_LOGGER = logging.getLogger(__name__)


# IDP endpoints (both shared across all VW Group Brand IDs).
_IDP_DEVICE_AUTH_URL = "https://identity.vwgroup.io/oidc/v1/device_authorization"
_IDP_TOKEN_URL = "https://identity.vwgroup.io/oidc/v1/token"

# Conservative HTTP request timeout. The device_authorization POST is
# fast (< 1 s on the IDP side); the token-poll request must finish
# inside the polling interval the IDP told us to use, so 10 s is plenty.
_REQUEST_TIMEOUT_S = 10

# Hard cap on poll duration regardless of what the IDP says — defensive
# in case the IDP returns expires_in 0 or an unreasonable number. RFC
# 8628 § 3.3 suggests up to ~30 minutes is reasonable; 15 min is a
# pragmatic Home Assistant ceiling.
_MAX_POLL_DURATION_S = 900


@dataclass(frozen=True)
class DeviceCodeResponse:
    """Result of a successful ``/device_authorization`` POST.

    Mirrors the RFC 8628 § 3.2 response shape. All fields are required
    by the spec; the ``verification_uri_complete`` is optional in the
    RFC but VW always returns it (it encodes the ``user_code`` into
    the URL so the user only has to click once instead of typing the
    code into a form).
    """

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


class DeviceAuthorizationGrant:
    """RFC 8628 client for the VW Group Brand ID IDP.

    Stateless across calls — the device_code value drives the polling
    loop and the caller owns it (so HA can persist it across restart
    if needed, though we generally finish a flow in a single
    config_flow step).
    """

    def __init__(
        self,
        session: "ClientSession",
        client_id: str,
        *,
        scope: str = "openid profile",
    ) -> None:
        """Initialise with the brand-specific OAuth client_id + scope.

        Args:
            session: an aiohttp ClientSession.
            client_id: the VW Brand ID OAuth client_id. Must be one
                of the brand IDs whitelisted by VW for the device
                grant (see module docstring for the supported set).
            scope: OIDC scope string. Default ``"openid profile"``
                works across all whitelisted brands. Callers can
                widen the scope to include brand-specific claims if
                a later use case requires them (e.g. ``cars vin`` for
                vehicle access).
        """
        self._session = session
        self._client_id = client_id
        self._scope = scope

    async def request_device_code(self) -> DeviceCodeResponse:
        """Start the flow — call ``/device_authorization`` once.

        Returns:
            ``DeviceCodeResponse`` with the polling parameters. The
            user_code + verification_uri_complete are what gets shown
            to the end user.

        Raises:
            AuthenticationError: if the IDP rejects the client_id
            (``unauthorized_client``) or returns any non-200 status.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        try:
            async with self._session.post(
                _IDP_DEVICE_AUTH_URL,
                data={"client_id": self._client_id, "scope": self._scope},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=ClientTimeout(total=_REQUEST_TIMEOUT_S),
            ) as resp:
                status = resp.status
                payload = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(
                f"Device grant: /device_authorization request failed ({exc})"
            ) from exc

        if status != 200:
            err = payload.get("error", f"http_{status}")
            err_desc = payload.get("error_description", "")
            raise AuthenticationError(
                f"Device grant: /device_authorization HTTP {status} "
                f"({err}): {err_desc}"
            )

        # All required fields per RFC 8628 § 3.2
        required = ("device_code", "user_code", "verification_uri", "expires_in")
        missing = [k for k in required if k not in payload]
        if missing:
            raise AuthenticationError(
                f"Device grant: /device_authorization response missing "
                f"required fields: {missing}"
            )

        return DeviceCodeResponse(
            device_code=str(payload["device_code"]),
            user_code=str(payload["user_code"]),
            verification_uri=str(payload["verification_uri"]),
            verification_uri_complete=str(
                payload.get("verification_uri_complete", payload["verification_uri"])
            ),
            expires_in=int(payload["expires_in"]),
            # RFC 8628 § 3.2: interval is optional, default 5 seconds
            interval=int(payload.get("interval", 5)),
        )

    async def poll_for_tokens(
        self,
        device_code: str,
        *,
        interval: int = 5,
        expires_in: int = 300,
    ) -> TokenSet:
        """Poll ``/token`` until the user approves or the grant expires.

        Loops sending ``grant_type=device_code`` POSTs at the IDP's
        requested interval. RFC 8628 § 3.5 error codes drive the loop:

        - ``authorization_pending`` → keep polling (default case)
        - ``slow_down`` → bump the interval by 5 s and continue
        - ``expired_token`` → raise (the user took too long)
        - ``access_denied`` → raise (the user declined)
        - any other error → raise

        Returns:
            ``TokenSet`` with ``strategy="device_grant"``,
            ``access_token``, ``refresh_token`` (real one, no
            re-login workaround needed) and ``id_token``.

        Raises:
            AuthenticationError: on grant expiry, user decline, or
            any unexpected IDP response.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        deadline = time.monotonic() + min(expires_in, _MAX_POLL_DURATION_S)
        current_interval = max(1, interval)

        while True:
            if time.monotonic() >= deadline:
                raise AuthenticationError(
                    "Device grant: polling deadline reached before user "
                    "approved — please retry from the config flow"
                )

            await asyncio.sleep(current_interval)

            try:
                async with self._session.post(
                    _IDP_TOKEN_URL,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": device_code,
                        "client_id": self._client_id,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                    timeout=ClientTimeout(total=_REQUEST_TIMEOUT_S),
                ) as resp:
                    status = resp.status
                    payload = await resp.json(content_type=None)
            except Exception as exc:  # noqa: BLE001
                # Transient network errors during a polling loop are
                # expected — log and continue. The deadline check at
                # loop top guards against infinite retry.
                _LOGGER.debug(
                    "Device grant: poll request failed (%s) — retrying",
                    exc,
                )
                continue

            if status == 200:
                access_token = payload.get("access_token", "")
                id_token = payload.get("id_token", "")
                if not access_token or not id_token:
                    raise AuthenticationError(
                        "Device grant: /token returned 200 but no "
                        f"access_token/id_token — payload keys: "
                        f"{list(payload.keys())}"
                    )
                refresh_token = payload.get("refresh_token", "")
                expires_at = (
                    time.time() + int(payload.get("expires_in", 3600)) - 60
                )
                _LOGGER.info(
                    "Device grant: user approved — token set acquired "
                    "(refresh_token present: %s, expires in %ds)",
                    bool(refresh_token),
                    int(payload.get("expires_in", 3600)),
                )
                return TokenSet(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    id_token=id_token,
                    expires_at=expires_at,
                    strategy="device_grant",
                )

            err = payload.get("error", "")
            if err == "authorization_pending":
                # Expected — user has not approved yet. Continue
                # polling at the IDP's stated interval.
                continue
            if err == "slow_down":
                # RFC 8628 § 3.5: server is asking us to back off.
                # Increase interval by 5 s per the spec.
                current_interval += 5
                _LOGGER.debug(
                    "Device grant: slow_down — increasing poll interval "
                    "to %d s",
                    current_interval,
                )
                continue
            if err == "expired_token":
                raise AuthenticationError(
                    "Device grant: the user_code expired before the "
                    "user completed the browser approval"
                )
            if err == "access_denied":
                raise AuthenticationError(
                    "Device grant: the user declined the device "
                    "authorization in the browser"
                )

            # Anything else is unexpected — surface it verbatim so
            # debugging the IDP-side change is easy.
            err_desc = payload.get("error_description", "")
            raise AuthenticationError(
                f"Device grant: unexpected /token error {status} "
                f"({err}): {err_desc}"
            )

    async def run(
        self,
        on_user_code: Callable[[DeviceCodeResponse], None] | None = None,
    ) -> TokenSet:
        """End-to-end convenience method.

        Issues the device_code, calls ``on_user_code`` so the caller
        can surface the URL + code to the end user, then polls until
        completion. Returns the resulting TokenSet.

        For config_flow integration the caller typically returns a
        ``show_form`` from inside ``on_user_code`` to display the
        URL + code; that requires hand-rolling the show_form/poll
        split so HA can render the form between the two halves.
        ``request_device_code`` + ``poll_for_tokens`` separately are
        better-suited for that pattern; ``run`` is the one-shot
        convenience for scripts and tests.
        """
        code = await self.request_device_code()
        if on_user_code is not None:
            try:
                on_user_code(code)
            except Exception:  # noqa: BLE001 — caller's callback, do not block flow
                _LOGGER.warning(
                    "Device grant: on_user_code callback raised — "
                    "continuing with poll loop anyway"
                )
        return await self.poll_for_tokens(
            code.device_code,
            interval=code.interval,
            expires_in=code.expires_in,
        )


# ── Brand → DAG eligibility map ───────────────────────────────────────────
#
# Source: live HTTP probe on 2026-05-30 + re-probe 2026-05-31 of
# ``identity.vwgroup.io/oidc/v1/device_authorization`` with each known
# brand client_id. The brands listed here received a 200 + valid
# device_code response.
#
# VW EU client_ids tested 2026-05-31 (none DAG-eligible):
#   - a24fba63-…@apps_vw-dilab_com  (canonical) → HTTP 400 empty body
#   - 4edc53db-…@apps_vw-dilab_com  (VW 3.61.0 alt) → HTTP 400 empty body
#   - 16dd7960-…@apps_vw-dilab_com  (cross-found in Audi APK) → HTTP 400
# (rejection mode shifted from "403 unauthorized_client" on 2026-05-30
# to "400 empty body" on 2026-05-31 — VW tightened error surface; the
# client is still not whitelisted either way.)
#
# Update when VW expands the whitelist.
DAG_ENABLED_BRANDS = frozenset({"audi", "skoda", "seat", "cupra"})


def is_dag_eligible(brand_name: str) -> bool:
    """Return True if Device Authorization Grant is known to work for
    the given brand. Strategy resolver in base.py consults this before
    putting DAG at the head of the chain."""
    return brand_name.lower() in DAG_ENABLED_BRANDS
