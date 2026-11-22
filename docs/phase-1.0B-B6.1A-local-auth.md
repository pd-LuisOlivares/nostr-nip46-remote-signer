# B6.1A: ingreso del administrador con usuario y contraseña (SQLite + Argon2id + JWT) y correcciones P-35, P-36 y P-37

**Fecha:** 2026-11-21 · **Base:** `4b9e51eba698c3434f4fee3b0f6a5224e60e504b` (más los cambios de documentación locales de B6 etapa 1, conservados) · **Veredicto: PASS con observaciones** · Sin commit ni push.

> **Actualización B6.1B (2026-11-21):** el hallazgo **P-38** de este informe se corrigió en [`phase-1.0B-B6.1B-security-closure.md`](phase-1.0B-B6.1B-security-closure.md) (revalidación síncrona antes de firmar) y P-41 se verificó allí. Las cifras de pruebas de este informe son anteriores.

Sustituye **solo** el mecanismo de ingreso (el código de acceso de la terminal) por usuario y contraseña guardados en SQLite. No se tocó NIP-46, la criptografía Nostr, la política de firma ni el formato del JWT. Todo es validación **local**: no hubo conexión a Stacker News ni a relays públicos, no se firmó ningún evento real y no se usó la identidad de B4.

## 1. Diagnóstico de la autenticación anterior (D-8)

- Al arrancar, la aplicación generaba un **código de acceso** aleatorio, lo imprimía una vez en la terminal y el operador debía **copiarlo** a un formulario para canjearlo por un JWT. En Docker había que extraerlo de `docker compose logs`.
- Defectos (B6 etapa 1): el código dependía de la terminal (mala experiencia y riesgo de dejarlo en registros); **P-35**: cada petición sin credenciales (la sonda normal `GET /api/auth/session`, o una pestaña antigua) contaba como fallo y, tras 10 por minuto, bloqueaba **también** el inicio de sesión (429); el cuerpo de la respuesta de login entregaba el JWT al JavaScript de la página, que lo descartaba pero lo recibía.
- Lo que era correcto y se conservó: JWT HS256 de clave aleatoria en memoria, claims estrictos, revocación, cookie `HttpOnly`/`SameSite=Strict`, CSRF y `Origin`, `Host` restringido, CSP.

## 2. Estado previo de SQLite y del registro

- **SQLite:** no existía ninguna infraestructura (una prueba de arquitectura prohibía `sqlite3` en `app/`). Se creó una sola capa, `app/storage/`.
- **Registro:** no existía registro con `logging` en el producto. Solo existían la **auditoría NIP-46** en memoria (`app/services/audit.py`, visible en la interfaz) y los registros de IA en `docs/`. No se reconstruyó ni reemplazó la auditoría NIP-46.

## 3. Arquitectura implementada (decisión D-9)

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Persistencia | `app/storage/database.py` | Única apertura de SQLite: crea directorio, archivo (0600 donde se admite) y esquema (`PRAGMA user_version`); una conexión por operación; `BEGIN IMMEDIATE` para escrituras; errores genéricos (`StorageError`) sin rutas |
| | `app/storage/admins.py` | Todo el SQL, parametrizado. `create_if_none` es **una sola sentencia atómica** (`INSERT … WHERE NOT EXISTS`): arranques simultáneos no crean dos administradores |
| | `app/storage/secret_file.py` | Lectura de la contraseña inicial desde archivo (`ADMIN_PASSWORD_FILE`), acotada a 1 KiB |
| Seguridad | `app/security/passwords.py` | Política de contraseña y hash/verificación **Argon2id** (`argon2-cffi`, perfil RFC 9106 «low memory»: t=3, m=64 MiB, p=4, sal aleatoria de 16 bytes); hash de señuelo para igualar el costo con usuarios inexistentes |
| | `app/security/operator_auth.py` | Emisión/verificación/revocación del JWT (sin `access_code`) y dos limitadores de fallos independientes |
| Dominio | `app/services/admin_accounts.py` | `prepare` (inicializa SQLite y crea el administrador inicial) y `authenticate`; sin FastAPI |
| HTTP | `app/api/auth.py`, `app/api/security.py`, `app/schemas/control.py` | Login con usuario y contraseña, logout, guardia JWT |
| Arranque | `app/main.py`, `app/config.py`, `app/logging_config.py` | Todo el arranque ocurre en el `lifespan` (importar no toca el disco); configuración única; registro operacional |
| Interfaz | `app/static/index.html`, `app/static/app.js` | Formulario usuario/contraseña, estado de carga, mensajes seguros; defensa P-37 |

