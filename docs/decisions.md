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

## Fase 1.0B, B6 etapa 1: reproducibilidad desde un clon limpio (2026-11-21)

Detalle, comandos y evidencia: [`phase-1.0B-B6-stage1-reproducibility.md`](phase-1.0B-B6-stage1-reproducibility.md). **Veredicto: PASS con observaciones.** Sin conexión a Stacker News ni a relays públicos; sin usar la identidad privada de B4; sin cambios de código; sin commit ni push.

### Autorización y alcance

El propietario autorizó: clonar `origin/main` (`4b9e51e`) en una carpeta temporal, instalar y ejecutar siguiendo el README, Docker Compose, pruebas (incluida la E2E local), comprobación de la interfaz y revisión de portabilidad, `.gitignore` y la prueba de navegador con una comprobación en rojo (P-34); acceso a GitHub y a registros de paquetes solo para clonar e instalar. **No** autorizó cambios de criptografía, NIP-46, JWT, autorizaciones ni flujo de firma sin consulta: no se hicieron.

### Hallazgos verificados

- Un clon limpio instala con el README y da `613 passed, 9 skipped` (8 vectores NIP-44 sin archivo y el E2E de Docker); `622 passed` con los vectores y `E2E_DOCKER=1`, igual que el equipo original. **Esos 8 tests y las imágenes de laboratorio dependían de archivos del equipo original** (no versionados).
- Docker Compose: construcción con la etiqueta mutable por defecto, contenedor `healthy`, publicado solo en `127.0.0.1`, usuario no root, sistema de archivos de solo lectura, `cap_drop: ALL`. Interfaz y operador en Chrome 158: 19/19 comprobaciones.
- El 429 al iniciar sesión se debió a peticiones 401 con la forma del sondeo de la UI recibidas antes de cualquier prueba (pestaña antigua del navegador, **inferido** del registro de acceso). Cada petición sin credenciales válidas cuenta como fallo.
- Sonda de la UI con tarjetas manipuladas: «Aprobar» queda desactivado con una comprobación en `false`; el HTML hostil se muestra como texto sin ejecutarse; un clic real o el teclado no envían nada, pero un `click` sintético de JS sobre el botón desactivado sí llega a `decide()`.

### Supuestos y límites

Una ejecución en un único equipo (Windows 11) no demuestra compatibilidad universal. Inferidos, no ejecutados: Linux/macOS fuera de Docker, equipos sin Chrome/Edge, Firefox, arm64, construcción sin caché, reconstrucción del laboratorio desde cero.

### Propuestas nuevas o actualizadas (pendientes de decisión del propietario)

| # | Propuesta | Estado |
|---|---|---|
| P-34 | Prueba de navegador **versionada** con tarjeta manipulada y en Firefox. La sonda de esta etapa dio el resultado de arriba; falta incorporarla como prueba. | Parcial: verificada con un script desechable; **sin prueba versionada** |
| P-35 | No contar como fallo la ausencia de credenciales (sonda de sesión) o no bloquear el inicio de sesión por fallos de otras rutas. Afecta a D-8. | **Pendiente de decisión** |
| P-36 | Reglas de `.gitignore` para `identity.key`, `*.key`, `*.pem`, `*.nsec`, `.nip46-b4/` y `.env.*` (con `!.env.example`); probadas en un clon descartable sin ignorar nada versionado. Texto exacto en el documento de la etapa. | **Pendiente de decisión** (`.gitignore` no se modificó) |
| P-37 | `decide()` debe ignorar `approve` si alguna comprobación es `false` (defensa en profundidad) y prueba E2E. Afecta al flujo de aprobación. | **Pendiente de decisión** |

## Fase 1.0B, B6.1A: ingreso del administrador con SQLite + Argon2id + JWT (2026-11-21)

Detalle, pruebas y resultados: [`phase-1.0B-B6.1A-local-auth.md`](phase-1.0B-B6.1A-local-auth.md). **Veredicto: PASS con observaciones.** Sin conexión a Stacker News ni a relays públicos, sin firmar eventos reales, sin usar la identidad de B4, sin commit ni push.

### Decisión del propietario (alcance de esta iteración)

Sustituir **solo** el ingreso por código temporal de la terminal por usuario y contraseña en SQLite, con JWT HS256 emitido por el backend; corregir P-35, P-36 y P-37; mantener intactos NIP-46, la criptografía Nostr y la política de firma. Autorizó instalar dependencias necesarias desde fuentes oficiales. **No** autorizó commit, push, servicios externos ni cambios sustanciales del flujo de firma («si la corrección requiere modificar el comportamiento de autorización del backend, documenta el hallazgo y detente»).

### D-9: decisiones de diseño (reemplaza **solo** el mecanismo de ingreso de D-8; el resto de D-8 se conserva)

| # | Decisión | Por qué / alternativas descartadas |
|---|---|---|
| D-9.1 | SQLite con el módulo `sqlite3` de la biblioteca estándar, confinado a `app/storage/` (consultas parametrizadas, una conexión por operación, `BEGIN IMMEDIATE` en escrituras). Se crea sola; esquema versionado con `PRAGMA user_version` | Sin dependencias nuevas para persistir. Descartado: ORM (sobreingeniería), archivo plano con hash (sin integridad ni atomicidad) |
| D-9.2 | **Argon2id** con `argon2-cffi` y el perfil RFC 9106 «low memory» (t=3, m=64 MiB, p=4, sal de 16 bytes). Hash de señuelo para igualar el costo con usuarios inexistentes | Requisito del alcance. Descartado: `hashlib.scrypt` (estándar, pero se pidió Argon2id), bcrypt (límite de 72 bytes), PBKDF2 (no memoria-dura) |
| D-9.3 | Un único administrador (`id` fijo = 1 con `CHECK`), usuario único sin distinguir mayúsculas, `password_hash` con `CHECK` de prefijo `$argon2id$` (la base rechaza texto plano) | Alcance inicial pedido. Ampliarlo exige una migración y una decisión nueva |
| D-9.4 | Administrador inicial desde `ADMIN_USERNAME` (por defecto `admin`, no secreto) y `ADMIN_PASSWORD` o `ADMIN_PASSWORD_FILE` (excluyentes). **Sin contraseña por defecto.** Sin contraseña válida y sin administrador el arranque **falla** con instrucciones. Con administrador existente no se sobrescribe ni se recrea, y la contraseña de entorno **ni se lee**. Alta atómica (`INSERT … WHERE NOT EXISTS`) | Evita cuentas débiles o silenciosas y carreras entre procesos. Descartado: pantalla pública de registro (prohibida), contraseña generada e impresa (reintroduciría el secreto en la terminal) |
| D-9.5 | El JWT conserva el formato y la semántica de D-8; lo emite el backend tras verificar credenciales. La clave HS256 sigue siendo aleatoria y en memoria (independiente de la contraseña). **El cuerpo de la respuesta de login ya no incluye el JWT** salvo `return_token: true` (clientes de línea de comandos) | Cumple «no exponer el JWT al JavaScript del navegador». Cambio de contrato de la API: se actualizaron el arnés del laboratorio y el README |
| D-9.6 | Límites **globales** y separados: intentos de login (5 en 5 min; el intento cuenta antes de verificar y se descuenta solo si tiene éxito) y tokens inválidos (20 por minuto; un token válido nunca se frena). Sin credenciales = 401 sin contar | Resuelve P-35 sin debilitar la fuerza bruta y sin depender de cabeceras del cliente. Compromiso: bloqueo del ingreso por un tercero local (P-40). Descartado: límite por IP (tras Docker todas las IP son la puerta de enlace; no confiable) |
| D-9.7 | Registro operacional mínimo en el logger `nip46.auth` (eventos y prefijos de `jti`; nunca contraseñas, hashes, usuarios, tokens ni cookies). La auditoría NIP-46 en memoria no se tocó | Distingue operacional, autenticación, auditoría NIP-46 y registros de IA |
| D-9.8 | Docker: volumen con nombre `app_data` en `/data` (único escribible; raíz de solo lectura, usuario `uid 10001`), `DATABASE_PATH=/data/nip46.db`, sin credenciales en la imagen. Etiqueta de imagen `${APP_IMAGE:-…:dev}` y documentación de `-p` para otra copia (observación de B6 etapa 1) | Corrección mínima y compatible. Descartado: renombrar el proyecto por defecto (cambio mayor; lo usan README, laboratorio y pruebas) |
| D-9.9 | `.gitignore`/`.dockerignore` con reglas específicas para identidad, secretos, SQLite y auxiliares, configuración privada y evidencias sensibles (P-36), verificadas contra los archivos rastreados y no rastreados | Sin exclusiones amplias que oculten archivos legítimos |
| D-9.10 | P-37: `decide()` rechaza `approve` si alguna comprobación está en rojo o la tarjeta es desconocida. El backend no se modificó (ver P-38) | Defensa en profundidad; el servidor sigue siendo la autoridad |

