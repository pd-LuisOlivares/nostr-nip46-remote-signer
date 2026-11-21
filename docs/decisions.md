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
| D8 | Mantener la diferencia `config/` frente a `core/` como decisión arquitectónica pendiente, sin modificar la estructura. | Propuesta 2: **pendiente**. **Resuelta en la Fase 1.0B por D-2: `app/config.py`.** |

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
| `config/` frente a `core/` (D8) | **Resuelta (D-2, Fase 1.0B): `app/config.py`.** | — |
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

## Fase 0.3: investigación y diseño de interoperabilidad NIP-46 (2026-11-20)

> **Cómo leer esta sección.** Cada elemento tiene un estado: **Aprobada** (el propietario la aprobó expresamente), **Aprobada provisionalmente**, **Propuesta** (hecha por Claude Code y **pendiente de aprobación**) o **Hipótesis** (afirmación **sin validar**, con el experimento que la resolvería). **Ninguna propuesta se declara aprobada.** Los fundamentos están en [nip46-protocol-analysis.md](nip46-protocol-analysis.md), [stacker-news-compatibility.md](stacker-news-compatibility.md), [nip46-security-design.md](nip46-security-design.md) y [nip46-implementation-plan.md](nip46-implementation-plan.md). La fase no modificó código, dependencias ni infraestructura y **no hubo conexión con relays ni con Stacker News**.

### Decisiones del propietario

| # | Decisión | Estado |
|---|---|---|
| O-1 | La investigación de la Fase 0.3 queda **aprobada provisionalmente**, sujeta a revisión final (2026-11-20). Aprueba la **investigación**, no las propuestas de implementación. | Aprobada provisionalmente |
| O-2 | Se autoriza **exclusivamente** la Fase 0.3 (investigación y diseño): sin implementar, sin dependencias nuevas, sin conexiones externas, sin claves, sin commits ni push. La Fase 1.0 **no** está iniciada. | Aprobada |
| O-3 | La decisión **`config/` frente a `core/`** (D8) se mantiene **pendiente** hasta que exista una necesidad real. | Aprobada (**resuelta por D-2: `app/config.py`**, ver Fase 1.0B) |
| O-4 | Instrucciones de diseño para la revisión: incorporar autorización explícita de clientes, restricción inicial a `kind 27235`, validación previa a firmar, control de repetición y tratamiento de los desafíos como operaciones sensibles; distinguir lo obligatorio del primer prototipo de las mejoras posteriores; **evitar abstracciones sin responsabilidad concreta**. | Instrucción de diseño (las medidas concretas son las propuestas P-05, P-13 y P-15) |

### Hallazgos verificados

| # | Hallazgo | Fuente | Estado |
|---|---|---|---|
| H-1 | Stacker News solo ofrece `bunker://` (y NIP-05); no tiene `nostrconnect://`. | `components/nostr-auth.js`, `lib/nostr.js` (commit `0a798c7`) | Verificado en código |
| H-2 | NDK 2.12.2 **selecciona NIP-04 para la solicitud inicial** (estado `encryptionType = "nip04"`). | `rpc.ts:37, 206`; `dist/index.mjs:7287, 7423` | Verificado en código |
| H-3 | El login firma un `kind 27235` con `["challenge", k1]` como **primera** etiqueta; el servidor valida `id`, firma y esa etiqueta. `k1` son 32 bytes aleatorios en hex. | `nostr-auth.js:148-157`; `[...nextauth].js:241-270`; `api/resolvers/lnurl.js:12-14` | Verificado en código |
| H-4 | El cliente usa solo `connect`, `get_public_key` y `sign_event`; `connect` envía `params[0]` vacío. | `signers/nip46/index.ts:171-214, 256-277` | Verificado en código |
| H-5 | La CSP de producción solo permite `wss:`/`https:`: un relay local `ws://` no sirve para la prueba real. | `proxy.js:230` | Verificado en código |
| H-6 | `nsecbunkerd` (que Stacker News aún lista) ya no tiene código en su rama principal. | `kind-0/nsecbunkerd@master` | Verificado |
| H-7 | No existe una biblioteca Python que implemente el **rol de firmante** NIP-46, ni NIP-44 independiente. | PyPI y repos evaluados | Verificado |
| H-8 | NDK decide el cifrado de **cada evento recibido por detección de formato** (`?iv=`), con valor inicial fijo y reintento con el otro esquema; no hay negociación. El `dist/` publicado coincide con `src/`. | `rpc.ts:107-129`; `dist/index.mjs:7349-7367` | Verificado en código |
| H-9 | El archivo oficial de vectores NIP-44 (checksum verificado) marca como **inválidas** las longitudes ≥ 65536, mientras que el texto vigente de NIP-44 las permite con prefijo extendido. | `nip44.vectors.json` frente a `44.md` (2026-06-28) | Verificado |
| H-10 | `PrivateKey.ecdh()` de `coincurve` devuelve `sha256(clave comprimida)`, **no** la coordenada X que exigen NIP-44 y NIP-04. | `coincurve/keys.py:163-169` | Verificado en código |

### Propuestas (pendientes de aprobación)

| # | Propuesta | Alternativas | Prioridad |
|---|---|---|---|
| P-01 | Priorizar el flujo **`bunker://`** para la primera prueba; `nostrconnect://` queda para después. | `nostrconnect://` (no lo ofrece Stacker News) | Alta |
| P-02 | **Aceptar NIP-04 entrante** de forma acotada, configurable y registrada, y **responder en NIP-44** (como nsec.app), con modo «espejar» como contingencia. **El valor por defecto de la respuesta es provisional** hasta los experimentos E1, E2 y E4 (P-17). | Solo NIP-44 (no puede descifrar el `connect` inicial **[I]**); responder siempre en NIP-04 | Alta |
| P-03 | Métodos de la primera demostración: `connect`, `get_public_key`, `sign_event` (solo `kind 27235`). Respuestas mínimas a `ping`, `switch_relays` y `logout`; `nip04_*` y `nip44_*` denegados por defecto. | Implementar todos los métodos | Alta |
| P-04 | **Claves de transporte e identidad distintas**, con tipos separados en el código. | Una sola clave | Alta |
| P-05 | Política de firma: solo `kind 27235`, perfil de servicio configurable (contenido, lista blanca de `u`, formato del reto), **14 comprobaciones previas** y sin editar el evento (diseño de seguridad §6). | Firmar cualquier `27235` | Alta |
| P-06 | Dependencias nuevas: **`coincurve`**, **`cryptography`**, **`websockets`**; NIP-01, NIP-04, NIP-44 y NIP-46 se implementan en `app/nostr/` con los vectores oficiales. | `nostr-sdk`, `pynostr`, `python-nostr`, `secp256k1`, `pycryptodome`, `aiohttp` | Alta |
| P-07 | Cifrado en reposo con **AEAD** y clave externa por variable de entorno; esquema a documentar aquí **antes** de implementarlo. | Texto claro (prohibido por `AGENTS.md` §7) | Alta |
| P-08 | Aprobación humana explícita de cada conexión (estado «Pendiente» → «Activa»); `auth_url` como mejora posterior. | Aprobar automáticamente con el secreto | Media |
| P-09 | Estrategia de relays: **un relay `wss://` principal** y uno de reserva, elegidos con autorización; NIP-42 en el cliente de relay. | Varios relays desde el inicio | Media |
| P-10 | **Laboratorio de compatibilidad con NDK 2.12.2** (Node + relay local) antes de la prueba real; requiere aprobar la ejecución de código de terceros y herramientas de desarrollo. | Ir directamente a la prueba real | Media |
| P-11 | Repetición: firma y `id` antes de descifrar, ventana de `created_at`, ids de evento y de solicitud vistos, secreto y reto de un solo uso; en memoria en el primer incremento, SQLite después. | Sin protección en la primera iteración | Alta |
| P-12 | Plan de tareas T0-T13 (plan de implementación §5). | — | Media |
| P-13 | **Arquitectura mínima:** solo `RelayTransport` como interfaz; `Keypair`, `SigningPolicy`, `SignerService` y `KeyVault` concretos; sin `repositories/` ni SQLite en el primer incremento; `now` inyectado en lugar de una interfaz `Clock`; sin módulo de configuración hasta T1 (O-3). Las otras seis interfaces de la versión anterior se eliminan o se difieren (plan §3.3). | Arquitectura con ocho interfaces | Media |
| P-14 | **NIP-44:** límite de **65535 bytes de texto plano** en el primer prototipo, como **restricción provisional propia, no una regla normativa** (NIP-44 vigente permite hasta 2^32 − 1 bytes); es coherente con el archivo de vectores y con los mensajes NIP-46; el prefijo extendido (≥ 65536) y sus tres vectores por checksum se registran como pendientes. | Soportar de inmediato el prefijo extendido | Media |
| P-15 | **Clasificación de medidas de seguridad:** 12 obligatorias para el primer prototipo (M1-M12) y 10 mejoras posteriores (L1-L10); **concesión de un solo uso** para firmar el evento de autenticación (diseño de seguridad §1.1 y §6.3). | Concesiones persistentes desde el inicio | Alta |
| P-16 | **Archivo de vectores NIP-44:** confirmar la licencia antes de copiarlo al repositorio; si no es posible, leerlo de una ruta local verificando su SHA-256, con omisión **explícita** si no está. | Copiarlo sin verificar | Media |
| P-17 | **Experimentos E1 a E6** del laboratorio NDK (compatibilidad §3.5) como condición previa a la prueba real, con regla de decisión: NIP-44 por defecto si E1 y E2 pasan; espejo si fallan pero E4 pasa; bloqueo si ambos fallan. | Probar solo contra Stacker News | Alta |

