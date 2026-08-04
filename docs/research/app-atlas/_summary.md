# App Atlas — Cross-Brand Summary

> Auto-generated · Last refreshed: 2026-08-04 15:55 UTC

| Brand | Android package | Latest version | Source | Expected backend | OLA enforced? |
|---|---|---|---|---|---|
| **SEAT** | `com.seat.myseat.ola` | `2.20.2` | `google_play` | `ola` |  |
| **CUPRA** | `com.cupra.mycupra` | `2.20.3` | `google_play` | `ola` |  |
| **Volkswagen EU (We Connect ID)** | `com.volkswagen.weconnect` | `4.2.1` | `google_play` | `cariad_bff` |  |
| **Audi (myAudi)** | `de.myaudi.mobile.assistant` | `5.6.0` | `google_play` | `cariad_bff` |  |
| **Škoda (MyŠkoda)** | `cz.skodaauto.myskoda` | `8.14.0` | `uptodown` | `mysmob` |  |
| **Volkswagen US/CA (myVW)** | `com.vw.carnet.release` | `2026.7.28-9380` | `google_play` | `con_veh_net` |  |
| **Porsche (My Porsche)** | `com.porsche.one` | `20.26.31` | `apkmirror` | `ppa` |  |

## Methodology

Daily CI workflow ([`.github/workflows/app-atlas-builder.yml`](
../../../.github/workflows/app-atlas-builder.yml)) scrapes
APKMirror for the latest version of each VAG-brand Android app.
When a version changes (Phase A.2+), the workflow downloads the
APK, extracts it with apktool, and greps for known HTTP
patterns (OLA headers, backend URLs, etc).

**Phase progression**:

- **A.1 (current)**: version-polling only. Confirms which apps
  exist and tracks their version cadence.
- **A.2 (next)**: APK download + string-pattern grep.
- **A.3 (later)**: full decompile via jadx + cross-version
  semantic diff.

See per-brand pages in this directory for details.
