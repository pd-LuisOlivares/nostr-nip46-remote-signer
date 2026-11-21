# Informe técnico del laboratorio de interoperabilidad NIP-46 / NDK 2.12.2

**Fase 1.0A.** Fecha de ejecución: **2026-11-20 (UTC)**. Código y reproducción: [`lab/`](../lab/README.md). Definiciones de los experimentos, fijadas antes de ejecutar: [`lab/experiments/definitions.md`](../lab/experiments/definitions.md). Contexto: [stacker-news-compatibility.md](stacker-news-compatibility.md) §3.5.

Etiquetas: **[LAB]** observado en el laboratorio; **[V]** verificado en código o metadatos; **[I]** inferencia; **[H]** hipótesis sin validar.

> **Continuación:** la Fase 1.0A.2 (firmante real mínimo de laboratorio, sondas de relay y observación real de Stacker News) y el cierre de la Fase 1.0A están en [phase-1.0A-closure.md](phase-1.0A-closure.md). Este informe cubre solo la Fase 1.0A.1.

> **Alcance honesto.** El laboratorio valida la interoperabilidad con **NDK 2.12.2 ejecutándose en Node 22.23.5** frente a un relay mínimo local. **No valida compatibilidad con Stacker News**: no se ha observado el bundle del navegador de producción, ni la versión desplegada, ni relays públicos, ni su servidor. Nada de aquí es una autenticación real.

## 1. Resumen ejecutivo

- **NDK 2.12.2 completa NIP-46 con un firmante que responde en NIP-44 a su solicitud inicial en NIP-04** [LAB]. NDK arranca con `encryptionType = "nip04"`, cifra el `connect` con NIP-04, recibe la respuesta NIP-44, pasa a `nip44`, y el resto del flujo (`get_public_key`, `sign_event`) viaja en NIP-44. Esto **confirma por observación** lo que la Fase 0.3 había inferido del código (`rpc.ts:107-129`).
- **El modo espejo (todo en NIP-04) también completa el flujo** [LAB].
- El evento `kind 27235` que firma el firmante **pasa las comprobaciones de servidor de Stacker News replicadas** (mismo `@noble/curves` 1.8.1, id recalculado, firma Schnorr, `tags[0] = challenge`) [LAB].
- **Resultados: 39 de 39 verificaciones en PASS** (pruebas propias, aislamiento, E1-E7 con el firmante de referencia, E3, E5, E5b y la repetición con el simulador Python). **Regla de decisión (Fase 0.3), sobre las corridas con Python: recomendar NIP-44 como respuesta predeterminada** (E1 y E2 con Python en PASS). Sigue siendo una **recomendación provisional** sujeta a la aprobación del propietario y a la prueba real.
- Hallazgos nuevos sobre el cliente: NDK **acepta una respuesta firmada por otra clave** si el `id` coincide, y si `get_public_key` responde con error, `blockUntilReady()` **resuelve** pero `user.pubkey` **lanza** `npub not set` (§7).
- **Cuatro defectos propios** (arnés y entorno) se encontraron y corrigieron durante la construcción; ninguno alteró un criterio (§9).

## 2. Qué se ejecutó

| Elemento | Detalle |
|---|---|
| Cliente bajo prueba | `@nostr-dev-kit/ndk` **2.12.2** (la versión que fija el lockfile de Stacker News), con la **clausura mínima** de dependencias (24 entradas npm, 23 tarballs únicos), `nostr-tools` **2.16.2**, `@noble/curves` 1.8.1. Node **v22.23.5** (la versión de `.node-version` de Stacker News). |
| Réplica del camino de Stacker News | Mismo parche de URL (`lib/nostr.js:196-202`), mismo evento de login (`nostr-auth.js:148-157`) y mismas comprobaciones de servidor (`[...nextauth].js:241-270`). La URL `u` es ficticia (`https://sn.lab.invalid`). |
| Firmante de referencia | Node + `nostr-tools` 2.16.2 (la misma biblioteca criptográfica que usa el navegador de Stacker News): aísla el comportamiento de NDK. |
| Simulador Python | `lab_signer` con NIP-04/NIP-44 propios (`coincurve` 21.0.0, `cryptography` 50.0.2, `cffi` 2.1.1, `pycparser` 3.12), Python 3.12.16. **No es el firmante productivo.** |
| Relay | Mínimo propio (Python + `websockets` 17.4): EVENT/REQ/CLOSE; OK/EOSE/CLOSED/NOTICE; verifica id y firma; sin persistencia, NIP-42 ni NIP-11. |
| Identidades | Desechables, en memoria; el firmante usa claves de **transporte e identidad distintas**. E5 usa las claves públicas de juguete de los vectores oficiales. |

