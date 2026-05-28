# App Atlas Phase A.5 — Auth-Config Shield

**Status:** Active (v2.5.5)
**Trigger that built this:** v2.5.4 emergency hotfix for the 2026-05-28 VW
Azure WAF migration ([#313](https://github.com/its-me-prash/vwgroup-connect-ha/issues/313)) —
the migration broke 100% of Audi + Volkswagen EU users for ~6 h until evcc /
volkswagencarnet / ioBroker.vw-connect / vag_connect (in that order)
shipped ports. The patterns mined here aim to catch the **next**
rotation before users see a single 403.

---

## What the shield does

A small, self-contained extension to the daily App Atlas APK extraction.
Adds an `auth_secrets` bucket to the per-brand findings JSON that
specifically targets the values VW has been rotating aggressively in
2026 — values that, when changed, break auth across every
reverse-engineered client at the same time:

| Pattern bucket | What it captures | Why it matters |
|---|---|---|
| `header_names` | `x-qmauth`, `x-platform`, `x-android-package-name`, `x-assertion`, `X-Client-ID`, `X-App-Version` | Header names that VW adds/removes from validation. Each rotation = days of debugging. |
| `token_path_markers` | `/auth/v1/idk/oidc/token`, `/login/v1/idk/token`, `/oidc/v1/token`, etc. | The actual REST path strings. Catches URL migrations (like the 2026-05-28 `/login/v1/…` → `/auth/v1/idk/oidc/…` flip). |
| `qmauth_constants` | `qmClientId`, `qmSecret`, `qmauth` | Smali variable names near the rotating HMAC seeds. |
| `qmauth_secret_candidates` | 64-character hex literals found near a `qmauth` constant | The actual HMAC secret bytes (32 raw → 64 hex). Diff-friendly: a rotation lights up as one literal swapped for another. |
| `client_id_candidates` | UUIDs ending in `@apps_vw-dilab_com` plus 8-char hex strings near qmClient definitions | The OAuth client_id rotations. |

---

## How it works

`scripts/app_atlas/apk_extractor.py:grep_patterns()` was widened with a
third loop after the `ola_headers` and `known_backend_hosts` passes.
Each pattern is searched with the same ripgrep/grep fallback used for
the existing buckets, so there is no new dependency.

Results land under `auth_secrets` inside the per-brand cache file:

```json
{
  "extracted_at": "2026-05-28T16:46:57Z",
  "headers": [...],
  "endpoint_hosts": [...],
  "auth_secrets": {
    "header_names_seen": ["x-qmauth", "x-platform", "x-android-package-name", "x-assertion"],
    "token_path_markers_seen": ["/auth/v1/idk/oidc/token"],
    "qmauth_constants_seen": ["qmauth"],
    "qmauth_secret_candidates": ["1ab69925ac179aaa4e83abe671a9476d176418b85bd706f1436ca15be647989c"],
    "client_id_candidates": ["01da27b0", "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com"]
  }
}
```

---

## What "shield" actually means

The daily App Atlas workflow already opens an auto-PR when brand
versions change. The auth-secrets bucket extends that PR diff so a
maintainer can see at-a-glance:

- Brand X's `qmauth_secret_candidates` changed — VW rotated the HMAC seed → emergency hotfix needed within hours
- Brand X's `token_path_markers_seen` flipped from `/login/v1/idk/token` → `/auth/v1/idk/oidc/token` → URL migration imminent
- Brand X gained a new header name (`x-something`) → upcoming WAF rule, prepare to add the header

This is purely a **detection** layer. The fix still needs to be coded
by hand — but the time-to-detection drops from "user opens issue with
HTTP 403 dump" to "morning CI PR shows the rotation".

---

## Caveats

1. **APK-extraction lag**: APK releases lag backend changes by 0–48 h.
   The 2026-05-28 WAF migration happened mid-morning and the matching
   Audi 5.5.0 APK was on APKMirror by the afternoon — within the day,
   but not in advance. The shield captures rotations as they appear on
   APKMirror; it does not predict them.

2. **APKCombo Cloudflare**: as of 2026-05-28 evening APKCombo returns
   HTTP 403 to GitHub Actions IPs, blocking the live extraction.
   APKMirror + Uptodown remain reachable for the version-polling path,
   but the actual APK download fallback chain needs another pass (see
   `_apk-extraction-bootstrap-2026-05-25.md` for the previous round).
   Until that's fixed, the shield runs locally on maintainer machines
   only; the daily workflow only catches version-number bumps.

3. **Obfuscation**: VW occasionally ships R8/ProGuard with stronger
   string obfuscation. When `qmauth_constants` returns zero matches but
   `header_names_seen` shows `x-qmauth`, the values are still in the APK
   but the smali variable names were stripped — fall back to grep for
   `64-char hex constants near "POST"` patterns.

---

## Cross-references

- [evcc PR #30277](https://github.com/evcc-io/evcc/pull/30277) — URL migration (Go, MIT, 2026-05-28T06:28Z)
- [evcc PR #30292](https://github.com/evcc-io/evcc/pull/30292) — qmauth rotation + assertion headers (Go, MIT, 2026-05-28T12:13Z)
- volkswagencarnet PR #331 (Python, MIT) — same URL migration
- TA2k/ioBroker.vw-connect commit 61496dc00 (Node, MIT)
- audi_connect_ha — uses OpenID-Discovery (`/login/v1/idk/openid-configuration`) instead of hardcoded URLs, which would have auto-followed the migration if the discovery endpoint itself hadn't also been WAF-walled
- `_v3.0-artifact-mining-plan.md` — predecessor doc that scoped Phases A.1–A.4

---

## Future: Phase A.6 ideas

- **Auto-build a defaults-rotation PR** when the daily atlas detects a
  changed `qmauth_secret_candidate` for a brand whose hardcoded value
  in `idk.py` no longer matches. Would close the loop from
  "rotation detected" to "fix proposed" without manual intervention.
- **Cross-verify against models.py client_id** as part of the daily
  check — if the APK shows a UUID@apps_vw-dilab_com that doesn't match
  our `BrandConfig.client_id` constant, flag in the PR body.
