# nostr-nip46-remote-signer

Python-based Nostr NIP-46 remote signer with Stacker News authentication, FastAPI, Docker and security controls.

## 1. Descripción y objetivo

Proyecto de prueba técnica para la Secretaría de Gobierno Digital del Ministerio de Hacienda de Chile.

**Objetivo final:** implementar un firmante remoto (*remote signer*) Nostr conforme a **NIP-46** y demostrar una **autenticación real con Stacker News**. La aplicación es **portable**: cada persona la clona, la instala y la ejecuta en su propio equipo (Windows, Linux o macOS, directamente o con Docker), con **su propia identidad Nostr y su propio firmante**; no es un servicio multiusuario ni se publica en Internet.

Stack previsto: Python 3.12, FastAPI, HTML/CSS/JavaScript, Docker Compose y pytest. Las reglas de trabajo y seguridad están en [`AGENTS.md`](AGENTS.md); el contexto y el registro de trazabilidad de IA, en [`docs/`](docs/).

## 2. Estado del proyecto

| Fase | Estado |
|---|---|
| 0.x (instrucciones, base FastAPI/Docker, investigación y diseño) | Completadas |
| 1.0A (laboratorio de interoperabilidad, sondas de relay, observación real de Stacker News) | **Cierre técnico aprobado con observaciones**: [`docs/phase-1.0A-closure.md`](docs/phase-1.0A-closure.md). Se observó interoperabilidad real de protocolo; **la autenticación completa con Stacker News sigue pendiente** |
| 1.0B, Bloques B0 y B1 (dependencias, configuración y **núcleo Nostr**) | **Completados** (ver §4 y `docs/decisions.md`) |
| 1.0B, Bloques B2 y B3 (**firmante NIP-46** y **API local con JWT**) | **Completados y verificados localmente** (pruebas automatizadas, regresión NDK 2.12.2 y P-33). **No** son validación con Stacker News |
| 1.0B, Bloque B5 (**interfaz web**: HTML, CSS y JS sin frameworks) | **Implementada y probada** con un navegador real (Playwright + Chrome) |
| 1.0B, Bloque B6 (**E2E local**: navegador + aplicación + relay local; y en Docker con NDK real) | **Completado en entorno local** (ver §9). La demostración **real** de B6 (repetir el inicio de sesión desde la interfaz) está pendiente de autorización |
| 1.0B, Bloque B4 (autenticación **real** con Stacker News) | **Ejecutado el 2026-11-21: PASS con observaciones.** Una firma `kind 27235` aprobada manualmente; Stacker News abrió una sesión asociada a la identidad de prueba (observación del propietario). Ver [`docs/phase-1.0B-B4-gate.md`](docs/phase-1.0B-B4-gate.md) y `docs/decisions.md` |

**Implementado en `app/`:** FastAPI con `GET /health`; configuración (`app/config.py`); el núcleo `app/nostr/` (claves, eventos NIP-01, NIP-44, NIP-04 entrante, mensajes NIP-46, URI `bunker://` y transporte WebSocket a un relay); los servicios `app/services/` (política de firma del evento de login `kind 27235`, conexiones, aprobaciones, auditoría y el firmante NIP-46); la autenticación del operador con **JWT** (`app/security/`); la **API local de control** (`/api/*`) y la **interfaz web** (`app/static/`). La firma exige una **aprobación humana explícita** por solicitud y solo se admite el evento de login de Stacker News. **No existen** persistencia de claves ni multiusuario. El laboratorio (`lab/`) es un arnés de validación **separado del producto**: `app/` nunca importa de él.

## 3. Requisitos del entorno

- Python 3.12.
- pip.
- Docker con Compose v2 (opcional; solo para ejecutar con contenedores). Probado con Docker 25.0.2 y Compose v2.24.3.
- Sistemas: probado en Windows 11 (Python 3.12.10) y en Linux amd64 (Python 3.12.16, contenedor). macOS: no se ha probado, pero el proyecto no depende del sistema.

## 4. Estructura de carpetas

