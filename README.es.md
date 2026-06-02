<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Integración de Home Assistant para Audi · VW · Škoda · SEAT · CUPRA</strong>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?style=for-the-badge"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&style=for-the-badge&label=CI" alt="CI"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/downloads/its-me-prash/vwgroup-connect-ha/total?style=for-the-badge&label=Downloads" alt="Downloads"></a>
  <a href="../custom_components/vag_connect/quality_scale.yaml"><img src="https://img.shields.io/badge/Quality%20Scale-Platinum%20%F0%9F%8F%86-gold?style=for-the-badge"></a>
</p>

<p align="center">
  <a href="../README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Previously published as **`vag-connect-ha`** (VAG = Volkswagen AG, standard DACH abbreviation).
> Turns out that abbreviation reads *quite* differently to English speakers 😅
>
> **What keeps working as before**: all entities (e.g. `sensor.audi_q4_battery_soc`),
> all service-calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), all automations,
> the HACS install — **nothing breaks**. Marketing/display name changes, code internals
> stay unchanged. See [`MIGRATION.md`](MIGRATION.md).
>
> Huge thanks to the **Home Assistant UK** and **HA Ideas, Projects and Solutions**
> communities for the heads-up — especially **Si Gregory**, **Ben Johnson**, and **Evets David**.
>
> And a special shoutout to **Jordan Waeles**, whose `show_vag()` comment is now an officially
> supported easter egg in this integration (`vag_connect.show_vag` service, see CHANGELOG v2.2.3).

---


## Novedades en v2.10.0

El release más grande de esta integración hasta la fecha. Unas 6 semanas de trabajo intensivo en un solo cut.

