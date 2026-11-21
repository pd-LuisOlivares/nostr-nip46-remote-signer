# Firmante remoto mínimo y ensayo local (Fase 1.0A.2)

**Estado (cierre de la Fase 1.0A, ver `docs/phase-1.0A-closure.md`):** implementado y ensayado en local (E8-E12). Compuertas A y B **ejecutadas** el 2026-11-20 (observación sin firma); **C y D no**. El texto siguiente conserva el estado previo a esas ejecuciones y puede quedar desactualizado en los detalles. La **única** conexión externa realizada hasta ahora fue la Compuerta A con `relay.nsec.app:443` (2026-11-20, **NO-GO**: el relay no respondió al ClientHello de 1530 B; causa sin determinar). **Todo lo que está bajo «Procedimientos con conexión externa» y no figure como ejecutado NO se ha ejecutado y requiere autorización explícita del propietario** con el alcance de `AGENTS.md` §11. Esto es código de laboratorio (`lab/py/lab_real/`); no es el firmante definitivo ni se importa desde `app/`.

## Qué hay

| Pieza | Archivo | Función |
|---|---|---|
| Firmante | `lab/py/lab_real/signer.py` | Atiende solo `connect`, `get_public_key`, `sign_event`, `ping`; claves desechables en memoria; aprobación humana por solicitud; tope de firmas |
| Política | `lab/py/lab_real/policy.py` | Funciones puras para `kind 27235` (11 comprobaciones) |
| Aprobación | `lab/py/lab_real/approval.py` | Terminal (TTY) con tiempo máximo y denegación por defecto; guion automático **solo** con el relay del laboratorio |
| Evidencia | `lab/py/lab_real/evidence.py` | JSONL con lista blanca de eventos y campos; rechaza valores con forma de secreto |
| Proxy | `lab/py/lab_real/proxy.py` | `CONNECT` a **un** `host:puerto`; no intercepta TLS |
| Sonda | `lab/py/lab_real/probe.py` | Un evento efímero con clave desechable para medir el relay (EOSE, OK, eco, `AUTH` → se detiene sin autenticar, latencia, datos públicos de TLS) |
| TLS | `lab/py/lab_real/tls.py` | Opcional `TLS_GROUPS=X25519`: mismo contexto verificado, ClientHello de ~517 B en lugar de ~1530 B (OpenSSL 3.5). Vacío = comportamiento por defecto |
| Lanzador | `lab/real/run_gate_a.py` | `check`, `check-b`, `preflight` (sin tráfico externo) y `run` (secuencia A1→A2 en una ventana global de 5 min, un intento por destino, limpieza completa entre pruebas y escaneo de secretos). Destinos fijados en código |
| Compose | `lab/real/compose.real.yaml` | `proxy` (redes `real_internal` y `real_egress`) y `signer` (solo `real_internal`, `internal: true`). `MODE` es `observe` por defecto: firmar exige `MODE=sign` explícito |
| Controlador B | `lab/real/run_gate_b.py` | Controlador de la Compuerta B desde PowerShell (terminal real, URI solo en pantalla, ventana ≤ 300 s con reserva de limpieza, `Ctrl+C`, limpieza garantizada). Modos `check`, `rehearsal` (local) y `run` (real; solo con autorización) |
| Compuerta B | `lab/real/compose.gate-b.yaml` | Fija `MODE=observe`, aprobación por terminal, sin guion ni archivo de URI con valores literales (una variable de entorno olvidada no puede anularlos) |
| Ensayo | `lab/real/compose.rehearsal.yaml` + `lab/run_lab.py --stage rehearsal` | Misma topología con relay local y NDK real; `real_egress` también interna |

El firmante no tiene ruta a Internet: lo único que alcanza es el proxy, que solo acepta `CONNECT` al destino de `PROXY_ALLOW`. El certificado del relay lo verifica el firmante con la CA del sistema de la imagen (comprobado con una CA desechable en `tests/test_real_proxy.py`).

