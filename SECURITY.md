# Security Policy

> **Reporting context:** VW Group Connect is a Home Assistant integration that
> talks to manufacturer APIs on behalf of vehicle owners. It handles
> credentials, OAuth tokens, S-PINs, vehicle GPS positions, and VINs. We
> take security reports seriously.

---

## Supported Versions

Only the **latest minor release line** receives security fixes. Older lines
are not patched.

| Version | Supported |
|---|---|
| 5.2.x | ✅ |
| < 5.2 | ❌ — please update |

> This table was left at `4.7.x` for five minor lines. If you are reading it
> and the number looks older than the latest release, the release is right and
> the table is stale — please open an issue.

Home Assistant supports the integration on its own currently-supported core
versions (typically the last 4 monthly releases). Any HA below the
`hacs.json` minimum is unsupported.

---

## Reporting a Vulnerability

**Please do not file public GitHub issues for security vulnerabilities.**

Use one of the following private channels:

1. **GitHub Security Advisories (preferred)**
   <https://github.com/its-me-prash/vwgroup-connect-ha/security/advisories/new>
   — sends an encrypted private report to the maintainer.

2. **Direct contact**
   Open a GitHub Discussion marked `security` and ask the maintainer to
   move it private. Or use the contact details on the maintainer's GitHub
   profile.

Please include, where possible:

- Affected version(s) of VW Group Connect
- Affected Home Assistant version (if relevant)
- Steps to reproduce
- Impact assessment (what does an attacker gain?)
- Whether the issue has already been disclosed publicly

We will acknowledge receipt within **72 hours** and aim to publish a fix or
mitigation within **14 days** for high-severity issues.

---

## Scope

### In scope

- Code under `custom_components/vag_connect/`
- GitHub Actions workflows under `.github/workflows/`
- Documented installation and configuration paths

### Out of scope

- Vulnerabilities in upstream manufacturer APIs (CARIAD BFF, OLA,
  mysmob, PPA, etc.) — please report those to Volkswagen / Audi /
  Škoda / SEAT / CUPRA / Porsche directly.
- Issues caused by user misconfiguration or third-party HACS plugins.
- Theoretical issues without a working proof of concept.

---

## What we already do

- **Zero external runtime dependencies** (`requirements: []` in
  `manifest.json`) — no transitive supply-chain risk.
- **Credentials redaction** in `diagnostics.py` — passwords, S-PINs,
  usernames and GPS coordinates are redacted from diagnostics exports. The
  redaction is **by key name**, applied recursively, so a value is only safe
  once its key, or a key above it, is registered. That is a real limit and not
  a formality: until 5.2.1 the primary `website_cookies` jar was not
  registered, and a diagnostics file from an earlier version can carry a live
  volkswagen.de session. See **#1968** for what to do if you have attached
  one. Since 5.2.1 the completeness of that list is a test, derived from the
  key names in `const.py` rather than read off the list itself.
- **S-PIN fail-fast** (since v1.8.0 / #60) — privileged commands raise
  `ServiceValidationError` before they reach the API.
- **Reverse geocoding opt-in** (since v1.8.0 / #60) — vehicle GPS is
  not sent to third-party services unless the user explicitly enables it.
- **TLS-only API calls** — the integration uses HTTPS for every endpoint.
- **Token cache lives inside Home Assistant's protected `.storage/` dir**
  — since v1.19.2 the integration persists OAuth tokens (per-config-entry)
  via HA's `Store` helper to `.storage/vag_connect_tokens_<entry_id>`. The
  file is JSON, scoped to the HA instance's config volume (same trust
  boundary as `entry.data` credentials), and is removed automatically when
  the integration is removed via `async_remove_entry`.
- **Token redaction in diagnostics** — `access_token`, `refresh_token`,
  `id_token`, `client_secret` (snake_case + camelCase variants) and email
  addresses are masked in `diagnostics.py` exports. JWT-pattern strings
  are stripped from any value field via `JWT_RE`. Because the match is on the
  key name and runs recursively, a token dict nested under an unregistered
  container key is still masked by its inner names — which is why the
  `mbb_command_tokens` and `supplementary_tibber_tokens` values were covered
  before 5.2.1 while the cookie jar, whose keys are `name` / `value` /
  `domain`, was not.

---

## How a problem gets published

Reporting is private (above). **Disclosure is public**: once a fix is released,
what was wrong, which versions are affected and what a user has to do are
written up in a normal issue, linked from the release notes and from
`CHANGELOG.md`. The advisory for the diagnostics exposure is **#1968**. If a
fix changes what you were told to do, the correction is appended to that same
page rather than replacing it, so the record of what changed stays readable.

---

## What is NOT a vulnerability

- Manufacturer accounts being temporarily rate-limited after too many
  poll requests. This is a server-side rate-limit, not a vulnerability.
- HA users on the same Home Assistant instance being able to read each
  other's vehicle data. This is a **Home Assistant access-control
  matter**, not a VW Group Connect issue.

---

*Last updated: 2026-10-31 — v5.2.2*