### Hipótesis (sin validar)

| # | Hipótesis | Estado | Cómo resolverla |
|---|---|---|---|
| Y-1 | Una respuesta NIP-44 a una solicitud NIP-04 se procesa **de extremo a extremo** en NDK 2.12.2 con nuestro firmante. La **ruta de código existe** (H-8); falta la evidencia experimental. | **Sin validar** | E1, E2, E5 y E6 (Fase 1.0, T11) |
| Y-2 | El modo espejo (responder NIP-04) completa el flujo. | **Sin validar** | E4 |
| Y-3 | Nuestro firmante descifra el primer `connect` NIP-04 real de NDK. | **Sin validar** | E3 |
| Y-4 | La implementación NIP-44 del navegador (`nostr-tools` 2.16.2, según el lockfile) acepta nuestras cargas. **No se leyó** su código. | **Sin validar** | E5 |
| Y-5 | Producción de Stacker News ejecuta una versión equivalente a `master` con NDK 2.12.x. | **Sin validar** | Observación en la primera conexión real |
| Y-6 | El valor de `u` (`NEXT_PUBLIC_URL`) de producción, y que `content` y formato del reto coinciden con `master`. | **Sin validar** | Primera conexión de laboratorio o real, con rechazo seguro si no coinciden |
| Y-7 | Un relay público concreto acepta `kind 24133` sin NIP-42 y reenvía rápido los eventos efímeros. | **Sin validar** | Observación autorizada (T13) |
| Y-8 | El `k1` no caduca en el servidor dentro del tiempo de aprobación. | **Sin validar** | Prueba real |
| Y-9 | La serialización NIP-01 de `content` en Python coincide con `JSON.stringify` de JavaScript en los casos límite. | **Sin validar** | Pruebas de T2 y laboratorio |
| Y-10 | Las APIs de `cryptography` (ChaCha20 con nonce de 16 bytes, HKDF-expand) y `coincurve` (`multiply`) producen los resultados de los vectores. | **Sin validar** | Vectores en T3 |

### Preguntas pendientes para el propietario

Detalladas en [nip46-implementation-plan.md](nip46-implementation-plan.md) §7 (Q1 a Q9) y en [nip46-security-design.md](nip46-security-design.md) §13 (1 a 7). Las más relevantes:

1. ¿Se aprueba P-02 (NIP-04 entrante acotado) sabiendo que el valor por defecto de la respuesta es provisional (P-17)?
2. ¿Se aprueban las dependencias de P-06?
3. ¿Se aprueba que cada aprobación humana autorice **una sola autenticación** (P-15)?
4. ¿Se aprueba el laboratorio NDK y la ejecución de código de terceros para los experimentos (P-10, P-17)?
5. ¿Qué tratamiento se da al archivo de vectores (P-16) y al prefijo extendido de NIP-44 (P-14)?
6. ¿Qué relays y qué ventana de pruebas se autorizarán para la prueba real?

### Documentación

- `docs/project-context.md` se actualizó en la revisión de cierre de la Fase 0.3 por petición del propietario (estado de las Fases 0.1, 0.2 y 0.3). Sigue siendo una **síntesis**, no una transcripción.

## Fase 1.0A: laboratorio de interoperabilidad NDK 2.12.2 (2026-11-20)

> **Estado: lo respaldado por evidencia se marca como tal; todo lo que implica una decisión sigue siendo PROPUESTA pendiente de aprobación del propietario.** Evidencia, método y límites en [nip46-lab-report.md](nip46-lab-report.md). El laboratorio **no valida compatibilidad con Stacker News**: solo con NDK 2.12.2 en Node 22 frente a un relay local mínimo. No se modificó `app/`, ninguna dependencia productiva ni la infraestructura existente.

### Decisiones del propietario en esta fase

| # | Decisión | Estado |
|---|---|---|
| O-5 | Laboratorio en Docker con red interna y sin puertos publicados; niveles 1 y 2 de dependencias; experimento E7 adicional; relay mínimo propio; `unittest` para las pruebas del laboratorio. | Aprobada |
| O-6 | Tres reglas de `.gitignore` (`lab/results/`, `lab/node/node_modules/`, `lab/vendor/`); clausura mínima de 24 entradas npm; descargas con verificación de integridad; vectores NIP-44 como dato local sin versionar. | Aprobada |

### Hipótesis de la Fase 0.3 y su estado tras el laboratorio

| # | Hipótesis | Estado | Evidencia |
|---|---|---|---|
| Y-1 | Una respuesta NIP-44 a una solicitud NIP-04 se procesa de extremo a extremo en NDK 2.12.2 | **Validada en laboratorio** (Node 22, relay local; **no** en Stacker News) | E1 y E2, con firmante de referencia y con Python: PASS |
| Y-2 | El modo espejo (respuesta NIP-04) completa el flujo | **Validada en laboratorio** | E4 y E4m: PASS |
| Y-3 | El firmante descifra el primer `connect` NIP-04 real de NDK | **Validada en laboratorio** | E3: SHA-256 del texto plano igual en NDK y en Python |
| Y-4 | `nostr-tools` 2.16.2 acepta nuestras cargas NIP-44 | **Validada en laboratorio** (no se leyó su código) | E5: 7/7 mensajes en ambos sentidos |
| Y-9 | La serialización NIP-01 de Python coincide con JavaScript | **Validada solo en parte** | Coincide para el evento de login (texto ASCII); los caracteres de control siguen sin probarse |
| Y-10 | Las APIs de `cryptography` y `coincurve` reproducen los vectores | **Validada** | 33 pruebas, incluidos todos los vectores oficiales válidos e inválidos |
| Y-5, Y-6, Y-7, Y-8 | Versión de producción, valores del perfil, relays, caducidad de `k1` | **Sin cambios (sin validar)** | Requieren la prueba real |

### Conclusiones respaldadas por evidencia de laboratorio

| # | Conclusión | Experimentos |
|---|---|---|
| L-1 | NDK 2.12.2 arranca en NIP-04, cambia a NIP-44 al recibir una respuesta NIP-44 y completa el flujo; con un firmante solo-NIP-44 no podría ni descifrar el `connect` inicial (E3 lo confirma desde el lado del firmante). | E1, E2, E3 |
| L-2 | El modo espejo NIP-04 también completa el flujo: sirve como contingencia. | E4, E4m |
| L-3 | Con firmante de referencia y con Python el comportamiento de NDK es el mismo; la criptografía propia es interoperable con `nostr-tools` 2.16.2. | E5, E5b y repeticiones |
| L-4 | NDK no impone tiempo máximo, tolera respuestas tardías, duplicadas, con `id` ajeno o indescifrables, y soporta `auth_url`. | E6, E7 |
| L-5 | NDK acepta una respuesta firmada por otra clave si el `id` coincide (correlación solo por `id`). Debilidad del cliente, no corregible desde el firmante. | E7 `spoof` |
| L-6 | Si `get_public_key` responde con error, `blockUntilReady()` resuelve y `user.pubkey` lanza `npub not set`. | E7 `get_pubkey_error` |

