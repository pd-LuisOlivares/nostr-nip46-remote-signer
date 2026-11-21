# Compuerta B — Observación sin efecto de la interacción inicial con Stacker News

**Estado: PROCEDIMIENTO LISTO, SIN EJECUTAR y SIN AUTORIZAR.** No se ha contactado a Stacker News. Relay: **exclusivamente `wss://relay.primal.net:443`** (A1 dio GO el 2026-11-20; `relay.primal.io` dio NO-GO y está descartado por ahora; `relay.nsec.app` dio NO-GO). Requiere una autorización específica del propietario con los cinco puntos de `AGENTS.md` §11 (apartado 6). Una autorización de A no habilita B.

## 1. Objetivo
Observar **qué envía realmente** Stacker News al firmante cuando se inicia el registro por Nostr: método `connect` (parámetros y permisos solicitados) y la solicitud `sign_event` (estructura del evento `kind 27235`, valor real de `u`), **sin firmar nada y sin crear una cuenta**. El resultado fija `SN_ORIGIN` y la política para la Compuerta C. No se supone que Stacker News envíe todos los parámetros esperados: el firmante describe lo que llegue, también lo anómalo o ausente.

## 2. Por qué el firmante no puede firmar en esta compuerta (verificado localmente, sin red)
1. `MODE=observe` es el **valor por defecto** (`Config.from_env` y `compose.real.yaml`).
2. `lab/real/compose.gate-b.yaml` lo **fija con valor literal** junto con aprobación por terminal, sin guion ni archivo de URI: ninguna variable olvidada en la sesión de PowerShell lo anula.
3. **Entorno hostil, comprobado dos veces:** `python -X utf8 lab/real/run_gate_a.py check-b --tls-groups X25519` (configuración final de compose con `MODE=sign`, `APPROVAL_MODE=scripted`, `APPROVAL_SCRIPT`, `URI_FILE` hostiles: efectivo `observe`/`tty`) y `preflight-b` (dentro del contenedor, con ese mismo entorno hostil y un aprobador que dice «sí» a todo: `connect` = `ack`, 3 `sign_event` válidos = `unauthorized`, **0 firmas**, 0 respuestas de aprobación de firma consumidas, todo lo publicado firmado solo con la clave de transporte, proxy 10/10 denegaciones, 0 residuos Docker). Resultado: PASS.
4. En `lab_real/signer.py` la **primera** instrucción de `on_sign` es la rama de observación; la clave de identidad se usa en una sola línea, posterior a esa rama (guardado por `tests/test_real_guards.py`).
5. En modo observación **no se muestra ninguna pregunta de firma**: no hay nada que el operador pueda aprobar por error. La única pregunta es la de `connect`.
6. Pruebas: `tests/test_real_signer.py` (30 aprobaciones «sí», 15 variantes y parámetros malformados: 0 firmas) y ensayo local **E11** con NDK 2.12.2 (11 solicitudes, incluida una válida): ninguna se firma. Ninguna es validación con Stacker News.

## 3. Verificado: la preparación local NO creó ninguna cuenta ni contactó a Stacker News
- La **única** forma conocida de crear una cuenta es firmar un `kind 27235` válido para `/signup` (en `master`, el servidor valida `id`, firma y `tags[0]` antes de crear el usuario; en producción no está verificado [I]). Con el origen real **nunca se ha firmado** ningún evento: las firmas de los ensayos usan `https://sn.lab.invalid`, y las sondas A no firman `27235`.
- Destinos externos contactados por el proxy en TODA la evidencia local: `relay.nsec.app:443` (Compuerta A de 17:00), `relay.primal.net:443` (A1) y un `connect_failed` a `relay.primal.io:443` (A2). **Ninguno a Stacker News.** `stacker.news` aparece en la evidencia solo como un `CONNECT` de prueba enviado al proxy local y **rechazado con 403 sin resolver ni conectar** (preflights).
- El código de `lab_real/` y `lab_common/` no importa clientes HTTP ni nombra `stacker.news` (guardas en `tests/test_real_guards.py`). El firmante solo puede alcanzar el proxy; el proxy, un único `host:puerto`.
- Nadie usó un navegador ni herramientas de red contra Stacker News en esta preparación.

