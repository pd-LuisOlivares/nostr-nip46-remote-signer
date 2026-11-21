# Cierre de la Fase 1.0A: laboratorio e interoperabilidad NIP-46

**Estado formal: cierre técnico APROBADO por el propietario con observaciones (2026-11-20).** Preparado por Claude Code; las observaciones aprobadas son las limitaciones documentadas en §3 (ausencia de `session_end`, ausencia de veredicto automático de la Compuerta B, primer intento NO-GO de la Compuerta A local, autenticación real pendiente para B4/B6). No hay commit ni push (todo el trabajo de la Fase 1.0A sigue sin versionar; lo hará el propietario). La Fase 1.0B **no está iniciada**. Fecha: 2026-11-20. Las horas de los registros están en UTC; Chile (America/Santiago) es UTC−3 ese día.

**Etiquetas.** **[OBS]** observado y comprobado en un archivo de evidencia (se indica la ruta). **[V]** verificado en código o metadatos. **[DECL]** declarado por el propietario, **sin evidencia local que lo respalde**. **[H]** hipótesis sin validar. **[NV]** no verificado.

> **Qué demuestra y qué no (léase primero).** La Compuerta B observó, con Stacker News real y una identidad desechable, que su cliente **se conecta a nuestro firmante a través de `relay.primal.net`**, que nuestro firmante responde `connect` y `get_public_key` de forma que el cliente continúa, y que Stacker News envía un `sign_event` del evento de login esperado. Eso es **interoperabilidad de protocolo observada**. **No es una autenticación**: no se firmó ningún evento (el firmante estaba en `MODE=observe`), Stacker News no recibió una firma, no se creó cuenta ni sesión, y **ninguna de las hipótesis sobre la aceptación de una firma por el servidor de Stacker News (por ejemplo la caducidad del reto, Y-8) se ha puesto a prueba**. La autenticación completa sigue **pendiente** y es el objetivo de la Fase 1.0B.

## 1. Alcance y subfases

| Subfase | Contenido | Estado |
|---|---|---|
| 1.0A.1 | Laboratorio local con NDK 2.12.2 real, relay mínimo propio y firmantes de referencia (E1 a E7) | Completada (39 de 39 en PASS; ver [nip46-lab-report.md](nip46-lab-report.md)) |
| 1.0A.2 | Firmante real mínimo de laboratorio (`lab/py/lab_real/`), ensayos locales E8 a E12, sondas de relay (Compuerta A), observación con Stacker News (Compuerta B) | Completada (esta consolidación) |
| 1.0A.3 | Cierre documental: este documento, `docs/decisions.md`, `docs/ai-log.md`, continuidad | Preparada; **transcripciones sin exportar** (ver §9) |

La **Compuerta C** (inicio de sesión real con una firma) y la **D** (repetición) **no se ejecutaron**; no hay autorización para ellas.

## 2. Evidencia consolidada y verificación

### 2.1 Laboratorio local y ensayos (sin red externa)

| Elemento | Resultado | Fuente |
|---|---|---|
| E1 a E7 (1.0A.1) | 39 de 39 PASS (corrida oficial) | [nip46-lab-report.md](nip46-lab-report.md) |
| Ensayo `--stage rehearsal` (E8, E8-control, E9, E9c, E10 y 7 controles, E10b-s/n y control, E11 y 4 controles) | **20 de 20 PASS** en la última corrida completa | `lab/results/rehearsal-20261120T230851Z/` [OBS]; criterios en `lab/experiments/definitions-real.md` |
| `unittest` del laboratorio (dentro de Docker) | 119 OK | comando en `lab/real/README.md` |
| Pruebas del lanzador A y del controlador B (host, dobles) | 14 OK y 50 OK | `lab/real/test_run_gate_a.py`, `lab/real/test_run_gate_b.py` |
| `pytest` del proyecto | 5 OK (solo `/health`; **no hay funcionalidad Nostr en `app/`**) | `tests/` |

### 2.2 Compuerta A: sondas de relay (efecto externo autorizado, un intento por destino)