### Regla de decisión (Fase 0.3) aplicada

Sobre las corridas con Python: **E1 y E2 en PASS → recomendar NIP-44 como respuesta predeterminada.** Es una **recomendación respaldada por evidencia de laboratorio, no una decisión aprobada**; actualiza el estado de P-02 y P-17.

### Propuestas nuevas o actualizadas (pendientes de aprobación)

| # | Propuesta | Estado |
|---|---|---|
| P-02 (actualizada) | Responder en NIP-44 por defecto, aceptar NIP-04 solo como entrada y conservar el modo espejo como contingencia. Ya no es solo una inferencia: tiene respaldo experimental (L-1, L-2, L-3). | **Pendiente de aprobación** |
| P-17 (actualizada) | Los experimentos E1-E7 se ejecutaron: **PASS en todos**. Queda pendiente la prueba real, que es la única que puede decir algo sobre Stacker News. | **Cumplida en laboratorio; prueba real pendiente** |
| P-18 | Conservar el laboratorio (`lab/`) como **arnés de regresión** y ejecutar E1-E7 contra el firmante productivo cuando exista. | Pendiente |
| P-19 | El firmante **nunca responde con error a `get_public_key`** a un cliente autorizado, y los textos de `error` de `connect` son genéricos y estables (L-5, L-6). | Pendiente |
| P-20 | Antes de la prueba real, valorar una ejecución de NDK en un **navegador sin interfaz** (herramienta nueva: requeriría aprobación) para cerrar la diferencia Node/navegador. | Pendiente |
| P-21 | Confirmar la licencia del archivo de vectores NIP-44 antes de copiarlo al repositorio (reitera P-16). | Pendiente |

### Preguntas pendientes para el propietario

1. ¿Se aprueba P-02 con el respaldo de laboratorio, sabiendo que no cubre Stacker News?
2. ¿Se aprueba P-19 como requisito del firmante?
3. ¿Se valora P-20 (navegador sin interfaz) antes de la prueba real?
4. ¿Se conserva `lab/` en el repositorio (P-18) y se versionan sus archivos, excluidos `lab/vendor/` y `lab/results/`?

## Fase 1.0A.2 y cierre de la Fase 1.0A: validación con relay público y observación de Stacker News (2026-11-20)

> **Estado.** Cierre técnico preparado por Claude Code, **pendiente de aprobación del propietario**. Evidencia, verificación punto por punto y matriz de criterios en [phase-1.0A-closure.md](phase-1.0A-closure.md); propuesta de la Fase 1.0B en [phase-1.0B-proposal.md](phase-1.0B-proposal.md). **Aprobada** = instrucción expresa del propietario en esta sesión; el resto son propuestas. La Fase 1.0B **no** está iniciada. Interoperabilidad de protocolo observada **no** equivale a autenticación completa: **la autenticación real con Stacker News sigue pendiente**.

### Decisiones del propietario

| # | Decisión | Estado |
|---|---|---|
| O-7 | Implementar en `lab/` un firmante real mínimo y ensayarlo **solo en local** (E8 a E10); sin conexiones externas, cuentas, commits ni Fase 1.0B. Después: reanudación y verificación local previas a cualquier compuerta. | Aprobada |
| O-8 | Compuerta A con `relay.nsec.app:443` (2026-11-20, 17:00 a 17:02 Chile, un intento). Resultado **NO-GO**. | Aprobada y ejecutada |
| O-9 | Seleccionar `relay.primal.net:443` (A1) y `relay.primal.io:443` (A2) con `TLS_GROUPS=X25519` conservando la verificación TLS completa, ventana global de 5 minutos y un intento por destino (2026-11-20, 20:03 a 20:08 Chile). Resultados: A1 **GO**, A2 **NO-GO**. Registrar que el cambio de relay y de grupo TLS impide atribuir causalmente el fallo anterior al tamaño del ClientHello. | Aprobada y ejecutada |
| O-10 | Seleccionar **exclusivamente** `relay.primal.net:443` para las validaciones siguientes; **no investigar** `relay.primal.io`; no repetir sondas externas. | Aprobada |
| O-11 | Compuerta B (observación de Stacker News sin firmar): autorizada para 20:14 a 20:19 y **no ejecutada** (no había control automático del límite global ni forma segura de mostrar la URI desde la herramienta del agente). Se decidió construir un controlador verificable (`lab/real/run_gate_b.py`), validarlo con una Compuerta A local y ejecutar la B desde la PowerShell del propietario. | Aprobada |
| O-12 | Ejecución por el propietario del ensayo local interactivo (dos intentos: NO-GO y GO) y de la Compuerta B real (2026-11-20, ventana configurada 20:50:00 a 20:55:00 Chile; ejecución 20:50:05 a 20:54:24). **El texto de esa autorización no consta en el repositorio [NV].** | Ejecutadas por el propietario; ventana no verificada documentalmente |
| O-13 | Mantener la clasificación **LAB / DEV / DOC** del uso de IA sin reorganizar el repositorio ni reconstruir tiempos; no registrar las pruebas manuales de conectividad hechas en Windows. | Aprobada |

### Resultados que cambian el estado de las hipótesis (detalle en el cierre, §5)

| # | Hipótesis | Estado |
|---|---|---|
| Y-5 | Producción de Stacker News equivale a `master` con NDK 2.12.x | **Compatible con lo observado; no demostrada** |
| Y-6 | `u`, `content` y formato del reto | **Validada**: `u = https://stacker.news`, `content = Stacker News Authentication`, `method = GET`, etiquetas `challenge`, `u`, `method`, reto de 64 hexadecimales |
| Y-7 | Un relay público acepta `kind 24133` sin NIP-42 | **Validada solo para `relay.primal.net`** (sin `AUTH`) |
| Y-8 | El reto no caduca dentro del tiempo de aprobación | **Sin validar** (no se firmó) |

### Hallazgos verificados de la Fase 1.0A.2

| # | Hallazgo | Fuente |
|---|---|---|
| F-1 | Hubo dos ejecuciones interactivas de la Compuerta A local: la primera NO-GO (16 de 17; falló solo la atestación del operador, causa **[NV]**) y la segunda GO (17 de 17), sin cambios de código entre ambas. | `lab/results/gate-b-rehearsal-20261120T2342*/`, `…T234353Z/` |
| F-2 | La evidencia de parada forzada **no incluye `session_end`** (o lo incluye con un motivo artefacto de la carrera de cierre); `cero_firmas` no lo verifica en ese caso. Causa más probable **[H]**: el firmante no maneja `SIGTERM`. | `run_meta_b.json`, `evidence.jsonl` |
| F-3 | No existe un evaluador GO/NO-GO para la ejecución real de la Compuerta B; la clasificación es manual. | `lab/real/run_gate_b.py` |
| F-4 | `connect` real: 2 parámetros de tipo cadena, sin permisos, por NIP-04; `get_public_key` y `sign_event` por NIP-44. | `gate-b-run-02/evidence.jsonl` |
| F-5 | La plantilla de `sign_event` trae `id` y `pubkey` además de `content`, `created_at`, `kind` y `tags` (362 B, etiquetas en orden `challenge`, `u`, `method`): la política debe verificarlos, no ignorarlos. | `observed_sign` |
| F-6 | El firmante del laboratorio reintentaba la conexión al relay hasta 3 veces; se hizo configurable (`RELAY_ATTEMPTS`) y la Compuerta B lo fija en 1. | `signer.py`, `compose.gate-b.yaml` |
| F-7 | El ClientHello por defecto (OpenSSL 3.5.7) pesa 1530 B y con `X25519` 517 B; la causa del silencio de `relay.nsec.app` **sigue sin determinar [H]**. | medición local, `real-probe-20261120T165758/` |

### Propuestas nuevas (pendientes de aprobación)

