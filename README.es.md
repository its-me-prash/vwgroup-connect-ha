<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Una sola integración de Home Assistant para las marcas del Grupo Volkswagen — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW EE. UU./Canadá · Bentley</strong><br>
  <em>Acceso directo a la API, multicanal con conmutación automática, sin middleware.</em>
</p>

<p align="center">
  <a href="https://github.com/sponsors/its-me-prash"><img src="https://img.shields.io/badge/%E2%9D%A4%20Sponsor-ec6cb9?logo=github-sponsors&logoColor=white" alt="Patrocina este proyecto"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg" alt="HACS Default"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?include_prereleases" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%20v3-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2024.4%2B-blue" alt="Home Assistant"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  🌍 <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Nota sobre el cambio de nombre
> Anteriormente publicado como **`vag-connect-ha`** (VAG = Volkswagen AG, abreviatura estándar en la región DACH).
> Resulta que esa abreviatura suena *bastante* distinta para los angloparlantes 😅
>
> **Lo que sigue funcionando igual que antes**: todas las entidades (p. ej. `sensor.audi_q4_battery_soc`),
> todas las llamadas de servicio (`vag_connect.lock`, `vag_connect.show_vag`, etc.), todas las automatizaciones,
> la instalación por HACS — **nada se rompe**. Cambia el nombre de marketing/visualización, el código interno
> permanece inalterado. Consulta [`MIGRATION.md`](MIGRATION.md).
>
> Un enorme agradecimiento a las comunidades **Home Assistant UK** y **HA Ideas, Projects and Solutions**
> por el aviso — en especial a **Si Gregory**, **Ben Johnson** y **Evets David**.
>
> Y una mención especial para **Jordan Waeles**, cuyo comentario `show_vag()` es ahora un easter egg
> oficialmente soportado en esta integración (servicio `vag_connect.show_vag`, ver CHANGELOG v2.2.3).

---

## ¿Qué es esto?