| Ejecución | Destino | Resultado | Evidencia |
|---|---|---|---|
| A (17:00 Chile) | `relay.nsec.app:443` | **NO-GO**: TCP abierto, 1530 B enviados, 0 B recibidos en 10 s; sin TLS | `lab/results/real-probe-20261120T165758/` [OBS] |
| A1 (20:03 Chile) | `relay.primal.net:443` | **GO**: TLS 1.3 verificado (`CERT_REQUIRED`, `check_hostname`, certificado `primal.net`), WSS, `EOSE` 1466 ms, `OK` verdadero 1804 ms, eco 1862 ms, sin `AUTH`; 1 evento publicado; `TLS_GROUPS=X25519` | `lab/results/gate-a-ab/A1/` [OBS] |
| A2 (20:03 Chile) | `relay.primal.io:443` | **NO-GO**: el proxy no logró conectar (`connect_failed`, ≈ 2 s); sin TCP, TLS ni WSS; la sonda terminó con una excepción no capturada (corregida después) | `lab/results/gate-a-ab/A2/` [OBS] |

Medición adicional [OBS]: con OpenSSL 3.5.7 el ClientHello por defecto de nuestro cliente ocupa 1530 B (igual a los bytes enviados en la sonda de `relay.nsec.app`) y con X25519 solo 517 B. **La causa del silencio de `relay.nsec.app` sigue sin determinar [H]**: el GO de A1 (con X25519 y otro relay) **no permite atribuirla al tamaño del ClientHello**. La causa del fallo de `relay.primal.io` también es **[NV]** (el proxy no distingue DNS de rechazo) y, por decisión del propietario, no se investiga.

### 2.3 Compuerta A local operativa (controlador de la Compuerta B; solo infraestructura local)

Evaluador formal: `evaluate_lab` en `lab/real/run_gate_b.py`; 17 criterios fijados antes de ejecutar y documentados en `definitions-real.md` (E12). Los veredictos están en `evaluacion_b.json` de cada directorio [OBS].

**Dato que el informe del propietario no menciona y debe constar:** hubo **dos** ejecuciones interactivas en PowerShell, con 86 s de diferencia. La primera dio **NO-GO** (16 criterios cumplidos, 1 fallido: `operador_confirma_haber_visto_la_uri`); la segunda dio **GO** (17 de 17). El código del controlador no cambió entre ambas (última modificación 20:33 hora de Chile; las ejecuciones fueron a las 20:42 y 20:43). **La causa de la respuesta negativa del operador en el primer intento no está registrada [NV]**; el resto de criterios de esa ejecución fueron correctos (URI mostrada una vez, `connect` aprobado, 11 firmas denegadas, 0 firmas, 0 residuos). Se conserva ambas como evidencia: la confirmación del operador es una atestación humana y no puede reconstruirse.

Matriz completa de criterios (generada directamente de los `evaluacion_b.json`):

| # | Criterio | Interactivo, intento 1 | Interactivo, intento 2 | Desatendido `full` | Desatendido `manual-stop` | Desatendido `timeout` |
|---|---|---|---|---|---|---|
| 1 | `stdin_stdout_son_terminal_real` | sí | sí | n/a | n/a | n/a |
| 2 | `prechecks_check_b_y_preflight_b` | sí | sí | sí | sí | sí |
| 3 | `uri_mostrada_una_sola_vez_en_la_terminal` | sí | sí | sí | sí | sí |
| 4 | `operador_confirma_haber_visto_la_uri` | **NO** | sí | n/a | n/a | n/a |
| 5 | `uri_y_secretos_ausentes_de_archivos` | sí | sí | sí | sí | sí |
| 6 | `modo_observe_y_tty_efectivos_con_entorno_hostil` | sí | sí | sí | sí | sí |
| 7 | `connect_aprobado_manualmente` (¹) | sí | sí | sí | sí | sí |
| 8 | `solicitudes_nip46_recibidas` (¹) | sí | sí | sí | sí | sí |
| 9 | `sign_event_rechazados_sin_preguntar` (¹) | sí | sí | sí | sí | sí |
| 10 | `cliente_ve_todas_las_firmas_denegadas` | sí | sí | sí | n/a | n/a |
| 11 | `cero_firmas` (²) | sí | sí | sí | sí | sí |
| 12 | `cero_aprobaciones_de_firma` | sí | sí | sí | sí | sí |
| 13 | `cero_cuentas_ni_destinos_externos` | sí | sí | sí | sí | sí |
| 14 | `un_solo_lanzamiento_y_un_solo_tunel` | sí | sí | sí | sí | sí |
| 15 | `motivo_de_fin_esperado` | sí | sí | sí | sí | sí |
| 16 | `dentro_de_la_ventana` | sí | sí | sí | sí | sí |
| 17 | `limpieza_docker_sin_residuos` | sí | sí | sí | sí | sí |
| | **Veredicto del evaluador** | **NO-GO** | **GO** | **GO** | **GO** | **GO** |
| | Verdaderos / falsos / no aplica | 16 / 1 / 0 | 17 / 0 / 0 | 15 / 0 / 2 | 14 / 0 / 3 | 14 / 0 / 3 |