```text
nostr-nip46-remote-signer/
├── app/
│   ├── main.py            # create_app(): crea FastAPI y registra routers
│   ├── config.py          # único punto de lectura de variables de entorno (relay, origen, tiempos, topes, hosts)
│   ├── api/               # capa HTTP (solo validación y delegación)
│   │   ├── health.py      # GET /health
│   │   ├── control.py     # API local de control /api/* (identidad, firmante, URI, solicitudes, auditoría)
│   │   ├── auth.py        # inicio y cierre de sesión del operador (JWT en cookie HttpOnly)
│   │   └── security.py    # guardia JWT, CSRF, validación de Host/Origin, CSP y cabeceras
│   ├── security/operator_auth.py  # JWT HS256: código de acceso, claims, revocación, límite de fallos (sin FastAPI)
│   ├── static/            # interfaz web: index.html, app.css, app.js (sin frameworks, sin innerHTML)
│   ├── schemas/           # modelos Pydantic estrictos (health, control)
│   ├── services/          # lógica de negocio: SIN FastAPI ni red
│   │   ├── policy.py      # 11 comprobaciones del evento de login kind 27235
│   │   ├── connections.py # secretos de un solo uso y estados de cliente
│   │   ├── approvals.py   # solicitudes pendientes y decisión del operador
│   │   ├── audit.py       # auditoría con lista blanca (sin secretos)
│   │   ├── signer.py      # SignerService: NIP-46 completo
│   │   └── runtime.py     # identidad en memoria y ciclo de vida del firmante
│   └── nostr/             # núcleo de protocolo: NO depende de FastAPI (E/S de red solo en relay.py)
│       ├── errors.py      # errores de dominio (mensajes genéricos, sin secretos)
│       ├── keys.py        # Keypair opaco, BIP-340, ECDH, importación hex/nsec (NIP-19)
│       ├── event.py       # eventos NIP-01: serialización canónica, id, firma, verificación
│       ├── nip44.py       # NIP-44 v2 (cifrar y descifrar)
│       ├── nip04.py       # NIP-04 SOLO para descifrar solicitudes entrantes
│       ├── nip46.py       # mensajes NIP-46 estrictos y URI bunker://
│       └── relay.py       # ÚNICO módulo con E/S de red: transporte WebSocket (TLS verificado)
├── tests/                 # espejo de app/; tests/e2e/ = navegador real; tests/nostr/fixtures/ = datos de interoperabilidad
├── lab/                   # laboratorio y arnés de regresión (NO es el producto)
├── docs/                  # decisiones, cierre de fases, propuestas y registro de IA
├── Dockerfile  compose.yaml  .dockerignore  .env.example
├── pyproject.toml  constraints.txt
└── AGENTS.md  CLAUDE.md  README.md
```

El código de protocolo no depende de FastAPI (ver `AGENTS.md` §4) y la E/S de red está confinada a `app/nostr/relay.py`; `tests/test_architecture.py` lo comprueba. La persistencia queda fuera de alcance: la clave vive solo en memoria (D-3).

## 5. Instalación local

Desde la raíz del repositorio. Los comandos `python -m …` son iguales en todos los sistemas una vez creado y activado el entorno virtual.

**Linux o macOS (bash/zsh):**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar las dependencias (con el entorno activado, en cualquier sistema):

```bash
python -m pip install -c constraints.txt -e ".[dev]"
```

`.venv/` está excluido de Git. Sin activar el entorno se puede invocar el intérprete directamente (`.venv/bin/python` en Linux/macOS, `.venv\Scripts\python.exe` en Windows).

## 6. Dependencias

Las directas están fijadas en [`pyproject.toml`](pyproject.toml) y **todas** (directas y transitivas) por versión exacta en [`constraints.txt`](constraints.txt), que pip aplica con `-c`; el Dockerfile usa el mismo archivo.

