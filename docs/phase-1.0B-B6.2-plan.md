# Fase 1.0B, B6.2 — plan operativo de la validación real con Stacker News

> **Estado vigente (2026-11-22, actualizado): ver §17 y §17.6.** La validación real **no se hizo con la imagen `manual-b61d`** ni con el plan supervisado de este documento (una firma, ventana de 15 minutos): se ejecutó con la **versión final en modo continuo** (imagen `d17-continuous`, perfil `deploy/continuous.env`, `http://127.0.0.1:8001`) y el propietario **confirmó personalmente el PASS**. **No hay evidencia técnica capturada** de esa ejecución (ver §17.6); este documento conserva el plan original como referencia. La primera ventana (T0 20:03) se suspendió sin ejecutar nada.

**Estado de la preparación original: PREPARADO, PRECONDICIONES VERIFICADAS (§14). NO AUTORIZADO TODAVÍA.** Este documento prepara y documenta B6.2. No se ha realizado ninguna conexión externa, no se ha usado la identidad privada de B4, no hay firmas reales y no hay commit ni push. La ejecución requiere la **autorización expresa del propietario** con el alcance de §2 y §13 (`AGENTS.md` §11).

Relación con otras validaciones: la validación **local** B6.1D (PASS, cerrada en [`phase-1.0B-B6.1D-closure.md`](phase-1.0B-B6.1D-closure.md)) se conserva y es **independiente** de esta. B4 (2026-11-21, [`phase-1.0B-B4-gate.md`](phase-1.0B-B4-gate.md)) fue el primer inicio de sesión real y ya asoció una cuenta de Stacker News a la identidad de prueba; B6.2 repite la interoperabilidad **con el producto actual** (ingreso con usuario y contraseña, SQLite, revalidación P-38, resultado real P-42, interfaz B6) y añade lo que B4 no observó: **persistencia de la sesión al recargar**.

Regla de veredicto: **B6.2 no se declara PASS porque el firmante haya generado una firma.** Hace falta además que Stacker News acepte la autenticación (observación del propietario) y que se cumpla cada fila de la matriz B (§9).

## 1. Qué cambia respecto de B4 y qué no

| Aspecto | B4 | B6.2 |
|---|---|---|
| Ingreso al panel | Código de acceso de un solo uso en la terminal | **Usuario y contraseña** (Argon2id, SQLite, JWT en cookie `HttpOnly`) |
| Ejecución | `python -m uvicorn` en el host | Igual (se conservan límites exactos, ver §4) |
| Revalidación antes de firmar | No existía | **P-38**: se revalida política y aprobación justo antes de firmar |
| Resultado de la firma en la interfaz | No | **P-42**: «Firmada» / «Rechazada al firmar» / «Falló» |
| Persistencia de sesión al recargar | **No reportada** | **Se verifica** (paso 11) |
| Destino | `https://stacker.news/signup` | `https://stacker.news/login` (**supuesto no verificado**: lo confirma el propietario al abrirla; si no existiera, se detiene la prueba y se pide autorización para otro destino) |
| Código, protocolo, política | — | **Sin cambios.** No se adapta el firmante a Stacker News |

## 2. Presentación previa a la autorización (lo que se pide aprobar)

1. **Servicios externos:** (a) el relay público indicado en el punto 2; (b) `https://stacker.news` **solo desde una ventana privada del navegador del propietario**. El agente no abre Stacker News ni usa herramientas de navegador o red sobre él. Nada más.
2. **Relay público exacto:** `wss://relay.primal.net` (puerto 443; `RELAY_TLS_GROUPS=X25519`; sin reconexión automática; un `AUTH` NIP-42 termina la sesión). Ningún otro relay.
3. **Identidad (solo clave pública):** `c5a035bf14ae9793f27e2a6707c2975fc58b8ba341b511efa3b82954aded1a3f` — la identidad dedicada de pruebas de B4. Su clave privada vive solo en `%USERPROFILE%\.nip46-b4\identity.key`, fuera del repositorio; el agente **no la lee, no la muestra, no la registra ni la copia** a informes. La importa el propietario desde la interfaz.
4. **Operaciones NIP-46 previstas:** `connect` (aprobación humana), `get_public_key` (automática, solo lectura de la clave pública) y **una** `sign_event` de `kind` 27235 (aprobación humana, 11 comprobaciones en verde). `ping` solo si el cliente lo envía (sin efecto). Cualquier otro método o `kind` se rechaza por política y es **condición de parada**.
5. **Riesgos y medidas:** §11.
6. **Pasos del propietario desde el navegador:** §6 (pasos 4 a 11, lo que ocurre en Stacker News y en el panel).
7. **Decisiones del propietario (2026-11-21):** ejecutar en `localhost:8001` con Uvicorn; consultas de **solo lectura** del agente para diagnosticar (sin aprobar, firmar ni manipular credenciales); **sí** a preparar una captura redactada del resultado en Stacker News; la validación local B6.1D se conserva íntegra; la validación en Ubuntu queda para el final (§16). **Pendiente de su respuesta:** fecha y hora de inicio, destino y confirmación expresa de §13.

## 3. Prohibiciones (siguen vigentes durante toda la prueba)

Sin billeteras ni pagos; sin publicar contenido ni editar el perfil; sin correo ni datos adicionales; sin captcha o verificaciones externas; sin otras páginas ni otros relays; sin aprobaciones automáticas (cada `connect` y cada firma las aprueba una persona en el panel); sin ampliar políticas, ventanas ni límites; sin claves ajenas al proyecto; sin cambios en el comportamiento del firmante. Sin reintentos ni segunda URI: una segunda tentativa requiere **nueva autorización**. Sin capturas ni exportaciones que contengan la URI, la contraseña, la clave, el JWT, las cookies o el reto completo.

## 4. Configuración propuesta (valores de B4, límites exactos)

> **Actualización (D-16, 2026-11-21):** la ejecución de B6.2 pasa a **Docker Compose** con el perfil `deploy/b62.env` (§17). Los **valores** de esta tabla se conservan; lo que cambia es el mecanismo (el «por qué no Docker» de abajo queda superado: `compose.yaml` ya reenvía `CONNECTION_TTL_S`, `MAX_REQUESTS` y `SIGNER_WINDOW_S`). La ejecución con Uvicorn y `data/b62.db` en el host se conserva solo como historia de la primera ventana, que se suspendió sin ejecutar nada.

