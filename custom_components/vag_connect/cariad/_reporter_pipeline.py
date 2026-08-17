# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reporter Pipeline — shared 1-click bug-discovery workflow.

Companion to ``_unexpected_keys.py`` (Vehicle Data Scout) and
``_error_reporter.py`` (Error Reporter). Both feed into this module's
formatter so the user gets a uniform "Report or Copy" experience for
every kind of finding.

Why this lives here and not in ``repairs.py``:

- ``repairs.py`` is HA-glue and brand-agnostic — it raises auth issues.
  This module knows about *the content* of the repair issue (Markdown
  formatting, GitHub URL building, opt-in payload sizes).
- Pure functions here can be unit-tested without HA — only the
  ``ensure_repair_issue`` helper touches the HA registry.

UX contract (from v1.9.0 README announcement, all 8 languages):

1. HA Repair Notification appears under Settings → System → Repairs
   ("Bell" icon turns red).
2. User clicks "Learn more" → modal with summary + 2 buttons:
      "Report on GitHub" — opens browser at a pre-filled issue URL
      "Copy for Forum/Facebook" — copies a Markdown blurb to clipboard
        (handled in HA frontend via ``learn_more_url`` deep link;
        Markdown is also embedded in the description so users can
        copy-paste manually)
3. NEVER auto-pushes. GDPR / HACS rules / GitHub ToS forbid it.

Privacy guarantee: every value that lands in the report goes through
``mask_vin`` / ``_redact`` / ``mask_value`` in the upstream modules.
This module does NOT mask — it formats already-masked data. If you
ever change that, audit the call sites first.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Iterable

import homeassistant.helpers.issue_registry as ir
from homeassistant.core import HomeAssistant

from ..const import DOMAIN
from ._error_reporter import ErrorRecord
from ._unexpected_keys import UnexpectedField, _VIN_RE

# GitHub caps issue-URL query params at ~8KB total. v2.11.4 dropped
# this from 6500 to 4000 because urllib.parse.quote inflates markdown
# bodies ~1.5x (most chars stay literal, but newlines, brackets and
# backticks all expand). Some Chrome / Firefox builds silently drop the
# body param when the FINAL encoded URL crosses 8KB, producing the
# empty-body issues we saw in #409 and #412. 4000 raw → ~6000 encoded
# leaves comfortable headroom.
_GITHUB_BODY_MAX = 4000

# Repo where users land for crowd-sourced bug reports. Keeping this
# constant means we can swap to a discussions URL later without touching
# the call sites.
_REPO_URL = "https://github.com/its-me-prash/vag-connect-ha"

# Issue IDs in the HA Repair registry. Stable IDs — registry deduplicates
# by (domain, issue_id), so re-raising with the same ID just updates the
# existing card instead of stacking duplicates.
ISSUE_ID_UNEXPECTED_KEYS = "vehicle_data_scout_findings"
ISSUE_ID_ERROR_REPORTER = "error_reporter_findings"


# ── Intentional-skip allowlist — REPAIR suppression, NOT data suppression ──
# Matching findings stay fully Scout-VISIBLE in diagnostics (they remain in
# VehicleData.raw_unmapped_fields → the raw_api_fields sensor, and in the
# coordinator's unexpected_findings count) but are kept OUT of the user-facing
# Scout repair, so they stop prompting every reporter to hand-file the same
# already-investigated issue. Distinct from EXPECTED_KEYS / EU-DA first()-reclaim,
# which remove the field from raw_unmapped_fields entirely — these must NOT be
# data-suppressed (scope_potential_total is intentionally-unmapped-but-visible per
# _eu_data_act.py; the ownerless openings are kept Scout-visible per #1100).
# Spam so far: scope_potential_total → #1151/#1156/#1164/#1166/#1167;
#              c0bb1348/d5dc7c87 → #1140/#1149/#1152/#1161/#1168;
#              *.is_set → #465/#1216 (and every EU-DA portal car).
# ``is_set`` is the EU-DA envelope "is this field populated" boolean that rides
# alongside many fields (mileage.is_set, hvbatterytemperature.is_set, trunk.is_set
# …). It carries no value we surface (absence is already ``None``), and the leaf
# match here catches every ``*.is_set`` in one entry, so no portal car keeps
# getting prompted to file it. Stays Scout-visible in diagnostics like the rest.
_SCOUT_REPAIR_SKIP_LEAVES: frozenset[str] = frozenset({"scope_potential_total", "is_set"})
# Substring match on the (masked) sample: #1100's UUID annotation rides in the
# value as ``... (uuid c0bb1348)``; keying on the UUID (not the eu_data_act.open
# PATH) preserves discovery — a genuinely-new opening UUID on the same leaf still
# raises the repair.
_SCOUT_REPAIR_SKIP_UUIDS: frozenset[str] = frozenset({"c0bb1348", "d5dc7c87"})