## Requisitos

- Docker Compose v2 y las imágenes del laboratorio, construidas **sin red** desde `lab/vendor/` (hashes verificados): `docker compose -f lab/compose.yaml -p nip46-lab build relay signer-ref`.
- Ninguna dependencia nueva respecto a la Fase 1.0A.1.

## Ensayo local (sin conexiones externas)

```powershell
# Pruebas unitarias (119) dentro del contenedor
docker compose -f lab/compose.yaml -p nip46-lab run --rm -T -e LAB_QUIET=1 py-job python -W error::ResourceWarning -m unittest discover -s tests -t . -v
docker compose -f lab/compose.yaml -p nip46-lab down -v --remove-orphans

# E8, E9, E9c, E10 (+ controles negativos), E10b (flujo interactivo) y E11 (modo observación de la Compuerta B) con NDK 2.12.2 real, firmante real, proxy y relay local
python -X utf8 lab/run_lab.py --stage rehearsal

# Comprobaciones previas de la Compuerta A SIN tráfico externo (nunca envían el destino permitido; limpian al terminar)
python -X utf8 lab/real/run_gate_a.py check     --tls-groups X25519
python -X utf8 lab/real/run_gate_a.py preflight --tls-groups X25519 --evidence-dir lab/results/gate-a-preflight
python -X utf8 lab/real/run_gate_a.py check-b   --tls-groups X25519
python -X utf8 lab/real/run_gate_a.py preflight-b --tls-groups X25519 --evidence-dir lab/results/gate-b-preflight   # Compuerta B bajo entorno hostil: 0 firmas
python -X utf8 -m unittest lab/real/test_run_gate_a.py      # secuencia A1/A2 con reloj y ejecutor simulados (14 pruebas, sin red)
python -X utf8 -m unittest lab/real/test_run_gate_b.py      # controlador de la Compuerta B con reloj, procesos y Docker falsos (50 pruebas, sin red)

# Compuerta A LOCAL operativa del controlador de la Compuerta B (infraestructura local; la INTERACTIVA la opera el propietario en PowerShell)
python -X utf8 lab/real/run_gate_b.py check --tls-groups X25519
python -X utf8 lab/real/run_gate_b.py rehearsal --auto --scenario full --window-s 180     # desatendido (stdin simulado)
python -X utf8 lab/real/run_gate_b.py rehearsal --auto --scenario manual-stop --window-s 60
python -X utf8 lab/real/run_gate_b.py rehearsal --auto --scenario timeout --window-s 60
python -X utf8 lab/real/run_gate_b.py rehearsal --interactive --scenario full               # INTERACTIVO: URI en su terminal, aprobacion manual de connect
```

Criterios fijados de antemano: `lab/experiments/definitions-real.md`. Resultados crudos (sin secretos, excluidos de Git): `lab/results/rehearsal-<fecha>/`. Limpieza (solo ese proyecto): `docker compose -f lab/real/compose.real.yaml -f lab/real/compose.rehearsal.yaml -p nip46-rehearsal down -v --remove-orphans` (requiere las variables de entorno del ensayo; `run_lab.py` ya la ejecuta al terminar).

## Procedimientos con conexión externa (requieren autorización por compuerta)

Variables comunes (PowerShell) para B y C. Los valores `RELAY_*` y `SN_ORIGIN` son **propuestas** hasta que el propietario las apruebe:

```powershell
$env:RELAY_URL   = "wss://relay.primal.net"    # propuesta (opción principal); relay.nsec.app dio NO-GO y relay.primal.io (alternativa) NO está verificado ni autorizado
$env:PROXY_ALLOW = "relay.primal.net:443"      # UN solo host:puerto; el proxy rechaza listas y comodines al arrancar
$env:SN_ORIGIN   = "https://stacker.news"      # provisional: se confirma en la Compuerta B
$env:TLS_GROUPS  = "X25519"                    # ClientHello pequeño (ver tls.py); vacío = por defecto
$env:EVIDENCE_DIR = (New-Item -ItemType Directory -Force "lab/results/real-$(Get-Date -Format yyyyMMddTHHmmss)").FullName
$c = "docker compose -f lab/real/compose.real.yaml -p nip46-real"
```

