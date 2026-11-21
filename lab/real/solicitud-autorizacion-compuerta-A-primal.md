# Solicitud de autorización — Compuerta A, secuencia A1/A2 (relay.primal.net y relay.primal.io)

**HISTÓRICO: autorizada y ejecutada el 2026-11-20 20:03–20:03:14 (America/Santiago): A1 `relay.primal.net` GO, A2 `relay.primal.io` NO-GO. Ver sección 4f del documento de continuidad.** Texto original: **Estado: BORRADOR para autorización expresa. No está autorizada y no se ha realizado ninguna conexión externa desde la preparación.** Formato según `AGENTS.md` §11. Decisiones del propietario ya incorporadas: `TLS_GROUPS=X25519` con verificación TLS completa; ventana global de cinco minutos con dos pruebas secuenciales; A2 se ejecuta aunque A1 sea GO. Falta únicamente la **fecha y hora de inicio en Chile**. Esta autorización no habilita la Compuerta B (Stacker News), la C ni la D.

## 0. Antecedente y límite de interpretación
- La Compuerta A anterior (`relay.nsec.app:443`) terminó NO-GO: 1530 B enviados, 0 B recibidos.
- Medido sin red: el ClientHello por defecto de nuestro cliente es de 1530 B; con X25519, 517 B.
- **Registro obligatorio:** usar `X25519` es un cambio de configuración, no un experimento controlado. Un GO o un NO-GO de A1/A2 **no permite atribuir causalmente** al tamaño del ClientHello el fallo anterior (el relay y el momento también son distintos). El lanzador lo deja escrito en `run_meta_global.json`.
- `relay.primal.net` tiene TCP/WSS verificados a mano desde Windows (dato del propietario). `relay.primal.io` **no** tiene conectividad verificada y no se asume equivalente. Ambos pertenecen presumiblemente al mismo operador [H], así que la comparación no es entre terceros independientes.

## 1. Servicios y destinos
| Prueba | Destino único permitido en el proxy | Orden |
|---|---|---|
| A1 | `wss://relay.primal.net:443` (`PROXY_ALLOW=relay.primal.net:443`) | primero |
| A2 | `wss://relay.primal.io:443` (`PROXY_ALLOW=relay.primal.io:443`) | segundo, siempre que A1 no haya disparado una parada global |
- **Nunca ambos a la vez:** cada prueba levanta su propio proxy con un solo `host:puerto`; al terminar A1 se ejecuta `down -v --remove-orphans` y se verifica 0 contenedores/redes/volúmenes antes de iniciar A2. En cada prueba el proxy debe rechazar al otro relay (comprobado en el preflight).
- Stacker News: **no** se contacta. Otros destinos: no.

## 2. Identidad
Una clave desechable en memoria por prueba (distinta en A1 y A2), descartada al terminar. Sin cuentas, sin claves reales, sin NIP-42 (no se responde a `AUTH`).

## 3. Operaciones permitidas (por prueba, y solo estas)
1. DNS y `CONNECT` al destino de esa prueba a través del proxy; TLS de extremo a extremo con verificación de certificado y de nombre (CA del sistema), `TLS_GROUPS=X25519`.
2. Una conexión WebSocket y **una** suscripción (`REQ`, `kind 24133`, `#p` = clave desechable).
3. **Como máximo un** evento `kind 24133` (efímero), cifrado NIP-44 hacia la propia clave, contenido fijo, solo tras `EOSE`.
4. Leer `OK` y el eco; registrar `AUTH`, `NOTICE`, `CLOSED`; cerrar y limpiar.
Total máximo de eventos publicados en toda la sesión: **2** (uno por destino).

