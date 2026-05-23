# Contributing to VW Group Connect

> Thanks for taking the time to look at the code. This integration is
> community-maintained and grows from the contributions of users who file
> good bug reports, share anonymised diagnostics and write small focused
> patches.

---

## Bug reports

Use the issue templates:
<https://github.com/its-me-prash/vwgroup-connect-ha/issues/new/choose>

A good bug report contains:

- VW Group Connect version (`manifest.json`)
- Home Assistant version
- Brand and rough vehicle model
- Country / region (some endpoints differ)
- Whether the same action works in the manufacturer's official app
- Whether the manufacturer's online services subscription is active
- Whether an S-PIN is configured
- Sanitised logs (filter `vag_connect` in HA logs)
- Anonymised diagnostics (download via Settings → Devices & Services →
  VW Group Connect → ⋮ → Diagnose herunterladen)

**Please remove tokens, full VINs, GPS coordinates, email addresses and
S-PIN values before pasting anything in a public issue.** Diagnostics
already redact these by default — if you paste a raw HA log, double-check.

---

## Privacy & data handling (added 2026-04-30 after #53 review)

This section is binding for **maintainers** and PR reviewers. Even when
a tester pastes their own VIN/GPS/tokens publicly in an issue body, the
maintainer-side rules below still apply.

### What goes in the repo / fixtures / commits

- ✅ Anonymised payload shapes — VIN replaced with placeholder, tokens
  removed, GPS rounded to 1 decimal (~11 km bucket)
- ✅ Issue / PR cross-references that name the contributor by
  GitHub handle (which is already public)
- ❌ Full VINs (17 chars), even from the tester's own car
- ❌ Access / refresh / id-tokens, S-PIN values
- ❌ User-IDs (UUIDs), account-IDs, email addresses
- ❌ Exact GPS coordinates (more than 1 decimal place)
- ❌ Home / parking address, license plates
- ❌ Screenshots with personal data, even if the tester posted them
- ❌ Raw HA logs without redaction

### Fixture redaction template

When converting a real-world payload into a regression fixture, save
under `tests/fixtures/{brand}/{model}_{year}_{situation}_redacted.json`
with this shape:

```json
{
  "brand": "cupra",
  "model": "born",
  "model_year": 2023,
  "region": "DE",
  "subscription": "active",
  "vin": "REDACTED_VIN",
  "userId": "REDACTED_UUID",
  "tokens": "REDACTED",
  "location": {
    "latitude": 48.0,
    "longitude": 11.0,
    "redacted": true,
    "note": "rounded to 1 decimal"
  }
}
```

### Asking a tester for fixture consent

```markdown
Danke {Name} — deine Logs/Screenshots helfen sehr.

Dürfen wir daraus eine vollständig anonymisierte Testfixture für
{Brand} {Modell} erstellen? Wir entfernen vorher: VIN, Tokens,
Account-IDs, E-Mail, exakte GPS, sonstige persönliche Daten.

Die Fixture würde nur dazu dienen, künftige Regressionen zu
verhindern — keine Weiterverwendung in Marketing oder anderen Kontexten.
```

### Self-check before posting on user issues

1. **Diagnose vs. Annahme:** habe ich Beweise oder rate ich? Pauschale
   "Abo abgelaufen" als generische 403-Antwort ist nicht OK wenn der
   Tester seinen aktiven Vertrag erwähnt hat.
2. **Verifiziert vs. spekulativ:** behauptungen über offizielle App-
   Verhalten brauchen captured-traffic-Beweise oder `[Inference]` Marker.
3. **Daten-Hygiene:** zitiere ich VIN/Token/GPS aus dem Issue? →
   maskieren oder weglassen, auch wenn der User es selbst gepostet hat.

### `[Inference]` marker für Code

Wenn ein Code-Pfad pragmatisch funktioniert (Server akzeptiert Payload,
Tests grün), aber semantische Korrektheit gegen offizielle App-Logik
nicht verifiziert ist, dokumentiere das im Docstring + Code-Comment:

```python
# ⚠️ [Inference] — semantische Interpretation NICHT verifiziert gegen
# official-app traffic. Pragmatischer Fix der Server-Validation
# besteht; ob das semantisch der App-Logik entspricht, ist offen.
```

Beispiel im Repo: `cariad/api/seat_cupra.py:command_flash` — der OLA-
Endpoint akzeptiert `userPosition = vehicle position`, aber wir wissen
nicht ob die offizielle My CUPRA-App das gleich oder über phone-GPS macht.

---

## FAQ — Subscription / Service Plus / paid plans (closes #47)

**Q: Do I need "Security & Service Plus" or another paid subscription for VW Group Connect to work?**

In **most countries: No.** VW Group Connect uses the same free API as the manufacturer apps (myAudi, WeConnect, MyŠkoda, MyCupra). If you can log in to the app, you can use VW Group Connect for vehicle status, GPS, door/window state, climate state.

**Some countries / some vehicles: certain commands are paywalled.** Confirmed examples:

- 🇵🇹 **Portugal** — lock/unlock, climate, charging require Security & Service Plus (Facebook user report)
- Some 2024+ premium Audi models — wake-up + advanced commands require an active "Audi connect plus" plan

This is a **VW Group server-side restriction** — the API itself rejects commands for accounts without the right plan. We cannot bypass it from integration side.

**Q: How do I tell if my command failure is "no subscription" vs "code bug" vs "vehicle missing capability"?**

Check the error body. Common patterns since v1.9.1 `classify_command_failure`:

| Error body content | Most likely cause | Action |
|---|---|---|
| `"missing-capability"` | Server says: *this VIN doesn't have this feature enabled* (region/trim/firmware) | Cannot fix in integration. Capability-Filter Phase 3 (v1.13.0) will hide the entity entirely. |
| `"subscription_expired"` / `"not_entitled"` | Paid plan expired | Renew plan in manufacturer portal. |
| `"spin_error"` with `spinState: "DEFINED"` | S-PIN required for this command | Configure S-PIN in integration options. |
| `"Bad Gateway"` / `"4007"` / `"4111"` | Backend transient error | Retry. v1.10.1 retry logic handles most of these. |
| `404 Not Found` | Endpoint doesn't exist for vehicle's API profile (PPC/PPE 2024+) | v1.8.5 v1→v2 fallback handles most; rest needs new code. |
| `403` no body / generic | Could be auth token expired, retry exceeded, or temp rate limit | Restart integration. |

**Q: My MyCupra/myAudi app shows the function works — why does VW Group Connect fail?**

Three independent reasons (#53 lesson):

1. **Different API profile** — the app may use a brand-specific newer endpoint that we don't know yet. Vehicle Data Scout (v1.9.0) helps catch this.
2. **Different payload shape** — same endpoint, but app sends fields we don't (e.g. `userPosition` for SEAT/CUPRA honk-and-flash, fixed in v1.10.2).
3. **Genuine `missing-capability`** — the app gracefully hides the button when the server says no. Our v1.9.1 Phase 2 marks the entity unavailable AFTER first failure; Phase 3 (v1.13.0) will hide it like the app does.

**Q: Where do I see if my account has an active subscription?**

In the manufacturer's web portal:
- 🇪🇺 myAudi → Profile → Connect Plus subscription
- 🇪🇺 WeConnect → My Account → Online services
- 🇪🇺 MyŠkoda → Account → Connected services
- 🇪🇺 MyCupra → Account → My services

Also confirmed by user-report on #53 (Gerhard, CUPRA Born) and others: the integration's diagnostic output shows the API response, which usually contains a hint about subscription state.

---

## Pull requests

```bash
git clone https://github.com/its-me-prash/vwgroup-connect-ha
cd vwgroup-connect-ha
pip install pytest pytest-asyncio pytest-cov ruff mypy aiohttp voluptuous homeassistant
python -m pytest tests/        # all green
python -m ruff check custom_components/
python -m mypy custom_components/vag_connect/ --ignore-missing-imports \
  --disallow-untyped-defs --disallow-incomplete-defs --warn-return-any
```

### Rules

- **One PR = one concern.** Atomic, reviewable. The session-based roadmap
  in [`docs/ROADMAP.md`](docs/ROADMAP.md) gives the broader plan.
- **Tests for new features.** A new sensor needs a parser test plus an
  entity test. A new command needs a coordinator dispatch test.
- **Lint clean** — `ruff check` returns 0.
- **CHANGELOG.md updated** — CI fails the PR otherwise.
- **No external runtime dependencies.** `manifest.json` requirements stay
  empty. We bundle our own CARIAD client.
- **No broken behaviour.** If you change a contract, update the matching
  test instead of disabling it.
- **No fake writable entities.** A switch must call a real API command
  or it must not exist.
- **Privacy first.** Anything that could send user data to a third party
  is opt-in and documented in [`PRIVACY.md`](PRIVACY.md).
- **Reference projects must be MIT or Apache-2.0.** GPL code may not be
  copied. See [`NOTICE.md`](NOTICE.md) for the current reference list.

### Commit messages

```
feat:     new feature              → Added in CHANGELOG
fix:      bug fix                  → Fixed
refactor: code restructuring        → Changed
docs:     documentation only
test:     tests
chore:    build / deps
ci:       GitHub Actions
i18n:     translations
```

The `changelog_check.yml` workflow rejects PRs that touch
`custom_components/` without a CHANGELOG entry.

### Translations

`strings.json` is the **English source of truth**. Mirror every change
into all 8 language files (`translations/{de,en,cs,es,fr,nl,pl,sv}.json`).
Use everyday driver vocabulary, not API jargon: e.g. *Lichthupe*, not
*Lichtsignal*.

---

## Adding a new brand

1. `cariad/api/{brand}.py` — API client, derive from `CariadBaseClient`
   or write a brand-specific class
2. `cariad/models.py` — add `BrandConfig` + `BRANDS` entry
3. `cariad/api/factory.py` — routing
4. `const.py` — `BRANDS` dict
5. `config_flow.py` — `_BRAND_OPTIONS`
6. `tests/test_cariad.py` — at minimum: factory routing, status parser
7. README feature table (mirror in all 8 languages)
8. `docs/research/VAG_GROUP_ECOSYSTEM.md` — add the brand to the map

**Capability-first:** the new client must implement a capability check
so commands the vehicle does not support are not exposed as entities.
See issue #56.

---

## Live testers wanted

Some brands are implemented but lack real-world verification:

| Brand | Status |
|---|---|
| Audi | Live tested (S6, multiple models) |
| VW EU | Live tested (ID series, Golf, Tiguan) |
| Škoda | Live tested (Octavia 2025) — see #54 |
| SEAT | Awaiting first real account |
| CUPRA | Live tested (Born — limited by subscription, see #53 #42) |
| Porsche | Implemented, **no live test** — `new_brand.yml` template |
| VW US/CA | Implemented, **no live test** — `new_brand.yml` template |

If you have a vehicle and want to help, open the
[`new_brand.yml`](https://github.com/its-me-prash/vwgroup-connect-ha/issues/new?template=new_brand.yml)
template.

---

## Code of conduct

Be civil. Be specific. Don't paste secrets. The maintainer is one person
on their own time — patches and patience travel further than demands.