**Esquema (`admins`):** `id` (fijo en 1: un único administrador), `username` único sin distinguir mayúsculas (3 a 64 caracteres), `password_hash` (`CHECK` que exige el prefijo `$argon2id$` y ≤ 512 caracteres: **la base misma rechaza texto plano**), `is_active`, `created_at`, `updated_at`, `last_login_at`.

**Se guarda en SQLite:** la cuenta del administrador (usuario y hash). **No se guarda:** contraseña, claves privadas Nostr, secretos bunker, JWT, cookies ni la clave de firma del JWT (una prueba comprueba que la base no tiene columnas de esos tipos).

## 4. Migración del login

| Antes (D-8) | Ahora (D-9) |
|---|---|
| `{"code": "<código de la terminal>"}` | `{"username": "...", "password": "...", "return_token": false}` |
| Respuesta con `token` en el cuerpo | El cuerpo **no** trae el JWT (solo `csrf_token` y `expires_in_s`); el token va solo en la cookie `HttpOnly`. `"return_token": true` lo incluye para clientes de línea de comandos |
| Código impreso en la terminal | Ningún secreto en la terminal |
| Campo «Código de acceso» | Campos «Usuario» y «Contraseña», botón «Iniciar sesión», Enter, estado «Verificando…», `aria-busy`, mensajes `role="alert"` |

Se actualizaron las pruebas antiguas (no se eliminó ninguna para conseguir PASS): `test_auth.py` se reescribió con los mismos escenarios (cookie, CSRF, revocación, tokens vencidos, `none`, reinicio, `Host`/`Origin`) y se amplió; `test_operator_auth.py` conserva todos los casos de JWT (claims, algoritmo, caducidad, revocación, tope de sesiones).

## 5. Inicialización del administrador

1. Arranque (`lifespan`): se crea el directorio y el archivo si faltan, y el esquema.
2. Si ya hay administrador: se conserva **sin cambios** (no se sobrescribe ni se recrea) y la contraseña de entorno **ni siquiera se lee**.
3. Si no hay: se toma `ADMIN_PASSWORD` o, si no, `ADMIN_PASSWORD_FILE` (excluyentes), se valida (12 a 128 caracteres; sin reglas de composición; rechaza caracteres de control, igual al usuario y casi un único carácter repetido), se calcula Argon2id y se inserta de forma atómica.
4. Sin contraseña inicial válida: **el arranque falla** con instrucciones (`[arranque] No existe un administrador y falta una contraseña inicial válida. Defina ADMIN_PASSWORD (o ADMIN_PASSWORD_FILE …) …`) y no se crea ninguna cuenta. No hay contraseña por defecto en el código, la imagen, `compose.yaml` ni `.env.example` (la variable está vacía y comentada).
5. Cómo pasar la contraseña sin historial ni archivos versionados, y qué hacer si se pierde: README §8 («Primer arranque», «Si se pierde la contraseña»). Recuperación: detener, borrar la base (o `docker compose down -v`) y repetir el primer arranque; la base solo contiene la cuenta.

## 6. Generación y gestión del JWT

El backend verifica las credenciales (Argon2id contra SQLite) y **solo entonces** `OperatorAuth.issue()` genera el JWT HS256 (mismos claims, TTL 900 s por defecto, `jti` activos, revocación en logout, máximo 8 sesiones). La clave de firma son 48 bytes aleatorios generados al arrancar, solo en memoria, **independientes de la contraseña** (una prueba lo comprueba). La interfaz nunca recibe ni copia el token: queda en la cookie `HttpOnly`; `document.cookie` está vacío y no hay `localStorage` ni `sessionStorage`. CSRF, `Origin` y `Host` sin cambios.

## 7. Correcciones P-35, P-36 y P-37

