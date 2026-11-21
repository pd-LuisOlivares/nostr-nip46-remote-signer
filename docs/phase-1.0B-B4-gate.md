# Bloque B4 — Demostración real de autenticación con Stacker News: compuerta operativa única

**Estado (2026-11-21): EJECUTADA. Resultado: PASS con observaciones** (ver `docs/decisions.md`, «B4: ejecución real y resultado»). Autorización expresa del propietario; ventana real de T0 00:01:05 a 00:03:10 (Santiago), 1 firma, firmante detenido con `session_end`. La observación de la sesión en Stacker News es del propietario. **Esta compuerta queda cerrada**: repetir la demostración (p. ej. la validación real de B6) requiere una nueva autorización.

> Una prueba automatizada, un E2E local o una firma válida **no demuestran** la autenticación en Stacker News (AGENTS.md §3, §10.6). B4 solo es PASS si Stacker News confirma una sesión autenticada.

## 1. Decisiones registradas del propietario (D-5 y destino)

| # | Decisión | Estado |
|---|---|---|
| D-5 | Identidad Nostr **nueva, dedicada y reutilizable** para la prueba, generada por el propietario y conservada **solo por él**, fuera del repositorio. | **Aprobada** |
| Destino | `https://stacker.news/signup`, flujo **«Continue with Nostr»** mediante `bunker://`. | **Aprobado** |
| Cuenta real | El propietario **acepta** que la demostración pueda **crear una cuenta real de prueba** en Stacker News. | **Aceptado** |
| Ejecución | Esta instrucción **no autoriza** la demostración real. | **Pendiente de autorización y de confirmación de inicio** |

## 2. Alcance técnico fijado (no ampliable)

| Elemento | Valor |
|---|---|
| Relay | `wss://relay.primal.net` (puerto 443), TLS verificado, `RELAY_TLS_GROUPS=X25519`; una sola conexión, **sin reconexión automática**; si el relay pide `AUTH` o falla el TLS, la sesión termina |
| Servicio | `https://stacker.news/signup` en una **ventana privada** del navegador del propietario; ninguna otra página ni API de Stacker News |
| Política | `kind 27235` únicamente, origen `u` = `https://stacker.news`, contenido «Stacker News Authentication», las 11 comprobaciones; **sin ampliar la política** |
| Firmas | **Máximo 1** firma real (`MAX_SIGNATURES=1`); un reto = una firma; sin reintentos automáticos de autenticación |
| Aprobación | **Humana y obligatoria** de `connect` y de `sign_event` desde la interfaz; ningún guion |
| Ventana | **15 minutos máximo** desde el arranque del producto (T0); sesión del firmante 12 minutos (§5) |
| URI | **Una** URI `bunker://` de un solo uso |

## 3. Identidad de prueba: generación y custodia privadas

La clave **no** se genera dentro del producto (D-3: sin persistencia) ni se escribe en el repositorio. La herramienta `lab/tools/b4_identity.py` la crea **fuera del repositorio**, con permisos restringidos, y **nunca la imprime** (solo muestra la clave pública, que no es secreta). Se niega a escribir dentro del repositorio y a sobrescribir una identidad existente.

```powershell
# PowerShell 7, desde la raíz del repositorio, con el entorno virtual activo. SIN red.
python lab/tools/b4_identity.py generate        # crea %USERPROFILE%\.nip46-b4\identity.key (o use --out <ruta fuera del repositorio>)
python lab/tools/b4_identity.py pubkey          # muestra SOLO la clave pública (anótela truncada: 8 primeros caracteres)
```
1. **Respalde** el archivo de forma privada (gestor de contraseñas o medio cifrado propio). Si lo pierde, pierde la cuenta de prueba; el proyecto no puede recuperarla.
2. **No** lo copie al repositorio, a chats, a capturas ni a tickets. El agente nunca lo ve.
3. Para usarla: `python lab/tools/b4_identity.py copy` la pone en el portapapeles **sin mostrarla**; péguela en «Importar una clave propia» de la interfaz y ejecute enseguida `python lab/tools/b4_identity.py clear-clipboard`.
4. La clave vive en memoria del firmante solo mientras corre; al detener el proceso desaparece de la aplicación. Para reutilizarla en otra sesión (p. ej. la repetición de B6) se importa de nuevo desde su archivo, **con nueva autorización**.