## 4. Procedimiento (lo ejecuta el PROPIETARIO en su PowerShell, con el controlador `run_gate_b.py`; solo con autorización de B)
**Por qué el propietario y no el agente:** la URI `bunker://` debe verse solo en una terminal interactiva y la pregunta de `connect` exige teclado real. El controlador **rechaza** ejecutarse si stdin o stdout no son una terminal (comprobado: desde la herramienta del agente termina en NO-GO sin tocar Docker).

Requisitos previos (todos locales, sin red):
1. La **Compuerta A local interactiva** (apartado 7) dio GO en la terminal del propietario.
2. Autorización escrita de B con fecha y hora de Chile (apartado 6).

```powershell
cd <raiz del repositorio>
python -X utf8 lab/real/run_gate_b.py run --tls-groups X25519 --start 2026-MM-DDTHH:MM:00-03:00 --evidence-dir lab/results/gate-b-run
```
Qué hace el controlador, en este orden:
1. Rechaza empezar si no hay terminal real, si ya pasó el inicio +60 s, si la ventana venció, si `evidence.jsonl` ya existe en el directorio o si hay recursos Docker del proyecto.
2. Ejecuta `check-b` y `preflight-b` (entorno hostil, **sin tráfico externo**; pueden correr antes de la hora). Si fallan: NO-GO, nada se conecta.
3. Espera al inicio. A partir de ahí: proxy de `relay.primal.net:443` (único destino) y firmante (`MODE=observe`, `APPROVAL_MODE=tty`, un solo intento de conexión al relay, URI de un solo uso con vida 270 s).
4. Muestra la URI **solo en su terminal** (pasa por la memoria del controlador; no va a archivos, registros ni argumentos). Le reenvía sus respuestas (máx. 5 líneas cortas).
5. Vigila cada ~0,5 s: firma o aprobación de firma en la evidencia, modo distinto de `observe`, cualquier destino distinto del autorizado o un segundo intento de conexión en el proxy: ante cualquiera, parada inmediata y limpieza.
6. Termina por: `Ctrl+C` (parada manual), fin de la observación (**inicio + 260 s**; los últimos 40 s se reservan a detener y limpiar; ventana global 300 s), o terminación del firmante. Siempre ejecuta: matar procesos → guardar el registro del proxy (solo `host:puerto` y bytes) → `down -v --remove-orphans` del proyecto → limpieza forzada por etiqueta si quedaran recursos → escaneo de secretos → `run_meta_b.json`.

Interacción manual del propietario durante la observación:
1. Espere en la terminal «Observacion activa» y la línea `URI 1: bunker://…` (**no la copie a ningún archivo, chat ni captura**; cópiela directamente al navegador).
2. En una ventana **privada** del navegador (sin sesión de Stacker News) abra `https://stacker.news/signup`, elija el registro por Nostr y pegue la URI. **No pulse nada más** que lo estrictamente necesario para pegar/enviar la URI; ante cualquier botón de crear cuenta, continuar o confirmar: no pulsar y detener con `Ctrl+C`.
3. Si el firmante muestra «Activar esta conexion? [s/N]»: lea el cliente y responda `s` (esto solo activa la conexión, no crea cuenta). Cualquier otra respuesta la rechaza.
4. Stacker News enviará `get_public_key` y, esperablemente, `sign_event`: el firmante **imprime la estructura y la deniega solo**. No hay pregunta que responder. Anote lo que muestra el navegador (mensaje de error).
5. Termine con `Ctrl+C` cuando haya visto el resultado (o deje que el tiempo lo cierre). El controlador imprime un resumen sin la URI.
6. Evidencia: `lab/results/gate-b-run/` (`evidence.jsonl` con la estructura observada, `proxy.jsonl`, `run_meta_b.json`, `pre/`). Del `evidence.jsonl`: `observed_request` (métodos, nº y tipos de parámetros, permisos de `connect`), `observed_sign` (`kind`, etiquetas y longitudes, `u_seen`, `method_seen`, `content_seen`, forma del reto, antigüedad) y `decision` (todas `modo_observacion`). El reto nunca se registra en claro. No se guardan capturas.

