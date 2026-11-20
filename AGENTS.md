# AGENTS.md — Instrucciones para agentes de IA

Fuente compartida de reglas para todos los agentes de IA (Codex, Claude Code u otros) que trabajen en este repositorio. `CLAUDE.md` referencia este archivo y solo añade particularidades operativas de Claude Code. Si hay conflicto, prevalece la instrucción explícita del propietario del proyecto, y después este archivo.

## 1. Contexto, objetivo y alcance

- **Contexto:** prueba técnica para la Secretaría de Gobierno Digital del Ministerio de Hacienda de Chile.
- **Proyecto:** firmante remoto (*remote signer*) Nostr conforme a **NIP-46**, en Python.
- **Objetivo obligatorio:** demostrar una **autenticación real con Stacker News** usando el firmante remoto.
- **Alcance:** solo lo necesario para cumplir ese objetivo con calidad, seguridad y reproducibilidad. Todo lo demás está fuera de alcance salvo petición explícita.
- **Estado inicial (Fase 0.1):** el repositorio solo contiene `README.md` y `.gitignore`. No existe código. Antes de asumir que algo existe, verifícalo en el repositorio.

## 2. Stack previsto

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| API / backend | FastAPI |
| Frontend | HTML, CSS y JavaScript (sin frameworks pesados salvo justificación documentada) |
| Persistencia | SQLite |
| Despliegue | Docker Compose |
| Pruebas | pytest |

El stack es el *previsto*: no se instala ni se crea nada de él hasta que la fase correspondiente lo autorice. Cambiar de tecnología requiere autorización y registro en `docs/decisions.md`.

## 3. Prioridad absoluta: interoperabilidad NIP-46 con Stacker News

- La interoperabilidad real con Stacker News tiene prioridad sobre cualquier otra mejora, optimización o funcionalidad adicional.
- Implementa NIP-46 según la especificación oficial (repositorio `nostr-protocol/nips`) y verifica contra ella; no la reconstruyas de memoria. Registra la versión/fecha de la especificación consultada.
- No asumas cómo Stacker News realiza el login ni qué métodos, cifrado (NIP-44 / NIP-04), URIs (`bunker://`, `nostrconnect://`) o relays espera: **compruébalo** con documentación o comportamiento observado y documenta el hallazgo.
- Una prueba automatizada que pasa **no demuestra** interoperabilidad. Solo cuenta como validada una autenticación real contra Stacker News, ejecutada y documentada con evidencia (ver §10).

### JWT y NIP-46 son cosas distintas
- **JWT** autentica sesiones de la **API local**, cuando esa funcionalidad esté implementada.
- **NIP-46** permite la comunicación y autorización entre aplicaciones Nostr y un firmante remoto.
- **JWT no reemplaza a NIP-46** ni se usa como sustituto del flujo de firma remota.
- Una autenticación local exitosa (JWT, sesión de la API) **no demuestra** una autenticación exitosa en Stacker News.
- La **prueba de integración real con Stacker News** sigue siendo el criterio funcional principal del proyecto.

## 4. Arquitectura

- **Modular, con separación de responsabilidades.** Capas sugeridas (a confirmar en el plan de cada fase):
  - `api` / rutas HTTP: solo validación de entrada, serialización y delegación; sin lógica de negocio.
  - `services` / dominio: lógica de negocio y casos de uso.
  - `nip46` / `nostr`: protocolo (eventos, cifrado, firma, transporte a relays) aislado e independiente de FastAPI.
  - `storage` / repositorios: acceso a SQLite detrás de una interfaz; ningún SQL fuera de esta capa.
  - `security` / `auth`: gestión de claves, sesiones/tokens y autorización.
  - `config`: lectura y validación de variables de entorno en un único punto.
- El código del protocolo Nostr no debe importar FastAPI ni la capa HTTP. Las dependencias fluyen hacia el dominio, no al revés.
- Prefiere inyección de dependencias (p. ej. `Depends` de FastAPI) para facilitar pruebas con dobles.
- Evita sobreingeniería: la solución más simple que cumpla el requisito y sea correcta.

## 5. Convenciones de código

