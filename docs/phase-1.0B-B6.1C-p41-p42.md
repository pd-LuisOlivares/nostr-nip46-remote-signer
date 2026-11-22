# B6.1C: cierre de P-41 (compuerta Argon2id) y P-42 (resultado real de la firma en la interfaz)

**Fecha:** 2026-11-21 · **Base:** `4b9e51eba698c3434f4fee3b0f6a5224e60e504b` más los cambios locales sin commit de B6 etapa 1, B6.1A y B6.1B (conservados) · **Veredicto: PASS** (P-41 y P-42 pueden cerrarse; ver §6) · Sin commit ni push.

Validación **local**: sin conexión a Stacker News ni a relays públicos, sin la identidad de B4 y sin firmas reales (las pruebas usan claves efímeras). `AGENTS.md` y `CLAUDE.md` no se modificaron. No se cambiaron los parámetros de Argon2id, la política NIP-46, la revalidación de P-38 ni el comportamiento de firma.

## 1. P-41: una verificación Argon2id activa por proceso

**Problema (B6.1B):** cada verificación Argon2id reserva 64 MiB y el limitador admite hasta 5 en vuelo: 5 simultáneas con 256 a 352 MiB provocaban un OOM-kill del contenedor.

**Corrección:** `VerificationGate` (`app/security/verification_gate.py`, sin FastAPI), usada por `POST /api/auth/login` para **toda** verificación (`AdminAccounts.authenticate`, que incluye al usuario inexistente con su hash de señuelo: mismo costo y misma respuesta).
- **Una activa** (`asyncio.Semaphore(1)`); el cálculo corre en un hilo (`asyncio.to_thread`): **no bloquea el event loop**.
- **Cola acotada:** como máximo 4 esperando (`DEFAULT_MAX_WAITING`); con la cola llena, rechazo inmediato. **Espera máxima 3 s** (`DEFAULT_WAIT_TIMEOUT_S`; una verificación dura ~0,05-0,1 s). Superado cualquiera: `Busy` → **503** `{"detail": "servicio ocupado"}` con `Retry-After: 2`. Nunca hay cola ilimitada.
- **Sin carreras ni fugas de cupo:** el cupo se libera **cuando termina el hilo**, no cuando se cancela quien esperaba (un cliente que se desconecta no deja dos cálculos a la vez); la espera usa `wait_for(acquire)`, de modo que un rechazo no consume cupo.
- **Fuerza bruta intacta:** el intento se reserva antes de verificar (como en B6.1A). Un rechazo por capacidad (503) **libera** su reserva: no se verificó nada, no es un fallo de credenciales y no da ventaja de fuerza bruta; los 5 fallos **reales** siguen bloqueando con 429 aunque la contraseña sea correcta (probado).
- **Registro:** `auth event=login_busy`; nunca contraseñas ni hashes. La interfaz muestra un mensaje distinto para 503 («ocupado o no disponible»).
- **Parámetros de Argon2id:** **sin cambios** (RFC 9106 «low memory»: t=3, m=64 MiB, p=4).

**Despliegue real (un proceso):** `Dockerfile` (`CMD uvicorn app.main:app …`), `compose.yaml`, el laboratorio y el comando del README **no** usan `--workers` ni `WEB_CONCURRENCY` (una prueba lo verifica). El semáforo es **por proceso**: con varios procesos no sería un límite global y la memoria máxima sería N × 64 MiB. Pero esa configuración **no está soportada** de todos modos: la clave de firma del JWT, las sesiones y los limitadores viven en la memoria de cada proceso (una sesión emitida por un proceso no valdría en otro).

### Resultados de memoria (contenedor real, sin swap, raíz de solo lectura; 3 rondas de ráfagas por caso)

| Límite | Ráfaga simultánea | Antes (B6.1B, sin compuerta) | Ahora |
|---|---|---|---|
| 128 MiB | 1, 5 y 8 | 5: cae | **OK**: respuestas 401/429, sin OOM, `/health` 200 |
| 192 MiB | 5 | OOM-kill | **OK** (exploración) |
| 256 MiB | 5 y 8 | **OOM-kill** (exit 137) | **OK** |
| 384 MiB | 8 | OK | **OK** |
| 512 MiB | 8 | OK | **OK** |