## 4. Autorización operativa (completar para habilitar la ejecución)

1. **Servicios:** relay `wss://relay.primal.net:443` y `https://stacker.news/signup` (solo vía el navegador del propietario). ✔ registrados en §1–§2.
2. **Identidad y cuenta real:** identidad dedicada de §3; creación de una cuenta real de prueba aceptada. ✔ registrados en §1.
3. **Confirmación de inicio (obligatoria):** la ventana empieza **solo** cuando el propietario lo confirme por escrito en la conversación y arranque el producto (T0). Fecha y hora de inicio (America/Santiago): [______]
4. **Operaciones permitidas:** arrancar el producto con el relay real; importar la clave; iniciar el firmante; emitir **una** URI; aprobar **un** `connect` revisado; aprobar **una** `sign_event` con las 11 comprobaciones en verde; observar el resultado en Stacker News; cerrar sesión en Stacker News; detener el firmante.
5. **Restricciones:** no pagos, no publicar, no editar perfil, no correo ni datos adicionales, no captcha o verificaciones externas, no otras páginas, no otros relays, no reintentos ni repetición sin nueva autorización, no capturas ni HAR con la URI, el código de acceso, la clave, el JWT o cookies.
6. **Operador de la sesión:** el propietario. El agente no ejecuta ninguna acción externa y no aprueba solicitudes.

**Autorizo ejecutar la Compuerta B4 con este alcance:** propietario ______  firma/confirmación ______  inicio (Chile) ______

## 5. Procedimiento exacto (lo ejecuta el propietario)

### A. Preparación (antes de T0; sin red externa)
```powershell
cd <raíz del repositorio>; .\.venv\Scripts\Activate.ps1
python -m pytest -q -m "not e2e"                 # opcional: sanidad local, todo en 127.0.0.1
New-Item -ItemType Directory -Force lab/results/b4-<fecha> | Out-Null   # carpeta de evidencias (excluida de Git)
```
Tenga a mano: una **ventana privada** del navegador sin sesión de Stacker News, y su identidad de §3.

### B. Arranque (T0 = momento en que usted lo confirma y ejecuta esto)
```powershell
$env:RELAY_URL = "wss://relay.primal.net"; $env:RELAY_TLS_GROUPS = "X25519"; $env:SERVICE_ORIGIN = "https://stacker.news"
$env:SESSION_TTL_S = "720"; $env:CONNECTION_TTL_S = "720"; $env:APPROVAL_TTL_S = "120"; $env:MAX_SIGNATURES = "1"; $env:MAX_REQUESTS = "30"; $env:JWT_TTL_S = "900"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
La terminal muestra **una sola vez** el código de acceso. Anote la hora de T0. **Fin duro: T0 + 15 min** (detenga todo si llega).

### C. Interfaz (<http://127.0.0.1:8000>)
1. Inicie sesión con el código de acceso.
2. `python lab/tools/b4_identity.py copy` → pegue en «Importar una clave propia» → **Importar** → `python lab/tools/b4_identity.py clear-clipboard`. Verifique que la clave pública mostrada coincide con la de `pubkey` (primeros 8 caracteres).
3. **Iniciar firmante**: debe pasar a **Listo** en pocos segundos (primera conexión real a `relay.primal.net`). Si queda **Fallido** (p. ej. TLS) → §6, **no reintente**.
4. **Emitir URI de un solo uso**; cópiela (no se vuelve a mostrar).

### D. Stacker News (ventana privada)
1. Abra `https://stacker.news/signup`, pulse **Continue with Nostr**, elija el inicio con firmante remoto (*bunker*) y pegue la URI. **No pulse nada más que lo necesario.** Ante cualquier petición de datos, pago, correo, captcha o términos adicionales → §6.
2. En la interfaz aparece **Conexión de un cliente**: confirme que es el cliente esperado y **Aprobar** (dentro de 120 s).
3. Stacker News pedirá la clave pública (automático) y luego la **firma**: aparece **Firma del evento de inicio de sesión**. Revise: **11 comprobaciones en verde**, `u` = `https://stacker.news`, contenido «Stacker News Authentication», antigüedad de pocos segundos → **Aprobar**. Si algo no coincide: **Rechazar** y §6.
4. Observe el resultado en Stacker News (sin pulsar nada adicional). Anote lo que ve: usuario autenticado/menú de usuario, nombre mostrado, mensajes de error. Recargue **una** vez la misma página para comprobar si la sesión persiste.