| Paquete | Versión | Tipo | Para qué |
|---|---|---|---|
| fastapi | 0.165.0 | ejecución | API HTTP |
| uvicorn | 0.54.0 | ejecución | servidor ASGI |
| coincurve | 21.0.0 | ejecución | BIP-340 (Schnorr) y ECDH sobre secp256k1 |
| cryptography | 50.0.2 | ejecución | ChaCha20 y HKDF (NIP-44), AES-CBC (NIP-04 entrante) |
| websockets | 17.4 | ejecución | cliente de relay (se usa desde el Bloque B2) |
| PyJWT | 2.15.1 | ejecución | JWT HS256 de la API local (D-8; MIT; sin dependencias propias con HS256) |
| cffi, pycparser | 2.1.1, 3.12 | transitivas | requeridas por `coincurve` y `cryptography` |
| pytest | 9.2.0 | desarrollo | pruebas |
| httpx | 0.28.1 | desarrollo | cliente de pruebas de FastAPI |
| playwright (+ greenlet, pyee) | 1.64.1 | desarrollo | pruebas E2E con navegador real (Apache-2.0); usa el Chrome/Edge instalado, no descarga navegadores |
| setuptools | 84.2.1 | construcción | solo al instalar el proyecto |

Las tres dependencias Nostr son las versiones **validadas en el laboratorio** de la Fase 1.0A (decisión D-1). Propósito, alternativas, licencia y mantenimiento: [`docs/nip46-implementation-plan.md`](docs/nip46-implementation-plan.md) §2.5.

### Qué es (y qué no es) `constraints.txt`

Fija **versiones exactas** para que local y Docker instalen lo mismo. **No incluye hashes**: no es un bloqueo verificable criptográficamente y no protege frente a un paquete alterado que conserve la misma versión. Tampoco fija `pip` ni (por defecto) la imagen base. `colorama` figura porque se instala en Windows; en Linux pip lo ignora, así que un único archivo sirve para ambos sistemas.

### Actualizar `constraints.txt`

Solo cuando cambien las dependencias directas de `pyproject.toml` o se quiera actualizar las transitivas. Requiere aprobación del propietario.

1. Crear un entorno temporal limpio **fuera del repositorio** e instalar **sin** restricciones. Linux/macOS: `python3.12 -m venv /tmp/lock-venv && /tmp/lock-venv/bin/python -m pip install ".[dev]"`. Windows: `py -3.12 -m venv $env:TEMP\lock-venv` y `& $env:TEMP\lock-venv\Scripts\python.exe -m pip install ".[dev]"`.
2. Obtener las versiones con `pip freeze --exclude nostr-nip46-remote-signer` en ese entorno y sustituir con ellas las líneas del archivo bajo la cabecera de comentarios. Para añadir solo paquetes nuevos conservando el resto, compare el resultado y añada únicamente lo nuevo (así se hizo en el Bloque B0: certifi se conservó).
3. Eliminar el entorno temporal.
4. Revisar el diff: solo dependencias del proyecto y de las pruebas.
5. Verificar en el entorno del proyecto: `python -m pip install -c constraints.txt -e ".[dev]"`, `python -m pip check` y `python -m pytest`.
6. Verificar en Linux: `docker compose build --no-cache`. La construcción **falla** si la imagen instala un paquete que no figure en `constraints.txt` con esa versión exacta.

## 7. Configuración

Solo por variables de entorno, leídas y validadas en un único módulo (`app/config.py`). Copie `.env.example` a `.env` (no se versiona) si quiere que Docker Compose las tome, o expórtelas en la terminal. **No hay secretos en el repositorio ni en la configuración por defecto.**

