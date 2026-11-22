# nostr-nip46-remote-signer

Firmante remoto (*remote signer*) Nostr conforme a **NIP-46**, en Python (FastAPI, SQLite, Docker Compose), para iniciar sesión en Stacker News con una identidad Nostr sin entregarle la clave privada.

## Inicio rápido para evaluadores

Todo se hace desde el navegador. Tras el comando de arranque no hace falta PowerShell, ningún script ni un asistente de IA.

### 1. Requisitos previos

- **Docker con Compose v2** (probado con Docker 25.0.2 y Compose v2.24.3) y **conexión a Internet**: el primer arranque construye la imagen (descarga la imagen base y los paquetes de Python) y, más tarde, el firmante se conecta al relay público y usted a Stacker News.
- Un navegador. Para Stacker News se recomienda una **ventana privada** y una **identidad Nostr de prueba**, nunca una clave personal.
- El puerto `8000` libre en su equipo (si no lo está, cambie `APP_PORT` en `deploy/demo.env`).

### 2. Clonar el repositorio

```bash
git clone https://github.com/pd-LuisOlivares/nostr-nip46-remote-signer.git
cd nostr-nip46-remote-signer
```

### 3. Levantar la aplicación

Este único comando funciona igual en PowerShell, bash y zsh, desde la raíz del repositorio:

```bash
docker compose --env-file deploy/demo.env -p nip46-evaluacion up --build -d
```

La primera vez tarda unos minutos. Cuando `docker compose -p nip46-evaluacion ps` muestre el servicio como `healthy`, ya puede usarla. El comando crea un proyecto Docker propio (`nip46-evaluacion`) con su contenedor, su red y su volumen; no afecta a ningún otro proyecto. Arrancar **no abre ninguna conexión externa**: el relay solo se contacta cuando usted pulsa «Iniciar firmante».

### 4. URL de acceso

<http://127.0.0.1:8000> (solo accesible desde su propio equipo).

### 5. Usuario y contraseña de demostración

| Usuario | Contraseña |
|---|---|
| `evaluador` | `demo-nip46-zuentkew6ahznf94` |

> **Credenciales públicas y solo para evaluación local.** Son exclusivas de este proyecto de demostración (no son personales ni de otro servicio) y están a la vista en [`deploy/demo.env`](deploy/demo.env).
> - **No las use en producción.** Para cualquier otro despliegue defina una contraseña propia (§8, «Primer arranque»).
> - **No exponga el puerto a otras máquinas ni a Internet con estas credenciales.** Compose lo publica solo en `127.0.0.1`; no lo cambie.
> - El repositorio **no contiene claves privadas Nostr ni secretos reales**.

### 6. Generar o importar una identidad Nostr

En el panel, sección **Identidad**: pulse **Crear identidad temporal** (recomendado) o pegue una clave de prueba propia (hex o `nsec`) en «Importar una clave propia» y pulse **Importar**. La interfaz muestra solo la clave **pública**.

> **La clave privada vive solo en memoria** (la del contenedor). No se guarda en SQLite ni en ningún archivo, nunca se muestra y no vuelve a salir. **Tras reiniciar o recrear el contenedor, o detenerlo y volver a arrancarlo, debe generar o importar la identidad de nuevo.** Una identidad nueva tiene otra clave pública y Stacker News la tratará como otra cuenta; para conservar la misma cuenta, importe siempre la misma clave de prueba.

### 7. Iniciar el firmante

Pulse **Iniciar firmante**. Pasa a **Listo** tras conectarse al relay `wss://relay.primal.net` (un efecto externo real). No hay ventana de tiempo obligatoria: el firmante sigue activo hasta que usted pulse **Detener**, y si el relay se corta, **se reconecta solo** (esperas de 2, 5, 10, 20 y 40 s; el estado muestra «Reconectando»; tras 5 fallos seguidos pasa a «Fallido» y hay que iniciarlo de nuevo).

### 8. Obtener la URI `bunker://`

En **Conexión bunker://** pulse **Emitir URI de un solo uso** y luego **Copiar**. La URI se muestra una sola vez, sirve para **un** emparejamiento y caduca a los 5 minutos. Es un secreto: no la pegue en chats ni en archivos.

### 9. Iniciar sesión con Nostr en Stacker News

1. En una ventana privada, abra <https://stacker.news/signup> (o <https://stacker.news/login?type=nostr>) y elija **Continue with Nostr**.
2. Elija el inicio con **firmante remoto** (*bunker*) y pegue la URI.

(Es el recorrido observado en la validación real B4; la interfaz de Stacker News puede cambiar. No necesita billetera Lightning ni hacer pagos.)

### 10. Aprobar el `connect`

En **Solicitudes pendientes** aparece una tarjeta «Conexión de un cliente». Revísela y pulse **Aprobar** (o **Rechazar**). Cada nueva conexión exige su propia aprobación; la solicitud caduca a los 5 minutos.

### 11. Aprobar el `sign_event`

Aparece la tarjeta «Firma del evento de inicio de sesión». Antes de aprobar compruebe que las **11 comprobaciones están en verde**, que el origen `u` es `https://stacker.news`, que el contenido es «Stacker News Authentication» y que el evento es de hace unos segundos; pulse **Aprobar**. Si algo no coincide, **Rechazar**. Cada firma exige su propia aprobación: **no hay firmas automáticas ni aprobaciones que se conserven**. Debe aprobar pronto: pasados 120 s desde la creación del evento, la política lo descarta y ya no firma.

### 12. Verificar la autenticación

Stacker News debe mostrar una sesión iniciada (menú de usuario). En el panel, **Recientes** debe mostrar la solicitud como aprobada y firmada, y **Auditoría** el evento `sign_ok` y el recuento de firmas. «Firmada» significa que la firma se produjo y se autoverificó; la sesión efectiva la confirma Stacker News.

### 13. Revocar conexiones y detener el firmante

- **Revocar** (en **Conexiones**) revoca esa conexión y cancela sus solicitudes pendientes; las demás siguen activas.
- **Detener** cierra el firmante de forma ordenada y revoca todas las conexiones.
- **Cerrar sesión** termina la sesión de la interfaz (dura 1 hora en este perfil).

### Detener y restablecer la demostración

- `docker compose -p nip46-evaluacion stop` detiene el contenedor y `docker compose -p nip46-evaluacion start` lo reanuda (se conserva el administrador; la identidad Nostr hay que crearla o importarla de nuevo). `docker compose -p nip46-evaluacion down` elimina el contenedor y la red **conservando** el volumen; para volver a levantarla repita el comando del paso 3.
- **Restablecer desde cero (destruye datos).** Solo si necesita empezar de nuevo: `docker compose --env-file deploy/demo.env -p nip46-evaluacion down -v` **borra el volumen `nip46-evaluacion_app_data`** (la cuenta de administrador de esta demostración) y el contenedor y la red de ese proyecto. No afecta a ningún otro proyecto ni volumen de Docker. No es un paso rutinario.
- Si cambia la contraseña de `deploy/demo.env` en un volumen que ya existe, **se ignora**: la contraseña solo se aplica al crear el administrador.

### Si algo no funciona

- *Inicio de sesión bloqueado:* 5 intentos fallidos bloquean el ingreso 5 minutos.
- *El firmante queda en «Fallido»:* el relay no respondió o rechazó la conexión; consulte `docker compose -p nip46-evaluacion logs app` (los registros no contienen secretos) y vuelva a pulsar **Iniciar firmante**.
- *La URI caducó o se usó:* emita otra.