| Variable | Valor | Motivo |
|---|---|---|
| `RELAY_URL` | `wss://relay.primal.net` | Relay de B4 (conectividad verificada) |
| `RELAY_TLS_GROUPS` | `X25519` | Requerido por este relay en este entorno (hallazgo de B3/B4) |
| `SERVICE_ORIGIN` | `https://stacker.news` | Origen exacto esperado en la etiqueta `u` |
| `APPROVAL_TTL_S` | `120` | Igual que B4; no mayor que la ventana de firma (`SIGNER_WINDOW_S`, por defecto 120) |
| `MAX_SIGNATURES` | `1` | Una sola firma real |
| `SESSION_TTL_S` / `CONNECTION_TTL_S` | `720` / `720` | La sesión y la conexión caducan antes del límite duro |
| `MAX_REQUESTS` | `30` | Tope de solicitudes de la sesión |
| `JWT_TTL_S` | `900` | Sesión del panel de 15 min |
| `DATABASE_PATH` | `data/b62.db` | Base **propia** de B6.2 (`/data/` y `*.db` están ignorados por Git); no toca la base de la demostración |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD_FILE` | usuario de prueba / archivo **fuera del repositorio** | Cuenta nueva, solo para B6.2 |
| Puerto y host | `127.0.0.1:8001`, abierto como `http://localhost:8001` | La cookie de sesión es por **nombre de host** (no por puerto): usar `localhost` evita pisar la sesión de la demostración local (`127.0.0.1:8000`) si sigue levantada |

Por qué no Docker Compose en esta prueba: el `compose.yaml` del producto **no** reenvía `CONNECTION_TTL_S`, `MAX_REQUESTS` ni `SIGNER_WINDOW_S` (quedarían en 1800, 60 y 120 por defecto). Con `python -m uvicorn` se replican los límites de B4 sin tocar código. Si el propietario prefiere Docker, la sesión (`SESSION_TTL_S=720`) sigue acotando la prueba, pero `CONNECTION_TTL_S` y `MAX_REQUESTS` serían los valores por defecto; debe decidirlo expresamente.

## 5. Verificaciones previas (sin red externa; las puede hacer el agente tras la autorización de preparación)

1. `git status` y `git diff --check` limpios para los archivos de documentación; la suite relevante (`python -m pytest -q -m "not e2e"`) en verde; `mypy --strict app` limpio.
2. Existencia (**solo nombre**, sin leer) de `%USERPROFILE%\.nip46-b4\identity.key`.
3. Creación de la contraseña del administrador de B6.2 **por el propietario** (el agente no la lee):
   ```powershell
   $d = Join-Path $env:USERPROFILE ".nip46-b62"; New-Item -ItemType Directory -Force $d | Out-Null
   $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Fill($b)
   [Convert]::ToBase64String($b) | Set-Content -NoNewline (Join-Path $d "admin_password.txt")   # no se imprime; ábralo usted para iniciar sesión
   ```
4. Comprobación de que `localhost` está en `ALLOWED_HOSTS` (por defecto sí) y de que el puerto 8001 está libre.
5. Primer arranque **solo local** (sin iniciar el firmante, sin conexión externa) para comprobar que el panel responde en `http://localhost:8001` y que el ingreso funciona. Esto **no** cuenta como parte de la ventana de 15 minutos y no abre ningún socket externo (el relay solo se contacta al pulsar «Iniciar firmante»).

## 6. Procedimiento operativo (11 pasos; ventana máxima de 15 minutos desde T0)

T0 = el propietario confirma por escrito el inicio y ejecuta el arranque. **Fin duro: T0 + 15 min.** Terminal de PowerShell en la raíz del repositorio, con el entorno virtual activado.

| # | Paso | Quién | Dónde | Verificación |
|---|---|---|---|---|
| 1 | **Ingreso al panel local con usuario y contraseña** | Propietario | `http://localhost:8001` | Panel visible; cookie `HttpOnly`; sin JWT en pantalla |
| 2 | **Importar la identidad de B4** (`python lab/tools/b4_identity.py copy` → pegar en «Importar una clave propia» → `python lab/tools/b4_identity.py clear-clipboard`) | Propietario | Panel | La clave pública mostrada coincide con la de §2 (primeros 8 caracteres) |
| 3 | **Iniciar el firmante con el relay público** | Propietario | Panel | Estado «Listo» en pocos segundos; si «Fallido» → §8, sin reintentar |
| 4 | **Generar la URI bunker de un solo uso** | Propietario | Panel | La URI se muestra una vez; **solo el propietario** la ve y la copia |
| 5 | **Conectar desde Stacker News**: ventana privada → `https://stacker.news/login` → «Continue with Nostr» → bunker → pegar la URI | Propietario | Navegador | Aparece «Conexión de un cliente» en el panel |
| 6 | **Aprobar `connect`** tras revisar el cliente (dentro de 120 s) | Propietario | Panel | Auditoría: `decision approved=true reason=humano`; `get_public_key` respondido |
| 7 | **Solicitud y aprobación de `sign_event`**: aparece «Firma del evento de inicio de sesión»; revisar las **11 comprobaciones en verde**, `u` = `https://stacker.news`, contenido «Stacker News Authentication», antigüedad de pocos segundos → **Aprobar** | Propietario | Panel | Auditoría: `policy ok=true`, `decision approved=true`, `revalidation ok` |
| 8 | **Verificar la firma producida** | Propietario (panel) + agente (auditoría exportada) | Panel / API | Resultado «Firmada» (P-42) y `sign_ok` con `self_verify=true`; exactamente **1** `sign_ok` |
| 9 | **Verificar la entrega de la respuesta al relay** | Agente (auditoría exportada) | Auditoría | `response_published method=sign_event relay_ok=true` |
| 10 | **Confirmar el inicio de sesión en Stacker News** (sin pulsar nada más) | Propietario | Navegador | Usuario autenticado / menú de usuario; anotar mensajes de error |
| 11 | **Recargar la página una vez** para comprobar la persistencia de la sesión | Propietario | Navegador | Sigue autenticado, o se anota que no |

Cierre inmediato (**E**): en el panel **Detener** (queda `session_end`) → exportar la auditoría (`GET /api/audit?limit=500` con la sesión del panel, o copiar la tabla) → `python lab/tools/b4_check_evidence.py <archivo>` («Sin fugas» y resumen coherente) → cerrar sesión en Stacker News y la ventana privada → **Cerrar sesión** en el panel → `Ctrl+C` en la terminal → `python lab/tools/b4_identity.py clear-clipboard`. Notas del propietario sin URI, contraseña, clave, JWT, cookies ni retos (hora de T0 y fin, clave pública truncada, qué mostró Stacker News y si persistió). Se comparte con el agente **solo** la auditoría exportada, la salida del verificador y las notas.