| Variable | Por defecto | Descripción |
|---|---|---|
| `APP_PORT` | `8000` | Puerto del **host** en el que Docker Compose publica la API (solo en `127.0.0.1`) |
| `RELAY_URL` | `wss://relay.primal.net` | Relay Nostr de referencia; obligatoriamente `wss://` |
| `RELAY_TLS_GROUPS` | (vacío) | Un único grupo TLS opcional (p. ej. `X25519`); la verificación del certificado y del nombre se mantiene siempre |
| `RELAY_ALLOW_INSECURE` | `0` | `1` admite `ws://` **solo** para un relay local de pruebas; nunca en una demostración real |
| `SERVICE_ORIGIN` | `https://stacker.news` | Valor EXACTO esperado de la etiqueta `u` del evento de login |
| `SIGNER_WINDOW_S` | `120` | Antigüedad máxima aceptada de `created_at` y de los eventos de transporte (1–300) |
| `SECRET_TTL_S` / `CONNECTION_TTL_S` / `SESSION_TTL_S` | `600` / `1800` / `3600` | Vida del secreto de la URI, de una conexión y de la sesión del firmante |
| `APPROVAL_TTL_S` | `120` | Segundos que una solicitud espera la decisión del operador (5–600); vencida = denegada |
| `MAX_SIGNATURES` / `MAX_REQUESTS` / `MAX_PENDING` | `1` / `60` / `16` | Firmas reales, solicitudes atendidas y solicitudes pendientes simultáneas por sesión |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,[::1]` | Cabeceras `Host` admitidas por la API (defensa frente a DNS rebinding) |
| `JWT_TTL_S` | `900` | Vida de la sesión JWT del operador en segundos (5–3600); al vencer hay que volver a iniciar sesión |
| `COOKIE_SECURE` | `0` | `1` marca la cookie de sesión como `Secure` (solo si se sirve por HTTPS; la aplicación local usa `http://127.0.0.1`) |

Un valor inválido hace fallar el arranque con un mensaje que nombra la variable, **nunca** su valor. **No existe** variable para el código de acceso, la clave de firma del JWT ni la clave Nostr: el **código de acceso** se genera aleatoriamente **al arrancar** y se muestra **una sola vez** en la terminal; la **clave de firma del JWT** es aleatoria y vive solo en memoria; la **clave privada Nostr** vive **solo en memoria** (decisión D-3). Con el `RELAY_URL` real, «Iniciar firmante» **abre una conexión real** a ese relay.

## 8. Ejecución de FastAPI

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

La aplicación queda en <http://127.0.0.1:8000> (interfaz web en `/`), solo accesible desde el propio equipo. Detener con `Ctrl+C` (la parada es ordenada y deja constancia de cierre en la auditoría). **No exponga la aplicación a Internet.**

Al arrancar, la terminal muestra **una sola vez** el **código de acceso** del operador de esa ejecución (`[operador] Codigo de acceso de ESTA ejecucion ...`). Cada ejecución genera uno nuevo; no se guarda ni existe ninguna credencial fija. Con Docker Compose el código queda en el registro del contenedor (`docker compose logs app`): trátelo como un secreto de la sesión.

### Operar con la interfaz web (lo habitual)

1. Abra <http://127.0.0.1:8000> e inicie sesión con el código de acceso. La sesión (JWT) dura 15 minutos por defecto y va en una cookie `HttpOnly` + `SameSite=Strict`; el navegador **no guarda nada** (ni `localStorage` ni claves).
2. **Identidad:** «Crear identidad temporal» o importar una clave propia (hex o `nsec`; el campo se vacía al enviarla y la clave no se vuelve a mostrar).
3. **Firmante:** «Iniciar firmante» (abre **una** conexión al relay configurado).
4. **Conexión:** «Emitir URI de un solo uso»; cópiela una vez (no se vuelve a consultar) y péguela en la aplicación cliente (p. ej. Stacker News).
5. **Solicitudes pendientes:** revise cada tarjeta y pulse **Aprobar** o **Rechazar**. En una firma debe ver las 11 comprobaciones en verde, el origen `u` esperado y el contenido de Stacker News. Las solicitudes que incumplen la política se deniegan solas y no se ofrecen; el botón «Aprobar» se desactiva si alguna comprobación falla.
6. **Auditoría** (sanitizada) y **cierre**: «Detener» deja `session_end`; «Cerrar sesión» revoca el JWT.

### Autenticación del operador (JWT, decisión D-8)