## 3. Dependencias y verificaciones de integridad

Manifiesto completo con URL, hash y licencia: [`lab/deps/artifacts.json`](../lab/deps/artifacts.json). Hashes y digests, los mismos presentados y aprobados en el paso 1.

- **Descarga:** `lab/tools/fetch_artifacts.py` (solo HTTPS, hosts del manifiesto, sin redirecciones, tope de tamaño, hash verificado **antes** de guardar). **29 artefactos, 0 fallos de integridad** [LAB]: 23 tarballs npm (sha512), 5 ruedas Python (sha256) y los vectores NIP-44 (sha256 `269ed0f6…`, igual al que publica la especificación). Hosts contactados: `registry.npmjs.org`, `files.pythonhosted.org`, `raw.githubusercontent.com` (solo los vectores, fijados al commit `1f8dba17…`) y, para las imágenes, `docker pull` por digest.
- **Imágenes:** `node@sha256:e9f565d3…` (`22.23.5-bookworm-slim`) y `python@sha256:5e2bdb1b…` (`3.12.16-slim-trixie`); ambas `linux/amd64`, con el ID de configuración que anunciaban sus manifiestos.
- **Instalación:** construcción con `network: none`. Node: `install-vendor.mjs` **re-verifica sha512 y extrae con `tar`** (sin `npm`, sin scripts de instalación). Python: `pip install --no-index --no-deps --require-hashes`.
- **Clave npm expirada (investigada):** 41 de las 44 entradas del lockfile se firmaron con la clave `SHA256:jl3bwswu…`, que expiró el 2025-01-29, y 3 (NDK 2.12.2, `nostr-tools` 2.16.2, `debug` 4.4.3) con la vigente. Comparé la fecha de publicación de cada versión con esa expiración: **las 41 se publicaron antes de que expirara** y las 3 posteriores usan la clave vigente. **La expiración no reduce la confianza** [V]. Además cada sha512 coincide con el del lockfile de Stacker News.
- **Vectores NIP-44:** dato local sin versionar (el repositorio de origen no declara licencia).

## 4. Aislamiento verificado

Comprobación automática (`AISL`) [LAB]: red `nip46-lab_lab_net` con `internal: true`; **sin puertos publicados**; sistema de archivos de solo lectura; `cap_drop: ALL` y capacidades efectivas `0000000000000000`; `no-new-privileges`; no privilegiado; usuario **10001** (no root); **sin ruta por defecto** dentro del contenedor (no hay camino a Internet); no se puede escribir en el sistema de archivos raíz. El único volumen es un `tmpfs` en memoria con la URI `bunker://` y la clave **pública** de identidad. Los registros solo contienen claves públicas truncadas, ids, esquemas y SHA-256 del texto plano.

## 5. Resultados

Todos los PASS se decidieron con criterios fijados antes de ejecutar y se apoyan en lo que **observó el relay** (independiente de lo que declaran los actores). Veredictos posibles: PASS, FAIL, BLOCKED, INCONCLUSIVE. Para cada experimento, el esquema de solicitudes y de respuestas es el observado en el relay.

