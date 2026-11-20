# Decisiones técnicas y supuestos

Registro según `AGENTS.md` §9. Cada decisión indica quién la tomó: **Propietario** (aprobada por él) o **Propuesta de Claude Code** (hecha por el agente; su estado se indica).

## Fase 0.2: inicialización técnica

### Decisiones del propietario en el prompt de la fase

- Dependencias iniciales: FastAPI y Uvicorn (ejecución); pytest y httpx (desarrollo). Gestión en `pyproject.toml`.
- Endpoint `GET /health` con respuesta fija `{"status": "ok"}`.
- Docker y Compose con healthcheck basado en la biblioteca estándar de Python, ejecución sin root y puerto configurable (8000 por defecto).
- No crear módulos vacíos; `.env.example` mínimo; sin `.env` real.

### Decisiones del propietario en la revisión técnica (2026-11-20)

La implementación quedó **aprobada provisionalmente**, sujeta a revisión final.

| # | Decisión del propietario | Efecto |
|---|---|---|
| D1 | Mantener `httpx` por ahora. Documentar el aviso sobre `httpx2`, sin migrar automáticamente. | Ver "Aviso sobre `httpx`" más abajo. |
| D2 | Proponer un mecanismo de bloqueo reproducible de dependencias, compatible con Windows y Docker Linux, sin incorporar herramientas ni modificar dependencias sin aprobación. | Alternativa A aprobada el 2026-11-20 y aplicada: ver "Bloqueo de versiones con `constraints.txt`". |
| D3 | Mantener temporalmente `python:3.12-slim`. Documentar el riesgo de la etiqueta mutable y la posibilidad de fijar un digest. | Ver "Imagen base". |
| D4 | Mantener `/docs` y `/openapi.json` habilitados durante el desarrollo; revisar su disponibilidad antes de producción. | Ver "Documentación interactiva". |
| D5 | Aprobar el endurecimiento Docker: usuario no root, sistema de archivos de solo lectura, `cap_drop: ALL` y `no-new-privileges`. | Propuestas 6 y 7 de la tabla: **aprobadas**. |
| D6 | Mantener el enlace del puerto HTTP a `127.0.0.1`. | Propuesta 7: **aprobada**. |
| D7 | No crear módulos vacíos ni implementar SQLite todavía. | Propuesta 1: **aprobada**. |
| D8 | Mantener la diferencia `config/` frente a `core/` como decisión arquitectónica pendiente, sin modificar la estructura. | Propuesta 2: **pendiente**. |

### Propuestas de Claude Code

Estado: "Aprobada" si el propietario la aprobó expresamente (ver D1 a D8); "Provisional" si solo está cubierta por la aprobación provisional general de la fase.

