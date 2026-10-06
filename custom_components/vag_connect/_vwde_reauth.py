# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The volkswagen.de re-login mechanics, shared by two flows.

#1717 — the "needs re-login" repair used to hand the user off by starting the
options flow from the backend, which Home Assistant never presents, and then
marked itself resolved anyway: the notice vanished and nothing happened. For the
repair to carry the login itself it needs these steps, and the options flow
already had them.

Moved here rather than reimplemented. The error classification below was
hardened over several reports (a redirect loop, an expired SSO session and a
portal outage all used to report "wrong password"), and a second copy would
drift away from it. Both flows now inherit exactly one implementation.

Consumers must provide ``self.hass`` and ``self._config_entry``, and initialise
the ``_ovw_*`` attributes — :meth:`VwDeReauthMixin.ovw_reset` does that.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class VwDeReauthMixin:
    """The vw.de login: credentials, optional e-mail code, cookie capture."""

    # Supplied by whichever flow mixes this in — declarations only, so no class
    # attribute is created and the host's own ``hass`` is not shadowed. The
    # entry is ``Any`` rather than ``ConfigEntry`` because the repair flow holds
    # None until one of its steps looks the entry up, while the options flow is
    # handed a real one in __init__.
    hass: HomeAssistant
    _config_entry: Any

    def ovw_reset(self) -> None:
        """Initialise the per-flow login state. Call from __init__."""
        self._ovw_session: Any = None
        self._ovw_connector: Any = None
        self._ovw_cookies: list[dict[str, Any]] = []
        self._ovw_username: str = ""

    async def _ovw_persist(self) -> None:
        """Write the captured cookies onto the entry and reload it.

        Split out of the options flow's ``_ovw_finish`` so both flows share the
        persistence while each finishes its own way — a repair resolves an
        issue, an options flow creates an entry.
        """
        from .const import (  # noqa: PLC0415
            CONF_SUPPLEMENTARY_AUTHPROXY,
            CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
        )

        self.hass.config_entries.async_update_entry(
            self._config_entry,
            data={
                **self._config_entry.data,
                CONF_SUPPLEMENTARY_AUTHPROXY: True,
                CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: self._ovw_cookies,
            },
        )
        # The update listener only reloads on credential changes; the
        # supplementary config lives in entry.data, so reload explicitly
        # (after this flow returns) to arm the merged channel.
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(self._config_entry.entry_id)
        )

    async def _ovw_begin_login(self, username: str, password: str) -> bool:
        """Drive the vw.de authproxy login; True if an OTP step is needed.
        Mirrors the config-flow's _wap_begin_login (kept self-contained so the
        OptionsFlow owns its own throwaway session + connector)."""
        import aiohttp  # noqa: PLC0415

        from .cariad.auth._website_authproxy import (  # noqa: PLC0415
            WebsiteAuthProxyConnector,
        )
        from .cariad.exceptions import (  # noqa: PLC0415
            AuthenticationError,
            EmailTwoFactorRequiredError,
            InvalidCredentialsError,
        )

        await self._ovw_close_session()
        self._ovw_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=True),
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        self._ovw_connector = WebsiteAuthProxyConnector(
            self._ovw_session, username, password, brand="volkswagen",
        )
        try:
            result = await self._ovw_connector.begin_login()
        except EmailTwoFactorRequiredError:
            return True
        except InvalidCredentialsError as err:
            await self._ovw_close_session()
            _LOGGER.warning("Website authproxy rejected the credentials: %s", err)
            raise ValueError("invalid_credentials") from err
        except AuthenticationError as err:
            await self._ovw_close_session()
            # v2.24.1 (#957) — this is the options-flow twin of the setup-time
            # login at line ~637, and it was the only one of the two that stayed
            # silent. Every one of the upstream raise sites landed here as a bare
            # "invalid_credentials", so a redirect loop, an expired SSO session or
            # a portal outage all told the user their password was wrong and left
            # nothing in the log to tell them apart.
            #
            # The log line fixed half of that; the verdict the USER sees was still
            # "your password is wrong". #1313 (@realynot) hit exactly this site on
            # a re-login whose credentials reach the OTP step on volkswagen.de,
            # and #1679 (@Fishermanjb) the same symptom at setup. Only a genuine
            # 401 keeps the credential verdict now.
            _LOGGER.warning("Website authproxy login failed: %s", err)
            raise ValueError("website_login_failed") from err
        except Exception as err:  # noqa: BLE001
            await self._ovw_close_session()
            _LOGGER.error(
                "Website authproxy unexpected error: %s", type(err).__name__,
            )
            raise ValueError("cannot_connect") from err
        if result == "otp_required":
            return True
        self._ovw_cookies = self._ovw_capture_cookies()
        await self._ovw_close_session()
        return False

    async def _ovw_submit_otp(self, code: str) -> bool:
        """Submit the OTP for the supplementary vw.de login."""
        from .cariad.exceptions import AuthenticationError  # noqa: PLC0415

        if self._ovw_connector is None:
            raise ValueError("cannot_connect")
        try:
            ok = bool(await self._ovw_connector.submit_otp(code))
            if ok:
                self._ovw_cookies = self._ovw_capture_cookies()
        except AuthenticationError as err:
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            raise ValueError("cannot_connect") from err
        finally:
            await self._ovw_close_session()
        return ok

    def _ovw_capture_cookies(self) -> list[dict[str, Any]]:
        """Export the connector's session cookies (never raises → empty list)."""
        connector = self._ovw_connector
        if connector is None:
            return []
        try:
            cookies = connector.export_cookies()
        except Exception:  # noqa: BLE001
            return []
        return cookies if isinstance(cookies, list) else []

    async def _ovw_close_session(self) -> None:
        """Close the throwaway login session + drop the connector."""
        sess = self._ovw_session
        self._ovw_session = None
        self._ovw_connector = None
        if sess is not None:
            try:
                await sess.close()
            except Exception:  # noqa: BLE001
                pass