### Dependencia nueva (AGENTS.md §8; autorizada por el alcance)

| Paquete | Propósito | Alternativa estándar | Licencia | Mantenimiento | Seguridad |
|---|---|---|---|---|---|
| `argon2-cffi==25.1.0` + `argon2-cffi-bindings==26.2.0` | Hash Argon2id de la contraseña | `hashlib.scrypt` (descartada: se pidió Argon2id) | MIT (ambas) | Versiones vigentes servidas por PyPI el 2026-11-21; **no se verificó** más allá de eso | Implementación de referencia en C vía `cffi` (ya presente); fijadas en `pyproject.toml` y `constraints.txt` (sin *hashes*, como el resto) |

### Hallazgos verificados

- Antes no existía ni SQLite ni registro con `logging` en el producto; solo la auditoría NIP-46 en memoria.
- **P-35 corregido** y probado (unitarias, API y navegador). **P-36 corregido:** `git ls-files -ci --exclude-standard` vacío y todos los archivos nuevos visibles.
- **P-37 corregido en la interfaz** (prueba E2E de mutación: falla sin la guardia). En el backend: una firma que incumple la política nunca llega a la cola del operador ni se puede aprobar por la API.
- **Hallazgo P-38 (abierto):** el backend **no revalida la ventana temporal** de la política tras la aprobación humana (solo repetición y tope). Demostrado con una prueba `xfail` estricta. **No se corrigió** por tocar el flujo de firma; decisión del propietario.
- Regresión NIP-46 con NDK 2.12.2 real (servicio y API): E1, E2, E3 y E8 en PASS. Suite: 762 passed, 1 skipped, 1 xfailed (con `E2E_DOCKER=1`); copia limpia: 751 passed, 12 skipped, 1 xfailed; `mypy --strict app` limpio; cobertura 99 % (módulos de B6.1A al 100 %).

### Supuestos y límites (no verificados o aceptados)

- Probado en Windows 11 + Docker Desktop y Chrome; **no** en Linux/macOS sin Docker, Firefox ni arm64. En Windows el modo 0600 de la base no se aplica.
- La verificación «copia limpia» fue una exportación del árbol de trabajo (los cambios no están en un commit); debe repetirse con un `git clone` real.
- `ADMIN_PASSWORD` en el entorno del contenedor es visible con `docker inspect` mientras exista; se recomienda retirarla tras el primer arranque.
- Argon2id con 64 MiB por verificación no se probó en equipos con poca memoria.

### Propuestas nuevas o actualizadas

| # | Propuesta | Estado |
|---|---|---|
| P-34 | Prueba de navegador con tarjeta manipulada (Chrome) | **Cumplida** (`tests/e2e/test_browser_login.py`); Firefox **pendiente** (opcional) |
| P-35 | Bloqueo por solicitudes sin credenciales | **Corregida** (D-9.6) |
| P-36 | Reglas de `.gitignore` para identidad y secretos | **Corregida** (D-9.9; reglas ampliadas) |
| P-37 | `decide()` y aprobaciones bloqueadas por política | **Corregida en la interfaz**; backend: ver P-38 |
| P-38 | Revalidar la política completa (ventana temporal) justo antes de firmar y alinear `APPROVAL_TTL_S` ≤ `SIGNER_WINDOW_S`. Más estricto; puede denegar aprobaciones lentas | **Pendiente de decisión** (afecta al flujo de firma) |
| P-39 | Herramienta de cambio o recuperación de contraseña sin borrar la base | Pendiente (opcional; hoy se recupera borrando la base) |
| P-40 | Límite de login por origen real (exigiría un proxy de confianza) para que un tercero local no pueda bloquear el ingreso | Pendiente (opcional) |
| P-41 | Probar Argon2id en equipos con poca memoria y re-hash automático al cambiar parámetros | Pendiente (opcional) |

## Fase 1.0B, B6.1B: cierre de seguridad antes de la validación real (2026-11-21)

Detalle, pruebas y resultados: [`phase-1.0B-B6.1B-security-closure.md`](phase-1.0B-B6.1B-security-closure.md). **Veredicto: PASS con observaciones.** Sin conexión a Stacker News ni a relays públicos, sin usar la identidad de B4, sin firmas reales, sin commit ni push.

### Decisión del propietario (alcance)

Resolver P-38 revalidando la política inmediatamente antes de firmar, sin cambiar la autorización humana ni el comportamiento existente; verificar P-41 con Argon2id bajo un límite de memoria; **no** implementar P-39 ni rediseñar P-40; no cambiar parámetros de seguridad sin evidencia.

### D-10: revalidación obligatoria justo antes de usar la clave privada (cierra P-38)

| # | Decisión | Por qué / alternativas descartadas |
|---|---|---|
| D-10.1 | Tras la decisión humana, `_revalidate_and_sign` (síncrono, **sin `await`**) comprueba con el reloj de ahora: aprobación vigente y **consumida en ese instante**, firmante activo, cliente activo, **política completa** (vigencia temporal, ventana, repetición y las demás) y **vínculo** solicitud-firma. Si algo falla: `unauthorized`, ninguna firma ni evento firmado, reto sin gastar, registro seguro | Causa raíz: la política se evaluaba solo antes de pedir la aprobación y se firmaba ese resultado antiguo. Síncrono para evitar carreras. Descartado: solo repetir la comprobación de la ventana (dejaría sin cubrir aprobación vencida/consumida, firmante y cliente, y alteración) |
| D-10.2 | Vínculo `template_binding` (SHA-256 de identidad, `kind`, `created_at`, etiquetas y contenido) calculado al **ofrecer** la solicitud y comparado al firmar; se firma la plantilla re-evaluada ahora | Garantiza que lo firmado es exactamente lo aprobado |
| D-10.3 | `ApprovalRegistry.consume`: una aprobación se gasta una sola vez y **también si se rechaza** (falla de forma segura) | No se reintenta con la misma decisión; los reintentos del cliente exigen otra aprobación humana (sin aprobaciones implícitas) |
| D-10.4 | Evento de auditoría `revalidation` en la lista blanca (sin plantilla, reto, huella ni claves) | Trazabilidad sin secretos; no se tocó el resto de la auditoría |
| D-10.5 | **No** se modificó ningún límite (`SIGNER_WINDOW_S`, `APPROVAL_TTL_S`, topes) ni la política | La revalidación solo puede denegar más; la ventana efectiva de aprobación pasa a ser `SIGNER_WINDOW_S` menos la antigüedad de la plantilla |