Arranque (T0), ejecutado por el propietario (la contraseña inicial se lee del archivo; no se imprime):
```powershell
$env:RELAY_URL = "wss://relay.primal.net"; $env:RELAY_TLS_GROUPS = "X25519"; $env:SERVICE_ORIGIN = "https://stacker.news"
$env:SESSION_TTL_S = "720"; $env:CONNECTION_TTL_S = "720"; $env:APPROVAL_TTL_S = "120"; $env:MAX_SIGNATURES = "1"; $env:MAX_REQUESTS = "30"; $env:JWT_TTL_S = "900"
$env:DATABASE_PATH = "data/b62.db"; $env:ADMIN_USERNAME = "b62-admin"; $env:ADMIN_PASSWORD_FILE = (Join-Path $env:USERPROFILE ".nip46-b62\admin_password.txt")
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```
Una sola instancia, sin `--workers` (la compuerta Argon2id es por proceso).

## 7. Qué hace y qué no hace el agente

- **Puede** (solo si el propietario lo autoriza en §13): preparar la documentación, ejecutar las verificaciones locales de §5, procesar la auditoría exportada, ejecutar `b4_check_evidence.py` y redactar el informe.
- **Diagnóstico de solo lectura durante la ventana (autorizado el 2026-11-21):** `GET /health` (sin sesión), lectura de `server.log` y de los archivos de `lab/results/b62-<fecha>/`, y estado de procesos y puertos. **Consultar `/api/audit`, `/api/status` o `/api/requests` exige una sesión del panel, es decir, la contraseña de B6.2: el agente NO la lee ni la usa** (se considera manipular credenciales). La auditoría la exporta el propietario (§15) y la pega o guarda para el agente. Si prefiere que el agente la consulte, debe autorizar aparte la lectura de ese archivo de contraseña.
- **No puede, en ningún caso:** aprobar o denegar solicitudes, iniciar el firmante, importar claves, emitir o ver la URI, abrir Stacker News ni leer la contraseña, la clave o las cookies. Al vencer la ventana o al cumplirse una condición de parada, el propietario detiene el firmante (el agente solo avisa).

## 8. Condiciones de parada (**Detener** + `Ctrl+C`; sin reintento)

1. `sign_event` con alguna comprobación en rojo, o cualquier solicitud rechazada por la política.
2. `u` distinto de `https://stacker.news`, contenido distinto, o cualquier página/dominio distinto del destino autorizado.
3. Segunda `sign_event`, otro `kind`, otro método o un segundo `connect` de otro cliente.
4. Error TLS o de relay: «Fallido», `AUTH` NIP-42, cierre de la suscripción o ausencia de respuesta.
5. Cualquier `policy ok=false` en la auditoría durante la sesión real.
6. Pasan 15 minutos desde T0, caduca el reto o la solicitud, o habría que emitir una segunda URI.
7. Stacker News pide datos, correo, pagos, billetera, captcha o términos adicionales; aparece una URI, contraseña o clave donde no debe; errores inexplicados.
8. Fuga de un secreto: detenerlo todo y avisar; no copiar el secreto en ningún informe.

## 9. Matriz B — validación externa B6.2 (independiente de la matriz A)

Estado actual: **todo NO PROBADO (pendiente)**. Leyenda: **PASS automatizado**, **PASS manual** (confirmado por el propietario), **FAIL**, **NO PROBADO**. Nada de esta matriz se rellena con pruebas automatizadas locales: las pruebas con relay de laboratorio pertenecen a la matriz A.

| # | Resultado a distinguir | Evidencia que lo prueba | Estado |
|---|---|---|---|
| B0 | Ingreso al panel con usuario/contraseña; clave importada con la pública esperada; firmante «Listo» con el relay público; URI emitida (pasos 1–4) | Auditoría: `session_start`, `relay_ready`, `bunker_issued`; observación del propietario | NO PROBADO |
| B1 | **Conexión establecida** (Stacker News contactó al firmante a través del relay) | Auditoría: `request method=connect` desde un `client8` | NO PROBADO |
| B2 | **Solicitud recibida** (`get_public_key` y `sign_event` de `kind` 27235 con las 11 comprobaciones en verde) | Auditoría: `request`, `policy ok=true`, `pending_created` | NO PROBADO |
| B3 | **Aprobación humana** de `connect` y de `sign_event` | Auditoría: `decision approved=true reason=humano` (×2) | NO PROBADO |
| B4 | **Firma producida y verificada** (exactamente una) | Auditoría: `revalidation ok`, `sign_ok self_verify=true` (×1); interfaz «Firmada» | NO PROBADO |
| B5 | **Respuesta publicada en el relay** | Auditoría: `response_published relay_ok=true` para `connect` y `sign_event` | NO PROBADO |
| B6 | **Autenticación aceptada por Stacker News** (sesión abierta, sin datos adicionales) | **Solo** observación del propietario (notas); captura redactada solo si la autoriza | NO PROBADO |
| B7 | **Persistencia de la sesión al recargar** | Observación del propietario (paso 11) | NO PROBADO |
| B8 | **Evidencia sanitizada** (sin fugas; auditoría coherente: 1 `sign_ok`, 1 `session_end`, 0 errores, 0 fallos de política) | `b4_check_evidence.py`: «Sin fugas» y «COHERENTE» | NO PROBADO |

Que `relay_ok=true` (B5) significa solo que el relay aceptó el evento: **no** demuestra que Stacker News lo recibió ni que aceptó el inicio de sesión. Eso solo lo muestra B6.

## 10. Criterios de veredicto

| Veredicto | Condición |
|---|---|
| **PASS (B6.2)** | B0 a B8 en PASS: auditoría coherente **y** Stacker News muestra una sesión autenticada (B6) **y** la sesión persiste al recargar (B7), sin datos adicionales y sin violar ninguna restricción |
| **PASS parcial** | B0 a B6 en PASS y B7 en FAIL o NO PROBADO: se documenta exactamente qué se observó |
| **FAIL** | Hay firma verificada y entregada (B4 y B5 en PASS) pero Stacker News no abre sesión, muestra un error o exige datos adicionales (B6 en FAIL). Hallazgo documentado, **sin reintentos** |
| **BLOCKED** | No hubo firma (B4 en NO PROBADO): se activó una condición de §8, falló el relay/TLS o se agotó el tiempo |