(¹) En `manual-stop` y `timeout` no hay cliente: el criterio se cumple si **no** hay solicitudes ni decisiones. (²) Ver el hallazgo F-2 sobre `session_end`.

Lo informado para el intento 2 queda **verificado** [OBS] en `lab/results/gate-b-rehearsal-20261120T234353Z/{evaluacion_b,run_meta_b}.json`: GO, 17 de 17, `tty_stdin` y `tty_stdout` verdaderos, URI una vez en la terminal, `connect` aprobado con motivo `humano`, 11 `sign_event` denegados (`modo_observacion`), `sign_ok` 0, residuos Docker 0/0/0, único destino `relay-lab:7777`, escaneo de secretos vacío. Era una prueba local: **no** tocó Stacker News.

### 2.4 Compuerta B: observación real con Stacker News (verificación punto por punto)

Evidencia: `lab/results/gate-b-run-02/` (`evidence.jsonl`, `proxy.jsonl`, `run_meta_b.json`, `pre/`). Antes hubo una ejecución, `gate-b-run/`, **interrumpida manualmente antes del inicio de la ventana, sin conexión externa** (`conexion_externa_iniciada = false`, 0 lanzamientos).

| Afirmación recibida | Resultado de la verificación | Fuente |
|---|---|---|
| Relay `relay.primal.net:443` | **Verificado** | `run_meta_b.json` (`destino_unico`), `proxy.jsonl` |
| Dentro de la ventana autorizada | **Verificado contra el comando; autorización confirmada por el propietario.** El comando configuró la ventana 20:50:00 a 20:55:00 (Chile) y la ejecución fue de 20:50:05.650 a 20:54:24.798. El texto escrito de esa autorización no está en el repositorio **[NV documental]**, pero el propietario confirmó expresamente en el encargo de cierre que la ejecución estuvo dentro de la ventana autorizada **[DECL]** | `run_meta_b.json` |
| `connect`: 1 solicitud, aprobada manualmente | **Verificado**: 1 `connect`, decisión `humano`, aprobada, latencia 6877 ms | `evidence.jsonl` |
| `get_public_key`: 1 solicitud | **Verificado** | `evidence.jsonl` |
| `sign_event`: 1 solicitud, rechazada deliberadamente | **Verificado**: 1 solicitud, decisión denegada con motivo `modo_observacion` | `evidence.jsonl` |
| `kind` 27235 | **Verificado** | `observed_sign.kind` |
| `content`: `Stacker News Authentication` | **Verificado** | `observed_sign.content_seen` |
| `u`: `https://stacker.news` | **Verificado** (20 caracteres) | `observed_sign.u_seen` |
| `method`: `GET` | **Verificado** | `observed_sign.method_seen` |
| Comprobaciones de política fallidas: ninguna | **Verificado**: `policy_failed = []` frente a `SN_ORIGIN=https://stacker.news` (valor provisional que ahora coincide con lo observado) | `observed_sign.policy_failed` |
| `sign_ok`: 0 | **Verificado**: ningún evento `sign_ok`; ninguna decisión de firma aprobada | `evidence.jsonl` |
| Un túnel y un único destino externo | **Verificado**: 1 `connect_allowed` a `relay.primal.net:443`, 0 fallidos, ningún otro destino | `proxy.jsonl`, `run_meta_b.json` |
| Limpieza Docker: 0 contenedores, redes y volúmenes | **Verificado** (`residuos_finales` 0/0/0, también tras `down`) | `run_meta_b.json` |
| Motivo de finalización: `tiempo` | **Verificado** | `run_meta_b.json` |
| Duración 259,15 s | **Verificado** (`duracion_total_s`); limpieza 4,55 s; dentro del límite de 300 s | `run_meta_b.json` |
| Stacker News mostró `unauthorized` | **No verificable [DECL]**: se prohibieron las capturas. Sí está verificado que el firmante **publicó** la respuesta a `sign_event` y que el relay la aceptó (`response_published`, `relay_ok` verdadero); el texto `unauthorized` de esa respuesta lo fija el código y lo cubren las pruebas, pero **no se registra el contenido** en la evidencia | `evidence.jsonl` |
| Es el resultado esperado porque el firmante estaba en `MODE=observe` | **Coherente** con el código y con `session_start` (`mode = observe`, `approval_mode = tty`) [OBS]; que la pantalla de Stacker News mostrase ese texto es [DECL] | `evidence.jsonl` |

