# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
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
    Instead it is lazy-imported only when ``enable_browser_fallback``
    is set on the scraper.

    v2.18.0 — nothing sets it today: the OptionsFlow toggle that was
    meant to drive it never had a reader and has been removed, and the
    only caller that forwarded the flag is itself unreachable. The
    fallback is therefore dormant rather than merely off.

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
import uuid
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

# v2.10.5 — verified live-trace endpoints captured 2026-06-03.
# Custom Data Request lives under /proxy_api/euda-apim/ on the portal
# host. The "Frequency=15mins" + "Duration=1 month" combo is the only
# one that yields 15-minute polling drops; other combinations return
# fewer or sparser dumps. See docs/EU_DATA_ACT_PORTAL.md for the
# full payload schema.
_EUDA_APIM = "/proxy_api/euda-apim"
# The EndDate that accompanies Duration="No Expiry". The portal keeps
# treating StartDate/EndDate as a window, so a one-month EndDate next to a
# no-expiry Duration would contradict itself; this pushes the window out far
# enough that it is never the thing that stops a feed.
_NO_EXPIRY_WINDOW_DAYS = 3650
_CUSTOM_REQUEST_POST_PATH = _EUDA_APIM + "/datarequest/vehicles/{vin}/requests/partial"
_CUSTOM_REQUEST_META_PATH = _EUDA_APIM + "/datarequest/vehicles/{vin}/metadata/partial"
_ALL_REQUEST_META_PATH = _EUDA_APIM + "/datarequest/vehicles/{vin}/metadata/all"
# v2.18.0 (Phase C) — the ONE-TIME / historical export. Proven from a real
# Audi trace 2026-07-17: clicking the portal's one-time-download button POSTs
# here (NOT to requests/partial), with a much simpler body — Frequency null,
# no Identifier, no Duration, DataClusters null. See kickoff_historical_export.
_ALL_REQUEST_POST_PATH = _EUDA_APIM + "/datarequest/vehicles/{vin}/requests/all"
_DATASET_LIST_PATH = (
    _EUDA_APIM + "/datadelivery/vehicles/{vin}/{identifier}/list"
)
_CSRF_TOKEN_PATH = "/libs/granite/csrf/token.json"
# The portal runs TWO independent auth layers on one host, which is the whole
# reason data-request creation can fail while reads work fine:
#   * ``/proxy_api/*``  → the APIM reverse proxy. Our portal login authenticates
#     HERE, and this is where every read goes.
#   * ``/libs/granite/*``, ``/services/*``, ``/content/*`` → the AEM publish
#     tier. The CSRF token lives here, and Adobe's own CSRF clientlib says the
#     endpoint returns a blank body "during non-authenticated requests".
# A session can therefore be perfectly valid for reads and anonymous for the
# token, which surfaces as HTTP 200 with an empty ``{}`` body. Probing the AEM
# leg tells the two apart; the page GET is the same request a browser makes when
# the user opens the portal, and is our best-effort attempt to revive that leg.
_AEM_PERMISSION_CHECK_PATH = "/services/permissioncheck"
_AEM_SESSION_PAGE_PATH = "/de/en/user.html"

# Canonical Data Clusters, spelled as the portal UI sends them. The SET matters
# (the six exact strings); the ORDER does NOT — a real portal-UI trace
# (2026-07-17) sent the same six in a different order (Warning Lights 4th, not
# 6th) and it was accepted. An earlier comment here claimed "ordering matters";
# that was wrong. Spelling is still exact.
_DEFAULT_DATA_CLUSTERS = (
    "All Data",
    "Charging",
    "Driving Behaviour",
    "Maintenance Related Information",
    "Parking Data",
    "Vehicle Warning Lights",
)


# DataActSessionExpiredError is defined right after DataActScraperError
# below; both subclass Exception.

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


