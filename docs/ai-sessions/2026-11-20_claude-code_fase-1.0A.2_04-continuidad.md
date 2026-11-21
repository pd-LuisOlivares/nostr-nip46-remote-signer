# Punto de continuidad — Fase 1.0A.2 (implementación local y ensayos E8-E10)

- **Fecha:** 2026-11-20 · **Agente:** Claude Code (Sonnet 5.5) · **Nivel de razonamiento:** no disponible
- **Naturaleza de este archivo:** estado de avance redactado por el agente por cierre anticipado (límite de uso). **No es una transcripción**; la transcripción de esta interacción está **pendiente** de exportación al cierre de la Fase 1.0A (1.0A.3).
- **Restricciones respetadas:** sin commit ni push; **sin conexiones externas** (Stacker News, relays públicos); sin cambios en `app/`, `pyproject.toml`, `constraints.txt`, `AGENTS.md` ni `CLAUDE.md`; sin dependencias nuevas; `ai-log.md`, `decisions.md` y el informe de 1.0A **no** se consolidaron (reservado a 1.0A.3).

## 1. Qué se implementó (asistencia de IA / implementación por agente)

Todo bajo `lab/` (código de laboratorio, no productivo):

- `lab/py/lab_real/`: `signer.py` (firmante mínimo: connect, get_public_key, sign_event, ping; claves desechables en memoria; aprobación humana por solicitud; tope 2 firmas; ventana ±120 s; respuestas siempre NIP-44), `policy.py` (11 comprobaciones puras de `kind 27235`), `approval.py` (TTY, denegar por defecto; guion solo con el relay del laboratorio), `evidence.py` (lista blanca, rechaza secretos), `proxy.py` (CONNECT a un solo `host:puerto`), `probe.py` (sonda del relay), `__main__.py`.
- `lab/real/compose.real.yaml` (proxy + signer; signer solo en red `internal`, `logging: none`), `lab/real/compose.rehearsal.yaml` (ensayo local), `lab/real/README.md` (runbook, procedimientos de las compuertas A–C, lista de aprobaciones del propietario, limitaciones).
- `lab/node/client/main.mjs`: escenarios `e8` y `e9`. `lab/run_lab.py`: etapa `--stage rehearsal` (no forma parte de `all`).
- `lab/experiments/definitions-real.md`: criterios E8–E10 fijados antes de ejecutar (con dos enmiendas declaradas, ver §3).
- Pruebas: `lab/py/tests/test_real_{policy,evidence,approval,proxy,signer}.py`.

## 2. Resultados reales (automatizados/locales; ninguno es validación con Stacker News)

| Verificación | Comando | Resultado |
|---|---|---|
| `unittest` del laboratorio (incluye 1.0A.1) | `docker compose -f lab/compose.yaml -p nip46-lab run --rm -T -e LAB_QUIET=1 py-job python -W error::ResourceWarning -m unittest discover -s tests -t .` | 76 pruebas OK (última ejecución completa, antes de añadir la prueba wss; después `tests.test_real_proxy`: 6 OK, incluida wss/TLS con CA desechable) |
| Ensayo E8, E8-control, E9, E9c, E10 | `python -X utf8 lab/run_lab.py --stage rehearsal` | **todos PASS** (última corrida: `lab/results/rehearsal-20261120T194011Z/`, excluida de Git) |
| `pytest` del proyecto | `.venv\Scripts\python.exe -m pytest -q` | 5 passed |
| Escaneo de crudos | patrones `nsec1`, `bunker://`, `secret=`, cookie, Authorization, Bearer; 64-hex en evidencia/proxy | 0 coincidencias |
| Limpieza Docker | `docker ps -a/network ls/volume ls` filtrando `nip46` | 0 contenedores, 0 redes, 0 volúmenes |
| `git diff --check` | — | sin salida (limpio); archivos nuevos revisados a mano: sin espacios finales ni CRLF |
| `git status` | — | `M .gitignore, docs/ai-log.md, docs/decisions.md`; sin seguimiento: `docs/ai-sessions/*`, `docs/nip46-*.md`, `lab/` |