def _is_scout_repair_skipped(f: UnexpectedField) -> bool:
    """True if a finding is known/intentionally-unmapped and must not spawn the
    user-facing Scout repair. It stays in raw_unmapped_fields regardless."""
    if f.path.rsplit(".", 1)[-1] in _SCOUT_REPAIR_SKIP_LEAVES:
        return True
    sample = f.sample_masked or ""
    return any(u in sample for u in _SCOUT_REPAIR_SKIP_UUIDS)


# ---------------------------------------------------------------------------
# Privacy guard — the model-name choke point
# ---------------------------------------------------------------------------


def _safe_model(model: str | None, *, vin: str | None = None) -> str | None:
    """Return a privacy-safe model name, or ``None`` to omit it entirely.

    The model is meant to be a *generic* label like ``"ID.4"`` — fine to put
    in a public GitHub issue title/body. But for some brands (notably Audi,
    whose CARIAD/myAudi vehicle list ships the VIN as the vehicle "name" when
    the owner never renamed the car) the value we receive is the raw 17-char
    VIN — a privacy-sensitive identifier that ties to registration and
    ownership records. The footer claims "VINs masked to last 6 chars", so a
    full VIN leaking through the title/model bypasses that guarantee.

    This is the single choke point every report flows through, so the guard
    here is bulletproof regardless of how the upstream resolved the model:

    - empty / whitespace-only  → ``None`` (caller omits the line)
    - contains a VIN substring (17-char VIN charset, any case) → ``None``
    - equals this vehicle's VIN (case-insensitive) → ``None``
    - anything else → the trimmed model, passed through unchanged

    We *omit* rather than mask-to-6: a 6-char VIN tail is not a "model" and
    would only confuse triage. The brand alone is enough to scope the issue,
    and the per-record masked VIN (``r.vin_masked``) still gives a maintainer
    a disambiguator inside the body.
    """
    if not model:
        return None
    trimmed = model.strip()
    if not trimmed:
        return None
    if vin and trimmed.upper() == vin.strip().upper():
        return None
    # Catch an embedded VIN in ANY case — a suffixed "<VIN> Quattro" or a
    # lowercased VIN — via search()+upper(), not an all-or-nothing uppercase
    # fullmatch (a model containing a full 17-char VIN is never legitimate).
    if _VIN_RE.search(trimmed.upper()):
        return None
    return trimmed


# ---------------------------------------------------------------------------
# Markdown formatters — pure functions, easy to unit-test
# ---------------------------------------------------------------------------