### Requisitos para un evaluador sin archivos del desarrollador

Un clon limpio contiene todo lo necesario para levantar y usar el producto: **no** hace falta un `.env`, ni la identidad de pruebas de B4, ni la carpeta `data/`, ni imágenes de laboratorio. Solo se necesita:

| Para | Necesita |
|---|---|
| Levantar y usar la aplicación (pasos 1 a 13) | Docker con Compose v2, Internet (construir la imagen y, al iniciar el firmante, alcanzar el relay) y un navegador. **Nada más** |
| Ejecutar las pruebas en local (§5 y §9) | Python 3.12 y `pip`; para las E2E de navegador, Chrome o Edge instalado (si no hay, se omiten solas) |

**Qué no trae un clon** (no se versiona a propósito): los **vectores oficiales de NIP-44** (`lab/vendor/`, licencia sin aclarar; sus **8 pruebas se omiten con aviso**, ver §9), las **imágenes de laboratorio** `nip46-lab-py:1.0a` y `nip46-lab-node:1.0a` (solo las necesitan las pruebas de Docker con `E2E_DOCKER=1`, que se omiten sin ellas) y la base de datos de otros entornos.

**Verificado en un clon limpio (2026-11-22, desde GitHub, en un directorio temporal):** `pip install -c constraints.txt -e ".[dev]"` y `pip check` sin errores; `python -m pytest` → **1029 passed, 35 skipped, 0 failed** (26 de Docker, 8 vectores NIP-44 y 1 de permisos POSIX); `docker compose --env-file deploy/demo.env up --build -d` con **proyecto, puerto (18090) y etiqueta de imagen exclusivos de la prueba**, con una segunda construcción **sin caché**: contenedor `healthy`, inicio de sesión con las credenciales de este README (200; contraseña incorrecta, 401), identidad temporal creada sin exponer la clave privada, modo `continuous`, cabeceras de seguridad y `Host` ajeno rechazado. **No se inició el firmante ni se contactó con relays ni con Stacker News**: el flujo completo con Stacker News (pasos 7 a 12) no forma parte de esa verificación. Informe: [`docs/NIGHTLY-REVIEW.md`](docs/NIGHTLY-REVIEW.md).

## 1. Descripción y objetivo

Proyecto de prueba técnica para la Secretaría de Gobierno Digital del Ministerio de Hacienda de Chile.

**Objetivo:** un firmante remoto Nostr conforme a **NIP-46** y una **autenticación real con Stacker News**. La aplicación es **portable**: cada persona la clona y la ejecuta en su propio equipo (Windows, Linux o macOS, con Docker o directamente), con **su propia identidad Nostr y su propio firmante**; no es un servicio multiusuario ni se publica en Internet.

Stack: Python 3.12, FastAPI, HTML/CSS/JavaScript sin frameworks, SQLite, Docker Compose y pytest. Las reglas de trabajo y seguridad están en [`AGENTS.md`](AGENTS.md); el contexto, las decisiones y el registro de trazabilidad de IA, en [`docs/`](docs/).

## 2. Estado del proyecto

El producto está **implementado y probado de forma automatizada y local**. Se distinguen tres tipos de validación:

| Tipo | Estado |
|---|---|
| **Pruebas automatizadas** (pytest, sin red; ver §9) | Pasan. Incluyen el núcleo Nostr con vectores oficiales (NIP-44, BIP-340), el firmante, la API con JWT, la interfaz con navegador real y la regresión con el cliente **NDK 2.12.2** (el de Stacker News) |
| **Validación manual local** (Docker, relay local, cliente web de laboratorio) | Realizada; el modo continuo, la reconexión, los límites y la revocación se validaron en contenedor sin servicios externos |
| **Validación real con Stacker News** | **B4 (2026-11-21): PASS con observaciones** — una firma `kind 27235` aprobada a mano; Stacker News abrió una sesión (observación del propietario; [`docs/phase-1.0B-B4-gate.md`](docs/phase-1.0B-B4-gate.md)). **Segunda ejecución, con la versión final en modo continuo (2026-11-22): PASS confirmado personalmente por el propietario** (la autenticación real se completó desde la interfaz web). El detalle técnico (auditoría, horas, número de firmas) **no se capturó como evidencia**; cualquier repetición requiere autorización expresa |

Una prueba automatizada que pasa **no demuestra** interoperabilidad: solo cuenta la autenticación real contra Stacker News. El historial de fases y de decisiones está en [`docs/`](docs/) (§14).

**Modos del firmante (`SIGNER_MODE`).** `continuous` (**por defecto**): disponible mientras el operador no lo detenga, sin parada por duración de sesión, con reconexión automática al relay y límites de frecuencia (30 solicitudes/min por conexión y 120/min en total); **cada `connect` y cada `sign_event` exigen aprobación humana individual**, sin firma automática. `supervised`: el modo de validación de B6.2 (una firma, sesión limitada), que se activa con `deploy/b62.env`.