| # | Propuesta | Motivo | Alternativas descartadas | Estado |
|---|---|---|---|---|
| 1 | Estructura mínima: `app/main.py`, `app/api/health.py`, `app/schemas/health.py`. No se crearon `core/`, `nostr/`, `services/` ni `repositories/`. | El prompt pide no crear módulos vacíos. `schemas/` se creó porque contiene el modelo de respuesta. | Crear la estructura completa de referencia con paquetes vacíos. | Aprobada (D7) |
| 2 | Capa de configuración (`core/` o `config`) **no creada**. | No hay variables que la aplicación lea todavía: `APP_PORT` solo lo usa Compose. `AGENTS.md` §8 pide un único módulo `config`; el prompt de la fase sugiere `core/`. | Crear un módulo vacío. | **Pendiente** (D8): nombre por decidir cuando exista la primera variable |
| 3 | Versiones de dependencias directas fijadas con `==` en `pyproject.toml`, tomando la última publicada en PyPI el 2026-11-20. | `AGENTS.md` §8 pide fijar versiones. | Rangos compatibles (`>=`), menos reproducibles. | Provisional |
| 4 | Backend de construcción `setuptools==84.2.1` y paquete instalable (`pip install -e ".[dev]"` en local, `pip install .` en Docker). | Una única fuente de dependencias (`pyproject.toml`) para local y Docker. Es una dependencia de construcción, no de ejecución. Licencia MIT, mantenida por PyPA. | Mantener un `requirements.txt` duplicado. Con el pip instalado (25.0.1) no hay una forma directa de instalar solo las dependencias de `[project]` sin construir el proyecto. | Provisional |
| 5 | `uvicorn` y `fastapi` sin extras (`[standard]`). | Menos paquetes y menor superficie. Los extras añaden uvloop, httptools, websockets, watchfiles, python-dotenv, pyyaml, etc. | `uvicorn[standard]`; `fastapi[standard]`. | Provisional |
| 6 | Dockerfile multietapa con venv en `/opt/venv`; imagen final sin pip de construcción ni dependencias de desarrollo; usuario `app` (uid 10001). | Imagen final sin artefactos de construcción ni pytest/httpx (comprobado). | Una sola etapa. | Aprobada (D5) |
| 7 | Compose publica en `127.0.0.1:${APP_PORT:-8000}`, con `read_only`, `cap_drop: ALL`, `no-new-privileges` e `init`. | Proyecto orientado a seguridad: no exponer en la red local por defecto y reducir privilegios. Comprobado que la aplicación funciona así. | Publicar en `0.0.0.0` (por defecto de Docker). Para acceder desde otra máquina habría que cambiarlo explícitamente. | Aprobada (D5, D6) |
| 8 | Healthcheck con `urllib` de la biblioteca estándar, contra `127.0.0.1:8000` dentro del contenedor. | La imagen no incluye curl ni wget. | Instalar curl. | Provisional. Comprobado que pasa a `unhealthy` si el servicio no responde. |
| 9 | `.env.example` con una sola variable (`APP_PORT`). | Es la única variable usada. | Añadir variables futuras (secretos, relays): prohibido en esta fase. | Provisional |
| 10 | `.dockerignore` con patrones `**/` (corrección tras la revisión). | Los patrones de `.dockerignore` no son recursivos. La versión inicial (`__pycache__/`, `.env`, `*.db`, etc.) solo excluía en la raíz, y un `__pycache__` o `.env` anidados habrían entrado al contexto de construcción. Comprobado con una copia de prueba con archivos ficticios. | Dejar los patrones del primer borrador. | Provisional |
| 11 | `constraints.txt` con la versión exacta de todas las dependencias, usado en local y en Docker (con comprobación que falla la construcción si se instala algo no listado). | Reproducibilidad sin herramientas nuevas. Ver "Bloqueo de versiones con `constraints.txt`". | Alternativa B (hashes con `uv` o `pip-tools`): requiere autorización. | Aprobada (D2) |

### Aviso sobre `httpx` (D1)

Al ejecutar pytest, Starlette 1.10.0 emite `StarletteDeprecationWarning`: usar `httpx` con `starlette.testclient` está obsoleto y recomienda instalar `httpx2`. **Se mantiene `httpx==0.28.1` por decisión del propietario.** No se migra automáticamente.

- **Riesgo:** una versión futura de Starlette podría dejar de admitir `httpx` en `TestClient` y romper las pruebas. Con las versiones actuales el aviso es solo informativo y las 5 pruebas pasan.
- **Mitigación:** las versiones de las dependencias transitivas (incluido Starlette) están fijadas en `constraints.txt`, de modo que una actualización no rompe las pruebas sin aviso.
- **Para decidir más adelante:** migrar a `httpx2` (dependencia de desarrollo adicional, requiere autorización y revisión de su licencia, mantenimiento y seguridad) o seguir con `httpx` mientras Starlette lo admita.

### Imagen base (D3)

`Dockerfile` usa `python:3.12-slim`, una **etiqueta mutable**: el mismo texto puede apuntar a imágenes distintas en construcciones distintas (parches de Python, cambios del sistema base de Debian). Se mantiene temporalmente.

- **Riesgo:** construcciones no reproducibles; una actualización de la imagen base podría cambiar el comportamiento sin que cambie el repositorio, o incorporar un cambio no revisado.
- **Opción:** fijar un digest, es decir `FROM python:3.12-slim@sha256:<digest>`, o conservar la etiqueta y el digest juntos. El digest se obtiene de la imagen publicada (por ejemplo con `docker buildx imagetools inspect python:3.12-slim`; **no ejecutado todavía**). La contrapartida es que los parches de seguridad de la imagen base dejan de llegar solos y hay que actualizar el digest a propósito. Debe ir acompañado de un proceso de revisión periódica.