### Hallazgos verificados

- **P-38 corregido** y probado (regresión normal + 12 pruebas de escenarios + unitarias; verificación por mutación: las 5 comprobaciones esenciales se detectan; la sexta es equivalente por redundancia).
- **P-41 verificado:** Argon2id (64 MiB) funciona con un login a la vez desde **128 MiB**, hasta 3 simultáneos desde 256 MiB y la ráfaga máxima del limitador (5) desde **384 MiB**; con 256 a 352 MiB una ráfaga de 5 verificaciones simultáneas provoca **OOM-kill** del contenedor (`exit 137`). Memoria en reposo 43 MiB. **Parámetros sin cambios.**
- Regresión: suite 783 passed, 1 skipped, 1 xfailed (con `E2E_DOCKER=1`); NDK 2.12.2 real (servicio y API) E1/E2/E3/E8 en PASS; `mypy --strict app` limpio; SQLite, JWT, cookies, CSRF y login sin regresiones.

### Supuestos y límites

- La medición de P-41 se hizo en un solo anfitrión (Docker Desktop, cgroup v2); otros pueden diferir en la memoria base.
- La verificación en copia limpia es una exportación del árbol de trabajo (no hay commit).
- Sin cambios en plataformas no probadas (Linux/macOS sin Docker, Firefox, arm64).

### Propuestas nuevas o actualizadas

| # | Propuesta | Estado |
|---|---|---|
| P-38 | Revalidar la política completa justo antes de firmar | **Corregida** (D-10) |
| P-41 | Argon2id con memoria limitada | **Verificada con hallazgo abierto**: la ráfaga de 5 verificaciones falla con 256 a 352 MiB. Alternativas **sin implementar**: A (recomendada) limitar a 1 o 2 las verificaciones Argon2id concurrentes; B documentar el mínimo de 384 MiB y fijar `mem_limit`; C bajar el costo de memoria (reduce el margen RFC 9106). Pendiente de su decisión |
| P-42 | La interfaz muestra «aprobada» en Recientes aunque la revalidación rechazara la firma (el motivo solo está en la auditoría) y su cuenta atrás usa `APPROVAL_TTL_S`, no la ventana real. Mostrar el rechazo y la ventana efectiva | Pendiente (opcional; no implementado para no ampliar funcionalidades) |
| P-39, P-40 | Sin cambios (no se implementaron en esta iteración) | Pendientes |

## Fase 1.0B, B6.1C: cierre de P-41 y P-42 (2026-11-21)

Detalle, pruebas y resultados: [`phase-1.0B-B6.1C-p41-p42.md`](phase-1.0B-B6.1C-p41-p42.md). **Veredicto: PASS** (P-41 y P-42 se cierran). Sin conexión a Stacker News ni a relays públicos, sin la identidad de B4, sin firmas reales, sin commit ni push.

### Decisión del propietario (alcance)

Evitar el OOM por verificaciones Argon2id concurrentes (una verificación activa por proceso, con espera acotada) sin cambiar los parámetros ni la fuerza bruta; y que la interfaz represente el resultado real de la firma, con una corrección mínima que reutilice el estado y la auditoría. No ampliar funcionalidades ni cambiar políticas para aprobar pruebas.

### D-11 (cierra P-41): compuerta de verificaciones Argon2id

| # | Decisión | Por qué / alternativas |
|---|---|---|
| D-11.1 | `VerificationGate`: un `Semaphore(1)` por proceso, cola de hasta 4 esperando, espera máxima de 3 s; superado, `Busy` → 503 `servicio ocupado` con `Retry-After: 2`. La verificación corre en un hilo; el cupo se libera al terminar el hilo (no al cancelarse quien espera) | Corresponde a la alternativa A de B6.1B. Descartado: bajar el costo de memoria de Argon2id (C: reduce el margen RFC 9106 sin necesidad) y solo documentar 384 MiB (B: deja el OOM posible) |
| D-11.2 | Cubre toda verificación (usuario existente o no, mismo costo); un rechazo por capacidad **libera** su reserva del limitador de intentos (no es un fallo de credenciales ni da ventaja de fuerza bruta) | Los 5 fallos reales siguen bloqueando con 429 |
| D-11.3 | **Parámetros de Argon2id sin cambios** (t=3, m=64 MiB, p=4) | No hay evidencia que lo justifique: con la compuerta no hay OOM desde 128 MiB |
| D-11.4 | Un solo proceso soportado (el semáforo es por proceso; clave JWT, sesiones y limitadores también son por proceso). Verificado: ni `Dockerfile`, ni `compose.yaml`, ni el laboratorio, ni el README usan `--workers` | Un límite global exigiría un almacén compartido (fuera de alcance) |

### D-12 (cierra P-42): resultado real de la firma

| # | Decisión | Por qué / alternativas |
|---|---|---|
| D-12.1 | `PendingRequest.outcome` (`None`/`signed`/`refused`/`failed`) y `outcome_reason` (código fijo); `status` **no cambia** y la API añade ambos campos (aditivo) | Compatibilidad. Descartado: un sistema nuevo de seguimiento o nuevos estados en `status` |
| D-12.2 | `signed` = firma producida y autoverificada; `refused` = revalidación o reto/tope; `failed` = autoverificación o sesión terminada (`finalize_unresolved`) | La entrega al relay ya se audita (`response_published`); no se añade seguimiento |
| D-12.3 | La interfaz muestra el resultado del servidor, anuncia cada transición (no el historial previo al ingreso) y el mensaje tras «Aprobar» ya no sugiere éxito. Solo códigos fijos, nunca datos de la plantilla | Corrección mínima sobre el estado y la auditoría existentes |

### Hallazgos verificados

- **P-41:** sin la compuerta, 5 verificaciones simultáneas con 256 a 352 MiB provocaban OOM-kill; con ella no hay OOM desde **128 MiB** con 1, 5 y 8 intentos simultáneos (3 rondas), y con 192, 256, 384 y 512 MiB. Pruebas de mutación: las 5 mutaciones de la compuerta se detectan.
- **P-42:** la interfaz mostraba «aprobada» aunque la revalidación rechazara la firma; ahora muestra cinco estados distintos con el motivo. 6 de 6 mutaciones (backend e interfaz) detectadas.
- Regresión: suite 815 passed, 1 skipped, 0 xfailed (con `E2E_DOCKER=1`); NDK 2.12.2 real (servicio y API) E1/E2/E3/E8 PASS; `mypy --strict app` limpio (36 archivos); cobertura 99 %.

### Supuestos y límites

«Firmada» no incluye la entrega al relay; solo un proceso; medición de memoria en un anfitrión (Docker Desktop); E2E de navegador solo en Chrome.