**P-35 (bloqueo por solicitudes sin credenciales): corregido.**
- Dos contadores globales independientes (no dependen de `X-Forwarded-For` ni de otra cabecera; hay una prueba que los varía): *intentos de login* (5 fallidos o en curso por 5 minutos → 429 con `Retry-After`, también con la contraseña correcta; un éxito no consume cupo; los intentos concurrentes cuentan: 30 simultáneos no obtienen más de 5 verificaciones) y *tokens inválidos* (más de 20 por minuto → 429; un token válido nunca se frena).
- Una petición **sin credenciales** responde 401 y no cuenta como fallo de nada. Los tokens inválidos no bloquean el inicio de sesión (ventanas distintas).
- Mismos mensajes para usuario inexistente y contraseña incorrecta (401 `credenciales invalidas`), con el mismo costo de cálculo.
- Pruebas: `tests/api/test_auth.py` (60 sondeos anónimos y 25 tokens inválidos seguidos de un login correcto; ráfaga concurrente; cambio de usuario y de cabeceras; expiración de la ventana), `tests/security/test_operator_auth.py`, y el E2E de navegador (25 recargas + 30 sondeos y luego login).

**P-36 (archivos sensibles): corregido en `.gitignore`.** Ignora archivos de identidad (`identity.key`, `*.key`, `*.pem`, `*.nsec`, `.nip46-b4/`), secretos locales (`secrets/`, `*.secret`, `admin_password*`), SQLite y auxiliares (`/data/`, `*.db`, `*.db-journal`, `*.db-wal`, `*.db-shm`, `*.sqlite*`), configuración privada (`.env.*` salvo `.env.example`) y evidencias sensibles o temporales (`/evidence-private/`, `/evidence-raw/`, `*.har`, `*.pcap*`, `*.tmp`, `/tmp/`). `.dockerignore` excluye lo mismo de la imagen. **Verificación:** `git ls-files -ci --exclude-standard` → **vacío** (ningún archivo rastreado queda ignorado); `git ls-files -o --exclude-standard` lista todos los archivos nuevos de código, pruebas y documentación (ninguno necesario desaparece); 27 rutas candidatas comprobadas con `git check-ignore` (las sensibles ignoradas; `.env.example`, `lab/tools/b4_identity.py`, `docs/evidence/*`, `tests/nostr/fixtures/*` y `app/storage/*` visibles). Ver también la verificación en copia limpia (§10).

**P-37 (aprobaciones bloqueadas por política): corregido en la interfaz; hallazgo abierto en el backend (P-38).**
- *Interfaz:* `decide()` se niega a aprobar si la tarjeta tiene alguna comprobación en `false` o si la interfaz no la conoce; muestra «Esta solicitud incumple la política y no puede aprobarse.» y **no envía ninguna petición**. El botón sigue desactivado. Pruebas E2E (Chrome) con tarjetas manipuladas servidas con `page.route`: clic real, Enter y **clic sintético** no envían `POST /approve`; las tarjetas con 11 comprobaciones en verde y `connect` sí se aprueban; HTML hostil se muestra como texto. **Comprobación de mutación:** con la guardia desactivada temporalmente la prueba falla (el POST se enviaba); restaurada, pasa.
- *Backend, lo que sí está confirmado y probado:* la política (11 comprobaciones) se evalúa **antes** de crear la solicitud; una firma que la incumple **nunca llega a la cola del operador**, no se puede aprobar por la API (404/409), no se firma y no hay `sign_ok` en la auditoría (`test_a_policy_violating_request_never_exists_so_it_cannot_be_approved_through_the_api`). Al firmar se revalidan además repetición del reto y tope de firmas, se consume la aprobación de forma atómica y se autoverifica la firma.
- ***Hallazgo P-38 (no se corrigió: afecta al flujo de firma):*** tras la aprobación humana **no se revalida la ventana temporal** (`created_at`) de la política. Con `APPROVAL_TTL_S` mayor que `SIGNER_WINDOW_S` (o simplemente aprobando tarde), se firma una plantilla ya más antigua que la ventana. Demostrado con una prueba `xfail` estricta (`test_approval_given_after_the_policy_window_elapsed_must_not_sign`); si alguien lo corrige, el `xfail` estricto avisa. Impacto práctico acotado: el operador aprobó viendo la antigüedad real y el servicio de destino aplica su propia ventana; pero es la «revalidación antes de firmar» que se pidió confirmar. Propuesta: volver a ejecutar `evaluate()` justo antes de `_sign_once` y denegar si falla (más estricto, no amplía permisos; puede denegar aprobaciones lentas). **Se detuvo antes de implementarlo**, por la instrucción de este alcance; requiere su decisión.