Nota: el total tras la última edición no se volvió a ejecutar completo (solo `tests.test_real_proxy`); rehacer `unittest discover` al retomar.

## 3. Hallazgos y desviaciones a decidir

- Dos fallos del evaluador de E10 en la primera ejecución (falso positivo `GPG_KEY` de la imagen base; inspección de un contenedor ya eliminado) y un criterio débil («≥ 3 rechazos» satisfecho por ruido del healthcheck) se corrigieron **después** de ver resultados; están declarados en `definitions-real.md`. El proxy dejó de registrar conexiones vacías.
- **Desviación del plan §9 #14:** tras el tope de firmas el firmante deniega pero **no se cierra** (E9 exige observar la denegación `tope`). Pendiente de decisión del propietario.
- El plan hablaba de «15 comprobaciones»: 11 están en `policy.py` y las otras (transporte, conexión activa, aprobación, tope, consumo atómico y autoverificación) en `signer.py`.
- Sin verificar: visualización interactiva de la URI en TTY con `logging: none` (solo se probó que `logs` no conserva nada y que la URI se imprime en un test unitario); comportamiento del relay público (AUTH, límites).

## 4. Pendiente

1. Re-ejecutar `unittest discover` completo y `--stage rehearsal` una vez más como confirmación final.
2. Entregar al propietario el informe de 1.0A.2 (resultados E8–E10, archivos, verificaciones, limitaciones, procedimiento de la primera sonda, lista de aprobaciones: ver `lab/real/README.md`).
3. Esperar autorización externa por compuerta (A sonda del relay; B Ejecución 0; C registro real; D opcional). **Ninguna concedida.**
4. En 1.0A.3: consolidar `docs/ai-log.md`, `docs/decisions.md`, informe y exportar/redactar transcripciones. No hacer commit sin autorización.

## 4b. Reanudación (verificación final local, misma fecha)

- Imágenes reconstruidas sin red; `unittest discover`: **77 OK** (incluye wss/TLS por proxy con CA desechable).
- `--stage rehearsal` (`lab/results/rehearsal-20261120T195241Z/`): E8, E8-control, E9, E9c, E10, **7 controles negativos de E10**, **E10b-s, E10b-n y E10b-control: todos PASS**. Criterios de E10b y de los controles fijados en `definitions-real.md` antes de ejecutar.
- Nuevos: `lab/py/tests/interactive_client.py`, `lab/real/solicitud-autorizacion-compuerta-A.md` (borrador, **sin autorizar**).
- Escaneo de crudos y limpieza Docker repetidos: 0 hallazgos, 0 recursos residuales; `git diff --check` limpio.
- Límite de E10b: entrada estándar enlazada (`run -T`), no pseudo-TTY. `docker logs` devuelve solo el error del daemon (79 caracteres), no contenido.
- Pendiente: autorización del propietario para la Compuerta A; 1.0A.3.

## 4c. Compuerta A ejecutada (2026-11-20, autorizada 17:00–17:02 America/Santiago)

- Una sola sonda a `relay.nsec.app:443` por el proxy; inicio real 17:00:00.036, fin de limpieza 17:00:13.766 (dentro de la ventana). Sin reintentos.
- **Resultado: NO-GO.** El proxy permitió el `CONNECT` y abrió el TCP hacia el relay (`connect_allowed`), se enviaron 1530 bytes y **no llegó ningún byte de vuelta** en 10 s; la sonda terminó con `TimeoutError` (sin TLS, sin WebSocket, sin EOSE/OK/eco, sin AUTH). No hubo otro destino en el proxy.
- Causa **no determinada**: relay caído o que no responde, o descarte del ClientHello TLS (~1,5 KB) en la ruta. Ambas son hipótesis [H]; no se ejecutó ninguna otra prueba (no autorizado).
- Cambio previo a la ejecución (verificado localmente): `probe.py` ahora se detiene al recibir `AUTH` y registra datos públicos del canal TLS (`tls`).
- Evidencia depurada (excluida de Git): `lab/results/real-probe-20261120T165758/`. Docker 0/0/0; `unittest` 77 OK tras el cambio.
- Siguiente compuerta **no iniciada**; esperar revisión del propietario.

