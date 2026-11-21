# Propuesta técnica de la Fase 1.0B: producto mínimo en `app/`

**Estado actualizado (2026-11-20): el propietario aprobó D-1 a D-4, D-6 y D-7 y autorizó los Bloques B0 y B1, que están COMPLETADOS (B1 cerrado el 2026-11-21 con el CSV oficial de BIP-340; ver la interacción 27 del registro de IA) (ver `docs/decisions.md`, sección «Fase 1.0B, Bloques B0 y B1»). D-5 sigue pendiente. B2 a B6 NO están autorizados; el §9 detalla B2. El texto de las secciones 1 a 8 conserva la propuesta original.** Versión original: «PROPUESTA pendiente de aprobación; no se implementó nada». Parte de la evidencia de [phase-1.0A-closure.md](phase-1.0A-closure.md) y respeta [nip46-security-design.md](nip46-security-design.md) y [nip46-implementation-plan.md](nip46-implementation-plan.md) (de los que esta propuesta es una **versión recortada y ordenada por riesgo**). Etiquetas: **[D]** propuesta; **[LAB]** observado en la Fase 1.0A; **[PDF]** alcance indicado por el propietario.

> **Actualización de avance (2026-11-21).** B0 y B1 completados; **B2 y B3 implementados y verificados localmente** (O-17; detalle y resultados en `docs/decisions.md`, sección «Fase 1.0B, Bloques B2 y B3»); **B4 preparado y pendiente de una única autorización operativa** (`docs/phase-1.0B-B4-gate.md`; D-5 sin decidir). B5 y B6 **no** están autorizados. Las decisiones B2-1 a B2-7 se aplicaron según su recomendación. Este documento no se reestructura: es la propuesta original.

> **Actualización de avance (2026-11-21, cierre local).** B2 y B3 verificados (P-33 cumplida); D-4 reemplazada por **D-8 (JWT)**; **B5 (interfaz) implementada y probada con un navegador real**; **B6 verificado solo en local** (E2E de navegador y de Docker con NDK 2.12.2 real); **B4 sigue preparado y sin ejecutar** (`docs/phase-1.0B-B4-gate.md`): ni B4 ni la validación real de B6 se dan por completados sin evidencia de una sesión autenticada en Stacker News.

> **Actualización de avance (2026-11-21, cierre de jornada).** **B4 se ejecutó: PASS con observaciones** (`docs/phase-1.0B-B4-gate.md`, `docs/decisions.md`). B6 sigue pendiente de la validación real y de la reproducibilidad desde un clon limpio. Continuidad: `docs/handoff-2026-11-21.md`.

## 1. Alcance (solo lo necesario) y exclusiones

Incluye únicamente las diez capacidades pedidas **[PDF]**: (1) clave Nostr, crear o ingresar; (2) firmante NIP-46 en Python; (3) conexión al relay validado; (4) URI `bunker://`; (5) API FastAPI para controlar el firmante y consultar solicitudes pendientes; (6) interfaz HTML, CSS y JavaScript sin frameworks; (7) aprobación explícita de `connect`; (8) validación y aprobación explícita del `sign_event` de autenticación; (9) firma y respuesta NIP-46; (10) demostración real de inicio de sesión en Stacker News.

**Excluido de forma deliberada [D]:** SQLite y persistencia de conexiones (salvo la decisión D-3), varios clientes o relays, `nostrconnect://`, `auth_url`, métodos `nip04_*`/`nip44_*`, firma de otros `kind`, concesiones persistentes, métricas, rotación de claves, navegador sin interfaz y cualquier funcionalidad no listada.

## 2. Decisiones que el propietario debe tomar antes de escribir código (Bloque B0)