- Python 3.12, con **tipado estático completo** en funciones públicas (`mypy`/`pyright` limpio cuando se configure). Sin `Any` injustificado.
- Formato y lint con la herramienta que se acuerde en la fase de configuración (se propone `ruff`); no mezclar estilos.
- Nombres en inglés en el código; documentación y comentarios de propósito en español o inglés, de forma consistente por archivo.
- Funciones pequeñas, con una responsabilidad. Sin código muerto ni comentarios que repitan lo que hace el código.
- **Manejo de errores:**
  - Define excepciones de dominio propias; no uses `except:` ni `except Exception:` sin relanzar o registrar con motivo.
  - Los errores hacia el cliente son genéricos y estables (sin trazas, rutas internas, ni detalles criptográficos); el detalle técnico va a logs **sin datos sensibles**.
  - Falla de forma segura: ante duda en validación o verificación de firma, rechaza.
  - Tiempos de espera y reintentos acotados en toda comunicación de red (relays, Stacker News).
- Usa `async` de forma coherente; no bloquees el *event loop* con E/S síncrona.

## 6. Pruebas (pytest)

- Toda funcionalidad nueva incluye pruebas; todo bug corregido incluye una prueba de regresión.
- Estructura `tests/` espejo de la estructura del código. Pruebas determinísticas, sin depender de red ni de relays reales (usa dobles/fixtures).
- Usa **vectores de prueba oficiales** de NIP-44/NIP-01/BIP-340 cuando existan.
- Cubre rutas de error y casos límite (entradas malformadas, firmas inválidas, tokens expirados, accesos no autorizados), no solo el camino feliz.
- Las claves usadas en pruebas son **generadas para la prueba o claramente de juguete**; nunca claves reales.
- **Obligación:** ejecuta la suite relevante antes de dar una tarea por terminada y reporta el comando exacto y el resultado real (pasaron/fallaron/omitidas). Si no pudiste ejecutarla, dilo explícitamente y explica por qué.

## 7. Seguridad

### Claves privadas Nostr
- Nunca en texto plano en base de datos, logs, respuestas HTTP, mensajes de error, URLs ni código fuente.
- Si el diseño exige persistirlas, debe hacerse **cifradas en reposo** con una clave de cifrado externa al repositorio (variable de entorno/secret) y con el esquema documentado en `docs/decisions.md`.
- Mantén su manipulación confinada a un módulo mínimo y auditable; minimiza el tiempo que permanecen en memoria y evita copiarlas.
- Usa bibliotecas criptográficas establecidas; **no inventes criptografía propia**. Comparaciones de secretos en tiempo constante.

### Secretos y credenciales
- **Prohibido incorporar credenciales reales al repositorio**: claves privadas (`nsec`, hex), tokens, secretos JWT, contraseñas, claves API, cookies de sesión de Stacker News, ni siquiera en historial, ejemplos, pruebas, fixtures o documentación.
- Solo se versiona un `.env.example` con **valores ficticios** y claramente marcados.
- Si detectas un secreto real en el repositorio o en una salida, **detente, avisa al usuario** y no lo propagues (no lo copies en respuestas, logs ni documentación).
- Archivos de base de datos SQLite, `.env` y volúmenes de datos no se versionan (ver supuestos pendientes sobre `.gitignore`).
- **Archivos `.env`:** por defecto, **no los leas ni los imprimas**. Trabaja siempre con `.env.example`. Única excepción, limitada:
  - Solo cuando el propietario autorice explícitamente una verificación concreta (p. ej. "comprueba que `X` esté definida").
  - Inspecciona **exclusivamente** los nombres de las claves o la presencia de las variables necesarias (p. ej. con una comprobación que devuelva solo "definida/no definida").
  - **No imprimas, copies, registres ni expongas valores**, ni en respuestas, logs, documentación o transcripciones.
  - La autorización para revisar una variable **no** autoriza a acceder a otras variables ni a otros secretos, y no se extiende a verificaciones posteriores.

### Logs
- **Prohibido registrar** secretos, tokens (JWT, de sesión, de acceso), claves privadas, contenido descifrado de mensajes NIP-46, cabeceras `Authorization`, cookies ni datos personales sensibles.
- Si hay que referenciar una clave pública o un identificador, hazlo truncado/ofuscado. Usa identificadores de correlación en vez de datos.
- Configura los logs de bibliotecas (uvicorn, httpx, websockets) para que no vuelquen cabeceras ni cuerpos.