**Implementado en `app/`:** FastAPI con `GET /health`; configuración (`app/config.py`); el núcleo `app/nostr/` (claves, eventos NIP-01, NIP-44, NIP-04 entrante, mensajes NIP-46, URI `bunker://` y transporte WebSocket a un relay); los servicios `app/services/` (política de firma del evento de login `kind 27235`, conexiones con revocación individual, aprobaciones, auditoría, límites de frecuencia, estado de sesión conservado entre reconexiones y el firmante NIP-46 con su supervisor de reconexión); la **cuenta del administrador local** (SQLite en `app/storage/`; contraseña con Argon2id en `app/security/passwords.py`) y su sesión con **JWT** (`app/security/`); la **API local de control** (`/api/*`) y la **interfaz web** (`app/static/`). Cada `connect` y cada firma exigen una **aprobación humana explícita** y solo se admite el evento de login de Stacker News (`kind 27235`); no hay firma automática ni aprobaciones persistentes. **No existen** persistencia de claves Nostr ni multiusuario (SQLite guarda solo la cuenta del administrador). El laboratorio (`lab/`) es un arnés de validación **separado del producto**: `app/` nunca importa de él.

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
│   │   ├── auth.py        # inicio (usuario y contraseña) y cierre de sesión del administrador (JWT en cookie HttpOnly)
│   │   └── security.py    # guardia JWT, CSRF, validación de Host/Origin, CSP y cabeceras
│   ├── security/          # sin FastAPI
│   │   ├── operator_auth.py  # JWT HS256: emisión, claims, revocación y límites de fallos (intentos de login / tokens inválidos)
│   │   └── passwords.py      # política de contraseña y hash/verificación Argon2id
│   ├── storage/           # ÚNICO lugar con SQLite y SQL (consultas parametrizadas): database.py, admins.py, secret_file.py
│   ├── logging_config.py  # registro operacional mínimo de la autenticación (logger `nip46.auth`)
│   ├── static/            # interfaz web: index.html, app.css, app.js (sin frameworks, sin innerHTML)
│   ├── schemas/           # modelos Pydantic estrictos (health, control)
│   ├── services/          # lógica de negocio: SIN FastAPI ni red
│   │   ├── policy.py      # 11 comprobaciones del evento de login kind 27235
│   │   ├── connections.py # secretos de un solo uso y estados de cliente
│   │   ├── approvals.py   # solicitudes pendientes y decisión del operador
│   │   ├── audit.py       # auditoría con lista blanca (sin secretos)
│   │   ├── signer.py      # SignerService: NIP-46 completo
│   │   ├── runtime.py     # identidad en memoria, ciclo de vida y reconexión automática del firmante
│   │   ├── session_state.py # estado que se conserva entre reconexiones (clave de transporte, conexiones, anti-replay)
│   │   ├── ratelimit.py   # límites de frecuencia de ventana móvil (global y por conexión)
│   │   └── admin_accounts.py # primer arranque del administrador y autenticación (sin FastAPI)
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
├── deploy/                # perfiles de Docker Compose (demo.env = evaluación; continuous.env, b62.env = validación) y herramienta de importación de la base
├── Dockerfile  compose.yaml  .dockerignore  .env.example
├── pyproject.toml  constraints.txt
└── AGENTS.md  CLAUDE.md  README.md
```

El código de protocolo no depende de FastAPI (ver `AGENTS.md` §4) y la E/S de red está confinada a `app/nostr/relay.py`; `tests/test_architecture.py` lo comprueba. La única persistencia es la cuenta del administrador en SQLite (D-9); la clave Nostr vive solo en memoria (D-3).

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
| argon2-cffi (+ argon2-cffi-bindings) | 25.1.0 (+ 26.2.0) | ejecución | hash Argon2id de la contraseña del administrador (D-9; MIT; la implementación de referencia en C; usa `cffi`, ya presente) |
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
| `SIGNER_MODE` | `continuous` | `continuous` (por defecto): firmante disponible hasta que el operador lo detenga, con reconexión y límites de frecuencia; `supervised`: modo de validación de B6.2 (topes totales de sesión) |
| `SECRET_TTL_S` / `CONNECTION_TTL_S` / `SESSION_TTL_S` | continuo `300` / `28800` / (no se aplica); supervisado `600` / `1800` / `3600` | Vida del secreto de la URI, de una conexión (al caducar hay que emparejar de nuevo) y de la sesión del firmante (solo supervisado) |
| `REQUESTS_PER_MIN` | `30` | Solo modo continuo: solicitudes por minuto **por conexión** (1–120). Además hay un límite **global** fijo de 120/min, aplicado antes de verificar la firma o descifrar. Al superarlos el mensaje se descarta sin detener el firmante ni revocar conexiones |
| `APPROVAL_TTL_S` | continuo `300` / supervisado `120` | Segundos que una solicitud espera la decisión del operador (5–600); vencida = denegada |
| `MAX_SIGNATURES` / `MAX_REQUESTS` | `1` / `60` | **Solo modo supervisado**: topes totales de firmas y de solicitudes por sesión. En continuo no se aplican (los sustituyen los límites de frecuencia y la aprobación humana de cada firma) |
| `MAX_PENDING` | `16` | Solicitudes pendientes simultáneas |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,[::1]` | Cabeceras `Host` admitidas por la API (defensa frente a DNS rebinding) |
| `JWT_TTL_S` | `900` | Vida de la sesión JWT del operador en segundos (5–3600); al vencer hay que volver a iniciar sesión |
| `COOKIE_SECURE` | `0` | `1` marca la cookie de sesión como `Secure` (solo si se sirve por HTTPS; la aplicación local usa `http://127.0.0.1`) |
| `DATABASE_PATH` | `data/nip46.db` | Archivo SQLite del administrador (relativo al directorio de trabajo; en Docker Compose es `/data/nip46.db`, un volumen). Se crea solo |
| `ADMIN_USERNAME` | `admin` | Usuario del administrador **inicial** (3–64 caracteres: letras, números, `.`, `-`, `_`). No es secreto. Solo se usa si la base no tiene administrador |
| `ADMIN_PASSWORD` | (ninguna) | Contraseña **inicial** (12–128 caracteres). **Sin valor por defecto.** Solo el primer arranque; después se ignora (ni siquiera se lee) |
| `ADMIN_PASSWORD_FILE` | (vacío) | Alternativa a `ADMIN_PASSWORD`: ruta de un archivo de texto con la contraseña inicial (excluyentes). No se lee si ya hay administrador |
| `APP_IMAGE` | `nostr-nip46-remote-signer:dev` | Solo Docker Compose: etiqueta de la imagen local (útil para una segunda copia del repositorio) |

En Docker Compose, todas las variables de arriba (salvo `RELAY_ALLOW_INSECURE`, `ADMIN_PASSWORD_FILE` y `DATABASE_PATH`) llegan al contenedor. Los perfiles de `deploy/` (§10) agrupan valores: `demo.env` para evaluación (contraseña pública, solo local), `continuous.env` y `b62.env` para la validación real.

Un valor inválido hace fallar el arranque con un mensaje que nombra la variable, **nunca** su valor. **Ya no existe** el código de acceso de la terminal (D-9). **No existe** variable para la clave de firma del JWT ni la clave Nostr: la **clave de firma del JWT** la genera el servidor al azar en cada arranque y vive solo en memoria (nunca se deriva de la contraseña); la **clave privada Nostr** vive **solo en memoria** (decisión D-3). `ADMIN_PASSWORD` y `ADMIN_PASSWORD_FILE` no aparecen en `repr` ni en los errores. Con el `RELAY_URL` real, «Iniciar firmante» **abre una conexión real** a ese relay.

## 8. Ejecución de FastAPI

### Primer arranque: crear el administrador local

La aplicación **ya no muestra un código de acceso** en la terminal: se ingresa con **usuario y contraseña** guardados en SQLite (solo su hash Argon2id). En una instalación nueva el administrador se crea **una sola vez**, en el primer arranque, con una contraseña inicial que usted aporta. **El código no tiene ninguna contraseña por defecto** ni hay pantalla pública de registro. La única excepción es el perfil de **evaluación** `deploy/demo.env` (ver «Inicio rápido» y D-18): trae una contraseña pública, solo para uso local, y se activa únicamente si usted lo selecciona con `--env-file`. Para cualquier otro uso, siga los pasos de abajo con una contraseña propia.

1. Elija una contraseña de 12 a 128 caracteres (sin reglas de composición; no puede ser igual al usuario ni casi un único carácter repetido) y, si quiere, un usuario (`ADMIN_USERNAME`, por defecto `admin`).
2. Pásela a la aplicación **sin escribirla en la línea de comandos** (el historial de la terminal la guardaría) ni en archivos versionados:
   - PowerShell 7: `$env:ADMIN_PASSWORD = Read-Host "Contraseña inicial" -MaskInput`
   - bash o zsh: `read -rs ADMIN_PASSWORD; export ADMIN_PASSWORD`
   - Docker Compose toma las variables del entorno de la terminal (lo anterior sirve) o de un `.env` local (no se versiona): edítelo con un editor de texto, no con `echo`.
   - Alternativa para una ejecución local: `ADMIN_PASSWORD_FILE=<ruta>` con un archivo de texto que contenga solo la contraseña. Manténgalo fuera del repositorio o en `secrets/` (excluido de Git) y con permisos solo para su usuario.
3. Arranque la aplicación (comando de abajo). Se crean el directorio y el archivo `data/nip46.db` (o `DATABASE_PATH`), el esquema y el administrador. La terminal solo registra `auth event=admin_bootstrap result=created`: **nunca** la contraseña ni el hash.
4. **Retire la contraseña del entorno** (`Remove-Item Env:ADMIN_PASSWORD` o `unset ADMIN_PASSWORD`; borre la línea de `.env` o el archivo). En los arranques siguientes la cuenta existente se conserva tal cual: no se sobrescribe, no se recrea y la variable ni siquiera se lee. Cambiar `ADMIN_PASSWORD` más adelante **no** cambia la contraseña guardada.