| # | Propuesta | Estado |
|---|---|---|
| P-22 | Parada **ordenada** del firmante (`SIGTERM` manejado, evento de cierre con motivo «detenido por el controlador») y criterio que exija `session_end` o lo declare no verificado (F-2). Aplicable al producto y al laboratorio. | Pendiente |
| P-23 | Evaluador de la ejecución real de la Compuerta B (antes de cualquier Compuerta C) (F-3). | Pendiente |
| P-24 | Conservar en el producto la verificación de `id` y `pubkey` opcionales de la plantilla de `sign_event` (F-5) y la regla de un intento de conexión sin reintentos automáticos salvo decisión expresa (F-6). | Pendiente |
| P-25 | Opción `RELAY_TLS_GROUPS=X25519` en el cliente de relay del producto, conservando la verificación completa (resultado A1). | Pendiente |
| P-26 | Fase 1.0B: bloques B0 a B6 y decisiones D-1 a D-7 de [phase-1.0B-proposal.md](phase-1.0B-proposal.md); primer bloque recomendado: B0 + B1 (núcleo Nostr). | **Pendiente de aprobación** |
| P-27 | Versionar `lab/` y conservar una **selección sanitizada** de evidencia, ya que `lab/results/` está excluido de Git (hallazgo F-8 del cierre). | Pendiente |

### Limitaciones y supuestos no verificados

- El firmante de `lab/py/lab_real/` **no es el producto**: identidad y secretos solo en memoria, sin API, interfaz ni persistencia.
- **No se observó la respuesta de Stacker News a una firma válida** (sesión, cuenta, caducidad del reto). **[NV]** que Stacker News mostrase `unauthorized`: lo declaró el propietario y no hay captura.
- El contenido de `params[0]` de `connect` no se registra (solo tipos) **[NV]**.
- Las causas del fallo de `relay.nsec.app` y de `relay.primal.io` están sin determinar.
- La ventana autorizada de la Compuerta B real no puede contrastarse con el texto de la autorización **[NV]**.
- Transcripciones de la Fase 1.0A.2 sin exportar (ver `docs/ai-log.md`).

### Restricciones que se mantienen en el desarrollo

Ver [phase-1.0A-closure.md](phase-1.0A-closure.md) §8: interoperabilidad real primero; efectos externos solo con autorización por compuerta; sin claves ni URI reales en repositorio o registros; denegar por defecto y aprobación humana explícita; respuestas NIP-44 y NIP-04 solo como entrada; relay `wss://relay.primal.net:443` con TLS verificado; un intento sin reintentos automáticos; protocolo independiente de FastAPI; dependencias solo con aprobación; evidencia de cierre en toda parada.

## Fase 1.0B, Bloques B0 y B1: dependencias, configuración y núcleo Nostr (2026-11-20)

> **Estado.** Implementados B0 y B1 por Claude Code con autorización expresa del propietario; **B2 a B6 no están autorizados ni iniciados**. Sin commit ni push. Detalle de pruebas y verificaciones en el informe de la interacción 26 de [ai-log.md](ai-log.md). La interoperabilidad con Stacker News sigue siendo **de protocolo observado**; la autenticación completa está pendiente (B4/B6).

### Decisiones del propietario

| # | Decisión | Estado |
|---|---|---|
| O-14 | **Cierre técnico de la Fase 1.0A aprobado con observaciones** (primer intento de la Compuerta A NO-GO 16/17, segundo GO 17/17; Compuerta B con `connect`, `get_public_key` y `sign_event` reales y cero firmas; `session_end` ausente y falta de veredicto automático como limitaciones documentadas; autenticación real pendiente para B4/B6). No repetir compuertas; conservar evidencias; `lab/results/` fuera de Git con un resumen sanitizado; `lab/` se conserva como laboratorio y arnés de regresión, separado del producto. | Aprobada |
| O-15 | **Exportar las transcripciones pendientes de la Fase 1.0A**, revisándolas y eliminando secretos, tokens, claves privadas y URI `bunker://` completas. No registrar en las iteraciones las pruebas exploratorias manuales de conectividad en Windows. | Aprobada |
| D-1 | Dependencias `coincurve==21.0.0`, `cryptography==50.0.2`, `websockets==17.4`, las versiones verificadas en el laboratorio. | Aprobada (resuelve P-06) |
| D-2 | Un único módulo `app/config.py` para la configuración por variables de entorno (resuelve D8/O-3: **se descarta `core/`**). | Aprobada |
| D-3 | La clave privada Nostr vive **solo en memoria** durante el MVP; sin SQLite, almacenamiento cifrado ni persistencia de identidades. **Reemplaza P-07** (AEAD en reposo) para el MVP. | Aprobada |
| D-4 | Token de operador aleatorio generado al iniciar la aplicación para proteger las operaciones sensibles; **sin JWT ni sistema de usuarios**. Se implementa en B3; en B0/B1 solo se registra. **Modifica expresamente** lo previsto en `AGENTS.md` §3 y §7 (JWT para la API local): prevalece la instrucción del propietario (`AGENTS.md` §Introducción); **`AGENTS.md` no se modificó** (queda como contradicción documental a resolver por el propietario). | **Reemplazada por D-8** (2026-11-21; JWT) |
| D-5 | La identidad de Stacker News para la demostración real **queda pendiente**; no se crean cuentas ni se autentica nada en B0/B1. | Pendiente |
| D-6 | Mantener Python 3.12 y **preparar** el bloqueo de la imagen base por digest antes de las pruebas reales. | Aprobada (preparada, no activada) |
| D-7 | Relay de referencia `wss://relay.primal.net`, con verificación TLS y la opción X25519 validada. | Aprobada |
| O-16 | **Requisito transversal de portabilidad:** la aplicación se clona, instala y ejecuta en cualquier equipo compatible (Windows, Linux, macOS, o Docker) con su propia identidad, configuración y firmante; sin rutas ni IP propias; por defecto sin exponer la API a Internet; sin tokens ni secretos en JavaScript público; instalación reproducible y documentada. No implica servicio multiusuario ni despliegue público. | Aprobada |

### Resumen de implementación

- **B0.** `pyproject.toml` (+3 dependencias, con su propósito), `constraints.txt` (+5 líneas: las tres y `cffi==2.1.1`, `pycparser==3.12`; **certifi se conserva en 2026.10.23**: una resolución nueva traía 2026.11.20 y no se adoptó para no cambiar versiones no pedidas), `Dockerfile`/`compose.yaml` (`PYTHON_IMAGE`, digest preparado: `python@sha256:5e2bdb1b…4fa5b`, el **índice multiarquitectura** de `python:3.12.16-slim-trixie` ya verificado en el laboratorio; **no** activado por defecto), `app/config.py` (`RELAY_URL`, `RELAY_TLS_GROUPS`) y `.env.example`. Verificado: `pip check` limpio, `constraints.txt` idéntico a `pip freeze`, 5 pruebas previas en PASS, construcción Docker (con el guardián de `constraints.txt`), contenedor `healthy` y `/health` 200, importaciones y firma Schnorr dentro de la imagen.
- **B1.** `app/nostr/{errors,keys,event,nip44,nip04,nip46}.py`. `Keypair` opaco (sin lectura pública de la clave, bloquea `pickle` y `copy`, `repr` sin secreto, errores sin entradas); importación hex y `nsec` (NIP-19, bech32 propio de ~40 líneas comprobado con el ejemplo oficial y con `nostr-tools`); eventos NIP-01 estrictos; NIP-44 v2 con los vectores oficiales; **NIP-04 solo descifra** (sin función de cifrado); mensajes NIP-46 con Pydantic estricto y URI `bunker://` (relay obligatorio, `wss://` salvo bandera, secreto de 128 bits generado con `secrets`, sin parámetros extra). Sin dependencias de FastAPI ni de `lab/`; sin E/S (comprobado por `tests/test_architecture.py`).
- **Módulo extra:** `app/nostr/errors.py` (errores de dominio compartidos) no estaba en la lista de cinco módulos; se justifica por evitar importaciones circulares y duplicación.

### Hallazgos de B0/B1

