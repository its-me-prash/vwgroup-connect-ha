# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Config flow for VAG Connect — setup, reconfigure, and re-authentication."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    BRANDS,
    CONF_BRAND,
    CONF_ENABLE_PUSH_AUDI_VW,
    CONF_ENABLE_PUSH_FCM,
    CONF_ENABLE_PUSH_MQTT,
    CONF_ENABLE_REVERSE_GEOCODING,
    CONF_FORCE_ACCESS,
    CONF_FORCE_PPE_CLIMATE,
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# ── Brand selector options with icons ────────────────────────────────────────
# HA renders these as a visual select list (not a plain dropdown)
_BRAND_OPTIONS: list[SelectOptionDict] = [
    SelectOptionDict(value="audi",          label="Audi (myAudi)"),
    SelectOptionDict(value="volkswagen",    label="Volkswagen EU (WeConnect ID)"),
    SelectOptionDict(value="skoda",         label="Škoda (MyŠkoda)"),
    SelectOptionDict(value="seat",          label="SEAT"),
    SelectOptionDict(value="cupra",         label="CUPRA"),
    SelectOptionDict(value="volkswagen_na", label="Volkswagen US / CA"),
    SelectOptionDict(value="porsche",       label="Porsche (My Porsche)"),
]

_BRAND_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=_BRAND_OPTIONS,
        mode=SelectSelectorMode.LIST,   # visual radio-button list, not dropdown
        translation_key="brand",
    )
)

_USERNAME_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
)

_PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)

_SPIN_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off")
)

_MFA_SELECTOR = TextSelector(
    TextSelectorConfig(
        type=TextSelectorType.NUMBER,
        autocomplete="one-time-code",
    )
)

_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_SCAN_INTERVAL,
        max=60,
        step=1,
        mode=NumberSelectorMode.SLIDER,
        unit_of_measurement="min",
    )
)

_BOOL_SELECTOR = BooleanSelector()


# ── Credential validation ─────────────────────────────────────────────────────

async def _validate_credentials(
    hass: HomeAssistant, brand: str, username: str, password: str,
    mfa_code: str | None = None,
) -> None:
    """Validate credentials by authenticating with the CARIAD API."""
    import aiohttp  # noqa: PLC0415
    from .cariad import CariadClientFactory  # noqa: PLC0415
    from .cariad.exceptions import (  # noqa: PLC0415
        AuthenticationError,
        MarketingConsentError,
        RateLimitError,
        TermsAndConditionsError,
        TwoFactorRequiredError,
        UpstreamUnavailableError,
    )

    connector = aiohttp.TCPConnector(ssl=True)
    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    ) as auth_session:
        client = CariadClientFactory.create(brand, auth_session, username, password)
        try:
            await client.authenticate(mfa_code=mfa_code)
        except TermsAndConditionsError as err:
            raise ValueError("terms_and_conditions") from err
        except MarketingConsentError as err:
            raise ValueError("marketing_consent") from err
        except TwoFactorRequiredError as err:
            raise ValueError(f"two_factor_required:{err}") from err
        except RateLimitError as err:
            raise ValueError("too_many_requests") from err
        except UpstreamUnavailableError as err:
            # v2.5.7 — 5xx from CARIAD-BFF token endpoint = VW server-side
            # incident, NOT bad credentials. Surface as a distinct error
            # so users do not reconfigure their integration in a panic.
            _LOGGER.warning(
                "VAG Connect (%s): upstream VW backend unavailable: %s",
                brand, err,
            )
            raise ValueError("upstream_unavailable") from err
        except AuthenticationError as err:
            _LOGGER.warning("VAG Connect auth failed (%s): %s", brand, err)
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            # v1.24.1 (2026-05-08 audit): one-line ERROR with type only,
            # full traceback at DEBUG. aiohttp can chain InvalidURL with
            # form-encoded request URLs that may carry username; keeping
            # the traceback off the default ERROR-level avoids that PII
            # vector while DEBUG remains available for triage.
            import traceback  # noqa: PLC0415
            _LOGGER.error(
                "VAG Connect unexpected error during %s auth: %s",
                brand, type(err).__name__,
            )
            _LOGGER.debug(
                "VAG Connect %s auth traceback: %s\n%s",
                brand, err,
                "".join(traceback.format_tb(err.__traceback__)),
            )
            raise ValueError("cannot_connect") from err