## 5. Pasos que exigirán autorización expresa adicional durante la interacción con Stacker News
Cada uno queda **fuera** de una autorización genérica de «ejecutar la Compuerta B»; si el propietario no lo concede por escrito, no se hace:
1. **Acceso al servicio:** abrir `https://stacker.news/signup` en el navegador del operador (efecto externo: Stacker News ve IP y hora). Otras páginas (`/login`, `/settings`, API) quedan excluidas.
2. **Aprobar `connect`:** activar la conexión con Stacker News (entrega la clave pública desechable). Decisión del propietario, no del agente.
3. **Cualquier dato adicional** que pida Stacker News (correo, términos, pagos, captcha, cookies): detenerse y pedir autorización.
4. **Cualquier botón de «crear cuenta», «continuar» o «confirmar»** tras una denegación, o cualquier flujo que parezca crear un registro sin firma [H]: no pulsar; detener y consultar.
5. **Firmar** cualquier evento (Compuerta C, otra autorización): en B es imposible por diseño; si Stacker News no avanza sin firma, **ese es el hallazgo**.
6. **Reintentar** la sesión del firmante, repetir el flujo, cambiar de relay o de navegador/perfil.
7. **Conservar** capturas, vídeos o HAR de Stacker News (solo con la URI y los datos de sesión redactados) y **qué** parte de la evidencia pasa a la documentación.
8. **Ampliar** la duración (10 minutos), el número de URIs (1) o los permisos de `connect`.
9. **Responder a `AUTH`** del relay o cualquier otra interacción con el relay distinta de suscribirse y responder `connect`/`get_public_key`.

## 6. Datos que el propietario debe fijar en la autorización de B (AGENTS.md §11)
1. **Servicios:** `relay.primal.net:443` y Stacker News solo vía el navegador del operador, solo `/signup`.
2. **Identidad:** clave desechable en memoria del firmante; sin cuentas ni claves personales; navegador en ventana privada.
3. **Operaciones permitidas:** conexión `wss` al relay; aprobar `connect`; recibir `get_public_key` y `sign_event` (este último solo observado y denegado).
4. **Duración:** fecha y hora de inicio [______] America/Santiago, máximo 10 minutos; sin reintentos de la sesión del firmante.
5. **Restricciones:** no firmar, no crear cuenta, no completar datos adicionales, no otros relays, no otras páginas de Stacker News, no repetir sin nueva autorización.
Riesgos que acepta: el relay y Stacker News ven la IP pública y la hora; si Stacker News crease un registro previo sin firma [H, contrario a lo observado en `master`], quedaría huérfano.

## 7. Compuerta A local interactiva (prerrequisito; solo infraestructura local, sin red externa)
Ensaya el **mismo controlador** con un relay de laboratorio y el cliente NDK 2.12.2 local en lugar de Stacker News. **No la ejecuta el agente sin confirmación del propietario.** En su PowerShell:
```powershell
python -X utf8 lab/real/run_gate_b.py rehearsal --interactive --scenario full
```
1. El controlador hace los prechecks (≈ 25 s), espera ~30 s al inicio y muestra «FIRMANTE LISTO» y `URI 1: bunker://…` **en su terminal**.
2. Un cliente NDK local recibe la URI por su entrada estándar y se conecta: aparece «Activar esta conexion? [s/N]». **Escriba `s` y Enter** (aprobación manual de `connect`).
3. El cliente envía 11 `sign_event` (uno válido): el firmante imprime cada estructura y las deniega **sin preguntar**. No escriba nada más.
4. El controlador termina solo («cliente_termino»), limpia y pregunta «Viste la URI bunker:// en ESTA terminal? [s/N]»: responda `s` solo si la vio.
5. Imprime `GO` o `NO-GO` con los criterios. Pruebas de parada: repita con `--scenario manual-stop` (cuando aparezca «Observacion activa» pulse `Ctrl+C`; esperado: `interrupcion_manual`) y `--scenario timeout` (no toque nada; esperado: `tiempo` a los ~45 s con `--window-s 60`).
Criterios GO/NO-GO: ver `lab/experiments/definitions-real.md` (E12). Las variantes desatendidas (`--auto`) usan stdin simulado y **no sustituyen** esta comprobación.

**Autorizo la Compuerta B con el alcance indicado** (completar): propietario ______  fecha y hora de inicio (Chile) ______