## 8. Archivos

**Creados:** `app/storage/{__init__,database,admins,secret_file}.py`, `app/security/passwords.py`, `app/services/admin_accounts.py`, `app/logging_config.py`, `tests/storage/{__init__,test_database}.py`, `tests/security/test_passwords.py`, `tests/services/test_admin_accounts.py`, `tests/api/test_startup.py`, `tests/e2e/{test_browser_login,test_docker_persistence}.py`, este documento.

**Modificados:** `app/{config,main}.py`, `app/api/{auth,security}.py`, `app/schemas/control.py`, `app/security/operator_auth.py`, `app/static/{index.html,app.js}`, `Dockerfile`, `compose.yaml`, `.dockerignore`, `.gitignore`, `.env.example`, `pyproject.toml`, `constraints.txt`, `lab/{run_product_regression.py,product/auth_driver.py,product/compose.yaml,e2e/compose.yaml}`, `tests/{support,test_architecture,test_config,test_health}.py`, `tests/api/{test_auth,test_control_api}.py`, `tests/security/test_operator_auth.py`, `tests/services/test_signer.py`, `tests/e2e/{conftest,test_browser_flow,test_docker_ndk}.py`, `README.md`, `docs/{decisions,ai-log,handoff-2026-11-21,project-context}.md`. `AGENTS.md` y `CLAUDE.md` **no** se modificaron.

**Dependencia nueva (autorizada en el alcance):** `argon2-cffi==25.1.0` y su binding `argon2-cffi-bindings==26.2.0` (instaladas desde PyPI; fijadas en `pyproject.toml` y `constraints.txt`). Propósito: Argon2id exigido por el alcance. Alternativa en la biblioteca estándar: `hashlib.scrypt` (también memoria-dura), descartada porque se pidió Argon2id. Licencia: MIT (ambas). Seguridad: envuelve la implementación de referencia en C mediante `cffi` (ya presente). Mantenimiento: son las versiones vigentes que PyPI sirvió hoy; no se verificó más allá de eso.

## 9. Registro operacional

Logger `nip46.auth` (stderr): `admin_bootstrap` (`created`/`exists`), `login_ok` (prefijo de 8 caracteres del `jti`), `login_failed`, `login_blocked` (segundos de espera), `logout`, `login_error` (almacenamiento) y `startup_failed` (tipo de error). Nunca contraseñas, hashes, usuarios escritos, tokens ni cookies (pruebas unitarias, de API, de navegador y de Docker lo comprueban con `caplog` y con los registros reales del proceso y del contenedor).

## 10. Pruebas ejecutadas (comandos y resultados reales)

Entorno: Windows 11, Python 3.12.10, SQLite 3.49.1, Docker 25.0.2 (Docker Desktop), Chrome 158 con Playwright 1.64.1.

