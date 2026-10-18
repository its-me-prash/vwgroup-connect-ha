# Cross-Brand App Atlas — Legal Disclosure

## What this project does

The App Atlas is a continuous-integration workflow that:

1. Reads the public Google Play store listing of each of the eight
   publicly-distributed Volkswagen Group brand builds for its latest
   version-number. Google Play is the only source; the third-party
   APK mirrors this used to poll were removed on 2026-10-17
2. **(Phase A.2, live)** Downloads an APK from Google Play, as an
   ordinary store client would, into a temporary directory on a
   maintainer's machine
3. **(Phase A.2/A.3, live)** Extracts metadata + HTTP-related string
   constants (endpoint URLs, header names, public configuration
   values) using standard open-source tooling (`apktool`, `jadx`)
4. Documents the extracted information in human-readable Markdown
   files in [`docs/research/app-atlas/`](.)

## What this project does NOT do

- **No APKs are hosted in this repository.** An APK is downloaded into a
  temporary directory, read, and discarded when the run ends. Since
  2026-10-17 that run is a maintainer's local one rather than a CI job
  (see "Where this runs" below). No binary is committed; the findings
  cache it writes is local and git-ignored, and the only committed
  record is the extracted text on the atlas pages in this directory.
- **No decompiled source code is committed.** Only extracted factual
  information (URLs, header constants) appears in the atlas pages.
- **No user data is touched.** The atlas operates only on the
  publicly-distributed app binaries, not on any individual user's
  device, account, or vehicle data.
- **No user's credentials are involved, and no VW Group account is
  signed into.** Two clarifications, because the plain "no accounts, no
  tokens" this bullet used to claim is not precise enough to be useful:
  1. Downloading from Google Play needs a Play client identity, so the
     fetch uses an anonymous, disposable account from a public dispenser
     and passes the store's terms-acceptance flag. No person's Google
     account, and no brand account of any kind, is used or signed into.
  2. The grep over a decoded APK does look for authentication *config*
     constants that the app ships in its own binary — header names,
     token endpoint paths, OAuth client ids. Those are published
     constants inside a publicly-distributed app, which is the
     interoperability information this exercise is for; no credential
     belonging to a user or to Volkswagen Group is obtained, and
     anything resembling a secret is not republished.

## Where this runs

Version polling runs in a scheduled GitHub Actions job (eight public
Google Play listings, read anonymously). Phases A.2 and A.3 — the APK
download, the `apktool` decode and the `jadx` decompile — are run by a
maintainer locally, and only their extracted findings are committed.
They were moved out of CI on 2026-10-17 because the Play download needs
a disposable store account, and repeatedly signing such an account in
from a shared CI runner address gets it locked.

## Legal basis

Reverse engineering software for the purpose of achieving
interoperability with another program is explicitly permitted under:

- **European Union**: Software Directive 2009/24/EC, Article 6 —
  "decompilation for interoperability" exception
- **United States**: DMCA §1201(f) — interoperability exception to
  the anti-circumvention rules
- **Switzerland**: Copyright Act Art. 21 — reverse engineering for
  interoperability

The factual technical information extracted (URLs, header constants,
endpoint paths) is not subject to copyright protection per:

- **United States**: *Baker v. Selden* (101 U.S. 99, 1879) — facts
  and methods are not copyrightable
- **European Union**: Database Directive 96/9/EC Article 8 — lawful
  user's right to extract insubstantial parts of factual data

## Why VW Group hasn't published an official API

VW Group operates a partner-only API program (per gridio.io 2026-05
announcement). Independent developers and Home Assistant users who
own VW Group vehicles and want to integrate their cars with their
home-automation systems have no official path. This integration —
like 30+ similar community projects — exists because that gap is
real, the demand is real, and reverse engineering is the only
available remedy.

**VW Group is welcome to publish an official API.** If they do, we
will immediately migrate this integration to use it and retire the
reverse-engineering pipeline.

## Disclaimer

This integration and its associated tooling are not affiliated with,
endorsed by, sponsored by, or otherwise approved by Volkswagen AG,
SEAT S.A., Škoda Auto a.s., Audi AG, Porsche AG, or any of their
subsidiaries or affiliates. All trademarks are property of their
respective owners.

The integration is provided "as is" without warranty of any kind.
Users are responsible for ensuring their use of the integration
complies with their vehicle manufacturer's terms of service for
their own account.