| Id | Qué comprueba | Solicitudes → respuestas observadas | Referencia | Python |
|---|---|---|---|---|
| E0 | Pruebas propias: relay NIP-01, vectores oficiales NIP-44 (válidos e inválidos), NIP-04 | — (33 pruebas) | PASS | PASS (mismas 33) |
| E1 | Respuesta NIP-44 al `connect` NIP-04 | nip04 → nip44; NDK pasa de `nip04` a `nip44` | PASS | PASS |
| E2 | `get_public_key` y `sign_event 27235` tras E1 | nip04, nip44, nip44 → nip44 ×3; login `all_ok` | PASS | PASS |
| E3 | Python descifra el primer `connect` NIP-04 real de NDK | SHA-256 del texto plano igual en NDK y en Python | — | PASS |
| E4 | Todo en NIP-04 | nip04 ×3 → nip04 ×3; NDK no cambia de esquema; login `all_ok` | PASS | PASS |
| E4m (complemento) | Modo espejo | igual que E4 | PASS | PASS |
| E5 | NIP-44 cruzado `nostr-tools` ↔ Python (1, 32, 33, 1000 B, Unicode, ~1000 B Unicode, 65535 B) | 7/7 en ambos sentidos | PASS | PASS |
| E5b (complemento) | NIP-04 cruzado, mismos mensajes | 7/7 en ambos sentidos | PASS | PASS |
| E6 | Ráfaga: `ack`, clave pública y 20 `sign_event` concurrentes | 22 solicitudes (1 nip04 + 21 nip44); 20/20 firmas válidas; una transición | PASS | PASS |
| E6j (complemento) | Igual con retardo aleatorio 0-40 ms (reordena) | 20/20 firmas válidas; una transición | PASS | PASS |
| E7 `wrong_id` | Respuesta con `id` ajeno y luego la correcta | resuelve a ~1,6 s, solo con la correcta | PASS | PASS |
| E7 `error_field` | Campo `error` | `blockUntilReady()` rechaza con el texto de `error` | PASS | PASS |
| E7 `malformed_json` | Texto plano no JSON | NDK lo descarta (`Unexpected token`) y resuelve con la correcta | PASS | PASS |
| E7 `garbage` | Contenido indescifrable | NDK intenta ambos esquemas, falla y resuelve con la correcta | PASS | PASS |
| E7 `bad_mac` | MAC NIP-44 alterado | NDK: `invalid MAC`; resuelve con la correcta | PASS | PASS |
| E7 `spoof` | `ack` firmado por **otra clave** | **NDK lo acepta** y completa | PASS | PASS |
| E7 `duplicate` | Misma respuesta dos veces | se procesa dos veces; resuelve una; sin errores | PASS | PASS |
| E7 `unknown_id_first` | Respuesta con `id` desconocido y luego la correcta | la desconocida se ignora | PASS | PASS |
| E7 `auth_url` | `auth_url` y luego la final con el mismo `id` | NDK emite `authUrl` con la URL y resuelve a ~1,1 s | PASS | PASS |
| E7 `get_pubkey_error` | `get_public_key` con `error` | resuelve, pero `user.pubkey` lanza `npub not set` | PASS | PASS |
| E7 `mixed` | Esquemas alternados | 2 transiciones (`nip04→nip44→nip04`); resuelve | PASS | PASS |
| Control negativo | Provoca un rechazo y evalúa con los criterios de E1 | `blockUntilReady()` rechazado → **FAIL** | — | (el evaluador discrimina) |

Duración de un flujo completo de login en el laboratorio: **~80-150 ms** [LAB].

## 6. Evidencia del intercambio NIP-46 (E2 con el simulador Python)

Orden de eventos `kind 24133` registrado por el relay (ids truncados, claves públicas de 8 caracteres):

| # | Origen → destino | Esquema | Contenido (caracteres) |
|---|---|---|---|
| 1-2 | Suscripciones `REQ` `{"kinds":[24133],"#p":[clave del suscriptor]}` (firmante y cliente) | — | — |
| 3 | cliente NDK → firmante | **nip04** | 136 (`connect`) |
| 4 | firmante → cliente NDK | **nip44** | 132 (`ack`) |
| 5 | cliente NDK → firmante | nip44 | 176 (`get_public_key`) |
| 6 | firmante → cliente NDK | nip44 | 220 (clave de identidad) |
| 7 | cliente NDK → firmante | nip44 | 688 (`sign_event`) |
| 8 | firmante → cliente NDK | nip44 | 944 (evento firmado) |

Registrado por NDK (instrumentación sobre la instancia, sin modificar NDK ni registrar texto plano): `encryptionType` empieza en `nip04`; tras procesar la respuesta del evento 4 pasa a `nip44`; las dos solicitudes siguientes se cifran con `nip44`. El texto plano del `connect` que cifró NDK y el que descifró Python tienen el **mismo SHA-256** (E3). El relay recibió también la suscripción de NDK exactamente como la leímos del código: `{"kinds":[24133],"#p":[…]}`, **sin `since` ni `limit`** [LAB], y **no hubo peticiones HTTP/NIP-11**.

## 7. Diferencias entre el análisis estático y el comportamiento real

| Tema | Análisis estático (Fase 0.3) | Observado |
|---|---|---|
| Cifrado de la respuesta | La ruta existe; funcionamiento de extremo a extremo **sin validar** (E-5) | **Funciona** con `nostr-tools` 2.16.2 en Node, con firmante de referencia y con Python |
| Suscripción de NDK | Sin `since` (N4) | Confirmado en el relay |
| `get_public_key` con error | N7: «resuelve con clave indefinida» | Resuelve, pero **`user.pubkey` es un getter que lanza `npub not set`** (`dist/index.mjs:5546`); un cliente que lo lea sin protección falla |
| Respuestas de otra clave | No analizado | **NDK las acepta** (correlación solo por `id`, no por la clave del firmante) |
| Contenido indescifrable | «ambos intentos fallan» | Se descarta; el mensaje del segundo intento (NIP-04 sobre un contenido sin `?iv=`) es un error genérico de `nostr-tools` (`join.decode input should be string`) |
| `auth_url` | Soportado por la UI | Confirmado: `authUrl` se emite y la resolución llega con la respuesta final |

