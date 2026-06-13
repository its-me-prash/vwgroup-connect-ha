# App Atlas — Cross-Brand Summary

> Auto-generated · Last refreshed: 2026-06-13 07:38 UTC

| Brand | Android package | Latest version | Source | Expected backend | OLA enforced? |
|---|---|---|---|---|---|
| **SEAT** | `com.seat.myseat.ola` | `2.17.0` | `uptodown` | `ola` |  |
| **CUPRA** | `com.cupra.mycupra` | `2.18.0` | `uptodown` | `ola` |  |
| **Volkswagen EU (We Connect ID)** | `com.volkswagen.weconnect` | `(fetch failed)` | `—` | `cariad_bff` |  |
| **Audi (myAudi)** | `de.myaudi.mobile.assistant` | `5.5.1` | `apkmirror` | `cariad_bff` |  |
| **Škoda (MyŠkoda)** | `cz.skodaauto.myskoda` | `8.13.0` | `uptodown` | `mysmob` |  |
| **Volkswagen US/CA (myVW)** | `com.vw.carnet.release` | `2026.5.27-9076` | `apkmirror` | `con_veh_net` |  |
| **Porsche (My Porsche)** | `com.porsche.one` | `12.24.27` | `apkmirror` | `ppa` |  |

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