Los 429 son el limitador de fuerza bruta (5 fallos por ventana), como corresponde. Pruebas automáticas (`tests/e2e/test_docker_argon2_memory.py`, `E2E_DOCKER=1`): 128 MiB × 1/5/8, 256 MiB × 5/8, 384 MiB × 8 y 512 MiB × 8 — **el `xfail` se eliminó porque el problema está resuelto** (la prueba de 256 MiB × 5 ahora es una aserción normal).

### Pruebas de P-41
`tests/security/test_verification_gate.py` (7): una sola activa con 12 tareas, cola llena con rechazo inmediato y recuperación, espera agotada y recuperación, **cancelación sin liberar el cupo hasta que termina el hilo**, cola de cero, errores que liberan el cupo, valores acotados. `tests/api/test_login_capacity.py` (8 casos): login correcto, contraseña incorrecta y usuario inexistente (mismo 401 y mismo costo), **5 y 8 simultáneos** (nunca dos verificaciones a la vez; 5×401 + 3×429), **tiempo de espera agotado** → 503 que no cuenta como fallo, cola llena → 503, recuperación, límite de fuerza bruta intacto tras rechazos por capacidad, cookie/JWT/CSRF/logout intactos y despliegue de un solo proceso. Las pruebas existentes de login, SQLite, JWT, cookies y CSRF no cambiaron y pasan. **Comprobación de mutación** (cada mutación detectada por las pruebas indicadas): sin compuerta (6 pruebas), dos activas (11), cola sin límite (2), cupo liberado al cancelar (1), el rechazo por capacidad cuenta como fallo (3).

## 2. P-42: estado real de la firma

**Ciclo de vida inspeccionado:** `PendingRequest.status` solo guardaba la **decisión del operador** (`pending/approved/denied/expired/cancelled`). Tras aprobar, `_revalidate_and_sign` podía rechazar la firma (P-38) y la interfaz seguía mostrando «aprobada» (y el mensaje «Solicitud aprobada.» salía antes del resultado).

**Corrección mínima (reutiliza el estado y la auditoría; sin sistema de seguimiento nuevo):**
- `PendingRequest` gana `outcome` (`None`, `signed`, `refused`, `failed`) y `outcome_reason` (código corto y fijo). `status` **no cambia** (compatibilidad: los consumidores anteriores siguen funcionando; los campos nuevos son aditivos). La API (`RequestOut`) expone ambos.
- `signer._revalidate_and_sign` fija el resultado real: `signed` (firma producida **y autoverificada**), `refused` (revalidación: `politica_incumplida`, `aprobacion_caducada|consumida|no_vigente`, `firmante_no_activo`, `cliente_no_activo`, `solicitud_alterada`, o `reutilizacion_o_tope`) o `failed` (`autoverificacion`). Al terminar la sesión, `finalize_unresolved` pasa a `failed/sesion_terminada` toda firma aprobada que no llegó a tener resultado (nunca queda «pendiente» para siempre).
- La interfaz muestra el resultado del servidor (`stateOf`), anuncia **cada transición** con un banner (los resultados anteriores al ingreso no se anuncian) y el mensaje tras pulsar «Aprobar» ya no sugiere éxito.

### Estados representados

| Estado | Backend | Interfaz (Recientes / banner) |
|---|---|---|
| Pendiente de aprobación | `status = pending` | Tarjeta en «Solicitudes pendientes» |
| Aprobada por el operador, pendiente de resultado | `status = approved`, `outcome = None` | «Aprobada por el operador; falta el resultado de la firma»; banner tras pulsar: «Solicitud aprobada. Falta el resultado de la firma (vea «Recientes»).» |
| Firmada correctamente | `outcome = signed` | «Firmada correctamente»; banner «Firma realizada correctamente.» |
| Rechazada por política o revalidación | `outcome = refused` + motivo | «Rechazada al firmar: <motivo en español>»; banner de error «La firma NO se realizó: …» |
| Fallida | `outcome = failed` + motivo | «Fallida: <motivo>»; banner de error |
| Rechazada por el operador / expirada / cancelada | `status = denied / expired / cancelled` | «rechazada» / «caducada» / «cancelada» |
| `connect` | sin cambios (`status`) | «aprobada», etc. (sin resultado de firma) |