## 8. Diferencias entre Node (referencia) y Python

En las **17 corridas comparables** el veredicto y el comportamiento observable de NDK coinciden entre el firmante de referencia (`nostr-tools`) y el simulador Python. Las diferencias son solo de tiempo (el simulador Python respondió un poco más rápido en este entorno) y de texto en errores aleatorios. Python supera además los **vectores oficiales de NIP-44** (válidos e inválidos) y la prueba cruzada E5. Por tanto, el resultado de NDK no depende de una particularidad de `nostr-tools`: la implementación propia de NIP-44/NIP-04 es interoperable en estas condiciones. Limitación: el simulador aplica el tope **provisional** de 65535 bytes (P-14), no una regla de NIP-44.

## 9. Problemas encontrados y correcciones

| # | Problema | Dónde | Corrección |
|---|---|---|---|
| 1 | BuildKit en Windows fallaba con `changes out of order` al usar varios `COPY` desde subcarpetas | Entorno | Un solo `COPY . /ctx` por imagen con `.dockerignore` propio |
| 2 | El manifiesto con hashes quedaba **ignorado por Git** por la regla preexistente `MANIFEST` (insensible a mayúsculas en Windows) | Entorno | Carpeta renombrada a `lab/deps/`; no se ampliaron las reglas de `.gitignore` autorizadas |
| 3 | E7 `get_pubkey_error` salió **INCONCLUSIVE**: mi arnés leía `user.pubkey` sin proteger y NDK lanza | **Arnés**, no NDK | Lectura protegida; el criterio pre-registrado no cambió; el caso pasó a PASS |
| 4 | E5/E5b salieron **BLOCKED**: `xtest.mjs` importaba `@noble/hashes/utils`, que en la clausura mínima solo existe anidado | **Arnés**, no el cifrado | Se eliminó esa importación; E5 pasó a PASS y se repitió el recorrido completo |

La corrida oficial que se informa es la última, completa y sin pruebas bloqueadas. Las anteriores (parciales) quedaron en `lab/results/` (excluido de Git).

## 10. Recomendación: NIP-44 frente a modo espejo NIP-04

**Recomendación (provisional): responder en NIP-44 por defecto**, según la regla de la Fase 0.3 aplicada a las corridas con Python (E1 y E2 en PASS), **aceptando NIP-04 solo como entrada** (el `connect` inicial de NDK llega en NIP-04: E3). El modo espejo NIP-04 también funciona (E4, E4m) y se conserva como **contingencia**, no como valor por defecto, porque NIP-04 no está autenticado y la especificación lo desaconseja.

Cautelas: es un resultado de laboratorio con NDK en Node; el despliegue de Stacker News y su bundle de navegador siguen sin observar [H]; y la decisión final corresponde al propietario (P-02, P-17).

## 11. Implicaciones para el diseño del firmante [I]

- Un firmante **no debe responder con error a `get_public_key`** a un cliente autorizado: dejaría a NDK con una clave que lanza al leerla.
- Los textos del campo `error` de `connect` llegan a quien llame a `blockUntilReady()` (Stacker News los muestra): deben ser **genéricos y estables**.
- NDK **no impone tiempo máximo** y tolera respuestas tardías, duplicadas o con `id` desconocido: una aprobación humana lenta o el flujo `auth_url` son viables.
- NDK **no ata la respuesta a la clave del firmante**: es una debilidad del cliente que el firmante no puede corregir; conviene conocerla al evaluar el riesgo.
- La **memoria de ids ya vistos y la ventana de tiempo** siguen siendo necesarias en el firmante; NDK no las exige.

## 12. Limitaciones y riesgos residuales

| Riesgo o limitación | Prioridad |
|---|---|
| NDK en Node ≠ bundle de navegador de Stacker News; versión de producción sin observar | Alta |
| Relay mínimo: sin NIP-42, límites de tasa ni comportamiento de relays públicos | Alta |
| El simulador Python no es el firmante definitivo; no valida política, persistencia ni aprobación humana | Media |
| Serialización NIP-01 comprobada con contenido ASCII del evento de login; los caracteres de control siguen sin probarse contra `JSON.stringify` | Media |
| Las imágenes Docker no se escanearon (no se contactó con servicios de análisis) | Media |
| Vectores NIP-44 de licencia no declarada: dato local sin versionar; los tres vectores del prefijo extendido siguen pendientes (P-14) | Media |
| Los PASS dependen de criterios fijados por nosotros; el control negativo muestra que el evaluador discrimina, pero no sustituye una revisión independiente | Media |