| # | Hallazgo | Estado |
|---|---|---|
| F-8b | **Defecto real detectado por las pruebas antes de entregar:** en Python `$` de una expresión regular acepta un salto de línea final, de modo que `"<64 hex>\n"` se habría aceptado como clave, id o firma. Corregido con `\Z` en todos los patrones; hay pruebas de regresión por cada uno (claves, `nsec`, ids, firmas, secretos, hosts, métodos). | Corregido |
| Y-9 | **Validada**: la serialización NIP-01 de Python coincide con `JSON.stringify` de Node 22 en 180 casos (los 32 caracteres de control, `\u007f`, ` / `, comillas, barras, emoji y etiquetas), contrastada con fixtures generados por `lab/tools/gen_core_fixtures.mjs`. Los sustitutos aislados no tienen representación UTF-8 y se **rechazan**. | Validada en laboratorio local |
| H-NIP19 | El ejemplo oficial de NIP-19 (`nsec1vl029…` ↔ `67dea2ed…`) y las claves codificadas por `nostr-tools` decodifican a la clave esperada. | Verificado |
| L-BIP340 | **Cerrado en la interacción 27.** En B1 solo estaban verificados los vectores 0 a 3 (transcritos y comprobados por cálculo). Con la descarga autorizada del **CSV oficial completo** (origen `raw.githubusercontent.com/bitcoin/bips/master/bip-0340/test-vectors.csv`, obtenido 2026-11-21T00:55:30Z, SHA-256 `34c9d1d9…851c2d`, 6892 bytes) se ejecutan **los 19 vectores, sin omitir ninguno**: 9 positivos y 10 negativos (15 con mensaje de 32 bytes por la biblioteca y el producto; 4 con mensaje de 0, 1, 17 y 100 bytes por la biblioteca, porque el producto solo firma y verifica identificadores de 32 bytes). Todos pasan; la implementación no se modificó. El JSON provisional con los vectores 0 a 3 se eliminó. | **Cumplido** |
| L-NIP44 | Los vectores oficiales de NIP-44 **no se versionan** (licencia sin aclarar, P-16/P-21): se leen de una ruta local verificada por SHA-256 `269ed0f6…25040` y se **omiten con aviso visible** si faltan; con el archivo presente pasan todos (válidos e inválidos). | Cumple P-16 |
| L-TIPOS | `mypy --strict` sobre `app/nostr` y `app/config.py`: sin incidencias, con **herramientas temporales** instaladas fuera de las dependencias del proyecto (mypy no está en `constraints.txt`). Cobertura de líneas y ramas del código de `app/`: 100 % (medida con `coverage`, también temporal). No hay configuración permanente de mypy/ruff: decisión pendiente. | Informado |
| L-DOCKER | La construcción Docker se verificó con el digest como argumento (`PYTHON_IMAGE`); la construcción con la etiqueta mutable por defecto **no se ejecutó** (habría requerido consultar el registro de imágenes). | Informado |

### Cierre de B1 (interacción 27)

El propietario autorizó **exclusivamente** cerrar los criterios pendientes de B1 (no B2). Aceptó las descargas de PyPI de B0 **como tráfico de instalación de dependencias**: **no deben documentarse como ejecución completamente offline** (las comprobaciones de B0 y B1 que instalaron paquetes usaron PyPI; la generación de fixtures con Node y la ejecución de las pruebas no necesitan red). La prohibición de conexiones externas sigue aplicando a relays, Stacker News y servicios de autenticación. Se autorizó **una única** descarga del CSV oficial de BIP-340 (ver L-BIP340), con TLS verificado, sin código ejecutable ni dependencias nuevas. `mypy` y `ruff` **no** se incorporan como dependencias. **Estado formal de B1: ver la interacción 27 de `docs/ai-log.md`.**

### Dependencias y accesos a red durante B0

Para verificar compatibilidad (instalación en un entorno temporal limpio, en `.venv`, en un contenedor Linux y en la construcción Docker) se **descargaron paquetes del índice público de PyPI** (`pypi.org` y `files.pythonhosted.org`): solo las versiones fijadas y sus transitivas; sin datos del proyecto. **No hubo conexiones a relays, a Stacker News ni a ningún otro servicio.** El criterio «sin conexiones externas» se interpreta como ausencia de relays y servicios; las descargas de paquetes eran inherentes a B0 (instalar dependencias aprobadas) y se informan aquí.

### Propuestas nuevas o actualizadas (pendientes)

| # | Propuesta | Estado |
|---|---|---|
| P-28 | Bloque B2 (firmante NIP-46 sin interfaz): ver [phase-1.0B-proposal.md](phase-1.0B-proposal.md) §9. | Pendiente de aprobación |
| P-29 | Obtener y verificar el CSV oficial de BIP-340 (con autorización de una descarga) para cerrar el criterio parcial. | **Cumplida** (interacción 27) |
| P-30 | Valorar `mypy` y `ruff` como dependencias de desarrollo (hoy solo se ejecutaron temporalmente). | Pendiente |
| P-31 | Resolver la contradicción de `AGENTS.md` (§3/§7 mencionan JWT) con D-4: actualizar `AGENTS.md` por el propietario. | Pendiente |


## Fase 1.0B, Bloques B2 y B3: firmante NIP-46 funcional y API local de control; preparación de B4 (2026-11-21)

### Decisiones del propietario

| # | Decisión | Estado |
|---|---|---|
| O-17 | **Implementar conjuntamente B2 (firmante NIP-46), B3 (API local y control del operador) y preparar B4** sin aprobaciones intermedias; una **única** autorización operativa antes de cualquier conexión real. B5 y B6 quedan sin autorizar. Se mantienen: sin commit ni push, sin modificar `AGENTS.md`/`CLAUDE.md`, sin relays públicos ni Stacker News, sin cuentas, sin firmar solicitudes externas, sin persistencia de claves, sin JWT, sin ampliar la política a otros `kind`, sin interfaz web. | Aprobada |
| B2-1 a B2-7 | Las siete decisiones del plan de B2 (`docs/phase-1.0B-proposal.md` §9.2) se aplican **según su recomendación**: `websockets`/`asyncio`/`ssl` solo en `app/nostr/relay.py` (la prueba de arquitectura vigila el resto); origen `https://stacker.news` configurable; una aprobación = una firma de un reto; caducidad de solicitudes 120 s; un único intento de conexión al relay, sin reconexión; auditoría en memoria con lista blanca (sin SQLite); aprobación por guion solo en el arnés del laboratorio. | Aplicadas |
| D-5 | Identidad de Stacker News para B4: **sigue pendiente**. Se presentan las opciones A (desechable, cuenta real huérfana) y B (identidad de prueba dedicada del propietario) en `docs/phase-1.0B-B4-gate.md` §3. | Pendiente |

### Resumen de implementación

- **Capas.** `app/nostr/relay.py` (transporte; única E/S de red) · `app/services/{policy,connections,approvals,audit,signer,runtime}.py` (sin FastAPI ni red) · `app/api/{control,security}.py` y `app/schemas/control.py` (HTTP) · `app/main.py` (`create_app`, `lifespan`, validación de `Host`) · `app/config.py` ampliado. `tests/test_architecture.py` comprueba: el núcleo no importa FastAPI, la red solo está en `relay.py`, los servicios no importan la API, y la aplicación no persiste claves.
- **Firmante.** Clave de **transporte** distinta de la de **identidad**; los eventos de transporte se validan (firma, `id`, `kind 24133`, `p`, ventana, repetición) **antes** de descifrar; `connect` NIP-04 entrante se acepta y toda respuesta va en NIP-44; `connect` exige secreto de un solo uso (solo se guarda su SHA-256) **y** aprobación humana; `sign_event` solo para `kind 27235` con 11 comprobaciones; una solicitud que incumple la política **no se ofrece** al operador; la aprobación se consume de forma atómica (sin `await` entre comprobar y consumir) antes de firmar, la firma se **autoverifica** y se verifica que etiquetas, contenido y `created_at` no cambiaron; topes de firmas, solicitudes, pendientes, clientes y secretos sin usar; errores hacia el cliente genéricos y estables; `session_end` siempre (parada, cancelación, error, `AUTH`, `CLOSED`, vida máxima).
- **API.** Token de operador de 256 bits generado al arrancar y mostrado una vez (se conserva solo su SHA-256; comparación en tiempo constante; límite por fallos → 429); dependencia a nivel de router (denegar por defecto); `Host` restringido (anti DNS rebinding); `Cache-Control: no-store` y cabeceras de seguridad; el manejador de 422 **no repite la entrada** (una clave mal formada no reaparece); la URI `bunker://` solo viaja en la respuesta de `POST /api/connections`.
- **Configuración nueva** (todas validadas, sin valores sensibles por defecto): `RELAY_ALLOW_INSECURE`, `SERVICE_ORIGIN`, `SIGNER_WINDOW_S`, `SECRET_TTL_S`, `CONNECTION_TTL_S`, `SESSION_TTL_S`, `APPROVAL_TTL_S`, `MAX_SIGNATURES` (por defecto 1), `MAX_REQUESTS`, `MAX_PENDING`, `ALLOWED_HOSTS`. **Sin dependencias nuevas** (`pip check` limpio; `constraints.txt` sin cambios).
- **Docker.** Dentro del contenedor se escucha en `0.0.0.0:8000`; el host publica solo `127.0.0.1` (comprobado: `/health` 200, `/api/status` 401 sin token y 200 con token, `Host` ajeno 400). `compose.yaml` pasa las variables del firmante.