| Comando | Resultado |
|---|---|
| `python -m pytest -q -rs -rx` con `E2E_DOCKER=1` (equipo de desarrollo, con los vectores NIP-44) | **762 passed, 1 skipped, 1 xfailed** (105 s). El omitido: prueba de permisos POSIX (no aplica en Windows). El `xfail`: P-38 |
| `python -m pytest -q -rs` sin `E2E_DOCKER` | 759 passed, 4 skipped, 1 xfailed (69 s) |
| **Copia limpia** (exportación de los archivos rastreados y nuevos no ignorados a una carpeta vacía; venv nuevo; `pip install -c constraints.txt -e ".[dev]"`; `pytest -q -rs`) | pip sin errores, `pip check` limpio, argon2-cffi 25.1.0 y bindings 26.2.0; **751 passed, 12 skipped, 1 xfailed** (71 s). Omitidas: 8 vectores NIP-44 (archivo no versionado), 3 de Docker (`E2E_DOCKER`), 1 POSIX. No se creó `data/` ni ninguna base |
| `mypy --strict app` (herramienta temporal, no es dependencia) | `Success: no issues found in 35 source files` |
| `python -m pip check` | `No broken requirements found.` |
| Cobertura de líneas y ramas sobre `app/` (`coverage` temporal; pruebas no E2E, 740 passed, 1 skipped, 1 xfailed) | **99 % total** (1932 sentencias, 12 sin cubrir, todas en módulos anteriores: `control.py`, `relay.py`, `audit.py`…). **Módulos nuevos o reescritos de B6.1A: 100 %** de líneas y ramas (`storage/*`, `security/passwords.py`, `security/operator_auth.py`, `services/admin_accounts.py`, `api/auth.py`, `api/security.py`, `main.py`, `config.py`, `logging_config.py`) |
| E2E de navegador (Chrome): `tests/e2e` | 19 aprobadas (7 anteriores adaptadas + 12 nuevas: login, P-35, persistencia, arranque abortado, P-37) |
| `E2E_DOCKER=1 pytest tests/e2e/test_docker_persistence.py tests/e2e/test_docker_ndk.py` | 3 passed |
| `python lab/run_product_regression.py` y `--api` (NDK 2.12.2 real, red interna) | **E1, E2, E3 y E8: PASS en ambos modos** (regresión NIP-46: sin cambios de comportamiento) |
| `git diff --check` | limpio (ver informe final) |

**Pruebas obligatorias del alcance (cobertura):** (1) SQLite desde cero: `test_database.py`, `test_admin_accounts.py`, E2E Docker; (2) administrador inicial; (3) contraseña ausente o inválida: `test_admin_accounts.py`, `test_startup.py`, E2E de navegador y de Docker (arranque abortado); (4) reinicio con administrador existente: `test_admin_accounts.py`, `test_startup.py`, E2E de navegador y Docker; (5) persistencia tras reinicio de Docker: `test_docker_persistence.py` (`restart`, `down` sin `-v` y recreación sin contraseña inicial, y que otra contraseña de entorno no sobrescribe); (6) contraseña correcta e incorrecta; (7) Argon2id y ausencia de texto plano (en la base y en el archivo en bruto, también dentro del contenedor); (8) usuario inexistente; (9) fuerza bruta (incluida la ráfaga concurrente); (10) sondeos anónimos sin bloqueo; (11) JWT automático; (12) cookies, CSRF y revocación; (13) logout; (14) P-37; (15) regresión NIP-46 (suite del firmante + arnés con NDK real); (16) E2E de navegador del login; (17) copia limpia: se verificó con una exportación del árbol de trabajo (no con un `git clone` literal, porque los cambios aún no están en un commit).

## 11. Reproducibilidad y Docker

- `compose.yaml`: volumen con nombre `app_data` en `/data` (único directorio escribible), `DATABASE_PATH=/data/nip46.db`, `ADMIN_USERNAME`/`ADMIN_PASSWORD` desde el entorno; raíz de solo lectura, `cap_drop: ALL` y `no-new-privileges` se conservan. `Dockerfile`: `/data` creado vacío para `uid 10001` (modo 700) y `VOLUME`; la imagen **no contiene credenciales** (comprobado con `docker image inspect`).
- **Verificado en Docker:** el administrador persiste tras `restart`, `down` y recreación; una contraseña distinta en el entorno no sobrescribe la guardada; el archivo de la base pertenece a `uid 10001` con modo `0600`; solo `/data` es escribible; sin contraseña inicial el contenedor se detiene con instrucciones.
- **Observación B6.1 sobre nombres fijos:** corrección **mínima y segura**: la etiqueta de la imagen es ahora `${APP_IMAGE:-nostr-nip46-remote-signer:dev}` (por defecto no cambia nada) y el comentario de `compose.yaml` documenta que `-p`/`COMPOSE_PROJECT_NAME` tienen prioridad sobre `name:`; así una segunda copia tiene proyecto, imagen **y volumen** propios. No se renombró el proyecto por defecto (lo usan el README, el laboratorio y las pruebas); cambiarlo sería un cambio mayor: queda como pendiente opcional.
- Rutas: `DATABASE_PATH` relativa por defecto (`data/nip46.db`), sin rutas absolutas del equipo.
- **No se asume** compatibilidad con plataformas no probadas: el flujo se ejecutó en Windows 11 + Docker Desktop (contenedores Linux amd64) y Chrome. Linux/macOS sin Docker, Firefox y arm64 no se probaron; en Windows el modo 0600 de la base no se aplica (hereda las ACL de la carpeta).

