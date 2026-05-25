# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Cross-Brand App Atlas — discover what each VAG-brand Android app actually
talks to.

Background: every reverse-engineering project today is brand-siloed.
CarConnectivity has separate connectors per brand. PyCupra only knows
CUPRA. mitch-dc only knows VW EU. Nobody systematically checks
"does the Audi app talk to OLA?" or "did VW silently consolidate
backends?"

The App Atlas fills that gap. Daily CI workflow walks all 7 brand
apps, extracts HTTP-related strings + endpoints + headers from each,
and produces ``docs/research/app-atlas/{brand}.md`` reports. When
something changes (new version, new endpoints, header additions),
the pipeline auto-commits an updated atlas + flags potential
action-items.

Phase progression (build in stages, ship each as a separate PR):

- A.1: scaffolding + lightweight version-polling (no APK download)
       — confirms the pipeline scaffolding works for all 7 brands
- A.2: APK download + apktool extraction → string-pattern grep
       — definitive header / endpoint discovery
- A.3: jadx full decompile + cross-version diff reports
       — semantic-level change detection (new auth flows, etc.)

Phase B: act on discoveries — separate PRs as findings accumulate.

Legal: standard reverse-engineering for interoperability per EU
Software Directive Art. 6 and US DMCA §1201(f). No APKs hosted in
this repo; downloads are transient during CI runs.
"""
