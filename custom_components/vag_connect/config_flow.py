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
    } else "cannot_connect"


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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: brand + credentials."""
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
            step_id="user",
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
