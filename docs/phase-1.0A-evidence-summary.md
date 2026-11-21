# Resumen sanitizado de la evidencia de la Fase 1.0A

**Origen y alcance.** Extracto de los archivos de `lab/results/` (excluido de Git; las evidencias originales **se conservan sin modificar**). Contiene solo métricas y estructura: **sin claves, secretos, URI `bunker://`, retos de autenticación ni textos descifrados**. Generado por script a partir de los JSON originales; los SHA-256 permiten comprobar que el original no ha cambiado. Interpretación y salvedades: [phase-1.0A-closure.md](phase-1.0A-closure.md). Horas en UTC (Chile = UTC−3).

## 1. Sondas de relay (Compuerta A)

| Ejecución | Destino | Veredicto | Detalle |
|---|---|---|---|
| Compuerta A (17:00 Chile) | `relay.nsec.app:443` | **NO-GO** | EOSE False, error `TimeoutError`; túnel: 1530 B enviados, 0 B recibidos en 10.0 s; inicio real 2026-11-20T17:00:00.036-03:00 |
| A1 | `relay.primal.net:443` | **GO** | EOSE 1466 ms, OK 1804 ms, eco 1862 ms, `AUTH` False; TLS TLSv1.3 TLS_AES_256_GCM_SHA384, `CERT_REQUIRED`, `check_hostname`=True, CN `primal.net`; `TLS_GROUPS`=X25519 |
| A2 | `relay.primal.io:443` | **NO-GO** | el proxy no logró conectar (`conexiones fallidas`); sin TCP/TLS/WSS; la sonda terminó sin JSON (excepción no capturada, corregida después); destinos vistos por el proxy: ['relay.primal.io:443'] |

Ventana global A1/A2: inicio real 2026-11-20T23:03:00.009+00:00, fin 2026-11-20T23:03:14.375+00:00, duración 14.37 s (límite 300 s), `dentro_de_la_ventana`=True. Residuos Docker finales: A1={'contenedores': 0, 'redes': 0, 'volumenes': 0}, A2={'contenedores': 0, 'redes': 0, 'volumenes': 0}. Nota registrada por el lanzador: TLS_GROUPS=X25519 cambia el ClientHello (~517 B en lugar de ~1530 B): un resultado no permite atribuir causalmente al tamano el fallo anterior de relay.nsec.app.

## 2. Compuerta A local operativa (controlador de la Compuerta B): matriz de criterios E12

| # | Criterio | Interactivo, intento 1 | Interactivo, intento 2 | Desatendido `full` | Desatendido `manual-stop` | Desatendido `timeout` |
|---|---|---|---|---|---|---|
| 1 | `stdin_stdout_son_terminal_real` | sí | sí | n/a | n/a | n/a |
| 2 | `prechecks_check_b_y_preflight_b` | sí | sí | sí | sí | sí |
| 3 | `uri_mostrada_una_sola_vez_en_la_terminal` | sí | sí | sí | sí | sí |
| 4 | `operador_confirma_haber_visto_la_uri` | **NO** | sí | n/a | n/a | n/a |
| 5 | `uri_y_secretos_ausentes_de_archivos` | sí | sí | sí | sí | sí |
| 6 | `modo_observe_y_tty_efectivos_con_entorno_hostil` | sí | sí | sí | sí | sí |
| 7 | `connect_aprobado_manualmente` | sí | sí | sí | sí | sí |
| 8 | `solicitudes_nip46_recibidas` | sí | sí | sí | sí | sí |
| 9 | `sign_event_rechazados_sin_preguntar` | sí | sí | sí | sí | sí |
| 10 | `cliente_ve_todas_las_firmas_denegadas` | sí | sí | sí | n/a | n/a |
| 11 | `cero_firmas` | sí | sí | sí | sí | sí |
| 12 | `cero_aprobaciones_de_firma` | sí | sí | sí | sí | sí |
| 13 | `cero_cuentas_ni_destinos_externos` | sí | sí | sí | sí | sí |
| 14 | `un_solo_lanzamiento_y_un_solo_tunel` | sí | sí | sí | sí | sí |
| 15 | `motivo_de_fin_esperado` | sí | sí | sí | sí | sí |
| 16 | `dentro_de_la_ventana` | sí | sí | sí | sí | sí |
| 17 | `limpieza_docker_sin_residuos` | sí | sí | sí | sí | sí |
| | **Veredicto del evaluador** | **NO-GO** | **GO** | **GO** | **GO** | **GO** |

| Ejecución | Motivo de fin | Duración total (s) | Limpieza (s) | Cliente local | Residuos Docker |
|---|---|---|---|---|---|
| Interactivo, intento 1 | `cliente_termino` | 18.78 | 5.04 | 11 firmas solicitadas, 0 firmadas | {'contenedores': 0, 'redes': 0, 'volumenes': 0} |
| Interactivo, intento 2 | `cliente_termino` | 22.51 | 4.79 | 11 firmas solicitadas, 0 firmadas | {'contenedores': 0, 'redes': 0, 'volumenes': 0} |
| Desatendido `full` | `cliente_termino` | 14.2 | 4.76 | 11 firmas solicitadas, 0 firmadas | {'contenedores': 0, 'redes': 0, 'volumenes': 0} |
| Desatendido `manual-stop` | `interrupcion_manual` | 9.74 | 2.73 | sin cliente | {'contenedores': 0, 'redes': 0, 'volumenes': 0} |
| Desatendido `timeout` | `tiempo` | 50.36 | 5.01 | sin cliente | {'contenedores': 0, 'redes': 0, 'volumenes': 0} |

