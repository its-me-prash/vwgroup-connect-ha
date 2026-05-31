# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
"""v2.8.0 - EU Data Act portal vehicle-data scraper (Action #3).

This module is the in-house automated download layer that sits on top
of ``_data_act_portal.py``. ``_data_act_portal.py`` performs the OAuth
login against the portal at ``eu-data-act.drivesomethinggreater.com``
and yields a session cookie / TokenSet. This module then uses that
authenticated session to fetch the actual vehicle-data payload that
end users would otherwise download manually by clicking the "Get
customised data" button in the portal's web UI.

## Two-route design

Live testing of the portal requires real VW EU credentials, which the
project does not have in the v2.8.0 staging cycle. The module ships
both candidate routes as scaffolding so a credentialed tester can
exercise them and the implementation can be tightened in v2.8.1:

Route A - JSON API behind the portal session
    The portal exposes a metadata endpoint at
    ``/proxy_api/vum/v2/users/me/relations/{vin}`` (verified from
    public sources, see ``_private/research-archive/old-docs/
    RESEARCH_NOTES_2026-04-29.md``). Whether the customised-data
    payload itself is served by a sibling JSON endpoint behind the
    same session cookie is not knowable from static analysis alone -
    the click-through flow on the portal must be observed under a
    live login. ``_attempt_api_fetch`` therefore probes the relations
    endpoint plus a small list of conservatively named candidate
    paths (see ``_API_DATA_CANDIDATE_PATHS``). It returns ``None`` on
    any HTTP non-2xx or non-zip content type so the coordinator can
    fall back to Route B.

Route B - Headless browser
    When Route A returns nothing, ``_attempt_browser_fetch`` drives a
    headless Chromium via ``playwright`` to perform the same UI click
    a human would. Playwright is an OPTIONAL dependency: it is NOT
    listed in ``manifest.json`` (that would force every HA user to
    install around 100 MB of Chromium just to set up the integration).
    Instead it is lazy-imported only when the user explicitly enables
    the ``CONF_ENABLE_DATA_ACT_BROWSER`` OptionsFlow toggle. If the
    toggle is enabled but the package is missing, the integration
    surfaces a clear repair issue telling the user to ``pip install
    playwright`` from inside their HA container.

## Polling cadence and wake-state requirement

The portal publishes new dataset drops roughly every 15 minutes per
VIN (server-side limit, also documented in ``_data_act_portal.py``).
A new dataset is only published when the vehicle has had a wake
event since the last drop. Wake events include:
- An ignition cycle (driving)
- A charge session start or stop
- A remote lock or unlock cycle

If the user is on a car they have not touched in days, every poll
will return either an empty payload or a payload identical to the
last one. The scraper tracks consecutive-empty-poll streaks and the
coordinator surfaces a Repair issue after ``_EMPTY_STREAK_HINT_AT``
polls in a row pointing the user at the wake-state requirement.

## Why this is a separate file

``_data_act_portal.py`` is the LOGIN strategy and is wired into the
auth resolver chain in ``cariad/api/base.py``. It has a narrow
public interface (``DataActPortalAuth.login`` returning a TokenSet)
and is tested as an auth strategy. The data fetch is a separate
concern with a different cadence, a different failure surface, and a
different optional-dependency profile. Splitting them means the
existing auth tests keep working untouched and the new fetch tests
have their own well-scoped fixtures.
"""

from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiohttp import ClientSession

from ..models import VehicleData

_LOGGER = logging.getLogger(__name__)


# Portal base URL - kept identical to the login module so a future
# rename only has to change one of these. The login module is the
# canonical source for the host string; we duplicate it here rather
# than import to keep the modules decoupled (the scraper is usable
# in tests without spinning up the auth strategy).
_PORTAL_BASE = "https://eu-data-act.drivesomethinggreater.com"

# Route A candidate endpoints. The first entry is the only path that
# has been verified from public sources and known community Python
# code: it returns vehicle metadata for the supplied VIN under the
# portal session cookie. The remaining entries are conservative guesses
# patterned after common ASP.NET, Spring Boot, and Auth0 SPA backends
# that the rest of the portal infrastructure appears to be built on.
# None of these are known to return a zip - they exist so that a
# credentialed tester running the integration once will surface the
# real shape in the integration log via the response-content-type
# trace below. v2.8.1 will tighten this list based on what survives.
_API_DATA_CANDIDATE_PATHS: tuple[str, ...] = (
    "/proxy_api/vum/v2/users/me/relations/{vin}",
    "/proxy_api/vum/v2/users/me/vehicles/{vin}/customised-data",
    "/proxy_api/vum/v2/users/me/vehicles/{vin}/data-export",
    "/api/v1/customised-data/{vin}",
    "/api/v1/vehicles/{vin}/export",
)