Si **no** hay administrador y falta una contraseña inicial válida, el arranque **se detiene** con un mensaje que dice qué definir (y, en Docker, el contenedor queda reiniciándose: vea `docker compose logs app`). Nunca se crea una cuenta silenciosa ni con una contraseña débil.

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

La aplicación queda en <http://127.0.0.1:8000> (interfaz web en `/`), solo accesible desde el propio equipo. Detener con `Ctrl+C` (la parada es ordenada y deja constancia de cierre en la auditoría). **No exponga la aplicación a Internet.**

### Qué se guarda y qué no (SQLite, decisión D-9)

| Se guarda en SQLite (`admins`, un único administrador) | **No** se guarda en SQLite ni en ningún archivo |
|---|---|
| identificador, usuario único (sin distinguir mayúsculas), **hash Argon2id** (RFC 9106 «low memory»: t=3, m=64 MiB, p=4, sal aleatoria de 16 bytes), estado, fechas de creación y de actualización y del último acceso | la contraseña (ni cifrada), claves privadas Nostr, secretos `bunker://`, JWT, cookies, la clave de firma del JWT |

La base la crea sola el primer arranque (archivo con permisos solo del propietario donde el sistema los admite). La base real, sus archivos auxiliares (`-journal`, `-wal`, `-shm`) y `data/` están excluidos de Git. Todo el SQL está en `app/storage/` y es parametrizado.

### Operar con la interfaz web (lo habitual)

1. Abra <http://127.0.0.1:8000> e ingrese con **usuario y contraseña** (Enter envía el formulario). El servidor verifica las credenciales y **genera el JWT automáticamente**: usted no copia ningún código ni token. La sesión dura 15 minutos por defecto y va en una cookie `HttpOnly` + `SameSite=Strict` que el JavaScript de la página no puede leer (ni siquiera recibe el token en la respuesta); el navegador **no guarda nada** (ni `localStorage` ni claves).
2. **Identidad:** «Crear identidad temporal» o importar una clave propia (hex o `nsec`; el campo se vacía al enviarla y la clave no se vuelve a mostrar).
3. **Firmante:** «Iniciar firmante» (abre una conexión al relay configurado). En modo continuo permanece activo hasta que lo detenga y se reconecta solo ante pérdidas recuperables del relay (estado «Reconectando»); una detención manual, un cierre por `AUTH`/TLS o agotar los reintentos no se reconectan.
4. **Conexión:** «Emitir URI de un solo uso»; cópiela una vez (no se vuelve a consultar) y péguela en la aplicación cliente (p. ej. Stacker News).
5. **Solicitudes pendientes:** revise cada tarjeta y pulse **Aprobar** o **Rechazar**. En una firma debe ver las 11 comprobaciones en verde, el origen `u` esperado y el contenido de Stacker News. Las solicitudes que incumplen la política se deniegan solas y no se ofrecen; el botón «Aprobar» se desactiva si alguna comprobación falla **y** la interfaz se niega a aprobar aunque se fuerce un clic sintético (P-37).
6. **Conexiones:** «Revocar» revoca una sola conexión (y cancela sus solicitudes pendientes).
7. **Auditoría** (sanitizada) y **cierre**: «Detener» deja `session_end` y revoca todas las conexiones; «Cerrar sesión» revoca el JWT.

### Sesión del administrador (JWT, decisiones D-8 y D-9)