| # | Decisión | Recomendación [D] | Si no se decide |
|---|---|---|---|
| D-1 | **Dependencias** de ejecución: `coincurve==21.0.0`, `cryptography==50.0.2`, `websockets==17.4` (con `cffi` y `pycparser` transitivos), las mismas versiones validadas en el laboratorio. `pydantic` ya llega con FastAPI. Para pruebas asíncronas se usa el plugin `anyio` ya instalado (sin paquete nuevo). Propósito, alternativas, licencias y mantenimiento: [plan §2.5](nip46-implementation-plan.md). Actualizar `constraints.txt` y ejecutar la comprobación del Dockerfile. | Aprobar | No se puede empezar el Bloque B1 |
| D-2 | Nombre de la capa de configuración (`config/` frente a `core/`, pendiente desde D8/O-3): se resuelve al crear la primera variable. | Un único módulo `app/config.py` (variables de entorno validadas, falla al arrancar si falta una obligatoria) | Bloque B3 sin variables |
| D-3 | **Persistencia de la clave.** (a) Solo en memoria: se pierde al reiniciar; mínimo y sin riesgo de almacenamiento. (b) Cifrada en reposo (AEAD con clave externa por variable de entorno) en un archivo o SQLite: exige esquema aprobado en `docs/decisions.md` (P-07) y bloqueo con hashes (alternativa B, L7) antes de manejar claves. | **(a)** para 1.0B; (b) solo si el PDF lo exige | Se asume (a) |
| D-4 | **Autenticación de la API local.** `AGENTS.md` §3 y §7 prevén JWT para la API local cuando exista; añadiría `PyJWT` u otra dependencia. Alternativa mínima: un token de operador aleatorio generado al arrancar y mostrado una vez en la terminal (encabezado `Authorization`, comparación en tiempo constante) y la API enlazada a `127.0.0.1`. | Token de operador en el Bloque B3; JWT solo si el PDF lo pide | Token de operador |
| D-5 | **Cuenta de Stacker News para la demostración (B4/B6).** Una identidad desechable nueva **crea una cuenta real** y queda huérfana al descartarse la clave [LAB: solo `/signup` crea usuarios]. Alternativa: una cuenta de prueba designada por el propietario. Revisar las condiciones de uso. | Decisión expresa del propietario | No se ejecuta la demostración |
| D-6 | Fijar el digest de la imagen base (`python:3.12-slim`, D3) y valorar bloqueo con hashes **antes** de manejar claves reales. | Fijar el digest antes del B4 | Riesgo medio ya registrado |
| D-7 | Relay y TLS de la demostración: **`wss://relay.primal.net:443`**, opción `RELAY_TLS_GROUPS=X25519` conservando la verificación completa **[LAB: A1 GO]**. | Aprobar | — |

## 3. Arquitectura mínima

Se mantienen los principios del plan §3.1: el código de protocolo **no importa FastAPI**; las dependencias fluyen hacia el dominio; un módulo solo si tiene una responsabilidad concreta; en memoria; una sola interfaz (`RelayTransport`) para poder probar sin red.