Los resultados locales y los reales se documentan **por separado** en `docs/ai-log.md` y `docs/decisions.md`.

## 11. Riesgos y medidas

| # | Riesgo | Medida |
|---|---|---|
| R1 | Exposición de la clave privada de B4 al importarla (portapapeles, historial, captura) | Importación solo por el propietario, desde el archivo fuera del repositorio, con `copy`/`clear-clipboard`; el agente no la lee ni la registra; sin capturas del panel durante la importación |
| R2 | Fuga de la URI bunker (contiene el secreto de conexión de un solo uso) | La ve solo el propietario; caduca en 10 min y se consume al primer `connect`; prohibido en capturas, notas, informes o chats; el verificador busca `bunker://` y `secret=` |
| R3 | Cuenta real de Stacker News (efecto no reversible) | Cuenta ya asociada a la identidad de prueba (B4); solo inicio de sesión; sin billetera, pagos, contenido ni perfil |
| R4 | Metadatos en un relay público (clave pública del firmante, momento y tamaño de los mensajes; el contenido va cifrado NIP-44/NIP-04) | Un solo relay, ventana ≤ 15 min, identidad dedicada de pruebas; se acepta que la clave pública es pública |
| R5 | Fallos del relay: `AUTH` NIP-42, TLS, límites de tasa o cierre de la suscripción | Sin reconexión automática; parada sin reintento (§8) |
| R6 | Deriva de reloj frente a la ventana de firma de 120 s (rechazo por antigüedad) | Reloj sincronizado antes de T0; el panel muestra el plazo efectivo; ante rechazo, parada sin reintento |
| R7 | Stacker News cambia el flujo (otra URL, métodos, cifrado) | No se asume: se observa y se documenta; no se modifica el firmante para adaptarlo |
| R8 | Mezcla de sesiones con la demostración local (cookie compartida entre puertos de un mismo host) | `localhost:8001` frente a `127.0.0.1:8000`; base y contraseña propias de B6.2 |
| R9 | Fuerza bruta contra el panel local | Solo loopback; limitadores de ingreso, compuerta Argon2id y comprobaciones de Host/Origin ya existentes y probadas |
| R10 | Capturas, HAR o registros con secretos | Prohibidos con URI, contraseña, clave, JWT, cookies y reto completo; registros sin datos sensibles; `server.log` con la salida de uvicorn no se comparte sin revisión |
| R11 | Aprobación por reflejo (el propietario aprueba sin revisar) | Las 11 comprobaciones y `u`/contenido/antigüedad se revisan antes de pulsar «Aprobar»; no hay aprobación automática |
| R12 | Una prueba que «pasa» localmente se presente como validación real | Dos matrices separadas; B6 y B7 solo por observación del propietario |

## 12. Evidencias y registro

Carpeta de evidencias: `lab/results/b62-<fecha>/` (excluida de Git; ver `.gitignore`). Contenido permitido: auditoría exportada, salida de `b4_check_evidence.py` y `notas.txt` (sin secretos). Tras la ejecución, el agente registra en `docs/ai-log.md` el alcance autorizado y lo realmente ejecutado, y en `docs/decisions.md` el resultado y los hallazgos, distinguiendo prueba automatizada, validación local y validación real.

## 13. Formulario de autorización (para que el propietario lo complete)

La presente instrucción **no** autoriza todavía: conexiones externas, uso de la identidad privada de B4, firmas reales, commit ni push. Para iniciar, el propietario debe confirmar expresamente:

1. **Servicios:** `wss://relay.primal.net:443` y `https://stacker.news` (solo en su ventana privada). ☐
2. **Identidad:** la de clave pública `c5a035bf…1a3f` (B4), importada **por el propietario**; cuenta de Stacker News ya asociada. ☐
3. **Operaciones permitidas:** los pasos 1 a 11 de §6; `connect`, `get_public_key`, una `sign_event` `kind` 27235. ☐
4. **Duración y límites:** ventana ≤ 15 minutos desde T0, 1 firma, sin reintentos ni segunda URI. ☐
5. **Restricciones:** las de §3 y las condiciones de parada de §8. ☐
6. **Destino:** `https://stacker.news/login` (o indique otro). ☐
7. **Ejecución:** `python -m uvicorn` en `127.0.0.1:8001`, abierto como `http://localhost:8001` (**decidido por el propietario el 2026-11-21**). ☐ confirmar para la prueba
8. **Agente durante la ventana:** solo diagnóstico de solo lectura (§7); sin aprobar, firmar ni manipular credenciales (**decidido el 2026-11-21**). ☐ confirmar para la prueba
9. **Captura redactada del resultado en Stacker News:** sí, preparada según §16 (**decidido el 2026-11-21**). ☐ confirmar para la prueba
10. **Fecha y hora de inicio (America/Santiago):** [______]

Una autorización de pruebas **no** habilita operaciones futuras ni acciones fuera de este alcance: al terminar la sesión o salirse de lo autorizado se vuelve a pedir autorización.

## 14. Resultado de las precondiciones (2026-11-21; todo local, sin red externa)

Se ejecutó en el equipo del propietario con una clave de **juguete** y sin leer secretos. Nada de lo siguiente abrió sockets externos, tocó la demostración ni creó la base de B6.2.