### Propuestas

| # | Propuesta | Estado |
|---|---|---|
| P-41 | Argon2id con memoria limitada | **Cerrada** (D-11) |
| P-42 | Mostrar el resultado real de la firma | **Cerrada** (D-12) |
| P-39, P-40 | Cambio de contraseña guiado; límite de login por origen | Pendientes (opcionales; no se tocaron) |

## Fase 1.0B, B6.1D-R3: cliente web local NIP-46 y plazo efectivo de firma (2026-11-21)

Detalle, pruebas y resultados: [`phase-1.0B-B6.1D-R3-web-client.md`](phase-1.0B-B6.1D-R3-web-client.md). Diagnóstico previo: [`phase-1.0B-B6.1D-diagnosis-and-proposal.md`](phase-1.0B-B6.1D-diagnosis-and-proposal.md). Sin conexión a Stacker News ni a relays públicos, sin la identidad de B4, sin commit ni push.

### Decisiones aprobadas por el propietario

1. Cliente **NDK 2.12.2 real en Node**, reutilizando la imagen de laboratorio existente. 2. El firmante muestra el **plazo efectivo** restante para firmar, distinto del TTL de aprobación. 3. Demostración con **ventana de firma 45 s y TTL de aprobación 120 s**, solo en local. 4. `lab/manual/local_client.py` se **conserva** como herramienta técnica. 5. Limpieza de las pruebas Docker **sin borrar volúmenes preexistentes**.

### D-13: cliente web de laboratorio

| # | Decisión | Por qué / alternativas |
|---|---|---|
| D-13.1 | Servicio Node (`lab/manual/client_web/`) en `nip46-lab-node:1.0a` con NDK real; la página no hace criptografía. Las operaciones usan `rpc.sendRequest` de NDK (el atajo `event.sign()` solo devuelve la firma y no permite verificar el evento completo) | Descartado: cliente propio en Python (probaría nuestro protocolo contra sí mismo) y bundle de NDK para el navegador (build nuevo, dependencias nuevas) |
| D-13.2 | «Firmada» solo tras verificar: id, BIP-340, identidad declarada en `get_public_key`, plantilla y reto idénticos; una respuesta tardía nunca es éxito | Cumple «no aceptar una respuesta sin comprobar su contenido» |
| D-13.3 | El cliente **no puede aprobar** y **no alcanza al firmante**: dos redes (`signer_net`, `client_net`) con el relay en ambas; sin credenciales, cookies ni rutas del firmante | La aprobación humana existe solo en el panel del firmante |
| D-13.4 | Solo relays locales, Host/Origin/cabecera propia/token por sesión, sin CORS, CSP estricta, URI y claves solo en memoria, registro redactado | Aislamiento y no fuga de secretos |
| D-13.5 | Fuera del producto: vive en `lab/manual/` (Compose de laboratorio); no está en `Dockerfile`, `compose.yaml` ni `.dockerignore` | Prueba estática |

### D-14: plazo efectivo de firma en el firmante

| # | Decisión | Por qué / alternativas |
|---|---|---|
| D-14.1 | `sign_deadline = created_at + SIGNER_WINDOW_S + 1` (instante exclusivo desde el que la política rechaza) y `sign_expires_in_s` (floor, no sobreestima) en `/api/requests`, solo en firmas pendientes. Solo lectura: no cambia política, revalidación, límites ni autorización | La política acepta mientras `int(ahora) − created_at ≤ ventana` |
| D-14.2 | La tarjeta muestra «Plazo efectivo para firmar» = el menor entre ventana y aprobación, ambos datos y, al vencer, «Ya no puede firmarse» con el botón rotulado «Aprobar (ya no firmará)». **El botón no se desactiva** | El servidor es la autoridad y la revalidación P-38 debe poder demostrarse (aprobar fuera de plazo → «Rechazada al firmar»); desactivarlo podría bloquear algo que el servidor aún acepta por redondeo de reloj. Descartado: desactivarlo |
| D-14.3 | Demostración: ventana 45 s, TTL 120 s (variables `MANUAL_*` en el Compose de laboratorio); el producto conserva sus valores por defecto | No se amplía ninguna ventana del producto |

### Limpieza Docker (decisión 5)
La única fuga (`docker rm -f` en `test_docker_argon2_memory.py`) pasó a `docker rm -fv`. No se ejecutó `docker volume prune` ni se borró ningún volumen; los 55 volúmenes anónimos antiguos de pruebas anteriores quedan a la espera de su decisión.

### Hallazgos verificados
- 842 passed, 1 skipped con `E2E_DOCKER=1`; 818 passed, 25 skipped sin Docker (estable en 3 ejecuciones); regresión NDK real E1/E2/E3/E8 en PASS; `mypy --strict app` limpio; cobertura 99 %.
- 14 de 14 mutaciones detectadas (verificador, servidor, contador).
- Dos pruebas propias corregidas: `test_the_deployment_runs_a_single_process` (no contemplaba la advertencia del README sobre `--workers`) y la aprobación tardía real del navegador (ventana de 2 s intermitente → 5 s).

### Supuestos y límites
Cliente de laboratorio, no cliente general; Chrome y Docker Desktop en Windows; el cliente ve un `unauthorized` genérico (el motivo está en el firmante); la validación manual del propietario está **pendiente**.

### Propuestas
| # | Propuesta | Estado |
|---|---|---|
| P-43 | Listado de solo lectura de los volúmenes anónimos antiguos que contengan únicamente `nip46.db` con usuarios de prueba, para que el propietario decida su borrado | Pendiente (opcional) |
| P-39, P-40 | Sin cambios | Pendientes (opcionales) |

## Fase 1.0B, B6.1D cierre y preparación de B6.2 (2026-11-21)

Detalle: [`phase-1.0B-B6.1D-closure.md`](phase-1.0B-B6.1D-closure.md) y [`phase-1.0B-B6.2-plan.md`](phase-1.0B-B6.2-plan.md). Solo documentación: sin cambios de código, sin conexiones externas, sin uso de la identidad de B4, sin commit ni push.

### Decisión del propietario
La validación local B6.1D-R3 **se conserva permanentemente** (no se reemplaza ni se elimina el cliente web local) y se añade una segunda validación de interoperabilidad real con Stacker News (B6.2). El propietario declaró **7 de 7 comprobaciones manuales en PASS**.

### D-15: documentación de B6.1D y B6.2
| # | Decisión | Por qué / alternativas |
|---|---|---|
| D-15.1 | **Dos matrices independientes**: A (local, B6.1D: PASS) y B (externa, B6.2: pendiente). Los resultados externos se distinguen en conexión, solicitud recibida, aprobación humana, firma producida y verificada, respuesta publicada en el relay y autenticación aceptada por Stacker News | Evita presentar una prueba local o un `relay_ok` como validación real |
| D-15.2 | **B6.2 no es PASS porque el firmante genere una firma**: exige además la observación del propietario en Stacker News y la persistencia al recargar | Lección de B4 (relay OK ≠ sesión aceptada) |
| D-15.3 | El PASS manual local es una **declaración del propietario**; la auditoría sanitizada (`docs/evidence/b6.1d-r3-manual-audit-2026-11-21.txt`) es evidencia **corroborante**, no sustituta. La correspondencia de A1–A7 con los siete puntos del propietario es del agente y se marca como tal | No atribuir al propietario detalles que no transcribió |
| D-15.4 | B6.2 se propone con `python -m uvicorn` en `127.0.0.1:8001` abierto como `localhost`, base `data/b62.db` y cuenta propia, con los límites de B4 (ventana ≤ 15 min, 1 firma, `SESSION_TTL_S`/`CONNECTION_TTL_S` 720, `MAX_REQUESTS` 30) | El `compose.yaml` no reenvía `CONNECTION_TTL_S`, `MAX_REQUESTS` ni `SIGNER_WINDOW_S`; la cookie es por host, no por puerto, y así no se pisa la demostración local |

