# App Atlas — Cross-Brand Summary

> Auto-generated · Last refreshed: 2026-10-17 10:07 UTC

| Brand | Android package | Latest version | Source | Expected backend | OLA enforced? |
|---|---|---|---|---|---|
| **SEAT** | `com.seat.myseat.ola` | `2.23.0` | `google_play` | `ola` |  |
| **CUPRA** | `com.cupra.mycupra` | `2.23.0` | `google_play` | `ola` |  |
| **Volkswagen EU (We Connect ID)** | `com.volkswagen.weconnect` | `4.6.4` | `google_play` | `cariad_bff` |  |
| **Audi (myAudi)** | `de.myaudi.mobile.assistant` | `5.8.1` | `google_play` | `cariad_bff` |  |
| **Škoda (MyŠkoda)** | `cz.skodaauto.myskoda` | `8.17.0` | `google_play` | `mysmob` |  |
| **Volkswagen US/CA (myVW)** | `com.vw.carnet.release` | `2026.9.29-9674` | `google_play` | `con_veh_net` |  |
| **Porsche (My Porsche, North America)** | `com.porsche.one` | `21.26.39 (not re-confirmed)` | (retained from `apkmirror`) | `ppa` |  |
| **Porsche (My Porsche, rest-of-world)** | `de.porsche.one` | `21.26.39 (not re-confirmed)` | (retained from `apkcombo`) | `ppa` |  |

## Methodology

Daily CI workflow ([`.github/workflows/app-atlas-builder.yml`](
../../../.github/workflows/app-atlas-builder.yml)) reads the Google
Play listing of each VAG-brand Android app for its latest
version-name. Play is the only source: a mirror serves whatever it
last ingested, which can lag the store by weeks, so a brand Play
does not publish a version for is reported as a gap rather than
filled in from elsewhere.

That job polls versions and nothing else. The APK download and the
extraction on top of it (phases A.2 and A.3 below) are run by a
maintainer locally and only their findings are committed, because
the Play download needs a disposable store account and signing one
in repeatedly from a shared runner address gets it locked. So a
green daily run means the versions were checked, not that the APKs
were re-extracted; each page dates its own extraction record.

**Phase progression**:

- **A.1**: version-polling. Confirms which apps exist and tracks
  their version cadence. Runs daily in CI.
- **A.2**: APK download + string-pattern grep. Run locally.
- **A.3**: full decompile via jadx + constant diff. Run locally.

See per-brand pages in this directory for details.