| # | Precondición | Resultado | Cómo se comprobó |
|---|---|---|---|
| 1 | B6.2 no reutiliza la base de B6.1D | **OK.** La demostración guarda su base en el volumen Docker `nip46-manual_app_data` (`/data/nip46.db` en el contenedor). B6.2 usa `data/b62.db` en el host: la carpeta `data/` ni siquiera existe todavía (`/data/` y `*.db` están ignorados por Git) | Ruta resuelta de `DATABASE_PATH`; `ls data`; `docker volume ls` |
| 2 | No reutiliza secretos ni credenciales de B6.1D | **OK.** La contraseña de B6.2 vive en `%USERPROFILE%\.nip46-b62\` (carpeta que **no existe aún**; la demo usa `.nip46-manual`). La clave de firma del JWT se genera **en memoria** en cada arranque (`secrets.token_bytes`) y no se guarda ni se comparte. La aplicación **no carga archivos `.env`** (sin `dotenv` en `app/`) | `grep` del código; `ls` de nombres |
| 3 | No afecta volúmenes ni sesiones del laboratorio | **OK.** Los contenedores `nip46-manual-*` siguen `healthy` y no se tocan. La cookie de sesión `nip46_session` no tiene atributo `Domain` (es por host, no por puerto; `Path=/api`): `localhost:8001` y `127.0.0.1:8000` son hosts distintos y no se pisan. El puerto 8001 está libre y el 8000 es el de la demo | `docker compose ps`, `netstat`, lectura de `app/api/auth.py` |
| 4 | Variables efectivas (sin valores secretos) | **OK.** `RELAY_URL=wss://relay.primal.net`, `RELAY_TLS_GROUPS=X25519`, `RELAY_ALLOW_INSECURE=False`, `SERVICE_ORIGIN=https://stacker.news`, `SIGNER_WINDOW_S=120`, `SECRET_TTL_S=600`, `APPROVAL_TTL_S=120`, `SESSION_TTL_S=720`, `CONNECTION_TTL_S=720`, `MAX_SIGNATURES=1`, `MAX_REQUESTS=30`, `MAX_PENDING=16`, `JWT_TTL_S=900`, `ALLOWED_HOSTS=127.0.0.1,localhost,[::1]`, `COOKIE_SECURE=False`, `DATABASE_PATH=data/b62.db`, `ADMIN_USERNAME=b62-admin`, contraseña **definida solo por archivo** (no leído). Ninguna variable ajena presente en el entorno del agente; para el **terminal del propietario** el arranque de §15 **limpia** primero cualquier variable que pueda alterar la configuración | `Settings.from_env` con exactamente esas variables |
| 5 | Política compatible con **una** firma `kind` 27235 | **OK.** Un evento 27235 con la forma de Stacker News pasa las 11 comprobaciones; `kind` 1 falla `kind`; `u` con ruta (`https://stacker.news/login`) falla `origin`; antigüedad 119 s pasa y 121 s falla; el tope es 1 firma por sesión. Con el evento **real** de B4 la política dio `ok=true` (`u=https://stacker.news`, antigüedad 1 s). 103 pruebas de política, configuración e inicio en verde | Script local con clave de juguete; `pytest tests/services/test_policy.py tests/test_config.py tests/api/test_startup.py` |
| 6 | Ventana suficiente para el flujo manual | **OK con margen amplio.** En B4: aprobación de `connect` en 13,4 s, de `sign_event` en 7,8 s, sesión completa de 2 min 5 s. Presupuesto: aprobar `connect` ≤ 120 s, aprobar la firma ≤ 120 s desde que se crea el evento, sesión 720 s, límite duro 900 s. **Riesgo residual:** el tiempo de espera propio de Stacker News para la respuesta de `connect` no es conocido (en B4 no hubo problema con 13,4 s); apruebe con rapidez tras revisar | Auditoría de B4; configuración efectiva |
| 7 | No requiere modificar código ni ampliar permisos | **OK.** Sin cambios en `app/`, `Dockerfile` ni `compose.yaml`; solo variables de entorno ya existentes y la política vigente (1 firma, `kind` 27235, origen exacto). No se amplía ninguna ventana, límite ni permiso | `git status` (solo documentación nueva) |
| 8 | `Host` y puerto | **OK.** Con una app en memoria y base temporal: `Host: localhost:8001` → `/health` 200 y `/api/status` sin sesión 401; `Host: evil.invalid` → 400 | Prueba ASGI local (sin sockets) |
| 9 | Exportación de la auditoría | **OK.** La secuencia de §15 (ingreso con usuario y contraseña, `GET /api/audit?limit=500`) funciona; se probó en memoria con credenciales de prueba | Prueba ASGI local |

**Riesgos que las precondiciones no eliminan:**
- Si `https://stacker.news/login` firmara un evento con otro `u` (p. ej. con ruta), la política lo **rechaza** y no habría firma: sería una condición de parada (BLOCKED), no un fallo del firmante. B4 observó `u=https://stacker.news` (`/signup`); para `/login` **no hay observación previa**.
- No se pudo comprobar la sincronización del reloj de Windows desde el agente: sincronícelo antes de T0 (Configuración → Hora e idioma → Sincronizar ahora). Un desvío de más de 30 s adelantado o de más de 120 s atrasado haría rechazar el evento.
- Una autenticación local exitosa no demuestra la de Stacker News (B6 y B7 de la matriz solo por su observación).

## 15. Instrucciones exactas para el propietario (PowerShell 7, raíz del repositorio)

> **Actualización (D-16):** los pasos de «Antes de T0» y de «T0 — arranque» que usan Uvicorn quedan **sustituidos por los comandos de Docker Compose de §17**. El resto (navegador, importación de la identidad, cierre, auditoría) no cambia salvo el origen del `server.log` (§17.2, paso 6).

**Antes de T0 (sin red externa; no cuenta en los 15 minutos):**

1. Sincronice el reloj. Abra una **ventana privada** del navegador, sin sesión de Stacker News y sin extensiones que lean páginas.
2. Cree la contraseña de B6.2 (no se imprime; es distinta de la de la demostración):
   ```powershell
   $d = Join-Path $env:USERPROFILE ".nip46-b62"; New-Item -ItemType Directory -Force $d | Out-Null
   $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Fill($b)
   [Convert]::ToBase64String($b) | Set-Content -NoNewline (Join-Path $d "admin_password.txt"); Remove-Variable b
   ```
3. Active el entorno y cree la carpeta de evidencias (excluida de Git):
   ```powershell
   .\.venv\Scripts\Activate.ps1
   $f = Get-Date -Format "yyyyMMdd-HHmm"; $ev = "lab/results/b62-$f"; New-Item -ItemType Directory -Force $ev | Out-Null; $ev
   ```
4. Avise al agente («listo para T0») y confirme por escrito el inicio. **T0 = el momento en que usted ejecute el paso 5. Fin duro: T0 + 15 minutos.**

**T0 — arranque (terminal 1; déjela abierta):**