El intento interactivo 1 dio NO-GO únicamente por el criterio 4 (atestación del operador); causa no registrada.

## 3. Compuerta B real: observación de Stacker News (`gate-b-run-02/`)

| Campo | Valor |
|---|---|
| Destino único | `relay.primal.net:443` (`TLS_GROUPS`=X25519) |
| Ventana configurada / ejecución (Chile) | 2026-11-20T20:50:00.000-03:00 a 2026-11-20T20:55:00.000-03:00 / 2026-11-20T23:50:05.650+00:00 a 2026-11-20T23:54:24.798+00:00 (UTC) |
| Duración total / limpieza | 259.15 s / 4.55 s; `dentro_de_la_ventana`=True |
| Motivo de fin | `tiempo` |
| Modo efectivo | `observe` / aprobación `tty` |
| Métodos recibidos | `connect`: 1, `get_public_key`: 1, `sign_event`: 1 |
| `connect` observado | 2 parámetros de tipo ['str', 'str'], permisos: None |
| Decisiones de `connect` | [[True, 'humano']] |
| Decisiones de `sign_event` | [[False, 'modo_observacion']] |
| `sign_ok` (firmas) | 0 |
| `kind` / `content` / `u` / `method` | 27235 / `Stacker News Authentication` / `https://stacker.news` / `GET` |
| Etiquetas (nombre, nº de valores, longitud) | [['challenge', 1, 64], ['u', 1, 20], ['method', 1, 3]] |
| Campos de la plantilla / tamaño / antigüedad | ['content', 'created_at', 'id', 'kind', 'pubkey', 'tags'] / 362 B / 0 s |
| Forma del reto | `hex64` (el reto no se registra) |
| Comprobaciones de política fallidas | [] |
| Respuestas publicadas (aceptadas por el relay) | {'connect': 1, 'get_public_key': 1, 'sign_event': 1} |
| `session_end` | None (ausente: ver limitación F-2 del cierre) |
| Túneles / destinos vistos / fallidos | 1 / ['relay.primal.net:443'] / 0 |
| Residuos Docker finales | {'contenedores': 0, 'redes': 0, 'volumenes': 0} |
| Escaneo de secretos en la evidencia | `{}` (vacío = sin hallazgos) |

No existe `evaluacion_b.json` para esta ejecución: **no hay veredicto automático** (hallazgo F-3). Lo que mostró la pantalla de Stacker News es una declaración del propietario, sin captura.

## 4. Ensayo local (`--stage rehearsal`, última corrida completa)

20 resultados: PASS=20. Identificadores: `E8`, `E8-control`, `E9`, `E9c`, `E10`, `E10-control:relay_directo_conecta`, `E10-control:ruido_en_el_proxy`, `E10-control:secreto_en_la_salida_del_cliente`, `E10-control:log_driver_json`, `E10-control:puertos_publicados`, `E10-control:variable_api_token`, `E10-control:no_new_privs_cero`, `E10b-s`, `E10b-control`, `E10b-n`, `E11`, `E11-control:valida_firmada`, `E11-control:sign_ok_inyectado`, `E11-control:secreto_en_el_relay`, `E11-control:hex64_en_la_evidencia`.

## 5. Integridad de los originales (SHA-256)

| Archivo original (bajo `lab/results/`) | SHA-256 |
|---|---|
| `real-probe-20261120T165758/probe_stdout.json` | `8f217b201aeae8ed0e6fd11dfa56d6a11ec5e6f59ef04213889dce79a046aaf0` |
| `gate-a-ab/run_meta_global.json` | `286991af7677302b5fb0ebca1e4e51ea621ba7c86b61d1b5fd89993dd9ad8e83` |
| `gate-a-ab/A1/probe_stdout.json` | `016fc2a9b80b0fa7db6c3dd94fdf1906473a892bde7b459298ae7781f4f95a5d` |
| `gate-a-ab/A2/proxy.jsonl` | `279e2d5980867e7915badb52ca76fcd32ce7959e4c66d2f597a4a6e70dd89c3a` |
| `gate-b-rehearsal-20261120T234227Z/evaluacion_b.json` | `bb90c2f54722817a09b621399d0a54d6ded3e6806cdc9c93948cc70b8aa2d0e7` |
| `gate-b-rehearsal-20261120T234353Z/evaluacion_b.json` | `a01136f245c085e936eb7da7a636edfbad663c42e435e91df84a8a3a64c82730` |
| `gate-b-run-02/evidence.jsonl` | `6451ddef86fe725754f31ec6a430dbb1ac84a781871e4903246d11e582769b65` |
| `gate-b-run-02/proxy.jsonl` | `bc66ead7ecbef018f92c0a6d6f547b102b01cf64456dfcdaf5935cd035310656` |
| `gate-b-run-02/run_meta_b.json` | `ccaf8eb0449d439761c8990fb890f3fb2f24ae43bedfec3d8d6290ed90756514` |
| `rehearsal-20261120T230851Z/results.json` | `c8706ddb607726ab44198ecd957e8aae05239b6e42d10966ab79a89ec0175b7b` |