### Decisiones posteriores del propietario (2026-11-21) y precondiciones
1. Ejecutar B6.2 en `localhost:8001` con Uvicorn, siempre que no afecte la base, las credenciales, los volúmenes ni las sesiones de B6.1D (**verificado**, plan §14). 2. El agente puede hacer consultas de **solo lectura** para diagnosticar; no puede aprobar solicitudes, firmar ni manipular credenciales (por eso **no** consulta `/api/audit`, que exige la contraseña de B6.2: la auditoría la exporta el propietario). 3. Se autoriza **preparar** una captura redactada del resultado en Stacker News. 4. La validación local B6.1D y sus herramientas se conservan íntegras. 5. La validación en Ubuntu queda **para el final**, tras completar B6.2, cerrar pruebas, documentar y publicar.
Precondiciones comprobadas en local, sin red externa y sin código nuevo (plan §14): base, contraseña y JWT de B6.2 separados de los de la demostración; variables efectivas correctas; política compatible con una firma `kind` 27235; ventanas suficientes (B4: 13,4 s y 7,8 s de aprobación frente a 120 s); sin cambios de código ni permisos. Pendiente de verificar solo por el propietario: sincronización del reloj y el valor de `u` en `/login`.

### Estado de la autorización
**B6.2 NO está autorizada.** Faltan, entre otros, la confirmación del propietario de servicios, relay exacto, identidad, operaciones, duración, restricciones, destino y fecha de inicio (formulario de §13 del plan). No se autorizó: conexiones externas, uso de la identidad privada de B4, firmas reales, commit, push.

### Supuestos no verificados
- El destino `https://stacker.news/login` (B4 usó `/signup`) y que el flujo «Continue with Nostr» con bunker siga igual: lo confirma el propietario al abrirlo; si no, se detiene la prueba.
- Que la comprobación de `Host` del firmante acepte `localhost:8001` (puerto distinto): se verifica en el arranque local previo, sin red externa.
- La cuenta de Stacker News asociada a la identidad de B4 sigue existiendo.

### Propuestas
| # | Propuesta | Estado |
|---|---|---|
| P-43, P-39, P-40 | Sin cambios | Pendientes (opcionales) |

## Fase 1.0B, B6.2: Docker Compose como entorno principal (2026-11-21)

Detalle operativo: [`phase-1.0B-B6.2-plan.md`](phase-1.0B-B6.2-plan.md) §17. Etapa 1 de la transición: **solo configuración, documentación y pruebas**; sin cambios en `app/`, sin detener contenedores, sin migrar la base, sin reconstruir imágenes, sin commit ni push, sin T0 y sin conexiones externas.

### D-16: Docker Compose es el entorno principal y obligatorio de ejecución del producto
| # | Decisión | Por qué / alternativas |
|---|---|---|
| D-16.1 | **Docker Compose** es el entorno principal de desarrollo, validación e integración y de despliegue final. **Sustituye** la decisión del propietario del 2026-11-21 de ejecutar B6.2 con Uvicorn en `localhost:8001` (D-15.4) | Un único código fuente y **una única instancia activa** del producto, sin un laboratorio paralelo permanente. Alternativa descartada: Uvicorn en Windows como entorno principal (más rápido de editar, pero distinto del entregable y sin el aislamiento del contenedor) |
| D-16.2 | `compose.yaml` reenvía `SIGNER_WINDOW_S`, `SECRET_TTL_S`, `CONNECTION_TTL_S`, `MAX_REQUESTS`, `MAX_PENDING` y `COOKIE_SECURE` (vacío = valor por defecto). **No** reenvía `RELAY_ALLOW_INSECURE` ni `ADMIN_PASSWORD_FILE` | Sin reenvío, Docker habría validado límites distintos de los del plan (1800 s y 60 solicitudes en lugar de 720 s y 30). `ws://` queda imposible en el producto en Docker; el archivo de contraseña no se monta |
| D-16.3 | `deploy/b62.env` es un **perfil específico de validación**, no la configuración definitiva; se aplica con `--env-file` (sustituye al `.env` local) y no contiene secretos | Reproducibilidad de la prueba sin depender de un `.env` personal. Alternativa descartada: editar los valores por defecto del producto |
| D-16.4 | La base se reutiliza con `deploy/import_admin_db.py`: origen de solo lectura, destino creado con `O_EXCL` (sin sobrescritura ni opción de forzar), copia con la API de respaldo de SQLite, comprobación de integridad, esquema, administradores, propietario (`uid 10001`) y permisos (`0600`/`0700`), SHA-256 del origen antes y después, sin red, sin leer ni imprimir credenciales | Evita exponer la contraseña (`ADMIN_PASSWORD` sería visible con `docker inspect`) y conserva el administrador. Alternativas descartadas: montaje *bind* de `data/` (permisos y bloqueo de SQLite distintos entre Windows y Ubuntu) y copia de archivo (no consistente) |
| D-16.5 | Puerto **8001** durante B6.2; el 8000 será el predeterminado del producto después | Coherencia con el plan y con las cookies por nombre de host |
| D-16.6 | La demostración B6.1D se detiene con `stop` (reversible; nunca `down`, `-v` ni `prune`) **solo cuando el propietario lo confirme en la etapa siguiente**; sus evidencias y las de la primera ventana de B6.2 se conservan | `docker volume prune` podría alcanzar volúmenes ajenos (`magento246_appdata`) |
| D-16.7 | Antes de T0 se comprueban, solo en lectura, los valores efectivos y de seguridad **dentro** del contenedor, la ausencia de sockets salientes y de eventos del relay, y el reloj del contenedor | El arranque no abre conexiones externas por construcción (el relay solo se contacta desde `runtime.start()` por la API autenticada), y además se verifica |

### Supuestos no verificados (D-16)
- Que el contenedor alcance el relay público con TLS (`X25519`) desde Docker Desktop: **no verificable sin red externa**; el propietario no autorizó una prueba de conectividad previa.
- Que la imagen que se use coincida con el código actual de `app/`: se comprobará por hash; si difiere, la reconstrucción exige autorización (contacta Docker Hub y PyPI).
- Que el reloj de la VM de Docker coincida con el de Windows: se comprueba antes de T0.
- Que la validación en Ubuntu reproduzca los mismos resultados: pendiente (el volumen con nombre, el digest multiarquitectura y los comandos en bash están previstos).

### Resultado de esta etapa (automatizado, no es validación de B6.2)
`pytest -m "not e2e"`: 808 passed, 1 skipped, 50 deselected; E2E Docker nueva (`tests/e2e/test_docker_b62_profile.py`, con la imagen local existente, sin construir ni descargar): 1 passed. `mypy` no está instalado en el entorno (P-30): **no se ejecutó**. No se ejecutaron `tests/e2e/test_docker_persistence.py`, `test_docker_argon2_memory.py` ni `test_docker_ndk.py` (construyen imágenes: requieren acceso a Docker Hub o PyPI, sin autorizar).