5. ```powershell
   # Limpia variables que podrían alterar la configuración y fija exactamente las de B6.2
   foreach ($n in "ADMIN_PASSWORD","RELAY_ALLOW_INSECURE","ALLOWED_HOSTS","MAX_PENDING","COOKIE_SECURE","APP_PORT") { Remove-Item "Env:$n" -ErrorAction SilentlyContinue }
   $env:RELAY_URL = "wss://relay.primal.net"; $env:RELAY_TLS_GROUPS = "X25519"; $env:SERVICE_ORIGIN = "https://stacker.news"
   $env:SIGNER_WINDOW_S = "120"; $env:SECRET_TTL_S = "600"; $env:APPROVAL_TTL_S = "120"; $env:MAX_SIGNATURES = "1"; $env:MAX_REQUESTS = "30"
   $env:SESSION_TTL_S = "720"; $env:CONNECTION_TTL_S = "720"; $env:JWT_TTL_S = "900"
   $env:DATABASE_PATH = "data/b62.db"; $env:ADMIN_USERNAME = "b62-admin"; $env:ADMIN_PASSWORD_FILE = (Join-Path $env:USERPROFILE ".nip46-b62\admin_password.txt")
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 2>&1 | Tee-Object -FilePath "$ev/server.log"
   ```
   Debe aparecer «Uvicorn running on http://127.0.0.1:8001» y un registro `admin_bootstrap result=created` (primer arranque). No hay código de acceso en la terminal.

**Navegador (pasos 1 a 4 del §6):**

6. Abra `http://localhost:8001` (**con `localhost`, no `127.0.0.1`**). Usuario `b62-admin`; la contraseña está en `%USERPROFILE%\.nip46-b62\admin_password.txt` (ábrala usted; no la pegue en ningún chat).
7. **Importar la identidad B4** (terminal 2, misma raíz y entorno): `python lab/tools/b4_identity.py copy --file "$env:USERPROFILE\.nip46-b4\identity.key"` → pegue en «Importar una clave propia» → **Importar** → `python lab/tools/b4_identity.py clear-clipboard`. Compruebe que la clave pública mostrada empieza por `c5a035bf`.
8. **Iniciar firmante** → debe pasar a **Listo**. Si pasa a **Fallido**: no reintente, avise (§8).
9. **Emitir URI de un solo uso** y cópiela. No la pegue en ningún chat ni nota.

**Navegador, ventana privada (pasos 5 a 11 del §6):**

10. Abra `https://stacker.news/login` → «Continue with Nostr» → inicio con firmante remoto (bunker) → pegue la URI. No pulse nada más. Ante datos, pago, billetera, correo, captcha o términos → §8.
11. En el panel: tarjeta **Conexión de un cliente** → revise y **Aprobar** (dentro de 120 s).
12. En el panel: **Firma del evento de inicio de sesión** → compruebe las **11 comprobaciones en verde**, `u` = `https://stacker.news`, contenido «Stacker News Authentication» y antigüedad de pocos segundos → **Aprobar**. Si algo está en rojo: **Denegar** y §8.
13. En el panel debe aparecer el resultado **Firmada** (P-42). Mire Stacker News **sin pulsar nada más**: anote si aparece su usuario autenticado (esperable: asociado a `@c5a035bf14…`). Si aparece la incorporación de billetera, **no conecte ninguna** (en B4 se eligió «Skip for now»).
14. **Recargue la página una vez** y anote si sigue autenticado.
15. **Captura redactada** (solo si el resultado es visible): ver §16.

**Cierre inmediato (en cuanto termine, o al llegar a T0 + 15 min):**

16. En el panel: **Detener**. Exporte la auditoría (terminal 2, **con el servidor aún en marcha**; la contraseña se lee del archivo y no se imprime):
    ```powershell
    $B = "http://localhost:8001"; $pw = (Get-Content (Join-Path $env:USERPROFILE ".nip46-b62\admin_password.txt") -Raw).Trim()
    Invoke-RestMethod -Method Post -Uri "$B/api/auth/login" -ContentType application/json -Body (@{username="b62-admin"; password=$pw} | ConvertTo-Json) -SessionVariable s | Out-Null
    Invoke-RestMethod -Uri "$B/api/audit?limit=500" -WebSession $s | ConvertTo-Json -Depth 6 | Set-Content "$ev/audit.json"; Remove-Variable pw
    ```
    (El firmante detenido sigue permitiendo consultar la auditoría.)
17. **Cerrar sesión** en el panel. En la terminal 1: `Ctrl+C`. Cierre la ventana privada (cierra la sesión de Stacker News) y ejecute `python lab/tools/b4_identity.py clear-clipboard`.
18. `python lab/tools/b4_check_evidence.py "$ev/audit.json"` → debe decir «Sin fugas» y «COHERENTE» (una `sign_ok` y un `session_end`). Si detecta fugas, **no comparta el archivo**.
19. Escriba `$ev/notas.txt` (§16) y avise al agente. Una segunda tentativa requiere **nueva autorización**.

## 16. Evidencias, sanitización y captura

| Evidencia | Contenido permitido | Sanitización y verificación | Destino |
|---|---|---|---|
| `audit.json` (auditoría exportada) | Eventos con identificadores truncados (8/16 caracteres) y contadores | El producto no registra claves, URI, JWT ni retos completos; `b4_check_evidence.py` busca `nsec`, `bunker://`, `secret=`, JWT, cookies, hexadecimales de 64 caracteres y base64 largo | `lab/results/b62-<fecha>/` (ignorada por Git); copia sanitizada a `docs/evidence/` solo con su aprobación |
| Salida del verificador | «Sin fugas» / «COHERENTE» y resumen técnico | Salida de herramienta, sin datos | Igual |
| `server.log` | Registro de uvicorn y de la aplicación (sin cuerpos ni cabeceras; el producto no imprime secretos) | El agente lo **lee** (solo lectura) y lo escanea con los mismos patrones antes de citar nada; si hay un hallazgo, no se cita ni se versiona | Solo `lab/results/` (no se versiona) |
| `notas.txt` | Hora de T0 y de fin, clave pública truncada (8 caracteres), qué mostró Stacker News, si la sesión persistió al recargar | **Sin** URI, contraseña, clave, JWT, cookies, retos ni datos de la cuenta más allá del seudónimo público | `lab/results/` |
| **Captura redactada** (autorizada el 2026-11-21) | Solo la ventana del navegador con el **resultado** en Stacker News (estado autenticado y seudónimo `@c5a035bf14…`, derivado de la clave pública) | La toma el propietario (el agente no usa herramientas de navegador ni de pantalla). Debe **excluir**: barra de direcciones con parámetros, herramientas de desarrollo, cookies, portapapeles, el panel del firmante con la URI, y cualquier dato de billetera, correo o saldo. Se guarda como `$ev/sn-resultado.png`; el agente la **revisa visualmente** antes de aceptarla; si aparece algo sensible, se recorta o se descarta; no se versiona sin su aprobación expresa | `lab/results/` |