### E. Cierre y evidencias (inmediatamente después)
1. En la interfaz: **Detener** (queda `session_end`). Copie la tabla de **Auditoría** a `lab/results/b4-<fecha>/audit.txt`, **o** expórtela por la API (el firmante detenido no impide consultar):
   ```powershell
   $B = "http://127.0.0.1:8000"; $code = Read-Host "Codigo de acceso" -MaskInput
   $H = @{ Authorization = "Bearer " + (Invoke-RestMethod -Method Post -Uri "$B/api/auth/login" -ContentType application/json -Body (@{code=$code} | ConvertTo-Json)).token }
   Invoke-RestMethod -Uri "$B/api/audit?limit=500" -Headers $H | ConvertTo-Json -Depth 6 | Set-Content lab/results/b4-<fecha>/audit.json
   ```
2. **Verifique que la evidencia está sanitizada** y resuma la parte técnica:
   ```powershell
   python lab/tools/b4_check_evidence.py lab/results/b4-<fecha>/audit.json   # o audit.txt
   ```
   Debe decir «Sin fugas» y «COHERENTE» (una `sign_ok` y un `session_end`). Si detecta fugas, **no comparta el archivo**.
3. Cierre la sesión de Stacker News y la ventana privada; **Cerrar sesión** en el panel; `Ctrl+C` en la terminal del producto; `python lab/tools/b4_identity.py clear-clipboard`.
4. Escriba `lab/results/b4-<fecha>/notas.txt` con: hora de T0 y de fin, **clave pública truncada (8 caracteres)**, qué mostró Stacker News y si la sesión persistió al recargar. **No** incluya URI, código, clave, JWT, cookies ni retos. Capturas de pantalla solo si usted las autoriza y **sin** esos datos.
5. Comparta con el agente **solo** `audit.*`, la salida del verificador y `notas.txt`.

## 6. Condiciones de parada (pulse **Detener** y `Ctrl+C`; no reintente)

1. **Evento inválido** o `sign_event` con alguna comprobación en rojo (el producto ya lo deniega solo), o cualquier solicitud rechazada por la política.
2. **Origen inesperado**: `u` distinto de `https://stacker.news`, contenido distinto, o cualquier página/dominio distintos de `stacker.news/signup`.
3. **Solicitud adicional de firma** (una segunda `sign_event`, otro `kind`, otro método como cifrado delegado) o un segundo `connect` de otro cliente.
4. **Error TLS o de relay**: el firmante pasa a **Fallido**, el relay pide `AUTH`, cierra la suscripción o no hay respuesta.
5. **Fallo de política** (cualquier `policy ok=false` en la auditoría durante la sesión real).
6. **Tiempo agotado**: pasan 15 minutos desde T0, caduca el reto o la solicitud, o habría que emitir una segunda URI.
7. **Comportamiento no previsto**: Stacker News pide datos, correo, pagos, captcha o términos; aparece una URI, código o clave donde no debe; el navegador o el panel muestran errores inexplicados.