| # | Propuesta | Estado |
|---|---|---|
| P-44 | Reconstruir la imagen del producto desde el árbol actual si el hash de `app/` difiere de la imagen local | Pendiente de autorización (acceso a Docker Hub y PyPI) |
| P-45 | Fijar `PYTHON_IMAGE` por digest multiarquitectura (D-6) para la entrega final y la validación en Ubuntu | Pendiente de decisión |
| P-46 | Pasar el puerto predeterminado del producto a 8000 y retirar la demostración B6.1D tras B6.2 | Pendiente (después de B6.2) |

## Fase 1.0B: modo continuo del firmante y trazabilidad de IA (2026-11-22)

Detalle de las interacciones: `docs/ai-log.md`, entradas 42 a 47. **Requerimiento del propietario (definitivo):** que el evaluador pueda usar el firmante NIP-46 **desde la interfaz web**, sin comandos de terminal para abrir ventanas de trabajo ni para gestionar sesiones, conexiones o aprobaciones (la terminal solo sirve para la configuración inicial y el arranque de Docker). **Se mantiene la aprobación humana individual de cada `connect` y de cada `sign_event`, incluido `kind 27235`. No existe ni existirá firma automática, concesión `auto_sign` ni aprobación implícita.** Todas las operaciones del evaluador (crear o importar identidad, iniciar y detener el firmante, emitir la URI bunker, aprobar o rechazar) **ya existían en la interfaz web**; lo que obligaba a repetir pasos eran los límites automáticos del firmante.

### D-17: decisiones aprobadas por el propietario
| # | Decisión | Estado |
|---|---|---|
| D-17.1 | `SIGNER_MODE=continuous` es el valor **predeterminado**, de forma coherente en `Settings()`, `Settings.from_env()` y Docker Compose | **Aprobada e implementada** (Paso 1) |
| D-17.2 | `deploy/b62.env` fija explícitamente `SIGNER_MODE=supervised`; el modo `supervised` conserva su comportamiento y sus límites (`MAX_SIGNATURES=1`, `SESSION_TTL_S`, `MAX_REQUESTS`, sin reintentos) | **Aprobada e implementada** (Pasos 1 y 2; sin regresiones) |
| D-17.3 | **Sin firma automática**: se retiró la propuesta de concesiones por conexión y la variable `AUTO_SIGN_PER_HOUR` (corrección de alcance del propietario) | **Aprobada e implementada** (Paso 1b; una prueba garantiza que no existe ningún campo ni variable de firma automática) |
| D-17.4 | Plazos por defecto del modo continuo: `SECRET_TTL_S=300`, `CONNECTION_TTL_S=28800`, `APPROVAL_TTL_S=300` (supervisado: 600, 1800 y 120); una variable explícita siempre los reemplaza | **Aprobada e implementada** (configuración) |
| D-17.5 | Ciclo de vida continuo: el runtime conserva clave de transporte, conexiones y registros anti-replay (acotados en tamaño y vigencia); sin parada por `SESSION_TTL_S`; un fallo **recuperable** del relay conserva las conexiones; detención manual o cualquier otro fin las revoca y limpia el estado; los retos firmados se recuerdan tras una detención manual mientras no cambie la identidad (cambiarla lo descarta todo); reiniciar el proceso no recupera nada | **Aprobada e implementada** (Paso 2) |
| D-17.6 | **Opción A**: en modo continuo **no hay tope total de firmas por sesión** (cada firma exige aprobación humana). `MAX_REQUESTS`, `MAX_SIGNATURES` y `SESSION_TTL_S` solo se aplicarán en supervisado, **en el mismo paso** en que estén implementados y probados sus sustitutos: `REQUESTS_PER_MIN=30` por conexión y un límite global de 120 solicitudes por minuto, ambos sin detener el firmante ni revocar | **Aprobada e implementada** (Componente 3, 2026-11-22): `REQUESTS_PER_MIN` por conexión (ventana móvil de 60 s, solo clientes ACTIVOS identificados por la firma) y 120 globales por minuto (antes de verificar la firma o descifrar, a todo mensaje); al superarlos se descarta sin detener ni revocar; `MAX_REQUESTS`, `MAX_SIGNATURES` y `SESSION_TTL_S` solo rigen en supervisado |
| D-17.7 | Reconexión automática acotada al relay, solo en modo continuo, con esperas de 2, 5, 10, 20 y 40 s, conservando conexiones, clave de transporte y registros anti-replay; sin reconexión tras detención manual ni ante errores permanentes (AUTH, suscripción cerrada, configuración TLS); un supervisor único en `SignerRuntime` | **Aprobada e implementada** (Componente 2): supervisor único en `SignerRuntime`, transporte nuevo por intento, 5 intentos con esperas de 2, 5, 10, 20 y 40 s, `FAILED` con `reconexion_agotada` y conexiones conservadas |
| D-17.8 | Revocación individual de conexiones con identificadores opacos y aleatorios (`DELETE /api/connections/{id}`, JWT y CSRF, 404 si el id no es del runtime activo) y botón «Revocar» en la interfaz. **La renovación de conexiones queda fuera de alcance**: al caducar, se empareja de nuevo desde la interfaz | **Aprobada e implementada** (Componente 1): `DELETE /api/connections/{id}` con 200, 404, 409 y 422, cancelación de pendientes, auditoría `connection_revoked` y botón «Revocar» |
| D-17.9 | No se persisten claves privadas ni conexiones: reiniciar el proceso exige volver a cargar la identidad (debe quedar documentado) | **Aprobada**; documentación en el Paso 6 |
| D-17.10 | La experiencia del evaluador por la interfaz web (identidad temporal como camino principal del README, importación como alternativa) y Docker como mecanismo principal | **Aprobada**; README en el Paso 6 |
| D-17.11 | La validación real con Stacker News se hará con la **versión final** en Docker y **no** con la imagen `manual-b61d` (que queda obsoleta para ello) | **Aprobada y ejecutada el 2026-11-22** (PASS confirmado por el propietario; ver «Resultado de la validación real con la versión final») |
| D-17.12 | **Trazabilidad de IA**: las transcripciones se exportan al cierre de cada Paso o bloque autorizado (no solo de cada fase) y se verifican antes de cada commit y de la publicación final con un **comando explícito** (`python tools/ai_sessions.py check`); **no se instalan hooks de Git**. Se modificaron de forma mínima y solo documental `AGENTS.md` §9 y `CLAUDE.md` | **Aprobada e implementada** (interacción 47) |

### Estado real de la implementación (2026-11-22)
| Bloque | Estado |
|---|---|
| Paso 1 (configuración) y Paso 1b (retiro de `AUTO_SIGN_PER_HOUR`) | **Completos y probados** |
| Paso 2 (estado y ciclo de vida) | **Completo y probado** (40 pruebas nuevas y 10 mutaciones detectadas) |
| Pasos 3 a 5, componente 1 (revocación individual) | **Completo y probado** |
| Pasos 3 a 5, componente 2 (reconexión) | **Completo y probado** (con relays y esperas simulados y un E2E de navegador con un relay local que se mata y se reinicia) |
| Pasos 3 a 5, componente 3 (límites de frecuencia y continuidad) | **Completo y probado** |
| Paso 6 (reconstrucción y validación local de Docker, ampliación de autorización) | **Completo y probado en local** (no es validación real con Stacker News): imagen `nostr-nip46-remote-signer:d17-continuous`, perfil `deploy/continuous.env`, contenedor local sustituido conservando el volumen y la imagen `manual-b61d` (vía de recuperación: `deploy/b62.env`); detalle y evidencias en la entrada 48 de `docs/ai-log.md` |
| README y perfiles de despliegue para el evaluador | **Implementados** el 2026-11-22 (D-18: `deploy/demo.env` y «Inicio rápido» del README); **pendiente** la prueba de clon limpio |