| Módulo `app/…` | Responsabilidad | Origen en el laboratorio | Estado |
|---|---|---|---|
| `nostr/keys.py` | `Keypair` opaco (`repr` sin secreto): clave pública, firma Schnorr, ECDH sin hash; crear o ingresar (hex o `nsec`) | `lab_common/nostr.py` | **Adaptar** (tipado completo, errores de dominio, validación estricta) |
| `nostr/event.py` | Evento NIP-01: serialización, `id`, firma, verificación, formato estricto | `lab_common/nostr.py` | **Adaptar**; falta el caso de caracteres de control (Y-9) |
| `nostr/nip44.py`, `nostr/nip04.py` | NIP-44 v2 (vectores oficiales) y NIP-04 **solo para descifrar** | `lab_common/nip44.py`, `nip04.py` | **Adaptar y portar las pruebas** |
| `nostr/nip46.py` | Modelos estrictos de solicitud y respuesta, métodos admitidos, construcción de `bunker://` con `relay` obligatorio | `lab_real/signer.py` (parte) | **Escribir** sobre el comportamiento observado |
| `nostr/relay.py` | `RelayTransport` (Protocolo) y `WebsocketRelay`: suscribir, publicar, `OK`/`EOSE`/`AUTH`/`CLOSED`, tiempos acotados, un reintento explícito, TLS verificado con `RELAY_TLS_GROUPS` opcional | `lab_real/signer.py` (`_session`), `tls.py` | **Escribir/adaptar** |
| `services/policy.py` | Las 11 comprobaciones puras de `kind 27235` con perfil configurable (origen, `content`, ventana); **conservar la verificación de `id` y `pubkey` opcionales** de la plantilla (hallazgo F-5) | `lab_real/policy.py` | **Reutilizar casi tal cual** |
| `services/connections.py` | Estados Emitida → Pendiente → Activa; secreto de un solo uso (solo hash), vida acotada; concesión de un solo uso para firmar | `lab_real/signer.py` (parte) | **Adaptar** |
| `services/signer.py` | Valida el evento de transporte (firma, `id`, ventana, repetición **antes** de descifrar), descifra NIP-04/NIP-44, despacha `connect`/`get_public_key`/`sign_event`/`ping`, **responde siempre NIP-44**; las decisiones llegan por **solicitudes pendientes** resueltas desde la API (no por TTY) | `lab_real/signer.py` | **Adaptar** (cambia la E/S de aprobación) |
| `api/…` | Validación y delegación; autorización en cada endpoint (D-4); errores genéricos | — | **Escribir** |
| `main.py` | Arranque y parada ordenada del firmante en el `lifespan` (con evento de cierre, F-2) | — | **Ampliar** |
| `static/` (HTML, CSS, JS) | Interfaz del operador | — | **Escribir** |

**API mínima [D]** (todas exigen el token de operador; solo `127.0.0.1`):
`POST /api/identity` (crear) · `PUT /api/identity` (ingresar; el secreto nunca se devuelve) · `GET /api/identity` (solo clave pública) · `POST /api/signer/start` y `/stop` · `GET /api/signer` (estado) · `POST /api/connections` (emite la URI `bunker://`, **se devuelve una sola vez**) · `GET /api/requests` (pendientes, con la estructura validada y el resultado de cada comprobación) · `POST /api/requests/{id}/approve` y `/deny`.

**Interfaz [D]:** una página con identidad, arranque/parada, URI (mostrar y copiar, una vez), y lista de solicitudes pendientes con aprobar/denegar; `textContent` (nunca `innerHTML` con datos no confiables), CSP restrictiva, sin frameworks. Para `sign_event` muestra `kind`, `u`, `content`, antigüedad, forma del reto (nunca el reto completo) y las comprobaciones; si alguna falla, **no ofrece aprobar**.

**Reglas de seguridad que se traspasan tal cual del laboratorio:** denegación por defecto; solo `kind 27235`; verificación previa de `id` y `pubkey` de la plantilla; reto de un solo uso; ventana ±120 s; tope de firmas por sesión; sin edición del evento; autoverificación de la firma antes de responder; errores genéricos hacia el cliente; evidencia y registros sin claves, URI, retos ni descifrados.

## 4. Reutilización: qué se copia, qué se escribe y qué no entra

- **Se copia y adapta** (con sus pruebas): criptografía y eventos (`lab_common`), política de `kind 27235` y máquina de estados del firmante (`lab_real`).
- **Se escribe de nuevo:** modelos NIP-46 estrictos, cliente de relay productivo, servicio de solicitudes pendientes, API, interfaz, configuración, parada ordenada.
- **No entra en el producto:** aprobación por TTY y guion, modo observación, proxy, controladores de compuertas, sonda de relay, relay local, simuladores, evidencia JSONL de laboratorio. Se conservan en `lab/` como **arnés de regresión** y de procedimientos (P-18).
- El código de `app/` **no importa** de `lab/`.