def descriptor_expired(desc: dict[str, Any]) -> bool:
    """True only when a metadata/partial descriptor clearly reports it is
    past its window / no longer active. Unknown or unparseable -> False, so
    we never drop a possibly-valid request on a shape we don't recognise.

    The portal's window-end field is ``EndDate`` (a "No Expiry" request has
    none or a portal-assigned far-future one, a "One Month" one ~31 days out),
    so a past EndDate is the reliable "this feed has lapsed" signal; a MISSING
    EndDate is treated as not-lapsed. A few alternate key names plus an
    explicit status field are checked defensively.

    Module-level (not a method) so both the kickoff path
    (``DataActScraper.get_active_custom_request_identifier``) and the 15-min
    poll path (``EUDataActConnector.get_vehicle_data``) share ONE expiry rule
    and can never diverge (#957/#966).
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    status = str(
        desc.get("Status") or desc.get("State") or desc.get("RequestState") or ""
    ).upper()
    if status in (
        "EXPIRED", "INACTIVE", "COMPLETED", "CANCELLED", "CANCELED",
        "CLOSED", "FINISHED", "TERMINATED",
    ):
        return True
    now = datetime.now(tz=timezone.utc)
    for key in (
        "EndDate", "ExpiryDate", "ExpiresAt", "ValidUntil",
        "ExpirationDate", "ValidTo",
    ):
        raw = desc.get(key)
        if not isinstance(raw, str) or len(raw) < 10:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < now:
            return True
    return False


def pick_active_15min_identifier(payload: Any) -> str | None:
    """Return the Identifier of the first active (non-expired) 15-min Custom
    Request in a metadata/partial *payload*, or ``None``.

    Pure — no I/O. The portal returns the descriptors either as a bare list,
    a dict wrapping them under ``items`` / ``requests`` / ``data``, or a single
    descriptor dict; all three shapes are walked defensively. Only a descriptor
    whose ``Frequency`` is ``15mins`` with a plausible ``Identifier`` (>= 16
    chars) and that is not expired is adopted.

    Shared by the kickoff path and the poll path so a list-shaped payload can
    never again read as ``no_request`` on the poll while the kickoff walker
    sees the same list correctly (#957/#966).
    """
    candidates: list[dict[str, Any]] = []
    if isinstance(payload, list):
        candidates = [p for p in payload if isinstance(p, dict)]
    elif isinstance(payload, dict):
        for key in ("items", "requests", "data"):
            inner = payload.get(key)
            if isinstance(inner, list):
                candidates = [p for p in inner if isinstance(p, dict)]
                break
        if not candidates and payload.get("Identifier"):
            # Single-dict response variant.
            candidates = [payload]
    for c in candidates:
        if str(c.get("Frequency", "")).lower() != "15mins":
            continue
        identifier = c.get("Identifier")
        if not (isinstance(identifier, str) and len(identifier) >= 16):
            continue
        if descriptor_expired(c):
            continue
        return identifier
    return None


class DataActScraperError(Exception):
    """Raised by ``DataActScraper`` when a fetch fails in an explicit way.

    Distinct from generic ``Exception`` so callers (the coordinator)
    can decide whether to log loudly or quietly. Transient errors
    (HTTP 5xx, timeouts) are NOT raised - they return ``None`` from
    ``fetch_vehicle_zip`` so the next poll can retry without entity
    flicker. Only structural failures (auth missing, browser toggle
    enabled but ``playwright`` not installed, etc.) raise.
    """


class DataActSessionExpiredError(DataActScraperError):
    """v2.10.5 - raised when the portal returns 401 on an endpoint we
    depend on. The coordinator catches this and opens a Repairs issue
    prompting the user to reauthenticate; portal sessions are cookie-
    bound and not refreshable from the integration side.
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

    # v2.9.0 - provenance canary, see ``_canaries.py``. Class-level
    # attribute so any port of the Data Act scraper carries it.
    _PROVENANCE_DATA_ACT = "dataact_scraper_provenance_q9xrh4m2_2026"

    def __init__(
        self,
        session: "ClientSession",
        *,
        brand_name: str,
        enable_browser_fallback: bool = False,
        language: str = "de",
        country: str = "de",
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
                API returns no zip. Nothing sets it today (v2.18.0) —
                see the class docstring.
        """
        self._session = session
        self._brand_name = brand_name
        self._enable_browser_fallback = enable_browser_fallback
        self._language = language.lower()
        self._country = country.lower()
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
        Live-credential testing (TODO — requires a credentialed VW EU
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

        # TODO (credentialed tester) - live route A discovery requires real
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

                # TODO (credentialed tester) - real selectors require a recorded DOM
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

    # ── v2.10.2 Phase B: usership verification ───────────────────────────────

    # ── v2.10.5 Phase C: Custom Data Request (live-trace based) ──────────────

    def _portal_cookie_names(self) -> list[str]:
        """Cookie NAMES on the portal jar — never values.

        Which cookies we hold is the other half of the anonymous-at-AEM
        diagnosis (the AEM session rides its own cookie), and the names alone
        are safe to log. A value here would be a live session token.
        """
        try:
            return sorted({
                c.key for c in self._session.cookie_jar
                if "drivesomethinggreater" in (c["domain"] or "")
                or "vwgroup" in (c["domain"] or "")
            })[:12]
        except Exception:  # noqa: BLE001
            return []

    async def _fetch_csrf_token(self) -> str | None:
        """Return a fresh CSRF token, or None if the portal did not
        deliver one. CSRF expires per-session so callers re-fetch
        before every POST that needs it.

        v2.18.0 (#709) — every failure here used to return a bare None, and
        the caller logged "no CSRF token - aborting" with no reason. That made
        the whole kickoff undiagnosable: a reporter hands us a debug log and it
        says the token is missing, without saying whether the portal answered
        403 (session gone), 404 (the path moved), timed out, or simply started
        naming the token something else. No CSRF means no data request, which
        means no data at all — so this is the one failure we most need to be
        able to read, and it was the one that told us the least.

        Worth knowing: _CSRF_TOKEN_PATH is an Adobe AEM endpoint
        (/libs/granite/...). The portal is AEM-backed, so if VW ever moves off
        it or renames the field, this goes silent for every single user at once
        — and the log below is what would tell us which of those it was.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        url = _PORTAL_BASE + _CSRF_TOKEN_PATH
        token, anonymous_at_aem = await self._csrf_get(url)
        if token is not None:
            return token
        if not anonymous_at_aem:
            # Either a hard HTTP error, or authenticated at AEM and still no
            # token (the renamed-field / moved-endpoint case the docstring
            # warns about). Loading the page helps with neither, so stop here
            # and let the log above stand as the diagnosis.
            return None
        # Empty body + anonymous at AEM: the AEM leg of the session is missing
        # or lapsed while the proxy leg still works. Load the portal page once,
        # exactly as a browser does, then retry. Best-effort — if the AEM leg
        # cannot be revived from the cookies we hold, this simply fails again
        # and the log above has already recorded why.
        _LOGGER.debug(
            "CSRF token fetch: session is anonymous at the AEM layer — "
            "loading %s once to try to revive it", _AEM_SESSION_PAGE_PATH,
        )
        try:
            async with self._session.get(
                _PORTAL_BASE + _AEM_SESSION_PAGE_PATH,
                timeout=ClientTimeout(total=15),
                allow_redirects=True,
            ) as page:
                _LOGGER.debug(
                    "CSRF token fetch: portal page GET landed %s (HTTP %s)",
                    str(page.url).split("?")[0][:100], page.status,
                )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "CSRF token fetch: portal page GET raised %s: %s",
                type(exc).__name__, exc,
            )
            return None
        token, _ = await self._csrf_get(url)
        return token

    async def _csrf_get(self, url: str) -> tuple[str | None, bool]:
        """One CSRF fetch → ``(token, anonymous_at_aem)``.

        The second element is what makes an empty body diagnosable: the portal
        edge stamps ``x-sky-isauth`` on the response, so a ``200 {}`` with
        ``x-sky-isauth: 0`` means "anonymous at AEM", not "the field was
        renamed". Those two need completely different responses from us and the
        old code could not tell them apart. It is ``True`` ONLY for that
        anonymous-empty-body case, so a hard HTTP error never triggers a retry.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        try:
            async with self._session.get(
                url,
                timeout=ClientTimeout(total=10),
                headers={"Accept": "application/json"},
            ) as resp:
                # getattr: a response object without headers must not turn a
                # readable failure into an AttributeError traceback.
                is_auth_hdr = getattr(resp, "headers", {}).get("x-sky-isauth")
                if resp.status != 200:
                    _LOGGER.debug(
                        "CSRF token fetch: %s returned HTTP %s (portal session "
                        "expired, or the endpoint moved)",
                        _CSRF_TOKEN_PATH, resp.status,
                    )
                    return None, False
                data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "CSRF token fetch: %s raised %s: %s",
                _CSRF_TOKEN_PATH, type(exc).__name__, exc,
            )
            return None, False
        # ``token`` is the field the portal's own Granite clientlib reads.
        if isinstance(data, dict):
            token = data.get("token") or data.get("csrfToken")
            if isinstance(token, str) and token:
                return token, False
            anonymous = str(is_auth_hdr or "0").strip() == "0"
            _LOGGER.debug(
                "CSRF token fetch: HTTP 200 but no usable token. "
                "Keys present: %s | x-sky-isauth=%s (%s at the AEM layer) | "
                "portal cookies held: %s",
                sorted(data)[:12],
                is_auth_hdr if is_auth_hdr is not None else "absent",
                "ANONYMOUS" if anonymous else "authenticated",
                self._portal_cookie_names(),
            )
            return None, anonymous
        _LOGGER.debug(
            "CSRF token fetch: HTTP 200 but the body is %s, not an object",
            type(data).__name__,
        )
        return None, False

    async def get_active_custom_request_identifier(
        self, vin: str
    ) -> str | None:
        """Return the Identifier of the active 15-min Custom Request,
        or None if no active request exists yet.

        GET metadata/partial returns 200 with either an empty list or
        a list of request descriptors. We pick the first descriptor
        whose Frequency is "15mins" - that is the one we kick off
        from the integration. The portal enforces at most one active
        custom request per VIN, so this is unambiguous.

        Raises ``DataActSessionExpiredError`` on 401 so the coordinator
        can open a Repairs issue.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        url = _PORTAL_BASE + _CUSTOM_REQUEST_META_PATH.format(vin=vin)
        try:
            async with self._session.get(
                url,
                timeout=ClientTimeout(total=20),
                headers={
                    "Accept": "application/json",
                    # v2.17.x — the euda-apim layer now rejects requests without
                    # a traceId (the portal's newer API contract; verified live
                    # 2026-07-12 — the sibling relations endpoint 400s
                    # "Required request header 'traceId' not present" without it).
                    "traceId": uuid.uuid4().hex,
                },
            ) as resp:
                if resp.status == 401:
                    raise DataActSessionExpiredError(
                        "metadata/partial returned 401 - portal session expired"
                    )
                if resp.status != 200:
                    _LOGGER.debug(
                        "metadata/partial HTTP %s for VIN %s",
                        resp.status, _mask_vin(vin),
                    )
                    return None
                payload = await resp.json(content_type=None)
        except DataActSessionExpiredError:
            raise
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("metadata/partial fetch failed: %s", exc)
            return None

        # Payload shape captured 2026-06-03: either a list of request
        # descriptors directly, a dict wrapping them under "items"/"requests"/
        # "data", or a single descriptor dict. The walk (incl. the #465
        # expired-descriptor skip) lives in the module-level
        # ``pick_active_15min_identifier`` so the poll path shares it verbatim.
        identifier = pick_active_15min_identifier(payload)
        if identifier is None:
            _LOGGER.debug(
                "metadata/partial: no active 15-min request for VIN %s",
                _mask_vin(vin),
            )
        return identifier

    @staticmethod
    def _descriptor_expired(desc: dict[str, Any]) -> bool:
        """Back-compat shim → module-level :func:`descriptor_expired`.

        Kept because tests and internal callers reference
        ``DataActScraper._descriptor_expired``; the logic now lives at module
        level so the poll path can share it (#957/#966).
        """
        return descriptor_expired(desc)

    async def kickoff_custom_data_request(
        self,
        vin: str,
        *,
        name: str = "VAG Connect HA Integration",
        duration_days: int = 31,
        data_clusters: tuple[str, ...] | None = None,
    ) -> str | None:
        """Create the active 15-min Custom Data Request for ``vin``.

        Should ONLY be called when ``get_active_custom_request_identifier``
        returns None for this VIN (the portal allows AT MOST ONE active
        custom request and rejects a second concurrent kickoff with 4xx).

        Returns the new Identifier on success, None on failure. Raises
        ``DataActSessionExpiredError`` on 401.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415
        import secrets as _secrets  # noqa: PLC0415
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        csrf = await self._fetch_csrf_token()
        if not csrf:
            _LOGGER.debug(
                "kickoff_custom_data_request: no CSRF token - aborting"
            )
            return None

        identifier = _secrets.token_hex(16)  # 32 chars
        now = datetime.now(timezone.utc).replace(microsecond=0)
        clusters = list(data_clusters or _DEFAULT_DATA_CLUSTERS)

        def _body(duration: str, days: int | None) -> dict[str, Any]:
            body: dict[str, Any] = {
                "Name": name,
                "Identifier": identifier,
                "Frequency": "15mins",
                # v2.17.x — the portal REQUIRES a Duration field; without it the
                # POST 400s "Invalid Duration: None. Allowed values are
                # ['No Expiry', 'One Month'] or upcoming dates …" (verified live
                # 2026-07-12). StartDate/EndDate must not contradict it.
                "Duration": duration,
                "StartDate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "DataClusters": clusters,
                "EmailFrequency": "No notification",
                "LastNotificationDate": None,
            }
            # #957/#966 — "No Expiry" is the portal UI's "unlimited" duration,
            # which sends NO EndDate. We previously paired it with a literal
            # EndDate = now + 3650 days (10 years, well outside the portal's
            # ~12-month continuous grant): a self-contradicting shape no human
            # ever creates, plausibly accepted-but-inert. Mirror the UI and omit
            # EndDate for the no-expiry duration (our own kickoff_historical_export
            # already POSTs EndDate=None, so the layer accepts it). Finite
            # durations keep an explicit EndDate.
            if days is not None:
                end = (now + timedelta(days=days)).replace(
                    hour=23, minute=59, second=59
                )
                body["EndDate"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
            return body

        # Every feed used to be created as "One Month", so the data
        # stopped roughly four weeks after setup and the sensors went quiet
        # with no error anywhere. The portal's own message lists "No Expiry"
        # as an allowed value, so that is what we ask for now.
        #
        # "One Month" stays as a fallback: we cannot re-verify the exact
        # no-expiry body shape against the live portal from here, and a
        # rejected kickoff means NO data feed at all. Asking for less is far
        # better than asking for nothing.
        attempts: list[tuple[str, int | None]] = [
            ("No Expiry", None),            # UI-native: null EndDate, not now+3650d
            ("One Month", duration_days),   # proven-emitting finite fallback
        ]
        url = _PORTAL_BASE + _CUSTOM_REQUEST_POST_PATH.format(vin=vin)
        for index, (duration, days) in enumerate(attempts):
            last = index == len(attempts) - 1
            try:
                async with self._session.post(
                    url,
                    json=_body(duration, days),
                    timeout=ClientTimeout(total=30),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        # The portal's own Granite CSRF clientlib sets exactly
                        # this one header on every non-GET same-origin request.
                        # ``X-CSRF-Token`` was ours, and is not a thing here.
                        "CSRF-Token": csrf,
                        # Required by the euda-apim layer (see metadata GET
                        # above); without it the POST 503s at the AEM edge.
                        "traceId": uuid.uuid4().hex,
                    },
                ) as resp:
                    if resp.status == 401:
                        raise DataActSessionExpiredError(
                            "requests/partial returned 401 - portal session expired"
                        )
                    if resp.status in (200, 201, 202):
                        # #957/#966 — a 2xx does NOT prove a working request
                        # landed: a non-native body can be accepted-but-inert, in
                        # which case the old status-only break trusted it blindly
                        # and never tried the proven "One Month". Read it back: the
                        # created request must show up as the active one. If it
                        # doesn't, treat this attempt as failed and fall through to
                        # the next duration. Turns "12h of silent nothing" into a
                        # one-cycle detected failure.
                        try:
                            confirmed = await self.get_active_custom_request_identifier(vin)
                        except DataActSessionExpiredError:
                            raise
                        except Exception:  # noqa: BLE001
                            confirmed = None
                        if confirmed:
                            _LOGGER.info(
                                "EU Data Act Custom Request kicked off for VIN %s "
                                "(Identifier=%s..., Duration=%s, frequency=15min)",
                                _mask_vin(vin), str(confirmed)[:8], duration,
                            )
                            return confirmed
                        if not last:
                            _LOGGER.info(
                                "kickoff_custom_data_request: Duration=%r returned "
                                "%s but no active request appeared on readback — "
                                "retrying with %r",
                                duration, resp.status, attempts[index + 1][0],
                            )
                            continue
                        _LOGGER.warning(
                            "kickoff_custom_data_request: created (HTTP %s) but no "
                            "active request appeared for VIN %s — no data feed will "
                            "start until this is resolved.",
                            resp.status, _mask_vin(vin),
                        )
                        return None
                    body_text = await resp.text(errors="replace")
                    if not last:
                        _LOGGER.info(
                            "kickoff_custom_data_request: portal rejected "
                            "Duration=%r (HTTP %s), retrying with %r: %s",
                            duration, resp.status, attempts[index + 1][0],
                            body_text[:200],
                        )
                        continue
                    # WARNING, not INFO: a non-2xx here means the portal rejected
                    # the request (e.g. a changed request format) → the car gets
                    # NO data feed, silently. It must be visible so the next
                    # portal-side format change doesn't go unnoticed for months.
                    _LOGGER.warning(
                        "kickoff_custom_data_request HTTP %s for VIN %s — no data "
                        "feed will start until this is resolved: %s",
                        resp.status, _mask_vin(vin), body_text[:300],
                    )
                    return None
            except DataActSessionExpiredError:
                raise
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("kickoff_custom_data_request failed: %s", exc)
                return None
        # Every attempt now returns inside the loop (success via readback, or a
        # detected failure); this is only reached if the attempt list were empty.
        return None  # pragma: no cover

    async def kickoff_historical_export(self, vin: str) -> bool:
        """Create a ONE-TIME historical export for ``vin`` (Phase C).

        The 15-min feed (kickoff_custom_data_request) gives live telemetry; this
        is the other request type — a one-time snapshot of the full config set
        (departure timers, charge profiles, climate settings) in the legacy
        Car-Net dialect. The portal generates the ZIP asynchronously (like the
        feed, up to ~24h), after which it is picked up via metadata/all +
        datadelivery.

        Body + endpoint are mirrored EXACTLY from a real Audi trace
        (2026-07-17): POST requests/all with Frequency/EndDate/DataClusters/
        EmailFrequency all null and no Identifier/Duration — a much simpler
        shape than the 15-min kickoff above. Returns True on a 2xx.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        csrf = await self._fetch_csrf_token()
        if not csrf:
            _LOGGER.debug("kickoff_historical_export: no CSRF token - aborting")
            return False

        # The browser sends millisecond precision (…:46.111Z); match it.
        now = datetime.now(timezone.utc)
        start = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
        body: dict[str, Any] = {
            "Name": "Request File",
            "Frequency": None,
            "StartDate": start,
            "EndDate": None,
            "DataClusters": None,
            "EmailFrequency": None,
        }
        url = _PORTAL_BASE + _ALL_REQUEST_POST_PATH.format(vin=vin)
        try:
            async with self._session.post(
                url,
                json=body,
                timeout=ClientTimeout(total=30),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    # Origin is what the browser sends on this POST; CSRF/traceId
                    # are carried defensively (the requests/partial POST proves
                    # the AEM edge accepts them).
                    "Origin": _PORTAL_BASE,
                    # One header, matching the portal's own CSRF clientlib.
                    "CSRF-Token": csrf,
                    "traceId": uuid.uuid4().hex,
                },
            ) as resp:
                if resp.status == 401:
                    raise DataActSessionExpiredError(
                        "requests/all returned 401 - portal session expired"
                    )
                if resp.status not in (200, 201, 202):
                    body_text = await resp.text(errors="replace")
                    _LOGGER.warning(
                        "kickoff_historical_export HTTP %s for VIN %s: %s",
                        resp.status, _mask_vin(vin), body_text[:300],
                    )
                    return False
        except DataActSessionExpiredError:
            raise
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("kickoff_historical_export failed: %s", exc)
            return False

        _LOGGER.info(
            "EU Data Act one-time historical export requested for VIN %s "
            "— the portal will generate the ZIP asynchronously",
            _mask_vin(vin),
        )
        return True


# ── helpers ──────────────────────────────────────────────────────────────────


def _looks_like_zip(body: bytes) -> bool:
    """Cheap zip-magic check before we hand bytes to ``zipfile``."""
    return len(body) >= 4 and body[:4] in (b"PK\x03\x04", b"PK\x05\x06")


def _mask_vin(vin: str) -> str:
    """Return a masked VIN suffix safe to put in logs."""
    if not vin:
        return "?"
    return f"...{vin[-6:]}" if len(vin) > 6 else vin


def _extract_download_urls(payload: Any) -> list[str]:
    """Walk the datadelivery/list response and return all plausible
    download URLs (ZIP or otherwise) the portal points at.

    The exact shape captured per live trace is a file list with one
    URL per entry; we accept either a flat list of dicts or a wrapped
    ``{"files": [...]}`` envelope. URLs must be https:// to count.
    """
    out: list[str] = []
    entries: list[Any] = []
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        for key in ("files", "items", "data", "downloads"):
            inner = payload.get(key)
            if isinstance(inner, list):
                entries = inner
                break
        if not entries and payload.get("downloadUrl"):
            entries = [payload]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in ("downloadUrl", "download_url", "url", "href", "link"):
            val = entry.get(key)
            if isinstance(val, str) and val.startswith("https://"):
                if val not in out:
                    out.append(val)
                break
    return out


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
