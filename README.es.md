<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Una sola integración de Home Assistant para las siete marcas del Grupo Volkswagen — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW EE. UU./Canadá</strong><br>
  <em>Acceso directo a la API, multicanal con conmutación automática, sin intermediarios.</em>
</p>

<p align="center">
  <a href="https://github.com/sponsors/its-me-prash"><img src="https://img.shields.io/badge/%E2%9D%A4%20Sponsor-ec6cb9?logo=github-sponsors&logoColor=white" alt="Sponsor this project"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg" alt="HACS Default"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?include_prereleases" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%20v3-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  🌍 <a href="README.md">English</a> · <a href="README.fr.md">Français</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Nota sobre el cambio de nombre
> Antes se publicaba como **`vag-connect-ha`** (VAG = Volkswagen AG, la abreviatura habitual en la zona DACH).
> Resulta que esa abreviatura suena *bastante* distinta para quien habla inglés 😅
>
> **Lo que sigue funcionando igual que antes**: todas las entidades (p. ej. `sensor.audi_q4_battery_soc`),
> todas las llamadas a servicios (`vag_connect.lock`, `vag_connect.show_vag`, etc.), todas las automatizaciones,
> la instalación por HACS — **nada se rompe**. Cambia el nombre de marketing/visible; las tripas del código
> quedan intactas. Consulta [`MIGRATION.md`](MIGRATION.md).
>
> Mil gracias a las comunidades de **Home Assistant UK** y **HA Ideas, Projects and Solutions**
> por el aviso — en especial a **Si Gregory**, **Ben Johnson** y **Evets David**.
>
> Y una mención especial para **Jordan Waeles**, cuyo comentario `show_vag()` es ahora un easter egg
> oficialmente soportado en esta integración (servicio `vag_connect.show_vag`, ver CHANGELOG v2.2.3).

---

## ¿Qué es esto?