Qué **no** se recopila: la URI, la contraseña, la clave privada, el JWT, las cookies, el reto completo, grabaciones de red (HAR) ni capturas del paso de importación o de la URI.

**Validación en Ubuntu (decisión 5 del propietario):** queda **después** de completar B6.2, cerrar las pruebas, documentar y publicar el proyecto. No forma parte de esta autorización.

## 17. Ejecución en Docker Compose (D-16; sustituye a Uvicorn en §4 y §15)

**Estado (2026-11-22): configuración, documentación y pruebas implementadas, y transición EJECUTADA hasta el subpaso 3.4 (interacciones 40 y 41 de `docs/ai-log.md`); B6.2 real NO ejecutada.** El propietario decidió que **Docker Compose es el entorno principal** (desarrollo, validación y despliegue). Una única instancia activa del producto durante B6.2; puerto **8001** (el 8000 será el predeterminado del producto después de esta validación). La demostración B6.1D **se detiene de forma reversible** antes de la prueba (autorizado; sin eliminar imágenes, redes ni volúmenes) y todas sus evidencias, y las de la primera ventana de B6.2 (`lab/results/b62-20261121-2000/`), se conservan.

### 17.0 Estado de la transición (2026-11-22)
| Paso del plan | Estado | Resultado verificado |
|---|---|---|
| 1. Detener B6.1D (reversible) | **Hecho** | `docker compose ... stop`: 3 contenedores detenidos; puertos 8000, 17777 y 18080 libres; volumen, imágenes, redes y recursos ajenos (Magento) intactos |
| 2. Imagen | **Hecho** | SHA-256 de `app/` frente a las imágenes: `manual-b61d` coincide **39/39**; `dev` difiere en 5 archivos y **no debe usarse**. Dependencias de `manual-b61d` iguales a `constraints.txt` (solo `pip`), `pip check` sin problemas, `compose config` con el perfil correcto. No se reconstruyó nada |
| 3. Entorno limpio | **Hecho** | variables de la sesión limpiadas y `APP_IMAGE=nostr-nip46-remote-signer:manual-b61d` |
| 4. Crear, importar y arrancar | **Hecho** (subpasos 3.0 a 3.4) | proyecto `nostr-nip46-remote-signer` creado; `data/b62.db` importada (integridad `ok`, 1 administrador, `uid 10001`, `0600`/`0700`, SHA-256 del origen sin cambios); aplicación en `127.0.0.1:8001`, healthy, `admin_bootstrap result=exists`, sin actividad NIP-46 ni sockets salientes |
| 5. Comprobaciones previas a T0 (reloj, valores efectivos, sockets) | **Pendiente** (subpaso 3.5) | las de valores efectivos y sockets se cubren en la prueba E2E; el reloj del contenedor no se comparó todavía |
| T0 y la prueba real con Stacker News | **No autorizada / no ejecutada** | se hará con el código final del modo continuo (D-17), **no** con `manual-b61d` |

**Consecuencia (decisión del propietario, 2026-11-22):** la imagen `manual-b61d` queda **obsoleta para la validación real**, porque el modo continuo cambia `app/`. Antes de la prueba real habrá que reconstruir la imagen (con la autorización aparte para acceder a Docker Hub y PyPI), actualizar el perfil de validación y pedir una nueva autorización operativa con su alcance (los términos de «una firma» y «15 minutos» eran los de la autorización anterior). El perfil `deploy/b62.env` fija `SIGNER_MODE=supervised`, que conserva el comportamiento de B6.2.

### 17.1 Qué cambió (y qué no)
| Elemento | Cambio |
|---|---|
| `compose.yaml` | Reenvía `SIGNER_WINDOW_S`, `SECRET_TTL_S`, `CONNECTION_TTL_S`, `MAX_REQUESTS`, `MAX_PENDING`, `COOKIE_SECURE` (vacío = valor por defecto). **No** reenvía `RELAY_ALLOW_INSECURE` ni `ADMIN_PASSWORD_FILE` |
| `deploy/b62.env` (nuevo) | **Perfil de validación**, no la configuración definitiva del producto: los límites exactos de §4, `APP_PORT=8001`, sin secretos. Se usa con `--env-file`, que **sustituye** al `.env` local |
| `deploy/import_admin_db.py` (nuevo) | Importa `data/b62.db` al volumen sin sobrescribir, sin exponer la contraseña y sin modificar el origen (§17.3) |
| `app/`, `Dockerfile` | **Sin cambios** |

### 17.2 Orden de la transición (cada paso se ejecuta solo con la confirmación del propietario; **ninguno** abre conexiones al relay ni a Stacker News)
1. **Detener B6.1D (reversible):** `docker compose -p nip46-manual -f compose.yaml -f lab/manual/compose.manual.yaml stop` (nunca `down`, nunca `-v`; se reanuda con `start`). Comprobar que los puertos 8000, 17777 y 18080 quedan libres.
2. **Imagen:** comparar el código de `app/` del árbol con el de la imagen que se usará (hash de cada archivo). Si **difiere**, hay que reconstruir, lo que **contacta Docker Hub y PyPI**: requiere autorización aparte, antes de T0. Si coincide, se reutiliza.
3. **Entorno limpio** (las variables del proceso **prevalecen** sobre `--env-file`):
   ```powershell
   foreach ($n in "ADMIN_USERNAME","ADMIN_PASSWORD","ADMIN_PASSWORD_FILE","RELAY_URL","RELAY_TLS_GROUPS","RELAY_ALLOW_INSECURE","SERVICE_ORIGIN","ALLOWED_HOSTS","APP_PORT","APP_IMAGE","SIGNER_WINDOW_S","SECRET_TTL_S","APPROVAL_TTL_S","MAX_SIGNATURES","MAX_REQUESTS","MAX_PENDING","SESSION_TTL_S","CONNECTION_TTL_S","JWT_TTL_S","COOKIE_SECURE") { Remove-Item "Env:$n" -ErrorAction SilentlyContinue }
   $dc = @("compose","--env-file","deploy/b62.env","-p","nostr-nip46-remote-signer")   # bash: DC="docker compose --env-file deploy/b62.env -p nostr-nip46-remote-signer"
   ```
