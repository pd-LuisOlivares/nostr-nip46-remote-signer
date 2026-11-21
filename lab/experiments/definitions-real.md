# Experimentos E8-E10 y criterios de la validación real (Fase 1.0A.2)

Estos criterios se fijaron **antes** de ejecutar el ensayo local y están codificados en `lab/run_lab.py` (`--stage rehearsal`). No se ajustan según los resultados. Veredictos: PASS, FAIL, BLOCKED, INCONCLUSIVE. **Ninguno de estos experimentos tiene conexión externa** y ninguno demuestra interoperabilidad con Stacker News: solo verifican que el firmante real mínimo, su política y su aislamiento se comportan como se diseñó frente a NDK 2.12.2 real y un relay local.

Topología del ensayo: `client` (NDK 2.12.2) y `relay-lab` en `real_egress` (interna en el ensayo); `proxy` en `real_internal` y `real_egress`; `signer` (`lab_real`) solo en `real_internal`. El firmante usa aprobación **con guion** (solo permitida con el relay del laboratorio).

## E8 — Política restrictiva (guion `connect=y,sign=y`)

NDK solicita 11 firmas en este orden: `wrong_origin`, `wrong_content`, `wrong_method`, `extra_tag`, `wrong_kind`, `stale` (−600 s), `future` (+60 s), `bad_challenge`, `tag_order`, `valid`, `replay_same_challenge` (mismo reto que `valid`).

PASS si **todo** es cierto: cliente listo con la identidad esperada; las 9 inválidas y la repetición **no** se firman; cada rechazo lo causa su comprobación (`origen`, `content`, `metodo`, `estructura`, `kind`, `created_at`, `challenge`, `estructura`, `reutilizacion`); `valid` se firma con `id` y firma verificados sin conexión, `pubkey` = identidad, 3 etiquetas sin cambios y todas las comprobaciones OK; **exactamente una** pregunta de firma (`humano`, aprobada) y **un** evento `sign_ok` con autoverificación. INCONCLUSIVE si no se ejercitan las 11 solicitudes. **Control negativo:** el evaluador debe dar FAIL si se le presenta un crudo donde `wrong_origin` aparece firmada.

## E9 — Aprobación humana y límites (guion `connect=y,sign=n,sign=timeout,sign=y,sign=y`, espera máxima 3 s, tope 2)

NDK solicita 5 firmas válidas con retos distintos. PASS si: firman solo la 3.ª y la 4.ª; las decisiones de firma, en orden, son (denegada/`humano`), (denegada/`timeout`), (aprobada/`humano`), (aprobada/`humano`), (denegada/`tope`); las dos firmas verifican (`id`, firma, `pubkey`) y hay 2 eventos `sign_ok`; la solicitud con *timeout* tardó ≥ 2,5 s en resolverse.

## E9c — Denegación por defecto (guion vacío)

PASS si: `blockUntilReady` no resuelve con éxito; la única decisión es `connect` denegada; 0 eventos de política y 0 firmas.

## E10 — Ciclo completo y comprobaciones de seguridad (guion `connect=y,sign=y`, escenario `e2`)

PASS si **todas** se cumplen:

1. NDK completa connect → get_public_key → sign_event y el evento firmado pasa las comprobaciones de servidor de Stacker News (`all_ok`).
2. Todas las respuestas del firmante observadas en el relay son NIP-44.
3. El proxy registra `connect_allowed` a `relay-lab:7777`; el firmante **no** resuelve `relay-lab` directamente; no tiene ruta por defecto; no conecta a una dirección de documentación (`192.0.2.1`).
4. El proxy responde 200 al destino configurado y 403 a otro host, otro puerto y a sí mismo; registra exactamente esos 3 rechazos por «destino fuera de la lista blanca» (`example.com:443`, `proxy:3128`, `relay-lab:7778`) y ningún otro rechazo. *Enmienda posterior a la primera ejecución:* la versión inicial exigía «≥ 3 rechazos» y los habría satisfecho con el ruido del *healthcheck* (conexiones cerradas sin datos); se endureció y el proxy ya no registra esas conexiones vacías.
5. El firmante pertenece solo a la red interna (`internal: true`); el proxy a dos redes; ningún contenedor publica puertos.
6. Firmante y proxy: sistema de archivos de solo lectura, `cap_drop ALL`, `no-new-privileges`, sin privilegios, usuario no root, sin capacidades efectivas.
7. El servicio `signer` usa `logging: none` y `docker compose logs signer` no devuelve salida (hipótesis [H] del plan, ahora medida).
8. El entorno del firmante no tiene variables con nombre de secreto (`KEY`, `SECRET`, `TOKEN`, `NSEC`, `PASS`), salvo `GPG_KEY`, que viene de la imagen base de Python (huella pública para verificar CPython). *Enmienda posterior a la primera ejecución:* la primera versión del evaluador marcó `GPG_KEY` como falso positivo y comprobaba los puertos del contenedor `client`, que ya no existe al inspeccionar (`run --rm`); ambos fallos eran del evaluador y no del sistema, y se corrigieron y declararon antes de repetir el ensayo completo.
9. `probe.py` por el proxy contra el relay local da veredicto GO.
10. SIGINT (interruptor de emergencia) produce `session_end` con motivo `interruptor_de_emergencia`.
11. El secreto de la URI (leído solo para esta comprobación) no aparece en la evidencia, el crudo del cliente, los registros del proxy, los del relay ni la salida de la sonda; tampoco `bunker://` ni `nsec1`.
12. La evidencia y los registros del proxy no contienen ninguna cadena de 64 hex.
13. `/tmp` del firmante está vacío y `/ctl` (solo ensayo) contiene únicamente `bunker.txt` e `identity.txt`.

**Limitación declarada:** las claves privadas desechables solo existen en la memoria del firmante y no se pueden buscar por valor desde fuera; su ausencia en disco y registros se garantiza por construcción (sistema de archivos de solo lectura, lista blanca de evidencia con pruebas, `logging: none`) y se comprueba por forma (sin 64 hex ni `nsec1`), no por valor.

## E10-control — Controles negativos del evaluador de E10 (añadidos en la reanudación de 1.0A.2, antes de ejecutarlos)

Sobre una copia del crudo de E10 se altera **un** dato por vez y el evaluador debe dar FAIL **por la comprobación esperada** (y solo entonces el control es PASS): `relay_directo = "conecta"` → `sin_acceso_directo_al_relay`; un rechazo de proxy con otro motivo → `sin_ruido_en_el_proxy`; el secreto de la URI añadido a la salida del cliente → `secreto_de_la_uri_ausente_de_toda_la_evidencia`; `log_driver = json-file` → `logging_none_sin_salida_conservada`; puertos publicados en el firmante → `sin_puertos_publicados`; una variable `API_TOKEN` en el entorno → `sin_variables_con_forma_de_secreto`; `NoNewPrivs = 0` → `no_root_y_sin_capacidades`.

## E10b — Flujo interactivo de aprobación y visualización de la URI (guion **no** usado: aprobación por terminal)

El firmante arranca con `APPROVAL_MODE=tty`, sin `URI_FILE`, con el relay local detrás del proxy, y se ejecuta **en primer plano** con la entrada estándar enlazada al orquestador (`docker compose run --rm -T`; no hay pseudo-TTY disponible desde el orquestador, ver limitaciones). Un cliente de una sola vez (`tests/interactive_client.py`) lee la URI **de la salida del firmante** y envía `connect` y `get_public_key`. Dos variantes: respuesta `s` y respuesta `n`.

