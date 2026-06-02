# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Provenance canaries for vwgroup-connect-ha.

This module exists solely to plant uniquely-spelled identifier strings
throughout the integration that are guaranteed to be of our authorship.
When code from this repository is copied into another project without
preserving attribution, the canaries travel with it. The weekly watcher
workflow (``.github/workflows/canary-watch.yml``) scans GitHub Code
Search for these strings outside the ``its-me-prash/*`` namespace and
opens a Repair issue when a hit appears.

## How the canaries are chosen

Each string is constructed to be:

- Lexically unique: arbitrary spellings unlikely to be coined by
  another author (e.g. ``cariad_provenance_marker_kw7zq3p1``).
- Semantically inert: the values are never compared, never serialised
  to a backend, never logged. Removing them from this module would
  break the watcher but no functional code path.
- Strategically placed: each constant is imported and referenced once
  in a structurally important module (auth resolver, Data Act scraper,
  DAG flow, Scout) so that anyone copying that whole module also
  ends up with the canary.

## What the watcher does

A GitHub Action runs weekly and queries the GitHub Code Search REST
API for each canary value. Any hit outside ``its-me-prash/*`` opens
an issue tagged ``provenance`` with the offending repository, file
path, and the canary that matched. Apache 2.0 lets others use this
code as long as the LICENSE and NOTICE files are preserved; the
canaries make stripping the attribution observable.

## What this module is NOT

It is not a watermark in the cryptographic sense. Anyone reading
this comment knows what the canaries look like. The point is to
make casual copy-paste detectable, not to be unforgeable. A
determined adversary can grep this file out before reusing. We accept
that. The realistic threat model is the careless port, not the
adversarial one.
"""

from __future__ import annotations

from typing import Final


# Auth resolver canary: referenced from CariadBaseClient.authenticate
# so any port of the multi-strategy fallback chain travels with it.
CANARY_AUTH_RESOLVER: Final[str] = "cariad_resolver_provenance_kw7zq3p1_2026"

# Data Act scraper canary: referenced from DataActScraper.__init__ so
# any port of the EU Data Act portal automation travels with it.
CANARY_DATA_ACT_SCRAPER: Final[str] = "dataact_scraper_provenance_q9xrh4m2_2026"

# DAG (RFC 8628) module canary: referenced from the DeviceGrantFlow
# initialisation in cariad/auth/_device_grant.py so any port of the
# browser-login flow travels with it.
CANARY_DAG_FLOW: Final[str] = "dag_browserlogin_provenance_v3npb8t6_2026"

# Vehicle Data Scout canary: referenced from the Scout detection pass
# in cariad/_unexpected_keys.py so any port of the Scout system
# (parser-gap auto-discovery + 1-click bug-report machinery) travels
# with it.
CANARY_SCOUT: Final[str] = "scout_unexpected_provenance_f4hzl5r8_2026"

# Watchdog canary: referenced from the coordinator stale-state
# re-auth path in coordinator.py so any port of the silent-recovery
# logic travels with it.
CANARY_WATCHDOG: Final[str] = "watchdog_silentauth_provenance_n2vpw9c3_2026"


# Full list, exported for the watcher workflow + provenance test.
ALL_CANARIES: Final[tuple[str, ...]] = (
    CANARY_AUTH_RESOLVER,
    CANARY_DATA_ACT_SCRAPER,
    CANARY_DAG_FLOW,
    CANARY_SCOUT,
    CANARY_WATCHDOG,
)