## 5. Siguiente paso exacto para retomar

1. `docker compose -f lab/compose.yaml -p nip46-lab build relay signer-ref` (offline) y ejecutar los comandos de §2 (unittest completo + `--stage rehearsal`); confirmar PASS y limpieza.
2. Presentar el informe de cierre de 1.0A.2 con la lista «Qué debe aprobar el propietario» de `lab/real/README.md`.
3. Detenerse y esperar la autorización de la Compuerta A (alcance de `AGENTS.md` §11). Sin ella, no conectar a ningún relay público ni a Stacker News.

## 4d. Preparación de la nueva Compuerta A (relay.primal.net) y de la Compuerta B (misma fecha, **sin conexiones externas**)

Autoría: **decisión humana** — el propietario eligió `relay.primal.net:443` (opción A, con TCP/WSS verificados a mano desde Windows) y `relay.primal.io:443` como alternativa **no autorizada**, y pidió preparar B sin ejecutarla. **Asistencia de IA y implementación por agente** — lo siguiente.

- **Hallazgo medido (sin red):** el ClientHello de nuestro cliente (OpenSSL 3.5.7, Python 3.12.16) ocupa **1530 B**, exactamente los `bytes_up` de la Compuerta A fallida; con `X25519` solo, **517 B**. La causa del silencio de `relay.nsec.app` sigue siendo hipótesis [H].
- **Código (todo en `lab/`, sin tocar `app/`, dependencias ni `AGENTS.md`/`CLAUDE.md`):** `lab_real/tls.py` (`TLS_GROUPS`, opcional; vacío = comportamiento anterior); `probe.py` y `signer.py` lo usan; `proxy.py` valida `PROXY_ALLOW` (un solo `host:puerto`); modo observación del firmante (`MODE=observe` por defecto, primera rama de `on_sign`, nuevos eventos de evidencia `observed_request`/`observed_sign`, `policy.describe_sign_params`); `lab/real/compose.gate-b.yaml`; `lab/real/run_gate_a.py` (`check`, `check-b`, `preflight`, `run`).
- **Pruebas:** `unittest` 77 → **97 OK** (`test_real_probe.py` nuevo: AUTH, CLOSED, silencio con tiempo límite y una sola conexión, un solo evento, agujero negro TLS por proxy, ClientHello restringido, TLS verificado con CA desechable; destinos del proxy para `relay.primal.net:443`; modo observación con aprobador que dice «sí» a todo). Ensayo `--stage rehearsal` ampliado con **E11** (Compuerta B con NDK real) y 4 controles negativos.
- **Desviación declarada:** E11 falló la primera vez por dos supuestos erróneos **míos** (64 hex en el log del relay de laboratorio, que contiene ids públicos; etiqueta `client` que NDK añade a `kind 1`). Se enmendó `definitions-real.md`, se re-evaluó el crudo y se repitió el ensayo completo.
- **Preflight (`run_gate_a.py preflight`, sin tráfico externo):** PASS; 10/10 destinos no permitidos con 403 sin conexión saliente (`connect_denied` ×10, ningún `connect_allowed`); firmante solo en red interna; sin puertos; 0 residuos.
- **Estado:** nada autorizado ni ejecutado externamente. Solicitudes en borrador: `lab/real/solicitud-autorizacion-compuerta-A-primal.md` y `lab/real/solicitud-autorizacion-compuerta-B.md`. Decisión pendiente del propietario: relay, `--tls-groups` (X25519 recomendado o default), fecha y hora de la ventana.

## 4e. Ajuste A1/A2 y clasificación conceptual LAB / DEV / DOC (sin ejecución externa)

