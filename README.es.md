<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Una sola integración de Home Assistant para los coches del Grupo Volkswagen: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW y Audi EE. UU./Canadá</strong><br>
  <em>Batería, carga, autonomía, puertas, climatización y ubicación GPS en Home Assistant. Acceso directo a la API, varios canales de lectura con conmutación automática, sin middleware.</em>
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
  🌍 <a href="README.md">English</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.it.md">Italiano</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a> · <a href="README.da.md">Dansk</a> · <a href="README.nb.md">Norsk</a> · <a href="README.fi.md">Suomi</a>
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

**VW Group Connect es una integración de [Home Assistant](https://www.home-assistant.io) que lleva tu coche del Grupo Volkswagen a tu hogar inteligente: estado de la batería y de la carga, autonomía, cuentakilómetros, climatización, puertas y ventanillas, ubicación GPS y mucho más, para Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley y las cuentas norteamericanas de VW / Audi, todo desde una única entrada de configuración.**

Donde el backend de la marca todavía lo permite, también envía órdenes remotas como bloqueo/desbloqueo y control de climatización y carga. **Eso depende de la marca, no es universal:** Audi y Škoda son bidireccionales, Volkswagen EU a través del portal de la EU Data Act es de solo lectura, y las órdenes de SEAT/CUPRA están bloqueadas por el fabricante. La tabla de abajo dice exactamente qué es qué.

Para seguir funcionando pese a los cambios de API de Volkswagen de 2026, habla **varios canales de lectura y conmuta automáticamente** cuando uno está bloqueado: los backends nativos de cada marca, el portal de datos del vehículo de la **EU Data Act** (solo lectura), un canal web `volkswagen.de` opcional (beta), un relleno de huecos opcional vía **Tibber** y un inicio de sesión **sin contraseña** duradero para los vehículos Car-Net más antiguos. Funciona sin problemas **junto a [evcc](https://evcc.io)** (consulta [docs/EVCC.md](docs/EVCC.md)) y no necesita **ningún add-on, bróker ni contenedor intermedio**. Home Assistant instala automáticamente tres pequeños paquetes de Python; solo los usan los canales opcionales push y complementario (ADB).

> 🎉 **Ahora disponible directamente en HACS** — sin necesidad de repositorio personalizado.

---

## Lo destacado

- **10 marcas/fuentes del Grupo Volkswagen seleccionables** en una sola integración: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW EE. UU./Canadá, Audi EE. UU./Canadá, Porsche, Bentley y **Audi plug&play (dongle OBD)** para Audis antiguos sin conectividad previa.
- **Audis antiguos sin conectividad integrada, a través de un dongle OBD (nuevo en 4.3.0)**: los coches invisibles para el backend de CARIAD y el portal de la EU Data Act (A4/A5 sin conectividad, Touareg, e-up!, …) pueden leerse mediante la instantánea en la nube de un dongle plug&play de TEXA — cuentakilómetros, tensión de la batería de 12 V, luces de aviso, última posición de aparcamiento, más datos maestros de fábrica (potencia del motor, cilindrada, colores, designación del modelo). De solo lectura, en su propio silo de tokens.
- **Control bidireccional donde el backend de la marca lo permite**: bloqueo/desbloqueo, climatización, carga, SoC objetivo. Esto es **por marca, no universal**. Mira la tabla de abajo antes de contar con una orden.
- **El asistente de a bordo de Škoda «Laura» en Home Assistant (nuevo en 3.0.0)**: pregúntale por la autonomía, la carga y los viajes como servicio, o entrégalo a cualquier agente de conversación (el Assist integrado, OpenAI, Anthropic, Google, Ollama) como una herramienta que puede llamar y encadenar. Consejos de solo lectura sobre los que tus automatizaciones pueden actuar.
- **Eventos del Registro, firmware y tarjetas de calendario (nuevo en 3.1.0)**: las notificaciones push del fabricante se convierten en una entidad `event` por vehículo (Registro + automatizaciones, sin filtro de bus YAML), una entidad `update` de firmware de solo lectura muestra el estado OTA (Škoda hoy, sin botón de instalación) y dos entidades `calendar` despliegan la planificación de carga + las fechas de vencimiento de servicio.
- **Opción de inicio de sesión sin contraseña** (navegador/código de dispositivo) para Audi, SEAT, CUPRA y Audi EE. UU./CA. No se guarda ninguna contraseña en Home Assistant. Škoda pasó a correo + contraseña en la 3.0.1 cuando VW revocó su concesión de código de dispositivo.
- **Multicanal con conmutación automática**: backend nativo de la marca, portal de la EU Data Act, web vw.de opcional, Tibber opcional, Car-Net duradero y un lector en la nube por dongle OBD para Audis sin conectividad previa. Si un canal cae, tus datos no se apagan.
- **Canal complementario (experimental, opcional)**: cuando todas las vías del backend están cerradas, la integración puede leer los datos de tu coche manejando la app oficial en un móvil Android de repuesto. Tres transportes: **ADB sobre TCP**, el [**add-on ADB Bridge**](https://github.com/its-me-prash/vwgroup-app-adb-bridge) para móviles modernos y — nuevo en la beta 4.4.0 — una **app de agente complementaria** que ejecuta el móvil, que *llama a Home Assistant* mediante un long-poll saliente para que la NAT, las IP cambiantes y el aislamiento de clientes Wi-Fi dejen de importar (la app de agente es un artefacto aparte, aún no publicado; el protocolo está en [docs/COMPANION_AGENT.md](docs/COMPANION_AGENT.md)). Volkswagen está verificado contra un dispositivo real; el resto de marcas son de solo lectura hasta que se confirme un mapa de pantallas. No se rootea nada ni se leen tokens de la app.
- **Resiliente por diseño**: conserva los últimos valores conocidos y la última posición de aparcamiento durante las caídas del portal, filtra los falsos centinelas de «sin lectura», nunca deja que el cuentakilómetros retroceda y te dice cuándo un inicio de sesión fallido es una avería del fabricante y no tu contraseña.
- **Tú controlas la frecuencia de sondeo**: un **deslizador de intervalo de sondeo** por cuenta (una entidad Number, en minutos) que las automatizaciones pueden manejar, creado en todas las instalaciones, incluidas las de solo lectura por portal.
- **Rastreador GPS**, más de 100 entidades en varias plataformas, más de 30 llamadas de servicio, varios vehículos por cuenta, nombres de entidad en **12 idiomas**.
- **Porsche funciona sobre su propio backend**, no sobre el portal de la EU Data Act. La vía del portal *excluye* estructuralmente a Porsche, así que las herramientas que solo usan el portal nunca podrán cubrirlo. El código de las órdenes está aquí, pero el propio inicio de sesión de Porsche es experimental ahora mismo (mira la tabla).
- **Vehicle Data Scout** detecta automáticamente la deriva de la API y ofrece un informe de error en un clic — y desde la 3.0.0 su descarga de diagnósticos censurados incluye también las respuestas en bruto de la API, así que un único adjunto es todo lo necesario para añadir compatibilidad con un campo nuevo. **Quality Scale: Platinum.**

---

## Estado por marca

| Marca | Control | Datos | Notas |
|---|---|---|---|
| **Audi** (EU) | ✅ Bidireccional | ✅ Completo | backend myAudi (incl. arranque/parada de motor térmico). Los Audi Car-Net heredados pueden optar por un **canal de órdenes MBB duradero** que sobrevive a los reinicios y al muro de Play-Integrity — nuevo en 4.4.0, desactivado por defecto; los Audi ID/MEB más nuevos no son elegibles ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **Škoda** | ✅ Bidireccional | ✅ Completo | backend nativo de Škoda |
| **VW EE. UU./CA** | 🇨🇦 ✅ Bidireccional · 🇺🇸 ⛔ bloqueado por VW | 🇨🇦 ✅ Completo · 🇺🇸 ⛔ | Canadá inicia sesión en su propio servidor + cliente de app y muestra todos los datos, confirmado en un ID.4 canadiense real ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **EE. UU.: desde el 2026-08-13 VW aplica atestación del dispositivo (Play Integrity) en el plano norteamericano, así que el inicio de sesión / intercambio de tokens de EE. UU. falla en seco (401) — un muro del lado de VW que un cliente de código abierto no puede satisfacer fuera del dispositivo ([#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)).** |
| **VW EU** | 🔒 Solo lectura por defecto · ⚠️ órdenes = Car-Net **beta** | ✅ Telemetría completa vía el portal de la EU Data Act | Consulta la nota honesta de abajo ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Órdenes bloqueadas por VW | ✅ Portal de la EU Data Act | Acceso OLA revocado en el servidor en 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Bidireccional pendiente de prueba real | ✅ Inicio de sesión + lectura | My Bentley, funciona sobre el tenant Audi/IDK |
| **Porsche** | ⚠️ Experimental | ⚠️ Experimental | Porsche Connect, backend propio. Porsche pasó a la app *Porsche One*, así que **es previsible que el inicio de sesión falle en las cuentas actuales**. El código de las órdenes está ahí pero es inalcanzable hasta que se reconstruya el inicio de sesión ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi EE. UU./CA** | ⏳ Bidireccional pendiente de prueba real | ✅ Completo | backend myAudi NA. EE. UU. ahora lee del servicio de vehículos regional `na` y está **confirmado funcionando en un Audi Q5 de EE. UU. real** (58 entidades) — gracias @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canadá usa el servicio EMEA. Los comandos heredan las rutas bidireccionales de Audi pero aún no se han confirmado por separado en real en NA ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |
| **Audi plug&play** (dongle OBD) | ⛔ Solo lectura | ✅ Lecturas vía la nube del dongle | Dongle OBD de TEXA para Audis sin conectividad previa; cuentakilómetros, 12 V, luces, posición de aparcamiento + datos maestros de fábrica. De solo lectura, silo de tokens propio (nuevo en 4.3.0) |

> **Nota honesta sobre el control de VW EU.** Los vehículos Volkswagen EU son **de solo lectura por defecto**: obtienes telemetría completa a través del portal de la EU Data Act, pero ningún comando remoto. El **2026-08-18 VW deshabilitó el inicio de sesión** que usaba el bidireccional moderno (CARIAD), así que ese canal ya no se puede configurar. Los comandos remotos para VW EU existen ahora **solo como una BETA bidireccional de Car-Net (MBB) duradera**, y únicamente para coches **MQB / Car-Net heredados** — es un interruptor opcional, **no** una función por defecto. **Los coches MEB / de la familia ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) no tienen ninguna ruta de comandos** y se crean como de solo lectura. La beta de Car-Net se sigue en **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — se buscan probadores.

> En 2026 Volkswagen colocó partes de su API tras una atestación del dispositivo, y la ha ido apretando a lo largo del año: **Volkswagen EE. UU. dejó de funcionar el 2026-08-13** (atestación de Play-Integrity en el plano norteamericano, [#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)) y el **inicio de sesión bidireccional moderno de VW EU se retiró el 2026-08-18**. Esta integración sortea la atestación allí donde es posible (inicio de sesión Car-Net duradero, portal de la EU Data Act, web vw.de) y es transparente sobre lo que cada canal puede y no puede hacer. **Consejo: ejecuta solo una integración bidireccional por coche — VW limita la tasa de las cuentas que varias apps machacan a la vez, y una cuenta bloqueada también rompe la app oficial.**

---

## Limitaciones conocidas

Algunas cosas son **estructurales** — provienen de cómo funcionan los backends de Volkswagen en 2026, no de la integración, y ningún ajuste las arregla:

- **VW EU es de solo lectura por defecto; los comandos son un alpha de MBB solo para coches heredados.** Ver la nota de marca de arriba. **Los coches MEB / de la familia ID son de solo lectura** — la ruta de comandos Car-Net duradera no los reconoce (responde "Unknown user"), y el backend MEB de VW no expone nada equivalente. La configuración lo detecta y crea una **entrada de solo lectura** (con un aviso de reparación) en lugar de fallar, así que es un límite conocido, no uno silencioso. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **Los comandos remotos de CUPRA / SEAT están bloqueados por VW.** El acceso a los servicios en línea (OLA) de estas marcas fue revocado del lado del servidor en 2026 (HTTP 403); volver a iniciar sesión o subir la versión de la app no lo restaura. Los datos siguen fluyendo vía el portal de la EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Los datos del portal de la EU Data Act son escasos y varían según el coche.** VW publica hoy solo una porción de campos (a menudo cuentakilómetros + bloqueo + carga, a veces mucho más). Esa porción se amplía con el tiempo a medida que VW expande el portal de cara a la fecha límite de septiembre de 2026 — campos que hoy aparecen como `unknown` pueden rellenarse por sí solos, sin necesidad de cambios. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Los coches VW EU no tienen posición GPS en vivo a través del portal de la EU Data Act.** Volkswagen Group Info Services ha [confirmado por escrito](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13#issuecomment-5359744122) que el diccionario de datos de la exportación continua del portal incluye un clúster *Seguimiento de la ubicación del vehículo* pero **ningún punto de datos definido para las coordenadas actuales del coche** (latitud / longitud) — así que un coche VW EU leído solo a través del portal muestra su ubicación como `unknown`. Esto es un límite del conjunto de datos de VW, no de la integración, y el endpoint de posición de la app del fabricante se ha cerrado a terceros. Los VW / Audi norteamericanos y otras marcas con un endpoint de posición funcional no se ven afectados. ([#923](https://github.com/its-me-prash/vwgroup-connect-ha/issues/923))
- **Norteamérica: VW y Audi ya leen ambos — los comandos de Audi son la última pieza sin confirmar.** **VW EE. UU./CA funciona, incluido Canadá**, confirmado contra un ID.4 canadiense real: Canadá inicia sesión en su propio servidor y, desde la corrección del envoltorio de datos, muestra la telemetría completa ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi EE. UU./CA ahora también lee**: EE. UU. lee del servicio de vehículos regional `na`, confirmado en un Audi Q5 de EE. UU. real (gracias @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canadá usa el servicio EMEA. Los comandos heredan las rutas bidireccionales de Audi pero aún no se han confirmado por separado en real en cuentas norteamericanas ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **Es previsible que el inicio de sesión de Porsche falle ahora mismo.** Porsche retiró la app *My Porsche*, contra la que se autentica esta integración, en favor de *Porsche One*. Las lecturas y las órdenes están implementadas, pero probablemente no pasarás del inicio de sesión hasta que eso se reconstruya. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Las actualizaciones push (casi en tiempo real) son una BETA opcional, desactivada por defecto.** Los canales MQTT (Škoda) y Firebase (Audi/VW, CUPRA/SEAT) están cableados pero no validados en real, y las marcas los protegen cada vez más con atestación de app, que no puede satisfacerse fuera del dispositivo. Déjalos desactivados salvo que quieras ayudar a probarlos. El sondeo normal es la vía soportada.

> **Cómo lo vemos.** Según la EU Data Act (Reglamento (UE) 2023/2854), los datos de tu coche son *tuyos*. Ejecutar esta integración en tu propio hardware es *tú* accediendo a *tus propios* datos (Artículo 4) — datos que se te deben con la misma calidad con la que el fabricante se sirve a sí mismo, en tiempo real siempre que sea técnicamente posible. El portal de VW, de solo lectura y con horas de retraso, no está hoy a la altura de eso. Esta integración es deliberadamente **agnóstica respecto al canal**: en cuanto VW ofrezca a los propietarios una interfaz en tiempo real y con capacidad de control — como exige la Data Act, y como algunos fabricantes ya ofrecen a sus propietarios — la admitiremos aquí, gratis, para todos. Respaldamos tu derecho a acceder en tiempo real a los datos de tu propio coche.

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

- **Navegador / código de dispositivo (sin contraseña)** para *Audi, SEAT, CUPRA y Audi EE. UU./CA*. Inicia sesión en tu móvil o portátil y aprueba el dispositivo; no se guarda ninguna contraseña en Home Assistant (conserva un refresh token real). Este paso ofrece además el **S-PIN** opcional y el intervalo de escaneo.
- **Portal, correo + contraseña** para *Volkswagen EU, Škoda, Volkswagen EE. UU./CA, Bentley y Porsche (experimental)*. Introduce las credenciales de tu marca. Este paso muestra un selector de marca, correo, contraseña, **S-PIN** opcional, intervalo de escaneo y un interruptor **«activar órdenes MBB»** — el canal de órdenes Car-Net duradero — para Volkswagen EU y, **ahora validado en real, para los Audi Car-Net heredados** (desactivado por defecto, [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)); a los inicios de sesión Audi sin contraseña (código de dispositivo) se les ofrece la misma opción de MBB duradero como un paso de configuración dedicado. Para **Volkswagen EE. UU./Canadá** aparece aquí un **selector de país (EE. UU. o CA)**; se muestra **solo** para esa marca y ninguna otra lo usa. **Audi plug&play (dongle OBD)** es su propia opción — los vehículos se descubren automáticamente desde la cuenta en la nube del dongle.

> El **portal de la EU Data Act no es un tercer botón de inicio de sesión.** Es la estrategia de solo lectura a la que el coordinador recurre automáticamente, y además puede *añadirse* como canal de lectura suplementario desde **Configurar → Opciones**. Lo mismo vale para el canal web `volkswagen.de` (beta opcional, solo desde las Opciones, de solo lectura) y para el canal **Tibber** opcional, que rellena los campos que los canales propios dejaron vacíos y nunca sobrescribe datos más recientes.

### El campo S-PIN — cuándo lo necesitas

El **S-PIN** es el PIN de seguridad de la app de tu marca. Es opcional en el formulario y solo se requiere para algunas acciones: es necesario para las **lecturas de datos y comandos de VW EE. UU./Canadá**, y para los comandos remotos sensibles a la seguridad en las marcas que los protegen tras el S-PIN. Déjalo en blanco si tu coche no pide ninguno.

---

### Volkswagen EU — cómo hacer que tus datos empiecen a fluir (importante)

Para Volkswagen EU, **iniciar sesión no basta** — VW solo transmite datos del vehículo una vez que *tú* has activado la compartición de datos del lado de VW. Si tu coche aparece sin datos (o no aparece en absoluto), casi siempre es por este motivo, **no** por una contraseña incorrecta. Haz esto una vez:

1. **Añade la integración:** elige **Portal (email + contraseña)** y selecciona **Volkswagen EU**, luego inicia sesión.
2. **Completa cualquier solicitud puntual en el portal de VW.** Abre el portal de datos de VW una vez en un navegador o en la app de la marca y termina lo que te pida: **acepta los términos, confirma el consentimiento, finaliza el onboarding / selección de región.** El acceso sin interfaz no puede superar estos pasos — este es el caso `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Concede el consentimiento de compartición de datos.** En el portal, establece **"Uso de datos no personales" = Concedido** (el consentimiento de compartición de datos de la EU Data Act).
4. **No busques un interruptor de "solicitud continua de datos" — no existe.** La integración crea esa solicitud para cada coche por su cuenta, y es **gratuita**. Desde la v2.29.0 la solicitud se crea **sin fecha de caducidad**; las versiones anteriores pedían un mes, y por eso algunas instalaciones dejaron de recibir datos sin previo aviso al cabo de unas cuatro semanas. Si tus datos se han detenido y configuraste la cuenta antes de la v2.29.0, elimina la cuenta de la integración y vuelve a añadirla una vez para que se cree una solicitud nueva. Sin una solicitud, el portal no devuelve nada para ese VIN y el vehículo aparece sin lecturas.
5. **Espera a que el coche envíe una instantánea.** Incluso después de todo lo anterior, la propagación lleva tiempo. El coche puede leer **`offline` / `unknown` durante un rato — a menudo hasta su próximo trayecto o despertar, hasta ~24 h** — antes de que se rellenen los sensores. Esto es normal.

El portal sirve inicialmente solo una **porción de campos**, y esa porción **se amplía con el tiempo** a medida que VW expande la cobertura del portal de cara a la fecha límite de septiembre de 2026 — campos que hoy aparecen como `unknown` pueden rellenarse por sí solos. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Lista completa de campos.** El diccionario de datos oficial del grupo VW (cada clave de EU Data Act -> campo, descripción y unidad) está en [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Un workflow semanal vigila la página del diccionario del portal y abre una pull request cuando VW publica una versión más nueva, para que la tabla no se quede obsoleta en silencio.

> El interruptor de Opciones **`eu_data_act_auto_kickoff`** es el que crea esa Solicitud de Datos Personalizada de 15 minutos, y está **activado por defecto** — en modo portal no hay datos sin ella. Desactívalo solo si prefieres gestionar la solicitud por tu cuenta.

---

## Lo que obtienes

- **Sensores:** SoC de la batería, autonomía (eléctrica / combustión / total), nivel de combustible, cuentakilómetros, temperaturas, potencia de carga, velocidad de carga (siempre en km/h, convertido si tu coche informa en mph) y tipo de carga, objetivo de carga, historial por sesión de carga (energía, duración, inicio, CA/CC) en Škoda y SEAT/CUPRA, estadísticas de viaje y agregados de por vida, intervalos de servicio y de cambio de aceite, versión de software, estado de conexión, última conexión, y — en Škoda — el último repostaje, la sesión de aparcamiento de pago en curso, los recordatorios de servicio, los temporizadores de salida y el modo de carga preferido, y más.
- **Sensores binarios:** puertas bloqueadas, puertas/ventanas/maletero/capó/techo solar abiertos, enchufe conectado, cargando, actualización OTA disponible, luces, vehículo en línea, temporizadores de salida, alarma.
- **Control:** bloquear/desbloquear, iniciar/detener climatización, iniciar/detener carga, calefacción de ventanas, temporizadores de salida, fijar SoC objetivo / temperatura / corriente máxima de carga, bocina y luces (con duración a elegir y opción de solo luces o también bocina), despertar, refrescar, buscar estaciones de carga, modo camping y ventilación activa (aireación del habitáculo Škoda sin calefacción) *(la disponibilidad depende de la marca y el modelo)*.
- **Rastreador de dispositivo:** posición GPS para el mapa de Home Assistant. Un sondeo que vuelve sin coordenadas conserva la última posición de aparcamiento conocida en vez de perderla.
- **Imágenes:** renders del vehículo donde la marca los proporciona.
- **Eventos, actualizaciones y calendarios (nuevo en 3.1.0):** una entidad `event` de push por vehículo (notificaciones del fabricante en el Registro + automatizaciones), una entidad **update** de firmware de solo lectura (estado OTA de Škoda — sin botón de instalación, el coche se actualiza solo) y **calendarios de planificación de carga + de servicio** que colocan los temporizadores y las fechas de vencimiento en una línea de tiempo.
- **Ajustes:** un deslizador de **intervalo de sondeo** por cuenta, en minutos, para que una automatización sondee más a menudo mientras conduces y afloje por la noche. Existe en todas las instalaciones, incluidas las entradas de portal de solo lectura.
- **12 idiomas:** los nombres de las entidades están totalmente traducidos al inglés, alemán, francés, español, italiano, neerlandés, polaco, checo, sueco, danés, noruego y finés.

> 💡 **Panel de Energía:** el sensor de energía cargada es `total_increasing`, así que añádelo directamente al **panel de Energía** de Home Assistant, o envuélvelo en un helper `utility_meter` para obtener totales de energía cargada diarios/mensuales. Usa el sensor acumulativo de **energía cargada (kWh)** para esto — no los sensores de eficiencia por 100 km (esos son promedios, no contadores).

### Servicios

La integración incluye **más de 30 llamadas de servicio** (`vag_connect.*`), muchas de ellas específicas de cada marca — *la disponibilidad depende de la marca y el modelo*. Entre ellas: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (combustión Audi), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (calefacción auxiliar / estacionaria — SEAT/CUPRA, Škoda y VW/Audi por un canal de órdenes bidireccional, donde el coche lo tenga equipado), `send_destination` (SEAT/CUPRA/Škoda) y `update_charging_settings` (SEAT/CUPRA), el `ask_assistant` de Škoda (ver más abajo), `set_location_target_soc` y `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send`, y el easter egg `show_vag`.

---

## evcc

[evcc](https://evcc.io) puede tomar el estado de carga, la autonomía y el estado de la carga de tu coche directamente de Home Assistant, para que la carga con excedente solar se planifique con la batería real y no con una estimación. Dentro de la integración no corre nada adicional: evcc lee la propia API REST de Home Assistant. La vía de **lectura** funciona en **todas las marcas**, incluidos los coches VW EU / portal de solo lectura. La vía de **escritura** (`chargeEnable`) solo funciona en un coche bidireccional (Audi o Škoda con un canal de órdenes vivo) y solo cuando evcc trata al propio coche como el punto de carga. Con un cargador inteligente de verdad, a evcc le basta la vía de lectura.

Las recetas de `evcc.yaml` listas para usar y la configuración inicial están en [docs/EVCC.md](docs/EVCC.md). Este conector está en **beta**.

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

## Live Activity de iOS — cuenta atrás de carga en la pantalla de bloqueo

Una **Live Activity** nativa (pantalla de bloqueo + Dynamic Island) que hace la cuenta atrás hasta que tu coche termina de cargar, con una barra de progreso del estado de carga. La integración ya expone una marca de tiempo **absoluta** de fin de carga (`sensor.*_charge_complete_eta` en todos los VE), así que iOS puede ir descontando la cuenta atrás por su cuenta — sin push por segundo.

**Importa el blueprint incluido** *"Live Activity — EV charging countdown (iOS)"* (`blueprints/automation/vag_connect/live_activity_charging_countdown.yaml`), elige los sensores de carga / SoC / fin de carga de tu vehículo y el servicio `notify.mobile_app_*` de tu móvil. Se inicia cuando empieza la carga, se refresca a medida que se mueven el ETA y el SoC, y se borra cuando la carga se detiene.

> 📱 **Requisitos:** la app Home Assistant Companion con **Live Activities** habilitadas (iOS 17.2+, HA Core 2026.7+). Las Live Activities son actualmente una función de **Labs** en la compilación **TestFlight** de la app — actívalas en Labs. Una Live Activity necesita un handshake de token entre la app y Home Assistant, así que tu móvil tiene que poder alcanzar HA (localmente o mediante una conexión remota) cuando empieza la carga. Esto se publica ya para que estés listo el día que salga de TestFlight. **iOS 2026.8 añade compatibilidad con iPad y una Live Activity rediseñada — el mismo blueprint maneja ambas.**

---

## Asistente de IA de Škoda («Laura») — nuevo en 3.0.0

El propio asistente de a bordo de MyŠkoda, **Laura**, está disponible dentro de Home Assistant.
Pregúntale por la autonomía, la carga y los viajes con el servicio `vag_connect.ask_assistant`
(devuelve una respuesta de texto que puedes enviar como notificación, reproducir por voz o usar
para bifurcar), o entrégala a un **agente de conversación** — el Assist integrado en modo LLM, u
OpenAI / Anthropic / Google / Ollama — como una herramienta que puede llamar y encadenar (pregunta
a Laura → luego `send_destination` al coche). Es de **solo lectura, consultiva y solo para Škoda**;
es una **beta**, así que se agradece tu opinión sobre la calidad de las respuestas.

La configuración, el disparador por voz («pregunta a Laura …») y automatizaciones de ejemplo listas
para usar — incluida *el coche llega a casa → recarga + precalienta + di la autonomía en voz alta* —
están en **[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Opciones (Configurar)

Desde **Ajustes → Dispositivos y servicios → VW Group Connect → Configurar** puedes ajustar:
intervalo de escaneo (también disponible en vivo como deslizador de intervalo de sondeo), S-PIN (más un S-PIN por vehículo cuando la cuenta tiene más de un coche), geocodificación inversa, **modo de solo lectura**, forzar climatización PPE (Audi), interruptores de push (MQTT/FCM/Audi-VW, todos beta opcional y desactivados por defecto), anulación de client-id, **`eu_data_act_auto_kickoff`** (activado por defecto), ocultar entidades vacías (activado por defecto), **ABRP** (habilitar + api_key + token de usuario, validados como un par), además de **añadir / eliminar** los canales de lectura suplementarios: `volkswagen.de` (beta), el portal de la EU Data Act, **Tibber** y el canal experimental de **móvil complementario**.

---

## Apoya este proyecto ❤️

Esto es un proyecto de una sola persona — y VW no lo pone fácil: cada cambio de backend significa días de ingeniería inversa para encontrar de nuevo una ruta que funcione. Esa persistencia es lo que lo mantiene vivo allí donde proyectos consolidados se han rendido. Si vale algo para ti, puedes apoyar el mantenimiento continuo a través de **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. ¡Gracias! 🙏

### Nuestros patrocinadores

<!-- SPONSORS:START -->
Be the first public sponsor to show up here, and thank you either way!
<!-- SPONSORS:END -->

_Esta lista se actualiza cada semana y muestra solo a los patrocinadores que eligieron ser públicos en GitHub Sponsors. A los patrocinadores privados nunca se les nombra aquí, solo se les cuenta, y les damos las gracias igual._

---

## Comunidad y soporte

Adónde acudir depende de lo que necesites:

- **Preguntas, ayuda con la configuración, ejemplos de panel, «¿esto es normal?»** → [GitHub Discussions](https://github.com/its-me-prash/vwgroup-connect-ha/discussions). Las preguntas generales de Home Assistant que no sean específicas de esta integración encajan mejor en el [foro de la comunidad de HA](https://community.home-assistant.io).
- **Un fallo, un error o un campo de la API desconocido** → abre una incidencia vía [New issue → choose a template](https://github.com/its-me-prash/vwgroup-connect-ha/issues/new/choose). El **Vehicle Data Scout** rellena gran parte del informe por ti. Un informe útil indica tu marca, región, versión de Home Assistant + de la integración, y si la misma acción funciona en la app oficial del fabricante — la lista de comprobación corta está en [`CONTRIBUTING.md`](CONTRIBUTING.md); cómo viaja un informe desde su presentación hasta la corrección está en [`docs/TRIAGE.md`](docs/TRIAGE.md).
- **Una vulnerabilidad de seguridad** → por favor, **no** abras una incidencia pública. Repórtala de forma privada a través de [GitHub Security Advisories](https://github.com/its-me-prash/vwgroup-connect-ha/security/advisories/new); el proceso está en [`SECURITY.md`](SECURITY.md).

### Qué esperar

Esto es un proyecto de una sola persona, mantenido en el tiempo libre. Las respuestas son **según disponibilidad** — a veces el mismo día, a veces más lentas cuando VW rompe algo y una corrección se salta la cola. No hay SLA, y no lo habrá. Cuanto más específico sea tu informe (registros saneados, diagnósticos censurados, pasos exactos), más rápido se resuelve. La norma de la casa, en versión corta: **sé cordial, sé específico, no pegues secretos — los parches y la paciencia llegan más lejos que las exigencias.**

### Cómo ayudar

No hace falta escribir código para hacer avanzar esto:

- **Presenta buenos informes de error** y adjunta diagnósticos censurados — una descarga del Scout suele ser todo lo necesario para mapear un campo nuevo.
- **Prueba en un coche real.** Varias marcas están implementadas pero a la espera de la primera confirmación en real — mira la [lista de probadores en real](CONTRIBUTING.md#live-testers-wanted).
- **Mejora las traducciones.** Los nombres de las entidades se distribuyen en 12 idiomas; se agradecen correcciones y ayuda con un idioma nuevo.
- **Envía un parche.** Un PR, un asunto — mira [`CONTRIBUTING.md`](CONTRIBUTING.md).

Todo el que ayuda recibe crédito en [`CONTRIBUTORS.md`](CONTRIBUTORS.md) y se le agradece por su nombre en las notas de la versión. Cómo se toman las decisiones — y quién tiene la última palabra en un proyecto de un solo mantenedor — está escrito en [`GOVERNANCE.md`](GOVERNANCE.md); las reglas básicas para participar están en [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## Contribuir

PRs bienvenidos, consulta [`CONTRIBUTING.md`](CONTRIBUTING.md). Las preguntas habituales están respondidas en [docs/FAQ.md](docs/FAQ.md). El **Vehicle Data Scout** convierte campos desconocidos de la API en un informe de error precargado de un solo clic, así que puedes ayudar a mejorar la cobertura sin leer código.

## Licencia

[GNU AGPL v3.0-or-later](LICENSE) para el código de la integración. Atribución obligatoria + condiciones de nombre/marca registrada en el uso/fork: ver [`ATTRIBUTION.md`](ATTRIBUTION.md). Atribuciones de código abierto upstream en [`NOTICE.md`](NOTICE.md).