### Documentación interactiva (D4)

`/docs` y `/openapi.json` quedan habilitados con la configuración por defecto de FastAPI **durante el desarrollo**. **Deben revisarse antes de cualquier despliegue de producción** (por ejemplo, desactivarlos o protegerlos), porque exponen el contrato completo de la API.

### Bloqueo de versiones con `constraints.txt` (D2: alternativa A aprobada y aplicada)

El propietario aprobó la alternativa A el 2026-11-20 (cierre de la Fase 0.2): un archivo de restricciones de pip, sin herramientas adicionales y sin cambiar las versiones directas aprobadas.

**Qué es.** [`constraints.txt`](../constraints.txt) fija la versión exacta de las 23 dependencias efectivas del proyecto (14 de ejecución en Linux, más las de desarrollo y `colorama` en Windows). Se usa con `pip install -c constraints.txt ...` en local y en el Dockerfile.

**Qué NO es.** No incluye hashes. **No es un bloqueo verificable criptográficamente**: reproduce versiones, pero no detecta un paquete alterado que conserve la misma versión. Tampoco fija `pip` ni la imagen base (ver D3).

**Cómo se generó.** Con `pip freeze --exclude-editable` sobre el `.venv` del proyecto, que contiene solo las dependencias de `pyproject.toml` (extras `dev` incluidos) y sus transitivas. Se contrastó con una resolución nueva (`pip install --dry-run --report`) sin restricciones: 23 paquetes en ambos lados, **sin paquetes ajenos, sin faltantes y sin versiones distintas**. Las versiones directas no cambiaron.

**Diferencias Windows y Linux.** `colorama==0.4.6` es una dependencia condicional (de `click` y `pytest` solo en Windows). Figura en el archivo y pip lo ignora en Linux, por lo que **un único archivo sirve para ambos sistemas**. No se detectó ninguna dependencia exclusiva de Linux que no pueda representarse (si apareciera, habría que añadirla con su versión exacta o informar antes de cambiar de solución).

**Uso en Docker.** El Dockerfile copia `constraints.txt`, instala con `pip install -c constraints.txt .` y **hace fallar la construcción** si `pip freeze` muestra algún paquete (salvo el propio proyecto) que no figure en el archivo con esa versión exacta. Probado con un archivo al que se le quitó `anyio`: la construcción falló y señaló `anyio==4.16.0`.

**Procedimiento de actualización.** Está en el `README.md` ("Actualizar `constraints.txt`"). Resumen: entorno temporal limpio fuera del repositorio, instalación sin restricciones, `pip freeze --exclude-editable`, sustitución de las líneas bajo la cabecera, revisión del diff, verificación local (`pip check` y `pytest`) y verificación en Linux con `docker compose build --no-cache`. Requiere aprobación del propietario.

**Limitaciones.**
- Sin hashes (ver arriba).
- `pip freeze` se ejecuta en Windows y omitiría una dependencia exclusiva de Linux; la comprobación del Dockerfile la detectaría.
- Mantenimiento manual al cambiar o actualizar dependencias.

**Alternativa B (no aprobada; requeriría autorización: herramienta nueva): bloqueo con hashes y marcadores de plataforma.** Una herramienta como `uv` (`uv pip compile --universal --generate-hashes`) o `pip-tools` (`pip-compile --generate-hashes`) genera todas las versiones con los hashes SHA-256 de cada artefacto, instalable con `pip install --require-hashes`. *Ventajas:* verifica la integridad y puede cubrir varias plataformas. *Limitaciones:* añade una herramienta (licencia, mantenimiento y seguridad por evaluar), los paquetes con ruedas por plataforma exigen los hashes de cada una (Windows y Linux), y **no se ha probado en este repositorio**. El formato estándar `pylock.toml` (PEP 751) **no se evaluó**. Se recomienda valorarla antes de la fase que maneje claves privadas.