**VW Group Connect es una integración de [Home Assistant](https://www.home-assistant.io) que lleva los datos y el control del coche conectado a tu hogar inteligente para las marcas del Grupo Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW EE. UU./Canadá y Bentley — desde una única entrada de configuración.**

Muestra el estado de la batería y la carga, la autonomía, el cuentakilómetros, la climatización, puertas y ventanas, la ubicación y mucho más, y — allí donde el backend de la marca aún lo permite — envía comandos remotos como bloquear/desbloquear y control de climatización y carga. Para seguir funcionando a través de los cambios de la API de Volkswagen de 2026, habla **varios canales y conmuta automáticamente** cuando uno se bloquea: los backends nativos de cada marca, el portal de datos del vehículo de solo lectura de la **EU Data Act**, un canal web opcional de `volkswagen.de` y un inicio de sesión **sin contraseña** y duradero para vehículos Car-Net más antiguos. Funciona perfectamente **junto a [evcc](https://evcc.io)** y necesita **cero dependencias de PyPI**.

> 🎉 **Ahora disponible directamente en HACS** — sin necesidad de repositorio personalizado.

---

## Lo destacado

- **8 marcas del Grupo Volkswagen seleccionables** en una sola integración — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW EE. UU./Canadá, Porsche y Bentley.
- **Compatible con Porsche** — Porsche funciona sobre su propio backend *Porsche Connect*, **no** sobre el portal de la EU Data Act. La ruta del portal *excluye* estructuralmente a Porsche, así que las herramientas que solo usan el portal nunca podrán cubrirlo; esta integración sí.
- **Control bidireccional allí donde el backend de la marca lo permite** — bloquear/desbloquear, climatización, carga, SoC objetivo. Consulta en la tabla de más abajo qué marcas tienen soporte real de comandos; VW EU es de solo lectura por defecto (ver la nota honesta correspondiente).
- **Opción de inicio de sesión sin contraseña** (navegador/código de dispositivo) para Audi/Škoda/SEAT/CUPRA — ninguna contraseña se almacena en Home Assistant.
- **Multicanal con conmutación automática** — nativo de marca → portal de la EU Data Act → web opcional vw.de → Car-Net duradero. Que un canal se caiga no deja tus datos a oscuras.
- **Resiliente por diseño** — conserva los últimos valores conocidos durante caídas del portal, filtra centinelas falsos de "sin lectura" y nunca deja que el cuentakilómetros retroceda.
- **Rastreador de dispositivo por GPS**, más de 100 entidades en múltiples plataformas, más de 20 llamadas de servicio, multivehículo por cuenta.
- **Vehicle Data Scout** — detecta automáticamente la deriva de la API y ofrece un informe de error con un solo clic. **Quality Scale: Platinum.**

---

## Estado por marca

| Marca | Control | Datos | Notas |
|---|---|---|---|
| **Audi** | ✅ Bidireccional | ✅ Completo | backend myAudi (incl. arranque/parada del motor de combustión) |
| **Škoda** | ✅ Bidireccional | ✅ Completo | backend nativo de Škoda |
| **Porsche** | ✅ Bidireccional | ✅ Completo | Porsche Connect — backend propio, no el portal de la EU Data Act |
| **VW EE. UU./CA** | ✅ Bidireccional | ✅ Completo | nube VW NA (requiere el selector de país EE. UU./CA + S-PIN) |
| **VW EU** | 🔒 Solo lectura por defecto · ⚠️ comandos = MBB **alpha** | ✅ Telemetría completa vía portal de la EU Data Act | Ver la nota honesta más abajo — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Comandos bloqueados por VW | ✅ Portal de la EU Data Act | Acceso OLA revocado del lado del servidor en 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Bidireccional pendiente de prueba en vivo | ✅ Inicio de sesión + lectura | My Bentley — funciona sobre el tenant Audi/IDK |

> **Nota honesta sobre el control de VW EU.** Los vehículos Volkswagen EU son **de solo lectura por defecto**: obtienes telemetría completa a través del portal de la EU Data Act, pero ningún comando remoto. Los comandos remotos para VW EU existen **solo como un ALPHA experimental bidireccional de MBB duradero**, y únicamente para coches **MQB / Car-Net heredados** — es un interruptor opcional, **no** una función por defecto. **Los coches MEB / de la familia ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) no tienen ninguna ruta de comandos** y se crean como de solo lectura. El alpha de MBB se sigue en **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — se buscan probadores.

> En 2026 Volkswagen colocó partes de su API tras una verificación de atestación del dispositivo. Esta integración la sortea allí donde es posible (inicio de sesión Car-Net duradero, portal de la EU Data Act, web vw.de) y es transparente sobre lo que cada canal puede y no puede hacer.

---

## Limitaciones conocidas

Algunas cosas son **estructurales** — provienen de cómo funcionan los backends de Volkswagen en 2026, no de la integración, y ningún ajuste las arregla:

- **VW EU es de solo lectura por defecto; los comandos son un alpha de MBB solo para coches heredados.** Ver la nota de marca de arriba. **Los coches MEB / de la familia ID son de solo lectura** — la ruta de comandos Car-Net duradera no los reconoce (responde "Unknown user"), y el backend MEB de VW no expone nada equivalente. La configuración lo detecta y crea una **entrada de solo lectura** (con un aviso de reparación) en lugar de fallar, así que es un límite conocido, no uno silencioso. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **Los comandos remotos de CUPRA / SEAT están bloqueados por VW.** El acceso a los servicios en línea (OLA) de estas marcas fue revocado del lado del servidor en 2026 (HTTP 403); volver a iniciar sesión o subir la versión de la app no lo restaura. Los datos siguen fluyendo vía el portal de la EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Los datos del portal de la EU Data Act son escasos y varían según el coche.** VW publica hoy solo una porción de campos (a menudo cuentakilómetros + bloqueo + carga, a veces mucho más). Esa porción se amplía con el tiempo a medida que VW expande el portal de cara a la fecha límite de septiembre de 2026 — campos que hoy aparecen como `unknown` pueden rellenarse por sí solos, sin necesidad de cambios. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Instalación

**Vía HACS (recomendado):**

1. Abre **HACS** en Home Assistant.
2. Busca **"VW Group Connect"** e instálalo.
3. Reinicia Home Assistant.
4. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → VW Group Connect** y sigue el flujo de inicio de sesión.

<sup>Recién fusionado en el repositorio por defecto de HACS — si todavía no aparece en la búsqueda, dale algo de tiempo al índice de HACS para que se actualice, o añade `its-me-prash/vwgroup-connect-ha` como repositorio personalizado mientras tanto.</sup>

**Home Assistant mínimo: `2024.4.0`.**

### Opciones de inicio de sesión (el asistente de configuración tiene dos rutas)

La primera pantalla de la integración ofrece **dos** métodos de inicio de sesión. Elige el que admita tu marca:

- **Navegador / código de dispositivo (sin contraseña)** — *Audi · Škoda · SEAT · CUPRA.* Inicia sesión en tu teléfono o portátil y aprueba el dispositivo; no se almacena ninguna contraseña en Home Assistant (conserva un token de actualización real). Este paso también ofrece los campos opcionales de **S-PIN**, intervalo de escaneo y forzar acceso.
- **Portal — email + contraseña** — *Volkswagen EU · Porsche.* Introduce el inicio de sesión de tu marca. Este paso expone un selector de marca (Volkswagen EU, Porsche y las demás marcas de email/contraseña), email, contraseña, **S-PIN** opcional, intervalo de escaneo, forzar acceso y un interruptor **"habilitar comandos MBB"** (que solo tiene efecto en Volkswagen EU — ver [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Para **Volkswagen EE. UU./Canadá** aparece aquí un **selector de país (EE. UU. vs CA)** — se muestra **únicamente** para esa marca y ninguna otra lo usa.

> El **portal de la EU Data Act no es un tercer botón de inicio de sesión.** Es la estrategia de solo lectura a la que el coordinador conmuta automáticamente, y además puede *añadirse* como canal de lectura suplementario desde **Configurar → Opciones**. Lo mismo aplica al canal web `volkswagen.de` (un canal de lectura suplementario opcional, solo desde Opciones).

### El campo S-PIN — cuándo lo necesitas

El **S-PIN** es el PIN de seguridad de la app de tu marca. Es opcional en el formulario y solo se requiere para algunas acciones: es necesario para las **lecturas de datos y comandos de VW EE. UU./Canadá**, y para los comandos remotos sensibles a la seguridad en las marcas que los protegen tras el S-PIN. Déjalo en blanco si tu coche no pide ninguno.

---

### Volkswagen EU — cómo hacer que tus datos empiecen a fluir (importante)

Para Volkswagen EU, **iniciar sesión no basta** — VW solo transmite datos del vehículo una vez que *tú* has activado la compartición de datos del lado de VW. Si tu coche aparece sin datos (o no aparece en absoluto), casi siempre es por este motivo, **no** por una contraseña incorrecta. Haz esto una vez:

1. **Añade la integración:** elige **Portal (email + contraseña)** y selecciona **Volkswagen EU**, luego inicia sesión.
2. **Completa cualquier solicitud puntual en el portal de VW.** Abre el portal de datos de VW una vez en un navegador o en la app de la marca y termina lo que te pida: **acepta los términos, confirma el consentimiento, finaliza el onboarding / selección de región.** El acceso sin interfaz no puede superar estos pasos — este es el caso `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Concede el consentimiento de compartición de datos.** En el portal, establece **"Uso de datos no personales" = Concedido** (el consentimiento de compartición de datos de la EU Data Act).
4. **Habilita la solicitud continua de datos** para ese coche en concreto. Sin ella, el portal devuelve *ninguna solicitud de datos* para ese VIN y el vehículo aparece sin lecturas.
5. **Espera a que el coche envíe una instantánea.** Incluso después de todo lo anterior, la propagación lleva tiempo. El coche puede leer **`offline` / `unknown` durante un rato — a menudo hasta su próximo trayecto o despertar, hasta ~24 h** — antes de que se rellenen los sensores. Esto es normal.

El portal sirve inicialmente solo una **porción de campos**, y esa porción **se amplía con el tiempo** a medida que VW expande la cobertura del portal de cara a la fecha límite de septiembre de 2026 — campos que hoy aparecen como `unknown` pueden rellenarse por sí solos. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Opcional:** el interruptor de Opciones **`eu_data_act_auto_kickoff`** puede crear automáticamente por ti la Solicitud de Datos Personalizada de 15 minutos. Es opcional porque crearla implica una **suscripción de 1 mes en tu cuenta de VW**, así que la integración no lo hará sin tu permiso.

---

## Lo que obtienes

- **Sensores:** SoC de la batería, autonomía (eléctrica / combustión / total), nivel de combustible, cuentakilómetros, temperaturas, potencia/velocidad/tipo de carga, objetivo de carga, estadísticas de viaje y agregados de por vida, intervalos de servicio y de cambio de aceite, versión de software, estado de conexión, última conexión y más.
- **Sensores binarios:** puertas bloqueadas, puertas/ventanas/maletero/capó/techo solar abiertos, enchufe conectado, cargando, actualización OTA disponible, luces, vehículo en línea, temporizadores de salida, alarma.
- **Control:** bloquear/desbloquear, iniciar/detener climatización, iniciar/detener carga, calefacción de ventanas, temporizadores de salida, fijar SoC objetivo / temperatura / corriente máxima de carga, bocina y luces, despertar, refrescar, buscar estaciones de carga *(la disponibilidad depende de la marca y el modelo)*.
- **Rastreador de dispositivo:** posición GPS para el mapa de Home Assistant.
- **Imágenes:** renders del vehículo donde la marca los proporciona.

> 💡 **Panel de Energía:** el sensor de energía cargada es `total_increasing`, así que añádelo directamente al **panel de Energía** de Home Assistant, o envuélvelo en un helper `utility_meter` para obtener totales de energía cargada diarios/mensuales. Usa el sensor acumulativo de **energía cargada (kWh)** para esto — no los sensores de eficiencia por 100 km (esos son promedios, no contadores).

### Servicios

La integración incluye **más de 20 llamadas de servicio** (`vag_connect.*`), muchas de ellas específicas de cada marca — *la disponibilidad depende de la marca y el modelo*. Entre ellas: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (combustión Audi), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (Webasto de SEAT/CUPRA), `send_destination` y `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, y el easter egg `show_vag`.

---

## Telemetría en vivo de ABRP (A Better Routeplanner)

Puedes enviar los datos en vivo de tu coche a **[A Better Routeplanner](https://abetterrouteplanner.com/)** para que planifique en torno a tu estado de carga real. Es **opcional y está desactivado por defecto** — nada sale de tu red hasta que lo activas y se ejecuta realmente una subida.

**1. Consigue las dos credenciales.**

- **`token`** (por vehículo) — abre la app de ABRP → **Settings → tu coche → Live Data → "Generic" / otro coche** y copia el token que muestra.
- **`api_key`** (clave de desarrollador) — es una clave de socio/desarrollador emitida por **iternio**, *no* algo que la app entregue. Solicítala a iternio (su formulario de solicitud de clave de desarrollador/API). **Deliberadamente no incluimos una clave** — codificar una que no nos pertenece sería suplantación de identidad e incrustaría un secreto ajeno en un repositorio público. Pega la tuya.

**2. Actívalo.** Integración → **Configurar** → desplázate hasta la sección **ABRP** → marca *Habilitar envío de telemetría ABRP* y pega ambos valores. Se validan como un par (recibirás un error si solo se establece uno), se almacenan enmascarados y **nunca se escriben en el registro**.

**3. Automatiza la subida.** Importa el blueprint incluido **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), elige tu vehículo y su sensor **ABRP data changed**, y listo. El blueprint sube solo cuando hay una instantánea genuinamente nueva (el sensor binario *ABRP data changed* es el disparador idempotente — se reinicia tras cada envío correcto, así que la misma instantánea nunca se envía dos veces).

También puedes llamar directamente al servicio **`vag_connect.abrp_send`** (apunta a un dispositivo o VIN; la api_key/token provienen de las opciones a menos que las pases en línea).

> 🔒 **Privacidad:** la telemetría incluye GPS. Solo sale de tu red cuando se ejecuta `abrp_send` (es decir, cuando *tú* lo disparas / habilitas el blueprint). Lo que enviamos: estado de carga, estado de la carga, GPS, rumbo, energía + capacidad, autonomía estimada, temperatura ambiente + de la batería, cuentakilómetros. Lo que deliberadamente **no** enviamos: nada que no podamos medir de forma fiable (velocidad, tensión/corriente del pack de alta tensión, estado de salud) — omitido en lugar de adivinado.

---

## Opciones (Configurar)

Desde **Ajustes → Dispositivos y servicios → VW Group Connect → Configurar** puedes ajustar:
intervalo de escaneo, S-PIN, geocodificación inversa, **modo de solo lectura**, forzar climatización PPE (Audi), interruptores de push (MQTT/FCM/Audi-VW), **conmutación de navegador para la EU Data Act** (Playwright / ~100 MB de Chromium, opcional), **despertar antes de sondear** + retardo de despertar, anulación de client-id, **`eu_data_act_auto_kickoff`**, ocultar entidades vacías (activado por defecto), **ABRP** (habilitar + api_key + token de usuario, validados como un par), además de **añadir / eliminar** los canales de lectura suplementarios `volkswagen.de` y del portal de la EU Data Act.

---

## Apoya este proyecto ❤️

Esto es un proyecto de una sola persona — y VW no lo pone fácil: cada cambio de backend significa días de ingeniería inversa para encontrar de nuevo una ruta que funcione. Esa persistencia es lo que lo mantiene vivo allí donde proyectos consolidados se han rendido. Si vale algo para ti, puedes apoyar el mantenimiento continuo a través de **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. ¡Gracias! 🙏

---

## Contribuir

PRs bienvenidos — consulta [`CONTRIBUTING.md`](CONTRIBUTING.md). El **Vehicle Data Scout** convierte campos desconocidos de la API en un informe de error precargado de un solo clic, así que puedes ayudar a mejorar la cobertura sin leer código.

## Licencia

[GNU AGPL v3.0-or-later](LICENSE) para el código de la integración. Atribución obligatoria + condiciones de nombre/marca registrada en el uso/fork: ver [`ATTRIBUTION.md`](ATTRIBUTION.md). Atribuciones de código abierto upstream en [`NOTICE.md`](NOTICE.md).
