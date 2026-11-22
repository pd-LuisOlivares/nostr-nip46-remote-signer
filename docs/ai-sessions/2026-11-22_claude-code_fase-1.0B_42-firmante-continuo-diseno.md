# Interacción 42: Firmante continuo: análisis, diseño y alcance

| Campo | Valor |
|---|---|
| Fecha del primer prompt (UTC) | 2026-11-22T02:30:47.948Z (America/Santiago = UTC-3) |
| Fase | 1.0B |
| Agente | Claude Code (extensión de VS Code, versión 2.1.330) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 97ea8763-694e-4b53-8496-52b85c37bc64 |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con `tools/ai_sessions.py`; no reconstruido |
| Hasta (UTC) | 2026-11-22T02:35:18.475Z |
| Estado | PARCIAL (la sesión de origen sigue abierta: se reexporta al cerrarla) |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `pasted_content`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas **no** se incluyen (los archivos resultantes están en el repositorio y los resultados de las pruebas, en `docs/decisions.md`). **No se incluye razonamiento interno del modelo** ni contexto del sistema. Las marcas `<!-- fecha -->` son del archivo de sesión.

**Redacción aplicada** (patrones y lectura de los hallazgos): URI `bunker://`, claves `nsec`, secretos de conexión, JWT, tokens `Bearer`, hashes de contraseña, contraseñas, correos, rutas locales, usuario local y nombre del autor. Las cadenas hexadecimales de 64 caracteres se clasifican por contexto: se conservan las claves **públicas**, los identificadores y las huellas SHA-256 necesarios para entender la evidencia (revisadas una a una) y la exportación se detiene ante cualquier duda. La ruta absoluta del proyecto se acortó a ruta relativa. Redacciones en este archivo: ninguna.

---

## Prompt del propietario (2026-11-22T02:30:47.948Z)

El subpaso 3.4 terminó correctamente: PASS.

La aplicación está funcionando en Docker con la imagen `nostr-nip46-remote-signer:manual-b61d`, el contenedor está healthy, `/health` responde HTTP 200, la base SQLite fue reconocida y no existen conexiones externas ni actividad NIP-46.

Antes de continuar con B6.2, necesitamos revisar una decisión de arquitectura relacionada con la experiencia de uso final.

## Objetivo

La prueba técnica debe poder ejecutarse por un evaluador que clone el repositorio, levante Docker, configure su identidad Nostr y complete el inicio de sesión en Stacker News sin depender de que nosotros abramos una ventana temporal de autorización.

Actualmente tenemos `SIGNER_WINDOW_S=120` y `MAX_SIGNATURES=1`. Estos límites son útiles para una validación controlada, pero no deberían obligar al evaluador a repetir manualmente una operación temporal para utilizar el firmante.

Queremos que la aplicación pueda permanecer funcionando de forma continua y que el acceso administrativo esté protegido mediante JWT.

**Importante:** JWT protege las operaciones administrativas, pero no autoriza automáticamente las solicitudes recibidas mediante NIP-46. Necesitamos una política de autorización específica para el firmante.

## Trabajo solicitado: análisis, sin implementación

1. Revisa el flujo actual de autenticación administrativa, creación de identidad, conexión NIP-46 y autorización de firmas.
2. Identifica exactamente dónde se exige abrir una ventana temporal y qué ocurre cuando expira.
3. Propón el cambio mínimo para permitir conexiones NIP-46 persistentes, autorizadas previamente desde una sesión administrativa autenticada.
4. Evalúa cómo permitir el flujo de autenticación de Stacker News sin aprobar manualmente cada solicitud.
5. Propón una política restrictiva para solicitudes `sign_event` de tipo `kind: 27235`, incluyendo validación de contenido, destino, vigencia y prevención de reutilización cuando corresponda.
6. Mantén la posibilidad de revocar conexiones y rechazar operaciones no autorizadas.
7. Determina qué controles existentes podemos reutilizar y cuáles tendrían que cambiar.
8. Evalúa cómo evitar que un tercero pueda utilizar un enlace bunker filtrado para obtener firmas.
9. Identifica los cambios mínimos en código, pruebas, configuración y README.
10. Explica cómo conservar una experiencia sencilla para el evaluador sin ampliar innecesariamente el alcance de la prueba técnica.