def _map_error(err_code: str) -> str:
    """Map ValueError string to strings.json error key."""
    return err_code if err_code in {
        "terms_and_conditions", "marketing_consent", "two_factor_required",
        "too_many_requests", "invalid_credentials", "missing_library",
        "upstream_unavailable",  # v2.5.7 — 5xx from VW backend
        "brand_not_dag_eligible",  # v2.7.0 — user picked non-DAG brand for browser login
    } else "cannot_connect"


def _extract_user_id_from_id_token(id_token: str, fallback: str) -> str:
    """v2.7.0 — Decode the ``sub`` claim from an OIDC id_token.

    Used by the browser-login (DAG) flow to derive a stable per-user
    identifier without ever asking the user for their email. The
    id_token is signed by VW's IDP — we do NOT verify the signature
    here (the IDP verified it when minting it; tampering doesn't
    affect us because we only consume our own freshly-acquired token).

    Returns the ``sub`` claim if extractable, else ``fallback``.
    Never raises — id_token formats vary across brands and we never
    want a parse failure to block setup.
    """
    import base64  # noqa: PLC0415
    import json  # noqa: PLC0415

    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return fallback
        payload_b64 = parts[1]
        # Base64-url padding: JWT strips '=', so add it back.
        padding = (-len(payload_b64)) % 4
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + ("=" * padding))
        payload = json.loads(payload_bytes.decode("utf-8"))
        sub = payload.get("sub")
        if isinstance(sub, str) and sub:
            return sub
    except Exception:  # noqa: BLE001 — defensive, never block setup
        pass
    return fallback


# ── Schema builders ───────────────────────────────────────────────────────────

def _credentials_schema(
    brand: str = "",
    username: str = "",
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    spin: str = "",
    force_access: bool = False,
) -> vol.Schema:
    """Credentials + advanced settings schema with proper selectors."""
    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_BRAND, default=brand or vol.UNDEFINED): _BRAND_SELECTOR,
        vol.Required(CONF_USERNAME, default=username or vol.UNDEFINED): _USERNAME_SELECTOR,
        vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        vol.Optional(CONF_SPIN, default=spin): _SPIN_SELECTOR,
        vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): _INTERVAL_SELECTOR,
        vol.Optional(CONF_FORCE_ACCESS, default=force_access): _BOOL_SELECTOR,
    }
    return vol.Schema(schema)


# ── Config Flow ───────────────────────────────────────────────────────────────

class VagConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for VAG Connect."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_brand: str = ""
        self._pending_username: str = ""
        self._pending_password: str = ""
        self._pending_entry_data: dict[str, Any] = {}
        # v2.7.0 — Device Authorization Grant (browser-login) state.
        # Two-phase flow so HA's show_progress can re-render with the
        # populated URL + user_code BEFORE the long polling wait begins.
        self._dag_brand: str = ""
        self._dag_user_input: dict[str, Any] = {}
        # Phase 1: request_device_code() — fast (~1 s HTTP round-trip).
        self._dag_request_task: Any = None
        # Phase 2: poll_for_tokens() — slow (waits up to 5 min for the
        # user to approve in their browser).
        self._dag_poll_task: Any = None
        # Populated by Phase 1, displayed during Phase 2.
        self._dag_user_code: str = ""
        self._dag_verification_uri: str = ""
        self._dag_device_code: str = ""
        self._dag_poll_interval: int = 5
        self._dag_expires_in: int = 300
        # Populated by Phase 2, consumed by the finish step.
        self._dag_tokens: Any = None
        self._dag_user_id: str = ""
        # Captured if either phase fails.
        self._dag_error: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1 (v2.7.0): menu — browser login vs email + password.

        Browser login (Device Authorization Grant) is recommended for
        Audi/Skoda/SEAT/CUPRA — no password storage in HA, real
        refresh_token, password-less. VW EU and Porsche stay on the
        email + password path because VW has not whitelisted those
        client_ids for the device grant flow.

        v2.7.0b4 — menu_options pass as ``dict`` with raw labels embedded
        rather than a ``list`` that relies on translation lookup. The
        translation-lookup path turned out brittle in practice: when a
        user upgrades from a pre-menu version (e.g. v2.6.0) without a
        full HA restart, HA caches the old strings and renders the new
        menu with empty chevrons because the menu_options keys don't
        exist in the cached strings. Embedding the labels makes the
        menu render correctly regardless of cache state.
        """
        return self.async_show_menu(
            step_id="user",
            menu_options={
                "browser_login": (
                    "Browser-Login — Audi / Škoda / SEAT / CUPRA "
                    "(empfohlen, kein Passwort in HA)"
                ),
                "email_password": (
                    "E-Mail + Passwort — Volkswagen EU / Porsche (Legacy)"
                ),
            },
        )

    async def async_step_email_password(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.7.0 — original credentials flow (was async_step_user).

        Browser-login users skip this step entirely. Legacy email +
        password path stays for backwards compatibility and for brands
        without device-grant whitelisting (VW EU, Porsche).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            brand    = user_input[CONF_BRAND]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(f"{brand}_{username}")
            self._abort_if_unique_id_configured()

            try:
                await _validate_credentials(self.hass, brand, username, password)
            except ValueError as err:
                err_str = str(err)
                if err_str.startswith("two_factor_required"):
                    self._pending_brand    = brand
                    self._pending_username = username
                    self._pending_password = password
                    self._pending_entry_data = self._build_entry_data(brand, username, password, user_input)
                    return await self.async_step_mfa()
                errors["base"] = _map_error(err_str)
            else:
                return self.async_create_entry(
                    title=f"{BRANDS[brand]} — {username}",
                    data=self._build_entry_data(brand, username, password, user_input),
                )

        # v2.2.3 (#270 roberttco VW NA, 2026-05-21) — when validation
        # fails, re-render the form with the user's previous selections
        # preserved. Previously ``_credentials_schema()`` was called with
        # NO arguments → brand/username/spin/scan_interval/force-access
        # all reset to defaults, surprising the user (they thought the
        # rejection was about their brand pick rather than credentials).
        # Now we thread the last user_input back into the schema so only
        # the password field requires re-entry. Password is intentionally
        # NOT preserved (HA convention — never echo passwords to the
        # client even via schema-default).
        suggested = user_input or {}
        return self.async_show_form(
            step_id="email_password",
            data_schema=_credentials_schema(
                brand=suggested.get(CONF_BRAND, ""),
                username=suggested.get(CONF_USERNAME, ""),
                scan_interval=int(
                    suggested.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ),
                spin=suggested.get(CONF_SPIN, ""),
                force_access=bool(suggested.get(CONF_FORCE_ACCESS, False)),
            ),
            errors=errors,
        )

    async def async_step_browser_login(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.7.0 — Browser-login (Device Authorization Grant) step 1.

        User picks a DAG-eligible brand and optional advanced settings.
        Submits → we start the background DAG task and transition to the
        pending step (which shows progress + verification URL).
        """
        from .cariad.auth._device_grant import DAG_ENABLED_BRANDS  # noqa: PLC0415

        errors: dict[str, str] = {}

        if user_input is not None:
            brand = user_input[CONF_BRAND]
            if brand not in DAG_ENABLED_BRANDS:
                # Defence in depth — the form should have filtered these
                # out already, but the user could send a crafted payload.
                errors["base"] = "brand_not_dag_eligible"
            else:
                # Reset state for this attempt.
                self._dag_brand = brand
                self._dag_user_input = dict(user_input)
                self._dag_request_task = None
                self._dag_poll_task = None
                self._dag_user_code = ""
                self._dag_verification_uri = ""
                self._dag_device_code = ""
                self._dag_tokens = None
                self._dag_user_id = ""
                self._dag_error = ""
                return await self.async_step_browser_login_pending()

        # DAG-eligible brand options only (subset of the standard list).
        dag_brand_options: list[SelectOptionDict] = [
            opt for opt in _BRAND_OPTIONS
            if opt["value"] in DAG_ENABLED_BRANDS
        ]
        dag_brand_selector = SelectSelector(
            SelectSelectorConfig(
                options=dag_brand_options,
                mode=SelectSelectorMode.LIST,
                translation_key="brand",
            )
        )

        suggested = user_input or {}
        return self.async_show_form(
            step_id="browser_login",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_BRAND, default=suggested.get(CONF_BRAND, vol.UNDEFINED),
                ): dag_brand_selector,
                vol.Optional(
                    CONF_SPIN, default=suggested.get(CONF_SPIN, ""),
                ): _SPIN_SELECTOR,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(suggested.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                ): _INTERVAL_SELECTOR,
                vol.Optional(
                    CONF_FORCE_ACCESS,
                    default=bool(suggested.get(CONF_FORCE_ACCESS, False)),
                ): _BOOL_SELECTOR,
            }),
            errors=errors,
        )

    async def async_step_browser_login_pending(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.7.0b6 — Browser-login Phase 1: request the device_code.

        This step ONLY drives the fast /device_authorization HTTP call.
        It shows a 'requesting login code…' progress dialog while in
        flight, then hands off to ``browser_login_approve`` (a separate
        step_id) for the slow polling phase.

        Why split into two step_ids instead of re-using one step with two
        progress_action values:

        HA's frontend caches the progress description by step_id, not by
        progress_action. When you change progress_action within the same
        step the dialog often keeps showing the FIRST description (with
        empty placeholders). The b4 attempt at single-step two-phase
        flow hit exactly this — the URL + user_code never appeared and
        the spinner spun forever on the user's HA install.

        Two distinct step_ids = HA tears down the first progress dialog
        and renders a fresh one for the second, picking up the new
        placeholders cleanly.
        """
        # Kick off request_device_code() on first entry
        if self._dag_request_task is None:
            self._dag_request_task = self.hass.async_create_task(
                self._do_request_device_code()
            )

        if not self._dag_request_task.done():
            return self.async_show_progress(
                step_id="browser_login_pending",
                progress_action="requesting_device_code",
                progress_task=self._dag_request_task,
            )

        if self._dag_error or not self._dag_device_code:
            # Phase 1 failed — drop back to the brand picker so user
            # can retry. The error message lives in self._dag_error
            # (surfaced via debug log; future: repair-issue / notification).
            return self.async_show_progress_done(next_step_id="browser_login")

        # Phase 1 done — hand off to Phase 2 (separate step_id so HA
        # re-renders the progress dialog with the populated placeholders).
        return self.async_show_progress_done(
            next_step_id="browser_login_approve"
        )

    async def async_step_browser_login_approve(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.7.0b6 — Browser-login Phase 2: wait for user approval.

        Polls /token while the user opens the verification URL in their
        own browser, signs in to their Brand ID account, and approves
        the device. HA shows the URL + user_code in the progress dialog
        the whole time. When polling completes:
          - success → advance to ``browser_login_finish``
          - failure → drop back to brand picker so user can retry

        Reached only after Phase 1 (``browser_login_pending``) populated
        ``_dag_verification_uri`` and ``_dag_user_code``.
        """
        # Defensive — should only be reached with Phase 1 state populated.
        if not self._dag_device_code:
            return self.async_show_progress_done(next_step_id="browser_login")

        # Kick off poll_for_tokens() on first entry
        if self._dag_poll_task is None:
            self._dag_poll_task = self.hass.async_create_task(
                self._do_poll_tokens()
            )

        if not self._dag_poll_task.done():
            return self.async_show_progress(
                step_id="browser_login_approve",
                progress_action="awaiting_browser_login",
                progress_task=self._dag_poll_task,
                description_placeholders={
                    "verification_uri": self._dag_verification_uri,
                    "user_code": self._dag_user_code,
                },
            )

        # Poll done — advance to finish (success) or restart (failure)
        next_step = (
            "browser_login_finish" if self._dag_tokens else "browser_login"
        )
        return self.async_show_progress_done(next_step_id=next_step)

    async def _do_request_device_code(self) -> None:
        """v2.7.0b4 — Phase 1 of the DAG flow: get device_code.

        Fast HTTP call to /oidc/v1/device_authorization. Populates
        self._dag_device_code / _user_code / _verification_uri /
        _poll_interval / _expires_in. Errors stash on _dag_error.

        Critically runs to completion FAST so the show_progress can
        re-render Phase 2 with the URL + code fully populated in the
        description placeholders.
        """
        import aiohttp  # noqa: PLC0415
        from .cariad.auth._device_grant import DeviceAuthorizationGrant  # noqa: PLC0415

        try:
            connector = aiohttp.TCPConnector(ssl=True)
            self._dag_session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=aiohttp.CookieJar(unsafe=True),
            )
            from .cariad.models import BRANDS as BRAND_CONFIGS  # noqa: PLC0415

            brand_cfg = BRAND_CONFIGS[self._dag_brand]
            self._dag_client = DeviceAuthorizationGrant(
                self._dag_session,
                brand_cfg.client_id,
                scope=brand_cfg.scope,
            )
            code = await self._dag_client.request_device_code()
            self._dag_device_code = code.device_code
            self._dag_user_code = code.user_code
            self._dag_verification_uri = code.verification_uri_complete
            self._dag_poll_interval = code.interval
            self._dag_expires_in = code.expires_in
            _LOGGER.debug(
                "Browser login Phase 1 OK — user_code=%s, expires_in=%ds",
                self._dag_user_code, self._dag_expires_in,
            )
        except Exception as err:  # noqa: BLE001 — flow-level catch
            self._dag_error = str(err)
            _LOGGER.warning(
                "Browser login Phase 1 failed for %s: %s",
                self._dag_brand, err,
            )
            if hasattr(self, "_dag_session") and self._dag_session is not None:
                await self._dag_session.close()

    async def _do_poll_tokens(self) -> None:
        """v2.7.0b4 — Phase 2 of the DAG flow: poll for token approval.

        Reuses the DeviceAuthorizationGrant + aiohttp session created
        during Phase 1 so the poll respects the same cookie jar.
        Closes the session in either success or failure path.
        """
        from .const import BRANDS as _CONST_BRANDS  # noqa: PLC0415

        try:
            self._dag_tokens = await self._dag_client.poll_for_tokens(
                self._dag_device_code,
                interval=self._dag_poll_interval,
                expires_in=self._dag_expires_in,
            )
            self._dag_user_id = _extract_user_id_from_id_token(
                self._dag_tokens.id_token,
                fallback=f"{self._dag_brand}_dag",
            )
            _LOGGER.info(
                "Browser login succeeded for %s — sub=%s",
                _CONST_BRANDS.get(self._dag_brand, self._dag_brand),
                self._dag_user_id[:8] if self._dag_user_id else "(none)",
            )
        except Exception as err:  # noqa: BLE001 — flow-level catch
            self._dag_error = str(err)
            _LOGGER.warning(
                "Browser login Phase 2 failed for %s: %s",
                self._dag_brand, err,
            )
        finally:
            sess = getattr(self, "_dag_session", None)
            if sess is not None:
                await sess.close()
                # Use setattr so mypy doesn't complain about None being
                # assigned to a ClientSession-typed attribute.
                setattr(self, "_dag_session", None)

    async def async_step_browser_login_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.7.0 — Browser-login step 3: create the config entry.

        Reached only after _run_dag_flow set _dag_tokens. Stores the
        tokens in the entry's data dict; the coordinator's existing
        token-persistence machinery picks them up on first run.
        """
        if self._dag_tokens is None:
            # Shouldn't happen if step routing is correct, but defensive.
            return self.async_abort(reason="dag_no_tokens")

        unique = f"{self._dag_brand}_{self._dag_user_id}"
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()

        # Reuse _build_entry_data but with synthetic email-substitute
        # (BrandID `sub`). Password is empty — the refresh-token path
        # handles renewal without it.
        entry_data = self._build_entry_data(
            self._dag_brand,
            self._dag_user_id,
            "",  # no password stored
            self._dag_user_input,
        )
        # Stash the DAG-acquired tokens so the coordinator's token
        # persistence loader picks them up before the first poll cycle.
        entry_data["dag_initial_tokens"] = {
            "access_token": self._dag_tokens.access_token,
            "refresh_token": self._dag_tokens.refresh_token,
            "id_token": self._dag_tokens.id_token,
            "expires_at": self._dag_tokens.expires_at,
            "strategy": "device_grant",
        }
        return self.async_create_entry(
            title=f"{BRANDS[self._dag_brand]} — {self._dag_user_id[:8]}…",
            data=entry_data,
        )

    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2 (optional): MFA code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mfa_code = str(user_input.get("mfa_code", "")).strip()
            try:
                await _validate_credentials(
                    self.hass,
                    self._pending_brand,
                    self._pending_username,
                    self._pending_password,
                    mfa_code=mfa_code,
                )
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                return self.async_create_entry(
                    title=f"{BRANDS[self._pending_brand]} — {self._pending_username}",
                    data=self._pending_entry_data,
                )

        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({
                vol.Required("mfa_code"): _MFA_SELECTOR,
            }),
            description_placeholders={"username": self._pending_username},
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Re-auth when credentials expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Re-enter credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

        if user_input is not None and reauth_entry is not None:
            brand    = reauth_entry.data[CONF_BRAND]
            username = reauth_entry.data[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            spin     = user_input.get(CONF_SPIN, reauth_entry.data.get(CONF_SPIN, ""))

            try:
                await _validate_credentials(self.hass, brand, username, password)
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                self.hass.config_entries.async_update_entry(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: password, CONF_SPIN: spin},
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
                vol.Optional(
                    CONF_SPIN,
                    default=reauth_entry.data.get(CONF_SPIN, "") if reauth_entry else "",
                ): _SPIN_SELECTOR,
            }),
            errors=errors,
            description_placeholders={
                "brand":    BRANDS.get(reauth_entry.data.get(CONF_BRAND, ""), "") if reauth_entry else "",
                "username": reauth_entry.data.get(CONF_USERNAME, "") if reauth_entry else "",
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Reconfigure without removing the integration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None and entry is not None:
            brand    = user_input[CONF_BRAND]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                await _validate_credentials(self.hass, brand, username, password)
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                new_unique_id = f"{brand}_{username}"
                await self.async_set_unique_id(new_unique_id)
                self._abort_if_unique_id_configured(updates={"entry_id": entry.entry_id})

                self.hass.config_entries.async_update_entry(
                    entry,
                    title=f"{BRANDS[brand]} — {username}",
                    unique_id=new_unique_id,
                    data=self._build_entry_data(brand, username, password, user_input),
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        current = entry.data if entry else {}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_credentials_schema(
                brand=current.get(CONF_BRAND, ""),
                username=current.get(CONF_USERNAME, ""),
                scan_interval=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                spin=current.get(CONF_SPIN, ""),
                force_access=current.get(CONF_FORCE_ACCESS, False),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> VagConnectOptionsFlow:
        """Return options flow handler."""
        return VagConnectOptionsFlow(config_entry)

    @staticmethod
    def _build_entry_data(
        brand: str, username: str, password: str, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Build the config entry data dict from validated user input."""
        return {
            CONF_BRAND:         brand,
            CONF_USERNAME:      username,
            CONF_PASSWORD:      password,
            CONF_SPIN:          user_input.get(CONF_SPIN, ""),
            CONF_SCAN_INTERVAL: max(
                int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                MIN_SCAN_INTERVAL,
            ),
            CONF_FORCE_ACCESS:  user_input.get(CONF_FORCE_ACCESS, False),
        }