## 12. Riesgos y limitaciones

- **P-38** (arriba): la ventana temporal no se revalida al firmar. Mitigación documentada: `APPROVAL_TTL_S` ≤ `SIGNER_WINDOW_S`.
- **P-40:** el límite de login es global: un tercero con acceso a la red local (el puerto solo se publica en `127.0.0.1`) podría bloquear el ingreso 5 minutos con intentos erróneos. Es el compromiso de no depender de datos que el cliente controla; una alternativa por origen real exigiría un proxy de confianza.
- Con `ADMIN_PASSWORD` en el entorno del contenedor, la contraseña inicial es visible con `docker inspect` mientras esa variable exista: por eso se recomienda quitarla y recrear el contenedor tras el primer arranque (o usar `ADMIN_PASSWORD_FILE` en ejecuciones locales).
- **P-39:** no hay cambio de contraseña ni recuperación guiada; se recupera borrando la base.
- **P-41:** Argon2id usa 64 MiB por verificación (perfil RFC 9106 «low memory»): no se probó en equipos con poca memoria ni se implementó el re-hash al subir parámetros.
- Sin *hashes* en `constraints.txt` (sigue igual); `mypy` y `ruff` siguen fuera del proyecto.
- Los E2E de navegador solo cubren Chrome (Firefox sigue pendiente dentro de P-34).
- Un administrador (id fijo): ampliarlo a varios exige una migración y una decisión nueva.

## 13. Estado de Git

Sin commit, sin push y sin tocar el historial. Los cambios de documentación de B6 etapa 1 se conservaron y se trabajó sobre ellos. Ver el informe final para la salida de `git status` y `git diff --check`.

## 14. Veredicto: **PASS con observaciones**

Se cumplen los criterios de aceptación: el administrador ingresa con usuario y contraseña; SQLite conserva solo el hash Argon2id y persiste tras reiniciar (también en Docker); el JWT lo emite el backend; el panel y las protecciones de sesión no cambian; P-35 y P-36 están corregidos y probados; P-37 está corregido y probado en la interfaz y el backend se confirmó parcialmente; la copia limpia se instala y pasa; no hay regresiones NIP-46 (regresión con NDK real en PASS); no se usaron servicios de autenticación Nostr externos ni hubo commit o push.

**Observaciones (lo que queda pendiente):** (1) **P-38**: el backend no revalida la ventana temporal tras la aprobación; se documentó con una prueba `xfail` estricta y se detuvo antes de cambiar el flujo de firma; (2) la verificación «desde un clon limpio» se hizo con una exportación del árbol de trabajo porque no hay commit; debe repetirse con un `git clone` real tras publicar; (3) sin `--no-cache` ni digest de la imagen base; (4) transcripciones de las interacciones 32, 33 y 34 pendientes de exportar.

## 15. Pasos concretos para B6.2

1. **Decisión suya** sobre P-38 (recomendado: revalidar la política justo antes de firmar y alinear `APPROVAL_TTL_S` ≤ `SIGNER_WINDOW_S`), y sobre P-39, P-40 y P-41.
2. **Revisión y, si lo autoriza, commit y push** de B6.1A (y de la etapa 1 de B6, aún sin publicar), revisando antes con `git diff --cached` los secretos.
3. **Verificación con un `git clone` real** del commit publicado (instalación con el README, suite, `docker compose up --build -d` con `ADMIN_PASSWORD` por entrada oculta, y el flujo de ingreso por la interfaz), más `docker compose build --no-cache`.
4. **Compuerta operativa de B6 real** (requiere su autorización expresa, con alcance): repetir el inicio de sesión en Stacker News desde la interfaz **con el nuevo ingreso**, con la misma identidad de B4 importada por la interfaz, comprobando la **persistencia de la sesión al recargar** y, si lo autoriza, una captura redactada; mismas restricciones (una firma, aprobación humana, ventana ≤ 15 min, sin reintentos). Cierre documental y exportación de las transcripciones pendientes.
