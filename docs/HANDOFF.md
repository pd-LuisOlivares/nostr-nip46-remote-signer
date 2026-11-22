# HANDOFF — estado al cierre de la jornada del 2026-11-22

Para retomar el proyecto en una sesión nueva. Reemplaza en la práctica a [`handoff-2026-11-21.md`](handoff-2026-11-21.md), que describe el estado anterior (supervisado, B6.1D). **Este archivo no contiene credenciales ni secretos**; las referencias a contraseñas y claves son solo a *dónde* están.

## 1. Estado actual del proyecto

- **Producto:** firmante remoto Nostr **NIP-46** (Python 3.12, FastAPI, SQLite, Docker Compose, pytest), **implementado y probado**. Modo por defecto `SIGNER_MODE=continuous`: sin ventana obligatoria, reconexión automática al relay, límites de frecuencia (30/min por conexión y 120/min globales), revocación individual de conexiones y **aprobación humana individual de cada `connect` y cada `sign_event`** (sin firma automática ni aprobaciones persistentes). El modo `supervised` (B6.2) se conserva intacto.
- **Perfil de evaluación (D-18):** `deploy/demo.env` (credenciales de demostración **públicas a propósito**, solo uso local) y README con «Inicio rápido para evaluadores».
- **Repositorio:** hasta el 2026-11-22 `HEAD = 4b9e51e` (época de B4) y casi todo el producto estaba sin commit (47 modificados y 60 sin rastrear). El propietario **autorizó** un único commit de consolidación (`chore: consolidate NIP-46 signer after successful Stacker News validation`) y su push a `origin/main` (sin force push). **El SHA y el resultado del push constan en `git log` y en la entrada 51 de `docs/ai-log.md`**: comprobarlos antes de asumir que está publicado.
- **Fase:** 1.0B. Quedan la evidencia del PASS, la prueba de clon limpio y las decisiones del §9; el commit de consolidación se autorizó (ver arriba).

## 2. Validación real con Stacker News

| Validación | Fecha | Versión | Resultado |
|---|---|---|---|
| B4 | 2026-11-21 | supervisada, una firma | **PASS con observaciones** (observado por el propietario) |
| Paso 7 | 2026-11-22 | **definitiva, modo continuo**, imagen `d17-continuous`, perfil `deploy/continuous.env`, `http://127.0.0.1:8001` | **PASS, confirmado personalmente por el propietario**: «la prueba real con Stacker News fue exitosa» y el firmante «permitió completar la autenticación real desde la interfaz web» |

**Lo que NO está verificado ni documentado** (el PASS es una declaración del propietario; el agente no participó en la prueba): instante de inicio y fin, clave pública usada, número de firmas, aprobaciones individuales de `connect` y `sign_event`, cumplimiento de las condiciones de la autorización (identidad B4, una sola firma, 15 minutos) y la auditoría sanitizada. **No hay evidencia exportada.** Está registrado en `docs/ai-log.md` (entrada 50) con esas salvedades; **no inventar detalles**.

**Estado del firmante al cerrar: no verificado.** Una comprobación de solo lectura mostró **1 conexión TCP saliente establecida** en el contenedor, así que probablemente **sigue iniciado**. Pulsar **Detener** en la interfaz si no se necesita.

## 3. Imagen Docker y entorno utilizado