### Resultado de la validación real con la versión final (2026-11-22)
Segunda autenticación real con Stacker News, la primera con la **versión definitiva** (modo continuo, imagen `nostr-nip46-remote-signer:d17-continuous`, perfil `deploy/continuous.env`, interfaz local `http://127.0.0.1:8001`). **Veredicto: PASS declarado y confirmado personalmente por el propietario** el 2026-11-22.

| Lo que **confirmó el propietario** | Lo que **NO está respaldado por evidencia técnica** (no verificado por el agente ni capturado) |
|---|---|
| La prueba real con Stacker News fue exitosa | Instantes de inicio y fin y duración |
| El firmante NIP-46 permitió completar la autenticación real desde la interfaz web | Clave pública usada (se indicó la identidad de prueba B4, no se verificó) |
| | Número de firmas emitidas y si se respetó el máximo de una |
| | Aprobación individual y manual de cada `connect` y `sign_event` (la política lo exige y las pruebas lo cubren, pero no hay registro de esta ejecución) |
| | Auditoría sanitizada de la sesión (vive en memoria; no se exportó antes de cerrar la jornada) |
| | Cumplimiento de las condiciones de la autorización (ventana, destino exacto, relay) y estado final del firmante (una comprobación mostró una conexión saliente abierta, es decir, probablemente seguía iniciado) |

Consecuencias: (1) cumple el criterio funcional de `AGENTS.md` §3 **según el propietario**, pero sin evidencia reproducible; (2) el supuesto «que el contenedor alcance el relay público con TLS desde Docker Desktop» queda **respaldado indirectamente** por el éxito declarado, no verificado; (3) el supuesto «que Stacker News reutilice su clave de cliente en inicios posteriores» **sigue sin verificar**; (4) si se quiere una evidencia sólida hace falta repetir con captura sanitizada de la auditoría y autorización expresa nueva. D-17.11 queda **ejecutada**.

### Propuestas y decisiones de implementación de la IA **sin aprobación expresa** (siguen pendientes)
| # | Propuesta | Estado |
|---|---|---|
| P-47 | En modo continuo, un cliente **revocado o caducado** podría emparejarse de nuevo con su **misma** clave de cliente (con una URI nueva y la aprobación humana de siempre; nunca recuperaría automáticamente la autorización anterior). El propietario considera aceptable ese criterio, pero **no** la ha aprobado formalmente | **Pendiente; NO implementada** (la regla estaba escrita en el código del componente 1 y se **retiró**; hoy un cliente revocado o caducado solo se empareja con una clave de cliente nueva; una prueba lo fija) **Análisis nocturno (2026-11-22): NO bloquea la entrega; no se implementa** (cambia la máquina de estados de `connect`, sensible para la seguridad, y no se sabe si Stacker News reutiliza su clave de cliente: si genera una nueva por inicio de sesión, no hace falta). Riesgo aceptado: tras revocar o caducar hay que usar una clave de cliente nueva. Ver D-19.3 |
| P-48 | Control contra abuso para remitentes **no autorizados** o desconocidos (límite propio de 10 solicitudes por minuto por remitente, con almacenamiento acotado), además del global de 120 y el de 30 por conexión | **Pendiente; NO implementada**. Cubierto en parte por el límite global (antes de descifrar y a todo mensaje, válido o no). **Riesgo conocido**: sin ella, un remitente desconocido puede agotar el presupuesto global y retrasar a los clientes legítimos hasta que avance la ventana (no revoca ni detiene nada; hay una prueba que lo documenta) **Análisis nocturno (2026-11-22): NO bloquea la entrega; no se implementa.** Un límite propio por remitente no resolvería el riesgo descrito, porque el límite global se cuenta **antes** de identificar al remitente (hay que descifrar para saberlo); solo recortaría las respuestas `unauthorized`. Riesgo aceptado y documentado. Ver D-19.4 |
| P-49 | Mostrar en el panel el estado de reconexión («Reconectando, intento n de 5») y el motivo de agotamiento | **Implementada (2026-11-22, commit local `1933ec7`)**: el estado expone `reconnect_attempt` y `reconnect_max` solo mientras se reconecta y el panel muestra «Reconectando, intento n de 5»; el motivo de agotamiento ya se mostraba. Pruebas de regresión incluidas |

### Supuestos no verificados (D-17)
- Que Stacker News reutilice su clave de cliente NIP-46 en inicios de sesión posteriores; si crea una nueva cada vez, cada inicio de sesión exigirá emitir otra URI y aprobar otro `connect`. Solo se observó **un** inicio de sesión real (B4).
- Que el contenedor alcance el relay público con TLS desde Docker Desktop (no verificable sin red externa; no se autorizó una prueba previa).
- Que el reloj de la máquina virtual de Docker coincida con el de Windows (subpaso 3.5, no ejecutado).
- Nada de D-17 ha sido validado contra Stacker News: **las pruebas son automatizadas (con dobles y relays locales), no validación real**.

## Fase 1.0B: perfil de demostración para evaluadores (2026-11-22)

### D-18: perfil `deploy/demo.env` con credenciales de demostración públicas (excepción acotada a D-9)
Autorizada expresamente por el propietario el 2026-11-22. El proyecto será evaluado por terceros a partir de un repositorio público y el evaluador debe poder levantarlo con Docker Compose y usarlo **completamente desde la interfaz web**, sin PowerShell, sin scripts auxiliares y sin un asistente de IA. D-9 (sin contraseña por defecto) obligaba a definir `ADMIN_PASSWORD` por la terminal antes del primer arranque, y sin ella el contenedor se detenía y se reiniciaba en bucle.