## 4. Límites de tiempo
- **Ventana global: 5 minutos**, incluida la limpieza. Inicio programado `[AAAA-MM-DD HH:MM:00]` America/Santiago (UTC-03:00); límite duro `inicio + 300 s`.
- No se inicia nada pasado `inicio + 60 s`. Antes del inicio no hay tráfico (el lanzador solo espera).
- Por prueba: un intento; apertura TLS/WS ≤ 10 s, espera total de la sonda ≤ 20 s, tope del contenedor 60 s (o lo que quede menos 15 s); limpieza ≤ 45 s.
- A2 solo arranca si quedan ≥ 90 s de ventana y se ejecuta, además, aunque A1 sea GO o NO-GO. Peor caso calculado: A1 termina a `+135 s` y A2 aún dispone de más de 90 s; esperado: ≈ 15–40 s por prueba.
- **Sin reintentos automáticos** en ninguna capa (la sonda y el lanzador no tienen bucles de reintento; probado con un relay que no responde: una sola conexión).

## 5. Paradas (el resto de la secuencia no se ejecuta)
- Inicio fuera de ventana; falla la comprobación estática de configuración o hay residuos previos.
- El proxy registra un `host:puerto` distinto del de esa prueba; aparece cualquier secreto (`nsec1`, `bunker://`, `secret=`, `authorization`, `cookie`, `bearer`, 64 hex) en la evidencia; quedan recursos Docker tras la limpieza.
- Se alcanza el límite duro.
Nota: `AUTH` o un fallo TLS en A1 **no** son parada global: esa prueba se registra como NO-GO (sin autenticar ni publicar) y A2 continúa, porque su resultado es independiente.

## 6. Comandos
Antes (sin red; ya ejecutados en la preparación y repetibles):
```powershell
python -X utf8 -m unittest lab/real/test_run_gate_a.py
python -X utf8 lab/real/run_gate_a.py preflight --tls-groups X25519 --relay-host relay.primal.net --evidence-dir lab/results/gate-a-preflight/relay.primal.net
python -X utf8 lab/real/run_gate_a.py preflight --tls-groups X25519 --relay-host relay.primal.io  --evidence-dir lab/results/gate-a-preflight/relay.primal.io
```
Ejecución (una sola orden; puede lanzarse antes de la hora: espera hasta `--start`):
```powershell
python -X utf8 lab/real/run_gate_a.py run --tls-groups X25519 --start 2026-MM-DDTHH:MM:00-03:00 --evidence-dir lab/results/gate-a-ab
```

## 7. Evidencia esperada (`lab/results/gate-a-ab/`, excluida de Git)
- `A1/` y `A2/`: `probe_stdout.json` (veredicto, `eose`, `ok`, `echo`, `auth_challenge_received`, avisos, versión/cifrado TLS y certificado público), `proxy.jsonl` (solo `host:puerto`, bytes y segundos), `probe_stderr_tail.txt`, `run_meta.json` (horas reales, intentos, destinos vistos, residuos, escaneo de secretos).
- `run_meta_global.json`: ventana, inicio/fin reales, duración total, `dentro_de_la_ventana`, tabla `comparacion` A1 vs A2 (latencias a EOSE/OK/eco, TLS, clasificación automática), nota de causalidad.
- Clasificación final (informe, no automática) por destino: **GO** (`eose`, `ok`, `echo`, sin `AUTH`), **PARTIAL** (WSS con TLS verificado pero falta algo; no se convierte en GO), **NO-GO**. Se distingue, cuando la evidencia lo permite, relay / conectividad / nuestra implementación.
- Limpieza final: `docker compose -p nip46-real down -v --remove-orphans` (solo ese proyecto) y recuento 0/0/0. Se anotará en `docs/ai-log.md` (en 1.0A.3) el alcance autorizado y lo ejecutado. Ningún resultado demuestra interoperabilidad con Stacker News.

## 8. Riesgos aceptados al autorizar
Cada relay verá la **IP pública** del equipo y la hora de su prueba; si A1 da GO se publican **dos** eventos efímeros en total, uno por relay; A2 se ejecuta sin conectividad previa verificada.

**Autorizo esta secuencia A1/A2 con el alcance indicado** (completar): propietario ______  fecha y hora de inicio (Chile) ______