| Elemento | Valor |
|---|---|
| Contenedor B6.2 | `nostr-nip46-remote-signer-app-1`, proyecto `nostr-nip46-remote-signer`, sano, sin reinicios, arrancó 2026-11-22 04:47 UTC |
| Imagen en uso | `nostr-nip46-remote-signer:d17-continuous` (`1ad4127f8ab3…`), construida con la base fijada por digest |
| Imagen de recuperación | `nostr-nip46-remote-signer:manual-b61d` (`aebce8324156…`), **no sobrescrita** |
| Otra imagen | `nostr-nip46-remote-signer:dev` (`19ae52ac159e…`) |
| Etiqueta del perfil demo | `nostr-nip46-remote-signer:evaluation`: **todavía no construida** en esta máquina (el perfil se validó con la imagen `d17-continuous`) |
| Perfil | `deploy/continuous.env` (puerto 8001, modo continuo, relay `wss://relay.primal.net`, `RELAY_TLS_GROUPS=X25519`, origen `https://stacker.news`) |
| Volumen | `nostr-nip46-remote-signer_app_data` (SQLite) |
| Recuperar B6.2 anterior | `APP_IMAGE=nostr-nip46-remote-signer:manual-b61d docker compose --env-file deploy/b62.env -p nostr-nip46-remote-signer up -d --no-build --pull never app` |
| Hardening | `read_only`, `cap_drop ALL`, `no-new-privileges`, uid 10001, solo `127.0.0.1` |

La identidad Nostr **no persiste**: tras reiniciar o recrear el contenedor hay que importarla de nuevo desde la interfaz.

## 4. Resultados de las últimas pruebas (previas a la prueba real; no se ejecutó nada nuevo después)

| Prueba | Resultado |
|---|---|
| `python -m pytest` completo (con navegador real) | **1037 passed, 27 skipped, 0 failed** (26 de Docker sin `E2E_DOCKER` y 1 de permisos POSIX) |
| `python -m pytest -m "not e2e"` | **1010 passed, 1 skipped** |
| `tests/test_deploy_profile.py` | 24 passed (incluye el perfil demo y su coherencia con el README) |
| `tests/test_ai_traceability.py` | 54 passed |
| E2E Docker con `d17-continuous` (`E2E_DOCKER=1`) | 3 passed: modo continuo con relay local efímero, perfil supervisado y cliente NDK real |
| Perfil demo en contenedor efímero (sin volumen) | login 200 con las credenciales del perfil, 401 con otra contraseña u otro usuario; sin conexiones salientes |
| `git diff --check` | limpio |
| Cobertura y tipos | `coverage`, `mypy`, `pyright` y `ruff` **no están instalados** (no se instalaron) |

Son pruebas **automatizadas y locales**; la validación real es la del §2.

## 5. Arquitectura actual y dudas sobre los puertos 8000 y 8001

Capas (`app/`): `api` (HTTP, sin lógica), `services` (política `kind 27235`, conexiones con ids opacos y revocación, aprobaciones, auditoría con lista blanca, firmante, `runtime` con supervisor de reconexión, `session_state`, `ratelimit`, `admin_accounts`), `nostr` (protocolo, sin FastAPI; E/S solo en `relay.py`), `storage` (único SQL, parametrizado), `security` (JWT, Argon2id, compuerta de verificaciones), `config` (único punto de lectura del entorno) y `static` (HTML/CSS/JS sin frameworks). Un único proceso (no usar `--workers`). `lab/` es un arnés separado: `app/` nunca lo importa.

**Puertos (duda abierta):**
- **8001** = entorno B6.2/validación real (`deploy/continuous.env` y `deploy/b62.env`, proyecto `nostr-nip46-remote-signer`).
- **8000** = valor por defecto de `compose.yaml` y del **perfil de evaluación** `deploy/demo.env` (proyecto `nip46-evaluacion`, volumen propio `nip46-evaluacion_app_data`).
- Los dos entornos pueden coexistir porque usan proyectos, volúmenes y puertos distintos, pero **no está decidido cuál es el entorno canónico del producto final**: el README documenta el 8000 para el evaluador y la validación real se hizo en el 8001. Decidir si el entregable queda con una sola instancia y un solo puerto, y qué se hace con el contenedor B6.2 una vez cerrada la evidencia. También: el README cita en algunos ejemplos `127.0.0.1:8000` genérico; revisar coherencia tras la decisión.

## 6. Persistencia de usuarios (SQLite)