- **Decisión humana:** `TLS_GROUPS=X25519` con verificación completa (sin atribución causal al tamaño del ClientHello); secuencia A1 `relay.primal.net` → A2 `relay.primal.io` en una ventana global de 5 minutos, un destino por proxy, un intento por destino, limpieza completa entre ambos, A2 aunque A1 sea GO; la Compuerta B sigue solo preparada. **Implementación por agente:** `run_gate_a.py` (`run` = secuencia; `run_one`, `run_sequence`, `denied_probes`), `test_run_gate_a.py` (14 pruebas con reloj simulado), prueba de proxy para A2, solicitud A1/A2 reescrita, README.
- **Verificación local:** `unittest` del laboratorio 98 OK; `lab/real/test_run_gate_a.py` 14 OK; `pytest` 5 passed; preflight PASS para ambos destinos (10 `connect_denied`, sin `connect_allowed`, el otro relay denegado en cada uno); `check-b` rc=0; Docker 0/0/0.
- **Clasificación conceptual del uso de IA (solo criterio; `ai-log.md` no se modifica ni se reorganiza el repositorio; se aplicará en 1.0A.3):**
  - **LAB** — investigación y validación: laboratorio `lab/` (E1–E11, ensayos locales, sondas A1/A2, preflights, medición del ClientHello, criterios y evaluadores, procedimiento de la Compuerta B, `docs/nip46-*`).
  - **DEV** — implementación del producto: `app/`, `tests/` del proyecto, `pyproject.toml`, Docker raíz. **Sin trabajo DEV en 1.0A.2**: el firmante de `lab/py/lab_real/` es código de laboratorio, no el producto.
  - **DOC** — documentación: `README`, `docs/decisions.md`, `docs/ai-log.md`, `docs/ai-sessions/`, solicitudes de autorización, informes. En esta fase se redactó, pero la consolidación pertenece a 1.0A.3.
- **Pendiente:** autorización expresa con fecha y hora de Chile; 1.0A.3.

## 4f. Secuencia A1/A2 ejecutada (2026-11-20, autorizada 20:03:00–20:08:00 America/Santiago)

- Una sola ejecución del lanzador: inicio real 20:03:00.009, fin 20:03:14.375 (14,4 s; límite 300 s). Un intento por destino, sin reintentos, proxy con un único destino por prueba, limpieza entre A1 y A2.
- **A1 `relay.primal.net:443`: GO.** TCP por el proxy, TLS 1.3 (`TLS_AES_256_GCM_SHA384`, `CERT_REQUIRED`, `check_hostname` verdadero, certificado `primal.net`), WSS, `EOSE` a 1466 ms, `OK` true a 1804 ms, eco a 1862 ms; sin `AUTH`, `NOTICE` ni `CLOSED`; 1 evento publicado; túnel con 1473 B hacia el relay y 4554 B de vuelta.
- **A2 `relay.primal.io:443`: NO-GO.** El proxy registró `connect_failed` (su conexión TCP al destino falló en ≈ 2 s; el proxy no registra si fue DNS o rechazo): no hubo TCP hacia el relay, ni TLS, ni WSS, ni eventos. La sonda terminó con una excepción no capturada (`InvalidProxyStatus: proxy rejected connection: HTTP 502`) y sin JSON de veredicto: defecto de robustez de `probe.py` (no captura `WebSocketException`), sin efecto en la seguridad; **no se corrigió ni se repitió** (no autorizado).
- Evidencia depurada: `lab/results/gate-a-ab/` (excluida de Git). Docker 0/0/0; escaneo de secretos 0 coincidencias (lanzador y verificación independiente). Sin commit ni push; 1.0A.3 y Compuerta B no iniciadas.

## 4g. Cierre técnico de A1/A2 y preparación final de la Compuerta B (sin conexiones externas)