### Validación, autenticación y autorización
- Valida **toda** entrada externa (HTTP, relays, eventos Nostr, parámetros de URL) con modelos Pydantic estrictos: tipos, longitudes, formatos (hex, bech32, URIs), rangos.
- Verifica firma, `id`, `kind`, `pubkey` y marcas de tiempo de los eventos Nostr recibidos; rechaza eventos inválidos o repetidos (*replay*).
- Autenticación de la API local con JWT (distinta de NIP-46, ver §3): algoritmo fijado explícitamente (nunca aceptar `none`), expiración corta, validación de `exp`/`iss`/`aud`, secreto desde variable de entorno.
- Autorización explícita en cada endpoint: un usuario solo accede a sus propios recursos y permisos de firma. Denegar por defecto.
- Consultas SQL siempre parametrizadas. Protección de la interfaz web (CORS restrictivo, cabeceras de seguridad, sin `innerHTML` con datos no confiables, límite de tasa en endpoints sensibles).
- Los permisos de firma (qué `kind` de evento puede firmar cada cliente) deben ser explícitos y mínimos.

## 8. Dependencias y configuración

- **Dependencias:** mínimas, mantenidas y justificadas. Para cada una indica propósito, alternativa en la biblioteca estándar, licencia, estado de mantenimiento y consideraciones de seguridad. Fija versiones (archivo de dependencias con versiones y, si es posible, *hashes*/lockfile).
- **Autorización por fase:** el plan de una fase puede incluir un conjunto de paquetes que el propietario apruebe de antemano. Una vez aprobado ese plan, el agente puede instalar **esas** dependencias sin pedir aprobación individual por paquete. Requieren **nueva autorización** cualquier dependencia adicional, cambio de versión significativo (p. ej. de versión mayor) o sustitución de un paquete fuera del plan aprobado. Sin plan aprobado, no se instala nada.
- **Configuración:** exclusivamente mediante **variables de entorno**, leídas y validadas en un único módulo `config`. Sin valores sensibles por defecto en el código. Falla al arrancar si falta una variable obligatoria.
- Mantén `.env.example` sincronizado con las variables realmente usadas, con valores ficticios.

## 9. Documentación y registro

- **Decisiones técnicas y supuestos:** registra cada decisión relevante (qué, por qué, alternativas descartadas) y cada supuesto en `docs/decisions.md`. Un supuesto no verificado debe marcarse como tal.
- **Registro de interacciones con agentes de IA:** se conserva el registro **completo**, no solo resúmenes. Consta de:
  - `docs/ai-log.md`: índice con una entrada por interacción relevante: fecha, agente, modelo, nivel de razonamiento (cuando esté disponible), objetivo, resumen del resultado, archivos afectados, resultados de pruebas, y las correcciones, decisiones y autorizaciones humanas relevantes. Cada entrada enlaza a su transcripción.
  - `docs/ai-sessions/`: transcripciones **completas** (prompts enviados a Codex o Claude Code y respuestas completas de los agentes), un archivo por sesión o interacción, con nombre `AAAA-MM-DD_<agente>_<fase>_<tema>.md` y un encabezado con fecha, agente, modelo y nivel de razonamiento (o "no disponible").
  - **Exportación:** usa el mecanismo de exportación del propio agente cuando exista (p. ej. el comando de exportación de la sesión o los archivos de sesión locales de Claude Code o Codex; verifica su ubicación y formato reales, no los supongas) o copia manualmente los prompts y respuestas. El propietario puede aportar las transcripciones si el agente no puede acceder a ellas.
  - **Veracidad:** no inventes ni reconstruyas de memoria transcripciones, y no afirmes que se exportó una sesión que no se pudo recuperar. Si no es recuperable, indícalo en `docs/ai-log.md` como "transcripción no recuperada", con el motivo, y conserva al menos el resumen.
  - **Redacción previa obligatoria:** antes de guardar o versionar una transcripción, redacta secretos, credenciales, claves privadas, tokens, cookies y datos personales sensibles, sustituyéndolos por marcadores del tipo `[REDACTADO:tipo]`. Revisa el archivo resultante de forma directa antes de darlo por listo. No dejes copias sin redactar dentro del repositorio. Si dudas de que una transcripción esté limpia, no la guardes y avisa al propietario.
  - Los archivos de `docs/ai-sessions/` se crean y actualizan como cualquier otro archivo: sin commit sin autorización (§11).