PASS de cada variante si **todo** es cierto: (1) la URI `bunker://` aparece **una sola vez** en la salida del firmante y la pregunta «Activar esta conexion?» después; (2) con `s` el cliente recibe `ack` y luego la clave pública de la identidad (mismos 8 primeros caracteres que muestra el firmante); con `n` recibe `unauthorized` y `get_public_key` también `unauthorized`; (3) la evidencia registra `approval_mode = tty` y una decisión `connect` (aprobada solo con `s`, motivo `humano`); (4) el contenedor tiene `LogConfig = none` y `docker logs` no devuelve nada; (5) mientras el firmante corre, `/tmp` y `/ctl` están vacíos (la URI no se escribió en ningún archivo); (6) el secreto de la URI y el texto `bunker://` no aparecen en la evidencia, los registros del proxy ni los del relay. **Control negativo:** el evaluador debe dar FAIL si se le presenta el secreto dentro de la salida de `docker logs`.

## E11 — Compuerta B en ensayo local: el modo observación deniega TODA firma (añadido en la preparación de la nueva Compuerta A/B, antes de ejecutarlo)

Escenario `e8` de NDK 2.12.2 (11 solicitudes de firma, incluida una **válida** y la repetición de su reto) contra el firmante real con `MODE=observe` y un guion que **aprueba todo** (`connect=y` + 30 × `sign=y`): si existiera una ruta de aprobación accidental, firmaría.

PASS si **todo** es cierto: (1) el cliente queda listo con la identidad esperada (connect y `get_public_key` sí funcionan); (2) se ejercitan las 11 solicitudes y **ninguna** se firma, tampoco la válida; (3) la evidencia no tiene ningún `sign_ok` ni ningún evento `policy` (la ruta de firma no se alcanza); (4) hay 11 decisiones de firma y todas son (denegada, `modo_observacion`), ninguna con motivo `humano`; (5) los 11 eventos `observed_sign` reflejan lo que NDK envió: `u` (`https://evil.invalid` en `wrong_origin`, el origen del laboratorio en el resto), nº de etiquetas (4 en `extra_tag` y en `wrong_kind`, 3 en el resto), `kind` (1 en `wrong_kind`), etiqueta `method` (`POST` en `wrong_method`), `content` (`otro texto` en `wrong_content`), forma del reto (`otro` en `bad_challenge`, `hex64` en el resto), antigüedad (≈ 600 s en `stale`, ≈ −60 s en `future`, entre −5 y 10 s en el resto), primera etiqueta `u` en `tag_order`, y el mismo `challenge_sha16` en `valid` y `replay_same_challenge`; (6) `observed_request` registra `connect`, `get_public_key` y exactamente 11 `sign_event`; (7) ni el reto en claro de ninguna variante, ni `bunker://`, `secret=` ni `nsec1` aparecen en la evidencia, el proxy ni el relay, y ninguna cadena de 64 hex aparece en la evidencia ni en el proxy (como en E10 n.º 12). **Controles negativos** (cada uno debe fallar exactamente por su comprobación): `valid.signed = true` → (2); un `sign_ok` inyectado en la evidencia → (3); `bunker://` inyectado en el registro del relay → (7); 64 hex inyectados en la evidencia → (7); 64 hex inyectados en el registro del relay **no** deben hacer fallar (7) (el relay del laboratorio registra ids y claves públicas).

*Enmiendas posteriores a la primera ejecución de E11 (el firmante se comportó bien; fallaron dos supuestos míos, ya corregidos y declarados):* (a) la versión inicial de (7) exigía ausencia de 64 hex también en el registro del relay, que por diseño contiene ids de evento y claves públicas (E10 ya limitaba ese escaneo a evidencia y proxy); (b) la versión inicial de (5) suponía 3 etiquetas en `wrong_kind`, pero NDK 2.12.2 añade una etiqueta `client` a los eventos `kind 1`, observada tal cual por el firmante (los `kind 27235` salen con 3 etiquetas). Se volvió a evaluar el crudo de esa misma ejecución con el evaluador corregido y después se repitió el ensayo completo.

## E12 — Compuerta A local operativa: controlador `run_gate_b.py` (ensayo local; criterios codificados en `evaluate_lab` antes de la primera ejecución)