Cronología [OBS] (UTC): URI emitida 23:50:11; `connect` recibido 23:50:39; aprobado 23:50:45.991; `get_public_key` 23:50:46.7; `sign_event` 23:50:47.5; respuesta denegada publicada 23:50:47.9; la sesión siguió abierta hasta el límite de tiempo (23:54:20) sin más solicitudes.

**Veredicto formal.** El evaluador de `run_gate_b.py` solo evalúa el ensayo local; **para la ejecución real no existe un veredicto GO/NO-GO generado por una herramienta** (`gate-b-run-02/` no tiene `evaluacion_b.json`). La clasificación siguiente es **manual, hecha por Claude Code en este cierre y sujeta a la revisión del propietario**: **GO de observación** (objetivo de la compuerta cumplido: se observaron `connect`, `get_public_key` y la estructura real de `sign_event`, sin firmas, sin cuenta, un solo destino, dentro del tiempo y con limpieza completa). **No es un GO de autenticación.**

## 3. Hallazgos e inconsistencias

| # | Hallazgo | Impacto | Acción |
|---|---|---|---|
| F-1 | Dos ejecuciones interactivas de la Compuerta A local, la primera NO-GO por la atestación del operador (§2.3). | Bajo (el resto de criterios fue correcto) pero debe constar. | Registrado aquí y en `docs/ai-log.md`. Causa **[NV]**. |
| F-2 | **Ausencia de `session_end`** en la evidencia (`session_end: null`) del intento interactivo 2 y de la Compuerta B real. Causa más probable **[H, coherente con el código; no se probó aislada]**: el controlador termina el contenedor del firmante a la fuerza (`docker down`), el firmante no maneja `SIGTERM` y no alcanza a escribir su evento de cierre. En el intento 1 sí aparece, pero con motivo `relay_no_disponible` y error `ConnectionClosedError`: es un **artefacto de la carrera** entre el cierre del proxy y el del firmante (con `RELAY_ATTEMPTS=1`), **no** una caída real del relay. | El criterio `cero_firmas` se apoya en `sign_ok = 0` y en `(session_end or {}).get("signatures", 0)`: **si no hay `session_end`, el contador de firmas del cierre no se verifica** y el valor por defecto 0 no es evidencia. La ausencia de firmas **sí** está respaldada por 3 vías independientes: 0 eventos `sign_ok`, ninguna decisión de firma aprobada y todas las decisiones `modo_observacion`. | **Pendiente de corregir**: parada ordenada (detener primero el firmante con `SIGTERM`, manejarlo y emitir `session_end` con motivo «detenido por el controlador») y que el criterio exija `session_end` o lo marque como no verificado. No se modificó código en este cierre. |
| F-3 | No hay evaluador para la ejecución real (§2.4). | El veredicto de la Compuerta B es manual. | Opcional: añadir un evaluador de la ejecución real antes de la Compuerta C. |
| F-4 | `connect` de Stacker News llegó con **2 parámetros de tipo cadena y sin permisos** (`perms_seen` ausente) y por **NIP-04**; `get_public_key` y `sign_event` por **NIP-44** [OBS]. El **contenido** de `params[0]` no se registra (solo tipos) [NV]; el secreto coincidió con `params[1]`. | Coherente con el análisis estático (H-4) y con el laboratorio (L-1), pero el valor de `params[0]` no está medido. | Aceptable; no hace falta registrar valores. |
| F-5 | El evento de `sign_event` es una **plantilla con seis campos**: `content`, `created_at`, `id`, `kind`, `pubkey`, `tags` (incluye `id` y `pubkey`), 362 B, `created_at` con 0 s de antigüedad, etiquetas en orden `challenge`, `u`, `method` (reto de 64 hexadecimales en minúsculas). | La política del laboratorio ya admitía `id` y `pubkey` opcionales verificándolos: es **imprescindible conservar** esa regla en el producto. | Ver [phase-1.0B-proposal.md](phase-1.0B-proposal.md). |
| F-6 | El firmante del laboratorio **reintentaba la conexión al relay hasta 3 veces** (descubierto al preparar «un solo intento»). | Habría roto la restricción de un intento. | Corregido en el laboratorio (`RELAY_ATTEMPTS`); en el producto, los reintentos serán una decisión explícita y acotada. |
| F-7 | Durante el ensayo del controlador se corrigieron tres defectos de implementación (sintaxis JS, mínimo de observación en ventanas cortas, reutilización de directorios de evidencia). | Ninguno afectó a un resultado externo. | Declarados en E12. |
| F-8 | Todo el trabajo de 1.0A (incluido `lab/`) está **sin versionar**, y `lab/results/` está excluido de Git. | Riesgo de pérdida; la evidencia cruda **no** viaja con el repositorio. | Decisión del propietario (commit y qué evidencia sanitizada conservar). |
| F-9 | Las transcripciones de la Fase 1.0A no están exportadas (ver §9). | Trazabilidad incompleta según `AGENTS.md` §9. | Pendiente de autorización y de revisión de datos sensibles. |