def build_unexpected_keys_report(
    findings: Iterable[UnexpectedField],
    *,
    brand: str,
    model: str | None = None,
    model_year: int | None = None,
    firmware: str | None = None,
    integration_version: str = "",
) -> str:
    """Format Vehicle Data Scout findings as a copy-pasteable Markdown body.

    Layout matches the issue templates so a maintainer can triage in one
    glance:

    - context block (brand / model / model year / firmware / version)
    - one row per finding (path, masked sample, endpoint, first seen)
    - a privacy note at the bottom so the reporter knows what was stripped

    The output is intentionally short and table-friendly — Facebook /
    forum users paste it as-is. Markdown also renders cleanly on GitHub.
    """
    findings_list = list(findings)
    if not findings_list:
        return ""

    model = _safe_model(model)

    lines: list[str] = []
    lines.append(f"## Vehicle Data Scout — {len(findings_list)} new field(s)")
    lines.append("")
    lines.append(f"- **Brand:** `{brand}`")
    if model:
        lines.append(f"- **Model:** `{model}`")
    if model_year is not None:
        lines.append(f"- **Model year:** `{model_year}`")
    if firmware:
        lines.append(f"- **Firmware:** `{firmware}`")
    if integration_version:
        lines.append(f"- **Integration:** `vag_connect {integration_version}`")
    lines.append(
        f"- **Reported at:** `{datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}`"
    )
    lines.append("")
    # b1/A3 — annotate each finding with the official EU Data Act spec name
    # when the path identifies a known field UUID. Turns an opaque UUID into a
    # human field name in the bug report (and is the same dictionary the raw
    # field discovery uses). Enrichment only — never fails the report.
    from .auth import eu_data_dictionary as _dd  # noqa: PLC0415
    lines.append("| Path | Spec field (official) | Sample (masked) | Endpoint | First seen |")
    lines.append("|---|---|---|---|---|")
    for f in findings_list:
        # Pipe characters in any cell would break the Markdown table.
        # Replace defensively — the masking layer never produces them
        # but a future regex change might.
        path = f.path.replace("|", "\\|")
        spec = (_dd.describe(f.path) or "—").replace("|", "\\|")
        sample = (f.sample_masked or "").replace("|", "\\|")
        endpoint = (f.endpoint or "").replace("|", "\\|")
        first_seen = f.first_seen_at or ""
        lines.append(f"| `{path}` | {spec} | `{sample}` | `{endpoint}` | {first_seen} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "_Privacy: VINs masked to last 6 chars, GPS rounded to 1 decimal, "
        "userIDs/JWTs/emails stripped. No raw API response is included._"
    )
    return "\n".join(lines)


def build_error_report(
    records: Iterable[ErrorRecord],
    *,
    brand: str,
    model: str | None = None,
    integration_version: str = "",
) -> str:
    """Format Error Reporter records as a copy-pasteable Markdown body.

    One section per error — exception type as a heading, then a fenced
    code block with the message + truncated traceback. The maintainer
    needs the traceback to find the call site; the user has already had
    it scrubbed of tokens by ``_redact`` upstream.
    """
    records_list = list(records)
    if not records_list:
        return ""

    model = _safe_model(model)

    lines: list[str] = []
    lines.append(f"## Error Reporter — {len(records_list)} recent error(s)")
    lines.append("")
    lines.append(f"- **Brand:** `{brand}`")
    if model:
        lines.append(f"- **Model:** `{model}`")
    if integration_version:
        lines.append(f"- **Integration:** `vag_connect {integration_version}`")
    lines.append(
        f"- **Reported at:** `{datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}`"
    )
    lines.append("")

    for idx, r in enumerate(records_list, start=1):
        lines.append(f"### {idx}. `{r.exception_type}` at {r.timestamp}")
        if r.endpoint:
            lines.append(f"- **Endpoint:** `{r.endpoint}`")
        rec_model = _safe_model(r.model)
        if rec_model:
            lines.append(f"- **Model:** `{rec_model}`")
        if r.model_year is not None:
            lines.append(f"- **Model year:** `{r.model_year}`")
        if r.firmware:
            lines.append(f"- **Firmware:** `{r.firmware}`")
        if r.vin_masked:
            lines.append(f"- **VIN:** `{r.vin_masked}`")
        lines.append("")
        lines.append("```")
        lines.append(r.message_masked or "(no message)")
        if r.traceback_masked:
            lines.append("")
            lines.append(r.traceback_masked.rstrip())
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Privacy: VINs masked, Bearer/JWT/UUID/email tokens stripped from "
        "messages and tracebacks. No credentials are included._"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GitHub URL builder — pure function
# ---------------------------------------------------------------------------