4. **Crear (sin iniciar), importar y arrancar** (sin construir ni descargar nada; en bash, `$DC` en lugar de `docker @dc`):
   ```powershell
   docker @dc create --no-build --pull never
   python deploy/import_admin_db.py --source data/b62.db --volume nostr-nip46-remote-signer_app_data --image nostr-nip46-remote-signer:manual-b61d
   docker @dc up -d --no-build --pull never
   ```
5. **Comprobaciones previas a T0 (solo lectura):**
   - (a) `docker @dc config` muestra los límites del perfil, `127.0.0.1:8001` y ninguna contraseña.
   - (b) `docker @dc logs --no-color --no-log-prefix app` dice `admin_bootstrap result=exists` y **no** contiene `relay_ready`, `bunker_issued` ni `session_start`.
   - (c) Valores efectivos dentro del contenedor (`Settings.from_env`), `uid 10001`, `CapEff` 0, `NoNewPrivs` 1 y **ningún socket saliente** (`/proc/net/tcp` y `tcp6` sin `ESTABLISHED` hacia direcciones no loopback), con las mismas comprobaciones que `tests/e2e/test_docker_b62_profile.py`.
   - (d) **Reloj:** comparar `docker @dc exec -T app python -c "import time; print(int(time.time()))"` con `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`. La política tolera 120 s de antigüedad y **30 s de adelanto**, y la VM de Docker puede desviarse tras suspender el equipo. Si difiere más de unos segundos, no iniciar T0 y avisar.
6. **Registro del servidor** (sustituye a `Tee-Object`; el producto no imprime secretos): al terminar, `docker @dc logs --no-color --no-log-prefix app > lab/results/b62-20261121-2250-v2/server.log`. Se escanea con los mismos patrones (§16) antes de citarlo.
7. **Después de la prueba:** `docker @dc stop` (conserva contenedor y volumen) o `down` **sin** `-v`.

### 17.3 Importación de la base (`deploy/import_admin_db.py`)
- **Origen intacto:** se monta de **solo lectura** en un contenedor efímero (`--network none --read-only --cap-drop ALL --user 10001`) y se compara su SHA-256 antes y después. Rechaza un origen que no sea SQLite, que sea un enlace simbólico o que tenga `-journal`, `-wal` o `-shm` pendientes (hay que detener antes cualquier proceso que lo use).
- **Sin sobrescritura:** el destino `/data/nip46.db` se crea con `O_EXCL`; si ya existe, se aborta sin tocarlo. **No hay opción para forzar.** Si algo falla tras crearlo, se elimina **solo** ese archivo recién creado.
- **Verificado dentro del contenedor auxiliar:** copia con la API de respaldo de SQLite; `integrity_check` = ok; misma `user_version`; mismo número de administradores (≥ 1); archivo con `uid 10001` y modo `0600`; `/data` con `uid 10001` y modo `0700`; sin archivos residuales.
- **Secretos:** no lee ni imprime contraseñas, hashes ni usuarios. La contraseña de `%USERPROFILE%\.nip46-b62\admin_password.txt` no se monta ni pasa por el entorno: con la base importada no hace falta `ADMIN_PASSWORD`, así que `docker inspect` no puede exponerla.
- **Precondiciones que exige:** el volumen existe (`create`), ningún contenedor en marcha lo usa y la imagen existe en local (no descarga ni construye).

### 17.4 Pruebas de esta etapa
`tests/test_deploy_profile.py` (deterministas, sin red) y `tests/e2e/test_docker_b62_profile.py` (`E2E_DOCKER=1`; proyecto y volumen efímeros; base y contraseña **ficticias**; no construye ni descarga). Son **pruebas automatizadas**: no demuestran interoperabilidad con Stacker News ni validan B6.2.

### 17.5 Riesgos nuevos y abiertos
| Riesgo | Medida |
|---|---|
| Desviación del reloj de la VM de Docker respecto de Windows | Comprobación previa (17.2, 5d) |
| Que el contenedor no logre el TLS al relay (MTU/NAT de Docker Desktop; B6.2 no admite reintentos) | **No verificable sin red externa**; el propietario **no** autorizó una prueba previa de conectividad. Si «Iniciar firmante» pasa a «Fallido», §8 (sin reintentar) |
| Imagen desactualizada respecto de `app/` | Comparación de hashes y, si difiere, reconstrucción con autorización (17.2, paso 2) |
| `restart: unless-stopped` | El contenedor no inicia el firmante por sí solo (solo lo hace la API autenticada); un reinicio no abre conexiones |
| `docker volume prune` | **Prohibido**: puede alcanzar volúmenes ajenos (`magento246_appdata`) |

### 17.6 Resultado de la validación real (2026-11-22)
**PASS declarado y confirmado personalmente por el propietario**: «la prueba real con Stacker News fue exitosa» y el firmante permitió «completar la autenticación real desde la interfaz web». Entorno: imagen `nostr-nip46-remote-signer:d17-continuous`, perfil `deploy/continuous.env` (modo continuo, relay `wss://relay.primal.net`, `RELAY_TLS_GROUPS=X25519`, origen `https://stacker.news`), proyecto `nostr-nip46-remote-signer`, volumen `nostr-nip46-remote-signer_app_data`. La contraseña del administrador de ese entorno se restableció antes de la prueba con autorización expresa (respaldo previo de la base; entrada 50 de `docs/ai-log.md`).

| Criterio del plan (§2 a §9) | Estado |
|---|---|
| Autenticación efectiva en Stacker News | **Confirmada por el propietario** (sin captura ni evidencia técnica) |
| Una sola firma `kind 27235` | **No verificado** (el modo continuo no tiene tope total de firmas; el límite lo ponía la persona) |
| Aprobación manual individual de `connect` y `sign_event` | **No verificado en esta ejecución** (la política lo exige; hay pruebas automatizadas) |
| Ventana máxima de 15 minutos, T0 y fin | **No verificado** (el plan supervisado no se aplicó tal cual) |
| Identidad B4 (`c5a035bf…`) | **No verificado** (el agente no participó ni leyó la clave) |
| Auditoría sanitizada y evidencia en `lab/results/` | **No capturada** |
| Estado final del firmante | **No verificado**; una comprobación posterior mostró una conexión saliente abierta (probablemente seguía iniciado) |

Para una evidencia sólida habría que repetir la prueba con captura de la auditoría sanitizada y una autorización nueva con alcance definido (`AGENTS.md` §11).