- Un **único administrador** por base (D-9): tabla `admins` con hash **Argon2id**, estado y fechas. No hay multiusuario ni recuperación de contraseña en la aplicación.
- **No se guardan** contraseñas en claro, claves Nostr, secretos `bunker://`, JWT ni cookies.
- B6.2: usuario `b62-admin` en el volumen `nostr-nip46-remote-signer_app_data`. **El 2026-11-22 se restableció su contraseña** (solo el hash y `updated_at`) con autorización expresa; respaldo previo en `%USERPROFILE%\.nip46-b62-backups\2026-11-22_antes-de-restablecer-contrasena\` (fuera del repositorio; SHA-256 de la base original, prefijo `766db8ae`). La contraseña nueva se mostró en el chat y **no se registró en ningún archivo**; la conoce el propietario.
- Demostración: usuario y contraseña públicos en `deploy/demo.env` (D-18); solo se aplican al crear el administrador en un volumen **nuevo**.
- Identidad de B4: archivo privado `%USERPROFILE%\.nip46-b4\identity.key` (fuera del repositorio; **mantener respaldo propio**; ningún agente debe leerlo).

## 7. Archivos modificados y sin rastrear (para el futuro commit)

Conteo antes de la consolidación: **47 modificados** y **60 sin rastrear** (incluye las transcripciones de `docs/ai-sessions/`); se incorporaron al commit de consolidación tras revisar su contenido (escaneo de secretos sin hallazgos reales). `git diff --check` limpio. Ningún archivo sensible quedó sin ignorar (`.env`, `*.db` y claves están en `.gitignore`).

- **Sin rastrear que hay que incorporar:** `app/` (`logging_config.py`, `security/passwords.py`, `security/verification_gate.py`, `services/admin_accounts.py`, `services/ratelimit.py`, `services/session_state.py`, `storage/`), `deploy/` (`b62.env`, `continuous.env`, `demo.env`, `import_admin_db.py`), `docs/` (fases B6.x, `evidence/`, `HANDOFF.md`, `ai-sessions/`), `lab/manual/`, `tests/` (nuevos de storage, revocación, reconexión, límites, estado de sesión, perfiles, E2E de login, reconexión, Docker y cliente web) y `tools/` (`ai_sessions.py` y su manifiesto).
- **Modificados:** raíz (`.dockerignore`, `.env.example`, `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `Dockerfile`, `README.md`, `compose.yaml`, `constraints.txt`, `pyproject.toml`), `app/` (16 archivos), `docs/` (`ai-log.md`, `decisions.md`, `handoff-2026-11-21.md`, `project-context.md`), `lab/` (4) y `tests/` (13).
- **Revisar antes de commitear:** `deploy/demo.env` contiene una credencial **pública a propósito** (el escáner de `tools/ai_sessions.py scan` lo marca; es esperado). Las transcripciones 48 a 50 están **parciales** y se reexportan al cerrar la sesión.

## 8. Riesgos de seguridad pendientes

1. **Publicación del producto:** hasta la consolidación el repositorio no contenía el producto actual. **Verificar** que el commit y el push se completaron (§1) y hacer la prueba de clon limpio.
2. **Contraseña de `b62-admin` compartida en el chat:** está en el historial local de la sesión (JSONL, fuera del repositorio) y en cualquier respaldo privado de esos historiales. Las transcripciones del repositorio se redactan. **Recomendado: cambiarla después de cerrar la jornada** y no volver a usar esa.
3. **Credencial de demostración pública** (`deploy/demo.env`, D-18): excepción acotada a D-9 y a la regla de `AGENTS.md` §7; documentada, pero conviene que el propietario confirme que acepta publicarla.
4. **P-47** (volver a emparejar con la misma clave de cliente tras revocar o caducar): **no implementada**; hoy hay que usar una clave de cliente nueva. **P-48** (límite propio para remitentes no autorizados): **no implementada**; un remitente desconocido puede agotar el límite global de 120/min. **P-49** (contador de intentos en el panel): **parcial**. Ninguna cuenta con aprobación expresa.
5. **Supuestos no verificados (D-17):** que Stacker News reutilice su clave de cliente en inicios posteriores, que el reloj de Docker coincida con el de Windows y que el flujo descrito en el README siga vigente.
6. **Cadena de suministro:** `constraints.txt` fija versiones **sin hashes**; la imagen base por defecto usa una etiqueta mutable (digest disponible, D-6).
7. **Sin cobertura ni análisis estático** (herramientas no instaladas); sin medición de cobertura.
8. **Auditoría de la prueba real sin capturar:** vive en memoria y **se pierde si se reinicia o recrea el contenedor** (§10, paso 1).
9. **Límite global de intentos de inicio de sesión:** 5 fallos por 5 minutos bloquean el ingreso (P-40); la sesión de la interfaz caduca a los 15 minutos (1 hora en el perfil demo).
10. **Relay público:** disponibilidad y TLS dependen de `relay.primal.net` (se usa `RELAY_TLS_GROUPS=X25519`).

