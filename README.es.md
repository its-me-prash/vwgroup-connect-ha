<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Integración de Home Assistant para Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>Una integración para las 7 marcas VAG, acceso directo a la API, sin middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Licencia"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  <a href="README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Antes publicada como **`vag-connect-ha`** (VAG = Volkswagen AG, abreviatura habitual en el ámbito DACH).
> Resultó que esa abreviatura suena *bastante distinta* para los angloparlantes 😅
>
> **Lo que sigue funcionando igual**: todas las entidades (p. ej. `sensor.audi_q4_battery_soc`),
> todas las llamadas de servicio (`vag_connect.lock`, `vag_connect.show_vag`, etc.), todas las automatizaciones,
> la instalación por HACS — **nada se rompe**. Cambia el nombre de marketing/visualización,
> las interioridades del código siguen igual. Detalles en [`MIGRATION.md`](MIGRATION.md).
>
> Enorme agradecimiento a las comunidades **Home Assistant UK** y **HA Ideas, Projects and Solutions**
> por el aviso — especialmente a **Si Gregory**, **Ben Johnson** y **Evets David**.
>
> Y un saludo especial a **Jordan Waeles**, cuyo comentario `show_vag()` es ahora un easter egg
> oficialmente soportado en esta integración (servicio `vag_connect.show_vag`, ver CHANGELOG v2.2.3).

---

## ¿Qué es esto?