- **Decisión humana:** A1 `relay.primal.net` = GO; A2 `relay.primal.io` = NO-GO; solo `relay.primal.net:443` en lo sucesivo; A2 no se investiga ni se repite sonda alguna. **Implementación por agente:** `probe.py` captura `WebSocketException` (incl. `InvalidProxyStatus`), errores de TLS/TCP, mensajes mal formados y excepciones no previstas y siempre emite JSON (`error`, `error_stage` = `conexion`|`intercambio`|`configuracion`, `error_detail` acotado); la ruta de éxito no cambia. Lanzador: `preflight-b`, `hostile_env`, `GATE_B_RELAY`. Nueva `tests/test_real_guards.py`; procedimiento de la Compuerta B reescrito solo para `relay.primal.net`.
- **Pruebas locales (sin red):** `unittest` del laboratorio **116 OK** (de 98: +14 de fallos —proxy 502/403/cierre/rechazo, TLS con certificado no confiable y sin TLS, WSS con cierre 1011/1000, mensajes mal formados, HTTP no WebSocket, excepción no prevista, CLI con JSON y sin traceback, éxito sin cambios— y +4 guardas de código); `test_run_gate_a.py` 14 OK; `pytest` 5 OK; `preflight-b` PASS (entorno hostil: efectivo `observe`/`tty`, 0 firmas, 0 preguntas de firma); `check-b` rc=0.
- **Verificación de «ninguna cuenta»:** ningún `kind 27235` firmado con el origen real; destinos externos en toda la evidencia local: `relay.nsec.app`, `relay.primal.net`, `relay.primal.io` (fallido); `stacker.news` solo como `CONNECT` de prueba rechazado con 403 por el proxy local; el código de `lab_real/` no importa clientes HTTP ni nombra `stacker.news`.
- **Clasificación conceptual (sin medir ni reconstruir duraciones):** la Compuerta A (sondas A1/A2, preflights, medición del ClientHello) es **LAB**; la robustez de la sonda y la preparación de la Compuerta B son **LAB** (código de laboratorio bajo `lab/`); la redacción de procedimientos y solicitudes es **DOC**; **no hay trabajo DEV** en esta fase (`app/` intacto). Las duraciones de trabajo no se midieron y no se registran.
- **No hecho (restricciones):** Compuerta B, acceso a Stacker News, cuentas, commit/push, Fase 1.0B, cierre 1.0A.3.

## 4h. Controlador de la Compuerta B (`run_gate_b.py`) y Compuerta A local operativa (sin conexiones externas)

- **Contexto:** la Compuerta B autorizada para 20:14–20:19 **no se ejecutó** (no había control automático del límite global; la URI y la pregunta de `connect` no podían manejarse de forma segura desde la herramienta del agente). **Decisión humana:** construir un controlador verificable, validarlo con una nueva Compuerta A **local** y ejecutar la B real solo con nueva autorización expresa.
- **Implementación por agente:** `lab/real/run_gate_b.py` (controlador: terminal real obligatoria, URI solo por la memoria del controlador hacia la pantalla, reenvío acotado de respuestas, ventana ≤ 300 s con reserva de limpieza de 40 s, `Ctrl+C`, limpieza garantizada y forzada por etiqueta, monitor de condiciones de parada, `check`/`rehearsal`/`run`); `lab/real/test_run_gate_b.py` (50 pruebas); `RELAY_ATTEMPTS` en el firmante (un solo intento en la Compuerta B; antes reintentaba hasta 3 veces) y TTLs acotados en `compose.gate-b.yaml`; modo `BUNKER_FROM_STDIN` del cliente NDK local; criterios E12 en `definitions-real.md`; procedimiento de la Compuerta B reescrito para el controlador.
- **Resultados (reales, locales):** `unittest` del laboratorio **119 OK**; `test_run_gate_a.py` 14 OK; `test_run_gate_b.py` **50 OK**; `pytest` 5 OK; `run_gate_b.py check` PASS; ensayos desatendidos con NDK 2.12.2 local y entorno hostil: `full` **GO** (11 firmas denegadas, 0 firmas, `connect` aprobado «humano», URI 1 vez, fin `cliente_termino`, 14,2 s), `manual-stop` **GO** (`interrupcion_manual` por CTRL_BREAK), `timeout` **GO** (`tiempo`, 50,4 s de una ventana de 60 s); Docker 0/0/0; escaneo de secretos 0.
- **Rechazo de terminal no interactiva (medido):** `rehearsal --interactive` y `run` lanzados desde la herramienta del agente terminan en NO-GO antes de tocar Docker.
- **Hallazgos corregidos durante el ensayo:** error de sintaxis JS en el parche de `main.mjs`; mínimo de observación no escalado en ventanas cortas; reutilización de un directorio de evidencia (ahora se rechaza). Reportados en `definitions-real.md` (E12).
- **No verificado:** la comprobación **interactiva real** en la PowerShell del propietario (`rehearsal --interactive`): terminal real, lectura de teclado por hilo, `Ctrl+C` real y confirmación visual de la URI. **No la ejecuté** (requiere su confirmación).
- **Clasificación conceptual (sin medir duraciones):** LAB — controlador, pruebas, ensayos, diagnóstico (incluido el hallazgo de reintentos del firmante); DOC — procedimiento, criterios E12, esta nota; DEV — **ninguno** (el firmante y el controlador son código de laboratorio, no el producto).