## Restricciones

- No modifiques código, documentación ni configuración.
- No cambies la instancia Docker B6.2 que ya está funcionando.
- No detengas ni reinicies contenedores.
- No accedas al relay público ni a Stacker News.
- No inicies el firmante.
- No abras ventanas de autorización.
- No modifiques SQLite.
- No reconstruyas imágenes ni descargues dependencias.
- No hagas commit ni push.
- No establezcas T0.

## Entregable

Presenta una propuesta técnica breve con:

- Diagnóstico del comportamiento actual.
- Diseño mínimo recomendado.
- Controles de seguridad que se conservarían.
- Archivos que habría que modificar.
- Riesgos y mitigaciones.
- Plan de implementación y pruebas, dividido en pasos pequeños.

Indica expresamente si es posible reutilizar la validación B6.2 actual o si debemos preparar una nueva configuración después de implementar el cambio.

No implementes nada todavía. Espera mi aprobación.

<!-- 2026-11-22T02:30:49.868Z -->
Analizo el código actual del firmante, sin modificar nada. Empiezo por los servicios y la API.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

<!-- 2026-11-22T02:32:57.331Z -->
# Propuesta: firmante continuo con autorización previa

Es solo análisis: no modifiqué código, documentación, configuración ni la instancia Docker B6.2. No hubo accesos externos, no inicié el firmante y no hice commit ni push. No establecí T0.

## 1. Diagnóstico del comportamiento actual

**Dónde se exige abrir una ventana temporal.** No es una sola ventana. Son seis límites distintos:

| Límite (por defecto → B6.2) | Dónde actúa | Qué pasa al vencer |
|---|---|---|
| `SESSION_TTL_S` (3600 → 720) | `_watchdog`, [signer.py:148-150](app/services/signer.py#L148-L150) | La sesión se detiene: cierra el relay, cancela aprobaciones y **revoca todas las conexiones** ([signer.py:134](app/services/signer.py#L134)). |
| `CONNECTION_TTL_S` (1800 → 720) | [connections.py:67](app/services/connections.py#L67) | El cliente pasa a `REVOKED`, que es permanente. |
| `MAX_REQUESTS` (60 → 30) | [signer.py:196-200](app/services/signer.py#L196-L200) | **Termina la sesión** (`tope_de_solicitudes`). |
| `MAX_SIGNATURES` (1) | [signer.py:279-281](app/services/signer.py#L279-L281) y `_sign_once` | Rechaza toda firma posterior. Es un tope total, no por tiempo. |
| `APPROVAL_TTL_S` (120) más el plazo de P-38 | `_ask` y `_revalidate_and_sign` | La solicitud vence y se deniega. Hay que aprobar antes de `created_at + 121 s`. |
| `SECRET_TTL_S` (600) | `issue_secret` | La URI bunker caduca. Es de un solo uso y hay un máximo de 3 sin usar. |

**`SIGNER_WINDOW_S` (120) no es una ventana del operador.** Es la frescura permitida de `created_at`, y su vigencia máxima es el anti-replay. Debe conservarse.

**Qué ocurre al expirar.**
- El firmante pasa a `STOPPED` o `FAILED` y cierra la suscripción al relay.
- Ya no recibe nada: Stacker News ve un timeout.
- Hay que pulsar «Iniciar», emitir otra URI y aprobar de nuevo el `connect`.

**Por qué no persiste nada.**
- `SignerRuntime.start()` crea en cada arranque un `ConnectionManager`, un `ApprovalRegistry`, el conjunto de retos vistos y la clave de transporte.
- La clave Nostr vive solo en memoria (D-3).
- Hay **cero estado persistente** entre sesiones.

**Lo que ya sirve:**
- La política tiene 11 comprobaciones para `kind 27235`.
- La revalidación inmediata antes de firmar (P-38).
- La auditoría y la autoverificación de la firma.
- JWT con CSRF y CSP, la comprobación de `Host`, y las respuestas siempre en NIP-44.

## 2. Diseño mínimo recomendado

JWT sigue protegiendo solo la API administrativa. Para NIP-46 se añade una **autorización por conexión**, concedida por el administrador autenticado y no solicitada por el cliente:

1. **Un modo `SIGNER_MODE=supervised|continuous`**, con `supervised` por defecto. En ese modo todo queda como hoy (B6.2, manual, una firma, 15 min). El modo `continuous` cambia lo siguiente:
   - Sin `_watchdog` por tiempo.
   - `MAX_REQUESTS` deja de terminar la sesión y pasa a ser un límite por minuto y por cliente (nuevo `REQUESTS_PER_MIN`).
   - El tope total de firmas se sustituye por un límite móvil (nuevo `AUTO_SIGN_PER_HOUR`, por conexión).
2. **Estado del runtime, no de la sesión.** `SignerRuntime` conserva la clave de transporte, el `ConnectionManager` y los retos vistos durante la vida del proceso. Así una caída del relay o un «Iniciar» manual no obliga a repetir el emparejamiento. En `continuous` solo se revoca todo al pulsar «Detener» o al reiniciar el proceso. Los retos vistos se guardan con límite de tamaño y vigencia.
3. **Concesión de firma por conexión.** Es una pregunta en la tarjeta de `connect`, que **sigue siendo humana**: «¿Permitir firmar automáticamente el login de Stacker News?». Si se acepta, la conexión queda con `auto_sign=True` solo para `kind 27235`, con vigencia absoluta. El `kind` no es configurable y es una constante.
4. **Firma automática.** En `_on_sign`, si la conexión está activa, tiene la concesión, la política pasa **las 11 comprobaciones**, no supera su límite horario y la revalidación P-38 sigue pasando, se firma sin tarjeta. Si algo falla, se deniega como ahora y la solicitud no se ofrece a nadie.
5. **Revocación.** Cada conexión recibe un identificador aleatorio opaco, porque el prefijo de 8 caracteres puede colisionar. Habrá `DELETE /api/connections/{id}`, que exige JWT y CSRF, y «Detener» revoca todo.
6. **Identidad.** No se persiste la clave privada (sigue D-3). Tras reiniciar el contenedor, el evaluador la importa de nuevo.

## 3. Política para `sign_event` con `kind: 27235`

- **Se conservan las 11 comprobaciones:**
  - tamaño ≤ 1024 B y esquema cerrado
  - `kind` 27235
  - `pubkey` e `id` coherentes
  - `created_at` entre −30 s y +120 s
  - exactamente tres etiquetas (`challenge`, `u`, `method`), reto de 64 hex
  - `u` igual al origen exacto
  - `method=GET`
  - contenido «Stacker News Authentication»
  - reto no repetido
- **Frescura en modo automático:** ventana de 60 s, con la misma revalidación al instante de firmar.
- **Anti-replay:** el conjunto de retos vistos persiste durante el proceso, ya no solo durante la sesión.
- **Límites por conexión:** `AUTO_SIGN_PER_HOUR` (propuesta: 6) y un intervalo mínimo entre firmas de unos segundos.
- **Auditoría:** cada firma automática deja `decision reason=auto_politica` con `client8` y `challenge_sha16`, sin secretos.
- **Cualquier otro método o `kind`** sigue rechazado. No hay comodines.

Una firma `27235` sobre un reto reciente de Stacker News equivale a iniciar sesión como el usuario. Por eso, **quien controla un cliente activo es quien puede iniciar sesión**. La política no puede comprobar que el reto lo emitió Stacker News para ese navegador, y hacerlo exigiría una llamada externa. La defensa es el emparejamiento humano, la revocación, la caducidad y los límites.

## 4. URI bunker filtrada

- **Se conserva:** el secreto de 128 bits se guarda como hash, es de un solo uso (se gasta aunque se deniegue), caduca, hay un máximo de 3 sin usar, se muestra una sola vez y nunca se registra. Un cliente desconocido solo puede enviar `connect`. El `connect` sigue necesitando aprobación humana.
- **Qué cubre eso:** una URI ya usada no sirve. Si un atacante se conecta primero, el cliente legítimo recibe `unauthorized` y el operador lo nota. Así el atacante solo logra una tarjeta pendiente que alguien tiene que aprobar.
- **Endurecimiento propuesto:**
  - Bajar `SECRET_TTL_S` a 300 s en modo continuo.
  - Mostrar en la tarjeta de `connect` hace cuánto se emitió la URI.
  - Admitir una sola tarjeta de `connect` pendiente a la vez, auto-denegando las demás.
- **No se haría ninguna URI reutilizable.** Si Stacker News crea una clave de cliente nueva en cada login, cada login necesitará una URI nueva y un clic de aprobación. Eso es aceptable.

## 5. Controles reutilizables y los que cambian

- **Se reutilizan sin cambios:** la política, P-38, la auditoría, la autoverificación, el transporte NIP-44, JWT, CSRF y CSP, y el registro de aprobaciones para `connect`.
- **Cambian:**
  - `signer.py` (`_on_sign`, `_shutdown`, `run`)
  - `connections.py` (concesión, identificador, revocación individual)
  - `runtime.py` (propiedad del estado entre arranques)
  - `config.py` (nuevas variables validadas)
  - `schemas/control.py` y `api/control.py` (aprobación con concesión y revocación)
  - `app/static/*` (casilla, lista y botón de revocar)

## 6. Cambios mínimos por área

- **Código:** los archivos de §5.
- **Configuración:** `SIGNER_MODE`, `AUTO_SIGN_PER_HOUR` y `REQUESTS_PER_MIN`, reenviados en `compose.yaml`. Perfiles: `deploy/b62.env` queda tal cual y se crea `deploy/continuous.env`, ambos sin secretos. Se actualiza `.env.example`.
- **Documentación:** README (§7 y §10) y una nueva decisión D-17.
- **Pruebas:**
  - Unitarias: concesión, límite horario, anti-replay persistente, revocación, el modo `supervised` intacto y un reloj inyectado que demuestre que no hay corte a los 15 min ni a las 24 h.
  - API: JWT y CSRF obligatorios, revocación y aprobación con concesión.
  - Mutaciones: cliente no emparejado, `kind` distinto, `u` ajeno, reto repetido, firma tras revocar, URI usada dos veces.
  - Regresión NDK real (E1/E2/E3/E8) más un escenario de firma automática.
  - E2E de navegador y de Docker.

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Se relaja una decisión previa**: B4 decidió «aprobación humana por solicitud». | D-17 la sustituye de forma explícita y solo para `27235`, con emparejamiento humano. Requiere tu aprobación. |
| Un cliente activo comprometido puede iniciar sesión como el usuario. | Caducidad absoluta de la concesión, revocación individual, límite horario y auditoría. |
| Crecimiento de memoria de retos y conexiones. | Límites de tamaño y vigencia; ya existe `MAX_CLIENTS`. |
| Si el relay cierra la conexión, el firmante queda `FAILED` sin reconexión automática. | El estado persiste en el runtime, así que basta un «Iniciar» sin volver a emparejar. Una reconexión con backoff acotado es opcional y no se hace en el mínimo. |
| **Supuesto no verificado:** cómo se comporta Stacker News en logins posteriores (¿reutiliza la clave de cliente o la URI?). | Solo se observó un login en B4. Se comprueba en la validación real y se documenta. |
| La clave sigue solo en memoria. | Se documenta que tras reiniciar hay que importarla de nuevo. Persistirla cifrada exigiría una clave externa y queda fuera del alcance. |

## 8. Plan de implementación y pruebas

Cada paso tiene su prueba y espera tu aprobación:
1. Configuración y validación de las nuevas variables.
2. Estado en el runtime (clave de transporte, conexiones y retos) y el modo continuo sin corte por tiempo.
3. Concesión por conexión, firma automática bajo la política, límites y auditoría.
4. Revocación individual por API y por interfaz.
5. Regresión NDK real con el escenario de firma automática.
6. README, decisión D-17, perfiles y E2E de Docker.

## 9. ¿Se puede reutilizar la validación B6.2 actual?

- **Se reutiliza:** la infraestructura Docker preparada, la base importada, el procedimiento, la matriz B y las restricciones. El modo `supervised` conserva exactamente la configuración de hoy.
- **No sirve como validación del producto final.** La imagen `manual-b61d` coincide con el `app/` actual, pero tras este cambio el código será otro. Una validación real con esa imagen probaría el código anterior, no el entregable.
- **Recomendación:** no ejecutar B6.2 ahora. Implementar primero, reconstruir la imagen (con tu autorización para acceder a Docker Hub y PyPI) y hacer **una única** validación real con el código final, empezando por el perfil `supervised` y después el `continuous`. Cada una necesita su alcance de autorización, porque `MAX_SIGNATURES=1` y los 15 minutos eran términos de la autorización actual.
- **Alternativa:** ejecutar B6.2 ahora con la imagen actual como evidencia de la ruta supervisada, y una validación adicional más tarde para el modo continuo. Costaría dos pruebas reales.

La instancia B6.2 actual en Docker sigue como está y puede dejarse en marcha, sin firmante.

Espero tu aprobación del diseño para empezar por el paso 1. Si lo apruebas, solicito también tu decisión sobre la recomendación del punto 9.

## Prompt del propietario (2026-11-22T02:34:02.516Z)

Revisé tu propuesta de firmante continuo.

**Apruebo la dirección general de la arquitectura, con ajustes, pero todavía no autorizo implementar todo el diseño.**

Decisiones:

1. Conservamos `SIGNER_WINDOW_S` como control de frescura y anti-replay. Entiendo que no corresponde a una ventana manual del operador.

2. Adoptaremos un modo continuo que permita mantener el firmante disponible sin detenerlo automáticamente por el TTL de sesión.

3. JWT seguirá protegiendo las operaciones administrativas. La autorización NIP-46 se gestionará por conexión, mediante un emparejamiento aprobado por el administrador autenticado.

4. Permitiremos firma automática exclusivamente para eventos de autenticación de Stacker News `kind: 27235` que superen la política restrictiva y la revalidación inmediata.

5. Conservaremos controles de revocación, límites por conexión, auditoría, protección anti-replay y rechazo de operaciones no autorizadas.

6. No persistiremos claves privadas en esta etapa. Documentaremos que reiniciar el proceso requiere volver a cargar la identidad.

7. El modo continuo debe ser la experiencia principal descrita en el README para el evaluador, sin depender de configuraciones ocultas o procedimientos manuales de nuestra parte.

8. No ejecutaremos ahora la validación real B6.2 sobre la imagen antigua. Validaremos Stacker News cuando el código final esté implementado y probado en Docker.

**Antes de implementar, necesito que aclares tres aspectos:**

- ¿Cómo funcionará la renovación o caducidad de una conexión autorizada sin obligar a repetir continuamente el emparejamiento?
- ¿Qué ocurre exactamente cuando el relay pierde conexión? ¿Podemos incorporar una reconexión automática sencilla y acotada sin ampliar demasiado el alcance?
- ¿Cuál será el procedimiento mínimo que seguirá el evaluador desde `docker compose up` hasta iniciar sesión en Stacker News? Identifica todos los clics y aprobaciones necesarios.

También necesito que propongas valores predeterminados razonables para `REQUESTS_PER_MIN`, `AUTO_SIGN_PER_HOUR` y la vigencia absoluta de la autorización, indicando qué sucede al alcanzar cada límite.

No modifiques todavía código, configuración, documentación, SQLite ni la instancia Docker en funcionamiento.

No realices conexiones externas, reconstrucciones, commits ni push.

Entrega estas aclaraciones y una propuesta definitiva de alcance mínimo. Espera mi aprobación antes de implementar.

<!-- 2026-11-22T02:34:04.700Z -->
Reviso el transporte al relay y los controles de la interfaz para que los conteos de clics y la viabilidad de la reconexión sean exactos.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T02:35:18.475Z -->
# Aclaraciones y alcance mínimo definitivo

Es solo análisis. No modifiqué código, configuración, documentación, SQLite ni la instancia Docker. No hice conexiones externas, reconstrucciones, commits ni push. No establecí T0.

## 1. Caducidad y renovación sin repetir el emparejamiento

La autorización de una conexión tiene **una sola vigencia absoluta**, `CONNECTION_TTL_S`. En modo continuo vale **8 h por defecto**.

| Situación | Qué ocurre |
|---|---|
| La conexión vence | Pasa a `EXPIRED`, un estado distinto de `REVOKED`. El cliente recibe `unauthorized`. El panel la muestra como «Caducada» con **Renovar** y **Revocar**. |
| El administrador pulsa **Renovar** | La vigencia se reinicia desde ahora, con la **misma** clave de cliente y la misma concesión. No hay URI nueva ni emparejamiento nuevo. Es una acción autenticada con JWT y CSRF. |
| Renovación automática por uso | **No existe**. Un cliente comprometido la mantendría viva para siempre. |
| La conexión está `REVOKED` o `DENIED` | Es terminal: no se renueva y hay que emparejar de nuevo. |
| Vence el JWT del administrador (15 min) | No afecta al firmante ni a las conexiones. Solo hay que volver a iniciar sesión para administrar. |

Mientras el proceso esté vivo, las conexiones persisten porque el runtime las conserva (ver §2).

## 2. Qué pasa cuando el relay pierde conexión

**Hoy:** `messages()` termina, el estado pasa a `FAILED` (`el_relay_cerro_la_conexion` o `relay_no_disponible`) y `_shutdown` **revoca todas las conexiones**. Hay que pulsar «Iniciar», emitir otra URI y aprobar de nuevo. `WebsocketRelay` es de un solo uso (`"el transporte ya se uso"`).

**Reconexión acotada: sí es sencilla, y la incluyo en el alcance.** Solo se aplica en modo continuo. El modo supervisado sigue sin reintentos, como exige B6.2.
- Un supervisor en `SignerRuntime` crea un transporte nuevo con la `relay_factory` existente tras una desconexión.
- **Backoff fijo, sin variables de entorno nuevas:** 2, 5, 10, 20 y 40 s, es decir 5 intentos en unos 77 s. El contador se reinicia tras 60 s en estado `READY`.
- **No se reintenta** en estos casos: «Detener» del operador, `AUTH` del relay (NIP-42), `CLOSED` de la suscripción o un error de configuración TLS.
- Si se agotan los intentos, el estado pasa a `FAILED` y las **conexiones se conservan**. Un «Iniciar» las reanuda sin emparejar otra vez.
- Nuevo estado visible `reconnecting` (intento n de 5) y eventos de auditoría `relay_reconnect`.
- Se conserva la clave de transporte, porque un cambio rompería las URI ya emitidas.
- La nueva suscripción usa `since = ahora − SIGNER_WINDOW_S`. Lo ocurrido durante la caída más allá de 120 s se pierde y el cliente verá un timeout.
- Las aprobaciones pendientes se cancelan.
- Los conjuntos de eventos, solicitudes y retos vistos pasan al runtime, con tamaño acotado, para no reprocesar duplicados del relay.
- **Reglas de «Detener»:** una parada manual revoca todo; un fallo del relay conserva las conexiones.

## 3. Procedimiento mínimo del evaluador

**Terminal:** clonar el repositorio, definir `ADMIN_PASSWORD` con entrada oculta y ejecutar `docker compose up --build -d`.

**Panel (`http://127.0.0.1:8000`):**

| # | Acción | Clics |
|---|---|---|
| 1 | Iniciar sesión (usuario y contraseña) | 1 |
| 2 | **Crear identidad temporal** (sin tocar ninguna clave), o pegar su `nsec` e **Importar** | 1 (o 2) |
| 3 | **Iniciar firmante** | 1 |
| 4 | **Emitir URI de un solo uso** y **Copiar** | 2 |
| 5 | En Stacker News: login → «Continue with Nostr» → bunker → pegar y enviar. Es externo, y las etiquetas exactas **no están verificadas** hoy | — |
| 6 | En el panel aparece «Conexión de un cliente» con la casilla «Permitir firmar automáticamente el login de Stacker News» → **Aprobar** | 1 |
| 7 | Stacker News pide `sign_event`: se **firma automáticamente**. El panel lo registra como «Firmada automáticamente» | 0 |

- **Total:** 6 clics en el panel y exactamente una aprobación humana, el emparejamiento. No hay ninguna aprobación por firma.
- **Plazos que sí existen:** pegar la URI antes de `SECRET_TTL_S` (300 s) y aprobar antes de `APPROVAL_TTL_S` (300 s). Ya no hay límite de 15 minutos ni de una firma.
- **Logins posteriores:** si Stacker News conserva su clave de cliente mientras la autorización siga vigente, no hay clics adicionales. Si genera una clave nueva en cada login, hay que emitir otra URI y aprobar otra vez (3 clics). Esto **no está verificado** y se comprobará en la validación real.
- **Con identidad temporal:** el login crea una cuenta nueva en Stacker News, porque la cuenta depende de la clave pública, y otra tras cada reinicio del proceso. Para usar una cuenta existente hay que importar la clave.
- **Reiniciar el proceso:** la identidad y las conexiones desaparecen y hay que repetir los pasos 2 a 6.

## 4. Valores predeterminados propuestos

Son los de `SIGNER_MODE=continuous`. Una variable explícita los reemplaza.

| Parámetro | Valor | Al alcanzar el límite |
|---|---|---|
| `REQUESTS_PER_MIN` (por conexión, ventana móvil de 60 s; rango 1–120) | **30** | La solicitud se **descarta** con un error genérico al cliente. No termina la sesión ni revoca. Hay una auditoría `rate_limited` como máximo una vez por minuto, para no inundar el registro. Se libera sola. |
| Tope global del firmante (constante, 120/min) | **120** | Las solicitudes de clientes sin conexión se descartan sin descifrar, con una auditoría por minuto. |
| `AUTO_SIGN_PER_HOUR` (por conexión, ventana móvil de 3600 s; rango 1–60) | **6** | Se responde `unauthorized` con auditoría `limite_horario`. El panel muestra el tiempo hasta que se libere. No termina la sesión ni revoca. |
| Intervalo mínimo entre firmas (constante) | **5 s** | La segunda solicitud se rechaza con `intervalo_minimo` y se puede repetir pasados esos segundos. |
| `CONNECTION_TTL_S` (vigencia absoluta, en continuo) | **28800 (8 h)** | La conexión pasa a `EXPIRED`; el administrador puede renovarla o revocarla (§1). |
| `SECRET_TTL_S` | **300** | La URI caduca. Se emite otra. |
| `APPROVAL_TTL_S` | **300** | La tarjeta vence y se deniega. El cliente puede volver a intentarlo con una URI nueva. |

En continuo se ignoran `SESSION_TTL_S`, `MAX_REQUESTS` y `MAX_SIGNATURES`. En supervisado conservan su significado actual.

## 5. Alcance mínimo definitivo

**Incluido**
1. **Configuración:** `SIGNER_MODE`, `REQUESTS_PER_MIN` y `AUTO_SIGN_PER_HOUR`, con sus rangos validados y los valores por defecto de §4. Se reenvían en `compose.yaml`, `deploy/b62.env` fija `SIGNER_MODE=supervised` y se actualiza `.env.example`.
2. **Estado en el runtime:** clave de transporte, conexiones y conjuntos de eventos, solicitudes y retos vistos, todos acotados, más el ciclo de vida continuo sin corte por tiempo.
3. **Concesión de firma por conexión** solo para `kind 27235`, con la política restrictiva, la revalidación P-38 y los límites de §4. La política de frescura en automático es de 60 s, y la auditoría deja `auto_politica`.
4. **Caducidad, renovación y revocación individual** con identificador opaco, por API y panel.
5. **Reconexión acotada** (§2).
6. **README** con el modo continuo como camino principal, la decisión D-17 y las pruebas (NDK real, E2E de navegador y de Docker).

**Excluido:** persistir claves o conexiones entre reinicios, `nostrconnect://`, otros `kind`, URI reutilizables, renovación deslizante, varios usuarios y rediseño de la interfaz.

## 6. Decisiones que necesito de ti

1. **Valor predeterminado.** Propongo que `Settings.from_env` use `continuous` por defecto, con el mismo comportamiento en Docker y en Uvicorn. El dataclass `Settings()` seguiría en `supervised` para no alterar las pruebas existentes, aunque habría que actualizar las expectativas de `tests/test_config.py`. El perfil de B6.2 fijaría `supervised`. La alternativa es dejarlo solo en `compose.yaml`, pero crearía dos valores por defecto distintos.
2. **Casilla de firma automática.** Propongo que aparezca **marcada por defecto** en la tarjeta de `connect`, con texto explícito, en modo continuo. Desmarcada obligaría a una aprobación por firma.
3. **Reconexión.** Confirma si la incluyes en el alcance mínimo; mi recomendación es que sí.
4. **Valores** de §4, si quieres cambiar alguno.
5. **Identidad temporal** como camino principal del README, con la importación como alternativa.

Espero tu aprobación del alcance antes de empezar el paso 1.