# ── Options Flow ──────────────────────────────────────────────────────────────

class VagConnectOptionsFlow(config_entries.OptionsFlow):
    """Scan interval + S-PIN without full reconfigure."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Options: scan interval, S-PIN, reverse geocoding opt-in."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_data = self._config_entry.data
        current_options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current_options.get(
                        CONF_SCAN_INTERVAL,
                        current_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ),
                ): _INTERVAL_SELECTOR,
                vol.Optional(
                    CONF_SPIN,
                    default=current_options.get(
                        CONF_SPIN, current_data.get(CONF_SPIN, "")
                    ),
                ): _SPIN_SELECTOR,
                vol.Optional(
                    CONF_ENABLE_REVERSE_GEOCODING,
                    default=current_options.get(
                        CONF_ENABLE_REVERSE_GEOCODING,
                        current_data.get(CONF_ENABLE_REVERSE_GEOCODING, False),
                    ),
                ): _BOOL_SELECTOR,
                # v1.12.0 (#63) — Read-only Mode toggle. When True, the
                # next reload will skip lock/switch/button(non-refresh)/
                # climate/number entities. Sensors + binary_sensors stay.
                vol.Optional(
                    CONF_READ_ONLY,
                    default=current_options.get(
                        CONF_READ_ONLY,
                        current_data.get(CONF_READ_ONLY, False),
                    ),
                ): _BOOL_SELECTOR,
                # v1.14.0 (#29 + #51 Facelift) — PPE/PPC Climate body.
                # Audi-only effect; harmless toggle on other brands.
                # Forces ``climatisationMode: comfort`` body shape and
                # omits ``targetTemperature*`` for Audi Q6/A6 e-tron,
                # RS e-tron GT Facelift, A3 2024+ PHEV. Auto-detection
                # is too unreliable to default-on; user opts in.
                vol.Optional(
                    CONF_FORCE_PPE_CLIMATE,
                    default=current_options.get(
                        CONF_FORCE_PPE_CLIMATE,
                        current_data.get(CONF_FORCE_PPE_CLIMATE, False),
                    ),
                ): _BOOL_SELECTOR,
                # v1.18.0 (#57 Push Bundle, foundation phase) — opt-in
                # toggle for Skoda mysmob MQTT push updates. Default
                # False because deps (aiomqtt + firebase-messaging) are
                # lazy-imported (not in manifest yet) and live activation
                # is pending community-tester validation. Other brands
                # ignore this option for now (CUPRA/SEAT FCM will land
                # in v1.19.0).
                vol.Optional(
                    CONF_ENABLE_PUSH_MQTT,
                    default=current_options.get(
                        CONF_ENABLE_PUSH_MQTT,
                        current_data.get(CONF_ENABLE_PUSH_MQTT, False),
                    ),
                ): _BOOL_SELECTOR,
                # v1.19.0 (#57 Push Bundle, foundation phase) — opt-in
                # toggle for CUPRA/SEAT OLA Firebase Cloud Messaging
                # push updates. Default False; same lazy-import +
                # foundation pattern as v1.18.0 Skoda MQTT toggle. Only
                # meaningful for brand in {cupra, seat}.
                vol.Optional(
                    CONF_ENABLE_PUSH_FCM,
                    default=current_options.get(
                        CONF_ENABLE_PUSH_FCM,
                        current_data.get(CONF_ENABLE_PUSH_FCM, False),
                    ),
                ): _BOOL_SELECTOR,
                # v1.23.0 (#57 Push Bundle, foundation phase, Audi/VW
                # track) — opt-in toggle for Audi/VW Cariad-BFF FCM
                # push updates. Default False; same lazy-import +
                # foundation pattern as v1.18.0 + v1.19.0. Only
                # meaningful for brand in {audi, volkswagen}.
                # User-suggested 2026-05-07 (myAudi App push → HA).
                vol.Optional(
                    CONF_ENABLE_PUSH_AUDI_VW,
                    default=current_options.get(
                        CONF_ENABLE_PUSH_AUDI_VW,
                        current_data.get(CONF_ENABLE_PUSH_AUDI_VW, False),
                    ),
                ): _BOOL_SELECTOR,
            }),
        )