- **Fix login VW EU Auth0 SPA (#388)**: VW migró la página de password a una plantilla full-SPA hacia 2026-05-31. Retry JSON Content-Type sobre `/u/login` más detección de consent endurecida desbloquea a usuarios en classic-auth.
- **Paridad parser cross-brand**: VW EU Group A (10 campos nuevos - 12V, ventilación activa, techo solar trasero, capota, totales por viaje), SEAT/CUPRA Group B (6 endpoints OLA - warning-lights v3, battery-care configurable, estadísticas de carga, taller preferido), VW NA Group C (4 endpoints - migración `data.exteriorStatus.*`, arregla el síntoma "todo en null" del ID.4 US 2023 #322).
- **Detección de bloqueo de cuenta VW** con issue Repairs guiada + auto-clear.
- **Aplicación de la Scout Policy**: cada ruta JSON silenced debe también parsearse a una entidad, o llevar una exención T2-T5 explícita. Cierra #384, #389.
- **Canaries de procedencia + watcher semanal** + hardening (SPDX, drift-gate Bruno, mypy strict).

El resto de v2.7-v2.9 sigue activo: Browser-Login DAG, multi-strategy auth, Data Act Portal, MFA, push FCM, Standheizung, brake-service, parser telemetry.

Ver el [CHANGELOG](CHANGELOG.md#2100---2026-06-02) completo.

## Novedades en v2.7.x

**Inicio de sesión por navegador (sin contraseña en HA) para Audi, Škoda, SEAT, CUPRA.** OAuth Device Authorization Grant RFC 8628. Escanea un código QR con el móvil o abre la URL en cualquier dispositivo, confirma un código corto, hecho. refresh_token real, sin re-login cada dos horas.

**Resolutor multi-estrategia de auth.** Hasta tres estrategias de respaldo por marca (Browser-Login, OIDC Hybrid Flow, EU Data Act Portal solo lectura). Una estrategia muere, la integración sigue con la siguiente.

**Data Act Portal como respaldo solo lectura.** Implementación propia del login del portal EU Data Act, integrada como estrategia de 3er nivel. Solo lectura pero sin attestation, así que irrompible cuando VW endurece la ruta OAuth.

**Muchos más datos.** Estadísticas de viaje (distancia de por vida, último viaje), nivel de aceite, presión por neumático, puertas / ventanas / techo / maletero por posición, temperatura exterior en MY24+, calefacción auxiliar Webasto, todas las alertas del fabricante incluso las específicas como Audi STO.

Ver [CHANGELOG](CHANGELOG.md#270---2026-05-31).

---

## Donde lideramos

Estado al 2026-05-31, tras el cambio del backend VW del 2026-05-27 que golpeó a toda la comunidad de integraciones HA-VAG a la vez:

| Funcionalidad | Estado aquí | Estado en otros |
|---|---|---|
| OAuth Device Authorization Grant (QR-Login) para Audi/Škoda/SEAT/CUPRA | ✅ desde v2.7.0 | Nadie |
| Cadena multi-estrategia (3 niveles por marca) | ✅ desde v2.6.0 | Nadie |
| Portal EU Data Act como 3er nivel solo lectura | ✅ desde v2.6.0 | Solo como integración separada |
| Red de seguridad InvalidURL contra fuga de tokens | ✅ desde v2.7.2 | Nadie |
| Watcher del gate de attestation server-side | ✅ desde v2.7.0 | Nadie |
| Vehicle Data Scout, detección automática de drift de API | ✅ desde v1.9.0 | Nada equivalente |
| Las 7 marcas VAG en una integración | ✅ | Otros proyectos tienen un repo por marca |

---

## Donde están los límites (con honestidad)

**VW EU está duramente bloqueado por Play Integrity desde el 2026-05-27.** Este muro afecta a toda integración VAG basada en Python (la nuestra incluida). No es un retraso por nuestra parte, es la política backend de VW:

- El endpoint del token valida una cabecera `X-Assertion` que debe ser un JWS firmado por Google Play Integrity
- Python no puede generar este token, la clave de firma vive solo en el servicio de attestation de Google
- Consecuencia: los usuarios VW EU no obtienen un refresh_token real y son forzados a reloguearse cada ~2h

Lo que ofrecemos para VW EU: OIDC Hybrid Flow como estrategia primaria (lectura + escritura, 2h re-login), portal EU Data Act como respaldo solo lectura (cadencia 15 min, sin attestation), watcher semanal que abre automáticamente un issue cuando VW abre la puerta.

**Fecha límite EU Data Act 2026-09-12.** Para esa fecha, VW debe legalmente proveer acceso directo a los datos del vehículo a los propietarios sin attestation. Nuestro `_data_act_portal.py` está listo para ese día.

## ✨ v2.0.0 Big-Bang Highlights — also available in English

> The detailed v2.0.0 highlights table + "What makes us unique" USP section
> are maintained in English on the German + English READMEs. They are
> provided here as the canonical source so non-DE/EN readers can still
> see all v2.0 features with `` markers without waiting on
> 6 parallel translations.

### Latest highlights — v2.0.0 Big-Bang

| Feature | Status |
|---|---|
| **Skoda Driving-Score Sensor** | Efficiency score 0-100 + class bucket for Skoda MY24+ |
| **Cross-brand Aux-Heating parity (Skoda)** | SkodaClient now inherits the Webasto switch from SEAT/CUPRA |
| **Porsche TPMS sensors** | 4 tire-pressure sensors + warning binary_sensor (PPA TIRE_PRESSURE) |
| **Long-Term Trip Aggregates** | Lifetime distance / avg fuel / avg electric (Audi + VW EU) |
| **Departure-Timer Read-Only Binary-Sensors** | 3 pure-read enabled-sensors |
| **Weekly Preheat (`recurring_on`)** | Service param for weekday lists (Audi + VW EU + VW NA) |
| **Charging-Station POI Lookup** | `vag_connect.find_charging_stations` service |
| **Vehicle Alarm sensors** | closes issue #33 |
| **heaterSource sensor** | closes issue #163 |
| **Push Manager Lifecycle Wiring** | Skoda MQTT + CUPRA/SEAT FCM + Audi/VW Cariad FCM (opt-in) |
| **EU Data Act Abstraction Shim** | Architectural seam for the 2026-09-12 EUDA Art. 3 deadline |
| **Auth Resilience One-Click Repair** | Repair button for 4 auth reasons triggers reauth flow |
| **System Health Panel** | Drop-in `system_health.py` |
| **Quality Scale Platinum** | Re-introduced after v1.26.x revert |
| **DeviceInfo `configuration_url` + `suggested_area`** | Brand-aware "Open in App" button |

### What makes us unique

- **Native coverage of all 7 VAG brands** in a single integration
- **Direct manufacturer-API access** without middleware / Docker / 3rd service
- **Vehicle Data Scout** — automatic JSON-field drift detection with Repair notification + 1-click GitHub issue
- **Capability-Filter Phase 3** — phantom entities suppressed before spawn
- **Per-VIN wakeup cap + cooldown** — protects 12V battery
- **Auth Resilience One-Click Repair** — reauth flow from Repairs panel
- **System Health Panel** — at-a-glance push channel status, API quota, last poll
- **Bruno-CI Stage 2** — strict URL-drift check
- **Token persistence across HA updates** — no re-login after HACS updates since v1.19.2
- **Diagnostics anonymisation by default** — VINs, GPS, tokens stripped before export


Quería controlar mi Audi en Home Assistant — completamente. Así que construí esto.

**VW Group Connect** es una integración autónoma de Home Assistant para todas las marcas VAG. Sin dependencias externas, sin Docker, sin servicios externos.

Desde v0.14.1, la integración habla **directamente** con la API CARIAD — cliente async propio, completamente autónomo. Arquitectura cloud-polling, 80+ entidades en 10 plataformas, 14 servicios.

> ✅ **Sucesor multi-marca mantenido activamente** de [`mitch-dc/volkswagen_we_connect_id`](https://github.com/mitch-dc/volkswagen_we_connect_id) (archivado el 2025-10-29) y [`skodaconnect/homeassistant-skodaconnect`](https://github.com/skodaconnect/homeassistant-skodaconnect) (obsoleto el 2025-03-14). Una integración para Audi, VW, Škoda, SEAT, CUPRA, Porsche y VW US/CA — sin plugin separado por marca.

## Estado actual y límites honestos / Current Status & Honest Limits (v1.12.3)

VW Group Connect se desarrolla activamente. Para que sepas qué funciona y qué viene:

### ✅ Qué funciona AHORA (todas las 7 marcas)

**🛰️ Bug-Reports y solicitudes de features en 1 clic (LIVE desde v1.9.0)**

Dos sensores de diagnóstico con una pipeline reporter compartida — **primera validación live real por usuarios de la comunidad** en v1.10.2 (Gerhard / CUPRA Born), v1.12.2 (tritanium73 / Skoda) y v1.12.3 (DnnsJp74 / Audi):

- 🔬 **Vehicle Data Scout** — detecta automáticamente campos JSON desconocidos en la API de tu coche. Localizado por marca en 8 idiomas (DE: API-Beobachter, FR: Observateur d'API, etc.).
- 🚨 **Error Reporter** — Ring-buffer de los últimos 20 errores de integración con contexto anonimizado (modelo, firmware, stack trace).
- 🔘 **Reporter Pipeline:** ambos sensores crean automáticamente notificaciones HA Repair con un GitHub-Issue prerellenado como enlace de 1 clic. Más una descarga de diagnostics con todo enmascarado para foro/Facebook.
- 🔒 **Promesa de privacidad:** Nada sale de tu HA sin tu clic explícito. VINs enmascarados, GPS redondeado a 1 decimal, JWTs/UUIDs/emails eliminados. Cumple GDPR.

**🟢🟡⚫ Multi-Brand Connection-State (v1.8.12)**

Sensor `connection_state` (online / standby / offline) para Audi, VW EU, Škoda, SEAT, CUPRA — primera integración VAG con estado de conexión centralizado. Helper agnóstico de marca `compute_connection_state` con recorrido recursivo `carCapturedTimestamp`.

**🔋 Monitorización batería 12V + Smart-Wake (v1.12.0)**

- Sensor `voltage_12v` (V) + binary `warning_12v_low` por debajo de 11.5V — evita caídas silenciosas de la API por batería de arranque vacía
- Sensor `wake_count_today` + soft-cap a 3 wakes/día (`_WAKE_BUDGET_PER_DAY`) protege la 12V de wake-loops, lanza `wake_budget_exhausted` ANTES de la llamada API

**💨 UI optimista para Lock/Climate/Charging (v1.11.1)**

Los switches cambian inmediatamente al hacer clic (patrón myskoda PR #832), roundtrip API en segundo plano. En caso de fallo: revert + ServiceValidationError. 8 métodos actuator migrados.

**🔋 PHEV-Range-Triple (v1.10.0 + #94 + #96 follow-up en v1.11.1)**

Tres sensores de autonomía explícitos: `electric_range_km`, `combustion_range_km`, `total_range_km`. El parser VW EU/Audi clasifica por tipo de motor (4 fuentes en lugar de 2). Fallback Audi diésel desde `measurements.rangeStatus.value.dieselRange`. Verificado vía evcc-io/evcc#19045 + sample Audi Q4 + logs CarConnectivity.

**🔒 Modo Read-only Fase 1 (v1.12.0)**

Toggle de opciones "Read-only Mode" → omite plataformas lock/switch/button(non-refresh)/climate/number para propietarios conservadores con privacidad/seguridad. Sensors + binary_sensors + device_tracker permanecen.

**⚡ Number Max-Charge-Current escribible (v1.12.0)**

Slider 6-32A en lugar de un sensor solo de lectura. Nuevo `command_set_max_charge_current` POST chargingSettings.

**💡 Binary-Sensors por luz (v1.12.0)**

Dinámicamente por tipo de luz desde el dict `lights_individual` + agregados `lights_on` + `lights_count`.

**🛠️ Estabilidad defensiva (v1.8.7 + v1.10.1)**

- Retry 504, retry errores de red transitorios, cache 6h + tolerancia 3 fallos
- Protección token-refresh-storm (max 3/h) — evita bans de IP
- Helpers `safe_int` / `safe_float` / `safe_enum` — toleran rarezas del backend

**🚪 Firmware-Shapes CUPRA Born 2026 (v1.10.2 — primera validación live de Gerhard #53)**

Cadena de fallback de nombres de campos: `battery.currentSocPercentage` (Born 2026) → `currentPct` (Rainer #109) → `currentSOC_pct` (legacy). Tolerancia enum minúsculas para `"connected"` / `"locked"`. Compatibilidad hacia atrás preservada.

**🔓 Lock + Wake para Audi/VW (v1.9.1, #92 Audi S6 C8)**

`command_lock` ahora envía S-PIN para Audi/VW (CARIAD BFF respondía `403 spin_error`). `command_wake` usa fallback v1→v2.

**🛡️ Capability-Filter Fase 2 (v1.9.1, #56)**

Body-sniffing `classify_command_failure` para marcadores `missing-capability` / `subscription_expired` / `not_entitled` / `spin_error`. `_cariad_cmd` escribe cada resultado en FeatureState. Las entidades ligadas a comandos (Lock/Climate/Switch/Buttons) pasan automáticamente a unavailable cuando el backend dice "no" definitivo.

### ⚠️ Aún en progreso / What's still in progress (sesiones planificadas)

- **v1.13.0 MINOR** — Export de diagnostics anonimizado (#62) + Capability-Filter Fase 3 (`capability.active && user-enabled` PRE-creación-de-entidad, oculta botones como la app MyCupra) + Read-only Fase 2/3 (Command-Locking + separación de servicios cloud_refresh vs wake_vehicle).
- **v1.14.0 MINOR** — Trip Statistics desde Audi `tripstatistics/v1` (#24, #35).
- **v1.15.0+ MINOR** — PPC Climate Body conditional shape (#29, #51), Theft/Alarm Binary (#33), UI timer Climate (#26).
- **v1.16.0 MINOR** — SoC objetivo de carga específico por ubicación + perfiles de carga (#25, #31).
- **v1.17.0 MINOR** — Remote Start ICE (#28, patrón upstream #717).
- **v1.18.0 MINOR** — Push CUPRA/SEAT (Firebase FCM) + Push Skoda (mysmob MQTT) para actualizaciones en tiempo real sin polling (#57, #27).
- **v2.0.0 MAJOR** — HACS Default + Live-Tests todas las marcas + EU Data Act ready (pycupra `EUDAConnection` como referencia, deadline septiembre 2026) (#13, #59).

### 🚫 Límites conscientes / Conscious limits

- **Plataforma image:** no existe API CARIAD render-image oficial. La entidad image cambiará a URLs proporcionadas por el usuario en una futura release.
- **PPC/PPE Audi 2025+** (Q5, A5/S5, A6 e-tron, Q6 e-tron, RS e-tron GT Facelift) — nueva arquitectura E³ 1.2, aún no reverse-engineereada públicamente (ni en upstream ni en CarConnectivity). VW Group Connect detecta estos vehículos y hace **graceful degradation** en lugar de errores 404.
- **Ford / marcas no-VAG:** fuera de alcance — ver [`marq24/ha-fordpass`](https://github.com/marq24/ha-fordpass) para Ford.

### 🔧 Requisito de privacidad

Para que la posición GPS, el estado del vehículo y la calefacción estacionaria funcionen, **"Compartir mi posición"** debe estar activado en tu app My-VW / My-Audi / MySkoda / MyCupra — de lo contrario el backend responde con 403.

### 📚 Más información / More info

- 🗺️ Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md) — priorización P0/P1/P2/P3 completa de todos los issues abiertos
- 📜 Tech Changelog: [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — por release: mapeos de campos + decisiones de arquitectura + refs a fuentes externas
- 🎨 Guía Dashboards + tarjeta Lovelace BETA: [`docs/dashboards.md`](docs/dashboards.md) — solución de problemas "Añadir al panel" + tarjeta Lovelace dedicada (BETA)
- 🤝 Session Handoff (para colaboradores y herramientas IA): [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md)
- 🔒 Reglas de privacidad y manejo de datos: sección [`CONTRIBUTING.md`](CONTRIBUTING.md) (post-#53 third-party review)
- 📋 FAQ Subscription / Service Plus / diagnóstico `missing-capability`: sección FAQ de [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Marcas Compatibles

| Brand | Auth | API | Status |
|---|---|---|---|
| **Volkswagen EU** | IDK | emea.bff.cariad.digital | ✅ |
| **Audi** | IDK + AZS/MBB | emea.bff.cariad.digital | ✅ |
| **Škoda** | IDK | mysmob.api.connect.skoda-auto.cz | ✅ |
| **SEAT** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| **CUPRA** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| Porsche | Auth0 | api.ppa.porsche.com | ✅ Beta |
| VW NA (US/CA) | VW NA Auth | b-h-s.spr.*.p.con-veh.net | ✅ Beta |

> **Porsche & VW NA:** Ambas marcas están disponibles como Beta desde v1.0.0. Buscamos testers — reporta feedback como [Issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues)!

---

## Características

| Feature | Audi | VW EU | Škoda | SEAT/CUPRA |
|---|:---:|:---:|:---:|:---:|
| Fuel / Battery level | ✓ | ✓ | ✓ | ✓ |
| Range | ✓ | ✓ | ✓ | ✓ |
| Odometer | ✓ | ✓ | ✓ | ✓ |
| GPS position | ✓ | ✓ | ✓ | ✓ |
| Doors (total + per door) | ✓ | ✓ | ✓ | ✓ |
| Windows | ✓ | ✓ | ✓ | ✓ |
| Climate start/stop | ✓ | ✓ | ✓ | ✓ |
| Target temperature | ✓ | ✓ | ✓ | ✓ |
| Lock / Unlock | ✓ | ✓ | ✓ | ✓ |
| Flash lights | ✓ | ✓ | ✓ | ✓ |
| Wake vehicle | ✓ | ✓ | ✓ | ✓ |
| Service due km/days | ✓ | ✓ | ✓ | ✓ |
| Online status | ✓ | ✓ | ✓ | ✓ |
| Battery SoC % | ✓ | ✓ | ✓ | ✓ |
| Charge state | ✓ | ✓ | ✓ | ✓ |
| Charge power kW | ✓ | ✓ | ✓ | ✓ |
| Charge speed km/h | ✓ | ✓ | ✓ | ✓ |
| Charge ETA | ✓ | ✓ | ✓ | ✓ |
| Charge target % | ✓ | ✓ | ✓ | ✓ |
| Trunk / hood / sunroof | ✓ | ✓ | ✓ | ✓ |
| Window heating | ✓ | ✓ | ✓ | ✓ |
| Vehicle renders | ✓ | — | — | ✓ |
| Departure timers 1–3 | ✓ | ✓ | — | — |
| Battery temperature | ✓ | ✓ | — | — |
| AdBlue range | ✓ | ✓ | — | ✓ |

---

## Instalación

### HACS

1. HACS → Integraciones → ⋮ → Repositorios personalizados
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha` — Categoría: Integración
3. Instalar **VW Group Connect** → Reiniciar Home Assistant
4. Ajustes → Integraciones → **+ Integración** → **VW Group Connect**

### Manual

```bash
cp -r custom_components/vag_connect ~/.homeassistant/custom_components/
```

Reinicia Home Assistant.

---

## Configuración

| Field | Required | Description |
|---|---|---|
| Marca | ✓ | Audi / Volkswagen / Škoda / SEAT / CUPRA |
| Correo | ✓ | Correo de la app del fabricante |
| Contraseña | ✓ | Contraseña de la app |
| S-PIN | — | Requerido para bloqueo (en Seguridad en la app) |
| Intervalo | — | Minutos entre actualizaciones (predeterminado: 5) |

**¿Qué app?** Audi → myAudi · VW → WeConnect · Škoda → MyŠkoda · SEAT → My SEAT · CUPRA → MyCupra

---

## Limitaciones Conocidas

- **S-PIN** necesario para bloqueo
- **Intervalo** mínimo 5 minutos
- **2FA** — confirmar una vez manualmente en la app
- **Porsche / VW NA** — funcional como Beta, buscamos testers

---


## Licencia

Apache License 2.0 — [LICENSE](LICENSE)

**VW Group Connect™** es una marca no registrada (™, no ®). Por favor no uses este nombre en forks para evitar confusión.

Esta integración es un proyecto comunitario independiente sin afiliación con Volkswagen AG, Audi AG, Škoda Auto, SEAT S.A., CUPRA, Porsche AG ni ninguna filial del Grupo Volkswagen.

---

*Copyright 2026 [Prash Balan](https://github.com/its-me-prash) · Apache License 2.0*