### Verificaciones ejecutadas (automatizadas y de laboratorio; **no** son validación con Stacker News)

| Verificación | Resultado |
|---|---|
| `python -m pytest -q` (Windows, Python 3.12.10) | **530 passed**, 0 omitidas (254 de B0/B1 + pruebas nuevas de política, conexiones, aprobaciones, auditoría, firmante, `runtime`, transporte `relay` con servidor WebSocket local y CA desechable, API y configuración) |
| `mypy --strict app` (herramienta temporal; no es dependencia) | Sin incidencias (25 archivos) |
| Cobertura de líneas y ramas (herramienta temporal) | **99 %** de `app/` en conjunto; todos los módulos nuevos ≥ 92 % (mínimo `runtime.py`: la rama de tiempo agotado de la parada de 10 s no se ejercita) |
| Regresión NDK 2.12.2 contra el firmante **del producto** (`lab/run_product_regression.py`; relay del laboratorio, red `internal`, aprobación por guion **solo** en el arnés) | E1, E2, E3 y E8: **PASS**; las 9 variantes inválidas de E8 se rechazan sin llegar al operador, la válida se firma intacta, la repetición se rechaza, 1 firma |
| Contenedor del producto (publicación solo en `127.0.0.1`, token, `Host`) | OK |
| `pip check`, `git diff --check` | Limpios |

### Hallazgos de B2/B3

| # | Hallazgo |
|---|---|
| F-9 | Las respuestas de error NIP-46 llevan `result="error"` además de `error` (comportamiento verificado con NDK en la Fase 1.0A); las pruebas distinguen error por el campo `error`, no por la ausencia de `result`. |
| F-10 | La plantilla de `sign_event` de Stacker News trae `id` y `pubkey` (F-5): la política los **verifica** (id recalculado con la identidad del firmante) y firma lo recibido sin editarlo. |
| F-11 | Pydantic (Rust) no admite `\Z` en `Path(pattern=…)`: se usa `^…$` en los patrones de FastAPI; las expresiones regulares de `re` mantienen `\Z` (F-8b). |
| F-12 | Con `ws://` y `ssl=None` explícito `websockets` falla: el transporte solo pasa `ssl` en `wss://`. |

### Limitaciones y supuestos no verificados

- **Sin autenticación real con Stacker News**: nunca se firmó con el origen real; la respuesta de Stacker News a una firma válida no se ha observado (Y-8). Ver `docs/phase-1.0B-B4-gate.md` §2.
- La API se probó con httpx/ASGI y un cliente doble; no se ejecutó una sesión completa con `uvicorn` real + NDK en red interna (la regresión NDK usa el servicio, sin la capa HTTP).
- NDK en el **navegador** de Stacker News sigue sin observarse contra este firmante (Y-5).
- La imagen del producto con etiqueta mutable por defecto no se construyó; sí con el digest (D-6).
- Sin *hashes* en `constraints.txt` (alternativa B no aprobada); `mypy`/`ruff` siguen sin ser dependencias (P-30).
- La espera de parada de `SignerRuntime.stop()` (10 s) no tiene prueba de la rama de tiempo agotado.
- Sin reconexión al relay ni al hacer `start` tras un fallo: se crea una sesión nueva a petición del operador.

### Propuestas nuevas o actualizadas (pendientes)

| # | Propuesta | Estado |
|---|---|---|
| P-32 | Autorización operativa única de B4 (`docs/phase-1.0B-B4-gate.md`): D-5, ventana, operador y restricciones. | **Pendiente de autorización** |
| P-33 | Ensayo completo local `uvicorn` + NDK en red interna antes de B4 (cierra el límite «API con cliente doble»). | Pendiente (opcional) |
| P-28 | Bloque B2 (ver `docs/phase-1.0B-proposal.md` §9). | **Cumplida** (implementada y verificada localmente) |
| P-31 | Resolver la contradicción de `AGENTS.md` (JWT) con D-4. | **Resuelta en lo esencial por D-8** (JWT); `AGENTS.md` no se modificó |


## Fase 1.0B, cierre local de B2 a B6: JWT, interfaz web y E2E (2026-11-21)

### Decisiones del propietario

| # | Decisión | Estado |
|---|---|---|
| D-8 | **La autenticación de la API local pasa a JWT** (reemplaza a **D-4**, token de operador). Local y monousuario, sin base de datos ni usuarios; sin credenciales predeterminadas; clave de firma aleatoria; expiración corta; validación estricta; revocación al cerrar sesión o reiniciar; sin `localStorage`; protección CSRF con cookies; restricción de `Host` y `Origin`. Resuelve **P-31** en lo esencial (`AGENTS.md` §3 y §7 ya preveían JWT; no se modificó `AGENTS.md`). | Aprobada |
| O-18 | Completar B2/B3 (P-33 primero), implementar **B5** (interfaz) y **B6** (E2E de navegador real) en local sin aprobaciones intermedias; **B4 real** y cualquier conexión a `relay.primal.net`, Stacker News, cuentas reales o firma externa quedan sujetos a una compuerta única (`docs/phase-1.0B-B4-gate.md`). | Aprobada |
| D-5 | Identidad para B4: **identidad de prueba dedicada y reutilizable bajo control del propietario** (opción B); sin cuenta real ni clave personal sin aprobación expresa. La confirmación concreta queda en la compuerta. | Parcial (instrucción de principio; confirmación pendiente) |

### Diseño de D-8 (JWT)

- **Inicio de sesión sin credenciales fijas:** al arrancar se genera un **código de acceso** aleatorio (se muestra una vez en la terminal; solo se guarda su SHA-256) que se canjea en `POST /api/auth/login` por un JWT **HS256** firmado con una clave aleatoria de 384 bits que **solo vive en memoria** (cambia en cada arranque: reiniciar invalida todas las sesiones).
- **Validación:** algoritmo fijado (lista cerrada; `none` y otros algoritmos se rechazan), `exp`/`iat`/`nbf`/`iss`/`aud`/`sub`/`jti`/`csrf` obligatorios, `jti` activo en el servidor (cerrar sesión revoca), máximo 8 sesiones, vida por defecto 900 s (`JWT_TTL_S`, 5–3600).
- **Transporte del token:** cookie `nip46_session` `HttpOnly` + `SameSite=Strict` + `Path=/api` (`Secure` con `COOKIE_SECURE=1`); la interfaz **no guarda nada** en el navegador. Con cookie, las escrituras exigen `X-CSRF-Token` (claim propio, comparación en tiempo constante) y un `Origin` local que coincida con `Host`; con `Authorization: Bearer` (línea de comandos) no hace falta CSRF. Límite de fallos (429 solo para quien falla; un token válido sigue funcionando), `Host` restringido (400), `docs`/`openapi` deshabilitados, CSP estricta (`default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`) y cabeceras de seguridad.
- **Desviación consciente de `AGENTS.md` §7** («secreto desde variable de entorno»): la clave de firma del JWT **no** viene del entorno sino que se genera aleatoriamente en cada arranque (orden expresa del propietario: «clave de firma criptográficamente aleatoria», sin claves JWT versionadas). Es más restrictiva (no hay un secreto que configurar ni filtrar); su coste es que las sesiones no sobreviven a un reinicio, lo cual es el comportamiento deseado.
- **Dependencia nueva:** `PyJWT==2.15.1` (MIT; publicado 2026-09-28, más de siete semanas antes; con HS256 no requiere el extra `crypto`; alternativa de la biblioteca estándar: implementar HS256 a mano con `hmac`, descartada por `AGENTS.md` §7 «no inventes criptografía propia»; mantenida, sin dependencias propias para este uso). Instalada desde PyPI (tráfico de instalación aceptado).
- **Desarrollo:** `playwright==1.64.1` (Apache-2.0; 2026-10-22) con `greenlet==3.5.6` y `pyee==14.0.0`. Se eligió frente a Selenium/Cypress porque es una biblioteca Python que maneja el Chrome/Edge **ya instalado** (`channel`), sin descargar navegadores ni drivers y con espera automática. **No** entra en la imagen del producto.