Tras parar: exporte la evidencia (§5.E) y avise al agente. Una segunda tentativa requiere **nueva autorización**.

## 7. Criterios PASS, FAIL y BLOCKED

| Veredicto | Condición (todas) |
|---|---|
| **PASS (B4 completado)** | (a) La auditoría tiene **exactamente una** `sign_ok` y un `session_end`, sin fallos de política ni errores de relay; (b) **Stacker News muestra una sesión autenticada** tras completar el flujo, sin que se hayan proporcionado datos adicionales; (c) el verificador de evidencias da «Sin fugas»; (d) el propietario describe lo observado. Si Stacker News muestra la identidad (o su clave pública), debe corresponder a la usada; si no la muestra, se anota como **no verificable** y no se declara coincidencia. |
| **FAIL** | La firma se emitió y se autoverificó (`sign_ok` = 1) pero Stacker News **no** abre sesión, muestra un error o exige datos adicionales para continuar. Se documenta como hallazgo (hipótesis Y-8), **sin reintentos**. |
| **BLOCKED** | No hubo firma (`sign_ok` = 0): se activó una condición de §6 antes de firmar, falló el relay o el TLS, o se agotó el tiempo. Sin firma no hay efecto en Stacker News. |

Un PASS solo cubre B4. La validación real de B6 (repetir el inicio de sesión desde la interfaz) requiere su propia autorización. Los resultados locales y los reales se documentan **por separado** en `docs/ai-log.md`.

## 8. Evidencia sanitizada (qué se conserva y qué nunca)

| Se conserva (en `lab/results/b4-<fecha>/`, excluida de Git) | Nunca |
|---|---|
| Auditoría (`audit.json`/`audit.txt`: eventos, métodos, resultado de la política, `sign_ok`, `session_end`), salida del verificador, `notas.txt` (horas, clave pública truncada, observación de Stacker News) | Clave privada o `nsec`; URI `bunker://` o su secreto; código de acceso; JWT; cookies o cabeceras `Authorization`; reto completo; texto descifrado; archivos HAR |

El verificador (`lab/tools/b4_check_evidence.py`) detecta esos patrones y el recuento coherente. Al documentar en el repositorio solo se resumirá y se redactará lo estrictamente necesario.

## 9. Riesgos que el propietario acepta

- El relay y Stacker News ven la IP pública y la hora; se crea (o usa) una cuenta **real** de Stacker News ligada a la clave de prueba, probablemente **sin posibilidad de borrarla** [no verificado].
- La respuesta de Stacker News a una firma válida es **no observada**: puede rechazar el inicio de sesión sin que sea un defecto del firmante.
- Una firma emitida no se puede revocar; por eso solo se firma un reto, tras revisión humana, con tope 1.
- El código de acceso queda visible en la terminal durante la sesión; la clave pasa por el portapapeles al importarla (se vacía después).
- Si pierde el archivo de la identidad, la cuenta de prueba queda inaccesible.

## 10. Verificaciones locales previas (sin conexiones externas)

Realizadas el 2026-11-21 sin iniciar el firmante contra ningún relay real: batería de pruebas completa en local (todo en `127.0.0.1`), E2E de navegador con relay local, E2E de Docker con NDK real en red propia, arranque de la aplicación por Docker Compose y herramientas de §3 y §5.E probadas con datos ficticios. Detalle en `docs/decisions.md` («Cierre de la compuerta de B4») y el informe de la sesión.

## 11. Qué NO hace el agente

No conecta a `relay.primal.net`, no abre ni consulta Stacker News, no crea la cuenta, no firma eventos externos, no hace commit ni push, no modifica `AGENTS.md` ni `CLAUDE.md`, no inicia funcionalidades nuevas y **no declara B4 completado**. Espera la autorización expresa y la confirmación de inicio.