# Acceptable Content-Type prefixes for a real customised-data response.
# We accept zip (the documented manual download) plus json (in case
# the portal returns a wrapper that contains a download URL we then
# follow as a second request - handled inside ``_attempt_api_fetch``).
_ZIP_CONTENT_TYPES: tuple[str, ...] = (
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
)
_JSON_CONTENT_TYPES: tuple[str, ...] = (
    "application/json",
    "application/vnd.api+json",
)

# Maximum acceptable zip size in bytes. Portal exports are documented
# at low hundreds of kilobytes per VIN; anything larger is almost
# certainly the wrong response (HTML error page, hostile redirect,
# etc.) and we refuse to load it into memory.
_MAX_ZIP_BYTES = 50 * 1024 * 1024

# Request timeouts. Generous because the portal is known to be slow
# when preparing a new export on the server side.
_API_REQUEST_TIMEOUT_S = 60
_BROWSER_NAV_TIMEOUT_S = 90

# Repair-issue thresholds. The integration surfaces a wake-state hint
# when this many consecutive polls return either no zip at all or a
# zip whose contents are byte-identical to the previous poll. Empirical
# choice: at 15-minute cadence, 4 polls is one hour - long enough to
# rule out short transient backend hiccups, short enough that a user
# who genuinely has not touched the car for a day will get the hint
# within the first 25 % of that day.
_EMPTY_STREAK_HINT_AT = 4


class DataActScraperError(Exception):
    """Raised by ``DataActScraper`` when a fetch fails in an explicit way.

    Distinct from generic ``Exception`` so callers (the coordinator)
    can decide whether to log loudly or quietly. Transient errors
    (HTTP 5xx, timeouts) are NOT raised - they return ``None`` from
    ``fetch_vehicle_zip`` so the next poll can retry without entity
    flicker. Only structural failures (auth missing, browser toggle
    enabled but ``playwright`` not installed, etc.) raise.
    """