### Resultados locales (no son validación con Stacker News)

| Verificación | Resultado |
|---|---|
| **P-33** (aplicación completa: Uvicorn → runtime → firmante → relay → NDK real → API HTTP → aprobación → firma), `python lab/run_product_regression.py --api` | E1, E2, E3 y E8 **PASS** (red Docker `internal`; el *driver* opera la API HTTP) |
| Regresión del servicio (`python lab/run_product_regression.py`) | E1, E2, E3 y E8 **PASS** |
| `python -m pytest -q` (Windows, Python 3.12.10) | **607 passed, 1 omitida** (la omitida es el E2E en Docker, que requiere `E2E_DOCKER=1`; con la variable: 608 passed) |
| E2E de **navegador real** (Chrome 158 vía Playwright; relay local; identidades ficticias): 7 pruebas de interfaz | PASS: cookie `HttpOnly`/`Strict`, `document.cookie` vacío, `localStorage`/`sessionStorage` vacíos, CSRF, cierre de sesión con revocación, caducidad del JWT, importación de clave sin eco, flujo completo con aprobación y rechazo desde la interfaz, reinicio limpio; sin errores de consola ni violaciones de CSP |
| E2E en **Docker con NDK 2.12.2 real** (navegador → contenedor → relay del laboratorio ← cliente NDK; `E2E_DOCKER=1`) | PASS: `connect` y `sign_event` aprobados desde la interfaz, login verificado por el cliente NDK (id, firma, reto, identidad), 1 firma, `session_end`, el código de acceso aparece una vez en el registro y nunca la URI |
| `mypy --strict app` (herramienta temporal) | Sin incidencias (28 archivos) |
| Cobertura de líneas y ramas (herramienta temporal, sin E2E) | **99 %**; todos los módulos nuevos ≥ 96 % (antes `runtime.py` estaba en 92 %: se añadieron pruebas de la rama de parada con tiempo agotado y con error inesperado) |
| `pip check`, `git diff --check` | Limpios |

### Hallazgos

| # | Hallazgo |
|---|---|
| F-13 | Playwright (API síncrona) deja un bucle de eventos activo que rompía **66** pruebas asíncronas posteriores en la misma ejecución; se corrigió con el navegador en alcance de módulo. |
| F-14 | El navegador registra en consola cada respuesta 401/400 esperada («Failed to load resource»); las pruebas E2E las excluyen y vigilan CSP y errores de JavaScript. |
| F-15 | La clave de firma del JWT solo en memoria hace que reiniciar invalide las sesiones; es deseado, pero implica volver a iniciar sesión tras cada arranque. |
| F-16 | Al montar la interfaz en `/`, una ruta `/api/...` mal normalizada cae en el servidor estático (responde 404/405 sin datos): sin efecto de seguridad. |

### Limitaciones y supuestos no verificados

- **B4 no se ha ejecutado y no se declara completado.** Tampoco la validación real de B6. Nunca se firmó con el origen real, no se observó NDK del **navegador** de Stacker News contra este firmante ni la respuesta de Stacker News a una firma válida (Y-8).
- Los E2E de navegador usan un relay local mínimo y un cliente de prueba (Python); el E2E Docker usa NDK 2.12.2 en Node (no el bundle de producción de Stacker News).
- La interfaz se probó en Chrome (Chromium); no en Firefox ni Safari. No se probó la cookie con `COOKIE_SECURE=1` en un navegador (sí a nivel de API).
- La interfaz no incluye pruebas unitarias de JavaScript; su lógica de «no aprobar con comprobaciones fallidas» está en el código y en la política del servidor (las solicitudes con fallos no se crean), no en una prueba de navegador con datos manipulados.
- Sigue sin haber *hashes* en `constraints.txt`; `mypy`/`ruff` siguen sin ser dependencias del proyecto (P-30).
- La imagen del producto con etiqueta mutable por defecto no se construyó; sí con el digest (D-6).

### Propuestas nuevas o actualizadas (pendientes)

| # | Propuesta | Estado |
|---|---|---|
| P-32 | Autorización operativa única de B4 (`docs/phase-1.0B-B4-gate.md`). | **Pendiente de autorización** |
| P-33 | Ensayo completo `uvicorn` + NDK en red interna. | **Cumplida** (`--api`) |
| P-34 | Prueba de navegador de la interfaz con datos manipulados (tarjeta con una comprobación en `false`) y en Firefox. | Pendiente (opcional) |


## Fase 1.0B, cierre de la compuerta de B4: registro de D-5 y preparación operativa (2026-11-21)

### Decisiones del propietario

| # | Decisión | Estado |
|---|---|---|
| D-5 | **Identidad Nostr nueva, dedicada y reutilizable** para la prueba de B4, generada y conservada **solo por el propietario**, fuera del repositorio y sin mostrarse en informes. Completa la instrucción de principio de O-18. | **Aprobada** |
| O-19 | **Destino de B4:** `https://stacker.news/signup`, flujo «Continue with Nostr» mediante `bunker://`, relay `wss://relay.primal.net:443`, ventana máxima de 15 minutos, **una** firma real, aprobación humana de `connect` y `sign_event`, sin ampliar la política `kind 27235`, sin reintentos automáticos de autenticación. El propietario **acepta** que se cree una **cuenta real de prueba** en Stacker News. | **Aprobada** |
| O-20 | **Esta decisión no autoriza ejecutar la demostración real.** La ventana empieza solo con la confirmación expresa del propietario. Hasta entonces: sin conexión a `relay.primal.net`, sin interacción con Stacker News, sin crear la cuenta, sin firmar eventos externos. | **Vigente** |

### Preparación realizada (sin servicios externos)

- **Compuerta** (`docs/phase-1.0B-B4-gate.md`) reescrita: decisiones registradas, alcance técnico fijado, autorización y confirmación de inicio por completar, procedimiento exacto por fases (preparación, arranque con variables de entorno de la ventana, interfaz, Stacker News, cierre), condiciones de parada, veredictos PASS/FAIL/BLOCKED y evidencia sanitizada. Ajuste de límites para respetar los 15 minutos: `SESSION_TTL_S=720`, `CONNECTION_TTL_S=720`, `APPROVAL_TTL_S=120`, `MAX_SIGNATURES=1`, `MAX_REQUESTS=30`, `JWT_TTL_S=900`.
- **Herramientas de laboratorio (no son el producto, no añaden funcionalidad a `app/`):**
  - `lab/tools/b4_identity.py`: genera la identidad **fuera del repositorio**, con permisos restringidos (`0600` o `icacls`), sin sobrescribir ni escribir dentro del repositorio, y **nunca imprime la clave privada** (solo la pública); `copy` la deja en el portapapeles sin mostrarla y `clear-clipboard` lo vacía.
  - `lab/tools/b4_check_evidence.py`: comprueba que la auditoría exportada no contiene clave `nsec`, URI `bunker://` ni secreto, JWT, cookies ni `Authorization`, hexadecimales de 64 caracteres (claves, retos, ids, firmas) ni cargas base64 largas, y resume la parte técnica (una `sign_ok`, un `session_end`). **No decide PASS**: eso lo observa el propietario en Stacker News.
  - Pruebas: `tests/lab_tools/test_b4_tools.py` (14). El verificador se contrastó con la auditoría de una sesión local real (sin fugas, resumen coherente). No se generó ninguna identidad real ni se tocó el portapapeles real.