## 5. Bloques de desarrollo, pruebas y criterios de aceptación

Cada bloque cierra con `pytest`, `git diff --check`, `README`/`docs/decisions.md` al día y registro de IA (LAB/DEV/DOC), y **no avanza sin autorización expresa**. Las pruebas son deterministas, sin red real (relay falso en proceso) y con claves generadas para la prueba. Orden elegido para llegar **cuanto antes a un inicio de sesión real** con el menor trabajo previo: núcleo → firmante sin interfaz → API → **demostración real vía API** → interfaz → demostración final con la interfaz.

| Bloque | Contenido | Criterios de aceptación (todos obligatorios) |
|---|---|---|
| **B0** Decisiones | D-1 a D-7; dependencias; `constraints.txt` | Decisiones registradas como aprobadas en `docs/decisions.md`; `pip check` limpio; construcción Docker con el guardián de `constraints.txt` correcta; 5 pruebas existentes en PASS |
| **B1** Núcleo Nostr (T2 a T5) | `keys`, `event`, `nip44`, `nip04` (entrante), `nip46` | Vectores oficiales BIP-340 y **todos** los casos válidos e inválidos de NIP-44 (más los tres de prefijo extendido registrados como pendientes por checksum, P-14); serialización NIP-01 con casos de escape; NIP-04 solo descifra; `repr` de `Keypair` sin secreto; claves públicas inválidas rechazadas; `mypy`/tipado sin `Any` injustificado; cobertura de rutas de error |
| **B2** Firmante sin interfaz (T6, T8, T9) | `relay`, `policy`, `connections`, `signer` con aprobaciones por método Python | Pruebas contra relay falso en proceso con un cliente doble que imita a NDK (`connect` NIP-04 con secreto, `get_public_key`, `sign_event`); `connect` denegado por defecto y de un solo uso; `sign_event` solo `27235`, solo con aprobación; 11 comprobaciones de política con los casos de E8; repetición y vencimiento rechazados; respuestas siempre NIP-44; **regresión con el arnés de laboratorio**: E1 a E3 y E8 contra el firmante productivo con NDK 2.12.2 en PASS; cierre ordenado con evento de cierre (F-2); sin secretos en registros (prueba con `caplog`) |
| **B3** API y claves (T7 mínimo, T10) | Identidad en memoria (crear/ingresar), endpoints, autenticación (D-4), `lifespan` | Cada endpoint exige autorización y deniega por defecto; la URI se devuelve **una sola vez**; el secreto de la clave no aparece en ninguna respuesta ni registro; validación estricta de entradas (Pydantic); errores genéricos; pruebas con `TestClient`; flujo completo local por API con el cliente NDK del laboratorio: `connect` aprobado, `sign_event` válido firmado y verificado (con el origen de laboratorio) y uno inválido rechazado |
| **B4** Demostración real vía API (T13; **Compuerta C**, requiere D-5 y autorización por compuerta con ventana) | Inicio de sesión real con identidad desechable, solo con la API (sin interfaz) | Evidencia de nivel «login completo»: Stacker News acepta el evento firmado y establece sesión; **una** firma aprobada; sin secretos en la evidencia; limpieza; informe que distingue observado, inferido e hipótesis. Cualquier otro resultado se documenta sin repetir |
| **B5** Interfaz | HTML, CSS y JS sin frameworks | Sin `innerHTML` con datos no confiables; CSP y cabeceras de seguridad comprobadas; URI mostrada una vez; no se ofrece aprobar un `sign_event` con comprobaciones fallidas; prueba manual local con el cliente NDK del laboratorio y con un navegador (sin tráfico externo) |
| **B6** Demostración final y documentación | Repetición del inicio de sesión desde la interfaz (**compuerta propia**); README reproducible | Un tercero puede instalar, configurar, ejecutar, probar y repetir la demostración desde cero; evidencia fechada con los pasos y el resultado |