`POST /api/auth/login` (`{"username": "...", "password": "..."}`) verifica las credenciales contra SQLite y, si son correctas, el **backend** emite un JWT HS256 firmado con una clave aleatoria de 384 bits que vive solo en memoria (cambia en cada arranque: reiniciar invalida todas las sesiones; nunca se deriva de la contraseña). Claims validados: `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, `jti` y `csrf`; algoritmo fijado, sin `none`; 8 sesiones como máximo; `POST /api/auth/logout` revoca el token en el servidor. El JWT llega al navegador **solo** en la cookie `HttpOnly`; un cliente de línea de comandos lo pide con `"return_token": true` para usarlo como `Authorization: Bearer`. Con cookie, las operaciones que cambian estado exigen `X-CSRF-Token` y un `Origin` local; con `Authorization: Bearer` no (el navegador no lo envía solo). Se rechazan las cabeceras `Host` ajenas. Sin cookie ni `Bearer`, todo `/api/*` responde 401.

**Usuario inexistente y contraseña incorrecta dan exactamente la misma respuesta** (401 `credenciales invalidas`, con el mismo costo de cálculo): no se puede averiguar si un usuario existe.

**Límites de intentos (P-35).** Hay dos contadores independientes y globales (no dependen de cabeceras que el cliente pueda cambiar, como `X-Forwarded-For`):
- *Inicio de sesión:* 5 intentos fallidos (los simultáneos también cuentan) por ventana de 5 minutos; al llegar al límite responde 429 con `Retry-After` **aunque la contraseña sea correcta**. Un inicio de sesión correcto no consume el cupo. Compromiso aceptado: alguien con acceso a la red local podría bloquear el ingreso durante 5 minutos (ver P-40).
- *Capacidad de verificación (P-41):* solo **una** verificación Argon2id corre a la vez por proceso (cola de hasta 4 y espera máxima de 3 s, sin bloquear el servidor); si se supera, el login responde **503** (`servicio ocupado`, `Retry-After: 2`) sin contar como intento fallido. Un único proceso es lo soportado: no use `--workers` (la clave JWT, las sesiones y los límites viven en la memoria de cada proceso).
- *Tokens inválidos:* más de 20 tokens caducados, revocados o falsificados por minuto reciben 429; un token válido nunca se frena.
- Una petición **sin credenciales** (la sonda normal de la interfaz, `GET /api/auth/session`, o una pestaña antigua) responde 401 y **no cuenta** como fallo de nada: ya no puede bloquear el ingreso.

### Registros que se generan

| Registro | Qué contiene | Dónde |
|---|---|---|
| **Operacional de autenticación** (logger `nip46.auth`, a la terminal / `docker compose logs app`) | solo eventos y metadatos: `admin_bootstrap` (`created` o `exists`), `login_ok` (prefijo de 8 caracteres del id de sesión), `login_failed`, `login_blocked` (segundos de espera), `login_busy` (capacidad de verificación agotada), `logout`, `login_error`, `startup_failed` (tipo de error) | stderr |
| **Auditoría NIP-46** (sanitizada, en memoria) | sesión del firmante, solicitudes, decisiones y firmas; visible en la interfaz | memoria |
| Registros de interacción con IA | `docs/ai-log.md` y `docs/ai-sessions/` | repositorio |

**Nunca** se registran contraseñas, hashes, usuarios escritos en el formulario, tokens, cookies, claves ni secretos de conexión (hay pruebas que lo comprueban).

### Si se pierde la contraseña

No hay recuperación por correo ni por pregunta secreta (la aplicación es local y no usa servicios externos). La base solo contiene la cuenta del administrador, así que el procedimiento es: **detener la aplicación, borrar la base y repetir el primer arranque** con una contraseña inicial nueva.
- Local: borre `data/nip46.db` (o el archivo de `DATABASE_PATH`) y sus auxiliares `-journal`, `-wal` y `-shm`.
- Docker Compose: **destruye los datos de ese entorno.** `docker compose -p <proyecto> down -v` borra el volumen `<proyecto>_app_data` (solo el de ese proyecto). Identifique antes el proyecto y el volumen (`docker volume ls`); en la demostración de evaluación son `nip46-evaluacion` y `nip46-evaluacion_app_data`. No lo ejecute sin `-p` en una máquina donde haya otros entornos.

Esto **no** afecta a nada más: la identidad Nostr vive solo en memoria y la identidad de B4 está en su propio archivo fuera del repositorio. Una herramienta de cambio de contraseña sin borrar la base queda como propuesta (P-39).

### Operar solo con la línea de comandos

| Método y ruta | Qué hace |
|---|---|
| `POST /api/auth/login` · `GET /api/auth/session` · `POST /api/auth/logout` | Inicio (usuario y contraseña; `"return_token": true` para recibir el JWT), consulta y cierre de sesión |
| `GET /api/status` | Estado de la identidad y del firmante (sin claves ni secretos) |
| `POST /api/identity` · `PUT /api/identity` · `GET /api/identity` | Crear una identidad temporal · importar una clave (`{"secret": "<hex o nsec>"}`) · consultar la clave pública. Cambiar solo con el firmante detenido |
| `POST /api/signer/start` · `POST /api/signer/stop` | Inicia (conexión al relay) o detiene el firmante; `stop` deja evidencia de cierre |
| `POST /api/connections` · `GET /api/connections` | Emite una URI `bunker://` de **un solo uso** (`Cache-Control: no-store`, se ve una vez) · lista los clientes (id opaco, clave truncada y estado) |
| `DELETE /api/connections/{id}` | Revoca **una** conexión (y cancela sus solicitudes pendientes); 404 si el id no existe, 409 si ya no está activa |
| `GET /api/requests?scope=pending`, `recent` o `all` | Solicitudes de decisión (`connect`, `sign_event`) con resumen y comprobaciones |
| `POST /api/requests/{id}/approve` y `/deny` | Decisión humana sobre **una** solicitud; una aprobación = una firma de un reto |
| `GET /api/audit?limit=100` | Auditoría sanitizada |

Ejemplo en PowerShell 7 (segunda terminal; ajuste el puerto si no es 8000). Las credenciales se piden con entrada oculta, sin dejarlas en el historial:

```powershell
$B = "http://127.0.0.1:8000"
$user = Read-Host "Usuario"
$pass = Read-Host "Contraseña" -MaskInput
$body = @{ username = $user; password = $pass; return_token = $true } | ConvertTo-Json
$H = @{ Authorization = "Bearer " + (Invoke-RestMethod -Method Post -Uri "$B/api/auth/login" -ContentType application/json -Body $body).token }
$pass = $null; $body = $null
Invoke-RestMethod -Method Post -Uri "$B/api/identity" -Headers $H            # clave pública de la identidad nueva
Invoke-RestMethod -Method Post -Uri "$B/api/signer/start" -Headers $H        # abre la conexión al relay configurado
(Invoke-RestMethod -Method Post -Uri "$B/api/connections" -Headers $H).uri   # URI bunker:// de un solo uso (no la copie a archivos ni chats)
Invoke-RestMethod -Uri "$B/api/requests" -Headers $H                          # qué se pide, con sus comprobaciones
Invoke-RestMethod -Method Post -Uri "$B/api/requests/<id>/approve" -Headers $H   # o /deny
Invoke-RestMethod -Method Post -Uri "$B/api/signer/stop" -Headers $H
Invoke-RestMethod -Uri "$B/api/audit" -Headers $H
```

Equivalente con `curl` (Linux, macOS, Git Bash): `read -rs PW; TOKEN=$(printf '{"username":"admin","password":"%s","return_token":true}' "$PW" | curl -s -X POST -H 'Content-Type: application/json' --data @- http://127.0.0.1:8000/api/auth/login | python -c 'import sys,json;print(json.load(sys.stdin)["token"])'); unset PW` y después `curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/connections`. (El cuerpo viaja por la entrada estándar para que la contraseña no aparezca en la lista de procesos; una contraseña con comillas o barras invertidas exige escapado JSON.)

**Efecto externo:** «Iniciar firmante» con el `RELAY_URL` por defecto se conecta a un relay público real. Para ensayar sin red externa use un relay local (`RELAY_URL=ws://127.0.0.1:<puerto>` con `RELAY_ALLOW_INSECURE=1`), las pruebas E2E (§9) o el arnés de `lab/`.

## 9. Ejecución de pytest

```bash
python -m pytest -v
```

No requieren Docker, Internet ni servicios externos. Son pruebas automatizadas: **no demuestran** interoperabilidad con Stacker News.

**Resultado verificado el 2026-11-22** (Windows 11, Python 3.12, Chrome instalado; con los vectores NIP-44 del laboratorio presentes): `python -m pytest` → `1037 passed, 27 skipped` (unos 130 s). Las omitidas son 26 pruebas de Docker (necesitan `E2E_DOCKER=1`) y 1 de permisos POSIX (no aplica en Windows). Sin los vectores NIP-44 (ver abajo) se omiten además los 8 vectores oficiales, y sin Chrome ni Edge, las E2E de navegador. `python -m pytest -m "not e2e"` → `1004 passed, 1 skipped`. Use `python -m pytest -rs -rx` para ver los motivos.

- **Vectores oficiales de NIP-44** (válidos e inválidos): no se versionan porque la licencia de su repositorio de origen no está aclarada. Las pruebas los leen de `NIP44_VECTORS_PATH` o de `lab/vendor/vectors/nip44.vectors.json`, verifican su SHA-256 y, si el archivo no existe, **se omiten con un aviso visible**. Se obtienen con las herramientas del laboratorio (`lab/tools/fetch_artifacts.py`, requiere red).
- **BIP-340:** el **CSV oficial completo** (19 vectores, positivos y negativos) está incluido como fixture, con su origen, fecha y SHA-256 en `tests/nostr/fixtures/README.md`; las pruebas ejecutan todos los vectores sin omitir ninguno.
- Los datos de interoperabilidad con `nostr-tools` (la biblioteca que usa Stacker News) están en `tests/nostr/fixtures/` y se generan con `lab/tools/gen_core_fixtures.mjs`.

### Pruebas E2E con navegador real (B6, solo entorno local)

Operan la **interfaz** con un navegador real (Playwright; usa Chrome o Edge instalados) contra la aplicación completa (Uvicorn) y un relay local en memoria; un cliente de prueba hace de «Stacker News». Identidades ficticias y sin Internet. Se ejecutan junto con el resto (`python -m pytest`); se omiten solos si no hay navegador. Para ejecutar solo las E2E o excluirlas:

```bash
python -m pytest -m e2e          # solo E2E de navegador
python -m pytest -m "not e2e"    # todo menos las E2E
```

Cubren: el **formulario de usuario y contraseña** (accesibilidad, Enter, estado de carga, mensajes idénticos para usuario inexistente y contraseña incorrecta, límite de intentos, JWT oculto al JavaScript, persistencia tras reiniciar y arranque abortado sin contraseña inicial), la defensa P-37 de «Aprobar» (clic real y sintético, HTML hostil como texto), la ausencia de bloqueo por sondeos anónimos (P-35), inicio de sesión y atributos de la cookie, ausencia de almacenamiento en el navegador, CSRF, cierre de sesión (revocación), caducidad del JWT, importación de clave sin eco, el flujo completo (identidad → firmante → URI una vez → `connect` aprobado → `get_public_key` → solicitudes inválidas rechazadas sin llegar al operador → `sign_event` aprobado y verificado → rechazo → auditoría sin secretos → parada con `session_end`) y el reinicio.

**E2E en Docker con el cliente NDK 2.12.2 real** (navegador → contenedor del producto → relay del laboratorio ← NDK real; sin servicios externos). Requiere las imágenes del laboratorio (`lab/README.md`) y la del producto:

```powershell
$env:E2E_DOCKER = "1"; python -m pytest tests/e2e/test_docker_ndk.py -v
```

**Argon2id con memoria limitada (P-41)** (`tests/e2e/test_docker_argon2_memory.py`, también con `E2E_DOCKER=1`; usa la imagen `nostr-nip46-remote-signer:dev` ya construida): arranca el contenedor real con `--memory` sin swap y comprueba el arranque, el login y ráfagas de verificaciones simultáneas (128 MiB × 1/5/8, 256 MiB × 5/8, 384 MiB × 8, 512 MiB × 8; tres rondas): no debe haber corte de conexión, 5xx ni OOM.

**Docker Compose real del producto** (`tests/e2e/test_docker_persistence.py`, también con `E2E_DOCKER=1`; construye la imagen del repositorio con un proyecto y una etiqueta propios): administrador inicial desde el entorno, persistencia de SQLite tras `restart`, `down` y recreación **sin** la contraseña inicial, que una contraseña distinta en el entorno no sobrescribe la guardada, usuario no root, raíz de solo lectura con solo `/data` escribible, ausencia de credenciales en la imagen y los registros, y el arranque abortado sin contraseña inicial.

**Modo continuo en Docker** (`tests/e2e/test_docker_continuous.py`, también con `E2E_DOCKER=1`; usa la imagen local `nostr-nip46-remote-signer:d17-continuous` —o `D17_TEST_IMAGE`— y la del laboratorio `nip46-lab-py:1.0a`, y **no construye ni descarga nada**): proyecto Docker efímero con un relay local, clave de prueba generada al vuelo y sin servicios externos; opera la interfaz en un navegador real (importación de identidad, URI solo desde la interfaz y ausente de los registros, aprobación humana de `connect` y de dos `sign_event`, límite de 30 por conexión, revocación individual, reconexión tras parar y arrancar el relay y ausencia de sockets hacia fuera de la red de Docker).

Además, `python lab/run_product_regression.py` (servicio) y `python lab/run_product_regression.py --api` (aplicación completa por HTTP, P-33) ejecutan E1, E2, E3 y E8 con NDK 2.12.2 en red Docker `internal`.

**Qué NO demuestran:** nada de lo anterior es una autenticación con Stacker News. Es validación **local**; la **real** está pendiente de la autorización de B4.

## 10. Ejecución mediante Docker Compose

**Para evaluar**, use el perfil de demostración del «Inicio rápido» (contraseña pública, solo local):

```bash
docker compose --env-file deploy/demo.env -p nip46-evaluacion up --build -d
```

**Para cualquier otro uso** (con una contraseña propia, que usted define como se explica abajo):

```bash
docker compose up --build -d
```

**Primer arranque en Docker:** defina antes `ADMIN_PASSWORD` (y, si quiere, `ADMIN_USERNAME`) **sin escribirla en la línea de comandos** (ver §8, «Primer arranque»): por ejemplo, en PowerShell 7 `$env:ADMIN_PASSWORD = Read-Host "Contraseña inicial" -MaskInput` y luego el comando anterior. Después de que el contenedor esté `healthy`, retire la variable y recree el contenedor (`Remove-Item Env:ADMIN_PASSWORD; docker compose up -d`): la cuenta persiste y la contraseña ya no hace falta. Sin contraseña inicial en una instalación nueva, el contenedor se detiene con instrucciones (`docker compose logs app`).

Dentro del contenedor la aplicación escucha en `0.0.0.0:8000` (necesario para que Docker pueda reenviar el tráfico), pero el puerto **se publica en el host solo en `127.0.0.1`**: no queda accesible desde la red local ni desde Internet. Para cambiar el puerto del host: `APP_PORT=8080 docker compose up --build -d` (Linux/macOS) o `$env:APP_PORT=8080; docker compose up --build -d` (PowerShell). Estado y healthcheck: `docker compose ps`.

Tras `docker compose up`, abra <http://127.0.0.1:8000> e ingrese con su usuario y contraseña. `compose.yaml` pasa al contenedor las variables del administrador (`ADMIN_USERNAME`, `ADMIN_PASSWORD`) y del firmante (`RELAY_URL`, `RELAY_TLS_GROUPS`, `SERVICE_ORIGIN`, `APPROVAL_TTL_S`, `MAX_SIGNATURES`, `SESSION_TTL_S`, `ALLOWED_HOSTS`, `JWT_TTL_S`, `SIGNER_WINDOW_S`, `SECRET_TTL_S`, `CONNECTION_TTL_S`, `MAX_REQUESTS`, `MAX_PENDING`, `COOKIE_SECURE`; vacío = valor por defecto de la §7); `DATABASE_PATH` queda fijo en `/data/nip46.db`. **No** reenvía `RELAY_ALLOW_INSECURE` (Docker nunca admite `ws://`) ni `ADMIN_PASSWORD_FILE`.

**Persistencia.** SQLite vive en el volumen con nombre `app_data` (en `/data`, el **único** directorio escribible: la raíz del contenedor sigue siendo de solo lectura y el usuario es el no privilegiado `uid 10001`). `docker compose down` **conserva** el volumen (y por tanto el administrador). La imagen no contiene credenciales. Empezar desde cero **destruye los datos de ese entorno** (la cuenta de administrador): `docker compose -p <proyecto> down -v` borra únicamente el volumen `<proyecto>_app_data`; con el proyecto por defecto sería `nostr-nip46-remote-signer_app_data`. Identifique siempre el proyecto y el volumen antes (`docker volume ls`) y no lo use de forma rutinaria; el procedimiento de la demostración de evaluación está en el «Inicio rápido». La clave privada Nostr nunca está en el volumen: se pierde siempre al reiniciar el contenedor y se vuelve a crear o importar desde la interfaz.

**Perfil de validación B6.2 (D-16).** `deploy/b62.env` es un perfil **específico de validación** (no la configuración definitiva del producto) con los límites exactos de [`docs/phase-1.0B-B6.2-plan.md`](docs/phase-1.0B-B6.2-plan.md) §4: puerto 8001, relay y origen reales, una firma, 30 solicitudes, ventana de firma de 120 s y sesión y conexión de 720 s. No contiene secretos. Se aplica con `--env-file`, que **sustituye** al `.env` local (un `.env` personal no altera la validación):

```bash
docker compose --env-file deploy/b62.env -p nostr-nip46-remote-signer up -d      # Linux/macOS/PowerShell (desde la raíz del repositorio)
```

**Puertos 8000 y 8001 (aclaración).** El `8000` es el valor por defecto de `compose.yaml` y el del perfil de evaluación `deploy/demo.env` (proyecto Docker `nip46-evaluacion`); el `8001` es el de los perfiles de validación real `deploy/continuous.env` y `deploy/b62.env` (proyecto `nostr-nip46-remote-signer`). Son **proyectos Docker distintos, con contenedor, red y volumen propios**, pensados para no interferir entre sí; **no son dos instancias de un mismo despliegue ni se ha verificado o decidido** cuál será la instalación canónica del entregable final ni si deben coexistir (pendiente; ver [`docs/HANDOFF.md`](docs/HANDOFF.md) §5). Un solo proceso del firmante por proyecto.

Arrancar el contenedor **no abre ninguna conexión externa**: el relay solo se contacta cuando la persona pulsa «Iniciar firmante» en el panel. **Reutilizar una base SQLite existente** (p. ej. `data/b62.db`) sin exponer la contraseña ni sobrescribir nada: cree antes el volumen con `docker compose --env-file deploy/b62.env -p nostr-nip46-remote-signer create --no-build --pull never` y ejecute `python deploy/import_admin_db.py --source data/b62.db --volume nostr-nip46-remote-signer_app_data --image <imagen-del-proyecto>`. **Indique siempre `--image` con la misma imagen que usa el proyecto** (`APP_IMAGE`; en la validación B6.2, `nostr-nip46-remote-signer:manual-b61d`): su valor por defecto es `nostr-nip46-remote-signer:dev`, que puede no coincidir con el código actual. La herramienta monta el origen **solo de lectura** en un contenedor efímero sin red, **nunca sobrescribe** un destino existente, comprueba integridad, esquema, número de administradores, propietario (`uid 10001`) y permisos (`0600`, directorio `0700`), y comprueba que el archivo de origen no cambió (SHA-256). No imprime contraseñas, hashes ni usuarios. Con la base importada no se necesita `ADMIN_PASSWORD`. Procedimiento completo: plan B6.2 §17.

**Varias copias del repositorio.** Por defecto `compose.yaml` usa el proyecto `nostr-nip46-remote-signer` y la imagen `nostr-nip46-remote-signer:dev`: otra copia reemplazaría esa imagen y compartiría contenedor, red **y el volumen con el administrador** con la primera. Para una copia independiente use un proyecto y una imagen propios: `APP_IMAGE=mi-copia:dev docker compose -p mi-copia up --build -d` (PowerShell: `$env:APP_IMAGE = "mi-copia:dev"; docker compose -p mi-copia up --build -d`) y, si hace falta, otro `APP_PORT`. El valor por defecto no cambia nada para quien ya usa el proyecto actual.

**Imagen base.** Por defecto `python:3.12-slim` (etiqueta mutable). Para un bloqueo verificable antes de las pruebas reales hay un digest del índice multiarquitectura (amd64 y arm64) verificado en el laboratorio: `PYTHON_IMAGE=python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b docker compose build` (decisión D-6; no activado por defecto). Con ese digest se verificó el Bloque B0.

### Demostración local desde el navegador (cliente web de laboratorio, B6.1D-R3)

Permite probar **todo el protocolo NIP-46 con dos pestañas del navegador**, sin scripts durante el recorrido: la pestaña A es el firmante (donde se **aprueba**) y la pestaña B es un cliente de demostración que usa el cliente **NDK 2.12.2 real** (el de Stacker News) contra un relay **local**. Es solo de laboratorio: no forma parte de la imagen ni del `compose.yaml` del producto, no tiene forma de aprobar nada y no se conecta a Stacker News ni a relays públicos. Requiere las imágenes del laboratorio `nip46-lab-py:1.0a` y `nip46-lab-node:1.0a` (`lab/README.md`).

```powershell
# Una vez (PowerShell 7, raiz del repositorio). Contrasena inicial por entrada oculta, solo la primera vez en un volumen nuevo:
$env:ADMIN_USERNAME = "admin-manual"; $env:ADMIN_PASSWORD = Read-Host "Contraseña inicial de prueba" -MaskInput
$env:APP_IMAGE = "nostr-nip46-remote-signer:demo"
docker compose -p nip46-demo -f compose.yaml -f lab/manual/compose.manual.yaml up --build -d
Remove-Item Env:ADMIN_PASSWORD        # la cuenta persiste en el volumen: ya no hace falta
# Detener: docker compose -p nip46-demo -f compose.yaml -f lab/manual/compose.manual.yaml down      (down -v borra tambien la base de prueba)
```

- **Pestaña A (firmante):** <http://127.0.0.1:8000>. **Pestaña B (cliente):** <http://127.0.0.1:18080>. **Relay local:** `ws://127.0.0.1:17777` (desde Docker, `ws://relay:7777`). Todo se publica solo en `127.0.0.1`.
- **Parámetros solo de la demostración:** ventana de firma **45 s** y TTL de aprobación **120 s** (variables `MANUAL_SIGNER_WINDOW_S` y `MANUAL_APPROVAL_TTL_S`). El firmante muestra en cada solicitud de firma el **plazo efectivo restante** («Plazo efectivo para firmar: N s»), que es el **menor** entre la ventana de la política y la caducidad de la aprobación; al llegar a cero indica «Ya no puede firmarse» y el botón pasa a «Aprobar (ya no firmará)».
- **Recorrido:** A: ingresar → «Crear identidad temporal» → «Iniciar firmante» → «Emitir URI de un solo uso» → «Copiar». B: pegar la URI → «Crear sesión» → «Conectar (connect)» → en A **Aprobar** → «get_public_key» y «ping» → «Firma válida» → en A **Aprobar** (B muestra «Firmada y verificada» con 7 comprobaciones ✓) → «Enviar firma inválida» (cada variante: se rechaza sin tarjeta) → «Firma válida» y esperar más de 45 s antes de aprobar (B: «Rechazada»; A: «Rechazada al firmar: la política dejó de cumplirse»). Una URI es de un solo uso: repetirla en una sesión nueva también se rechaza.
- **Qué no es:** no sustituye la validación real con Stacker News; «Firmada» en la pestaña B solo se muestra tras **verificar criptográficamente** la respuesta (id, firma BIP-340, identidad, contenido y reto).
- **Herramientas técnicas** (se conservan): `lab/manual/local_client.py` (cliente de terminal contra el mismo relay) y `lab/manual/check_live.py` (28 comprobaciones automatizadas de solo lectura sobre la pila viva).
- **Pruebas** (`E2E_DOCKER=1`): `tests/e2e/test_manual_client_web.py` automatiza los dos navegadores con aprobaciones **de prueba** (clics de Playwright), distintas de las que usted hace a mano.

## 11. Consulta de `/health`

```bash
curl http://127.0.0.1:8000/health
```

(PowerShell: `Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing`.) Respuesta esperada: HTTP 200, `Content-Type: application/json`, cuerpo `{"status":"ok"}`. El endpoint solo indica que el proceso responde; no consulta Stacker News ni relays.

## 12. Detención de contenedores

```bash
docker compose down                          # proyecto por defecto
docker compose -p nip46-evaluacion down      # demostración de evaluación
```

Solo afecta a los recursos de ese proyecto (contenedor y red). El volumen `app_data` (el administrador) **permanece**; borrarlo destruye datos y se explica en §10 y en el «Inicio rápido». La imagen permanece (`nostr-nip46-remote-signer:dev`, o `:evaluation` en la demostración); se borra con `docker image rm <imagen>`.

## 13. Limitaciones actuales

- **Autenticación real con Stacker News: dos ejecuciones, ambas observadas por el propietario.** La de B4 (2026-11-21, PASS con observaciones) fue observada por el propietario (sin captura ni comprobación de persistencia al recargar) y con la versión de entonces (supervisada, una firma). Se repitió el 2026-11-22 con la versión final en modo continuo (imagen `d17-continuous`): **PASS confirmado por el propietario**, sin evidencia técnica capturada (auditoría, horas y número de firmas **no verificados**); cualquier repetición requiere autorización expresa. El resto de las validaciones (B2, B3, B5, B6 local, modo continuo en Docker) son entorno local.
- **Sin persistencia de claves Nostr (D-3)** y sin multiusuario: SQLite guarda solo **un** administrador (D-9). **Reiniciar o recrear el contenedor borra la identidad** (hay que crearla o importarla de nuevo), cierra todas las sesiones de la interfaz y revoca las conexiones. La sesión de la interfaz dura 15 minutos por defecto (1 hora en el perfil de demostración). La cookie no es `Secure` por defecto porque la aplicación local usa `http://127.0.0.1`.
- **Credenciales de demostración públicas** (`deploy/demo.env`, D-18): solo para evaluación local; no deben usarse en producción ni exponerse en red.
- No hay recuperación ni cambio de contraseña desde la aplicación: se recupera borrando la base (ver §8; P-39). El límite de intentos es global: alguien con acceso a la red local puede bloquear el ingreso 5 minutos (P-40).
- **Revalidación antes de firmar (P-38, corregido en B6.1B; P-42 corregido en B6.1C; plazo efectivo visible en B6.1D-R3):** tras la aprobación humana el firmante vuelve a comprobar, justo antes de usar la clave, que la aprobación sigue vigente y sin consumir, que el firmante y el cliente siguen activos, que la política completa (incluida la ventana temporal `SIGNER_WINDOW_S`) se sigue cumpliendo y que lo que se firma es exactamente lo aprobado. **Consecuencia práctica:** una aprobación tardía **ya no firma**: debe aprobar dentro de `SIGNER_WINDOW_S` (120 s por defecto) menos la antigüedad de la plantilla, aunque `APPROVAL_TTL_S` sea mayor. La interfaz muestra el **resultado real** de cada firma (P-42): «Aprobada por el operador; falta el resultado de la firma», «Firmada correctamente», «Rechazada al firmar: <motivo>» o «Fallida: <motivo>», y lo anuncia con un banner; «firmada» significa que la firma se produjo y se autoverificó, no que el relay confirmara la entrega (eso se audita aparte, `response_published`).
- **Relay (modo continuo):** una sola conexión al relay; ante pérdidas **recuperables** se reconecta sola (2, 5, 10, 20 y 40 s) conservando conexiones y anti-replay, y tras 5 fallos seguidos pasa a «Fallido» (iniciar de nuevo a mano). **No** se reconecta tras una detención manual ni ante errores permanentes: un relay que exija `AUTH` (NIP-42), un error de TLS o un cierre explícito detienen la sesión.
- **Límites de frecuencia (continuo):** 120 solicitudes/min en total (aplicado antes de verificar la firma) y 30/min por conexión; lo que excede se descarta sin respuesta. Un remitente desconocido puede agotar el límite global y retrasar a los clientes legítimos hasta que avance la ventana de 60 s (no hay límite propio para remitentes no autorizados; propuesta pendiente). Una conexión revocada no se puede emparejar de nuevo con la misma clave de cliente: hay que usar una clave de cliente nueva (propuesta pendiente).
- NIP-44: texto plano limitado a 65535 bytes (restricción provisional P-14); sin prefijo extendido.
- Las versiones están fijadas en `constraints.txt`, pero **sin *hashes***: no hay verificación criptográfica de los paquetes (alternativa B no aprobada).
- La imagen base por defecto usa una etiqueta mutable (digest preparado, ver §10).
- `/docs`, `/redoc` y `/openapi.json` de FastAPI están **deshabilitados** (la interfaz tiene una CSP estricta).
- `pytest` muestra un aviso: Starlette marca `httpx` como obsoleto para su cliente de pruebas. Se mantiene `httpx` por ahora.
- **Memoria y Argon2id (P-41, cerrado en B6.1C):** cada verificación usa 64 MiB (perfil RFC 9106 «low memory»), pero una compuerta limita a **una** verificación activa por proceso, así que el pico es ~43 MiB de base + 64 MiB. Medido en el contenedor real sin swap: **sin OOM desde 128 MiB** con 1, 5 y 8 intentos simultáneos (antes, 5 simultáneos con 256 a 352 MiB lo provocaban). Los parámetros de Argon2id no cambiaron. Solo se soporta un proceso.
- No hay configuración de `mypy`/`ruff` en el proyecto; la comprobación de tipos estricta del Bloque B1 se ejecutó con herramientas externas temporales (ver `docs/decisions.md`).

## 14. Documentación

- Cierre de la Fase 1.0A y propuesta de la Fase 1.0B: [`docs/phase-1.0A-closure.md`](docs/phase-1.0A-closure.md), [`docs/phase-1.0B-proposal.md`](docs/phase-1.0B-proposal.md), resumen sanitizado de la evidencia: [`docs/phase-1.0A-evidence-summary.md`](docs/phase-1.0A-evidence-summary.md).
- Demostración real de B4 (resultado PASS con observaciones) y su compuerta: [`docs/phase-1.0B-B4-gate.md`](docs/phase-1.0B-B4-gate.md); evidencia sanitizada en [`docs/evidence/`](docs/evidence/).
- Cliente web local NIP-46 y contador del plazo efectivo de firma (B6.1D-R3): [`docs/phase-1.0B-B6.1D-R3-web-client.md`](docs/phase-1.0B-B6.1D-R3-web-client.md); diagnóstico de la validación manual (B6.1D): [`docs/phase-1.0B-B6.1D-diagnosis-and-proposal.md`](docs/phase-1.0B-B6.1D-diagnosis-and-proposal.md); cierre de B6.1D: [`docs/phase-1.0B-B6.1D-closure.md`](docs/phase-1.0B-B6.1D-closure.md); plan de la validación real B6.2 (pendiente de autorización): [`docs/phase-1.0B-B6.2-plan.md`](docs/phase-1.0B-B6.2-plan.md).
- Compuerta Argon2id (P-41) y resultado real de la firma en la interfaz (P-42), B6.1C: [`docs/phase-1.0B-B6.1C-p41-p42.md`](docs/phase-1.0B-B6.1C-p41-p42.md).
- Cierre de seguridad B6.1B (revalidación antes de firmar, P-38; Argon2id con memoria limitada, P-41): [`docs/phase-1.0B-B6.1B-security-closure.md`](docs/phase-1.0B-B6.1B-security-closure.md).
- Autenticación local con SQLite + JWT y correcciones P-35/P-36/P-37 (B6.1A): [`docs/phase-1.0B-B6.1A-local-auth.md`](docs/phase-1.0B-B6.1A-local-auth.md).
- Reproducibilidad desde un clon limpio (B6, etapa 1): [`docs/phase-1.0B-B6-stage1-reproducibility.md`](docs/phase-1.0B-B6-stage1-reproducibility.md).
- **Continuidad (leer primero para retomar):** [`docs/handoff-2026-11-21.md`](docs/handoff-2026-11-21.md).
- Decisiones y registro de IA: [`docs/decisions.md`](docs/decisions.md), [`docs/ai-log.md`](docs/ai-log.md).
- Investigación y diseño (Fase 0.3), todo **propuestas** salvo lo que `docs/decisions.md` marque como aprobado:
  - [Análisis del protocolo NIP-46](docs/nip46-protocol-analysis.md)
  - [Compatibilidad con Stacker News](docs/stacker-news-compatibility.md)
  - [Diseño de seguridad](docs/nip46-security-design.md)
  - [Plan de implementación y prueba real](docs/nip46-implementation-plan.md)
- Laboratorio: [`lab/README.md`](lab/README.md) y [`docs/nip46-lab-report.md`](docs/nip46-lab-report.md).