- **README y guías:** deben permitir a un tercero instalar, configurar, ejecutar, probar y reproducir la demostración con Stacker News desde cero. Mantenlos al día con cada cambio.
- Escribe documentación clara, sin jerga innecesaria, con comandos copiables.
- No elimines ni sobrescribas documentación existente sin justificarlo y sin que el usuario lo sepa.

## 10. Reglas de trabajo para todos los agentes

1. **Revisar antes de modificar:** lee el código y la documentación existentes relacionados con la tarea antes de cambiarlos. No asumas.
2. **Plan breve primero** ante cambios importantes (nuevos módulos, cambios de arquitectura, dependencias, seguridad, esquema de datos). Espera conformidad del usuario si el cambio es significativo.
3. **Incremental y por fases:** respeta las fases definidas por el propietario del proyecto. No adelantes trabajo de fases futuras ni avances a la siguiente fase sin autorización explícita.
4. **Sin funcionalidades fuera de alcance:** implementa solo lo solicitado. Si ves mejoras posibles, propónlas por escrito en lugar de implementarlas.
5. **No afirmar sin comprobar:** no digas que algo funciona, compila o pasa pruebas si no lo ejecutaste. Si no pudiste verificarlo, dilo.
6. **Distinguir tipos de validación**, en cualquier informe:
   - *Prueba automatizada* (pytest, con dobles, sin red).
   - *Validación manual local* (app corriendo localmente).
   - *Validación real con Stacker News* (autenticación efectiva contra el servicio real, con evidencia: fecha, pasos, resultado).
   Nunca presentes las dos primeras como si fueran la tercera.
7. **Informar** riesgos, limitaciones, supuestos y decisiones relevantes de forma proactiva y concisa.
8. **Documentación comprensible y reproducible** como parte de cada entrega, no como tarea posterior.
9. **Ejecutar pruebas y reportar resultados** (comando, salida resumida, fallos) al cerrar cada tarea.
10. **Ante la duda sobre seguridad o alcance, pregunta** en lugar de decidir por tu cuenta.

## 11. Control de versiones y acciones destructivas

- **Prohibido** realizar `git commit`, `git push`, `git merge`, `git rebase`, `git reset --hard`, `git clean`, borrado de ramas, reescritura de historial, ni borrar/sobrescribir archivos de forma masiva **sin autorización explícita del usuario** para esa acción concreta. Una autorización previa no se extiende a acciones posteriores.
- Antes de cualquier borrado o sobrescritura, inspecciona el objetivo y confírmalo.
- Al terminar una tarea, deja el árbol de trabajo para revisión: ejecuta `git diff --check` y `git status` (ambos obligatorios) y reporta su resultado.
- **Archivos nuevos sin rastrear:** `git diff` y `git diff --check` **no los incluyen** por defecto, así que una salida vacía no demuestra que estén limpios. Para esos archivos, inspecciona directamente su contenido y revisa su formato (espacios finales, saltos de línea, codificación) antes de darlos por buenos. **No uses `git add` automáticamente** solo para hacerlos visibles en un diff; si necesitas comparar, usa copias previas o `git diff --no-index`.
- No modifiques `.gitignore` ni historial salvo que la tarea lo pida; propón el cambio y justifícalo.
- **Servicios externos con efectos** (publicar eventos en relays, autenticarte en Stacker News, etc.): prohibido sin autorización explícita del propietario. El propietario puede autorizar una **sesión de pruebas de integración con alcance definido**, que debe especificar:
  - el servicio externo o los relays a utilizar;
  - la identidad o cuenta **de prueba** autorizada (nunca una cuenta personal o real no designada);
  - las operaciones permitidas;
  - la duración o los límites de la sesión;
  - las restricciones aplicables.

  Si falta alguno de estos puntos, pídelo antes de actuar. Una autorización de pruebas **no habilita automáticamente** operaciones futuras ni acciones fuera de su alcance: al terminar la sesión o salirte de lo autorizado, vuelve a pedir autorización. Registra en `docs/ai-log.md` el alcance autorizado y lo realmente ejecutado.