## 6. Primer bloque recomendado: **B0 seguido de B1**

**Por qué:** es el requisito de todo lo demás, no tiene efectos externos, se prueba por completo con vectores oficiales y deja listo el terreno del bloque que desbloquea el flujo completo (B2). B0 son decisiones y una actualización de dependencias; B1 es el núcleo criptográfico y de formato.

**Criterios de aceptación del primer bloque (B0 + B1):**
1. D-1 a D-3 aprobadas y registradas; `constraints.txt` actualizado, `pip check` limpio y la construcción Docker correcta.
2. `app/nostr/{keys,event,nip44,nip04,nip46}.py` con tipado completo, errores de dominio y sin importar FastAPI.
3. **Todos** los vectores oficiales BIP-340 y NIP-44 (válidos e inválidos) en PASS, con el archivo de vectores leído de una ruta local verificada por SHA-256 y omisión explícita si falta (P-16), y una prueba de interoperabilidad con los mensajes capturados del laboratorio (NIP-44 y NIP-04 entrante).
4. `Keypair`: `repr`/`str` sin secreto, comparación en tiempo constante, entrada hex o `nsec` validada y rechazo de claves inválidas.
5. Construcción y análisis de `bunker://` con `relay` obligatorio y secreto de ≥ 128 bits; pruebas de rutas de error (entradas mal formadas, longitudes límite, firmas inválidas).
6. 5 pruebas existentes más las nuevas en PASS; `git diff --check` y `git status` reportados; sin secretos ni claves reales en pruebas.

## 7. Riesgos de la Fase 1.0B y mitigación

| Riesgo | Mitigación |
|---|---|
| La respuesta de Stacker News a una **firma válida** no se ha observado (Y-8: caducidad del reto; sesión; cuenta) | Ejecutar B4 pronto, vía API, antes de invertir en la interfaz; abortar y documentar sin reintentos |
| La demostración crea una cuenta real huérfana (D-5) | Decisión expresa del propietario antes de B4 |
| Diferencias entre NDK en Node (laboratorio) y el navegador de producción (Y-5) | La observación real de la Compuerta B ya coincidió; B4 es la comprobación definitiva |
| Manejo de claves reales o persistencia | D-3 en memoria; (b) solo con esquema aprobado y bloqueo con hashes |
| Parada del firmante sin evidencia de cierre (F-2) | Criterio de aceptación de B2 |
| Reintentos o `AUTH` del relay | Un intento explícito; `AUTH` se registra y detiene salvo decisión expresa |
| Alcance creciente | Cada bloque exige autorización; lo no listado en §1 queda fuera |

## 8. Preguntas abiertas para el propietario

1. ¿Se aprueban D-1 a D-7, en particular D-3 (clave en memoria) y D-4 (token de operador o JWT)?
2. ¿Se aprueba el orden de los bloques (demostración real por API antes de la interfaz)?
3. ¿Qué cuenta de Stacker News se usará en B4 y se aceptan sus condiciones (D-5)?
4. ¿Se versiona `lab/` y qué evidencia sanitizada se conserva en el repositorio (hallazgo F-8)?
5. ¿Se autoriza exportar las transcripciones de la Fase 1.0A para cerrar la 1.0A.3?

## 9. Propuesta detallada del Bloque B2 (firmante NIP-46 sin interfaz) — **implementada y verificada localmente el 2026-11-21 (O-17)**

**Objetivo.** Un firmante NIP-46 completo **dentro del proceso**, sin API ni interfaz, que reciba solicitudes por un relay, aplique la política y entregue las decisiones humanas a través de **solicitudes pendientes** (en B3 las resolverá la API). Se prueba con un relay falso en proceso, un cliente doble que imita a NDK y, como regresión, con el cliente NDK 2.12.2 del laboratorio contra un relay **local**. No se conecta a ningún relay público ni a Stacker News.

