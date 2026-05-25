# Cross-Brand App Atlas — Legal Disclosure

## What this project does

The App Atlas is a continuous-integration workflow that:

1. Polls public Android app stores (APKMirror, APKPure) for the
   latest version-numbers of seven publicly-distributed Volkswagen
   Group brand apps
2. **(Phase A.2+, planned)** Downloads the APK files from those
   same public mirrors transiently during CI runs
3. **(Phase A.2+, planned)** Extracts metadata + HTTP-related string
   constants (endpoint URLs, header names, public configuration
   values) using standard open-source tooling (`apktool`, `jadx`)
4. Documents the extracted information in human-readable Markdown
   files in [`docs/research/app-atlas/`](.)

## What this project does NOT do

- **No APKs are hosted in this repository.** APK files are downloaded
  transiently during CI runs and discarded when the workflow ends.
- **No decompiled source code is committed.** Only extracted factual
  information (URLs, header constants) appears in the atlas pages.
- **No user data is touched.** The atlas operates only on the
  publicly-distributed app binaries, not on any individual user's
  device, account, or vehicle data.
- **No authentication credentials are involved.** No accounts are
  signed into, no tokens are extracted.

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