### Compuerta A — sondas del relay (A1 y A2, un intento por destino y autorización)

Historial: **primera sonda, `relay.nsec.app:443`, 2026-11-20 17:00 America/Santiago: NO-GO** (TCP abierto, 1530 B enviados, 0 B recibidos; sin TLS). **A1/A2 ejecutadas el 2026-11-20 20:03 (`TLS_GROUPS=X25519`): `relay.primal.net` GO; `relay.primal.io` NO-GO (el proxy no logró conectar)**. Se descartó `relay.primal.io` y no se investiga; las siguientes validaciones usan solo `relay.primal.net:443`. Cada nueva ejecución externa requiere autorización nueva (`solicitud-autorizacion-compuerta-A-primal.md` queda como histórico de A1/A2). La sonda ahora devuelve siempre un JSON estructurado (`error`, `error_stage`, `error_detail`) ante fallos de proxy, TLS o WSS.

Efecto externo: por destino, **una** conexión `wss` y **un** evento efímero (`kind 24133`, cifrado, hacia una clave desechable propia); en el proxy solo hay **un** destino por prueba y A2 se ejecuta aunque A1 sea GO. Sin Stacker News, sin cuenta, sin identidad real. Se ejecuta **solo** con el lanzador, que impone la ventana, el destino fijado en código, un único intento, la limpieza y el escaneo de secretos:

```powershell
python -X utf8 lab/real/run_gate_a.py run --tls-groups X25519 --start 2026-MM-DDTHH:MM:00-03:00 --evidence-dir lab/results/gate-a-ab
```

Criterio GO: `eose`, `ok` y `echo` verdaderos, sin `auth_challenge_received`. `AUTH` → se registra y se detiene sin autenticar. Si el proxy registra cualquier otro `host:puerto`, o el veredicto no es GO: detenerse y no pasar a la siguiente compuerta ni cambiar de relay sin autorización nueva.

### Compuerta B — Ejecución 0 (observación sin efecto): el firmante **niega** siempre la firma

Se ejecuta **solo** con `run_gate_b.py run` desde la PowerShell del propietario. Procedimiento completo, interacción manual, parada, pasos que exigen autorización adicional y datos que debe fijar el propietario: `solicitud-autorizacion-compuerta-B.md` (solo `relay.primal.net`). Prerrequisito: la Compuerta A local interactiva en GO. Resumen: se usa `compose.gate-b.yaml` (fija `MODE=observe`; no anulable por el entorno), `python lab/real/run_gate_a.py check-b …` debe dar rc=0 y el firmante imprime «MODO OBSERVACION». El operador sigue el flujo de `docs/nip46-real-validation-plan.md` §10 en una ventana privada hasta que Stacker News envía `sign_event`; el firmante **imprime la estructura recibida y deniega sin preguntar**. Se anota el `u` recibido para fijar `SN_ORIGIN`. **No se crea cuenta.** Salida: `Ctrl+C` (interruptor de emergencia).

### Compuerta C — Ejecución 1 (registro real con identidad desechable): **crea una cuenta real**

```powershell
$env:MODE = "sign"; $env:SN_ORIGIN = "<valor observado en la Compuerta B>"      # MODE=sign explícito: por defecto el firmante solo observa
Invoke-Expression "$c run --rm signer"
Remove-Item Env:MODE                                                          # no dejarlo puesto: una sesión posterior firmaría
```

Cada solicitud pide aprobación humana (`s` = sí; todo lo demás o 120 s sin respuesta = no). Tope: 2 firmas por sesión. La cuenta creada queda **huérfana** al terminar (la clave desechable solo existía en memoria).

