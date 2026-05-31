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


## Novedades en v2.7.0

**Inicio de sesión por navegador (sin contraseña en HA)**: Para Audi, Škoda, SEAT y CUPRA, OAuth Device Authorization Grant disponible. Escanea el QR con el móvil, inicia sesión con tu cuenta Brand ID, confirma un código corto. refresh_token real, sin re-login cada dos horas.

**Más datos por coche**: Estadísticas de viaje, nivel de aceite, presión por neumático, puertas/ventanas/techo/maletero por posición, temperatura exterior MY24+, calefacción auxiliar.

**Todas las alertas del fabricante**: Nuevo sensor "Vehicle Warning Messages" muestra cada alerta del backend.

[CHANGELOG completo](CHANGELOG.md#270---2026-05-31).

---

## ✨ v2.0.0 Big-Bang Highlights — also available in English

> The detailed v2.0.0 highlights table + "What makes us unique" USP section
> are maintained in English on the German + English READMEs. They are
> provided here as the canonical source so non-DE/EN readers can still
> see all v2.0 features with `**[NEW v2.0]**` markers without waiting on
> 6 parallel translations.

### Latest highlights — v2.0.0 Big-Bang

| Feature | Status |
|---|---|
| **Skoda Driving-Score Sensor** | **[NEW v2.0]** Efficiency score 0-100 + class bucket for Skoda MY24+ |
| **Cross-brand Aux-Heating parity (Skoda)** | **[NEW v2.0]** SkodaClient now inherits the Webasto switch from SEAT/CUPRA |
| **Porsche TPMS sensors** | **[NEW v2.0]** 4 tire-pressure sensors + warning binary_sensor (PPA TIRE_PRESSURE) |
| **Long-Term Trip Aggregates** | **[NEW v2.0]** Lifetime distance / avg fuel / avg electric (Audi + VW EU) |
| **Departure-Timer Read-Only Binary-Sensors** | **[NEW v2.0]** 3 pure-read enabled-sensors |
| **Weekly Preheat (`recurring_on`)** | **[NEW v2.0]** Service param for weekday lists (Audi + VW EU + VW NA) |
| **Charging-Station POI Lookup** | **[NEW v2.0]** `vag_connect.find_charging_stations` service |
| **Vehicle Alarm sensors** | **[NEW v2.0]** closes issue #33 |
| **heaterSource sensor** | **[NEW v2.0]** closes issue #163 |
| **Push Manager Lifecycle Wiring** | **[NEW v2.0]** Skoda MQTT + CUPRA/SEAT FCM + Audi/VW Cariad FCM (opt-in) |
| **EU Data Act Abstraction Shim** | **[NEW v2.0]** Architectural seam for the 2026-09-12 EUDA Art. 3 deadline |
| **Auth Resilience One-Click Repair** | **[NEW v2.0]** Repair button for 4 auth reasons triggers reauth flow |
| **System Health Panel** | **[NEW v2.0]** Drop-in `system_health.py` |
| **Quality Scale Platinum** | **[NEW v2.0]** Re-introduced after v1.26.x revert |
| **DeviceInfo `configuration_url` + `suggested_area`** | **[NEW v2.0]** Brand-aware "Open in App" button |

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