## 4. Protocolos y comportamientos verificados

**Con Stacker News real (Compuerta B) [OBS]:**
- Stacker News **inicia con `connect` por NIP-04** (`scheme: nip04`) y **cambia a NIP-44** para `get_public_key` y `sign_event` tras recibir nuestra respuesta NIP-44. Es lo que predijo el laboratorio (L-1): responder siempre en NIP-44 y aceptar NIP-04 solo como entrada **funciona frente al cliente real**.
- `connect` llega con 2 parámetros (cadenas) y sin permisos; `get_public_key` sin parámetros; `sign_event` con 1 parámetro (el evento como cadena JSON).
- El valor real de `u` es `https://stacker.news`, el `content` es `Stacker News Authentication`, el método es `GET` y las etiquetas van en el orden `challenge`, `u`, `method`. Esto **confirma lo previsto en el código de `master`** (H-3) y resuelve la hipótesis Y-6 en cuanto a esos valores.
- El relay `relay.primal.net` aceptó y retransmitió eventos `kind 24133` sin pedir `AUTH` (sonda y sesión real); NIP-42 **no** se ejercitó.
- Tiempos observados: aprobación manual de `connect` en 6,9 s; `get_public_key` 0,7 s y `sign_event` 0,8 s después; sin reintentos de Stacker News.

