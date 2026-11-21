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
| 1.0B, Bloques B2 a B6 (firmante NIP-46, API, interfaz, demostración real) | **No iniciados**; propuesta en [`docs/phase-1.0B-proposal.md`](docs/phase-1.0B-proposal.md) |

**Implementado en `app/`:** FastAPI con `GET /health`, configuración mínima (`app/config.py`) y el núcleo `app/nostr/` (claves, eventos NIP-01, NIP-44, NIP-04 entrante, mensajes NIP-46 y URI `bunker://`). **No existen todavía** el servicio firmante, la conexión a relays, la API de control ni la interfaz web. El laboratorio (`lab/`) es un arnés de validación **separado del producto**: `app/` nunca importa de él.

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
│   ├── config.py          # único punto de lectura de variables de entorno (RELAY_URL, RELAY_TLS_GROUPS)
│   ├── api/health.py      # GET /health (capa HTTP, sin lógica de negocio)
│   ├── schemas/health.py
│   └── nostr/             # núcleo de protocolo: NO depende de FastAPI ni hace E/S de red
│       ├── errors.py      # errores de dominio (mensajes genéricos, sin secretos)
│       ├── keys.py        # Keypair opaco, BIP-340, ECDH, importación hex/nsec (NIP-19)
│       ├── event.py       # eventos NIP-01: serialización canónica, id, firma, verificación
│       ├── nip44.py       # NIP-44 v2 (cifrar y descifrar)
│       ├── nip04.py       # NIP-04 SOLO para descifrar solicitudes entrantes
│       └── nip46.py       # mensajes NIP-46 estrictos y URI bunker://
├── tests/                 # espejo de app/; tests/nostr/fixtures/ con los datos de interoperabilidad
├── lab/                   # laboratorio y arnés de regresión (NO es el producto)
├── docs/                  # decisiones, cierre de fases, propuestas y registro de IA
├── Dockerfile  compose.yaml  .dockerignore  .env.example
├── pyproject.toml  constraints.txt
└── AGENTS.md  CLAUDE.md  README.md
```

El código de protocolo no depende de FastAPI (ver `AGENTS.md` §4); `tests/test_architecture.py` lo comprueba. Las capas de servicios, API, persistencia y seguridad se añadirán en los bloques siguientes.

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
| cffi, pycparser | 2.1.1, 3.12 | transitivas | requeridas por `coincurve` y `cryptography` |
| pytest | 9.2.0 | desarrollo | pruebas |
| httpx | 0.28.1 | desarrollo | cliente de pruebas de FastAPI |
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

`RELAY_*` ya se valida (`Settings.from_env`), pero **ningún componente se conecta todavía** a un relay. El token de operador que protegerá la API se generará **al arrancar** la aplicación (Bloque B3) y no vivirá en archivos ni en JavaScript público. La clave privada Nostr se mantendrá **solo en memoria** (decisión D-3).

## 8. Ejecución de FastAPI

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

La API queda en <http://127.0.0.1:8000>, solo accesible desde el propio equipo. Detener con `Ctrl+C`. **No exponga la API a Internet.**

## 9. Ejecución de pytest

```bash
python -m pytest -v
```

No requieren Docker, Internet ni servicios externos. Son pruebas automatizadas: **no demuestran** interoperabilidad con Stacker News.

- **Vectores oficiales de NIP-44** (válidos e inválidos): no se versionan porque la licencia de su repositorio de origen no está aclarada. Las pruebas los leen de `NIP44_VECTORS_PATH` o de `lab/vendor/vectors/nip44.vectors.json`, verifican su SHA-256 y, si el archivo no existe, **se omiten con un aviso visible**. Se obtienen con las herramientas del laboratorio (`lab/tools/fetch_artifacts.py`, requiere red).
- **BIP-340:** el **CSV oficial completo** (19 vectores, positivos y negativos) está incluido como fixture, con su origen, fecha y SHA-256 en `tests/nostr/fixtures/README.md`; las pruebas ejecutan todos los vectores sin omitir ninguno.
- Los datos de interoperabilidad con `nostr-tools` (la biblioteca que usa Stacker News) están en `tests/nostr/fixtures/` y se generan con `lab/tools/gen_core_fixtures.mjs`.

## 10. Ejecución mediante Docker Compose

```bash
docker compose up --build -d
```

Dentro del contenedor la aplicación escucha en `0.0.0.0:8000` (necesario para que Docker pueda reenviar el tráfico), pero el puerto **se publica en el host solo en `127.0.0.1`**: no queda accesible desde la red local ni desde Internet. Para cambiar el puerto del host: `APP_PORT=8080 docker compose up --build -d` (Linux/macOS) o `$env:APP_PORT=8080; docker compose up --build -d` (PowerShell). Estado y healthcheck: `docker compose ps`.

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

- **Sin servicio firmante, sin conexión a relays, sin API de control ni interfaz web** (Bloques B2 a B5). Solo existe el núcleo de protocolo y `/health`.
- **Sin autenticación real con Stacker News**: la Fase 1.0A observó interoperabilidad de protocolo (sin firmar); el inicio de sesión completo está pendiente.
- NIP-44: texto plano limitado a 65535 bytes (restricción provisional P-14); sin prefijo extendido.
- Las versiones están fijadas en `constraints.txt`, pero **sin *hashes***: no hay verificación criptográfica de los paquetes (alternativa B no aprobada).
- La imagen base por defecto usa una etiqueta mutable (digest preparado, ver §10).
- `/docs` y `/openapi.json` de FastAPI están habilitados durante el desarrollo; revisar antes de producción.
- `pytest` muestra un aviso: Starlette marca `httpx` como obsoleto para su cliente de pruebas. Se mantiene `httpx` por ahora.
- No hay configuración de `mypy`/`ruff` en el proyecto; la comprobación de tipos estricta del Bloque B1 se ejecutó con herramientas externas temporales (ver `docs/decisions.md`).

## 14. Documentación

- Cierre de la Fase 1.0A y propuesta de la Fase 1.0B: [`docs/phase-1.0A-closure.md`](docs/phase-1.0A-closure.md), [`docs/phase-1.0B-proposal.md`](docs/phase-1.0B-proposal.md), resumen sanitizado de la evidencia: [`docs/phase-1.0A-evidence-summary.md`](docs/phase-1.0A-evidence-summary.md).
- Decisiones y registro de IA: [`docs/decisions.md`](docs/decisions.md), [`docs/ai-log.md`](docs/ai-log.md).
- Investigación y diseño (Fase 0.3), todo **propuestas** salvo lo que `docs/decisions.md` marque como aprobado:
  - [Análisis del protocolo NIP-46](docs/nip46-protocol-analysis.md)
  - [Compatibilidad con Stacker News](docs/stacker-news-compatibility.md)
  - [Diseño de seguridad](docs/nip46-security-design.md)
  - [Plan de implementación y prueba real](docs/nip46-implementation-plan.md)
- Laboratorio: [`lab/README.md`](lab/README.md) y [`docs/nip46-lab-report.md`](docs/nip46-lab-report.md).