**Estado de partida (B0 y B1):** claves, eventos, NIP-44, NIP-04 entrante, mensajes NIP-46 y URI `bunker://` ya implementados y probados (253 pruebas, incluido el CSV oficial completo de BIP-340; 100 % de líneas y ramas del código de `app/`).

### 9.1 Subbloques y módulos

| Subbloque | Módulo `app/…` | Contenido | Origen en el laboratorio |
|---|---|---|---|
| B2a | `services/policy.py` | Las 11 comprobaciones puras de `kind 27235` con perfil configurable (origen `https://stacker.news`, `content`, ventana ±120 s); verifica `id` y `pubkey` opcionales de la plantilla (hallazgo F-5); devuelve el resultado de **cada** comprobación | `lab_real/policy.py` (casi tal cual) |
| B2a | `services/connections.py` | Estados Emitida → Pendiente → Activa; secreto de un solo uso (solo su SHA-256), TTL, vida de la conexión; clientes desconocidos solo pueden enviar `connect`; revocación | `lab_real/signer.py` (parte) |
| B2a | `services/approvals.py` | Registro **en memoria** de solicitudes pendientes (`connect`, `sign_event`) con `id` opaco, estructura validada para mostrar, caducidad y resolución por `approve`/`deny` (futuros de `asyncio`); es lo que consumirá la API de B3 | nuevo (sustituye al aprobador TTY) |
| B2b | `services/signer.py` | `SignerService`: valida el evento de transporte (`kind 24133`, etiqueta `p`, ventana, `id` y firma **antes** de descifrar, ids vistos), descifra NIP-04/NIP-44, despacha `connect`/`get_public_key`/`sign_event`/`ping`, **responde siempre NIP-44** firmado con la clave de transporte; `sign_event` solo con política OK, aprobación humana y concesión de un solo uso; tope de firmas; autoverificación de la firma; errores genéricos; **`stop(reason)` ordenado que deja evidencia de cierre** (F-2) | `lab_real/signer.py` |
| B2b | `services/audit.py` | Registro de auditoría con **lista blanca** de eventos y campos que rechaza claves, URI, retos y descifrados (la idea de `lab_real/evidence.py`), con salida a `logging` | `lab_real/evidence.py` (idea) |
| B2c | `nostr/relay.py` | `RelayTransport` (Protocolo) y `WebsocketRelay`: un intento de conexión, tiempos acotados, `REQ`/`EVENT`/`EOSE`/`OK`/`CLOSED`/`AUTH` (se registra y **detiene**, sin responder), TLS verificado con `RELAY_TLS_GROUPS` opcional, `ws://` solo con bandera explícita para el relay local de pruebas; más un relay falso para pruebas en `tests/` | `lab_real/signer.py` (`_session`), `tls.py`, `probe.py` |
| B2d | `lab/` (no producto) | Arnés de regresión: imagen del producto + relay y cliente NDK locales en una red interna; un ejecutor mínimo **dentro de `lab/`** que importa `app.*` (el sentido permitido: el laboratorio usa el producto, nunca al revés) con aprobación por guion **solo para el relay del laboratorio** | `lab/real/compose.rehearsal.yaml`, `run_lab.py` |

Configuración nueva en `app/config.py` (todas con valor por defecto no sensible y validación): `SERVICE_ORIGIN` (`https://stacker.news`), ventana de tiempo, TTL del secreto y de la conexión, tope de firmas por sesión. **Sin dependencias nuevas.** El token de operador (D-4) **no** forma parte de B2: es de B3.

### 9.2 Decisiones que el propietario debería tomar antes de B2