**VW Group Connect es una integración de [Home Assistant](https://www.home-assistant.io) que lleva los datos y el control del coche conectado a tu hogar inteligente para las siete marcas del Grupo Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche y VW EE. UU./Canadá — más Bentley (solo lectura), desde una única entrada de configuración.**

Pone a tu disposición el estado de la batería y la carga, la autonomía, el cuentakilómetros, la climatización, puertas y ventanas, la ubicación y mucho más, y —donde el backend de la marca todavía lo permite— envía órdenes remotas como bloquear/desbloquear y control de climatización y carga. Para seguir funcionando pese a los cambios de la API de Volkswagen de 2026, habla **varios canales y conmuta automáticamente** cuando uno queda bloqueado: los backends nativos de cada marca, el portal de datos del vehículo de solo lectura del **EU Data Act**, un canal web opcional de `volkswagen.de` y un inicio de sesión **sin contraseña** y duradero para los vehículos Car-Net más antiguos. Convive sin problemas **junto a [evcc](https://evcc.io)** y no necesita **ninguna dependencia de PyPI**.

> 🎉 **Ya disponible directamente en HACS** — sin repositorio personalizado.

---

## Lo más destacado

- **Las 7 marcas del Grupo VW, incl. Porsche y VW EE. UU./Canadá** en una sola integración — el portal del EU Data Act *excluye* estructuralmente a Porsche, así que las herramientas que solo usan el portal nunca podrán cubrirlo.
- **Control bidireccional** donde la marca lo permite (bloquear/desbloquear, climatización, carga, SoC objetivo) — no solo lecturas.
- **Opción de inicio de sesión sin contraseña** (navegador/código de dispositivo) — no se guarda ninguna contraseña en Home Assistant.
- **Multicanal con conmutación automática** — nativo de la marca → portal del EU Data Act → web opcional de vw.de → Car-Net duradero. Que se caiga un canal no deja tus datos a oscuras.
- **Resiliente por diseño** — conserva los últimos valores conocidos durante las caídas del portal, filtra los valores centinela falsos de «sin lectura» y nunca deja que el cuentakilómetros vaya hacia atrás.
- **Localizador GPS**, más de 100 entidades en 11 plataformas, más de 20 llamadas a servicios, varios vehículos por cuenta.
- **Vehicle Data Scout** — detecta automáticamente los cambios de la API y ofrece un informe de error con un solo clic. **Quality Scale: Platinum.**

---

## Estado por marca

| Marca | Control | Datos | Notas |
|---|---|---|---|
| **Audi** | ✅ Bidireccional | ✅ Completo | backend myAudi |
| **Škoda** | ✅ Bidireccional | ✅ Completo | backend nativo de Škoda |
| **Porsche** | ✅ Bidireccional | ✅ Completo | Porsche Connect |
| **VW EE. UU./CA** | ✅ Bidireccional | ✅ Completo | nube de VW NA |
| **VW EU** | ⚠️ Car-Net duradero (modelos antiguos) | ✅ EU Data Act + vw.de (beta) | coches ID/MEB más nuevos: solo lectura vía portal |
| **CUPRA / SEAT** | ⚠️ Limitado | ✅ EU Data Act | backend de marca bloqueado por VW desde 2026 |
| **Bentley** | ⏳ A la espera de pruebas en vivo | ✅ Inicio de sesión + lectura | My Bentley — funciona sobre la plataforma/tenant de Audi |

> Nota honesta: en 2026 Volkswagen puso partes de su API tras atestación de dispositivo. Esta integración da un rodeo alrededor de ese muro donde puede (inicio de sesión Car-Net duradero, portal del EU Data Act, web de vw.de) y es transparente sobre lo que cada canal puede y no puede hacer.

---

## Limitaciones conocidas

Algunas cosas son **estructurales** — vienen de cómo funcionan los backends de Volkswagen en 2026, no de la integración, y ningún ajuste las arregla:

- **Los coches de la familia MEB / ID son de solo lectura** (ID.3 / ID.4 / ID.5 / ID.7, Enyaq, Born, Q4 e-tron). Las órdenes remotas —bloqueo, climatización, carga— **no están disponibles** para estos coches: la vía de comandos Car-Net duradera que usamos no los reconoce (responde «Unknown user») y el backend MEB de VW no expone nada equivalente. Aun así obtienes la telemetría a través del portal del EU Data Act — solo que sin control. La configuración detecta esto y crea una **entrada de solo lectura** en lugar de fallar, así que es un límite conocido, no uno silencioso.
- **Las órdenes remotas de CUPRA / SEAT están bloqueadas por VW.** El acceso a los servicios online (OLA) de estas marcas se revocó del lado del servidor en 2026 (HTTP 403); volver a iniciar sesión o subir la versión de la app no lo recupera. Los datos siguen fluyendo por el portal del EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Los datos del portal del EU Data Act son escasos y varían según el coche.** Hoy VW publica solo una porción de los campos (a menudo cuentakilómetros + bloqueo + carga, a veces mucho más). Eso se irá ampliando con el tiempo a medida que VW expanda el portal de cara al plazo de septiembre de 2026 — los campos que hoy aparecen como `unknown` pueden rellenarse solos, sin que haya que cambiar nada. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Instalación

**Vía HACS (recomendado):**

1. Abre **HACS** en Home Assistant.
2. Busca **«VW Group Connect»** e instálalo.
3. Reinicia Home Assistant.
4. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → VW Group Connect** y sigue el flujo de inicio de sesión.

<sup>Recién fusionado en el repositorio por defecto de HACS — si todavía no aparece en la búsqueda, dale un poco de tiempo al índice de HACS para que se actualice, o añade mientras tanto `its-me-prash/vwgroup-connect-ha` como repositorio personalizado.</sup>

**Opciones de inicio de sesión** (elige la que admita tu coche/marca):
- **Navegador / código de dispositivo (sin contraseña)** — inicia sesión en el móvil o el portátil y aprueba el dispositivo; no se guarda ninguna contraseña. (Audi, Škoda, SEAT, CUPRA.)
- **Correo + contraseña** — necesario para Volkswagen EU y Porsche.
- **Portal del EU Data Act** — alternativa de solo lectura para todas las marcas.

---

## Lo que obtienes

- **Sensores:** SoC de la batería, autonomía (eléctrica / combustión / total), nivel de combustible, cuentakilómetros, temperaturas, potencia/velocidad/tipo de carga, objetivo de carga, estadísticas de viaje y acumulados de por vida, intervalos de servicio y de cambio de aceite, versión del software, estado de conexión, última conexión y más.
- **Sensores binarios:** puertas bloqueadas, puertas/ventanas/maletero/capó/techo solar abiertos, cable enchufado, cargando, actualización OTA disponible, luces, vehículo en línea, temporizadores de salida, alarma.
- **Control:** bloquear/desbloquear, iniciar/detener climatización, iniciar/detener carga, calefacción de ventanas, temporizadores de salida, fijar SoC objetivo / temperatura / corriente máxima de carga, claxon y luces, despertar, actualizar, buscar puntos de carga *(la disponibilidad depende de la marca y el modelo)*.
- **Localizador:** posición GPS para el mapa de Home Assistant.
- **Imágenes:** renders del vehículo cuando la marca los proporciona.

> 💡 **Panel de energía:** el sensor de energía cargada es `total_increasing`, así que añádelo directamente al **panel de energía** de Home Assistant, o envuélvelo en un ayudante `utility_meter` para obtener totales de energía cargada diarios/mensuales. Usa para esto el sensor acumulado de **energía cargada (kWh)** — no los sensores de eficiencia por 100 km (esos son promedios, no contadores).

---

## Apoya este proyecto ❤️

Este es un proyecto de una sola persona — y VW no se lo pone fácil: cada cambio de backend supone días de ingeniería inversa para volver a encontrar una vía que funcione. Esa constancia es lo que lo mantiene vivo donde proyectos consolidados se han rendido. Si tiene algún valor para ti, puedes apoyar el mantenimiento continuo a través de **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. ¡Gracias! 🙏

---

## Cómo contribuir

Los PR son bienvenidos — consulta [`CONTRIBUTING.md`](CONTRIBUTING.md). El **Vehicle Data Scout** convierte los campos desconocidos de la API en un informe de error precompletado con un solo clic, así que puedes ayudar a mejorar la cobertura sin leer código.

## Licencia

[GNU AGPL v3.0-or-later](LICENSE) para el código de la integración. Atribución obligatoria + condiciones de nombre/marca al usarlo o hacer fork: consulta [`ATTRIBUTION.md`](ATTRIBUTION.md). Atribuciones de código abierto de terceros en [`NOTICE.md`](NOTICE.md).