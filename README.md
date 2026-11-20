# nostr-nip46-remote-signer

Python-based Nostr NIP-46 remote signer with Stacker News authentication, FastAPI, JWT, Docker and security controls.

## 1. Descripción y objetivo

Proyecto de prueba técnica para la Secretaría de Gobierno Digital del Ministerio de Hacienda de Chile.

**Objetivo final:** implementar un firmante remoto (*remote signer*) Nostr conforme a **NIP-46** y demostrar una **autenticación real con Stacker News**.

Stack previsto: Python 3.12, FastAPI, HTML/CSS/JavaScript, SQLite, Docker Compose y pytest. Las reglas de trabajo y seguridad están en [`AGENTS.md`](AGENTS.md); el contexto y el registro de trazabilidad de IA, en [`docs/`](docs/).

## 2. Alcance implementado (Fase 0.2)

Solo infraestructura inicial:

- Aplicación FastAPI ejecutable con una función de creación (`create_app`).
- Endpoint `GET /health`.
- Pruebas automatizadas con pytest.
- Dockerfile y Docker Compose.
- Dependencias gestionadas con `pyproject.toml`.

**No está implementado** nada del firmante: ni NIP-46, ni NIP-04/NIP-44, ni autenticación con Stacker News, ni relays, ni gestión de claves, ni JWT, ni SQLite, ni interfaz web. Ver [Limitaciones actuales](#13-limitaciones-actuales).

## 3. Requisitos del entorno

- Python 3.12 (desarrollado y probado con 3.12.10).
- pip.
- Docker Desktop con Compose v2 (solo para la ejecución con contenedores). Probado con Docker 25.0.2 y Compose v2.24.3 en Windows 11.

## 4. Estructura inicial de carpetas

```text
nostr-nip46-remote-signer/
├── app/
│   ├── __init__.py
│   ├── main.py            # create_app(): crea FastAPI y registra routers
│   ├── api/
│   │   ├── __init__.py
│   │   └── health.py      # GET /health (capa HTTP, sin lógica de negocio)
│   └── schemas/
│       ├── __init__.py
│       └── health.py      # Modelo Pydantic de la respuesta
├── tests/
│   ├── __init__.py
│   └── test_health.py
├── docs/                  # decisiones, contexto y registro de IA
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .env.example
├── pyproject.toml
├── constraints.txt        # versiones exactas de todas las dependencias (sin hashes)
├── AGENTS.md
├── CLAUDE.md
└── README.md
```

Las demás capas previstas (configuración, protocolo Nostr, servicios, persistencia, seguridad) **no se han creado todavía**: se añadirán en la fase que las necesite. El código de protocolo Nostr no deberá depender de FastAPI (ver `AGENTS.md` §4).

## 5. Instalación local con Python 3.12

Los comandos son para PowerShell, desde la raíz del repositorio. Si todavía no existe el entorno virtual:

```powershell
py -3.12 -m venv .venv
```

## 6. Uso del entorno virtual

Activar (el prompt mostrará `(.venv)`):

```powershell
.\.venv\Scripts\Activate.ps1
```

Alternativa sin activar: invocar el intérprete directamente con `.\.venv\Scripts\python.exe`. Los comandos de abajo usan esa forma, que funciona igual con el entorno activado o sin activar. `.venv/` está excluido de Git.

## 7. Instalación de dependencias

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"
```

Las dependencias directas están fijadas en [`pyproject.toml`](pyproject.toml) y **todas** las dependencias (directas y transitivas) están fijadas por versión en [`constraints.txt`](constraints.txt), que pip aplica con `-c`. El Dockerfile usa el mismo archivo. Las versiones directas de la validación de la Fase 0.2:

| Paquete | Versión | Tipo |
|---|---|---|
| fastapi | 0.165.0 | ejecución |
| uvicorn | 0.54.0 | ejecución |
| pytest | 9.2.0 | desarrollo |
| httpx | 0.28.1 | desarrollo (cliente de pruebas) |
| setuptools | 84.2.1 | construcción (solo al instalar el proyecto) |

### Qué es (y qué no es) `constraints.txt`

Fija **versiones exactas** para que local y Docker instalen lo mismo. **No incluye hashes**: no es un bloqueo verificable criptográficamente y no protege frente a un paquete alterado que conserve la misma versión. Tampoco fija `pip` ni la imagen base. `colorama` figura en el archivo porque se instala en Windows; en Linux pip lo ignora, así que un único archivo sirve para ambos sistemas.

### Actualizar `constraints.txt`

Solo cuando cambien las dependencias directas de `pyproject.toml` o se quiera actualizar las transitivas. Requiere aprobación del propietario.

1. Crear un entorno temporal limpio **fuera del repositorio** e instalar **sin** restricciones (resuelve las transitivas más recientes compatibles con las versiones directas):

   ```powershell
   py -3.12 -m venv $env:TEMP\lock-venv
   & $env:TEMP\lock-venv\Scripts\python.exe -m pip install -e ".[dev]"
   ```

2. Generar la lista de versiones y sustituir con ella las líneas del archivo situadas bajo la cabecera de comentarios (conservar la cabecera y actualizarla si cambia la versión de Python):

   ```powershell
   & $env:TEMP\lock-venv\Scripts\python.exe -m pip freeze --exclude-editable
   ```

3. Eliminar el entorno temporal: `Remove-Item -Recurse -Force $env:TEMP\lock-venv`.
4. Revisar el diff de `constraints.txt`: debe contener solo dependencias del proyecto y de las pruebas.
5. Verificar en el entorno del proyecto: `.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"`, luego `pip check` y `pytest`.
6. Verificar en Linux: `docker compose build --no-cache`. La construcción **falla** si la imagen instala algún paquete que no figure en `constraints.txt` con esa versión exacta. Si el fallo corresponde a una dependencia que solo existe en Linux, añadir su línea tal como la muestra `docker run --rm --entrypoint pip nostr-nip46-remote-signer:dev freeze`.

## 8. Ejecución de FastAPI

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

La API queda en <http://127.0.0.1:8000>. Detener con `Ctrl+C`.

## 9. Ejecución de pytest

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

No requieren Docker, Internet ni servicios externos. Son pruebas automatizadas: **no demuestran** interoperabilidad con Stacker News.

## 10. Ejecución mediante Docker Compose

```powershell
docker compose up --build -d
```

El puerto del host es configurable con la variable `APP_PORT` (por defecto 8000), por ejemplo `$env:APP_PORT=8080` antes del comando, o copiando `.env.example` a `.env`. El puerto se publica solo en `127.0.0.1`, no en la red local. Estado y healthcheck:

```powershell
docker compose ps
```

## 11. Consulta de `/health`

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing
```

Respuesta esperada: HTTP 200, `Content-Type: application/json`, cuerpo `{"status":"ok"}`. El endpoint solo indica que el proceso responde; no consulta Stacker News ni relays.

## 12. Detención de contenedores

```powershell
docker compose down
```

Solo afecta a los recursos de este proyecto (`nostr-nip46-remote-signer`). La imagen construida (`nostr-nip46-remote-signer:dev`) permanece; se puede borrar con `docker image rm nostr-nip46-remote-signer:dev`.

## 13. Limitaciones actuales

- Sin funcionalidad Nostr ni de firma: la aplicación solo expone `/health`.
- Sin autenticación local, base de datos ni interfaz web.
- Sin validación real con Stacker News.
- Las versiones de todas las dependencias están fijadas en `constraints.txt`, pero **sin *hashes***: no hay verificación criptográfica de los paquetes. Un bloqueo con hashes requeriría una herramienta adicional y no está aprobado (ver `docs/decisions.md`).
- La imagen base `python:3.12-slim` se referencia por una etiqueta mutable, no por *digest*; las construcciones pueden no ser idénticas en el tiempo. Se puede fijar un digest más adelante.
- La documentación interactiva de FastAPI (`/docs`, `/openapi.json`) está habilitada durante el desarrollo. Su disponibilidad debe revisarse antes de producción.
- `pytest` muestra un aviso: Starlette marca `httpx` como obsoleto para su cliente de pruebas y recomienda `httpx2`. Se mantiene `httpx` por ahora, sin migración automática.
- La decisión sobre el nombre de la capa de configuración (`config/` o `core/`) está pendiente.

## 14. Próximas fases previstas

Sin fechas ni alcance definidos todavía; cada fase requiere aprobación del propietario. Entre lo previsto por el proyecto: protocolo NIP-46, persistencia SQLite, autenticación local con JWT, interfaz web y la prueba de integración real con Stacker News.

La Fase 0.3 produjo solo **documentos de investigación y diseño** (propuestas **pendientes de aprobación**, sin código ni validación real):

- [Análisis del protocolo NIP-46](docs/nip46-protocol-analysis.md)
- [Compatibilidad con Stacker News](docs/stacker-news-compatibility.md)
- [Diseño de seguridad](docs/nip46-security-design.md)
- [Plan de implementación y prueba real](docs/nip46-implementation-plan.md)
