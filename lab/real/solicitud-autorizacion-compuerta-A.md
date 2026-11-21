# Solicitud de autorización — Compuerta A (sonda del relay)

**HISTÓRICO: esta solicitud (relay.nsec.app) fue autorizada y ejecutada el 2026-11-20 17:00 America/Santiago con resultado NO-GO; la nueva solicitud es `solicitud-autorizacion-compuerta-A-primal.md`.** Texto original: **Estado: BORRADOR para decisión del propietario. No está autorizada. No se ha realizado ninguna conexión externa.** Formato según `AGENTS.md` §11. Los valores entre `[ ]` los completa o corrige el propietario. Una autorización de esta compuerta **no** habilita las compuertas B, C ni D.

## 1. Servicio externo y relay
- Relay propuesto: `wss://relay.nsec.app` (puerto 443). [H: no verificado que esté operativo ni que acepte eventos efímeros; la sonda es precisamente la prueba.]
- Único destino de red permitido: `relay.nsec.app:443`, aplicado por el proxy (`PROXY_ALLOW`).
- Stacker News: **no** se contacta. Otros relays: **no**; si la sonda da NO-GO, cualquier alternativa requiere una autorización nueva.
- Propietario: [confirmar o cambiar el relay] ______

## 2. Identidad
- Ninguna cuenta ni identidad persistente. La sonda genera **una clave desechable en memoria** que se descarta al terminar. No se usa ninguna clave real del propietario ni de terceros.

## 3. Operaciones permitidas (todas, y solo estas)
1. Resolución DNS y túnel `CONNECT` a `relay.nsec.app:443` a través del proxy; TLS de extremo a extremo con verificación de certificado.
2. Una conexión WebSocket y una suscripción (`REQ`) a `kind 24133` dirigida a la clave desechable.
3. Publicar **un** evento `kind 24133` (rango efímero NIP-01), cifrado NIP-44 hacia la propia clave desechable, con contenido fijo sin datos personales.
4. Leer el `OK` y el eco del evento; medir latencias; registrar si el relay envía `AUTH`, `NOTICE` o `CLOSED`.
5. Cerrar la conexión y detener los contenedores.

## 4. Duración y límites
- **Una** ejecución, sin reintentos. Tiempo máximo por paso 10 s; la sesión completa debe terminar en menos de 2 minutos.
- Un solo evento publicado. Si algo falla, no se repite sin nueva autorización.
- Ventana de la autorización: [fecha y hora de inicio y fin] ______

## 5. Restricciones y reglas de aborto
- Sin cuentas, sin Stacker News, sin otros hosts ni puertos, sin cookies ni credenciales.
- **Abortar de inmediato** (`Ctrl+C`, `down -v --remove-orphans`) si el proxy registra un `host:puerto` distinto, si el relay pide `AUTH`/pago, si aparece cualquier secreto en la salida, o si ocurre algo fuera de lo descrito.
- Riesgo aceptado: el relay verá la **IP pública del equipo** del operador y la hora de la conexión (el proxy no oculta la IP).

## 6. Comandos exactos (PowerShell, desde la raíz del repositorio)

```powershell
$env:RELAY_URL    = "wss://relay.nsec.app"
$env:PROXY_ALLOW  = "relay.nsec.app:443"
$env:SN_ORIGIN    = "https://stacker.news"        # requerido por compose; la sonda no lo usa ni contacta ese sitio
$env:EVIDENCE_DIR = (New-Item -ItemType Directory -Force "lab/results/real-probe-$(Get-Date -Format yyyyMMddTHHmmss)").FullName
$c = "docker compose -f lab/real/compose.real.yaml -p nip46-real"
Invoke-Expression "$c up -d proxy"
Invoke-Expression "$c run --rm -T signer python -m lab_real.probe"
Invoke-Expression "$c logs --no-color --no-log-prefix proxy"
Invoke-Expression "$c down -v --remove-orphans"
```

## 7. Evidencia y registro
- Se conserva: el JSON de la sonda (veredicto GO/NO-GO, tiempos, `eose`, `ok`, `echo`, `auth_challenge_received`) y el registro del proxy (solo `host:puerto` y bytes), en `lab/results/` (excluido de Git).
- Veredicto **GO**: `eose`, `ok` y `echo` verdaderos y sin `AUTH`. Cualquier otro resultado = **NO-GO** y se detiene el avance.
- Al cierre se anotará en `docs/ai-log.md` el alcance autorizado y lo realmente ejecutado. El resultado de la sonda **no demuestra** interoperabilidad con Stacker News.

## 8. Verificado localmente antes de pedir esto
Ver el informe de verificación local: 77 pruebas `unittest` OK, E8, E9, E9c, E10, E10b y sus controles negativos en PASS, sin secretos en la evidencia y sin recursos Docker residuales. No verificado: comportamiento del relay público; asignación real de pseudo-TTY.

**Autorizo la Compuerta A con el alcance indicado** (completar): propietario ______  fecha ______