### Cierre de cualquier sesión real

```powershell
Invoke-Expression "$c down -v --remove-orphans"      # solo el proyecto nip46-real
```

La URI `bunker://` **no se guarda en ningún archivo** (solo en la terminal); no la pegue en chats, capturas ni documentos. El servicio `signer` usa `logging: none`. Antes de conservar una captura, revise que no contenga la URI, el `secret=`, cookies ni tokens. La evidencia JSONL de `EVIDENCE_DIR` solo contiene eventos de una lista blanca.

## Qué debe aprobar el propietario antes de cualquier conexión real

1. **Relay:** host y URL exactos (propuesta `wss://relay.primal.net`, puerto 443) y su política de reserva si la sonda da NO-GO (cada alternativa, p. ej. `relay.primal.io`, requiere su propia verificación y autorización; ninguna está autorizada hoy).
2. **Autorización por compuerta** con los cinco puntos de `AGENTS.md` §11: servicio/relays, identidad o cuenta de **prueba**, operaciones permitidas, duración y límites, restricciones. Una autorización por compuerta (A, B, C, D); ninguna habilita la siguiente.
3. **Identidad:** confirmar que solo se usan claves desechables generadas en memoria por el firmante, y que la cuenta de Stacker News creada en la Compuerta C queda huérfana y se acepta que no se pueda borrar.
4. **`SN_ORIGIN`:** confirmar que se fija a partir de la Ejecución 0 (observación sin firma) y no por suposición.
5. **Operaciones permitidas:** conexión `wss` al relay; en B, abrir `/signup` y recibir `sign_event` sin firmarlo; en C, **una** firma y el registro; en D (opcional), un segundo inicio de sesión con la misma sesión del firmante.
6. **Duración y límites:** vida del secreto (600 s), de la conexión (30 min) y de la sesión (60 min); tope de 2 firmas; ventana de ±120 s (sujeta a que Stacker News la tolere).
7. **Restricciones:** sin cuentas personales ni reales no designadas, sin otros relays, sin otras solicitudes a Stacker News fuera del flujo, sin publicar eventos distintos del de la sonda y las respuestas NIP-46.
8. **Evidencia:** qué se conserva (JSONL sin secretos y capturas redactadas), dónde (fuera de Git) y cuál se selecciona después para la documentación.
9. **Reloj y tiempos:** navegador y firmante en el mismo equipo; aceptar que una aprobación lenta o una URI caducada se clasifica como fallo de tiempo, no de protocolo.

## Limitaciones conocidas

- Lo ensayado aquí es **local**: ninguna prueba demuestra interoperabilidad con Stacker News ni con el relay público.
- El relay público puede exigir `AUTH` (NIP-42) o limitar la tasa; la sonda lo mide y el firmante **no** implementa `AUTH`.
- Tras alcanzar el tope de firmas el firmante **sigue activo y deniega** toda firma adicional (el plan decía «se cierra»); se cierra por `Ctrl+C` o por la vida máxima de la sesión.
- `signer` con `logging: none`: E10b midió que la URI aparece **una sola vez** en la salida del firmante en primer plano, que la aprobación por terminal funciona (`s` y `n`), que `docker logs` no devuelve contenido (solo el error «configured logging driver does not support reading») y que `/tmp` y `/ctl` quedan vacíos. **Se hizo con la entrada estándar enlazada (`run -T`), no con un pseudo-TTY**: la asignación real de TTY (`docker compose run` sin `-T`) solo se verifica en la primera ejecución interactiva autorizada.
- Las claves privadas no se pueden buscar por valor desde fuera; su ausencia en disco y registros se garantiza por construcción y se comprueba por forma.
- El proxy resuelve el nombre del relay dentro de su propio contenedor: el DNS del relay lo hace el proxy, no el firmante.
