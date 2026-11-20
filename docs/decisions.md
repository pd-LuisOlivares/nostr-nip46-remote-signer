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

## Fase 0.3: investigación y diseño de interoperabilidad NIP-46 (2026-11-20)

> **Cómo leer esta sección.** Cada elemento tiene un estado: **Aprobada** (el propietario la aprobó expresamente), **Aprobada provisionalmente**, **Propuesta** (hecha por Claude Code y **pendiente de aprobación**) o **Hipótesis** (afirmación **sin validar**, con el experimento que la resolvería). **Ninguna propuesta se declara aprobada.** Los fundamentos están en [nip46-protocol-analysis.md](nip46-protocol-analysis.md), [stacker-news-compatibility.md](stacker-news-compatibility.md), [nip46-security-design.md](nip46-security-design.md) y [nip46-implementation-plan.md](nip46-implementation-plan.md). La fase no modificó código, dependencias ni infraestructura y **no hubo conexión con relays ni con Stacker News**.

### Decisiones del propietario

| # | Decisión | Estado |
|---|---|---|
| O-1 | La investigación de la Fase 0.3 queda **aprobada provisionalmente**, sujeta a revisión final (2026-11-20). Aprueba la **investigación**, no las propuestas de implementación. | Aprobada provisionalmente |
| O-2 | Se autoriza **exclusivamente** la Fase 0.3 (investigación y diseño): sin implementar, sin dependencias nuevas, sin conexiones externas, sin claves, sin commits ni push. La Fase 1.0 **no** está iniciada. | Aprobada |
| O-3 | La decisión **`config/` frente a `core/`** (D8) se mantiene **pendiente** hasta que exista una necesidad real. | Aprobada |
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