## 4i. Cierre documental de la Fase 1.0A y propuesta de la Fase 1.0B (sin conexiones externas)

- **Hecho:** verificación de lo informado por el propietario contra `lab/results/` (ver `docs/phase-1.0A-closure.md` §2); documentos nuevos `docs/phase-1.0A-closure.md` y `docs/phase-1.0B-proposal.md`; actualizados `docs/decisions.md`, `docs/ai-log.md` (entradas 17 a 25 y clasificación LAB/DEV/DOC), `docs/project-context.md`, encabezados de `nip46-real-validation-plan.md`, `nip46-lab-report.md` y `lab/real/README.md`. Se eliminaron dos directorios `__pycache__` generados por mí en `lab/` (cachés regenerables). **No se modificó `app/`, `pyproject.toml`, `constraints.txt`, `AGENTS.md` ni `CLAUDE.md`; no se borró ninguna evidencia; no hubo commit ni push.**
- **Hallazgos de la verificación:** dos ejecuciones interactivas de la Compuerta A local (la primera NO-GO, causa **[NV]**); `session_end` ausente en parada forzada (F-2); sin evaluador para la ejecución real (F-3); ventana autorizada de la B real y lo mostrado por Stacker News **no verificables** localmente.
- **Pendiente:** aprobación del cierre y de la propuesta 1.0B; decisión sobre versionar `lab/` y la evidencia; exportación de transcripciones (1.0A.3, con autorización).
- **Clasificación:** DOC.

## 4j. Cierre formal de la Fase 1.0A, B0 y B1 de la Fase 1.0B (sin conexiones a relays ni a Stacker News)

- **Autorizado por el propietario (2026-11-21 00:26 UTC):** cierre técnico de la 1.0A con observaciones; B0 y B1; pruebas y comprobaciones Docker locales; documentación y registro de IA; exportación de transcripciones; propuesta de B2. **No** B2 a B6.
- **Hecho:** ver `docs/ai-log.md` (entrada 26) y `docs/decisions.md` («Fase 1.0B, Bloques B0 y B1»). Núcleo en `app/nostr/`, configuración en `app/config.py`, 253 pruebas en PASS (1 omitida con aviso), `mypy --strict` limpio y 100 % de cobertura de `app/` con herramientas temporales, verificación en Windows, Linux y Docker; resumen sanitizado de la evidencia en `docs/phase-1.0A-evidence-summary.md`; propuesta de B2 en `docs/phase-1.0B-proposal.md` §9.
- **Pendiente:** criterio parcial de los vectores BIP-340; D-5; decisión sobre versionar `lab/` y los documentos nuevos (commit del propietario); autorización para B2.
- **Clasificación:** DEV (núcleo y configuración), LAB (fixtures y verificaciones), DOC.

## 4k. Cierre de los criterios pendientes de B1 (interacción 27)

Descarga única autorizada del CSV oficial de BIP-340 (SHA-256 `34c9d1d9…851c2d`); 19 vectores ejecutados sin omisiones (9 positivos, 10 negativos); B1 completado. Detalle en `docs/decisions.md` (L-BIP340) y `docs/ai-log.md` (entrada 27). B2 no iniciado.
