# VAG Connect HA — Session Handoff

> **Living document.** Updated at the end of every release sprint so the
> next chat / contributor / AI tool has a single page that orients them
> in 5 minutes.

**Last updated:** 2026-05-08 — post v1.24.1 sprint (CI hot-fix + Audit
Quick-Win-Hardening + Doc-Hygiene — 8 releases since v1.20.0 in 4 days).

> ℹ️ **Sektionen unterhalb sind teilweise historisch (v1.8.x baseline).**
> Aktuelle authoritative Quellen: [`ROADMAP.md`](ROADMAP.md) für Sprint-
> Planung, [`../CHANGELOG.md`](../CHANGELOG.md) für Release-Historie.
> Die `Current state` Box gibt jeweils den jüngsten manifest+release-
> stand wieder. Voll-Rewrite dieses Dokuments ist als eigene Session
> in der Sprint-Pipeline (post-v1.25.0).

---

## Where to look first (5-minute orientation)

| What | Where |
|---|---|
| 🎯 Verified API facts archive | [`docs/RESEARCH_NOTES_2026-04-29.md`](RESEARCH_NOTES_2026-04-29.md) |
| 📜 Full technical changelog with citations | [`docs/CHANGELOG_TECHNICAL.md`](CHANGELOG_TECHNICAL.md) |
| 👥 Human-friendly release notes | [`../CHANGELOG.md`](../CHANGELOG.md) |
| 📋 Sessioned roadmap | [`docs/ROADMAP.md`](ROADMAP.md) (mirrors README) |
| 🐛 Active issues | https://github.com/its-me-prash/vag-connect-ha/issues |
| 🔬 Original P0/P1 audit (v1.8.0 baseline) | [`docs/AUDIT_2026-04-26.md`](AUDIT_2026-04-26.md) |
| 🔬 Multi-source audit + session map | [`docs/AUDIT_2026-04-29.md`](AUDIT_2026-04-29.md) |
| 🌍 Brand & API ecosystem | [`research/VAG_GROUP_ECOSYSTEM.md`](research/VAG_GROUP_ECOSYSTEM.md) |
| 🚫 Out-of-scope brands | [`research/LUXURY_BRANDS.md`](research/LUXURY_BRANDS.md) |

---

## Current state — v1.24.1 (released as Latest 2026-05-08)

```
Branch:           main
Manifest:         version 1.24.1, iot_class cloud_polling
Quality scale:    clean (CI publishes badges dynamically)
Open PRs:         none
Branch protection: ON — 5 required checks (Lint, Tests, Hassfest, HACS, CHANGELOG)
                  ⚠️ NOTE: v1.24.0 was bypassed via admin override (root-cause:
                  ruff E741 fixed in v1.24.1). DO NOT bypass again — review
                  branch-protection settings to disable admin-bypass on main.
Latest tag:       v1.24.0 → released (v1.24.1 in flight)
Open issues:      ~8 (4 wait-on-user incl. stale-clock running, 2 wait-on-
                  community-tester, 1 actionable-now, 1 ongoing-live-test)
                  → see ROADMAP.md "P0 / P1 / P2" tables for prioritization
                  → 6 internal ROADMAP items are NOT tracked as GH issues
                    (visibility gap, action-item to backfill)
```

### Recently shipped (post v1.20.0 audit on 2026-05-08)