| # | Decisión | Estado |
|---|---|---|
| D-18.1 | Se versiona `deploy/demo.env` con `ADMIN_USERNAME=evaluador` y una contraseña de **demostración pública a propósito** (27 caracteres, generada con `secrets`, **sin relación** con ninguna contraseña personal, de otro servicio ni con la del entorno B6.2; cumple la política de la aplicación). Es la **única** excepción a D-9 y **no** a `AGENTS.md` §7 en sus demás reglas: no hay claves privadas Nostr, JWT, tokens ni secretos reales en el repositorio | **Aprobada e implementada** |
| D-18.2 | **La excepción se limita al perfil.** El código no tiene ningún valor por defecto de contraseña (`Settings`, `compose.yaml`, `.env.example` y los demás perfiles siguen sin contraseña) y el perfil solo se activa cuando el evaluador lo selecciona con `--env-file deploy/demo.env`. Una prueba comprueba que la contraseña no aparece en ningún otro archivo de configuración | **Aprobada e implementada** |
| D-18.3 | Contenido del perfil: imagen `nostr-nip46-remote-signer:evaluation` (etiqueta propia, no pisa `dev`, `manual-b61d` ni `d17-continuous`), `APP_PORT=8000` (publicado solo en `127.0.0.1`), `JWT_TTL_S=3600` (máximo permitido, para no pedir el ingreso cada 15 minutos con un firmante continuo), `SIGNER_MODE=continuous`, relay `wss://relay.primal.net`, **`RELAY_TLS_GROUPS=X25519`** (el mismo ajuste que usaron B4 y la validación continua para el relay real; no estaba en la lista de la autorización, se añadió por necesidad técnica) y origen `https://stacker.news` | **Aprobada e implementada** |
| D-18.4 | **Aislamiento:** el comando documentado usa el proyecto Docker propio `nip46-evaluacion` (volumen `nip46-evaluacion_app_data`), distinto del de B6.2 (`nostr-nip46-remote-signer`, volumen `nostr-nip46-remote-signer_app_data`), que no se toca | **Aprobada e implementada** |
| D-18.5 | **Restablecer desde cero** (`down -v`) se documenta solo como operación **destructiva y excepcional**, con proyecto y volumen identificados explícitamente, nunca como paso rutinario | **Aprobada e implementada** |
| D-18.6 | Advertencias obligatorias (README y el propio perfil): solo para evaluación local; no usar en producción; no exponer el puerto a otras máquinas ni a Internet con estas credenciales; usar otra contraseña en cualquier otro despliegue | **Aprobada e implementada** |
| D-18.7 | La clave privada Nostr sigue viviendo solo en memoria (D-3): tras reiniciar el contenedor el evaluador crea o importa la identidad de nuevo. No se usa la identidad de B4 como identidad del evaluador. **No se persisten claves** | **Aprobada** (sin cambios de código) |

**Riesgos y mitigaciones.** (1) *Credencial pública:* el puerto se publica solo en loopback, la aplicación comprueba `Host` y el `Origin` del login, la cookie es `HttpOnly` + `SameSite=Strict`, hay límite de intentos (5 por 5 minutos) y, sobre todo, **cada `connect` y cada `sign_event` siguen exigiendo la aprobación humana individual en la interfaz**: conocer la contraseña no permite firmar sin una persona. (2) *Uso fuera de la demostración:* avisos en el perfil, el README y `.env.example`. (3) *Volumen preexistente:* si ya existe un volumen del proyecto, la contraseña del perfil se **ignora** (D-9: no se sobrescribe la cuenta existente). **No se modificó código funcional.**

**Supuestos no verificados (D-18).** (1) Que el flujo de Stacker News descrito en el README (`/signup` o `/login?type=nostr` → «Continue with Nostr» → *bunker*) siga siendo el vigente: procede de la observación de B4 y del análisis del código de Stacker News, no de una prueba nueva. (2) Que `docker compose up --build` reproduzca la imagen en un clon limpio: depende de que el repositorio publicado incluya todos los archivos del producto (hoy hay archivos sin rastrear; ver el informe de la tarea) y se comprobará en la prueba de clon limpio, **pendiente**. (3) Nada de D-18 se ha validado contra Stacker News.

**Verificación de clon limpio (2026-11-22, fuera del alcance de D-18 pero relacionada).** Clon desde GitHub en un directorio temporal: instalación según el README sin errores, `python -m pytest` **1029 passed, 35 skipped, 0 failed**, construcción Docker con el perfil demo (incluida una **sin caché**) con recursos exclusivos de la prueba, inicio de sesión con las credenciales del README correcto, identidad temporal sin exposición de claves, sin conexiones externas del firmante. Los recursos de la prueba se eliminaron tras comprobar su pertenencia y el entorno B6.2 no cambió. **No** se probó el flujo con Stacker News. Detalle y hallazgos en `docs/NIGHTLY-REVIEW.md`. El supuesto (2) de D-18 («que `up --build` reproduzca la imagen en un clon limpio») queda **verificado** para el estado publicado en `70b4481`.


## Fase 1.0B: ajustes de la jornada nocturna autónoma (2026-11-22)

### D-19: decisiones tomadas sin supervisión dentro de la autorización nocturna
Autorizadas por el propietario para instalaciones nuevas, con la política «opción conservadora y documentar el criterio». **No** cambian el entorno B6.2 (puerto 8001, volumen, base, credenciales, contenedor), ni la criptografía, ni la aprobación manual. Todo quedó en commits **locales**, sin push.

| # | Decisión | Estado |
|---|---|---|
| D-19.1 | **El firmante de la demostración de laboratorio deja el puerto 8000** y pasa al **18000** mediante el perfil propio `lab/manual/manual.env` (`APP_PORT=18000`, `ADMIN_USERNAME=admin-manual`, sin secretos). Puertos definitivos: 8000 evaluación, 8001 validación real del propietario, 18000 firmante de laboratorio, 18080 cliente NIP-46 de laboratorio, 17777 relay local. La interfaz del firmante (`app/static/`) y el cliente de laboratorio (`lab/manual/client_web/`) siguen siendo aplicaciones distintas; el cliente no entra en `compose.yaml`; no se duplican instancias del firmante (una por proyecto Docker) ni se comparten bases. Alternativas descartadas: mover el perfil de evaluación a otro puerto (el 8000 ya es el valor por defecto documentado) o fusionar el laboratorio en `compose.yaml` (mezcla producto y laboratorio) | **Implementada** (commit local `4f2c112`); prueba que impide repetir un puerto entre perfiles |
| D-19.2 | **P-49 se implementa** (contador «intento n de 5»): cambio acotado y de bajo riesgo en el estado y la interfaz; no toca esperas, límites, aprobaciones ni protocolo | **Implementada** (commit local `1933ec7`) |
| D-19.3 | **P-47 no se implementa.** Criterio: no bloquea la entrega, modifica el emparejamiento (sensible) y depende de un supuesto sin verificar (si Stacker News reutiliza su clave de cliente). Requiere aprobación formal del propietario. Alternativa documentada si hiciera falta: permitir un nuevo `connect` con la misma clave solo con URI nueva y aprobación humana, nunca recuperando la autorización anterior | **Pendiente de decisión del propietario** |
| D-19.4 | **P-48 no se implementa.** Criterio: el límite global (120/min) se cuenta antes de descifrar, así que un límite por remitente no impide agotarlo; la mitigación real exigiría filtrar en el relay o identificar antes de descifrar. Riesgo aceptado: un remitente desconocido puede retrasar a clientes legítimos hasta que avance la ventana de 60 s; no revoca ni detiene nada | **Riesgo aceptado; pendiente de decisión** |
| D-19.5 | **`.dockerignore` reduce el contexto de construcción** (`deploy/`, `docs/`, `lab/`, `tests/`, `tools/`): la imagen solo copia `app/` y tres archivos; los perfiles con la credencial de demostración pública y las transcripciones ya no viajan al daemon. Defensa en profundidad, sin efecto en la imagen | **Implementada** (commit local `2ffd56b`) |
| D-19.6 | **Hallazgos de seguridad que NO se corrigieron** por requerir una decisión del propietario o un cambio de arquitectura: correo de autoría en la historia pública, dependencias sin hashes y base mutable (D-6), `Cache-Control` ausente en la página estática, límite de login global (P-40). Ver `docs/NIGHTLY-REVIEW.md` §4 y `docs/OVERNIGHT-RESULTS.md` | **Documentados** |
