# Research Notes 2026-05-02 — Pre-Research für v1.13.0 / v1.14.0 / v1.15.0 Bundles

> Verfasst vor Implementation um Mid-Flight-Surprises zu vermeiden.
> Status pro Issue: ✅ verified / ⚠️ [Inference] / ❌ gap → defer.
> Quellen: Codebase + `docs/RESEARCH_NOTES_2026-04-29.md` + `docs/SESSION_HANDOFF.md` + `docs/AUDIT_2026-04-29.md` + `docs/ROADMAP.md` + Live-Issues via `gh issue view`.

**Konvention:**
- ✅ VERIFIED — eigener Parser/Command liest das Feld bereits, oder externe PR/Issue mit gepostetem JSON-Dump, oder eigene Fixture.
- ⚠️ [Inference] — Pattern aus einer Quelle bekannt, aber nicht live verifiziert; ODER analoges Brand-Pattern.
- ❌ GAP — kein verifizierter Pfad. Defer aus aktuellem Bundle.

---

## Bundle 1 — v1.13.0 Production Hardening

### #56 Phase 3 — Capability-Filter PRE-Entity-Creation

**Ist-Stand:**
- Coordinator hat `vehicle_capabilities` cache (24h TTL) + `vehicle_supports_capability(vin, capability_id) -> bool | None` mit konservativer Logik (None = "weiß nicht, nicht filtern").
- `cariad/api/vw_eu.py:115-125` und `cariad/api/seat_cupra.py:83-94` rufen die Capabilities-Endpoints ab. Audi via Inheritance VW EU. Skoda + Porsche + VW NA: kein Endpoint implementiert (Stub gibt leeres dict zurück).
- Phase 2 (#56) ist live: command-bound Entities setzen `_command_id` + werden nach erstem definitiven 4xx über `is_command_known_unsupported` auf `unavailable` gestellt.
- Phase 3 = Entities **gar nicht erst** registrieren wenn capability cache schon `False` zurückgibt → spart UI-Clutter.

**Verified sources:**
- ✅ Eigener Code: `coordinator.py:691-724` (`vehicle_supports_capability`), `coordinator.py:726-760` (`refresh_capabilities`).
- ✅ Capability-IDs verifiziert in production:
  - VW EU CARIAD: `honkAndFlash` (camelCase) — `cariad/api/vw_eu.py:120`.
  - SEAT/CUPRA OLA: `honk-and-flash` (kebab-case) — `cariad/api/seat_cupra.py:87`.
- ✅ Schema-Form verifiziert: SEAT/CUPRA `{capabilities: [{id, status: [...]}]}` mit `status=[]` = "fully usable" (CC-seatcupra #109 + RESEARCH_NOTES_2026-04-29 §3 Skoda capability section).
- ⚠️ Skoda: capability schema laut RESEARCH_NOTES_2026-04-29 §3 ist `{active, editable, user-enabled, status, license-issue, parameters}` — anderes Schema als VW EU/OLA. Skoda-Endpoint URL ist `/api/v1/vehicle-access/{vin}/capabilities` (Issue #56 body) — aber **noch nicht in unserem `cariad/api/skoda.py` implementiert**.

**Mapping Capability-ID ↔ Entity (zu pflegen):**

| HA-Entity | Command-ID | VW EU CARIAD cap-id | OLA cap-id | Skoda cap-id |
|---|---|---|---|---|
| `command_lock`/`command_unlock` | `command_lock` | `access` | `access` | `access` |
| `command_flash` | `command_flash` | `honkAndFlash` | `honk-and-flash` | `honk-and-flash` |
| `command_wake` | `command_wake` | `vehicleWakeUpTrigger` (⚠️ inference) | wake unbekannt | `vehicleWakeUpTrigger` |
| `climate_start`/`stop` | `command_start_climate` | `climatisation` | `climatisation` | `air-conditioning` |
| `charging_start`/`stop` | `command_start_charging` | `charging` | `charging` | `charging` |
| `command_window_heating_*` | `command_window_heating` | `windowHeating` (⚠️ inference) | `window-heating` (⚠️) | unbekannt |
| `set_target_soc` | `command_set_target_soc` | `chargingSettings` (⚠️) | `charging` | `charging` |
| `command_set_departure_timer` | `command_set_departure_timer` | `departureTimers` (⚠️) | `departure-timers` (⚠️) | `departure-timers` |

**Implementation plan (5 bullets):**
1. **Konservative Default-Logik** — Phase 3 deaktiviert eine Entity nur wenn `vehicle_supports_capability(vin, cap_id) is False` (also Cache populated UND cap fehlt/limited). Bei `None` wird Entity erzeugt (Phase 2 fängt das später ab). Verhindert false negatives wenn `refresh_capabilities` failed oder Brand keinen Endpoint hat.
2. **Setup-Hook** — Async-`setup_entry` jeder Plattform (button.py, switch.py, lock.py, climate.py, number.py) ruft `vehicle_supports_capability` vor `add_entities` und filtert. **Skoda darf nicht gefiltert werden** bis Skoda-Endpoint implementiert ist (sonst hidet alles).
3. **Capability-ID-Map** als Single-Source-of-Truth in `const.py` (oder neu `cariad/_capabilities.py`): pro Brand ein Dict `{command_id: cap_id_string}`. Brand-Lookup bekommt der Coordinator schon über `entry.data["brand"]`.
4. **Skoda-Capabilities-Endpoint zuerst implementieren** (sonst liefert Phase 3 für Skoda nur `None`-Returns). Endpoint laut Issue #56: `GET /api/v1/vehicle-access/{vin}/capabilities`. Schema: capability dicts mit `{id?, active?, editable?, user-enabled?, status?, license-issue?}` — `status` kann String, list[str] oder list[int] sein (RESEARCH_NOTES §3). Brauchen Anpassung von `vehicle_supports_capability` für `active` + `user-enabled` Felder (heute nur `status`). **TODO konfirmieren ob mysmob das Feld `id` setzt** — myskoda Quellcode-Lookup nötig.
5. **Tests** — Unit-Tests pro Plattform mit drei Capability-States (✅ aktiv, ❌ definitiv aus, ⚠️ unknown/None) → erwartete Entity-Counts. Plus: Test dass Phase 3 nicht hidet wenn Brand kein cap-endpoint hat.

**Risiken / Surprises:**
- Audi hat **keinen `devicePlatform`-Field** (RESEARCH_NOTES §3 + Hypothesis-Korrektur). Aber Capabilities-Endpoint existiert via VW EU Inheritance — die Capability-Liste IST die platform-discriminator.
- VW NA Capabilities-Schema unbekannt (`vw_na.py` hat Stub) → für US/CA-User keine Phase 3, fall-through auf Phase 2.
- Audi RS e-tron GT (#51) liefert ggf. Capabilities die mit alten Endpoint-Pfaden inkompatibel sind. Phase 3 darf NICHT ohne v1/v2-Fallback-Awareness verstecken.

**Confidence:** ⚠️ [Inference] für Skoda + VW NA (Schema-Detail), ✅ für VW EU + SEAT/CUPRA. Wird durchgeführt mit konservativem `None=keep`.

---

### #63 Phase 2 + Phase 3 — Command-Locking + cloud_refresh vs wake_vehicle

**Ist-Stand:**
- Phase 1 (read-only mode) ist seit v1.12.0 live: `coordinator.is_read_only()` + `CONF_READ_ONLY` Setting; Plattformen `button.py`, `lock.py`, `switch.py`, `number.py`, `climate.py` skippen Setup wenn `True`.
- `services.yaml` hat `wake_vehicle` (per-VIN, mit S-PIN-Awareness via base) + `refresh_vehicle` (alle Vehicles, no-VIN). Beide existieren. Aber:
  - `refresh_vehicle` macht `entry.runtime_data.async_request_refresh()` → das pollt **Server**, weckt Auto NICHT (Code: `__init__.py:185-188`).
  - `wake_vehicle` ruft `command_wake` (CARIAD `/vehicleWakeup`) → echter Auto-Wake.
  - **Trennung existiert also schon, aber schlecht dokumentiert.** Phase 3 Item ist eher Doku + ggf. Cooldown.
- Smart-Wake-Counter mit Soft-Cap 3/Tag ist seit v1.12.0 (#55) implementiert: `coordinator.py:1285-1340` + `_wake_counts` dict + `wake_count_today` sensor.

**Verified sources:**
- ✅ Eigener Code: `__init__.py:185-218` (Service-Registry), `services.yaml:1-108`, `coordinator.py:1285-1340` (smart-wake counter).
- ✅ MySkoda + Volkswagencarnet patterns für Command-Lock: nicht direkt verlinkt, aber Pattern ist generisch (asyncio.Lock per VIN per Command-Class).
- ⚠️ "5-min Cooldown auf wake_vehicle" — Issue-Text aus #63 Phase 3 ist vorgeschlagen, kein Reference-Repo dafür.

**Implementation plan (5 bullets):**
1. **Per-VIN-per-command-class Lock** — neu in `coordinator.py`: `self._command_locks: dict[tuple[str, str], asyncio.Lock]` mit Default-Timeout 30s (`asyncio.wait_for`). Jede `async_<command>`-Funktion wraps in `async with`.
2. **Entity-Side**: command-bound Entities prüfen via `coordinator.is_command_in_flight(vin, command)` und gehen visuell auf "transitioning" (= `available=True` aber Optimistic-State + busy hint). Optimistic-Update-Layer existiert seit v1.11.1 (3B-Part-3) → diese mit Lock kombinieren.
3. **Service-Split** — `wake_vehicle` bleibt wie ist (per-VIN explizit, mit Smart-Wake-Counter). NEU: `refresh_cloud_cache` als **Alias** für bestehendes `refresh_vehicle` (rename + Deprecation-Warning auf altem Namen). Beschreibungen in `services.yaml` klar trennen ("Cloud-Cache pull, weckt Auto NICHT" vs. "Sendet Wakeup-Befehl ans Auto").
4. **5-min Cooldown auf `wake_vehicle`** — letzte-wake Timestamp pro VIN (in-memory; nicht persistent — Restart darf wake erlauben). Repair-Notification wenn User vor Cooldown wieder triggert.
5. **Read-only Phase 2/3** — Command-Lock-Logic gilt ALSO im non-read-only-Fall. Read-Only-Phase-2 = sicherstellen dass die SERVICES selbst (nicht nur Entities) blockieren wenn `is_read_only()`. Heute: services können trotz read-only weiter aufgerufen werden! Fix: Service-Handler prüfen `_coord(vin).is_read_only()` und werfen `HomeAssistantError`.

**Risiken / Surprises:**
- Bei `wake_vehicle` greifen 3 Layer: Smart-Wake-Counter (v1.12.0), neue Per-VIN Cooldown (Phase 3), Command-Lock (Phase 2). Reihenfolge muss klar sein: erst read-only-check, dann Cooldown, dann Counter, dann Lock, dann API-Call. Tests müssen alle 4 Pfade abdecken.
- Service-Rename `refresh_vehicle` → `refresh_cloud_cache` ist semver-relevant. Vorschlag: BEIDE Namen aktiv für ein Release, alter Name mit Logger-Warning.

**Confidence:** ✅ — Alle Bausteine existieren; Phase 2/3 ist Glue + Naming + Cooldown.

---

### #62 Anonymized Diagnostics-Export

**Ist-Stand:**
- `diagnostics.py` (existiert!) macht bereits Redaction für: VIN (`mask_vin`), `latitude`, `longitude`, `address`, `parking_address`, `user_id`, `account_id`, `email`, plus Credentials (`CONF_PASSWORD`, `CONF_SPIN`, `CONF_USERNAME`).
- `cariad/_util.py:mask_vin` ist Single-Source-of-Truth (`WAUZZZ********` Schema).
- v1.9.0 Reporter-Pipeline (`_unexpected_keys.py` + `_error_reporter.py`) macht bereits Werte-Maskierung (`mask_value`) — siehe RESEARCH_NOTES_2026-04-29 + Roadmap-Eintrag v1.9.0.
- Eine Fixture existiert: `tests/fixtures/seat_cupra/cupra_born_2023_active_subscription_redacted.json` (Gerhard's Born, mit Consent, v1.12.1).

**Verified sources:**
- ✅ `diagnostics.py:1-92`, `cariad/_util.py:mask_vin`, `cariad/_error_reporter.py:serialise_for_diagnostics`.
- ✅ Redaction-Template in `docs/SESSION_HANDOFF.md` "User-Data Handling" Abschnitt (Hard Rule #18, post-#53 review).
- ✅ Reference-fixtures aus Reference-Repos (CC-seatcupra #109 Born, CC-skoda #50 Kodiaq, volkswagencarnet #921 ID.4) sind in RESEARCH_NOTES_2026-04-29 §3 dokumentiert (Schemas), aber NICHT als JSON committed (Privacy/Lizenz).

**Implementation plan (5 bullets):**
1. **Diagnostics-Service** — Issue verlangt explizite `vag_connect.export_diagnostics` Service (nicht nur HA-built-in download). Heute: HA's Built-in Diagnostics-Download nutzt schon unseren `async_get_config_entry_diagnostics`. Issue-Acceptance-Criteria deuten an dass das schon reicht — nur Doku in `CONTRIBUTING.md` "wie download und teilen" fehlt.
2. **Token-Redaction expandieren** — `_REDACT_KEYS` schließt aktuell `access_token`/`refresh_token`/`id_token` NICHT explizit ein. Sind die je in `entry.data` oder `entry.options`? Falls ja: zur Liste hinzufügen. Sind sonst nur in coordinator-internal cache (nicht in `vehicles` dict).
3. **Email-Maskierung** — heute: `email` → `**REDACTED**`. Issue-Vorschlag: `u***@***.com`. Trivialer Patch in `_scrub`.
4. **GPS-Rounding** statt Redaction — Issue verlangt entweder remove ODER round-to-1-decimal. Heute: removed komplett. Vorschlag: Option-Flag, default = remove (privacy-by-default).
5. **API-Tracing-Toggle** — neue Option `enable_api_tracing: bool = False` mit aggressiver Warning. Setzt LOGGER-Level für `cariad.api.*` auf DEBUG bei Setup. Repair-Issue nach 24h erinnern dass deaktiviert werden soll.
6. **Fixture-Tests** — convert Gerhard's Born-Fixture (v1.12.1 commit) in regression test. Plus 2 mehr Fixtures: anonymisierte Versionen aus #54 (GitHobi Skoda) + #51 (G.S. Audi RS e-tron GT) mit Consent. **WARNUNG**: ohne Consent NICHT committen — Hard Rule #18.

**Risiken / Surprises:**
- Issue #54 + #51 Tester sind NICHT (mehr) responsiv — kein Consent möglich. Fallback: Fixtures aus dem öffentlich gepostetem JSON in den Reference-Issues (CC-seatcupra #109, CC-skoda #50, volkswagencarnet #921) — die sind public + Tester wussten dass es public ist + werden via Reference-Link attribuiert. **Aber**: VINs in Reference-Issues sind nicht alle redacted. Wir müssen vor Commit RE-REDACT.
- v1.9.0 Reporter-Pipeline macht schon JSON-Maskierung in deren Buffer — das landet bereits gemaskt in `diagnostics`. Doppel-Maskierung egal (idempotent).

**Confidence:** ✅ — Alle Bausteine da, kleine Patches + Fixture-Erweiterung + Doku.

---

### #64 Process — Issue Forms + Brand Captains + CODEOWNERS

**Ist-Stand:**
- `.github/` Verzeichnis existiert. Ob ISSUE_TEMPLATE Forms drin sind: zu prüfen.
- Hard Rule #18 (User-Data) bereits in CONTRIBUTING.md + SESSION_HANDOFF (v1.12.1 PR #101).
- Brand-Captains-Liste: nur als Vorschlag in #64, nicht implementiert.
- CODEOWNERS: existiert nicht.

**Verified sources:**
- ✅ Issue-Body #64 listet alle Forms + Labels + CODEOWNERS-Skelett.
- ✅ ROADMAP.md hat Doc-PR-Eintrag in P1-Bucket schon vorgesehen ("v1.13.x doc").

**Implementation plan (5 bullets):**
1. `.github/ISSUE_TEMPLATE/{bug_vehicle,feature_request,brand_research,scout_report,error_report}.yaml` — 5 Forms wie im Issue + 2 die zum v1.9.0 Reporter passen.
2. `.github/CODEOWNERS` — `@its-me-prash` overall + per-File overrides für Brand-Captains sobald sie verfügbar (heute nur self).
3. `BRAND_CAPTAINS.md` (Root) — Tabelle mit Name / Brand / Modell / Was sie testen. Initial-State: leer + Aufruf in CONTRIBUTING.md.
4. **Labels in Repo-Settings via gh-CLI** (`gh label create`) — Skript dazu in `scripts/setup-labels.sh`, idempotent.
5. **Privacy-Guide bereits in CONTRIBUTING.md** (PR #101) — nur Cross-Linking auf Issue-Forms ergänzen.

**Risiken / Surprises:**
- Doc-only-PRs müssen `changelog_check.yml` triggern (siehe Hard Rule #17, v1.8.12 Patch). `paths`-Filter checken: ist `.github/**` schon drin? Falls nein: extend.

**Confidence:** ✅ — pure Doc/YAML Arbeit, kein API-Risiko.

---

## Bundle 2 — v1.14.0 Audi Feature Pack

### #24 + #35 — Verbrauchsdaten / Trip Stats / Ladehistorie LTS

**Ist-Stand:**
- VW EU/Audi Parser liest schon: `currentSOC_pct`, `targetSOC_pct`, `electric_range_km`, `combustion_range_km`, `total_range_km`, `currentFuelLevel_pct`, `chargePower_kW` (via v1.10.0 + v1.11.0 + v1.11.1 PHEV-Range-Triple).
- `models.py` hat ~80 Felder; KEIN `trip_*` Datamodel.
- KEIN `cariad/api/trip_stats.py` modul.
- `sensor.py` hat KEIN `state_class=TOTAL_INCREASING` Sensor für kWh — heute nur `currentSOC_pct` und Range-Sensoren.

**Verified sources:**
- ✅ Audi tripstatistics-Endpoint **verifiziert** in RESEARCH_NOTES_2026-04-29 §3 + AUDIT_2026-04-29 §4.3 + SESSION_HANDOFF "Useful constants":
  ```
  GET {homeRegion}/api/bs/tripstatistics/v1/vehicles/{vin}/tripdata/{kind}
      ?type=list&from=1970-01-01T00:00:00Z&to=<ISO_NOW>
  kind ∈ {"longTerm", "shortTerm"}
  ```
  Source: `upstream/audi_services.py:337` + `audi_connect_account.py:1007/1010`.
- ✅ Datamodel-Vorschlag: `TripStatistics(kind, start_mileage, end_mileage, distance_km, avg_consumption, recent_trips: list[Trip])`.
- ⚠️ **Skoda Trip-Stats Endpoint nicht verifiziert** in unseren notes. myskoda lib hat möglicherweise was, aber wir haben es nicht gegrepped. Issue #35 zitiert nur die Skoda-HA Issues #898 + #733 als Feature-Request (also user-side, nicht API-side).
- ⚠️ **VW EU + SEAT/CUPRA + Porsche Trip-Stats**: keine Endpoints in unseren Notes. CARIAD-BFF könnte gleichen `tripstatistics`-Endpoint haben (Audi nutzt CARIAD-BFF auch), aber unverifiziert.
- ✅ HA-state-255-char Anti-Pattern: Trip-list MUSS in `extra_state_attributes`, nicht state. Pattern aus audi #113.

**Implementation plan:**
1. **Audi-Only initial scope** — `cariad/api/trip_stats.py` neu, getriggert nur wenn `entry.data["brand"] == "audi"`. Andere Brands skippen ohne Error.
2. **Felder-Mapping**: `kind="shortTerm"` → letzter Trip + `last_trip_distance_km`/`last_trip_avg_consumption` Sensoren. `kind="longTerm"` → `lifetime_avg_consumption`/`lifetime_distance_km` Sensoren.
3. **LTS-Sensor** `total_charged_energy_kwh` (`state_class=TOTAL_INCREASING`) braucht entweder kontinuierliche Energie-Akkumulation aus `chargingStatus.value.chargedEnergy_kWh` (TBD ob das Feld existiert) ODER Akkustand-Delta × Capacity. **Letzteres ist [Inference]** und unzuverlässig — Akku-Capacity ist statisch nur auf Schätzbasis.
4. **Cache 1h** für Trip-Stats — ändern sich rarely, separater Polling-Cycle (nicht im Standard-Coordinator-Loop).
5. **Tests** mit Mock-Response in audi-services.py-Format (1-2 longTerm Trips + 1 shortTerm).

**Risiken / Surprises:**
- ❌ **Ladehistorie LTS Sensor (`sensor.{auto}_geladene_energie_kwh` mit TOTAL_INCREASING)** ist die schwierigste Komponente — kein verifizierter Quellfeld auf VW Group APIs für kumulierte Lade-Energie. Volkswagencarnet/myskoda zeigen `chargedRange` (km) NICHT `chargedEnergy` (kWh). Wir können ein `derived` Sensor bauen via `(targetSOC - startSOC) × battery_capacity_kWh / 100` aber das braucht Battery-Capacity-Lookup pro VIN — auch nicht verifiziert in API. **Empfehlung: Verbrauchs-Sensoren (#24) ✅ in v1.14.0, Ladehistorie LTS (#35) → defer auf v1.15.0+ pending API-Research für `chargedEnergy_kWh`**.
- VW EU/Audi `tripstatistics`-Endpoint ist verifiziert, aber Subscription-required (paid Audi connect). Capability-gate via Phase 3 (#56).

**Confidence:**
- #24 (Verbrauch / Trip Stats Audi): ✅ verified.
- #35 (Ladehistorie LTS): ❌ GAP — kein `chargedEnergy_kWh` Feld in unseren Quellen. **Defer.**

---

### #29 + #51 — PPC Climate Body für 2025 A3/Q5 + Audi RS e-tron GT 404

**Ist-Stand:**
- v1.8.5 `CommandProfile` Layer + v1/v2 Endpoint-Fallback ist live. v1.8.8 erweitert auf 6 Hauptkommandos. v1.9.1 erweitert auf `command_wake`. Audi RS e-tron GT pre-Facelift sollte **fixed** sein (gemäß Status-Update in #51 Comments).
- PPE/PPC Body-Shape-Conditional (für Q6 e-tron / A6 e-tron / RS e-tron GT Facelift) ist NICHT implementiert. RESEARCH_NOTES §3 + ROADMAP "Standalone enhancements" listet das als pending.
- `devicePlatform` Field fehlt im Audi vehicle-response (verified in audi_models.py grep).

**Verified sources:**
- ✅ PPE Climate Body Pattern aus upstream PR #644 + Issue #677:
  ```json
  {
    "climatisationWithoutExternalPower": true,
    "climatizationAtUnlock": false,
    "windowHeatingEnabled": true,
    "climatisationMode": "comfort",  // MANDATORY, NOT null
    "zoneFrontLeftEnabled": false,
    ...
    // targetTemperature + targetTemperatureUnit MUST BE OMITTED
  }
  ```
  Source: RESEARCH_NOTES_2026-04-29 §3 "Audi CARIAD-BFF — extras beyond VW EU".
- ✅ v1/v2-Fallback `_post_command` läuft seit v1.8.5 (cariad/api/base.py + vw_eu.py).
- ⚠️ **Detection für PPE/PPC**: upstream hat User-Side `api_level` (0/1) Toggle — fragile (Issue #677, #706 zeigen Cross-Vehicle-Probleme). Wir haben KEIN besseres Signal.
- ❌ Vollständige PPE-Endpoint-Map (z.B. lock/unlock body shape für PPE) ist NICHT public reverse-engineered — weder in upstream noch CarConnectivity noch evcc (RESEARCH_NOTES_2026-04-29 §1 "Strategic context").
- Hard Rule #15: "Do not endpoint-guess for PPC/PPE — wait for upstream — risks Audi account suspension."

**Implementation plan:**
1. **PPE Climate Body conditional** — heuristik via VIN-Pattern + `model_year >= 2024` + Engine-Type. Nur `climatisation_start` Body anpassen, nicht andere Commands. Fallback bei 4xx auf alten Body.
2. **VIN-basierte PPE-Liste** in `const.py` — initial: RS e-tron GT Facelift, Q6 e-tron, A6 e-tron, A3 2024+ PHEV. User-overridable via Option `force_ppe_climate: bool`.
3. **Capability-Check** — wenn Capabilities-Endpoint `climatisation` capability mit spezifischen `parameters` zurückgibt (z.B. `mandatoryFields: ["climatisationMode"]`), das als Discriminator nutzen. **TBD ob CARIAD-BFF Capabilities-Endpoint sowas liefert.**
4. **Repair-Issue** wenn PPE-Heuristik triggered aber 4xx → User informieren dass Modell zu neu ist.
5. **Test mit Mock**: `model_year=2025`, `model="Q6 e-tron"` → Body ohne targetTemperature; `model_year=2023`, `model="Q5"` → Body MIT targetTemperature.

**Risiken / Surprises:**
- ❌ Wir haben KEIN verifiziertes Signal für PPC-vs-MQB. VIN-Heuristik ist [Inference] — sicher falsch für edge cases.
- Hard Rule #15 verbietet endpoint-guessing. Body-shape-changes auf bekanntem Endpoint sind ABER okay (Server validiert Body, kein Account-Risk).
- Issue #51 Status-Update sagt "pre-Facelift sollte funktionieren". Wenn G.S. wieder respondsiv ist + sein RS e-tron GT pre-Facelift IMMER NOCH 404 macht → ist's eine andere Bug. → vor v1.14.0 Verify-Ping auf #51.

**Confidence:**
- #51 (RS e-tron GT pre-Facelift): ✅ — bereits gefixt durch v1.8.5/v1.8.8/v1.9.1. Issue kann zu nach Verify geschlossen werden.
- #51 (RS e-tron GT Facelift): ❌ GAP — graceful degradation only.
- #29 (PPC Climate für A3 2024+/Q5 2025): ⚠️ [Inference] Body-Shape-Conditional implementierbar, aber Detection ist fragil. **Empfehlung: implementieren, mit klarer Doc dass es Heuristik ist.**

---

### #28 — Remote Start ICE (upstream #717 zwei-Schritt-Pattern)

**Ist-Stand:**
- KEIN engine-start command in `cariad/api/*`. Issue #28 Comments verlinken klar auf upstream PR #717.

**Verified sources:**
- ✅ Two-Step Pattern aus upstream PR #717 (in RESEARCH_NOTES_2026-04-29 §3 + Issue #28 Comments):
  1. `PUT /engine/{VIN}/userpromptproof` mit S-PIN-Body → Response enthält `securedActivationData`.
  2. `POST /engine/{VIN}/start` mit `securedActivationData` aus Step 1.
- ✅ Pattern ist analogous zu unserem SecToken-Flow (v1.8.4) für SEAT/CUPRA Lock — zwei-Schritt mit Token-Exchange. Wir haben also Architektur-Erfahrung.
- ⚠️ Body-Shape von Step 1 (genaue Felder vom S-PIN Submit) nicht in unseren Notes dokumentiert — muss aus PR #717 Source extracted werden.
- ⚠️ Audi-only? Issue #28 Body sagt "Audi S6, RS-Modelle 2024+" + "modellabhängig". Inheritance (`AudiClient(VWEUClient)`) → automatisch verfügbar für alle VW EU Brands? **Nicht verifiziert** — Endpoint ist `/engine/...` (kein `/vehicle/v1/.../engine`) → wahrscheinlich Audi-spezifischer URL-Prefix.

**Implementation plan:**
1. **`AudiClient.command_engine_start(vin, spin)`** in `cariad/api/audi.py` (NICHT in vw_eu.py — Audi-spezifisch).
2. Step 1: `PUT` mit S-PIN. Response → extract `securedActivationData` (string).
3. Step 2: `POST /engine/{vin}/start` mit dem Token. Status-Code-Discrimination wie immer.
4. **Capability-gate**: `has_combustion = engineType.primaryEngineType in ("gasoline", "diesel", "hybrid")` + `command_engine_start` cap-id (TBD).
5. Service `vag_connect.engine_start` mit `vin` + `s_pin` (required, da S-PIN vom User kommt — nicht aus saved config). Doku-Warning dass S-PIN im Service-Call-Log landet.

**Risiken / Surprises:**
- S-PIN im Service-Call-Log: Privacy-Issue. Vorschlag: S-PIN aus saved entry-config (analog zu `unlock`), nicht im service-call.
- Endpoint-Pfad `/engine/...` vs. `/vehicle/v1/.../engine/...` ist nicht 100% klar aus den Notes — vor Implementation muss upstream PR #717 Source genau gelesen werden.
- ❌ **Live-Tester benötigt** für ICE-Audi 2024+ mit Engine-Start-Capability. Issue #28 Comment: "eigene Session sobald ICE-User-Tester verfügbar." Heute wahrscheinlich keiner verfügbar.

**Confidence:** ⚠️ [Inference] für Pattern (von einer Quelle bekannt, nicht live verifiziert in unserem Code). **Empfehlung: implementieren mit `[Inference]`-Markern + behind capability-gate. Live-Test kann nach Release passieren.**

---

## Bundle 3 — v1.15.0 Cross-Brand UX Pack

### #26 — Klimatisierungs-Timer / Abfahrtstimer UI

**Ist-Stand:**
- `command_set_departure_timer(vin, timer_id, enabled, departure_time)` ist live in `vw_eu.py:456-477`. Service `set_departure_timer` registriert in `__init__.py:212-218` + `services.yaml:148-178`.
- Parser liest `departureTimers.departureTimersStatus.value.timers` und setzt `departure_timer_{1,2,3}_enabled` + `departure_timer_{1,2,3}_time` Felder (`vw_eu.py:866-871`).
- KEINE dedizierten HA-Entities (datetime, switch) für die einzelnen Timer — User muss Service direkt aufrufen.

**Verified sources:**
- ✅ Eigener Code: alles oben.
- ✅ API-Pattern verifiziert: upstream #653 + volkswagencarnet #891 (Issue-Body #26).
- ⚠️ SEAT/CUPRA + Skoda departure-timer Endpoints — wahrscheinlich gleiches Pattern (CARIAD-BFF), aber nicht in unserem Parser für OLA/mysmob.

**Implementation plan:**
1. **`number.py` Erweiterung**: pro Timer (1-3) zwei Entities: `datetime.{auto}_abfahrtstimer_N` (`platform: datetime`, neue Plattform!) für Zeit + `switch.{auto}_abfahrtstimer_N_aktiv` für Enabled-Flag.
2. Brauchen NEW Plattform `datetime.py` — HA hat seit Core 2023.10 ein dediziertes datetime-Plattform (`SensorDeviceClass.TIMESTAMP` reicht für read-only nicht).
3. Set-Operation routet auf bestehenden `command_set_departure_timer`.
4. **Brand-Coverage**: VW EU (incl. Audi) ✅, SEAT/CUPRA + Skoda ⚠️ — separater Endpoint-Research nötig. **Initial scope: VW EU only**.
5. Tests: 3 Timer × 2 Entities × {enabled, time} kombinatorisch.

**Risiken / Surprises:**
- HA `datetime` platform ist relativ neu — Min-HA-Version-Bump ggf. nötig (manifest `homeassistant: 2023.10+`). Heute checken.
- `departureTime` Format ist `"HH:MM"` (ohne Datum) — HA `datetime` will full datetime. Konvertierung "heute + HH:MM" / "morgen + HH:MM" je nachdem ob Zeit schon vergangen ist.

**Confidence:** ✅ — Command + Parser existieren. Nur UI-Bindings + neue Plattform.

---

### #25 + #31 — Standort-spezifischer Ladeziel-SoC + Ladeprofile pro Standort

**Ist-Stand:**
- Wir lesen `targetSOC_pct` global (nicht standort-spezifisch). KEIN `chargingProfiles` Parsing in `vw_eu.py` (grep: nur `_unexpected_keys.py` Eintrag — also Scout hat das Feld gemeldet, aber Parser ignoriert es).
- KEIN `chargingLocation` oder `chargingProfile` field in `models.py:VehicleData`.

**Verified sources:**
- ⚠️ Issue #25: API-Pfad `charging/chargingSettings.value.targetSOC_pct` mit Standort-Awareness. Plus POST `/charging/settings` mit `chargingLocation`. **Body-Shape NICHT verifiziert** in unserem Code oder Reference-Repos in Notes.
- ⚠️ Issue #31: API-Pfad `charging/chargingProfiles` mit pro-Profil `targetSOC_pct`, `profileName`, `profileId`. Reference: ha-porscheconnect #319 — Porsche-spezifisch. Ob CARIAD-BFF gleiches Schema hat: ❌ unverifiziert.
- ✅ `chargingProfiles` ist in unserem `_unexpected_keys.py` Whitelist (v1.9.1 Scout-Pfade #91), also unsere Live-Vehicles SEHEN das Feld → es existiert. Aber Inhalt nicht in unseren Notes dokumentiert.

**Implementation plan (alleine #25):**
1. Read-side: parse `chargingProfiles[].targetSOC_pct` + `[].profileName` + `[].profileId`. Erkenne aktives Profil (`isActive=True` oder analog).
2. Sensor `aktives_ladeprofil` (string) + `ladziel_aktuell_pct` (überschreibt globalen targetSOC).
3. Write-side: HA `select` Plattform für Profil-Auswahl + `number` per Profil für targetSOC.
4. **Body-Shape muss aus echtem Vehicle live-dump extracted werden** — ohne Tester können wir nur Read implementieren, nicht Write.

**Risiken / Surprises:**
- ❌ **Body-Shape `POST /charging/settings` mit `chargingLocation`** ist GAP. Audi #722 Issue ist nur Feature-Request, kein verifiziertes Beispiel.
- ❌ `chargingProfiles[].profileId` Format unbekannt (UUID? int?). Verifying braucht Live-Dump.
- Scout könnte schon mehr Daten gesammelt haben — nach #91 Closure (v1.11.0) ist `chargingProfiles` kein "unexpected" mehr, also Scout hört auf zu reporten. Gewinn ist also negativ.

**Confidence:**
- #25 + #31 Read-Side: ⚠️ [Inference] — wir wissen das Feld existiert, kennen aber innere Schemas nicht. **Empfehlung: nur Read-Side in v1.15.0, Write-Side defer.**
- Write-Side: ❌ GAP. **Defer beide bis Live-Dump aus Scout-Reports verfügbar.**

---

### #33 — Diebstahl/Alarm Binary Sensor

**Ist-Stand:**
- KEIN `alarm_active` / `vehicle_alarm` Field in `models.py`.
- Issue-Body #33 behauptet: `access/accessStatus.value.{vehicleAlarm, siren}` mit Werten `ALARM`/`NO_ALARM` + `ACTIVE`/`INACTIVE`.

**Verified sources:**
- ❌ NICHT in RESEARCH_NOTES_2026-04-29 dokumentiert.
- ❌ NICHT in unserem `cariad/api/*` parser code.
- Issue #33 Reference: upstream/homeassistant-pycupra #44 — pycupra-Specific.
- ✅ ROADMAP.md hat schon Hinweis: "API-Endpoint research nötig — alarmStatus job in CARIAD selectivestatus? Feature-Discovery dann implementation."

**Implementation plan:**
- Vor Implementation: Scout-Pipeline erweitern um `access.accessStatus.value.vehicleAlarm` + `access.accessStatus.value.siren` als "expected" zu blacklisten und sehen ob in Live-Dumps auftaucht.
- Falls Field gesehen → Binary-Sensor parsing trivial (`vehicleAlarm == "ALARM"`).
- Falls Field NIE gesehen → das Feld ist Anti-Theft-feature-gated (paid Audi Connect Plus / Security & Service) → Capability-Gate.

**Risiken / Surprises:**
- Alarm-Events sind Edge-Case — die meisten Polls werden `NO_ALARM` zeigen. Test-Coverage schwierig ohne Live-Trigger.
- pycupra reference: möglicherweise OLA-spezifisches Schema, anderer Pfad als CARIAD-BFF.

**Confidence:** ❌ GAP — kein verifizierter Pfad. **Defer aus v1.15.0** bis ein Vehicle Data Scout-Report von einem Brand-Captain das Feld bestätigt. Add zu Scout-Whitelist als Vorbereitung.

---

### #36 — Navigation: Ziel ans Auto

**Ist-Stand:**
- KEIN `navigation` / `destination` / `send_destination` Code in `cariad/api/*`. Komplett neu.

**Verified sources:**
- ⚠️ Issue #36 Body: `POST /navigation/v1/vehicles/{vin}/destinations` mit `{latitude, longitude, poiName}`. Reference: skodaconnect/homeassistant-myskoda #684 — Skoda-spezifisch.
- ❌ Keine VW EU / Audi / SEAT/CUPRA Reference in unseren Notes.
- ❌ KEIN Endpoint-Capability in CARIAD-BFF Notes verifiziert.

**Implementation plan:**
- Skoda-only initial scope: implement `POST /api/v1/vehicle-navigation/{vin}/destinations` (myskoda lib path TBD, verify gegen myskoda source).
- Service `vag_connect.send_navigation_destination` mit `vin`, `latitude`, `longitude`, `name?`.
- Capability-gate: `navigation` cap-id.

**Risiken / Surprises:**
- ❌ Endpoint nicht in unseren Notes verifiziert. myskoda lib müsste gegrepped werden, das passiert NICHT in dieser Audit-Session.
- Multi-Brand-Coverage komplett offen — Audi nutzt vermutlich anderen myAudi-spezifischen Endpoint (vgql GraphQL?), VW EU vermutlich CARIAD-BFF aber Pfad unverifiziert.

**Confidence:** ❌ GAP — Endpoint nicht verifiziert. **Defer aus v1.15.0** bis myskoda lib gegrepped UND mindestens 1 Brand-Captain für Live-Test verfügbar.

---

## Recommendation per Bundle

### v1.13.0 (Production Hardening) — INCLUDED ITEMS

| # | Status | Note |
|---|---|---|
| #56 Phase 3 | ⚠️ [Inference] | Implementierbar mit konservativer Default-Logik (None=keep). Skoda-Endpoint zuerst implementieren. |
| #63 Phase 2 (Command-Lock) | ✅ | Per-VIN-Lock pure Engineering, kein API-Risk. |
| #63 Phase 3 (refresh vs wake) | ✅ | Trennung existiert, nur Doku + Service-Rename + 5min Cooldown. |
| #62 Diagnostics-Export | ✅ | Diagnostics + Reporter-Pipeline existieren. Nur Token-Redaction expand + Email-Mask + GPS-Round + Tracing-Toggle + 2 Fixtures. |
| #64 Process | ✅ | Pure Doc/YAML, kein Code-Risk. |

**v1.13.0 → ALLE 4 Items IN.** Zusätzlich Verify-Ping auf #51 vor Bundle-Start (klären ob noch open).

### v1.14.0 (Audi Feature Pack) — INCLUDED ITEMS

| # | Status | Note |
|---|---|---|
| #24 (Trip Stats Audi, Verbrauch) | ✅ | Endpoint verifiziert (audi_services.py:337). Audi-only initial. |
| #35 (Ladehistorie LTS) | ❌ GAP | `chargedEnergy_kWh` Feld nicht in unseren Quellen. Defer. |
| #29 (PPC Climate Body) | ⚠️ [Inference] | Body-Shape verifiziert (audi #644), Detection ist Heuristik. Mit `[Inference]`-Markern + Repair-Issue. |
| #51 (RS e-tron GT 404) | ✅ pre-Facelift fixed / ❌ Facelift GAP | Verify-Ping bestätigen, dann close. Facelift via graceful degradation. |
| #28 (Remote Start ICE) | ⚠️ [Inference] | Pattern aus audi #717 bekannt, Body-Detail braucht Source-Read. Behind capability-gate. Live-Test post-release. |

**v1.14.0 → IN: #24 (Verbrauch/Trip Stats), #29 (PPC Climate Body), #28 (Remote Start ICE). DEFER: #35 (Ladehistorie LTS), #51 Facelift.**

### v1.15.0 (Cross-Brand UX Pack) — INCLUDED ITEMS

| # | Status | Note |
|---|---|---|
| #26 (Klima-Timer UI) | ✅ | Command + Parser existieren. Neue HA `datetime` Plattform brauchen. VW EU only initial. |
| #25 (Standort Ladeziel-SoC) | ⚠️ [Inference] read-side / ❌ write-side GAP | Read-Side via Scout-Whitelist; Write-Side defer. |
| #31 (Ladeprofile pro Standort) | ⚠️ read / ❌ write GAP | Wie #25. |
| #33 (Diebstahl/Alarm Binary) | ❌ GAP | Field nicht verifiziert. Add zu Scout-Whitelist, Defer. |
| #36 (Navigation Ziel ans Auto) | ❌ GAP | Endpoint nicht verifiziert. myskoda lib grep + Tester nötig. Defer. |

**v1.15.0 → IN: #26 (Klima-Timer UI), #25/#31 read-side. DEFER: #25/#31 write-side, #33, #36.**

### DEFERRED (❌ GAP, needs separate research session)

| # | Reason | Next Step |
|---|---|---|
| #35 Ladehistorie LTS | `chargedEnergy_kWh` Feld nicht in Quellen | Audi/Skoda live-dump grep, evtl. derived sensor (battery-cap × delta-SoC) als [Inference] |
| #51 RS e-tron GT Facelift | PPE Endpoints nicht reverse-engineered (Hard Rule #15) | Wait on upstream / CC-audi upstream |
| #25 + #31 write-side | Body-Shape `POST /charging/settings` + `chargingProfiles` Schema unverifiziert | Live-Dump Scout-Report nötig (Audi/VW Brand-Captain) |
| #33 Alarm Binary | `access.accessStatus.value.vehicleAlarm` nicht verifiziert | Add zu Scout-Whitelist, abwarten |
| #36 Navigation | Endpoint-Pfad nicht verifiziert | myskoda lib grep + Brand-Captain Live-Test |

### Recommended sequencing changes vs. user proposal

- **#28 Remote Start ICE**: bleibt in v1.14.0 als ⚠️ aber **mit klarer Doku dass Live-Test post-release** (kein blocker, capability-gate verhindert false-positives).
- **#35 Ladehistorie LTS** aus v1.14.0 streichen → eigener "Charging Energy Tracking" Research-Spike.
- **#33 Alarm Binary** + **#36 Navigation** aus v1.15.0 streichen → beide Scout-Pipeline-First, dann eigener Sprint.

### Maintenance items vor Bundle-Start

1. **Verify-Pings auf #42 (CUPRA Formentor) + #48 (all-actions-fail) + #51 (Audi RS e-tron GT)** — wahrscheinlich gefixt durch v1.8.4/v1.8.5/v1.9.1/v1.10.2. Bestätigung sammeln, dann close.
2. **Scout-Whitelist erweitern** für `access.accessStatus.value.vehicleAlarm` + `chargingProfiles[].targetSOC_pct` — vorbereiten dass nächste Live-Dumps die Schema-Daten liefern für #33/#25/#31.
3. **Skoda Capabilities-Endpoint** in `cariad/api/skoda.py` implementieren — Voraussetzung für #56 Phase 3 auf Skoda-Brand. Sonst hidet Phase 3 nichts für Skoda-User.