Infraestructura 100 % local (proyecto Docker propio `nip46-gateb-lab`: relay de laboratorio, proxy, firmante con el override de la Compuerta B y cliente NDK 2.12.2 que recibe la URI por stdin), con **entorno hostil** (`MODE=sign`, `APPROVAL_MODE=scripted`, guion `connect=y,sign=y`, `URI_FILE`). Escenarios: `full` (11 solicitudes de firma, una válida), `manual-stop` (parada manual; en el ensayo desatendido, `CTRL_BREAK` al controlador) y `timeout` (ventana de 60 s, sin cliente). Variante **interactiva** (`--interactive`, persona en PowerShell) y **desatendida** (`--auto`, stdin simulado; **no sustituye** a la interactiva).

GO si **todos** los criterios aplicables son verdaderos y la ejecución no se abortó: (1) *solo interactivo:* stdin y stdout del controlador son una terminal real; (2) check-b y preflight-b dieron PASS antes de conectar; (3) la URI aparece **una sola vez** en la terminal (y, en el desatendido, el arnés lo comprueba de forma independiente); (4) *solo interactivo:* el operador confirma haberla visto; (5) ni la URI ni su secreto están en ningún archivo (escaneo de `bunker://`, `secret=`, `nsec1`, `authorization`, `cookie`, `bearer`, 64 hex en el directorio de evidencia y `pre/`; el arnés busca además el secreto concreto); (6) modo efectivo `observe` y aprobación `tty` pese al entorno hostil; (7) `full`: una única decisión de `connect` (`humano`, aprobada), 0 en los demás; (8) `full`: `connect`≥1, `get_public_key`≥1 y exactamente 11 `sign_event` recibidos; los demás escenarios, ninguna solicitud; (9) `full`: 11 decisiones de firma, todas (denegada, `modo_observacion`), 11 `observed_sign`, ninguna pregunta de firma (el guion/teclado ofrece «sí» sobrante que nadie consume); (10) `full`: el cliente ve las 11 firmas denegadas y 0 firmadas; (11) 0 `sign_ok` y 0 firmas en `session_end`; (12) 0 aprobaciones de firma; (13) el proxy solo vio el destino de laboratorio y no aparece `stacker.news` (0 cuentas: no hay ruta a Stacker News); (14) un solo lanzamiento del firmante, ≤ 1 túnel y 0 conexiones fallidas; (15) motivo de fin esperado (`cliente_termino`, `interrupcion_manual`, `tiempo`); (16) fin y limpieza dentro de la ventana; (17) 0 contenedores, redes y volúmenes del proyecto tras la limpieza.

Pruebas de mutación del evaluador: cada violación (firma, aprobación de firma, URI repetida, secreto en archivo, residuo Docker, fuera de ventana, motivo de fin, destino ajeno, segundo túnel, modo distinto de observe, prechecks, connect sin aprobar, firmas sin rechazar, cliente con firma) invierte el veredicto a NO-GO por su propio criterio (`test_run_gate_b.py::VerdictCase`).

*Hallazgos corregidos durante el ensayo (de implementación, no de criterio):* (a) el parche de `main.mjs` convirtió un `\n` de JavaScript en salto de línea real (error de sintaxis; el cliente salía con código 1); (b) el mínimo de 90 s de observación abortaba ventanas de ensayo de 60 s: ahora es 90 s con la ventana real (≥ 200 s) y 50 % en las cortas, y el ensayo empieza 30 s después de arrancar para dejar sitio a los prechecks; (c) reutilizar un directorio de evidencia mezclaba dos ejecuciones: ahora el controlador se niega a empezar si ya hay datos y no sobrescribe nada.

## Validación real (para la Fase 1.0A.2 con autorización externa)

Niveles de éxito S0-S6, abortos y compuertas A-D: ver `docs/nip46-real-validation-plan.md` §13-§14 y `lab/real/README.md`.