`POST /api/auth/login` (`{"code": "<código>"}`) canjea el código por un JWT HS256 firmado con una clave aleatoria que vive solo en memoria (cambia en cada arranque: reiniciar invalida todas las sesiones). Claims validados: `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, `jti` y `csrf`; algoritmo fijado, sin `none`; 8 sesiones como máximo; `POST /api/auth/logout` revoca el token en el servidor. Con cookie, las operaciones que cambian estado exigen `X-CSRF-Token` y un `Origin` local; con `Authorization: Bearer` no (el navegador no lo envía solo). Se limitan los intentos fallidos (429) y se rechazan las cabeceras `Host` ajenas. Sin cookie ni `Bearer` válidos, todo `/api/*` responde 401.

### Operar solo con la línea de comandos

| Método y ruta | Qué hace |
|---|---|
| `POST /api/auth/login` · `GET /api/auth/session` · `POST /api/auth/logout` | Inicio, consulta y cierre de sesión |
| `GET /api/status` | Estado de la identidad y del firmante (sin claves ni secretos) |
| `POST /api/identity` · `PUT /api/identity` · `GET /api/identity` | Crear una identidad temporal · importar una clave (`{"secret": "<hex o nsec>"}`) · consultar la clave pública. Cambiar solo con el firmante detenido |
| `POST /api/signer/start` · `POST /api/signer/stop` | Inicia (conexión al relay) o detiene el firmante; `stop` deja evidencia de cierre |
| `POST /api/connections` · `GET /api/connections` | Emite una URI `bunker://` de **un solo uso** (`Cache-Control: no-store`, se ve una vez) · lista los clientes (id truncado y estado) |
| `GET /api/requests?scope=pending`, `recent` o `all` | Solicitudes de decisión (`connect`, `sign_event`) con resumen y comprobaciones |
| `POST /api/requests/{id}/approve` y `/deny` | Decisión humana sobre **una** solicitud; una aprobación = una firma de un reto |
| `GET /api/audit?limit=100` | Auditoría sanitizada |

Ejemplo en PowerShell 7 (segunda terminal; ajuste el puerto si no es 8000):

```powershell
$B = "http://127.0.0.1:8000"
$code = Read-Host "Codigo de acceso" -MaskInput
$H = @{ Authorization = "Bearer " + (Invoke-RestMethod -Method Post -Uri "$B/api/auth/login" -ContentType application/json -Body (@{code=$code} | ConvertTo-Json)).token }
Invoke-RestMethod -Method Post -Uri "$B/api/identity" -Headers $H            # clave pública de la identidad nueva
Invoke-RestMethod -Method Post -Uri "$B/api/signer/start" -Headers $H        # abre la conexión al relay configurado
(Invoke-RestMethod -Method Post -Uri "$B/api/connections" -Headers $H).uri   # URI bunker:// de un solo uso (no la copie a archivos ni chats)
Invoke-RestMethod -Uri "$B/api/requests" -Headers $H                          # qué se pide, con sus comprobaciones
Invoke-RestMethod -Method Post -Uri "$B/api/requests/<id>/approve" -Headers $H   # o /deny
Invoke-RestMethod -Method Post -Uri "$B/api/signer/stop" -Headers $H
Invoke-RestMethod -Uri "$B/api/audit" -Headers $H
```

Equivalente con `curl` (Linux, macOS, Git Bash): `TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' -d "{\"code\":\"$CODE\"}" http://127.0.0.1:8000/api/auth/login | python -c 'import sys,json;print(json.load(sys.stdin)["token"])')` y después `curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/connections`.

**Efecto externo:** «Iniciar firmante» con el `RELAY_URL` por defecto se conecta a un relay público real. Para ensayar sin red externa use un relay local (`RELAY_URL=ws://127.0.0.1:<puerto>` con `RELAY_ALLOW_INSECURE=1`), las pruebas E2E (§9) o el arnés de `lab/`.

## 9. Ejecución de pytest

```bash
python -m pytest -v
```

No requieren Docker, Internet ni servicios externos. Son pruebas automatizadas: **no demuestran** interoperabilidad con Stacker News.

- **Vectores oficiales de NIP-44** (válidos e inválidos): no se versionan porque la licencia de su repositorio de origen no está aclarada. Las pruebas los leen de `NIP44_VECTORS_PATH` o de `lab/vendor/vectors/nip44.vectors.json`, verifican su SHA-256 y, si el archivo no existe, **se omiten con un aviso visible**. Se obtienen con las herramientas del laboratorio (`lab/tools/fetch_artifacts.py`, requiere red).
- **BIP-340:** el **CSV oficial completo** (19 vectores, positivos y negativos) está incluido como fixture, con su origen, fecha y SHA-256 en `tests/nostr/fixtures/README.md`; las pruebas ejecutan todos los vectores sin omitir ninguno.
- Los datos de interoperabilidad con `nostr-tools` (la biblioteca que usa Stacker News) están en `tests/nostr/fixtures/` y se generan con `lab/tools/gen_core_fixtures.mjs`.

### Pruebas E2E con navegador real (B6, solo entorno local)

Operan la **interfaz** con un navegador real (Playwright; usa Chrome o Edge instalados) contra la aplicación completa (Uvicorn) y un relay local en memoria; un cliente de prueba hace de «Stacker News». Identidades ficticias y sin Internet. Se ejecutan junto con el resto (`python -m pytest`); se omiten solos si no hay navegador. Para ejecutar solo las E2E o excluirlas:

```bash
python -m pytest -m e2e          # solo E2E de navegador
python -m pytest -m "not e2e"    # todo menos las E2E
```

Cubren: inicio de sesión y atributos de la cookie, ausencia de almacenamiento en el navegador, CSRF, cierre de sesión (revocación), caducidad del JWT, importación de clave sin eco, el flujo completo (identidad → firmante → URI una vez → `connect` aprobado → `get_public_key` → solicitudes inválidas rechazadas sin llegar al operador → `sign_event` aprobado y verificado → rechazo → auditoría sin secretos → parada con `session_end`) y el reinicio.

**E2E en Docker con el cliente NDK 2.12.2 real** (navegador → contenedor del producto → relay del laboratorio ← NDK real; sin servicios externos). Requiere las imágenes del laboratorio (`lab/README.md`) y la del producto:

```powershell
$env:E2E_DOCKER = "1"; python -m pytest tests/e2e/test_docker_ndk.py -v
```

Además, `python lab/run_product_regression.py` (servicio) y `python lab/run_product_regression.py --api` (aplicación completa por HTTP, P-33) ejecutan E1, E2, E3 y E8 con NDK 2.12.2 en red Docker `internal`.

**Qué NO demuestran:** nada de lo anterior es una autenticación con Stacker News. Es validación **local**; la **real** está pendiente de la autorización de B4.

## 10. Ejecución mediante Docker Compose

```bash
docker compose up --build -d
```

Dentro del contenedor la aplicación escucha en `0.0.0.0:8000` (necesario para que Docker pueda reenviar el tráfico), pero el puerto **se publica en el host solo en `127.0.0.1`**: no queda accesible desde la red local ni desde Internet. Para cambiar el puerto del host: `APP_PORT=8080 docker compose up --build -d` (Linux/macOS) o `$env:APP_PORT=8080; docker compose up --build -d` (PowerShell). Estado y healthcheck: `docker compose ps`.

Tras `docker compose up`, abra <http://127.0.0.1:8000> y use el código de acceso de `docker compose logs app`. `compose.yaml` pasa al contenedor las variables del firmante (`RELAY_URL`, `RELAY_TLS_GROUPS`, `SERVICE_ORIGIN`, `APPROVAL_TTL_S`, `MAX_SIGNATURES`, `SESSION_TTL_S`, `ALLOWED_HOSTS`, `JWT_TTL_S`).

**Imagen base.** Por defecto `python:3.12-slim` (etiqueta mutable). Para un bloqueo verificable antes de las pruebas reales hay un digest del índice multiarquitectura (amd64 y arm64) verificado en el laboratorio: `PYTHON_IMAGE=python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b docker compose build` (decisión D-6; no activado por defecto). Con ese digest se verificó el Bloque B0.

## 11. Consulta de `/health`

```bash
curl http://127.0.0.1:8000/health
```

(PowerShell: `Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing`.) Respuesta esperada: HTTP 200, `Content-Type: application/json`, cuerpo `{"status":"ok"}`. El endpoint solo indica que el proceso responde; no consulta Stacker News ni relays.

## 12. Detención de contenedores

```bash
docker compose down
```

Solo afecta a los recursos de este proyecto. La imagen (`nostr-nip46-remote-signer:dev`) permanece; se borra con `docker image rm nostr-nip46-remote-signer:dev`.

## 13. Limitaciones actuales

- **Autenticación real con Stacker News: una sola ejecución (B4, 2026-11-21, PASS con observaciones).** Fue observada por el propietario (sin captura ni comprobación de persistencia al recargar). La demostración real de B6 y cualquier repetición requieren nueva autorización. El resto de las validaciones (B2, B3, B5, B6 local) son entorno local.
- Sin persistencia de claves (D-3), sin multiusuario y sin base de datos; el JWT dura 15 minutos y reiniciar la aplicación cierra todas las sesiones. La cookie no es `Secure` por defecto porque la aplicación local usa `http://127.0.0.1`.
- Una sola conexión al relay por sesión, sin reconexión automática; un relay que exija `AUTH` (NIP-42) detiene la sesión.
- NIP-44: texto plano limitado a 65535 bytes (restricción provisional P-14); sin prefijo extendido.
- Las versiones están fijadas en `constraints.txt`, pero **sin *hashes***: no hay verificación criptográfica de los paquetes (alternativa B no aprobada).
- La imagen base por defecto usa una etiqueta mutable (digest preparado, ver §10).
- `/docs`, `/redoc` y `/openapi.json` de FastAPI están **deshabilitados** (la interfaz tiene una CSP estricta).
- `pytest` muestra un aviso: Starlette marca `httpx` como obsoleto para su cliente de pruebas. Se mantiene `httpx` por ahora.
- No hay configuración de `mypy`/`ruff` en el proyecto; la comprobación de tipos estricta del Bloque B1 se ejecutó con herramientas externas temporales (ver `docs/decisions.md`).

## 14. Documentación

- Cierre de la Fase 1.0A y propuesta de la Fase 1.0B: [`docs/phase-1.0A-closure.md`](docs/phase-1.0A-closure.md), [`docs/phase-1.0B-proposal.md`](docs/phase-1.0B-proposal.md), resumen sanitizado de la evidencia: [`docs/phase-1.0A-evidence-summary.md`](docs/phase-1.0A-evidence-summary.md).
- Demostración real de B4 (resultado PASS con observaciones) y su compuerta: [`docs/phase-1.0B-B4-gate.md`](docs/phase-1.0B-B4-gate.md); evidencia sanitizada en [`docs/evidence/`](docs/evidence/).
- **Continuidad (leer primero para retomar):** [`docs/handoff-2026-11-21.md`](docs/handoff-2026-11-21.md).
- Decisiones y registro de IA: [`docs/decisions.md`](docs/decisions.md), [`docs/ai-log.md`](docs/ai-log.md).
- Investigación y diseño (Fase 0.3), todo **propuestas** salvo lo que `docs/decisions.md` marque como aprobado:
  - [Análisis del protocolo NIP-46](docs/nip46-protocol-analysis.md)
  - [Compatibilidad con Stacker News](docs/stacker-news-compatibility.md)
  - [Diseño de seguridad](docs/nip46-security-design.md)
  - [Plan de implementación y prueba real](docs/nip46-implementation-plan.md)
- Laboratorio: [`lab/README.md`](lab/README.md) y [`docs/nip46-lab-report.md`](docs/nip46-lab-report.md).
