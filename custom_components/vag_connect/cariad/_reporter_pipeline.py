# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
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
from ._unexpected_keys import UnexpectedField

# GitHub caps issue-URL query params at ~8KB total. Stay well below to
# leave room for the title, labels and the encoding overhead. Chrome's
# practical URL limit is also ~8KB.
_GITHUB_BODY_MAX = 6500

# Repo where users land for crowd-sourced bug reports. Keeping this
# constant means we can swap to a discussions URL later without touching
# the call sites.
_REPO_URL = "https://github.com/its-me-prash/vag-connect-ha"

# Issue IDs in the HA Repair registry. Stable IDs — registry deduplicates
# by (domain, issue_id), so re-raising with the same ID just updates the
# existing card instead of stacking duplicates.
ISSUE_ID_UNEXPECTED_KEYS = "vehicle_data_scout_findings"
ISSUE_ID_ERROR_REPORTER = "error_reporter_findings"


# ---------------------------------------------------------------------------
# Markdown formatters — pure functions, easy to unit-test
# ---------------------------------------------------------------------------


def build_unexpected_keys_report(
    findings: Iterable[UnexpectedField],
    *,
    brand: str,
    model_year: int | None = None,
    firmware: str | None = None,
    integration_version: str = "",
) -> str:
    """Format Vehicle Data Scout findings as a copy-pasteable Markdown body.

    Layout matches the issue templates so a maintainer can triage in one
    glance:

    - context block (brand / model year / firmware / version)
    - one row per finding (path, masked sample, endpoint, first seen)
    - a privacy note at the bottom so the reporter knows what was stripped

    The output is intentionally short and table-friendly — Facebook /
    forum users paste it as-is. Markdown also renders cleanly on GitHub.
    """
    findings_list = list(findings)
    if not findings_list:
        return ""

    lines: list[str] = []
    lines.append(f"## Vehicle Data Scout — {len(findings_list)} new field(s)")
    lines.append("")
    lines.append(f"- **Brand:** `{brand}`")
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
    lines.append("| Path | Sample (masked) | Endpoint | First seen |")
    lines.append("|---|---|---|---|")
    for f in findings_list:
        # Pipe characters in any cell would break the Markdown table.
        # Replace defensively — the masking layer never produces them
        # but a future regex change might.
        path = f.path.replace("|", "\\|")
        sample = (f.sample_masked or "").replace("|", "\\|")
        endpoint = (f.endpoint or "").replace("|", "\\|")
        first_seen = f.first_seen_at or ""
        lines.append(f"| `{path}` | `{sample}` | `{endpoint}` | {first_seen} |")
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

    lines: list[str] = []
    lines.append(f"## Error Reporter — {len(records_list)} recent error(s)")
    lines.append("")
    lines.append(f"- **Brand:** `{brand}`")
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
    findings_list = list(findings)
    issue_id = f"{entry_id}_{ISSUE_ID_UNEXPECTED_KEYS}"

    if not findings_list:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    body = build_unexpected_keys_report(
        findings_list,
        brand=brand,
        model_year=model_year,
        firmware=firmware,
        integration_version=integration_version,
    )
    url = github_issue_url(
        f"[Vehicle Data Scout] {len(findings_list)} new field(s) on {brand}",
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
        integration_version=integration_version,
    )
    url = github_issue_url(
        f"[Error Reporter] {len(records_list)} recent error(s) on {brand}",
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


def clear_reporter_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Drop both reporter issues for one entry.

    Called when the user removes the integration or hits "Reset" on the
    sensors. Cheap to call defensively — ``async_delete_issue`` is a
    no-op if the issue doesn't exist.
    """
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_{ISSUE_ID_UNEXPECTED_KEYS}")
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_{ISSUE_ID_ERROR_REPORTER}")