- **Comprobación de que la aplicación sigue funcionando en local sin conexiones externas:** ver el informe de la sesión (batería de pruebas, E2E de navegador, E2E Docker con NDK real y arranque con Docker Compose, todo en `127.0.0.1` o en red Docker propia).

### Limitaciones y supuestos no verificados (sin cambios sustanciales)

- B4 **no se ha ejecutado** ni se declara completado; tampoco la validación real de B6.
- No se conoce cómo muestra Stacker News la identidad tras el inicio de sesión: si no muestra la clave pública, la coincidencia queda como **no verificable** (el criterio PASS lo contempla).
- El texto exacto de los botones de Stacker News («Continue with Nostr», opción de firmante remoto) es el indicado por el propietario; no se ha verificado en esta sesión.
- Es probable que la cuenta creada no se pueda borrar [no verificado].
- `clear-clipboard` en Windows escribe un espacio (el comando `clip` no admite entrada vacía de forma fiable).

### Propuestas

| # | Propuesta | Estado |
|---|---|---|
| P-32 | Ejecución de B4 (`docs/phase-1.0B-B4-gate.md`). | **Pendiente de autorización expresa y confirmación de inicio** |

## Fase 1.0B, B4: ejecución real y resultado (2026-11-21)

### Autorizaciones y ejecución (alcance autorizado frente a lo ejecutado)

| Concepto | Autorizado | Ejecutado |
|---|---|---|
| Servicios | `wss://relay.primal.net:443` y `https://stacker.news/signup` (navegador del propietario) | Solo esos. `relay.primal.net` desde el firmante; Stacker News solo desde el navegador del propietario. El agente no abrió Stacker News |
| Identidad | Nueva, dedicada y reutilizable, del propietario (D-5); clave pública `c5a035bf14ae…1a3f` | Esa, importada por el propietario desde la interfaz; el agente no vio la clave privada |
| Ventana 1 | 15 min desde T0 = 2026-11-20 23:53:44 (Santiago) | La aplicación se arrancó; la identidad no estaba importada y quedaban 9 min: el propietario eligió **nueva ventana**. **El firmante no se inició; ninguna conexión externa** |
| Ventana 2 | 15 min desde «iniciar ahora» | T0 = 2026-11-21 00:01:05, límite 00:16:05; firmante detenido a las **00:03:10** (2 min 5 s) |
| Firmas | Máximo 1 (`kind 27235`) con aprobación humana de `connect` y `sign_event` | **1**; ambas aprobaciones manuales del propietario (13,4 s y 7,8 s de latencia) |
| Configuración | Compuerta §5.B | `RELAY_TLS_GROUPS=X25519`, `SERVICE_ORIGIN=https://stacker.news`, `SESSION_TTL_S=720`, `CONNECTION_TTL_S=720`, `APPROVAL_TTL_S=120`, `MAX_SIGNATURES=1`, `MAX_REQUESTS=30`, `JWT_TTL_S=900` |

### Resultado de B4: **PASS** (con observaciones)

- **Auditoría sanitizada** (`lab/results/b4-20261120T235344/audit.json`, excluida de Git): `session_start` → `relay_ready` → `bunker_issued` → `connect` (NIP-04) aprobado → `get_public_key` (NIP-44) → `sign_event` con política `ok=true` (11 comprobaciones, origen visto `https://stacker.news`, antigüedad 1 s) → aprobación humana → **`sign_ok` con autoverificación** → respuesta publicada (`relay_ok=true`) → `session_end` (`detenido_por_el_operador`, 1 firma). 0 errores, 0 avisos del relay, 0 fallos de política. El verificador (`lab/tools/b4_check_evidence.py`): «Sin fugas» y resumen coherente.
- **Observación del propietario en Stacker News (no verificada por el agente):** Stacker News mostró una **sesión asociada a `@c5a035bf14…`** y el *onboarding* «Step 1 of 3 — Do you need a lightning wallet?»; no se creó ni conectó billetera y el propietario eligió «Skip for now». Es la primera vez que Stacker News acepta una firma de este firmante: **cierra la hipótesis Y-8 en el sentido favorable** (el reto no caducó, la firma se aceptó y se creó/abrió la cuenta).
- **No se infirió éxito del OK del relay:** el criterio fue la sesión observada por el propietario.

### Observaciones y límites

- La sesión de Stacker News la observó solo el propietario; no se reportó la comprobación de **persistencia al recargar** (§5.D.4 de la compuerta) ni se capturó pantalla. El *onboarding* posterior a la sesión no formaba parte de la autenticación y el propietario no proporcionó datos en él.
- Stacker News deriva el nombre de la clave pública (`@c5a035bf14…`): es coherencia con la identidad usada, pero no una verificación criptográfica independiente.
- Se creó una **cuenta real de prueba** ligada a esa clave (aceptado por el propietario); probablemente no se pueda borrar [no verificado].
- La primera ventana no llegó a iniciar el firmante por falta de tiempo (el código de acceso se copió mal dos veces): lección para el procedimiento: dejar la interfaz iniciada y la clave importada antes de abrir la ventana. Esas dos fallas (401) quedan en el registro del servidor y no suponen riesgo.
- Tras el cierre se **detuvo el servidor** (la clave desapareció de memoria) y se **borró `server.log`** por contener el código de acceso de la sesión. La clave privada y el respaldo siguen solo en poder del propietario.
- **No** se declara la validación real de B6 (repetir el inicio de sesión desde la interfaz): requiere su propia autorización.

## Cierre de la jornada del 2026-11-21 (estado y continuidad)

### Estado consolidado

B0 y B1 completados (publicados en `88b2971`). B2, B3 (con JWT, D-8), B5 y el E2E local de B6 implementados y verificados **en local**. **B4: PASS con observaciones** (ver la sección «B4: ejecución real y resultado»). **B6 real y la validación final reproducible: pendientes.** Detalle y orden recomendado en [`handoff-2026-11-21.md`](handoff-2026-11-21.md).

### Lo observado frente a lo verificado (B4)

- **Verificado por la auditoría sanitizada** (`docs/evidence/b4-audit-2026-11-21.json`, `b4-verificador-2026-11-21.txt`): una `sign_ok` con autoverificación, `connect` y `sign_event` aprobados por una persona, `session_end`, 0 errores y 0 fallos de política.
- **Observado solo por el propietario:** sesión de Stacker News asociada a `@c5a035bf14…` y *onboarding* de billetera omitido (`docs/evidence/b4-notas-2026-11-21.txt`). Sin captura ni comprobación de persistencia.

### Problemas surgidos y su resolución (resumen de la jornada)

| Problema | Resolución |
|---|---|
| `\Z` y `$` en expresiones regulares (Python y Pydantic) | `\Z` en `re`; `^…$` en patrones de FastAPI; pruebas de regresión |
| Pruebas de `/health` rotas al validar `Host` | Base de URL local en el fixture, sin cambiar las pruebas |
| Playwright síncrono rompía 66 pruebas asíncronas | Navegador en alcance de módulo |
| Fin de línea CRLF en archivos editados con Python en Windows | Normalización a LF y comprobación antes de publicar |
| Código de acceso copiado mal (dos 401) y ventana 1 sin tiempo | Nueva ventana autorizada; el firmante no se había iniciado |

### Restricciones que siguen vigentes

Sin conexiones a `relay.primal.net` ni a Stacker News sin autorización expresa y con alcance; una firma por sesión y solo `kind 27235`; aprobación humana de cada `connect` y `sign_event`; claves Nostr solo en memoria; JWT con clave aleatoria por arranque; la URI `bunker://` la emite una persona, nunca el agente; sin `git add -A`, sin `--force`; `AGENTS.md` y `CLAUDE.md` no se modifican sin autorización; las evidencias se sanean antes de conservarse.

### Qué falta para cerrar B6

Reproducibilidad desde un clon limpio; revisión final de README; nueva compuerta operativa para repetir el inicio de sesión real desde la interfaz con la misma identidad (con comprobación de persistencia); cierre documental y exportación de las transcripciones pendientes (ver `ai-log.md`).