### Verificaciones finales de la Fase 0.2 (2026-11-20)

Ejecutadas por Claude Code tras incorporar `constraints.txt`. Son pruebas automatizadas y validación manual local y con Docker; **no hay validación real con Stacker News**.

| Verificación | Resultado |
|---|---|
| `pip install -c constraints.txt -e ".[dev]"` en `.venv` (Windows) | Correcto; `pip freeze --exclude-editable` coincide con el archivo (0 diferencias). |
| `pip check` | `No broken requirements found.` |
| `python -m pytest -q` | 5 pasaron, 0 fallaron, 0 omitidas, 1 aviso (`httpx`, ver D1). |
| Linux con extras `dev` (contenedor temporal, no el del proyecto) | `pip check` limpio, 22 de los 23 paquetes (la única ausencia es `colorama`) y las 5 pruebas pasan. |
| `docker compose build --no-cache` | Correcto; el guardián de `constraints.txt` pasó. |
| `docker compose up -d` | Contenedor `healthy`. |
| `GET http://127.0.0.1:8000/health` | HTTP 200, `application/json`, `{"status":"ok"}`. |
| Contenido de la imagen final | 14 paquetes de terceros, todos con la versión de `constraints.txt`, más el propio proyecto. Sin `pytest`, `httpx`, `httpcore`, `certifi`, `pluggy`, `iniconfig`, `pygments`, `packaging` ni `colorama`. Usuario `app` (uid 10001). |
| `docker compose down` | Solo se eliminaron el contenedor y la red del proyecto. |

### Decisiones postergadas para fases posteriores

| Tema | Estado | Cuándo decidir |
|---|---|---|
| `httpx` frente a `httpx2` (D1) | Se mantiene `httpx`; sin migrar. | Al actualizar Starlette o cuando retire el soporte. |
| Fijar digest de `python:3.12-slim` (D3) | Etiqueta mutable por ahora. | Antes de la prueba real con Stacker News o de cualquier despliegue. |
| Disponibilidad de `/docs` y `/openapi.json` (D4) | Habilitados en desarrollo. | Antes de producción. |
| `config/` frente a `core/` (D8) | Pendiente; estructura sin cambios. | Al crear la primera variable de configuración. |
| SQLite y `.gitignore` (D7) | No implementado; el `.gitignore` no cubre `*.db` ni `*.sqlite`. | Al definir la persistencia. |
| Bloqueo con hashes (alternativa B) | No aprobado. | Antes de la fase que maneje claves privadas. |
| Módulos de dominio (`nostr/`, `services/`, `repositories/`) | No creados (D7). | En la fase que los necesite. |

### Riesgos pendientes y prioridad

| Prioridad | Riesgo | Cuándo atenderlo |
|---|---|---|
| Media | Versiones fijadas con `constraints.txt` pero **sin hashes**: no hay verificación criptográfica de los paquetes (cadena de suministro). Incluye `opentelemetry-api`, que FastAPI 0.165.0 declara como dependencia propia y no se pidió expresamente. | Antes de la fase que maneje claves (alternativa B, requiere autorización). |
| Media | Imagen base por etiqueta mutable (D3). | Antes de la prueba real con Stacker News o de cualquier despliegue. |
| Media | `/docs` y `/openapi.json` expuestos (D4). | Antes de producción. |
| Media | `.gitignore` no cubre `*.db` ni `*.sqlite` (solo `db.sqlite3`). | Antes de implementar SQLite. |
| Media-baja | Aviso de obsolescencia de `httpx` con `starlette.testclient` (D1). | Cuando Starlette anuncie su retirada o al actualizar. |
| Baja | Diferencia `config/` frente a `core/` (D8). | Al crear la primera variable de configuración. |
| Baja | Transcripciones pendientes de la Fase 0.1 (06 a 08) y de ChatGPT (ver `docs/ai-log.md`). | Cuando el propietario lo decida. |

### Supuestos no verificados

- La compatibilidad de Python 3.12.10 con futuras bibliotecas Nostr no se ha comprobado; se evaluará al incorporarlas.
- **Interoperabilidad con Stacker News:** sin cambios; no se ha comprobado nada.