**En laboratorio (NDK 2.12.2 en Node, relay local) [LAB, ver el informe del laboratorio]:** NIP-44 y NIP-04 con vectores oficiales, `connect`, `get_public_key`, `sign_event` y `ping`; NDK acepta respuestas tardías, duplicadas o con `id` ajeno (L-4, L-5) y trata mal un error de `get_public_key` (L-6); política restrictiva de 11 comprobaciones sobre `kind 27235`; aprobación humana por solicitud con denegación por defecto; tope de firmas; repeticiones rechazadas.

**Infraestructura de pruebas controladas [OBS]:** proxy de un único `host:puerto` (rechaza listas y comodines); firmante en una red Docker `internal`, sin puertos publicados, sistema de archivos de solo lectura, sin capacidades; TLS de extremo a extremo con verificación; evidencia con lista blanca que rechaza claves, URI y retos; controlador con ventana ≤ 300 s, reserva de limpieza, parada manual y limpieza forzada por etiqueta.

## 5. Estado de las hipótesis

| # | Hipótesis | Estado tras la Fase 1.0A |
|---|---|---|
| Y-5 | Producción de Stacker News equivale a `master` con NDK 2.12.x | **Compatible con lo observado** (mismo orden NIP-04 → NIP-44, mismos valores de `u`, `content`, `method`, etiquetas). **No demostrado**: no se observó la versión desplegada |
| Y-6 | Valor de `u`, `content` y formato del reto | **Validada** para `u`, `content`, `method`, orden de etiquetas y forma del reto (64 hexadecimales) |
| Y-7 | Un relay público acepta `kind 24133` sin NIP-42 | **Validada solo para `relay.primal.net`** (sin `AUTH` observado); otros relays: no |
| Y-8 | El reto `k1` no caduca dentro del tiempo de aprobación | **Sin validar**: pasaron ≈ 8 s entre `connect` y `sign_event` y no se firmó; la edad del reto en Stacker News se desconoce |
| Y-1 a Y-4, Y-9, Y-10 | (ver `docs/decisions.md`, 1.0A.1) | Sin cambios |
| Nueva | La respuesta de Stacker News a una firma **válida** (sesión, cuenta) | **Sin observar** |

## 6. Decisiones y limitaciones

Decisiones del propietario durante la 1.0A.2 (detalle en `docs/decisions.md`): relay único `relay.primal.net:443` para las validaciones siguientes; `relay.primal.io` y `relay.nsec.app` descartados sin investigar; `TLS_GROUPS=X25519` conservando la verificación completa; ventanas con tope duro y un intento por destino; la Compuerta B solo en modo observación y el controlador ejecutado por el propietario en su PowerShell; no repetir sondas externas.

Limitaciones: el firmante de laboratorio **no es el producto**; la identidad y los secretos son solo de memoria; no hay persistencia, API ni interfaz; el ensayo local usa NDK en Node (no el bundle del navegador de producción); un solo relay; E10b usó stdin enlazado y la Compuerta A interactiva se ejecutó una vez con GO tras un NO-GO; no hay veredicto automático para la ejecución real; sin transcripciones exportadas.

## 7. Componentes de laboratorio potencialmente reutilizables

Se **copian y adaptan** al producto (el código de `app/` no importa de `lab/`). Detalle y tareas en [phase-1.0B-proposal.md](phase-1.0B-proposal.md) §4.