def github_issue_url(
    title: str,
    body: str,
    *,
    repo_url: str = _REPO_URL,
    labels: tuple[str, ...] = (),
    body_max: int = _GITHUB_BODY_MAX,
) -> str:
    """Build a pre-filled GitHub issue URL.

    Truncates the body if it would push past the URL limit (browsers
    silently drop everything past ~8KB, and GitHub's own backend rejects
    longer query strings with a 414). When truncation kicks in we append
    a marker so reviewers know there's more locally.

    The URL is safe to feed straight into ``learn_more_url`` on a HA
    repair issue, or to print and copy to clipboard.
    """
    if len(body) > body_max:
        body = body[: body_max - 80] + (
            "\n\n_… truncated — full report available via "
            "Settings → Devices → VAG Connect → Diagnostics._"
        )
    params: list[tuple[str, str]] = [("title", title), ("body", body)]
    if labels:
        params.append(("labels", ",".join(labels)))
    qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{repo_url.rstrip('/')}/issues/new?{qs}"


# ---------------------------------------------------------------------------
# HA Repair-issue glue — only function in this module that touches HA
# ---------------------------------------------------------------------------


def ensure_unexpected_keys_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    findings: Iterable[UnexpectedField],
    brand: str,
    model: str | None = None,
    model_year: int | None = None,
    firmware: str | None = None,
    integration_version: str = "",
) -> None:
    """Create or refresh the Vehicle Data Scout repair issue for one entry.

    Called from the coordinator after each successful poll *only* when
    new findings have been added since the last call. The HA registry
    deduplicates by ``(DOMAIN, issue_id)`` — re-raising with the same ID
    just refreshes the card.

    If ``findings`` is empty we delete the existing issue (the user
    cleared the buffer, or the API surface stabilised).

    ``learn_more_url`` points to a pre-filled GitHub issue URL so
    "Learn more" in the HA UI sends the user straight into a 1-click
    report. The Markdown body is also embedded in the description so
    Facebook/forum users can copy-paste without leaving HA.
    """
    # Drop the intentional-skip set from the REPAIR only (they stay in
    # raw_unmapped_fields / diagnostics). If a poll's findings are *only* the
    # skipped set, findings_list is empty and the empty-case below deletes the
    # repair — no more per-user spam for scope_potential_total / c0bb1348.
    findings_list = [f for f in findings if not _is_scout_repair_skipped(f)]
    issue_id = f"{entry_id}_{ISSUE_ID_UNEXPECTED_KEYS}"

    if not findings_list:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    body = build_unexpected_keys_report(
        findings_list,
        brand=brand,
        model=model,
        model_year=model_year,
        firmware=firmware,
        integration_version=integration_version,
    )
    safe_model = _safe_model(model)
    brand_model = f"{brand} {safe_model}" if safe_model else brand
    url = github_issue_url(
        f"[Vehicle Data Scout] {len(findings_list)} new field(s) on {brand_model}",
        body,
        labels=("vehicle-data-scout", brand),
    )

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="vehicle_data_scout_findings",
        translation_placeholders={
            "brand": brand,
            "count": str(len(findings_list)),
        },
        learn_more_url=url,
    )


def ensure_error_reporter_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    records: Iterable[ErrorRecord],
    brand: str,
    model: str | None = None,
    integration_version: str = "",
) -> None:
    """Create or refresh the Error Reporter repair issue for one entry.

    Mirrors ``ensure_unexpected_keys_issue`` but for runtime exceptions.
    Severity is ERROR (vs WARNING for unexpected keys) — runtime errors
    likely mean a feature is broken, not just unmapped.

    ``records`` is the *current* ring buffer contents — caller passes
    ``buffer.records`` directly. Empty buffer → issue is deleted.
    """
    records_list = list(records)
    issue_id = f"{entry_id}_{ISSUE_ID_ERROR_REPORTER}"

    if not records_list:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    body = build_error_report(
        records_list,
        brand=brand,
        model=model,
        integration_version=integration_version,
    )
    safe_model = _safe_model(model)
    brand_model = f"{brand} {safe_model}" if safe_model else brand
    url = github_issue_url(
        f"[Error Reporter] {len(records_list)} recent error(s) on {brand_model}",
        body,
        labels=("error-reporter", brand),
    )

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="error_reporter_findings",
        translation_placeholders={
            "brand": brand,
            "count": str(len(records_list)),
        },
        learn_more_url=url,
    )
