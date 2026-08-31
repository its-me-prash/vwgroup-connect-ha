# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Config flow for VW Group Connect — setup, reconfigure, and re-authentication."""

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
    QrCodeSelector,
    QrCodeSelectorConfig,
    QrErrorCorrectionLevel,
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
    CONF_ABRP_API_KEY,
    CONF_ABRP_ENABLE,
    CONF_ABRP_USER_TOKEN,
    CONF_BATTERY_NOMINAL_KWH,
    CONF_FUEL_TANK_CAPACITY,
    CONF_KEEP_RAW_DATASETS,
    CONF_BRAND,
    CONF_CLIENT_ID_OVERRIDE,
    CONF_COUNTRY,
    CONF_EU_DATA_ACT_AUTO_KICKOFF,
    CONF_ENABLE_PUSH_AUDI_VW,
    CONF_ENABLE_PUSH_FCM,
    CONF_ENABLE_PUSH_MQTT,
    CONF_ENABLE_REVERSE_GEOCODING,
    CONF_FORCE_PPE_CLIMATE,
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MBB_COMMAND_FALLBACK,
    CONF_MEB_COMMANDS_UNAVAILABLE,
    CONF_MBB_COMMAND_CLIENT_ID,
    CONF_MBB_COMMAND_TOKENS,
    CONF_MBB_VINS,
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    CONF_SPIN_BY_VIN,
    CONF_HIDE_EMPTY_ENTITIES,
    CONF_SUPPLEMENTARY_AUTHPROXY,
    CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
    CONF_TEST_COHORT,
    CONF_SUPPLEMENTARY_EU_PORTAL,
    CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
    CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
    CONF_VWEU_TWOWAY_ADDED_EU_PORTAL,
    CONF_SUPPLEMENTARY_TIBBER,
    CONF_SUPPLEMENTARY_TIBBER_TOKENS,
    CONF_WEBSITE_AUTHPROXY,
    CONF_WEBSITE_COOKIES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _brand_label(brand: str) -> str:
    """Display label for a brand, safe for brands offered in the picker but
    absent from the ``BRANDS`` map — e.g. Bentley, which rides the Audi IDK
    tenant and is deliberately kept out of ``BRANDS`` (which is parity-locked
    to DEEPLINK_SCHEMES + capabilities). Falls back to a title-cased name so
    entry-title formatting never KeyErrors."""
    return BRANDS.get(brand, brand.replace("_", " ").title())


# ── Brand selector options with icons ────────────────────────────────────────
# HA renders these as a visual select list (not a plain dropdown)
_BRAND_OPTIONS: list[SelectOptionDict] = [
    SelectOptionDict(value="audi",          label="Audi (myAudi)"),
    SelectOptionDict(value="volkswagen",    label="Volkswagen EU (WeConnect ID)"),
    SelectOptionDict(value="skoda",         label="Škoda (MyŠkoda)"),
    SelectOptionDict(value="seat",          label="SEAT"),
    SelectOptionDict(value="cupra",         label="CUPRA"),
    SelectOptionDict(value="volkswagen_na", label="Volkswagen US / CA"),
    SelectOptionDict(value="audi_na",       label="Audi US / CA (experimental)"),
    SelectOptionDict(value="porsche",       label="Porsche (My Porsche) — experimental, login may fail"),
    # v2.14.11 — Bentley (login+read; Audi IDK tenant). Two-way live-test gated.
    SelectOptionDict(value="bentley",       label="Bentley (My Bentley)"),
    # plug&play OBD-dongle cloud reader for pre-connectivity Audi cars (read-only).
    SelectOptionDict(value="audi_acpp",     label="Audi plug&play — OBD dongle (older cars)"),
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

# v2.15.1 (#503) — Volkswagen US/Canada region picker. Only relevant for the
# volkswagen_na brand (US vs CA pick different MYVW client_id + API host); all
# other brands ignore the stored value. Inline English option labels (no
# translation_key) so we don't add per-option i18n keys to all 9 string files.
_COUNTRY_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            SelectOptionDict(value="us", label="United States"),
            SelectOptionDict(value="ca", label="Canada"),
        ],
        mode=SelectSelectorMode.DROPDOWN,
    )
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

# Nameplate NET battery capacity for the optional State-of-Health sensor. 0 = off.
_KWH_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=0,
        max=250,
        step=0.1,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="kWh",
    )
)

_LITERS_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=0,
        max=200,
        step=1,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="L",
    )
)

_BOOL_SELECTOR = BooleanSelector()


# ── Credential validation ─────────────────────────────────────────────────────

async def _validate_credentials(
    hass: HomeAssistant, brand: str, username: str, password: str,
    mfa_code: str | None = None,
    country: str = "us",
) -> None:
    """Validate credentials by authenticating with the CARIAD API."""
    import aiohttp  # noqa: PLC0415
    from .cariad import CariadClientFactory  # noqa: PLC0415
    from .cariad.exceptions import (  # noqa: PLC0415
        AuthenticationError,
        MarketingConsentError,
        NorthAmericaAttestationError,
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
        client = CariadClientFactory.create(
            brand, auth_session, username, password, country=country
        )
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
                "VW Group Connect (%s): upstream VW backend unavailable: %s",
                brand, err,
            )
            raise ValueError("upstream_unavailable") from err
        except NorthAmericaAttestationError as err:
            # #1165/#659 — NA sign-in blocked by VW Play-Integrity, NOT a wrong
            # password. Surface the real reason so NA owners stop looping on the
            # credentials step. Must precede the generic AuthenticationError catch
            # (it is a subclass).
            _LOGGER.warning(
                "VW Group Connect (%s): North America sign-in blocked by VW "
                "device attestation (not a credentials problem): %s", brand, err,
            )
            raise ValueError("na_signin_attestation") from err
        except AuthenticationError as err:
            _LOGGER.warning("VW Group Connect auth failed (%s): %s", brand, err)
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            # v1.24.1 (2026-05-08 audit): one-line ERROR with type only,
            # full traceback at DEBUG. aiohttp can chain InvalidURL with
            # form-encoded request URLs that may carry username; keeping
            # the traceback off the default ERROR-level avoids that PII
            # vector while DEBUG remains available for triage.
            import traceback  # noqa: PLC0415
            _LOGGER.error(
                "VW Group Connect unexpected error during %s auth: %s",
                brand, type(err).__name__,
            )
            _LOGGER.debug(
                "VW Group Connect %s auth traceback: %s\n%s",
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
        "portal_interaction_required",  # v2.15.4 (#527) — non-credential portal stop
        "na_signin_attestation",  # #1165/#659 — VW NA Play-Integrity sign-in wall
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
    enable_mbb_commands: bool = False,
    country: str = "us",
) -> vol.Schema:
    """Credentials + advanced settings schema with proper selectors."""
    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_BRAND, default=brand or vol.UNDEFINED): _BRAND_SELECTOR,
        vol.Required(CONF_USERNAME, default=username or vol.UNDEFINED): _USERNAME_SELECTOR,
        vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        vol.Optional(CONF_SPIN, default=spin): _SPIN_SELECTOR,
    }
    # v2.15.6 (gr6803/#465) — the US/Canada region picker is ONLY meaningful for
    # the volkswagen_na brand (US vs CA pick different MYVW client_id + API
    # host). Previously it was added unconditionally, so EU users (who select
    # the form's brand in this same step) saw a stray "country" dropdown that
    # only offered USA/Canada. Now we render it solely for volkswagen_na — on
    # the first render (brand unknown) it stays hidden; if a VW-NA login fails,
    # the form re-renders with brand=volkswagen_na and the picker appears so the
    # user can switch us↔ca. Every other brand never sees it.
    if brand.lower() in ("volkswagen_na", "audi_na"):
        schema[vol.Optional(CONF_COUNTRY, default=country)] = _COUNTRY_SELECTOR
    schema.update({
        vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): _INTERVAL_SELECTOR,
        # b12 — VW + Audi: after the portal login, add a durable-MBB command
        # channel (extra QR confirm) so this read-only portal entry also gets
        # remote lock/climate/charge. Ignored for other brands. Audi is
        # EXPERIMENTAL (legacy Car-Net only, unverified end-to-end — #666).
        vol.Optional("enable_mbb_commands", default=enable_mbb_commands): _BOOL_SELECTOR,
    })
    return vol.Schema(schema)


# ── Config Flow ───────────────────────────────────────────────────────────────

class VagConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for VW Group Connect."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_brand: str = ""
        self._pending_username: str = ""
        self._pending_password: str = ""
        self._pending_entry_data: dict[str, Any] = {}
        # v2.22.2 — the raw user_input captured when a login needs 2FA, so the
        # MFA-success finish can honour the "enable MBB commands" tick (VW/Audi)
        # exactly like the non-2FA path. Without it, a 2FA account silently got a
        # read-only portal entry and the command channel was dropped.
        self._pending_user_input: dict[str, Any] = {}
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
        # v2.15.0 — durable MBB strategy flag. When True the DAG flow uses the
        # e-Remote client + ``mbb`` scope and, after the browser confirm, mints
        # a durable MBB bearer via register/v1 + token-exchange. Default False
        # → the standard browser-login flow is completely unaffected.
        self._dag_mbb: bool = False
        self._dag_mbb_tokens: Any = None
        self._dag_mbb_client_id: str = ""
        # v2.15.0a8 — set when the MBB exchange says "Unknown user" (account/car
        # has no legacy Car-Net/MBB enrolment → newer ID/MEB car). Aborts the
        # flow with a clear "not eligible, use EU Data Act" message.
        self._dag_mbb_ineligible: bool = False
        # b12 — MBB COMMAND-CHANNEL setup: the Portal (email/pw) login can tick
        # "enable MBB commands" → after the portal validates, chain to the MBB
        # QR; the finish then creates a PORTAL-primary entry (reads) WITH the
        # MBB command channel (commands). These hold the portal entry across
        # the QR detour.
        self._dag_mbb_command: bool = False
        self._pending_portal_data: dict[str, Any] = {}
        self._pending_portal_title: str = ""
        # v2.17.2 (#666) — set when the MBB command channel is being added to an
        # EXISTING entry via Reconfigure. The QR finish/approve steps then UPDATE
        # this entry in place instead of creating a new one.
        self._mbb_reconfigure_entry_id: str | None = None
        # b15 — device-grant Audi MBB command-fallback opt-in
        # (async_step_audi_mbb_fallback). ``_dag_mbb_fallback`` tags the QR run so
        # browser_login_finish ATTACHES the durable bearer to an existing Audi
        # (``_mbb_fallback_entry_id``) instead of creating a new entry.
        self._dag_mbb_fallback: bool = False
        self._mbb_fallback_entry_id: str | None = None
        # v2.14.0 — website-authproxy (opt-in beta) pending state between the
        # credentials step and the email-OTP step. The connector + its session
        # are held open across the two-step OTP exchange so the cookie jar
        # survives; closed in either terminal path.
        self._wap_username: str = ""
        self._wap_user_input: dict[str, Any] = {}
        self._wap_connector: Any = None
        self._wap_session: Any = None
        # v2.14.3 — session cookies captured after a successful website-authproxy
        # login (no-OTP path in _wap_begin_login OR after _wap_submit_otp). Saved
        # into entry.data under CONF_WEBSITE_COOKIES so the runtime coordinator
        # can hydrate the jar and skip re-prompting the email-OTP on setup.
        self._wap_cookies: list[dict[str, Any]] = []

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
        # b12 — TWO login paths only. QR/browser-login (passwordless, two-way
        # native) for Audi/SEAT/CUPRA; Portal (email/pw) for Volkswagen EU /
        # Škoda / Porsche (v3.0.1: VW revoked Škoda's device_code grant, so
        # Škoda moved from QR to email+password), which can opt into a
        # durable-MBB command channel right
        # in that step (the old standalone "mbb_login" + "website_authproxy"
        # menu entries are gone — MBB is now the Portal's command toggle, and
        # vw.de is an options-only supplementary read channel).
        return self.async_show_menu(
            step_id="user",
            menu_options={
                "browser_login": (
                    "Browser-Login (QR) — Audi / SEAT / CUPRA "
                    "(empfohlen, kein Passwort in HA)"
                ),
                "email_password": (
                    "Portal (E-Mail + Passwort) — Volkswagen EU / Škoda / Porsche "
                    "· VW: dauerhafte Zwei-Wege-Befehle (MBB) gleich mit aktivierbar"
                ),
                # v3.0.0-alpha — experimental fourth source. Drives the official
                # app on a spare phone over ADB; last-resort two-way where the
                # network side is read-only. Clearly flagged EXPERIMENTAL.
                "companion_adb": (
                    "Companion-Handy (ADB) — EXPERIMENTELL, alle Marken "
                    "(zweites Handy mit eingeloggter App nötig)"
                ),
                # b15 — arm the durable MBB command fallback on an EXISTING
                # device-grant Audi (Car-Net cars). One-time browser confirm; the
                # BFF stays primary, MBB only steps in if VW ever revokes the
                # device grant. Aborts gracefully if no eligible Audi entry exists.
                "audi_mbb_fallback": (
                    "Fernbefehle für einen bestehenden Audi absichern — "
                    "Reserve-Verbindung, damit Ver-/Entriegeln, Klima & Laden "
                    "weiterlaufen, falls sich die Audi-Anbindung ändert"
                ),
            },
        )

    async def async_step_companion_adb(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v3.0.0-alpha — set up the companion (ADB) channel.

        Collects the phone's network-ADB address, the brand, the VIN the app
        shows, and an optional S-PIN, then validates the connection by opening
        ADB and reading the app's version. No credentials are stored: the phone
        is already signed in, and the only secret at rest is the ADB RSA key.
        """
        from .const import (  # noqa: PLC0415
            COMPANION_MIN_TOKEN_LEN,
            CONF_ADB_HOST,
            CONF_ADB_PORT,
            CONF_COMPANION_ADDON_TOKEN,
            CONF_COMPANION_AGENT_TOKEN,
            CONF_COMPANION_USE_ADDON,
            CONF_COMPANION_USE_RELAY,
            CONF_STRATEGY,
            CONF_VIN,
            DEFAULT_ADB_PORT,
            DEFAULT_COMPANION_ADDON_PORT,
            STRATEGY_COMPANION_ADB,
        )
        from .companion.presets import PRESETS  # noqa: PLC0415

        errors: dict[str, str] = {}

        if user_input is not None:
            brand = user_input[CONF_BRAND]
            host = (user_input.get(CONF_ADB_HOST) or "").strip()
            use_addon = bool(user_input.get(CONF_COMPANION_USE_ADDON))
            addon_token = (user_input.get(CONF_COMPANION_ADDON_TOKEN) or "").strip()
            # v4.4.0 (#968) — relay mode. The phone's agent app calls Home
            # Assistant, so there is nothing here to dial and nothing to probe:
            # the token IS the binding, and setup succeeds as soon as it is long
            # enough. The entry then waits for the agent to check in.
            use_relay = bool(user_input.get(CONF_COMPANION_USE_RELAY))
            agent_token = (user_input.get(CONF_COMPANION_AGENT_TOKEN) or "").strip()
            # The add-on serves its API on its own port, so a user who ticked
            # the box and left the ADB default in place gets the right one.
            _default_port = (
                DEFAULT_COMPANION_ADDON_PORT if use_addon else DEFAULT_ADB_PORT
            )
            port = int(user_input.get(CONF_ADB_PORT) or _default_port)
            if use_addon and port == DEFAULT_ADB_PORT:
                port = DEFAULT_COMPANION_ADDON_PORT
            vin = user_input[CONF_VIN].strip().upper()
            spin = (user_input.get(CONF_SPIN) or "").strip()

            if use_relay:
                valid = len(agent_token) >= COMPANION_MIN_TOKEN_LEN
                reason = "companion_agent_token_too_short"
            elif not host:
                valid, reason = False, "companion_host_required"
            else:
                valid, reason = await self._companion_probe(
                    brand, host, port, use_addon=use_addon, addon_token=addon_token
                )
            if not valid:
                errors["base"] = reason
            else:
                await self.async_set_unique_id(f"companion_{brand}_{vin}")
                self._abort_if_unique_id_configured()
                preset = PRESETS[brand]
                _how = "Companion/Agent" if use_relay else "Companion/ADB"
                title = f"{brand.title()} ({_how}) {vin[-6:]}"
                if not preset.verified:
                    title += " [alpha, read-only]"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_STRATEGY: STRATEGY_COMPANION_ADB,
                        CONF_BRAND: brand,
                        CONF_ADB_HOST: host,
                        CONF_ADB_PORT: port,
                        CONF_VIN: vin,
                        CONF_SPIN: spin,
                        CONF_COMPANION_USE_ADDON: use_addon,
                        CONF_COMPANION_ADDON_TOKEN: addon_token,
                        CONF_COMPANION_USE_RELAY: use_relay,
                        CONF_COMPANION_AGENT_TOKEN: agent_token,
                    },
                )

        brands = {b: b.title() for b in PRESETS}
        schema = vol.Schema(
            {
                vol.Required(CONF_BRAND, default="volkswagen"): vol.In(brands),
                # Optional since v4.4.0: relay mode never dials the phone, so
                # there is no address to give. Still required for both ADB
                # paths, enforced below with its own error rather than by the
                # schema, so the message can say why.
                vol.Optional(CONF_ADB_HOST, default=""): str,
                vol.Optional(CONF_ADB_PORT, default=DEFAULT_ADB_PORT): int,
                vol.Required(CONF_VIN): str,
                vol.Optional(CONF_SPIN, default=""): str,
                # #968 — on Android 11+ the phone only speaks wireless debugging
                # (TLS + pairing), which the built-in transport cannot do. Tick
                # this and give the ADD-ON's address above instead of the
                # phone's; the add-on holds the phone connection.
                vol.Optional(CONF_COMPANION_USE_ADDON, default=False): bool,
                vol.Optional(CONF_COMPANION_ADDON_TOKEN, default=""): str,
                # v4.4.0 (#968) — the third way to reach the phone, and the only
                # one that needs nothing FROM Home Assistant's side of the
                # network: an agent app on the phone long-polls HA. Tick this,
                # paste the token the agent generated, and leave the host field
                # as anything (it is unused on this path).
                vol.Optional(CONF_COMPANION_USE_RELAY, default=False): bool,
                vol.Optional(CONF_COMPANION_AGENT_TOKEN, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="companion_adb", data_schema=schema, errors=errors,
        )

    async def _companion_probe(
        self,
        brand: str,
        host: str,
        port: int,
        *,
        use_addon: bool = False,
        addon_token: str = "",
    ) -> tuple[bool, str]:
        """Open ADB and read the app version; returns (ok, error_key)."""
        from .companion.presets import PRESETS  # noqa: PLC0415
        from .companion.transport import (  # noqa: PLC0415
            CompanionTransportError,
            NetworkAdbTransport,
        )

        preset = PRESETS.get(brand)
        if preset is None:
            return False, "companion_unknown_brand"
        transport: NetworkAdbTransport
        if use_addon:
            # host/port address the add-on; it owns the phone connection, so
            # there is no local RSA key involved.
            from .companion.addon_transport import AddOnAdbTransport  # noqa: PLC0415

            transport = AddOnAdbTransport(host, port, token=addon_token)
        else:
            adbkey = self.hass.config.path(".storage", "vag_connect_adbkey")
            transport = NetworkAdbTransport(host, port, adbkey)
        try:
            await transport.connect()
            version = await transport.current_app_version(preset.package)
        except CompanionTransportError as err:
            _LOGGER.warning("Companion ADB probe failed: %s", err)
            # v2.26.0 — a bare "InvalidCommandError" is the fingerprint of
            # Android 11+ "wireless debugging": the pure-python transport reaches
            # the port but it speaks TLS + pairing, which adb-shell cannot. Point
            # the user at the companion add-on rather than a generic "no connect".
            if "InvalidCommandError" in str(err):
                return False, "companion_needs_addon"
            return False, "companion_cannot_connect"
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Companion ADB probe error: %s", type(err).__name__)
            if type(err).__name__ == "InvalidCommandError":
                return False, "companion_needs_addon"
            return False, "companion_cannot_connect"
        finally:
            await transport.close()
        if version is None:
            return False, "companion_app_not_found"
        return True, ""

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
            country  = user_input.get(CONF_COUNTRY, "us")

            await self.async_set_unique_id(f"{brand}_{username}")
            self._abort_if_unique_id_configured()

            try:
                await _validate_credentials(
                    self.hass, brand, username, password, country=country
                )
            except ValueError as err:
                err_str = str(err)
                if err_str.startswith("two_factor_required"):
                    self._pending_brand    = brand
                    self._pending_username = username
                    self._pending_password = password
                    self._pending_entry_data = self._build_entry_data(brand, username, password, user_input)
                    self._pending_user_input = dict(user_input)
                    return await self.async_step_mfa()
                errors["base"] = _map_error(err_str)
            else:
                portal_data = self._build_entry_data(
                    brand, username, password, user_input,
                )
                # b12 — VW/Audi + "enable MBB commands": the portal validated
                # above (reads); now chain to the MBB QR so the finish creates a
                # portal-primary entry WITH a durable-MBB command channel on top.
                # Other brands or unticked → plain portal entry, exactly as before.
                # v2.17.1 (#666) — Audi Car-Net added: the legacy bs/* command
                # catalog was extracted from the Audi DEX and the brand segment
                # maps ('audi'→'Audi'), so Audi is wire-viable. EXPERIMENTAL —
                # only legacy Car-Net Audis (pre-MEB) and unverified end-to-end.
                if (
                    user_input.get("enable_mbb_commands")
                    and brand in ("volkswagen", "audi")
                ):
                    self._pending_portal_data = portal_data
                    self._pending_portal_title = f"{_brand_label(brand)} — {username}"
                    self._dag_mbb = True
                    self._dag_mbb_command = True
                    self._dag_brand = brand
                    self._dag_user_input = dict(user_input)
                    self._dag_request_task = None
                    self._dag_poll_task = None
                    self._dag_user_code = ""
                    self._dag_verification_uri = ""
                    self._dag_device_code = ""
                    self._dag_tokens = None
                    self._dag_mbb_tokens = None
                    self._dag_mbb_client_id = ""
                    self._dag_mbb_ineligible = False
                    self._dag_user_id = ""
                    self._dag_error = ""
                    return await self.async_step_browser_login_pending()
                return self.async_create_entry(
                    title=f"{_brand_label(brand)} — {username}",
                    data=portal_data,
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
                enable_mbb_commands=bool(
                    suggested.get("enable_mbb_commands", False)
                ),
                country=suggested.get(CONF_COUNTRY, "us"),
            ),
            errors=errors,
        )

    async def async_step_website_authproxy(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.14.0 — OPT-IN, BETA: volkswagen.de website-authproxy login.

        Volkswagen-only, read-only channel. Collects email + password, drives
        the authproxy → Auth0 login, and either creates the entry (with the
        ``website_authproxy`` flag) or advances to the email-OTP step. The
        existing email_password / browser_login paths are untouched.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(f"volkswagen_web_{username}")
            self._abort_if_unique_id_configured()

            self._wap_username = username
            self._wap_user_input = dict(user_input)
            try:
                needs_otp = await self._wap_begin_login(username, password)
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                if needs_otp:
                    return await self.async_step_website_authproxy_otp()
                return self.async_create_entry(
                    title=f"Volkswagen.de (beta) — {username}",
                    data=self._build_website_entry_data(
                        username, user_input, self._wap_cookies,
                    ),
                )

        suggested = user_input or {}
        return self.async_show_form(
            step_id="website_authproxy",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_USERNAME,
                    default=suggested.get(CONF_USERNAME, vol.UNDEFINED),
                ): _USERNAME_SELECTOR,
                vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(
                        suggested.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ),
                ): _INTERVAL_SELECTOR,
            }),
            errors=errors,
        )

    async def async_step_website_authproxy_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.14.0 — email-OTP step for the website-authproxy login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = str(user_input.get("mfa_code", "")).strip()
            try:
                ok = await self._wap_submit_otp(code)
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                if ok:
                    return self.async_create_entry(
                        title=f"Volkswagen.de (beta) — {self._wap_username}",
                        data=self._build_website_entry_data(
                            self._wap_username, self._wap_user_input,
                            self._wap_cookies,
                        ),
                    )
                errors["base"] = "invalid_credentials"

        return self.async_show_form(
            step_id="website_authproxy_otp",
            data_schema=vol.Schema({
                vol.Required("mfa_code"): _MFA_SELECTOR,
            }),
            description_placeholders={"username": self._wap_username},
            errors=errors,
        )

    async def _wap_begin_login(self, username: str, password: str) -> bool:
        """Drive the authproxy login; return True if an OTP step is needed.

        Keeps the connector + its aiohttp session open across an OTP exchange
        (the cookie jar must survive). Maps connector errors to the same
        ValueError codes the email_password path uses, so the shared
        ``_map_error`` produces a localised message.
        """
        import aiohttp  # noqa: PLC0415

        from .cariad.auth._website_authproxy import (  # noqa: PLC0415
            WebsiteAuthProxyConnector,
        )
        from .cariad.exceptions import (  # noqa: PLC0415
            AuthenticationError,
            EmailTwoFactorRequiredError,
        )

        # Close any half-open connector from a prior attempt in this flow.
        await self._wap_close_session()
        connector_ssl = aiohttp.TCPConnector(ssl=True)
        self._wap_session = aiohttp.ClientSession(
            connector=connector_ssl,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        self._wap_connector = WebsiteAuthProxyConnector(
            self._wap_session, username, password, brand="volkswagen",
        )
        try:
            result = await self._wap_connector.begin_login()
        except EmailTwoFactorRequiredError:
            return True
        except AuthenticationError as err:
            await self._wap_close_session()
            _LOGGER.warning("Website authproxy login failed: %s", err)
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            await self._wap_close_session()
            _LOGGER.error(
                "Website authproxy unexpected error: %s", type(err).__name__,
            )
            raise ValueError("cannot_connect") from err
        if result == "otp_required":
            return True
        # Logged in without OTP — the validation succeeded. Capture the fresh
        # session cookies BEFORE closing the throwaway session so the runtime
        # coordinator can hydrate them and skip a fresh login + OTP prompt.
        self._wap_cookies = self._wap_capture_cookies()
        await self._wap_close_session()
        return False

    async def _wap_submit_otp(self, code: str) -> bool:
        """Submit the OTP against the open connector. Returns login success."""
        from .cariad.exceptions import AuthenticationError  # noqa: PLC0415

        if self._wap_connector is None:
            raise ValueError("cannot_connect")
        try:
            ok = bool(await self._wap_connector.submit_otp(code))
            # Capture the post-OTP session cookies BEFORE the finally-block
            # closes the session, so they can be persisted into entry.data.
            if ok:
                self._wap_cookies = self._wap_capture_cookies()
        except AuthenticationError as err:
            _LOGGER.warning("Website authproxy OTP failed: %s", err)
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Website authproxy OTP unexpected error: %s",
                type(err).__name__,
            )
            raise ValueError("cannot_connect") from err
        finally:
            await self._wap_close_session()
        return ok

    def _wap_capture_cookies(self) -> list[dict[str, Any]]:
        """Export the connector's volkswagen.de / vwgroup.io session cookies.

        Returns an empty list (never raises) when no connector is held or the
        export fails, so a capture hiccup can never block entry creation — the
        worst case is the runtime path falling back to a fresh login.
        """
        connector = self._wap_connector
        if connector is None:
            return []
        try:
            cookies = connector.export_cookies()
        except Exception:  # noqa: BLE001
            return []
        return cookies if isinstance(cookies, list) else []

    async def _wap_close_session(self) -> None:
        """Close the throwaway validation session + drop the connector."""
        sess = self._wap_session
        self._wap_session = None
        self._wap_connector = None
        if sess is not None:
            try:
                await sess.close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _build_website_entry_data(
        username: str,
        user_input: dict[str, Any],
        cookies: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Entry data for the website-authproxy (opt-in beta) mode.

        Carries the ``CONF_WEBSITE_AUTHPROXY`` flag the coordinator keys on,
        plus the standard credentials/interval. ``CONF_READ_ONLY`` is forced
        True (the channel cannot send commands), and ``CONF_BRAND`` is pinned
        to volkswagen.

        v2.14.3 — ``cookies`` are the volkswagen.de / vwgroup.io session cookies
        captured by the config flow after the login (incl. email-OTP) succeeded.
        Persisting them under ``CONF_WEBSITE_COOKIES`` lets the coordinator
        hydrate the jar at runtime so ``_arm_website_proxy`` resumes the session
        instead of re-prompting the email-OTP on every setup/restart.
        """
        return {
            CONF_BRAND:            "volkswagen",
            CONF_USERNAME:         username,
            CONF_PASSWORD:         user_input.get(CONF_PASSWORD, ""),
            CONF_WEBSITE_AUTHPROXY: True,
            CONF_WEBSITE_COOKIES:  cookies or [],
            CONF_READ_ONLY:        True,
            CONF_SCAN_INTERVAL: max(
                int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                MIN_SCAN_INTERVAL,
            ),
        }

    async def async_step_mbb_login(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.15.0 — Volkswagen EU durable MBB login (alpha) step 1.

        VW-pinned variant of the browser-login flow: no brand picker (the
        MBB recipe is VW-only), but it surfaces the S-PIN field so two-way
        lock/unlock works. Submits → reuse the exact same DAG QR/poll
        machinery (with the MBB client + scope, set via ``self._dag_mbb``).
        """
        if user_input is not None:
            # Reset DAG state for this MBB attempt.
            self._dag_mbb = True
            self._dag_mbb_fallback = False  # b15 — this is the VW MBB flow, not the Audi fallback
            self._dag_brand = "volkswagen"
            self._dag_user_input = dict(user_input)
            self._dag_request_task = None
            self._dag_poll_task = None
            self._dag_user_code = ""
            self._dag_verification_uri = ""
            self._dag_device_code = ""
            self._dag_tokens = None
            self._dag_mbb_tokens = None
            self._dag_mbb_client_id = ""
            self._dag_mbb_ineligible = False
            self._dag_user_id = ""
            self._dag_error = ""
            return await self.async_step_browser_login_pending()

        suggested: dict[str, Any] = user_input or {}
        return self.async_show_form(
            step_id="mbb_login",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_MBB_VINS, default=suggested.get(CONF_MBB_VINS, ""),
                ): TextSelector(TextSelectorConfig()),
                vol.Optional(
                    CONF_SPIN, default=suggested.get(CONF_SPIN, ""),
                ): _SPIN_SELECTOR,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(suggested.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                ): _INTERVAL_SELECTOR,
            }),
        )

    async def async_step_audi_mbb_fallback(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """b15 — arm the durable MBB command FALLBACK on an existing device-grant
        Audi. A device-grant Audi stores no password, so Reconfigure / Re-auth
        (both password-gated) can't reach it — this menu step runs a one-time MBB
        browser confirm and attaches the durable Car-Net bearer to the chosen Audi
        as a BFF-refusal fallback (``CONF_MBB_COMMAND_FALLBACK``), so lock / climate
        / charge survive a future device-grant revocation. Only Car-Net (pre-MEB)
        Audis are eligible; MEB / ID cars are rejected at the MBB exchange and the
        flow aborts with ``mbb_not_eligible``."""
        candidates = [
            e for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.data.get(CONF_BRAND) == "audi"
            and (e.data.get("dag_initial_tokens") or {}).get("strategy")
            == "device_grant"
            and not e.data.get(CONF_MBB_COMMAND_FALLBACK)
        ]
        if not candidates:
            return self.async_abort(reason="no_devicegrant_audi")

        if user_input is not None:
            self._mbb_fallback_entry_id = (
                user_input.get("entry_id") or candidates[0].entry_id
            )
            # Reset DAG state for the MBB attempt (mirrors async_step_mbb_login),
            # tagged as a fallback so browser_login_finish attaches rather than
            # creating a new entry.
            self._dag_mbb = True
            self._dag_mbb_fallback = True
            self._dag_brand = "audi"
            self._dag_request_task = None
            self._dag_poll_task = None
            self._dag_user_code = ""
            self._dag_verification_uri = ""
            self._dag_device_code = ""
            self._dag_tokens = None
            self._dag_mbb_tokens = None
            self._dag_mbb_client_id = ""
            self._dag_mbb_ineligible = False
            self._dag_user_id = ""
            self._dag_error = ""
            self._dag_user_input = dict(user_input)
            return await self.async_step_browser_login_pending()

        schema_dict: dict[Any, Any] = {}
        if len(candidates) > 1:
            schema_dict[vol.Required("entry_id")] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=e.entry_id, label=e.title)
                        for e in candidates
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            )
        schema_dict[vol.Optional(CONF_MBB_VINS, default="")] = TextSelector(
            TextSelectorConfig()
        )
        schema_dict[vol.Optional(CONF_SPIN, default="")] = _SPIN_SELECTOR
        return self.async_show_form(
            step_id="audi_mbb_fallback",
            data_schema=vol.Schema(schema_dict),
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
            if brand == "skoda":
                # v3.0.1 — VW revoked Škoda's device_code grant (403
                # unauthorized_client on identity.vwgroup.io). QR is dead for
                # Škoda only; the form no longer offers it, but a stale/crafted
                # payload lands here — send the user to email + password with a
                # clear reason instead of a silent form reload.
                errors["base"] = "skoda_qr_retired"
            elif brand not in DAG_ENABLED_BRANDS:
                # Defence in depth — the form should have filtered these
                # out already, but the user could send a crafted payload.
                errors["base"] = "brand_not_dag_eligible"
            else:
                # Reset state for this attempt.
                self._dag_mbb = False
                self._dag_mbb_fallback = False  # b15 — normal device grant, not the Audi MBB fallback
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
            return self.async_show_progress_done(
                next_step_id=(
                    "audi_mbb_fallback"
                    if self._dag_mbb_fallback
                    else "mbb_login" if self._dag_mbb else "browser_login"
                )
            )

        # Phase 1 done — hand off to Phase 2 (separate step_id so HA
        # re-renders the progress dialog with the populated placeholders).
        return self.async_show_progress_done(
            next_step_id="browser_login_approve"
        )

    async def async_step_browser_login_approve(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """v2.7.0b7 — Browser-login Phase 2: form-based URL display.

        Why a form instead of show_progress:

        Earlier betas (b4, b6) tried two-phase show_progress with
        description_placeholders to surface the verification URL +
        user_code. In practice the HA frontend kept showing a spinner
        without the placeholder text on multiple installs — even
        after a full HA restart. Root cause traced to HA's
        progress-dialog rendering pipeline caching the description by
        flow id and not always picking up placeholders from a
        show_progress call that wasn't the first one in the flow.

        Forms render the step description via the standard config_flow
        text pipeline which substitutes ``description_placeholders``
        reliably. Trading the auto-advance UX of show_progress for
        bulletproof URL/code visibility is the right trade-off — the
        user can see exactly what to do and gets immediate feedback
        when they click submit.

        Behaviour:
          - First entry: kick off background poll task, show form with
            URL + code as plain text, submit button visible.
          - User opens URL in their browser, signs in, approves.
          - User clicks submit:
            - poll task done + tokens → advance to finish step
            - poll task done + error → drop to brand picker (retry)
            - poll task still running → re-show form with
              ``still_waiting_browser`` error (user clicked too early).
        """
        # Defensive — should only be reached with Phase 1 state populated.
        if not self._dag_device_code:
            if self._dag_mbb_fallback:
                return await self.async_step_audi_mbb_fallback()
            return await self.async_step_browser_login()

        # Kick off poll_for_tokens() on first entry (idempotent)
        if self._dag_poll_task is None:
            self._dag_poll_task = self.hass.async_create_task(
                self._do_poll_tokens()
            )
            # v2.7.0b8 — Belt and suspenders: also fire a persistent
            # notification with URL + code so the user can copy it from
            # the HA sidebar even if the form description renders empty
            # (HA frontend cache / translation-loader edge cases have
            # bitten us multiple times). Notification dismisses itself
            # automatically when this step finishes.
            self._fire_dag_persistent_notification()
            # And log at WARNING so the URL surfaces in Settings → Logs
            # too. Third independent path to the same info.
            _LOGGER.warning(
                "VW Group Connect browser login: open %s on any device "
                "and confirm code %s. (Also shown in the dialog and in "
                "the HA notifications sidebar.)",
                self._dag_verification_uri,
                self._dag_user_code,
            )

        errors: dict[str, str] = {}

        if user_input is not None:
            # User clicked "I've approved" — check poll state
            if self._dag_poll_task.done():
                self._dismiss_dag_persistent_notification()
                # v2.15.0 — for the MBB flow, success also requires the
                # durable bearer to have been minted (register + exchange);
                # a poll-OK but mint-failed attempt must route back to retry.
                minted_ok = self._dag_tokens and (
                    not self._dag_mbb or self._dag_mbb_tokens is not None
                )
                if minted_ok:
                    return await self.async_step_browser_login_finish()
                # v2.15.0a8 — MBB exchange said "Unknown user": this car is a
                # newer ID/MEB model with no legacy Car-Net/MBB enrolment, so
                # MBB will never work for it. Abort with a clear pointer to the
                # EU Data Act / email-password channels rather than looping.
                if self._dag_mbb and self._dag_mbb_ineligible:
                    # b12 — when MBB was an add-on command channel on a portal
                    # entry, an MBB-ineligible (MEB/ID) car must NOT lose the
                    # portal reads: create the portal entry without commands.
                    if self._dag_mbb_command and self._pending_portal_data:
                        # b13 — flag the read-only fallback so the coordinator
                        # raises a clear "commands unavailable on this MEB/ID
                        # car" repair instead of silently missing the command
                        # entities the user ticked the box for.
                        return await self._create_or_update_portal_entry(
                            title=self._pending_portal_title,
                            data={**self._pending_portal_data,
                                  CONF_MEB_COMMANDS_UNAVAILABLE: True},
                        )
                    return self.async_abort(reason="mbb_not_eligible")
                # Poll/mint completed with error — reset state and route
                # back to the right brand/MBB picker so user can retry.
                self._dag_poll_task = None
                self._dag_device_code = ""
                if self._dag_mbb_fallback:
                    return await self.async_step_audi_mbb_fallback()
                if self._dag_mbb:
                    return await self.async_step_mbb_login()
                return await self.async_step_browser_login()
            # Clicked submit before poll completed — re-render with hint
            errors["base"] = "still_waiting_browser"

        # v2.7.0b9 — URL and user_code live INSIDE the form schema as
        # pre-filled selector fields, not just in the description
        # placeholders. Reason: on at least one real install the form
        # description rendered empty (translation-loader miss or HA
        # frontend quirk we still don't fully understand), but the
        # schema fields rendered fine. Pushing the critical content
        # into fields makes the URL and code visible no matter what
        # happens to the description.
        #
        # Field shape:
        #   - qr_code: QrCodeSelector renders the verification URL as
        #     a scannable QR code. User points their phone camera at
        #     the screen and gets to the login page in one tap.
        #   - verification_url: TextSelector pre-filled with the URL.
        #     User can copy-paste if they don't want to scan.
        #   - user_code: TextSelector pre-filled with the 8-char code.
        #     Copy-paste friendly.
        #   - approved_in_browser: BooleanSelector. The actual submit
        #     trigger. Defaults to True so the user just clicks Submit.
        #
        # Field NAMES are deliberately self-descriptive so the raw-key
        # fallback ("verification_url", "user_code") is still readable
        # if the translation lookup misses for any reason.
        confirm_schema = vol.Schema({
            vol.Required(
                "qr_code",
                default=self._dag_verification_uri,
            ): QrCodeSelector(
                QrCodeSelectorConfig(
                    data=self._dag_verification_uri,
                    scale=6,
                    error_correction_level=QrErrorCorrectionLevel.QUARTILE,
                )
            ),
            vol.Optional(
                "verification_url",
                default=self._dag_verification_uri,
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Optional(
                "user_code",
                default=self._dag_user_code,
            ): TextSelector(TextSelectorConfig()),
            vol.Required(
                "approved_in_browser",
                default=True,
            ): BooleanSelector(),
        })

        return self.async_show_form(
            step_id="browser_login_approve",
            data_schema=confirm_schema,
            description_placeholders={
                "verification_uri": self._dag_verification_uri,
                "user_code": self._dag_user_code,
            },
            errors=errors,
            last_step=False,
        )

    def _fire_dag_persistent_notification(self) -> None:
        """v2.7.0b8 — Side-channel display of the DAG URL + user_code.

        Fires a HA persistent_notification with the same content the
        form description shows. Independent rendering pipeline, so a
        translation-loader miss in the form does not also hide the
        notification. Notification id is fixed so it overwrites any
        prior one and gets dismissed cleanly when the flow advances.
        """
        from homeassistant.components.persistent_notification import (  # noqa: PLC0415
            async_create as pn_create,
        )

        message = (
            f"**1. Open this URL** on any device:\n\n"
            f"{self._dag_verification_uri}\n\n"
            f"**2. Sign in** to your Brand ID account.\n\n"
            f"**3. Confirm the code:** `{self._dag_user_code}`\n\n"
            f"**4. Go back to Settings > Devices & Services** and "
            f"click Submit / Weiter in the VW Group Connect dialog."
        )
        pn_create(
            self.hass,
            message,
            title="VW Group Connect - Browser Login",
            notification_id="vag_connect_browser_login",
        )

    def _dismiss_dag_persistent_notification(self) -> None:
        """Dismiss the URL + user_code notification.

        Called once the user clicks Submit (regardless of whether
        polling actually completed) so the notification does not
        linger after the flow advances.
        """
        from homeassistant.components.persistent_notification import (  # noqa: PLC0415
            async_dismiss as pn_dismiss,
        )

        pn_dismiss(self.hass, notification_id="vag_connect_browser_login")

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
            # v2.15.0 — durable MBB login uses the e-Remote client + ``mbb``
            # scope (NOT the DAG-dead VW app client), tagged strategy="mbb".
            if self._dag_mbb:
                from .cariad.auth._device_grant import (  # noqa: PLC0415
                    mbb_dag_config,
                )

                mbb_cfg = mbb_dag_config(self._dag_brand)
                if mbb_cfg is None:
                    raise ValueError(
                        "MBB durable login needs a Car-Net brand (Volkswagen or "
                        f"Audi); got {self._dag_brand}"
                    )
                mbb_client_id, mbb_scope = mbb_cfg
                self._dag_client = DeviceAuthorizationGrant(
                    self._dag_session,
                    mbb_client_id,
                    scope=mbb_scope,
                    strategy="mbb",
                )
            else:
                from .cariad.models import BRANDS as BRAND_CONFIGS  # noqa: PLC0415
                from .cariad.auth._device_grant import dag_idp_urls  # noqa: PLC0415

                brand_cfg = BRAND_CONFIGS[self._dag_brand]
                # v2.19.0 — Audi US/CA drives the flow against the NA IDP; every
                # other DAG brand keeps the EU IDP (defaults).
                _dev_auth_url, _tok_url = dag_idp_urls(self._dag_brand)
                self._dag_client = DeviceAuthorizationGrant(
                    self._dag_session,
                    brand_cfg.client_id,
                    scope=brand_cfg.scope,
                    device_auth_url=_dev_auth_url,
                    token_url=_tok_url,
                )
            try:
                code = await self._dag_client.request_device_code()
            except Exception as _dc_err:  # noqa: BLE001 — MBB failover only
                # MBB failover — if VW disabled the primary MBB client's device
                # grant (the way they killed 650d46ca on 2026-08-18), fall back to
                # the backup MBB client, which mints the same mbb-scoped token.
                # ONLY for the MBB flow and ONLY on an unauthorized_client-class
                # rejection; anything else re-raises unchanged.
                if not (self._dag_mbb and "unauthorized" in str(_dc_err).lower()):
                    raise
                from .cariad.auth._device_grant import (  # noqa: PLC0415
                    mbb_dag_backup_config,
                )
                _bk = mbb_dag_backup_config(self._dag_brand)
                if _bk is None:
                    raise
                _LOGGER.warning(
                    "MBB primary device-grant client rejected (%s) — failing over "
                    "to the backup MBB client",
                    type(_dc_err).__name__,
                )
                self._dag_client = DeviceAuthorizationGrant(
                    self._dag_session, _bk[0], scope=_bk[1], strategy="mbb",
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
            # v2.15.0 — durable MBB: exchange the freshly-minted ``mbb``-scoped
            # id_token for the durable MBB bearer via register/v1 + token
            # exchange. Runs HERE (Phase 2) so it reuses the still-open DAG
            # session before the finally-block closes it.
            if self._dag_mbb:
                from .cariad.auth import _mbboauth  # noqa: PLC0415

                mbb_tokens, mbb_client_id = await _mbboauth.mint_mbb_bearer(
                    self._dag_session, self._dag_tokens.id_token,
                )
                self._dag_mbb_tokens = mbb_tokens
                self._dag_mbb_client_id = mbb_client_id
                _LOGGER.info(
                    "MBB durable bearer minted (refresh_token present: %s)",
                    bool(mbb_tokens.refresh_token),
                )
        except Exception as err:  # noqa: BLE001 — flow-level catch
            self._dag_error = str(err)
            # v2.15.0a8 — the MBB token exchange returns
            # ``invalid_grant: "Unknown user"`` when the account/vehicle has no
            # legacy Car-Net/MBB enrolment — i.e. a newer ID/MEB car. That's
            # not a transient failure: MBB (durable login + commands) simply
            # doesn't cover MEB cars. Flag it so the flow aborts with a clear
            # "use EU Data Act instead" message rather than looping the VIN form.
            low = str(err).lower()
            if self._dag_mbb and ("unknown user" in low or "invalid_grant" in low):
                self._dag_mbb_ineligible = True
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

    async def _create_or_update_portal_entry(
        self, *, title: str, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Finalize a portal(+MBB) entry. When the MBB command channel was
        added to an EXISTING entry via Reconfigure (``_mbb_reconfigure_entry_id``),
        update that entry in place + reload; otherwise create a new entry."""
        if self._mbb_reconfigure_entry_id:
            entry = self.hass.config_entries.async_get_entry(
                self._mbb_reconfigure_entry_id
            )
            if entry is not None:
                self.hass.config_entries.async_update_entry(
                    entry, title=title, data=data
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
        return self.async_create_entry(title=title, data=data)

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

        # b15 — device-grant Audi command FALLBACK: the MBB QR just minted the
        # durable Car-Net bearer; attach it to an EXISTING device-grant Audi entry
        # as a BFF-refusal fallback (CONF_MBB_COMMAND_FALLBACK). Reached from
        # ``async_step_audi_mbb_fallback`` (menu) or the setup checkbox, both of
        # which set ``_dag_mbb_fallback`` + ``_mbb_fallback_entry_id``. The BFF
        # stays the command primary; MBB only steps in when the BFF refuses (401/
        # 403) — see coordinator ``_cariad_cmd``. If the MBB bearer never minted
        # (MEB/ID car), abort with the eligibility reason.
        if self._dag_mbb_fallback:
            if self._dag_mbb_tokens is None:
                return self.async_abort(reason="mbb_not_eligible")
            entry = self.hass.config_entries.async_get_entry(
                self._mbb_fallback_entry_id or ""
            )
            if entry is None:
                return self.async_abort(reason="reconfigure_failed")
            new_data = {
                **entry.data,
                CONF_MBB_COMMAND_FALLBACK: True,
                CONF_MBB_COMMAND_TOKENS: {
                    "access_token": self._dag_mbb_tokens.access_token,
                    "refresh_token": self._dag_mbb_tokens.refresh_token,
                    "id_token": self._dag_tokens.id_token,
                    "expires_at": self._dag_mbb_tokens.expires_at,
                    "strategy": "mbb",
                },
                CONF_MBB_COMMAND_CLIENT_ID: self._dag_mbb_client_id,
            }
            raw_vins = str(self._dag_user_input.get(CONF_MBB_VINS, "") or "")
            vins = [
                v.strip().upper()
                for v in raw_vins.replace(",", " ").split()
                if 11 <= len(v.strip()) <= 17
            ]
            if vins:
                new_data[CONF_MBB_VINS] = vins
            _spin = str(self._dag_user_input.get(CONF_SPIN, "") or "").strip()
            if _spin:
                new_data[CONF_SPIN] = _spin
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="mbb_fallback_armed")

        # b12 — Portal-primary entry WITH an MBB command channel: the QR just
        # minted the durable-MBB bearer; attach it to the pending portal entry
        # (reads) as a command channel. The portal's unique_id was already set +
        # de-duped in async_step_email_password, so don't touch it here.
        if self._dag_mbb_command:
            entry_data = dict(self._pending_portal_data)
            if self._dag_mbb_tokens is not None:
                entry_data[CONF_MBB_COMMAND_CHANNEL] = True
                entry_data[CONF_MBB_COMMAND_TOKENS] = {
                    "access_token": self._dag_mbb_tokens.access_token,
                    "refresh_token": self._dag_mbb_tokens.refresh_token,
                    "id_token": self._dag_tokens.id_token,
                    "expires_at": self._dag_mbb_tokens.expires_at,
                    "strategy": "mbb",
                }
                entry_data[CONF_MBB_COMMAND_CLIENT_ID] = self._dag_mbb_client_id
            else:
                # b13 — commands requested but the MBB bearer never minted
                # (MEB/ID car): keep the read-only portal entry and flag it so
                # the coordinator surfaces a clear "commands unavailable" repair.
                entry_data[CONF_MEB_COMMANDS_UNAVAILABLE] = True
            return await self._create_or_update_portal_entry(
                title=self._pending_portal_title, data=entry_data,
            )

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
        # v2.15.0 — durable MBB entry: persist the MBB bearer + refresh
        # (strategy="mbb") plus the registered X-Client-Id that minted it
        # (needed by every MBB refresh + read + command). Keep the OIDC
        # id_token too — its ``sub`` becomes the X-MbbUserId header.
        if self._dag_mbb:
            if self._dag_mbb_tokens is None:
                return self.async_abort(reason="dag_no_tokens")
            entry_data["dag_initial_tokens"] = {
                "access_token": self._dag_mbb_tokens.access_token,
                "refresh_token": self._dag_mbb_tokens.refresh_token,
                "id_token": self._dag_tokens.id_token,
                "expires_at": self._dag_mbb_tokens.expires_at,
                "strategy": "mbb",
            }
            entry_data["mbb_client_id"] = self._dag_mbb_client_id
            # v2.15.0a4 — the fal-scoped MBB bearer can't list the garage
            # (usermanagement 403s with XID_APP_VW), so persist the VIN(s)
            # the user supplied. Normalise to an uppercased list, splitting
            # on commas/whitespace and keeping plausible 11–17-char VINs.
            raw_vins = str(self._dag_user_input.get(CONF_MBB_VINS, "") or "")
            vins = [
                v.strip().upper()
                for v in raw_vins.replace(",", " ").split()
                if 11 <= len(v.strip()) <= 17
            ]
            entry_data[CONF_MBB_VINS] = vins
            return self.async_create_entry(
                title=f"Volkswagen EU (MBB) — {self._dag_user_id[:8]}…",
                data=entry_data,
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
            title=f"{_brand_label(self._dag_brand)} — {self._dag_user_id[:8]}…",
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
                    country=self._pending_entry_data.get(CONF_COUNTRY, "us"),
                )
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                # v2.22.2 — honour "enable MBB commands" on a 2FA account too.
                # The non-2FA path (async_step_email_password) chains VW/Audi +
                # ticked-box logins into the durable-MBB QR before creating the
                # entry; here that decision used to be dropped, so a 2FA VW/Audi
                # user who asked for commands got a read-only portal entry.
                ui = self._pending_user_input
                if (
                    ui.get("enable_mbb_commands")
                    and self._pending_brand in ("volkswagen", "audi")
                ):
                    self._pending_portal_data = self._pending_entry_data
                    self._pending_portal_title = (
                        f"{_brand_label(self._pending_brand)} — "
                        f"{self._pending_username}"
                    )
                    self._dag_mbb = True
                    self._dag_mbb_command = True
                    self._dag_brand = self._pending_brand
                    self._dag_user_input = dict(ui)
                    self._dag_request_task = None
                    self._dag_poll_task = None
                    self._dag_user_code = ""
                    self._dag_verification_uri = ""
                    self._dag_device_code = ""
                    self._dag_tokens = None
                    self._dag_mbb_tokens = None
                    self._dag_mbb_client_id = ""
                    self._dag_mbb_ineligible = False
                    self._dag_user_id = ""
                    self._dag_error = ""
                    return await self.async_step_browser_login_pending()
                return self.async_create_entry(
                    title=f"{_brand_label(self._pending_brand)} — {self._pending_username}",
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
            country  = reauth_entry.data.get(CONF_COUNTRY, "us")

            try:
                await _validate_credentials(
                    self.hass, brand, username, password, country=country
                )
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
            country  = user_input.get(CONF_COUNTRY, "us")

            try:
                await _validate_credentials(
                    self.hass, brand, username, password, country=country
                )
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                new_unique_id = f"{brand}_{username}"
                await self.async_set_unique_id(new_unique_id)
                # v2.17.1 (#584) — abort ONLY if the account was changed to one
                # that already has its own entry. Reconfiguring the SAME account
                # must update in place; the old `_abort_if_unique_id_configured(
                # updates=...)` matched the very entry being reconfigured and
                # aborted with "already configured", making Reconfigure (and the
                # MBB toggle it surfaces) unreachable for existing users.
                account_changed = new_unique_id != entry.unique_id
                if account_changed:
                    self._abort_if_unique_id_configured()

                base = self._build_entry_data(brand, username, password, user_input)
                # v2.17.2 — for the SAME account, MERGE so a credential update
                # keeps everything the base builder doesn't own: the durable-MBB
                # command channel, supplementary-portal creds, DAG tokens (the
                # old code passed only base fields, silently wiping an existing
                # two-way channel on every Reconfigure). For a DIFFERENT account
                # (unique_id changed) do a clean rebuild — carrying the previous
                # account's brand-specific tokens forward would be wrong.
                merged = base if account_changed else {**entry.data, **base}

                # v2.17.2 (#666) — arm the durable-MBB command channel on an
                # EXISTING portal entry via Reconfigure (VW/Audi). Mirrors the
                # initial email_password MBB chain; the QR finish/approve steps
                # update THIS entry in place (see _mbb_reconfigure_entry_id +
                # _create_or_update_portal_entry).
                #
                # v2.18.0 (#584) — this used to also require the channel NOT to
                # be on already, which turned re-approval into a dead end: the
                # one moment you need to re-run the QR flow is when the channel
                # is armed but its tokens are gone, and that was the exact case
                # the guard excluded. Ticking the box did nothing, and the only
                # escape was delete + re-add — which renames every entity and
                # takes the user's dashboards and automations with it.
                #
                # So a ticked box now always offers the approval, and submitting
                # Reconfigure with MBB on means "re-approve". Reconfigure already
                # demands the password, so this is not a surprise step.
                if (
                    user_input.get("enable_mbb_commands")
                    and brand in ("volkswagen", "audi")
                ):
                    self._mbb_reconfigure_entry_id = entry.entry_id
                    self._pending_portal_data = merged
                    self._pending_portal_title = f"{_brand_label(brand)} — {username}"
                    self._dag_mbb = True
                    self._dag_mbb_command = True
                    self._dag_brand = brand
                    self._dag_user_input = dict(user_input)
                    self._dag_request_task = None
                    self._dag_poll_task = None
                    self._dag_user_code = ""
                    self._dag_verification_uri = ""
                    self._dag_device_code = ""
                    self._dag_tokens = None
                    self._dag_mbb_tokens = None
                    self._dag_mbb_client_id = ""
                    self._dag_mbb_ineligible = False
                    self._dag_user_id = ""
                    self._dag_error = ""
                    return await self.async_step_browser_login_pending()

                self.hass.config_entries.async_update_entry(
                    entry,
                    title=f"{_brand_label(brand)} — {username}",
                    unique_id=new_unique_id,
                    data=merged,
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
                # v2.18.0 (#584) — this argument was simply not passed, so the
                # box fell back to its `False` default and rendered unticked for
                # everyone, including users whose MBB channel was on. It read as
                # "MBB is off" while the code believed it was on, and the two
                # disagreeing is what made the dead end above inescapable: the
                # form told you to tick a box that was already effectively set.
                # Note the schema field is named enable_mbb_commands but the
                # stored key is CONF_MBB_COMMAND_CHANNEL — they are not the same
                # string, which is how this stayed invisible.
                enable_mbb_commands=bool(current.get(CONF_MBB_COMMAND_CHANNEL, False)),
                country=current.get(CONF_COUNTRY, "us"),
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
        data: dict[str, Any] = {
            CONF_BRAND:         brand,
            CONF_USERNAME:      username,
            CONF_PASSWORD:      password,
            CONF_SPIN:          user_input.get(CONF_SPIN, ""),
            CONF_SCAN_INTERVAL: max(
                int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                MIN_SCAN_INTERVAL,
            ),
        }
        # v2.15.5 — the US/Canada region picker is ONLY meaningful for the
        # volkswagen_na brand (it selects the MYVW client_id + API host).
        # Previously we stamped CONF_COUNTRY="us" onto EVERY brand's entry,
        # which polluted Swiss/EU entries with a bogus country="us" (the
        # field is shown to all email/password brands via the shared schema).
        # It is harmless downstream — the EU Data Act portal builds its OIDC
        # state from its own country/language defaults ("de__de__BRAND"), not
        # from CONF_COUNTRY — but it is misleading in diagnostics and a latent
        # trap. So we only persist it for volkswagen_na; every other brand
        # leaves it unset (the coordinator/factory already default to "us"
        # for the VW-NA path that is the only consumer).
        if brand.lower() == "volkswagen_na":
            data[CONF_COUNTRY] = user_input.get(CONF_COUNTRY, "us")
        return data


# ── Options Flow ──────────────────────────────────────────────────────────────

# ── v2.19.0: Tibber Data-API OAuth2 (auth-code + PKCE) config-flow constants ─
_TIBBER_REDIRECT_URI = "https://my.home-assistant.io/redirect/oauth"


def _tibber_pkce_challenge(verifier: str) -> str:
    """S256 PKCE challenge (base64url, no padding) for a code verifier."""
    import base64  # noqa: PLC0415
    import hashlib  # noqa: PLC0415
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class VagConnectOptionsFlow(config_entries.OptionsFlow):
    """Scan interval + S-PIN without full reconfigure."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        # b1/C1 — state for the optional "add vw.de read channel" sub-flow.
        self._ovw_session: Any = None
        self._ovw_connector: Any = None
        self._ovw_cookies: list[dict[str, Any]] = []
        self._ovw_username: str = ""
        self._ovw_pending_options: dict[str, Any] = {}
        # VW EU Two-Way (650d46ca) opt-in: options stashed while the login sub-flow runs
        self._vweu_pending_options: dict[str, Any] = {}
        # b8/C1 — state for the "add EU Data Act portal read channel" sub-flow.
        self._oportal_pending_options: dict[str, Any] = {}
        # v2.19.0 — state for the "add Tibber read channel" OAuth2 sub-flow.
        self._otib_pending_options: dict[str, Any] = {}
        self._otib_client_id: str = ""
        self._otib_client_secret: str = ""
        self._otib_verifier: str = ""
        self._otib_state: str = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Options: scan interval, S-PIN, reverse geocoding opt-in."""
        from .const import (  # noqa: PLC0415
            CONF_VWEU_DEVICE_GRANT,
            CONF_VWEU_TWOWAY_COOKIES,
            CONF_VWEU_TWOWAY_EMAIL,
            CONF_VWEU_TWOWAY_PASSWORD,
            CONF_VWEU_TWOWAY_TOKENS,
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            # v2.15.5 — ABRP: if the user flipped the master switch on, both
            # the developer api_key and the per-vehicle token must be set,
            # else the sender can't authenticate. Re-show the form with an
            # error instead of saving a half-configured (silently dormant)
            # state. The values themselves never get logged.
            if user_input.get(CONF_ABRP_ENABLE):
                if not (user_input.get(CONF_ABRP_API_KEY) or "").strip() or not (
                    user_input.get(CONF_ABRP_USER_TOKEN) or ""
                ).strip():
                    errors["base"] = "abrp_credentials_required"

        # Only persist / branch when the submit validated cleanly. On an
        # error we fall through to re-show the form (with ``errors``) below.
        if user_input is not None and not errors:
            # v2.17.5 (#759) — fold the per-VIN S-PIN fields into one
            # CONF_SPIN_BY_VIN dict and drop the transient per-field keys so they
            # never persist as standalone options. Empty fields = shared S-PIN.
            _by_vin: dict[str, str] = {}
            _had_per_vin_fields = False
            for _k in list(user_input.keys()):
                if _k.startswith(f"{CONF_SPIN_BY_VIN}_"):
                    _had_per_vin_fields = True
                    _val = str(user_input.pop(_k) or "").strip()
                    if _val:
                        _by_vin[_k[len(CONF_SPIN_BY_VIN) + 1:]] = _val
            if _had_per_vin_fields:
                # Write the resolved dict UNCONDITIONALLY (even when empty) so
                # blanking a field actually clears that VIN's override. Before,
                # an empty result left the key absent, and the options→data fold
                # (see the entry.options trap) then kept the stale value — so a
                # per-VIN S-PIN could never be removed once set (#759 follow-up).
                user_input[CONF_SPIN_BY_VIN] = _by_vin
            # b1/C1 — if the user ticked "add vw.de read channel", branch into
            # the login sub-flow; the remaining options are saved when it
            # completes. Default-False so untouched submits behave exactly as
            # before (the flag is popped so it's never stored as an option).
            if user_input.pop(CONF_SUPPLEMENTARY_AUTHPROXY, False):
                self._ovw_pending_options = dict(user_input)
                return await self.async_step_add_vwde()
            # VW EU Two-Way (650d46ca): opt-in two-way commands + modern BFF reads
            # via a headless device-grant login. Ticking it routes to the login
            # sub-flow; the remaining options are saved when it completes.
            # Volkswagen-gated on submit; default False = no change.
            if user_input.pop(CONF_VWEU_DEVICE_GRANT, False):
                self._vweu_pending_options = dict(user_input)
                return await self.async_step_add_vweu_twoway()
            # b8/C1 — add the EU Data Act portal as a supplementary read channel
            # (email/pw, no OTP) to fill the reads a command primary (MBB) lacks.
            if user_input.pop(CONF_SUPPLEMENTARY_EU_PORTAL, False):
                self._oportal_pending_options = dict(user_input)
                return await self.async_step_add_portal()
            # v2.19.0 — add Tibber as a supplementary read channel (OAuth2 auth-
            # code+PKCE). Branches into the two-step client-id → authorize sub-
            # flow; the remaining options are saved when it completes.
            if user_input.pop(CONF_SUPPLEMENTARY_TIBBER, False):
                self._otib_pending_options = dict(user_input)
                return await self.async_step_add_tibber()
            # b11 — OFF-switch for the supplementary channels. Without this a
            # channel could only ever be ADDED (the toggles above route on True),
            # so a stuck/dead/redundant supplementary kept failing every restart
            # with no way to remove it. Ticking a remove-toggle clears it from
            # entry.data + reloads. Shown in the schema only when it's active.
            # VW EU Two-Way rollback: clear the flag + all stored creds/tokens
            # and reload; the coordinator then reverts to the normal auth chain.
            if user_input.pop("remove_vweu_twoway", False):
                new_data = {**self._config_entry.data}
                for _vk in (
                    CONF_VWEU_DEVICE_GRANT, CONF_VWEU_TWOWAY_TOKENS,
                    CONF_VWEU_TWOWAY_EMAIL, CONF_VWEU_TWOWAY_PASSWORD,
                    CONF_VWEU_TWOWAY_COOKIES,
                ):
                    new_data.pop(_vk, None)
                # v4.0.0 — if enabling two-way auto-carried the EU Data Act
                # portal over as a supplementary gap-filler, remove THAT here so
                # reverting to EU-DA-primary doesn't leave EU-DA armed twice
                # (primary + redundant supplementary). Only the auto-carried one
                # (marker) is touched — a user's own supplementary stays.
                if new_data.pop(CONF_VWEU_TWOWAY_ADDED_EU_PORTAL, False):
                    new_data.pop(CONF_SUPPLEMENTARY_EU_PORTAL, None)
                    new_data.pop(CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME, None)
                    new_data.pop(CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD, None)
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data,
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._config_entry.entry_id)
                )
                return self.async_create_entry(title="", data=dict(user_input))
            remove_web = user_input.pop("remove_supplementary_authproxy", False)
            remove_portal = user_input.pop("remove_supplementary_eu_portal", False)
            remove_tibber = user_input.pop("remove_supplementary_tibber", False)
            if remove_web or remove_portal or remove_tibber:
                new_data = {**self._config_entry.data}
                if remove_web:
                    new_data.pop(CONF_SUPPLEMENTARY_AUTHPROXY, None)
                    new_data.pop(CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES, None)
                if remove_portal:
                    new_data.pop(CONF_SUPPLEMENTARY_EU_PORTAL, None)
                    new_data.pop(CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME, None)
                    new_data.pop(CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD, None)
                if remove_tibber:
                    new_data.pop(CONF_SUPPLEMENTARY_TIBBER, None)
                    new_data.pop(CONF_SUPPLEMENTARY_TIBBER_TOKENS, None)
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data,
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(
                        self._config_entry.entry_id
                    )
                )
                return self.async_create_entry(title="", data=user_input)
            return self.async_create_entry(title="", data=user_input)

        current_data = self._config_entry.data
        current_options = self._config_entry.options
        schema: dict[Any, Any] = {
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
                # Optional nameplate NET battery capacity (kWh) for the
                # State-of-Health sensor. 0 = off (no SoH). VW ships no SoH field,
                # so the user supplies the nameplate and we compute
                # current-max / nominal.
                vol.Optional(
                    CONF_BATTERY_NOMINAL_KWH,
                    default=current_options.get(
                        CONF_BATTERY_NOMINAL_KWH,
                        current_data.get(CONF_BATTERY_NOMINAL_KWH, 0),
                    ),
                ): _KWH_SELECTOR,
                # Optional fuel-tank capacity (litres) so a litres-only source
                # (acpp plug&play) can show a fuel-level %. 0 = off (litres only).
                vol.Optional(
                    CONF_FUEL_TANK_CAPACITY,
                    default=current_options.get(
                        CONF_FUEL_TANK_CAPACITY,
                        current_data.get(CONF_FUEL_TANK_CAPACITY, 0),
                    ),
                ): _LITERS_SELECTOR,
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
                # #923 — opt-in test cohort. When ticked, the integration may run
                # experimental reads/probes (e.g. the vw.de parkingposition GPS
                # lever) and surface a dismissible Repair asking the user to share
                # aggressively-redacted diagnostics so a capability can be
                # confirmed for their model. Persistent bool, default OFF; read
                # via entry.data (options are folded into data by the listener).
                vol.Optional(
                    CONF_TEST_COHORT,
                    default=current_options.get(
                        CONF_TEST_COHORT,
                        current_data.get(CONF_TEST_COHORT, False),
                    ),
                ): _BOOL_SELECTOR,
                # P1-5 — opt-in diagnostic archive of raw EU Data Act dataset
                # ZIPs. Default OFF: raw datasets carry GPS + VIN + telemetry, so
                # keeping the last few on disk is a privacy trade the user makes
                # knowingly. Only meaningful on the EU Data Act portal channel;
                # harmless toggle on other channels (nothing writes it).
                vol.Optional(
                    CONF_KEEP_RAW_DATASETS,
                    default=current_options.get(
                        CONF_KEEP_RAW_DATASETS,
                        current_data.get(CONF_KEEP_RAW_DATASETS, False),
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
                # v2.10.4 - OAuth client_id override. Power-user escape
                # hatch for when the community spots a fresh client_id
                # in a new APK before our daily atlas builder catches
                # it. Pasted value is prepended to the resolver chain
                # so it gets tried first; the existing fallbacks stay
                # in place. Empty string = no override. Format must
                # match "UUID@apps_vw-dilab_com" or the resolver
                # silently drops it.
                vol.Optional(
                    CONF_CLIENT_ID_OVERRIDE,
                    default=current_options.get(
                        CONF_CLIENT_ID_OVERRIDE,
                        current_data.get(CONF_CLIENT_ID_OVERRIDE, ""),
                    ),
                ): str,
                # v2.10.5 - EU Data Act portal Custom Data Request
                # auto-kickoff. Only meaningful when the integration
                # is operating in read-only data_act_portal mode (live
                # BFF strategies exhausted). When True, the coordinator
                # checks at startup whether an active 15-min Custom
                # Request exists for each VIN and creates one when
                # none does — without it a VW EU car shows NO data.
                # DEFAULT ON, matching the runtime default in
                # coordinator._ensure_data_act_custom_request_kickoff
                # (v2.17.1). It MUST stay True here: rendering the toggle
                # default-False meant a user who merely opened + saved
                # Configure (e.g. to set the S-PIN) silently persisted
                # auto_kickoff=False and killed their own portal feed.
                vol.Optional(
                    CONF_EU_DATA_ACT_AUTO_KICKOFF,
                    default=current_options.get(
                        CONF_EU_DATA_ACT_AUTO_KICKOFF,
                        current_data.get(
                            CONF_EU_DATA_ACT_AUTO_KICKOFF, True,
                        ),
                    ),
                ): _BOOL_SELECTOR,
                # b3 — hide entities without data (default on) so the device
                # isn't flooded with "unknown" sensors; an entity still appears
                # the moment its value arrives. Off = show every entity.
                vol.Optional(
                    CONF_HIDE_EMPTY_ENTITIES,
                    default=current_options.get(
                        CONF_HIDE_EMPTY_ENTITIES,
                        current_data.get(CONF_HIDE_EMPTY_ENTITIES, True),
                    ),
                ): _BOOL_SELECTOR,
                # v2.15.5 — ABRP (A Better Routeplanner) live telemetry push.
                # Three opt-in fields, all default-dormant. The api_key is a
                # DEVELOPER key you register with iternio (we don't ship one —
                # hardcoding a key we don't own would be impersonation). The
                # token is the per-vehicle "Generic" token from the ABRP app
                # (Settings → car → Live Data). With the enable switch off, or
                # either field blank, the sender makes zero outbound calls.
                vol.Optional(
                    CONF_ABRP_ENABLE,
                    default=current_options.get(
                        CONF_ABRP_ENABLE,
                        current_data.get(CONF_ABRP_ENABLE, False),
                    ),
                ): _BOOL_SELECTOR,
                vol.Optional(
                    CONF_ABRP_API_KEY,
                    default=current_options.get(
                        CONF_ABRP_API_KEY,
                        current_data.get(CONF_ABRP_API_KEY, ""),
                    ),
                ): _PASSWORD_SELECTOR,
                vol.Optional(
                    CONF_ABRP_USER_TOKEN,
                    default=current_options.get(
                        CONF_ABRP_USER_TOKEN,
                        current_data.get(CONF_ABRP_USER_TOKEN, ""),
                    ) if isinstance(
                        current_options.get(
                            CONF_ABRP_USER_TOKEN,
                            current_data.get(CONF_ABRP_USER_TOKEN, ""),
                        ),
                        str,
                    ) else "",
                ): _PASSWORD_SELECTOR,
                # b1/C1 — opt-in: add (or refresh) a supplementary read-only
                # volkswagen.de channel that the coordinator merges onto this
                # entry's primary data (VIN/odometer/service/master). Ticking it
                # routes to the vw.de login; default False = no change. Brand-
                # gated to volkswagen on submit.
                vol.Optional(
                    CONF_SUPPLEMENTARY_AUTHPROXY,
                    default=False,
                ): _BOOL_SELECTOR,
                # b8/C1 — opt-in: add the EU Data Act portal as a supplementary
                # read channel (email/pw, no OTP) to fill the reads a command
                # primary (MBB) can't. Default False = no change.
                vol.Optional(
                    CONF_SUPPLEMENTARY_EU_PORTAL,
                    default=False,
                ): _BOOL_SELECTOR,
                # v2.19.0 — opt-in: add Tibber (OAuth2) as a supplementary
                # read-only EV source, merged onto the primary as the LOWEST-
                # trust gap-fill. Ticking it routes to the Tibber OAuth sub-flow;
                # default False = no change.
                vol.Optional(
                    CONF_SUPPLEMENTARY_TIBBER,
                    default=False,
                ): _BOOL_SELECTOR,
        }
        # b11 — only surface a remove-toggle for a channel that's actually
        # active, so a stuck/redundant supplementary can be turned off (and the
        # form stays uncluttered for everyone else).
        if current_data.get(CONF_SUPPLEMENTARY_AUTHPROXY):
            schema[vol.Optional(
                "remove_supplementary_authproxy", default=False,
            )] = _BOOL_SELECTOR
        if current_data.get(CONF_SUPPLEMENTARY_EU_PORTAL):
            schema[vol.Optional(
                "remove_supplementary_eu_portal", default=False,
            )] = _BOOL_SELECTOR
        if current_data.get(CONF_SUPPLEMENTARY_TIBBER):
            schema[vol.Optional(
                "remove_supplementary_tibber", default=False,
            )] = _BOOL_SELECTOR
        # VW EU Two-Way (650d46ca): Volkswagen-only. Show the add-toggle for a VW
        # entry that has not armed it, and a remove-toggle once armed (so it can
        # be rolled back without deleting the integration). The add-toggle is
        # hidden while VWEU_TWOWAY_DISABLED — VW disabled the 650d46ca device_code
        # grant on 2026-08-18 (device_authorization → 403 unauthorized_client), so
        # a fresh channel can't mint. All the flow code is preserved; flipping
        # VWEU_TWOWAY_DISABLED back to False re-offers the toggle unchanged.
        if current_data.get(CONF_BRAND) == "volkswagen":
            from .cariad.auth._device_grant import (  # noqa: PLC0415
                VWEU_TWOWAY_DISABLED,
            )
            if current_data.get(CONF_VWEU_DEVICE_GRANT):
                schema[vol.Optional(
                    "remove_vweu_twoway", default=False,
                )] = _BOOL_SELECTOR
            elif not VWEU_TWOWAY_DISABLED:
                schema[vol.Optional(
                    CONF_VWEU_DEVICE_GRANT, default=False,
                )] = _BOOL_SELECTOR
        # Škoda official public API — opt-in FAILOVER key. A Škoda entry may add
        # an API key it minted in the app (Settings → Smart Home → API Keys,
        # v8.16+); the official API is then read ONLY when the primary channel
        # hard-fails (it is rate-limited to 20 req/hour/key, so never polled
        # continuously). Pre-filled so re-opening options never blanks it.
        if current_data.get(CONF_BRAND) == "skoda":
            from .const import CONF_SKODA_OFFICIAL_API_KEY  # noqa: PLC0415
            schema[vol.Optional(
                CONF_SKODA_OFFICIAL_API_KEY,
                default=str(current_options.get(
                    CONF_SKODA_OFFICIAL_API_KEY,
                    current_data.get(CONF_SKODA_OFFICIAL_API_KEY, ""),
                )),
            )] = _PASSWORD_SELECTOR
        # v2.17.5 (#759) — one optional S-PIN field per known VIN, shown only
        # when the account has more than one vehicle (each may carry its own
        # S-PIN). Empty leaves that vehicle on the shared CONF_SPIN above; values
        # are folded into CONF_SPIN_BY_VIN on submit.
        _coord = getattr(self._config_entry, "runtime_data", None)
        _vehicles = getattr(_coord, "vehicles", None)
        # v2.18.0 — options THEN data, like every other field above. The update
        # listener folds options into entry.data and blanks entry.options, so an
        # options-only read showed these fields blank even after they were set,
        # and submitting the form then wrote the blanks back over the saved map.
        _cur_by_vin = current_options.get(
            CONF_SPIN_BY_VIN, current_data.get(CONF_SPIN_BY_VIN)
        )
        if not isinstance(_cur_by_vin, dict):
            _cur_by_vin = {}
        if isinstance(_vehicles, dict) and len(_vehicles) > 1:
            for _vin in _vehicles:
                schema[vol.Optional(
                    f"{CONF_SPIN_BY_VIN}_{_vin}",
                    default=str(_cur_by_vin.get(_vin, "")),
                )] = _SPIN_SELECTOR
        # v2.26.0 — companion (ADB) advanced opt-ins, surfaced only for a
        # companion entry (both default OFF: each TAPS the phone, so a user opts
        # in only after confirming the flow on their own device).
        from .const import (  # noqa: PLC0415
            CONF_COMPANION_READ_CHARGE_DETAIL,
            CONF_COMPANION_WAKE_SLEEP,
            CONF_STRATEGY,
            STRATEGY_COMPANION_ADB,
        )
        if current_data.get(CONF_STRATEGY) == STRATEGY_COMPANION_ADB:
            schema[vol.Optional(
                CONF_COMPANION_READ_CHARGE_DETAIL,
                default=current_options.get(
                    CONF_COMPANION_READ_CHARGE_DETAIL,
                    current_data.get(CONF_COMPANION_READ_CHARGE_DETAIL, False),
                ),
            )] = _BOOL_SELECTOR
            schema[vol.Optional(
                CONF_COMPANION_WAKE_SLEEP,
                default=current_options.get(
                    CONF_COMPANION_WAKE_SLEEP,
                    current_data.get(CONF_COMPANION_WAKE_SLEEP, False),
                ),
            )] = _BOOL_SELECTOR
            # v4.4.0 (#968) — the deeper nav-read opt-ins. Each walks further
            # into the app than the charge-detail read, so each is its own
            # toggle and each defaults to OFF.
            from .const import (  # noqa: PLC0415
                CONF_COMPANION_READ_CLIMATE_DETAIL,
                CONF_COMPANION_READ_PARKING_POSITION,
                CONF_COMPANION_READ_VEHICLE_HEALTH,
            )
            for _key in (
                CONF_COMPANION_READ_VEHICLE_HEALTH,
                CONF_COMPANION_READ_CLIMATE_DETAIL,
                CONF_COMPANION_READ_PARKING_POSITION,
            ):
                schema[vol.Optional(
                    _key,
                    default=current_options.get(
                        _key, current_data.get(_key, False)
                    ),
                )] = _BOOL_SELECTOR
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    # ── b8/C1: supplementary EU Data Act portal read-channel sub-flow ───────

    async def async_step_add_portal(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect EU Data Act portal credentials (email/pw, no OTP), validate
        with a test login, and store them as a supplementary read channel that
        the coordinator merges onto the primary (e.g. MBB) — filling SoC /
        charging / odometer / service that the primary can't read."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await self._oportal_test_login(email, password)
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={
                        **self._config_entry.data,
                        CONF_SUPPLEMENTARY_EU_PORTAL: True,
                        CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME: email,
                        CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD: password,
                    },
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(
                        self._config_entry.entry_id
                    )
                )
                return self.async_create_entry(
                    title="", data=self._oportal_pending_options
                )

        return self.async_show_form(
            step_id="add_portal",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): _USERNAME_SELECTOR,
                vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
            }),
            errors=errors,
        )

    async def _oportal_test_login(self, email: str, password: str) -> None:
        """Validate the portal credentials with a throwaway login. Raises
        ValueError(code) on failure so _map_error renders a localised message."""
        import aiohttp  # noqa: PLC0415

        from .cariad.auth._eu_data_act import EUDataActConnector  # noqa: PLC0415
        from .cariad.exceptions import (  # noqa: PLC0415
            AuthenticationError,
            EmailTwoFactorRequiredError,
            MarketingConsentError,
            PortalInteractionRequiredError,
            RateLimitError,
            TermsAndConditionsError,
            TwoFactorRequiredError,
        )

        brand = str(self._config_entry.data.get(CONF_BRAND, "")) or "volkswagen"
        session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=True),
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        try:
            connector = EUDataActConnector(session, brand=brand)
            await connector.login(email, password)
        # v2.15.4 (#527) — the portal login can stop on a non-credential
        # step (T&C / consent / 2FA / onboarding / soft block). Map each to
        # its existing distinct code so valid-credential users are NOT told
        # to fix their password. Subclass order: Email-2FA before its 2FA
        # parent; the generic AuthenticationError catch-all stays LAST.
        except TermsAndConditionsError as err:
            raise ValueError("terms_and_conditions") from err
        except MarketingConsentError as err:
            raise ValueError("marketing_consent") from err
        except EmailTwoFactorRequiredError as err:
            raise ValueError("two_factor_required") from err
        except TwoFactorRequiredError as err:
            raise ValueError("two_factor_required") from err
        except RateLimitError as err:
            raise ValueError("too_many_requests") from err
        except PortalInteractionRequiredError as err:
            raise ValueError("portal_interaction_required") from err
        except AuthenticationError as err:
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            raise ValueError("cannot_connect") from err
        finally:
            try:
                await session.close()
            except Exception:  # noqa: BLE001
                pass

    # ── v2.19.0: supplementary Tibber Data-API read-channel sub-flow ────────

    async def async_step_add_tibber(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1 of the Tibber OAuth2 (auth-code+PKCE) sub-flow: collect the
        user's own Data-API client (id + secret, created at
        data-api.tibber.com/clients/manage). We then build the authorize URL and
        move to the code-paste step. Read-only — Tibber has no vehicle commands.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = str(user_input.get("tibber_client_id", "")).strip()
            client_secret = str(
                user_input.get("tibber_client_secret", "")
            ).strip()
            if not client_id or not client_secret:
                errors["base"] = "invalid_credentials"
            else:
                import secrets  # noqa: PLC0415
                self._otib_client_id = client_id
                self._otib_client_secret = client_secret
                # RFC 7636: verifier is 43-128 unreserved chars (token_urlsafe
                # yields A-Za-z0-9-_, all valid); state guards against CSRF.
                self._otib_verifier = secrets.token_urlsafe(48)
                self._otib_state = secrets.token_urlsafe(16)
                return await self.async_step_tibber_authorize()
        return self.async_show_form(
            step_id="add_tibber",
            data_schema=vol.Schema({
                vol.Required("tibber_client_id"): _USERNAME_SELECTOR,
                vol.Required("tibber_client_secret"): _PASSWORD_SELECTOR,
            }),
            errors=errors,
            description_placeholders={
                "manage_url": "https://data-api.tibber.com/clients/manage",
                "redirect_uri": _TIBBER_REDIRECT_URI,
            },
        )

    async def async_step_tibber_authorize(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: the user opens the authorize URL, grants access, and pastes
        back the redirected URL (or the bare code). We exchange it for tokens
        (PKCE) and store them as the supplementary Tibber channel in entry.data.
        """
        errors: dict[str, str] = {}
        authorize_url = self._otib_authorize_url()
        if user_input is not None:
            try:
                code = self._otib_extract_code(
                    str(user_input.get("tibber_auth_response", "")).strip()
                )
                tokens = await self._otib_exchange_code(code)
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={
                        **self._config_entry.data,
                        CONF_SUPPLEMENTARY_TIBBER: True,
                        CONF_SUPPLEMENTARY_TIBBER_TOKENS: tokens,
                    },
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(
                        self._config_entry.entry_id
                    )
                )
                return self.async_create_entry(
                    title="", data=self._otib_pending_options
                )
        return self.async_show_form(
            step_id="tibber_authorize",
            data_schema=vol.Schema({
                vol.Required("tibber_auth_response"): _USERNAME_SELECTOR,
            }),
            errors=errors,
            description_placeholders={"authorize_url": authorize_url},
        )

    def _otib_authorize_url(self) -> str:
        """Build the Tibber authorize URL with PKCE (S256) + CSRF state."""
        from urllib.parse import urlencode  # noqa: PLC0415
        from .cariad._tibber_source import (  # noqa: PLC0415
            TIBBER_AUTHORIZE_URL,
            TIBBER_SCOPES,
        )
        params = {
            "response_type": "code",
            "client_id": self._otib_client_id,
            "redirect_uri": _TIBBER_REDIRECT_URI,
            "scope": TIBBER_SCOPES,
            "state": self._otib_state,
            "code_challenge": _tibber_pkce_challenge(self._otib_verifier),
            "code_challenge_method": "S256",
        }
        return f"{TIBBER_AUTHORIZE_URL}?{urlencode(params)}"

    def _otib_extract_code(self, raw: str) -> str:
        """Pull the auth code out of a pasted redirect URL (or accept a bare
        code), verifying the CSRF state when present. Raises ValueError on a
        missing code or a state mismatch."""
        if not raw:
            raise ValueError("invalid_credentials")
        code = raw
        if "code=" in raw or raw.lower().startswith("http"):
            from urllib.parse import parse_qs, urlparse  # noqa: PLC0415
            q = parse_qs(urlparse(raw).query)
            code = (q.get("code") or [""])[0].strip()
            st = (q.get("state") or [""])[0].strip()
            if self._otib_state and st and st != self._otib_state:
                raise ValueError("invalid_credentials")
        if not code:
            raise ValueError("invalid_credentials")
        return code

    async def _otib_exchange_code(self, code: str) -> dict[str, str]:
        """Exchange the auth code for the OAuth2 token bundle (PKCE). Raises
        ValueError(code) on failure so _map_error renders a localised message.
        The tokens are never logged."""
        import aiohttp  # noqa: PLC0415

        from .cariad._tibber_source import TIBBER_TOKEN_URL  # noqa: PLC0415
        session = aiohttp.ClientSession()
        try:
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _TIBBER_REDIRECT_URI,
                "client_id": self._otib_client_id,
                "client_secret": self._otib_client_secret,
                "code_verifier": self._otib_verifier,
            }
            async with session.post(
                TIBBER_TOKEN_URL, data=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 429:
                    raise ValueError("too_many_requests")
                body = await resp.json(content_type=None)
                if resp.status != 200:
                    raise ValueError("invalid_credentials")
        except ValueError:
            raise
        except Exception as err:  # noqa: BLE001
            raise ValueError("cannot_connect") from err
        finally:
            try:
                await session.close()
            except Exception:  # noqa: BLE001
                pass
        at = body.get("access_token") if isinstance(body, dict) else None
        rt = body.get("refresh_token") if isinstance(body, dict) else None
        if not at:
            raise ValueError("invalid_credentials")
        return {
            "access_token": str(at),
            "refresh_token": str(rt or ""),
            "client_id": self._otib_client_id,
            "client_secret": self._otib_client_secret,
        }

    # ── b1/C1: supplementary vw.de read-channel sub-flow ────────────────────

    async def async_step_add_vwde(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect vw.de credentials + drive the read-only login. Volkswagen
        only; on success stores the session cookies as a supplementary channel
        and reloads so the coordinator merges it onto the primary."""
        errors: dict[str, str] = {}
        if self._config_entry.data.get(CONF_BRAND) != "volkswagen":
            return self.async_abort(reason="not_volkswagen")

        if user_input is not None:
            self._ovw_username = user_input[CONF_USERNAME]
            try:
                needs_otp = await self._ovw_begin_login(
                    self._ovw_username, user_input[CONF_PASSWORD],
                )
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                if needs_otp:
                    return await self.async_step_add_vwde_otp()
                return await self._ovw_finish()

        return self.async_show_form(
            step_id="add_vwde",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): _USERNAME_SELECTOR,
                vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
            }),
            errors=errors,
        )

    async def async_step_add_vwde_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Email-OTP step for the supplementary vw.de channel login."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                ok = await self._ovw_submit_otp(str(user_input.get("mfa_code", "")).strip())
            except ValueError as err:
                errors["base"] = _map_error(str(err))
            else:
                if ok:
                    return await self._ovw_finish()
                errors["base"] = "invalid_credentials"

        return self.async_show_form(
            step_id="add_vwde_otp",
            data_schema=vol.Schema({vol.Required("mfa_code"): _MFA_SELECTOR}),
            description_placeholders={"username": self._ovw_username},
            errors=errors,
        )

    async def _ovw_finish(self) -> config_entries.ConfigFlowResult:
        """Persist the supplementary cookies onto the entry + reload so the
        coordinator arms the merged channel. Saves any pending options too."""
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
        return self.async_create_entry(title="", data=self._ovw_pending_options)

    # ── VW EU Two-Way (650d46ca) opt-in sub-flow ────────────────────────────

    async def async_step_add_vweu_twoway(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect VW ID credentials and mint a VW EU Two-Way (650d46ca) token via
        a headless device-grant login (Volkswagen only). The 1h token is
        non-refreshable, so the login password is stored to re-mint it unattended:
        an explicit opt-in feature, the password is only ever sent to VW's own
        identity server and is masked in diagnostics. Persists the token + creds
        and reloads so the coordinator activates the two-way channel."""
        from .const import (  # noqa: PLC0415
            CONF_VWEU_DEVICE_GRANT,
            CONF_VWEU_TWOWAY_EMAIL,
            CONF_VWEU_TWOWAY_PASSWORD,
            CONF_VWEU_TWOWAY_TOKENS,
        )

        errors: dict[str, str] = {}
        if self._config_entry.data.get(CONF_BRAND) != "volkswagen":
            return self.async_abort(reason="not_volkswagen")
        # Kill-switch guard (2026-08-18): VW disabled the 650d46ca device_code
        # grant, so a mint here is guaranteed to 403. While disabled the
        # add-toggle is hidden so this step is unreachable from the UI — this is
        # defence-in-depth for a stale in-flight flow. Flipping
        # VWEU_TWOWAY_DISABLED to False re-enables the whole path unchanged.
        from .cariad.auth._device_grant import (  # noqa: PLC0415
            VWEU_TWOWAY_DISABLED,
        )
        if VWEU_TWOWAY_DISABLED:
            return self.async_abort(reason="vweu_twoway_vw_disabled")

        if user_input is not None:
            email = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            import aiohttp  # noqa: PLC0415

            from .cariad.auth._vweu_twoway_login import (  # noqa: PLC0415
                VwEuTwoWayLogin,
            )
            from .cariad.exceptions import AuthenticationError  # noqa: PLC0415

            tokens = None
            serves = False
            try:
                async with aiohttp.ClientSession() as session:
                    tokens = await VwEuTwoWayLogin(session).login(email, password)
                    # Verify the car actually SERVES data on the modern CARIAD BFF
                    # before committing — the login can succeed while the car's
                    # live data still 4103s (not yet provisioned on the modern
                    # plane). Activating then would swap a working primary for an
                    # empty one. Per-car, empirical: no assumption about MQB vs MEB.
                    serves = await self._vweu_bff_serves_data(
                        session, tokens.access_token
                    )
            except AuthenticationError as err:
                msg = str(err)
                errors["base"] = (
                    "vweu_mfa_unsupported" if msg.startswith("MFA_UNSUPPORTED")
                    else "invalid_auth"
                )
            except Exception:  # noqa: BLE001 — surface any transport hiccup as a retry
                errors["base"] = "cannot_connect"
            if tokens is not None and not errors:
                if not serves:
                    # Login worked but the BFF returns no live data for this car
                    # yet. Keep the current channel untouched and tell the user.
                    errors["base"] = "vweu_no_bff_data"
                else:
                    _new_data = {
                        **self._config_entry.data,
                        CONF_VWEU_DEVICE_GRANT: True,
                        CONF_VWEU_TWOWAY_TOKENS: {
                            "access_token": tokens.access_token,
                            "refresh_token": tokens.refresh_token,
                            "id_token": tokens.id_token,
                            "expires_at": tokens.expires_at,
                            "strategy": "device_grant",
                        },
                        CONF_VWEU_TWOWAY_EMAIL: email,
                        CONF_VWEU_TWOWAY_PASSWORD: password,
                    }
                    # v4.0.0 — if this entry's PRIMARY read was the EU Data Act
                    # portal, activating two-way makes device_grant the primary
                    # and would otherwise silently DROP EU-DA (authenticate() is
                    # skipped for device_grant, so _eu_portal is never armed).
                    # Carry EU-DA over as a read-only SUPPLEMENTARY gap-filler
                    # (same Volkswagen ID the user just authenticated), so it
                    # keeps filling fields the BFF doesn't provide and the
                    # hard-failure revive can fall back to it when two-way drops.
                    # Only when EU-DA was primary and no supplementary portal is
                    # already configured (never override the user's own choice).
                    _strategy = (
                        self._config_entry.data.get("dag_initial_tokens") or {}
                    ).get("strategy")
                    if (
                        _strategy in ("data_act_portal", "device_grant_portal")
                        and not self._config_entry.data.get(
                            CONF_SUPPLEMENTARY_EU_PORTAL
                        )
                    ):
                        _new_data[CONF_SUPPLEMENTARY_EU_PORTAL] = True
                        _new_data[CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME] = email
                        _new_data[CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD] = password
                        # marker so removing two-way later also removes THIS
                        # auto-carried supplementary (not a user's own).
                        _new_data[CONF_VWEU_TWOWAY_ADDED_EU_PORTAL] = True
                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=_new_data,
                    )
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self._config_entry.entry_id
                        )
                    )
                    return self.async_create_entry(
                        title="", data=self._vweu_pending_options
                    )

        return self.async_show_form(
            step_id="add_vweu_twoway",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): _USERNAME_SELECTOR,
                vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
            }),
            errors=errors,
        )

    async def _vweu_bff_serves_data(self, session: Any, access_token: str) -> bool:
        """True if the CARIAD BFF returns real live data (not an all-error 4103)
        for the first vehicle on this token — i.e. the car is actually usable on
        the modern plane. Per-car empirical check; makes NO assumption about MQB
        vs MEB (a properly-provisioned MQB serves data here and passes)."""
        import aiohttp  # noqa: PLC0415

        base = "https://emea.bff.cariad.digital"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Volkswagen/3.61.0-android/14",
            "Accept": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with session.get(
                f"{base}/vehicle/v2/vehicles", headers=headers, timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    return False
                garage = await resp.json(content_type=None)
            rows = garage.get("data") if isinstance(garage, dict) else None
            vin = next(
                (r.get("vin") for r in (rows or [])
                 if isinstance(r, dict) and r.get("vin")),
                None,
            )
            if not vin:
                return False
            async with session.get(
                f"{base}/vehicle/v1/vehicles/{vin}/selectivestatus",
                params={"jobs": "access,charging,fuelStatus,measurements"},
                headers=headers, timeout=timeout,
            ) as resp2:
                if resp2.status not in (200, 207):
                    return False
                status = await resp2.json(content_type=None)
        except Exception:  # noqa: BLE001
            return False
        from .cariad.auth._vweu_twoway_login import (  # noqa: PLC0415
            bff_selectivestatus_has_data,
        )

        return bff_selectivestatus_has_data(status)

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
        except AuthenticationError as err:
            await self._ovw_close_session()
            # v2.24.1 (#957) — this is the options-flow twin of the setup-time
            # login at line ~637, and it was the only one of the two that stayed
            # silent. Every one of the upstream raise sites landed here as a bare
            # "invalid_credentials", so a redirect loop, an expired SSO session or
            # a portal outage all told the user their password was wrong and left
            # nothing in the log to tell them apart.
            _LOGGER.warning("Website authproxy login failed: %s", err)
            raise ValueError("invalid_credentials") from err
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