**Información sensible:** solo códigos fijos; ni la plantilla, el reto, la huella, claves ni texto libre del cliente (un código desconocido se muestra como texto, sin HTML; probado con contenido hostil).

### Pruebas de P-42
- **Backend** (`tests/services/test_signer.py`, `test_connections_approvals_audit.py`): ciclo pendiente → aprobada sin resultado → firmada; denegada y expirada sin resultado de firma; tope de firmas → `refused/reutilizacion_o_tope`; fallo de autoverificación → `failed`; sesión terminada → `failed/sesion_terminada`; `connect` sin cambios; vista pública sin secretos; todas las pruebas de revalidación de B6.1B ahora comprueban también el resultado `refused` y su motivo; `set_outcome` solo una vez y `finalize_unresolved` solo afecta a firmas aprobadas sin resultado.
- **API** (`tests/api/test_control_api.py`): `/api/requests` informa `signed`, y una aprobación tardía real (ventana de 1 s) como `refused/politica_incumplida` con `signatures == 0` y sin reto, claves ni plantilla.
- **Interfaz, navegador real** (`tests/e2e/test_browser_login.py`): todos los estados y **cada transición con respuestas controladas** (aprobada sin resultado no se muestra como firmada, solo una «Firmada correctamente», banners de error distintos), contenido hostil como texto, y el **flujo real** (relay local): una aprobación a tiempo se muestra como firmada y una aprobación tardía se muestra como **«Rechazada al firmar: la política dejó de cumplirse»** con el contador de firmas sin avanzar. **Mutación:** si la interfaz muestra «aprobada» como «firmada», si muestra la firma rechazada como firmada, si no anuncia las transiciones, o si el backend no registra el rechazo, marca firmada antes del resultado o deja la firma pendiente al cerrar, las pruebas fallan (6 de 6 mutaciones de P-42 detectadas).

## 3. Regresión

| Comprobación | Resultado |
|---|---|
| `pytest -q -rs -rx` con `E2E_DOCKER=1` (equipo de desarrollo, con vectores NIP-44) | **815 passed, 1 skipped, 0 xfailed** (162 s). Omitida: permisos POSIX (Windows) |
| `pytest -q -rs` sin `E2E_DOCKER` | 805 passed, 11 skipped (95 s): 7 de memoria + 1 NDK + 2 persistencia (Docker) y 1 POSIX |
| Copia limpia (exportación del árbol de trabajo, venv nuevo, instalación según el README, `pytest -q -rs`) | pip sin errores, `pip check` limpio; **797 passed, 19 skipped** (98 s) |
| E2E de navegador (Chrome) | 22 (incluidas en lo anterior): login SQLite, cookies, CSRF, revocación y P-37/P-42 |
| E2E Docker | SQLite persistente, NDK 2.12.2 real con el login nuevo y memoria limitada: aprobados |
| Regresión NIP-46 `lab/run_product_regression.py` y `--api` (NDK 2.12.2 real) | **E1, E2, E3 y E8: PASS en ambos modos** |
| `mypy --strict app` | `Success: no issues found in 36 source files` (1 error de tipos propio corregido en el camino) |
| `pip check` / `git diff --check` | limpios |
| Cobertura de líneas y ramas de `app/` | 99 % total; `auth.py` y `main.py` 100 %, `verification_gate.py` 97 %, `approvals.py` 98 %, `signer.py` 99 % |

SQLite, JWT, cookies, CSRF, el login y la revalidación P-38 siguen funcionando (todas sus pruebas pasan sin cambios de política).