**VW Group Connect es una integración de [Home Assistant](https://www.home-assistant.io) para datos y control de coches conectados de las siete marcas del Grupo Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche y VW US/Canadá — desde una única entrada de configuración, instalable a través de [HACS](https://hacs.xyz).**

Expone el estado de batería y carga, autonomía, cuentakilómetros, climatización, puertas/ventanas y ubicación y — donde el backend de la marca aún lo permite (p. ej. Audi) — envía comandos como bloquear/desbloquear, climatización y control de carga. Para seguir funcionando a través de los cambios de la API de Volkswagen de 2026, habla varios canales y cambia automáticamente cuando uno queda bloqueado: los backends nativos de marca, el portal de datos de vehículo de solo lectura de la **EU Data Act** y un canal web `volkswagen.de` opcional.

A diferencia de las integraciones que solo usan el portal, también cubre **Porsche** (que el portal de la EU Data Act excluye) y mantiene el **control bidireccional de Audi**.

> Una integración de [Home Assistant](https://www.home-assistant.io) para datos y control de vehículos conectados de las siete marcas del Grupo VW (Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/CA) — una integración, varios canales de datos, fallback automático, instalación por HACS.

---

## Estado actual

VW fue cerrando en 2026, paso a paso, el acceso directo al vehículo para herramientas de terceros (CARIAD-BFF con attestation de dispositivo, OLA de CUPRA/SEAT detrás de Play Integrity desde junio de 2026). Esta integración sigue siendo usable porque habla **varios canales** y conmuta automáticamente en cuanto uno se bloquea:

- **Backends propios de marca** — acceso completo incl. control, donde está disponible (Audi, Škoda, Porsche, VW US/CA).
- **Portal EU Data Act** — fallback de solo lectura para todas las marcas (sin attestation, cadencia ~15 min).
- **Canal web volkswagen.de (Beta, opt-in)** — segundo canal de lectura sin attestation para VW.

El trabajo en curso gira en torno a la robustez del portal (reintento por timeout, frescura de los datos) y la resiliencia a través de los canales.

➡️ Historial de versiones completo: **[CHANGELOG.md](CHANGELOG.md)**.

---

## Donde lideramos

Estado honesto a mediados de 2026: el portal EU Data Act se ha convertido entretanto en el canal estándar de facto, y muchas integraciones lo usan. Lo que nos distingue en concreto:

| Fortaleza | Nosotros | Alternativas portal-only |
|---|---|---|
| **Las 7 marcas del grupo incl. Porsche** en una sola integración | ✅ | El portal EU Data Act **excluye Porsche estructuralmente** — las herramientas portal-only nunca pueden cubrir Porsche |
| **Control bidireccional de Audi** (bloqueo/clima/carga, fijar Target-SoC) | ✅ | El portal es **de solo lectura** por diseño |
| **Auth multicanal con fallback automático** (backend de marca → portal EU Data Act → web vw.de opt-in) | ✅ | normalmente de fuente única — un fallo del portal = caída total |
| **Vehicle Data Scout** — detecta el drift de la API automáticamente, genera reportes de bug en 1 clic | ✅ | nada equivalente |

---

## Donde están los límites (con honestidad)

**VW EU y el OLA de CUPRA/SEAT están detrás de attestation de dispositivo desde 2026.** Este muro (Google Play Integrity / Firebase App Check) afecta a toda integración VAG basada en Python — la nuestra incluida. No es un retraso por nuestra parte, es la política del backend de VW:

- El endpoint de token/OLA exige un token de attestation firmado por la app oficial, que Python no puede generar (la clave de firma vive solo en el servicio de attestation de Google/Firebase).
- Consecuencia: **VW EU** no obtiene un `refresh_token` duradero (el flujo OIDC-Hybrid aguanta ~2 h), y **CUPRA/SEAT** vía OLA reciben desde ~2026-06-08 un `403 "Forbidden device detected"`.

Lo que ofrecemos a pesar de ello:

1. **Portal EU Data Act** como fallback de solo lectura para todas las marcas (sin attestation, cadencia ~15 min) — toma el relevo automáticamente cuando el backend nativo se bloquea.
2. **Canal web volkswagen.de (Beta, opt-in)** como segundo canal de lectura sin attestation para VW.
3. **Flujo OIDC-Hybrid** para VW EU como estrategia de lectura+escritura (con el re-login cada 2 h como precio).

**Fecha límite EU Data Act 2026-09-12.** Para esa fecha VW debe, por reglamento de la UE, ofrecer acceso directo y sin attestation a los datos del propietario — la cobertura de campos del portal presumiblemente seguirá creciendo hasta entonces.

Estado por marca:

| Marca | Control | Datos | Comentario |
|---|---|---|---|
| **Audi** | ✅ Bidireccional | ✅ completo | Backend myAudi, sin muro de attestation |
| **Škoda** | ✅ Bidireccional | ✅ completo | Backend propio de Škoda |
| **Porsche** | ✅ Bidireccional | ✅ completo | Auth0 + PPA, estable |
| **VW US/CA** | ✅ Bidireccional | ✅ completo | Nube VW-NA (Beta) |
| **VW EU** | ⚠️ vía OIDC-Hybrid (~2 h re-login) | ✅ portal de solo lectura / vw.de-Beta | Backend con attestation gate |
| **CUPRA / SEAT** | ❌ OLA bloqueado (App Check) | ✅ portal de solo lectura | desde ~2026-06-08, no arreglable por header |

---

## Lo que obtienes

Más de 100 entidades en 11 plataformas de HA, más de 20 llamadas de servicio, soporte nativo multi-vehículo por cuenta. Quality Scale Platinum.

**Sensores** (por vehículo): Battery SoC, Range (eléctrica / combustión / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 esquinas, Last Alarm Timestamp, Heater Source para ID.x, Oil Level Warning, avisos del vehículo (sensor de texto con todos los warnings del backend).

**Binary Sensors**: Doors Locked, Doors Open por puerta, Windows Open por ventana, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On por luz, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Control**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 con Weekly-Preheat, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image Platform**: 1-7 renders del vehículo por VIN (Audi/VW vía GraphQL MediaService, CUPRA/SEAT vía OLA viewPoints, Skoda vía Widget + composites multi-ángulo).

**Device Tracker**: posición GPS como TrackerEntity para el mapa Lovelace de HA.

---

## Instalación

### Opción 1: Un clic (recomendado)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Opción 2: Repositorio personalizado de HACS

1. HACS → Integraciones → ⋮ → Repositorios personalizados
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Categoría: Integración
4. Instalar **VW Group Connect**
5. Reiniciar Home Assistant

### Opción 3: Manual

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Después reinicia HA.

---

## Configuración

Ajustes → Dispositivos y servicios → Añadir integración → "VW Group Connect"

**En la primera configuración eliges:**

- **Inicio de sesión por navegador** (recomendado para Audi/Škoda/SEAT/CUPRA): escanea un código QR o abre la URL, sin contraseña guardada en HA
- **Correo + contraseña** (para VW EU, Porsche, VW US/CA): clásico con credenciales de Brand-ID

**Opciones** (disponibles tras la configuración):
- Intervalo de polling (5-60 min, por defecto 10 min)
- Modo de solo lectura para automatizaciones seguras sin comandos accidentales
- Reverse-geocoding opt-in (envía GPS a OpenStreetMap para resolver direcciones)
- Toggles de push (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) como base, activación en vivo pendiente

---

## Ejemplos de Lovelace

### Map Card

```yaml
type: map
title: Flota
default_zoom: 12
hours_to_show: 24
entities:
  - device_tracker.audi_a4_b9_position
  - device_tracker.vw_golf_7_gte_position
  - zone.home
```

### Picture-Entity Card con render del vehículo

```yaml
type: picture-entity
entity: image.audi_a4_b9_render_side_lg
camera_view: live
show_state: false
show_name: false
```

### Búsqueda de estaciones de carga

```yaml
action: vag_connect.find_charging_stations
data:
  vin: WAUZZZ...
  latitude: 47.3769
  longitude: 8.5417
  radius_m: 5000
  max_results: 25
response_variable: result
```

Más ejemplos en [`docs/FAQ.md`](docs/FAQ.md). Las tarjetas Lovelace personalizadas se integran automáticamente vía `extra_state_attributes.image_url`.

---

## Preguntas frecuentes

| Pregunta | Respuesta |
|---|---|
| ¿Cuándo se despierta mi coche? | Solo en llamadas de servicio (Lock/Climate/Wake), nunca en los polls de estado. Smart-Wake-Cap: máx. 3 wakes/día por coche, 5 min de cooldown. |
| ¿Cuánta cuota de API? | MyCupra/MySeat: ~1500 llamadas/día. Con polling de 10 min: ~144 llamadas/día = 10 % del presupuesto. El sensor `requests_remaining_today` muestra el estado. |
| ¿Por qué tengo que volver a iniciar sesión cada 2 h en VW EU? | VW puso el endpoint de token detrás de Google Play Integrity desde 2026-05-27. Afecta a toda integración VAG basada en Python. La EU Data Act 2026-09-12 debería solucionarlo. |
| ¿El token se mantiene tras actualizar por HACS? | Sí, desde v1.19.2 vía persistencia en el Store de HA. |
| ¿Cómo reporto bugs? | HA → Integración → 🔧 Reparar → Reporte de bug. Los diagnostics se anonimizan (VINs enmascarados, GPS redondeado, tokens eliminados). |
| ¿Las etiquetas de campo muestran claves crudas (`brand`, `spin`) tras actualizar? | Recarga forzada del navegador (Ctrl+Shift+R). HA cachea las traducciones en el cliente. |

FAQ completa en [`docs/FAQ.md`](docs/FAQ.md). Solución de problemas de dashboards en [`docs/dashboards.md`](docs/dashboards.md).

---

## Privacidad y seguridad

- Sin servicios externos, todo directo entre HA y la API del fabricante
- Caché de token local en `.storage/` de HA (por entrada de configuración, JSON, eliminado automáticamente al quitar la integración)
- Diagnostics anonimizados: VINs enmascarados, GPS redondeado a 1 decimal, tokens y contraseñas completamente eliminados
- Reverse-geocoding opt-in, desactivado por defecto
- Enmascarado de VIN consistente en todos los logs
- Las URLs de token se redactan en el log de ERROR (v2.7.2+)

Detalles en [`PRIVACY.md`](PRIVACY.md) y [`SECURITY.md`](SECURITY.md).

---

## Contribuir

PRs bienvenidos, ver [`CONTRIBUTING.md`](CONTRIBUTING.md). Reglas de estilo en [`STYLE.md`](STYLE.md) (privado en `_private/STYLE.md` para maintainers).

**Vehicle Data Scout** (en vivo desde v1.9.0): cuando tu integración detecta campos JSON desconocidos, crea automáticamente una notificación de Repair en HA con un enlace a un issue de GitHub prerrellenado. Reporte de bug en 1 clic sin estudiar el código.

---

## Licencia

[Apache License 2.0](LICENSE) para el código de la integración. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) para el contenido de `docs/research/`. Atribuciones a proyectos open-source upstream en [`NOTICE.md`](NOTICE.md).
