# App Atlas — Cross-Brand Summary

> Auto-generated · Last refreshed: 2026-09-17 08:58 UTC

| Brand | Android package | Latest version | Source | Expected backend | OLA enforced? |
|---|---|---|---|---|---|
| **SEAT** | `com.seat.myseat.ola` | `2.22.1` | `google_play` | `ola` |  |
| **CUPRA** | `com.cupra.mycupra` | `2.22.1` | `google_play` | `ola` |  |
| **Volkswagen EU (We Connect ID)** | `com.volkswagen.weconnect` | `4.3.2` | `google_play` | `cariad_bff` |  |
| **Audi (myAudi)** | `de.myaudi.mobile.assistant` | `5.7.0` | `google_play` | `cariad_bff` |  |
| **Škoda (MyŠkoda)** | `cz.skodaauto.myskoda` | `8.16.0` | `google_play` | `mysmob` |  |
| **Volkswagen US/CA (myVW)** | `com.vw.carnet.release` | `2026.7.28-9380` | `google_play` | `con_veh_net` |  |
| **Porsche (My Porsche, North America)** | `com.porsche.one` | `20.26.37` | `apkmirror` | `ppa` |  |
| **Porsche (My Porsche, rest-of-world)** | `de.porsche.one` | `20.26.37` | `apkcombo` | `ppa` |  |

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