| # | Decisión | Recomendación [D] |
|---|---|---|
| B2-1 | `app/nostr/relay.py` hace E/S de red; hoy `tests/test_architecture.py` prohíbe E/S en todo `app/nostr/`. | Permitir `websockets`, `asyncio` y `ssl` **solo** en `relay.py` y actualizar la prueba para vigilar que el resto del núcleo siga sin E/S (`AGENTS.md` §4 sitúa el transporte dentro de la capa de protocolo) |
| B2-2 | Origen del perfil de Stacker News. | Valor por defecto `https://stacker.news` (observado en la Compuerta B) configurable por `SERVICE_ORIGIN` |
| B2-3 | Alcance de cada aprobación de firma. | **Una sola autenticación** (P-15): una aprobación = una firma de un reto |
| B2-4 | Caducidad de una solicitud pendiente sin resolver. | 120 s, igual que el laboratorio; vencida = denegada |
| B2-5 | Reintentos de conexión al relay. | **Ninguno automático** en B2 (un intento); reconexión controlada se decide en B3 |
| B2-6 | Auditoría. | Lista blanca propia en memoria y `logging`; **sin SQLite** (D-3) |
| B2-7 | Aprobación por guion en el arnés. | Solo con hosts del laboratorio; el producto nunca la admite |

### 9.3 Pruebas y criterios de aceptación de B2 (todos obligatorios)

1. **Política**: las 11 comprobaciones con los casos de E8 (origen, `content`, método, etiqueta extra, `kind`, antigüedad, futuro, reto inválido, orden de etiquetas, repetición) y el evento real observado (362 B, seis campos) sin fallos.
2. **Conexión**: `connect` desconocido solo con secreto válido, vigente y **no usado**; secreto de un solo uso aunque se deniegue; denegado por defecto y sin aprobación humana no se activa; método antes de `connect` = `unauthorized`; conexión que caduca.
3. **Transporte**: eventos con firma o `id` inválidos, ventana excedida, `p` ajeno o repetidos **no se descifran ni responden**; `connect` NIP-04 inicial **se descifra** y se responde en NIP-44; NIP-04 nunca se usa para cifrar.
4. **`sign_event`**: solo `kind 27235`; política OK **y** aprobación explícita; concesión de un solo uso; tope de firmas; el reto repetido se rechaza; el evento firmado se autoverifica y conserva etiquetas, contenido y `created_at` sin cambios.
5. **`get_public_key`** a un cliente activo nunca devuelve error (P-19); los demás errores son genéricos y estables.
6. **Relay**: un intento, tiempos acotados, `AUTH`/`CLOSED` registrados y detención sin autenticar, un solo `EVENT` por respuesta, TLS verificado probado con una CA desechable (certificado no confiable rechazado), `ws://` rechazado sin la bandera.
7. **Cierre ordenado**: `stop()` deja evidencia de cierre con motivo y recuento de firmas; probado con tiempo, interrupción y error.
8. **Secretos**: ninguna clave, URI, reto, texto descifrado ni carga cifrada en registros, errores ni auditoría (pruebas con `caplog` y escaneo).
9. **Regresión con el laboratorio**: E1 a E3 y la variante de E8 (11 solicitudes) con NDK 2.12.2 contra el firmante **del producto** en PASS, solo con el relay local y red interna; **ninguna conexión externa**.
10. `mypy --strict` sin incidencias (herramienta temporal), cobertura de líneas y ramas del código nuevo ≥ 95 %, `git diff --check` limpio, `app/` sin importar `lab/`, dependencias sin cambios.

### 9.4 Fuera de B2
API, token de operador, interfaz, conexión a `relay.primal.net` o a Stacker News, persistencia, JWT, cuentas, más relays y cualquier compuerta. Cada uno exige su propio bloque o autorización.

### 9.5 Riesgos de B2
La regresión con NDK puede revelar diferencias no vistas en el laboratorio (se resuelven con el firmante de referencia como comparación); la gestión de futuros de `asyncio` y de cancelaciones exige pruebas de carrera; el reloj se inyecta (`now`) para que las pruebas de tiempo sean deterministas.