## 9. Tareas restantes hasta la publicación

1. Capturar y archivar la **evidencia sanitizada** de la validación real (auditoría, hora de inicio y fin, clave pública truncada a 8 caracteres, número de firmas y observación de la sesión) en `docs/evidence/`, **solo con lo que el propietario aporte**.
2. `README.md` (§2 y §13) y `docs/ai-log.md` ya registran el PASS (declaración del propietario, sin evidencia técnica); **falta** `docs/decisions.md` (D-17.11 y el estado de B6.2) y `docs/phase-1.0B-B6.2-plan.md`.
3. Detener el firmante si sigue activo y **cambiar la contraseña de `b62-admin`**.
4. Decidir el entorno canónico y los puertos 8000/8001 (§5).
5. Confirmar que el commit de consolidación está en `origin/main` (`git fetch` y `git log origin/main -1`); en adelante, cada commit exige autorización explícita.
6. **Prueba de clon limpio:** clonar en una carpeta nueva, `docker compose --env-file deploy/demo.env -p nip46-evaluacion up --build -d`, entrar con las credenciales del README, importar o crear una identidad y recorrer el flujo **sin** relays reales salvo autorización; comprobar `python -m pytest` y los 8 vectores NIP-44 omitidos si faltan `lab/vendor/`.
7. Sustituir el marcador `<URL-del-repositorio>` del README por la URL real.
8. Decidir P-47, P-48 y P-49.
9. Cierre de trazabilidad: reexportar las transcripciones al cerrar la sesión, `python tools/ai_sessions.py check` y `scan`, respaldo privado de historiales.
10. **Autorizar la publicación** y hacer push (no antes).

## 10. Orden recomendado para la siguiente sesión

1. Leer este archivo, `docs/ai-log.md` (entradas 47 a 50) y `docs/decisions.md` (D-17 y D-18). Comprobar `git status`, `docker ps` y `docker images`.
2. **Antes de cualquier reinicio del contenedor:** si la auditoría de la prueba real interesa, que el propietario la copie desde la interfaz (sección Auditoría) y la sanitice; luego detener el firmante.
3. Completar el registro del PASS en decisiones y plan B6.2 (§9, puntos 1 y 2; README y `ai-log` ya lo tienen).
4. Cambiar la contraseña de `b62-admin` y confirmar el respaldo de la identidad B4.
5. Ejecutar `python -m pytest` completo y `git diff --check`; reexportar transcripciones y `python tools/ai_sessions.py check`.
6. Con autorización: prueba de clon limpio, correcciones, decisión sobre P-47/48/49 y puertos.
7. Con autorización: publicación.

**Reglas que siguen vigentes** (`AGENTS.md`/`CLAUDE.md`): sin commit, push ni merge sin autorización explícita; no leer `.env`, claves ni contraseñas; no usar relays ni Stacker News sin una autorización con alcance definido; no borrar volúmenes (`down -v`) ni sobrescribir imágenes; distinguir pruebas automatizadas, validación local y validación real.