class DataActScraper:
    """Automated vehicle-data downloader sitting on a portal session.

    Usage:

        portal = DataActPortalAuth(session, brand)
        await portal.login(email, password)
        scraper = DataActScraper(session, brand_name=brand)
        zip_bytes = await scraper.fetch_vehicle_zip(vin)
        if zip_bytes is not None:
            parsed = scraper.parse_zip(zip_bytes)
            vehicle = scraper.to_vehicle_data(vin, parsed)

    The class is stateful only in the empty-streak counter - the
    session cookies live on the ``ClientSession`` instance passed by
    the caller, so the scraper can be re-created cheaply per poll if
    needed.
    """

    def __init__(
        self,
        session: "ClientSession",
        *,
        brand_name: str,
        enable_browser_fallback: bool = False,
    ) -> None:
        """Set up a scraper.

        Args:
            session: Authenticated ``aiohttp.ClientSession`` that has
                already been driven through the portal login flow in
                ``_data_act_portal.py``. The portal cookie is expected
                to be set on this session.
            brand_name: Lower-case brand name used purely for logging
                and Repair-issue messages. Has no effect on the wire
                format.
            enable_browser_fallback: If True, ``fetch_vehicle_zip``
                will fall back to a headless browser when the JSON
                API returns no zip. Driven by the OptionsFlow toggle
                ``CONF_ENABLE_DATA_ACT_BROWSER``. Off by default
                because the playwright dependency is heavy.
        """
        self._session = session
        self._brand_name = brand_name
        self._enable_browser_fallback = enable_browser_fallback
        self._empty_streak: int = 0
        # Hash of the last successfully fetched zip, used to detect
        # "the portal handed us the exact same data as last time"
        # which is also a wake-state-stale signal. None means we have
        # never had a successful fetch on this scraper instance.
        self._last_zip_digest: int | None = None

    @property
    def empty_streak(self) -> int:
        """Consecutive polls that returned no fresh data.

        Public so the coordinator can decide whether to raise a
        Repair issue. Resets to 0 on any successful fetch with a
        digest different from ``_last_zip_digest``.
        """
        return self._empty_streak

    @property
    def needs_wake_hint(self) -> bool:
        """True when the user should be reminded to wake the vehicle.

        Reads the empty-streak counter against ``_EMPTY_STREAK_HINT_AT``.
        The coordinator surfaces an HA Repair issue when this flips to
        True and clears it on the next successful fetch.
        """
        return self._empty_streak >= _EMPTY_STREAK_HINT_AT

    async def fetch_vehicle_zip(self, vin: str) -> bytes | None:
        """Return the customised-data zip bytes for ``vin``, or None.

        Tries Route A first. If Route A returns nothing AND the
        browser fallback is enabled, tries Route B. Any structural
        error (no session, browser enabled but missing dep) raises
        ``DataActScraperError``; transient failures return ``None``.

        Side effect: maintains the empty-streak counter so the
        coordinator can surface the wake-state hint when the streak
        crosses ``_EMPTY_STREAK_HINT_AT``.
        """
        masked_vin = _mask_vin(vin)
        _LOGGER.debug(
            "Data Act scraper: fetch attempt for brand=%s vin=%s",
            self._brand_name, masked_vin,
        )

        zip_bytes: bytes | None = None
        try:
            zip_bytes = await self._attempt_api_fetch(vin)
        except DataActScraperError:
            # Propagate structural errors so the coordinator can
            # show the user a repair issue.
            raise
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "Data Act scraper: Route A raised %s for vin=%s, "
                "moving on to Route B if enabled",
                type(exc).__name__, masked_vin,
            )

        if zip_bytes is None and self._enable_browser_fallback:
            try:
                zip_bytes = await self._attempt_browser_fetch(vin)
            except DataActScraperError:
                raise
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Data Act scraper: Route B raised %s for vin=%s",
                    type(exc).__name__, masked_vin,
                )

        # Update empty-streak counter and digest tracking.
        if zip_bytes is None:
            self._empty_streak += 1
            return None

        digest = hash(zip_bytes)
        if digest == self._last_zip_digest:
            # Identical payload as last poll. Treat as "no new data"
            # for streak purposes but still return the bytes so the
            # coordinator can decide whether to re-parse.
            self._empty_streak += 1
        else:
            self._empty_streak = 0
            self._last_zip_digest = digest
        return zip_bytes

    async def _attempt_api_fetch(self, vin: str) -> bytes | None:
        """Route A: probe candidate JSON / zip endpoints on the portal.

        Implementation note: the only candidate path we have ANY
        external evidence for is the leading one in
        ``_API_DATA_CANDIDATE_PATHS``, and that path is documented as
        returning a metadata JSON, not the customised-data zip itself.
        Live-credential testing (TODO v2.8.1, requires real VW EU
        account) is what will tell us:
          1. whether one of the candidate paths returns the zip
             directly under the session cookie, or
          2. whether the metadata response carries a signed download
             URL we then follow.

        Until then, this method conservatively probes the candidates
        and logs the response content type so a credentialed tester
        can see which path is correct. It returns None on every path
        that does not produce a recognisable zip.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        for raw_path in _API_DATA_CANDIDATE_PATHS:
            path = raw_path.format(vin=vin)
            url = f"{_PORTAL_BASE}{path}"
            try:
                async with self._session.get(
                    url,
                    timeout=ClientTimeout(total=_API_REQUEST_TIMEOUT_S),
                    headers={"Accept": "application/json, application/zip"},
                ) as resp:
                    ct = resp.headers.get("Content-Type", "").lower()
                    if resp.status != 200:
                        _LOGGER.debug(
                            "Data Act scraper: %s returned HTTP %d "
                            "(content-type=%s)",
                            raw_path, resp.status, ct,
                        )
                        continue

                    # If the response is a zip, return it directly.
                    if any(ct.startswith(p) for p in _ZIP_CONTENT_TYPES):
                        body = await resp.read()
                        if len(body) > _MAX_ZIP_BYTES:
                            _LOGGER.warning(
                                "Data Act scraper: %s returned %d bytes, "
                                "exceeds %d byte safety cap, skipping",
                                raw_path, len(body), _MAX_ZIP_BYTES,
                            )
                            continue
                        if _looks_like_zip(body):
                            _LOGGER.info(
                                "Data Act scraper: Route A succeeded "
                                "via %s (%d bytes)", raw_path, len(body),
                            )
                            return body
                        _LOGGER.debug(
                            "Data Act scraper: %s declared zip content-type "
                            "but bytes are not a zip signature, skipping",
                            raw_path,
                        )
                        continue

                    # If the response is JSON, look for a download URL
                    # field. Common shapes across ASP.NET / Spring Boot:
                    # ``downloadUrl``, ``download_url``, ``url``,
                    # ``href``, plus nested under ``data``.
                    if any(ct.startswith(p) for p in _JSON_CONTENT_TYPES):
                        try:
                            payload = await resp.json(content_type=None)
                        except Exception:  # noqa: BLE001
                            continue
                        download_url = _extract_download_url(payload)
                        if download_url:
                            zip_bytes = await self._download_zip_from_url(
                                download_url,
                            )
                            if zip_bytes is not None:
                                _LOGGER.info(
                                    "Data Act scraper: Route A succeeded "
                                    "via %s -> signed download URL "
                                    "(%d bytes)", raw_path, len(zip_bytes),
                                )
                                return zip_bytes
                        else:
                            _LOGGER.debug(
                                "Data Act scraper: %s returned JSON but "
                                "no recognisable download URL field",
                                raw_path,
                            )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Data Act scraper: %s raised %s",
                    raw_path, type(exc).__name__,
                )
                continue

        # TODO v2.8.1 - live route A discovery requires real
        # credentials, see _private/research-archive/old-docs/
        # RESEARCH_NOTES_2026-04-29.md section 9 for the only
        # confirmed endpoint shape we have so far.
        return None

    async def _download_zip_from_url(self, url: str) -> bytes | None:
        """Fetch a signed-URL zip discovered in a Route A JSON response."""
        from aiohttp import ClientTimeout  # noqa: PLC0415

        try:
            async with self._session.get(
                url,
                timeout=ClientTimeout(total=_API_REQUEST_TIMEOUT_S),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return None
                body = await resp.read()
                if len(body) > _MAX_ZIP_BYTES:
                    return None
                if _looks_like_zip(body):
                    return body
        except Exception:  # noqa: BLE001
            return None
        return None

    async def _attempt_browser_fetch(self, vin: str) -> bytes | None:
        """Route B: drive a headless browser to click the export button.

        Lazy-imports ``playwright``. Raises ``DataActScraperError``
        with a user-friendly message when the package is missing so
        the OptionsFlow toggle has a clear feedback path.

        The implementation is intentionally scaffolded rather than
        fully wired: actually clicking through the portal UI requires
        observing the live DOM under a real session and the project
        does not have credentials to record a stable selector path in
        the v2.8.0 cycle. Once a credentialed tester captures the DOM
        snapshot, v2.8.1 fills in the selectors below the TODO marker.
        """
        try:
            import playwright.async_api as pw  # noqa: PLC0415
        except ImportError as exc:
            raise DataActScraperError(
                "Data Act browser fallback is enabled but the "
                "'playwright' Python package is not installed. From "
                "inside your Home Assistant container run: "
                "'pip install playwright' and 'playwright install "
                "chromium'. Note: the chromium download is large "
                "(around 100 MB), so this is intentionally opt-in."
            ) from exc

        masked_vin = _mask_vin(vin)
        _LOGGER.debug(
            "Data Act scraper: Route B (browser) starting for vin=%s",
            masked_vin,
        )

        # The session cookies live on the aiohttp session; we have to
        # transfer them onto the playwright browser context so the
        # portal recognises the same authenticated user.
        cookies = _cookies_for_playwright(self._session)

        async with pw.async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context()
                if cookies:
                    await ctx.add_cookies(cookies)
                page = await ctx.new_page()
                await page.goto(
                    f"{_PORTAL_BASE}/",
                    timeout=_BROWSER_NAV_TIMEOUT_S * 1000,
                    wait_until="domcontentloaded",
                )

                # TODO v2.8.1 - real selectors require a recorded DOM
                # snapshot from a credentialed tester. Until then the
                # method bails out cleanly and the coordinator falls
                # back to "no data this cycle". Suggested selector
                # families to try based on common Angular / React SPA
                # patterns observed in the portal's tech stack:
                #   button:has-text("Get customised data")
                #   button:has-text("Eigene Daten herunterladen")
                #   [data-testid='get-customised-data']
                #   a.download-export
                # A real tester should capture page.content() under a
                # live login, paste it into the scaffold below, and
                # iterate.
                _LOGGER.info(
                    "Data Act scraper: Route B scaffolded but selectors "
                    "not yet wired - awaiting v2.8.1 tester capture. "
                    "Returning None for vin=%s.", masked_vin,
                )
                return None
            finally:
                await browser.close()

    def parse_zip(self, zip_bytes: bytes) -> dict[str, Any]:
        """Extract JSON entries from a customised-data zip.

        The portal export is a zip containing one or more JSON files.
        File names are not stable across firmwares (community-observed
        names include ``vehicleStatus.json``, ``status.json``,
        ``measurements.json``, ``charging.json``) so the parser is
        defensive: it loads every ``*.json`` member into a dict keyed
        by member name (without the ``.json`` suffix) and lets
        ``to_vehicle_data`` walk that combined structure.

        Non-JSON members (PDFs, CSVs, images that some firmwares
        include) are ignored - the integration only consumes JSON
        today.

        Returns an empty dict if the zip has no JSON members or is
        unreadable. Never raises - the caller (the coordinator) needs
        a stable contract.
        """
        out: dict[str, Any] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if not name.lower().endswith(".json"):
                        continue
                    try:
                        raw = zf.read(name)
                        member = json.loads(raw.decode("utf-8", errors="replace"))
                    except (json.JSONDecodeError, KeyError) as exc:
                        _LOGGER.debug(
                            "Data Act scraper: parse_zip skipped %s (%s)",
                            name, type(exc).__name__,
                        )
                        continue
                    key = name.rsplit("/", 1)[-1].removesuffix(".json")
                    out[key] = member
        except zipfile.BadZipFile:
            _LOGGER.warning(
                "Data Act scraper: parse_zip received bytes that are "
                "not a valid zip archive (%d bytes)", len(zip_bytes),
            )
            return {}
        return out

    def to_vehicle_data(
        self,
        vin: str,
        parsed: dict[str, Any],
    ) -> VehicleData:
        """Map a parsed zip dict into a ``VehicleData`` record.

        The mapping is defensive and tolerates missing or extra keys:
        every field is set only when a recognisable source value is
        present in ``parsed``. Unrecognised keys are left as defaults
        so a firmware that ships a new field name does not crash the
        whole poll.

        The shape we expect to see in ``parsed`` after ``parse_zip``
        is a dict-of-dicts: top-level keys are zip member basenames
        (e.g. ``status``, ``measurements``, ``charging``) and the
        values are the JSON body of that member.

        Core fields populated when available:
          - ``battery_soc``       <- charging.currentSOC_pct
          - ``range_km``          <- measurements.rangeStatus.totalRange_km
          - ``odometer_km``       <- measurements.odometerStatus.odometer
          - ``last_seen_at``      <- status.carCapturedTimestamp

        Additional fields are mapped when present; absence is fine.
        """
        out = VehicleData(vin=vin)

        # Charging block.
        charging = _safe_dict(parsed.get("charging"))
        if charging:
            soc = _first_int(
                charging.get("currentSOC_pct"),
                _nested(charging, "batteryStatus", "value", "currentSOC_pct"),
            )
            if soc is not None:
                out.battery_soc = soc
            target = _first_int(
                charging.get("targetSOC_pct"),
                _nested(charging, "chargingSettings", "value", "targetSOC_pct"),
            )
            if target is not None:
                out.target_soc = target
            state = _first_str(
                charging.get("chargingState"),
                _nested(charging, "chargingStatus", "value", "chargingState"),
            )
            if state is not None:
                out.charging_state = state

        # Measurements block - odometer, range, fuel.
        measurements = _safe_dict(parsed.get("measurements"))
        if measurements:
            odo = _first_int(
                _nested(measurements, "odometerStatus", "odometer"),
                _nested(measurements, "odometerStatus", "value", "odometer"),
                measurements.get("odometer"),
            )
            if odo is not None:
                out.odometer_km = odo
            rng = _first_int(
                _nested(measurements, "rangeStatus", "totalRange_km"),
                _nested(measurements, "rangeStatus", "value", "totalRange_km"),
            )
            if rng is not None:
                out.range_km = rng
            fuel = _first_int(
                _nested(measurements, "fuelLevelStatus", "currentFuelLevel_pct"),
                _nested(
                    measurements, "fuelLevelStatus", "value",
                    "currentFuelLevel_pct",
                ),
            )
            if fuel is not None:
                out.fuel_level = fuel

        # Status block - timestamps + lock + warnings. The portal
        # also serves an aggregated ``status.json`` member on most
        # firmwares; we read the wake / capture timestamp from it.
        status = _safe_dict(parsed.get("status"))
        if status:
            captured = _first_str(
                status.get("carCapturedTimestamp"),
                _nested(status, "value", "carCapturedTimestamp"),
            )
            if captured is not None:
                out.last_seen_at = captured
            locked = _first_bool(
                _nested(status, "access", "doorsLocked"),
                _nested(status, "value", "access", "doorsLocked"),
            )
            if locked is not None:
                out.doors_locked = locked

        # Top-level convenience fields seen on some firmwares.
        # The zip archive ships these in a top-level "top.json" member,
        # which parse_zip turns into ``parsed["top"]``; older / smaller
        # exports inline them at the parsed root. Try both.
        for source_dict in (parsed.get("top"), parsed):
            if not isinstance(source_dict, dict):
                continue
            if out.license_plate is None:
                plate = _first_str(source_dict.get("licensePlate"))
                if plate is not None:
                    out.license_plate = plate
            if out.model is None:
                model = _first_str(source_dict.get("model"))
                if model is not None:
                    out.model = model

        # Record the time we successfully parsed the export so the
        # coordinator can render "last poll" UI even when none of the
        # source fields above carried a timestamp.
        out.last_updated_at = time.time()
        return out


# ── helpers ──────────────────────────────────────────────────────────────────


def _looks_like_zip(body: bytes) -> bool:
    """Cheap zip-magic check before we hand bytes to ``zipfile``."""
    return len(body) >= 4 and body[:4] in (b"PK\x03\x04", b"PK\x05\x06")


def _mask_vin(vin: str) -> str:
    """Return a masked VIN suffix safe to put in logs."""
    if not vin:
        return "?"
    return f"...{vin[-6:]}" if len(vin) > 6 else vin


def _extract_download_url(payload: Any) -> str | None:
    """Walk a JSON payload and return the first plausible download URL.

    Looks for common field names (``downloadUrl``, ``download_url``,
    ``url``, ``href``, ``link``) at the top level and one level deep
    under ``data``. Returns the first URL that begins with ``https://``;
    anything else is treated as suspicious and skipped.
    """
    if not isinstance(payload, dict):
        return None
    candidates = ("downloadUrl", "download_url", "url", "href", "link")
    for key in candidates:
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("https://"):
            return val
    data = payload.get("data")
    if isinstance(data, dict):
        for key in candidates:
            val = data.get(key)
            if isinstance(val, str) and val.startswith("https://"):
                return val
    return None


def _cookies_for_playwright(session: Any) -> list[dict[str, Any]]:
    """Translate an aiohttp cookie jar to a playwright cookie list.

    Playwright wants a list of dicts shaped like
    ``{"name", "value", "domain", "path"}``. We export only cookies
    bound to the portal host so we never accidentally leak unrelated
    cookies into the browser context.
    """
    out: list[dict[str, Any]] = []
    jar = getattr(session, "cookie_jar", None)
    if jar is None:
        return out
    portal_host = _PORTAL_BASE.split("://", 1)[1]
    for cookie in jar:
        try:
            domain = cookie.get("domain", "") or ""
        except Exception:  # noqa: BLE001
            continue
        if domain and domain.lstrip(".") not in portal_host:
            continue
        try:
            out.append({
                "name": cookie.key,
                "value": cookie.value,
                "domain": domain.lstrip(".") or portal_host,
                "path": cookie.get("path", "/") or "/",
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def _safe_dict(val: Any) -> dict[str, Any]:
    """Return ``val`` if it is a dict, else an empty dict."""
    return val if isinstance(val, dict) else {}


def _nested(source: Any, *path: str) -> Any:
    """Walk a nested dict by string keys, returning None on miss."""
    node: Any = source
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
        if node is None:
            return None
    return node


def _first_int(*candidates: Any) -> int | None:
    """Return the first candidate that converts cleanly to int."""
    for c in candidates:
        if isinstance(c, bool):
            continue
        if isinstance(c, int):
            return c
        if isinstance(c, float):
            return int(c)
    return None


def _first_str(*candidates: Any) -> str | None:
    """Return the first candidate that is a non-empty str."""
    for c in candidates:
        if isinstance(c, str) and c:
            return c
    return None


def _first_bool(*candidates: Any) -> bool | None:
    """Return the first candidate that is a bool."""
    for c in candidates:
        if isinstance(c, bool):
            return c
    return None