| Version | Title | New tests |
|---|---|---|
| v1.24.1 | CI fix + Doc hygiene + Quick-Win Hardening (Audit 2026-05-08) | (no new tests — pure hygiene) |
| v1.24.0 | Cross-brand image-entity wiring (CUPRA/SEAT silent bug + Skoda multi-angle) | 24 |
| v1.23.0 | Audi/VW Push Foundation (Cariad FCM channel) | 12 |
| v1.22.0 | Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic) | 8 |
| v1.21.0 | Audi/VW MBB Legacy-Path Migration Phase 1 (8 user-bugs structural fix) | 29 |
| v1.20.3 | Cariad-wrapper-404 detection + Switch hasattr-gate | 7 |
| v1.20.2 | Skoda parser hardening + phantom-entity fix + cleanup | 12 |
| v1.20.1 | BinarySensor LOCK-class invert (#131) + Doc refresh | 7 |
| v1.20.0 | Bundle 2 Phase A — Skoda Widget + Vehicle-Info + Equipment | 16 |

### Releases shipped 2026-04-29

| Version | Title | New tests |
|---|---|---|
| v1.8.6 | Docs Truthfulness + Multi-Brand-Successor positioning | — |
| v1.8.7 | Defensive Programming Pass — retry, stale-cache, token guard | 12 |
| v1.8.8 | Session 3B — CARIAD v1/v2 lock/climate/charging | 4 |
| v1.8.9 | Session 3C — CUPRA OLA status JSON paths fix | 12 |
| v1.8.10 | Hotfix legacy doors fallback inversion | — |
| v1.8.11 | Session 3S — Škoda carCapturedTimestamp connection-state | 10 |
| v1.8.12 | MVP-Move — Multi-Brand connection-state (all 4 CARIAD brands) | 12 |
| v1.9.0 | Vehicle Data Scout + Error Reporter (Reporter Pipeline) | 18 |
| v1.9.1 | Audi Lock+Wake Hotfix (#92) + Capability-Filter Phase 2 + Scout-Pfade #90/#91 | 18 |
| v1.10.0 | PHEV-Range-Triple + Audi-Diesel-Range (#94 + #91) | 13 |

### Releases shipped 2026-04-30

| Version | Title | New tests |
|---|---|---|
| v1.10.1 | Defensive Coding Phase 2 (#58) | 16 |
| v1.10.2 | CUPRA Born 2026 Firmware-Shapes (Gerhard #53 erste Live-Validation) | 16 |
| v1.11.0 | Issue #91 Closure (Lights/Service-Days/Max-Charge-Current sensor) | 15 |
| v1.11.1 | Golf GTE Fuel-Range #96 + Optimistic UI (3B-Part-3) | 18 |
| (Doc PR #101) | Privacy & data handling rules + [Inference] markers (post-#53 review) | — |
| v1.12.0 | 5-in-1 Sprint: 12V #23 + Per-Light + Writeable Number + Smart-Wake #55 + Read-only #63-Phase-1 | 25 |
| **v1.12.1** | **Scout-Pfade #105/#106 + Gerhard's Born Fixture (#53 consent) + #47 FAQ** | **19** |

Total über beide Tage: ~210 neue Tests, 17 Code-Releases + 1 Doc-PR, alle CI-green, alle merged + tagged.

### Process improvements (don't lose these)

- ✅ **Branch protection on `main`** — 5 required status checks
  (Lint, Unit Tests, HA Hassfest, HACS, CHANGELOG). Failing CI now
  blocks merge (lesson from v1.8.9 incident where failing test got
  merged because protection wasn't on)
- ✅ **CI watcher fallback** — `gh pr checks --watch` returns exit 0
  on "completed" (not "all green"). Always parse `gh pr checks <num>`
  explicitly: count non-SUCCESS conclusions before merging
- ✅ **`changelog_check.yml` triggers also on `CHANGELOG.md` and
  `docs/CHANGELOG_TECHNICAL.md`** — doc-only PRs no longer BLOCKED by
  required check that wouldn't run
- ✅ **CHANGELOG split** — `CHANGELOG.md` is human-friendly with emojis,
  `docs/CHANGELOG_TECHNICAL.md` has full technical detail with all
  issue/PR citations

---

## Architecture map (where to look in code)

```
custom_components/vag_connect/
├── __init__.py              PLATFORMS list = 10, service registration, setup hooks
├── coordinator.py           Own poll loop (NOT HA scheduler), per-VIN
│                            availability, capabilities cache, command profile,
│                            failure tolerance + 6h stale-cache (v1.8.7)
├── entity_base.py           VagConnectEntity — per-VIN availability check
├── config_flow.py           Setup + Options flow (reverse_geocoding opt-in)
├── const.py                 Brand IDs, conf keys
├── manifest.json            ⚠️  Single source of truth for version
├── strings.json             English source for translations
├── translations/{cs,de,en,es,fr,nl,pl,sv}.json   Mirror of strings.json
├── sensor.py                ~30 sensor descriptions, including
│                            connection_state (v1.8.11), vehicle_state
├── binary_sensor.py         ~16 binary sensors + per-door + per-window
│                            (v1.8.9 added windows_individual + VagWindowSensor)
├── switch.py, button.py, climate.py, number.py, lock.py, image.py,
│   select.py, device_tracker.py    Other 9 platforms
└── cariad/
    ├── _util.py             mask_vin (privacy) + compute_connection_state
    │                        (v1.8.12 — recursive timestamp walk, brand-agnostic)
    ├── exceptions.py        APIError, AuthenticationError,
    │                        TermsAndConditionsError, MarketingConsentError,
    │                        TwoFactorRequiredError, RateLimitError,
    │                        TokenExpiredError, SpinError, VehicleCommandError,
    │                        CommandProfile (12-value enum, v1.8.5),
    │                        CommandFailureReason (10-value enum, v1.8.2),
    │                        classify_command_failure() helper
    ├── models.py            BrandConfig (1 per brand), VehicleData (~80 fields)
    ├── factory.py           CariadClientFactory.create(brand, ...)
    ├── auth/
    │   ├── idk.py           IDK PKCE — VW EU, Audi, Škoda, SEAT, CUPRA, VW NA
    │   └── porsche.py       Auth0 PKCE — Porsche
    └── api/
        ├── base.py          CariadBaseClient — _request with v1.8.7 retry
        │                    layer; _post_command (v1/v2 fallback v1.8.5)
        ├── vw_eu.py         VWEUClient — selectivestatus parsing,
        │                    _post_command_with_fallback_paths (v1.8.8),
        │                    connection_state via helper (v1.8.12)
        ├── audi.py          AudiClient(VWEUClient) — AZS token + vgql GraphQL
        ├── skoda.py         SkodaClient — mysmob endpoints, detail block
        │                    (v1.8.11), reliableLockStatus, fullyChargedAt,
        │                    connection_state refactored to helper (v1.8.12)
        ├── seat_cupra.py    SeatCupraClient — OLA endpoints, SecToken lock
        │                    flow (v1.8.4), pycupra-style status paths (v1.8.9),
        │                    Live-API charging fields (v1.8.9),
        │                    connection_state via helper (v1.8.12)
        ├── porsche.py       PorscheClient — api.ppa.porsche.com
        ├── vw_na.py         VWNorthAmericaClient — VW US/CA
        └── graphql.py       VehicleImageFetcher — Audi vgql GraphQL only
```

### Reading order for a new contributor / AI tool

1. **This file** — orientation
2. [`docs/RESEARCH_NOTES_2026-04-29.md`](RESEARCH_NOTES_2026-04-29.md) —
   verified API facts, every claim cited
3. [`docs/CHANGELOG_TECHNICAL.md`](CHANGELOG_TECHNICAL.md) — what
   changed and why
4. `cariad/api/base.py` — request lifecycle, retry semantics
5. `cariad/_util.py:compute_connection_state` — example of clean,
   well-tested, brand-agnostic helper
6. `cariad/api/skoda.py` — most recent example of a brand client
   following all v1.8.x patterns

---

## Sessioned roadmap (next sessions)

| Session | Version | Scope | Issues |
|---|---|---|---|
| ~~1 — Foundation Fix~~ | ~~v1.8.0~~ | ✅ Done — 7 P0 release blockers | ✅ #60 |
| ~~2A — Capabilities Foundation~~ | ~~v1.8.2~~ | ✅ Done — error taxonomy + 3-state model + cache | ✅ #68 |
| ~~2B — Button gating~~ | ~~v1.8.3~~ | ✅ Done — SEAT/CUPRA flash/wake | ✅ partial #56 |
| ~~2C — SEAT/CUPRA Lock~~ | ~~v1.8.4~~ | ✅ Done — SecToken flow | ✅ #53 partial |
| ~~3A — Command Profile~~ | ~~v1.8.5~~ | ✅ Done — v1/v2 fallback for 4 set-value | ✅ #51, #61 done, #74 partial |
| ~~Docs Truthfulness~~ | ~~v1.8.6~~ | ✅ Done | ✅ |
| ~~Defensive Programming~~ | ~~v1.8.7~~ | ✅ Done — retry, stale-cache, token guard | ✅ |
| ~~3B — CARIAD v1/v2 main commands~~ | ~~v1.8.8~~ | ✅ Done — lock, unlock, climate, charging | ✅ #51, #74 |
| ~~3C — CUPRA OLA status fix~~ | ~~v1.8.9~~ | ✅ Done — Gerhard's 19 entities | ✅ #53 commands |
| ~~Hotfix~~ | ~~v1.8.10~~ | ✅ Done — legacy doors inversion | — |
| ~~3S — Škoda connection-state~~ | ~~v1.8.11~~ | ✅ Done — closes #54 | ✅ #54 |
| ~~MVP-Move — Multi-Brand connection-state~~ | ~~v1.8.12~~ | ✅ Done — VW EU + Audi + CUPRA + SEAT | — |
| **Vehicle Data Scout + Error Reporter** | **v1.9.0** | Two new diagnostic sensors sharing one **Reporter Pipeline** for crowd-sourced bug discovery. (1) **Vehicle Data Scout** — logs JSON fields the parser doesn't read (mirrors tillsteinbach `CarConnectivity-*` "Unexpected Keys found" pattern, our richest source of API findings — CC-seatcupra #109, CC-skoda #50). User-facing name brand-localised (DE: "API-Beobachter", FR: "Détecteur de nouvelles données", etc.). (2) **Error Reporter** — captures last N Exceptions / API errors / stack traces from the integration with brand + model + firmware context. **Common Reporter Pipeline (1-click workflow, both sources):** detection → HA repair notification → user clicks "Mehr Info" → modal shows anonymised content + 2 buttons: `📤 Bug auf GitHub melden` (opens pre-filled GitHub issue) AND `📋 Copy für Forum/Facebook` (copies formatted Markdown to clipboard for non-GitHub users). Especially valuable for the Facebook community — non-technical users get a one-click way to share usable bug reports without learning Markdown or GitHub. ~30 sec end-to-end. NO auto-push to external servers (GDPR + HACS-Default + GitHub ToS); opt-in telemetry is a separate v1.10.x scope. Privacy: every value passes through `mask_vin`-style anonymisation. Implementation: `cariad/_unexpected_keys.py` + `cariad/_error_reporter.py` + shared `_reporter_pipeline.py` for HA-side modal/notifications + 8-language strings for buttons + brand-localised sensor names. **Semver: MINOR (new sensors), not patch.** | new |
| **Capability-Filter Phase 2** | v1.9.1 | `capability.active && capability.user-enabled` before entity creation. CC-seatcupra #64 pattern. PATCH (refines existing capability cache). | #56 |
| **Defensive Coding Phase 2** | v1.9.2 | Generic `except Exception` audit across all API clients. Enum tolerance for `CHARGING_INTERRUPTED`, `NOT_ACTIVATED`, `NO_UPDATE_AVAILABLE` etc. PATCH. | #58 |
| **3B-Part-3 — Optimistic Lock/Climate** | v1.9.3 | myskoda #832 pattern — optimistic update + state restoration. PATCH (better UX of existing entities). | — |
| **Diagnostics + Smart-Wake + 12V protection** | **v1.10.0** | MINOR (new sensors): anonymized diagnostics export, persistent wake counter (max 3/day), `wake_count_today` sensor, **NEVER auto-wake**, 12V drain detection from `connectionWarning.insufficientBatteryLevelWarning` (volkswagencarnet #940). | #62, #63, #55, #23 |
| **Process & Governance** | — | Issue forms, brand captains, CODEOWNERS, privacy guide. Doc-only, no version. | #64 |
| **Push CUPRA/SEAT + Push Škoda** | v1.10.x | Firebase FCM via `mqtt.messagehub.de` (CUPRA/SEAT) + mysmob MQTT broker (Škoda-only). PATCH each (additive). | #57, #27 |
| **Trip Stats + Image refactor** | **v1.11.0** | MINOR: Audi `tripstatistics/v1` schema (verified audi_services.py:337); per-trip data model; image platform → user-supplied URL or removal. | #24, #35, #36 |
| **HACS Default + v2.0.0** | **v2.0.0** | MAJOR: Live tests all brands, compatibility matrix, EU Data Act ready (pycupra `EUDAConnection` ready to port). | #13, #59 |

### Out-of-band (no fixed version yet)

- **PPC/PPE Plattform Support** for Audi 2025+ (Q5, A5/S5, A6 e-tron,
  Q6 e-tron, RS e-tron GT Facelift) — depends on public reverse-engineering
  by audi_connect_ha or CC-audi. Currently graceful degradation only.
  See [`docs/AUDIT_2026-04-29.md`](AUDIT_2026-04-29.md) for status.
- **LEGACY_MBB Routing** for VW T6 Multivan 2016 (#76) — blocked on
  Tobias' diagnostic logs. No speculative implementation.
- **Skoda Kodiaq Mk2 `/v2/garage` 403** (#75) — likely
  `connectivityGenerations: ["MOD5"]` needed; `/v3/garage` does not exist
  (verified). Awaiting User diagnostics.

---

## Known live issues (waiting on user verification with v1.8.12)

| Issue | User | Brand / Model | Status |
|---|---|---|---|
| #54 | @GitHobi | Škoda | ✅ Should be fixed by v1.8.11 connection_state — **awaiting verification** |
| #53 | @Gerhard2808 | CUPRA Born | ✅ 5 fixes flowed in (v1.8.4, 1.8.8, 1.8.9, 1.8.10, 1.8.12) — **awaiting verification** |
| #42 | @migendi | CUPRA Formentor | ✅ Same fix bundle as #53 — **awaiting verification** |
| #51 | G.S. (Facebook) | Audi RS e-tron GT | ✅ pre-Facelift fixed by v1.8.5/8; Facelift via graceful degradation only |
| #74 | @marcogrewe | VW Passat 2025 (B9) | ✅ Set-value + main commands fixed by v1.8.5/8/12 — **awaiting verification** |
| #75 | (Kodiaq Mk2) | Škoda Kodiaq 2 (Mk2) | ⏳ `/v2/garage` 403, `/v3/garage` doesn't exist — needs diagnostic dump |
| #76 | @tobias-t6 | VW T6 Multivan 2016 | ⏳ awaiting Tobias' logs before any LEGACY_MBB routing |

---

## Hard rules ("learnings" — do not repeat the bugs)

1. **Never sign as AI assistant** — commits, comments, releases. Author lines and footers stay neutral.
2. **Bilingual user-facing text** — contributor's language first, translation below.
3. **README + 8 translations updated together** at every release.
4. **CHANGELOG entry per version** — CI fails the PR otherwise.
5. **VINs anonymised** — masked or example placeholders in code, docs, tests, fixtures. Same for userID and precise GPS.
6. **Car-friendly translations** — "Lichthupe", "Klimaanlage", "Zentralverriegelung" — drivers' language, not API jargon.
7. **Semver before bump** — patch = bug fix only, minor = new features, major = breaking change.
8. **Do not guess API behaviour** — verify against `pycupra` / `myskoda` / `audi_connect_ha` / `volkswagencarnet` references and add the URL to the commit body.
9. **Never expose tokens, S-PIN, account IDs, precise GPS** — in logs, diagnostics, fixtures, issue bodies.
10. **Capability-first** — new entities check `capabilities` before being created.
11. **404 ≠ auth-fail** — capability missing for newer models is the most common cause. Strict status-code discrimination.
12. **Wake the car only on explicit user request** — never auto-trigger from coordinator. Persistent counter, max 3/day.
13. **Aggregate in state, JSON in attributes** — HA state limit is 255 chars. JSON-blob states will be truncated and break dashboards.
14. **Stale-but-visible > unavailable** on transient backend errors. 6h cache window.
15. **Do not endpoint-guess for PPC/PPE** — wait for upstream (audi_connect_ha, acfischer42/CC-audi, tillsteinbach SeatCupra #49) before any blind requests against E³ 1.2 backends. Risks Audi account suspension.
16. **CI explicit-check before merge** — `gh pr checks <num>` must show 0 non-SUCCESS conclusions. Don't trust `--watch` exit codes alone (lesson from v1.8.9 ship-with-failing-test).
17. **Doc-only PRs without code change** — no manifest bump, but CHANGELOG.md change still triggers `changelog_check.yml` (since v1.8.12 workflow extension).
18. **User-data privacy by default** — see "User-Data Handling" section below. Even when a tester pastes their VIN/GPS/tokens publicly in an issue, do NOT pull them into the repo, fixtures, or maintainer comments unredacted. Anonymise first, ask for explicit fixture consent, document the source.
19. **`[Inference]` markers for unverified semantic claims** — when we choose a pragmatic implementation that passes server validation but isn't verified against official-app traffic, label it `[Inference]` in code comments + docstrings. The OLA `userPosition` field for SEAT/CUPRA honk-and-flash is the canonical example (vehicle position works, but whether the official My SEAT/My CUPRA app uses phone GPS is not verified).

---

## User-Data Handling (added after #53 third-party privacy review)

When a community tester (Facebook group, GitHub issue, forum) shares debug data, follow this hierarchy:

### What is OK to use

- ✅ **Diagnose im Issue-Thread** — read VIN, logs, screenshots to identify root cause, payload, endpoint, capability, entity behaviour
- ✅ **Code-Entscheidungen ableiten** — "CUPRA Born needs OLA payload + lowercase enum" is fine to deduce
- ✅ **Anonymisierte Fixtures** — only after redaction (see below) AND ideally with explicit user consent

### What is NOT OK

- ❌ Vollständige VIN in Repo / Fixtures / Docs / Commits / Comments
- ❌ Access-Tokens, Refresh-Tokens, JWTs, S-PIN
- ❌ User-ID / Account-ID
- ❌ E-Mail-Adresse
- ❌ Exakte GPS-Koordinaten (>1 Dezimalstelle)
- ❌ Heimat- / Parkadresse
- ❌ Kennzeichen
- ❌ Screenshots mit persönlichen Daten ungescrubbed
- ❌ Vollständige Rohlogs ohne Redaction

### Fixture redaction template

When converting a tester's payload into a regression fixture:

```json
{
  "brand": "cupra",
  "model": "born",
  "model_year": 2023,
  "region": "DE",
  "subscription": "active",
  "vin": "REDACTED_VIN_LAST6_e.g.012345",
  "userId": "REDACTED_UUID",
  "tokens": "REDACTED",
  "location": {
    "latitude": 48.0,
    "longitude": 11.0,
    "redacted": true,
    "note": "rounded to 1 decimal (~11 km bucket)"
  },
  "capabilities": {
    "honk_and_flash": "missing-capability",
    "wake": "missing-capability"
  }
}
```

Save under `tests/fixtures/{brand}/{model}_{year}_{situation}_redacted.json`.

### Asking for fixture consent

Use this template when proposing to convert a tester's data into a fixture:

```markdown
Danke {Name} — deine Logs/Screenshots helfen uns sehr.

Dürfen wir daraus eine vollständig anonymisierte Testfixture für {Brand} {Modell} erstellen?
Wir entfernen vorher: VIN, Tokens, Account-IDs, E-Mail, exakte GPS, sonstige persönliche Daten.

Die Fixture würde nur dazu dienen, künftige {Brand}-{Modell}-Regressionen automatisch zu testen — keine Weiterverwendung in Marketing oder anderen Kontexten.
```

### Maintainer self-check before commenting on a user issue

Before posting a diagnostic comment on a user-reported issue, verify:

1. **Diagnose-Hypothese vs. Fakten:** habe ich tatsächlich Beweise für meine Vermutung, oder ist das eine pauschale Annahme? (Beispiel-Fail: pre-1.11.1 wurde `subscription_expired` als generische 403-Erklärung gepostet, obwohl Gerhard's Vertrag aktiv war — siehe #53.)
2. **Verifiziert vs. spekulativ:** wenn ich eine Verhaltensbeschreibung mache ("die offizielle App macht es so"), habe ich App-Traffic captured? Sonst → `[Inference]` markieren oder weglassen.
3. **Daten-Hygiene:** zitiere ich VIN / Token / GPS aus dem Issue-Body? Falls ja → maskieren oder weglassen, auch wenn der User es selbst geschrieben hat.

### Why these rules

- HACS / HA Community: Vertrauen kommt von Privacy-by-default. Tester teilen mehr, wenn sie sehen dass mit ihren Daten sauber umgegangen wird.
- GitHub Issues sind public + permanent. Was du heute zitierst, ist auch in 5 Jahren noch indexiert.
- Hard Rule #8 (no speculation) gilt auch für User-Communication, nicht nur Code.

---

## Useful constants (do not hardcode in tests; import from code)

```python
# Auth
IDK_BASE      = "https://identity.vwgroup.io"
CARIAD_BFF    = "https://emea.bff.cariad.digital"
AZS_TOKEN_URL = "https://emea.bff.cariad.digital/login/v1/audi/token"
OLA_BASE      = "https://ola.prod.code.seat.cloud.vwgroup.com"
SKODA_BASE    = "https://mysmob.api.connect.skoda-auto.cz"
PORSCHE_PPA   = "https://api.ppa.porsche.com"

# CUPRA confidential client (OAuth requires client_secret, unlike SEAT)
CUPRA_SECRET  = "eb8814e6…"  # see cariad/models.py BRAND_CUPRA

# Audi vgql via AZS token (NOT IDK bearer)
AZS_APP_API   = "app-api.live-my.audi.com"

# Reverse geocoding (opt-in)
NOMINATIM     = "https://nominatim.openstreetmap.org/reverse"

# Session 3C — CUPRA OLA additional endpoints (verified in pycupra/connection.py)
OLA_USER_ME      = f"{OLA_BASE}/v1/users/me"                # → userID, cache once
OLA_MYCAR        = f"{OLA_BASE}/v5/users/{{user_id}}/vehicles/{{vin}}/mycar"
OLA_MILEAGE      = f"{OLA_BASE}/v1/vehicles/{{vin}}/mileage"
OLA_PARKING      = f"{OLA_BASE}/v1/vehicles/{{vin}}/parkingposition"

# Session 9 — Audi Trip Statistics (verified in audi_connect_ha/audi_services.py:337)
AUDI_TRIPSTATS = "{home_region}/api/bs/tripstatistics/v1/vehicles/{vin}/tripdata/{kind}"
# kind ∈ {"longTerm", "shortTerm"}  — "cyclic" in API spec but not used by audi_connect_ha

# Session 10 (#59 EU Data Act) — pycupra already has reference implementation
EUDA_BASE = "https://eu-data-act.drivesomethinggreater.com"
EUDA_RELATIONS = f"{EUDA_BASE}/proxy_api/vum/v2/users/me/relations/{{vin}}"
# See pycupra/eudaconnection.py — saves us reverse-engineering when EU Data Act lands Sep 2026

# Connection-state thresholds (v1.8.12 — universal across brands)
CONNECTION_ONLINE_THRESHOLD_S  = 1800   # < 30 min
CONNECTION_STANDBY_THRESHOLD_S = 86400  # < 24 h; older = "offline"
```

---

## Reference projects (clean-room, MIT/Apache-2.0)

For full attribution and "what to look up where" matrix, see
[`docs/RESEARCH_NOTES_2026-04-29.md`](RESEARCH_NOTES_2026-04-29.md)
section 4. Quick summary:

| Project | Status | Used for |
|---|---|---|
| `arjenvrh/audi_connect_ha` | active fork | AZS token exchange |
| `audiconnect/audi_connect_ha` | active | Trip statistics + audi_models.py reference |
| `robinostlund/homeassistant-volkswagencarnet` | active | VW EU patterns; EULA repair pattern; Service Discovery |
| `skodaconnect/myskoda` | active | mysmob endpoints; `carCapturedTimestamp` |
| `skodaconnect/homeassistant-myskoda` | active | Stale-cache UX, wake limits |
| `skodaconnect/homeassistant-skodaconnect` | **deprecated 2025-03** | Historical reference only |
| `WulfgarW/pycupra` | active | OLA endpoints, `EUDAConnection` (EU Data Act ready) |
| `WulfgarW/homeassistant-pycupra` | active | Live-test issue tracker |
| `CJNE/pyporscheconnectapi` | active | Porsche Auth0 + PPA |
| `matpoulin/CarConnectivity-connector-volkswagen-na` | active | VW US/CA |
| `mitch-dc/volkswagen_we_connect_id` | **archived 2025-10-29** | Historical issue forensics — we are the active successor |
| `tillsteinbach/CarConnectivity-*` | active | Multi-brand connector ecosystem direction |

---

## How to start the next session (recipe for a fresh AI / contributor)

1. Read this file (top to bottom, ~10 min)
2. Read [`docs/RESEARCH_NOTES_2026-04-29.md`](RESEARCH_NOTES_2026-04-29.md)
   sections 1, 2, 3, 6 (~20 min)
3. Pick a session from the "Sessioned roadmap" above
4. Verify the source(s) for that session in
   [`docs/RESEARCH_NOTES_2026-04-29.md`](RESEARCH_NOTES_2026-04-29.md)
   section 4
5. If anything is unclear or unverified: spawn a research agent against
   the relevant reference repo (recipe in `RESEARCH_NOTES` section 7)
6. Implement on a branch named `session/v1.8.X-name` from `main`
7. Add tests (target: 5-12 new per session)
8. CHANGELOG entry: human-friendly in `CHANGELOG.md`, full technical in
   `docs/CHANGELOG_TECHNICAL.md`
9. Manifest bump (only if code changed)
10. PR + watch CI explicitly (`gh pr checks <num>`, count non-SUCCESS)
11. Merge with `gh pr merge --merge --delete-branch` (don't squash —
    we keep individual commits for git-blame archaeology)
12. Tag the merge commit: `git tag v1.8.X $MERGE_SHA && git push origin v1.8.X`
13. After tag-push the release workflow auto-publishes; if needed:
    `gh release edit v1.8.X --draft=false --latest`
14. Update relevant open issues with "Fixed in v1.8.X — please verify"
15. Update this file's "Current state" + "Releases shipped today" + roadmap
