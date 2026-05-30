# Bruno-Workflow für vag-connect-ha

> **Audience:** Contributors who want to add a new endpoint, verify
> body shapes against live VAG APIs, or trace endpoint drift over time.
> **Tool:** [Bruno](https://www.usebruno.com/) — open-source Postman alternative,
> stores collections as plain-text `.bru` files (git-friendly).
> **CI:** `.github/workflows/bruno-validation.yml` runs structural
> validation + URL-drift check on every PR.

## Why Bruno?

When VAG (Audi/VW/Skoda/SEAT/CUPRA) ships an API change — new field,
renamed endpoint, new required header — our integration breaks
silently for days until a user reports a 404. Bruno collections are
**living documentation** that lets us:

1. **Pin** the verified request shape for every endpoint
2. **Detect drift** automatically (CI compares Python URLs vs `.bru` URLs)
3. **Onboard new contributors** without Python knowledge — they can
   add a `.bru` file and we generate the Python skeleton
4. **Cross-link** with upstream sources (`Timwun/Cupra-WeConnect-Bruno-Collection`)

## Repository layout

```
tests/bruno/
├── seat_cupra/                       # SEAT/CUPRA OLA endpoints
│   ├── bruno.json                    # collection metadata
│   ├── environments/
│   │   └── mock.bru                  # dummy VIN/token for CI parsing
│   ├── 01_GET_status.bru
│   ├── 02_GET_charging_status.bru
│   └── ...
├── skoda/                            # Skoda mysmob endpoints
└── cariad_bff/                       # Audi + VW EU CARIAD-BFF endpoints

scripts/
└── check_bruno_url_drift.py          # Python ↔ Bruno drift scanner

.github/workflows/
└── bruno-validation.yml              # CI: structure + drift gate
```

## File naming convention

`<seq>_<METHOD>_<short_name>.bru`

Examples:
- `01_GET_status.bru`
- `03_POST_climatisation_start.bru`
- `05_PUT_destination.bru`

Sequence number reflects logical order in user workflows (read-first,
then write). Method is uppercase HTTP verb. Name is `snake_case`,
maximum 30 chars.

## `.bru` file template

Copy this when adding a new endpoint:

```
meta {
  name: <Human-readable name shown in Bruno GUI>
  type: http
  seq: <next-available-sequence-number>
}

<get|post|put|patch|delete> {
  url: {{base_url}}<path-with-{{vin}}-placeholders>
  body: <none|json|text>
  auth: bearer
}

auth:bearer {
  token: {{access_token}}
}

headers {
  Accept: application/json
  Content-Type: application/json    # Only if body
  SecToken: {{sec_token}}            # Only if S-PIN-protected
}

body:json {
  { ...verbatim JSON body shape... }
}

docs {
  Brief explanation:
  - What the endpoint does
  - Which Python method calls it (cariad/api/<brand>.py:<method>)
  - Any quirks (case sensitivity, undocumented fields, brand-firmware
    dependencies)
  - Reference URL (myskoda PR / pycupra source / Bruno seq from Timwun)
}
```

## Adding a new endpoint — full workflow

1. **Write the `.bru` file first** (in `tests/bruno/<brand>/`)
2. **Capture or verify** the body shape (see "Capturing API traffic"
   below)
3. **Implement Python client method** in `cariad/api/<brand>.py`
4. **Run drift check locally:**
   ```bash
   python scripts/check_bruno_url_drift.py --brand seat_cupra
   ```
   Should report `✅ No drift` for the URL you just added.
5. **PR**: Bruno-validation workflow runs automatically.

## Capturing API traffic (advanced)

For new endpoints we don't have specs for, capture from the official
manufacturer mobile app:

### Setup (one-time)

1. **Android emulator** — BlueStacks / MEmu / Android Studio AVD
   (rooted with Magisk so SSL pinning bypass works)
2. **mitmproxy** — `pipx install mitmproxy`, run `mitmweb` on
   `localhost:8080`
3. **Install mitmproxy CA cert** on emulator
   (System certs via `MagiskTrustUserCerts` Magisk module)
4. **Frida + ssl-pinning bypass** for the manufacturer app
   (search GitHub for "frida ssl pinning bypass <android>")

### Capture session

1. Start `mitmweb` (proxy on 8080)
2. Configure emulator's WiFi to use proxy `<host>:8080`
3. Open MyCupra/MySeat/MyAudi/etc. app, perform actions you want to capture
4. mitmweb shows every HTTPS request decoded
5. Right-click a request → Export as cURL or HAR
6. Convert to `.bru` format using the template above
7. Add to `tests/bruno/<brand>/`

### Privacy note

**Always anonymize captured `.bru` files before committing:**
- Replace VIN with `{{vin}}` (env var)
- Replace user_id with `{{user_id}}`
- Replace tokens with `{{access_token}}`
- Round any captured GPS to 2 decimals
- Use the `mock.bru` environment for CI

Same anonymization rules as our `docs/research/` and `tests/fixtures/`
work (Hard Rule #18).

## CI behaviour

**`bruno-validation`** workflow runs on PRs that touch:
- `tests/bruno/**`
- `custom_components/vag_connect/cariad/api/**.py`
- `scripts/check_bruno_url_drift.py`
- The workflow itself

Two jobs:

1. **`validate-bruno-collections`** — installs `@usebruno/cli` and runs
   `bru run --env mock` to verify every `.bru` parses cleanly. **Does
   not hit live APIs** (mock token would 401 anyway). Failures only on
   syntax / template errors.
2. **`url-drift-check`** — runs `scripts/check_bruno_url_drift.py`
   against all 4 brand client modules. **Warn-only mode** initially
   (exit 0 even on drift). Will switch to `--strict` once we have full
   `.bru` coverage of every endpoint we use.

## Future: live API tests

Currently CI only validates **structure**, not **correctness against
live VAG backends**. Going live needs:

- Dedicated test account per brand (cost: ~€80–100 per brand per year)
- Test vehicle with active subscription (you have Audi S6 + Golf GTE,
  others need Brand Captain access)
- Quota budget (~1500 calls/day per brand)
- mitmproxy-style logging in CI for failed assertions

This is planned for v2.0.0+. For now, manual validation by Brand
Captains via local `bru run --env <real-account>`.

## Strategic context — why this matters

`vag-connect-ha` is the only HA integration that targets the **whole
VAG family** (Audi/VW/Skoda/SEAT/CUPRA/Porsche/VW NA). Other projects
focus on one brand. By maintaining authoritative `.bru` collections
for every brand, we become the **reference implementation +
documentation** for the entire VAG-HA ecosystem.

That's the v2.0.0 + EU Data Act (Sept 2026) play — see
`docs/HACS-CHECKLIST.md` "Outstanding" section.

## References

- [Bruno project](https://www.usebruno.com/)
- [@usebruno/cli on npm](https://www.npmjs.com/package/@usebruno/cli)
- [Timwun/Cupra-WeConnect-Bruno-Collection](https://github.com/Timwun/Cupra-WeConnect-Bruno-Collection) — the upstream reference our `seat_cupra` collection extends
- [_private/research-archive/cupra-bruno-endpoints-2026-05-02.md](research/cupra-bruno-endpoints-2026-05-02.md) — extracted catalog from Timwun's collection
- [_private/research-archive/cariad-charging-host-2026-05-02.md](research/cariad-charging-host-2026-05-02.md) — research for the 2nd Cariad host (charging stats)