| Componente (`lab/…`) | Qué aporta | Reutilización |
|---|---|---|
| `py/lab_common/nostr.py`, `nip44.py`, `nip04.py` | Eventos NIP-01, firma y verificación BIP-340 (coincurve), NIP-44 v2 con los vectores oficiales, NIP-04 entrante | **Alta**: base de `app/nostr/` (tipado completo, `Keypair` opaco, errores de dominio) |
| `py/lab_real/policy.py` | 11 comprobaciones puras de `kind 27235`; sin fallos frente al evento real | **Alta**: casi tal cual, con perfil configurable |
| `py/lab_real/signer.py` | Máquina de estados de `connect`/`get_public_key`/`sign_event`/`ping`, secretos de un solo uso por hash, repetición, topes, respuestas NIP-44 | **Media**: la lógica sí; la E/S TTY y el modo observación no |
| `py/lab_real/evidence.py` | Registro con lista blanca que rechaza secretos | **Media**: idea y pruebas; el producto necesita un registro de auditoría propio |
| `py/lab_real/tls.py` | Contexto TLS verificado con `X25519` | **Media**: como opción de configuración del cliente de relay |
| `py/lab_real/probe.py` | Sonda de relay con resultado estructurado | **Baja/opcional**: diagnóstico fuera del producto |
| `py/lab_relay/`, `node/client/`, `node/signer-ref/`, `run_lab.py` | Relay local mínimo, cliente NDK 2.12.2, firmante de referencia, orquestador | **Arnés de regresión** (P-18): se ejecuta contra el firmante productivo; no es código de producto |
| `real/run_gate_a.py`, `run_gate_b.py`, `compose.*.yaml`, proxy | Controladores y topología aislada de las compuertas | **Procedimiento de laboratorio** para futuras compuertas; no es producto |
| `py/tests/`, vectores locales | Pruebas y casos negativos | Portar a `pytest` (el archivo de vectores NIP-44 sigue sin licencia aclarada: P-16/P-21) |

## 8. Restricciones que deben mantenerse durante el desarrollo

1. **Interoperabilidad real primero** (`AGENTS.md` §3): un PASS automatizado no valida Stacker News; solo cuenta una autenticación real documentada.
2. **Efectos externos solo con autorización por compuerta** (`AGENTS.md` §11) con relay, identidad de prueba, operaciones, duración y restricciones.
3. **Sin claves ni URI reales en repositorio, registros o documentación**; identidades desechables; la URI `bunker://` solo en la interfaz del propietario, de un solo uso y con caducidad corta.
4. **Denegar por defecto**: aprobación explícita de `connect` y de cada `sign_event`; solo `kind 27235`; validación previa a firmar con la política restrictiva (incluida la verificación de `id` y `pubkey` de la plantilla, F-5); concesión de un solo uso; control de repeticiones.
5. **Respuestas NIP-44; NIP-04 solo como entrada.** Relay `wss://relay.primal.net:443` con TLS verificado (`X25519` si hace falta); sin responder a `AUTH` sin decisión expresa.
6. **Un intento y sin reintentos automáticos** salvo decisión explícita y acotada; tiempos límite en toda E/S de red.
7. **Sin secretos en logs ni evidencias**; errores genéricos hacia el cliente.
8. El código de protocolo **no importa FastAPI**; lo reutilizado del laboratorio se adapta, no se importa; dependencias nuevas solo con aprobación y `constraints.txt` actualizado.
9. Toda parada del firmante debe dejar evidencia de cierre (F-2).

## 9. Trazabilidad y pendientes de cierre

- **Resumen sanitizado de la evidencia:** [phase-1.0A-evidence-summary.md](phase-1.0A-evidence-summary.md) (métricas y estructura, con el SHA-256 de cada original; los originales se conservan en `lab/results/`, excluido de Git).
- **Registro de uso de IA:** entradas 17 a 26 de [ai-log.md](ai-log.md), con la clasificación LAB / DEV / DOC. No se registran tiempos de trabajo (no se midieron) y no se incorporan las pruebas manuales de conectividad que el propietario hizo en Windows.
- **Transcripciones de la Fase 1.0A:** el propietario **autorizó su exportación** (2026-11-20) con redacción de secretos, tokens, claves privadas y URI `bunker://` completas. Estado y resultado: entrada 26 de [ai-log.md](ai-log.md).
- **Pendientes del propietario:** aprobar el cierre; decidir el versionado de `lab/` y de la evidencia (F-8); aprobar o ajustar la propuesta de la Fase 1.0B; cualquier autorización externa futura (Compuerta C) será específica.
- **Archivos de evidencia citados** (todos bajo `lab/results/`, excluidos de Git): `real-probe-20261120T165758/`, `gate-a-ab/`, `gate-b-rehearsal-20261120T234227Z/`, `gate-b-rehearsal-20261120T234353Z/`, `gate-b-final-*-203453/`, `gate-b-run/`, `gate-b-run-02/`, `rehearsal-20261120T230851Z/`.