## 4. Limitaciones conocidas

- **«Firmada» significa que la firma se produjo y se autoverificó en el servidor.** No confirma que el relay aceptara ni que el cliente recibiera la respuesta: eso se registra aparte en la auditoría (`response_published`) y no se añadió seguimiento nuevo (fuera de alcance).
- El resultado vive en memoria (como el resto de solicitudes) y el historial se limita a 100 solicitudes.
- La compuerta es **por proceso**; solo se soporta un proceso (ver §1). Bajo una ráfaga la latencia de los intentos simultáneos se serializa (5 × ~60-100 ms).
- Un tercero local aún puede bloquear el ingreso 5 minutos con intentos erróneos (P-40, sin cambios).
- Medición de memoria en un solo anfitrión (Docker Desktop, cgroup v2); E2E de navegador solo en Chrome; Linux/macOS sin Docker y arm64 sin probar.

## 5. Riesgos pendientes

P-39 (sin cambio de contraseña guiado) y P-40 (límite de login global) siguen abiertos y opcionales; sin *hashes* en `constraints.txt`; la verificación «copia limpia» es una exportación del árbol de trabajo (no hay commit).

## 6. ¿Pueden cerrarse P-41 y P-42?

- **P-41: sí.** La compuerta limita a una verificación activa por proceso, con cola acotada, espera máxima y rechazo controlado; no hay OOM con 256 MiB ni con 128 MiB; la protección de fuerza bruta y el resto de la autenticación están intactos; el `xfail` se eliminó porque está resuelto. Salvedad documentada: solo un proceso.
- **P-42: sí.** La interfaz ya no presenta una aprobación como firma: muestra el resultado real del backend (cinco estados distintos) y anuncia el resultado. Salvedad documentada: «firmada» no incluye la entrega al relay.

## 7. Archivos

**Creados:** `app/security/verification_gate.py`, `tests/security/test_verification_gate.py`, `tests/api/test_login_capacity.py`, este informe.
**Modificados:** `app/api/auth.py`, `app/main.py`, `app/services/{approvals,signer}.py`, `app/schemas/control.py`, `app/static/{app.js,app.css}`, `tests/e2e/{test_docker_argon2_memory,test_browser_login}.py`, `tests/services/{test_signer,test_connections_approvals_audit}.py`, `tests/api/test_control_api.py`, `README.md`, `docs/{decisions,ai-log,handoff-2026-11-21,project-context,phase-1.0B-B6.1B-security-closure}.md`. `AGENTS.md` y `CLAUDE.md` sin cambios.

## 8. Estado de Git

Sin commit, sin push, historial intacto. `HEAD` sigue en `4b9e51e`, igual que `origin/main`; el trabajo de B6 etapa 1, B6.1A, B6.1B y B6.1C está en el árbol de trabajo. Ver el informe final para `git status` y `git diff --check`.

## 9. Preparación para B6.2

1. **Su revisión y, si lo autoriza, commit y push** de todo el trabajo pendiente (revisando secretos con `git diff --cached`).
2. **Verificación con un `git clone` real** del commit publicado: instalación con el README, suite, `docker compose build --no-cache`, `docker compose up --build -d` con `ADMIN_PASSWORD` por entrada oculta e ingreso por la interfaz.
3. **Compuerta operativa de B6 real** (autorización expresa, con alcance): repetir el inicio de sesión en Stacker News desde la interfaz con el nuevo ingreso y la misma identidad de B4 (importada por la interfaz), comprobando la persistencia de la sesión al recargar. Una firma, aprobación humana **dentro de `SIGNER_WINDOW_S`** (120 s por defecto menos la antigüedad de la plantilla), ventana ≤ 15 min, sin reintentos. Con P-42 la interfaz mostrará «Firmada correctamente» solo si la firma existe y, si se rechaza, el motivo.
4. Cierre documental y exportación de las transcripciones pendientes (interacciones 32 a 36). Opcionales: P-39 y P-40.
